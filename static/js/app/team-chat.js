/* CaseHub App · Chat de equipe — org-scoped, polling.
 * Fase 1: canal #equipe. Fase 2 (este arquivo): lista de membros + DMs 1-a-1.
 * Backend seguro: /api/team-chat (routes/team_messages.py). DM so' acessivel a membros.
 */
(function () {
  'use strict';
  var root = document.querySelector('[data-team-chat]');
  if (!root) return;

  var PREFIX = window.CASEHUB_PREFIX || '/casehub';
  var API = PREFIX + '/api/team-chat';
  var MAESTRO_ICON_URL = root.getAttribute('data-maestro-icon') || '/static/brand-kit/maestro/maestro.png';
  var btn = root.querySelector('[data-tc-toggle]');
  var panel = root.querySelector('[data-tc-panel]');
  var listEl = root.querySelector('[data-tc-list]');
  var form = root.querySelector('[data-tc-form]');
  var input = root.querySelector('[data-tc-input]');
  var badge = root.querySelector('[data-tc-badge]');
  var closeBtn = root.querySelector('[data-tc-close]');
  var minBtn = root.querySelector('[data-tc-min]');
  var titleEl = root.querySelector('[data-tc-title]');
  var membersBtn = root.querySelector('[data-tc-members]');
  var membersPanel = root.querySelector('[data-tc-members-panel]');
  var channelsEl = root.querySelector('[data-tc-channels]');
  var attachBtn = root.querySelector('[data-tc-attach]');
  var fileInput = root.querySelector('[data-tc-file]');
  var settingsBtn = root.querySelector('[data-tc-settings]');
  var settingsPanel = root.querySelector('[data-tc-settings-panel]');
  var fontSizeWrap = root.querySelector('[data-tc-fontsize]');
  var fontVal = root.querySelector('[data-tc-fontval]');

  var channelId = null, lastId = 0, open = false, msgTimer = null, chanTimer = null;
  var channels = [], currentName = '#equipe', currentKind = 'channel';
  var seenMsgIds = {};            // anti-duplicacao: ids ja renderizados na conversa atual
  var loadingMsgs = false;        // evita fetches concorrentes (envio + poll)

  // --- Tamanho da fonte da conversa (persistido por navegador) ---
  var FONT_KEY = 'tc-msg-font', FONT_MIN = 11, FONT_MAX = 22, FONT_DEFAULT = 14;
  function getFont(){ var v; try { v = parseInt(localStorage.getItem(FONT_KEY), 10); } catch(e){} return (v && v >= FONT_MIN && v <= FONT_MAX) ? v : FONT_DEFAULT; }
  function applyFont(px){
    px = Math.max(FONT_MIN, Math.min(FONT_MAX, px));
    if (panel) panel.style.setProperty('--tc-msg-font', px + 'px');
    if (fontVal) fontVal.textContent = px + 'px';
    try { localStorage.setItem(FONT_KEY, String(px)); } catch(e){}
    if (fontSizeWrap){
      var dec = fontSizeWrap.querySelector('[data-step="-1"]'), inc = fontSizeWrap.querySelector('[data-step="1"]');
      if (dec) dec.disabled = px <= FONT_MIN;
      if (inc) inc.disabled = px >= FONT_MAX;
    }
  }

  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function parseServerTime(value) {
    if (value == null || value === '') return null;
    if (typeof value === 'number') {
      var fromNumber = new Date(value);
      return Number.isFinite(fromNumber.getTime()) ? fromNumber : null;
    }
    var raw = String(value).trim();
    if (!raw) return null;
    var normalized = raw.replace(' ', 'T');
    if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(normalized)) normalized += 'Z';
    var parsed = new Date(normalized);
    return Number.isFinite(parsed.getTime()) ? parsed : null;
  }

  function hhmm(s){
    var d = parseServerTime(s);
    if (!d) return '';
    return d.toLocaleTimeString('pt-BR', {
      timeZone: 'America/Sao_Paulo',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  function firstName(n){ n = String(n == null ? '' : n).trim(); return n.charAt(0) === '#' ? n : (n.split(/\s+/)[0] || n); }
  // Avatar com fallback: foto 404 -> inicial colorida (uploads/avatars pode nao
  // existir neste host). 'error' de <img> nao borbulha -> listener em captura.
  function avImg(imgCls, fbCls, src, ini, color){
    return '<img class="' + imgCls + '" style="background:' + esc(color || '#888') + '" src="' + esc(src) + '" loading="lazy" alt=""'
      + ' data-tc-fb="' + esc(fbCls) + '" data-tc-ini="' + esc(String(ini == null ? '?' : ini).charAt(0).toUpperCase() || '?')
      + '" data-tc-color="' + esc(color || '#888') + '">';
  }
  if (!window.__tcAvFb){
    window.__tcAvFb = true;
    document.addEventListener('error', function(e){
      var img = e.target;
      if (!img || img.tagName !== 'IMG' || !img.dataset || !img.dataset.tcFb || img.dataset.tcDone) return;
      img.dataset.tcDone = '1';
      var sp = document.createElement('span');
      sp.className = img.dataset.tcFb;
      if (img.dataset.tcColor) sp.style.background = img.dataset.tcColor;
      sp.textContent = img.dataset.tcIni || '?';
      if (img.parentNode) img.parentNode.replaceChild(sp, img);
    }, true);
  }

  function setBadge(n){
    if (!badge) return;
    if (n > 0) { badge.textContent = n > 99 ? '99+' : String(n); badge.hidden = false; }
    else { badge.hidden = true; }
  }

  function setTitle(){ if (titleEl) titleEl.textContent = (currentKind === 'dm' ? '@ ' : '') + currentName; }

  var _chanSig = '';
  function renderChannels(){
    if (!channelsEl) return;
    // Anti-flicker: so reescreve o innerHTML (que recria os <img> e os faz
    // re-decodar/piscar) quando a lista, o canal ativo, o unread ou a foto
    // realmente mudam. O poll de 4s (markRead -> loadChannels) nao toca o DOM.
    var sig = channels.map(function(c){
      return c.id + ':' + (c.id === channelId ? 1 : 0)
        + ':' + ((c.unread > 0 && c.id !== channelId) ? 1 : 0)
        + ':' + (c.peer_photo_url || '') + ':' + c.name;
    }).join('|');
    if (sig === _chanSig) return;
    _chanSig = sig;
    channelsEl.innerHTML = channels.map(function(c){
      var active = c.id === channelId ? ' is-active' : '';
      var dot = (c.unread > 0 && c.id !== channelId) ? '<span class="tc-chip__dot"></span>' : '';
      return '<button type="button" class="tc-chip' + active + '" data-cid="' + c.id + '" data-name="' + esc(c.name) +
             '" data-kind="' + esc(c.kind) + '">' + (c.kind === 'dm' ? (c.peer_photo_url ? avImg('tc-chip__av', 'tc-chip__av tc-chip__av--initial', c.peer_photo_url, c.name, c.peer_color||'#6b7280') : '<span class="tc-chip__av tc-chip__av--initial" style="background:' + esc(c.peer_color||'#6b7280') + '">' + esc((c.name||'?')[0].toUpperCase()) + '</span>') : '') + esc(firstName(c.name)) + dot + '</button>';
    }).join('');
  }

  async function loadChannels(){
    try {
      var r = await fetch(API + '/channels', { credentials: 'same-origin' });
      if (!r.ok) return;
      var d = await r.json();
      channels = d.channels || [];
      if (channelId == null && channels.length) {
        channelId = channels[0].id; currentName = channels[0].name; currentKind = channels[0].kind; setTitle();
      }
      setBadge(channels.reduce(function(s, c){ return s + (c.unread || 0); }, 0));
      renderChannels();
    } catch(e){}
  }

  function renderAppend(msgs){
    if (!msgs || !msgs.length) return;
    var atBottom = listEl.scrollHeight - listEl.scrollTop - listEl.clientHeight < 60;
    var mineIncoming = false;
    var html = '';
    msgs.forEach(function(m){
      // anti-duplicacao: envio + poll de 4s podem buscar a mesma msg (mesmo
      // since=lastId) antes de qualquer um atualizar lastId. Renderiza 1x por id.
      if (m.id != null) {
        if (seenMsgIds[m.id]) return;
        seenMsgIds[m.id] = 1;
      }
      lastId = Math.max(lastId, m.id);
      if (m.mine) mineIncoming = true;
      var isMaestro = !!m.is_maestro || m.actor_type === 'maestro';
      var msgClass = 'tc-msg ' + (m.mine ? 'is-mine ' : '') + (isMaestro ? 'is-maestro' : '');
      var att = '';
      if (m.attachment_url) {
        var au = esc(m.attachment_url), an = esc(m.attachment_name || 'arquivo');
        if (m.attachment_kind === 'image') att = '<a href="' + au + '" target="_blank" rel="noopener"><img class="tc-msg__img" src="' + au + '" alt="' + an + '" loading="lazy"></a>';
        else if (m.attachment_kind === 'audio') att = '<audio class="tc-msg__audio" controls preload="none" src="' + au + '"></audio>';
        else att = '<a class="tc-msg__file" href="' + au + '" target="_blank" rel="noopener" download>📄 ' + an + '</a>';
      }
      var maestroAvatar = '<span class="tc-msg__avatar tc-msg__avatar--maestro" aria-hidden="true">' +
        '<img src="' + esc(MAESTRO_ICON_URL) + '" alt="" loading="lazy"></span>';
      var hav = m.mine ? '' : (isMaestro
        ? maestroAvatar
        : (m.photo_url
          ? avImg('tc-msg__avatar', 'tc-msg__avatar tc-msg__avatar--ini', m.photo_url, m.author, m.color||'#888')
          : '<span class="tc-msg__avatar tc-msg__avatar--ini" style="background:' + esc(m.color || '#888') + '">' + esc((m.author || '?').charAt(0).toUpperCase()) + '</span>'));
      html += '<div class="' + msgClass + '">' +
        (m.mine ? '' : '<span class="tc-msg__head">' + hav + '<span class="tc-msg__author" style="color:' + esc(m.color) + '">' + esc(m.author) + '</span></span>') +
        att +
        (m.body ? '<span class="tc-msg__bubble">' + esc(m.body) + '</span>' : '') +
        '<span class="tc-msg__time">' + hhmm(m.created_at) + '</span>' +
      '</div>';
    });
    listEl.insertAdjacentHTML('beforeend', html);
    if (atBottom || mineIncoming) listEl.scrollTop = listEl.scrollHeight;
  }

  async function loadMessages(){
    if (channelId == null) { await loadChannels(); }
    if (channelId == null) return;
    if (loadingMsgs) return;       // nao deixa envio + poll buscarem em paralelo
    loadingMsgs = true;
    try {
      var r = await fetch(API + '/channels/' + channelId + '/messages?since=' + lastId, { credentials: 'same-origin' });
      if (!r.ok) return;
      var d = await r.json();
      renderAppend(d.messages || []);
    } catch(e){}
    finally { loadingMsgs = false; }
  }

  async function markRead(){
    if (channelId == null) return;
    try { await fetch(API + '/channels/' + channelId + '/read', { method: 'POST', credentials: 'same-origin' }); } catch(e){}
    loadChannels();
  }

  function switchChannel(cid, name, kind){
    if (membersPanel) membersPanel.hidden = true;
    if (listEl) listEl.style.display = '';
    if (cid === channelId) return;
    channelId = cid; currentName = name; currentKind = kind; lastId = 0;
    seenMsgIds = {};
    if (listEl) listEl.innerHTML = '';
    setTitle(); renderChannels();
    loadMessages().then(markRead);
  }

  async function loadMembers(){
    var html = '<div class="tc-empty">Carregando…</div>';
    if (membersPanel) membersPanel.innerHTML = html;
    try {
      var r = await fetch(API + '/members', { credentials: 'same-origin' });
      var d = r.ok ? await r.json() : { members: [] };
      var ms = d.members || [];
      if (membersPanel) {
        membersPanel.innerHTML = ms.length
          ? '<div class="tc-members__head">Conversar com</div>' + ms.map(function(m){
              var av = m.photo_url
                ? avImg('tc-avatar', 'tc-avatar tc-avatar--ini', m.photo_url, m.name, m.color||'#888')
                : '<span class="tc-avatar tc-avatar--ini" style="background:' + esc(m.color || '#888') + '">' + esc((m.name || '?').charAt(0).toUpperCase()) + '</span>';
              return '<button type="button" class="tc-member" data-uid="' + m.id + '" data-name="' + esc(m.name) + '">' +
                av + '<span class="tc-member__name">' + esc(m.name) + '</span></button>';
            }).join('')
          : '<div class="tc-empty">Você é o único na equipe por enquanto.</div>';
      }
    } catch(e){ if (membersPanel) membersPanel.innerHTML = '<div class="tc-empty">Não foi possível carregar.</div>'; }
  }

  async function openDM(userId, name){
    try {
      var r = await fetch(API + '/dm', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin', body: JSON.stringify({ user_id: userId })
      });
      if (!r.ok) return;
      var d = await r.json();
      if (d.channel_id) { await loadChannels(); switchChannel(d.channel_id, d.name || name, 'dm'); }
    } catch(e){}
  }

  function openPanel(){
    open = true; root.classList.add('is-open'); panel.hidden = false;
    loadChannels().then(function(){ setTitle(); return loadMessages(); }).then(markRead);
    if (msgTimer) clearInterval(msgTimer);
    msgTimer = setInterval(function(){ loadMessages().then(function(){ if (open) markRead(); }); }, 4000);
    setTimeout(function(){ if (input) input.focus(); }, 80);
  }

  function closePanel(){
    open = false; root.classList.remove('is-open'); panel.hidden = true;
    if (membersPanel) membersPanel.hidden = true;
    if (settingsPanel) settingsPanel.hidden = true;
    if (msgTimer) { clearInterval(msgTimer); msgTimer = null; }
    loadChannels();
  }

  if (btn) btn.addEventListener('click', function(){ open ? closePanel() : openPanel(); });
  if (minBtn) minBtn.addEventListener('click', closePanel);
  if (closeBtn) closeBtn.addEventListener('click', function () { closePanel(); markRead(); });

  if (membersBtn) membersBtn.addEventListener('click', function(){
    if (!membersPanel) return;
    if (settingsPanel) settingsPanel.hidden = true;
    var show = membersPanel.hidden;
    if (show) loadMembers();
    membersPanel.hidden = !show;
    if (listEl) listEl.style.display = show ? 'none' : '';
  });

  // --- Configurações (engrenagem): popover com o stepper de tamanho de fonte ---
  if (settingsBtn) settingsBtn.addEventListener('click', function(){
    if (!settingsPanel) return;
    settingsPanel.hidden = !settingsPanel.hidden;
  });
  if (fontSizeWrap) fontSizeWrap.addEventListener('click', function(e){
    var b = e.target.closest && e.target.closest('[data-step]');
    if (!b) return;
    applyFont(getFont() + parseInt(b.getAttribute('data-step'), 10));
  });
  // fecha o popover ao clicar fora dele (e fora da engrenagem)
  document.addEventListener('click', function(e){
    if (!settingsPanel || settingsPanel.hidden) return;
    if (settingsPanel.contains(e.target) || (settingsBtn && settingsBtn.contains(e.target))) return;
    settingsPanel.hidden = true;
  });
  if (membersPanel) membersPanel.addEventListener('click', function(e){
    var b = e.target.closest && e.target.closest('[data-uid]');
    if (!b) return;
    openDM(parseInt(b.getAttribute('data-uid'), 10), b.getAttribute('data-name'));
  });
  if (channelsEl) channelsEl.addEventListener('click', function(e){
    var b = e.target.closest && e.target.closest('[data-cid]');
    if (!b) return;
    switchChannel(parseInt(b.getAttribute('data-cid'), 10), b.getAttribute('data-name'), b.getAttribute('data-kind'));
  });

  if (form) form.addEventListener('submit', async function(e){
    e.preventDefault();
    var body = (input.value || '').trim();
    if (!body || channelId == null) return;
    input.value = '';
    try {
      var r = await fetch(API + '/channels/' + channelId + '/messages', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin', body: JSON.stringify({ body: body })
      });
      if (r.ok) await loadMessages();
    } catch(err){ if (input) input.value = body; }
  });

  // --- anexar imagem / áudio / arquivo ---
  function setUploading(on){
    if (input) input.placeholder = on ? 'Enviando arquivo…' : 'Mensagem para a equipe…';
    if (attachBtn) attachBtn.disabled = !!on;
  }
  async function uploadFile(f){
    if (!f || channelId == null) return;
    setUploading(true);
    try {
      var fd = new FormData(); fd.append('file', f);
      var r = await fetch(API + '/channels/' + channelId + '/upload', { method: 'POST', credentials: 'same-origin', body: fd });
      var d = {};
      try { d = await r.json(); } catch(e){}
      if (!r.ok) { try { (window.toast && window.toast.error) ? window.toast.error(d.error || 'Falha no envio.') : alert(d.error || 'Não foi possível enviar o arquivo.'); } catch(e){} }
      else { await loadMessages(); }
    } catch(e){ try { alert('Falha no envio do arquivo.'); } catch(_){} }
    finally { setUploading(false); if (fileInput) fileInput.value = ''; }
  }
  if (attachBtn && fileInput) attachBtn.addEventListener('click', function(){ fileInput.click(); });
  if (fileInput) fileInput.addEventListener('change', function(){ if (fileInput.files && fileInput.files[0]) uploadFile(fileInput.files[0]); });

  // baseline + polling leve (canais + badge) enquanto fechado
  applyFont(getFont());
  loadChannels();
  chanTimer = setInterval(function(){ loadChannels(); }, 20000);
})();
