// @ts-check
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const PAGES = [
  '/casehub/dashboard',
  '/casehub/clients',
  '/casehub/clients/new',
  '/casehub/cases',
  '/casehub/cases/new',
  '/casehub/tasks/kanban',
  '/casehub/calendar',
  '/casehub/emails',
  '/casehub/billing',
  '/casehub/controladoria',
  '/casehub/controladoria/indices',
  '/casehub/prazos',
  '/casehub/tribunal',
  '/casehub/tools',
  '/casehub/tools/rescisao',
  '/casehub/checklists',
  '/casehub/assistente',
  '/casehub/assistente/config',
  '/casehub/reports',
  '/casehub/settings',
  '/casehub/notifications',
  '/casehub/admin',
  '/casehub/admin/customizacao',
];

const MAX_CLICKS_PER_PAGE = 15;
const CLICK_TIMEOUT = 5000;
const SCREENSHOT_DIR = path.join(__dirname, '..', 'test-results', 'visual-audit');
const REPORT_PATH = path.join(SCREENSHOT_DIR, 'audit-report.json');

function slugify(url) {
  return url.replace(/^\/casehub\//, '').replace(/\//g, '-') || 'root';
}

function sanitize(text) {
  return (text || 'unknown').replace(/[^a-zA-Z0-9_-]/g, '_').substring(0, 40);
}

test('Visual audit of all CaseHub Lite pages', async ({ page, context }) => {
  test.setTimeout(600000); // 10 minutes total

  // Ensure screenshot directory exists
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

  let screenshotCounter = 0;
  const report = {
    pages: [],
    total_screenshots: 0,
    total_pages: PAGES.length,
    total_errors: 0,
    timestamp: new Date().toISOString(),
  };

  // ---- LOGIN ----
  console.log('Logging in...');
  await page.goto('/casehub/login', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(1000);

  // Try to fill login form
  const emailInput = page.locator('input[name="email"], input[type="email"], input[name="username"]').first();
  const passInput = page.locator('input[name="password"], input[type="password"]').first();

  await emailInput.fill('victor@vingren.me');
  await passInput.fill('demo123');

  // Click submit
  const submitBtn = page.locator('button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Entrar")').first();
  await submitBtn.click();
  await page.waitForTimeout(3000);
  await page.waitForLoadState('networkidle').catch(() => {});

  console.log('Login done. Current URL:', page.url());

  // Take a post-login screenshot
  screenshotCounter++;
  const loginScreenshot = `${String(screenshotCounter).padStart(3, '0')}-post-login.png`;
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, loginScreenshot), fullPage: true });

  // ---- AUDIT EACH PAGE ----
  for (let pageIdx = 0; pageIdx < PAGES.length; pageIdx++) {
    const pageUrl = PAGES[pageIdx];
    const pageSlug = slugify(pageUrl);
    const pageReport = {
      url: pageUrl,
      title: '',
      screenshots: [],
      elements_found: 0,
      elements_clicked: 0,
      modals_opened: 0,
      errors: [],
      mobile_screenshot: '',
    };

    console.log(`\n=== [${pageIdx + 1}/${PAGES.length}] ${pageUrl} ===`);

    // Navigate to the page
    try {
      await page.goto(pageUrl, { waitUntil: 'networkidle', timeout: 20000 });
    } catch (e) {
      try {
        await page.goto(pageUrl, { waitUntil: 'domcontentloaded', timeout: 15000 });
      } catch (e2) {
        pageReport.errors.push(`Navigation failed: ${e2.message}`);
        report.pages.push(pageReport);
        report.total_errors++;
        continue;
      }
    }
    await page.waitForTimeout(1500);

    pageReport.title = await page.title();

    // 1) Full page screenshot - initial state (desktop)
    screenshotCounter++;
    const initialScreenshot = `${String(screenshotCounter).padStart(3, '0')}-${pageSlug}-initial.png`;
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, initialScreenshot), fullPage: true });
    pageReport.screenshots.push(initialScreenshot);

    // 2) Find clickable elements
    const clickableSelector = 'button, a[href], select, [role="button"], .btn, [role="tab"], [role="menuitem"]';
    const allClickables = page.locator(clickableSelector).filter({ hasText: /.+/ });
    let count = 0;
    try {
      count = await allClickables.count();
    } catch {
      count = 0;
    }
    pageReport.elements_found = count;
    console.log(`  Found ${count} clickable elements`);

    // Click up to MAX_CLICKS_PER_PAGE elements
    let clicked = 0;
    for (let i = 0; i < count && clicked < MAX_CLICKS_PER_PAGE; i++) {
      const el = allClickables.nth(i);
      let elText = '';

      try {
        const visible = await el.isVisible({ timeout: 2000 });
        if (!visible) continue;

        elText = (await el.innerText({ timeout: 2000 })).trim().substring(0, 50);
        if (!elText) continue;

        // Skip navigation links that would leave casehub entirely
        const tagName = await el.evaluate(e => e.tagName.toLowerCase()).catch(() => '');
        const href = await el.getAttribute('href').catch(() => null);

        // Skip logout links
        if (href && (href.includes('logout') || href.includes('login'))) {
          continue;
        }

        // Record current state
        const urlBefore = page.url();
        const htmlBefore = await page.locator('body').innerHTML({ timeout: 3000 }).catch(() => '');

        console.log(`  [${clicked + 1}] Clicking: "${elText.substring(0, 30)}"`);

        // Click the element
        await el.click({ timeout: CLICK_TIMEOUT, force: false });
        clicked++;
        pageReport.elements_clicked++;

        await page.waitForTimeout(2000);

        const urlAfter = page.url();
        const htmlAfter = await page.locator('body').innerHTML({ timeout: 3000 }).catch(() => '');

        // Check if something changed
        const urlChanged = urlAfter !== urlBefore;
        const contentChanged = htmlAfter !== htmlBefore;

        // Check for modals
        const modalVisible = await page.locator('.modal.show, .modal[style*="display: block"], [role="dialog"], .swal2-popup, .swal2-container').first().isVisible({ timeout: 1000 }).catch(() => false);

        if (modalVisible) {
          pageReport.modals_opened++;
        }

        if (urlChanged || contentChanged || modalVisible) {
          screenshotCounter++;
          const actionSlug = sanitize(elText);
          const actionScreenshot = `${String(screenshotCounter).padStart(3, '0')}-${pageSlug}-click-${actionSlug}.png`;
          await page.screenshot({ path: path.join(SCREENSHOT_DIR, actionScreenshot), fullPage: true });
          pageReport.screenshots.push(actionScreenshot);
        }

        // Close modal if opened
        if (modalVisible) {
          await page.keyboard.press('Escape');
          await page.waitForTimeout(500);
          // Try clicking dismiss buttons
          const closeBtn = page.locator('.modal .close, .modal .btn-close, .swal2-close, [data-dismiss="modal"], [data-bs-dismiss="modal"]').first();
          if (await closeBtn.isVisible({ timeout: 500 }).catch(() => false)) {
            await closeBtn.click({ timeout: 2000 }).catch(() => {});
            await page.waitForTimeout(500);
          }
        }

        // If URL changed, go back
        if (urlChanged) {
          try {
            await page.goto(pageUrl, { waitUntil: 'networkidle', timeout: 15000 });
          } catch {
            await page.goto(pageUrl, { waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => {});
          }
          await page.waitForTimeout(1000);
        }
      } catch (err) {
        const errMsg = `Element "${elText || i}": ${err.message.substring(0, 100)}`;
        pageReport.errors.push(errMsg);
        report.total_errors++;

        // Make sure we're still on the right page
        if (!page.url().includes(pageUrl.replace('/casehub/', ''))) {
          try {
            await page.goto(pageUrl, { waitUntil: 'domcontentloaded', timeout: 10000 });
            await page.waitForTimeout(1000);
          } catch {
            // give up on this page
            break;
          }
        }
      }
    }

    // 3) Mobile screenshot
    try {
      await page.setViewportSize({ width: 375, height: 812 });
      await page.waitForTimeout(1000);
      screenshotCounter++;
      const mobileScreenshot = `${String(screenshotCounter).padStart(3, '0')}-${pageSlug}-mobile.png`;
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, mobileScreenshot), fullPage: true });
      pageReport.mobile_screenshot = mobileScreenshot;
      pageReport.screenshots.push(mobileScreenshot);

      // Reset viewport
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.waitForTimeout(500);
    } catch (err) {
      pageReport.errors.push(`Mobile screenshot failed: ${err.message.substring(0, 100)}`);
      report.total_errors++;
      // Reset viewport anyway
      await page.setViewportSize({ width: 1440, height: 900 }).catch(() => {});
    }

    report.pages.push(pageReport);
    console.log(`  Screenshots: ${pageReport.screenshots.length}, Clicked: ${pageReport.elements_clicked}, Modals: ${pageReport.modals_opened}, Errors: ${pageReport.errors.length}`);
  }

  // ---- SAVE REPORT ----
  report.total_screenshots = screenshotCounter;
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2));
  console.log(`\n=== AUDIT COMPLETE ===`);
  console.log(`Total screenshots: ${report.total_screenshots}`);
  console.log(`Total pages: ${report.total_pages}`);
  console.log(`Total errors: ${report.total_errors}`);
  console.log(`Report saved to: ${REPORT_PATH}`);
});
