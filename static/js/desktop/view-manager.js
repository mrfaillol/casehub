/**
 * CaseHub View Manager
 * Gerencia qual visualização está ativa: 'os' (Liquid Glass OS-like, default)
 * ou 'web' (Web Browser Classic, opt-in).
 *
 * Persiste em localStorage. Emite evento 'casehub:view:change' pra outros módulos.
 * Inicialização é feita inline em base.html <head> (anti-FOUC) antes deste script.
 *
 * API pública: window.CaseHubView.get() / set('os'|'web') / toggle()
 */
(function () {
    'use strict';
    if (window.CaseHubView) return;

    var STORAGE_KEY = 'casehub_view';
    var VALID = ['os', 'web'];
    var DEFAULT = 'os';

    function readStored() {
        try {
            var v = localStorage.getItem(STORAGE_KEY);
            return VALID.indexOf(v) >= 0 ? v : DEFAULT;
        } catch (_) {
            return DEFAULT;
        }
    }

    function apply(view) {
        if (VALID.indexOf(view) < 0) view = DEFAULT;
        VALID.forEach(function (v) {
            document.body.classList.toggle('view-' + v, v === view);
        });
        try { localStorage.setItem(STORAGE_KEY, view); } catch (_) {}
        document.dispatchEvent(new CustomEvent('casehub:view:change', {
            detail: { view: view }
        }));
        return view;
    }

    window.CaseHubView = {
        get: function () { return readStored(); },
        set: function (view) { return apply(view); },
        toggle: function () {
            var current = readStored();
            return apply(current === 'os' ? 'web' : 'os');
        },
        DEFAULT: DEFAULT,
        VALID: VALID.slice()
    };

    // Sync inicial — idempotente mesmo se inline script já aplicou a classe
    if (document.body) {
        apply(readStored());
    } else {
        document.addEventListener('DOMContentLoaded', function () { apply(readStored()); }, { once: true });
    }

    /* ------------------------------------------------------------------
       A11y fix — scrollable-region-focusable
       Adiciona tabindex="0" em elementos scrollable sem interactive content,
       pra usuários de teclado poderem scrollar com arrow keys.
       WCAG 2.1 AA — Success Criterion 2.1.1 (Keyboard).
       ------------------------------------------------------------------ */
    function makeScrollablesFocusable() {
        var candidates = document.querySelectorAll('.widget-body, .macos-window-content, .app-content-scroll, .tab-content-area');
        for (var i = 0; i < candidates.length; i++) {
            var el = candidates[i];
            if (el.hasAttribute('tabindex')) continue;
            var s = getComputedStyle(el);
            var scrollable = (s.overflowY === 'auto' || s.overflowY === 'scroll' || s.overflow === 'auto' || s.overflow === 'scroll');
            if (scrollable && el.scrollHeight > el.clientHeight + 4) {
                el.setAttribute('tabindex', '0');
                if (!el.hasAttribute('role')) el.setAttribute('role', 'region');
                if (!el.hasAttribute('aria-label')) {
                    var near = el.closest('[id]');
                    el.setAttribute('aria-label', 'Área rolável' + (near && near.id ? ' — ' + near.id : ''));
                }
            }
        }
    }

    // Rodar múltiplas vezes pra pegar widgets que populam tardiamente (gridstack, iframes)
    function scheduleAll() {
        [100, 400, 1200, 2500].forEach(function (t) { setTimeout(makeScrollablesFocusable, t); });
    }
    if (document.readyState === 'complete') {
        scheduleAll();
    } else {
        window.addEventListener('load', scheduleAll, { once: true });
    }
    // Re-apply quando layout muda (debounced)
    var mo = new MutationObserver(function () {
        clearTimeout(window._cchubScrollableT);
        window._cchubScrollableT = setTimeout(makeScrollablesFocusable, 300);
    });
    mo.observe(document.documentElement, { childList: true, subtree: true });
})();
