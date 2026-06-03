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

  var channelId = null, lastId = 0, open = false, msgTimer = null, chanTimer = null;
  var channels = [], currentName = '#equipe', currentKind = 'channel';

  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function hhmm(s){ try { var d = new Date(String(s).replace(' ', 'T')); return d.toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit'}); } catch(e){ return ''; } }

  function setBadge(n){
    if (!badge) return;
    if (n > 0) { badge.textContent = n > 99 ? '99+' : String(n); badge.hidden = false; }
    else { badge.hidden = true; }
  }

  function setTitle(){ if (titleEl) titleEl.textContent = (currentKind === 'dm' ? '@ ' : '') + currentName; }

  function renderChannels(){
    if (!channelsEl) return;
    channelsEl.innerHTML = channels.map(function(c){
      var active = c.id === channelId ? ' is-active' : '';
      var dot = (c.unread > 0 && c.id !== channelId) ? '<span class="tc-chip__dot"></span>' : '';
      return '<button type="button" class="tc-chip' + active + '" data-cid="' + c.id + '" data-name="' + esc(c.name) +
             '" data-kind="' + esc(c.kind) + '">' + (c.kind === 'dm' ? '@' : '') + esc(c.name) + dot + '</button>';
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
      lastId = Math.max(lastId, m.id);
      if (m.mine) mineIncoming = true;
      var att = '';
      if (m.attachment_url) {
        var au = esc(m.attachment_url), an = esc(m.attachment_name || 'arquivo');
        if (m.attachment_kind === 'image') att = '<a href="' + au + '" target="_blank" rel="noopener"><img class="tc-msg__img" src="' + au + '" alt="' + an + '" loading="lazy"></a>';
        else if (m.attachment_kind === 'audio') att = '<audio class="tc-msg__audio" controls preload="none" src="' + au + '"></audio>';
        else att = '<a class="tc-msg__file" href="' + au + '" target="_blank" rel="noopener" download>📄 ' + an + '</a>';
      }
      html += '<div class="tc-msg ' + (m.mine ? 'is-mine' : '') + '">' +
        (m.mine ? '' : '<span class="tc-msg__author" style="color:' + esc(m.color) + '">' + esc(m.author) + '</span>') +
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
    try {
      var r = await fetch(API + '/channels/' + channelId + '/messages?since=' + lastId, { credentials: 'same-origin' });
      if (!r.ok) return;
      var d = await r.json();
      renderAppend(d.messages || []);
    } catch(e){}
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
              return '<button type="button" class="tc-member" data-uid="' + m.id + '" data-name="' + esc(m.name) + '">' +
                '<span class="tc-member__dot" style="background:' + esc(m.color) + '"></span>' + esc(m.name) + '</button>';
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
    if (msgTimer) { clearInterval(msgTimer); msgTimer = null; }
    loadChannels();
  }

  if (btn) btn.addEventListener('click', function(){ open ? closePanel() : openPanel(); });
  if (minBtn) minBtn.addEventListener('click', closePanel);
  if (closeBtn) closeBtn.addEventListener('click', function () { closePanel(); markRead(); });

  if (membersBtn) membersBtn.addEventListener('click', function(){
    if (!membersPanel) return;
    var show = membersPanel.hidden;
    if (show) loadMembers();
    membersPanel.hidden = !show;
    if (listEl) listEl.style.display = show ? 'none' : '';
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
  loadChannels();
  chanTimer = setInterval(function(){ loadChannels(); }, 20000);
})();
