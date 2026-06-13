/* CaseHub App · Accessibility controller — "Fonte Grande / Letra Grande"
 *
 * Modo togglável + persistente para público 40-60+ ("CaseHub for Dummies").
 * Aplica a classe `ch-a11y-large` em <html> (documentElement) a partir do
 * localStorage no load, e oferece toggle via [data-toggle="a11y-large"]
 * (checkbox/switch) ou window.CHA11y.toggle().
 *
 * Persistência: localStorage chave 'casehub.a11y.large' = 'on' | 'off'.
 * Estilo aplicado em static/css/app/accessibility.css (reescala tokens --fs-*).
 *
 * Independente do theme.js — sem dependências. Idempotente (re-bind seguro).
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'casehub.a11y.large';
  var CLASS = 'ch-a11y-large';
  var root = document.documentElement;

  function read() {
    try { return localStorage.getItem(STORAGE_KEY) === 'on'; } catch (e) { return false; }
  }
  function write(on) {
    try { localStorage.setItem(STORAGE_KEY, on ? 'on' : 'off'); } catch (e) {}
  }

  function apply(on) {
    root.classList.toggle(CLASS, !!on);
    syncControls(!!on);
    document.dispatchEvent(new CustomEvent('casehub:a11y-large', { detail: { on: !!on } }));
  }

  function syncControls(on) {
    document.querySelectorAll('[data-toggle="a11y-large"]').forEach(function (el) {
      if (el.tagName === 'INPUT' && el.type === 'checkbox') {
        el.checked = on;
      } else {
        el.setAttribute('aria-pressed', on ? 'true' : 'false');
      }
      el.setAttribute(
        'aria-label',
        on ? 'Fonte grande ativada (toque para voltar ao padrão)'
           : 'Fonte grande desativada (toque para ampliar o texto)'
      );
    });
  }

  function setOn(on) {
    write(on);
    apply(on);
  }
  function toggle() {
    setOn(!root.classList.contains(CLASS));
  }

  function bind() {
    document.querySelectorAll('[data-toggle="a11y-large"]').forEach(function (el) {
      if (el.__chA11yBound) return;
      el.__chA11yBound = true;
      if (el.tagName === 'INPUT' && el.type === 'checkbox') {
        el.addEventListener('change', function () { setOn(el.checked); });
      } else {
        el.addEventListener('click', function (e) { e.preventDefault(); toggle(); });
      }
    });
  }

  function init() {
    apply(read());
    bind();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.CHA11y = {
    isOn: function () { return root.classList.contains(CLASS); },
    setOn: setOn,
    toggle: toggle,
    bind: bind
  };
})();
