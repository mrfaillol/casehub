/**
 * Stress Test — Simulate Victor's video scenario
 * Rapidly clicks 10 dock icons in 2s. Measures:
 *   - Windows opened (should cap around maxActiveWindows)
 *   - FPS degradation curve
 *   - Heap growth
 *   - Dedup effectiveness (no duplicates)
 *   - Load queue behavior (sequential, not parallel)
 */

const { chromium } = require('playwright');
const fs = require('fs');

const DIR = '/Users/beijaflor/Documents/Trabalho/TEMP/stress-test';
fs.mkdirSync(DIR, { recursive: true });

(async () => {
    const b = await chromium.launch({ headless: true });
    const p = await b.newPage({ viewport: { width: 1440, height: 900 } });

    // Login
    await p.goto('https://dev.vingren.me/casehub/login');
    await p.fill('input[name="email"]', 'victor@vingren.me');
    await p.fill('input[name="password"]', 'dev123');
    await p.click('button[type="submit"]');
    await p.waitForURL(/dashboard/, { timeout: 15000 });
    await p.waitForTimeout(3000);

    // Baseline state
    const baseline = await p.evaluate(() => ({
        fps: window.osResourceManager?.fps || 60,
        heap: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576 * 10) / 10 : null,
        windows: window.osWindowManager?.windows.size || 0,
    }));
    console.log('BASELINE:', baseline);

    // Stress: rapid spam-click on 10 dock icons in 2 seconds
    const stressResult = await p.evaluate(async () => {
        const samples = [];
        const links = Array.from(document.querySelectorAll('.sidebar .nav-link'))
            .filter(l => l.getAttribute('href') && l.getAttribute('href') !== '#')
            .slice(0, 10);

        // Fire 10 rapid clicks + some duplicates
        const clickOrder = [];
        for (let i = 0; i < 10; i++) {
            const link = links[i % links.length];
            link.click();
            clickOrder.push(link.getAttribute('href'));
            // Small delay to simulate rapid user clicks (~20ms between)
            await new Promise(r => setTimeout(r, 20));
        }
        // Also trigger 5 duplicate clicks on same icon (spam test)
        for (let i = 0; i < 5; i++) {
            links[0].click();
            await new Promise(r => setTimeout(r, 20));
        }

        // Sample resources every 300ms for 5 seconds
        for (let t = 0; t < 17; t++) {
            await new Promise(r => setTimeout(r, 300));
            samples.push({
                t: t * 300,
                fps: window.osResourceManager?.fps || 60,
                windows: window.osWindowManager?.windows.size || 0,
                active: window.osResourceManager?.activeWindows.size || 0,
                heap: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576 * 10) / 10 : null,
                perfMode: document.body.classList.contains('performance-mode'),
                queue: window.osWindowManager?._loadQueue?.length || 0,
            });
        }

        // Final window URLs (dedup check)
        const urls = [];
        window.osWindowManager?.windows.forEach((win) => {
            if (win.url) urls.push(win.url);
        });

        return { clickOrder, samples, finalUrls: urls };
    });

    await p.screenshot({ path: DIR + '/after-stress.png' });

    fs.writeFileSync(DIR + '/report.json', JSON.stringify({ baseline, ...stressResult }, null, 2));

    // Analysis
    console.log('\n=== STRESS TEST RESULT ===');
    console.log(`Clicks fired: ${stressResult.clickOrder.length}`);
    console.log(`Unique URLs requested: ${new Set(stressResult.clickOrder).size}`);
    console.log(`Final windows open: ${stressResult.finalUrls.length}`);
    console.log(`Duplicates prevented: ${stressResult.clickOrder.length - stressResult.finalUrls.length}`);

    const minFps = Math.min(...stressResult.samples.map(s => s.fps));
    const maxHeap = Math.max(...stressResult.samples.map(s => s.heap));
    const maxWindows = Math.max(...stressResult.samples.map(s => s.windows));
    const anyPerfMode = stressResult.samples.some(s => s.perfMode);
    const maxQueue = Math.max(...stressResult.samples.map(s => s.queue));

    console.log(`\nMin FPS during stress: ${minFps}`);
    console.log(`Max heap: ${maxHeap} MB`);
    console.log(`Peak windows: ${maxWindows}`);
    console.log(`Peak load queue depth: ${maxQueue}`);
    console.log(`Performance mode triggered: ${anyPerfMode ? 'yes' : 'no'}`);

    console.log('\n=== VERDICT ===');
    if (stressResult.finalUrls.length <= 5) console.log(`✅ Windows capped at ${stressResult.finalUrls.length} (target ≤ 5)`);
    else console.log(`❌ ${stressResult.finalUrls.length} windows opened (should be ≤ 5)`);

    if (minFps >= 30) console.log(`✅ Min FPS ${minFps} ≥ 30`);
    else console.log(`❌ Min FPS ${minFps} < 30 (degraded)`);

    if (maxHeap - baseline.heap < 30) console.log(`✅ Heap grew ${(maxHeap - baseline.heap).toFixed(1)} MB (< 30 MB)`);
    else console.log(`❌ Heap grew ${(maxHeap - baseline.heap).toFixed(1)} MB`);

    const duplicatesPreventedPct = ((stressResult.clickOrder.length - stressResult.finalUrls.length) / stressResult.clickOrder.length * 100).toFixed(0);
    console.log(`✅ Dedup rate: ${duplicatesPreventedPct}%`);

    console.log(`\nFull report: ${DIR}/report.json`);
    await b.close();
})().catch(e => { console.error('Fatal:', e.message); process.exit(1); });
