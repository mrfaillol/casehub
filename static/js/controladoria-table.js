/**
 * CaseHub Lite — Controladoria Table (Asana-style)
 * Inline editing, dropdowns, bulk actions, sorting
 */
(function() {
    var PREFIX = window.CASEHUB_PREFIX || '/casehub';

    // ── Inline Editing ──────────────────────────────────────────
    document.addEventListener('click', function(e) {
        var cell = e.target.closest('td.editable');
        if (!cell || cell.classList.contains('editing')) return;
        if (cell.querySelector('input, select')) return;

        var field = cell.dataset.field;
        var prazoId = cell.dataset.prazoId;
        if (!field || !prazoId) return;

        // Status: cycle on click
        if (field === 'status') {
            cycleStatus(cell, prazoId);
            return;
        }

        // Responsavel: user dropdown
        if (field === 'assigned_to' || field === 'responsavel') {
            openUserDropdown(cell, prazoId);
            return;
        }

        // Tipo peticao: select dropdown (BUG-R2)
        if (field === 'tipo_peticao') {
            openTipoPeticaoEdit(cell, prazoId);
            return;
        }

        // Text fields: inline input
        openTextEdit(cell, field, prazoId);
    });

    function cycleStatus(cell, prazoId) {
        var order = ['pendente', 'em_andamento', 'concluido'];
        var labels = { pendente: 'Pendente', em_andamento: 'Em Andamento', concluido: 'Concluido' };
        var row = cell.closest('tr');
        var current = row ? row.dataset.status : 'pendente';
        var idx = order.indexOf(current);
        var next = order[(idx + 1) % order.length];

        saveField(prazoId, 'status', next, function() {
            if (row) row.dataset.status = next;
            var dot = cell.querySelector('.status-dot');
            if (dot) { dot.className = 'status-dot status-dot--' + next; }
            var label = cell.querySelector('.status-label');
            if (label) label.textContent = labels[next] || next;
            flashCell(cell);
            // Update row urgency class if needed (no page reload)
            var urgClasses = ['urg-vermelho','urg-amarelo','urg-verde','urg-concluido'];
            if (next === 'concluido') {
                urgClasses.forEach(function(c) { row.classList.remove(c); });
                row.classList.add('urg-concluido');
                // Open tipo_peticao modal
                window.abrirModalConcluir(parseInt(row.dataset.prazoId));
            }
        });
    }

    function openTextEdit(cell, field, prazoId) {
        var original = cell.textContent.trim();
        var raw = cell.dataset.rawValue !== undefined ? cell.dataset.rawValue : original;
        cell.classList.add('editing');

        var input = document.createElement('input');
        // R11: Use date picker for date fields
        var dateFields = ['data_inicio', 'data_intimacao', 'data_vencimento'];
        if (dateFields.indexOf(field) >= 0) {
            input.type = 'date';
            // Try to parse DD/MM to YYYY-MM-DD for the date input
            var parts = original.split('/');
            if (parts.length === 2) {
                var year = new Date().getFullYear();
                input.value = year + '-' + parts[1].padStart(2, '0') + '-' + parts[0].padStart(2, '0');
            } else if (raw && raw.match(/^\d{4}-\d{2}-\d{2}$/)) {
                input.value = raw;
            }
        } else {
            input.type = 'text';
            input.value = raw;
        }
        input.className = 'ctrl-inline-input';
        input.style.cssText = 'width:100%;border:none;outline:none;font:inherit;color:inherit;background:transparent;padding:0;margin:0;';

        cell.textContent = '';
        cell.appendChild(input);
        input.focus();
        input.select();

        function finish() {
            var val = input.value.trim();
            cell.classList.remove('editing');
            if (val !== raw && val !== original) {
                saveField(prazoId, field, val, function() {
                    cell.textContent = val || original;
                    if (cell.dataset.rawValue !== undefined) cell.dataset.rawValue = val;
                    flashCell(cell);
                });
            } else {
                cell.textContent = original;
            }
        }

        input.addEventListener('blur', finish);
        input.addEventListener('keydown', function(ev) {
            if (ev.key === 'Enter') { ev.preventDefault(); input.blur(); }
            if (ev.key === 'Escape') { input.value = raw; input.blur(); }
        });
    }

    function openUserDropdown(cell, prazoId) {
        var usersData = window.ORG_USERS || [];
        if (!usersData.length) {
            openTextEdit(cell, 'responsavel', prazoId);
            return;
        }

        cell.classList.add('editing');
        var select = document.createElement('select');
        select.className = 'ctrl-inline-input ctrl-inline-select';
        select.style.cssText = 'width:100%;border:none;outline:none;font:inherit;color:inherit;background:transparent;padding:0;color-scheme:inherit;';

        var opt0 = document.createElement('option');
        opt0.value = '';
        opt0.textContent = '— Sem responsavel —';
        select.appendChild(opt0);

        usersData.forEach(function(u) {
            var opt = document.createElement('option');
            opt.value = u.name;
            opt.textContent = u.name;
            select.appendChild(opt);
        });

        var original = cell.textContent.trim();
        cell.textContent = '';
        cell.appendChild(select);
        select.focus();

        function finish() {
            var val = select.value;
            cell.classList.remove('editing');
            if (val && val !== original) {
                saveField(prazoId, 'responsavel', val, function() {
                    var user = usersData.find(function(u) { return u.name === val; });
                    var initials = user ? user.initials : val.split(' ').map(function(w){return w[0]}).join('').toUpperCase().slice(0,2);
                    cell.innerHTML = '<div class="assignee-cell"><div class="assignee-avatar">' + initials + '</div><span>' + val + '</span></div>';
                    flashCell(cell);
                });
            } else {
                cell.innerHTML = original ? '<div class="assignee-cell"><div class="assignee-avatar">?</div><span>' + original + '</span></div>' : '<span style="color:#94a3b8">Atribuir</span>';
            }
        }

        select.addEventListener('blur', finish);
        select.addEventListener('change', function() { select.blur(); });
    }

    function saveField(prazoId, field, value, onSuccess) {
        fetch(PREFIX + '/controladoria/' + prazoId + '/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ field: field, value: value })
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.success) { onSuccess(); }
            else { showToast('Erro: ' + (data.error || 'falha'), 'error'); }
        })
        .catch(function() { showToast('Erro de conexao', 'error'); });
    }

    function flashCell(cell) {
        cell.style.transition = 'background 0.3s';
        cell.style.background = 'rgba(34,197,94,0.15)';
        setTimeout(function() { cell.style.background = ''; }, 800);
    }

    // ── Dropdown Actions (⋯) ────────────────────────────────────
    document.addEventListener('click', function(e) {
        // Close all open dropdowns
        document.querySelectorAll('.ctrl-dropdown.is-open').forEach(function(d) {
            if (!d.contains(e.target)) d.classList.remove('is-open');
        });
        // Toggle
        var trigger = e.target.closest('.ctrl-dropdown-trigger');
        if (trigger) {
            e.stopPropagation();
            trigger.closest('.ctrl-dropdown').classList.toggle('is-open');
        }
        // Action click
        var action = e.target.closest('[data-action]');
        if (action) {
            var name = action.dataset.action;
            var id = parseInt(action.closest('.ctrl-dropdown').dataset.prazoId);
            action.closest('.ctrl-dropdown').classList.remove('is-open');
            handleAction(name, id);
        }
    });

    function handleAction(name, id) {
        if (name === 'editar') {
            var row = document.querySelector('tr[data-prazo-id="' + id + '"]');
            if (row) { var ed = row.querySelector('td.editable'); if (ed) ed.click(); }
        }
        else if (name === 'duplicar') { apiPost('/' + id + '/duplicar', {}, 'Duplicado'); }
        else if (name === 'concluir') { abrirModalConcluir(id); }
        else if (name === 'mover-cima') { moveRow(id, 'up'); }
        else if (name === 'mover-baixo') { moveRow(id, 'down'); }
        else if (name === 'excluir') {
            if (confirm('Excluir este prazo?')) { apiPost('/' + id + '/excluir', {}, 'Excluido'); }
        }
    }

    function apiPost(path, body, successMsg) {
        fetch(PREFIX + '/controladoria' + path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.success || d.new_id) {
                showToast(successMsg, 'success');
                setTimeout(function() { location.reload(); }, 600);
            } else { showToast('Erro', 'error'); }
        })
        .catch(function() { showToast('Erro de conexao', 'error'); });
    }

    function moveRow(id, dir) {
        var row = document.querySelector('tr[data-prazo-id="' + id + '"]');
        if (!row) return;
        var sib = dir === 'up' ? row.previousElementSibling : row.nextElementSibling;
        if (!sib || !sib.dataset.prazoId) return;
        if (dir === 'up') row.parentNode.insertBefore(row, sib);
        else row.parentNode.insertBefore(sib, row);
        flashCell(row.querySelector('td'));
    }

    // ── Checkboxes + Bulk ───────────────────────────────────────
    var checkAll = document.getElementById('ctrl-check-all');
    var bulkBar = document.getElementById('ctrl-bulk');
    var bulkCount = document.getElementById('ctrl-bulk-count');

    if (checkAll) {
        checkAll.addEventListener('change', function() {
            document.querySelectorAll('.ctrl-row-check').forEach(function(cb) {
                cb.checked = checkAll.checked;
            });
            refreshBulk();
        });
    }

    document.addEventListener('change', function(e) {
        if (e.target.classList.contains('ctrl-row-check')) refreshBulk();
    });

    function refreshBulk() {
        var checked = document.querySelectorAll('.ctrl-row-check:checked');
        var n = checked.length;
        if (bulkBar) bulkBar.classList.toggle('is-visible', n > 0);
        if (bulkCount) bulkCount.textContent = n + ' selecionado' + (n !== 1 ? 's' : '');
        var total = document.querySelectorAll('.ctrl-row-check').length;
        if (checkAll) {
            checkAll.checked = n > 0 && n === total;
            checkAll.indeterminate = n > 0 && n < total;
        }
    }

    var deselectBtn = document.getElementById('ctrl-deselect');
    if (deselectBtn) {
        deselectBtn.addEventListener('click', function() {
            if (checkAll) checkAll.checked = false;
            document.querySelectorAll('.ctrl-row-check').forEach(function(cb) { cb.checked = false; });
            refreshBulk();
        });
    }

    // Bulk actions (global functions for onclick)
    window.bulkConcluir = function() {
        var ids = getSelectedIds();
        if (!ids.length) return;
        if (!confirm('Concluir ' + ids.length + ' prazo(s)?')) return;
        fetch(PREFIX + '/controladoria/bulk-concluir', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: ids })
        }).then(function(r) { return r.json(); }).then(function(d) {
            if (d.success) { showToast(d.updated + ' concluido(s)', 'success'); setTimeout(function() { location.reload(); }, 600); }
        });
    };

    window.bulkExcluir = function() {
        var ids = getSelectedIds();
        if (!ids.length) return;
        if (!confirm('Excluir ' + ids.length + ' prazo(s)?')) return;
        fetch(PREFIX + '/controladoria/bulk-excluir', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: ids })
        }).then(function(r) { return r.json(); }).then(function(d) {
            if (d.success) { showToast(d.deleted + ' excluido(s)', 'success'); setTimeout(function() { location.reload(); }, 600); }
        });
    };

    function getSelectedIds() {
        return Array.from(document.querySelectorAll('.ctrl-row-check:checked')).map(function(cb) {
            return parseInt(cb.closest('tr').dataset.prazoId);
        });
    }

    // ── Sorting ─────────────────────────────────────────────────
    var sortAsc = true;
    var currentSortKey = 'Vencimento';

    function doSort(key) {
        var tbody = document.querySelector('.ctrl-table tbody');
        if (!tbody) return;

        if (currentSortKey === key) { sortAsc = !sortAsc; }
        else { currentSortKey = key; sortAsc = true; }

        // Update active state on pills AND headers
        document.querySelectorAll('.prazo-sort-btn').forEach(function(b) { b.classList.toggle('is-active', b.dataset.sort === key); });
        document.querySelectorAll('.sortable-th').forEach(function(h) { h.classList.toggle('is-active', h.dataset.sort === key); });

        var rows = Array.from(tbody.querySelectorAll('tr[data-prazo-id]'));
        rows.sort(function(a, b) {
            var va = a.dataset['sort' + key] || '';
            var vb = b.dataset['sort' + key] || '';
            // Dates (YYYY-MM-DD) must compare as strings, not numbers
            var isDate = va.length === 10 && va[4] === '-' && va[7] === '-';
            if (!isDate) {
                var na = parseFloat(va), nb = parseFloat(vb);
                if (!isNaN(na) && !isNaN(nb)) return sortAsc ? na - nb : nb - na;
            }
            return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
        });
        rows.forEach(function(r) { tbody.appendChild(r); });
    }

    window.sortPrazos = function(btn) { doSort(btn.dataset.sort); };

    // Headers clicáveis
    document.querySelectorAll('.sortable-th').forEach(function(th) {
        th.addEventListener('click', function() { doSort(th.dataset.sort); });
    });

    // ── Toast ───────────────────────────────────────────────────
    function showToast(msg, type) {
        var el = document.createElement('div');
        el.className = 'ctrl-toast ctrl-toast--' + (type || 'info');
        el.textContent = msg;
        document.body.appendChild(el);
        requestAnimationFrame(function() { el.classList.add('is-visible'); });
        setTimeout(function() {
            el.classList.remove('is-visible');
            setTimeout(function() { el.remove(); }, 300);
        }, 2500);
    }
    window.showToast = showToast;

    // I1: Edit tipo_peticao via badge click (global function for onclick)
    window.editTipoPeticao = function(badge) {
        var prazoId = badge.dataset.prazoId;
        var original = badge.textContent.trim();
        var select = document.createElement('select');
        select.className = 'ctrl-inline-input ctrl-inline-select';
        select.style.cssText = 'font-size:11px;padding:2px 4px;border:1px solid var(--line,#7c3aed);border-radius:4px;background:var(--surface-card,var(--bg-surface,#fff));color:var(--fg-default,#1f2937);color-scheme:inherit;';
        var tipos = ['Pet. Simples','Impugnacao ou decote RPV','Manif. Laudo/Quesitos',
            'Informa pericia ou audiencia','Pet. Complexa','Defesas','Replicas','Recursos','Contrarrazoes','Outros'];
        tipos.forEach(function(t) {
            var opt = document.createElement('option');
            opt.value = t; opt.textContent = t;
            if (t === original) opt.selected = true;
            select.appendChild(opt);
        });
        badge.textContent = '';
        badge.appendChild(select);
        select.focus();
        function finish() {
            var val = select.value;
            if (val && val !== original) {
                saveField(prazoId, 'tipo_peticao', val, function() {
                    badge.textContent = val;
                    flashCell(badge);
                });
            } else {
                badge.textContent = original;
            }
        }
        select.addEventListener('blur', finish);
        select.addEventListener('change', function() { select.blur(); });
    };

    // ── Botão ✓ Concluir inline (P7) ──────────────────────────
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('.btn-concluir-inline');
        if (btn) {
            e.stopPropagation();
            abrirModalConcluir(btn.dataset.prazoId);
        }
    });

    // ── Editar tipo_peticao em concluídos (BUG-R2) ────────────
    function openTipoPeticaoEdit(cell, prazoId) {
        var original = cell.textContent.trim();
        cell.classList.add('editing');
        var select = document.createElement('select');
        select.className = 'ctrl-inline-input ctrl-inline-select';
        select.style.cssText = 'width:100%;border:1px solid var(--line,#d1d5db);border-radius:4px;font:inherit;padding:2px 4px;background:var(--surface-card,var(--bg-surface,#fff));color:var(--fg-default,#1f2937);color-scheme:inherit;';
        var tipos = ['Pet. Simples','Impugnacao ou decote RPV','Manif. Laudo/Quesitos',
            'Informa pericia ou audiencia','Pet. Complexa','Defesas','Replicas','Recursos','Contrarrazoes','Outros'];
        tipos.forEach(function(t) {
            var opt = document.createElement('option');
            opt.value = t; opt.textContent = t;
            if (t === original) opt.selected = true;
            select.appendChild(opt);
        });
        cell.textContent = '';
        cell.appendChild(select);
        select.focus();
        function finish() {
            var val = select.value;
            cell.classList.remove('editing');
            if (val && val !== original) {
                saveField(prazoId, 'tipo_peticao', val, function() {
                    cell.textContent = val;
                    flashCell(cell);
                });
            } else {
                cell.textContent = original;
            }
        }
        select.addEventListener('blur', finish);
        select.addEventListener('change', function() { select.blur(); });
    }

    // ── Reabrir prazo concluído (R12) ─────────────────────────
    document.addEventListener('click', function(e) {
        var btn = e.target.closest('.btn-reabrir-inline');
        if (btn) {
            e.stopPropagation();
            var prazoId = btn.dataset.prazoId;
            if (!confirm('Reabrir este prazo?')) return;
            saveField(prazoId, 'status', 'pendente', function() {
                showToast('Prazo reaberto', 'success');
                setTimeout(function() { location.reload(); }, 600);
            });
        }
    });

    // ── Modal Concluir (tipo de petição) ────────────────────────
    function abrirModalConcluir(prazoId) {
        document.getElementById('concluirPrazoId').value = prazoId;
        document.getElementById('concluirTipoPeticao').value = 'Pet. Simples';
        // Guard against missing element / bundle — see #207.
        var concluirEl = document.getElementById('modalConcluirPrazo');
        if (typeof bootstrap === 'undefined' || !bootstrap.Modal || !concluirEl) return;
        var modal = bootstrap.Modal.getOrCreateInstance(concluirEl);
        modal.show();
    }
    window.abrirModalConcluir = abrirModalConcluir;

    window.confirmarConclusao = function() {
        var prazoId = document.getElementById('concluirPrazoId').value;
        var tipo = document.getElementById('concluirTipoPeticao').value;
        var concluirEl = document.getElementById('modalConcluirPrazo');
        var modal = (typeof bootstrap !== 'undefined' && bootstrap.Modal && concluirEl) ? bootstrap.Modal.getInstance(concluirEl) : null;
        if (modal) modal.hide();
        apiPost('/' + prazoId + '/concluir', { tipo_peticao: tipo }, 'Concluido como ' + tipo);
    };

    // ── Modal Descrição (igual Lovable) ─────────────────────────
    window.abrirModalDescricao = function(cell) {
        var prazoId = cell.dataset.prazoId;
        var rawValue = cell.dataset.rawValue || cell.textContent.trim();
        document.getElementById('descPrazoId').value = prazoId;
        document.getElementById('descTexto').value = rawValue;
        // Guard against missing element / bundle — see #207.
        var descEl = document.getElementById('modalDescricao');
        if (typeof bootstrap === 'undefined' || !bootstrap.Modal || !descEl) return;
        var modal = bootstrap.Modal.getOrCreateInstance(descEl);
        modal.show();
        // Focus textarea after modal opens
        descEl.addEventListener('shown.bs.modal', function() {
            document.getElementById('descTexto').focus();
        }, { once: true });
    };

    window.salvarDescricao = function() {
        var prazoId = document.getElementById('descPrazoId').value;
        var texto = document.getElementById('descTexto').value.trim();
        var descEl = document.getElementById('modalDescricao');
        var modal = (typeof bootstrap !== 'undefined' && bootstrap.Modal && descEl) ? bootstrap.Modal.getInstance(descEl) : null;
        if (modal) modal.hide();
        saveField(prazoId, 'descricao', texto, function() {
            // Update the cell in the table
            var cell = document.querySelector('td.desc-cell[data-prazo-id="' + prazoId + '"]');
            if (cell) {
                cell.dataset.rawValue = texto;
                cell.textContent = texto.length > 60 ? texto.substring(0, 60) + '...' : texto;
                flashCell(cell);
            }
            showToast('Descricao salva', 'success');
        });
    };

    // ── Toggle Layout (estático / widget) ───────────────────────
    window.toggleLayoutMode = function() {
        var grid = document.getElementById('ctrl-grid');
        if (!grid) return;
        var isLocked = grid.classList.contains('grid-locked');
        if (isLocked) {
            // Unlock → enable Gridstack
            grid.classList.remove('grid-locked');
            if (window.ctrlGrid) {
                window.ctrlGrid.enableMove(true);
                window.ctrlGrid.enableResize(true);
            }
            document.querySelectorAll('.gs-widget-header .gs-grip').forEach(function(g) { g.style.display = ''; });
            var btn = document.getElementById('toggleLayoutBtn');
            if (btn) { btn.textContent = 'Travar Layout'; btn.title = 'Travar posicao dos widgets'; }
            showToast('Layout destravado — arraste os widgets', 'info');
        } else {
            // Lock → disable Gridstack
            grid.classList.add('grid-locked');
            if (window.ctrlGrid) {
                window.ctrlGrid.enableMove(false);
                window.ctrlGrid.enableResize(false);
            }
            document.querySelectorAll('.gs-widget-header .gs-grip').forEach(function(g) { g.style.display = 'none'; });
            var btn = document.getElementById('toggleLayoutBtn');
            if (btn) { btn.textContent = 'Editar Layout'; btn.title = 'Destravar para mover widgets'; }
            showToast('Layout travado', 'info');
        }
        localStorage.setItem('ctrl-layout-locked', isLocked ? 'false' : 'true');
    };

    function lockControladoriaGrid() {
        var shouldLock = localStorage.getItem('ctrl-layout-locked');
        if (shouldLock === null || shouldLock === 'true') {
            var grid = document.getElementById('ctrl-grid');
            if (grid) {
                grid.classList.add('grid-locked');
                // Delay to let Gridstack init first
                setTimeout(function() {
                    if (window.ctrlGrid) {
                        window.ctrlGrid.enableMove(false);
                        window.ctrlGrid.enableResize(false);
                    }
                    document.querySelectorAll('.gs-widget-header .gs-grip').forEach(function(g) { g.style.display = 'none'; });
                }, 500);
            }
        }
    }

    // Auto-lock on page load (default: locked for cleaner view)
    document.addEventListener('DOMContentLoaded', lockControladoriaGrid);
    document.addEventListener('casehub:soft-navigation', lockControladoriaGrid);

})();
