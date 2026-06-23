/**
 * Client Follow-up System Configuration
 * CaseHub
 * v1.0
 */

const FOLLOWUP_CONFIG = {
  // TEST MODE - When true, all emails go to testRecipient instead of clients
  // v11.0: DESATIVADO para produção
  testMode: false,
  testRecipient: 'admin@example.com',

  // Email Configuration
  fromEmail: (process.env.ORG_EMAIL || 'info@casehub.app'),
  fromName: '${process.env.ORG_NAME || "CaseHub"}',

  // Follow-up Intervals (in days)
  weeklyIntervalDays: 7,
  monthlyIntervalDays: 30,

  // Cron Schedules (server timezone)
  // Format: second minute hour day-of-month month day-of-week
  weeklyCron: '0 9 * * 1',    // Every Monday at 9:00 AM
  monthlyCron: '0 9 1 * *',   // 1st of each month at 9:00 AM

  // Rate Limiting
  emailsPerMinute: 10,        // Max emails per minute (Resend limit)
  delayBetweenEmails: 6000,   // 6 seconds between emails

  // Retry Configuration
  maxRetries: 3,
  retryDelayMs: 30000,        // 30 seconds between retries

  // Moskit Configuration (reused from existing)
  moskitApiKey: process.env.MOSKIT_API_KEY || '',
  moskitBaseUrl: 'https://api.moskitcrm.com/v2',
  moskitResponsibleId: 105810,

  // Paths
  activeClientsPath: './active-clients.json'
};

/**
 * Toggle test mode
 */
function setTestMode(enabled, testEmail = null) {
  FOLLOWUP_CONFIG.testMode = enabled;
  if (testEmail) {
    FOLLOWUP_CONFIG.testRecipient = testEmail;
  }
  console.log(`[FOLLOWUP-CONFIG] Test mode: ${enabled ? 'ON' : 'OFF'}`);
  if (enabled) {
    console.log(`[FOLLOWUP-CONFIG] All emails will be sent to: ${FOLLOWUP_CONFIG.testRecipient}`);
  }
  return {
    testMode: FOLLOWUP_CONFIG.testMode,
    testRecipient: FOLLOWUP_CONFIG.testRecipient
  };
}

/**
 * Get current configuration status
 */
function getConfigStatus() {
  return {
    testMode: FOLLOWUP_CONFIG.testMode,
    testRecipient: FOLLOWUP_CONFIG.testRecipient,
    fromEmail: FOLLOWUP_CONFIG.fromEmail,
    weeklyIntervalDays: FOLLOWUP_CONFIG.weeklyIntervalDays,
    monthlyIntervalDays: FOLLOWUP_CONFIG.monthlyIntervalDays,
    weeklyCron: FOLLOWUP_CONFIG.weeklyCron,
    monthlyCron: FOLLOWUP_CONFIG.monthlyCron
  };
}

module.exports = {
  FOLLOWUP_CONFIG,
  setTestMode,
  getConfigStatus
};
