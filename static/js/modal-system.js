/**
 * CaseHub Modal System
 * Replaces prompt() and confirm() with Bootstrap 5 modals
 *
 * Usage:
 *   const name = await modal.prompt('Title', 'Message', {placeholder: '...'});
 *   const confirmed = await modal.confirm('Title', 'Message', {danger: true});
 */
class ModalSystem {
    constructor() {
        this.modalCounter = 0;
    }

    async prompt(title, message, options = {}) {
        return new Promise((resolve) => {
            const modalId = `modal-prompt-${this.modalCounter++}`;
            const inputId = `input-${modalId}`;
            const modal = this.createModal(modalId, {
                title: title,
                body: `<p>${message}</p><input type="text" class="form-control" id="${inputId}" value="${options.defaultValue || ''}" placeholder="${options.placeholder || ''}">`,
                buttons: [
                    {
                        label: 'Cancel',
                        class: 'btn-secondary',
                        callback: () => resolve(null)
                    },
                    {
                        label: 'OK',
                        class: 'btn-primary',
                        callback: () => {
                            const input = document.getElementById(inputId);
                            resolve(input.value);
                        }
                    }
                ],
                icon: 'fa-edit text-primary'
            });

            document.body.appendChild(modal);
            const bsModal = new bootstrap.Modal(modal);
            bsModal.show();

            // Focus input after modal is shown
            setTimeout(() => document.getElementById(inputId)?.focus(), 300);

            // Clean up modal on hide
            modal.addEventListener('hidden.bs.modal', () => modal.remove());
        });
    }

    async confirm(title, message, options = {}) {
        return new Promise((resolve) => {
            const modalId = `modal-confirm-${this.modalCounter++}`;
            const modal = this.createModal(modalId, {
                title: title,
                body: `<p>${message}</p>`,
                buttons: [
                    {
                        label: options.cancelLabel || 'Cancel',
                        class: 'btn-secondary',
                        callback: () => resolve(false)
                    },
                    {
                        label: options.confirmLabel || 'Confirm',
                        class: options.danger ? 'btn-danger' : 'btn-primary',
                        callback: () => resolve(true)
                    }
                ],
                icon: options.icon || 'fa-exclamation-triangle text-warning'
            });

            document.body.appendChild(modal);
            const bsModal = new bootstrap.Modal(modal);
            bsModal.show();

            // Clean up modal on hide
            modal.addEventListener('hidden.bs.modal', () => modal.remove());
        });
    }

    createModal(id, config) {
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.id = id;
        modal.tabIndex = -1;

        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title"><i class="fas ${config.icon} me-2"></i>${config.title}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">${config.body}</div>
                    <div class="modal-footer">
                        ${config.buttons.map((btn, i) => `
                            <button type="button" class="btn ${btn.class}" data-action="${i}">${btn.label}</button>
                        `).join('')}
                    </div>
                </div>
            </div>
        `;

        // Attach event listeners to buttons
        config.buttons.forEach((btn, i) => {
            modal.querySelector(`[data-action="${i}"]`).addEventListener('click', () => {
                btn.callback();
                // Guard: getInstance may return null if Bootstrap is not yet
                // attached or the element was already disposed. See #207.
                const instance = (typeof bootstrap !== 'undefined' && bootstrap.Modal)
                    ? bootstrap.Modal.getInstance(modal)
                    : null;
                if (instance) instance.hide();
            });
        });

        return modal;
    }
}

// Global instance available to all pages
window.modal = new ModalSystem();
