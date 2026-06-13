const fs = require("fs");
const os = require("os");
const path = require("path");
const { expect } = require("@playwright/test");

const VS_PROD_HOST = "casehub.sampletenantadvogados.com.br";

function normalizePrefix(value) {
  const raw = value || "/casehub";
  const withSlash = raw.startsWith("/") ? raw : `/${raw}`;
  return withSlash.replace(/\/+$/, "") || "/casehub";
}

function buildSmokeConfig() {
  const rawBaseUrl = process.env.CASEHUB_SMOKE_BASE_URL;
  if (!rawBaseUrl) {
    throw new Error("CASEHUB_SMOKE_BASE_URL is required for LegalOps smoke tests.");
  }

  const parsed = new URL(rawBaseUrl);
  const inferredPrefix = parsed.pathname && parsed.pathname !== "/" ? parsed.pathname : "";
  const prefix = normalizePrefix(process.env.CASEHUB_SMOKE_PREFIX || inferredPrefix || "/casehub");
  parsed.pathname = "/";
  parsed.search = "";
  parsed.hash = "";

  const host = parsed.hostname.toLowerCase();
  const vsProdAllowed = host === VS_PROD_HOST && process.env.CASEHUB_ALLOW_VS_PROD_SMOKE === "1";
  if (host === VS_PROD_HOST && !vsProdAllowed) {
    throw new Error(
      `Refusing authenticated mutation smoke against VS-prod (${VS_PROD_HOST}). ` +
        "Use local/dev/demo, or set CASEHUB_ALLOW_VS_PROD_SMOKE=1 only with explicit production QA-data approval."
    );
  }

  const localHost = host === "localhost" || host === "0.0.0.0" || host === "::1" || host.startsWith("127.");
  const approvedRemote = host === "dev.vingren.me" || host === "casehub.vingren.me";
  if (!localHost && !approvedRemote && !vsProdAllowed && process.env.CASEHUB_ALLOW_NON_PROD_SMOKE !== "1") {
    throw new Error(
      `Refusing smoke against unapproved host ${host}. ` +
        "Use localhost, dev.vingren.me, casehub.vingren.me, or set CASEHUB_ALLOW_NON_PROD_SMOKE=1 for another non-prod target."
    );
  }

  const artifactDir =
    process.env.CASEHUB_SMOKE_ARTIFACT_DIR ||
    path.join(os.tmpdir(), `casehub-legalops-smoke-${new Date().toISOString().replace(/[:.]/g, "-")}`);
  fs.mkdirSync(artifactDir, { recursive: true });

  return {
    baseOrigin: parsed.origin,
    host,
    prefix,
    artifactDir,
    url(route) {
      const suffix = route.startsWith("/") ? route : `/${route}`;
      return new URL(`${prefix}${suffix}`, parsed.origin).toString();
    },
  };
}

async function ensureAuthenticated(page, config) {
  await page.goto(config.url("/dashboard"), { waitUntil: "domcontentloaded" });

  const loginFormVisible = await page.locator('input[name="email"]').first().isVisible().catch(() => false);
  const onLogin = new URL(page.url()).pathname.endsWith(`${config.prefix}/login`) || loginFormVisible;
  if (!onLogin) {
    await dismissReleaseNotice(page);
    return;
  }

  const email = process.env.CASEHUB_AUDIT_EMAIL;
  const password = process.env.CASEHUB_AUDIT_PASSWORD;
  if (!email || !password) {
    throw new Error(
      "Authenticated smoke requires CASEHUB_AUDIT_STORAGE_STATE or CASEHUB_AUDIT_EMAIL/CASEHUB_AUDIT_PASSWORD."
    );
  }

  await page.goto(config.url("/login"), { waitUntil: "domcontentloaded" });
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', password);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.endsWith(`${config.prefix}/login`), { timeout: 15000 }).catch(() => {}),
    page.locator('button[type="submit"], input[type="submit"]').first().click(),
  ]);

  await page.goto(config.url("/dashboard"), { waitUntil: "domcontentloaded" });
  await expect(page.locator('input[name="email"]')).toHaveCount(0, { timeout: 10000 });
  await dismissReleaseNotice(page);
}

async function dismissReleaseNotice(page) {
  const notice = page.locator("[data-casehub-release-notice]").first();
  if (!(await notice.isVisible().catch(() => false))) {
    return;
  }

  await notice.locator("[data-casehub-release-close]").last().click();
  await expect(notice).toBeHidden({ timeout: 10000 });
}

function attachConsoleWatch(page) {
  const entries = [];
  page.on("console", (msg) => {
    if (["error", "warning"].includes(msg.type())) {
      entries.push(`${msg.type()}: ${msg.text()}`);
    }
  });
  page.on("pageerror", (error) => {
    entries.push(`pageerror: ${error.message}`);
  });
  return () => entries;
}

async function expectConsoleClean(getConsoleEntries) {
  const entries = getConsoleEntries();
  expect(entries, `Console errors/warnings:\n${entries.join("\n")}`).toEqual([]);
}

async function screenshot(page, config, name) {
  if (process.env.CASEHUB_SMOKE_SCREENSHOTS === "0") {
    return;
  }
  const file = path.join(config.artifactDir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  console.log(`screenshot:${file}`);
}

function applyOptionalStorageState(test) {
  const storageState = process.env.CASEHUB_AUDIT_STORAGE_STATE;
  if (storageState) {
    test.use({ storageState });
  }
}

module.exports = {
  applyOptionalStorageState,
  attachConsoleWatch,
  buildSmokeConfig,
  dismissReleaseNotice,
  ensureAuthenticated,
  expectConsoleClean,
  screenshot,
};
