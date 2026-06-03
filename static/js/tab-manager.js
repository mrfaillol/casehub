/**
 * CaseHub TabManager — Browser-within-browser tab system
 * Manages persistent iframe tabs with state preservation.
 *
 * Usage:
 *   const tabs = new TabManager({ maxTabs: 10 });
 *   tabs.openTab('/casehub/clients', 'Clientes', 'fas fa-users');
 *   tabs.switchTab('tab-id');
 *   tabs.closeTab('tab-id');
 */

class TabManager {
    constructor(options = {}) {
        this.maxTabs = options.maxTabs || 10;
        this.tabs = new Map();
        this.activeTab = 'home';
        this.tabOrder = ['home'];
        this.storageKey = 'casehub-tabs';

        this.tabBar = document.getElementById('tabList');
        this.contentArea = document.getElementById('tabContentArea');
        this.addBtn = document.getElementById('addTabBtn');

        if (!this.tabBar || !this.contentArea) return;

        this._bindEvents();
        this._restoreState();
    }

    /**
     * Open a tab. If URL already open, switch to it.
     * Only external URLs allowed — internal CaseHub pages navigate normally.
     */
    openTab(url, title, icon) {
        // Block internal CaseHub URLs — these should navigate normally, not iframe
        if (url.includes('/casehub/') || url.startsWith('/casehub')) {
            window.location.href = url;
            return null;
        }

        // Check if tab already exists for this URL
        for (const [id, tab] of this.tabs) {
            if (tab.url === url) {
                this.switchTab(id);
                return id;
            }
        }

        // Evict LRU if at max capacity
        if (this.tabs.size >= this.maxTabs) {
            this._evictLRU();
        }

        const tabId = 'tab-' + Date.now();

        // Create tab button
        const tabBtn = document.createElement('button');
        tabBtn.className = 'tab-bar__tab';
        tabBtn.dataset.tab = tabId;
        tabBtn.innerHTML = `
            <i class="${icon || 'fas fa-globe'}"></i>
            <span class="tab-bar__title">${this._escapeHtml(title)}</span>
            <span class="tab-bar__close" data-close="${tabId}" title="Fechar aba">&times;</span>
        `;
        tabBtn.addEventListener('click', (e) => {
            if (e.target.closest('.tab-bar__close')) return;
            this.switchTab(tabId);
        });
        tabBtn.querySelector('.tab-bar__close').addEventListener('click', (e) => {
            e.stopPropagation();
            this.closeTab(tabId);
        });
        this.tabBar.appendChild(tabBtn);

        // Create iframe pane
        const pane = document.createElement('div');
        pane.className = 'tab-pane';
        pane.id = tabId;

        const iframe = document.createElement('iframe');
        iframe.className = 'tab-iframe';
        iframe.setAttribute('loading', 'lazy');
        iframe.setAttribute('sandbox', 'allow-same-origin allow-scripts allow-forms allow-popups allow-modals');

        // Error handling for blocked iframes
        const fallback = document.createElement('div');
        fallback.className = 'tab-iframe-fallback';
        fallback.style.display = 'none';
        fallback.innerHTML = `
            <div class="tab-iframe-fallback__content">
                <i class="fas fa-external-link-alt" style="font-size: 2rem; margin-bottom: 1rem; opacity: 0.5;"></i>
                <p>Este site não permite ser exibido em uma aba interna.</p>
                <a href="${this._escapeHtml(url)}" target="_blank" rel="noopener noreferrer" class="glass-btn glass-btn--primary" style="margin-top: 1rem;">
                    <i class="fas fa-external-link-alt"></i> Abrir em nova janela
                </a>
            </div>
        `;

        iframe.addEventListener('error', () => {
            iframe.style.display = 'none';
            fallback.style.display = 'flex';
        });

        // Detect X-Frame-Options blocks (heuristic: if iframe is blank after timeout)
        setTimeout(() => {
            try {
                // Same-origin frames can be accessed
                if (iframe.contentDocument && iframe.contentDocument.body.innerHTML === '') {
                    // Might be blocked, but could also be loading
                }
            } catch (e) {
                // Cross-origin — can't check, but if no load event fired, show fallback
            }
        }, 5000);

        iframe.addEventListener('load', () => {
            // Successfully loaded
            fallback.style.display = 'none';
            iframe.style.display = 'block';
        });

        iframe.src = url;
        pane.appendChild(iframe);
        pane.appendChild(fallback);
        this.contentArea.appendChild(pane);

        // Store tab data
        this.tabs.set(tabId, {
            url,
            title,
            icon: icon || 'fas fa-globe',
            iframe,
            button: tabBtn,
            pane,
            fallback,
            lastActive: Date.now(),
        });
        this.tabOrder.push(tabId);

        // Switch to new tab
        this.switchTab(tabId);
        this._saveState();

        return tabId;
    }

    /**
     * Switch to a tab (hide current, show target). NO reload.
     */
    switchTab(tabId) {
        if (tabId === this.activeTab) return;

        // Deactivate current
        const currentBtn = this.tabBar.querySelector('.tab-bar__tab.active');
        if (currentBtn) currentBtn.classList.remove('active');

        const currentPane = this.contentArea.querySelector('.tab-pane.active');
        if (currentPane) currentPane.classList.remove('active');

        // Activate target
        if (tabId === 'home') {
            const homeBtn = this.tabBar.querySelector('[data-tab="home"]');
            const homePane = document.getElementById('tab-home');
            if (homeBtn) homeBtn.classList.add('active');
            if (homePane) homePane.classList.add('active');
        } else {
            const tab = this.tabs.get(tabId);
            if (!tab) return;
            tab.button.classList.add('active');
            tab.pane.classList.add('active');
            tab.lastActive = Date.now();
        }

        this.activeTab = tabId;
        this._saveState();

        // Scroll tab button into view
        const activeBtn = this.tabBar.querySelector('.tab-bar__tab.active');
        if (activeBtn) {
            activeBtn.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
        }
    }

    /**
     * Close a tab and remove its iframe from DOM.
     */
    closeTab(tabId) {
        if (tabId === 'home') return; // Can't close home

        const tab = this.tabs.get(tabId);
        if (!tab) return;

        // Remove from DOM
        tab.button.remove();
        tab.pane.remove();

        // Remove from state
        this.tabs.delete(tabId);
        this.tabOrder = this.tabOrder.filter(id => id !== tabId);

        // If closing active tab, switch to previous or home
        if (this.activeTab === tabId) {
            const prevTab = this.tabOrder[this.tabOrder.length - 1] || 'home';
            this.switchTab(prevTab);
        }

        this._saveState();
    }

    /**
     * Refresh a specific tab's iframe.
     */
    refreshTab(tabId) {
        const tab = this.tabs.get(tabId);
        if (!tab) return;
        tab.iframe.contentWindow.location.reload();
    }

    /**
     * Close all tabs except home.
     */
    closeAll() {
        for (const tabId of [...this.tabs.keys()]) {
            this.closeTab(tabId);
        }
    }

    // ─── Private ─────────────────────────────────────────────

    _bindEvents() {
        // Add tab button (opens prompt or URL bar)
        if (this.addBtn) {
            this.addBtn.addEventListener('click', () => {
                const url = prompt('URL da nova aba:');
                if (url) {
                    const title = url.replace(/^https?:\/\//, '').split('/')[0];
                    this.openTab(url, title, 'fas fa-globe');
                }
            });
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Ctrl+W — close current tab
            if (e.ctrlKey && e.key === 'w' && this.activeTab !== 'home') {
                e.preventDefault();
                this.closeTab(this.activeTab);
            }
            // Ctrl+Tab — next tab
            if (e.ctrlKey && e.key === 'Tab') {
                e.preventDefault();
                const idx = this.tabOrder.indexOf(this.activeTab);
                const nextIdx = e.shiftKey
                    ? (idx - 1 + this.tabOrder.length) % this.tabOrder.length
                    : (idx + 1) % this.tabOrder.length;
                this.switchTab(this.tabOrder[nextIdx]);
            }
        });
    }

    _saveState() {
        const state = {
            activeTab: this.activeTab,
            tabs: [],
        };
        for (const [id, tab] of this.tabs) {
            state.tabs.push({
                id,
                url: tab.url,
                title: tab.title,
                icon: tab.icon,
            });
        }
        try {
            localStorage.setItem(this.storageKey, JSON.stringify(state));
        } catch (e) {
            // localStorage full or unavailable
        }
    }

    _restoreState() {
        try {
            const raw = localStorage.getItem(this.storageKey);
            if (!raw) return;
            const state = JSON.parse(raw);
            if (!state.tabs || !Array.isArray(state.tabs)) return;

            for (const tab of state.tabs) {
                // Skip internal CaseHub URLs (legacy saved state)
                if (tab.url && (tab.url.includes('/casehub/') || tab.url.startsWith('/casehub'))) continue;
                this.openTab(tab.url, tab.title, tab.icon);
            }

            // Restore active tab
            if (state.activeTab && (state.activeTab === 'home' || this.tabs.has(state.activeTab))) {
                // Find the tab by URL since IDs are regenerated
                if (state.activeTab !== 'home') {
                    const originalTab = state.tabs.find(t => t.id === state.activeTab);
                    if (originalTab) {
                        for (const [id, tab] of this.tabs) {
                            if (tab.url === originalTab.url) {
                                this.switchTab(id);
                                break;
                            }
                        }
                    }
                }
            }
        } catch (e) {
            // Corrupted state, ignore
        }
    }

    _evictLRU() {
        let oldest = null;
        let oldestTime = Infinity;
        for (const [id, tab] of this.tabs) {
            if (tab.lastActive < oldestTime) {
                oldestTime = tab.lastActive;
                oldest = id;
            }
        }
        if (oldest) {
            this.closeTab(oldest);
        }
    }

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}

function initCaseHubTabs() {
    if (window.casehubTabs) return;
    if (document.getElementById('tabList')) {
        window.casehubTabs = new TabManager({ maxTabs: 10 });
    }
}

// Auto-initialize if tab bar exists in DOM. Deferred script execution can happen
// after inline listeners are registered, so initialize immediately once DOM is
// parse-ready instead of relying only on listener order.
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCaseHubTabs, { once: true });
} else {
    initCaseHubTabs();
}
