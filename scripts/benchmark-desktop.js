/**
 * CaseHub Desktop Mode — Performance Benchmark
 * Measures: TTI, JS heap, FPS during drag, interaction latency, paint timing.
 * Zero dependencies. Reports numbers + marks what's slow.
 */

const { chromium } = require('playwright');
const fs = require('fs');

const URL = 'https://dev.vingren.me/casehub/login';
const DIR = '/Users/beijaflor/Documents/Trabalho/TEMP/benchmark-desktop';
fs.mkdirSync(DIR, { recursive: true });

(async () => {
    const b = await chromium.launch({ headless: true });
    const p = await b.newPage({ viewport: { width: 1440, height: 900 } });

    const results = {};

    // ---- 1. Login + Time-to-Interactive ----
    const navStart = Date.now();
    await p.goto(URL, { waitUntil: 'networkidle' });
    await p.fill('input[name="email"]', 'victor@vingren.me');
    await p.fill('input[name="password"]', 'dev123');
    await p.click('button[type="submit"]');
    await p.waitForURL(/dashboard/, { timeout: 10000 });
    await p.waitForTimeout(500); // brief settle
    const tti = Date.now() - navStart;
    results.tti_ms = tti;

    // Wait for window manager ready
    await p.waitForFunction(() => window.osWindowManager, { timeout: 5000 });
    const wmReady = await p.evaluate(() => !!window.osWindowManager);
    results.window_manager_ready = wmReady;

    // ---- 2. Paint timing ----
    const paint = await p.evaluate(() => {
        const entries = performance.getEntriesByType('paint');
        const nav = performance.getEntriesByType('navigation')[0] || {};
        return {
            fcp: entries.find(e => e.name === 'first-contentful-paint')?.startTime,
            lcp: performance.getEntriesByType('largest-contentful-paint').pop()?.startTime,
            domContentLoaded: nav.domContentLoadedEventEnd,
            loadEvent: nav.loadEventEnd,
            transferSize: nav.transferSize,
        };
    });
    results.paint = paint;

    // ---- 3. JS Heap ----
    const mem = await p.evaluate(() => {
        if (!performance.memory) return null;
        return {
            usedMB: Math.round(performance.memory.usedJSHeapSize / 1048576 * 10) / 10,
            totalMB: Math.round(performance.memory.totalJSHeapSize / 1048576 * 10) / 10,
            limitMB: Math.round(performance.memory.jsHeapSizeLimit / 1048576),
        };
    });
    results.js_heap_initial = mem;

    // ---- 4. DOM size ----
    results.dom = await p.evaluate(() => ({
        nodes: document.getElementsByTagName('*').length,
        eventListeners: window.getEventListeners ? 'native' : 'unknown',
        stylesheets: document.styleSheets.length,
    }));

    // ---- 5. Open 3 windows sequentially and measure ----
    const openTimes = [];
    for (const app of ['/casehub/tasks', '/casehub/calendar/agenda', '/casehub/documents']) {
        const t0 = Date.now();
        await p.evaluate((url) => {
            if (window.osWindowManager) {
                window.osWindowManager.launchApp(url, url.split('/').pop(), 'fas fa-cube');
            }
        }, app);
        await p.waitForTimeout(1500);
        openTimes.push({ app, ms: Date.now() - t0 });
    }
    results.window_open_times = openTimes;

    // ---- 6. FPS during simulated drag ----
    const fpsTest = await p.evaluate(async () => {
        return new Promise(resolve => {
            const frames = [];
            let lastT = performance.now();
            let count = 0;
            const win = document.querySelector('.macos-window.macos-app-window');
            if (!win) return resolve({ error: 'no window' });
            const titlebar = win.querySelector('.macos-titlebar');

            // Simulate drag via PointerEvents
            const rect = titlebar.getBoundingClientRect();
            titlebar.dispatchEvent(new PointerEvent('pointerdown', {
                pointerId: 1, button: 0, clientX: rect.left + 50, clientY: rect.top + 10
            }));

            function tick() {
                const now = performance.now();
                const delta = now - lastT;
                frames.push(delta);
                lastT = now;
                count++;

                // Simulate pointer move
                document.dispatchEvent(new PointerEvent('pointermove', {
                    pointerId: 1, clientX: rect.left + 50 + count * 2, clientY: rect.top + 10 + count
                }));

                if (count < 120) requestAnimationFrame(tick);
                else {
                    document.dispatchEvent(new PointerEvent('pointerup', {
                        pointerId: 1, clientX: 500, clientY: 300
                    }));
                    const avg = frames.reduce((s, v) => s + v, 0) / frames.length;
                    const avgFps = Math.round(1000 / avg * 10) / 10;
                    const slowFrames = frames.filter(f => f > 20).length;
                    resolve({ avg_fps: avgFps, avg_frame_ms: Math.round(avg * 10) / 10, slow_frames: slowFrames, total_frames: frames.length });
                }
            }
            requestAnimationFrame(tick);
        });
    });
    results.drag_fps = fpsTest;

    // ---- 7. Memory after workload ----
    await p.waitForTimeout(500);
    results.js_heap_after = await p.evaluate(() => {
        if (!performance.memory) return null;
        return {
            usedMB: Math.round(performance.memory.usedJSHeapSize / 1048576 * 10) / 10,
            totalMB: Math.round(performance.memory.totalJSHeapSize / 1048576 * 10) / 10,
        };
    });

    // ---- 8. Interaction latency (click response time) ----
    const latency = await p.evaluate(async () => {
        const results = [];
        for (let i = 0; i < 5; i++) {
            const link = document.querySelector('.sidebar .nav-link');
            if (!link) continue;
            const t0 = performance.now();
            link.click();
            await new Promise(r => requestAnimationFrame(r));
            const t1 = performance.now();
            results.push(Math.round((t1 - t0) * 100) / 100);
        }
        return results;
    });
    results.dock_click_latency_ms = latency;

    // ---- 9. CSS/Style analysis ----
    results.css = await p.evaluate(() => {
        let totalRules = 0;
        for (const sheet of document.styleSheets) {
            try { totalRules += sheet.cssRules.length; } catch(e) {}
        }
        return {
            stylesheets: document.styleSheets.length,
            totalRules,
            computedStyleCalls: 'N/A (runtime stat not exposed)',
        };
    });

    // Final screenshot
    await p.screenshot({ path: DIR + '/final-state.png' });

    fs.writeFileSync(DIR + '/report.json', JSON.stringify(results, null, 2));
    await b.close();

    // ---- Analysis + verdict ----
    console.log('\n========== CASEHUB DESKTOP BENCHMARK ==========\n');
    console.log(`TTI (login → dashboard interactive): ${results.tti_ms}ms`);
    console.log(`FCP: ${Math.round(paint.fcp)}ms  |  LCP: ${Math.round(paint.lcp || 0)}ms  |  DOMContentLoaded: ${Math.round(paint.domContentLoaded)}ms`);
    console.log(`Initial transfer: ${(paint.transferSize / 1024).toFixed(1)} KB`);
    console.log(`DOM nodes: ${results.dom.nodes}  |  Stylesheets: ${results.dom.stylesheets}  |  CSS rules: ${results.css.totalRules}`);
    console.log(`JS heap initial: ${mem.usedMB}/${mem.totalMB} MB (limit ${mem.limitMB} MB)`);
    console.log(`JS heap after opening 3 windows: ${results.js_heap_after.usedMB} MB`);
    console.log(`Window open times (ms): ${openTimes.map(o => o.ms).join(', ')}`);
    console.log(`Dock click latency (ms): ${latency.join(', ')}`);
    console.log(`Drag FPS: ${fpsTest.avg_fps} avg | ${fpsTest.avg_frame_ms}ms per frame | ${fpsTest.slow_frames}/${fpsTest.total_frames} slow frames (>20ms)`);

    console.log('\n=== VERDICT ===');
    const verdicts = [];
    if (results.tti_ms > 5000) verdicts.push(`❌ TTI ${results.tti_ms}ms > 5s target`);
    else verdicts.push(`✅ TTI ${results.tti_ms}ms`);
    if (paint.fcp > 2500) verdicts.push(`❌ FCP ${Math.round(paint.fcp)}ms > 2.5s`);
    else verdicts.push(`✅ FCP ${Math.round(paint.fcp)}ms`);
    if (results.dom.nodes > 3000) verdicts.push(`⚠️ DOM ${results.dom.nodes} nodes (>3000 is heavy)`);
    else verdicts.push(`✅ DOM ${results.dom.nodes} nodes`);
    if (mem.usedMB > 50) verdicts.push(`⚠️ JS heap ${mem.usedMB} MB (>50 is heavy)`);
    else verdicts.push(`✅ JS heap ${mem.usedMB} MB`);
    if (fpsTest.avg_fps < 50) verdicts.push(`❌ Drag FPS ${fpsTest.avg_fps} (<50 is laggy)`);
    else verdicts.push(`✅ Drag FPS ${fpsTest.avg_fps}`);
    if (fpsTest.slow_frames > 5) verdicts.push(`⚠️ ${fpsTest.slow_frames} slow frames during drag`);
    const avgLat = latency.reduce((s, v) => s + v, 0) / latency.length;
    if (avgLat > 16) verdicts.push(`⚠️ Dock click latency ${avgLat.toFixed(1)}ms (>16ms = missed frame)`);
    else verdicts.push(`✅ Dock click latency ${avgLat.toFixed(1)}ms`);
    verdicts.forEach(v => console.log(v));

    console.log(`\nFull report: ${DIR}/report.json`);
})().catch(e => { console.error('Fatal:', e.message); process.exit(1); });
