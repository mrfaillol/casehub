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
  var PINNED_EXTRA_KEY = 'casehub.navtabs.pinned_extra.v1';

  var catalog = null;
  var rail = null;          // .ch-tabs[data-nav-tabs]
  var moreList = null;      // [data-tabs-more-list]

  // ── overflow (priority-plus) state ──────────────────────────────────────
  // Tabs that don't fit in the rail are diverted to the TOP of the "Mais"
  // dropdown (never silently hidden). This is DERIVED from width — not
  // persisted — so the visible set is deterministic per device, not driven by
  // a silent scroll position. `overflowKeys` is the ordered list of keys
  // currently diverted; `overflowTabs` maps key → detached .ch-tab element.
  var overflowKeys = [];
  var overflowTabs = {};
  var reflowRaf = 0;
  var reflowDebounce = 0;

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

  // ── pinned-extras set (catalog.extra routes the user promoted to the rail) ──
  // PessoaDemo 16/06: clicar uma rota no "Mais" deve fixá-la no tab bar e ela ficar
  // ali (por usuário → localStorage, como a ordem/closed das abas). Abas
  // primárias fechadas voltam via CLOSED_KEY; rotas "extra" (que vivem fora do
  // rail) ganham esta lista própria, injetada no rail a cada load.
  function getPinnedExtras() {
    var p = lsGet(PINNED_EXTRA_KEY);
    return Array.isArray(p) ? p : [];
  }
  function setPinnedExtras(arr) { lsSet(PINNED_EXTRA_KEY, arr); }
  function addPinnedExtra(key) {
    var p = getPinnedExtras();
    if (p.indexOf(key) === -1) { p.push(key); setPinnedExtras(p); }
  }
  function removePinnedExtra(key) {
    setPinnedExtras(getPinnedExtras().filter(function (k) { return k !== key; }));
  }
  function isExtraKey(key) {
    return (catalog && catalog.extra || []).some(function (t) { return t.key === key; });
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
    // Width-diverted tabs aren't in the DOM rail right now, but they ARE open
    // and belong after the visible ones (they were diverted from the right end,
    // overflowKeys is already left→right). Keep them in the saved order so a
    // later restore (bigger viewport) preserves position.
    if (overflowKeys.length) keys = keys.concat(overflowKeys);
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
    // Pinned extra (promoted from "Mais") → just unpin it; primary tab → mark
    // closed so it surfaces in "Mais" as a re-openable route.
    if (tab.getAttribute('data-extra') === 'true') removePinnedExtra(key);
    else markClosed(key);
    tab.parentNode && tab.parentNode.removeChild(tab);
    persistOrder();
    // Closing frees rail width → re-evaluate overflow (a diverted tab may now
    // fit back in). reflowOverflow() rebuilds the "Mais" list itself.
    reflowOverflow();
    if (wasActive && catalog) {
      // Navigate to dashboard (pinned) when the open route is closed.
      window.location.href = (catalog.prefix || '/casehub') + '/dashboard';
    }
  }

  /** Build a rail tab element from catalog meta, matching the static markup so
   *  reflow/drag/close machinery treats it like any other tab. `isExtra` marks
   *  catalog.extra routes promoted from "Mais" (persisted in PINNED_EXTRA_KEY). */
  function createRailTab(meta, isExtra) {
    var a = document.createElement('a');
    a.className = 'ch-tab';
    a.setAttribute('role', 'tab');
    a.setAttribute('data-route-key', meta.key);
    if (isExtra) a.setAttribute('data-extra', 'true');
    a.href = meta.href;
    if (catalog && catalog.active === meta.key) a.classList.add('is-active');
    a.innerHTML = '<i data-lucide="' + (meta.icon || 'circle') + '"></i> '
                + '<span class="ch-tab__label">' + escapeHtml(meta.label) + '</span>';
    return a;
  }

  /** Inject persisted pinned-extra routes into the rail (run at init). */
  function injectPinnedExtras() {
    if (!rail || !catalog) return;
    var have = {};
    railTabs().forEach(function (t) { have[t.getAttribute('data-route-key')] = 1; });
    getPinnedExtras().forEach(function (key) {
      if (have[key]) return;
      var meta = tabKeyByKey(key);
      if (meta) rail.appendChild(createRailTab(meta, true));
    });
  }

  /** Pin a route from "Mais" into the rail and keep it there. Closed primary
   *  tabs clear their closed flag; catalog.extra routes join PINNED_EXTRA. When
   *  `navigate` is true we also go to the route (clicking the label); when false
   *  the tab is added in place (the discoverable "+" affordance) — PessoaDemo 16/06. */
  function pinRouteToRail(key, navigate) {
    var meta = tabKeyByKey(key);
    if (!meta) return;
    var extra = isExtraKey(key);
    if (extra) addPinnedExtra(key);
    else unmarkClosed(key);

    if (rail) {
      var exists = railTabs().some(function (t) { return t.getAttribute('data-route-key') === key; });
      if (!exists) {
        var tab = createRailTab(meta, extra);
        rail.appendChild(tab);
        makeDraggable(tab);
      }
      addCloseButtons();
      persistOrder();
      mountIcons();
      reflowOverflow();   // also rebuilds the "Mais" list
    } else {
      rebuildMoreList();
    }
    if (navigate) window.location.href = meta.href;
  }

  /** Re-open/pin a route from the "Mais" dropdown → pin to rail + navigate. */
  function openRoute(key) {
    pinRouteToRail(key, true);
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
      // Reorder can change which tab sits at the right edge → re-evaluate which
      // ones overflow into "Mais".
      reflowOverflow();
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

  // ─────────────────────────────────────────────────────────────────────────
  //  OVERFLOW (priority-plus) — divert tabs that don't fit into "Mais"
  // ─────────────────────────────────────────────────────────────────────────

  /** A tab is "protected" from overflow: the active route (user is on it) and
   *  any pinned tab (none today — Painel is a separate bubble — but kept for
   *  safety). Protected tabs never leave the rail. */
  function isProtectedTab(tab) {
    if (!tab) return true;
    if (tab.getAttribute('data-pinned') === 'true') return true;
    if (tab.classList.contains('is-active')) return true;
    return false;
  }

  /** Reflow the rail: bring every diverted tab back, then (while the rail
   *  overflows its container) move the LAST non-protected tab out to the
   *  overflow list — which renders at the TOP of "Mais". Deterministic by
   *  width, so the visible set is stable per device. Skipped on mobile (the
   *  bottom-nav owns navigation there). */
  function reflowOverflow() {
    if (!rail) return;
    // Mobile: bottom-nav governs; the desktop rail is display:none. Restore any
    // diverted tabs so nothing is stuck out of the rail if the viewport grew.
    if (isMobile() || rail.offsetParent === null) {
      restoreAllOverflow();
      updateOverflowIndicator();
      return;
    }
    // 1) Bring all diverted tabs back into the rail (in catalog order via the
    //    persisted order pass) before re-measuring.
    restoreAllOverflow();
    applyOrder();

    // 2) While the rail content is wider than the rail, divert the last
    //    eligible (non-protected) tab. Guard the loop against runaway.
    var guard = 0;
    while (rail.scrollWidth > rail.clientWidth + 1 && guard < 64) {
      guard++;
      var tabs = railTabs();
      var victim = null;
      for (var i = tabs.length - 1; i >= 0; i--) {
        if (!isProtectedTab(tabs[i])) { victim = tabs[i]; break; }
      }
      if (!victim) break; // only protected tabs remain — stop (can't shrink more)
      var key = victim.getAttribute('data-route-key');
      overflowTabs[key] = victim;
      overflowKeys.unshift(key); // most-recently-diverted first → top of "Mais"
      if (victim.parentNode) victim.parentNode.removeChild(victim);
    }

    rebuildMoreList();
    updateOverflowIndicator();
  }

  /** Re-attach every diverted tab back into the rail and clear overflow state.
   *  Order is fixed afterwards by applyOrder()/catalog order. */
  function restoreAllOverflow() {
    if (!overflowKeys.length) return;
    // Append in original (catalog) order: overflowKeys is newest-first, so the
    // catalog-ordered re-insert is handled by applyOrder() after this.
    overflowKeys.slice().forEach(function (k) {
      var el = overflowTabs[k];
      if (el && rail) rail.appendChild(el);
    });
    overflowKeys = [];
    overflowTabs = {};
  }

  /** Edge-fade indicator (mirrors the mobile bottom-nav pattern, shell.css):
   *  set data-overflow-start/-end on the rail per scroll position so it's clear
   *  the rail can be dragged/scrolled (and that "Mais" holds the rest). */
  function updateOverflowIndicator() {
    if (!rail) return;
    var hasOverflow = rail.scrollWidth > rail.clientWidth + 1;
    if (!hasOverflow) {
      rail.removeAttribute('data-overflow-start');
      rail.removeAttribute('data-overflow-end');
      return;
    }
    var atStart = rail.scrollLeft <= 1;
    var atEnd = rail.scrollLeft + rail.clientWidth >= rail.scrollWidth - 1;
    rail.setAttribute('data-overflow-start', atStart ? 'false' : 'true');
    rail.setAttribute('data-overflow-end', atEnd ? 'false' : 'true');
  }

  /** Schedule a reflow on the next frame (coalesces ResizeObserver bursts). */
  function scheduleReflow() {
    if (reflowRaf) return;
    reflowRaf = (window.requestAnimationFrame || function (f) { return setTimeout(f, 16); })(function () {
      reflowRaf = 0;
      reflowOverflow();
    });
  }

  /** Observe rail/container size + window resize (debounced ~100ms) and the
   *  rail's own scroll (to update the edge fades). */
  function bindReflow() {
    if (rail.__chReflow) return;
    rail.__chReflow = true;

    if (window.ResizeObserver) {
      var shell = rail.closest('.ch-tabs-shell') || rail;
      var ro = new ResizeObserver(function () { scheduleReflow(); });
      try { ro.observe(shell); ro.observe(rail); } catch (_) {}
    }
    window.addEventListener('resize', function () {
      if (reflowDebounce) clearTimeout(reflowDebounce);
      reflowDebounce = setTimeout(reflowOverflow, 100);
    });
    rail.addEventListener('scroll', updateOverflowIndicator, { passive: true });
  }

  function rebuildMoreList() {
    if (!moreList || !catalog) return;
    var byKey = {};
    (catalog.tabs || []).forEach(function (t) { byKey[t.key] = t; });
    // Keys physically in the rail right now (excludes width-diverted ones).
    var domKeys = {};
    railTabs().forEach(function (t) { domKeys[t.getAttribute('data-route-key')] = 1; });

    var items = [];
    var overflowItem = {}; // mark which list entries came from width-overflow
    // 1) tabs diverted by WIDTH (priority-plus): always at the TOP so Drive (and
    //    Emails, when gestor) appear WITH their label instead of vanishing.
    overflowKeys.forEach(function (k) {
      var t = byKey[k];
      if (t) { items.push(t); overflowItem[k] = 1; }
    });
    // 2) tabs the user CLOSED via × (so they can re-open them).
    (catalog.tabs || []).forEach(function (t) {
      if (!domKeys[t.key] && !overflowItem[t.key] && !t.pinned) items.push(t);
    });
    // 3) catalog "extra" routes (always live outside the rail).
    (catalog.extra || []).forEach(function (t) {
      if (!domKeys[t.key] && !overflowItem[t.key]) items.push(t);
    });
    moreList.innerHTML = '';
    items.forEach(function (it) {
      // Width-diverted tabs are still "open" (they only spilled out of the rail
      // for lack of space) → no pin affordance, plain navigation.
      var isOverflow = !!overflowItem[it.key];
      // Pinnable = a closed primary tab OR a catalog.extra route. Clicking the
      // label pins + navigates; the "+" pins in place (stays on the page).
      var pinnable = !isOverflow && (tabIsCloseable(it.key) || isExtraKey(it.key));

      var a = document.createElement('a');
      a.className = 'ch-menu__item';
      a.setAttribute('role', 'menuitem');
      a.href = it.href;
      a.setAttribute('data-route-key', it.key);
      a.innerHTML = '<i data-lucide="' + (it.icon || 'circle') + '"></i> ' + escapeHtml(it.label);

      if (!pinnable) { moreList.appendChild(a); return; }

      // Pin label click → pin to rail + navigate (Equipe CaseHub: "aparece no tab bar e fica ali").
      a.addEventListener('click', function (e) {
        e.preventDefault();
        pinRouteToRail(it.key, true);
      });
      // Discoverable "+" → fixa no tab bar SEM sair da página (PessoaDemo: "como jogo daqui pra cá?").
      var pin = document.createElement('button');
      pin.type = 'button';
      pin.className = 'ch-menu__pin';
      pin.setAttribute('aria-label', 'Fixar "' + it.label + '" nas abas');
      pin.setAttribute('title', 'Fixar nas abas');
      pin.style.cssText = 'border:0;background:transparent;cursor:pointer;color:var(--text-muted,#888);display:inline-flex;align-items:center;padding:4px;flex:0 0 auto';
      pin.innerHTML = '<i data-lucide="pin"></i>';
      pin.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        pinRouteToRail(it.key, false);
      });
      var row = document.createElement('div');
      row.className = 'ch-menu__row';
      row.style.cssText = 'display:flex;align-items:center';
      a.style.flex = '1 1 auto';
      row.appendChild(a);
      row.appendChild(pin);
      moreList.appendChild(row);
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
      injectPinnedExtras();   // restore catalog.extra routes the user pinned
      applyOrder();
      addCloseButtons();
      bindDrag();
    }
    rebuildMoreList();
    if (rail) {
      // Priority-plus overflow: measure now, then keep in sync on resize. Icons
      // must be mounted first so tab width is final before we measure.
      mountIcons();
      reflowOverflow();
      bindReflow();
      // Re-measure once after Lucide CDN finishes (icons can land async and
      // change tab widths), so the initial divert isn't off by one.
      scheduleReflow();
    }
    pruneClosedBottomNav();
    bindMobileDragOut();
    bindMobileSearch();
    mountIcons();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window.CHNavTabs = { init: init, rebuildMore: rebuildMoreList };
})();
