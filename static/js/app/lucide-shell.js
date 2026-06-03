(function () {
  'use strict';

  function mountLucide() {
    if (!window.lucide || typeof window.lucide.createIcons !== 'function') return;
    window.lucide.createIcons({
      attrs: {
        'aria-hidden': 'true',
        focusable: 'false'
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountLucide);
  } else {
    mountLucide();
  }

  window.CHLucide = { mount: mountLucide };
})();
