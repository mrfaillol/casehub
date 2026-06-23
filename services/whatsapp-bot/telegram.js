/**
 * Modulo Telegram - WhatsApp Bot
 * CaseHub
 * v1.0 - Notificacoes via Telegram (GRATIS e ILIMITADO)
 */

const https = require('https');

const TELEGRAM_CONFIG = {
  botToken: process.env.TELEGRAM_BOT_TOKEN || '',
  chatId: process.env.TELEGRAM_CHAT_ID || ''
};

const isConfigured = Boolean(TELEGRAM_CONFIG.botToken && TELEGRAM_CONFIG.chatId);

function requireConfigured() {
  if (!isConfigured) {
    throw new Error('TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars are required to use Telegram notifications.');
  }
}

/**
 * Enviar mensagem via Telegram
 */
async function sendMessage(text, parseMode = 'HTML') {
  if (!isConfigured) {
    return { success: false, error: 'telegram_not_configured' };
  }
  return new Promise((resolve, reject) => {
    const data = JSON.stringify({
      chat_id: TELEGRAM_CONFIG.chatId,
      text: text,
      parse_mode: parseMode
    });

    const options = {
      hostname: 'api.telegram.org',
      port: 443,
      path: `/bot${TELEGRAM_CONFIG.botToken}/sendMessage`,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data)
      }
    };

    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(body);
          if (result.ok) {
            console.log('[TELEGRAM] Mensagem enviada com sucesso');
            resolve({ success: true, messageId: result.result.message_id });
          } else {
            console.error('[TELEGRAM] Erro:', result.description);
            resolve({ success: false, error: result.description });
          }
        } catch (e) {
          resolve({ success: false, error: e.message });
        }
      });
    });

    req.on('error', (e) => {
      console.error('[TELEGRAM] Erro de conexao:', e.message);
      resolve({ success: false, error: e.message });
    });

    req.write(data);
    req.end();
  });
}

/**
 * Notificar nova lead
 */
async function notifyNewLead(leadData) {
  const name = leadData.client_name || leadData.whatsapp_name || 'Sem nome';
  const phone = leadData.phone || 'N/A';
  const interest = leadData.visa_interest || 'Nao informado';
  const email = leadData.email || 'Nao informado';
  const source = leadData.source || 'WhatsApp';
  const score = leadData.lead_score || 'N/A';

  const message = `🆕 *NOVA LEAD*

👤 *Nome:* ${name}
📱 *Tel:* ${phone}
📧 *Email:* ${email}
🎯 *Interesse:* ${interest}
📍 *Origem:* ${source}
📊 *Score:* ${score}`;

  return sendMessage(message, 'Markdown');
}

/**
 * Notificar lead urgente
 */
async function notifyUrgentLead(leadData) {
  const name = leadData.client_name || leadData.whatsapp_name || 'Sem nome';
  const phone = leadData.phone || 'N/A';

  const message = `🚨 *LEAD URGENTE*

👤 *Nome:* ${name}
📱 *Tel:* ${phone}

⚠️ Requer atenção imediata!`;

  return sendMessage(message, 'Markdown');
}

/**
 * Notificar consulta gratuita agendada
 */
async function notifyFreeConsultation(leadData) {
  const name = leadData.client_name || 'Sem nome';
  const phone = leadData.phone || 'N/A';
  const email = leadData.email || 'N/A';

  const message = `📅 *CONSULTA GRATUITA*

👤 *Nome:* ${name}
📱 *Tel:* ${phone}
📧 *Email:* ${email}

✅ Aguardando agendamento`;

  return sendMessage(message, 'Markdown');
}

/**
 * Notificar pagamento recebido
 */
async function notifyPaymentReceived(paymentData) {
  const name = paymentData.client_name || 'Cliente';
  const amount = paymentData.amount || '99';
  const phone = paymentData.phone || 'N/A';

  const message = `💰 *PAGAMENTO RECEBIDO*

👤 *Cliente:* ${name}
📱 *Tel:* ${phone}
💵 *Valor:* $${amount} USD

✅ Pagamento confirmado via Stripe`;

  return sendMessage(message, 'Markdown');
}

/**
 * v9.0: Notificar lead qualificada via Intake Form
 */
async function notifyQualifiedIntake(leadData) {
  const name = leadData.client_name || leadData.whatsapp_name || 'Sem nome';
  const phone = leadData.phone || 'N/A';
  const score = leadData.score || 0;
  const pathway = leadData.pathway || 'unknown';
  const summary = leadData.summary || '';

  // Formatar pathway para exibicao
  const pathwayNames = {
    'family_based': '👨‍👩‍👧 Family-Based',
    'employment_based': '💼 Employment-Based',
    'humanitarian_asylum': '🛡️ Asilo',
    'humanitarian_vawa': '🛡️ VAWA',
    'humanitarian_u_visa': '🛡️ U-Visa',
    'humanitarian_t_visa': '🛡️ T-Visa',
    'humanitarian_sijs': '🛡️ SIJS',
    'investor': '💰 Investidor',
    'unknown': '❓ A definir'
  };

  const pathwayDisplay = pathwayNames[pathway] || pathway;

  const message = `🎯 *LEAD QUALIFICADA (Intake Form)*

👤 *Nome:* ${name}
📱 *Tel:* ${phone}
📊 *Score:* ${score}/100
🛣️ *Pathway:* ${pathwayDisplay}

${summary ? '📝 *Resumo:*\n' + summary.substring(0, 300) + '...' : ''}

✅ *Elegível para consulta GRATUITA!*
📞 Ligar: https://wa.me/${phone.replace(/\D/g, '')}`;

  return sendMessage(message, 'Markdown');
}

/**
 * v10.0: Notificar nova mensagem (Human Handoff)
 * Quando lead em estado AWAITING_HUMAN envia mensagem
 */
async function notifyNewMessage(leadData) {
  const name = leadData.client_name || leadData.whatsapp_name || 'Sem nome';
  const phone = leadData.phone || 'N/A';
  const msg = (leadData.message || '').substring(0, 200);

  const message = `📩 *NOVA MENSAGEM*

👤 *De:* ${name}
📱 *Tel:* ${phone}
💬 *Msg:* ${msg}

📞 Responder: https://wa.me/${phone.replace(/\D/g, '')}`;

  return sendMessage(message, 'Markdown');
}

/**
 * Testar conexao
 */
async function testConnection() {
  return sendMessage('🤖 Bot conectado!', 'Markdown');
}

module.exports = {
  sendMessage,
  notifyNewLead,
  notifyUrgentLead,
  notifyFreeConsultation,
  notifyPaymentReceived,
  notifyQualifiedIntake,
  notifyNewMessage,
  testConnection,
  TELEGRAM_CONFIG,
  isConfigured,
  requireConfigured
};
