/**
 * SMS Queue Service - Manages SMS notification queue for Android/Tasker
 * Extracted from server.js (Fase 2.2 decomposition)
 *
 * The Android phone polls /api/sms-queue endpoints to fetch pending
 * SMS notifications and send them via native SMS.
 */

const SMS_NUMBERS = ['+14422197512', '+19406183140'];
const smsQueue = [];

// Add SMS to the queue (sends to all configured numbers)
function queueSMS(message) {
  const id = Date.now().toString();
  for (const number of SMS_NUMBERS) {
    smsQueue.push({
      id: id + '_' + number.slice(-4),
      to: number,
      message: message,
      created_at: new Date().toISOString()
    });
  }
  console.log('[SMS-QUEUE] Adicionado:', message.substring(0, 50) + '...');
}

// Get all pending SMS items
function getQueue() {
  if (smsQueue.length === 0) {
    return { pending: false, count: 0, messages: [] };
  }
  return {
    pending: true,
    count: smsQueue.length,
    messages: [...smsQueue]
  };
}

// Confirm SMS items as sent (removes from queue)
function confirmSMS(ids) {
  if (!ids || !Array.isArray(ids)) {
    return { success: false, error: "ids array obrigatorio" };
  }
  for (const id of ids) {
    const index = smsQueue.findIndex(sms => sms.id === id);
    if (index !== -1) {
      smsQueue.splice(index, 1);
    }
  }
  console.log('[SMS-QUEUE] Confirmados:', ids.length, '| Restantes:', smsQueue.length);
  return { success: true, remaining: smsQueue.length };
}

// Get next SMS for a target number (Tasker simple endpoint)
// Returns the message and removes it from queue
function getNextSimple(targetNumber) {
  if (!targetNumber) targetNumber = SMS_NUMBERS[0];
  const smsIndex = smsQueue.findIndex(sms => sms.to === targetNumber);

  if (smsIndex === -1) {
    return null;
  }

  const sms = smsQueue[smsIndex];
  smsQueue.splice(smsIndex, 1);
  console.log('[SMS-QUEUE] Enviando via simple:', sms.message.substring(0, 50) + '...');
  return sms.message;
}

// Get current queue size
function getQueueSize() {
  return smsQueue.length;
}

module.exports = {
  queueSMS,
  getQueue,
  confirmSMS,
  getNextSimple,
  getQueueSize,
  SMS_NUMBERS
};
