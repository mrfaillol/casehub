/**
 * PostgreSQL Sync Module
 * Syncs WhatsApp messages to CaseHub unified_messages table
 * v1.0 - 2026-02-06
 */

const { Pool } = require('pg');
const appConfig = require('./config');

// PostgreSQL configuration (from .env)
const pgPool = new Pool({
  host: appConfig.postgres.host,
  port: appConfig.postgres.port,
  user: appConfig.postgres.user,
  password: appConfig.postgres.password,
  database: appConfig.postgres.database,
  max: 5,
  idleTimeoutMillis: 30000
});

let pgConnected = false;

// Test connection on startup
pgPool.query('SELECT 1')
  .then(() => {
    pgConnected = true;
    console.log('[PG-SYNC] Conectado ao PostgreSQL (casehub)');
  })
  .catch(err => {
    console.warn('[PG-SYNC] Falha ao conectar PostgreSQL:', err.message);
    console.warn('[PG-SYNC] Sync desabilitado - mensagens so no MySQL');
  });

async function syncMessage(mysqlId, phone, role, content) {
  if (!pgConnected) return;
  
  try {
    const direction = role === 'user' ? 'inbound' : 'outbound';
    const fromId = direction === 'inbound' ? phone : 'CaseHub WhatsApp Bot';
    const toId = direction === 'inbound' ? 'CaseHub WhatsApp Bot' : phone;
    const preview = content ? content.substring(0, 500) : '';
    
    await pgPool.query(
      'INSERT INTO unified_messages (channel, source_table, source_id, direction, from_identifier, to_identifier, preview, status, is_read, message_at, created_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW()) ON CONFLICT (channel, source_table, source_id) DO NOTHING',
      ['whatsapp', 'whatsapp_conversations', mysqlId, direction, fromId, toId, preview, 'delivered', false]
    );
    
  } catch (err) {
    console.error('[PG-SYNC] Erro ao sincronizar:', err.message);
  }
}

async function getLastConversationId(mysqlPool, phone, content) {
  try {
    const [rows] = await mysqlPool.query(
      'SELECT id FROM conversations WHERE phone = ? AND content = ? ORDER BY id DESC LIMIT 1',
      [phone, content]
    );
    return rows[0] ? rows[0].id : null;
  } catch (err) {
    return null;
  }
}

module.exports = {
  syncMessage,
  getLastConversationId,
  pgPool
};
