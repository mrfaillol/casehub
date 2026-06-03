/* CaseHub App · Theme + Eco mode controller
 *
 * 3 estados ortogonais:
 *   theme:  light | dark | auto    (auto = prefers-color-scheme)
 *   eco:    on    | off  | auto    (auto = prefers-reduced-motion OR battery < 20% unplugged)
 *
 * Persistido em localStorage. Aplicado em <html data-theme="..." data-eco="...">.
 * Atalhos: T = ciclar tema · E = ciclar Eco.
 */
(function () {
  'use strict';

  var STORAGE_THEME = 'casehub.theme';
  var STORAGE_ECO = 'casehub.eco';
  var root = document.documentElement;
  var mqDark = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  var mqReduced = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;

  function readStored(key, fallback) {
    try {
      var v = localStorage.getItem(key);
      return v == null ? fallback : v;
    } catch (e) { return fallback; }
  }
  function writeStored(key, value) {
    try { localStorage.setItem(key, value); } catch (e) {}
  }

  function resolveTheme(pref) {
    if (pref === 'light' || pref === 'dark') return pref;
    if (mqDark && mqDark.matches) return 'dark';
    return 'light';
  }
  function resolveEco(pref) {
    if (pref === 'on' || pref === 'off') return pref === 'on';
    if (mqReduced && mqReduced.matches) return true;
    return false;
  }

  function applyTheme(pref) {
    var resolved = resolveTheme(pref);
    root.setAttribute('data-theme', resolved);
    root.setAttribute('data-theme-pref', pref || 'auto');
    sync();
    dispatch('theme', { pref: pref, resolved: resolved });
  }
  function applyEco(pref) {
    var resolved = resolveEco(pref);
    if (resolved) root.setAttribute('data-eco', 'true');
    else root.removeAttribute('data-eco');
    root.setAttribute('data-eco-pref', pref || 'auto');
    sync();
    dispatch('eco', { pref: pref, resolved: resolved });
  }

  function sync() {
    var t = root.getAttribute('data-theme') || 'light';
    var e = root.getAttribute('data-eco') === 'true';
    var btnT = document.querySelectorAll('[data-toggle="theme"]');
    var btnE = document.querySelectorAll('[data-toggle="eco"]');
    btnT.forEach(function (b) {
      b.setAttribute('aria-pressed', t === 'dark' ? 'true' : 'false');
      b.setAttribute('aria-label', t === 'dark' ? 'Tema escuro (T para alternar)' : 'Tema claro (T para alternar)');
    });
    btnE.forEach(function (b) {
      b.setAttribute('aria-pressed', e ? 'true' : 'false');
      b.setAttribute('aria-label', e ? 'Modo Eco ativo (E para alternar)' : 'Modo Eco desativado (E para alternar)');
    });
  }

  function dispatch(kind, detail) {
    document.dispatchEvent(new CustomEvent('casehub:' + kind, { detail: detail }));
  }

  function cycleTheme() {
    var resolved = root.getAttribute('data-theme') || resolveTheme(readStored(STORAGE_THEME, 'auto'));
    var next = resolved === 'dark' ? 'light' : 'dark';
    writeStored(STORAGE_THEME, next);
    applyTheme(next);
  }
  function cycleEco() {
    var cur = readStored(STORAGE_ECO, 'auto');
    var next = cur === 'auto' ? 'on' : cur === 'on' ? 'off' : 'auto';
    writeStored(STORAGE_ECO, next);
    applyEco(next);
  }

  // Bind toggles
  function bind() {
    document.querySelectorAll('[data-toggle="theme"]').forEach(function (el) {
      if (el.__chBound) return;
      el.__chBound = true;
      el.addEventListener('click', cycleTheme);
    });
    document.querySelectorAll('[data-toggle="eco"]').forEach(function (el) {
      if (el.__chBound) return;
      el.__chBound = true;
      el.addEventListener('click', cycleEco);
    });
  }

  // Keyboard shortcuts (skip if focus inside form input/textarea)
  function isTypingTarget(target) {
    if (!target) return false;
    var tag = (target.tagName || '').toLowerCase();
    return tag === 'input' || tag === 'textarea' || tag === 'select' || target.isContentEditable;
  }
  document.addEventListener('keydown', function (e) {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if (isTypingTarget(e.target)) return;
    if (e.key === 't' || e.key === 'T') { e.preventDefault(); cycleTheme(); }
    else if (e.key === 'e' || e.key === 'E') { e.preventDefault(); cycleEco(); }
  });

  // React to OS preference changes when user is on "auto"
  if (mqDark) mqDark.addEventListener('change', function () {
    var pref = readStored(STORAGE_THEME, 'auto');
    if (pref === 'auto') applyTheme('auto');
  });
  if (mqReduced) mqReduced.addEventListener('change', function () {
    var pref = readStored(STORAGE_ECO, 'auto');
    if (pref === 'auto') applyEco('auto');
  });

  // Battery API → suggest Eco if <20% and unplugged
  if (navigator.getBattery) {
    navigator.getBattery().then(function (battery) {
      function maybeSuggest() {
        var pref = readStored(STORAGE_ECO, 'auto');
        if (pref !== 'auto') return;
        if (!battery.charging && battery.level < 0.2) applyEco('on');
      }
      battery.addEventListener('levelchange', maybeSuggest);
      battery.addEventListener('chargingchange', maybeSuggest);
      maybeSuggest();
    }).catch(function () {});
  }

  // Bootstrap on DOMContentLoaded
  function init() {
    applyTheme(readStored(STORAGE_THEME, 'auto'));
    applyEco(readStored(STORAGE_ECO, 'auto'));
    bind();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Public API
  window.CHTheme = {
    get: function () {
      return {
        theme: readStored(STORAGE_THEME, 'auto'),
        eco: readStored(STORAGE_ECO, 'auto'),
        resolvedTheme: root.getAttribute('data-theme'),
        resolvedEco: root.getAttribute('data-eco') === 'true'
      };
    },
    setTheme: function (pref) { writeStored(STORAGE_THEME, pref); applyTheme(pref); },
    setEco: function (pref) { writeStored(STORAGE_ECO, pref); applyEco(pref); },
    cycleTheme: cycleTheme,
    cycleEco: cycleEco,
    bind: bind
  };
})();
