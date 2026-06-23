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
  var soundToggle = root.querySelector('[data-tc-sound-toggle]');
  var desktopToggle = root.querySelector('[data-tc-desktop-toggle]');
  var soundTestBtn = root.querySelector('[data-tc-sound-test]');
  var mediaBtn = root.querySelector('[data-tc-media]');
  var mediaPanel = root.querySelector('[data-tc-media-panel]');
  var mediaSearch = root.querySelector('[data-tc-media-search]');
  var mediaQuery = root.querySelector('[data-tc-media-query]');
  var mediaGrid = root.querySelector('[data-tc-media-grid]');
  var mediaEmpty = root.querySelector('[data-tc-media-empty]');
  var mediaSource = root.querySelector('[data-tc-media-source]');
  var replyBar = root.querySelector('[data-tc-reply]');
  var replyAuthorEl = root.querySelector('[data-tc-reply-author]');
  var replyBodyEl = root.querySelector('[data-tc-reply-body]');
  var replyCloseBtn = root.querySelector('[data-tc-reply-close]');

  var channelId = null, lastId = 0, open = false, msgTimer = null, chanTimer = null;
  var channels = [], currentName = '#equipe', currentKind = 'channel';
  var seenMsgIds = {};            // anti-duplicacao: ids ja renderizados na conversa atual
  var loadingMsgs = false;        // evita fetches concorrentes (envio + poll)
  var sending = false;            // evita double-submit (duplo toque mobile / duplo evento)
  var unreadPrimed = false, lastUnreadTotal = 0;
  var mediaKind = 'gif', mediaItems = [], mediaSearchTimer = null;
  var replyTo = null;

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

  // --- Tamanho da janela no desktop (resize nativo + persistencia local) ---
  var PANEL_W_KEY = 'tc-panel-width';
  var PANEL_H_KEY = 'tc-panel-height';
  var PANEL_MIN_W = 340, PANEL_MIN_H = 380, PANEL_DEFAULT_W = 380, PANEL_DEFAULT_H = 540;
  var panelResizeTimer = null;
  function clamp(n, min, max){ return Math.max(min, Math.min(max, n)); }
  function isDesktopPanel(){ return !!(window.matchMedia && window.matchMedia('(min-width: 880px)').matches); }
  function storedPanelInt(key, fallback){
    var v;
    try { v = parseInt(localStorage.getItem(key), 10); } catch(e){}
    return Number.isFinite(v) ? v : fallback;
  }
  function applyPanelSize(){
    if (!panel) return;
    if (!isDesktopPanel()) {
      panel.style.removeProperty('width');
      panel.style.removeProperty('height');
      return;
    }
    var maxW = Math.max(PANEL_MIN_W, window.innerWidth - 32);
    var maxH = Math.max(PANEL_MIN_H, window.innerHeight - 120);
    var w = clamp(storedPanelInt(PANEL_W_KEY, PANEL_DEFAULT_W), PANEL_MIN_W, maxW);
    var h = clamp(storedPanelInt(PANEL_H_KEY, PANEL_DEFAULT_H), PANEL_MIN_H, maxH);
    panel.style.width = w + 'px';
    panel.style.height = h + 'px';
  }
  function rememberPanelSize(){
    if (!panel || panel.hidden || !isDesktopPanel()) return;
    var box = panel.getBoundingClientRect();
    var w = Math.round(clamp(box.width, PANEL_MIN_W, Math.max(PANEL_MIN_W, window.innerWidth - 32)));
    var h = Math.round(clamp(box.height, PANEL_MIN_H, Math.max(PANEL_MIN_H, window.innerHeight - 120)));
    try {
      localStorage.setItem(PANEL_W_KEY, String(w));
      localStorage.setItem(PANEL_H_KEY, String(h));
    } catch(e){}
  }
  function scheduleRememberPanelSize(){
    if (panelResizeTimer) clearTimeout(panelResizeTimer);
    panelResizeTimer = setTimeout(rememberPanelSize, 160);
  }
  function setupPanelResize(){
    if (!panel) return;
    if ('ResizeObserver' in window) {
      var observer = new ResizeObserver(scheduleRememberPanelSize);
      observer.observe(panel);
    }
    window.addEventListener('resize', applyPanelSize);
  }

  var SOUND_KEY = 'tc-sound-enabled';
  var DESKTOP_KEY = 'tc-desktop-enabled';
  var audioCtx = null;
  function prefOn(key, fallback){
    try {
      var stored = localStorage.getItem(key);
      if (stored == null) return !!fallback;
      return stored === '1';
    } catch(e){ return !!fallback; }
  }
  function setPref(key, value){ try { localStorage.setItem(key, value ? '1' : '0'); } catch(e){} }
  function syncNotificationControls(){
    if (soundToggle) soundToggle.checked = prefOn(SOUND_KEY, true);
    if (desktopToggle) {
      desktopToggle.checked = prefOn(DESKTOP_KEY, false);
      desktopToggle.disabled = !('Notification' in window);
      desktopToggle.title = desktopToggle.disabled ? 'Navegador sem suporte a notificações' : '';
    }
  }
  function unlockAudio(){
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    if (!audioCtx) audioCtx = new AC();
    if (audioCtx.state === 'suspended' && audioCtx.resume) audioCtx.resume().catch(function(){});
    return audioCtx;
  }
  function playChime(){
    if (!prefOn(SOUND_KEY, true)) return;
    var ctx = unlockAudio();
    if (!ctx || ctx.state === 'suspended') return;
    var now = ctx.currentTime;
    [
      { f: 659.25, t: 0.00, d: 0.10, g: 0.030 },
      { f: 987.77, t: 0.08, d: 0.11, g: 0.026 },
      { f: 1318.51, t: 0.18, d: 0.16, g: 0.018 }
    ].forEach(function(note){
      var osc = ctx.createOscillator(), gain = ctx.createGain();
      osc.type = 'sine'; osc.frequency.value = note.f;
      gain.gain.setValueAtTime(0.0001, now + note.t);
      gain.gain.exponentialRampToValueAtTime(note.g, now + note.t + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + note.t + note.d);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now + note.t); osc.stop(now + note.t + note.d + 0.02);
    });
  }
  async function maybeEnableDesktopNotifications(){
    if (!desktopToggle || !desktopToggle.checked) return;
    if (!('Notification' in window)) { desktopToggle.checked = false; setPref(DESKTOP_KEY, false); return; }
    if (Notification.permission === 'default') {
      try { await Notification.requestPermission(); } catch(e){}
    }
    if (Notification.permission !== 'granted') {
      desktopToggle.checked = false;
      setPref(DESKTOP_KEY, false);
    }
  }
  function notifyUser(title, body){
    playChime();
    if (!prefOn(DESKTOP_KEY, false) || !('Notification' in window) || Notification.permission !== 'granted') return;
    if (!document.hidden && open) return;
    try {
      var n = new Notification(title || 'CaseHub', {
        body: body || 'Nova mensagem no chat da equipe',
        icon: '/static/brand-kit/favicon/casehub-favicon-degrade-4.svg',
        tag: 'casehub-team-chat'
      });
      n.onclick = function(){ window.focus(); openPanel(); n.close(); };
      setTimeout(function(){ try { n.close(); } catch(e){} }, 6000);
    } catch(e){}
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

  function messagePreview(m){
    return String((m && (m.body || m.attachment_name)) || 'Mídia').trim().slice(0, 160);
  }
  function setReplyTo(reply){
    if (!reply || !reply.id) return;
    replyTo = {
      id: parseInt(reply.id, 10),
      author: String(reply.author || 'Mensagem'),
      body: String(reply.body || 'Mídia').slice(0, 160)
    };
    if (replyAuthorEl) replyAuthorEl.textContent = replyTo.author;
    if (replyBodyEl) replyBodyEl.textContent = replyTo.body;
    if (replyBar) replyBar.hidden = false;
    showConversationList();
    setTimeout(function(){ if (input) input.focus(); }, 40);
  }
  function clearReply(){
    replyTo = null;
    if (replyBar) replyBar.hidden = true;
    if (replyAuthorEl) replyAuthorEl.textContent = '';
    if (replyBodyEl) replyBodyEl.textContent = '';
  }

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
      var unreadTotal = channels.reduce(function(s, c){ return s + (c.unread || 0); }, 0);
      if (unreadPrimed && !open && unreadTotal > lastUnreadTotal) {
        notifyUser('CaseHub · Chat da equipe', 'Nova mensagem no chat');
      }
      unreadPrimed = true;
      lastUnreadTotal = unreadTotal;
      setBadge(unreadTotal);
      renderChannels();
    } catch(e){}
  }

  function renderAppend(msgs, opts){
    if (!msgs || !msgs.length) return;
    opts = opts || {};
    var atBottom = listEl.scrollHeight - listEl.scrollTop - listEl.clientHeight < 60;
    var mineIncoming = false;
    var incoming = [];
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
      if (!m.mine) incoming.push(m);
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
      var quoted = '';
      if (m.reply_to_id) {
        var quotedBody = m.reply_to_body || m.reply_to_attachment_name || 'Mídia';
        quoted = '<span class="tc-msg__quote"><strong>' + esc(m.reply_to_author || 'Mensagem') + '</strong><span>' + esc(quotedBody) + '</span></span>';
      }
      var bubble = (m.body || quoted)
        ? '<span class="tc-msg__bubble">' + quoted + (m.body ? '<span class="tc-msg__text">' + esc(m.body) + '</span>' : '') + '</span>'
        : '';
      var replyBtn = m.id
        ? '<span class="tc-msg__actions"><button type="button" class="tc-msg__reply" data-reply-id="' + m.id + '" data-reply-author="' + esc(m.author || 'Mensagem') + '" data-reply-body="' + esc(messagePreview(m)) + '" aria-label="Responder mensagem" title="Responder">↩</button></span>'
        : '';
      html += '<div class="' + msgClass + '">' +
        (m.mine ? '' : '<span class="tc-msg__head">' + hav + '<span class="tc-msg__author" style="color:' + esc(m.color) + '">' + esc(m.author) + '</span></span>') +
        bubble +
        att +
        '<span class="tc-msg__time">' + hhmm(m.created_at) + '</span>' +
        replyBtn +
      '</div>';
    });
    listEl.insertAdjacentHTML('beforeend', html);
    if (atBottom || mineIncoming) listEl.scrollTop = listEl.scrollHeight;
    if (incoming.length && opts.notify !== false) {
      var first = incoming[incoming.length - 1];
      var body = first.body || first.attachment_name || 'Nova mídia no chat da equipe';
      notifyUser(first.author || 'CaseHub', String(body).slice(0, 120));
    }
  }

  async function loadMessages(opts){
    if (channelId == null) { await loadChannels(); }
    if (channelId == null) return;
    if (loadingMsgs) return;       // nao deixa envio + poll buscarem em paralelo
    loadingMsgs = true;
    try {
      var r = await fetch(API + '/channels/' + channelId + '/messages?since=' + lastId, { credentials: 'same-origin' });
      if (!r.ok) return;
      var d = await r.json();
      renderAppend(d.messages || [], opts || {});
    } catch(e){}
    finally { loadingMsgs = false; }
  }

  async function markRead(){
    if (channelId == null) return;
    try { await fetch(API + '/channels/' + channelId + '/read', { method: 'POST', credentials: 'same-origin' }); } catch(e){}
    loadChannels();
  }

  function switchChannel(cid, name, kind){
    showConversationList();
    if (cid === channelId) return;
    clearReply();
    channelId = cid; currentName = name; currentKind = kind; lastId = 0;
    seenMsgIds = {};
    if (listEl) listEl.innerHTML = '';
    setTitle(); renderChannels();
    loadMessages({ notify: false }).then(markRead);
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

  function showConversationList(){
    if (membersPanel) membersPanel.hidden = true;
    if (mediaPanel) mediaPanel.hidden = true;
    if (listEl) listEl.style.display = '';
  }
  function setMediaLoading(text){
    if (mediaEmpty) {
      mediaEmpty.hidden = false;
      mediaEmpty.textContent = text || 'Carregando...';
    }
    if (mediaGrid) mediaGrid.innerHTML = '';
  }
  function renderMediaItems(items, provider){
    mediaItems = items || [];
    if (mediaSource) mediaSource.textContent = provider ? ('Powered by ' + provider) : '';
    if (!mediaGrid || !mediaEmpty) return;
    if (!mediaItems.length) {
      mediaGrid.innerHTML = '';
      mediaEmpty.hidden = false;
      mediaEmpty.textContent = 'Nada encontrado. Tente outro termo.';
      return;
    }
    mediaEmpty.hidden = true;
    mediaGrid.innerHTML = mediaItems.map(function(item, idx){
      var title = esc(item.title || (mediaKind === 'sticker' ? 'Figurinha' : 'GIF'));
      var preview = esc(item.thumb || item.preview_url || item.url || '');
      return '<button type="button" class="tc-media__item" data-idx="' + idx + '" data-kind="' + esc(item.kind || mediaKind) + '" title="' + title + '">' +
        '<img src="' + preview + '" alt="' + title + '" loading="lazy">' +
      '</button>';
    }).join('');
  }
  async function searchMedia(){
    if (!mediaPanel || mediaPanel.hidden) return;
    var q = mediaQuery ? mediaQuery.value.trim() : '';
    setMediaLoading(q ? 'Buscando...' : 'Carregando destaques...');
    try {
      var url = API + '/media/search?kind=' + encodeURIComponent(mediaKind) + '&q=' + encodeURIComponent(q) + '&limit=18';
      var r = await fetch(url, { credentials: 'same-origin' });
      var d = r.ok ? await r.json() : { results: [] };
      renderMediaItems(d.results || [], d.provider || 'Tenor');
    } catch(e){ setMediaLoading('Não foi possível carregar agora.'); }
  }
  function setMediaKind(kind){
    mediaKind = kind === 'sticker' ? 'sticker' : 'gif';
    if (mediaPanel) {
      Array.prototype.forEach.call(mediaPanel.querySelectorAll('[data-tc-media-kind]'), function(b){
        b.classList.toggle('is-active', b.getAttribute('data-tc-media-kind') === mediaKind);
      });
    }
    searchMedia();
  }
  function toggleMediaPanel(){
    if (!mediaPanel) return;
    if (settingsPanel) settingsPanel.hidden = true;
    if (membersPanel) membersPanel.hidden = true;
    var show = mediaPanel.hidden;
    mediaPanel.hidden = !show;
    if (listEl) listEl.style.display = show ? 'none' : '';
    if (show) {
      if (mediaQuery) setTimeout(function(){ mediaQuery.focus(); }, 60);
      searchMedia();
    }
  }
  async function sendMediaItem(item){
    if (!item || channelId == null || sending) return;
    sending = true;
    try {
      var r = await fetch(API + '/channels/' + channelId + '/media', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          kind: item.kind || mediaKind,
          url: item.url,
          preview_url: item.preview_url,
          title: item.title || '',
          provider: item.provider || '',
          source_id: item.id || '',
          reply_to_id: replyTo ? replyTo.id : null
        })
      });
      if (r.ok) {
        clearReply();
        showConversationList();
        await loadMessages({ notify: false });
      }
    } catch(e){}
    finally { sending = false; }
  }

  function openPanel(){
    unlockAudio();
    open = true; root.classList.add('is-open'); panel.hidden = false;
    applyPanelSize();
    loadChannels().then(function(){ setTitle(); return loadMessages({ notify: false }); }).then(markRead);
    if (msgTimer) clearInterval(msgTimer);
    msgTimer = setInterval(function(){ loadMessages().then(function(){ if (open) markRead(); }); }, 4000);
    setTimeout(function(){ if (input) input.focus(); }, 80);
  }

  function closePanel(){
    open = false; root.classList.remove('is-open'); panel.hidden = true;
    if (membersPanel) membersPanel.hidden = true;
    if (settingsPanel) settingsPanel.hidden = true;
    if (mediaPanel) mediaPanel.hidden = true;
    if (msgTimer) { clearInterval(msgTimer); msgTimer = null; }
    loadChannels();
  }

  if (btn) btn.addEventListener('click', function(){ open ? closePanel() : openPanel(); });
  if (minBtn) minBtn.addEventListener('click', closePanel);
  if (closeBtn) closeBtn.addEventListener('click', function () { closePanel(); markRead(); });

  if (membersBtn) membersBtn.addEventListener('click', function(){
    if (!membersPanel) return;
    if (settingsPanel) settingsPanel.hidden = true;
    if (mediaPanel) mediaPanel.hidden = true;
    var show = membersPanel.hidden;
    if (show) loadMembers();
    membersPanel.hidden = !show;
    if (listEl) listEl.style.display = show ? 'none' : '';
  });

  // --- Configurações (engrenagem): popover com o stepper de tamanho de fonte ---
  if (settingsBtn) settingsBtn.addEventListener('click', function(){
    if (!settingsPanel) return;
    unlockAudio();
    if (mediaPanel) mediaPanel.hidden = true;
    if (membersPanel) membersPanel.hidden = true;
    if (listEl) listEl.style.display = '';
    settingsPanel.hidden = !settingsPanel.hidden;
  });
  if (soundToggle) soundToggle.addEventListener('change', function(){
    setPref(SOUND_KEY, soundToggle.checked);
    if (soundToggle.checked) playChime();
  });
  if (desktopToggle) desktopToggle.addEventListener('change', function(){
    setPref(DESKTOP_KEY, desktopToggle.checked);
    maybeEnableDesktopNotifications();
  });
  if (soundTestBtn) soundTestBtn.addEventListener('click', function(){ playChime(); });
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
  if (mediaBtn) mediaBtn.addEventListener('click', function(){
    unlockAudio();
    toggleMediaPanel();
  });
  if (mediaPanel) {
    mediaPanel.addEventListener('click', function(e){
      var tab = e.target.closest && e.target.closest('[data-tc-media-kind]');
      if (tab) { setMediaKind(tab.getAttribute('data-tc-media-kind')); return; }
      var itemBtn = e.target.closest && e.target.closest('[data-idx]');
      if (!itemBtn) return;
      sendMediaItem(mediaItems[parseInt(itemBtn.getAttribute('data-idx'), 10)]);
    });
  }
  if (mediaSearch) mediaSearch.addEventListener('submit', function(e){
    e.preventDefault();
    searchMedia();
  });
  if (mediaQuery) mediaQuery.addEventListener('input', function(){
    if (mediaSearchTimer) clearTimeout(mediaSearchTimer);
    mediaSearchTimer = setTimeout(searchMedia, 350);
  });
  if (channelsEl) channelsEl.addEventListener('click', function(e){
    var b = e.target.closest && e.target.closest('[data-cid]');
    if (!b) return;
    switchChannel(parseInt(b.getAttribute('data-cid'), 10), b.getAttribute('data-name'), b.getAttribute('data-kind'));
  });
  if (listEl) listEl.addEventListener('click', function(e){
    var b = e.target.closest && e.target.closest('[data-reply-id]');
    if (!b) return;
    setReplyTo({
      id: b.getAttribute('data-reply-id'),
      author: b.getAttribute('data-reply-author'),
      body: b.getAttribute('data-reply-body')
    });
  });
  if (replyCloseBtn) replyCloseBtn.addEventListener('click', clearReply);

  if (form) form.addEventListener('submit', async function(e){
    e.preventDefault();
    if (sending) return;
    var body = (input.value || '').trim();
    if (!body || channelId == null) return;
    var pendingReply = replyTo;
    input.value = '';
    clearReply();
    sending = true;
    try {
      var payload = { body: body };
      if (pendingReply && pendingReply.id) payload.reply_to_id = pendingReply.id;
      var r = await fetch(API + '/channels/' + channelId + '/messages', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin', body: JSON.stringify(payload)
      });
      if (r.ok) await loadMessages({ notify: false });
      else {
        if (input) input.value = body;
        if (pendingReply) setReplyTo(pendingReply);
      }
    } catch(err){ if (input) input.value = body; if (pendingReply) setReplyTo(pendingReply); }
    finally { sending = false; }
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
      if (replyTo && replyTo.id) fd.append('reply_to_id', replyTo.id);
      var r = await fetch(API + '/channels/' + channelId + '/upload', { method: 'POST', credentials: 'same-origin', body: fd });
      var d = {};
      try { d = await r.json(); } catch(e){}
      if (!r.ok) { try { (window.toast && window.toast.error) ? window.toast.error(d.error || 'Falha no envio.') : alert(d.error || 'Não foi possível enviar o arquivo.'); } catch(e){} }
      else { clearReply(); await loadMessages({ notify: false }); }
    } catch(e){ try { alert('Falha no envio do arquivo.'); } catch(_){} }
    finally { setUploading(false); if (fileInput) fileInput.value = ''; }
  }
  if (attachBtn && fileInput) attachBtn.addEventListener('click', function(){ fileInput.click(); });
  if (fileInput) fileInput.addEventListener('change', function(){ if (fileInput.files && fileInput.files[0]) uploadFile(fileInput.files[0]); });

  // baseline + polling leve (canais + badge) enquanto fechado
  applyFont(getFont());
  applyPanelSize();
  setupPanelResize();
  syncNotificationControls();
  loadChannels();
  chanTimer = setInterval(function(){ loadChannels(); }, 20000);
})();
