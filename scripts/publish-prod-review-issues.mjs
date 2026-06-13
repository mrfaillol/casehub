#!/usr/bin/env node

import childProcess from "child_process";
import crypto from "crypto";
import fs from "fs";
import path from "path";

const artifactDir = path.resolve(process.env.CASEHUB_PROD_REVIEW_ARTIFACT_DIR || process.argv[2] || "");
const repository = process.env.GITHUB_REPOSITORY || "";
const dryRun = process.env.CASEHUB_PROD_REVIEW_DRY_RUN === "1";
const extraLabels = parseLabels(process.env.CASEHUB_PROD_REVIEW_LABELS || "prod-review-factory,oracle-eng");
const requiredLabels = [
  "prod-review",
  "prod-review-factory",
  "oracle-eng",
  "army",
  "factory:envelope",
  "p1",
  "p2",
  "p3",
];

const labelDefinitions = {
  "prod-review": ["0e8a16", "Production review finding"],
  "prod-review-factory": ["1d76db", "Generated or updated by the production review factory"],
  "oracle-eng": ["5319e7", "Oracle engineering queue"],
  "army": ["6f42c1", "Eligible for army/runtime pickup"],
  "factory:envelope": ["d4c5f9", "Factory-created task envelope candidate"],
  "p1": ["b60205", "Priority 1"],
  "p2": ["d93f0b", "Priority 2"],
  "p3": ["fbca04", "Priority 3"],
};

function fail(message) {
  console.error(message);
  process.exit(1);
}

function parseLabels(value) {
  return String(value || "")
    .split(",")
    .map((label) => label.trim())
    .filter(Boolean);
}

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function runGh(args, options = {}) {
  return childProcess.execFileSync("gh", args, {
    encoding: "utf8",
    stdio: options.input ? ["pipe", "pipe", "pipe"] : ["ignore", "pipe", "pipe"],
    input: options.input,
    env: process.env,
  });
}

function ensureLabel(name) {
  if (dryRun) return;
  const [color, description] = labelDefinitions[name] || ["ededed", `CaseHub label: ${name}`];
  childProcess.spawnSync(
    "gh",
    [
      "api",
      "--method",
      "POST",
      `repos/${repository}/labels`,
      "-f",
      `name=${name}`,
      "-f",
      `color=${color}`,
      "-f",
      `description=${description}`,
    ],
    { encoding: "utf8", stdio: "ignore", env: process.env },
  );
}

function parseDraft(filePath) {
  const body = fs.readFileSync(filePath, "utf8");
  const title = body.match(/^#\s+(.+?)\s*$/m)?.[1]?.trim();
  if (!title) {
    throw new Error(`Missing first-level markdown title in ${filePath}`);
  }
  const draftLabels = parseLabels(body.match(/^Labels:\s*(.+?)\s*$/im)?.[1] || "");
  const fingerprint = crypto.createHash("sha256").update(body).digest("hex").slice(0, 16);
  const labels = unique(["prod-review", "prod-review-factory", "oracle-eng", "army", "factory:envelope", ...extraLabels, ...draftLabels]);
  return { body, filePath, fingerprint, labels, title };
}

// Sanitize an issue title for safe use as a free-text GitHub search term.
// The title originates from an untrusted draft file, so it must never be able
// to inject GitHub search qualifiers (e.g. `repo:`, `is:`, `label:`) or
// argument-injection sequences (leading `-`, brackets) into the query.
// We keep only the alphanumeric "words" of the title as a space-separated set
// of plain terms; the authoritative exact-title match below guarantees
// correctness, so this query only needs to narrow the candidate set.
function searchTermsFromTitle(title) {
  return String(title)
    .replace(/[^\p{L}\p{N}\s]+/gu, " ")
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");
}

function findOpenIssueByTitle(title) {
  // Repo and state come from dedicated flags (--repo, --state). The only
  // qualifier kept in the query string is the static `in:title`, which is a
  // hard-coded literal (never derived from the title). The sanitized title is
  // appended as plain terms, so it can carry no qualifiers or argv flags.
  const terms = searchTermsFromTitle(title);
  const args = ["issue", "list", "--repo", repository, "--state", "open", "--json", "number,title,url", "--limit", "100"];
  if (terms) {
    args.push("--search", `${terms} in:title`);
  }
  const output = runGh(args);
  const issues = JSON.parse(output || "[]");
  return issues.find((issue) => issue.title === title) || null;
}

function addLabels(issueNumber, labels) {
  if (dryRun) return;
  runGh(["api", "--method", "POST", `repos/${repository}/issues/${issueNumber}/labels`, "--input", "-"], {
    input: JSON.stringify({ labels }),
  });
}

function commentIssue(issueNumber, draft) {
  const body = [
    "### Production review factory update",
    "",
    `Artifact draft: \`${path.relative(artifactDir, draft.filePath)}\``,
    `Fingerprint: \`${draft.fingerprint}\``,
    "",
    "The production review audit generated this finding again. Re-run `npm run audit:prod-review` for local reproduction.",
  ].join("\n");
  if (dryRun) return;
  runGh(["api", "--method", "POST", `repos/${repository}/issues/${issueNumber}/comments`, "--input", "-"], {
    input: JSON.stringify({ body }),
  });
}

function createIssue(draft) {
  const payload = {
    title: draft.title,
    body: `${draft.body}\n\n---\nFactory fingerprint: \`${draft.fingerprint}\`\n`,
    labels: draft.labels,
  };
  if (dryRun) {
    return { number: null, title: draft.title, url: null };
  }
  const response = runGh(["api", "--method", "POST", `repos/${repository}/issues`, "--input", "-"], {
    input: JSON.stringify(payload),
  });
  return JSON.parse(response);
}

if (!artifactDir || artifactDir === path.resolve("")) {
  fail("Usage: publish-prod-review-issues.mjs <artifact-dir> or set CASEHUB_PROD_REVIEW_ARTIFACT_DIR");
}
if (!repository) {
  fail("GITHUB_REPOSITORY is required");
}
if (!fs.existsSync(artifactDir)) {
  fail(`Artifact directory not found: ${artifactDir}`);
}

for (const label of unique([...requiredLabels, ...extraLabels])) {
  ensureLabel(label);
}

const issuesDir = path.join(artifactDir, "issues");
const drafts = fs.existsSync(issuesDir)
  ? fs
      .readdirSync(issuesDir)
      .filter((name) => name.endsWith(".md"))
      .sort()
      .map((name) => parseDraft(path.join(issuesDir, name)))
  : [];

const published = [];
for (const draft of drafts) {
  for (const label of draft.labels) ensureLabel(label);
  const existing = findOpenIssueByTitle(draft.title);
  if (existing) {
    commentIssue(existing.number, draft);
    addLabels(existing.number, draft.labels);
    published.push({
      status: dryRun ? "dry-run-update" : "updated",
      number: existing.number,
      title: existing.title,
      url: existing.url,
      labels: draft.labels,
      fingerprint: draft.fingerprint,
      source: path.relative(artifactDir, draft.filePath),
    });
    continue;
  }

  const created = createIssue(draft);
  published.push({
    status: dryRun ? "dry-run-create" : "created",
    number: created.number,
    title: draft.title,
    url: created.html_url || created.url || null,
    labels: draft.labels,
    fingerprint: draft.fingerprint,
    source: path.relative(artifactDir, draft.filePath),
  });
}

const outputPath = path.join(artifactDir, "published-issues.json");
fs.writeFileSync(outputPath, `${JSON.stringify({ repository, dryRun, artifactDir, issues: published }, null, 2)}\n`);
console.log(outputPath);
