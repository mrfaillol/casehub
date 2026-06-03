/**
 * Notification Service - Centralized Message Sending Gateway
 * CaseHub WhatsApp Bot
 * v1.0 - Eliminates LLM conflict by funneling ALL outgoing messages through one point
 *
 * PROBLEM SOLVED:
 *   4 independent systems were sending WhatsApp messages without coordination:
 *   1. Main handler (message.reply)
 *   2. Lead Monitor (whatsappClient.sendMessage every 5 min)
 *   3. Auto Follow-up (whatsappClient.sendMessage every 15 min)
 *   4. Catch-up (whatsappClient.sendMessage on reactivation)
 *   This caused duplicate/conflicting responses to the same lead.
 *
 * SOLUTION:
 *   Every outgoing message MUST go through notificationService.send().
 *   The service enforces:
 *   - Bot guard checks (hardOff, business hours, never-contact)
 *   - Response deduplication (no double-sends within DEDUP_WINDOW_MS)
 *   - Source tracking (which system sent)
 *   - Logging of all sends and blocks
 *
 * USAGE:
 *   const notificationService = require('./services/notification-service');
 *   notificationService.init(whatsappClient, db, botConfig);
 *
 *   // Send a message (guards + dedup applied automatically)
 *   const result = await notificationService.send(phone, text, {
 *     source: 'main-handler',  // or 'lead-monitor', 'auto-followup', 'catch-up'
 *     replyTo: message,        // optional: use message.reply() instead of sendMessage
 *     skipGuard: false,        // optional: bypass guard (for Maestro admin only)
 *     skipDedup: false,        // optional: bypass dedup window
 *     saveToDB: true           // optional: auto-save to conversations table
 *   });
 */

let whatsappClient = null;
let db = null;
let botConfig = null;

// Deduplication: track last send time per phone
const lastSendTime = new Map();
const DEDUP_WINDOW_MS = 3 * 60 * 1000; // 3 minutes - no duplicate responses within this window

// Stats tracking
const stats = {
  sent: 0,
  blocked_guard: 0,
  blocked_dedup: 0,
  errors: 0
};

// Cleanup old entries every 10 minutes
setInterval(() => {
  const now = Date.now();
  let cleaned = 0;
  for (const [phone, data] of lastSendTime) {
    if (now - data.timestamp > DEDUP_WINDOW_MS * 2) {
      lastSendTime.delete(phone);
      cleaned++;
    }
  }
  if (cleaned > 0) {
    console.log(`[NOTIF-SERVICE] Cleaned ${cleaned} expired dedup entries`);
  }
}, 10 * 60 * 1000);

/**
 * Initialize the notification service with dependencies
 */
function init(client, database, botConfigModule) {
  whatsappClient = client;
  db = database;
  botConfig = botConfigModule;
  console.log("[NOTIF-SERVICE] Initialized - all outgoing messages will be guarded");
}

/**
 * Check if a message can be sent (guard + dedup)
 * Returns { allowed: boolean, reason: string }
 */
function canSend(phone, options = {}) {
  const { skipGuard = false, skipDedup = false, source = 'unknown' } = options;

  // Guard check (hardOff, business hours, never-contact)
  if (!skipGuard && botConfig) {
    // Hard OFF blocks everything
    if (typeof botConfig.isHardOff === 'function' && botConfig.isHardOff()) {
      return { allowed: false, reason: 'hard_off' };
    }

    // Full bot control check (includes business hours)
    if (typeof botConfig.shouldBotRespond === 'function') {
      const botStatus = botConfig.shouldBotRespond(phone);
      if (!botStatus.shouldRespond) {
        return { allowed: false, reason: botStatus.reason || 'bot_disabled' };
      }
    }
  }

  // Deduplication check
  if (!skipDedup) {
    const lastSend = lastSendTime.get(phone);
    if (lastSend) {
      const elapsed = Date.now() - lastSend.timestamp;
      if (elapsed < DEDUP_WINDOW_MS) {
        return {
          allowed: false,
          reason: `dedup_window (last sent ${Math.round(elapsed / 1000)}s ago by ${lastSend.source})`
        };
      }
    }
  }

  return { allowed: true, reason: 'ok' };
}

/**
 * Send a message through the centralized gateway
 *
 * @param {string} phone - Phone number (with or without @c.us)
 * @param {string} text - Message text to send
 * @param {Object} options
 * @param {string} options.source - Identifier of the calling system
 * @param {Object} options.replyTo - WhatsApp message object for inline reply
 * @param {boolean} options.skipGuard - Skip bot guard checks (admin only)
 * @param {boolean} options.skipDedup - Skip deduplication window
 * @param {boolean} options.saveToDB - Save message to DB (default: true)
 * @returns {Object} { sent: boolean, reason: string }
 */
async function send(phone, text, options = {}) {
  const {
    source = 'unknown',
    replyTo = null,
    skipGuard = false,
    skipDedup = false,
    saveToDB = true
  } = options;

  const cleanPhone = phone.replace(/@c\.us|@lid/g, '');

  // Pre-flight checks
  const check = canSend(cleanPhone, { skipGuard, skipDedup, source });
  if (!check.allowed) {
    const logLevel = check.reason === 'hard_off' ? 'log' : 'log';
    console[logLevel](`[NOTIF-SERVICE] BLOCKED [${source}] -> ${cleanPhone}: ${check.reason}`);

    if (check.reason.startsWith('dedup_window')) {
      stats.blocked_dedup++;
    } else {
      stats.blocked_guard++;
    }

    return { sent: false, reason: check.reason };
  }

  // Send the message
  try {
    if (!whatsappClient) {
      throw new Error('WhatsApp client not initialized');
    }

    if (replyTo && typeof replyTo.reply === 'function') {
      // Use inline reply (quotes the user's message)
      await replyTo.reply(text);
    } else {
      // Direct send
      await whatsappClient.sendMessage(phone, text);
    }

    // Record send time for dedup
    lastSendTime.set(cleanPhone, {
      timestamp: Date.now(),
      source: source
    });

    // Save to DB
    if (saveToDB && db) {
      try {
        await db.saveMessage(cleanPhone, 'assistant', text);
      } catch (dbErr) {
        console.error(`[NOTIF-SERVICE] DB save error for ${cleanPhone}:`, dbErr.message);
      }
    }

    stats.sent++;
    console.log(`[NOTIF-SERVICE] SENT [${source}] -> ${cleanPhone} (${text.substring(0, 60)}...)`);

    return { sent: true, reason: 'ok' };

  } catch (error) {
    stats.errors++;
    console.error(`[NOTIF-SERVICE] ERROR [${source}] -> ${cleanPhone}:`, error.message);
    return { sent: false, reason: `error: ${error.message}` };
  }
}

/**
 * Record that a message was sent (for external sends that bypass this service temporarily)
 * Used during migration to track sends from legacy code paths
 */
function recordSend(phone, source = 'legacy') {
  const cleanPhone = phone.replace(/@c\.us|@lid/g, '');
  lastSendTime.set(cleanPhone, {
    timestamp: Date.now(),
    source: source
  });
}

/**
 * Get service stats
 */
function getStats() {
  return {
    ...stats,
    activeDedup: lastSendTime.size,
    dedupWindowMs: DEDUP_WINDOW_MS
  };
}

/**
 * Reset dedup for a specific phone (used when human takes over)
 */
function resetDedup(phone) {
  const cleanPhone = phone.replace(/@c\.us|@lid/g, '');
  lastSendTime.delete(cleanPhone);
}

module.exports = {
  init,
  send,
  canSend,
  recordSend,
  getStats,
  resetDedup,
  DEDUP_WINDOW_MS
};
