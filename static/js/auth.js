/* auth.js — comportamento mínimo das telas de auth (login, signup, forgot)
   Theme-agnostic: não toca em CSS de theme. Apenas:
   - toggle de visibilidade do password
   - estado de loading do submit (label + aria-busy + disable de inputs)
*/

(function () {
  'use strict';

  // 1. Password toggle — delegated handler em [data-field-toggle]
  document.addEventListener('click', function (ev) {
    var btn = ev.target.closest('[data-field-toggle]');
    if (!btn) return;
    var fieldId = btn.getAttribute('data-field-toggle');
    var input = document.getElementById(fieldId);
    if (!input) return;
    var isHidden = input.type === 'password';
    input.type = isHidden ? 'text' : 'password';
    btn.setAttribute('aria-pressed', String(isHidden));
    btn.setAttribute('aria-label', isHidden ? 'Ocultar senha' : 'Mostrar senha');
  });

  // 2. Loading state — quando form submete, vira spinner e desabilita
  document.addEventListener('submit', function (ev) {
    var form = ev.target;
    if (!form || form.tagName !== 'FORM') return;
    var submit = form.querySelector('.auth-submit');
    if (!submit) return;
    var label = submit.querySelector('.auth-submit__label');
    if (label) label.textContent = 'Entrando…';
    submit.setAttribute('aria-busy', 'true');
    submit.disabled = true;
    // mantém os outros inputs habilitados pra browser fazer submit corretamente
    var spinner =
      '<svg class="auth-submit__spinner" viewBox="0 0 14 14" fill="none" aria-hidden="true">' +
      '<circle cx="7" cy="7" r="5.5" stroke="currentColor" stroke-width="1.5" stroke-dasharray="18 10" stroke-linecap="round"/>' +
      '</svg>';
    submit.insertAdjacentHTML('afterbegin', spinner);
  });
})();
