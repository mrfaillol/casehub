/* ============================================================
   whatsapp-crm.js — WhatsApp Web clone Tier-3 power-features (WS-D).

   The "Chrome-extension layer" on top of the chat clone. This file is
   LOADED ALONGSIDE chat.js but never edits it: it only reads the globals
   chat.js already publishes (WA_API_BASE, CASEHUB_PREFIX) and drives two
   new surfaces fetched as HTML fragments from routes/whatsapp_crm.py:

     * the CRM contact-info side panel  (<prefix>/crm/contact-panel/{phone})
     * the lead pipeline / funnel kanban (<prefix>/crm/pipeline)

   All endpoints live under WA_API_BASE (= PREFIX + page-router prefix),
   exactly like chat.js. AI-assist results are EPHEMERAL — rendered into
   the DOM only, never persisted.

   No build step: plain ES, no imports. Guarded so a missing mount point
   degrades silently (chat.js owns the page; this is additive).
   ============================================================ */
(function () {
  'use strict';

  // --- API base ------------------------------------------------------------
  // Reuse the exact base chat.html injects for chat.js. Fall back defensively
  // so the module never throws if loaded before chat.html's inline script.
  var API_BASE =
    (typeof window.WA_API_BASE === 'string' && window.WA_API_BASE) ||
    ((typeof window.CASEHUB_PREFIX === 'string' ? window.CASEHUB_PREFIX : '') +
      '/whatsapp-chat');
  var PREFIX =
    typeof window.CASEHUB_PREFIX === 'string' ? window.CASEHUB_PREFIX : '';

  // --- small DOM / fetch helpers ------------------------------------------
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function api(path) { return API_BASE + path; }

  function getJSON(path) {
    return fetch(api(path), { headers: { Accept: 'application/json' } })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      });
  }

  function postJSON(path, body) {
    return fetch(api(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body || {}),
    }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function getHTML(path) {
    return fetch(api(path), { headers: { Accept: 'text/html' } })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.text();
      });
  }

  function escapeHTML(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function fmtRelative(iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '—';
    var diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return 'agora';
    if (diff < 3600) return Math.floor(diff / 60) + ' min';
    if (diff < 86400) return Math.floor(diff / 3600) + ' h';
    if (diff < 172800) return 'ontem';
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' });
  }

  function fmtDate(iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '—';
    return d.toLocaleDateString('pt-BR', {
      day: '2-digit', month: 'short', year: 'numeric',
    });
  }

  function toast(msg, kind) {
    // Reuse chat.js's toast if present; otherwise a minimal inline fallback.
    if (typeof window.showToast === 'function') {
      window.showToast(msg, kind);
      return;
    }
    var el = document.createElement('div');
    el.className = 'wac-toast wac-toast--' + (kind || 'info');
    el.setAttribute('role', 'status');
    el.textContent = msg;
    document.body.appendChild(el);
    requestAnimationFrame(function () { el.classList.add('is-shown'); });
    setTimeout(function () {
      el.classList.remove('is-shown');
      setTimeout(function () { el.remove(); }, 220);
    }, 2600);
  }

  // ========================================================================
  // CRM CONTACT PANEL
  // ========================================================================
  var Panel = {
    el: null,        // the .wac-panel root once loaded
    host: null,      // the container the panel is mounted into
    phone: null,     // currently displayed phone
    contact: null,   // last contact CRM payload

    /* Mount/refresh the panel fragment for a phone into `host`. */
    open: function (phone, host) {
      if (!phone) return;
      this.host = host || this.host || $('#wacPanelHost');
      if (!this.host) return;
      this.phone = phone;
      var self = this;
      this.host.hidden = false;
      this.host.classList.add('wac-panel-host', 'is-loading');
      getHTML('/crm/contact-panel/' + encodeURIComponent(phone))
        .then(function (html) {
          self.host.innerHTML = html;
          self.host.classList.remove('is-loading');
          self.el = $('.wac-panel', self.host);
          self.bind();
          self.hydrate();
        })
        .catch(function (err) {
          self.host.classList.remove('is-loading');
          self.host.innerHTML =
            '<div class="wac-panel wac-panel--error">' +
            '<p class="wac-empty">Não foi possível carregar o painel CRM.</p>' +
            '</div>';
          console.warn('[wa-crm] contact-panel load failed:', err);
        });
    },

    close: function () {
      if (this.host) {
        this.host.hidden = true;
        this.host.classList.remove('wac-panel-host', 'is-loading');
      }
    },

    /* Wire every interactive control inside the freshly-loaded fragment. */
    bind: function () {
      if (!this.el) return;
      var self = this;
      var phone = this.phone;

      $all('[data-wac-close]', this.el).forEach(function (b) {
        b.addEventListener('click', function () { self.close(); });
      });

      // Lead-stage radio group ------------------------------------------------
      $all('[data-wac-stage]', this.el).forEach(function (btn) {
        btn.addEventListener('click', function () {
          var stage = btn.getAttribute('data-wac-stage');
          self.setStage(stage, btn);
        });
      });

      // Owner (dono do contato) ----------------------------------------------
      var ownerSel = $('#wacOwner', this.el);
      if (ownerSel) {
        var current = ownerSel.getAttribute('data-current') || '';
        getJSON('/api/crm/org-users')
          .then(function (res) {
            var users = (res && res.users) || [];
            users.forEach(function (u) {
              var opt = document.createElement('option');
              opt.value = String(u.id);
              opt.textContent = u.name;
              if (String(u.id) === String(current)) opt.selected = true;
              ownerSel.appendChild(opt);
            });
          })
          .catch(function () { /* dropdown keeps just the "Sem dono" option */ });
        ownerSel.addEventListener('change', function () {
          self.setOwner(ownerSel.value);
        });
      }

      // Notes ----------------------------------------------------------------
      self.loadNotes();
      var noteForm = $('#wacNoteForm', this.el);
      if (noteForm) {
        noteForm.addEventListener('submit', function (ev) {
          ev.preventDefault();
          var input = $('#wacNoteInput', self.el);
          var text = input ? input.value.trim() : '';
          if (text) { self.addNote(text); if (input) input.value = ''; }
        });
      }

      // Follow-up + duplicate check ------------------------------------------
      var fuSave = $('#wacFollowUpSave', this.el);
      var fuClear = $('#wacFollowUpClear', this.el);
      if (fuSave) fuSave.addEventListener('click', function () { self.saveFollowUp(false); });
      if (fuClear) fuClear.addEventListener('click', function () { self.saveFollowUp(true); });
      self.checkDuplicates();

      // Link client ----------------------------------------------------------
      var openLink = $('[data-wac-open-link]', this.el);
      var picker = $('#wacClientPicker', this.el);
      var search = $('#wacClientSearch', this.el);
      var results = $('#wacClientResults', this.el);
      if (openLink && picker) {
        openLink.addEventListener('click', function () {
          picker.hidden = false;
          if (search) search.focus();
        });
      }
      if (search && results) {
        var debounce;
        search.addEventListener('input', function () {
          clearTimeout(debounce);
          debounce = setTimeout(function () {
            self.searchClients(search.value, results);
          }, 220);
        });
      }
      var unlink = $('[data-wac-unlink]', this.el);
      if (unlink) {
        unlink.addEventListener('click', function () { self.linkClient(null); });
      }

      // Tags -----------------------------------------------------------------
      $all('[data-wac-tag-remove]', this.el).forEach(function (b) {
        b.addEventListener('click', function () {
          self.removeTag(b.getAttribute('data-wac-tag-remove'));
        });
      });
      var tagForm = $('#wacTagForm', this.el);
      if (tagForm) {
        tagForm.addEventListener('submit', function (ev) {
          ev.preventDefault();
          var input = $('#wacTagInput', self.el);
          if (input && input.value.trim()) {
            self.addTag(input.value.trim());
            input.value = '';
          }
        });
      }

      // Automation toggles ---------------------------------------------------
      var botSwitch = $('#wacBotSwitch', this.el);
      var takeoverSwitch = $('#wacTakeoverSwitch', this.el);
      if (botSwitch) {
        botSwitch.addEventListener('click', function () {
          self.toggleSwitch(botSwitch);
          self.saveBotSettings();
        });
      }
      if (takeoverSwitch) {
        takeoverSwitch.addEventListener('click', function () {
          self.toggleSwitch(takeoverSwitch);
          self.saveBotSettings();
        });
      }
      var followBtn = $('#wacFollowupBtn', this.el);
      if (followBtn) {
        followBtn.addEventListener('click', function () {
          // Follow-up flagging is handled by chat.js's followup endpoints;
          // surface it cooperatively without owning that state.
          if (typeof window.markForFollowup === 'function') {
            window.markForFollowup(phone).catch(function () {
              toast('Erro ao marcar follow-up.', 'error');
            });
          } else {
            fetch((window.WA_API_BASE || '') + '/api/followup/mark', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ phone: phone })
            }).then(function (resp) {
              if (!resp.ok) throw new Error('followup failed');
              toast('Contato marcado para follow-up.', 'success');
            }).catch(function () {
              toast('Erro ao marcar follow-up.', 'error');
            });
          }
        });
      }

      // AI assist (ephemeral) ------------------------------------------------
      var aiSuggest = $('#wacAiSuggest', this.el);
      var aiSummary = $('#wacAiSummary', this.el);
      if (aiSuggest) {
        aiSuggest.addEventListener('click', function () {
          self.runAI('suggest', aiSuggest);
        });
      }
      if (aiSummary) {
        aiSummary.addEventListener('click', function () {
          self.runAI('summary', aiSummary);
        });
      }
    },

    /* Format the date <dd> stats once the fragment is in the DOM. */
    hydrate: function () {
      if (!this.el) return;
      var first = $('#wacFirstContact', this.el);
      var last = $('#wacLastMsg', this.el);
      if (first) first.textContent = fmtDate(first.getAttribute('data-iso'));
      if (last) last.textContent = fmtRelative(last.getAttribute('data-iso'));
    },

    toggleSwitch: function (sw) {
      var on = !sw.classList.contains('is-on');
      sw.classList.toggle('is-on', on);
      sw.setAttribute('aria-checked', on ? 'true' : 'false');
    },

    setStage: function (stage, btn) {
      var self = this;
      postJSON('/api/crm/stage/' + encodeURIComponent(this.phone), { stage: stage })
        .then(function (res) {
          $all('[data-wac-stage]', self.el).forEach(function (b) {
            var active = b === btn;
            b.classList.toggle('is-active', active);
            b.setAttribute('aria-checked', active ? 'true' : 'false');
          });
          if (self.el) self.el.setAttribute('data-stage', res.stage || stage);
          toast('Estágio atualizado: ' + (res.stage || stage), 'success');
          // Keep the pipeline in sync if it is open.
          if (Pipeline.el) Pipeline.load();
        })
        .catch(function () { toast('Falha ao mudar estágio.', 'error'); });
    },

    setOwner: function (ownerUserId) {
      var self = this;
      var payload = { owner_user_id: ownerUserId ? parseInt(ownerUserId, 10) : null };
      postJSON('/api/crm/owner/' + encodeURIComponent(this.phone), payload)
        .then(function (res) {
          var owner = res && res.owner;
          var badge = $('#wacOwnerBadge', self.el);
          if (badge) {
            badge.textContent = owner ? owner.name : '';
            badge.style.background = owner ? (owner.color || '') : '';
          }
          toast(owner ? ('Dono: ' + owner.name) : 'Dono removido.', 'success');
          // Reflect in the sidebar + open-chat header without a full reload.
          if (typeof window.applyCrmOwner === 'function') {
            window.applyCrmOwner(self.phone, owner);
          }
          if (Pipeline.el) Pipeline.load();
        })
        .catch(function () { toast('Falha ao definir dono.', 'error'); });
    },

    loadNotes: function () {
      var self = this;
      getJSON('/api/crm/notes/' + encodeURIComponent(this.phone))
        .then(function (res) { self.renderNotes((res && res.notes) || []); })
        .catch(function () {});
    },

    renderNotes: function (notes) {
      var list = $('#wacNotes', this.el);
      if (!list) return;
      var self = this;
      list.innerHTML = '';
      if (!notes.length) {
        var empty = document.createElement('li');
        empty.className = 'wac-empty wac-empty--sm';
        empty.textContent = 'Sem notas ainda.';
        list.appendChild(empty);
        return;
      }
      notes.forEach(function (n) {
        var li = document.createElement('li');
        li.className = 'wac-note';
        var del = document.createElement('button');
        del.type = 'button';
        del.className = 'wac-note__del';
        del.setAttribute('aria-label', 'Excluir nota');
        del.textContent = '×';
        del.addEventListener('click', function () { self.deleteNote(n.id); });
        var body = document.createElement('div');
        body.className = 'wac-note__body';
        body.textContent = n.body || '';            // textContent => no XSS
        var meta = document.createElement('div');
        meta.className = 'wac-note__meta';
        meta.textContent = (n.author_name || 'Equipe') + ' · ' + fmtRelative(n.created_at);
        li.appendChild(del); li.appendChild(body); li.appendChild(meta);
        list.appendChild(li);
      });
    },

    addNote: function (body) {
      var self = this;
      postJSON('/api/crm/notes/' + encodeURIComponent(this.phone), { body: body })
        .then(function (res) {
          if (res && res.success) { self.loadNotes(); toast('Nota adicionada.', 'success'); }
          else { toast((res && res.error) || 'Falha ao adicionar nota.', 'error'); }
        })
        .catch(function () { toast('Falha ao adicionar nota.', 'error'); });
    },

    deleteNote: function (noteId) {
      var self = this;
      fetch(api('/api/crm/notes/' + encodeURIComponent(this.phone) + '/' + noteId),
            { method: 'DELETE', headers: { Accept: 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (res) { if (res && res.success) self.loadNotes(); })
        .catch(function () { toast('Falha ao excluir nota.', 'error'); });
    },

    saveFollowUp: function (clear) {
      var self = this;
      var dateEl = $('#wacFollowUpDate', this.el);
      var noteEl = $('#wacFollowUpNote', this.el);
      if (clear) {
        if (dateEl) dateEl.value = '';
        if (noteEl) noteEl.value = '';
      }
      var d = (dateEl && dateEl.value) ? dateEl.value : null;
      var note = noteEl ? noteEl.value : '';
      postJSON('/api/crm/follow-up/' + encodeURIComponent(this.phone), { date: d, note: note })
        .then(function (res) {
          if (res && res.success) toast(d ? ('Follow-up agendado para ' + d) : 'Follow-up removido.', 'success');
          else toast((res && res.error) || 'Falha ao agendar follow-up.', 'error');
        })
        .catch(function () { toast('Falha ao agendar follow-up.', 'error'); });
    },

    checkDuplicates: function () {
      var self = this;
      var box = $('#wacDupWarning', this.el);
      if (!box) return;
      getJSON('/api/crm/duplicates/' + encodeURIComponent(this.phone))
        .then(function (res) {
          var dups = (res && res.duplicates) || [];
          if (!dups.length) { box.hidden = true; return; }
          box.textContent = '⚠ Possível duplicata: ' + dups.map(function (d) {
            return d.display_name || d.phone;
          }).join(', ');           // textContent => no XSS
          box.hidden = false;
        })
        .catch(function () {});
    },

    searchClients: function (term, results) {
      results.innerHTML = '';
      var self = this;
      getJSON('/api/crm/clients?q=' + encodeURIComponent(term || ''))
        .then(function (rows) {
          if (!rows.length) {
            results.innerHTML =
              '<li class="wac-picker__empty">Nenhum cliente encontrado.</li>';
            return;
          }
          rows.forEach(function (c) {
            var li = document.createElement('li');
            li.className = 'wac-picker__item';
            li.setAttribute('role', 'option');
            li.setAttribute('tabindex', '0');
            li.innerHTML =
              '<span class="wac-picker__name">' + escapeHTML(c.name) + '</span>' +
              (c.email
                ? '<span class="wac-picker__sub">' + escapeHTML(c.email) + '</span>'
                : '');
            var pick = function () { self.linkClient(c.id); };
            li.addEventListener('click', pick);
            li.addEventListener('keydown', function (ev) {
              if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(); }
            });
            results.appendChild(li);
          });
        })
        .catch(function () {
          results.innerHTML =
            '<li class="wac-picker__empty">Erro ao buscar clientes.</li>';
        });
    },

    linkClient: function (clientId) {
      var self = this;
      postJSON('/api/crm/link/' + encodeURIComponent(this.phone), {
        client_id: clientId,
      })
        .then(function () {
          toast(clientId ? 'Cliente vinculado.' : 'Cliente desvinculado.', 'success');
          self.open(self.phone, self.host); // re-render fragment with new link
        })
        .catch(function () { toast('Falha ao vincular cliente.', 'error'); });
    },

    /* Read the current tag set from the rendered chips. */
    currentTags: function () {
      return $all('.wac-tag', this.el).map(function (t) {
        return t.getAttribute('data-tag');
      });
    },

    addTag: function (tag) {
      var tags = this.currentTags();
      if (tags.indexOf(tag) !== -1) return;
      tags.push(tag);
      this.saveTags(tags);
    },

    removeTag: function (tag) {
      var tags = this.currentTags().filter(function (t) { return t !== tag; });
      this.saveTags(tags);
    },

    saveTags: function (tags) {
      var self = this;
      postJSON('/api/crm/tags/' + encodeURIComponent(this.phone), { tags: tags })
        .then(function (res) { self.renderTags(res.tags || tags); })
        .catch(function () { toast('Falha ao salvar tags.', 'error'); });
    },

    renderTags: function (tags) {
      var box = $('#wacTags', this.el);
      if (!box) return;
      var self = this;
      box.innerHTML = '';
      tags.forEach(function (tag) {
        var span = document.createElement('span');
        span.className = 'wac-tag';
        span.setAttribute('data-tag', tag);
        span.innerHTML =
          escapeHTML(tag) +
          '<button type="button" class="wac-tag__remove" ' +
          'aria-label="Remover tag ' + escapeHTML(tag) + '">&times;</button>';
        span.querySelector('.wac-tag__remove').addEventListener('click', function () {
          self.removeTag(tag);
        });
        box.appendChild(span);
      });
    },

    saveBotSettings: function () {
      var botSwitch = $('#wacBotSwitch', this.el);
      var takeoverSwitch = $('#wacTakeoverSwitch', this.el);
      var botEnabled = botSwitch ? botSwitch.classList.contains('is-on') : true;
      var takeover = takeoverSwitch
        ? takeoverSwitch.classList.contains('is-on')
        : false;
      postJSON('/api/leads/' + encodeURIComponent(this.phone) + '/bot-settings', {
        bot_enabled: botEnabled,
        human_takeover: takeover,
        never_contact: takeover && !botEnabled,
      })
        .then(function () { toast('Automação atualizada.', 'success'); })
        .catch(function () { toast('Falha ao salvar automação.', 'error'); });
    },

    /* Ephemeral AI assist — render the live result, persist nothing. */
    runAI: function (kind, btn) {
      var out = $('#wacAiOut', this.el);
      if (!out) return;
      var self = this;
      var label = btn ? btn.textContent.trim() : '';
      if (btn) { btn.disabled = true; btn.classList.add('is-busy'); }
      out.hidden = false;
      out.classList.add('is-loading');
      out.innerHTML =
        '<span class="wac-spinner" aria-hidden="true"></span> Consultando IA…';

      var path = '/api/crm/ai/' + kind;
      postJSON(path, { phone: this.phone })
        .then(function (res) {
          var text = res.suggestion || res.summary || res.draft || null;
          out.classList.remove('is-loading');
          if (!text) {
            out.innerHTML =
              '<p class="wac-ai-out__empty">' +
              escapeHTML(res.error || 'Sem resultado da IA.') +
              '</p>';
            return;
          }
          out.innerHTML =
            '<p class="wac-ai-out__label">' + escapeHTML(label || 'IA') + '</p>' +
            '<div class="wac-ai-out__text">' + escapeHTML(text) + '</div>' +
            '<div class="wac-ai-out__actions">' +
            '<button type="button" class="wac-btn wac-btn--ghost wac-btn--sm" ' +
            'data-wac-ai-copy>Copiar</button>' +
            '<button type="button" class="wac-btn wac-btn--primary wac-btn--sm" ' +
            'data-wac-ai-use>Usar no campo</button>' +
            '</div>' +
            '<p class="wac-ai-out__note">Gerado ao vivo — nada é salvo.</p>';
          var copyBtn = $('[data-wac-ai-copy]', out);
          var useBtn = $('[data-wac-ai-use]', out);
          if (copyBtn) {
            copyBtn.addEventListener('click', function () {
              if (navigator.clipboard) {
                navigator.clipboard.writeText(text).then(function () {
                  toast('Copiado.', 'success');
                });
              }
            });
          }
          if (useBtn) {
            useBtn.addEventListener('click', function () { self.useInComposer(text); });
          }
        })
        .catch(function () {
          out.classList.remove('is-loading');
          out.innerHTML =
            '<p class="wac-ai-out__empty">Erro ao consultar a IA.</p>';
        })
        .finally(function () {
          if (btn) { btn.disabled = false; btn.classList.remove('is-busy'); }
        });
    },

    /* Drop AI text into the chat composer chat.js owns (best-effort, no persist). */
    useInComposer: function (text) {
      var input =
        $('#messageInput') || $('#wa-message-input') ||
        $('.wa-composer-input') || $('textarea.wa-input');
      if (input) {
        if ('value' in input) input.value = text;
        else input.textContent = text;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.focus();
        toast('Texto inserido no campo de mensagem.', 'success');
      } else {
        toast('Campo de mensagem não encontrado.', 'info');
      }
    },
  };

  // ========================================================================
  // QUICK-REPLY TEMPLATES
  // ========================================================================
  var Templates = {
    cache: null,

    /* Load templates once, render into `host` as a pickable list. */
    open: function (host, phone, onPick) {
      this.host = host;
      this.phone = phone;
      this.onPick = onPick;
      var self = this;
      if (this.cache) { this.render(); return; }
      getJSON('/api/crm/templates')
        .then(function (res) {
          self.cache = (res && res.templates) || [];
          self.render();
        })
        .catch(function () {
          if (self.host) {
            self.host.innerHTML =
              '<p class="wac-empty">Não foi possível carregar os templates.</p>';
          }
        });
    },

    render: function () {
      if (!this.host) return;
      var self = this;
      this.host.innerHTML = '';

      var newBtn = document.createElement('button');
      newBtn.type = 'button';
      newBtn.className = 'wac-btn wac-btn--ghost wac-btn--sm wac-tpl-new';
      newBtn.textContent = '+ Novo template';
      newBtn.addEventListener('click', function () { self.showForm(); });
      this.host.appendChild(newBtn);

      this.formHost = document.createElement('div');
      this.formHost.className = 'wac-tpl-form-host';
      this.formHost.hidden = true;
      this.host.appendChild(this.formHost);

      var list = document.createElement('div');
      list.className = 'wac-tpl-list';
      this.cache.forEach(function (tpl) {
        var row = document.createElement('div');
        row.className = 'wac-tpl-row';
        var item = document.createElement('button');
        item.type = 'button';
        item.className = 'wac-tpl';
        item.setAttribute('data-tpl-id', tpl.id);
        item.innerHTML =
          '<span class="wac-tpl__name">' + escapeHTML(tpl.name) + '</span>' +
          '<span class="wac-tpl__cat">' + escapeHTML(tpl.category) + '</span>' +
          '<span class="wac-tpl__preview">' +
          escapeHTML((tpl.text || '').slice(0, 90)) + '…</span>';
        item.addEventListener('click', function () { self.pick(tpl.id); });
        row.appendChild(item);
        if (tpl.is_custom) {
          var del = document.createElement('button');
          del.type = 'button';
          del.className = 'wac-tpl__del';
          del.setAttribute('aria-label', 'Excluir template');
          del.textContent = '×';
          del.addEventListener('click', function (ev) { ev.stopPropagation(); self.remove(tpl.id); });
          row.appendChild(del);
        }
        list.appendChild(row);
      });
      this.host.appendChild(list);
    },

    showForm: function () {
      var self = this, h = this.formHost;
      if (!h) return;
      h.hidden = false;
      h.innerHTML =
        '<input type="text" class="wac-tpl-input" id="wacTplName" maxlength="128" placeholder="Nome do template">' +
        '<textarea class="wac-tpl-input" id="wacTplBody" rows="4" maxlength="4000" ' +
        'placeholder="Texto (use {ORG_NAME}, [NOME], [DATA]…)"></textarea>' +
        '<div class="wac-tpl-form-actions">' +
        '<button type="button" class="wac-btn wac-btn--sm" id="wacTplSave">Salvar</button>' +
        '<button type="button" class="wac-btn wac-btn--ghost wac-btn--sm" id="wacTplCancel">Cancelar</button>' +
        '</div>';
      var save = $('#wacTplSave', h), cancel = $('#wacTplCancel', h);
      if (save) save.addEventListener('click', function () {
        var name = ($('#wacTplName', h) || {}).value || '';
        var bodyv = ($('#wacTplBody', h) || {}).value || '';
        if (!name.trim() || !bodyv.trim()) { toast('Nome e texto são obrigatórios.', 'error'); return; }
        self.create(name.trim(), bodyv.trim());
      });
      if (cancel) cancel.addEventListener('click', function () { h.hidden = true; h.innerHTML = ''; });
    },

    create: function (name, bodyPt) {
      var self = this;
      postJSON('/api/crm/templates', { name: name, body_pt: bodyPt, category: 'custom' })
        .then(function (res) {
          if (res && res.success) {
            self.cache = null; toast('Template criado.', 'success');
            self.open(self.host, self.phone, self.onPick);
          } else toast((res && res.error) || 'Falha ao criar template.', 'error');
        })
        .catch(function () { toast('Falha ao criar template.', 'error'); });
    },

    remove: function (tid) {
      var self = this;
      fetch(api('/api/crm/templates/' + encodeURIComponent(tid)),
            { method: 'DELETE', headers: { Accept: 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (res && res.success) {
            self.cache = null; toast('Template excluído.', 'success');
            self.open(self.host, self.phone, self.onPick);
          }
        })
        .catch(function () { toast('Falha ao excluir template.', 'error'); });
    },

    /* Fetch one template personalized for the current contact. */
    pick: function (tid) {
      var self = this;
      var qs = this.phone ? '?phone=' + encodeURIComponent(this.phone) : '';
      getJSON('/api/crm/template/' + encodeURIComponent(tid) + qs)
        .then(function (res) {
          if (typeof self.onPick === 'function') self.onPick(res.text || '');
          else Panel.useInComposer(res.text || '');
        })
        .catch(function () { toast('Falha ao carregar template.', 'error'); });
    },
  };

  // ========================================================================
  // PIPELINE / FUNNEL KANBAN
  // ========================================================================
  var Pipeline = {
    el: null,
    host: null,
    dragPhone: null,

    /* Mount the pipeline fragment into `host`, then hydrate the cards. */
    open: function (host) {
      this.host = host || this.host || $('#wacPipelineHost');
      if (!this.host) return;
      var self = this;
      this.host.hidden = false;
      this.host.classList.add('wac-pipeline-host');
      getHTML('/crm/pipeline')
        .then(function (html) {
          self.host.innerHTML = html;
          self.el = $('.wac-pipeline', self.host);
          self.bind();
          self.load();
        })
        .catch(function (err) {
          self.host.innerHTML =
            '<div class="wac-pipeline wac-pipeline--error">' +
            '<p class="wac-empty">Não foi possível carregar o funil.</p></div>';
          console.warn('[wa-crm] pipeline load failed:', err);
        });
    },

    close: function () {
      if (this.host) {
        this.host.hidden = true;
        this.host.classList.remove('wac-pipeline-host');
      }
    },

    bind: function () {
      if (!this.el) return;
      var self = this;
      $all('[data-wac-close]', this.el).forEach(function (b) {
        b.addEventListener('click', function () { self.close(); });
      });
      var refresh = $('#wacPipelineRefresh', this.el);
      if (refresh) {
        refresh.addEventListener('click', function () { self.load(); });
      }
      // Drop zones — each stage column accepts cards via native DnD.
      $all('[data-stage-dropzone]', this.el).forEach(function (zone) {
        zone.addEventListener('dragover', function (ev) {
          ev.preventDefault();
          zone.classList.add('is-dragover');
        });
        zone.addEventListener('dragleave', function () {
          zone.classList.remove('is-dragover');
        });
        zone.addEventListener('drop', function (ev) {
          ev.preventDefault();
          zone.classList.remove('is-dragover');
          var stage = zone.getAttribute('data-stage-dropzone');
          if (self.dragPhone) self.move(self.dragPhone, stage);
        });
      });
    },

    load: function () {
      if (!this.el) return;
      var self = this;
      var loading = $('#wacPipelineLoading', this.el);
      if (loading) loading.hidden = false;
      getJSON('/api/crm/pipeline')
        .then(function (data) { self.render(data); })
        .catch(function () {
          if (loading) {
            loading.innerHTML =
              '<span class="wac-empty">Erro ao carregar o funil.</span>';
          }
        });
      self.loadMetrics();
    },

    loadMetrics: function () {
      var self = this;
      getJSON('/api/crm/analytics')
        .then(function (m) { self.renderMetrics(m || {}); })
        .catch(function () {});
    },

    renderMetrics: function (m) {
      var box = $('#wacPipelineMetrics', this.el);
      if (!box) return;
      box.innerHTML = '';
      var items = [
        ['Conversão', (m.conversion_pct != null ? m.conversion_pct : 0) + '%'],
        ['Score médio', (m.avg_score != null ? m.avg_score : 0) + '/100'],
        ['Ganhos', m.won != null ? m.won : 0],
        ['Follow-ups vencidos', m.overdue != null ? m.overdue : 0],
      ];
      if (m.avg_days_to_win != null) items.push(['Dias até ganhar', m.avg_days_to_win]);
      items.forEach(function (it) {
        var cell = document.createElement('div');
        cell.className = 'wac-metric';
        var num = document.createElement('span');
        num.className = 'wac-metric__num';
        num.textContent = String(it[1]);                 // textContent => safe
        var lbl = document.createElement('span');
        lbl.className = 'wac-metric__lbl';
        lbl.textContent = it[0];
        cell.appendChild(num); cell.appendChild(lbl);
        box.appendChild(cell);
      });
    },

    render: function (data) {
      if (!this.el) return;
      var self = this;
      var loading = $('#wacPipelineLoading', this.el);
      if (loading) loading.hidden = true;

      var total = (data && data.total) || 0;
      var totalEl = $('#wacPipelineTotal', this.el);
      if (totalEl) {
        totalEl.textContent =
          total + (total === 1 ? ' conversa' : ' conversas');
      }

      var tpl = $('#wacPipelineCardTpl', this.el);
      (data.stages || []).forEach(function (stage) {
        var zone = self.el.querySelector(
          '[data-stage-dropzone="' + stage.key + '"]'
        );
        var countEl = self.el.querySelector(
          '[data-stage-count="' + stage.key + '"]'
        );
        if (countEl) countEl.textContent = stage.count;
        if (!zone) return;

        // Clear previous cards but keep the empty-state placeholder.
        $all('.wac-card', zone).forEach(function (c) { c.remove(); });
        var emptyEl = zone.querySelector('[data-stage-empty]');
        if (emptyEl) emptyEl.hidden = stage.cards.length > 0;

        stage.cards.forEach(function (card) {
          var node = self.buildCard(tpl, card, stage.key);
          if (node) zone.appendChild(node);
        });
      });
    },

    buildCard: function (tpl, card, stageKey) {
      var node;
      if (tpl && tpl.content) {
        node = tpl.content.firstElementChild.cloneNode(true);
      } else {
        node = document.createElement('article');
        node.className = 'wac-card';
        node.setAttribute('draggable', 'true');
        node.innerHTML =
          '<div class="wac-card__top"><span class="wac-card__avatar"></span>' +
          '<span class="wac-card__name"></span>' +
          '<span class="wac-card__unread" hidden></span></div>' +
          '<p class="wac-card__snippet"></p>' +
          '<div class="wac-card__meta"><span class="wac-card__client" hidden>' +
          '</span><span class="wac-card__time"></span></div>' +
          '<div class="wac-card__tags"></div>';
      }
      node.setAttribute('data-phone', card.phone || '');
      node.setAttribute('data-stage', stageKey);

      var name = card.name || card.phone || '—';
      var nameEl = node.querySelector('.wac-card__name');
      if (nameEl) nameEl.textContent = name;

      var avatar = node.querySelector('.wac-card__avatar');
      if (avatar) {
        if (card.profilePic) {
          avatar.style.backgroundImage = 'url("' + card.profilePic + '")';
          avatar.classList.add('has-img');
        } else {
          avatar.textContent = name.charAt(0).toUpperCase();
        }
      }

      var unread = node.querySelector('.wac-card__unread');
      if (unread) {
        if (card.unread) {
          unread.textContent = card.unread;
          unread.hidden = false;
        } else {
          unread.hidden = true;
        }
      }

      var snippet = node.querySelector('.wac-card__snippet');
      if (snippet) snippet.textContent = card.lastMessage || '—';

      var clientEl = node.querySelector('.wac-card__client');
      if (clientEl) {
        if (card.client_name) {
          clientEl.textContent = card.client_name;
          clientEl.hidden = false;
        } else {
          clientEl.hidden = true;
        }
      }

      var timeEl = node.querySelector('.wac-card__time');
      if (timeEl) timeEl.textContent = fmtRelative(card.lastMessageTime);

      var tagsEl = node.querySelector('.wac-card__tags');
      if (tagsEl) {
        tagsEl.innerHTML = '';
        (card.tags || []).slice(0, 4).forEach(function (t) {
          var chip = document.createElement('span');
          chip.className = 'wac-card__tag';
          chip.textContent = t;
          tagsEl.appendChild(chip);
        });
      }

      var self = this;
      node.addEventListener('dragstart', function () {
        self.dragPhone = card.phone;
        node.classList.add('is-dragging');
      });
      node.addEventListener('dragend', function () {
        node.classList.remove('is-dragging');
        self.dragPhone = null;
      });
      // Activating a card opens that conversation in the chat clone.
      var openConv = function () {
        if (typeof window.selectConversation === 'function') {
          window.selectConversation(card.phone);
        } else if (typeof window.openConversation === 'function') {
          window.openConversation(card.phone);
        }
        Panel.open(card.phone);
      };
      node.addEventListener('click', openConv);
      node.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); openConv(); }
      });
      return node;
    },

    /* Persist a stage change via the move endpoint, then refresh. */
    move: function (phone, stage) {
      var self = this;
      postJSON('/api/crm/pipeline/move', { phone: phone, stage: stage })
        .then(function (res) {
          toast('Lead movido para ' + (res.stage || stage) + '.', 'success');
          self.load();
          // Keep the contact panel stage picker in sync if it shows this phone.
          if (Panel.el && Panel.phone === phone) Panel.open(phone, Panel.host);
        })
        .catch(function () {
          toast('Falha ao mover o lead.', 'error');
          self.load();
        });
    },
  };

  // ========================================================================
  // PUBLIC API — the orchestrator wires chat.html buttons to these.
  // ========================================================================
  window.WhatsAppCRM = {
    /* Open/refresh the CRM contact panel for a phone.
       host: optional element to mount into (defaults to #wacPanelHost). */
    openContactPanel: function (phone, host) { Panel.open(phone, host); },
    closeContactPanel: function () { Panel.close(); },

    /* Open/refresh the pipeline kanban.
       host: optional element to mount into (defaults to #wacPipelineHost). */
    openPipeline: function (host) { Pipeline.open(host); },
    closePipeline: function () { Pipeline.close(); },
    refreshPipeline: function () { Pipeline.load(); },

    /* Render the quick-reply template picker into `host`.
       onPick(text) is called with the personalized template body. */
    openTemplates: function (host, phone, onPick) {
      Templates.open(host, phone, onPick);
    },

    /* Convenience: re-render the panel for whatever phone chat.js selected. */
    syncToSelected: function () {
      var phone = window.State && window.State.selectedPhone;
      if (phone) Panel.open(phone);
    },

    _internal: { Panel: Panel, Pipeline: Pipeline, Templates: Templates },
  };

  // Auto-bind any declarative triggers chat.html may carry (additive, optional).
  document.addEventListener('click', function (ev) {
    var t = ev.target.closest && ev.target.closest('[data-wac-action]');
    if (!t) return;
    var action = t.getAttribute('data-wac-action');
    if (action === 'open-pipeline') {
      ev.preventDefault();
      Pipeline.open();
    } else if (action === 'open-crm-panel') {
      ev.preventDefault();
      var phone =
        t.getAttribute('data-phone') ||
        (window.State && window.State.selectedPhone);
      if (phone) Panel.open(phone);
    } else if (action === 'open-templates') {
      ev.preventDefault();
      var host = $('#wacTemplatesHost');
      if (host) {
        Templates.open(
          host,
          window.State && window.State.selectedPhone,
          null
        );
      }
    }
  });
})();
