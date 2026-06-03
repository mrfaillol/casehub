/* ============================================================
   test_cases_mobile_no_overflow.mjs
   ------------------------------------------------------------
   Regressão para PR #554 audit finding (H1): /casehub/cases em
   viewport mobile 393x852 não pode produzir scrollWidth > 393.
   Baseline (PR #554): bodyScrollWidth=534, hasHorizontalOverflow=true.
   Suspeito (estática): tabela `.cases-list-table` (width:100%)
   com headers `white-space: nowrap` força min-width > 393, e a
   chain de ancestrais não carrega `box-sizing: border-box` (mesmo
   pattern do H3) — base.html não inclui reset.css.

   Roda sem auth: fixture estática reproduz o template `cases/list.html`
   no estado vazio (lite, PT-BR) com tokens reais carregados.
   Uso: node tests/ui/test_cases_mobile_no_overflow.mjs
   Exit 0 = pass, 1 = fail.
   ============================================================ */
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, '..', '..');

const tokens = readFileSync(`${REPO_ROOT}/static/css/themes/_tokens.css`, 'utf8');
const casesList = readFileSync(`${REPO_ROOT}/static/css/templates/cases-list.css`, 'utf8');

// Fixture replica `templates/cases/list.html` com product=lite, total=0, cases=[]
// (caminho empty-state — sem rows; o overflow do PR #554 foi observado neste
// exato estado, já que a tabela carrega 0 processos em prod).
const FIXTURE_HTML = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Processos - CaseHub</title>
  <style>${tokens}</style>
  <style>${casesList}</style>
  <!-- Shell minimal pra simular casehub-browser-basic mobile (body+main reset bare) -->
  <style>
    html, body { margin: 0; padding: 0; }
    body { font-family: var(--font-family-sans, sans-serif); background: var(--surface-base, #f7f7f7); }
  </style>
</head>
<body>
  <main class="cases-list-main" role="main" aria-labelledby="cases-list-title">
    <header class="cases-list-header">
      <h1 id="cases-list-title" class="cases-list-title">
        <i class="fas fa-folder" aria-hidden="true"></i>
        <span>Processos</span>
      </h1>
      <a href="/cases/new" class="cases-list-btn cases-list-btn--primary">
        <i class="fas fa-plus" aria-hidden="true"></i>
        <span>Novo Processo</span>
      </a>
    </header>

    <section class="cases-list-filters" aria-label="Filtros">
      <form method="get" class="cases-list-filters-form cases-list-filters-form--no-visa">
        <div class="cases-list-field">
          <label class="cases-list-field-label" for="search">Buscar</label>
          <div class="cases-list-search">
            <i class="fas fa-search cases-list-search-icon" aria-hidden="true"></i>
            <input type="text" id="search" class="cases-list-input" name="search" placeholder="Buscar processos...">
          </div>
        </div>
        <div class="cases-list-field">
          <label class="cases-list-field-label" for="status">Status</label>
          <select id="status" name="status" class="cases-list-select">
            <option value="">Todos os Status</option>
          </select>
        </div>
        <div class="cases-list-field">
          <span class="cases-list-field-label" aria-hidden="true">&nbsp;</span>
          <button type="submit" class="cases-list-btn cases-list-btn--ghost">
            <i class="fas fa-filter" aria-hidden="true"></i>
            <span>Filtrar</span>
          </button>
        </div>
      </form>
    </section>

    <section class="cases-list-card" aria-label="Lista de processos">
      <header class="cases-list-card-header">
        <span class="cases-list-count"><strong>0</strong> processos encontrados</span>
      </header>
      <div class="cases-list-table-wrapper">
        <table class="cases-list-table" id="casesTable">
          <thead>
            <tr>
              <th scope="col" class="cases-list-sortable">N Processo <span class="cases-list-sort-icon">▲▼</span></th>
              <th scope="col" class="cases-list-sortable">Cliente <span class="cases-list-sort-icon">▲▼</span></th>
              <th scope="col" class="cases-list-sortable">Status <span class="cases-list-sort-icon">▲▼</span></th>
              <th scope="col" class="cases-list-sortable">Prioridade <span class="cases-list-sort-icon">▲▼</span></th>
              <th scope="col" class="cases-list-sortable">Criado <span class="cases-list-sort-icon">▲▼</span></th>
              <th scope="col" class="cases-list-actions-cell"><span class="cases-list-visually-hidden">Ações</span></th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colspan="6" class="cases-list-empty">
                <i class="fas fa-folder-open cases-list-empty-icon"></i>
                <span>Nenhum processo encontrado</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
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

const measured = await page.evaluate(() => {
  const VW = window.innerWidth;
  const doc = document.documentElement;
  // Offenders that VISUALLY overflow E também escapam containers com
  // overflow auto/hidden — só esses contribuem pro body scrollWidth.
  // Elementos dentro de .cases-list-table-wrapper (overflow-x: auto)
  // são esperados (tabelas wide com scroll interno).
  const uncontainedOffenders = [];
  function inClippedAncestor(el) {
    let p = el.parentElement;
    while (p) {
      const cs = getComputedStyle(p);
      if (cs.overflowX === 'auto' || cs.overflowX === 'hidden' || cs.overflowX === 'scroll') return true;
      if (cs.overflow === 'auto' || cs.overflow === 'hidden' || cs.overflow === 'scroll') return true;
      p = p.parentElement;
    }
    return false;
  }
  function walk(el, depth = 0) {
    if (!(el instanceof HTMLElement) || depth > 25) return;
    const r = el.getBoundingClientRect();
    if (r.right > VW + 0.5 && r.width > 0 && !inClippedAncestor(el)) {
      const cs = getComputedStyle(el);
      uncontainedOffenders.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.className || '').toString().slice(0, 80),
        width: Math.round(r.width),
        right: Math.round(r.right),
        overflowX: cs.overflowX,
        depth,
      });
    }
    for (const c of el.children) walk(c, depth + 1);
  }
  walk(document.body);
  return {
    viewport: VW,
    bodyScrollWidth: doc.scrollWidth,
    bodyClientWidth: doc.clientWidth,
    uncontainedOffenderCount: uncontainedOffenders.length,
    uncontainedOffenders: uncontainedOffenders.slice(0, 20),
  };
});

await browser.close();

// Authoritative pass criterion: bodyScrollWidth (= user-visible horizontal
// overflow). Uncontained offenders are sanity-check secondary signal —
// if scrollWidth ≤ viewport but offenders exist, those are clipped/scrolling
// internally and don't cause body overflow.
const pass = measured.bodyScrollWidth <= MAX_ALLOWED_SCROLL;

console.log(JSON.stringify({ pass, expected_max: MAX_ALLOWED_SCROLL, ...measured }, null, 2));
process.exit(pass ? 0 : 1);
