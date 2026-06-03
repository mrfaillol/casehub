/**
 * Client Follow-up System
 * CaseHub
 * v1.0
 *
 * Main entry point - integrates scheduler and API routes
 * Uses setInterval for scheduling (no external dependencies)
 */

const { FOLLOWUP_CONFIG, setTestMode, getConfigStatus } = require('./config');
const { generateEmail } = require('./email-templates');
const { syncAllClients, getActiveClients, getClientsWithEmail, getStats } = require('./client-sync');
const { logFollowupActivity } = require('./moskit-activity');
const {
  sendWeeklyFollowups,
  sendMonthlyFollowups,
  sendTestEmail,
  getHistory,
  getStatus
} = require('./followup-scheduler');

// Scheduler state
let schedulerInterval = null;
let lastWeeklyCheck = null;
let lastMonthlyCheck = null;

/**
 * Initialize the follow-up system
 */
async function init() {
  console.log('[CLIENT-FOLLOWUP] Initializing follow-up system...');
  console.log(`[CLIENT-FOLLOWUP] Test mode: ${FOLLOWUP_CONFIG.testMode ? 'ON' : 'OFF'}`);

  if (FOLLOWUP_CONFIG.testMode) {
    console.log(`[CLIENT-FOLLOWUP] Test recipient: ${FOLLOWUP_CONFIG.testRecipient}`);
  }

  // Initial client sync (don't await - run in background)
  syncAllClients().then(result => {
    console.log(`[CLIENT-FOLLOWUP] Initial sync complete: ${result.totalClients} clients, ${result.emailsFound} with email`);
  }).catch(err => {
    console.error('[CLIENT-FOLLOWUP] Initial sync error:', err.message);
  });

  console.log('[CLIENT-FOLLOWUP] System initialized');
  return true;
}

/**
 * Check if it's time for weekly follow-ups (Monday 9 AM EST)
 */
function shouldRunWeekly() {
  const now = new Date();
  // Convert to EST
  const estNow = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const dayOfWeek = estNow.getDay(); // 0 = Sunday, 1 = Monday
  const hour = estNow.getHours();

  // Monday between 9:00-9:59 AM
  if (dayOfWeek === 1 && hour === 9) {
    // Check if already ran today
    if (lastWeeklyCheck) {
      const lastCheck = new Date(lastWeeklyCheck);
      if (lastCheck.toDateString() === estNow.toDateString()) {
        return false; // Already ran today
      }
    }
    return true;
  }
  return false;
}

/**
 * Check if it's time for monthly follow-ups (1st of month 9 AM EST)
 */
function shouldRunMonthly() {
  const now = new Date();
  // Convert to EST
  const estNow = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const dayOfMonth = estNow.getDate();
  const hour = estNow.getHours();

  // 1st of month between 9:00-9:59 AM
  if (dayOfMonth === 1 && hour === 9) {
    // Check if already ran this month
    if (lastMonthlyCheck) {
      const lastCheck = new Date(lastMonthlyCheck);
      if (lastCheck.getMonth() === estNow.getMonth() && lastCheck.getFullYear() === estNow.getFullYear()) {
        return false; // Already ran this month
      }
    }
    return true;
  }
  return false;
}

/**
 * Scheduler check function - runs every hour
 */
async function schedulerCheck() {
  console.log('[CLIENT-FOLLOWUP] Scheduler check...');

  // Check for weekly follow-ups
  if (shouldRunWeekly()) {
    console.log('[CLIENT-FOLLOWUP] Running scheduled weekly follow-ups...');
    try {
      const result = await sendWeeklyFollowups();
      lastWeeklyCheck = new Date().toISOString();
      console.log(`[CLIENT-FOLLOWUP] Weekly complete - ${result.sent} sent, ${result.failed} failed`);
    } catch (error) {
      console.error('[CLIENT-FOLLOWUP] Weekly error:', error.message);
    }
  }

  // Check for monthly follow-ups
  if (shouldRunMonthly()) {
    console.log('[CLIENT-FOLLOWUP] Running scheduled monthly follow-ups...');
    try {
      const result = await sendMonthlyFollowups();
      lastMonthlyCheck = new Date().toISOString();
      console.log(`[CLIENT-FOLLOWUP] Monthly complete - ${result.sent} sent, ${result.failed} failed`);
    } catch (error) {
      console.error('[CLIENT-FOLLOWUP] Monthly error:', error.message);
    }
  }
}

/**
 * Start automated scheduler (checks every hour)
 */
function startScheduler() {
  console.log('[CLIENT-FOLLOWUP] Starting scheduler...');

  // Run check every hour (3600000 ms)
  schedulerInterval = setInterval(schedulerCheck, 60 * 60 * 1000);

  // Run first check after 1 minute
  setTimeout(schedulerCheck, 60 * 1000);

  console.log('[CLIENT-FOLLOWUP] Scheduler started - checking every hour');
  console.log('[CLIENT-FOLLOWUP] Weekly: Monday 9 AM EST');
  console.log('[CLIENT-FOLLOWUP] Monthly: 1st of month 9 AM EST');

  return true;
}

/**
 * Stop scheduler
 */
function stopScheduler() {
  if (schedulerInterval) {
    clearInterval(schedulerInterval);
    schedulerInterval = null;
  }
  console.log('[CLIENT-FOLLOWUP] Scheduler stopped');
  return true;
}

/**
 * Setup Express routes for the follow-up system
 * @param {Express} app - Express application instance
 */
function setupRoutes(app) {
  console.log('[CLIENT-FOLLOWUP] Setting up API routes...');

  // Get system status
  app.get('/api/followup/status', async (req, res) => {
    try {
      const status = await getStatus();
      const clientStats = getStats();
      res.json({
        success: true,
        ...status,
        clients: clientStats
      });
    } catch (error) {
      res.status(500).json({ success: false, error: error.message });
    }
  });

  // Get configuration
  app.get('/api/followup/config', (req, res) => {
    res.json({
      success: true,
      config: getConfigStatus()
    });
  });

  // Toggle test mode
  app.post('/api/followup/test-mode', (req, res) => {
    try {
      const { enabled, testEmail } = req.body;

      if (typeof enabled !== 'boolean') {
        return res.status(400).json({ success: false, error: 'enabled must be a boolean' });
      }

      const result = setTestMode(enabled, testEmail);
      res.json({
        success: true,
        message: `Test mode ${enabled ? 'enabled' : 'disabled'}`,
        ...result
      });
    } catch (error) {
      res.status(500).json({ success: false, error: error.message });
    }
  });

  // Get all clients
  app.get('/api/followup/clients', async (req, res) => {
    try {
      const refresh = req.query.refresh === 'true';
      const clients = await getActiveClients(refresh);
      const stats = getStats();

      res.json({
        success: true,
        count: clients.length,
        stats: stats,
        clients: clients.map(c => ({
          name: c.name,
          caseNumber: c.caseNumber,
          phone: c.phone,
          email: c.email,
          country: c.country,
          moskitId: c.moskitId
        }))
      });
    } catch (error) {
      res.status(500).json({ success: false, error: error.message });
    }
  });

  // Sync clients with Moskit
  app.post('/api/followup/sync-clients', async (req, res) => {
    try {
      console.log('[API] Starting client sync...');
      const result = await syncAllClients(true);
      res.json({
        success: true,
        message: 'Client sync complete',
        ...result
      });
    } catch (error) {
      res.status(500).json({ success: false, error: error.message });
    }
  });

  // Send weekly follow-ups manually
  app.post('/api/followup/send-weekly', async (req, res) => {
    try {
      const { limit, dryRun } = req.body;
      console.log('[API] Triggering weekly follow-ups...');

      const result = await sendWeeklyFollowups({
        limit: limit || null,
        dryRun: dryRun || false
      });

      res.json({
        success: true,
        ...result
      });
    } catch (error) {
      res.status(500).json({ success: false, error: error.message });
    }
  });

  // Send monthly follow-ups manually
  app.post('/api/followup/send-monthly', async (req, res) => {
    try {
      const { limit, dryRun } = req.body;
      console.log('[API] Triggering monthly follow-ups...');

      const result = await sendMonthlyFollowups({
        limit: limit || null,
        dryRun: dryRun || false
      });

      res.json({
        success: true,
        ...result
      });
    } catch (error) {
      res.status(500).json({ success: false, error: error.message });
    }
  });

  // Send test email
  app.post('/api/followup/send-test', async (req, res) => {
    try {
      const { type = 'weekly' } = req.body;
      console.log(`[API] Sending test ${type} email...`);

      const result = await sendTestEmail(type);
      res.json({
        success: result.success,
        message: result.success ? 'Test email sent' : 'Failed to send test email',
        ...result
      });
    } catch (error) {
      res.status(500).json({ success: false, error: error.message });
    }
  });

  // Get follow-up history
  app.get('/api/followup/history', (req, res) => {
    try {
      const { type, phone, days, limit } = req.query;
      const history = getHistory({
        type,
        phone,
        days: days ? parseInt(days) : 30,
        limit: limit ? parseInt(limit) : 100
      });

      res.json({
        success: true,
        count: history.length,
        history: history
      });
    } catch (error) {
      res.status(500).json({ success: false, error: error.message });
    }
  });

  // Preview email template
  app.post('/api/followup/preview', (req, res) => {
    try {
      const { type = 'weekly', clientName = 'John Doe' } = req.body;
      const email = generateEmail(type, clientName);

      res.json({
        success: true,
        type: type,
        subject: email.subject,
        html: email.html,
        text: email.text
      });
    } catch (error) {
      res.status(500).json({ success: false, error: error.message });
    }
  });

  // Get email preview as HTML
  app.get('/api/followup/preview/:type', (req, res) => {
    try {
      const { type } = req.params;
      const clientName = req.query.name || 'John Doe';
      const email = generateEmail(type, clientName);

      res.setHeader('Content-Type', 'text/html');
      res.send(email.html);
    } catch (error) {
      res.status(500).send(`<h1>Error</h1><p>${error.message}</p>`);
    }
  });

  console.log('[CLIENT-FOLLOWUP] API routes configured:');
  console.log('  GET  /api/followup/status');
  console.log('  GET  /api/followup/config');
  console.log('  POST /api/followup/test-mode');
  console.log('  GET  /api/followup/clients');
  console.log('  POST /api/followup/sync-clients');
  console.log('  POST /api/followup/send-weekly');
  console.log('  POST /api/followup/send-monthly');
  console.log('  POST /api/followup/send-test');
  console.log('  GET  /api/followup/history');
  console.log('  POST /api/followup/preview');
  console.log('  GET  /api/followup/preview/:type');

  return true;
}

// Export all modules and functions
module.exports = {
  // Initialization
  init,
  setupRoutes,
  startScheduler,
  stopScheduler,

  // Config
  FOLLOWUP_CONFIG,
  setTestMode,
  getConfigStatus,

  // Client Sync
  syncAllClients,
  getActiveClients,
  getClientsWithEmail,
  getStats,

  // Scheduler
  sendWeeklyFollowups,
  sendMonthlyFollowups,
  sendTestEmail,
  getHistory,
  getStatus,

  // Templates
  generateEmail,

  // Moskit
  logFollowupActivity
};
