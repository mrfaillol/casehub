/* CaseHub App · Notifications dropdown */
(function () {
  'use strict';

  var menu = document.querySelector('[data-notifications-menu]');
  if (!menu) return;

  var prefix = menu.getAttribute('data-prefix') || window.CASEHUB_PREFIX || '/casehub';
  var list = menu.querySelector('[data-notifications-list]');
  var summary = menu.querySelector('[data-notifications-summary]');
  var markRead = menu.querySelector('[data-notifications-mark-read]');
  var badge = document.querySelector('[data-notifications-badge]');
  var loaded = false;

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (char) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char];
    });
  }

  function setSummary(text) {
    if (summary) summary.textContent = text;
  }

  function renderEmpty(text) {
    if (!list) return;
    list.innerHTML = '<div class="ch-notifications-menu__empty">' + escapeHtml(text) + '</div>';
  }

  function renderItems(items, total) {
    if (!list) return;
    if (!items.length) {
      renderEmpty('Nenhuma notificação recente.');
      setSummary('Tudo em dia.');
      return;
    }
    list.innerHTML = items.map(function (item) {
      var href = item.action_url || (prefix + '/notifications');
      var unread = item.is_read ? 'false' : 'true';
      return '<a class="ch-notifications-menu__item" role="menuitem" data-unread="' + unread + '" href="' + escapeHtml(href) + '">' +
        '<span class="ch-notifications-menu__dot" aria-hidden="true"></span>' +
        '<span class="ch-notifications-menu__body">' +
          '<strong class="ch-notifications-menu__title">' + escapeHtml(item.title || 'Notificação') + '</strong>' +
          '<span class="ch-notifications-menu__message">' + escapeHtml(item.message || '') + '</span>' +
          '<span class="ch-notifications-menu__time">' + escapeHtml(item.time_ago || '') + '</span>' +
        '</span>' +
      '</a>';
    }).join('');
    setSummary(total + ' notificação' + (total === 1 ? '' : 'ões') + ' no histórico recente.');
  }

  async function loadNotifications(force) {
    if (loaded && !force) return;
    renderEmpty('Carregando notificações...');
    try {
      var response = await fetch(prefix + '/api/notifications/recent?limit=5', {
        credentials: 'same-origin'
      });
      if (!response.ok) throw new Error('recent-' + response.status);
      var data = await response.json();
      var items = Array.isArray(data.notifications) ? data.notifications : [];
      renderItems(items, Number(data.total || items.length || 0));
      loaded = true;
    } catch (err) {
      renderEmpty('Não foi possível carregar notificações agora.');
      setSummary('Central disponível abaixo.');
    }
  }

  async function markAllRead() {
    try {
      var response = await fetch(prefix + '/api/notifications/mark-read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ ids: [] })
      });
      if (!response.ok) throw new Error('mark-read-' + response.status);
      if (badge) badge.remove();
      loaded = false;
      await loadNotifications(true);
      setSummary('Notificações marcadas como lidas.');
    } catch (err) {
      setSummary('Não foi possível marcar como lidas.');
    }
  }

  document.addEventListener('click', function (event) {
    var toggle = event.target.closest && event.target.closest('[data-notifications-toggle]');
    if (toggle) loadNotifications(false);
  });

  if (markRead) {
    markRead.addEventListener('click', function (event) {
      event.preventDefault();
      markAllRead();
    });
  }

  // ─── Som + alerta de notificação NOVA (Victor 29/05: "as notificações devem fazer som no PC") ───
  // Antes o sininho era 100% silencioso (só carregava ao clicar). Agora faz polling leve,
  // toca um chime (Web Audio, sem asset) e dispara uma notificação de desktop (com som do SO)
  // quando chega algo novo não-lido — ex.: patch notes de hotfix.
  var seenIds = null;            // null = baseline ainda não estabelecido (não toca som na 1ª carga)
  var POLL_MS = 45000;           // 45s — acima do mínimo de 10s recomendado

  function notifKey(i) { return String(i.id != null ? i.id : ((i.title || '') + '|' + (i.time_ago || ''))); }

  function playChime() {
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      var ctx = playChime._ctx || (playChime._ctx = new Ctx());
      if (ctx.state === 'suspended') ctx.resume();
      var o = ctx.createOscillator(), g = ctx.createGain();
      o.connect(g); g.connect(ctx.destination);
      o.type = 'sine'; o.frequency.setValueAtTime(880, ctx.currentTime);
      o.frequency.setValueAtTime(1175, ctx.currentTime + 0.12);
      g.gain.setValueAtTime(0.0001, ctx.currentTime);
      g.gain.exponentialRampToValueAtTime(0.13, ctx.currentTime + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.4);
      o.start(); o.stop(ctx.currentTime + 0.42);
    } catch (e) {}
  }

  function desktopNotify(item) {
    try {
      if (!('Notification' in window) || Notification.permission !== 'granted') return;
      var n = new Notification(item.title || 'CaseHub', {
        body: item.message || '',
        tag: 'casehub-notif-' + notifKey(item),
        icon: '/static/img/favicon.svg'
      });
      n.onclick = function () { window.focus(); if (item.action_url) location.href = item.action_url; try { n.close(); } catch (e) {} };
    } catch (e) {}
  }

  async function pollForNew() {
    try {
      var resp = await fetch(prefix + '/api/notifications/recent?limit=5', { credentials: 'same-origin' });
      if (!resp.ok) return;
      var data = await resp.json();
      var items = Array.isArray(data.notifications) ? data.notifications : [];
      var unread = items.filter(function (i) { return !i.is_read; });
      if (seenIds === null) { seenIds = {}; unread.forEach(function (i) { seenIds[notifKey(i)] = 1; }); return; } // baseline silencioso
      var fresh = unread.filter(function (i) { return !seenIds[notifKey(i)]; });
      if (fresh.length) {
        fresh.forEach(function (i) { seenIds[notifKey(i)] = 1; });
        playChime();
        desktopNotify(fresh[0]);
        if (badge) { badge.textContent = String((parseInt(badge.textContent, 10) || 0) + fresh.length); }
        loaded = false; // força recarregar a lista no próximo open do sininho
      }
    } catch (e) {}
  }

  // Aquece o AudioContext + pede permissão de desktop no 1º clique (gesto do usuário — exigência dos browsers)
  document.addEventListener('click', function warmup() {
    try { if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission(); } catch (e) {}
    try {
      var Ctx = window.AudioContext || window.webkitAudioContext;
      if (Ctx) { if (!playChime._ctx) playChime._ctx = new Ctx(); if (playChime._ctx.state === 'suspended') playChime._ctx.resume(); }
    } catch (e) {}
  }, { once: true });

  setInterval(pollForNew, POLL_MS);
  pollForNew(); // estabelece o baseline já
})();
