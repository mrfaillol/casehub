/**
 * CaseHub Desktop Window Manager (Phase 11)
 * Handles creating, dragging, resizing, snapping, and stacking of floating iframes
 */

class DesktopWindowManager {
    constructor() {
        if (!document.body.classList.contains('desktop')) return;

        // Viewport detection — responsive-manager.js já setou body.viewport-*
        this.viewport = this._detectViewport();
        this.isTouch = document.body.classList.contains('touch');
        this._applyViewportMode();

        document.addEventListener('viewportchange', (e) => {
            this.viewport = e.detail.viewport;
            this.isTouch = e.detail.touch;
            this._applyViewportMode();
        });

        this.windows = new Map();
        this.zIndexCounter = 1000;
        this.container = document.querySelector('.main-content');
        
        // Container positioning is handled by CSS (position: absolute in glass-override)

        this.bindGlobalEvents();

        // Convert the "Main App Window" (Home Dashboard) into the first managed window
        this.initMainHomeWindow();

        // Start menu bar clock
        this.startMenuBarClock();

        // Session save happens only on window open/close/minimize (event-driven)
        // Previous session restore is disabled — templates reopen via dock on demand

        // Initial dock indicators update
        this.updateDockIndicators();

        // Dock: vertical wheel → horizontal scroll (responsive icon navigation)
        this.enableDockWheelScroll();

        // Keyboard: Ctrl+T = auto-tile
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 't') {
                e.preventDefault();
                this.autoTile();
            }
        });
    }

    bindGlobalEvents() {
        const skipUrls = ['/logout', '/login', '/settings', '/profile', '/admin', '/set-language', '/customizacao'];

        // Mapeia cliques no Dock
        document.body.addEventListener('click', (e) => {
            const dockLink = e.target.closest('.dock-apps-nav .nav-link, .sidebar .nav-link, .sidebar .logo, .os-dock-logo');
            if (dockLink && dockLink.id !== 'desktopLaunchpadBtn') {
                const href = dockLink.getAttribute('href') || (dockLink.classList.contains('logo') ? '/casehub/dashboard' : null);
                if (href && href !== '#' && !href.startsWith('javascript:')) {
                    if (skipUrls.some(s => href.includes(s))) return;
                    e.preventDefault();
                    
                    // Se clicou na Logo (dashboard home)
                    if (dockLink.classList.contains('logo')) {
                        const winHome = this.windows.get('win-home');
                        if (winHome) {
                            if (winHome.state === 'minimized') this.unminimizeWindow('win-home');
                            this.bringToFront('win-home');
                        }
                        return;
                    }

                    let title = dockLink.dataset.tooltip || dockLink.textContent.trim();
                    let iconEl = dockLink.querySelector('i');
                    let iconClass = iconEl ? iconEl.className : 'fas fa-cube';

                    // Camada 1: click throttle — ignore spam clicks while opening
                    if (dockLink.classList.contains('opening')) return;
                    dockLink.classList.add('opening');
                    setTimeout(() => dockLink.classList.remove('opening'), 1200);

                    requestAnimationFrame(() => this.launchApp(href, title, iconClass));
                }
            }
        });

        // Resize da janela principal e limites
        window.addEventListener('resize', () => {
            this.windows.forEach(win => {
                if (win.state === 'maximized') {
                    this.maximizeWindow(win.id, true);
                }
            });
        });

        // Pointer events (modern, GPU-optimized) — works for both drag (via setPointerCapture)
        // and resize. Listening on document captures even fast cursor movements.
        document.addEventListener('pointermove', this.handleMouseMove.bind(this), { passive: true });
        document.addEventListener('pointerup', this.handleMouseUp.bind(this));
        document.addEventListener('pointercancel', this.handleMouseUp.bind(this));
        
        // Z-Index Tracker for background windows:
        // Click anywhere on a window (including iframe) brings it to front
        document.addEventListener('pointerdown', (e) => {
            const winEl = e.target.closest?.('.macos-window');
            if (winEl && winEl.id) this.bringToFront(winEl.id);
        }, true); // capture phase — fires before iframe swallows

        // Fallback: listener na bubble phase (captura clicks que iframe já processou)
        document.addEventListener('mousedown', (e) => {
            const winEl = e.target.closest?.('.macos-window');
            if (winEl && winEl.id) this.bringToFront(winEl.id);
        }, false);

        // Fallback: focusin bubble até document — iframe tomar focus traz janela pra frente
        document.addEventListener('focusin', (e) => {
            const winEl = e.target.closest?.('.macos-window');
            if (winEl && winEl.id) this.bringToFront(winEl.id);
        });

        // Iframe focus detector (fallback legado — caso iframe roube focus sem bubble)
        window.addEventListener('blur', () => {
            setTimeout(() => {
                if (document.activeElement && document.activeElement.tagName === 'IFRAME') {
                    const winEl = document.activeElement.closest('.macos-window');
                    if (winEl) this.bringToFront(winEl.id);
                }
            }, 50);
        });

        this.dragState = null; 
        this.resizeState = null; 
    }

    initMainHomeWindow() {
        const mainWindow = document.getElementById('mainAppWindow');
        if (!mainWindow) return;

        const id = 'win-home';
        mainWindow.id = id;
        
        // Inject geometric constraints so JS drag mechanism has a baseline
        // Posição/tamanho inicial vem do CSS (--win-x/y/w/h em view-system.css).
        // JS só sobrescreve durante drag/resize/maximize/restore (inline styles ganham).
        // Restaurar de localStorage se houver posição salva:
        try {
            var saved = JSON.parse(localStorage.getItem('casehub-win-home') || 'null');
            if (saved && saved.left && saved.top) {
                mainWindow.style.left = saved.left;
                mainWindow.style.top = saved.top;
                mainWindow.style.width = saved.width;
                mainWindow.style.height = saved.height;
            }
        } catch(_) {}
        mainWindow.style.position = 'absolute';
        
        this.windows.set(id, {
            id: id,
            el: mainWindow,
            state: mainWindow.classList.contains('os-maximized') ? 'maximized' : 'normal',
            isIframed: false
        });

        // Hijack its titlebar
        const titlebar = mainWindow.querySelector('.macos-titlebar');
        if (titlebar) {
            this.attachTitlebarEvents(id, mainWindow, titlebar);
        }

        this.addResizeHandles(mainWindow, id);

        this.bringToFront(id);
    }

    /**
     * Camada 4 — Iframe load queue. Processes 1 iframe every 400ms
     * to avoid thundering herd (multiple iframes loading in parallel kill main thread).
     */
    _scheduleIframeLoad(iframe, finalUrl) {
        if (!this._loadQueue) this._loadQueue = [];
        if (!this._loadQueueRunning) this._loadQueueRunning = false;

        this._loadQueue.push({ iframe, url: finalUrl });
        this._processLoadQueue();
    }
    _processLoadQueue() {
        if (this._loadQueueRunning || this._loadQueue.length === 0) return;
        this._loadQueueRunning = true;
        const { iframe, url } = this._loadQueue.shift();
        iframe.src = url;
        iframe.dataset.loaded = 'true';
        // Let next one through after 400ms (one iframe at a time)
        setTimeout(() => {
            this._loadQueueRunning = false;
            this._processLoadQueue();
        }, 400);
    }

    /**
     * Canonicalize URL: /tasks → /tasks/kanban, /calendar → /calendar/agenda
     * Prevents opening duplicate windows for the same logical app.
     */
    _canonicalUrl(url) {
        if (!url || typeof url !== 'string') return '';
        const clean = url.split('?')[0].replace(/\/$/, '');
        const aliases = {
            '/casehub/tasks': '/casehub/tasks/kanban',
            '/casehub/calendar': '/casehub/calendar/agenda',
        };
        return aliases[clean] || clean;
    }

    /**
     * Launch an App from Launchpad or Dock
     */
    launchApp(url, title, iconClass) {
        const canonical = this._canonicalUrl(url);
        // Find if already open (compare canonical URLs to dedup aliases)
        for (const [id, win] of this.windows.entries()) {
            if (!win.url) continue;
            if (this._canonicalUrl(win.url) === canonical) {
                this.unminimizeWindow(id);
                this.bringToFront(id);
                return;
            }
        }

        // Camada 3: Hard cap — remove DOM of oldest windows to free main thread
        const maxWindows = (window.osResourceManager?.maxActiveWindows) || 5;
        const openWindows = Array.from(this.windows.entries())
            .filter(([id, w]) => id !== 'win-home' && w.state !== 'minimized');
        if (openWindows.length >= maxWindows) {
            const excess = openWindows.length - maxWindows + 1;
            const closed = [];
            openWindows
                .sort((a, b) => (parseInt(a[1].el.style.zIndex) || 0) - (parseInt(b[1].el.style.zIndex) || 0))
                .slice(0, excess)
                .forEach(([id, w]) => {
                    closed.push(w.title || 'App');
                    // Unmount iframe antes de remover DOM — libera ~30MB por iframe
                    // (about:blank força unload de recursos/JS do app)
                    if (w.el) {
                        const ifr = w.el.querySelector('iframe');
                        if (ifr) {
                            try { ifr.src = 'about:blank'; } catch(_) {}
                            ifr.remove();
                        }
                        if (w.el.parentNode) w.el.parentNode.removeChild(w.el);
                    }
                    this.windows.delete(id);
                    if (window.osResourceManager) {
                        window.osResourceManager.activeWindows.delete(id);
                        window.osResourceManager.windowActivity.delete(id);
                    }
                });
            // Toast notification (Camada 6)
            if (closed.length) this._showToast(`${closed.join(', ')} fechada(s) para liberar recursos`);
        }

        const id = 'win-' + Date.now();
        
        // Build Window DOM
        const winEl = document.createElement('div');
        winEl.className = 'macos-window macos-app-window';
        winEl.id = id;
        winEl.style.position = 'absolute';
        
        // Calculate spawn position (cascade effect)
        const offset = (this.windows.size * 30) % 200;
        winEl.style.left = `calc(5vw + \${offset}px)`;
        winEl.style.top = `calc(5vh + \${offset}px)`;
        winEl.style.width = '1000px';
        winEl.style.height = '650px';
        winEl.style.maxWidth = '90vw';
        winEl.style.maxHeight = '80vh';
        winEl.style.margin = '0';
        // Use class for animation, then auto-remove so transform stays free for drag
        winEl.classList.add('window-opening');
        setTimeout(() => winEl.classList.remove('window-opening'), 500);

        // Titlebar
        const titlebar = document.createElement('div');
        titlebar.className = 'macos-titlebar';
        titlebar.style.cursor = 'grab';
        titlebar.innerHTML = `
            <div class="traffic-lights">
                <div class="traffic-dot close" data-action="close"></div>
                <div class="traffic-dot minimize" data-action="minimize"></div>
                <div class="traffic-dot maximize" data-action="maximize"></div>
            </div>
            <div class="os-window-title">
                <i class="${iconClass} me-2" style="font-size:12px;opacity:0.7"></i>${title}
            </div>
            <button class="window-versions-btn" data-action="versions" title="Versões anteriores"
                style="background:none;border:none;color:inherit;opacity:0.55;cursor:pointer;padding:4px 8px;font-size:12px;border-radius:6px;transition:opacity 150ms,background 150ms;">
                <i class="fas fa-history"></i>
            </button>
        `;

        // Content Area with Iframe
        const contentArea = document.createElement('div');
        contentArea.className = 'macos-window-content';
        contentArea.style.padding = '0';
        contentArea.style.height = 'calc(100% - var(--win-titlebar-h))';
        contentArea.style.overflow = 'hidden';

        const finalUrl = url + (url.includes('?') ? '&' : '?') + 'desktop_frame=1';

        const iframe = document.createElement('iframe');
        iframe.dataset.src = finalUrl; // Stored for lazy load
        iframe.style.width = '100%';
        iframe.style.height = '100%';
        iframe.style.border = 'none';
        iframe.style.background = 'var(--bg-card, #fff)';
        iframe.setAttribute('sandbox', 'allow-same-origin allow-scripts allow-forms allow-popups allow-downloads allow-top-navigation allow-modals');

        // Loading indicator
        const loader = document.createElement('div');
        loader.className = 'iframe-loader-overlay';
        loader.style.cssText = 'position:absolute; inset:0; display:flex; align-items:center; justify-content:center; background:var(--glass-3); z-index:10; transition:opacity 0.5s';
        loader.innerHTML = '<i class="fas fa-cube fa-2x" style="color:var(--desk-accent); opacity: 0.5"></i><span style="font-size: 14px; margin-left: 10px;">Clique para abrir</span>';
        
        iframe.onload = () => {
            if (iframe.src !== 'about:blank' && iframe.src.includes(finalUrl.split('?')[0])) {
                loader.style.opacity = '0';
                setTimeout(() => loader.remove(), 500);
            }
            try {
                const idoc = iframe.contentDocument;
                if (!idoc || !idoc.body) return;

                // CRITICAL: if iframe rendered OS chrome (nested dock/topbar), force reload with flag
                const nestedDock = idoc.querySelector('.ui-os-dock-wrapper, .os-dock-bubble');
                if (nestedDock && !iframe.src.includes('desktop_frame=1')) {
                    const sep = iframe.src.includes('?') ? '&' : '?';
                    iframe.src = iframe.src + sep + 'desktop_frame=1';
                    return;
                }
                // Also: if body still has class 'desktop' without iframe-mode, hide dock inline
                if (idoc.body.classList.contains('desktop') && !idoc.body.classList.contains('iframe-mode')) {
                    idoc.body.classList.add('iframe-mode');
                }

                // Click-to-front fix: pointerdown dentro do iframe traz janela pai pra frente
                idoc.addEventListener('pointerdown', () => {
                    const winEl = iframe.closest('.macos-window');
                    if (winEl && winEl.id) this.bringToFront(winEl.id);
                }, true);

                // Rewrite <a href> + intercept form submits to preserve desktop_frame
                const withFlag = (url) => {
                    if (!url || url.startsWith('#') || url.startsWith('http') || url.startsWith('javascript:') || url.startsWith('mailto:')) return url;
                    return url.includes('desktop_frame') ? url : url + (url.includes('?') ? '&' : '?') + 'desktop_frame=1';
                };
                const rewrite = () => {
                    idoc.querySelectorAll('a[href]').forEach(a => {
                        const href = a.getAttribute('href');
                        const nh = withFlag(href);
                        if (nh !== href) a.setAttribute('href', nh);
                    });
                    idoc.querySelectorAll('form[action]').forEach(f => {
                        const action = f.getAttribute('action');
                        const na = withFlag(action);
                        if (na !== action) f.setAttribute('action', na);
                    });
                };
                rewrite();
                // Throttled + drag-aware observer (no churn during drag)
                let rewriteQueued = false;
                const mo = new MutationObserver(() => {
                    if (window.__OS_DRAGGING__ || rewriteQueued) return;
                    rewriteQueued = true;
                    requestAnimationFrame(() => { rewriteQueued = false; rewrite(); });
                });
                mo.observe(idoc.body, { childList: true, subtree: true });
            } catch (e) { /* cross-origin blocked, ignore */ }
        };

        const loadContent = () => {
            if (iframe.dataset.loaded !== 'true') {
                loader.innerHTML = '<i class="fas fa-circle-notch fa-spin fa-2x" style="color:var(--desk-accent)"></i>';
                // Camada 4: go through load queue instead of direct assignment
                this._scheduleIframeLoad(iframe, iframe.dataset.src);
            }
            if (window.osResourceManager) {
                window.osResourceManager.activateWindow(id);
            }
        };

        // Auto-load via queue immediately (not on mousedown — user wants content now)
        requestAnimationFrame(() => loadContent());
        winEl.addEventListener('mousedown', loadContent, { once: true });

        contentArea.appendChild(loader);
        contentArea.appendChild(iframe);
        winEl.appendChild(titlebar);
        winEl.appendChild(contentArea);

        // Add Resize Handles
        this.addResizeHandles(winEl, id);

        this.container.appendChild(winEl);
        
        if (window.osResourceManager) {
             window.osResourceManager.observeElement(winEl);
             window.osResourceManager.registerWindow(id, winEl, iframe);
        }

        // Iframe error handling + timeout
        iframe.onerror = () => {
            loader.innerHTML = '<div style="text-align:center"><i class="fas fa-exclamation-triangle fa-2x" style="color:#f59e0b;margin-bottom:8px"></i><p style="font-size:13px">Não foi possível carregar</p><button onclick="this.closest(\'.macos-window\').querySelector(\'iframe\').src=this.closest(\'.macos-window\').querySelector(\'iframe\').dataset.src" style="padding:6px 16px;border:1px solid rgba(255,255,255,0.3);border-radius:6px;background:rgba(255,255,255,0.2);cursor:pointer;font-size:12px">Tentar de novo</button></div>';
            loader.style.opacity = '1';
        };
        setTimeout(() => {
            if (iframe.dataset.loaded === 'true' && loader.parentNode && loader.style.opacity !== '0') {
                loader.innerHTML = '<div style="text-align:center"><i class="fas fa-hourglass-half fa-2x" style="color:#f59e0b;opacity:0.5;margin-bottom:8px"></i><p style="font-size:13px">Carregamento lento...</p></div>';
            }
        }, 15000);

        this.windows.set(id, {
            id, url, title, iconClass, el: winEl, state: 'normal', isIframed: true
        });

        this.attachTitlebarEvents(id, winEl, titlebar);
        this.bringToFront(id);
        this.updateDockIndicators();
        this.saveSession();
    }

    addResizeHandles(winEl, id) {
        // 8 edges/corners — Victor quer resize por qualquer canto
        const HANDLE_STYLES = {
            n:  { top: '-5px',  left: '0',     width: '100%', height: '10px',  cursor: 'n-resize'  },
            s:  { bottom: '-5px', left: '0',   width: '100%', height: '10px',  cursor: 's-resize'  },
            e:  { right: '-5px',  top: '0',    width: '10px', height: '100%',  cursor: 'e-resize'  },
            w:  { left: '-5px',   top: '0',    width: '10px', height: '100%',  cursor: 'w-resize'  },
            ne: { top: '-5px',    right: '-5px', width: '15px', height: '15px', cursor: 'ne-resize' },
            nw: { top: '-5px',    left: '-5px',  width: '15px', height: '15px', cursor: 'nw-resize' },
            se: { bottom: '-5px', right: '-5px', width: '15px', height: '15px', cursor: 'se-resize' },
            sw: { bottom: '-5px', left: '-5px',  width: '15px', height: '15px', cursor: 'sw-resize' },
        };
        const directions = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'];
        directions.forEach(dir => {
            const handle = document.createElement('div');
            handle.className = `resize-handle resize-${dir}`;
            handle.style.position = 'absolute';
            // Corners acima das edges pra não serem cobertos
            handle.style.zIndex = dir.length === 2 ? '1000' : '999';
            Object.assign(handle.style, HANDLE_STYLES[dir]);

            handle.addEventListener('mousedown', (e) => {
                // F3: resize só em desktop (tablet/mobile bloqueado)
                if (this._resizeEnabled === false) return;
                e.preventDefault();
                e.stopPropagation();
                this.bringToFront(id);

                // Pra resize W/N precisamos mexer left/top — garantir posicionamento absoluto concreto
                if (dir.includes('w') || dir.includes('n')) {
                    const containerRect = this.container.getBoundingClientRect();
                    const winRect = winEl.getBoundingClientRect();
                    winEl.style.position = 'absolute';
                    winEl.style.margin = '0';
                    winEl.style.left = (winRect.left - containerRect.left) + 'px';
                    winEl.style.top = (winRect.top - containerRect.top) + 'px';
                }

                this.resizeState = {
                    id, dir,
                    startX: e.clientX, startY: e.clientY,
                    origW: winEl.offsetWidth, origH: winEl.offsetHeight,
                    origX: winEl.offsetLeft, origY: winEl.offsetTop
                };
                
                // Overlay to catch mouse during iframe resize
                this.showIframeShield();
            });
            winEl.appendChild(handle);
        });
    }

    attachTitlebarEvents(id, winEl, titlebar) {
        // Visual feedback: cursor indicates draggability
        titlebar.style.cursor = 'grab';

        // Pre-promote to GPU layer on hover (cheaper than at drag-start)
        titlebar.addEventListener('pointerenter', () => {
            if (!this.dragState) winEl.style.willChange = 'transform';
        });
        titlebar.addEventListener('pointerleave', () => {
            if (!this.dragState) winEl.style.willChange = 'auto';
        });

        winEl.addEventListener('pointerdown', () => this.bringToFront(id));

        // Pointer Events API — captures pointer for true 1:1 tracking
        titlebar.addEventListener('pointerdown', (e) => {
            if (e.target.closest('.traffic-lights')) return;
            if (e.button !== 0) return; // only primary button
            // F3: drag desabilitado em mobile (swipe via window-swipe.js cuida de troca de janela)
            if (this._dragEnabled === false) { this.bringToFront(id); return; }
            const win = this.windows.get(id);
            if (!win) return;
            if (win.state === 'maximized' || win.state === 'split') {
                this.unmaximizeWindow(id);
            }

            e.preventDefault();
            this.bringToFront(id);

            // Capture pointer so events fire even if cursor leaves titlebar
            try { titlebar.setPointerCapture(e.pointerId); } catch(_) {}

            const winRect = winEl.getBoundingClientRect();
            const containerRect = this.container.getBoundingClientRect();
            let left = winRect.left - containerRect.left;
            let top = winRect.top - containerRect.top;
            const currentWidth = winEl.offsetWidth;
            const currentHeight = winEl.offsetHeight;

            winEl.style.position = 'absolute';
            winEl.style.margin = '0';
            winEl.style.left = left + 'px';
            winEl.style.top = top + 'px';
            winEl.style.width = currentWidth + 'px';
            winEl.style.height = currentHeight + 'px';

            this.dragState = {
                id, pointerId: e.pointerId,
                startX: e.clientX, startY: e.clientY,
                origLeft: left, origTop: top,
                titlebar
            };

            titlebar.style.cursor = 'grabbing';
            winEl.classList.add('dragging');
            winEl.style.willChange = 'transform';

            // Pause global animations + monitors competing for main thread
            window.__OS_DRAGGING__ = true;
            document.body.classList.add('dragging-active');
            if (window.osResourceManager) window.osResourceManager.fpsLoopPaused = true;

            this.showIframeShield();
        });

        titlebar.addEventListener('dblclick', () => {
            const win = this.windows.get(id);
            if (win.state === 'maximized') {
                this.unmaximizeWindow(id);
            } else {
                this.maximizeWindow(id);
            }
        });

        // Versions button → abre picker em janela paralela
        titlebar.addEventListener('click', (e) => {
            const vbtn = e.target.closest('[data-action="versions"]');
            if (vbtn) {
                e.stopPropagation();
                this.openVersionPicker(id, vbtn);
            }
        });

        // Traffic lights
        titlebar.addEventListener('click', (e) => {
            const dot = e.target.closest('.traffic-dot');
            if (!dot) return;
            const action = dot.dataset.action;

            if (action === 'close') this.closeWindow(id);
            if (action === 'minimize') this.minimizeWindow(id);
            if (action === 'maximize') {
                const win = this.windows.get(id);
                if (win.state === 'maximized') this.unmaximizeWindow(id);
                else this.maximizeWindow(id);
            }
        });

        // Green traffic light: hover shows tile/split menu (macOS Sonoma style)
        const greenDot = titlebar.querySelector('.traffic-dot.maximize');
        if (greenDot) this.attachTileMenu(id, greenDot);
    }

    // Tile menu popup on green-dot hover
    attachTileMenu(id, anchor) {
        let menu = null;
        let hideTimer = null;

        const build = () => {
            const el = document.createElement('div');
            el.className = 'os-tile-menu';
            el.innerHTML = `
                <div class="os-tile-section-title">Mover e Redimensionar</div>
                <div class="os-tile-grid">
                    <button data-mode="left-half"    title="Metade esquerda"><span class="ti ti-left"></span></button>
                    <button data-mode="right-half"   title="Metade direita"><span class="ti ti-right"></span></button>
                    <button data-mode="top-half"     title="Metade superior"><span class="ti ti-top"></span></button>
                    <button data-mode="bottom-half"  title="Metade inferior"><span class="ti ti-bottom"></span></button>
                </div>
                <div class="os-tile-divider"></div>
                <div class="os-tile-section-title">Preencher e Organizar</div>
                <div class="os-tile-grid">
                    <button data-mode="fill"         title="Preencher tela"><span class="ti ti-fill"></span></button>
                    <button data-mode="center"       title="Centralizar"><span class="ti ti-center"></span></button>
                    <button data-mode="top-left"     title="Canto superior-esquerdo"><span class="ti ti-tl"></span></button>
                    <button data-mode="tile-all"     title="Organizar todas (Ctrl+T)"><span class="ti ti-grid"></span></button>
                </div>
            `;
            el.addEventListener('mouseenter', () => { if (hideTimer) clearTimeout(hideTimer); });
            el.addEventListener('mouseleave', scheduleHide);
            el.addEventListener('click', (e) => {
                const btn = e.target.closest('button[data-mode]');
                if (!btn) return;
                const mode = btn.dataset.mode;
                if (mode === 'tile-all') this.autoTile();
                else this.tileWindow(id, mode);
                hide();
            });
            return el;
        };

        const position = () => {
            const r = anchor.getBoundingClientRect();
            menu.style.top = (r.bottom + 6) + 'px';
            menu.style.left = (r.left - 8) + 'px';
        };

        const show = () => {
            if (!menu) { menu = build(); document.body.appendChild(menu); }
            position();
            menu.classList.add('visible');
        };
        const hide = () => { if (menu) menu.classList.remove('visible'); };
        const scheduleHide = () => {
            if (hideTimer) clearTimeout(hideTimer);
            hideTimer = setTimeout(hide, 200);
        };

        anchor.addEventListener('mouseenter', () => {
            if (hideTimer) clearTimeout(hideTimer);
            show();
        });
        anchor.addEventListener('mouseleave', scheduleHide);
    }

    handleMouseMove(e) {
        if (this.dragState) {
            const { id, startX, startY, origLeft, origTop } = this.dragState;
            const winEl = this.windows.get(id).el;
            
            let deltaX = e.clientX - startX;
            let deltaY = e.clientY - startY;
            
            // Constrain Bounds (Impedir que suma da tela)
            const maxW = window.innerWidth;
            const maxH = window.innerHeight;
            
            // Topo (Não entrar na menu-bar ou sumir pra cima)
            if (origTop + deltaY < 0) deltaY = -origTop;
            
            // Base (Tem que sobrar pelo menos 50px de titlebar para pegar de volta)
            if (origTop + deltaY > maxH - 50) deltaY = maxH - 50 - origTop;
            
            // Esquerda/Direita (Sobra 50px de app visível mínimo)
            if (origLeft + deltaX < -winEl.offsetWidth + 50) deltaX = -winEl.offsetWidth + 50 - origLeft;
            if (origLeft + deltaX > maxW - 50) deltaX = maxW - 50 - origLeft;
            
            // Direct transform — no rAF throttle, mouse events are already
            // at screen refresh rate in modern browsers
            winEl.style.transform = `translate3d(${deltaX}px, ${deltaY}px, 0)`;

            if (e.clientX < 20) {
                this.showSnapPreview('left');
            } else if (e.clientX > window.innerWidth - 20) {
                this.showSnapPreview('right');
            } else {
                this.hideSnapPreview();
            }
        }
        else if (this.resizeState) {
            const { id, dir, startX, startY, origW, origH, origX, origY } = this.resizeState;
            const winEl = this.windows.get(id).el;
            const MIN = 300;
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;

            if (dir.includes('e')) {
                winEl.style.width = Math.max(MIN, origW + dx) + 'px';
            }
            if (dir.includes('s')) {
                winEl.style.height = Math.max(MIN, origH + dy) + 'px';
            }
            if (dir.includes('w')) {
                const newW = Math.max(MIN, origW - dx);
                const clampedDx = origW - newW;
                winEl.style.width = newW + 'px';
                winEl.style.left = (origX + clampedDx) + 'px';
            }
            if (dir.includes('n')) {
                const newH = Math.max(MIN, origH - dy);
                const clampedDy = origH - newH;
                winEl.style.height = newH + 'px';
                winEl.style.top = (origY + clampedDy) + 'px';
            }
        }
    }

    handleMouseUp(e) {
        if (this.dragState) {
            const { id, startX, startY, origLeft, origTop, pointerId, titlebar: tb } = this.dragState;
            const winEl = this.windows.get(id).el;

            // Release pointer capture immediately
            if (tb && pointerId !== undefined) {
                try { tb.releasePointerCapture(pointerId); } catch(_) {}
            }

            let deltaX = e.clientX - startX;
            let deltaY = e.clientY - startY;
            if (origTop + deltaY < 0) deltaY = -origTop;

            const finalLeft = origLeft + deltaX;
            const finalTop = origTop + deltaY;

            // PHASE 1: Commit position via left/top WHILE transform still active.
            // Setting both keeps element visually in same place (transform overrides).
            winEl.style.left = finalLeft + 'px';
            winEl.style.top = finalTop + 'px';

            const titlebar = winEl.querySelector('.macos-titlebar');
            if (titlebar) titlebar.style.cursor = 'grab';

            // Persist position de janela home pra próxima sessão
            if (id === 'win-home') {
                try {
                    localStorage.setItem('casehub-win-home', JSON.stringify({
                        left: winEl.style.left,
                        top: winEl.style.top,
                        width: winEl.style.width,
                        height: winEl.style.height
                    }));
                } catch(_) {}
            }

            // Clear drag state immediately so new drags don't conflict
            this.dragState = null;
            this.hideSnapPreview();

            // PHASE 2 (next frame): swap transform for left/top atomically.
            // This prevents flicker because both visual positions are identical.
            requestAnimationFrame(() => {
                winEl.style.transform = 'none';
                // PHASE 3 (frame after): restore heavy visuals (backdrop-filter, shadow)
                requestAnimationFrame(() => {
                    winEl.classList.remove('dragging');
                    winEl.style.willChange = 'auto';

                    // Resume global animations + monitors AFTER visual restoration
                    window.__OS_DRAGGING__ = false;
                    document.body.classList.remove('dragging-active');
                    if (window.osResourceManager) window.osResourceManager.fpsLoopPaused = false;
                });
            });

            // Snap if at edges
            if (e.clientX < 20) {
                this.snapWindow(id, 'left');
            } else if (e.clientX > window.innerWidth - 20) {
                this.snapWindow(id, 'right');
            }
        }
        if (this.resizeState) {
            this.resizeState = null;
        }
        this.hideIframeShield();
    }

    // --- State Managers ---

    bringToFront(id) {
        const win = this.windows.get(id);
        if (!win || win.state === 'minimized') return;
        
        // Elevar se não está no topo OU se não é a focada atualmente (estado-classe desincronizado)
        const currentZ = parseInt(win.el.style.zIndex) || 1000;
        const currentlyFocused = win.el.classList.contains('window-focused');
        const needsElevation = currentZ < this.zIndexCounter || !currentlyFocused;

        if (needsElevation) {
            this.zIndexCounter++;
            win.el.style.zIndex = this.zIndexCounter;

            // Remove 'window-focused' das outras, adiciona nesta
            this.windows.forEach((w) => {
                if (w.el) w.el.classList.remove('window-focused');
            });
            win.el.classList.add('window-focused');
        }

        const titleEl = document.getElementById('osAppDynamicTitle');
        if (titleEl && win.title) titleEl.textContent = win.title;
        const menubarTitle = document.getElementById('menubarAppTitle');
        if (menubarTitle && win.title) menubarTitle.textContent = win.title;
        this.updateDockIndicators();
    }

    maximizeWindow(id, force = false) {
        const win = this.windows.get(id);
        if (!win) return;
        
        if (!force) {
            win.prevRect = {
                left: win.el.style.left,
                top: win.el.style.top,
                width: win.el.style.width,
                height: win.el.style.height,
                transform: win.el.style.transform
            };
        }
        
        win.state = 'maximized';
        win.el.style.left = '0';
        win.el.style.top = '0';
        win.el.style.width = '100vw';
        // No menu bar in desktop mode — fill until dock
        win.el.style.height = 'calc(100vh - var(--dock-h) - 16px)';
        win.el.style.transform = 'none';
        win.el.style.borderRadius = '0';
        this.bringToFront(id);
    }

    unmaximizeWindow(id) {
        const win = this.windows.get(id);
        if (!win) return;
        
        win.state = 'normal';
        win.el.style.borderRadius = 'var(--win-radius)';
        if (win.prevRect) {
            win.el.style.left = win.prevRect.left;
            win.el.style.top = win.prevRect.top;
            win.el.style.width = win.prevRect.width;
            win.el.style.height = win.prevRect.height;
            win.el.style.transform = win.prevRect.transform || 'none';
        }
    }

    minimizeWindow(id) {
        const win = this.windows.get(id);
        if (!win) return;
        
        win.state = 'minimized';
        win.el.style.transform = 'scale(0.1) translateY(100vh)';
        win.el.style.opacity = '0';
        win.el.style.pointerEvents = 'none';

        // Add a temporary restore dot to the dock
        const dock = document.querySelector('.dock-apps-nav .nav, .sidebar .nav');
        if (dock) {
            let restoreBtn = document.getElementById('restore-' + id);
            if (!restoreBtn) {
                restoreBtn = document.createElement('a');
                restoreBtn.className = 'nav-link temp-restore-btn';
                restoreBtn.id = 'restore-' + id;
                restoreBtn.dataset.tooltip = 'Restaurar: ' + win.title;
                restoreBtn.innerHTML = `<i class="${win.iconClass}" style="color: #27c93f; filter: drop-shadow(0 0 5px #27c93f);"></i>`;
                restoreBtn.style.position = 'relative';
                // Add a small activity dot underneath
                const dot = document.createElement('span');
                dot.style.cssText = 'position:absolute; bottom: -6px; left:50%; transform:translateX(-50%); width:4px; height:4px; background:#27c93f; border-radius:50%;';
                restoreBtn.appendChild(dot);

                restoreBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.unminimizeWindow(id);
                });
                dock.appendChild(restoreBtn);
            }
        }
    }

    unminimizeWindow(id) {
        const win = this.windows.get(id);
        if (!win) return;
        
        win.state = 'normal';
        win.el.style.transform = 'none';
        win.el.style.opacity = '1';
        win.el.style.pointerEvents = 'auto';
        this.bringToFront(id);

        const restoreBtn = document.getElementById('restore-' + id);
        if (restoreBtn) restoreBtn.remove();
    }

    closeWindow(id) {
        const win = this.windows.get(id);
        if (!win) return;

        // Proteção para não "matar" a dashboard do DOM, apenas minimizar.
        if (id === 'win-home') {
            this.minimizeWindow(id);
            return;
        }

        win.el.style.transform = 'scale(0.8)';
        win.el.style.opacity = '0';
        win.el.style.pointerEvents = 'none';
        setTimeout(() => {
            if (win.el && win.el.parentNode) win.el.remove();
            this.windows.delete(id);
            const restoreBtn = document.getElementById('restore-' + id);
            if (restoreBtn) restoreBtn.remove();
            this.saveSession();
            this.updateDockIndicators();
            
            // Tenta focar na próxima aba com z-index maior
            let topWin = null;
            let maxZ = 0;
            this.windows.forEach(w => {
                const z = parseInt(w.el.style.zIndex) || 0;
                if (w.state !== 'minimized' && z > maxZ) {
                    maxZ = z;
                    topWin = w.id;
                }
            });
            if (topWin) this.bringToFront(topWin);
        }, 300);
    }

    snapWindow(id, side) {
        this.tileWindow(id, side === 'left' ? 'left-half' : 'right-half');
    }

    // Generic tile modes — drives the green-hover menu
    tileWindow(id, mode) {
        const win = this.windows.get(id);
        if (!win) return;
        if (!win.prevRect && win.state !== 'split' && win.state !== 'tiled') {
            win.prevRect = {
                left: win.el.style.left, top: win.el.style.top,
                width: win.el.style.width, height: win.el.style.height
            };
        }
        win.state = 'tiled';
        const el = win.el;
        const avail = 'calc(100vh - var(--dock-h) - 16px)';
        const half = 'calc((100vh - var(--dock-h) - 16px) / 2)';
        const set = (l, t, w, h) => {
            el.style.left = l; el.style.top = t; el.style.width = w; el.style.height = h;
        };
        switch (mode) {
            case 'left-half':     set('0', '0', '50vw', avail); break;
            case 'right-half':    set('50vw', '0', '50vw', avail); break;
            case 'top-half':      set('0', '0', '100vw', half); break;
            case 'bottom-half':   set('0', half, '100vw', half); break;
            case 'fill':          set('0', '0', '100vw', avail); break;
            case 'center':        set('10vw', '5vh', '80vw', '70vh'); win.state = 'normal'; break;
            case 'top-left':      set('0', '0', '50vw', half); break;
            case 'top-right':     set('50vw', '0', '50vw', half); break;
            case 'bottom-left':   set('0', half, '50vw', half); break;
            case 'bottom-right':  set('50vw', half, '50vw', half); break;
        }
        el.style.borderRadius = '0';
    }

    // --- Utility Visuals ---

    showSnapPreview(side) {
        if (!this.snapPreview) {
            this.snapPreview = document.createElement('div');
            this.snapPreview.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 50vw;
                height: calc(100vh - var(--dock-h) - 16px);
                background: rgba(255,255,255,0.15);
                border: 2px solid rgba(255,255,255,0.5);
                z-index: 99;
                pointer-events: none;
                transform: translate3d(0, 0, 0);
                will-change: transform, opacity;
                opacity: 0;
                transition: opacity 0.15s;
            `;
            document.body.appendChild(this.snapPreview);
        }
        // Compositor-only updates (no reflow)
        const x = side === 'right' ? '50vw' : '0';
        this.snapPreview.style.transform = `translate3d(${x}, 0, 0)`;
        this.snapPreview.style.opacity = '1';
        this.snapPreview._currentSide = side;
    }

    hideSnapPreview() {
        if (this.snapPreview) {
            this.snapPreview.style.opacity = '0';
            // Don't remove from DOM — toggle opacity to avoid recreation cost
        }
    }

    showIframeShield() {
        if (!this.iframeShield) {
            this.iframeShield = document.createElement('div');
            this.iframeShield.style.position = 'fixed';
            this.iframeShield.style.inset = '0';
            this.iframeShield.style.zIndex = '999999'; // above everything during drag so iframes don't swallow mouse events
            document.body.appendChild(this.iframeShield);
        }
    }

    hideIframeShield() {
        if (this.iframeShield) {
            this.iframeShield.remove();
            this.iframeShield = null;
        }
    }

    // --- Session Persistence (Cache Permanente) ---

    // --- Versions picker ---

    _archiveKeyFromUrl(url) {
        // /casehub/cases/list?desktop_frame=1 → cases-list
        let p = (url || '').split('?')[0];
        p = p.replace(/^\/casehub\/?/, '').replace(/^\/+|\/+$/g, '');
        if (!p) p = 'home';
        return p.replace(/\//g, '-');
    }

    async openVersionPicker(id, anchorEl) {
        const win = this.windows.get(id);
        if (!win) return;
        const key = this._archiveKeyFromUrl(win.url);

        document.querySelectorAll('.window-versions-picker').forEach(el => el.remove());

        const picker = document.createElement('div');
        picker.className = 'window-versions-picker';
        const rect = anchorEl.getBoundingClientRect();
        Object.assign(picker.style, {
            position: 'fixed',
            top: (rect.bottom + 6) + 'px',
            right: (window.innerWidth - rect.right) + 'px',
            minWidth: '240px',
            background: 'var(--surface-2, rgba(255,255,255,0.92))',
            backdropFilter: 'blur(20px)',
            border: '1px solid var(--border, rgba(0,0,0,0.08))',
            borderRadius: '12px',
            boxShadow: '0 10px 40px rgba(0,0,0,0.15)',
            padding: '8px',
            zIndex: '1000000',
            fontSize: '13px',
            opacity: '0',
            transform: 'translateY(-4px)',
            transition: 'opacity 150ms, transform 150ms'
        });
        picker.innerHTML = '<div style="padding:8px 10px;opacity:0.6;">Carregando versões…</div>';
        document.body.appendChild(picker);
        requestAnimationFrame(() => { picker.style.opacity = '1'; picker.style.transform = 'translateY(0)'; });

        const closePicker = (ev) => {
            if (picker.contains(ev.target) || anchorEl.contains(ev.target)) return;
            picker.remove();
            document.removeEventListener('click', closePicker, true);
        };
        setTimeout(() => document.addEventListener('click', closePicker, true), 0);

        try {
            const resp = await fetch(`/casehub/templates/_archive/_index/${encodeURIComponent(key)}.html`);
            const data = resp.ok ? await resp.json() : { versions: [] };
            const versions = data.versions || [];
            if (!versions.length) {
                picker.innerHTML = `<div style="padding:10px;opacity:0.6;">Nenhuma versão arquivada ainda<br><span style="font-size:11px;">chave: ${key}</span></div>`;
                return;
            }
            picker.innerHTML = versions.map(v => `
                <button class="version-item" data-v="${v.id}"
                    style="display:block;width:100%;text-align:left;padding:8px 10px;border:none;background:transparent;border-radius:8px;cursor:pointer;font:inherit;color:inherit;transition:background 150ms;">
                    <div style="font-weight:500;">${v.label || v.id}</div>
                    ${v.date ? `<div style="font-size:11px;opacity:0.55;">${v.date}</div>` : ''}
                </button>
            `).join('');
            picker.querySelectorAll('.version-item').forEach(btn => {
                btn.addEventListener('mouseenter', () => btn.style.background = 'var(--surface-3, rgba(0,0,0,0.05))');
                btn.addEventListener('mouseleave', () => btn.style.background = 'transparent');
                btn.addEventListener('click', () => {
                    const v = btn.dataset.v;
                    const archiveUrl = `/casehub/templates/_archive/${encodeURIComponent(key)}.html?v=${encodeURIComponent(v)}`;
                    this.launchApp(archiveUrl, `${win.title} · ${v}`, 'fas fa-history');
                    picker.remove();
                });
            });
        } catch(e) {
            picker.innerHTML = '<div style="padding:10px;color:var(--danger, #c44);">Erro ao carregar versões</div>';
        }
    }

    saveSession() {
        const windows = [];
        this.windows.forEach((win, id) => {
            if (id === 'win-home' || !win.url) return;
            if (win.state === 'minimized') return; // não restaura minimizadas
            windows.push({
                url: win.url,
                title: win.title,
                iconClass: win.iconClass,
                state: win.state,
                left: win.el.style.left,
                top: win.el.style.top,
                width: win.el.style.width,
                height: win.el.style.height,
                zIndex: win.el.style.zIndex
            });
        });
        try {
            localStorage.setItem('casehub-desktop-session', JSON.stringify({
                ts: Date.now(),
                windows
            }));
        } catch(e) {}
    }

    restoreSession() {
        // Guards: skip via query string, flag de logout, ou sessão velha
        try {
            if (new URLSearchParams(location.search).get('nosession') === '1') return;
            if (sessionStorage.getItem('casehub-skip-restore') === '1') {
                sessionStorage.removeItem('casehub-skip-restore');
                return;
            }
            const raw = localStorage.getItem('casehub-desktop-session');
            if (!raw) return;
            const data = JSON.parse(raw);
            const windows = Array.isArray(data) ? data : (data.windows || []);
            const ts = data.ts || 0;
            // Sessão > 7 dias é stale — ignora
            if (ts && (Date.now() - ts) > 7 * 24 * 3600 * 1000) return;
            if (!windows.length) return;

            const cap = (window.osResourceManager?.maxActiveWindows) || 5;
            const toRestore = windows.slice(0, cap);

            // Deep-link: ?desktop_window=<url> abre só uma específica, ignora resto
            const deepLink = new URLSearchParams(location.search).get('desktop_window');
            const queue = deepLink
                ? toRestore.filter(w => w.url === deepLink || this._canonicalUrl(w.url) === this._canonicalUrl(deepLink))
                : toRestore;

            // Stagger pra respeitar iframe queue + ordenar por zIndex (mais antiga primeiro)
            queue
                .sort((a, b) => (parseInt(a.zIndex) || 0) - (parseInt(b.zIndex) || 0))
                .forEach((w, i) => {
                    setTimeout(() => {
                        this.launchApp(w.url, w.title, w.iconClass);
                        // Encontra a janela recém-criada (última adicionada com essa URL)
                        let winId = null;
                        for (const [id, ww] of this.windows.entries()) {
                            if (ww.url === w.url) winId = id; // última wins
                        }
                        if (!winId) return;
                        const el = this.windows.get(winId).el;
                        if (w.left) el.style.left = w.left;
                        if (w.top) el.style.top = w.top;
                        if (w.width) el.style.width = w.width;
                        if (w.height) el.style.height = w.height;
                        if (w.state === 'maximized') this.maximizeWindow(winId);
                    }, i * 450); // respeita iframe lazy-load queue (400ms + margem)
                });
        } catch(e) { /* silencioso — session restore é best-effort */ }
    }

    // --- Auto-Tiling ---

    autoTile() {
        const visible = [];
        this.windows.forEach((win, id) => {
            if (win.state !== 'minimized' && id !== 'win-home') visible.push(win);
        });
        if (visible.length === 0) return;

        const menuH = 44; // menubar + padding
        const dockH = 80; // dock + padding
        const areaW = this.container.offsetWidth;
        const areaH = window.innerHeight - menuH - dockH;

        if (visible.length === 1) {
            // Center, 80% size
            const w = visible[0];
            w.el.style.left = '10%';
            w.el.style.top = '10px';
            w.el.style.width = '80%';
            w.el.style.height = (areaH - 20) + 'px';
            w.state = 'normal';
            w.el.style.borderRadius = 'var(--win-radius)';
        } else if (visible.length === 2) {
            // Side by side 50/50
            visible.forEach((w, i) => {
                w.el.style.left = (i * 50) + '%';
                w.el.style.top = '0';
                w.el.style.width = '50%';
                w.el.style.height = areaH + 'px';
                w.el.style.borderRadius = '0';
                w.state = 'split';
            });
        } else if (visible.length === 3) {
            // 1 big left (60%) + 2 small right (40% split)
            visible[0].el.style.left = '0'; visible[0].el.style.top = '0';
            visible[0].el.style.width = '60%'; visible[0].el.style.height = areaH + 'px';
            visible[0].el.style.borderRadius = '0'; visible[0].state = 'split';

            visible[1].el.style.left = '60%'; visible[1].el.style.top = '0';
            visible[1].el.style.width = '40%'; visible[1].el.style.height = (areaH / 2) + 'px';
            visible[1].el.style.borderRadius = '0'; visible[1].state = 'split';

            visible[2].el.style.left = '60%'; visible[2].el.style.top = (areaH / 2) + 'px';
            visible[2].el.style.width = '40%'; visible[2].el.style.height = (areaH / 2) + 'px';
            visible[2].el.style.borderRadius = '0'; visible[2].state = 'split';
        } else {
            // Grid: 2 columns
            const cols = 2;
            const rows = Math.ceil(visible.length / cols);
            const cellW = areaW / cols;
            const cellH = areaH / rows;
            visible.forEach((w, i) => {
                const col = i % cols;
                const row = Math.floor(i / cols);
                w.el.style.left = (col * cellW) + 'px';
                w.el.style.top = (row * cellH) + 'px';
                w.el.style.width = cellW + 'px';
                w.el.style.height = cellH + 'px';
                w.el.style.borderRadius = '0';
                w.state = 'split';
            });
        }
    }

    // --- Dock Indicators ---

    updateDockIndicators() {
        // Find the top z-index among non-minimized windows (the focused one)
        let topZ = -1;
        let topUrl = null;
        this.windows.forEach(win => {
            if (win.state === 'minimized' || !win.url) return;
            const z = parseInt(win.el.style.zIndex) || 0;
            if (z > topZ) { topZ = z; topUrl = win.url; }
        });

        // Build set of open URLs
        const openUrls = new Set();
        this.windows.forEach(win => {
            if (win.state !== 'minimized' && win.url) openUrls.add(win.url);
        });

        // Apply classes (CSS-driven, no inline style churn)
        document.querySelectorAll('.dock-apps-nav .nav-link, .sidebar .nav-link').forEach(link => {
            const href = link.getAttribute('href');
            if (!href) return;
            const isOpen = openUrls.has(href);
            const isFocused = href === topUrl;
            link.classList.toggle('has-window', isOpen);
            link.classList.toggle('has-window-active', isOpen && isFocused);
        });

        // Populate the "Janelas Abertas" dock capsule (4ª cápsula dinâmica)
        this._renderOpenWindowsDock(topUrl);
    }

    _renderOpenWindowsDock(topUrl) {
        const container = document.getElementById('openWindowsDock');
        const list = document.getElementById('openWindowsList');
        if (!container || !list) return;

        // Coleta janelas não-minimizadas com URL
        const items = [];
        this.windows.forEach(win => {
            if (win.state === 'minimized' || !win.url) return;
            items.push(win);
        });

        // Estado vazio: esconde a cápsula (CSS animação)
        container.dataset.empty = items.length === 0 ? 'true' : 'false';
        if (items.length === 0) {
            list.innerHTML = '';
            return;
        }

        // Sincronização mínima — preserve elementos existentes, remove órfãos, adiciona novos
        const existingIds = new Set(Array.from(list.children).map(el => el.dataset.winId));
        const wantedIds = new Set(items.map(w => w.id));

        // Remove órfãos
        Array.from(list.children).forEach(el => {
            if (!wantedIds.has(el.dataset.winId)) el.remove();
        });

        // Adiciona/atualiza
        items.forEach(win => {
            let btn = list.querySelector(`[data-win-id="${win.id}"]`);
            const iconClass = (win.icon && typeof win.icon === 'string') ? win.icon : 'fas fa-window-maximize';
            const title = win.title || 'Janela';
            const isFocused = win.url === topUrl;

            if (!btn) {
                btn = document.createElement('button');
                btn.className = 'open-window-item';
                btn.dataset.winId = win.id;
                btn.type = 'button';
                btn.addEventListener('click', () => {
                    this.bringToFront(win.id);
                });
                list.appendChild(btn);
            }
            btn.title = title;
            btn.setAttribute('aria-label', title);
            btn.classList.toggle('focused', isFocused);
            btn.innerHTML = `<i class="${iconClass}"></i>`;
        });
    }

    // --- Menu Bar Clock ---

    // Dock: translate vertical wheel into horizontal scroll for dock icons
    enableDockWheelScroll() {
        const dock = document.querySelector('.os-dock-apps, .sidebar');
        if (!dock) return;
        dock.addEventListener('wheel', (e) => {
            // Only hijack if vertical scroll dominant and dock has horizontal overflow
            if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && dock.scrollWidth > dock.clientWidth) {
                e.preventDefault();
                dock.scrollLeft += e.deltaY;
            }
        }, { passive: false });
    }

    // Camada 6: Toast notification (system actions feedback)
    _showToast(message) {
        let container = document.getElementById('osToastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'osToastContainer';
            document.body.appendChild(container);
        }
        const toast = document.createElement('div');
        toast.className = 'os-toast';
        toast.textContent = message;
        container.appendChild(toast);
        requestAnimationFrame(() => toast.classList.add('visible'));
        setTimeout(() => {
            toast.classList.remove('visible');
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    }

    startMenuBarClock() {
        // Clock goes in the dock user bubble (no menu bar in desktop mode)
        const userBubble = document.querySelector('.os-dock-user, .user-dock-item');

        let clock = document.getElementById('desk-clock');
        if (!clock && userBubble) {
            clock = document.createElement('span');
            clock.id = 'desk-clock';
            clock.className = 'desk-clock';
            userBubble.prepend(clock);
        }
        if (!clock) return;

        const updateClock = () => {
            const now = new Date();
            clock.textContent = now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
        };
        updateClock();
        setInterval(updateClock, 1000);
    }

    // --- Viewport adaptation ---

    _detectViewport() {
        if (document.body.classList.contains('viewport-mobile')) return 'mobile';
        if (document.body.classList.contains('viewport-tablet')) return 'tablet';
        return 'desktop';
    }

    _applyViewportMode() {
        // Mobile/tablet: drag/resize desabilitados (touch gestos diferentes).
        // Desktop: comportamento padrão.
        // Implementação futura na Op C. Aqui só flag pros handlers consultarem.
        this._dragEnabled = this.viewport === 'desktop';
        this._resizeEnabled = this.viewport === 'desktop';
        this._snapEnabled = this.viewport === 'desktop';
    }

}

// Initialize on load
function initDesktopOS() {
    if (document.body.classList.contains('desktop')) {
        window.osWindowManager = new DesktopWindowManager();

        // Session restore: reabre janelas da sessão anterior após init completo
        // (guardas em restoreSession bloqueiam se ?nosession=1 ou skip-restore flag)
        setTimeout(() => {
            try { window.osWindowManager.restoreSession(); } catch(_) {}
        }, 300);
        
        // Auto-generate tooltips for dock icons (Sidebar links)
        const tooltipEl = document.createElement('div');
        tooltipEl.className = 'os-floating-tooltip';
        document.body.appendChild(tooltipEl);

        document.querySelectorAll('.dock-apps-nav .nav-link, .sidebar .nav-link, .sidebar .logo, .os-dock-logo').forEach(link => {
            // Find text inside the link or icon title
            let label = link.querySelector('span');
            let textValue = label ? label.textContent.trim() : link.textContent.trim();
            if (link.classList.contains('logo')) textValue = 'CaseHub OS';

            if (textValue && !link.hasAttribute('data-tooltip')) {
                link.setAttribute('data-tooltip', textValue);
            }

            link.addEventListener('mouseenter', (e) => {
                const tt = link.getAttribute('data-tooltip');
                if (!tt) return;
                tooltipEl.textContent = tt;
                const rect = link.getBoundingClientRect();
                
                // Position centered above the icon
                tooltipEl.style.left = (rect.left + (rect.width / 2)) + 'px';
                tooltipEl.style.top = (rect.top - 10) + 'px';
                tooltipEl.style.transform = 'translate(-50%, -100%)';
                tooltipEl.classList.add('visible');
            });

            link.addEventListener('mouseleave', () => {
                tooltipEl.classList.remove('visible');
            });
        });

        // Auto-update the active window title dynamically
        const activeLink = document.querySelector('.dock-apps-nav .nav-link.active, .sidebar .nav-link.active');
        const osTitleEl = document.getElementById('osAppDynamicTitle');
        if (activeLink && osTitleEl) {
            let label = activeLink.querySelector('span');
            osTitleEl.textContent = label ? label.textContent.trim() : activeLink.textContent.trim();
        }
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDesktopOS);
} else {
    initDesktopOS();
}
