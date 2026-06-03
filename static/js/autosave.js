/**
 * CaseHub Form Auto-Save
 * Saves all form inputs to localStorage automatically.
 * Restores data on page load if the server was down or page refreshed.
 * Clears saved data on successful form submit.
 */
(function() {
    'use strict';

    const STORAGE_PREFIX = 'casehub_autosave_';
    const EXPIRY_HOURS = 24;
    const SAVE_DEBOUNCE_MS = 500;
    const EXCLUDE_FIELDS = ['password', 'token', 'csrf', 'csrfmiddlewaretoken'];
    const EXCLUDE_TYPES = ['file', 'hidden', 'submit', 'button', 'reset'];

    function getFormKey(form, index) {
        var action = form.getAttribute('action') || '';
        var id = form.id || ('form_' + index);
        return STORAGE_PREFIX + location.pathname + '_' + id + '_' + action;
    }

    function shouldSaveField(input) {
        if (!input.name) return false;
        var name = input.name.toLowerCase();
        for (var i = 0; i < EXCLUDE_FIELDS.length; i++) {
            if (name.indexOf(EXCLUDE_FIELDS[i]) !== -1) return false;
        }
        if (EXCLUDE_TYPES.indexOf(input.type) !== -1) return false;
        return true;
    }

    function saveForm(form, key) {
        var data = {};
        var inputs = form.querySelectorAll('input, textarea, select');
        var hasData = false;

        for (var i = 0; i < inputs.length; i++) {
            var el = inputs[i];
            if (!shouldSaveField(el)) continue;

            if (el.type === 'checkbox') {
                data[el.name] = el.checked;
                hasData = true;
            } else if (el.type === 'radio') {
                if (el.checked) {
                    data[el.name] = el.value;
                    hasData = true;
                }
            } else if (el.value && el.value.trim()) {
                data[el.name] = el.value;
                hasData = true;
            }
        }

        if (hasData) {
            var entry = {
                data: data,
                timestamp: Date.now(),
                url: location.href
            };
            try {
                localStorage.setItem(key, JSON.stringify(entry));
            } catch (e) {
                // localStorage full or unavailable
            }
        }
    }

    function restoreForm(form, key) {
        var raw = localStorage.getItem(key);
        if (!raw) return false;

        try {
            var entry = JSON.parse(raw);
        } catch (e) {
            localStorage.removeItem(key);
            return false;
        }

        // Check expiry
        var age = Date.now() - entry.timestamp;
        if (age > EXPIRY_HOURS * 60 * 60 * 1000) {
            localStorage.removeItem(key);
            return false;
        }

        var data = entry.data;
        var restored = 0;
        var inputs = form.querySelectorAll('input, textarea, select');

        for (var i = 0; i < inputs.length; i++) {
            var el = inputs[i];
            if (!el.name || !data.hasOwnProperty(el.name)) continue;
            if (!shouldSaveField(el)) continue;

            // Don't overwrite fields that already have user-entered values
            if (el.type === 'checkbox') {
                el.checked = data[el.name];
                restored++;
            } else if (el.type === 'radio') {
                if (el.value === data[el.name]) {
                    el.checked = true;
                    restored++;
                }
            } else if (!el.value || !el.value.trim()) {
                el.value = data[el.name];
                restored++;
            }
        }

        return restored > 0;
    }

    function showRestoreBanner(formCount) {
        var banner = document.createElement('div');
        banner.id = 'autosave-banner';
        banner.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:9999;' +
            'background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;' +
            'padding:10px 20px;text-align:center;font-size:14px;' +
            'box-shadow:0 2px 10px rgba(0,0,0,0.2);display:flex;' +
            'justify-content:center;align-items:center;gap:12px;';
        banner.innerHTML = '<i class="fas fa-undo-alt"></i> ' +
            '<span>Dados restaurados do auto-save (' + formCount + ' campo' +
            (formCount > 1 ? 's' : '') + ')</span>' +
            '<button onclick="this.parentElement.remove()" style="' +
            'background:rgba(255,255,255,0.2);border:none;color:#fff;' +
            'padding:4px 12px;border-radius:12px;cursor:pointer;font-size:12px;">' +
            'OK</button>' +
            '<button onclick="window._casehubAutosaveClear();this.parentElement.remove()" style="' +
            'background:rgba(255,0,0,0.3);border:none;color:#fff;' +
            'padding:4px 12px;border-radius:12px;cursor:pointer;font-size:12px;">' +
            'Descartar</button>';
        document.body.prepend(banner);

        // Auto-dismiss after 8 seconds
        setTimeout(function() {
            if (banner.parentElement) {
                banner.style.transition = 'opacity 0.5s';
                banner.style.opacity = '0';
                setTimeout(function() { banner.remove(); }, 500);
            }
        }, 8000);
    }

    function clearAllFormsOnPage() {
        var forms = document.querySelectorAll('form');
        for (var i = 0; i < forms.length; i++) {
            var key = getFormKey(forms[i], i);
            localStorage.removeItem(key);
        }
        // Reset form fields
        location.reload();
    }

    function init() {
        var forms = document.querySelectorAll('form');
        if (forms.length === 0) return;

        var totalRestored = 0;
        var saveTimers = {};

        // Expose clear function for the discard button
        window._casehubAutosaveClear = clearAllFormsOnPage;

        for (var i = 0; i < forms.length; i++) {
            (function(form, index) {
                var key = getFormKey(form, index);

                // Restore saved data
                if (restoreForm(form, key)) {
                    totalRestored++;
                }

                // Debounced save on input
                form.addEventListener('input', function() {
                    clearTimeout(saveTimers[key]);
                    saveTimers[key] = setTimeout(function() {
                        saveForm(form, key);
                    }, SAVE_DEBOUNCE_MS);
                });

                form.addEventListener('change', function() {
                    saveForm(form, key);
                });

                // Clear on successful submit
                form.addEventListener('submit', function() {
                    localStorage.removeItem(key);
                });
            })(forms[i], i);
        }

        if (totalRestored > 0) {
            showRestoreBanner(totalRestored);
        }
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
