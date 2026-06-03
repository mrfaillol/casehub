// @ts-check
/**
 * CaseHub Visual Regression - Phase 1 runner
 *
 * Logs in to alpha production, screenshots 10 routes x 3 viewports x 2 themes
 * (60 PNGs) plus a small set of key interactions. Output goes to
 * tests/visual-audit/results/<ISO-timestamp>/.
 *
 * Run:
 *   LOGIN_EMAIL_ALPHA=... LOGIN_PASS_ALPHA=... node tests/visual-audit/run.spec.js
 *
 * Credentials are read from env vars only — never hardcoded.
 * Spec: memory/feedback_testing_automation.md (Phase 1)
 */
'use strict';

const fs = require('fs');
const path = require('path');

// Playwright lives in ~/Projects/casehub/node_modules — resolve from there.
const PLAYWRIGHT_NODE_MODULES = path.resolve(
  process.env.PLAYWRIGHT_NODE_MODULES ||
    path.join(__dirname, '..', '..', '..', 'casehub', 'node_modules')
);

// Allow override of where pixelmatch/pngjs live (compare.js uses the same trick).
const TRABALHO_NODE_MODULES = path.resolve(
  process.env.TRABALHO_NODE_MODULES ||
    path.join(__dirname, '..', '..', '..', 'trabalho-workspace', 'node_modules')
);

// eslint-disable-next-line import/no-dynamic-require, global-require
const { chromium } = require(path.join(PLAYWRIGHT_NODE_MODULES, 'playwright'));

const BASE_URL = process.env.CASEHUB_BASE_URL || 'https://casehub.legal';
const LOGIN_PATH = '/casehub/login';

const EMAIL = process.env.LOGIN_EMAIL_ALPHA;
const PASSWORD = process.env.LOGIN_PASS_ALPHA;

if (!EMAIL || !PASSWORD) {
  console.error(
    '[visual-audit] LOGIN_EMAIL_ALPHA and LOGIN_PASS_ALPHA env vars are required.'
  );
  process.exit(2);
}

const ROUTES = [
  '/casehub/dashboard',
  '/casehub/tasks/kanban',
  '/casehub/assistente',
  '/casehub/whatsapp-chat',
  '/casehub/casehub-md/poc',
  '/casehub/controladoria',
  '/casehub/cases',
  '/casehub/clients',
  '/casehub/files',
  '/casehub/calendar/agenda',
];

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile', width: 393, height: 852 },
];

const THEMES = ['light', 'dark'];

const INTERACTIONS = [
  {
    name: 'dashboard-cmdk-open',
    route: '/casehub/dashboard',
    viewport: 'desktop',
    theme: 'light',
    run: async (page) => {
      await page.keyboard.press(process.platform === 'darwin' ? 'Meta+K' : 'Control+K');
      await page.waitForTimeout(600);
    },
  },
  {
    name: 'dashboard-theme-toggle',
    route: '/casehub/dashboard',
    viewport: 'desktop',
    theme: 'light',
    run: async (page) => {
      const sel = await page
        .locator('[data-action="theme-toggle"], button[aria-label*="theme" i], button[title*="theme" i], .theme-toggle')
        .first();
      if (await sel.count()) {
        await sel.click({ trial: false }).catch(() => {});
        await page.waitForTimeout(400);
      } else {
        await page.evaluate(() => {
          try {
            localStorage.setItem('casehub.theme', 'dark');
          } catch (_) {}
          document.documentElement.classList.add('theme-dark');
          document.documentElement.setAttribute('data-theme', 'dark');
        });
        await page.waitForTimeout(400);
      }
    },
  },
  {
    name: 'mobile-sidebar-open',
    route: '/casehub/dashboard',
    viewport: 'mobile',
    theme: 'light',
    run: async (page) => {
      const sel = page
        .locator('[data-action="sidebar-toggle"], button[aria-label*="menu" i], button[aria-label*="sidebar" i], .sidebar-toggle, .nav-toggle')
        .first();
      if (await sel.count()) {
        await sel.click().catch(() => {});
        await page.waitForTimeout(500);
      }
    },
  },
  {
    name: 'assistente-prompt-typed',
    route: '/casehub/assistente',
    viewport: 'desktop',
    theme: 'light',
    run: async (page) => {
      const ta = page
        .locator('textarea, input[type="text"][placeholder*="Pergunte" i], input[type="text"][placeholder*="Maestro" i]')
        .first();
      if (await ta.count()) {
        await ta.fill('Qual o contexto do escritorio?');
        await page.waitForTimeout(400);
      }
    },
  },
  {
    name: 'whatsapp-chat-rendered',
    route: '/casehub/whatsapp-chat',
    viewport: 'desktop',
    theme: 'light',
    run: async (page) => {
      const item = page
        .locator('[data-role="conversation"], .conversation-item, .chat-list-item')
        .first();
      if (await item.count()) {
        await item.click({ trial: false }).catch(() => {});
        await page.waitForTimeout(800);
      }
    },
  },
];

const ROOT_DIR = path.resolve(__dirname);
const RESULTS_ROOT = path.join(ROOT_DIR, 'results');

function makeIsoStamp() {
  return new Date().toISOString().replace(/[:.]/g, '-');
}

function fileKey(route, viewport, theme) {
  const slug = route.replace(/^\//, '').replace(/[\/?#]/g, '_').replace(/[^a-zA-Z0-9_-]/g, '_');
  return `${slug}-${viewport}-${theme}.png`;
}

async function loginOnce(context) {
  const page = await context.newPage();
  try {
    await page.goto(`${BASE_URL}${LOGIN_PATH}`, {
      waitUntil: 'domcontentloaded',
      timeout: 30000,
    });
    await page.waitForTimeout(800);

    const emailSel = page
      .locator('input[type="email"], input[name="email"], input[id="email"], input[placeholder*="mail" i]')
      .first();
    const passSel = page
      .locator('input[type="password"], input[name="password"], input[id="password"]')
      .first();

    if (!(await emailSel.count()) || !(await passSel.count())) {
      throw new Error('Login form not found at ' + LOGIN_PATH);
    }

    await emailSel.fill(EMAIL);
    await passSel.fill(PASSWORD);

    const submit = page
      .locator('button[type="submit"], input[type="submit"], button:has-text("Entrar"), button:has-text("Login")')
      .first();
    await submit.click({ timeout: 10000 }).catch(async () => {
      await passSel.press('Enter');
    });

    // Wait for redirect away from /login.
    await page.waitForFunction(
      () => !/\/login(\b|\/?$)/.test(window.location.pathname),
      { timeout: 20000 }
    );

    if (!/\/casehub\//.test(page.url())) {
      console.warn(`[visual-audit] post-login URL unexpected: ${page.url()}`);
    }
    console.log(`[visual-audit] login OK, landed on ${page.url()}`);
  } finally {
    await page.close();
  }
}

async function applyTheme(page, theme) {
  await page.evaluate((t) => {
    try {
      localStorage.setItem('casehub.theme', t);
    } catch (_) {}
    const html = document.documentElement;
    html.setAttribute('data-theme', t);
    html.classList.remove('theme-light', 'theme-dark');
    html.classList.add(`theme-${t}`);
    if (t === 'dark') {
      html.classList.add('dark');
    } else {
      html.classList.remove('dark');
    }
  }, theme);
}

async function captureRoute(context, route, viewport, theme, outDir, maxAttempts = 3) {
  // Retry on 5xx (alpha nginx occasionally 502s during cold worker spin-up).
  let lastError = null;
  let lastHttpStatus = null;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const page = await context.newPage();
    try {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.addInitScript((t) => {
        try {
          localStorage.setItem('casehub.theme', t);
        } catch (_) {}
      }, theme);

      const resp = await page.goto(`${BASE_URL}${route}`, {
        waitUntil: 'domcontentloaded',
        timeout: 25000,
      });
      const httpStatus = resp ? resp.status() : null;
      lastHttpStatus = httpStatus;

      if (httpStatus && httpStatus >= 500 && attempt < maxAttempts) {
        // Retry — likely transient (nginx 502 during worker restart).
        await page.close();
        await new Promise((r) => setTimeout(r, 1200 * attempt));
        continue;
      }

      await applyTheme(page, theme);
      await page.waitForTimeout(900);
      await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});

      const file = path.join(outDir, fileKey(route, viewport.name, theme));
      await page.screenshot({ path: file, fullPage: false });
      const status = httpStatus && httpStatus < 400 ? 'ok' : 'http_error';
      return { route, viewport: viewport.name, theme, file, status, httpStatus, attempts: attempt };
    } catch (err) {
      lastError = err && err.message ? err.message : String(err);
      if (attempt < maxAttempts) {
        await page.close();
        await new Promise((r) => setTimeout(r, 1200 * attempt));
        continue;
      }
      const file = path.join(outDir, fileKey(route, viewport.name, theme));
      try {
        await page.screenshot({ path: file, fullPage: false });
      } catch (_) {
        /* swallow secondary error */
      }
      return {
        route,
        viewport: viewport.name,
        theme,
        file,
        status: 'error',
        httpStatus: lastHttpStatus,
        error: lastError,
        attempts: attempt,
      };
    } finally {
      await page.close();
    }
  }
  return {
    route,
    viewport: viewport.name,
    theme,
    status: 'error',
    httpStatus: lastHttpStatus,
    error: lastError || 'exhausted retries',
    attempts: maxAttempts,
  };
}

async function runInteractions(context, outDir) {
  const out = [];
  for (const action of INTERACTIONS) {
    const vp = VIEWPORTS.find((v) => v.name === action.viewport);
    const page = await context.newPage();
    let status = 'ok';
    let error = null;
    try {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.addInitScript((t) => {
        try {
          localStorage.setItem('casehub.theme', t);
        } catch (_) {}
      }, action.theme);
      await page.goto(`${BASE_URL}${action.route}`, {
        waitUntil: 'domcontentloaded',
        timeout: 25000,
      });
      await applyTheme(page, action.theme);
      await page.waitForTimeout(800);
      await page.waitForLoadState('networkidle', { timeout: 6000 }).catch(() => {});
      await action.run(page);
      await page.waitForTimeout(400);
      const file = path.join(outDir, `interaction-${action.name}.png`);
      await page.screenshot({ path: file, fullPage: false });
      out.push({ name: action.name, route: action.route, file, status });
    } catch (err) {
      status = 'error';
      error = err && err.message ? err.message : String(err);
      out.push({ name: action.name, route: action.route, status, error });
    } finally {
      await page.close();
    }
  }
  return out;
}

async function main() {
  const stamp = makeIsoStamp();
  const outDir = path.join(RESULTS_ROOT, stamp);
  fs.mkdirSync(outDir, { recursive: true });
  console.log(`[visual-audit] writing to ${outDir}`);

  const t0 = Date.now();
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent:
      'Mozilla/5.0 (Macintosh; visual-audit-bot) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36',
    deviceScaleFactor: 1,
    locale: 'pt-BR',
    timezoneId: 'America/Sao_Paulo',
  });

  const summary = {
    started_at: new Date().toISOString(),
    base_url: BASE_URL,
    routes: ROUTES,
    viewports: VIEWPORTS,
    themes: THEMES,
    captures: [],
    interactions: [],
    elapsed_ms: 0,
  };

  try {
    await loginOnce(context);

    for (const route of ROUTES) {
      for (const viewport of VIEWPORTS) {
        for (const theme of THEMES) {
          const r = await captureRoute(context, route, viewport, theme, outDir);
          summary.captures.push(r);
          const label = `${route} ${viewport.name} ${theme}`;
          if (r.status === 'ok') {
            console.log(`[visual-audit] OK ${label} (HTTP ${r.httpStatus ?? '?'})`);
          } else {
            console.warn(`[visual-audit] ERR ${label}: ${r.error}`);
          }
        }
      }
    }

    summary.interactions = await runInteractions(context, outDir);
  } finally {
    await context.close();
    await browser.close();
  }

  summary.elapsed_ms = Date.now() - t0;
  summary.finished_at = new Date().toISOString();

  const summaryFile = path.join(outDir, 'run-summary.json');
  fs.writeFileSync(summaryFile, JSON.stringify(summary, null, 2));
  fs.writeFileSync(path.join(RESULTS_ROOT, 'latest.txt'), stamp);

  const okCount = summary.captures.filter((c) => c.status === 'ok').length;
  const errCount = summary.captures.length - okCount;
  console.log(
    `[visual-audit] done — ${okCount}/${summary.captures.length} screenshots OK ` +
      `(${errCount} errors), ${summary.interactions.length} interactions, ` +
      `${Math.round(summary.elapsed_ms / 1000)}s elapsed.`
  );
  console.log(`[visual-audit] summary: ${summaryFile}`);
  console.log(`[visual-audit] pointer: ${path.join(RESULTS_ROOT, 'latest.txt')}`);

  if (errCount > 0) {
    process.exitCode = 1;
  }
}

main().catch((err) => {
  console.error('[visual-audit] fatal:', err);
  process.exit(1);
});

module.exports = { ROUTES, VIEWPORTS, THEMES, fileKey, TRABALHO_NODE_MODULES };
