/**
 * Client Sync Module
 * CaseHub
 * v1.0
 *
 * Handles syncing client data with Moskit CRM to get emails
 */

const fs = require('fs');
const path = require('path');
const { FOLLOWUP_CONFIG } = require('./config');

// In-memory cache of enriched clients
let enrichedClients = [];

/**
 * v11.0: Helper function to extract email from Moskit contact
 * Handles multiple possible formats from the API
 */
function extractEmail(contact) {
  if (!contact) return null;

  // Format 1: contact.email (string direta)
  if (typeof contact.email === 'string' && contact.email.includes('@')) {
    return contact.email;
  }

  // Format 2: contact.emails (string direta)
  if (typeof contact.emails === 'string' && contact.emails.includes('@')) {
    return contact.emails;
  }

  // Format 3: contact.emails[0].address (array de objetos com address)
  if (Array.isArray(contact.emails) && contact.emails.length > 0) {
    const firstEmail = contact.emails[0];
    if (typeof firstEmail === 'string' && firstEmail.includes('@')) {
      return firstEmail;
    }
    if (firstEmail && firstEmail.address) {
      return firstEmail.address;
    }
    if (firstEmail && firstEmail.email) {
      return firstEmail.email;
    }
  }

  return null;
}

/**
 * Load clients from JSON file
 */
function loadClientsFromJSON() {
  try {
    const jsonPath = path.join(__dirname, 'active-clients.json');
    const data = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
    console.log(`[CLIENT-SYNC] Loaded ${data.clients.length} clients from JSON`);
    return data.clients;
  } catch (error) {
    console.error('[CLIENT-SYNC] Error loading clients JSON:', error.message);
    return [];
  }
}

/**
 * Search Moskit contact by phone and get email
 */
async function getMoskitContactByPhone(phone) {
  if (!phone) return null;

  try {
    const cleanPhone = phone.replace(/\D/g, '');

    const response = await fetch(
      `${FOLLOWUP_CONFIG.moskitBaseUrl}/contacts?search=${cleanPhone}`,
      {
        method: 'GET',
        headers: {
          'apikey': FOLLOWUP_CONFIG.moskitApiKey,
          'Content-Type': 'application/json'
        }
      }
    );

    if (!response.ok) {
      console.error(`[CLIENT-SYNC] Moskit API error: ${response.status}`);
      return null;
    }

    const results = await response.json();

    if (results && results.length > 0) {
      const contact = results[0];
      return {
        moskitId: contact.id,
        name: contact.name,
        email: extractEmail(contact),
        phone: contact.phones && contact.phones.length > 0 ? contact.phones[0].number : null
      };
    }

    return null;
  } catch (error) {
    console.error(`[CLIENT-SYNC] Error fetching Moskit contact:`, error.message);
    return null;
  }
}

/**
 * Search Moskit contact by name
 */
async function getMoskitContactByName(name) {
  if (!name) return null;

  try {
    const response = await fetch(
      `${FOLLOWUP_CONFIG.moskitBaseUrl}/contacts?search=${encodeURIComponent(name)}`,
      {
        method: 'GET',
        headers: {
          'apikey': FOLLOWUP_CONFIG.moskitApiKey,
          'Content-Type': 'application/json'
        }
      }
    );

    if (!response.ok) {
      console.error(`[CLIENT-SYNC] Moskit API error: ${response.status}`);
      return null;
    }

    const results = await response.json();

    if (results && results.length > 0) {
      // Try to find exact name match
      const exactMatch = results.find(c =>
        c.name.toLowerCase() === name.toLowerCase()
      );
      const contact = exactMatch || results[0];

      return {
        moskitId: contact.id,
        name: contact.name,
        email: extractEmail(contact),
        phone: contact.phones && contact.phones.length > 0 ? contact.phones[0].number : null
      };
    }

    return null;
  } catch (error) {
    console.error(`[CLIENT-SYNC] Error fetching Moskit contact by name:`, error.message);
    return null;
  }
}

/**
 * Enrich a single client with Moskit data
 */
async function enrichClient(client) {
  let moskitData = null;

  // First try by phone
  if (client.phone) {
    moskitData = await getMoskitContactByPhone(client.phone);
  }

  // If no result and has name, try by name
  if (!moskitData && client.name) {
    moskitData = await getMoskitContactByName(client.name);
  }

  // v11.0: Preserve email from JSON if Moskit doesn't return one
  return {
    ...client,
    moskitId: moskitData?.moskitId || null,
    email: moskitData?.email || client.email || null,
    enrichedAt: new Date().toISOString()
  };
}

/**
 * Sync all clients - load from JSON and enrich with Moskit data
 * @param {boolean} forceRefresh - If true, re-fetch from Moskit even if cached
 */
async function syncAllClients(forceRefresh = false) {
  console.log('[CLIENT-SYNC] Starting client sync...');

  // Load base clients from JSON
  const baseClients = loadClientsFromJSON();

  if (baseClients.length === 0) {
    console.error('[CLIENT-SYNC] No clients found in JSON');
    return { success: false, error: 'No clients in JSON', clients: [] };
  }

  // Enrich each client with Moskit data
  const enrichedResults = [];
  let enrichedCount = 0;
  let emailsFound = 0;

  for (let i = 0; i < baseClients.length; i++) {
    const client = baseClients[i];

    // Rate limit - wait between API calls
    if (i > 0) {
      await new Promise(r => setTimeout(r, 300)); // 300ms delay
    }

    try {
      const enriched = await enrichClient(client);
      enrichedResults.push(enriched);
      enrichedCount++;

      if (enriched.email) {
        emailsFound++;
      }

      // Log progress every 10 clients
      if ((i + 1) % 10 === 0) {
        console.log(`[CLIENT-SYNC] Progress: ${i + 1}/${baseClients.length} clients processed`);
      }
    } catch (error) {
      console.error(`[CLIENT-SYNC] Error enriching ${client.name}:`, error.message);
      enrichedResults.push({ ...client, email: null, moskitId: null, error: error.message });
    }
  }

  // Update cache
  enrichedClients = enrichedResults;

  console.log(`[CLIENT-SYNC] Sync complete:`);
  console.log(`[CLIENT-SYNC] - Total clients: ${enrichedResults.length}`);
  console.log(`[CLIENT-SYNC] - Emails found: ${emailsFound}`);
  console.log(`[CLIENT-SYNC] - Without email: ${enrichedResults.length - emailsFound}`);

  return {
    success: true,
    totalClients: enrichedResults.length,
    emailsFound: emailsFound,
    withoutEmail: enrichedResults.length - emailsFound,
    clients: enrichedResults
  };
}

/**
 * Get all active clients (from cache or fresh sync)
 */
async function getActiveClients(refresh = false) {
  if (refresh || enrichedClients.length === 0) {
    await syncAllClients();
  }
  return enrichedClients;
}

/**
 * Get clients that have emails
 */
async function getClientsWithEmail(refresh = false) {
  const clients = await getActiveClients(refresh);
  return clients.filter(c => c.email && c.email.length > 0);
}

/**
 * Get client by phone number
 */
function getClientByPhone(phone) {
  const cleanPhone = phone.replace(/\D/g, '');
  return enrichedClients.find(c => {
    if (!c.phone) return false;
    return c.phone.replace(/\D/g, '').includes(cleanPhone);
  });
}

/**
 * Get client by name
 */
function getClientByName(name) {
  const searchName = name.toLowerCase();
  return enrichedClients.find(c =>
    c.name && c.name.toLowerCase().includes(searchName)
  );
}

/**
 * Get statistics about synced clients
 */
function getStats() {
  const total = enrichedClients.length;
  const withEmail = enrichedClients.filter(c => c.email).length;
  const withPhone = enrichedClients.filter(c => c.phone).length;
  const withMoskitId = enrichedClients.filter(c => c.moskitId).length;

  return {
    total,
    withEmail,
    withPhone,
    withMoskitId,
    withoutEmail: total - withEmail,
    percentWithEmail: total > 0 ? Math.round((withEmail / total) * 100) : 0
  };
}

module.exports = {
  loadClientsFromJSON,
  getMoskitContactByPhone,
  getMoskitContactByName,
  enrichClient,
  syncAllClients,
  getActiveClients,
  getClientsWithEmail,
  getClientByPhone,
  getClientByName,
  getStats
};
