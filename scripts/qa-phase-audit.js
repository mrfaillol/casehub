/**
 * CaseHub QA Phase Audit Script
 *
 * Usage:
 *   node scripts/qa-phase-audit.js \
 *     --url http://localhost:5000 \
 *     --phase 1 \
 *     --credentials admin@casehub.legal:password \
 *     --output-dir ./qa-output
 *
 * Requires: npx playwright install chromium
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------------------
// CLI args
// ---------------------------------------------------------------------------

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    url: 'http://localhost:5000',
    phase: '0',
    credentials: '',
    outputDir: './qa-output',
  };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--url':
        opts.url = args[++i];
        break;
      case '--phase':
        opts.phase = args[++i];
        break;
      case '--credentials':
        opts.credentials = args[++i];
        break;
      case '--output-dir':
        opts.outputDir = args[++i];
        break;
    }
  }

  if (!opts.credentials) {
    console.error('ERROR: --credentials user:pass is required');
    process.exit(1);
  }

  const [username, ...passParts] = opts.credentials.split(':');
  opts.username = username;
  opts.password = passParts.join(':');

  return opts;
}

// ---------------------------------------------------------------------------
// Views to audit
// ---------------------------------------------------------------------------

const VIEWS = [
  { name: 'login', path: '/casehub/login', requiresAuth: false },
  { name: 'dashboard', path: '/casehub/dashboard', requiresAuth: true },
  { name: 'clients', path: '/casehub/clients', requiresAuth: true },
  { name: 'cases', path: '/casehub/cases', requiresAuth: true },
  { name: 'tasks', path: '/casehub/tasks', requiresAuth: true },
  { name: 'tasks-kanban', path: '/casehub/tasks/kanban', requiresAuth: true },
  { name: 'calendar', path: '/casehub/calendar', requiresAuth: true },
  { name: 'prazos', path: '/casehub/prazos', requiresAuth: true },
  { name: 'controladoria', path: '/casehub/controladoria', requiresAuth: true },
  { name: 'documents', path: '/casehub/documents', requiresAuth: true },
  { name: 'emails', path: '/casehub/emails', requiresAuth: true },
  { name: 'settings', path: '/casehub/settings', requiresAuth: true },
  { name: 'admin', path: '/casehub/admin', requiresAuth: true },
  { name: 'leads', path: '/casehub/leads', requiresAuth: true },
  { name: 'tools', path: '/casehub/tools', requiresAuth: true },
];

const VIEWPORTS = [
  { label: 'desktop', width: 1440, height: 900 },
  { label: 'mobile', width: 375, height: 812 },
];

const MODES = ['light', 'dark'];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

function timestamp() {
  return new Date().toISOString();
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const opts = parseArgs();
  const baseUrl = opts.url.replace(/\/$/, '');

  // Prepare output directories
  const phaseDir = path.join(opts.outputDir, `phase-${opts.phase}`);
  const screenshotDir = path.join(phaseDir, 'screenshots');
  ensureDir(screenshotDir);

  const report = [];
  const allConsoleErrors = [];
  const allConsoleWarnings = [];
  const performanceEntries = [];

  console.log(`\n=== CaseHub QA Audit — Phase ${opts.phase} ===`);
  console.log(`Base URL: ${baseUrl}`);
  console.log(`Output:   ${phaseDir}\n`);

  const browser = await chromium.launch({ headless: true });

  // -----------------------------------------------------------------------
  // Create authenticated context
  // -----------------------------------------------------------------------
  const authContext = await browser.newContext({
    viewport: VIEWPORTS[0],
    ignoreHTTPSErrors: true,
  });
  const authPage = await authContext.newPage();

  console.log('Logging in...');
  try {
    await authPage.goto(`${baseUrl}/casehub/login`, {
      waitUntil: 'networkidle',
      timeout: 30000,
    });

    await authPage.fill('input[name="email"], input[name="username"], input[type="email"], #email, #username', opts.username);
    await authPage.fill('input[name="password"], input[type="password"], #password', opts.password);
    await authPage.click('button[type="submit"], input[type="submit"]');
    await authPage.waitForURL('**/dashboard**', { timeout: 15000 }).catch(() => {
      // Some setups redirect elsewhere — just wait for navigation
      return authPage.waitForLoadState('networkidle', { timeout: 10000 });
    });
    console.log('Login successful.\n');
  } catch (err) {
    console.error(`Login failed: ${err.message}`);
    console.error('Continuing anyway — authenticated views may fail.\n');
  }

  // Save auth storage state for reuse across contexts
  const storageState = await authContext.storageState();
  await authPage.close();
  await authContext.close();

  // -----------------------------------------------------------------------
  // Audit each view x viewport x mode
  // -----------------------------------------------------------------------
  for (const view of VIEWS) {
    console.log(`--- ${view.name} (${view.path}) ---`);
    const viewReport = {
      view: view.name,
      path: view.path,
      phase: opts.phase,
      timestamp: timestamp(),
      viewports: {},
    };

    for (const vp of VIEWPORTS) {
      for (const mode of MODES) {
        const label = `${view.name}_${vp.label}_${mode}`;
        const screenshotPath = path.join(screenshotDir, `${label}.png`);

        const contextOpts = {
          viewport: { width: vp.width, height: vp.height },
          ignoreHTTPSErrors: true,
        };

        // Use auth state for authenticated views
        if (view.requiresAuth) {
          contextOpts.storageState = storageState;
        }

        const context = await browser.newContext(contextOpts);
        const page = await context.newPage();

        const consoleErrors = [];
        const consoleWarnings = [];
        let loadTimeMs = null;
        let buttonsClicked = 0;
        let buttonsFailed = 0;

        // Capture console messages
        page.on('console', (msg) => {
          const type = msg.type();
          const text = msg.text();
          if (type === 'error') {
            consoleErrors.push(text);
            allConsoleErrors.push(`[${label}] ${text}`);
          } else if (type === 'warning') {
            consoleWarnings.push(text);
            allConsoleWarnings.push(`[${label}] ${text}`);
          }
        });

        page.on('pageerror', (err) => {
          consoleErrors.push(`PAGE_ERROR: ${err.message}`);
          allConsoleErrors.push(`[${label}] PAGE_ERROR: ${err.message}`);
        });

        try {
          // Set theme mode BEFORE navigation
          await page.addInitScript((themeMode) => {
            localStorage.setItem('casehub-theme', themeMode);
          }, mode);

          // Navigate
          const navStart = Date.now();
          await page.goto(`${baseUrl}${view.path}`, {
            waitUntil: 'networkidle',
            timeout: 30000,
          });
          const navEnd = Date.now();

          // Measure performance via Performance API
          loadTimeMs = await page.evaluate(() => {
            try {
              const perf = performance.getEntriesByType('navigation')[0];
              if (perf) {
                return Math.round(perf.loadEventEnd - perf.startTime);
              }
            } catch (_) {}
            return null;
          });

          // Fallback to wall-clock time
          if (!loadTimeMs || loadTimeMs <= 0) {
            loadTimeMs = navEnd - navStart;
          }

          // Apply theme class if needed (some apps use body class instead of localStorage)
          await page.evaluate((themeMode) => {
            document.documentElement.setAttribute('data-theme', themeMode);
            document.body.classList.remove('light-mode', 'dark-mode');
            document.body.classList.add(`${themeMode}-mode`);
            // Also try dispatching storage event for apps that listen to it
            window.dispatchEvent(new StorageEvent('storage', {
              key: 'casehub-theme',
              newValue: themeMode,
            }));
          }, mode);

          // Wait for any theme transition
          await page.waitForTimeout(500);

          // Take screenshot
          await page.screenshot({ path: screenshotPath, fullPage: true });

          // Click all visible buttons and links — try/catch each
          const clickables = await page.$$('button:visible, a:visible, [role="button"]:visible');
          for (const el of clickables) {
            try {
              // Only click if still attached and visible
              const isVisible = await el.isVisible().catch(() => false);
              if (!isVisible) continue;

              await el.click({ timeout: 2000, force: false, noWaitAfter: true });
              buttonsClicked++;

              // Small delay to let errors propagate
              await page.waitForTimeout(100);
            } catch (_) {
              buttonsFailed++;
            }
          }

          console.log(`  ${vp.label}/${mode}: ${loadTimeMs}ms, ${consoleErrors.length} errors, ${buttonsClicked} clicks (${buttonsFailed} failed)`);
        } catch (err) {
          console.error(`  ${vp.label}/${mode}: FAILED — ${err.message}`);
          consoleErrors.push(`NAVIGATION_ERROR: ${err.message}`);
          allConsoleErrors.push(`[${label}] NAVIGATION_ERROR: ${err.message}`);

          // Try screenshot anyway
          try {
            await page.screenshot({ path: screenshotPath, fullPage: true });
          } catch (_) {}
        }

        // Store per-viewport/mode data
        const key = `${vp.label}_${mode}`;
        viewReport.viewports[key] = {
          viewport: `${vp.width}x${vp.height}`,
          mode,
          load_time_ms: loadTimeMs,
          console_errors: consoleErrors,
          console_warnings: consoleWarnings,
          buttons_clicked: buttonsClicked,
          buttons_failed: buttonsFailed,
          screenshot: `screenshots/${label}.png`,
        };

        if (loadTimeMs) {
          performanceEntries.push(`${label}: ${loadTimeMs}ms`);
        }

        await page.close();
        await context.close();
      }
    }

    report.push(viewReport);
  }

  await browser.close();

  // -----------------------------------------------------------------------
  // Write output files
  // -----------------------------------------------------------------------

  // report.json
  fs.writeFileSync(
    path.join(phaseDir, 'report.json'),
    JSON.stringify(report, null, 2),
    'utf-8'
  );

  // console-errors.log
  fs.writeFileSync(
    path.join(phaseDir, 'console-errors.log'),
    allConsoleErrors.length > 0
      ? allConsoleErrors.join('\n') + '\n'
      : '(no console errors)\n',
    'utf-8'
  );

  // console-warnings.log
  fs.writeFileSync(
    path.join(phaseDir, 'console-warnings.log'),
    allConsoleWarnings.length > 0
      ? allConsoleWarnings.join('\n') + '\n'
      : '(no console warnings)\n',
    'utf-8'
  );

  // performance.log
  fs.writeFileSync(
    path.join(phaseDir, 'performance.log'),
    performanceEntries.length > 0
      ? performanceEntries.join('\n') + '\n'
      : '(no performance data)\n',
    'utf-8'
  );

  // -----------------------------------------------------------------------
  // Summary
  // -----------------------------------------------------------------------
  const totalErrors = allConsoleErrors.length;
  const totalWarnings = allConsoleWarnings.length;
  const avgLoad = performanceEntries.length > 0
    ? Math.round(
        performanceEntries
          .map((e) => parseInt(e.split(': ')[1]))
          .reduce((a, b) => a + b, 0) / performanceEntries.length
      )
    : 0;

  console.log('\n=== SUMMARY ===');
  console.log(`Views audited:    ${VIEWS.length}`);
  console.log(`Screenshots:      ${VIEWS.length * VIEWPORTS.length * MODES.length}`);
  console.log(`Console errors:   ${totalErrors}`);
  console.log(`Console warnings: ${totalWarnings}`);
  console.log(`Avg load time:    ${avgLoad}ms`);
  console.log(`Output:           ${phaseDir}`);
  console.log('');
}

main().catch((err) => {
  console.error('Fatal error:', err);
  process.exit(1);
});
