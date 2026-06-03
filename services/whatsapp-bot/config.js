/**
 * Centralized Configuration
 * CaseHub WhatsApp Bot
 * v2.0 - All secrets from .env, zero hardcoded values
 *
 * USAGE: const config = require('./config');
 *        config.moskit.apiKey, config.stripe.secretKey, etc.
 */
require('dotenv').config();

function requireEnv(name, fallback) {
  const val = process.env[name] || fallback;
  if (!val) {
    console.warn(`[CONFIG] WARNING: ${name} not set in .env`);
  }
  return val || '';
}

module.exports = {
  server: {
    port: process.env.PORT || 3001,
    nodeEnv: process.env.NODE_ENV || 'development',
    uiAccessToken: requireEnv('UI_ACCESS_TOKEN'),
    botName: process.env.BOT_NAME || 'CaseHub WhatsApp Bot',
    businessPhone: process.env.BUSINESS_PHONE || ''
  },

  database: {
    host: process.env.DB_HOST || 'localhost',
    user: requireEnv('DB_USER'),
    password: requireEnv('DB_PASSWORD'),
    database: requireEnv('DB_NAME')
  },

  postgres: {
    host: process.env.PG_HOST || 'localhost',
    port: parseInt(process.env.PG_PORT || '5432'),
    user: process.env.PG_USER || 'casehub',
    password: requireEnv('PG_PASSWORD'),
    database: process.env.PG_DATABASE || 'casehub'
  },

  gemini: {
    apiKey: requireEnv('GEMINI_API_KEY'),
    model: 'gemini-2.0-flash'
  },

  moskit: {
    apiKey: requireEnv('MOSKIT_API_KEY'),
    baseUrl: 'https://api.moskitcrm.com/v2',
    responsibleId: parseInt(process.env.MOSKIT_RESPONSIBLE_ID || '105810'),
    pipelineId: parseInt(process.env.MOSKIT_PIPELINE_ID || '70006'),
    stages: {
      NEW_LEAD: 322283,
      LEAD_QUALIFICATION: 322808,
      INTAKE_CALL: 322282,
      CONSULTATION: 322284,
      CLOSING: 322809,
      VISA_IN_PROGRESS: 371211
    }
  },

  stripe: {
    secretKey: requireEnv('STRIPE_SECRET_KEY'),
    webhookSecret: process.env.STRIPE_WEBHOOK_SECRET || '',
    consultationPrice: process.env.STRIPE_CONSULTATION_PRICE || 'price_default'
  },

  calendly: {
    apiKey: requireEnv('CALENDLY_API_KEY'),
    organizationUrl: process.env.CALENDLY_ORG_URL || '',
    userUrl: process.env.CALENDLY_USER_URL || ''
  },

  email: {
    resendApiKey: requireEnv('RESEND_API_KEY'),
    gmailEmail: process.env.GMAIL_CENTER_EMAIL || (process.env.ORG_EMAIL || 'info@casehub.app'),
    gmailAppPassword: requireEnv('GMAIL_CENTER_APP_PASSWORD')
  },

  callhippo: {
    apiKey: process.env.CALLHIPPO_API_KEY || '',
    email: process.env.CALLHIPPO_EMAIL || '',
    from: process.env.CALLHIPPO_FROM || '',
    to: process.env.CALLHIPPO_TO || '',
    webhookSecret: process.env.CALLHIPPO_WEBHOOK_SECRET || ''
  },

  twilio: {
    accountSid: process.env.TWILIO_ACCOUNT_SID || '',
    authToken: process.env.TWILIO_AUTH_TOKEN || '',
    phoneNumber: process.env.TWILIO_PHONE_NUMBER || ''
  },

  facebook: {
    pixelId: process.env.FB_PIXEL_ID || '',
    capiToken: process.env.FB_CAPI_TOKEN || ''
  },

  googleAds: {
    customerId: process.env.GOOGLE_ADS_CUSTOMER_ID || '',
    loginCustomerId: process.env.GOOGLE_ADS_LOGIN_CUSTOMER_ID || '',
    developerToken: process.env.GOOGLE_ADS_DEVELOPER_TOKEN || '',
    clientId: process.env.GOOGLE_ADS_CLIENT_ID || '',
    clientSecret: process.env.GOOGLE_ADS_CLIENT_SECRET || '',
    refreshToken: process.env.GOOGLE_ADS_REFRESH_TOKEN || ''
  },

  ga4: {
    measurementId: process.env.GA4_MEASUREMENT_ID || '',
    apiSecret: process.env.GA4_API_SECRET || ''
  },

  crm: {
    syncEnabled: process.env.CRM_SYNC_ENABLED === 'true',
    webhookUrl: process.env.CRM_WEBHOOK_URL || '',
    webhookApiKey: process.env.CRM_WEBHOOK_API_KEY || ''
  },

  maestro: {
    enabled: process.env.MAESTRO_ACTIVATION_ENABLED === 'true',
    adminPhone: process.env.MAESTRO_ADMIN_PHONE || '',
    apiKey: process.env.MAESTRO_API_KEY || '',
    url: process.env.MAESTRO_URL || '',
    perplexityApiKey: process.env.PERPLEXITY_API_KEY || ''
  },

  notifications: {
    googleChatWebhookVictor: process.env.GOOGLE_CHAT_WEBHOOK_VICTOR || ''
  }
};
