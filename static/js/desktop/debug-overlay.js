/**
 * Debug Overlay — FPS + viewport badge + CSS inspector
 * Ativado via ?debug=1 ou localStorage.casehub_debug=1
 *
 * Não roda em produção (zero cost se flag off).
 */
(function () {
    'use strict';
    if (window._casehubDebug) return;

    var params = new URLSearchParams(location.search);
    var debugOn = params.get('debug') === '1' ||
                  (function () { try { return localStorage.getItem('casehub_debug') === '1'; } catch (_) { return false; } })();
    var inspectOn = params.get('inspect') === '1';

    if (!debugOn && !inspectOn) return;
    window._casehubDebug = true;

    // Persist debug preference via URL param
    if (params.get('debug') === '1') {
        try { localStorage.setItem('casehub_debug', '1'); } catch (_) {}
    }

    // CSS
    var style = document.createElement('style');
    style.textContent = [
        '.cchub-debug-panel { position: fixed; top: 4px; left: 4px; z-index: 999999; background: rgba(0,0,0,0.85); color: #0f0; font-family: ui-monospace, Menlo, monospace; font-size: 11px; padding: 6px 10px; border-radius: 6px; pointer-events: none; line-height: 1.4; font-variant-numeric: tabular-nums; white-space: pre; }',
        '.cchub-debug-panel.warn { color: #ff0; }',
        '.cchub-debug-panel.bad { color: #f66; }',
        '.cchub-debug-close { position: fixed; top: 4px; right: 4px; z-index: 999999; background: #f33; color: #fff; border: none; padding: 2px 8px; font-size: 11px; border-radius: 4px; cursor: pointer; }',
        inspectOn ? '[style*="backdrop-filter"], .macos-window, .ui-os-dock-wrapper, .os-dock-bubble, .modal { outline: 2px dashed rgba(255,0,0,0.5) !important; outline-offset: -2px; }' : '',
        inspectOn ? '[style*="will-change"] { outline: 2px dashed rgba(0,120,255,0.5) !important; outline-offset: -2px; }' : ''
    ].join('\n');
    document.head.appendChild(style);

    // FPS overlay
    if (debugOn) {
        var panel = document.createElement('div');
        panel.className = 'cchub-debug-panel';
        document.documentElement.appendChild(panel);

        var close = document.createElement('button');
        close.className = 'cchub-debug-close';
        close.textContent = '× debug';
        close.addEventListener('click', function () {
            try { localStorage.removeItem('casehub_debug'); } catch (_) {}
            panel.remove();
            close.remove();
        });
        document.documentElement.appendChild(close);

        var frames = [];
        var last = performance.now();
        var MAX_SAMPLES = 60; // 1s @ 60fps

        function tick(now) {
            var delta = now - last;
            last = now;
            frames.push(delta);
            if (frames.length > MAX_SAMPLES) frames.shift();
            requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);

        function update() {
            if (!frames.length) return;
            var sum = 0, max = 0;
            for (var i = 0; i < frames.length; i++) { sum += frames[i]; if (frames[i] > max) max = frames[i]; }
            var avg = sum / frames.length;
            var fps = Math.round(1000 / avg);
            var sorted = frames.slice().sort(function (a, b) { return a - b; });
            var p95 = sorted[Math.floor(sorted.length * 0.95)];

            var viewport = document.body.className.match(/viewport-\w+/) || ['—'];
            var view = document.body.className.match(/view-\w+/) || ['—'];
            var touch = document.body.classList.contains('touch') ? ' touch' : '';
            var perf = document.body.classList.contains('performance-mode') ? ' ⚡' : '';

            panel.textContent =
                'FPS ' + fps + ' (p95 ' + p95.toFixed(1) + 'ms)' + perf + '\n' +
                viewport[0] + ' · ' + view[0] + touch + '\n' +
                window.innerWidth + '×' + window.innerHeight + ' · DPR ' + (window.devicePixelRatio || 1);

            panel.classList.remove('warn', 'bad');
            if (p95 > 16.67) panel.classList.add('warn');
            if (p95 > 33.33) panel.classList.add('bad');
        }
        setInterval(update, 500);
    }
})();
