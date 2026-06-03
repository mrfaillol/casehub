/* CaseHub App · Toast notification system
 * Non-blocking notifications replacing native alert().
 *
 * Usage:
 *   window.toast.success('Salvo com sucesso');
 *   window.toast.error('Erro ao salvar');
 *   window.toast.warning('Atenção');
 *   window.toast.info('Informação');
 *
 * Position: top-right, stacked. Auto-dismiss 3.5s (5s for errors).
 * Design tokens: --surface-card, --c-success, --c-danger, --c-warn, --c-blue.
 */
(function () {
  'use strict';

  function createContainer() {
    var el = document.createElement('div');
    el.id = 'ch-toast-stack';
    el.setAttribute('aria-live', 'polite');
    el.setAttribute('aria-atomic', 'false');
    el.style.cssText = [
      'position: fixed',
      'top: calc(var(--space-12, 56px) + var(--space-2, 8px))',
      'right: var(--space-4, 16px)',
      'z-index: 9999',
      'display: flex',
      'flex-direction: column',
      'gap: var(--space-2, 8px)',
      'pointer-events: none',
      'max-width: 380px'
    ].join(';');
    return el;
  }

  function ensureContainer() {
    var el = document.getElementById('ch-toast-stack');
    if (!el) {
      el = createContainer();
      document.body.appendChild(el);
    }
    return el;
  }

  var COLORS = {
    success: { border: 'var(--c-success, #16a34a)', icon: 'check' },
    error:   { border: 'var(--c-danger,  #dc2626)', icon: 'alert-circle' },
    warning: { border: 'var(--c-warn,    #d97706)', icon: 'alert-triangle' },
    info:    { border: 'var(--c-blue,    #2563eb)', icon: 'info' }
  };

  function show(message, type, duration) {
    var container = ensureContainer();
    var spec = COLORS[type] || COLORS.info;
    var ms = duration || (type === 'error' ? 5000 : 3500);

    var toast = document.createElement('div');
    toast.className = 'ch-toast ch-toast--' + (type || 'info');
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
    toast.style.cssText = [
      'background: var(--surface-card, #fff)',
      'color: var(--fg-default, #111)',
      'border: 1px solid var(--line, #e5e5e5)',
      'border-left: 3px solid ' + spec.border,
      'border-radius: var(--radius-md, 8px)',
      'box-shadow: var(--shadow-pop, 0 12px 32px rgba(0,0,0,0.18))',
      'padding: var(--space-3, 12px) var(--space-4, 16px)',
      'font-size: var(--fs-sm, 0.875rem)',
      'pointer-events: auto',
      'opacity: 0',
      'transform: translateX(8px)',
      'transition: opacity 180ms ease-out, transform 180ms ease-out',
      'display: flex',
      'align-items: flex-start',
      'gap: var(--space-2, 8px)',
      'min-width: 240px'
    ].join(';');

    // Use Lucide icon shim if available; fallback to text
    var iconSpan = document.createElement('span');
    iconSpan.setAttribute('data-icon', spec.icon);
    iconSpan.setAttribute('data-icon-size', '16');
    iconSpan.style.cssText = 'color: ' + spec.border + '; flex: 0 0 auto; line-height: 1; margin-top: 1px;';

    var text = document.createElement('span');
    text.style.cssText = 'flex: 1; word-break: break-word;';
    text.textContent = String(message == null ? '' : message);

    var closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.setAttribute('aria-label', 'Fechar');
    closeBtn.style.cssText = [
      'background: transparent',
      'border: none',
      'color: var(--fg-faint, #888)',
      'cursor: pointer',
      'font-size: 18px',
      'line-height: 1',
      'padding: 0 0 0 var(--space-2, 8px)',
      'flex: 0 0 auto'
    ].join(';');
    closeBtn.textContent = '×'; // ×

    toast.appendChild(iconSpan);
    toast.appendChild(text);
    toast.appendChild(closeBtn);
    container.appendChild(toast);

    // Trigger transition
    requestAnimationFrame(function () {
      toast.style.opacity = '1';
      toast.style.transform = 'translateX(0)';
    });

    var timer = null;
    var dismissed = false;

    function dismiss() {
      if (dismissed) return;
      dismissed = true;
      if (timer) clearTimeout(timer);
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(8px)';
      setTimeout(function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 200);
    }

    closeBtn.addEventListener('click', dismiss);
    toast.addEventListener('mouseenter', function () {
      if (timer) { clearTimeout(timer); timer = null; }
    });
    toast.addEventListener('mouseleave', function () {
      if (!dismissed) timer = setTimeout(dismiss, 1500);
    });

    timer = setTimeout(dismiss, ms);
    return dismiss;
  }

  window.toast = {
    show: show,
    success: function (msg, duration) { return show(msg, 'success', duration); },
    error:   function (msg, duration) { return show(msg, 'error', duration); },
    warning: function (msg, duration) { return show(msg, 'warning', duration); },
    info:    function (msg, duration) { return show(msg, 'info', duration); }
  };
})();
