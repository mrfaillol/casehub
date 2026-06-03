/**
 * Window Swipe — navegação horizontal entre janelas abertas em mobile/tablet.
 * Gesto: swipe horizontal no viewport com 2+ janelas abertas troca a focada.
 * Usa PointerEvent (W3C standard, unificado mouse/touch/stylus).
 *
 * Ativo apenas em body.viewport-mobile ou body.viewport-tablet + body.touch.
 */
(function () {
    'use strict';

    if (window._casehubWindowSwipe) return;
    window._casehubWindowSwipe = true;

    var SWIPE_THRESHOLD = 60;         // px mínimos pra considerar swipe
    var SWIPE_VELOCITY_MIN = 0.35;    // px/ms — 350px em 1s
    var SWIPE_MAX_VERT_RATIO = 0.5;   // vertical não pode ser mais de 50% do horizontal
    var IGNORE_SELECTORS = 'input, textarea, select, button, a, [contenteditable], [data-no-swipe], .table-responsive, .ui-os-dock-wrapper, .os-dock-bubble, table';

    var start = null;

    function shouldHandle() {
        if (!window.osWindowManager) return false;
        var body = document.body;
        if (!body.classList.contains('viewport-mobile') && !body.classList.contains('viewport-tablet')) return false;
        if (!body.classList.contains('touch')) return false;
        return true;
    }

    function onPointerDown(e) {
        if (!shouldHandle()) return;
        if (e.pointerType === 'mouse') return; // swipe só touch/stylus
        if (e.target.closest && e.target.closest(IGNORE_SELECTORS)) return;

        start = {
            x: e.clientX,
            y: e.clientY,
            t: performance.now(),
            id: e.pointerId
        };
    }

    function onPointerUp(e) {
        if (!start || e.pointerId !== start.id) { start = null; return; }

        var dx = e.clientX - start.x;
        var dy = e.clientY - start.y;
        var dt = performance.now() - start.t;
        start = null;

        var absX = Math.abs(dx);
        var absY = Math.abs(dy);

        if (absX < SWIPE_THRESHOLD) return;
        if (absY / absX > SWIPE_MAX_VERT_RATIO) return; // scroll vertical domina

        var velocity = absX / dt;
        if (velocity < SWIPE_VELOCITY_MIN) return;

        switchWindow(dx < 0 ? 1 : -1);
    }

    function switchWindow(direction) {
        var wm = window.osWindowManager;
        if (!wm || !wm.windows) return;

        // Coleta janelas não-minimizadas, ordenadas por z-index (topo ao final)
        var items = [];
        wm.windows.forEach(function (w) {
            if (w.state === 'minimized' || !w.url || !w.el) return;
            var z = parseInt(w.el.style.zIndex) || 0;
            items.push({ id: w.id, z: z });
        });
        if (items.length < 2) return;

        items.sort(function (a, b) { return b.z - a.z; });

        // Rotaciona: focada atual é items[0]; próxima (swipe left) é items[1], anterior (swipe right) é items[items.length-1]
        var targetId;
        if (direction === 1) {
            targetId = items[1].id;
        } else {
            targetId = items[items.length - 1].id;
        }

        if (wm.bringToFront) wm.bringToFront(targetId);
    }

    document.addEventListener('pointerdown', onPointerDown, { passive: true });
    document.addEventListener('pointerup', onPointerUp, { passive: true });
    document.addEventListener('pointercancel', function () { start = null; }, { passive: true });
})();
