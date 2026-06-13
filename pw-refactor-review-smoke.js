#!/usr/bin/env node
/**
 * Smoke visual dos 10 compare panels do refactor-review.
 * Captura: 3 screenshots por key (page overview, iframe "antes", iframe "depois").
 * Output: /tmp/refactor-review-smoke/<key>-{full,before,after}.png + index.html
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE = 'https://dev.vingren.me/casehub';
const OUT = '/tmp/refactor-review-smoke';
const KEYS = [
  'login.html', 'forgot_password.html', 'reset_password.html',
  'onboarding-signup.html', 'onboarding-welcome.html', 'onboarding-complete.html',
  'onboarding-branding.html', 'onboarding-drive.html',
  'onboarding-team.html', 'onboarding-plan.html',
];

fs.mkdirSync(OUT, { recursive: true });

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  const results = [];

  for (const key of KEYS) {
    console.log(`→ ${key}`);
    const entry = { key, status: 'unknown', notes: [] };
    const page = await ctx.newPage();

    try {
      // Full panel
      const resp = await page.goto(`${BASE}/refactor-review/${key}`, { waitUntil: 'networkidle', timeout: 20000 });
      entry.panel_status = resp.status();
      await page.waitForTimeout(1200); // iframes carregarem
      await page.screenshot({ path: `${OUT}/${key}-full.png`, fullPage: false });

      // Archive (before) direto
      const archVersions = await page.evaluate(async (k) => {
        const r = await fetch(`/casehub/templates/_archive/_index/${k}`);
        return r.ok ? r.json() : { versions: [] };
      }, key);
      const origV = (archVersions.versions || []).find(v => !String(v.id).startsWith('lab-gen-'))?.id
        || archVersions.versions?.[0]?.id;
      if (origV) {
        const archUrl = `${BASE}/templates/_archive/${key}?v=${origV}`;
        const beforePage = await ctx.newPage();
        const rB = await beforePage.goto(archUrl, { waitUntil: 'networkidle', timeout: 15000 });
        entry.before_status = rB.status();
        entry.before_version = origV;
        await beforePage.waitForTimeout(500);
        await beforePage.screenshot({ path: `${OUT}/${key}-before.png`, fullPage: false });
        await beforePage.close();
      } else {
        entry.before_status = 'no-archive';
      }

      // Preview (after) direto
      const afterPage = await ctx.newPage();
      const rA = await afterPage.goto(`${BASE}/refactor-review/_preview/${key}`, { waitUntil: 'networkidle', timeout: 15000 });
      entry.after_status = rA.status();
      await afterPage.waitForTimeout(500);
      await afterPage.screenshot({ path: `${OUT}/${key}-after.png`, fullPage: false });
      await afterPage.close();

      // Candidates (lab-gen-*)
      const labGen = (archVersions.versions || []).filter(v => String(v.id).startsWith('lab-gen-'));
      entry.lab_gen_count = labGen.length;
      if (labGen.length > 0) {
        const candPage = await ctx.newPage();
        const rC = await candPage.goto(`${BASE}/templates/_archive/${key}?v=${labGen[0].id}`, { waitUntil: 'networkidle', timeout: 15000 });
        entry.candidate_status = rC.status();
        entry.candidate_id = labGen[0].id;
        await candPage.waitForTimeout(500);
        await candPage.screenshot({ path: `${OUT}/${key}-candidate.png`, fullPage: false });
        await candPage.close();
      }

      entry.status = 'ok';
    } catch (e) {
      entry.status = 'error';
      entry.error = e.message;
    }

    await page.close();
    results.push(entry);
  }

  await browser.close();

  // Index HTML
  const idx = `<!doctype html><html><head><meta charset=utf-8><title>Refactor-Review Visual Smoke ${new Date().toISOString()}</title>
<style>
body{font:13px/1.4 system-ui;background:#0b0d12;color:#e8ecf1;margin:0;padding:16px}
h1{font-size:16px}h2{font-size:14px;margin:20px 0 8px}
table{border-collapse:collapse;margin:12px 0}td,th{padding:4px 8px;border:1px solid #333;font-size:11px}
.grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:20px}
.shot{background:#1a1a1a;border-radius:8px;padding:6px;font-size:11px}
.shot img{width:100%;display:block;border-radius:4px;max-height:260px;object-fit:cover;object-position:top}
.shot .lbl{margin-bottom:4px;color:#8b94a3}
.ok{color:#4ade80}.err{color:#f87171}
</style></head><body>
<h1>Refactor-Review Visual Smoke · ${new Date().toISOString()}</h1>
<table><tr><th>key</th><th>panel</th><th>before</th><th>after</th><th>candidates</th></tr>
${results.map(r => `<tr>
  <td>${r.key}</td>
  <td class="${r.panel_status===200?'ok':'err'}">${r.panel_status ?? '—'}</td>
  <td class="${r.before_status===200?'ok':'err'}">${r.before_status ?? '—'}</td>
  <td class="${r.after_status===200?'ok':'err'}">${r.after_status ?? '—'}</td>
  <td>${r.lab_gen_count ?? 0}${r.candidate_status?` (${r.candidate_status})`:''}</td>
</tr>`).join('')}
</table>
${results.map(r => `
<h2>${r.key}</h2>
<div class="grid">
  <div class="shot"><div class="lbl">panel (compare)</div><img src="${r.key}-full.png"></div>
  <div class="shot"><div class="lbl">archive "antes" (${r.before_version||'—'})</div>${fs.existsSync(path.join(OUT,r.key+'-before.png'))?`<img src="${r.key}-before.png">`:'<em>sem arquivo</em>'}</div>
  <div class="shot"><div class="lbl">/_preview "depois"</div>${fs.existsSync(path.join(OUT,r.key+'-after.png'))?`<img src="${r.key}-after.png">`:'<em>sem arquivo</em>'}</div>
  ${r.candidate_id?`<div class="shot"><div class="lbl">candidate lab-gen (${r.candidate_id})</div><img src="${r.key}-candidate.png"></div>`:''}
</div>
`).join('')}
<pre style="margin-top:20px;background:#1a1a1a;padding:12px;border-radius:8px;font-size:11px;white-space:pre-wrap">${JSON.stringify(results, null, 2)}</pre>
</body></html>`;
  fs.writeFileSync(`${OUT}/index.html`, idx);

  // Summary
  const failed = results.filter(r => r.status !== 'ok' || r.panel_status !== 200 || r.before_status !== 200 || r.after_status !== 200);
  console.log(`\nResultado: ${results.length - failed.length}/${results.length} ok`);
  if (failed.length) {
    console.log('FALHAS:');
    failed.forEach(r => console.log(`  ${r.key}: panel=${r.panel_status} before=${r.before_status} after=${r.after_status} ${r.error||''}`));
  }
  console.log(`\nAbra: file://${OUT}/index.html`);
  process.exit(failed.length ? 1 : 0);
})();
