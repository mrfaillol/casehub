/* ==========================================================================
 * cases-inline-edit.js — edição inline célula-a-célula na LISTA de processos.
 *
 * Clica em qualquer célula marcada [data-field] → vira input/select inline,
 * salva via PATCH {patch-base}/{case_id}/field, sem popup nem reload.
 *
 * Prazos (data-deadline="1") só são editáveis por ADMIN/ADVOGADO — o backend
 * é a fonte de verdade (403); o front também trava o affordance via
 * data-can-edit-deadlines no <table>.
 *
 * Convenções do projeto:
 *   - PATCH JSON, get_current_user no backend (401/403/404).
 *   - window.toast.{success,error} para feedback.
 *   - Animações 150-220ms transform/opacity (GPU). Sem libs externas.
 * ======================================================================== */
(function () {
  'use strict';

  var table = document.querySelector('[data-cases-table]');
  if (!table) return;

  var patchBase = table.getAttribute('data-patch-base') || '';
  var canEditDeadlines = table.getAttribute('data-can-edit-deadlines') === '1';
  var activeCell = null; // célula em edição no momento

  function toast(kind, msg) {
    if (window.toast && typeof window.toast[kind] === 'function') {
      window.toast[kind](msg);
    }
  }

  function parseOptions(raw) {
    // "value:Label|value:Label" → [{value, label}]
    return (raw || '').split('|').filter(Boolean).map(function (pair) {
      var idx = pair.indexOf(':');
      if (idx === -1) return { value: pair, label: pair };
      return { value: pair.slice(0, idx), label: pair.slice(idx + 1) };
    });
  }

  function statusPillClass(value) {
    var s = (value || 'active').toLowerCase();
    if (['closed', 'approved', 'denied', 'concluido', 'concluído', 'finalizado'].indexOf(s) !== -1) return 'ch-pill--ok';
    if (['review', 'rfe', 'revisao'].indexOf(s) !== -1) return 'ch-pill--warn';
    return 'ch-pill--info';
  }

  function renderDisplay(cell, displayText, rawValue) {
    var field = cell.getAttribute('data-field');
    if (field === 'status') {
      var label = displayText || rawValue || 'Ativo';
      cell.innerHTML = '<span class="ch-pill ' + statusPillClass(rawValue) +
        '"><span class="dot"></span></span>';
      cell.querySelector('.ch-pill').appendChild(document.createTextNode(label));
    } else {
      cell.textContent = displayText && displayText !== '' ? displayText : '—';
      // Re-anexa cadeado se for prazo travado (não chega aqui se travado, mas defensivo)
      if (cell.getAttribute('data-deadline') === '1' && !canEditDeadlines) {
        var lock = document.createElement('span');
        lock.className = 'ch-lock-glyph';
        lock.setAttribute('aria-hidden', 'true');
        lock.innerHTML = '&#128274;';
        cell.appendChild(lock);
      }
    }
  }

  function flashSaved(cell) {
    cell.classList.remove('ch-cell--saving');
    cell.classList.add('ch-cell--saved');
    setTimeout(function () { cell.classList.remove('ch-cell--saved'); }, 260);
  }

  function commit(cell, newValue) {
    var row = cell.closest('[data-case-id]');
    var caseId = row && row.getAttribute('data-case-id');
    var field = cell.getAttribute('data-field');
    if (!caseId || !field) return restore(cell);

    var prev = cell.getAttribute('data-value') || '';
    if (newValue === prev) return restore(cell); // nada mudou

    cell.classList.add('ch-cell--saving');

    fetch(patchBase + '/' + encodeURIComponent(caseId) + '/field', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ field: field, value: newValue === '' ? null : newValue })
    }).then(function (r) {
      return r.json().then(function (data) { return { ok: r.ok, status: r.status, data: data }; });
    }).then(function (res) {
      if (!res.ok) {
        cell.classList.remove('ch-cell--saving');
        var detail = (res.data && res.data.detail) || 'Erro ao salvar';
        if (res.status === 403) toast('warning', detail);
        else toast('error', detail);
        restore(cell); // mantém valor anterior
        return;
      }
      var rawVal = res.data.value == null ? '' : res.data.value;
      cell.setAttribute('data-value', rawVal);
      // Para select (status), usa o rótulo amigável do data-options, não o valor cru.
      var display = res.data.display;
      if (field === 'status') {
        var opts = parseOptions(cell.getAttribute('data-options'));
        var match = opts.filter(function (o) { return o.value === rawVal; })[0];
        if (match) display = match.label;
      }
      renderDisplay(cell, display, rawVal);
      restoreAffordance(cell);
      flashSaved(cell);
      toast('success', 'Atualizado');
    }).catch(function () {
      cell.classList.remove('ch-cell--saving');
      toast('error', 'Falha de conexão ao salvar');
      restore(cell);
    });
  }

  function restoreAffordance(cell) {
    activeCell = null;
  }

  function restore(cell) {
    // Re-renderiza o valor atual a partir de data-value (cancelar / no-op / erro)
    var field = cell.getAttribute('data-field');
    var raw = cell.getAttribute('data-value') || '';
    if (field === 'status') {
      var opts = parseOptions(cell.getAttribute('data-options'));
      var match = opts.filter(function (o) { return o.value === raw; })[0];
      renderDisplay(cell, match ? match.label : raw, raw);
    } else if (cell.getAttribute('data-type') === 'date') {
      renderDisplay(cell, raw ? formatBrDate(raw) : '—', raw);
    } else {
      renderDisplay(cell, raw, raw);
    }
    restoreAffordance(cell);
    cell.focus();
  }

  function formatBrDate(iso) {
    // "2026-05-29" → "29/05/2026"
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
    return m ? (m[3] + '/' + m[2] + '/' + m[1]) : iso;
  }

  function beginEdit(cell) {
    if (activeCell) return; // uma edição por vez
    if (cell.classList.contains('ch-cell--saving')) return;

    // Trava de prazo no front (backend reforça com 403)
    if (cell.getAttribute('data-deadline') === '1' && !canEditDeadlines) {
      toast('warning', 'Apenas administradores e advogados podem alterar prazos.');
      return;
    }

    activeCell = cell;
    var type = cell.getAttribute('data-type') || 'text';
    var value = cell.getAttribute('data-value') || '';
    var editor;

    if (type === 'select') {
      editor = document.createElement('select');
      editor.className = 'ch-cell-editor';
      parseOptions(cell.getAttribute('data-options')).forEach(function (o) {
        var opt = document.createElement('option');
        opt.value = o.value;
        opt.textContent = o.label;
        if (o.value === value) opt.selected = true;
        editor.appendChild(opt);
      });
    } else {
      editor = document.createElement('input');
      editor.className = 'ch-cell-editor';
      editor.type = (type === 'date') ? 'date' : 'text';
      editor.value = value;
    }

    cell.innerHTML = '';
    cell.appendChild(editor);
    editor.focus();
    if (editor.select) { try { editor.select(); } catch (e) {} }

    var finished = false;
    function done(save) {
      if (finished) return;
      finished = true;
      var v = editor.value;
      if (save) commit(cell, v);
      else restore(cell);
    }

    if (type === 'select') {
      editor.addEventListener('change', function () { done(true); });
      editor.addEventListener('blur', function () { done(false); });
    } else {
      editor.addEventListener('blur', function () { done(true); });
    }
    editor.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); done(true); }
      else if (e.key === 'Escape') { e.preventDefault(); done(false); }
    });
  }

  // Delegação de eventos no tbody
  table.addEventListener('click', function (e) {
    var cell = e.target.closest('.ch-cell[role="button"]');
    if (cell && table.contains(cell)) beginEdit(cell);
  });
  table.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    var cell = e.target.closest('.ch-cell[role="button"]');
    if (cell && cell === document.activeElement) {
      e.preventDefault();
      beginEdit(cell);
    }
  });
})();
