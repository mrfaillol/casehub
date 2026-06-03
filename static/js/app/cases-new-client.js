/* ==========================================================================
 * cases-new-client.js — cadastro rápido de cliente direto no form de processo.
 *
 * Botão "Novo cliente" abre modal (.ch-overlay/.ch-modal, padrão do projeto),
 * POST JSON → /cases/api/clients/quick-create, injeta <option> selecionada
 * no <select id="client_id"> sem reload nem sair da tela.
 *
 * Padrões: window.toast.* feedback; abertura via data-open (igual kanban).
 * ======================================================================== */
(function () {
  'use strict';

  var btn = document.getElementById('ch-new-client-btn');
  var modal = document.getElementById('ch-new-client-modal');
  var form = document.getElementById('ch-new-client-form');
  var saveBtn = document.getElementById('ch-new-client-save');
  var errorEl = document.getElementById('ch-new-client-error');
  var select = document.getElementById('client_id');
  if (!btn || !modal || !form || !saveBtn || !select) return;

  var url = btn.getAttribute('data-quick-create-url');
  var lastFocus = null;

  function toast(kind, msg) {
    if (window.toast && typeof window.toast[kind] === 'function') window.toast[kind](msg);
  }

  function showError(msg) {
    if (!errorEl) return;
    errorEl.textContent = msg;
    errorEl.hidden = false;
  }
  function clearError() {
    if (!errorEl) return;
    errorEl.textContent = '';
    errorEl.hidden = true;
  }

  function openModal() {
    lastFocus = document.activeElement;
    clearError();
    form.reset();
    modal.hidden = false;
    modal.setAttribute('data-open', 'true');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    var first = document.getElementById('nc_first_name');
    if (first) setTimeout(function () { first.focus(); }, 50);
  }

  function closeModal() {
    modal.hidden = true;
    modal.removeAttribute('data-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  function save() {
    clearError();
    var fd = new FormData(form);
    var first = (fd.get('first_name') || '').toString().trim();
    var last = (fd.get('last_name') || '').toString().trim();
    if (!first || !last) {
      showError('Nome e sobrenome são obrigatórios.');
      return;
    }

    var payload = {
      first_name: first,
      last_name: last,
      email: (fd.get('email') || '').toString().trim(),
      phone: (fd.get('phone') || '').toString().trim(),
      cpf: (fd.get('cpf') || '').toString().trim()
    };

    saveBtn.disabled = true;
    saveBtn.style.opacity = '0.6';

    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(payload)
    }).then(function (r) {
      return r.json().then(function (data) { return { ok: r.ok, data: data }; });
    }).then(function (res) {
      saveBtn.disabled = false;
      saveBtn.style.opacity = '';
      if (!res.ok || !res.data || !res.data.client) {
        showError((res.data && res.data.detail) || 'Não foi possível criar o cliente.');
        return;
      }
      var c = res.data.client;
      // Injeta a opção e seleciona
      var opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.label;
      opt.selected = true;
      select.appendChild(opt);
      select.value = String(c.id);
      // Dispara change para qualquer listener dependente
      select.dispatchEvent(new Event('change', { bubbles: true }));
      closeModal();
      toast('success', 'Cliente "' + c.label + '" criado e selecionado.');
    }).catch(function () {
      saveBtn.disabled = false;
      saveBtn.style.opacity = '';
      showError('Falha de conexão. Tente novamente.');
    });
  }

  btn.addEventListener('click', openModal);
  saveBtn.addEventListener('click', save);

  // Enter dentro do form salva (exceto em textarea, que aqui não existe)
  form.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); save(); }
  });

  // Botões de fechar + clique no backdrop + Esc
  modal.querySelectorAll('[data-new-client-close]').forEach(function (el) {
    el.addEventListener('click', closeModal);
  });
  modal.addEventListener('click', function (e) {
    if (e.target === modal) closeModal();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && modal.getAttribute('data-open') === 'true') closeModal();
  });
})();
