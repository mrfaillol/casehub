(function () {
  'use strict';

  function qs(selector, root) {
    return (root || document).querySelector(selector);
  }

  function qsa(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }

  function initTabs() {
    var track = qs('.casehub-basic-tabs__track');
    if (!track) return;

    var orderKey = 'casehub_basic_tab_order';
    var activeKey = 'casehub_basic_closed_tabs';

    try {
      var order = JSON.parse(localStorage.getItem(orderKey) || '[]');
      if (order.length) {
        order.forEach(function (key) {
          var tab = qs('[data-tab-key="' + key + '"]', track);
          if (tab) track.appendChild(tab);
        });
      }
      var closed = JSON.parse(localStorage.getItem(activeKey) || '[]');
      closed.forEach(function (key) {
        var tab = qs('[data-tab-key="' + key + '"]', track);
        if (tab && !tab.classList.contains('is-active')) tab.hidden = true;
      });
    } catch (_) {}

    var dragged = null;

    qsa('.casehub-basic-tabs__tab', track).forEach(function (tab) {
      tab.addEventListener('dragstart', function (event) {
        dragged = tab;
        tab.classList.add('is-dragging');
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', tab.dataset.tabKey || '');
      });

      tab.addEventListener('dragend', function () {
        tab.classList.remove('is-dragging');
        qsa('.is-drop-target', track).forEach(function (el) { el.classList.remove('is-drop-target'); });
        dragged = null;
        try {
          localStorage.setItem(orderKey, JSON.stringify(qsa('.casehub-basic-tabs__tab', track).map(function (el) {
            return el.dataset.tabKey;
          })));
        } catch (_) {}
      });

      tab.addEventListener('dragover', function (event) {
        if (!dragged || dragged === tab) return;
        event.preventDefault();
        tab.classList.add('is-drop-target');
        var rect = tab.getBoundingClientRect();
        var after = event.clientX > rect.left + rect.width / 2;
        track.insertBefore(dragged, after ? tab.nextSibling : tab);
      });

      tab.addEventListener('dragleave', function () {
        tab.classList.remove('is-drop-target');
      });
    });

    track.addEventListener('click', function (event) {
      var close = event.target.closest('[data-close-tab]');
      if (!close) return;
      event.preventDefault();
      event.stopPropagation();
      var key = close.dataset.closeTab;
      var tab = qs('[data-tab-key="' + key + '"]', track);
      if (!tab || tab.classList.contains('is-active')) return;
      tab.hidden = true;
      try {
        var closed = JSON.parse(localStorage.getItem(activeKey) || '[]');
        if (closed.indexOf(key) < 0) closed.push(key);
        localStorage.setItem(activeKey, JSON.stringify(closed));
      } catch (_) {}
    });
  }

  function initProfileMenu() {
    var button = qs('[data-casehub-profile-toggle]');
    var menu = qs('#casehub-basic-profile-menu');
    if (!button || !menu) return;

    function setOpen(open) {
      menu.hidden = !open;
      button.classList.toggle('is-active', open);
      button.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    button.addEventListener('click', function (event) {
      event.stopPropagation();
      setOpen(menu.hidden);
    });

    document.addEventListener('click', function (event) {
      if (menu.hidden) return;
      if (button.contains(event.target) || menu.contains(event.target)) return;
      setOpen(false);
    });

    var themeToggle = qs('[data-casehub-theme-toggle]', menu);
    if (themeToggle) {
      themeToggle.addEventListener('click', function () {
        var html = document.documentElement;
        var next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-theme', next);
        try { localStorage.setItem('theme', next); } catch (_) {}
        setOpen(false);
      });
    }
  }

  function initResourcePanel() {
    var toggle = qs('[data-casehub-resource-toggle]');
    var panel = qs('[data-casehub-resource-panel]');
    var perfToggle = qs('[data-casehub-perf-toggle]');
    var ecoStorageKey = 'casehub-basic-eco-mode';
    var compactQuery = window.matchMedia ? window.matchMedia('(max-width: 1040px)') : null;

    function hasEcoPreference() {
      try {
        return localStorage.getItem(ecoStorageKey) !== null;
      } catch (_) {
        return false;
      }
    }

    function applyCompactPerformance() {
      var compact = compactQuery ? compactQuery.matches : window.innerWidth <= 1040;
      document.body.classList.toggle('casehub-basic-compact-shell', compact);
      if (compact && !hasEcoPreference()) {
        document.body.classList.add('performance-mode');
      }
      if (perfToggle) {
        perfToggle.classList.toggle('is-active', document.body.classList.contains('performance-mode'));
        perfToggle.setAttribute('aria-pressed', document.body.classList.contains('performance-mode') ? 'true' : 'false');
      }
    }

    if (toggle && panel) {
      toggle.addEventListener('click', function () {
        var open = panel.hidden;
        panel.hidden = !open;
        toggle.classList.toggle('is-active', open);
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
    }
    if (perfToggle) {
      try {
        document.body.classList.toggle('performance-mode', localStorage.getItem(ecoStorageKey) === '1');
      } catch (_) {}
      perfToggle.classList.toggle('is-active', document.body.classList.contains('performance-mode'));
      perfToggle.setAttribute('aria-pressed', document.body.classList.contains('performance-mode') ? 'true' : 'false');
      perfToggle.addEventListener('click', function () {
        document.body.classList.toggle('performance-mode');
        var enabled = document.body.classList.contains('performance-mode');
        perfToggle.classList.toggle('is-active', enabled);
        perfToggle.setAttribute('aria-pressed', enabled ? 'true' : 'false');
        try { localStorage.setItem(ecoStorageKey, enabled ? '1' : '0'); } catch (_) {}
      });
    }
    applyCompactPerformance();
    if (compactQuery && compactQuery.addEventListener) {
      compactQuery.addEventListener('change', applyCompactPerformance);
    } else {
      window.addEventListener('resize', applyCompactPerformance);
    }

    var frames = [];
    var last = performance.now();
    var longTasks = { count: 0, total: 0 };
    var cls = 0;

    if ('PerformanceObserver' in window) {
      try {
        new PerformanceObserver(function (list) {
          list.getEntries().forEach(function (entry) {
            longTasks.count += 1;
            longTasks.total += entry.duration || 0;
          });
        }).observe({ type: 'longtask', buffered: true });
      } catch (_) {}
      try {
        new PerformanceObserver(function (list) {
          list.getEntries().forEach(function (entry) {
            if (!entry.hadRecentInput) cls += entry.value || 0;
          });
        }).observe({ type: 'layout-shift', buffered: true });
      } catch (_) {}
    }

    function tick(now) {
      frames.push(now - last);
      if (frames.length > 90) frames.shift();
      last = now;
      requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);

    function bytes(value) {
      if (!value) return '--';
      if (value > 1048576) return Math.round(value / 1048576) + ' MB';
      return Math.round(value / 1024) + ' KB';
    }

    setInterval(function () {
      if (!frames.length) return;
      var sorted = frames.slice().sort(function (a, b) { return a - b; });
      var p95 = sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))];
      var avg = frames.reduce(function (sum, v) { return sum + v; }, 0) / frames.length;
      var fps = Math.max(1, Math.round(1000 / avg));
      var memory = performance.memory;
      var nav = performance.getEntriesByType && performance.getEntriesByType('navigation')[0];
      var fpsEl = qs('[data-casehub-fps]');
      var p95El = qs('[data-casehub-frame-p95]');
      var heapEl = qs('[data-casehub-heap]');
      var domEl = qs('[data-casehub-dom-count]');
      var loadEl = qs('[data-casehub-load]');
      var longTasksEl = qs('[data-casehub-longtasks]');
      var resourcesEl = qs('[data-casehub-resource-count]');
      var clsEl = qs('[data-casehub-cls]');
      var ecoEl = qs('[data-casehub-eco-state]');
      var resourceEntries = performance.getEntriesByType ? performance.getEntriesByType('resource') : [];
      if (fpsEl) fpsEl.textContent = 'FPS ' + fps;
      if (p95El) p95El.textContent = p95.toFixed(1) + ' ms';
      if (heapEl) heapEl.textContent = memory ? bytes(memory.usedJSHeapSize) : '--';
      if (domEl) domEl.textContent = document.getElementsByTagName('*').length + ' nós';
      if (loadEl && nav) loadEl.textContent = Math.round(nav.duration) + ' ms';
      if (longTasksEl) longTasksEl.textContent = longTasks.count + ' / ' + Math.round(longTasks.total) + ' ms';
      if (resourcesEl) resourcesEl.textContent = resourceEntries.length + ' req';
      if (clsEl) clsEl.textContent = cls.toFixed(3);
      if (ecoEl) ecoEl.textContent = document.body.classList.contains('performance-mode') ? 'Ativo' : 'Normal';
    }, 700);
  }

  function initRailFocusMode() {
    var storageKey = 'casehub_basic_rail_collapsed';
    var toggles = qsa('[data-casehub-rail-toggle]');
    var peek = qs('.casehub-basic-rail-peek');
    if (!toggles.length) return;

    function setCollapsed(collapsed) {
      document.body.classList.toggle('casehub-rail-collapsed', collapsed);
      toggles.forEach(function (button) {
        button.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        var icon = qs('i', button);
        if (icon) {
          icon.classList.toggle('fa-angles-left', !collapsed);
          icon.classList.toggle('fa-angles-right', collapsed);
        }
      });
      if (peek) peek.hidden = !collapsed;
      try { localStorage.setItem(storageKey, collapsed ? '1' : '0'); } catch (_) {}
    }

    try {
      setCollapsed(localStorage.getItem(storageKey) === '1');
    } catch (_) {
      setCollapsed(false);
    }

    toggles.forEach(function (button) {
      button.addEventListener('click', function () {
        setCollapsed(!document.body.classList.contains('casehub-rail-collapsed'));
      });
    });
  }

  function initNeumorphicLabSync() {
    var storageKey = 'casehub-neumorphic-button-preset:v1';
    var channel = null;

    function px(value, fallback) {
      var number = Number(value);
      return Number.isFinite(number) ? number + 'px' : fallback;
    }

    function ms(value, fallback) {
      var number = Number(value);
      return Number.isFinite(number) ? number + 'ms' : fallback;
    }

    function applyPreset(payload) {
      if (!payload || !payload.tokens) return;
      var tokens = payload.tokens;
      var root = document.body && document.body.classList.contains('casehub-browser-basic')
        ? document.body
        : document.documentElement;
      var depth = Number(tokens.depth);
      var blur = Number(tokens.blur);
      var radius = Number(tokens.radius);
      root.style.setProperty('--nu-radius', px(radius, '10px'));
      root.style.setProperty('--nu-motion-duration', ms(tokens.duration, '150ms'));
      root.style.setProperty('--nu-press-lift', px(tokens.lift, '1px'));
      root.style.setProperty('--login-radius', px(radius, '8px'));
      root.style.setProperty('--login-motion-duration', ms(tokens.duration, '160ms'));
      root.style.setProperty('--login-press-lift', px(tokens.lift, '1px'));
      if (Number.isFinite(depth) && Number.isFinite(blur)) {
        var tightDepth = Math.max(2, Math.round(depth * 0.58));
        var tightBlur = Math.max(6, Math.round(blur * 0.62));
        root.style.setProperty(
          '--nu-raised',
          (-depth) + 'px ' + (-depth) + 'px ' + blur + 'px var(--nu-shadow-light), ' +
          depth + 'px ' + depth + 'px ' + blur + 'px var(--nu-shadow-dark)'
        );
        root.style.setProperty(
          '--nu-raised-tight',
          (-tightDepth) + 'px ' + (-tightDepth) + 'px ' + tightBlur + 'px var(--nu-shadow-light), ' +
          tightDepth + 'px ' + tightDepth + 'px ' + tightBlur + 'px var(--nu-shadow-dark)'
        );
        root.style.setProperty(
          '--login-shadow',
          depth + 'px ' + depth + 'px ' + blur + 'px rgba(164, 161, 153, 0.36), ' +
          (-depth) + 'px ' + (-depth) + 'px ' + blur + 'px rgba(255, 255, 255, 0.92)'
        );
        root.style.setProperty(
          '--login-inset',
          'inset ' + tightDepth + 'px ' + tightDepth + 'px ' + tightBlur + 'px rgba(164, 161, 153, 0.32), ' +
          'inset ' + (-tightDepth) + 'px ' + (-tightDepth) + 'px ' + tightBlur + 'px rgba(255, 255, 255, 0.76)'
        );
      }
      document.documentElement.dataset.casehubNuPreset = payload.preset || 'custom';
    }

    try {
      applyPreset(JSON.parse(localStorage.getItem(storageKey) || 'null'));
    } catch (_) {}

    window.addEventListener('storage', function (event) {
      if (event.key !== storageKey || !event.newValue) return;
      try { applyPreset(JSON.parse(event.newValue)); } catch (_) {}
    });

    if ('BroadcastChannel' in window) {
      channel = new BroadcastChannel('casehub-neumorphic-lab');
      channel.addEventListener('message', function (event) {
        if (event.data && event.data.type === 'casehub-neumorphic-preset') {
          applyPreset(event.data.payload);
        }
      });
    }
  }

  function initSoftNavigation() {
    if (window.__casehubBasicSoftNavigationBound) return;
    window.__casehubBasicSoftNavigationBound = true;

    var selectors = [
      '.casehub-basic-tabs__tab[href]',
      '.casehub-basic-rail__item[href]',
      '.casehub-basic-rail__profile-menu a[href]'
    ].join(',');

    document.addEventListener('click', function (event) {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      var link = event.target.closest(selectors);
      if (!link || !document.body.classList.contains('casehub-browser-basic')) return;
      if (link.target && link.target !== '_self') return;

      var url;
      try {
        url = new URL(link.href, window.location.href);
      } catch (_) {
        return;
      }

      if (url.origin !== window.location.origin) return;
      if (!url.pathname.startsWith('/casehub/')) return;
      if (/\/(logout|api|static)(\/|$)/.test(url.pathname)) return;
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;

      event.preventDefault();
      navigateSoft(url.href).catch(function () {
        window.location.assign(url.href);
      });
    });

    window.addEventListener('popstate', function () {
      navigateSoft(window.location.href, { replace: true }).catch(function () {
        window.location.reload();
      });
    });
  }

  async function navigateSoft(href, options) {
    options = options || {};
    document.body.classList.add('casehub-basic-soft-loading');
    try {
      var response = await fetch(href, {
        credentials: 'same-origin',
        headers: { 'X-CaseHub-Basic-Soft-Navigation': '1' }
      });
      if (!response.ok) throw new Error('soft_navigation_http_' + response.status);
      var html = await response.text();
      var nextDoc = new DOMParser().parseFromString(html, 'text/html');
      var nextMain = qs('main.main-content', nextDoc);
      var currentMain = qs('main.main-content');
      if (!nextMain || !currentMain) throw new Error('soft_navigation_missing_main');

      var routeScripts = collectRouteScripts(nextDoc);
      var nextTabShell = qs('.casehub-basic-tabs', nextMain);
      var currentTabShell = qs('.casehub-basic-tabs', currentMain);
      qsa('script', nextMain).forEach(function (script) { script.remove(); });
      routeScripts.forEach(function (script) {
        if (script.parentNode) script.parentNode.removeChild(script);
      });

      syncRouteStyles(nextDoc);
      if (nextDoc.title) document.title = nextDoc.title;

      if (nextTabShell && currentTabShell) {
        currentTabShell.innerHTML = nextTabShell.innerHTML;
        initTabs();
      }

      qsa(':scope > :not(.casehub-basic-tabs)', currentMain).forEach(function (node) {
        node.remove();
      });
      qsa(':scope > :not(.casehub-basic-tabs)', nextMain).forEach(function (node) {
        currentMain.appendChild(document.importNode(node, true));
      });

      updateActiveShell(new URL(href, window.location.href));
      if (!options.replace) {
        history.pushState({ casehubBasicSoft: true }, '', href);
      }
      await replayScripts(routeScripts);
      document.dispatchEvent(new CustomEvent('casehub:soft-navigation', { detail: { href: href } }));
    } finally {
      requestAnimationFrame(function () {
        document.body.classList.remove('casehub-basic-soft-loading');
      });
    }
  }

  function collectRouteScripts(doc) {
    var scripts = [];
    var main = qs('main.main-content', doc);
    if (main) scripts = scripts.concat(qsa('script', main));
    if (doc.body) {
      scripts = scripts.concat(qsa(':scope > script, :scope > link[rel="stylesheet"]', doc.body));
    }

    var node = doc.body ? doc.body.firstChild : null;
    while (node) {
      if (node.nodeType === Node.COMMENT_NODE && /casehub-route-scripts-start/i.test(node.nodeValue || '')) {
        node = node.nextSibling;
        break;
      }
      node = node.nextSibling;
    }
    while (node) {
      if (node.nodeType === Node.COMMENT_NODE && /casehub-route-scripts-end/i.test(node.nodeValue || '')) break;
      if (node.nodeType === Node.ELEMENT_NODE && node.tagName && ['script', 'link'].indexOf(node.tagName.toLowerCase()) >= 0) {
        scripts.push(node);
      }
      node = node.nextSibling;
    }
    return scripts;
  }

  function syncRouteStyles(doc) {
    qsa('style[data-casehub-soft-style]').forEach(function (style) {
      style.remove();
    });

    qsa('style', doc.head).forEach(function (style) {
      var clone = document.createElement('style');
      Array.prototype.slice.call(style.attributes || []).forEach(function (attr) {
        clone.setAttribute(attr.name, attr.value);
      });
      clone.setAttribute('data-casehub-soft-style', '1');
      clone.textContent = style.textContent || '';
      document.head.appendChild(clone);
    });

    loadMissingStyles(doc);
  }

  function loadMissingStyles(doc) {
    qsa('link[rel="stylesheet"][href]', doc.head).forEach(function (link) {
      var href = link.getAttribute('href');
      if (!href) return;
      var absolute = new URL(href, window.location.href).href;
      var exists = qsa('link[rel="stylesheet"][href]').some(function (current) {
        return new URL(current.getAttribute('href'), window.location.href).href === absolute;
      });
      if (exists) return;
      var clone = document.createElement('link');
      clone.rel = 'stylesheet';
      clone.href = absolute;
      document.head.appendChild(clone);
    });
  }

  function replayScripts(scripts) {
    return scripts.reduce(function (chain, oldScript) {
      return chain.then(function () {
        return new Promise(function (resolve, reject) {
          if (oldScript.tagName && oldScript.tagName.toLowerCase() === 'link') {
            var href = oldScript.getAttribute('href');
            if (!href) {
              resolve();
              return;
            }
            var absoluteHref = new URL(href, window.location.href).href;
            var styleExists = qsa('link[rel="stylesheet"][href]').some(function (current) {
              return new URL(current.getAttribute('href'), window.location.href).href === absoluteHref;
            });
            if (styleExists) {
              resolve();
              return;
            }
            var link = document.createElement('link');
            link.rel = oldScript.getAttribute('rel') || 'stylesheet';
            link.href = absoluteHref;
            link.onload = resolve;
            link.onerror = reject;
            document.head.appendChild(link);
            return;
          }

          var script = document.createElement('script');
          Array.prototype.slice.call(oldScript.attributes || []).forEach(function (attr) {
            if (attr.name === 'defer') return;
            script.setAttribute(attr.name, attr.value);
          });
          if (oldScript.src) {
            var src = new URL(oldScript.getAttribute('src'), window.location.href).href;
            var alreadyLoaded = qsa('script[src]').some(function (current) {
              return new URL(current.getAttribute('src'), window.location.href).href === src;
            });
            if (alreadyLoaded) {
              resolve();
              return;
            }
            script.src = src;
            script.onload = resolve;
            script.onerror = reject;
          } else {
            script.textContent = oldScript.textContent || '';
          }
          document.body.appendChild(script);
          if (!oldScript.src) resolve();
        });
      });
    }, Promise.resolve());
  }

  function updateActiveShell(url) {
    var path = url.pathname.replace(/\/+$/, '');
    function routeGroup(value) {
      var route = (value || '').replace(/\/+$/, '');
      if (/\/whatsapp(?:-chat)?(?:\/|$)/.test(route)) return 'whatsapp';
      if (/\/assistente(?:\/|$)/.test(route)) return 'maestro';
      if (/\/tasks(?:\/|$)/.test(route)) return 'tasks';
      if (/\/calendar(?:\/|$)/.test(route)) return 'calendar';
      return route;
    }
    var currentGroup = routeGroup(path);
    qsa('.casehub-basic-tabs__tab[href], .casehub-basic-rail__item[href]').forEach(function (link) {
      var linkPath;
      try {
        linkPath = new URL(link.href, window.location.href).pathname.replace(/\/+$/, '');
      } catch (_) {
        return;
      }
      var active = linkPath === path || routeGroup(linkPath) === currentGroup;
      link.classList.toggle('is-active', active);
      if (link.classList.contains('casehub-basic-tabs__tab')) {
        link.setAttribute('aria-selected', active ? 'true' : 'false');
      }
      if (link.classList.contains('casehub-basic-rail__item')) {
        if (active) link.setAttribute('aria-current', 'page');
        else link.removeAttribute('aria-current');
      }
    });
  }

  function init() {
    initTabs();
    initProfileMenu();
    initResourcePanel();
    initRailFocusMode();
    initNeumorphicLabSync();
    initSoftNavigation();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
