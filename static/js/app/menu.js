/* CaseHub App · Generic open/close menu controller
 * Used by topbar user dropdown + any [data-menu] dropdown.
 *
 * <button data-menu-toggle="user-menu">…</button>
 * <div id="user-menu" class="ch-menu">…</div>
 */
(function () {
  'use strict';

  function close(menu) {
    menu.setAttribute('data-open', 'false');
    menu.removeAttribute('data-open');
    var trig = document.querySelector('[data-menu-toggle="' + menu.id + '"]');
    if (trig) trig.setAttribute('aria-expanded', 'false');
  }
  function open(menu) {
    closeAll();
    menu.setAttribute('data-open', 'true');
    var trig = document.querySelector('[data-menu-toggle="' + menu.id + '"]');
    if (trig) trig.setAttribute('aria-expanded', 'true');
    var first = menu.querySelector('.ch-menu__item');
    if (first) try { first.focus({ preventScroll: true }); } catch (_) {}
  }
  function closeAll() {
    document.querySelectorAll('.ch-menu[data-open="true"]').forEach(close);
  }

  document.addEventListener('click', function (e) {
    var toggle = e.target.closest && e.target.closest('[data-menu-toggle]');
    if (toggle) {
      e.preventDefault();
      var id = toggle.getAttribute('data-menu-toggle');
      var menu = document.getElementById(id);
      if (!menu) return;
      if (menu.getAttribute('data-open') === 'true') close(menu);
      else open(menu);
      return;
    }
    // click outside any open menu → close
    var openMenu = document.querySelector('.ch-menu[data-open="true"]');
    if (openMenu && !openMenu.contains(e.target)) closeAll();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeAll();
  });
})();
