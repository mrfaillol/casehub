/**
 * CRM Sync Module - Dual-write to CaseHub CRM
 * Sends lead data to /api/leads/webhook alongside Moskit
 * CaseHub
 */

const https = require('https');
const http = require('http');

// CRM Configuration
const CRM_CONFIG = {
  // In production (VPS), use localhost since bot and CaseHub are on the same server
  baseUrl: process.env.CRM_WEBHOOK_URL || 'http://localhost:8001',
  apiKey: process.env.CRM_WEBHOOK_API_KEY || 'ilc-leads-webhook-2026',
  enabled: process.env.CRM_SYNC_ENABLED !== 'false', // enabled by default
  timeout: 5000 // 5s timeout
};

/**
 * Send lead data to CaseHub CRM webhook
 * Non-blocking: errors are logged but don't affect main flow
 */
async function sendToCRM(leadData) {
  if (!CRM_CONFIG.enabled) {
    return { success: false, reason: 'CRM sync disabled' };
  }

  try {
    const payload = {
      phone: leadData.phone ? String(leadData.phone).replace(/\D/g, '') : '',
      name: leadData.client_name || leadData.name || leadData.whatsapp_name || '',
      email: leadData.email || '',
      whatsapp_name: leadData.whatsapp_name || '',
      language: leadData.language || '',
      source: mapSource(leadData.source),
      source_detail: leadData.source || '',
      lead_score: leadData.lead_score || leadData.score || 0,
      visa_interest: leadData.visa_interest || leadData.interest || '',
      profession: leadData.profession || '',
      is_urgent: leadData.urgent || leadData.is_urgent || false,
      message_count: leadData.message_count || 0,
      notes: leadData.notes || '',
      moskit_contact_id: leadData.moskit_id || null,
      // UTM attribution data
      gclid: leadData.gclid || '',
      fbclid: leadData.fbclid || '',
      utm_source: leadData.utm_source || leadData.utmSource || '',
      utm_medium: leadData.utm_medium || leadData.utmMedium || '',
      utm_campaign: leadData.utm_campaign || leadData.utmCampaign || '',
    };

    // Add intake data if available
    if (leadData.intake_form_final_score) {
      payload.intake_form_final_score = leadData.intake_form_final_score;
    }
    if (leadData.intake_form_primary_pathway) {
      payload.intake_form_primary_pathway = leadData.intake_form_primary_pathway;
    }

    const response = await fetchWithTimeout(
      CRM_CONFIG.baseUrl + '/api/leads/webhook',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': CRM_CONFIG.apiKey
        },
        body: JSON.stringify(payload)
      },
      CRM_CONFIG.timeout
    );

    if (response.ok) {
      const result = await response.json();
      console.log('[CRM-SYNC] Lead synced:', result.lead_id, result.action);
      return { success: true, lead_id: result.lead_id, action: result.action };
    } else {
      const errorText = await response.text();
      console.error('[CRM-SYNC] HTTP error:', response.status, errorText);
      return { success: false, error: `HTTP ${response.status}` };
    }
  } catch (error) {
    console.error('[CRM-SYNC] Error:', error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Update an existing lead in CRM (by phone)
 * Used for intake form completions and score updates
 */
async function updateCRM(phone, updateData) {
  if (!CRM_CONFIG.enabled) {
    return { success: false, reason: 'CRM sync disabled' };
  }

  try {
    const payload = {
      phone: String(phone).replace(/\D/g, ''),
      ...updateData
    };

    const response = await fetchWithTimeout(
      CRM_CONFIG.baseUrl + '/api/leads/webhook',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': CRM_CONFIG.apiKey
        },
        body: JSON.stringify(payload)
      },
      CRM_CONFIG.timeout
    );

    if (response.ok) {
      const result = await response.json();
      console.log('[CRM-SYNC] Lead updated:', result.lead_id);
      return { success: true, lead_id: result.lead_id };
    } else {
      const errorText = await response.text();
      console.error('[CRM-SYNC] Update error:', response.status, errorText);
      return { success: false, error: `HTTP ${response.status}` };
    }
  } catch (error) {
    console.error('[CRM-SYNC] Update error:', error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Notify CaseHub caseworkers when a client sends a WhatsApp message.
 * Non-blocking: errors are logged but don't affect main flow.
 * Called when a known client (not a lead) sends a message.
 */
async function notifyClientMessage(phone, clientName, messagePreview) {
  if (!CRM_CONFIG.enabled) {
    return { success: false, reason: 'CRM sync disabled' };
  }

  try {
    const payload = {
      phone: String(phone).replace(/\D/g, ''),
      name: clientName || 'Unknown Client',
      message_preview: (messagePreview || '').substring(0, 200),
      is_known_client: true
    };

    const response = await fetchWithTimeout(
      CRM_CONFIG.baseUrl + '/api/notifications/whatsapp-message',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': CRM_CONFIG.apiKey
        },
        body: JSON.stringify(payload)
      },
      CRM_CONFIG.timeout
    );

    if (response.ok) {
      const result = await response.json();
      console.log('[CRM-NOTIFY] WhatsApp notification sent:', result.client_name, '-', result.notifications_created, 'staff notified');
      return { success: true, ...result };
    } else {
      const errorText = await response.text();
      console.error('[CRM-NOTIFY] HTTP error:', response.status, errorText);
      return { success: false, error: `HTTP ${response.status}` };
    }
  } catch (error) {
    console.error('[CRM-NOTIFY] Error:', error.message);
    return { success: false, error: error.message };
  }
}


/**
 * Map source strings from bot format to CRM format
 */
function mapSource(source) {
  if (!source) return 'WPP';
  const s = source.toLowerCase();
  if (s.includes('messenger')) return 'MSG';
  if (s.includes('instagram')) return 'IG';
  if (s.includes('site') || s.includes('form') || s.includes('elementor')) return 'SITE';
  if (s.includes('meta')) return 'META';
  return 'WPP';
}

/**
 * Fetch with timeout using Node.js built-in
 */
function fetchWithTimeout(url, options, timeoutMs) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`CRM request timeout (${timeoutMs}ms)`));
    }, timeoutMs);

    const urlObj = new URL(url);
    const client = urlObj.protocol === 'https:' ? https : http;

    const req = client.request(url, {
      method: options.method || 'POST',
      headers: options.headers || {}
    }, (res) => {
      clearTimeout(timer);
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        resolve({
          ok: res.statusCode >= 200 && res.statusCode < 300,
          status: res.statusCode,
          text: () => Promise.resolve(body),
          json: () => Promise.resolve(JSON.parse(body))
        });
      });
    });

    req.on('error', (err) => {
      clearTimeout(timer);
      reject(err);
    });

    if (options.body) {
      req.write(options.body);
    }
    req.end();
  });
}

module.exports = {
  sendToCRM,
  updateCRM,
  notifyClientMessage,
  CRM_CONFIG
};
