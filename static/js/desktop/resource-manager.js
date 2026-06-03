class ResourceManager {
    constructor() {
        this.maxBlurElements = 2;
        this.activeWindows = new Set();
        this.observer = null;
        this.frameCount = 0;
        this.lastTime = performance.now();
        this.fps = 60;
        this.isPerformanceMode = false;

        // Idle suspension: window → last activity timestamp
        this.windowActivity = new Map();
        this.idleTimeoutMs = 120000; // 2 minutes without interaction
        this.idleCheckMs = 30000;    // check every 30s

        // Detect device capability and set max windows
        this.detectCapability();

        this.initObserver();
        this.startFPSMonitor();
        this.startIdleMonitor();
        this.trackWindowActivity();
        this.updateIndicator();

        // Prefetch common routes for faster window loading
        this.prefetchCommonRoutes();
    }

    // Track any interaction inside a window to reset its idle timer
    trackWindowActivity() {
        document.addEventListener('pointerdown', (e) => {
            const winEl = e.target.closest?.('.macos-window');
            if (winEl && winEl.id) this.windowActivity.set(winEl.id, Date.now());
        }, true);
        // Iframe clicks: window.blur fires when focus enters iframe
        window.addEventListener('blur', () => {
            setTimeout(() => {
                if (document.activeElement && document.activeElement.tagName === 'IFRAME') {
                    const winEl = document.activeElement.closest('.macos-window');
                    if (winEl) this.windowActivity.set(winEl.id, Date.now());
                }
            }, 50);
        });
    }

    // Suspend idle windows (no interaction for idleTimeoutMs)
    startIdleMonitor() {
        setInterval(() => {
            if (!window.osWindowManager) return;
            const now = Date.now();
            const focusedId = this.getFocusedWindowId();
            window.osWindowManager.windows.forEach((win, id) => {
                if (id === 'win-home') return;              // never suspend home
                if (win.state === 'minimized') return;      // already suspended
                if (id === focusedId) return;               // never suspend focused
                if (!this.activeWindows.has(id)) return;    // already suspended
                const last = this.windowActivity.get(id) || now;
                if (now - last > this.idleTimeoutMs) {
                    this.suspendWindow(id);
                }
            });
        }, this.idleCheckMs);
    }

    getFocusedWindowId() {
        if (!window.osWindowManager) return null;
        let topZ = -1, topId = null;
        window.osWindowManager.windows.forEach((win, id) => {
            const z = parseInt(win.el.style.zIndex) || 0;
            if (z > topZ) { topZ = z; topId = id; }
        });
        return topId;
    }

    // Detect device RAM/CPU and adjust max active windows
    detectCapability() {
        const memory = navigator.deviceMemory || 4; // GB (Chrome only, defaults 4)
        const cores = navigator.hardwareConcurrency || 4;
        if (memory <= 2 || cores <= 2) {
            this.maxActiveWindows = 2;
        } else if (memory <= 4 || cores <= 4) {
            this.maxActiveWindows = 3;
        } else {
            this.maxActiveWindows = 5;
        }
    }

    // Prefetch most-used routes so windows open faster
    prefetchCommonRoutes() {
        const routes = ['/casehub/clients', '/casehub/tasks', '/casehub/documents'];
        routes.forEach(url => {
            const link = document.createElement('link');
            link.rel = 'prefetch';
            link.href = url + '?desktop_frame=1';
            document.head.appendChild(link);
        });
    }

    // Restore session windows gradually (1 per 500ms, not all at once)
    async restoreSessionGradually() {
        try {
            const raw = localStorage.getItem('casehub-desktop-session');
            if (!raw) return;
            const session = JSON.parse(raw);
            if (!Array.isArray(session) || session.length === 0) return;

            for (let i = 0; i < session.length && i < this.maxActiveWindows; i++) {
                const s = session[i];
                if (!s.url) continue;
                await new Promise(r => setTimeout(r, 600));
                if (window.osWindowManager) {
                    window.osWindowManager.launchApp(s.url, s.title, s.iconClass);
                }
            }
        } catch (e) {
            // Corrupted session, ignore
        }
    }

    initObserver() {
        if ('IntersectionObserver' in window) {
            this.observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    const el = entry.target;
                    // Disable blur locally when completely off view
                    if (!entry.isIntersecting && !this.isPerformanceMode) {
                        el.classList.add('viewport-hidden');
                    } else {
                        el.classList.remove('viewport-hidden');
                    }
                });
            }, { threshold: 0 });
        }
    }

    observeElement(el) {
        if (this.observer) {
            this.observer.observe(el);
        }
    }

    registerWindow(windowId, winEl, iframeEl) {
        if (this.activeWindows.size >= this.maxActiveWindows) {
            const oldestWin = Array.from(this.activeWindows)[0];
            this.suspendWindow(oldestWin);
        }

        this.activeWindows.add(windowId);
        this.windowActivity.set(windowId, Date.now());
        this.updateIndicator();

        if (iframeEl && iframeEl.src && !iframeEl.dataset.originalSrc) {
            iframeEl.dataset.originalSrc = iframeEl.src;
        }
    }

    suspendWindow(windowId) {
        if (!this.activeWindows.has(windowId)) return;

        this.activeWindows.delete(windowId);
        const win = window.osWindowManager ? window.osWindowManager.windows.get(windowId) : null;
        if (!win || !win.el) { this.updateIndicator(); return; }

        win.el.classList.add('suspended');
        const iframe = win.el.querySelector('iframe');
        if (iframe) {
            if (!iframe.dataset.originalSrc && iframe.src && iframe.src !== 'about:blank') {
                iframe.dataset.originalSrc = iframe.src;
            }
            iframe.src = 'about:blank'; // Free memory + pause server/client traffic
        }

        // Clickable overlay — click to reactivate
        let content = win.el.querySelector('.macos-window-content');
        if (content && !content.querySelector('.suspended-overlay')) {
            const overlay = document.createElement('div');
            overlay.className = 'suspended-overlay';
            overlay.innerHTML = `
                <div class="suspended-inner">
                    <i class="fas fa-moon"></i>
                    <div class="suspended-title">${win.title || 'App'} suspenso</div>
                    <div class="suspended-subtitle">Dados preservados. Clique para reativar.</div>
                </div>
            `;
            overlay.addEventListener('click', () => this.activateWindow(windowId));
            content.appendChild(overlay);
        }
        this.updateIndicator();
    }

    activateWindow(windowId) {
        if (this.activeWindows.has(windowId)) return;
        
        this.registerWindow(windowId, null, null);
        
        const win = window.osWindowManager ? window.osWindowManager.windows.get(windowId) : null;
        if (win && win.el) {
            win.el.classList.remove('suspended');
            const iframe = win.el.querySelector('iframe');
            if (iframe && iframe.dataset.originalSrc) {
                iframe.src = iframe.dataset.originalSrc;
            }
            const overlay = win.el.querySelector('.suspended-overlay');
            if (overlay) overlay.remove();
        }
    }

    startFPSMonitor() {
        const loop = (now) => {
            // Skip ALL work during drag — let main thread focus on cursor tracking
            if (this.fpsLoopPaused || window.__OS_DRAGGING__) {
                requestAnimationFrame(loop);
                return;
            }
            this.frameCount++;
            if (now - this.lastTime >= 1000) {
                this.fps = this.frameCount;
                this.frameCount = 0;
                this.lastTime = now;
                this.checkPerformance();
            }
            requestAnimationFrame(loop);
        };
        requestAnimationFrame(loop);
    }

    checkPerformance() {
        if (!this._startTime) this._startTime = performance.now();
        if (performance.now() - this._startTime < 10000) return;

        // Camada 5: adaptive suspension by FPS pressure
        const focusedId = window.osWindowManager ? window.osWindowManager.windows.get('win-home')?.id : null;
        let topZ = -1, topId = null;
        if (window.osWindowManager) {
            window.osWindowManager.windows.forEach((win, id) => {
                const z = parseInt(win.el.style.zIndex) || 0;
                if (z > topZ) { topZ = z; topId = id; }
            });
        }

        // Heap pressure check
        const mem = performance.memory;
        const heapRatio = mem ? mem.usedJSHeapSize / mem.jsHeapSizeLimit : 0;

        // FPS 30-49 OR heap > 70%: suspend non-focused after shorter idle (60s vs default 120s)
        if ((this.fps >= 30 && this.fps < 50) || heapRatio > 0.7) {
            this.idleTimeoutMs = 60000;
        } else if (this.fps >= 15 && this.fps < 30) {
            // FPS 15-29: aggressive — suspend ALL non-focused immediately
            if (window.osWindowManager) {
                window.osWindowManager.windows.forEach((win, id) => {
                    if (id === 'win-home' || id === topId) return;
                    if (win.state === 'minimized') return;
                    if (this.activeWindows.has(id)) this.suspendWindow(id);
                });
            }
            this.idleTimeoutMs = 30000;
        } else if (this.fps < 15 && this.fps > 0) {
            // Critical: activate performance mode (disable all blur)
            if (!this.isPerformanceMode) {
                this.isPerformanceMode = true;
                document.body.classList.add('performance-mode');
            }
        } else {
            // Normal operation
            this.idleTimeoutMs = 120000;
            if (this.isPerformanceMode && this.fps >= 45) {
                this.isPerformanceMode = false;
                document.body.classList.remove('performance-mode');
            }
        }
        this.updateIndicator();
    }

    updateIndicator() {
        // Build floating monitor widget once, persistent in UI
        let widget = document.getElementById('osResourceMonitor');
        if (!widget) {
            widget = document.createElement('div');
            widget.id = 'osResourceMonitor';
            widget.innerHTML = `
                <div class="orm-compact">
                    <div class="orm-metric" title="Janelas ativas / máximo">
                        <span class="orm-dot"></span>
                        <span class="orm-label">WIN</span>
                        <span class="orm-value" id="ormWindows">0/0</span>
                    </div>
                    <div class="orm-sep"></div>
                    <div class="orm-metric" title="Frames por segundo">
                        <span class="orm-label">FPS</span>
                        <span class="orm-value" id="ormFps">60</span>
                    </div>
                </div>
                <div class="orm-expanded">
                    <div class="orm-header">
                        <strong>Monitor do Sistema</strong>
                        <button class="orm-close" aria-label="Fechar">×</button>
                    </div>
                    <div class="orm-row"><span>Janelas ativas</span><b id="ormExpWindows">0/0</b></div>
                    <div class="orm-row"><span>FPS atual</span><b id="ormExpFps">60</b></div>
                    <div class="orm-row"><span>Memória detectada</span><b id="ormExpMem">—</b></div>
                    <div class="orm-row"><span>CPU (cores)</span><b id="ormExpCores">—</b></div>
                    <div class="orm-row"><span>Status</span><b id="ormExpStatus">Estável</b></div>
                    <div class="orm-divider"></div>
                    <div class="orm-controls">
                        <div class="orm-control-row">
                            <div class="orm-control-info">
                                <strong>Modo Economia</strong>
                                <small>Desliga blur e animações caras para máxima performance.</small>
                            </div>
                            <label class="orm-toggle">
                                <input type="checkbox" id="ormTogglePerf">
                                <span class="orm-toggle-track"><span class="orm-toggle-thumb"></span></span>
                            </label>
                        </div>
                        <div class="orm-control-row">
                            <div class="orm-control-info">
                                <strong>Suspender inativas</strong>
                                <small>Libera memória de janelas abertas mas não usadas agora.</small>
                            </div>
                            <button class="orm-btn" id="ormSuspendAll">Suspender</button>
                        </div>
                        <div class="orm-control-row">
                            <div class="orm-control-info">
                                <strong>Fechar todas</strong>
                                <small>Encerra todas as janelas abertas (sessão preservada).</small>
                            </div>
                            <button class="orm-btn orm-btn-danger" id="ormCloseAll">Fechar todas</button>
                        </div>
                    </div>
                    <p class="orm-help">
                        O CaseHub gerencia recursos automaticamente — janelas inativas por 2min são suspensas,
                        FPS baixo ativa Modo Economia. Os controles acima são para override manual.
                    </p>
                </div>
            `;

            // Preferir anexar dentro do cluster global (flex com bell) se existir
            const chromeHost = document.getElementById('osGlobalChrome');
            if (chromeHost) {
                chromeHost.appendChild(widget);
                widget.classList.add('in-global-chrome');
            } else {
                document.body.appendChild(widget);
            }

            // Click toggles expanded (ignora cliques nos controles internos pra não fechar)
            widget.addEventListener('click', (e) => {
                if (e.target.closest('.orm-controls') || e.target.closest('input,button,label')) return;
                widget.classList.toggle('expanded');
            });

            // Close button explícito
            const closeBtn = widget.querySelector('.orm-close');
            if (closeBtn) {
                closeBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    widget.classList.remove('expanded');
                });
            }

            // Controles ação
            const togglePerf = widget.querySelector('#ormTogglePerf');
            if (togglePerf) {
                // Sincroniza estado inicial com body
                togglePerf.checked = document.body.classList.contains('performance-mode');
                togglePerf.addEventListener('change', (e) => {
                    document.body.classList.toggle('performance-mode', e.target.checked);
                    try { localStorage.setItem('casehub-perf-mode', e.target.checked ? '1' : '0'); } catch(_) {}
                });
            }

            const suspendBtn = widget.querySelector('#ormSuspendAll');
            if (suspendBtn) {
                suspendBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (window.osWindowManager && window.osWindowManager.suspendInactive) {
                        window.osWindowManager.suspendInactive();
                    } else if (window.osWindowManager && window.osWindowManager.windows) {
                        // Fallback: minimiza todas que não têm foco recente
                        window.osWindowManager.windows.forEach(w => {
                            if (w.state !== 'minimized' && !w.el.classList.contains('window-focused')) {
                                window.osWindowManager.minimizeWindow?.(w.id);
                            }
                        });
                    }
                });
            }

            const closeAllBtn = widget.querySelector('#ormCloseAll');
            if (closeAllBtn) {
                closeAllBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    if (!confirm('Fechar todas as janelas abertas?')) return;
                    if (window.osWindowManager && window.osWindowManager.windows) {
                        const ids = Array.from(window.osWindowManager.windows.keys());
                        ids.forEach(id => window.osWindowManager.closeWindow?.(id));
                    }
                });
            }

            // Restaura Modo Economia do localStorage
            try {
                if (localStorage.getItem('casehub-perf-mode') === '1') {
                    document.body.classList.add('performance-mode');
                    if (togglePerf) togglePerf.checked = true;
                }
            } catch(_) {}
        }

        const winVal = document.getElementById('ormWindows');
        const fpsVal = document.getElementById('ormFps');
        const dot = widget.querySelector('.orm-dot');
        if (!winVal || !fpsVal || !dot) return;

        const shownFps = Math.min(60, this.fps || 60);
        winVal.textContent = `${this.activeWindows.size}/${this.maxActiveWindows}`;
        fpsVal.textContent = shownFps;

        dot.className = 'orm-dot';
        let status = 'Estável';
        if (this.isPerformanceMode || this.fps < 30) {
            dot.classList.add('critical');
            status = 'Crítico';
        } else if (this.activeWindows.size >= this.maxActiveWindows || this.fps < 50) {
            dot.classList.add('warn');
            status = 'Alto uso';
        }

        // Expanded panel values
        const byId = (id) => document.getElementById(id);
        if (byId('ormExpWindows'))  byId('ormExpWindows').textContent = `${this.activeWindows.size}/${this.maxActiveWindows}`;
        if (byId('ormExpFps'))      byId('ormExpFps').textContent = shownFps;
        if (byId('ormExpMem'))      byId('ormExpMem').textContent = (navigator.deviceMemory || '—') + ' GB';
        if (byId('ormExpCores'))    byId('ormExpCores').textContent = navigator.hardwareConcurrency || '—';
        if (byId('ormExpStatus'))   byId('ormExpStatus').textContent = status;

        widget.title = `Clique para mais informações`;
    }
}

// Initialize Resource Manager when document is ready
document.addEventListener('DOMContentLoaded', () => {
    if (document.body.classList.contains('desktop')) {
        window.osResourceManager = new ResourceManager();
        // Session auto-restore disabled — apps load on demand (economy principle)
    }
});
