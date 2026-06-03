/**
 * CaseHub — Onboarding Subdomain Live-Check
 *
 * Watches the slug input, debounces network calls to
 * /api/onboarding/check-subdomain, and updates the visual state
 * (available / reserved / taken / invalid) with the canonical
 * neuromorphic design tokens.
 *
 * Compatible with the wizard step at /setup/subdomain (Fatia C).
 * Loaded as `defer` so DOM is parsed.
 */
(function () {
    "use strict";

    var cfg = window.CASEHUB_SUBDOMAIN_CHECK || {};
    var endpoint = cfg.endpoint || "/api/onboarding/check-subdomain";
    var locale = cfg.locale === "lite" ? "lite" : "default";
    var msgs = (cfg.messages && cfg.messages[locale]) || {};

    var row = document.getElementById("slug-row");
    var input = document.getElementById("slug-input");
    var status = document.getElementById("slug-status");
    var previewText = document.getElementById("slug-preview-text");
    var suggestionsBox = document.getElementById("slug-suggestions");
    var submitBtn = document.getElementById("submit-btn");
    var iconHolder = document.getElementById("slug-icon");

    if (!row || !input || !status || !submitBtn) return;

    var debounceMs = 320;
    var debounceTimer = null;
    var inflightController = null;
    var lastCheckedSlug = "";

    function setState(state) {
        row.classList.remove("is-checking", "is-available", "is-error");
        status.classList.remove("is-available", "is-error");
        if (state === "checking") {
            row.classList.add("is-checking");
            iconHolder.innerHTML = '<span class="spinner" role="presentation"></span>';
        } else if (state === "available") {
            row.classList.add("is-available");
            status.classList.add("is-available");
            iconHolder.innerHTML = '<i class="fas fa-check-circle"></i>';
        } else if (state === "error") {
            row.classList.add("is-error");
            status.classList.add("is-error");
            iconHolder.innerHTML = '<i class="fas fa-circle-xmark"></i>';
        } else {
            iconHolder.innerHTML = '<i class="fas fa-circle-question"></i>';
        }
    }

    function renderSuggestions(list) {
        suggestionsBox.innerHTML = "";
        if (!list || !list.length) {
            suggestionsBox.hidden = true;
            return;
        }
        list.slice(0, 5).forEach(function (s) {
            var chip = document.createElement("button");
            chip.type = "button";
            chip.className = "slug-suggestion";
            chip.textContent = s;
            chip.setAttribute("aria-label", locale === "lite" ? "Usar sugestão " + s : "Use suggestion " + s);
            chip.addEventListener("click", function () {
                input.value = s;
                input.focus();
                triggerCheck(true);
            });
            suggestionsBox.appendChild(chip);
        });
        suggestionsBox.hidden = false;
    }

    function updatePreview(slugForDisplay) {
        if (!previewText) return;
        var display = slugForDisplay || "...";
        previewText.textContent = display + ".casehub.legal";
    }

    function setSubmit(enabled) {
        submitBtn.disabled = !enabled;
    }

    function checkSlug(slug, opts) {
        opts = opts || {};
        if (inflightController) inflightController.abort();
        inflightController = new AbortController();

        if (!slug) {
            setState("error");
            status.textContent = msgs.empty || "Empty";
            renderSuggestions(null);
            setSubmit(false);
            updatePreview("");
            return;
        }

        setState("checking");
        status.textContent = msgs.checking || "Checking…";

        var url = endpoint + "?slug=" + encodeURIComponent(slug);
        fetch(url, { signal: inflightController.signal, credentials: "same-origin" })
            .then(function (r) {
                if (!r.ok) throw new Error("HTTP " + r.status);
                return r.json();
            })
            .then(function (data) {
                lastCheckedSlug = slug;
                updatePreview(data.canonical_slug || slug);

                if (data.available) {
                    setState("available");
                    status.textContent = data.message || msgs.available || "Available";
                    renderSuggestions(null);
                    setSubmit(true);
                } else {
                    setState("error");
                    var key = data.reason || "invalid";
                    status.textContent = data.message || msgs[key] || msgs.invalid;
                    renderSuggestions(data.suggestions);
                    setSubmit(false);
                }
            })
            .catch(function (err) {
                if (err.name === "AbortError") return;
                setState("error");
                status.textContent = msgs.network || "Network error";
                setSubmit(false);
            });
    }

    function triggerCheck(immediate) {
        clearTimeout(debounceTimer);
        var raw = (input.value || "").trim();
        updatePreview(raw);
        if (immediate) {
            checkSlug(raw, { immediate: true });
        } else {
            debounceTimer = setTimeout(function () {
                checkSlug(raw);
            }, debounceMs);
        }
    }

    input.addEventListener("input", function () { triggerCheck(false); });
    input.addEventListener("blur", function () {
        if ((input.value || "").trim() !== lastCheckedSlug) triggerCheck(true);
    });

    // Initial: if the input has a server-suggested value, check it immediately
    if ((input.value || "").trim()) {
        triggerCheck(true);
    } else {
        setState("idle");
        status.textContent = "";
        updatePreview("");
        setSubmit(false);
    }

    // Guard: block submit if not validated
    document.getElementById("subdomain-form").addEventListener("submit", function (e) {
        if (submitBtn.disabled) {
            e.preventDefault();
            input.focus();
        }
    });
})();
