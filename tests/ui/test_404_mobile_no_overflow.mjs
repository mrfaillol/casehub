/* ============================================================
   test_404_mobile_no_overflow.mjs
   ------------------------------------------------------------
   Regressão para PR #554 audit finding (H3): página 404 em
   viewport mobile 393x852 não pode produzir scrollWidth > 393.
   Root cause: base_minimal.html não carregava reset.css; com
   box-sizing default content-box, .errors-404-btn (width: 100%
   + padding 12px 20px + border 1px) excedia o pai em ~10px.
   A mesma tela também precisa manter alvos móveis >=44px.
   Baseline (commit anterior): scrollWidth=403, overflow=10px.

   Roda sem auth: monta o HTML do 404 estaticamente contra os
   CSS files reais do projeto via file:// + setContent.
   Uso: node tests/ui/test_404_mobile_no_overflow.mjs
   Exit 0 = pass, 1 = fail.
   ============================================================ */
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, '..', '..');

const tokens = readFileSync(`${REPO_ROOT}/static/css/themes/_tokens.css`, 'utf8');
const neuromorphic = readFileSync(`${REPO_ROOT}/static/css/themes/neuromorphic.css`, 'utf8');
const baseMinimal = readFileSync(`${REPO_ROOT}/static/css/templates/base_minimal.css`, 'utf8');
const errors404 = readFileSync(`${REPO_ROOT}/static/css/templates/errors-404.css`, 'utf8');

// Fixture: 404 estático com email longo (worst-case footer) para garantir
// que o reset cobre não só o botão mas a inteira árvore standalone.
const FIXTURE_HTML = `<!DOCTYPE html>
<html lang="pt-BR" data-theme="neuromorphic">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Página Não Encontrada - CaseHub</title>
  <style>${tokens}</style>
  <style>${neuromorphic}</style>
  <style>${baseMinimal}</style>
  <style>${errors404}</style>
</head>
<body class="base-minimal minimal">
  <main class="base-minimal-main" role="main">
    <main class="errors-404-main" role="main">
      <section class="errors-404-container" aria-labelledby="t" aria-describedby="d">
        <h1 id="t" class="errors-404-code">404</h1>
        <p class="errors-404-lead">Página não encontrada</p>
        <p id="d" class="errors-404-detail">A página que você procura não existe ou foi movida: https://casehub.legal/casehub/notarealroute-h3-probe?probe=404-mobile-overflow-regression-with-a-long-token</p>
        <a href="/casehub/dashboard" class="errors-404-btn">
          <span>Ir para o Painel</span>
        </a>
        <hr class="errors-404-divider">
        <footer class="errors-404-help">
          <p>Precisa de ajuda?</p>
          <p>
            <a href="mailto:contato@casehub.legal">contato@casehub.legal</a>
          </p>
        </footer>
      </section>
    </main>
  </main>
</body>
</html>`;

const VIEWPORT = { width: 393, height: 852 };
const MAX_ALLOWED_SCROLL = VIEWPORT.width;

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 2 });
const page = await ctx.newPage();
await page.setContent(FIXTURE_HTML, { waitUntil: 'load' });
await page.waitForTimeout(150);
await page.keyboard.press('Tab');
await page.hover('.errors-404-btn');

const measured = await page.evaluate(() => {
  const VW = window.innerWidth;
  const doc = document.documentElement;
  const offenders = [];
  const tapTargetsUnder44 = [];
  function walk(el, depth = 0) {
    if (!(el instanceof HTMLElement) || depth > 25) return;
    const r = el.getBoundingClientRect();
    if (r.right > VW + 0.5 && r.width > 0) {
      offenders.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.className || '').toString(),
        width: Math.round(r.width),
        right: Math.round(r.right),
      });
    }
    for (const c of el.children) walk(c, depth + 1);
  }
  walk(document.body);

  document.querySelectorAll('a, button, input, select, textarea, summary, [role="button"], [tabindex]:not([tabindex="-1"])').forEach((el) => {
    const r = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    if (r.width <= 0 || r.height <= 0 || style.visibility === 'hidden' || style.display === 'none') return;
    if (r.width < 44 || r.height < 44) {
      tapTargetsUnder44.push({
        tag: el.tagName.toLowerCase(),
        label: (el.textContent || el.getAttribute('href') || el.tagName).trim().replace(/\s+/g, ' ').slice(0, 80),
        width: Math.round(r.width),
        height: Math.round(r.height),
      });
    }
  });

  const button = document.querySelector('.errors-404-btn');
  const buttonStyle = button ? window.getComputedStyle(button) : null;

  return {
    viewport: VW,
    bodyScrollWidth: doc.scrollWidth,
    bodyClientWidth: doc.clientWidth,
    offenderCount: offenders.length,
    offenders: offenders.slice(0, 10),
    tapTargetsUnder44,
    focusedControl: document.activeElement?.className || document.activeElement?.tagName || null,
    buttonColor: buttonStyle?.color || null,
    buttonBackground: buttonStyle?.backgroundColor || null,
  };
});

await browser.close();

const pass =
  measured.bodyScrollWidth <= MAX_ALLOWED_SCROLL &&
  measured.offenderCount === 0 &&
  measured.tapTargetsUnder44.length === 0 &&
  measured.focusedControl === 'errors-404-btn' &&
  measured.buttonColor !== measured.buttonBackground;

console.log(JSON.stringify({ pass, expected_max: MAX_ALLOWED_SCROLL, ...measured }, null, 2));
process.exit(pass ? 0 : 1);
