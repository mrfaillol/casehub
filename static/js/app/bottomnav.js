/* CaseHub App · Bottom-nav controller — abas dinâmicas no mobile
 * (29/05 Victor):
 *  - As abas abertas PREENCHEM a largura da nav (flex). 1 aba ocupa tudo; N dividem igual.
 *  - LIMITE por tela: maxTabs = largura / largura-mínima. Tentar abrir além → avisa pra fechar.
 *  - FECHAR: arraste a aba pra CIMA ou pra BAIXO (estilo balãozinho do Messenger). Sem × visível.
 *    Ao fechar, as restantes redistribuem o espaço.
 *  - "Painel" (dashboard) é fixo (sem ×, sem drag). Escolha persistida por dispositivo. Desktop intacto.
 */
(function () {
  'use strict';

  var STORE_KEY = 'ch_nav_pinned_v1';
  // Largura-mínima por aba (ícone + rótulo curto, layout vertical no mobile).
  // 58px → cabem mais abas antes de saturar a pílula; o excedente entra no
  // overflow-x scroll (não bloqueia mais). (onda2: Painel virou bolha separada.)
  var MIN_TAB_W = 58;
  // Bolha "Mais" (.ch-bottomnav-more) fica FORA da pílula, à direita: largura
  // = --bottomnav-h (64px) + o gap da .ch-bottomnav-row (--space-2 ≈ 8px). A
  // bolha "Painel" (.ch-bottomnav-home) à esquerda é simétrica → reservamos as
  // duas bolhas + gaps ao calcular quantas abas cabem na pílula.
  var MORE_BUBBLE_W = 64;
  var BUBBLE_GAP = 8;
  var mqMobile = (window.matchMedia)
    ? window.matchMedia('(max-width: 879px)')
    : { matches: false, addEventListener: function () {}, addListener: function () {} };

  // ─── helpers ───
  function itemKey(el) { return el.getAttribute('data-route-key') || el.getAttribute('data-nav-key') || el.getAttribute('href') || ''; }
  function isDashboard(el) { return el.getAttribute('data-pinned') === 'true' || /\/dashboard\/?$/.test(el.getAttribute('href') || ''); }
  function pathOf(href) { try { return new URL(href, location.origin).pathname.replace(/\/+$/, ''); } catch (e) { return (href || '').replace(/\/+$/, ''); } }
  function loadPinned() {
    try { var raw = JSON.parse(localStorage.getItem(STORE_KEY) || 'null'); if (Array.isArray(raw) && raw.length) return raw; } catch (e) {}
    return null;
  }
  function savePinned(list) { try { localStorage.setItem(STORE_KEY, JSON.stringify(list)); } catch (e) {} }
  function warn(msg) {
    try { if (window.toast && typeof window.toast.warning === 'function') { window.toast.warning(msg); return; } } catch (e) {}
    try { if (window.toast && typeof window.toast.info === 'function') { window.toast.info(msg); return; } } catch (e) {}
    try { window.alert(msg); } catch (e) {}
  }

  function catalog(nav) {
    return Array.prototype.slice.call(nav.querySelectorAll('.ch-bottomnav__item:not(.ch-bottomnav__item--more)'));
  }
  function defaultPinned(items) {
    var d = [];
    items.forEach(function (el) { if (el.classList.contains('ch-bottomnav__item--mobile-primary')) d.push(itemKey(el)); });
    return d.length ? d : items.slice(0, 4).map(itemKey);
  }
  function activeKey(nav) {
    var a = nav.querySelector('.ch-bottomnav__item.is-active:not(.ch-bottomnav__item--more)');
    return a ? itemKey(a) : null;
  }

  // Quantas abas cabem CONFORTAVELMENTE nesta tela. Já não é um teto rígido:
  // serve só pra decidir o ponto a partir do qual a pílula passa a rolar
  // (overflow-x). Descontamos as bolhas externas (Painel à esquerda + Mais à
  // direita) e seus gaps — elas vivem fora da pílula e não disputam o espaço
  // das abas. (onda2 Victor: nunca bloquear, deixar rolar.)
  function maxTabs(nav) {
    var sc = nav.querySelector('.ch-bottomnav__scroller') || nav;
    var w = sc.clientWidth;
    if (!w) {
      // Fallback antes do layout: largura da viewport menos as duas bolhas
      // externas (Painel + Mais) e os gaps entre elas e a pílula.
      w = window.innerWidth - (MORE_BUBBLE_W + BUBBLE_GAP) * 2;
    }
    return Math.max(2, Math.floor(w / MIN_TAB_W));
  }

  // ─── sem × visível — fechar é SÓ por gesto (arrastar a aba pra cima/baixo).
  //     (Victor 29/05: "descartar o X evidente e deixar só o gesto pra fechar".) ───
  function stripRemoveBtn(el) {
    var x = el.querySelector('.ch-nav-remove'); if (x) x.remove();
  }

  // ─── arrastar pra fora (pra baixo) → fecha (estilo chat-head do Messenger) ───
  function attachDrag(el, nav) {
    if (el.__chDrag || isDashboard(el)) return;
    el.__chDrag = true;
    var startX = null, startY = null, dragging = false, justDragged = false;
    el.addEventListener('pointerdown', function (e) {
      if (!mqMobile.matches || (e.target.closest && e.target.closest('.ch-nav-remove'))) return;
      startX = e.clientX; startY = e.clientY; dragging = false;
    });
    el.addEventListener('pointermove', function (e) {
      if (startY == null) return;
      var dx = e.clientX - startX, dy = e.clientY - startY;
      if (!dragging && Math.abs(dy) > 10 && Math.abs(dy) > Math.abs(dx)) {
        dragging = true;
        el.classList.add('ch-nav-dragging');
        try { el.setPointerCapture(e.pointerId); } catch (er) {}
      }
      if (dragging) {
        e.preventDefault();
        var d = dy; // pode arrastar pra baixo (positivo) ou pra cima
        el.style.transform = 'translateY(' + d + 'px) scale(' + Math.max(0.8, 1 - Math.abs(d) / 360) + ')';
        el.style.opacity = String(Math.max(0.12, 1 - Math.abs(d) / 100));
        el.classList.toggle('ch-nav-will-close', Math.abs(d) > 44);
      }
    });
    function end(e) {
      if (startY == null) return;
      var dy = ((e && e.clientY) || startY) - startY;
      var wasDragging = dragging;
      startY = null; startX = null; dragging = false;
      el.classList.remove('ch-nav-dragging', 'ch-nav-will-close');
      el.style.transform = ''; el.style.opacity = '';
      if (wasDragging) {
        justDragged = true;
        setTimeout(function () { justDragged = false; }, 360);
        if (Math.abs(dy) > 44) removeKey(nav, itemKey(el)); // arrastou pra fora → fecha
      }
    }
    el.addEventListener('pointerup', end);
    el.addEventListener('pointercancel', end);
    el.addEventListener('click', function (e) { if (justDragged) { e.preventDefault(); e.stopPropagation(); } }, true);
  }

  // ─── mutações ───
  function removeKey(nav, key) {
    var pinned = loadPinned() || defaultPinned(catalog(nav));
    var i = pinned.indexOf(key);
    if (i >= 0) { pinned.splice(i, 1); savePinned(pinned); render(nav); }
  }

  // ─── menu "Mais": fixa o módulo na barra (respeitando o limite) + navega ───
  function bindMoreMenu(nav) {
    var menu = document.getElementById('ch-bottom-more-menu');
    if (!menu || menu.__chNavBound) return;
    menu.__chNavBound = true;
    var byPath = {};
    catalog(nav).forEach(function (el) { var href = el.getAttribute('href'); if (href) byPath[pathOf(href)] = itemKey(el); });
    menu.addEventListener('click', function (e) {
      var a = e.target.closest && e.target.closest('a[href]');
      if (!a || !menu.contains(a)) return;
      var key = byPath[pathOf(a.getAttribute('href'))];
      if (!key) return; // link utilitário → navega normal
      var pinned = loadPinned() || defaultPinned(catalog(nav));
      if (pinned.indexOf(key) >= 0) return; // já é aba → navega normal
      // onda2 (Victor): NÃO bloqueamos mais com aviso. A pílula sustenta quantas
      // abas o usuário quiser — o que passar da largura confortável (maxTabs)
      // entra no overflow-x scroll. Só sinalizamos (sem barrar) quando a barra
      // já vai precisar rolar, pra dar feedback honesto.
      if (mqMobile.matches && pinned.length >= maxTabs(nav)) {
        try { if (window.toast && typeof window.toast.info === 'function') window.toast.info('Aba adicionada — arraste a barra pro lado pra ver todas.'); } catch (e) {}
      }
      pinned.push(key); savePinned(pinned); // navega normal; no reload aparece fixada e preenchendo
    });
  }

  // ─── render: abas mostradas PREENCHEM a largura ───
  function render(nav) {
    var items = catalog(nav);
    if (!mqMobile.matches) {
      items.forEach(function (el) {
        el.style.display = ''; el.style.flex = ''; el.style.minWidth = ''; el.style.transform = ''; el.style.opacity = '';
        el.classList.remove('ch-nav-pinned', 'ch-nav-dragging', 'ch-nav-will-close');
        var r = el.querySelector('.ch-nav-remove'); if (r) r.remove();
      });
      return;
    }
    var pinned = loadPinned() || defaultPinned(items);
    var act = activeKey(nav);
    // onda3 (Victor 09/06): abrir um módulo o FIXA como aba (modelo "abas de
    // navegador") — a rota ativa que ainda não é aba entra na lista persistida,
    // então acumula em vez de sumir ao trocar de página. Fechar = arrastar.
    if (act && pinned.indexOf(act) < 0) {
      var actEl = nav.querySelector('.ch-bottomnav__item.is-active:not(.ch-bottomnav__item--more)');
      if (actEl && !isDashboard(actEl)) { pinned.push(act); savePinned(pinned); }
    }
    var shown = pinned.slice();
    if (act && shown.indexOf(act) < 0) shown.push(act); // rota ativa sempre visível
    // onda2: a pílula sustenta MAIS abas. Enquanto cabem (≤ maxTabs) elas
    // dividem a largura igual e PREENCHEM a barra (flex 1 1 0). Quando passam
    // do confortável, ligamos o modo overflow: cada aba ganha uma largura
    // mínima e a barra rola na horizontal (overflow-x) em vez de espremer
    // tudo num grão ilegível. CSS lê a classe .ch-bottomnav--overflow.
    var scroller = nav.querySelector('.ch-bottomnav__scroller') || nav;
    var overflow = mqMobile.matches && shown.length > maxTabs(nav);
    nav.classList.toggle('ch-bottomnav--overflow', overflow);
    items.forEach(function (el) {
      var k = itemKey(el);
      var on = shown.indexOf(k) >= 0;
      el.style.display = on ? 'inline-flex' : 'none';
      if (on) {
        // Limpa resíduo de um arrasto interrompido (pointercancel sem 'end'):
        // sem isto a aba fica "presa" encolhida/transparente (bug visual).
        el.style.transform = '';
        el.style.opacity = '';
        el.classList.remove('ch-nav-dragging', 'ch-nav-will-close');
      }
      if (!on) {
        el.style.flex = '';
        el.style.minWidth = '';
      } else if (overflow) {
        // Rolagem horizontal: largura mínima fixa por aba (não encolhe).
        el.style.flex = '0 0 ' + MIN_TAB_W + 'px';
        el.style.minWidth = MIN_TAB_W + 'px';
      } else {
        el.style.flex = '1 1 0';   // ← preenche e divide igual
        el.style.minWidth = '0';
      }
      el.classList.toggle('ch-nav-pinned', pinned.indexOf(k) >= 0);
      stripRemoveBtn(el);
      attachDrag(el, nav);
    });
  }

  function init() {
    document.querySelectorAll('.ch-bottomnav').forEach(function (nav) {
      if (nav.__chBN) { render(nav); return; }
      nav.__chBN = true;
      window.addEventListener('resize', function () { render(nav); }, { passive: true });
      var onMq = function () { render(nav); };
      if (mqMobile.addEventListener) mqMobile.addEventListener('change', onMq);
      else if (mqMobile.addListener) mqMobile.addListener(onMq);
      bindMoreMenu(nav);
      render(nav);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window.CHBottomNav = { init: init };
})();
