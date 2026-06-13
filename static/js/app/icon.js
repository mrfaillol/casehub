/* CaseHub App · Inline SVG icon set.
 * Usage: <span data-icon="bell"></span> or window.CHIcon.svg("bell").
 * No external sprite, no Font Awesome.
 *
 * All icons drawn on 24x24 viewBox, stroke 1.75, line-cap round, no fill (uses currentColor).
 */
(function () {
  'use strict';

  var P = {
    /* nav / shell */
    dashboard:     'M3 12L12 4l9 8M5 10v10h14V10',
    clients:       'M16 11a4 4 0 1 0-8 0 4 4 0 0 0 8 0Zm-12 9a8 8 0 0 1 16 0',
    processes:     'M4 6h16M4 12h10M4 18h16M18 9l3 3-3 3',
    tasks:         'M4 6l2 2 4-4M4 12l2 2 4-4M4 18l2 2 4-4M14 6h6M14 12h6M14 18h6',
    kanban:        'M4 4v16M10 4v10M16 4v14M4 4h18',
    controladoria: 'M4 20V8m4 12V4m4 16V12m4 8V6m4 14v-9',
    agenda:        'M4 7h16M4 12h16M4 17h10M6 3v4M18 3v4',
    calendar:      'M4 7h16M4 7l1-3h14l1 3M4 7v13h16V7M9 11h2M15 11h2M9 15h2M15 15h2',
    billing:       'M4 6h16v12H4zM4 10h16M8 14h2',
    docs:          'M6 3h9l5 5v13H6zM15 3v5h5',
    settings:      'M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2zM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z',
    bell:          'M6 9a6 6 0 1 1 12 0c0 5 2 7 2 7H4s2-2 2-7Zm4 10a2 2 0 0 0 4 0',
    search:        'M10 4a6 6 0 1 0 0 12 6 6 0 0 0 0-12Zm5 11 5 5',
    plus:          'M12 5v14M5 12h14',
    menu:          'M4 6h16M4 12h16M4 18h16',
    grip:          'M9 5h.01M15 5h.01M9 12h.01M15 12h.01M9 19h.01M15 19h.01',
    chevron_right: 'M9 6l6 6-6 6',
    chevron_down:  'M6 9l6 6 6-6',
    chevron_up:    'M6 15l6-6 6 6',
    arrow_up:      'M12 19V5M5 12l7-7 7 7',
    arrow_down:    'M12 5v14M19 12l-7 7-7-7',
    sun:           'M12 4V2M12 22v-2M4 12H2M22 12h-2M5.6 5.6 4.2 4.2M19.8 19.8l-1.4-1.4M5.6 18.4l-1.4 1.4M19.8 4.2l-1.4 1.4M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10Z',
    moon:          'M21 13.5A9 9 0 1 1 10.5 3a7 7 0 0 0 10.5 10.5Z',
    leaf:          'M5 19c0-7 6-13 14-14-1 8-7 14-14 14Zm0 0L17 7',
    logout:        'M15 4h4v16h-4M10 8l-4 4 4 4M6 12h11',
    user:          'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-8 9a8 8 0 0 1 16 0',
    bolt:          'M13 2L4 14h7l-1 8 9-12h-7l1-8Z',
    check:         'M5 12l5 5 9-11',
    edit:          'M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3ZM13.5 6.5l3 3',
    trash:         'M4 7h16M10 11v6M14 11v6M6 7l1 14h10l1-14M9 7l1-3h4l1 3',
    x:             'M6 6l12 12M18 6 6 18',
    folder:        'M3 7v11a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-7l-2-3H5a2 2 0 0 0-2 2Z',
    file:          'M7 3h7l5 5v13H7zM14 3v5h5',
    inbox:         'M3 4h18l-2 10H5L3 4Zm0 10v6h18v-6m-6 0a3 3 0 1 1-6 0',
    flame:         'M12 21c-4 0-7-3-7-7 0-3 2-5 3-7 0 2 1 3 2 3 1-2-1-4 2-7 2 2 4 4 4 8 1 1 2 2 2 4 0 4-3 6-6 6Z',
    target:        'M12 5a7 7 0 1 1 0 14 7 7 0 0 1 0-14Zm0 4a3 3 0 1 1 0 6 3 3 0 0 1 0-6Z',
    chart:         'M4 20V10M10 20V4M16 20v-7M22 20v-4',
    /* feedback / actions / integrations */
    alert_triangle:'M12 3 2 20h20L12 3ZM12 10v5M12 18h.01',
    arrow_left:    'M19 12H5M11 6l-6 6 6 6',
    expand:        'M9 4H4v5M15 4h5v5M9 20H4v-5M15 20h5v-5',
    external_link: 'M14 4h6v6M20 4l-9 9M19 14v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
    mail:          'M3 6h18v12H3zM3 7l9 6 9-6',
    send:          'M21 3 3 11l7 3 3 7 8-18ZM10 14l11-11',
    shield:        'M12 3 5 6v5c0 4 3 7 7 9 4-2 7-5 7-9V6l-7-3Z',
    /* brand cube (special; not from icon set) — used as logo mark */
    cube:          'M12 2 3 7v10l9 5 9-5V7l-9-5Zm0 0v20M3 7l9 5 9-5'
  };

  function svg(name, attrs) {
    var d = P[name];
    if (!d) d = P.dashboard;
    var a = attrs || {};
    var size = a.size || 18;
    var stroke = a.stroke || 1.75;
    var cls = a.class || '';
    var ns = 'http://www.w3.org/2000/svg';
    var s = document.createElementNS(ns, 'svg');
    s.setAttribute('xmlns', ns);
    s.setAttribute('viewBox', '0 0 24 24');
    s.setAttribute('width', size);
    s.setAttribute('height', size);
    s.setAttribute('fill', 'none');
    s.setAttribute('stroke', 'currentColor');
    s.setAttribute('stroke-width', stroke);
    s.setAttribute('stroke-linecap', 'round');
    s.setAttribute('stroke-linejoin', 'round');
    s.setAttribute('aria-hidden', 'true');
    if (cls) s.setAttribute('class', cls);
    var p = document.createElementNS(ns, 'path');
    p.setAttribute('d', d);
    s.appendChild(p);
    return s;
  }

  function htmlFor(name, attrs) {
    var d = P[name] || P.dashboard;
    var a = attrs || {};
    var size = a.size || 18;
    var stroke = a.stroke || 1.75;
    var cls = a.class || '';
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="' + size + '" height="' + size +
      '" fill="none" stroke="currentColor" stroke-width="' + stroke + '" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"' +
      (cls ? ' class="' + cls + '"' : '') + '><path d="' + d + '"/></svg>';
  }

  function mount() {
    document.querySelectorAll('[data-icon]').forEach(function (el) {
      if (el.__chIcon) return;
      el.__chIcon = true;
      var name = el.getAttribute('data-icon');
      var size = parseInt(el.getAttribute('data-icon-size') || '18', 10);
      var stroke = parseFloat(el.getAttribute('data-icon-stroke') || '1.75');
      el.innerHTML = '';
      el.appendChild(svg(name, { size: size, stroke: stroke }));
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();

  window.CHIcon = { svg: svg, html: htmlFor, mount: mount, names: Object.keys(P) };
})();
