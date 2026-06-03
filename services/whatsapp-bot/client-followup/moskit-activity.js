/**
 * Moskit Activity Logger
 * CaseHub
 * v1.0
 *
 * Logs follow-up activities to Moskit CRM contacts as notes
 */

const { FOLLOWUP_CONFIG } = require('./config');

/**
 * Get Moskit contact by ID
 */
async function getMoskitContact(contactId) {
  try {
    const response = await fetch(
      `${FOLLOWUP_CONFIG.moskitBaseUrl}/contacts/${contactId}`,
      {
        method: 'GET',
        headers: {
          'apikey': FOLLOWUP_CONFIG.moskitApiKey,
          'Content-Type': 'application/json'
        }
      }
    );

    if (!response.ok) {
      console.error(`[MOSKIT-ACTIVITY] Error fetching contact ${contactId}: ${response.status}`);
      return null;
    }

    return await response.json();
  } catch (error) {
    console.error(`[MOSKIT-ACTIVITY] Error fetching contact:`, error.message);
    return null;
  }
}

/**
 * Update Moskit contact notes
 */
async function updateContactNotes(contactId, newNotes) {
  try {
    const response = await fetch(
      `${FOLLOWUP_CONFIG.moskitBaseUrl}/contacts/${contactId}`,
      {
        method: 'PUT',
        headers: {
          'apikey': FOLLOWUP_CONFIG.moskitApiKey,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          notes: newNotes,
          createdBy: { id: FOLLOWUP_CONFIG.moskitResponsibleId },
          responsible: { id: FOLLOWUP_CONFIG.moskitResponsibleId }
        })
      }
    );

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`[MOSKIT-ACTIVITY] Error updating contact ${contactId}: ${response.status} - ${errorText}`);
      return { success: false, error: errorText };
    }

    const result = await response.json();
    return { success: true, contact: result };
  } catch (error) {
    console.error(`[MOSKIT-ACTIVITY] Error updating contact:`, error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Format activity note text
 */
function formatActivityNote(type, details = {}) {
  const date = new Date().toLocaleString('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });

  const typeLabel = type === 'weekly' ? 'WEEKLY' : 'MONTHLY';

  let note = `[AUTO-FOLLOWUP] ${typeLabel} email sent on ${date}`;

  if (details.emailId) {
    note += `\nResend ID: ${details.emailId}`;
  }

  if (details.recipient) {
    note += `\nRecipient: ${details.recipient}`;
  }

  if (details.testMode) {
    note += `\n(TEST MODE - sent to test recipient)`;
  }

  return note;
}

/**
 * Log a follow-up activity to a Moskit contact
 */
async function logFollowupActivity(contactId, type, details = {}) {
  if (!contactId) {
    console.log('[MOSKIT-ACTIVITY] No contact ID provided, skipping activity log');
    return { success: false, error: 'No contact ID' };
  }

  try {
    // Get current contact to preserve existing notes
    const contact = await getMoskitContact(contactId);

    if (!contact) {
      console.error(`[MOSKIT-ACTIVITY] Contact ${contactId} not found`);
      return { success: false, error: 'Contact not found' };
    }

    // Format new note
    const activityNote = formatActivityNote(type, details);

    // Append to existing notes
    const existingNotes = contact.notes || '';
    const separator = existingNotes ? '\n\n---\n\n' : '';
    const updatedNotes = existingNotes + separator + activityNote;

    // Update contact
    const result = await updateContactNotes(contactId, updatedNotes);

    if (result.success) {
      console.log(`[MOSKIT-ACTIVITY] Logged ${type} follow-up for contact ${contactId}`);
    }

    return result;
  } catch (error) {
    console.error(`[MOSKIT-ACTIVITY] Error logging activity:`, error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Batch log activities for multiple contacts
 */
async function batchLogActivities(logs) {
  const results = [];

  for (const log of logs) {
    // Rate limit
    await new Promise(r => setTimeout(r, 300));

    const result = await logFollowupActivity(
      log.contactId,
      log.type,
      log.details
    );

    results.push({
      contactId: log.contactId,
      ...result
    });
  }

  const successful = results.filter(r => r.success).length;
  const failed = results.filter(r => !r.success).length;

  console.log(`[MOSKIT-ACTIVITY] Batch complete: ${successful} success, ${failed} failed`);

  return {
    total: results.length,
    successful,
    failed,
    results
  };
}

module.exports = {
  getMoskitContact,
  updateContactNotes,
  formatActivityNote,
  logFollowupActivity,
  batchLogActivities
};
