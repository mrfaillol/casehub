/**
 * Import WhatsApp conversations from exported file
 * Run on VPS: node import-conversations.js
 */

const mysql = require('mysql2/promise');
const fs = require('fs');

// Database config
const dbPassword = process.env.DB_PASSWORD;
if (!dbPassword) throw new Error("DB_PASSWORD environment variable is required");
const dbUser = process.env.DB_USER;
if (!dbUser) throw new Error("DB_USER environment variable is required");
const dbName = process.env.DB_NAME;
if (!dbName) throw new Error("DB_NAME environment variable is required");

const dbConfig = {
  host: process.env.DB_HOST || 'localhost',
  user: dbUser,
  password: dbPassword,
  database: dbName
};

// Parse WhatsApp export format: [HH:MM, DD/MM/YYYY] Sender: Message
function parseConversations(text) {
  const conversations = {};
  const lines = text.split('\n');

  let currentPhone = null;
  let currentMessage = null;

  const messageRegex = /^\[(\d{2}:\d{2}), (\d{2}\/\d{2}\/\d{4})\] (.+?): (.*)$/;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    const match = line.match(messageRegex);

    if (match) {
      // Save previous message if exists
      if (currentMessage && currentPhone) {
        if (!conversations[currentPhone]) {
          conversations[currentPhone] = [];
        }
        conversations[currentPhone].push(currentMessage);
      }

      const [, time, date, sender, content] = match;

      // Parse date: DD/MM/YYYY -> YYYY-MM-DD
      const [day, month, year] = date.split('/');
      const [hours, minutes] = time.split(':');
      const timestamp = `${year}-${month}-${day} ${hours}:${minutes}:00`;

      // Determine if it's from user or bot
      const isBot = sender === '${process.env.ORG_NAME || "CaseHub"}';
      const phone = isBot ? null : sender.replace(/[^\d+]/g, '').replace('+', '');

      if (phone) {
        currentPhone = phone;
      }

      if (currentPhone) {
        currentMessage = {
          phone: currentPhone,
          role: isBot ? 'assistant' : 'user',
          content: content,
          from_bot: isBot ? 1 : 0,
          created_at: timestamp
        };
      }
    } else if (currentMessage && line) {
      // Continuation of previous message (multi-line)
      currentMessage.content += '\n' + line;
    }
  }

  // Save last message
  if (currentMessage && currentPhone) {
    if (!conversations[currentPhone]) {
      conversations[currentPhone] = [];
    }
    conversations[currentPhone].push(currentMessage);
  }

  return conversations;
}

// Clean phone number to standard format
function cleanPhone(phone) {
  // Remove all non-digits except leading +
  let cleaned = phone.replace(/[^\d]/g, '');

  // Brazilian numbers: ensure 55 prefix
  if (cleaned.length === 11 && cleaned.startsWith('9')) {
    cleaned = '55' + cleaned;
  } else if (cleaned.length === 10) {
    cleaned = '55' + cleaned;
  }

  return cleaned;
}

async function importConversations() {
  console.log('[IMPORT] Starting conversation import...');

  // Read the conversations file
  const filePath = process.argv[2] || '/tmp/whatsapp-conversas.txt';

  if (!fs.existsSync(filePath)) {
    console.error('[ERROR] File not found:', filePath);
    process.exit(1);
  }

  const text = fs.readFileSync(filePath, 'utf8');
  console.log('[IMPORT] Read file:', filePath);

  // Parse conversations
  const conversations = parseConversations(text);
  const phones = Object.keys(conversations);
  console.log('[IMPORT] Found', phones.length, 'unique contacts');

  // Connect to database
  const db = await mysql.createConnection(dbConfig);
  console.log('[IMPORT] Connected to database');

  let totalMessages = 0;
  let newLeads = 0;

  for (const phone of phones) {
    const cleanedPhone = cleanPhone(phone);
    const messages = conversations[phone];

    console.log(`[IMPORT] Processing ${cleanedPhone} - ${messages.length} messages`);

    // Check/create lead
    const [existingLeads] = await db.execute(
      'SELECT id FROM leads WHERE phone = ?',
      [cleanedPhone]
    );

    if (existingLeads.length === 0) {
      // Create new lead
      await db.execute(
        `INSERT INTO leads (phone, language, lead_status, conversation_state, created_at, updated_at)
         VALUES (?, 'pt', 'cold', 'initial_contact', NOW(), NOW())`,
        [cleanedPhone]
      );
      newLeads++;
      console.log(`  [NEW LEAD] Created lead for ${cleanedPhone}`);
    }

    // Insert messages (skip if already exists)
    for (const msg of messages) {
      // Check if message already exists (by phone + content + timestamp)
      const [existing] = await db.execute(
        `SELECT id FROM conversations
         WHERE phone = ? AND content = ? AND created_at = ?`,
        [cleanedPhone, msg.content.substring(0, 500), msg.created_at]
      );

      if (existing.length === 0) {
        await db.execute(
          `INSERT INTO conversations (phone, role, content, created_at, from_bot)
           VALUES (?, ?, ?, ?, ?)`,
          [cleanedPhone, msg.role, msg.content, msg.created_at, msg.from_bot]
        );
        totalMessages++;
      }
    }
  }

  console.log('\n[IMPORT] ===== SUMMARY =====');
  console.log(`[IMPORT] Contacts processed: ${phones.length}`);
  console.log(`[IMPORT] New leads created: ${newLeads}`);
  console.log(`[IMPORT] Messages imported: ${totalMessages}`);

  await db.end();
  console.log('[IMPORT] Done!');
}

importConversations().catch(err => {
  console.error('[ERROR]', err);
  process.exit(1);
});
