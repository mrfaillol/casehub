let _ticketModal;
document.addEventListener('DOMContentLoaded', function() {
    // Guard against missing element / bundle — see #207.
    const el = document.getElementById('ticketModal');
    if (!el || !el.classList.contains('modal')) return;
    if (typeof bootstrap === 'undefined' || !bootstrap.Modal) return;
    try {
        _ticketModal = bootstrap.Modal.getOrCreateInstance(el);
    } catch (e) {
        if (window.console) console.warn('ticketModal init failed:', e);
    }
});

function openTicketModal() {
    if (!_ticketModal) return;
    document.getElementById('ticketTitle').value = '';
    document.getElementById('ticketDescription').value = '';
    document.getElementById('ticketCategory').value = 'Bug';
    document.getElementById('ticketSeverity').value = 'Medium';
    document.getElementById('ticketTitle').classList.remove('is-invalid');
    _ticketModal.show();
    setTimeout(function() { document.getElementById('ticketTitle').focus(); }, 300);
}

async function submitTicket() {
    var title = document.getElementById('ticketTitle').value.trim();
    if (!title) {
        document.getElementById('ticketTitle').classList.add('is-invalid');
        return;
    }
    document.getElementById('ticketTitle').classList.remove('is-invalid');
    var btn = document.getElementById('ticketSubmitBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Submitting...';
    try {
        var res = await fetch('/casehub/api/tickets/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: title,
                description: document.getElementById('ticketDescription').value.trim(),
                category: document.getElementById('ticketCategory').value,
                severity: document.getElementById('ticketSeverity').value,
                page_url: window.location.href,
                browser: navigator.userAgent,
                version: document.querySelector('.top-bar .text-muted') ? document.querySelector('.top-bar .text-muted').textContent.replace('CaseHub ', '') : '',
                environment: screen.width + 'x' + screen.height + ' | ' + navigator.language
            })
        });
        var data = await res.json();
        if (_ticketModal) _ticketModal.hide();
        if (data.success) {
            if (typeof showToast === 'function') showToast('success', 'Ticket submitted! It will be reviewed shortly.');
            else alert('Ticket submitted! It will be reviewed shortly.');
        } else {
            if (typeof showToast === 'function') showToast('error', 'Error: ' + (data.error || 'Try again later'));
            else alert('Error: ' + (data.error || 'Try again later'));
        }
    } catch (err) {
        if (typeof showToast === 'function') showToast('error', 'Network error: ' + err.message);
        else alert('Network error: ' + err.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-paper-plane me-1"></i> Submit Ticket';
    }
}
