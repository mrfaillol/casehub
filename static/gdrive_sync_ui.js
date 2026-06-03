/**
 * Google Drive Sync UI Component
 * Adds "Sync from Drive" button to client detail page
 */

(function() {
    'use strict';

    // Only run on client detail pages
    const clientIdMatch = window.location.pathname.match(/\/clients\/(\d+)/);
    if (!clientIdMatch) return;

    const clientId = clientIdMatch[1];

    // Add sync button to documents section
    function addSyncButton() {
        // Find documents section (look for h3 with "Documents" text)
        const documentsHeading = Array.from(document.querySelectorAll('h3, h2'))
            .find(h => h.textContent.includes('Documents') || h.textContent.includes('Documentos'));

        if (!documentsHeading) {
            console.log('[GDrive Sync] Documents section not found');
            return;
        }

        // Check if button already exists
        if (document.getElementById('gdrive-sync-btn')) return;

        // Create sync button
        const syncBtn = document.createElement('button');
        syncBtn.id = 'gdrive-sync-btn';
        syncBtn.className = 'btn btn-primary btn-sm';
        syncBtn.style.cssText = 'margin-left: 10px; position: relative;';
        syncBtn.innerHTML = `
            <svg width="16" height="16" fill="currentColor" style="margin-right: 5px; vertical-align: text-bottom;">
                <path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm1 12H7V7h2v5zm0-6H7V4h2v2z"/>
            </svg>
            Sync from Drive
        `;

        syncBtn.onclick = handleSyncClick;

        // Insert button next to heading
        documentsHeading.style.display = 'inline-block';
        documentsHeading.parentNode.insertBefore(syncBtn, documentsHeading.nextSibling);

        console.log('[GDrive Sync] Button added');
    }

    // Handle sync button click
    async function handleSyncClick(e) {
        const btn = e.target.closest('button');
        const originalHTML = btn.innerHTML;

        try {
            // Disable button and show loading
            btn.disabled = true;
            btn.innerHTML = `
                <span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                Syncing...
            `;

            // Call sync API
            const response = await fetch(`/api/documents/drive/sync-client/${clientId}?skip_existing=true`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            const result = await response.json();

            if (response.ok && result.success) {
                // Show success message
                showNotification('success', `
                    <strong>Sync Complete!</strong><br>
                    Downloaded: ${result.downloaded}<br>
                    Skipped: ${result.skipped}<br>
                    Failed: ${result.failed}<br>
                    Total: ${result.total}
                `);

                // Reload page if files were downloaded
                if (result.downloaded > 0) {
                    setTimeout(() => window.location.reload(), 2000);
                }
            } else {
                throw new Error(result.detail || 'Sync failed');
            }
        } catch (error) {
            console.error('[GDrive Sync] Error:', error);
            showNotification('error', `
                <strong>Sync Failed</strong><br>
                ${error.message || 'Unknown error'}
            `);
        } finally {
            // Re-enable button
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }
    }

    // Show notification (Bootstrap toast or alert)
    function showNotification(type, message) {
        // Try to use existing notification system
        if (typeof showToast === 'function') {
            showToast(message, type);
            return;
        }

        // Fallback: create Bootstrap alert
        const alert = document.createElement('div');
        alert.className = `alert alert-${type === 'success' ? 'success' : 'danger'} alert-dismissible fade show`;
        alert.style.cssText = 'position: fixed; top: 20px; right: 20px; z-index: 9999; max-width: 400px;';
        alert.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        document.body.appendChild(alert);

        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            alert.remove();
        }, 5000);
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', addSyncButton);
    } else {
        addSyncButton();
    }

    console.log('[GDrive Sync UI] Loaded for client', clientId);
})();
