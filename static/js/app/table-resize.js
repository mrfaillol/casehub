(function () {
  'use strict';

  var MIN_WIDTH = 56;
  var STORAGE_PREFIX = 'ch-col-widths:';
  var DESKTOP_QUERY = '(min-width: 721px)';
  var desktopMq = window.matchMedia ? window.matchMedia(DESKTOP_QUERY) : null;

  function isDesktopTableMode() {
    return desktopMq ? desktopMq.matches : window.innerWidth > 720;
  }

  function toArray(list) {
    return Array.prototype.slice.call(list || []);
  }

  function tableIndex(table) {
    return toArray(document.querySelectorAll('.ch-table')).indexOf(table);
  }

  function pageKey() {
    var bodyPage = document.body && document.body.dataset ? document.body.dataset.page : '';
    return bodyPage || window.location.pathname || 'page';
  }

  function tableKey(table) {
    var id = table.id || ('t' + tableIndex(table));
    return STORAGE_PREFIX + window.location.host + ':' + pageKey() + ':' + id;
  }

  function ensureColgroup(table) {
    var existing = table.querySelector('colgroup');
    var headers = table.querySelectorAll('thead th');
    if (!headers.length) return null;

    var colgroup = existing || document.createElement('colgroup');
    while (colgroup.children.length < headers.length) {
      colgroup.appendChild(document.createElement('col'));
    }

    if (!existing) {
      var anchor = table.querySelector('thead, tbody, tfoot');
      table.insertBefore(colgroup, anchor || table.firstChild);
    }
    return colgroup;
  }

  function getCols(table) {
    var colgroup = ensureColgroup(table);
    return colgroup ? toArray(colgroup.querySelectorAll('col')) : [];
  }

  function readWidths(table) {
    try {
      var raw = localStorage.getItem(tableKey(table));
      var parsed = raw ? JSON.parse(raw) : null;
      return Array.isArray(parsed) ? parsed : null;
    } catch (e) {
      return null;
    }
  }

  function saveWidths(table) {
    var widths = getCols(table).map(function (col) {
      return col.style.width || '';
    });
    try {
      localStorage.setItem(tableKey(table), JSON.stringify(widths));
    } catch (e) {}
  }

  function restoreWidths(table) {
    var widths = readWidths(table);
    if (!widths) return;

    getCols(table).forEach(function (col, index) {
      if (widths[index]) col.style.width = widths[index];
    });
  }

  function pixelWidth(col, th) {
    return parseFloat(col.style.width) || th.getBoundingClientRect().width || 80;
  }

  function freezeWidths(headers, cols) {
    headers.forEach(function (th, index) {
      if (!cols[index] || cols[index].style.width) return;
      cols[index].style.width = Math.round(pixelWidth(cols[index], th)) + 'px';
    });
  }

  function bindHandle(table, th, col, nextTh, nextCol) {
    if (th.__chColResize) return;
    th.__chColResize = true;

    var handle = document.createElement('span');
    handle.className = 'ch-col-resize-handle';
    handle.setAttribute('aria-hidden', 'true');
    th.appendChild(handle);

    handle.addEventListener('click', function (event) {
      event.preventDefault();
      event.stopPropagation();
    });

    handle.addEventListener('mousedown', function (event) {
      if (!isDesktopTableMode()) return;

      event.preventDefault();
      event.stopPropagation();

      var startX = event.clientX;
      var startWidth = pixelWidth(col, th);
      var nextStartWidth = nextCol && nextTh ? pixelWidth(nextCol, nextTh) : null;
      var previousCursor = document.body.style.cursor;
      var previousSelect = document.body.style.userSelect;

      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      handle.classList.add('is-dragging');

      function onMove(moveEvent) {
        var delta = moveEvent.clientX - startX;
        if (nextCol && nextStartWidth != null) {
          delta = Math.max(MIN_WIDTH - startWidth, Math.min(delta, nextStartWidth - MIN_WIDTH));
          col.style.width = Math.round(startWidth + delta) + 'px';
          nextCol.style.width = Math.round(nextStartWidth - delta) + 'px';
          return;
        }

        col.style.width = Math.round(Math.max(MIN_WIDTH, startWidth + delta)) + 'px';
      }

      function onUp() {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        document.body.style.cursor = previousCursor;
        document.body.style.userSelect = previousSelect;
        handle.classList.remove('is-dragging');
        saveWidths(table);
      }

      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  }

  function initTable(table) {
    if (table.__chTableResize) return;
    var headers = toArray(table.querySelectorAll('thead th'));
    if (!headers.length) return;

    restoreWidths(table);
    var cols = getCols(table);
    freezeWidths(headers, cols);
    headers.forEach(function (th, index) {
      if (cols[index]) bindHandle(table, th, cols[index], headers[index + 1], cols[index + 1]);
    });
    table.__chTableResize = true;
  }

  function init() {
    if (!isDesktopTableMode()) return;
    toArray(document.querySelectorAll('.ch-table')).forEach(initTable);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  if (desktopMq && desktopMq.addEventListener) {
    desktopMq.addEventListener('change', init);
  } else if (desktopMq && desktopMq.addListener) {
    desktopMq.addListener(init);
  }
})();
