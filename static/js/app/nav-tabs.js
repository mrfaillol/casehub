/* CaseHub App · Interactive nav-tabs (progressive enhancement)
 *
 * Enhances the static shell nav (templates/app/base.html):
 *   - Desktop rail (.ch-tabs[data-nav-tabs]): close button (×) per tab (except
 *     [data-pinned]), HTML5 drag-to-reorder, order persisted in localStorage.
 *   - "Mais" bubble dropdown (.ch-menu--tabs-more): lists routes NOT currently
 *     in the rail (closed tabs + catalog "extra"), each with its Lucide icon.
 *   - Mobile bottom-nav: closing the active route-tab = drag it OUT of the bar
 *     (pointer drag up past threshold) → removes tab + navigates to dashboard.
 *   - Mobile search: topbar lupa opens a docked search bar at the bottom edge
 *     (.ch-mobile-search); its input forwards the query to the command palette.
 *
 * No bundler. No heavy libs. All animation is transform/opacity (GPU), ≤220ms.
 * Honors prefers-reduced-motion + Eco mode (CSS handles the no-motion variants).
 *
 * State model: a single ordered list of "open tab keys" in localStorage drives
 * both the desktop rail order and which routes are considered "open". The pinned
 * Painel tab is always first and cannot be closed.
 */
(function () {
  'use strict';

  var ORDER_KEY = 'casehub.navtabs.order.v1';
  var CLOSED_KEY = 'casehub.navtabs.closed.v1';

  var catalog = null;
  var rail = null;          // .ch-tabs[data-nav-tabs]
  var moreList = null;      // [data-tabs-more-list]

  // ── utils ───────────────────────────────────────────────────────────────
  function reducedMotion() {
    var eco = document.documentElement.getAttribute('data-eco') === 'true';
    var pref = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    return eco || pref;
  }
  function isMobile() {
    return window.matchMedia && window.matchMedia('(max-width: 879.98px)').matches;
  }
  function readCatalog() {
    var el = document.querySelector('script[type="application/json"][data-route-catalog]');
    if (!el) return null;
    try { return JSON.parse(el.textContent); } catch (e) { return null; }
  }
  function lsGet(key) {
    try { var v = localStorage.getItem(key); return v ? JSON.parse(v) : null; }
    catch (e) { return null; }
  }
  function lsSet(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) {}
  }
  function mountIcons() {
    // Lucide CDN is async — retry a couple times if not ready yet.
    if (window.CHLucide && window.CHLucide.mount) { window.CHLucide.mount(); return; }
    var tries = 0;
    var t = setInterval(function () {
      tries++;
      if (window.CHLucide && window.CHLucide.mount) { window.CHLucide.mount(); clearInterval(t); }
      if (tries > 20) clearInterval(t);
    }, 100);
  }
  function tabKeyByKey(key) {
    if (!catalog) return null;
    var all = (catalog.tabs || []).concat(catalog.extra || []);
    for (var i = 0; i < all.length; i++) if (all[i].key === key) return all[i];
    return null;
  }

  // ── closed-tabs set (keys removed via × ) ────────────────────────────────
  function getClosed() {
    var c = lsGet(CLOSED_KEY);
    return Array.isArray(c) ? c : [];
  }
  function setClosed(arr) { lsSet(CLOSED_KEY, arr); }
  function markClosed(key) {
    var c = getClosed();
    if (c.indexOf(key) === -1) { c.push(key); setClosed(c); }
  }
  function unmarkClosed(key) {
    var c = getClosed().filter(function (k) { return k !== key; });
    setClosed(c);
  }

  // ─────────────────────────────────────────────────────────────────────────
  //  DESKTOP RAIL — order, close buttons, drag reorder
  // ─────────────────────────────────────────────────────────────────────────

  function railTabs() {
    return rail ? Array.prototype.slice.call(rail.querySelectorAll('.ch-tab')) : [];
  }

  /** Apply persisted order to the DOM (pinned tabs always pushed to front). */
  function applyOrder() {
    if (!rail) return;
    var order = lsGet(ORDER_KEY);
    if (!Array.isArray(order) || !order.length) return;
    var byKey = {};
    railTabs().forEach(function (t) { byKey[t.getAttribute('data-route-key')] = t; });
    // pinned first, then persisted order, then any leftover (new tabs added later)
    var seen = {};
    var ordered = [];
    railTabs().forEach(function (t) {
      if (t.getAttribute('data-pinned') === 'true') { ordered.push(t); seen[t.getAttribute('data-route-key')] = 1; }
    });
    order.forEach(function (k) {
      if (byKey[k] && !seen[k]) { ordered.push(byKey[k]); seen[k] = 1; }
    });
    railTabs().forEach(function (t) {
      var k = t.getAttribute('data-route-key');
      if (!seen[k]) { ordered.push(t); seen[k] = 1; }
    });
    ordered.forEach(function (t) { rail.appendChild(t); });
  }

  function persistOrder() {
    var keys = railTabs().map(function (t) { return t.getAttribute('data-route-key'); });
    lsSet(ORDER_KEY, keys);
  }

  /** Remove tabs the user previously closed. The currently-active route is
   *  auto-reopened (kept in the rail + cleared from the closed set), because the
   *  user explicitly navigated to it. Pinned tabs are never removed. */
  function pruneClosed() {
    if (!rail) return;
    var closed = getClosed();
    if (!closed.length) return;
    var activeKey = catalog ? catalog.active : null;
    // Normalize: route-map "active" maps to no tab; module keys match data-route-key.
    railTabs().forEach(function (tab) {
      var key = tab.getAttribute('data-route-key');
      if (tab.getAttribute('data-pinned') === 'true') return;
      if (closed.indexOf(key) === -1) return;
      if (key === activeKey) { unmarkClosed(key); return; } // user is on it → reopen
      tab.parentNode && tab.parentNode.removeChild(tab);
    });
  }

  /** Inject close button into each non-pinned tab. */
  function addCloseButtons() {
    railTabs().forEach(function (tab) {
      if (tab.getAttribute('data-pinned') === 'true') return;
      if (tab.querySelector('.ch-tab__close')) return;
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'ch-tab__close';
      btn.setAttribute('aria-label', 'Fechar aba');
      btn.setAttribute('tabindex', '-1');
      btn.innerHTML = '<i data-lucide="x"></i>';
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        closeTab(tab);
      });
      tab.appendChild(btn);
    });
  }

  function closeTab(tab) {
    if (!tab || tab.getAttribute('data-pinned') === 'true') return;
    var key = tab.getAttribute('data-route-key');
    var wasActive = tab.classList.contains('is-active');
    markClosed(key);
    tab.parentNode && tab.parentNode.removeChild(tab);
    persistOrder();
    rebuildMoreList();
    if (wasActive && catalog) {
      // Navigate to dashboard (pinned) when the open route is closed.
      window.location.href = (catalog.prefix || '/casehub') + '/dashboard';
    }
  }

  /** Re-open a previously closed tab (from the "Mais" dropdown) → navigate to it. */
  function openRoute(key) {
    var meta = tabKeyByKey(key);
    if (!meta) return;
    unmarkClosed(key);
    window.location.href = meta.href;
  }

  // ── HTML5 drag reorder (desktop) ──
  var dragEl = null;
  function bindDrag() {
    railTabs().forEach(makeDraggable);
  }
  function makeDraggable(tab) {
    if (tab.__chDrag) return;
    tab.__chDrag = true;
    tab.setAttribute('draggable', 'true');

    tab.addEventListener('dragstart', function (e) {
      dragEl = tab;
      tab.classList.add('is-dragging');
      rail.classList.add('is-reordering');
      try {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', tab.getAttribute('data-route-key') || '');
      } catch (_) {}
    });
    tab.addEventListener('dragend', function () {
      tab.classList.remove('is-dragging');
      rail.classList.remove('is-reordering');
      railTabs().forEach(function (t) { t.classList.remove('is-drop-before', 'is-drop-after'); });
      dragEl = null;
      persistOrder();
    });
    tab.addEventListener('dragover', function (e) {
      if (!dragEl || dragEl === tab) return;
      // Pinned tab stays first — don't allow dropping before it.
      if (tab.getAttribute('data-pinned') === 'true') return;
      e.preventDefault();
      var rect = tab.getBoundingClientRect();
      var before = (e.clientX - rect.left) < rect.width / 2;
      tab.classList.toggle('is-drop-before', before);
      tab.classList.toggle('is-drop-after', !before);
    });
    tab.addEventListener('dragleave', function () {
      tab.classList.remove('is-drop-before', 'is-drop-after');
    });
    tab.addEventListener('drop', function (e) {
      if (!dragEl || dragEl === tab) return;
      if (tab.getAttribute('data-pinned') === 'true') return;
      e.preventDefault();
      var rect = tab.getBoundingClientRect();
      var before = (e.clientX - rect.left) < rect.width / 2;
      tab.classList.remove('is-drop-before', 'is-drop-after');
      if (before) rail.insertBefore(dragEl, tab);
      else rail.insertBefore(dragEl, tab.nextSibling);
      persistOrder();
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  //  "MAIS" DROPDOWN — routes not in the rail, with per-page icons
  // ─────────────────────────────────────────────────────────────────────────

  function railKeys() {
    var s = {};
    railTabs().forEach(function (t) { s[t.getAttribute('data-route-key')] = 1; });
    return s;
  }

  function rebuildMoreList() {
    if (!moreList || !catalog) return;
    var inRail = railKeys();
    var items = [];
    // 1) tabs that were closed (so the user can re-open them)
    (catalog.tabs || []).forEach(function (t) {
      if (!inRail[t.key] && !t.pinned) items.push(t);
    });
    // 2) catalog "extra" routes (always live outside the rail)
    (catalog.extra || []).forEach(function (t) {
      if (!inRail[t.key]) items.push(t);
    });
    moreList.innerHTML = '';
    items.forEach(function (it) {
      var a = document.createElement('a');
      a.className = 'ch-menu__item';
      a.setAttribute('role', 'menuitem');
      a.href = it.href;
      a.setAttribute('data-route-key', it.key);
      a.innerHTML = '<i data-lucide="' + (it.icon || 'circle') + '"></i> ' + escapeHtml(it.label);
      // Re-open closed *tab* routes through openRoute (clears closed flag);
      // plain extras just navigate.
      a.addEventListener('click', function (e) {
        if (tabIsCloseable(it.key)) {
          e.preventDefault();
          openRoute(it.key);
        }
      });
      moreList.appendChild(a);
    });
    if (!items.length) {
      var empty = document.createElement('div');
      empty.className = 'ch-notifications-menu__empty';
      empty.textContent = 'Todas as rotas principais estão nas abas.';
      moreList.appendChild(empty);
    }
    mountIcons();
  }

  function tabIsCloseable(key) {
    var meta = null;
    (catalog.tabs || []).forEach(function (t) { if (t.key === key) meta = t; });
    return !!meta && !meta.pinned;
  }

  function escapeHtml(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  // ─────────────────────────────────────────────────────────────────────────
  //  MOBILE — drag the active route-tab OUT of the bottom-nav to close it
  // ─────────────────────────────────────────────────────────────────────────

  var THRESHOLD = 56; // px upward to confirm "drag out"

  /** Remove from the mobile bottom-nav any route-tab the user closed (via drag-out).
   *  Mirrors the desktop rail's pruneClosed: the currently-active route is kept
   *  (and un-closed, since the user navigated to it); Painel (pinned) never drops. */
  function pruneClosedBottomNav() {
    var scroller = document.querySelector('.ch-bottomnav__scroller');
    if (!scroller) return;
    var closed = getClosed();
    if (!closed.length) return;
    var activeKey = catalog ? catalog.active : null;
    Array.prototype.slice.call(scroller.querySelectorAll('.ch-bottomnav__item')).forEach(function (item) {
      if (item.classList.contains('ch-bottomnav__item--more')) return;
      if (item.getAttribute('data-pinned') === 'true') return;
      var key = item.getAttribute('data-route-key');
      if (!key || closed.indexOf(key) === -1) return;
      if (key === activeKey) { unmarkClosed(key); return; } // user is on it → reopen
      if (item.parentNode) item.parentNode.removeChild(item);
    });
  }

  function bindMobileDragOut() {
    var wrap = document.querySelector('.ch-bottomnav-wrap');
    if (!wrap || wrap.__chDragOut) return;
    wrap.__chDragOut = true;

    wrap.addEventListener('pointerdown', function (e) {
      if (!isMobile()) return;
      var item = e.target.closest && e.target.closest('.ch-bottomnav__item');
      if (!item) return;
      // Qualquer route-tab visível (não-fixo) pode ser arrastado pra fora p/ fechar
      // (= o × do desktop). O Painel (dashboard / data-pinned) NUNCA fecha.
      if (item.classList.contains('ch-bottomnav__item--more')) return;
      if (item.getAttribute('data-pinned') === 'true') return;
      var key = moduleToKey(item);
      if (!key || key === 'dashboard') return; // pinned / not a closeable route

      var startY = e.clientY;
      var startX = e.clientX;
      var moved = false;
      var armed = false;
      try { item.setPointerCapture(e.pointerId); } catch (_) {}

      function move(ev) {
        var dy = startY - ev.clientY;        // up = positive
        var dx = Math.abs(ev.clientX - startX);
        if (!moved && (dy > 6 || dx > 6)) moved = true;
        if (dy <= 0) {                        // dragging down/sideways — reset
          item.style.removeProperty('--drag-dy');
          item.style.removeProperty('--drag-progress');
          item.removeAttribute('data-dragging-out');
          wrap.removeAttribute('data-close-hint');
          wrap.removeAttribute('data-close-armed');
          armed = false;
          return;
        }
        ev.preventDefault();
        item.setAttribute('data-dragging-out', 'true');
        item.style.setProperty('--drag-dy', dy + 'px');
        item.style.setProperty('--drag-progress', Math.min(1, dy / (THRESHOLD * 1.4)).toFixed(3));
        wrap.setAttribute('data-close-hint', 'true');
        armed = dy >= THRESHOLD;
        wrap.setAttribute('data-close-armed', armed ? 'true' : 'false');
      }
      function up(ev) {
        item.removeEventListener('pointermove', move);
        item.removeEventListener('pointerup', up);
        item.removeEventListener('pointercancel', up);
        try { item.releasePointerCapture(e.pointerId); } catch (_) {}
        item.style.removeProperty('--drag-dy');
        item.style.removeProperty('--drag-progress');
        item.removeAttribute('data-dragging-out');
        wrap.removeAttribute('data-close-hint');
        wrap.removeAttribute('data-close-armed');
        if (armed) {
          // Confirmed close (= × do desktop): marca fechado (compartilhado com o
          // rail desktop). Se era a rota ativa, navega pro Painel; senão só some
          // da barra.
          markClosed(key);
          var wasActive = item.classList.contains('is-active');
          if (wasActive) {
            if (catalog) window.location.href = (catalog.prefix || '/casehub') + '/dashboard';
          } else if (item.parentNode) {
            item.parentNode.removeChild(item);
          }
          return;
        }
        // A real drag happened but wasn't confirmed → swallow the trailing click
        // so we don't reload the current route unexpectedly. A plain tap (no move)
        // falls through and navigates normally.
        if (moved) {
          item.addEventListener('click', function suppress(ce) {
            ce.preventDefault(); ce.stopPropagation();
            item.removeEventListener('click', suppress, true);
          }, true);
        }
      }
      item.addEventListener('pointermove', move);
      item.addEventListener('pointerup', up);
      item.addEventListener('pointercancel', up);
    });
  }

  // Map a bottom-nav item to a catalog key. Prefer the explicit data-route-key
  // (server-rendered); fall back to href matching for safety.
  function moduleToKey(item) {
    var dk = item.getAttribute('data-route-key');
    if (dk) return dk;
    var href = item.getAttribute('href') || '';
    if (!catalog) return null;
    var all = (catalog.tabs || []).concat(catalog.extra || []);
    for (var i = 0; i < all.length; i++) {
      if (href.indexOf(all[i].href) !== -1) return all[i].key;
    }
    return null;
  }

  // ─────────────────────────────────────────────────────────────────────────
  //  MOBILE SEARCH BAR (docked bottom edge)
  // ─────────────────────────────────────────────────────────────────────────

  function bindMobileSearch() {
    var box = document.querySelector('[data-mobile-search]');
    var input = box && box.querySelector('[data-mobile-search-input]');
    var closeBtn = box && box.querySelector('[data-mobile-search-close]');
    if (!box || !input) return;

    function openSearch() {
      box.hidden = false;
      box.setAttribute('aria-hidden', 'false');
      // slide-up: add is-entering for one frame, then remove
      if (!reducedMotion()) {
        box.classList.add('is-entering');
        requestAnimationFrame(function () {
          requestAnimationFrame(function () { box.classList.remove('is-entering'); });
        });
      }
      try { input.focus({ preventScroll: true }); } catch (_) { input.focus(); }
    }
    function closeSearch() {
      box.hidden = true;
      box.setAttribute('aria-hidden', 'true');
      input.value = '';
    }

    // Topbar mobile lupa → open docked bar (intercept the dedicated action).
    document.addEventListener('click', function (e) {
      var trig = e.target.closest && e.target.closest('[data-action="mobile-search-open"]');
      if (!trig) return;
      e.preventDefault();
      if (!isMobile()) {
        // Safety: on desktop fall back to palette (button is hidden anyway).
        document.dispatchEvent(new CustomEvent('casehub:palette:open'));
        return;
      }
      if (box.hidden) openSearch(); else closeSearch();
    });

    if (closeBtn) closeBtn.addEventListener('click', closeSearch);

    // Forward the query to the existing command palette (one search engine).
    // Enter (or first input) opens palette seeded with the value, then closes
    // the docked bar so results show in the palette overlay.
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { e.preventDefault(); closeSearch(); return; }
      if (e.key === 'Enter') {
        e.preventDefault();
        var q = input.value.trim();
        closeSearch();
        document.dispatchEvent(new CustomEvent('casehub:palette:open', { detail: { seed: q } }));
      }
    });

    // Close docked bar when keyboard dismissed / route palette opens elsewhere.
    document.addEventListener('casehub:palette:open', function (ev) {
      // If palette is opened by something else while our bar is up, hide ours.
      if (!box.hidden && (!ev.detail || ev.detail.from !== 'mobile-search')) {
        // keep behaviour simple: leave value in palette, hide docked bar
        box.hidden = true;
        box.setAttribute('aria-hidden', 'true');
      }
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  //  init
  // ─────────────────────────────────────────────────────────────────────────
  function init() {
    catalog = readCatalog();
    rail = document.querySelector('.ch-tabs[data-nav-tabs]');
    moreList = document.querySelector('[data-tabs-more-list]');

    if (rail) {
      pruneClosed();
      applyOrder();
      addCloseButtons();
      bindDrag();
    }
    rebuildMoreList();
    pruneClosedBottomNav();
    bindMobileDragOut();
    bindMobileSearch();
    mountIcons();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window.CHNavTabs = { init: init, rebuildMore: rebuildMoreList };
})();
