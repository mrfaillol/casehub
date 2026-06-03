/**
 * CaseHub Toast Notification System
 * Replaces alert() with non-blocking, dark-theme toasts
 *
 * Usage:
 *   toast.success('Operation completed!');
 *   toast.error('Something went wrong');
 *   toast.warning('Please check your input');
 *   toast.info('For your information');
 */
class ToastSystem {
    constructor() {
        this.container = this.createContainer();
        document.body.appendChild(this.container);
    }

    createContainer() {
        const div = document.createElement('div');
        div.id = 'toast-container';
        div.style.cssText = 'position:fixed;top:80px;right:20px;z-index:9999;min-width:320px;';
        return div;
    }

    show(message, type = 'info', duration = 3500) {
        const toast = document.createElement('div');
        toast.className = `custom-toast ${type}`;

        const icons = {
            success: 'fa-check-circle',
            error: 'fa-exclamation-circle',
            warning: 'fa-exclamation-triangle',
            info: 'fa-info-circle'
        };

        toast.innerHTML = `<i class="fas ${icons[type]}"></i><span>${message}</span>`;
        this.container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    success(msg) { this.show(msg, 'success'); }
    error(msg) { this.show(msg, 'error', 5000); }
    warning(msg) { this.show(msg, 'warning', 4000); }
    info(msg) { this.show(msg, 'info'); }
}

// Global instance available to all pages
window.toast = new ToastSystem();
