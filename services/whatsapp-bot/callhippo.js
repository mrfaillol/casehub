/**
 * Modulo CallHippo - SMS Notifications
 * CaseHub
 * v2.0 - Configuração via environment variables + validação
 */

const https = require('https');
const crypto = require('crypto');

// Configuração via environment variables (sem fallbacks hardcoded)
const CALLHIPPO_CONFIG = {
  apiKey: process.env.CALLHIPPO_API_KEY,
  fromNumber: process.env.CALLHIPPO_FROM,
  toNumber: process.env.CALLHIPPO_TO,
  userEmail: process.env.CALLHIPPO_EMAIL || (process.env.ORG_EMAIL || 'info@casehub.app'),
  webhookSecret: process.env.CALLHIPPO_WEBHOOK_SECRET,
  baseUrl: 'web.callhippo.com'
};

// Flag para verificar se config é válida
let configValid = false;

/**
 * Validar configuração na inicialização
 */
function validateConfig() {
  const required = ['apiKey', 'fromNumber', 'toNumber'];
  const missing = required.filter(key => !CALLHIPPO_CONFIG[key]);
  
  if (missing.length > 0) {
    console.warn('[CALLHIPPO] ⚠️ Configuração incompleta. Variáveis faltando:', missing.join(', '));
    console.warn('[CALLHIPPO] SMS está DESABILITADO até configurar:');
    console.warn('  - CALLHIPPO_API_KEY');
    console.warn('  - CALLHIPPO_FROM');
    console.warn('  - CALLHIPPO_TO');
    configValid = false;
    return false;
  }
  
  console.log('[CALLHIPPO] ✅ Configuração válida');
  console.log('[CALLHIPPO] From:', CALLHIPPO_CONFIG.fromNumber);
  console.log('[CALLHIPPO] To (default):', CALLHIPPO_CONFIG.toNumber);
  configValid = true;
  return true;
}

/**
 * Verificar se CallHippo está configurado
 */
function isConfigured() {
  return configValid;
}

/**
 * Validar webhook signature (HMAC)
 */
function validateWebhookSignature(payload, signature) {
  if (!CALLHIPPO_CONFIG.webhookSecret) {
    console.warn('[CALLHIPPO] Webhook secret não configurado - pulando validação');
    return true; // Permite se não tiver secret configurado
  }
  
  const expectedSignature = crypto
    .createHmac('sha256', CALLHIPPO_CONFIG.webhookSecret)
    .update(JSON.stringify(payload))
    .digest('hex');
  
  return signature === expectedSignature;
}

/**
 * Enviar SMS via CallHippo API
 */
async function sendSMS(message, toNumber = null) {
  // Validar config antes de enviar
  if (!configValid) {
    console.warn('[CALLHIPPO] SMS não enviado - configuração incompleta');
    return { success: false, error: 'CallHippo não configurado' };
  }

  return new Promise((resolve, reject) => {
    const data = JSON.stringify({
      from: CALLHIPPO_CONFIG.fromNumber,
      to: toNumber || CALLHIPPO_CONFIG.toNumber,
      userEmail: CALLHIPPO_CONFIG.userEmail,
      smsBody: message
    });

    const options = {
      hostname: CALLHIPPO_CONFIG.baseUrl,
      port: 443,
      path: '/v1/sms/send',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data),
        'apitoken': CALLHIPPO_CONFIG.apiKey,
        'accept': 'application/json'
      }
    };

    console.log('[CALLHIPPO] Enviando SMS...');
    console.log('[CALLHIPPO] De:', CALLHIPPO_CONFIG.fromNumber);
    console.log('[CALLHIPPO] Para:', toNumber || CALLHIPPO_CONFIG.toNumber);

    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(body);
          if (res.statusCode >= 200 && res.statusCode < 300) {
            console.log('[CALLHIPPO] ✅ SMS enviado com sucesso');
            resolve({ success: true, data: result });
          } else {
            console.error('[CALLHIPPO] ❌ Erro:', result);
            resolve({ success: false, error: result, statusCode: res.statusCode });
          }
        } catch (e) {
          console.error('[CALLHIPPO] Erro ao parsear resposta:', e.message);
          resolve({ success: false, error: e.message, raw: body });
        }
      });
    });

    req.on('error', (e) => {
      console.error('[CALLHIPPO] Erro de conexao:', e.message);
      resolve({ success: false, error: e.message });
    });

    req.setTimeout(10000, () => {
      req.destroy();
      resolve({ success: false, error: 'Timeout após 10s' });
    });

    req.write(data);
    req.end();
  });
}

/**
 * Notificar nova lead via SMS
 */
async function notifyNewLead(leadData) {
  if (!configValid) return { success: false, error: 'Não configurado' };

  const name = leadData.client_name || leadData.whatsapp_name || 'Sem nome';
  const phone = leadData.phone || 'N/A';
  const interest = leadData.visa_interest || 'Nao informado';
  const source = leadData.source || 'WhatsApp';

  const message = `🔔 NOVA LEAD CaseHub
Nome: ${name}
Tel: ${phone}
Interesse: ${interest}
Origem: ${source}`;

  return sendSMS(message);
}

/**
 * Notificar lead urgente via SMS
 */
async function notifyUrgentLead(leadData) {
  if (!configValid) return { success: false, error: 'Não configurado' };

  const name = leadData.client_name || leadData.whatsapp_name || 'Sem nome';
  const phone = leadData.phone || 'N/A';

  const message = `🚨 URGENTE CaseHub!
Nome: ${name}
Tel: ${phone}
Requer atenção imediata!`;

  return sendSMS(message);
}

/**
 * Notificar nova mensagem (Human Handoff)
 */
async function notifyNewMessage(leadData) {
  if (!configValid) return { success: false, error: 'Não configurado' };

  const name = leadData.client_name || leadData.whatsapp_name || 'Sem nome';
  const phone = leadData.phone || 'N/A';
  const msg = (leadData.message || '').substring(0, 100);

  const message = `💬 MSG CaseHub
De: ${name}
Tel: ${phone}
Msg: ${msg}`;

  return sendSMS(message);
}

/**
 * Testar conexao
 */
async function testConnection() {
  if (!configValid) {
    console.log('[CALLHIPPO] Tentando validar configuração...');
    validateConfig();
  }
  
  if (!configValid) {
    return { success: false, error: 'Configuração inválida' };
  }
  
  return sendSMS('✅ Teste de conexão CaseHub WhatsApp Bot - CallHippo OK');
}

// Validar config na inicialização do módulo
validateConfig();

module.exports = {
  sendSMS,
  notifyNewLead,
  notifyUrgentLead,
  notifyNewMessage,
  testConnection,
  validateConfig,
  validateWebhookSignature,
  isConfigured,
  CALLHIPPO_CONFIG
};
