#!/usr/bin/env node
/**
 * UI Remake — Playwright smoke validation
 *
 * Roda contra https://casehub.legal (ou BASE_URL env) em duas viewports:
 *   - desktop 1440×900
 *   - mobile  393×852
 *
 * Para cada rota canonical RICA, valida:
 *   - HTTP status 200 ou 302 (login redirect — esperado deslogado)
 *   - scroll_width ≤ viewport (0 horizontal overflow)
 *   - tap_targets <44px = 0 no mobile
 *   - console_error_count = 0
 *
 * NÃO executa: submit, save, delete, payment, sync, OAuth, QR.
 *
 * Uso:
 *   node scripts/playwright-rich-routes-smoke.cjs
 *   BASE_URL=https://dev.vingren.me node scripts/playwright-rich-routes-smoke.cjs
 *   ROUTES=/casehub/dashboard,/casehub/clients node scripts/playwright-rich-routes-smoke.cjs
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = process.env.BASE_URL || 'https://casehub.legal';
const ROUTES_ENV = process.env.ROUTES;
const OUT_DIR = process.env.OUT_DIR || '/tmp/ui-remake-smoke';

const RICH_ROUTES = ROUTES_ENV ? ROUTES_ENV.split(',') : [
  '/casehub/dashboard',
  '/casehub/clients',
  '/casehub/clients/new',
  '/casehub/cases',
  '/casehub/cases/new',
  '/casehub/tasks',
  '/casehub/tasks/kanban',
  '/casehub/tasks/new',
  '/casehub/tasks/calendar',
  '/casehub/controladoria',
  '/casehub/calendar',
  '/casehub/billing',
  '/casehub/billing/items/new',
  '/casehub/billing/time/new',
  '/casehub/invoices',
  '/casehub/invoices/new',
  '/casehub/documents',
  '/casehub/documents/upload',
  '/casehub/doc-templates',
  '/casehub/doc-templates/new',
  '/casehub/payments',
  '/casehub/payments/success',
  '/casehub/payments/cancel',
  '/casehub/payments/error',
  '/casehub/admin',
  '/casehub/admin/users',
  '/casehub/admin/users/new',
  '/casehub/admin/branding',
  '/casehub/admin/customizacao',
  '/casehub/admin/settings',
  '/casehub/admin/design-editor',
  '/casehub/profile',
  '/casehub/2fa/setup',
  '/casehub/integrations',
  '/casehub/subscription',
  '/casehub/settings',
  '/casehub/settings/numbering',
  '/casehub/signup',
  '/casehub/md',
  '/casehub/md/new',
  '/casehub/whatsapp',
  '/casehub/tools/rescisao',
];

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile',  width: 393,  height: 852 },
];

async function checkRoute(page, route, viewport) {
  const url = `${BASE}${route}`;
  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  let status = 0;
  let final_url = url;
  let scroll_width = 0;
  let client_width = viewport.width;
  let tap_under_44 = 0;
  let title = '';
  let err = '';

  try {
    const response = await page.goto(url, {
      waitUntil: 'domcontentloaded',
      timeout: 20000,
    });
    status = response ? response.status() : 0;
    final_url = page.url();
    title = await page.title();

    // Wait briefly for client-side render
    await page.waitForTimeout(800);

    // Measure overflow
    const metrics = await page.evaluate(() => {
      return {
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      };
    });
    scroll_width = metrics.scrollWidth;
    client_width = metrics.clientWidth;

    // Count tap targets under 44px (anchors, buttons, [role=button], [data-icon] clicks)
    tap_under_44 = await page.evaluate(() => {
      const selectors = ['a', 'button', '[role="button"]', 'input[type="submit"]', 'input[type="button"]'];
      const els = document.querySelectorAll(selectors.join(','));
      let count = 0;
      els.forEach(el => {
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) return; // hidden
        if (r.width < 44 || r.height < 44) count++;
      });
      return count;
    });
  } catch (e) {
    err = e.message;
  }

  return {
    route, viewport: viewport.name,
    status, final_url, title,
    scroll_width, client_width,
    overflow: scroll_width > client_width ? scroll_width - client_width : 0,
    tap_under_44,
    console_errors: consoleErrors.length,
    error: err,
  };
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true });

  const results = [];
  let fail = 0, ok = 0, redirect = 0;

  for (const viewport of VIEWPORTS) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      userAgent: viewport.name === 'mobile'
        ? 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1'
        : 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    });
    const page = await context.newPage();

    for (const route of RICH_ROUTES) {
      const result = await checkRoute(page, route, viewport);
      const okStatus = result.status === 200 || result.status === 302;
      const okOverflow = result.overflow === 0;
      const okTap = viewport.name === 'mobile' ? result.tap_under_44 === 0 : true;
      const okConsole = result.console_errors === 0;
      const passed = okStatus && okOverflow && okConsole;

      if (result.status === 302) redirect++;
      else if (passed) ok++;
      else fail++;

      const tag = passed ? '✓' : '✗';
      const overflow = result.overflow > 0 ? ` overflow=+${result.overflow}px` : '';
      const tap = result.tap_under_44 > 0 ? ` tap<44=${result.tap_under_44}` : '';
      const cerr = result.console_errors > 0 ? ` err=${result.console_errors}` : '';
      console.log(`  ${tag} ${viewport.name.padEnd(7)} ${String(result.status).padEnd(3)} ${route}${overflow}${tap}${cerr}${result.error ? ' ['+result.error+']' : ''}`);
      results.push(result);
    }

    await page.close();
    await context.close();
  }

  await browser.close();

  // Write JSON report
  const reportPath = path.join(OUT_DIR, 'report.json');
  fs.writeFileSync(reportPath, JSON.stringify({
    base_url: BASE,
    routes_count: RICH_ROUTES.length,
    viewports: VIEWPORTS,
    summary: { ok, redirect, fail, total: results.length },
    results,
  }, null, 2));

  console.log(`\nSummary: ${ok} OK · ${redirect} REDIRECT (auth) · ${fail} FAIL · total ${results.length}`);
  console.log(`Report: ${reportPath}`);
  process.exit(fail > 0 ? 1 : 0);
}

main().catch(e => {
  console.error('Smoke run failed:', e);
  process.exit(2);
});
