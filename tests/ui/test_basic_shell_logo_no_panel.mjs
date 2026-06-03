/* ============================================================
   test_basic_shell_logo_no_panel.mjs
   ------------------------------------------------------------
   Regression for the Basic shell brand chrome: the CaseHub mark
   should render as the logo itself, without a white raised panel
   behind it, while preserving the clickable brand hit area.

   Uso: node tests/ui/test_basic_shell_logo_no_panel.mjs
   ============================================================ */
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, '..', '..');

const tokens = readFileSync(`${REPO_ROOT}/static/css/themes/_tokens.css`, 'utf8');
const neuromorphic = readFileSync(`${REPO_ROOT}/static/css/themes/neuromorphic.css`, 'utf8');
const browserBasic = readFileSync(`${REPO_ROOT}/static/css/casehub-browser-basic.css`, 'utf8');

const FIXTURE_HTML = `<!DOCTYPE html>
<html lang="pt-BR" data-theme="neuromorphic">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CaseHub shell logo fixture</title>
  <style>${tokens}</style>
  <style>${neuromorphic}</style>
  <style>${browserBasic}</style>
</head>
<body class="casehub-browser-basic">
  <aside class="casehub-basic-rail" aria-label="Módulos CaseHub">
    <a class="casehub-basic-rail__brand" href="/casehub/dashboard" aria-label="CaseHub Painel">
      <span class="casehub-basic-rail__mark" aria-hidden="true">
        <img class="casehub-basic-rail__mark-img" src="/static/brand-kit/logo/casehub-logo-login-mark-blue.svg" alt="" width="34" height="36">
      </span>
      <span class="casehub-basic-rail__brand-text">CaseHub</span>
    </a>
  </aside>
  <header class="casehub-basic-mobile-header" aria-label="CaseHub">
    <a class="casehub-basic-mobile-header__brand" href="/casehub/dashboard" aria-label="CaseHub Painel">
      <span class="casehub-basic-mobile-header__mark" aria-hidden="true">
        <img class="casehub-basic-mobile-header__mark-img" src="/static/brand-kit/logo/casehub-logo-login-mark-blue.svg" alt="" width="30" height="32">
      </span>
    </a>
  </header>
</body>
</html>`;

const checks = [
  { name: 'desktop rail', viewport: { width: 1440, height: 900 }, selector: '.casehub-basic-rail__mark' },
  { name: 'mobile header', viewport: { width: 393, height: 852 }, selector: '.casehub-basic-mobile-header__mark' },
];

const browser = await chromium.launch();
const results = [];

for (const check of checks) {
  const context = await browser.newContext({ viewport: check.viewport });
  const page = await context.newPage();
  await page.setContent(FIXTURE_HTML, { waitUntil: 'load' });
  const result = await page.evaluate((selector) => {
    const mark = document.querySelector(selector);
    const img = mark?.querySelector('img');
    const markRect = mark?.getBoundingClientRect();
    const imgRect = img?.getBoundingClientRect();
    const style = mark ? getComputedStyle(mark) : null;
    return {
      selector,
      backgroundColor: style?.backgroundColor || null,
      boxShadow: style?.boxShadow || null,
      markWidth: Math.round(markRect?.width || 0),
      markHeight: Math.round(markRect?.height || 0),
      imgWidth: Math.round(imgRect?.width || 0),
      imgHeight: Math.round(imgRect?.height || 0),
    };
  }, check.selector);
  results.push({ ...check, ...result });
  await context.close();
}

await browser.close();

const pass = results.every((result) =>
  result.backgroundColor === 'rgba(0, 0, 0, 0)' &&
  result.boxShadow === 'none' &&
  result.markWidth >= 40 &&
  result.markHeight >= 40 &&
  result.imgWidth > 0 &&
  result.imgHeight > 0
);

console.log(JSON.stringify({ pass, results }, null, 2));
process.exit(pass ? 0 : 1);
