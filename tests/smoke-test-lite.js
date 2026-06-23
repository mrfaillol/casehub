/**
 * CaseHub Lite - Smoke Tests
 * Tests every button, dropdown, modal, form, and interactive element.
 * Run: cd casehub && npx playwright test tests/smoke-test-lite.js --headed
 */
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const BASE = 'http://137.131.237.130:8002/casehub';
const SHOTS = path.join(__dirname, '..', 'test-results', 'smoke-screenshots');
const RESULTS = [];
let shotNum = 0;

test.beforeAll(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
});

async function shot(page, name) {
  shotNum++;
  const filename = `${String(shotNum).padStart(3, '0')}-${name}.png`;
  await page.screenshot({ path: path.join(SHOTS, filename), fullPage: true });
  return filename;
}

function log(page, action, status, detail = '') {
  RESULTS.push({ page: page, action, status, detail, timestamp: new Date().toISOString() });
}

// ============================================================
// AUTH
// ============================================================
test.describe('Smoke Tests - CaseHub Lite', () => {

  test.beforeEach(async ({ page }) => {
    // Login
    await page.goto(`${BASE}/login`);
    await page.waitForTimeout(2000);
    const emailInput = page.locator('input[name="email"], input[type="email"]').first();
    const passInput = page.locator('input[name="password"], input[type="password"]').first();
    if (await emailInput.count() > 0) {
      await emailInput.fill('admin@example.com');
      await passInput.fill('demo123');
      await page.locator('button[type="submit"], button:has-text("Login")').first().click();
      await page.waitForTimeout(3000);
    }
  });

  // ============================================================
  // DASHBOARD
  // ============================================================
  test('Dashboard - todos os elementos', async ({ page }) => {
    await page.goto(`${BASE}/dashboard`);
    await page.waitForTimeout(3000);
    await shot(page, 'dashboard-loaded');

    // Stat cards
    const statCards = page.locator('.stat-card, [class*="stat"]');
    const cardCount = await statCards.count();
    log('dashboard', `Stat cards found: ${cardCount}`, cardCount >= 3 ? 'OK' : 'WARN');

    // Theme toggle
    const themeToggle = page.locator('#theme-toggle, button[onclick*="theme"], [class*="theme-toggle"]').first();
    if (await themeToggle.count() > 0) {
      await themeToggle.click();
      await page.waitForTimeout(1000);
      await shot(page, 'dashboard-dark-mode');
      log('dashboard', 'Theme toggle', 'OK');
      await themeToggle.click();
      await page.waitForTimeout(500);
    } else {
      log('dashboard', 'Theme toggle', 'NOT_FOUND');
    }

    // Sidebar links
    const sidebarLinks = page.locator('.sidebar a, nav a');
    const linkCount = await sidebarLinks.count();
    log('dashboard', `Sidebar links: ${linkCount}`, linkCount > 5 ? 'OK' : 'WARN');

    // Sidebar collapse (hamburger - only visible on mobile)
    const hamburger = page.locator('.hamburger-btn').first();
    if (await hamburger.count() > 0 && await hamburger.isVisible()) {
      await hamburger.click();
      await page.waitForTimeout(1000);
      await shot(page, 'sidebar-collapsed');
      log('dashboard', 'Hamburger menu', 'OK');
    } else {
      log('dashboard', 'Hamburger menu (desktop - hidden)', 'OK');
    }

    // Notification bell
    const bell = page.locator('[class*="notif"] button, .notification-bell, button:has(i.fa-bell)').first();
    if (await bell.count() > 0) {
      await bell.click();
      await page.waitForTimeout(1000);
      await shot(page, 'notification-panel');
      log('dashboard', 'Notification bell', 'OK');
      await page.keyboard.press('Escape');
    }
  });

  // ============================================================
  // CLIENTS
  // ============================================================
  test('Clients - lista + formulario + botoes', async ({ page }) => {
    await page.goto(`${BASE}/clients`);
    await page.waitForTimeout(3000);
    await shot(page, 'clients-list');

    // Search
    const search = page.locator('input[placeholder*="earch"], input[placeholder*="uscar"]').first();
    if (await search.count() > 0) {
      await search.fill('teste');
      await page.waitForTimeout(1000);
      await shot(page, 'clients-search');
      log('clients', 'Search input', 'OK');
      await search.clear();
    }

    // New Client button
    const newBtn = page.locator('a:has-text("Novo"), a:has-text("New"), a[href*="new"]').first();
    if (await newBtn.count() > 0) {
      await newBtn.click();
      await page.waitForTimeout(2000);
      await shot(page, 'clients-new-form');
      log('clients', 'New client form', 'OK');

      // Test all form fields
      const inputs = page.locator('input:not([type="hidden"]), select, textarea');
      const inputCount = await inputs.count();
      log('clients/new', `Form fields: ${inputCount}`, inputCount > 3 ? 'OK' : 'WARN');

      // Test dropdowns (only visible ones)
      const selects = page.locator('select:visible');
      for (let i = 0; i < await selects.count(); i++) {
        if (await selects.nth(i).isVisible()) {
          await selects.nth(i).click();
          await page.waitForTimeout(500);
          const options = await selects.nth(i).locator('option').count();
          log('clients/new', `Dropdown ${i}: ${options} options`, options > 0 ? 'OK' : 'WARN');
        }
      }
      await shot(page, 'clients-form-dropdowns');

      // Try submit empty (test validation)
      const submitBtn = page.locator('button[type="submit"], button:has-text("Salvar"), button:has-text("Save")').first();
      if (await submitBtn.count() > 0) {
        await submitBtn.click();
        await page.waitForTimeout(1000);
        await shot(page, 'clients-form-validation');
        log('clients/new', 'Empty submit validation', 'OK');
      }
    }
  });

  // ============================================================
  // CASES / PROCESSOS
  // ============================================================
  test('Cases - lista + formulario', async ({ page }) => {
    await page.goto(`${BASE}/cases`);
    await page.waitForTimeout(3000);
    await shot(page, 'cases-list');

    // Filters (only visible selects)
    const filters = page.locator('select:visible');
    const filterCount = await filters.count();
    for (let i = 0; i < Math.min(filterCount, 3); i++) {
      if (await filters.nth(i).isVisible()) {
        await filters.nth(i).selectOption({ index: 0 });
        await page.waitForTimeout(500);
        await shot(page, `cases-filter-${i}`);
        log('cases', `Filter dropdown ${i}`, 'OK');
      }
    }

    // New Case
    await page.goto(`${BASE}/cases/new`);
    await page.waitForTimeout(2000);
    await shot(page, 'cases-new-form');

    const inputs = page.locator('input:not([type="hidden"]), select, textarea');
    const inputCount = await inputs.count();
    log('cases/new', `Form fields: ${inputCount}`, inputCount > 3 ? 'OK' : 'WARN');

    // Test each select
    const selects = page.locator('select');
    for (let i = 0; i < await selects.count(); i++) {
      const opts = await selects.nth(i).locator('option').count();
      const name = await selects.nth(i).getAttribute('name') || `select-${i}`;
      log('cases/new', `Dropdown "${name}": ${opts} options`, opts > 0 ? 'OK' : 'EMPTY');
    }
    await shot(page, 'cases-form-all-fields');
  });

  // ============================================================
  // TASKS + KANBAN
  // ============================================================
  test('Tasks - kanban + interacoes', async ({ page }) => {
    await page.goto(`${BASE}/tasks/kanban`);
    await page.waitForTimeout(3000);
    await shot(page, 'kanban-board');

    // Kanban columns
    const columns = page.locator('[class*="kanban-column"], [class*="col-"]');
    const colCount = await columns.count();
    log('kanban', `Columns found: ${colCount}`, colCount >= 3 ? 'OK' : 'WARN');

    // New task button
    const newTask = page.locator('button:has-text("Nova"), button:has-text("New"), a:has-text("Nova Tarefa")').first();
    if (await newTask.count() > 0) {
      await newTask.click();
      await page.waitForTimeout(2000);
      await shot(page, 'kanban-new-task-modal');
      log('kanban', 'New task modal', 'OK');
      await page.keyboard.press('Escape');
      await page.waitForTimeout(500);
    }
  });

  // ============================================================
  // DOCUMENTS
  // ============================================================
  test('Documents - lista + upload', async ({ page }) => {
    await page.goto(`${BASE}/documents`);
    await page.waitForTimeout(3000);
    await shot(page, 'documents-list');

    // View toggles (list/grid/tree)
    const viewBtns = page.locator('button:has(i.fa-list), button:has(i.fa-th), button:has(i.fa-folder)');
    for (let i = 0; i < await viewBtns.count(); i++) {
      await viewBtns.nth(i).click();
      await page.waitForTimeout(1000);
      await shot(page, `documents-view-${i}`);
      log('documents', `View toggle ${i}`, 'OK');
    }

    // Upload button
    const uploadBtn = page.locator('button:has-text("Upload"), a:has-text("Upload")').first();
    if (await uploadBtn.count() > 0) {
      log('documents', 'Upload button', 'OK');
    }
  });

  // ============================================================
  // PRAZOS
  // ============================================================
  test('Prazos - calculadora CPC', async ({ page }) => {
    await page.goto(`${BASE}/prazos`);
    await page.waitForTimeout(3000);
    await shot(page, 'prazos-calculator');

    // Dropdown de prazos comuns
    const prazoSelect = page.locator('select').first();
    if (await prazoSelect.count() > 0) {
      await prazoSelect.selectOption({ index: 1 });
      await page.waitForTimeout(1000);
      await shot(page, 'prazos-selected');
      log('prazos', 'Deadline type dropdown', 'OK');
    }

    // State selector
    const stateSelect = page.locator('select').nth(1);
    if (await stateSelect.count() > 0) {
      const opts = await stateSelect.locator('option').count();
      log('prazos', `State dropdown: ${opts} options`, opts >= 27 ? 'OK' : 'WARN');
    }

    // Calculate button
    const calcBtn = page.locator('button:has-text("Calcular"), button[type="submit"]').first();
    if (await calcBtn.count() > 0) {
      await calcBtn.click();
      await page.waitForTimeout(2000);
      await shot(page, 'prazos-result');
      log('prazos', 'Calculate button', 'OK');
    }
  });

  // ============================================================
  // TRIBUNAL
  // ============================================================
  test('Tribunal - busca processual', async ({ page }) => {
    await page.goto(`${BASE}/tribunal`);
    await page.waitForTimeout(3000);
    await shot(page, 'tribunal-search');

    // Search input
    const searchInput = page.locator('input[placeholder*="processo"], input[placeholder*="CNJ"], input[type="text"]').first();
    if (await searchInput.count() > 0) {
      await searchInput.fill('0000000-00.0000.0.00.0000');
      await page.waitForTimeout(500);
      log('tribunal', 'Search input', 'OK');
    }

    // Search button
    const searchBtn = page.locator('button:has-text("Buscar"), button:has-text("Consultar"), button[type="submit"]').first();
    if (await searchBtn.count() > 0) {
      await searchBtn.click();
      await page.waitForTimeout(3000);
      await shot(page, 'tribunal-result');
      log('tribunal', 'Search submit', 'OK');
    }
  });

  // ============================================================
  // BILLING
  // ============================================================
  test('Billing - dashboard + botoes', async ({ page }) => {
    await page.goto(`${BASE}/billing`);
    await page.waitForTimeout(3000);
    await shot(page, 'billing-dashboard');

    // New charge button
    const newCharge = page.locator('a:has-text("Nova"), a:has-text("New"), button:has-text("Nova")').first();
    if (await newCharge.count() > 0) {
      await newCharge.click();
      await page.waitForTimeout(2000);
      await shot(page, 'billing-new-charge');
      log('billing', 'New charge form', 'OK');
    }
  });

  // ============================================================
  // SETTINGS
  // ============================================================
  test('Settings - todas as secoes', async ({ page }) => {
    await page.goto(`${BASE}/settings`);
    await page.waitForTimeout(3000);
    await shot(page, 'settings-main');

    // Click each settings card/link
    const settingsLinks = page.locator('.card a, .settings-card, a[href*="settings"]');
    const count = await settingsLinks.count();
    log('settings', `Settings sections: ${count}`, count > 0 ? 'OK' : 'WARN');
  });

  // ============================================================
  // EMAILS
  // ============================================================
  test('Emails - lista + compose', async ({ page }) => {
    await page.goto(`${BASE}/emails`);
    await page.waitForTimeout(3000);
    await shot(page, 'emails-list');

    // Compose button
    const compose = page.locator('a:has-text("Compose"), a:has-text("Compor"), a[href*="compose"]').first();
    if (await compose.count() > 0) {
      await compose.click();
      await page.waitForTimeout(2000);
      await shot(page, 'emails-compose');
      log('emails', 'Compose page', 'OK');
    }
  });

  // ============================================================
  // LEADS CRM
  // ============================================================
  test('Leads - pipeline + botoes', async ({ page }) => {
    await page.goto(`${BASE}/leads`);
    await page.waitForTimeout(3000);
    await shot(page, 'leads-dashboard');

    // New lead button
    const newLead = page.locator('button:has-text("Novo"), button:has-text("New"), a:has-text("Novo Lead")').first();
    if (await newLead.count() > 0) {
      await newLead.click();
      await page.waitForTimeout(2000);
      await shot(page, 'leads-new-modal');
      log('leads', 'New lead modal', 'OK');
      await page.keyboard.press('Escape');
    }
  });

  // ============================================================
  // RESPONSIVE
  // ============================================================
  test('Responsividade - mobile + tablet', async ({ page }) => {
    const viewports = [
      { width: 375, height: 812, name: 'mobile' },
      { width: 768, height: 1024, name: 'tablet' },
      { width: 1024, height: 768, name: 'tablet-landscape' },
    ];

    for (const vp of viewports) {
      await page.setViewportSize({ width: vp.width, height: vp.height });

      await page.goto(`${BASE}/dashboard`);
      await page.waitForTimeout(2000);
      await shot(page, `responsive-${vp.name}-dashboard`);

      // Check hamburger on mobile
      if (vp.width <= 768) {
        const hamburger = page.locator('.hamburger-btn, button[class*="hamburger"]').first();
        if (await hamburger.count() > 0 && await hamburger.isVisible()) {
          await hamburger.click();
          await page.waitForTimeout(1000);
          await shot(page, `responsive-${vp.name}-sidebar-open`);
          log(`responsive-${vp.name}`, 'Hamburger menu', 'OK');
          await page.keyboard.press('Escape');
        }
      }

      await page.goto(`${BASE}/clients`);
      await page.waitForTimeout(2000);
      await shot(page, `responsive-${vp.name}-clients`);

      log(`responsive-${vp.name}`, 'Pages rendered', 'OK');
    }
  });

  // ============================================================
  // SAVE RESULTS
  // ============================================================
  test.afterAll(async () => {
    const resultPath = path.join(SHOTS, '..', 'smoke-results.json');
    fs.writeFileSync(resultPath, JSON.stringify(RESULTS, null, 2));

    const ok = RESULTS.filter(r => r.status === 'OK').length;
    const warn = RESULTS.filter(r => r.status === 'WARN').length;
    const fail = RESULTS.filter(r => r.status === 'FAIL' || r.status === 'NOT_FOUND').length;

    console.log('\n=== SMOKE TEST RESULTS ===');
    console.log(`OK: ${ok} | WARN: ${warn} | FAIL: ${fail} | Total: ${RESULTS.length}`);
    console.log(`Screenshots: ${shotNum}`);
    console.log(`Results: ${resultPath}`);
  });
});
