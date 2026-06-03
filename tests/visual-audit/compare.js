// @ts-check
/**
 * CaseHub Visual Regression - diff engine (Phase 1)
 *
 * Compares the most recent run's screenshots (results/<ISO>/) against
 * tests/visual-baselines/. Uses pixelmatch for pixel-level diffs and
 * applies per-viewport tolerance.
 *
 * Run:
 *   node tests/visual-audit/compare.js
 *   node tests/visual-audit/compare.js --run 2026-05-27T...
 *
 * Output:
 *   results/<ISO>/diff/<file>.png  — visual diff masks
 *   results/<ISO>/report.json      — machine-readable result
 *   results/<ISO>/report.html      — human-readable side-by-side
 *
 * Spec: memory/feedback_testing_automation.md (Phase 1)
 */
'use strict';

const fs = require('fs');
const path = require('path');

// Pixelmatch + pngjs live in ~/Projects/trabalho-workspace/node_modules.
const TRABALHO_NODE_MODULES = path.resolve(
  process.env.TRABALHO_NODE_MODULES ||
    path.join(__dirname, '..', '..', '..', 'trabalho-workspace', 'node_modules')
);

// pngjs is CommonJS — safe to require directly.
// eslint-disable-next-line import/no-dynamic-require, global-require
const { PNG } = require(path.join(TRABALHO_NODE_MODULES, 'pngjs'));

// Tolerance per viewport (fraction of differing pixels, NOT pixelmatch threshold).
// Pixelmatch's `threshold` is sensitivity for what counts as "different" per-pixel;
// we use the returned mismatched-pixel ratio against these caps.
const TOLERANCE = {
  desktop: 0.005, // 0.5%
  tablet: 0.02, //   2%
  mobile: 0.05, //   5%
};

const PIXEL_THRESHOLD = 0.1; // pixelmatch antialiasing sensitivity

const ROOT_DIR = path.resolve(__dirname);
const RESULTS_ROOT = path.join(ROOT_DIR, 'results');
const BASELINES_DIR = path.resolve(path.join(__dirname, '..', 'visual-baselines'));

function args() {
  const out = { run: null };
  for (let i = 2; i < process.argv.length; i++) {
    const a = process.argv[i];
    if (a === '--run' && process.argv[i + 1]) {
      out.run = process.argv[i + 1];
      i++;
    }
  }
  return out;
}

function resolveRunDir(stamp) {
  if (stamp) {
    return path.join(RESULTS_ROOT, stamp);
  }
  const pointer = path.join(RESULTS_ROOT, 'latest.txt');
  if (!fs.existsSync(pointer)) {
    throw new Error(
      `No --run provided and ${pointer} does not exist. Run run.spec.js first.`
    );
  }
  return path.join(RESULTS_ROOT, fs.readFileSync(pointer, 'utf8').trim());
}

function viewportFromFile(name) {
  if (name.includes('-desktop-')) return 'desktop';
  if (name.includes('-tablet-')) return 'tablet';
  if (name.includes('-mobile-')) return 'mobile';
  return 'desktop'; // fallback for interaction-* shots
}

function readPng(filePath) {
  const data = fs.readFileSync(filePath);
  return PNG.sync.read(data);
}

function writePng(filePath, png) {
  fs.writeFileSync(filePath, PNG.sync.write(png));
}

async function loadPixelmatch() {
  // pixelmatch 7.x is ESM-only. Use dynamic import from CJS.
  const mod = await import(
    path.join(TRABALHO_NODE_MODULES, 'pixelmatch', 'index.js')
  );
  return mod.default;
}

function pad2(n) {
  return String(n).padStart(2, '0');
}

function tolerantResize(srcPng, targetWidth, targetHeight) {
  // pixelmatch requires equal dimensions. If a baseline and a current shot differ
  // in size (e.g. dynamic viewport content), we draw the smaller into a canvas
  // of max(width,height) and report dim_mismatch=true so the diff isn't a false
  // 100% mismatch.
  if (srcPng.width === targetWidth && srcPng.height === targetHeight) {
    return srcPng;
  }
  const canvas = new PNG({ width: targetWidth, height: targetHeight });
  // Fill with transparent black.
  canvas.data.fill(0);
  const copyH = Math.min(srcPng.height, targetHeight);
  const copyW = Math.min(srcPng.width, targetWidth);
  for (let y = 0; y < copyH; y++) {
    for (let x = 0; x < copyW; x++) {
      const sIdx = (srcPng.width * y + x) << 2;
      const dIdx = (targetWidth * y + x) << 2;
      canvas.data[dIdx] = srcPng.data[sIdx];
      canvas.data[dIdx + 1] = srcPng.data[sIdx + 1];
      canvas.data[dIdx + 2] = srcPng.data[sIdx + 2];
      canvas.data[dIdx + 3] = srcPng.data[sIdx + 3];
    }
  }
  return canvas;
}

async function compareOne(pixelmatch, baselinePath, currentPath, diffPath) {
  if (!fs.existsSync(baselinePath)) {
    return { status: 'no_baseline' };
  }
  if (!fs.existsSync(currentPath)) {
    return { status: 'no_current' };
  }
  const baseline = readPng(baselinePath);
  const current = readPng(currentPath);
  const dimMismatch =
    baseline.width !== current.width || baseline.height !== current.height;

  const width = Math.max(baseline.width, current.width);
  const height = Math.max(baseline.height, current.height);
  const baseAdj = tolerantResize(baseline, width, height);
  const currAdj = tolerantResize(current, width, height);

  const diff = new PNG({ width, height });
  const mismatched = pixelmatch(
    baseAdj.data,
    currAdj.data,
    diff.data,
    width,
    height,
    { threshold: PIXEL_THRESHOLD, includeAA: false }
  );
  writePng(diffPath, diff);
  const total = width * height;
  return {
    status: 'compared',
    mismatched_px: mismatched,
    total_px: total,
    ratio: total > 0 ? mismatched / total : 0,
    dim_mismatch: dimMismatch,
    baseline_dim: { w: baseline.width, h: baseline.height },
    current_dim: { w: current.width, h: current.height },
  };
}

function tolerantFor(viewport) {
  return TOLERANCE[viewport] ?? TOLERANCE.desktop;
}

function fmtPct(r) {
  return (r * 100).toFixed(3) + '%';
}

function renderHtml(runStamp, summary) {
  const rows = summary.entries
    .map((e) => {
      const cap = tolerantFor(e.viewport);
      const ratioStr = e.status === 'compared' ? fmtPct(e.ratio) : '—';
      const verdictColor =
        e.verdict === 'pass'
          ? '#0a8a3a'
          : e.verdict === 'fail'
          ? '#c0392b'
          : '#8a6d0a';
      const baseRel = e.baseline_rel || '';
      const curRel = e.current_rel || '';
      const diffRel = e.diff_rel || '';
      const triplet = (a) =>
        a ? `<a href="${a}"><img src="${a}" loading="lazy" /></a>` : '<div class="empty">—</div>';
      return `
        <tr>
          <td><code>${e.file}</code><br/><small>${e.viewport} · cap ${fmtPct(cap)}</small></td>
          <td>${triplet(baseRel)}</td>
          <td>${triplet(curRel)}</td>
          <td>${triplet(diffRel)}</td>
          <td><span style="color:${verdictColor};font-weight:600">${e.verdict.toUpperCase()}</span><br/><small>${e.status}<br/>diff: ${ratioStr}</small></td>
        </tr>`;
    })
    .join('\n');

  const passCount = summary.entries.filter((e) => e.verdict === 'pass').length;
  const failCount = summary.entries.filter((e) => e.verdict === 'fail').length;
  const newCount = summary.entries.filter((e) => e.verdict === 'new').length;

  return `<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8" />
<title>Visual Regression Report — ${runStamp}</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 24px; background:#f7f7f8; color:#222; }
  h1 { margin: 0 0 4px 0; }
  .meta { color:#666; margin-bottom: 18px; font-size: 14px; }
  .badges span { display:inline-block; padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; margin-right: 8px; }
  .b-pass { background:#d4f7df; color:#0a8a3a; }
  .b-fail { background:#ffd4cf; color:#c0392b; }
  .b-new  { background:#fff1cc; color:#8a6d0a; }
  table { border-collapse: collapse; width: 100%; background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.06); }
  th, td { border: 1px solid #e3e3e6; padding: 10px; vertical-align: top; }
  th { background: #fafafb; text-align: left; font-size: 13px; }
  td img { width: 220px; max-height: 160px; object-fit: cover; border-radius: 4px; border: 1px solid #e3e3e6; }
  .empty { width: 220px; height: 80px; display:flex; align-items:center; justify-content:center; color:#bbb; border: 1px dashed #ddd; border-radius:4px; }
  code { font-size: 12px; word-break: break-all; }
  small { color:#666; }
</style>
</head>
<body>
  <h1>Visual Regression Report</h1>
  <div class="meta">Run: <code>${runStamp}</code> · Base URL: <code>${summary.base_url}</code> · Generated: ${summary.generated_at}</div>
  <div class="badges">
    <span class="b-pass">PASS ${passCount}</span>
    <span class="b-fail">FAIL ${failCount}</span>
    <span class="b-new">NEW ${newCount}</span>
  </div>
  <table>
    <thead>
      <tr><th>File</th><th>Baseline</th><th>Current</th><th>Diff</th><th>Verdict</th></tr>
    </thead>
    <tbody>
      ${rows}
    </tbody>
  </table>
</body>
</html>
`;
}

async function main() {
  const { run } = args();
  const runDir = resolveRunDir(run);
  if (!fs.existsSync(runDir)) {
    throw new Error(`Run directory does not exist: ${runDir}`);
  }
  const runStamp = path.basename(runDir);
  console.log(`[compare] run: ${runStamp}`);
  console.log(`[compare] baselines: ${BASELINES_DIR}`);

  const diffDir = path.join(runDir, 'diff');
  fs.mkdirSync(diffDir, { recursive: true });

  const pixelmatch = await loadPixelmatch();

  const allPngs = fs
    .readdirSync(runDir)
    .filter((f) => f.endsWith('.png'))
    .sort();

  const entries = [];
  for (const file of allPngs) {
    const viewport = viewportFromFile(file);
    const baselinePath = path.join(BASELINES_DIR, file);
    const currentPath = path.join(runDir, file);
    const diffPath = path.join(diffDir, file);
    const res = await compareOne(pixelmatch, baselinePath, currentPath, diffPath);

    let verdict = 'unknown';
    if (res.status === 'no_baseline') {
      verdict = 'new';
    } else if (res.status === 'compared') {
      verdict = res.ratio <= tolerantFor(viewport) ? 'pass' : 'fail';
    } else {
      verdict = 'fail';
    }

    entries.push({
      file,
      viewport,
      tolerance: tolerantFor(viewport),
      verdict,
      ...res,
      baseline_rel: fs.existsSync(baselinePath)
        ? path.relative(runDir, baselinePath)
        : '',
      current_rel: file,
      diff_rel: res.status === 'compared' ? path.join('diff', file) : '',
    });
  }

  const summary = {
    run: runStamp,
    base_url: process.env.CASEHUB_BASE_URL || 'https://casehub.legal',
    generated_at: new Date().toISOString(),
    tolerance: TOLERANCE,
    pixel_threshold: PIXEL_THRESHOLD,
    entries,
    totals: {
      total: entries.length,
      pass: entries.filter((e) => e.verdict === 'pass').length,
      fail: entries.filter((e) => e.verdict === 'fail').length,
      new: entries.filter((e) => e.verdict === 'new').length,
    },
  };

  fs.writeFileSync(
    path.join(runDir, 'report.json'),
    JSON.stringify(summary, null, 2)
  );
  fs.writeFileSync(path.join(runDir, 'report.html'), renderHtml(runStamp, summary));

  console.log(
    `[compare] done — pass=${summary.totals.pass} fail=${summary.totals.fail} new=${summary.totals.new} total=${summary.totals.total}`
  );
  console.log(`[compare] report: ${path.join(runDir, 'report.html')}`);

  if (summary.totals.fail > 0) {
    process.exitCode = 1;
  }
}

main().catch((err) => {
  console.error('[compare] fatal:', err);
  process.exit(1);
});
