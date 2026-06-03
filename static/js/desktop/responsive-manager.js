/**
 * CaseHub Responsive Manager
 * Sincroniza body classes com viewport + input type via matchMedia.
 * Reage a mudanças live (rotate device, resize window, hotplug mouse/touch).
 *
 * Classes gerenciadas:
 *   body.viewport-mobile  (<768px)
 *   body.viewport-tablet  (768-1279px)
 *   body.viewport-desktop (≥1280px)
 *   body.touch            (ponteiro coarse ou touch disponível)
 *   body.mouse            (ponteiro fine ou mouse disponível)
 *
 * Classes ortogonais: podem coexistir (ex: tablet com mouse = tablet + mouse + touch).
 */
(function () {
    'use strict';

    if (window._casehubResponsiveMgr) return;
    window._casehubResponsiveMgr = true;

    var BP = {
        mobile: window.matchMedia('(max-width: 767px)'),
        tablet: window.matchMedia('(min-width: 768px) and (max-width: 1279px)'),
        desktop: window.matchMedia('(min-width: 1280px)'),
        coarse: window.matchMedia('(pointer: coarse)'),
        fine: window.matchMedia('(pointer: fine)'),
        reducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)')
    };

    function setClass(name, active) {
        document.body.classList.toggle(name, !!active);
    }

    function sync() {
        setClass('viewport-mobile', BP.mobile.matches);
        setClass('viewport-tablet', BP.tablet.matches);
        setClass('viewport-desktop', BP.desktop.matches);

        // Input types — coarse (touch) e fine (mouse) podem coexistir (iPad + mouse)
        var hasTouch = BP.coarse.matches || ('ontouchstart' in window) || navigator.maxTouchPoints > 0;
        var hasMouse = BP.fine.matches || (!hasTouch && window.innerWidth >= 1024);
        setClass('touch', hasTouch);
        setClass('mouse', hasMouse);

        setClass('reduced-motion', BP.reducedMotion.matches);

        // Evento custom pra outros módulos (window-manager etc) reagirem
        document.dispatchEvent(new CustomEvent('viewportchange', {
            detail: {
                viewport: BP.mobile.matches ? 'mobile' : (BP.tablet.matches ? 'tablet' : 'desktop'),
                touch: hasTouch,
                mouse: hasMouse,
                reducedMotion: BP.reducedMotion.matches
            }
        }));
    }

    // Listeners reativos — disparam só em mudança, zero custo steady-state
    Object.keys(BP).forEach(function (k) {
        var mq = BP[k];
        if (mq.addEventListener) {
            mq.addEventListener('change', sync);
        } else if (mq.addListener) {
            mq.addListener(sync); // Safari <14
        }
    });

    // Sync inicial — antes do DOMContentLoaded pra evitar flash
    if (document.body) {
        sync();
    } else {
        document.addEventListener('DOMContentLoaded', sync, { once: true });
    }

    /* ------------------------------------------------------------------
       Nav-bar self-aware — ResizeObserver no dock-wrapper.
       Seta data-density (compact/medium/comfortable) baseado no espaço real.
       CSS reage via [data-density="..."] selector.
       ------------------------------------------------------------------ */
    function observeDock() {
        var dock = document.querySelector('.ui-os-dock-wrapper');
        var apps = document.querySelector('.os-dock-bubble.os-dock-apps');
        if (!dock || !apps || dock._navObserved) return;
        dock._navObserved = true;
        /* syncAppsWidth removido — nova arquitetura dock-apps-nav.css usa
           inline-flex + fit-content que o browser resolve sozinho. Sem race
           condition de setTimeouts. */

        var ro = new ResizeObserver(function (entries) {
            for (var i = 0; i < entries.length; i++) {
                var w = entries[i].contentRect.width;
                document.documentElement.style.setProperty('--dock-available-width', w + 'px');
                var density;
                if (w < 480) density = 'compact';
                else if (w < 800) density = 'medium';
                else density = 'comfortable';
                if (dock.dataset.density !== density) {
                    dock.dataset.density = density;
                    document.dispatchEvent(new CustomEvent('dockdensitychange', { detail: { density: density, width: w } }));
                }
            }
        });
        ro.observe(apps);

        // Bonus: verificar se nav-links overflow do container apps
        var checkOverflow = function () {
            var nav = apps.querySelector('.nav') || apps;
            var hasOverflow = nav.scrollWidth > apps.clientWidth + 2;
            apps.classList.toggle('has-overflow', hasOverflow);
        };
        ro.observe(apps);
        setTimeout(checkOverflow, 200);
        setTimeout(checkOverflow, 800);
    }

    if (document.readyState === 'complete') observeDock();
    else window.addEventListener('load', observeDock, { once: true });

    /* ------------------------------------------------------------------
       F3 Cut 4 — IntersectionObserver pausa animations off-screen.
       Elementos com animação fora do viewport param de consumir main thread.
       ------------------------------------------------------------------ */
    function setupAnimationPause() {
        if (!('IntersectionObserver' in window)) return;
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (e) {
                e.target.style.animationPlayState = e.isIntersecting ? 'running' : 'paused';
            });
        }, { rootMargin: '100px' });

        // Observa elementos que provavelmente têm animação
        var candidates = document.querySelectorAll(
            '.widget-container, .card, .notification-panel, .user-dock-dropdown, ' +
            '[class*="animate-"], [style*="animation"]'
        );
        candidates.forEach(function (el) { io.observe(el); });
    }

    /* ------------------------------------------------------------------
       F3 Cut 5 — loading="lazy" auto em imgs sem atributo.
       Widget icons + avatars carregam só quando entram viewport.
       ------------------------------------------------------------------ */
    function lazyifyImages() {
        var imgs = document.querySelectorAll('img:not([loading])');
        imgs.forEach(function (img) {
            img.loading = 'lazy';
            img.decoding = 'async';
        });
    }

    function applyPerfOptimizations() {
        lazyifyImages();
        setupAnimationPause();
    }

    if (document.readyState === 'complete') {
        setTimeout(applyPerfOptimizations, 200);
    } else {
        window.addEventListener('load', function () {
            setTimeout(applyPerfOptimizations, 200);
        }, { once: true });
    }

    // Re-apply só algumas vezes em intervals — mais barato que MutationObserver global
    [1000, 3000, 8000].forEach(function (t) { setTimeout(applyPerfOptimizations, t); });
})();
