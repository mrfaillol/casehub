// compose-modal.js — Universal email compose modal
// Triggered by any element with [data-ch-compose].
// Optional data attrs: data-to, data-subject, data-body, data-client-id, data-case-id
(function () {
  'use strict';

  function endpoint() {
    var base = window.PREFIX || '/casehub';
    return (window.__composeProvider === 'gmail')
      ? base + '/gmail/send'
      : base + '/emails/send';
  }

  function openModal(opts) {
    var modal = document.getElementById('ch-compose-modal');
    if (!modal) return;

    document.getElementById('ch-compose-to').value        = opts.to       || '';
    document.getElementById('ch-compose-cc').value        = opts.cc       || '';
    document.getElementById('ch-compose-subject').value   = opts.subject  || '';
    document.getElementById('ch-compose-body').value      = opts.body     || '';
    document.getElementById('ch-compose-client-id').value = opts.clientId || '';
    document.getElementById('ch-compose-case-id').value   = opts.caseId   || '';

    var status = document.getElementById('ch-compose-status');
    status.textContent = '';
    status.className = 'ch-compose-modal__status';

    var sendBtn = document.getElementById('ch-compose-send-btn');
    sendBtn.disabled = false;

    var badge = document.getElementById('ch-compose-provider-badge');
    if (badge) {
      if (window.__composeProvider === 'gmail' && window.__composeAccount) {
        badge.textContent = '· via Gmail (' + window.__composeAccount + ')';
      } else if (window.__composeProvider === 'smtp') {
        badge.textContent = '· via SMTP';
      } else {
        badge.textContent = '';
      }
    }

    if (typeof lucide !== 'undefined') { lucide.createIcons(); }
    modal.showModal();

    setTimeout(function () {
      var toField = document.getElementById('ch-compose-to');
      if (toField && !toField.value) {
        toField.focus();
      } else {
        document.getElementById('ch-compose-body').focus();
      }
    }, 60);
  }

  window.__chComposeOpen = openModal;

  window.__chComposeSend = async function () {
    var status  = document.getElementById('ch-compose-status');
    var sendBtn = document.getElementById('ch-compose-send-btn');

    var to      = document.getElementById('ch-compose-to').value.trim();
    var subject = document.getElementById('ch-compose-subject').value.trim();
    var body    = document.getElementById('ch-compose-body').value.trim();

    if (!to || !to.includes('@')) {
      status.textContent = 'Informe um e-mail de destinatário válido.';
      status.className = 'ch-compose-modal__status ch-compose-modal__status--error';
      return;
    }
    if (!subject) {
      status.textContent = 'Informe o assunto.';
      status.className = 'ch-compose-modal__status ch-compose-modal__status--error';
      return;
    }
    if (!body) {
      status.textContent = 'Escreva a mensagem.';
      status.className = 'ch-compose-modal__status ch-compose-modal__status--error';
      return;
    }

    sendBtn.disabled = true;
    status.textContent = 'Enviando...';
    status.className = 'ch-compose-modal__status';

    var payload = {
      to:        to,
      subject:   subject,
      body:      body,
      cc:        document.getElementById('ch-compose-cc').value.trim(),
      client_id: document.getElementById('ch-compose-client-id').value || null,
      case_id:   document.getElementById('ch-compose-case-id').value   || null,
    };

    try {
      var res  = await fetch(endpoint(), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      var data = await res.json();
      if (data.success) {
        status.textContent = 'E-mail enviado com sucesso!';
        status.className = 'ch-compose-modal__status ch-compose-modal__status--success';
        setTimeout(function () {
          document.getElementById('ch-compose-modal').close();
        }, 1400);
      } else {
        status.textContent = 'Erro ao enviar: ' + (data.error || 'falha desconhecida');
        status.className = 'ch-compose-modal__status ch-compose-modal__status--error';
        sendBtn.disabled = false;
      }
    } catch (err) {
      status.textContent = 'Erro de rede. Tente novamente.';
      status.className = 'ch-compose-modal__status ch-compose-modal__status--error';
      sendBtn.disabled = false;
    }
  };

  // Delegate: click on any [data-ch-compose] opens the modal
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-ch-compose]');
    if (!btn) return;
    openModal({
      to:       btn.dataset.to       || '',
      subject:  btn.dataset.subject  || '',
      body:     btn.dataset.body     || '',
      clientId: btn.dataset.clientId || btn.dataset['client-id'] || '',
      caseId:   btn.dataset.caseId   || btn.dataset['case-id']   || '',
    });
  });

  // Close on backdrop click
  document.addEventListener('click', function (e) {
    var modal = document.getElementById('ch-compose-modal');
    if (modal && e.target === modal) { modal.close(); }
  });
}());
