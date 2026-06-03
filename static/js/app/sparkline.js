/* CaseHub App · Sparkline (vanilla SVG, GPU-friendly).
 * Usage: <span class="ch-sparkline" data-spark="1,3,2,5,4,7,6,9"></span>
 *        <span class="ch-sparkline" data-spark="..." data-area="true"></span>
 *
 * Auto-renders on DOMContentLoaded; re-mount on dynamic content via CHSpark.mount().
 */
(function () {
  'use strict';

  var NS = 'http://www.w3.org/2000/svg';

  function build(values, opts) {
    if (!values || !values.length) return null;
    var w = opts.width || 90;
    var h = opts.height || 36;
    var pad = 2;
    var area = !!opts.area;
    var min = Math.min.apply(null, values);
    var max = Math.max.apply(null, values);
    var range = max - min || 1;
    var stepX = (w - pad * 2) / (values.length - 1 || 1);
    var pts = values.map(function (v, i) {
      var x = pad + i * stepX;
      var y = h - pad - ((v - min) / range) * (h - pad * 2);
      return [x, y];
    });

    var d = 'M' + pts[0][0].toFixed(2) + ' ' + pts[0][1].toFixed(2);
    for (var i = 1; i < pts.length; i++) {
      d += ' L' + pts[i][0].toFixed(2) + ' ' + pts[i][1].toFixed(2);
    }

    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('class', 'ch-sparkline');
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('width', w);
    svg.setAttribute('height', h);

    if (area) {
      var areaD = d + ' L' + pts[pts.length - 1][0] + ' ' + (h - pad) +
                  ' L' + pts[0][0] + ' ' + (h - pad) + ' Z';
      var areaEl = document.createElementNS(NS, 'path');
      areaEl.setAttribute('d', areaD);
      areaEl.setAttribute('class', 'area');
      svg.appendChild(areaEl);
    }

    var line = document.createElementNS(NS, 'path');
    line.setAttribute('d', d);
    svg.appendChild(line);

    var last = pts[pts.length - 1];
    var dot = document.createElementNS(NS, 'circle');
    dot.setAttribute('cx', last[0]);
    dot.setAttribute('cy', last[1]);
    dot.setAttribute('r', 2.25);
    svg.appendChild(dot);

    return svg;
  }

  function parse(str) {
    if (!str) return [];
    return str.split(/[,\s]+/).map(function (s) { return parseFloat(s); }).filter(function (n) { return !isNaN(n); });
  }

  function mount(scope) {
    var root = scope || document;
    root.querySelectorAll('.ch-sparkline[data-spark]:not([data-mounted])').forEach(function (el) {
      var values = parse(el.getAttribute('data-spark'));
      if (!values.length) return;
      var area = el.getAttribute('data-area') === 'true';
      var w = parseFloat(el.getAttribute('data-width') || el.clientWidth || 90);
      var h = parseFloat(el.getAttribute('data-height') || el.clientHeight || 36);
      var s = build(values, { width: w, height: h, area: area });
      if (s) {
        el.innerHTML = '';
        el.appendChild(s);
        el.setAttribute('data-mounted', 'true');
      }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { mount(); });
  else mount();

  window.CHSpark = { mount: mount, build: build };
})();
