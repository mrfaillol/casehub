// @ts-check
/**
 * CaseHub Lite - Final Comprehensive Visual Audit
 *
 * Tests every page, button, dark mode, split-screen, Maestro FAB.
 * Credentials: via env CASEHUB_TEST_EMAIL / CASEHUB_TEST_PASSWORD (no real creds in repo)
 *
 * Run: cd casehub-whitelabel && npx playwright test tests/final-visual-audit.js
 */
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');
if (!process.env.CASEHUB_TEST_EMAIL || !process.env.CASEHUB_TEST_PASSWORD) { throw new Error('Defina CASEHUB_TEST_EMAIL e CASEHUB_TEST_PASSWORD (sem credencial hardcoded no repo)'); }

const BASE = 'http://REDACTED-HOST:8002/casehub';
const SCREENSHOT_DIR = path.join(__dirname, '..', 'test-results', 'final-audit');
const REPORT_PATH = path.join(SCREENSHOT_DIR, 'audit-report.json');

// All Lite sidebar pages
const PAGES = [
  { url: '/casehub/dashboard', name: 'Dashboard' },
  { url: '/casehub/clients', name: 'Clientes' },
  { url: '/casehub/clients/new', name: 'Novo Cliente' },
  { url: '/casehub/cases', name: 'Processos' },
  { url: '/casehub/cases/new', name: 'Novo Processo' },
  { url: '/casehub/tasks/kanban', name: 'Kanban' },
  { url: '/casehub/calendar', name: 'Calendario' },
  { url: '/casehub/emails', name: 'Emails' },
  { url: '/casehub/billing', name: 'Financeiro' },
  { url: '/casehub/controladoria', name: 'Controladoria' },
  { url: '/casehub/controladoria/indices', name: 'Indices Economicos' },
  { url: '/casehub/prazos', name: 'Prazos' },
  { url: '/casehub/tribunal', name: 'Tribunal' },
  { url: '/casehub/tools', name: 'Ferramentas' },
  { url: '/casehub/tools/rescisao', name: 'Rescisao' },
  { url: '/casehub/checklists', name: 'Checklists' },
  { url: '/casehub/assistente', name: 'Assistente' },
  { url: '/casehub/assistente/config', name: 'Assistente Config' },
  { url: '/casehub/reports', name: 'Relatorios' },
  { url: '/casehub/leads', name: 'Leads CRM' },
  { url: '/casehub/documents', name: 'Documentos' },
  { url: '/casehub/settings', name: 'Configuracoes' },
  { url: '/casehub/notifications', name: 'Notificacoes' },
  { url: '/casehub/admin', name: 'Admin' },
  { url: '/casehub/admin/customizacao', name: 'Customizacao' },
];

const DARK_MODE_PAGES = ['dashboard', 'clients', 'tasks/kanban'];
const MAX_CLICKS_PER_PAGE = 12;

function slugify(url) {
  return url.replace(/^\/casehub\//, '').replace(/\//g, '-') || 'root';
}

function sanitize(text) {
  return (text || 'unknown').replace(/[^a-zA-Z0-9_-]/g, '_').substring(0, 40);
}

test('Final comprehensive visual audit - CaseHub Lite', async ({ page }) => {
  test.setTimeout(600000); // 10 min

  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

  let shotCount = 0;
  const report = {
    run_date: new Date().toISOString(),
    base_url: BASE,
    credentials: process.env.CASEHUB_TEST_EMAIL || 'qa@casehub.internal',
    pages: [],
    dark_mode_tests: [],
    split_screen_test: null,
    maestro_fab_test: null,
    total_screenshots: 0,
    total_pages_visited: 0,
    total_issues: 0,
    issues_summary: [],
  };

  async function shot(name) {
    shotCount++;
    const filename = `${String(shotCount).padStart(3, '0')}-${name}.png`;
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, filename), fullPage: true });
    return filename;
  }

  async function shotViewport(name, w, h) {
    const oldVP = page.viewportSize();
    await page.setViewportSize({ width: w, height: h });
    await page.waitForTimeout(800);
    const f = await shot(name);
    await page.setViewportSize({ width: oldVP.width, height: oldVP.height });
    await page.waitForTimeout(500);
    return f;
  }

  // ========== LOGIN ==========
  console.log('=== LOGIN ===');
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(2000);
  await shot('login-page');

  const emailInput = page.locator('input[name="email"], input[type="email"], input[name="username"]').first();
  const passInput = page.locator('input[name="password"], input[type="password"]').first();

  await emailInput.fill(process.env.CASEHUB_TEST_EMAIL || 'qa@casehub.internal');
  await passInput.fill(process.env.CASEHUB_TEST_PASSWORD || '');

  const submitBtn = page.locator('button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Entrar")').first();
  await submitBtn.click();
  await page.waitForTimeout(4000);
  await page.waitForLoadState('domcontentloaded').catch(() => {});

  const postLoginUrl = page.url();
  console.log('Post-login URL:', postLoginUrl);
  await shot('post-login');

  // Check if login succeeded (should not still be on login page)
  const loginFailed = postLoginUrl.includes('/login');
  if (loginFailed) {
    console.log('WARNING: Login may have failed. Trying alternate approach...');
    // Try clicking any visible error/flash to get more info
    const flash = await page.locator('.alert, .flash, .error-message').first().textContent({ timeout: 2000 }).catch(() => '');
    console.log('Flash message:', flash);
    await shot('login-failed');
    report.issues_summary.push({ page: 'login', issue: `Login may have failed: ${flash}` });
  }

  // ========== VISIT EVERY PAGE ==========
  for (let i = 0; i < PAGES.length; i++) {
    const pg = PAGES[i];
    const slug = slugify(pg.url);
    const pageReport = {
      url: pg.url,
      name: pg.name,
      http_status: 200,
      load_time_ms: 0,
      title: '',
      screenshots: [],
      elements_found: 0,
      elements_clicked: 0,
      issues: [],
    };

    console.log(`\n=== [${i + 1}/${PAGES.length}] ${pg.name} (${pg.url}) ===`);

    // Navigate and measure load time
    const startTime = Date.now();
    let response;
    try {
      response = await page.goto(pg.url, { waitUntil: 'domcontentloaded', timeout: 20000 });
    } catch (e) {
      pageReport.issues.push(`Navigation failed: ${e.message.substring(0, 100)}`);
      report.pages.push(pageReport);
      report.total_issues++;
      continue;
    }
    await page.waitForTimeout(2000);
    pageReport.load_time_ms = Date.now() - startTime;
    pageReport.http_status = response ? response.status() : 0;
    pageReport.title = await page.title();

    // Check for redirects back to login
    if (page.url().includes('/login')) {
      pageReport.issues.push('Redirected to login - session lost?');
      report.total_issues++;
      // Try re-login
      await emailInput.fill(process.env.CASEHUB_TEST_EMAIL || 'qa@casehub.internal').catch(() => {});
      await passInput.fill(process.env.CASEHUB_TEST_PASSWORD || '').catch(() => {});
      await submitBtn.click().catch(() => {});
      await page.waitForTimeout(3000);
      continue;
    }

    report.total_pages_visited++;

    // Desktop screenshot (1440x900)
    const desktopShot = await shot(`${slug}-desktop`);
    pageReport.screenshots.push(desktopShot);

    // Mobile screenshot (375x812)
    const mobileShot = await shotViewport(`${slug}-mobile`, 375, 812);
    pageReport.screenshots.push(mobileShot);

    // ---- Click visible buttons/links on this page ----
    const clickableSelector = [
      'button:visible',
      'a[href]:visible',
      '[role="button"]:visible',
      '.btn:visible',
      '[role="tab"]:visible',
    ].join(', ');

    let clickables;
    let clickCount = 0;
    try {
      clickables = page.locator(clickableSelector).filter({ hasText: /.+/ });
      clickCount = await clickables.count();
    } catch {
      clickCount = 0;
    }
    pageReport.elements_found = clickCount;
    console.log(`  ${clickCount} clickable elements`);

    let clicked = 0;
    for (let j = 0; j < clickCount && clicked < MAX_CLICKS_PER_PAGE; j++) {
      const el = clickables.nth(j);
      let elText = '';
      try {
        if (!(await el.isVisible({ timeout: 1000 }))) continue;
        elText = (await el.innerText({ timeout: 1000 })).trim().substring(0, 50);
        if (!elText) continue;

        // Skip dangerous links
        const href = await el.getAttribute('href').catch(() => null);
        if (href && (href.includes('logout') || href.includes('login') || href.includes('delete') || href.includes('remove'))) continue;

        // Skip sidebar nav links (they change pages)
        const isInSidebar = await el.evaluate(e => {
          return !!e.closest('.sidebar, nav.sidebar, .side-nav, #sidebar');
        }).catch(() => false);
        if (isInSidebar && href && href.startsWith('/casehub/')) continue;

        const urlBefore = page.url();
        console.log(`  [${clicked + 1}] Click: "${elText.substring(0, 30)}"`);
        await el.click({ timeout: 5000, force: false });
        clicked++;
        pageReport.elements_clicked++;
        await page.waitForTimeout(1500);

        const urlAfter = page.url();
        const urlChanged = urlAfter !== urlBefore;

        // Check for modal
        const modalVisible = await page.locator('.modal.show, .modal[style*="display: block"], [role="dialog"], .swal2-popup, .swal2-container, .offcanvas.show').first().isVisible({ timeout: 800 }).catch(() => false);

        if (urlChanged || modalVisible) {
          const actionShot = await shot(`${slug}-click-${sanitize(elText)}`);
          pageReport.screenshots.push(actionShot);
        }

        // Close modal
        if (modalVisible) {
          await page.keyboard.press('Escape');
          await page.waitForTimeout(500);
          const closeBtn = page.locator('.modal .close, .modal .btn-close, .swal2-close, [data-dismiss="modal"], [data-bs-dismiss="modal"], .offcanvas .btn-close').first();
          if (await closeBtn.isVisible({ timeout: 500 }).catch(() => false)) {
            await closeBtn.click({ timeout: 2000 }).catch(() => {});
            await page.waitForTimeout(500);
          }
        }

        // If URL changed, go back
        if (urlChanged && !urlAfter.includes(slug.replace(/-/g, '/'))) {
          await page.goto(pg.url, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => {});
          await page.waitForTimeout(1000);
        }
      } catch (err) {
        // Silently continue
        if (!page.url().includes(slug.replace(/-/g, '/')) && !page.url().includes(pg.url.split('/').pop())) {
          await page.goto(pg.url, { waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => {});
          await page.waitForTimeout(1000);
        }
      }
    }

    report.pages.push(pageReport);
    console.log(`  Screenshots: ${pageReport.screenshots.length}, Clicked: ${clicked}, Issues: ${pageReport.issues.length}`);
  }

  // ========== DARK MODE TOGGLE ==========
  console.log('\n=== DARK MODE TESTS ===');
  for (const pagePath of DARK_MODE_PAGES) {
    const fullUrl = `${BASE}/${pagePath}`;
    const slug = pagePath.replace(/\//g, '-');
    console.log(`Dark mode: ${pagePath}`);

    await page.goto(fullUrl, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);

    // Find theme toggle
    const themeToggle = page.locator('#theme-toggle, button[onclick*="theme"], [class*="theme-toggle"], button:has(i.fa-moon), button:has(i.fa-sun), .dark-mode-toggle').first();
    const dmResult = { page: pagePath, toggled: false, screenshots: [] };

    if (await themeToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      // Light mode screenshot
      const lightShot = await shot(`${slug}-light-mode`);
      dmResult.screenshots.push(lightShot);

      // Toggle to dark
      await themeToggle.click();
      await page.waitForTimeout(1500);
      const darkShot = await shot(`${slug}-dark-mode`);
      dmResult.screenshots.push(darkShot);
      dmResult.toggled = true;

      // Toggle back
      await themeToggle.click().catch(() => {});
      await page.waitForTimeout(500);
      console.log(`  Dark mode toggled OK`);
    } else {
      console.log(`  Theme toggle not found`);
      dmResult.screenshots.push(await shot(`${slug}-no-toggle`));
    }
    report.dark_mode_tests.push(dmResult);
  }

  // ========== SPLIT-SCREEN ==========
  console.log('\n=== SPLIT-SCREEN TEST ===');
  await page.goto(`${BASE}/dashboard`, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(2000);

  const splitScreenResult = { tested: false, screenshots: [] };
  // Look for split-screen trigger
  const splitBtn = page.locator('button:has-text("Split"), button:has(i.fa-columns), [class*="split-screen"], [data-action="split"], button[title*="split"], button[title*="Split"]').first();
  if (await splitBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await splitBtn.click();
    await page.waitForTimeout(2000);
    splitScreenResult.tested = true;
    splitScreenResult.screenshots.push(await shot('split-screen-active'));
    console.log('  Split-screen activated');

    // Close split
    const closeSplit = page.locator('button:has-text("Close"), .split-close, button[title*="close"]').first();
    if (await closeSplit.isVisible({ timeout: 1000 }).catch(() => false)) {
      await closeSplit.click();
      await page.waitForTimeout(1000);
    }
  } else {
    console.log('  Split-screen button not found, checking sidebar...');
    // Try keyboard shortcut or other trigger
    const sidebarSplit = page.locator('a[href*="split"], [data-feature="split"]').first();
    if (await sidebarSplit.isVisible({ timeout: 1000 }).catch(() => false)) {
      await sidebarSplit.click();
      await page.waitForTimeout(2000);
      splitScreenResult.tested = true;
      splitScreenResult.screenshots.push(await shot('split-screen-sidebar'));
    } else {
      splitScreenResult.screenshots.push(await shot('split-screen-not-found'));
    }
  }
  report.split_screen_test = splitScreenResult;

  // ========== MAESTRO FAB ==========
  console.log('\n=== MAESTRO FAB TEST ===');
  await page.goto(`${BASE}/dashboard`, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(2000);

  const maestroResult = { found: false, clicked: false, screenshots: [] };
  // Look for floating action button
  const fabSelectors = [
    '.fab', '.floating-action-btn', '[class*="fab"]',
    'button[class*="float"]', '.maestro-fab', '#maestro-fab',
    'button[style*="position: fixed"]', '[class*="maestro"]',
    '.btn-floating', 'button:has(i.fa-robot)', 'button:has(i.fa-magic)',
    'button:has(i.fa-wand)', '[class*="assistant"]',
  ];

  for (const sel of fabSelectors) {
    const fab = page.locator(sel).first();
    if (await fab.isVisible({ timeout: 1000 }).catch(() => false)) {
      maestroResult.found = true;
      console.log(`  Found FAB with selector: ${sel}`);
      maestroResult.screenshots.push(await shot('maestro-fab-visible'));

      await fab.click();
      await page.waitForTimeout(2000);
      maestroResult.clicked = true;
      maestroResult.screenshots.push(await shot('maestro-fab-clicked'));

      // Close if panel opened
      await page.keyboard.press('Escape');
      await page.waitForTimeout(500);
      break;
    }
  }

  if (!maestroResult.found) {
    console.log('  Maestro FAB not found on dashboard');
    maestroResult.screenshots.push(await shot('maestro-fab-not-found'));

    // Try assistente page
    await page.goto(`${BASE}/assistente`, { waitUntil: 'domcontentloaded', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(2000);
    maestroResult.screenshots.push(await shot('maestro-assistente-page'));
  }
  report.maestro_fab_test = maestroResult;

  // ========== SAVE REPORT ==========
  report.total_screenshots = shotCount;
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2));

  console.log('\n========================================');
  console.log('FINAL AUDIT COMPLETE');
  console.log(`Total screenshots: ${shotCount}`);
  console.log(`Pages visited: ${report.total_pages_visited}`);
  console.log(`Total issues: ${report.total_issues}`);
  console.log(`Report: ${REPORT_PATH}`);
  console.log('========================================');
});
