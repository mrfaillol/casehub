/**
 * CaseHub - Documents inline preview
 * Issue #287
 *
 * Backwards-compatible global `openPreview` consumed by inline onclick handlers in
 * `templates/documents/list.html`. Adds:
 *   - explicit ESC handler (defensive; Bootstrap 5 already binds ESC, but the modal
 *     is sometimes opened without bootstrap.Modal available — see #207)
 *   - focus restoration to the trigger element on close
 *   - aria-modal=true / aria-labelledby
 *   - image lightbox (click-to-zoom toggle)
 *   - in-modal fallback for unsupported mime types instead of forcing window.open
 *
 * PDF.js vendoring (per issue #287 spec) is intentionally deferred: same-origin iframe
 * over `/documents/{id}/preview` (which sets Content-Disposition: inline) renders
 * natively in current Chrome/Firefox/Safari. Vendoring is only required for browsers
 * without built-in PDF rendering or for an air-gap deploy. Tracked separately.
 */
(function () {
    'use strict';

    var lastTrigger = null;
    var imageZoomed = false;

    function getModalEl() {
        return document.getElementById('previewModal');
    }

    function getBootstrapModal(el) {
        if (typeof bootstrap === 'undefined' || !bootstrap.Modal || !el) return null;
        return bootstrap.Modal.getOrCreateInstance(el);
    }

    function setHiddenState(el, hidden) {
        if (!el) return;
        el.style.display = hidden ? 'none' : 'block';
    }

    function showFallback(name, downloadUrl) {
        var body = document.querySelector('#previewModal .modal-body');
        if (!body) return;
        var existing = body.querySelector('.preview-fallback');
        if (existing) existing.remove();

        var wrap = document.createElement('div');
        wrap.className = 'preview-fallback';
        wrap.setAttribute('role', 'status');
        wrap.style.padding = '48px 24px';
        wrap.style.textAlign = 'center';

        var icon = document.createElement('i');
        icon.className = 'fas fa-file-alt';
        icon.setAttribute('aria-hidden', 'true');
        icon.style.fontSize = '48px';
        icon.style.opacity = '0.4';
        icon.style.marginBottom = '16px';
        wrap.appendChild(icon);

        var p = document.createElement('p');
        p.style.margin = '0 0 16px';
        p.style.color = 'rgba(255,255,255,0.85)';
        p.textContent = 'Pré-visualização não disponível para ' + (name || 'este formato') + '.';
        wrap.appendChild(p);

        var link = document.createElement('a');
        link.className = 'btn btn-outline-light btn-sm';
        link.setAttribute('download', '');
        link.href = downloadUrl;
        var dlIcon = document.createElement('i');
        dlIcon.className = 'fas fa-download me-1';
        dlIcon.setAttribute('aria-hidden', 'true');
        link.appendChild(dlIcon);
        link.appendChild(document.createTextNode('Baixar arquivo'));
        wrap.appendChild(link);

        body.appendChild(wrap);
    }

    function clearFallback() {
        var body = document.querySelector('#previewModal .modal-body');
        var existing = body && body.querySelector('.preview-fallback');
        if (existing) existing.remove();
    }

    function toggleImageZoom() {
        var img = document.getElementById('previewImage');
        if (!img) return;
        imageZoomed = !imageZoomed;
        img.classList.toggle('preview-image--zoomed', imageZoomed);
    }

    function openPreview(name, previewUrl, mimeType, downloadUrl) {
        // Backwards-compat: legacy callers passed only 3 args with the download URL
        // doubling as the iframe src. Keep both behaviors working.
        if (typeof downloadUrl === 'undefined') downloadUrl = previewUrl;

        var modalEl = getModalEl();
        if (!modalEl) return;

        lastTrigger = document.activeElement;

        var titleEl = document.getElementById('previewTitle');
        var dlEl = document.getElementById('previewDownload');
        var openEl = document.getElementById('previewOpen');
        var frame = document.getElementById('previewFrame');
        var img = document.getElementById('previewImage');

        if (titleEl) titleEl.textContent = name;
        if (dlEl) dlEl.href = downloadUrl;

        clearFallback();
        imageZoomed = false;
        if (img) img.classList.remove('preview-image--zoomed');

        // Only INERT raster image types render inline. image/svg+xml is active
        // content (embedded <script>/event handlers execute same-origin via
        // /preview). Drive sync / external imports may produce SVG mime even
        // though local uploads reject .svg, so guard at render time. Anything
        // outside the allowlist falls through to the download fallback below.
        // Codex 2026-05-08 P2 finding on #295.
        var INERT_IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp', 'image/bmp', 'image/tiff'];
        var mimeLower = (mimeType || '').toLowerCase();
        var isImage = INERT_IMAGE_TYPES.indexOf(mimeLower) !== -1;
        var isPdf = mimeLower === 'application/pdf';

        // The "Abrir" link points to the inline /preview URL for renderable
        // types (PDF, allowlisted images) and to the /download URL for
        // unsupported types — otherwise clicking "Abrir" on a fallback modal
        // for image/svg+xml would still open active SVG same-origin.
        // Codex 2026-05-08 P2 follow-up.
        if (openEl) openEl.href = (isImage || isPdf) ? previewUrl : downloadUrl;

        if (isImage) {
            setHiddenState(frame, true);
            setHiddenState(img, false);
            if (img) {
                img.src = previewUrl;
                img.alt = name;
            }
        } else if (isPdf) {
            setHiddenState(img, true);
            setHiddenState(frame, false);
            if (frame) frame.src = previewUrl;
        } else {
            setHiddenState(img, true);
            setHiddenState(frame, true);
            showFallback(name, downloadUrl);
        }

        modalEl.setAttribute('aria-modal', 'true');
        var bsModal = getBootstrapModal(modalEl);
        if (bsModal) bsModal.show();
    }

    function onHidden() {
        var frame = document.getElementById('previewFrame');
        var img = document.getElementById('previewImage');
        if (frame) frame.src = '';
        if (img) img.src = '';
        clearFallback();
        if (lastTrigger && typeof lastTrigger.focus === 'function') {
            try { lastTrigger.focus(); } catch (_) {}
        }
        lastTrigger = null;
    }

    function onKeydown(e) {
        if (e.key !== 'Escape') return;
        var modalEl = getModalEl();
        if (!modalEl || !modalEl.classList.contains('show')) return;
        var bsModal = getBootstrapModal(modalEl);
        if (bsModal) bsModal.hide();
    }

    function init() {
        var modalEl = getModalEl();
        if (!modalEl) return;
        modalEl.addEventListener('hidden.bs.modal', onHidden);
        var img = document.getElementById('previewImage');
        if (img) img.addEventListener('click', toggleImageZoom);
        document.addEventListener('keydown', onKeydown);

        // Event delegation: server-rendered triggers use [data-preview-trigger]
        // + dataset.previewName/Url/Mime/Download instead of inline onclick.
        // Reading via dataset bypasses any HTML-attribute quoting hazards
        // (Codex P1 finding 2026-05-08 on PR #295).
        document.addEventListener('click', function (ev) {
            var trigger = ev.target.closest('[data-preview-trigger]');
            if (!trigger) return;
            var ds = trigger.dataset;
            if (!ds.previewUrl) return;
            ev.preventDefault();
            openPreview(ds.previewName || '', ds.previewUrl, ds.previewMime || '', ds.previewDownload || ds.previewUrl);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.openPreview = openPreview;
})();
