/**
 * Conversion Tracking - Google Ads Offline Conversions & Facebook CAPI
 * CaseHub
 * v2.0 - Google Ads API real (Enhanced Conversions for Leads) + Facebook CAPI
 *
 * Fluxo:
 * 1. Lead preenche form na landing page (gclid capturado automaticamente)
 * 2. trackNewLead() -> envia "generate_lead" pro Google Ads + "Lead" pro Facebook
 * 3. Quando lead agenda consulta -> trackConsultationScheduled()
 * 4. Quando lead paga $99 -> trackPaymentCompleted()
 *
 * O Google usa esses dados offline pra otimizar o bidding da campanha.
 *
 * Setup necessario (env vars):
 *   GOOGLE_ADS_DEVELOPER_TOKEN  - Token de desenvolvedor (ads.google.com/aw/apicenter)
 *   GOOGLE_ADS_CLIENT_ID        - OAuth2 client ID (Google Cloud Console)
 *   GOOGLE_ADS_CLIENT_SECRET    - OAuth2 client secret
 *   GOOGLE_ADS_REFRESH_TOKEN    - OAuth2 refresh token
 *   GOOGLE_ADS_CUSTOMER_ID      - ID da conta Google Ads (sem hifens)
 *   GOOGLE_ADS_LOGIN_CUSTOMER_ID - ID da conta MCC (se aplicavel)
 *   GOOGLE_ADS_CONVERSION_LEAD           - Resource name da conversion action "Lead"
 *   GOOGLE_ADS_CONVERSION_CONSULTATION   - Resource name "Consultation Scheduled"
 *   GOOGLE_ADS_CONVERSION_PURCHASE       - Resource name "Purchase"
 *   GOOGLE_ADS_CONVERSION_QUALIFIED      - Resource name "Qualified Lead"
 *
 * Documentacao completa: /docs/GOOGLE-ADS-OFFLINE-CONVERSIONS.md
 */

const https = require('https');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

// ===== GOOGLE ADS API CONFIG =====
const GOOGLE_ADS_CONFIG = {
  developerToken: process.env.GOOGLE_ADS_DEVELOPER_TOKEN || '',
  clientId: process.env.GOOGLE_ADS_CLIENT_ID || '',
  clientSecret: process.env.GOOGLE_ADS_CLIENT_SECRET || '',
  refreshToken: process.env.GOOGLE_ADS_REFRESH_TOKEN || '',
  customerId: (process.env.GOOGLE_ADS_CUSTOMER_ID || '17815070319').replace(/-/g, ''),
  loginCustomerId: (process.env.GOOGLE_ADS_LOGIN_CUSTOMER_ID || '').replace(/-/g, ''),
  conversionActions: {
    lead: process.env.GOOGLE_ADS_CONVERSION_LEAD || '',
    consultation_scheduled: process.env.GOOGLE_ADS_CONVERSION_CONSULTATION || '',
    payment_completed: process.env.GOOGLE_ADS_CONVERSION_PURCHASE || '',
    qualified_lead: process.env.GOOGLE_ADS_CONVERSION_QUALIFIED || ''
  },
  // IDs para referencia (frontend gtag)
  conversionIds: ['AW-9306214813', 'AW-17815070319'],
  apiVersion: 'v19'
};

// ===== FACEBOOK CAPI CONFIG =====
const FACEBOOK_CONFIG = {
  pixelId: process.env.FB_PIXEL_ID || '',
  accessToken: process.env.FB_CAPI_TOKEN || '',
  testEventCode: process.env.FB_TEST_EVENT_CODE || ''
};

// ===== TOKEN CACHE =====
let accessTokenCache = { token: null, expiresAt: 0 };

// ===== FAILED CONVERSIONS QUEUE =====
const QUEUE_FILE = path.join(__dirname, 'data', 'failed-conversions.json');

function isGoogleAdsConfigured() {
  return !!(GOOGLE_ADS_CONFIG.developerToken &&
    GOOGLE_ADS_CONFIG.clientId &&
    GOOGLE_ADS_CONFIG.clientSecret &&
    GOOGLE_ADS_CONFIG.refreshToken);
}

function hashData(data) {
  if (!data) return null;
  return crypto.createHash('sha256').update(data.toLowerCase().trim()).digest('hex');
}

function normalizePhone(phone) {
  if (!phone) return null;
  let cleaned = phone.toString().replace(/\D/g, '');
  if (cleaned.length === 10) cleaned = '1' + cleaned;
  return '+' + cleaned;
}

function formatConversionDateTime(date) {
  const d = date || new Date();
  const pad = (n) => String(n).padStart(2, '0');
  // Use UTC to avoid timezone mismatch (VPS is BRT but Google needs accurate time)
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}+00:00`;
}

// ============================================================
// GOOGLE ADS - OAuth2 Token Management
// ============================================================

async function getAccessToken() {
  if (accessTokenCache.token && Date.now() < accessTokenCache.expiresAt - 300000) {
    return accessTokenCache.token;
  }

  return new Promise((resolve, reject) => {
    const postData = [
      'grant_type=refresh_token',
      `client_id=${encodeURIComponent(GOOGLE_ADS_CONFIG.clientId)}`,
      `client_secret=${encodeURIComponent(GOOGLE_ADS_CONFIG.clientSecret)}`,
      `refresh_token=${encodeURIComponent(GOOGLE_ADS_CONFIG.refreshToken)}`
    ].join('&');

    const options = {
      hostname: 'oauth2.googleapis.com',
      port: 443,
      path: '/token',
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Content-Length': Buffer.byteLength(postData)
      }
    };

    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(body);
          if (result.access_token) {
            accessTokenCache = {
              token: result.access_token,
              expiresAt: Date.now() + (result.expires_in * 1000)
            };
            resolve(result.access_token);
          } else {
            reject(new Error('OAuth2 failed: ' + (result.error_description || result.error || 'unknown')));
          }
        } catch (e) {
          reject(new Error('OAuth2 parse error: ' + e.message));
        }
      });
    });

    req.on('error', (e) => reject(new Error('OAuth2 connection error: ' + e.message)));
    req.write(postData);
    req.end();
  });
}

// ============================================================
// GOOGLE ADS - Upload Offline Conversions
// ============================================================

async function sendGoogleConversion(eventName, leadData) {
  const conversionAction = GOOGLE_ADS_CONFIG.conversionActions[eventName] ||
    GOOGLE_ADS_CONFIG.conversionActions.lead;

  if (!isGoogleAdsConfigured()) {
    console.log(`[GADS] API nao configurada - evento "${eventName}" salvo na fila`);
    console.log(`[GADS] Lead: ${leadData.phone || 'N/A'} - ${leadData.client_name || 'N/A'}`);
    queueFailedConversion('google', eventName, leadData, 'API nao configurada');
    return { success: false, platform: 'google', event: eventName, reason: 'not_configured' };
  }

  if (!conversionAction) {
    console.log(`[GADS] Conversion action nao definida para "${eventName}"`);
    queueFailedConversion('google', eventName, leadData, 'Conversion action nao definida');
    return { success: false, platform: 'google', event: eventName, reason: 'no_conversion_action' };
  }

  try {
    const accessToken = await getAccessToken();

    const conversion = {
      conversionAction: conversionAction,
      conversionDateTime: formatConversionDateTime(new Date()),
      currencyCode: 'USD'
    };

    // Valor por tipo de conversao
    if (eventName === 'payment_completed') {
      conversion.conversionValue = leadData.payment_amount ? (leadData.payment_amount / 100) : 99.0;
    } else if (eventName === 'consultation_scheduled') {
      conversion.conversionValue = 50.0;
    } else if (eventName === 'qualified_lead') {
      conversion.conversionValue = 25.0;
    } else {
      conversion.conversionValue = 10.0;
    }

    // gclid = matching mais preciso (click-based)
    if (leadData.gclid) {
      conversion.gclid = leadData.gclid;
      console.log(`[GADS] gclid: ${leadData.gclid.substring(0, 20)}...`);
    }

    // Enhanced Conversions: user identifiers hasheados
    const userIdentifiers = [];
    if (leadData.email) {
      userIdentifiers.push({ hashedEmail: hashData(leadData.email) });
    }
    if (leadData.phone) {
      const normalized = normalizePhone(leadData.phone);
      if (normalized) {
        userIdentifiers.push({ hashedPhoneNumber: hashData(normalized) });
      }
    }
    if (userIdentifiers.length > 0) {
      conversion.userIdentifiers = userIdentifiers;
    }

    const requestBody = {
      conversions: [conversion],
      partialFailure: true
    };

    const postData = JSON.stringify(requestBody);
    const customerId = GOOGLE_ADS_CONFIG.customerId;

    const headers = {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(postData),
      'Authorization': `Bearer ${accessToken}`,
      'developer-token': GOOGLE_ADS_CONFIG.developerToken
    };
    if (GOOGLE_ADS_CONFIG.loginCustomerId) {
      headers['login-customer-id'] = GOOGLE_ADS_CONFIG.loginCustomerId;
    }

    const options = {
      hostname: 'googleads.googleapis.com',
      port: 443,
      path: `/${GOOGLE_ADS_CONFIG.apiVersion}/customers/${customerId}:uploadClickConversions`,
      method: 'POST',
      headers: headers
    };

    return new Promise((resolve) => {
      const req = https.request(options, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            const result = JSON.parse(body);

            if (res.statusCode === 200 && result.results) {
              const failed = result.results.filter(r => r.failureMessage);
              if (failed.length === 0) {
                console.log(`[GADS] Conversao enviada: "${eventName}" | ${leadData.client_name || leadData.phone}`);
                resolve({ success: true, platform: 'google', event: eventName, result });
              } else {
                console.error(`[GADS] Rejeitada: ${failed[0].failureMessage}`);
                queueFailedConversion('google', eventName, leadData, failed[0].failureMessage);
                resolve({ success: false, platform: 'google', event: eventName, error: failed[0].failureMessage });
              }
            } else if (result.error) {
              const errorMsg = result.error.message || JSON.stringify(result.error);
              console.error(`[GADS] API error (${res.statusCode}): ${errorMsg}`);
              queueFailedConversion('google', eventName, leadData, errorMsg);
              resolve({ success: false, platform: 'google', event: eventName, error: errorMsg });
            } else {
              console.error(`[GADS] Resposta inesperada (${res.statusCode}):`, body.substring(0, 300));
              queueFailedConversion('google', eventName, leadData, `HTTP ${res.statusCode}`);
              resolve({ success: false, platform: 'google', event: eventName, error: body.substring(0, 200) });
            }
          } catch (e) {
            console.error('[GADS] Parse error:', e.message);
            resolve({ success: false, platform: 'google', event: eventName, error: e.message });
          }
        });
      });

      req.on('error', (e) => {
        console.error('[GADS] Connection error:', e.message);
        queueFailedConversion('google', eventName, leadData, e.message);
        resolve({ success: false, platform: 'google', event: eventName, error: e.message });
      });

      req.write(postData);
      req.end();
    });

  } catch (error) {
    console.error('[GADS] Erro:', error.message);
    queueFailedConversion('google', eventName, leadData, error.message);
    return { success: false, platform: 'google', event: eventName, error: error.message };
  }
}

// ============================================================
// FACEBOOK CAPI (mantido - ja funciona)
// ============================================================

async function sendFacebookConversion(eventName, leadData, eventSourceUrl) {
  if (!FACEBOOK_CONFIG.pixelId || !FACEBOOK_CONFIG.accessToken) {
    console.log('[CONVERSION] Facebook CAPI nao configurado');
    return { success: false, error: 'CAPI nao configurado' };
  }

  try {
    const timestamp = Math.floor(Date.now() / 1000);
    const eventId = `${eventName}_${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
    const userData = {};

    if (leadData.email) userData.em = [hashData(leadData.email)];
    if (leadData.phone) {
      const phone = leadData.phone.toString().replace(/\D/g, '');
      userData.ph = [hashData(phone)];
    }
    if (leadData.client_name) {
      const names = leadData.client_name.split(' ');
      if (names[0]) userData.fn = [hashData(names[0])];
      if (names[1]) userData.ln = [hashData(names.slice(1).join(' '))];
    }
    // Facebook click ID (fbc) from fbclid - improves event match quality
    if (leadData.fbclid) {
      userData.fbc = `fb.1.${timestamp}.${leadData.fbclid}`;
    }
    // Facebook browser ID (fbp) if available
    if (leadData.fbp) {
      userData.fbp = leadData.fbp;
    }

    const customData = {
      currency: 'USD',
      value: eventName === 'Purchase' ? 99 : 0
    };
    if (leadData.visa_interest) customData.content_name = leadData.visa_interest;
    if (leadData.source) customData.content_category = leadData.source;

    const eventData = {
      data: [{
        event_name: eventName,
        event_id: eventId,
        event_time: timestamp,
        action_source: 'website',
        event_source_url: eventSourceUrl || (process.env.ORG_WEBSITE || 'https://casehub.app'),
        user_data: userData,
        custom_data: customData
      }]
    };

    if (FACEBOOK_CONFIG.testEventCode) {
      eventData.test_event_code = FACEBOOK_CONFIG.testEventCode;
    }

    const postData = JSON.stringify(eventData);

    const options = {
      hostname: 'graph.facebook.com',
      port: 443,
      path: '/v18.0/' + FACEBOOK_CONFIG.pixelId + '/events?access_token=' + FACEBOOK_CONFIG.accessToken,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData)
      }
    };

    return new Promise((resolve) => {
      const req = https.request(options, (res) => {
        let body = '';
        res.on('data', chunk => body += chunk);
        res.on('end', () => {
          try {
            const result = JSON.parse(body);
            if (result.events_received) {
              console.log('[CONVERSION] Facebook CAPI - Evento enviado:', eventName, '- Recebidos:', result.events_received);
              resolve({ success: true, platform: 'facebook', event: eventName, result });
            } else {
              console.error('[CONVERSION] Facebook CAPI erro:', body);
              resolve({ success: false, error: body });
            }
          } catch (e) {
            resolve({ success: false, error: e.message });
          }
        });
      });

      req.on('error', (e) => {
        console.error('[CONVERSION] Facebook CAPI erro conexao:', e.message);
        resolve({ success: false, error: e.message });
      });

      req.write(postData);
      req.end();
    });
  } catch (error) {
    console.error('[CONVERSION] Erro Facebook:', error.message);
    return { success: false, error: error.message };
  }
}

// ============================================================
// FAILED CONVERSIONS QUEUE
// ============================================================

function queueFailedConversion(platform, eventName, leadData, error) {
  try {
    const dir = path.dirname(QUEUE_FILE);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    let queue = [];
    if (fs.existsSync(QUEUE_FILE)) {
      queue = JSON.parse(fs.readFileSync(QUEUE_FILE, 'utf8'));
    }

    if (queue.length >= 500) queue = queue.slice(-400);

    queue.push({
      platform,
      eventName,
      leadData: {
        phone: leadData.phone,
        email: leadData.email,
        client_name: leadData.client_name,
        gclid: leadData.gclid,
        source: leadData.source
      },
      error: String(error).substring(0, 200),
      timestamp: new Date().toISOString()
    });

    fs.writeFileSync(QUEUE_FILE, JSON.stringify(queue, null, 2));
  } catch (e) {
    // Nao quebrar por causa da fila
  }
}

async function retryFailedConversions() {
  if (!fs.existsSync(QUEUE_FILE)) return { retried: 0, success: 0 };

  try {
    const queue = JSON.parse(fs.readFileSync(QUEUE_FILE, 'utf8'));
    if (queue.length === 0) return { retried: 0, success: 0 };

    console.log(`[CONVERSION] Reprocessando ${queue.length} conversoes falhadas...`);

    let successCount = 0;
    const remaining = [];

    for (const item of queue) {
      if (item.platform === 'google' && isGoogleAdsConfigured()) {
        const result = await sendGoogleConversion(item.eventName, item.leadData);
        if (result.success) successCount++;
        else remaining.push(item);
      } else {
        remaining.push(item);
      }
    }

    fs.writeFileSync(QUEUE_FILE, JSON.stringify(remaining, null, 2));
    console.log(`[CONVERSION] Retry: ${successCount}/${queue.length} sucesso, ${remaining.length} pendentes`);
    return { retried: queue.length, success: successCount };
  } catch (e) {
    console.error('[CONVERSION] Retry error:', e.message);
    return { retried: 0, success: 0, error: e.message };
  }
}

// ============================================================
// PUBLIC API
// ============================================================

async function trackNewLead(leadData) {
  console.log('[CONVERSION] Rastreando nova lead:', leadData.phone);
  const results = await Promise.all([
    sendGoogleConversion('lead', leadData),
    sendFacebookConversion('Lead', leadData, (process.env.ORG_WEBSITE || 'https://casehub.app'))
  ]);
  return results;
}

async function trackConsultationScheduled(leadData) {
  console.log('[CONVERSION] Rastreando consulta agendada:', leadData.phone);
  const results = await Promise.all([
    sendGoogleConversion('consultation_scheduled', leadData),
    sendFacebookConversion('Schedule', leadData, (process.env.ORG_WEBSITE || 'https://casehub.app'))
  ]);
  return results;
}

async function trackPaymentCompleted(leadData) {
  console.log('[CONVERSION] Rastreando pagamento:', leadData.phone);
  const results = await Promise.all([
    sendGoogleConversion('payment_completed', leadData),
    sendFacebookConversion('Purchase', leadData, (process.env.ORG_WEBSITE || 'https://casehub.app'))
  ]);
  return results;
}

async function trackQualifiedLead(leadData) {
  console.log('[CONVERSION] Rastreando lead qualificada:', leadData.phone, '- Score:', leadData.lead_score);
  const results = await Promise.all([
    sendGoogleConversion('qualified_lead', leadData),
    sendFacebookConversion('CompleteRegistration', leadData, (process.env.ORG_WEBSITE || 'https://casehub.app'))
  ]);
  return results;
}

function getStatus() {
  let queueSize = 0;
  try {
    if (fs.existsSync(QUEUE_FILE)) {
      queueSize = JSON.parse(fs.readFileSync(QUEUE_FILE, 'utf8')).length;
    }
  } catch (e) {}

  return {
    google: {
      configured: isGoogleAdsConfigured(),
      customerId: GOOGLE_ADS_CONFIG.customerId,
      hasConversionActions: Object.values(GOOGLE_ADS_CONFIG.conversionActions).some(v => !!v),
      conversionActions: Object.fromEntries(
        Object.entries(GOOGLE_ADS_CONFIG.conversionActions).map(([k, v]) => [k, v ? 'SET' : 'MISSING'])
      )
    },
    facebook: {
      configured: !!(FACEBOOK_CONFIG.pixelId && FACEBOOK_CONFIG.accessToken),
      pixelId: FACEBOOK_CONFIG.pixelId ? 'SET' : 'MISSING'
    },
    failedQueue: queueSize
  };
}

// ===== LOG STATUS AO INICIALIZAR =====
const status = getStatus();
if (status.google.configured) {
  console.log('[GADS] Google Ads Offline Conversions ATIVO');
  console.log('[GADS] Customer ID:', GOOGLE_ADS_CONFIG.customerId);
  if (!status.google.hasConversionActions) {
    console.log('[GADS] AVISO: Conversion actions nao definidas (GOOGLE_ADS_CONVERSION_*)');
  }
} else {
  console.log('[GADS] Google Ads Offline Conversions NAO configurado - conversoes salvas na fila');
  const missing = [];
  if (!GOOGLE_ADS_CONFIG.developerToken) missing.push('GOOGLE_ADS_DEVELOPER_TOKEN');
  if (!GOOGLE_ADS_CONFIG.clientId) missing.push('GOOGLE_ADS_CLIENT_ID');
  if (!GOOGLE_ADS_CONFIG.clientSecret) missing.push('GOOGLE_ADS_CLIENT_SECRET');
  if (!GOOGLE_ADS_CONFIG.refreshToken) missing.push('GOOGLE_ADS_REFRESH_TOKEN');
  console.log('[GADS] Faltam:', missing.join(', '));
}
if (status.facebook.configured) {
  console.log('[OK] Conversion Tracking ativo (Facebook CAPI)');
}

module.exports = {
  trackNewLead,
  trackConsultationScheduled,
  trackPaymentCompleted,
  trackQualifiedLead,
  sendGoogleConversion,
  sendFacebookConversion,
  retryFailedConversions,
  getStatus,
  GOOGLE_ADS_CONFIG,
  FACEBOOK_CONFIG
};
