/* CaseHub App · Command palette / global search
 *
 * Listener for the `casehub:palette:open` event (dispatched by topbar Buscar
 * button and Cmd+K shortcut). Renders a centered overlay with an input.
 * Live search across clients, cases, and tasks via existing list endpoints
 * with a debounced fetch. Enter without selection → navigate to clients
 * filtered by the query.
 */
(function () {
  'use strict';

  var PREFIX = window.CASEHUB_PREFIX || '/casehub';
  var overlay = null;
  var input = null;
  var results = null;
  var debounceTimer = null;
  var currentRequestToken = 0;

  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.className = 'ch-palette';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Buscar');
    overlay.innerHTML = (
      '<div class="ch-palette__backdrop" data-palette-close></div>' +
      '<div class="ch-palette__panel" role="document">' +
        '<div class="ch-palette__inputwrap">' +
          '<span class="ch-palette__icon" data-icon="search" data-icon-size="18"></span>' +
          '<input type="search" class="ch-palette__input" autocomplete="off" ' +
                 'spellcheck="false" placeholder="Buscar clientes, processos, tarefas…" ' +
                 'aria-label="Termo de busca">' +
          '<kbd class="ch-palette__hint">esc</kbd>' +
        '</div>' +
        '<div class="ch-palette__results" role="listbox" aria-live="polite"></div>' +
        '<div class="ch-palette__footer">' +
          '<span>Enter para abrir lista de clientes</span>' +
          '<span>↑↓ navegar · esc fechar</span>' +
        '</div>' +
      '</div>'
    );
    document.body.appendChild(overlay);
    input = overlay.querySelector('.ch-palette__input');
    results = overlay.querySelector('.ch-palette__results');
    bindEvents();
    return overlay;
  }

  function bindEvents() {
    overlay.addEventListener('click', function (e) {
      if (e.target.hasAttribute('data-palette-close')) close();
    });
    input.addEventListener('input', onInput);
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { e.preventDefault(); close(); return; }
      if (e.key === 'Enter') {
        var active = results.querySelector('.ch-palette__row.is-active') ||
                     results.querySelector('.ch-palette__row');
        if (active && active.dataset.href) {
          e.preventDefault();
          go(active.dataset.href);
          return;
        }
        // No active row → navigate to clients filtered by query
        var q = (input.value || '').trim();
        if (q) {
          e.preventDefault();
          go(PREFIX + '/clients?search=' + encodeURIComponent(q));
        }
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        moveActive(e.key === 'ArrowDown' ? 1 : -1);
      }
    });
  }

  function moveActive(delta) {
    var rows = results.querySelectorAll('.ch-palette__row');
    if (!rows.length) return;
    var idx = -1;
    rows.forEach(function (r, i) { if (r.classList.contains('is-active')) idx = i; });
    idx = Math.max(0, Math.min(rows.length - 1, idx + delta));
    rows.forEach(function (r) { r.classList.remove('is-active'); });
    rows[idx].classList.add('is-active');
    rows[idx].scrollIntoView({ block: 'nearest' });
  }

  function open(ev) {
    ensureOverlay();
    overlay.classList.add('is-open');
    document.body.classList.add('ch-palette-open');
    // Optional seed (e.g. from the mobile docked search bar): pre-fill + search.
    var seed = ev && ev.detail && typeof ev.detail.seed === 'string' ? ev.detail.seed.trim() : '';
    setTimeout(function () {
      input.focus();
      if (seed) { input.value = seed; onInput(); }
      else { input.select(); }
    }, 16);
  }

  function close() {
    if (!overlay) return;
    overlay.classList.remove('is-open');
    document.body.classList.remove('ch-palette-open');
    if (input) input.value = '';
    if (results) results.innerHTML = '';
  }

  function go(href) {
    close();
    window.location.href = href;
  }

  function onInput() {
    clearTimeout(debounceTimer);
    var q = (input.value || '').trim();
    if (q.length < 2) {
      results.innerHTML = (
        '<div class="ch-palette__empty">Digite ao menos 2 letras…</div>'
      );
      return;
    }
    debounceTimer = setTimeout(function () { fetchResults(q); }, 160);
  }

  function fetchResults(q) {
    var token = ++currentRequestToken;
    results.innerHTML = '<div class="ch-palette__empty">Buscando…</div>';
    fetch(PREFIX + '/api/search?q=' + encodeURIComponent(q), {
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' }
    })
      .then(function (r) { return r.ok ? r.json() : { results: [] }; })
      .then(function (data) {
        if (token !== currentRequestToken) return;
        render(data.results || [], q);
      })
      .catch(function () {
        if (token !== currentRequestToken) return;
        results.innerHTML = (
          '<div class="ch-palette__empty">' +
            'Pressione Enter para abrir clientes com "' + escape(q) + '"' +
          '</div>'
        );
      });
  }

  function escape(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function render(rows, q) {
    if (!rows.length) {
      results.innerHTML = (
        '<div class="ch-palette__empty">' +
          'Nenhum resultado. <a href="' + PREFIX + '/clients?search=' + encodeURIComponent(q) + '">' +
            'Ver lista filtrada de clientes' +
          '</a>' +
        '</div>'
      );
      return;
    }
    var html = rows.map(function (r, i) {
      return (
        '<a class="ch-palette__row' + (i === 0 ? ' is-active' : '') + '" ' +
          'data-href="' + escape(r.href) + '" href="' + escape(r.href) + '">' +
          '<span class="ch-palette__row-kind">' + escape(r.kind || '') + '</span>' +
          '<span class="ch-palette__row-title">' + escape(r.title || '') + '</span>' +
          (r.subtitle ? '<span class="ch-palette__row-sub">' + escape(r.subtitle) + '</span>' : '') +
        '</a>'
      );
    }).join('');
    results.innerHTML = html;
    results.querySelectorAll('.ch-palette__row').forEach(function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        go(a.dataset.href);
      });
    });
  }

  document.addEventListener('casehub:palette:open', open);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && overlay && overlay.classList.contains('is-open')) close();
  });
})();
