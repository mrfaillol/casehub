/**
 * Follow-up Scheduler
 * CaseHub
 * v2.0 - Migrado de Resend para Gmail SMTP (nodemailer)
 * 2026-02-23
 */

const nodemailer = require('nodemailer');
const { FOLLOWUP_CONFIG } = require('./config');
const { generateEmail } = require('./email-templates');
const { getClientsWithEmail, syncAllClients } = require('./client-sync');
const { logFollowupActivity } = require('./moskit-activity');

let transporter = null;
const followupHistory = [];

function initTransporter() {
  if (!transporter) {
    try {
      const gmailUser = process.env.GMAIL_CENTER_EMAIL || (process.env.ORG_EMAIL || 'info@casehub.app');
      const gmailPass = process.env.GMAIL_CENTER_APP_PASSWORD;
      if (!gmailPass) {
        console.error('[FOLLOWUP-SCHEDULER] GMAIL_CENTER_APP_PASSWORD not configured');
        return null;
      }
      transporter = nodemailer.createTransport({
        service: 'gmail',
        auth: { user: gmailUser, pass: gmailPass }
      });
      console.log('[FOLLOWUP-SCHEDULER] Gmail SMTP initialized');
    } catch (error) {
      console.error('[FOLLOWUP-SCHEDULER] Failed to initialize Gmail SMTP:', error.message);
      transporter = null;
    }
  }
  return transporter;
}

function needsFollowup(client, type) {
  const intervalDays = type === 'weekly'
    ? FOLLOWUP_CONFIG.weeklyIntervalDays
    : FOLLOWUP_CONFIG.monthlyIntervalDays;
  const intervalMs = intervalDays * 24 * 60 * 60 * 1000;
  const lastFollowup = followupHistory
    .filter(f => f.clientPhone === client.phone && f.type === type && f.status === 'sent')
    .sort((a, b) => new Date(b.sentAt) - new Date(a.sentAt))[0];
  if (!lastFollowup) return true;
  return (Date.now() - new Date(lastFollowup.sentAt).getTime()) >= intervalMs;
}

async function sendFollowupEmail(client, type) {
  initTransporter();
  const email = generateEmail(type, client.name);
  const recipient = FOLLOWUP_CONFIG.testMode ? FOLLOWUP_CONFIG.testRecipient : client.email;
  if (!recipient) {
    console.log('[FOLLOWUP-SCHEDULER] No email for ' + client.name + ', skipping');
    return { success: false, error: 'No email address', client: client.name };
  }
  try {
    console.log('[FOLLOWUP-SCHEDULER] Sending ' + type + ' follow-up to ' + recipient + ' (' + client.name + ')');
    const result = await transporter.sendMail({
      from: FOLLOWUP_CONFIG.fromName + ' <' + FOLLOWUP_CONFIG.fromEmail + '>',
      to: recipient,
      subject: email.subject,
      html: email.html,
      text: email.text
    });
    const record = {
      id: result.messageId || ('local-' + Date.now()),
      clientName: client.name, clientPhone: client.phone, clientEmail: client.email,
      moskitId: client.moskitId, type: type, recipient: recipient,
      testMode: FOLLOWUP_CONFIG.testMode, status: 'sent',
      resendId: result.messageId, sentAt: new Date().toISOString()
    };
    followupHistory.push(record);
    if (client.moskitId && !FOLLOWUP_CONFIG.testMode) {
      await logFollowupActivity(client.moskitId, type, {
        emailId: result.messageId, recipient: recipient, testMode: FOLLOWUP_CONFIG.testMode
      });
    }
    console.log('[FOLLOWUP-SCHEDULER] Sent ' + type + ' follow-up to ' + client.name + ' (ID: ' + result.messageId + ')');
    return { success: true, emailId: result.messageId, client: client.name, recipient: recipient, testMode: FOLLOWUP_CONFIG.testMode };
  } catch (error) {
    console.error('[FOLLOWUP-SCHEDULER] Error sending to ' + client.name + ':', error.message);
    followupHistory.push({
      id: 'error-' + Date.now(), clientName: client.name, clientPhone: client.phone,
      clientEmail: client.email, type: type, recipient: recipient,
      testMode: FOLLOWUP_CONFIG.testMode, status: 'failed', error: error.message,
      sentAt: new Date().toISOString()
    });
    return { success: false, error: error.message, client: client.name };
  }
}

async function getClientsNeedingWeekly() {
  const clients = await getClientsWithEmail();
  return clients.filter(function(c) { return needsFollowup(c, 'weekly'); });
}

async function getClientsNeedingMonthly() {
  const clients = await getClientsWithEmail();
  return clients.filter(function(c) { return needsFollowup(c, 'monthly'); });
}

async function sendWeeklyFollowups(options) {
  options = options || {};
  var limit = options.limit || null;
  var dryRun = options.dryRun || false;
  console.log('[FOLLOWUP-SCHEDULER] Starting weekly follow-ups...');
  console.log('[FOLLOWUP-SCHEDULER] Test mode: ' + (FOLLOWUP_CONFIG.testMode ? 'ON' : 'OFF'));
  await syncAllClients();
  var clients = await getClientsNeedingWeekly();
  if (limit && limit > 0) clients = clients.slice(0, limit);
  console.log('[FOLLOWUP-SCHEDULER] Found ' + clients.length + ' clients needing weekly follow-up');
  if (dryRun) {
    console.log('[FOLLOWUP-SCHEDULER] DRY RUN - no emails will be sent');
    return { dryRun: true, type: 'weekly', clientCount: clients.length, clients: clients.map(function(c) { return { name: c.name, email: c.email }; }) };
  }
  var results = { type: 'weekly', startedAt: new Date().toISOString(), testMode: FOLLOWUP_CONFIG.testMode, total: clients.length, sent: 0, failed: 0, details: [] };
  for (var i = 0; i < clients.length; i++) {
    if (i > 0) await new Promise(function(r) { setTimeout(r, FOLLOWUP_CONFIG.delayBetweenEmails); });
    var result = await sendFollowupEmail(clients[i], 'weekly');
    results.details.push(result);
    if (result.success) results.sent++; else results.failed++;
  }
  results.completedAt = new Date().toISOString();
  console.log('[FOLLOWUP-SCHEDULER] Weekly follow-ups complete: ' + results.sent + ' sent, ' + results.failed + ' failed');
  return results;
}

async function sendMonthlyFollowups(options) {
  options = options || {};
  var limit = options.limit || null;
  var dryRun = options.dryRun || false;
  console.log('[FOLLOWUP-SCHEDULER] Starting monthly follow-ups...');
  console.log('[FOLLOWUP-SCHEDULER] Test mode: ' + (FOLLOWUP_CONFIG.testMode ? 'ON' : 'OFF'));
  await syncAllClients();
  var clients = await getClientsNeedingMonthly();
  if (limit && limit > 0) clients = clients.slice(0, limit);
  console.log('[FOLLOWUP-SCHEDULER] Found ' + clients.length + ' clients needing monthly follow-up');
  if (dryRun) {
    console.log('[FOLLOWUP-SCHEDULER] DRY RUN - no emails will be sent');
    return { dryRun: true, type: 'monthly', clientCount: clients.length, clients: clients.map(function(c) { return { name: c.name, email: c.email }; }) };
  }
  var results = { type: 'monthly', startedAt: new Date().toISOString(), testMode: FOLLOWUP_CONFIG.testMode, total: clients.length, sent: 0, failed: 0, details: [] };
  for (var i = 0; i < clients.length; i++) {
    if (i > 0) await new Promise(function(r) { setTimeout(r, FOLLOWUP_CONFIG.delayBetweenEmails); });
    var result = await sendFollowupEmail(clients[i], 'monthly');
    results.details.push(result);
    if (result.success) results.sent++; else results.failed++;
  }
  results.completedAt = new Date().toISOString();
  console.log('[FOLLOWUP-SCHEDULER] Monthly follow-ups complete: ' + results.sent + ' sent, ' + results.failed + ' failed');
  return results;
}

async function sendTestEmail(type) {
  type = type || 'weekly';
  initTransporter();
  var testClient = { name: 'Test Client', email: FOLLOWUP_CONFIG.testRecipient, phone: 'test', moskitId: null };
  console.log('[FOLLOWUP-SCHEDULER] Sending test ' + type + ' email to ' + FOLLOWUP_CONFIG.testRecipient);
  return await sendFollowupEmail(testClient, type);
}

function getHistory(options) {
  options = options || {};
  var type = options.type;
  var phone = options.phone;
  var days = options.days !== undefined ? options.days : 30;
  var limit = options.limit !== undefined ? options.limit : 100;
  var history = followupHistory.slice();
  if (type) history = history.filter(function(h) { return h.type === type; });
  if (phone) history = history.filter(function(h) { return h.clientPhone === phone; });
  if (days) {
    var cutoff = Date.now() - (days * 24 * 60 * 60 * 1000);
    history = history.filter(function(h) { return new Date(h.sentAt).getTime() >= cutoff; });
  }
  history.sort(function(a, b) { return new Date(b.sentAt) - new Date(a.sentAt); });
  if (limit) history = history.slice(0, limit);
  return history;
}

async function getStatus() {
  var clients = await getClientsWithEmail(false);
  var needsWeekly = await getClientsNeedingWeekly();
  var needsMonthly = await getClientsNeedingMonthly();
  var recentHistory = getHistory({ days: 7 });
  var sentThisWeek = recentHistory.filter(function(h) { return h.status === 'sent'; }).length;
  return {
    testMode: FOLLOWUP_CONFIG.testMode, testRecipient: FOLLOWUP_CONFIG.testRecipient,
    totalClientsWithEmail: clients.length, pendingWeekly: needsWeekly.length,
    pendingMonthly: needsMonthly.length, sentThisWeek: sentThisWeek,
    historyCount: followupHistory.length
  };
}

module.exports = {
  initResend: initTransporter,
  needsFollowup, sendFollowupEmail,
  getClientsNeedingWeekly, getClientsNeedingMonthly,
  sendWeeklyFollowups, sendMonthlyFollowups,
  sendTestEmail, getHistory, getStatus
};
