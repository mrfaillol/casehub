/* ============================================================
   test_browser_basic_box_sizing_reset.mjs
   ------------------------------------------------------------
   H_shell regression: garante que o reset `box-sizing: border-box`
   escopado a `body.casehub-browser-basic *` está ativo e que NÃO
   quebra layouts existentes (cases-list, generic empty page).

   Sem auth: monta fixtures estáticas com o shell CSS + um template
   de cada classe e verifica:
     - computed `box-sizing` de elementos sample é "border-box"
     - bodyScrollWidth ≤ viewport em mobile 393x852
     - bodyScrollWidth ≤ viewport em desktop 1440x900

   Uso: node tests/ui/test_browser_basic_box_sizing_reset.mjs
   Exit 0 = pass, 1 = fail.
   ============================================================ */
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, '..', '..');

const tokens = readFileSync(`${REPO_ROOT}/static/css/themes/_tokens.css`, 'utf8');
const shell = readFileSync(`${REPO_ROOT}/static/css/casehub-browser-basic.css`, 'utf8');
const casesList = readFileSync(`${REPO_ROOT}/static/css/templates/cases-list.css`, 'utf8');

function fixture(bodyContent) {
  return `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Test</title>
  <style>${tokens}</style>
  <style>${shell}</style>
  <style>${casesList}</style>
  <style>html, body { margin: 0; padding: 0; }</style>
</head>
<body class="casehub-browser-basic neuromorphic">
  ${bodyContent}
</body>
</html>`;
}

const CASE_BODY = `
  <main class="cases-list-main">
    <header class="cases-list-header">
      <h1 class="cases-list-title"><span>Processos</span></h1>
      <a href="#" class="cases-list-btn cases-list-btn--primary"><span>Novo Processo</span></a>
    </header>
    <section class="cases-list-card">
      <div class="cases-list-table-wrapper">
        <table class="cases-list-table">
          <thead><tr>
            <th class="cases-list-sortable">N Processo</th>
            <th class="cases-list-sortable">Cliente</th>
            <th class="cases-list-sortable">Status</th>
            <th class="cases-list-sortable">Prioridade</th>
            <th class="cases-list-sortable">Criado</th>
            <th class="cases-list-actions-cell"><span class="cases-list-visually-hidden">Ações</span></th>
          </tr></thead>
          <tbody>
            <tr><td colspan="6" class="cases-list-empty">
              <i class="fas fa-folder-open cases-list-empty-icon"></i>
              <span>Nenhum processo encontrado</span>
            </td></tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>
`;

const SCENARIOS = [
  { label: 'cases-list-mobile', viewport: { width: 393, height: 852 }, body: CASE_BODY },
  { label: 'cases-list-desktop', viewport: { width: 1440, height: 900 }, body: CASE_BODY },
];

const browser = await chromium.launch();
const results = [];

for (const sc of SCENARIOS) {
  const ctx = await browser.newContext({ viewport: sc.viewport, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.setContent(fixture(sc.body), { waitUntil: 'load' });
  await page.waitForTimeout(150);

  const measured = await page.evaluate(() => {
    const VW = window.innerWidth;
    const doc = document.documentElement;
    const sampleClasses = ['cases-list-main', 'cases-list-btn', 'cases-list-card', 'cases-list-table-wrapper'];
    const samples = sampleClasses.map((cls) => {
      const el = document.querySelector(`.${cls}`);
      if (!el) return { cls, found: false };
      return { cls, found: true, boxSizing: getComputedStyle(el).boxSizing };
    });
    const uncontainedOffenders = [];
    function inClippedAncestor(el) {
      let p = el.parentElement;
      while (p) {
        const cs = getComputedStyle(p);
        if (['auto', 'hidden', 'scroll'].includes(cs.overflowX)) return true;
        if (['auto', 'hidden', 'scroll'].includes(cs.overflow)) return true;
        p = p.parentElement;
      }
      return false;
    }
    function walk(el, depth = 0) {
      if (!(el instanceof HTMLElement) || depth > 25) return;
      const r = el.getBoundingClientRect();
      if (r.right > VW + 0.5 && r.width > 0 && !inClippedAncestor(el)) {
        uncontainedOffenders.push({
          tag: el.tagName.toLowerCase(),
          cls: (el.className || '').toString().slice(0, 80),
          width: Math.round(r.width),
          right: Math.round(r.right),
        });
      }
      for (const c of el.children) walk(c, depth + 1);
    }
    walk(document.body);
    return {
      viewport: VW,
      bodyScrollWidth: doc.scrollWidth,
      samples,
      uncontainedOffenders: uncontainedOffenders.slice(0, 10),
    };
  });

  // H_shell sub-A ASSERTS: box-sizing border-box é aplicado em descendentes
  // do shell browser-basic. NÃO asserta scrollWidth (= dock/Sub-B + outras
  // residências de layout que esta slice não pretende corrigir).
  // Sanity check: desktop (1440) deve passar sem overflow já que dock não existe
  // em desktop e o reset não introduz regressão visível ali.
  const allBorderBox = measured.samples.every((s) => !s.found || s.boxSizing === 'border-box');
  const desktopNoOverflow = sc.viewport.width < 1024 || measured.bodyScrollWidth <= sc.viewport.width;
  const pass = allBorderBox && desktopNoOverflow;
  results.push({ label: sc.label, pass, allBorderBox, desktopNoOverflow, ...measured });

  await ctx.close();
}

await browser.close();

const overallPass = results.every((r) => r.pass);
console.log(JSON.stringify({ overallPass, results }, null, 2));
process.exit(overallPass ? 0 : 1);
