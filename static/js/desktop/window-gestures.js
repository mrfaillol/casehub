/**
 * CaseHub Window Gestures — mobile-specific
 *
 * Ativa APENAS em body.view-os.viewport-mobile + body.touch:
 * - Swipe-down na titlebar > 60px → fecha janela (minimize ou close, dependendo)
 * - Injeta botão X (window-close-mobile) na titlebar se não existir
 *
 * GPU-only animations (transform + opacity). PointerEvent API unificado.
 */
(function () {
    'use strict';
    if (window._casehubWindowGestures) return;
    window._casehubWindowGestures = true;

    var SWIPE_DOWN_THRESHOLD = 60;   // px
    var SWIPE_MAX_HORIZONTAL = 40;   // px — se sair muito na horizontal, cancela
    var FOLLOW_RATIO = 0.6;          // quanto da distância o usuário "vê" no drag (visual feedback)

    function shouldHandle() {
        var body = document.body;
        return body.classList.contains('view-os') &&
               body.classList.contains('viewport-mobile') &&
               body.classList.contains('touch');
    }

    function injectCloseBtn(titlebar) {
        if (titlebar.querySelector('.window-close-mobile')) return;
        var btn = document.createElement('button');
        btn.className = 'window-close-mobile';
        btn.setAttribute('aria-label', 'Fechar janela');
        btn.innerHTML = '<i class="fas fa-times"></i>';
        btn.type = 'button';
        btn.addEventListener('click', function (e) {
            e.stopPropagation();
            var winEl = titlebar.closest('.macos-window');
            if (!winEl) return;
            closeOrHide(winEl);
        });
        titlebar.appendChild(btn);
    }

    function closeOrHide(winEl) {
        var wm = window.osWindowManager;
        if (!wm) return;
        var id = winEl.id;
        if (wm.closeWindow) {
            wm.closeWindow(id);
        } else if (wm.minimizeWindow) {
            wm.minimizeWindow(id);
        }
    }

    function setupTitlebar(titlebar) {
        if (titlebar._gesturesBound) return;
        titlebar._gesturesBound = true;

        injectCloseBtn(titlebar);

        var start = null;

        titlebar.addEventListener('pointerdown', function (e) {
            if (!shouldHandle()) return;
            if (e.pointerType === 'mouse') return;
            if (e.target.closest('.window-close-mobile')) return;

            var winEl = titlebar.closest('.macos-window');
            if (!winEl) return;

            start = {
                x: e.clientX,
                y: e.clientY,
                t: performance.now(),
                pid: e.pointerId,
                winEl: winEl
            };
            winEl.style.willChange = 'transform';
        }, { passive: true });

        titlebar.addEventListener('pointermove', function (e) {
            if (!start || e.pointerId !== start.pid) return;
            var dy = e.clientY - start.y;
            var dx = Math.abs(e.clientX - start.x);
            if (dy <= 0 || dx > SWIPE_MAX_HORIZONTAL) return;
            // Feedback visual: janela segue o dedo parcialmente
            var visual = dy * FOLLOW_RATIO;
            start.winEl.style.transform = 'translate3d(0, ' + visual + 'px, 0)';
            start.winEl.style.opacity = Math.max(0.4, 1 - dy / 400);
        }, { passive: true });

        function endDrag(e) {
            if (!start || e.pointerId !== start.pid) return;
            var dy = e.clientY - start.y;
            var dx = Math.abs(e.clientX - start.x);
            var winEl = start.winEl;
            start = null;

            // Reset transform/opacity com transição suave
            winEl.style.transition = 'transform 200ms ' + (getComputedStyle(document.body).getPropertyValue('--ease-out-expo') || 'ease-out') + ', opacity 200ms ease';
            if (dy > SWIPE_DOWN_THRESHOLD && dx < SWIPE_MAX_HORIZONTAL) {
                // Swipe-down confirmado: anima pra fora e fecha
                winEl.style.transform = 'translate3d(0, 100%, 0)';
                winEl.style.opacity = '0';
                setTimeout(function () {
                    winEl.style.transition = '';
                    winEl.style.transform = '';
                    winEl.style.opacity = '';
                    winEl.style.willChange = 'auto';
                    closeOrHide(winEl);
                }, 210);
            } else {
                // Cancelado: volta ao normal
                winEl.style.transform = '';
                winEl.style.opacity = '';
                setTimeout(function () {
                    winEl.style.transition = '';
                    winEl.style.willChange = 'auto';
                }, 210);
            }
        }

        titlebar.addEventListener('pointerup', endDrag, { passive: true });
        titlebar.addEventListener('pointercancel', endDrag, { passive: true });
    }

    function scan() {
        if (!shouldHandle()) return;
        document.querySelectorAll('.macos-titlebar').forEach(setupTitlebar);
    }

    // Scan inicial + a cada viewport change (janelas podem ser criadas dinamicamente)
    document.addEventListener('DOMContentLoaded', scan, { once: true });
    document.addEventListener('viewportchange', scan);

    // MutationObserver para janelas criadas depois do load (window-manager.openWindow)
    var mo = new MutationObserver(function (muts) {
        for (var i = 0; i < muts.length; i++) {
            for (var j = 0; j < muts[i].addedNodes.length; j++) {
                var n = muts[i].addedNodes[j];
                if (n.nodeType !== 1) continue;
                if (n.classList && n.classList.contains('macos-titlebar')) setupTitlebar(n);
                if (n.querySelector) {
                    n.querySelectorAll('.macos-titlebar').forEach(setupTitlebar);
                }
            }
        }
    });
    mo.observe(document.documentElement, { childList: true, subtree: true });
})();
