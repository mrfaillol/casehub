/**
 * CaseHub User Activity Tracker
 * Captures comprehensive user activity for real-time monitoring
 * CaseHub - 2026
 */
(function() {
    'use strict';

    // Don't run on monitor pages
    if (window.location.pathname.startsWith('/monitor')) {
        return;
    }

    const CASEHUB_TRACKER = {
        // Configuration
        config: {
            endpoint: '/monitor/api/activity/track',
            sessionKey: 'ilc_session_id',
            heartbeatInterval: 10000, // 10 seconds
            scrollThreshold: 25, // Report scroll at 25%, 50%, 75%, 100%
            debug: false
        },

        // Session data
        sessionId: null,
        userId: null,
        userEmail: null,
        userName: null,
        userType: 'visitor',
        source: 'wordpress',

        // State tracking
        lastScrollDepth: 0,
        clickCount: 0,
        lastInteraction: Date.now(),

        // Initialize tracker
        init: function() {
            this.sessionId = this.getOrCreateSession();
            this.detectSource();
            this.detectUser();

            // Track initial pageview
            this.trackEvent('pageview', {
                referrer: document.referrer
            });

            // Setup event listeners
            this.setupClickTracking();
            this.setupScrollTracking();
            this.setupFormTracking();
            this.setupNavigationTracking();

            // Heartbeat for "still here" status
            this.startHeartbeat();

            // Track page unload
            window.addEventListener('beforeunload', () => {
                this.trackEvent('page_exit', {}, true);
            });

            if (this.config.debug) {
                console.log('[CASEHUB-TRACKER] Initialized', {
                    sessionId: this.sessionId,
                    source: this.source,
                    userType: this.userType
                });
            }
        },

        // Detect which application we're on
        detectSource: function() {
            const path = window.location.pathname;
            if (path.startsWith('/casehub') || path.startsWith('/CASEHUB')) {
                this.source = 'casehub';
            } else if (path.startsWith('/tools') || path.startsWith('/TOOLS')) {
                this.source = 'ilc-tools';
            } else if (path.startsWith('/intake') || path.startsWith('/portal')) {
                this.source = 'portal';
            } else {
                this.source = 'wordpress';
            }
        },

        // Get or create session ID
        getOrCreateSession: function() {
            let sessionId = sessionStorage.getItem(this.config.sessionKey);
            if (!sessionId) {
                sessionId = 'ses_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
                sessionStorage.setItem(this.config.sessionKey, sessionId);
            }
            return sessionId;
        },

        // Detect logged-in user
        detectUser: function() {
            // CaseHub Tools detection via meta tag
            const userMeta = document.querySelector('meta[name="casehub-user"], meta[name="ilc-user"]');
            if (userMeta) {
                this.userId = userMeta.dataset.userId || userMeta.getAttribute('data-user-id');
                this.userEmail = userMeta.dataset.email || userMeta.getAttribute('data-email');
                this.userName = userMeta.dataset.name || userMeta.getAttribute('data-name');
                this.userType = userMeta.dataset.type || userMeta.getAttribute('data-type') || 'staff';
            }

            // WordPress detection
            if (document.body && document.body.classList.contains('logged-in')) {
                this.userType = this.userType === 'visitor' ? 'wordpress_user' : this.userType;
            }

            // Admin detection
            if (this.userEmail) {
                const email = this.userEmail.toLowerCase();
                if (email.includes('victor') || email.includes('admin@') || email === '${process.env.ADMIN_EMAIL || "admin@casehub.app"}') {
                    this.userType = 'admin';
                }
            }

            // Check for admin class on body
            if (document.body && (document.body.classList.contains('admin') || document.body.classList.contains('administrator'))) {
                this.userType = 'admin';
            }
        },

        // Main tracking function
        trackEvent: function(eventType, data, sync) {
            const payload = {
                session_id: this.sessionId,
                event_type: eventType,
                source: this.source,
                page_url: window.location.pathname + window.location.search,
                page_title: document.title,
                timestamp: new Date().toISOString(),
                user_id: this.userId,
                user_email: this.userEmail,
                user_name: this.userName,
                user_type: this.userType,
                ...data
            };

            // Update last interaction time
            this.lastInteraction = Date.now();

            // Send via beacon API (doesn't block page unload)
            if (navigator.sendBeacon && !sync) {
                const blob = new Blob([JSON.stringify(payload)], {type: 'application/json'});
                navigator.sendBeacon(this.config.endpoint, blob);
            } else {
                // Fallback to fetch
                fetch(this.config.endpoint, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload),
                    keepalive: true
                }).catch(() => {});
            }

            if (this.config.debug) {
                console.log('[CASEHUB-TRACKER]', eventType, payload);
            }
        },

        // Track ALL clicks
        setupClickTracking: function() {
            document.addEventListener('click', (e) => {
                const target = e.target.closest('a, button, [role="button"], input[type="submit"], .btn, .elementor-button');
                if (!target) return;

                this.clickCount++;

                // Get element info
                let elementText = '';
                if (target.textContent) {
                    elementText = target.textContent.trim().substring(0, 100);
                } else if (target.value) {
                    elementText = target.value.substring(0, 100);
                } else if (target.getAttribute('aria-label')) {
                    elementText = target.getAttribute('aria-label');
                }

                this.trackEvent('click', {
                    element_id: target.id || null,
                    element_type: target.tagName.toLowerCase(),
                    element_text: elementText,
                    metadata: {
                        click_number: this.clickCount,
                        href: target.href || null,
                        class: (target.className || '').substring(0, 100)
                    }
                });
            }, true);
        },

        // Track scroll depth
        setupScrollTracking: function() {
            let scrollTimeout;
            window.addEventListener('scroll', () => {
                clearTimeout(scrollTimeout);
                scrollTimeout = setTimeout(() => {
                    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
                    const docHeight = Math.max(
                        document.documentElement.scrollHeight,
                        document.body.scrollHeight
                    ) - window.innerHeight;

                    if (docHeight <= 0) return;

                    const scrollPercent = Math.round((scrollTop / docHeight) * 100);

                    // Report at thresholds
                    const thresholds = [25, 50, 75, 100];
                    for (const threshold of thresholds) {
                        if (scrollPercent >= threshold && this.lastScrollDepth < threshold) {
                            this.trackEvent('scroll', {
                                metadata: {
                                    scroll_depth: threshold,
                                    scroll_pixels: scrollTop
                                }
                            });
                            this.lastScrollDepth = threshold;
                        }
                    }
                }, 200);
            });
        },

        // Track form interactions
        setupFormTracking: function() {
            // Form field focus
            document.addEventListener('focus', (e) => {
                if (e.target.matches('input, select, textarea')) {
                    const form = e.target.closest('form');
                    const formId = form ? (form.id || form.getAttribute('name') || 'form') : 'no_form';

                    this.trackEvent('form_interaction', {
                        element_id: e.target.id || e.target.name,
                        element_type: e.target.type || e.target.tagName.toLowerCase(),
                        metadata: {
                            action: 'focus',
                            form_id: formId
                        }
                    });
                }
            }, true);

            // Form submissions
            document.addEventListener('submit', (e) => {
                const form = e.target;
                this.trackEvent('form_submit', {
                    element_id: form.id || form.getAttribute('name') || null,
                    metadata: {
                        form_id: form.id || form.getAttribute('name') || 'unknown',
                        form_action: form.action,
                        form_method: form.method
                    }
                });
            }, true);
        },

        // Track SPA navigation
        setupNavigationTracking: function() {
            // History API
            const originalPushState = history.pushState;
            const self = this;

            history.pushState = function(...args) {
                originalPushState.apply(history, args);
                setTimeout(() => {
                    self.lastScrollDepth = 0; // Reset scroll tracking
                    self.trackEvent('navigation', {referrer: document.referrer});
                }, 0);
            };

            window.addEventListener('popstate', () => {
                this.lastScrollDepth = 0;
                this.trackEvent('navigation', {referrer: document.referrer});
            });
        },

        // Heartbeat to maintain "online" status
        startHeartbeat: function() {
            setInterval(() => {
                // Only send heartbeat if user was active in last 60 seconds
                const isActive = (Date.now() - this.lastInteraction) < 60000;

                this.trackEvent('heartbeat', {
                    metadata: {
                        visible: !document.hidden,
                        active: isActive,
                        idle_seconds: Math.round((Date.now() - this.lastInteraction) / 1000)
                    }
                });
            }, this.config.heartbeatInterval);
        }
    };

    // Initialize when DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => CASEHUB_TRACKER.init());
    } else {
        CASEHUB_TRACKER.init();
    }

    // Expose for debugging
    window.CASEHUB_TRACKER = CASEHUB_TRACKER;
})();
