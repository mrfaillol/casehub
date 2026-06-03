/**
 * Simple SQL Migration Runner for WhatsApp Bot
 *
 * Usage:
 *   node migrate.js           - Run pending migrations
 *   node migrate.js --status  - Show migration status
 *   node migrate.js --force N - Force re-run migration N
 *
 * Migrations are numbered SQL files in ./migrations/
 * Format: NNN_description.sql (e.g., 001_baseline.sql)
 * Applied migrations tracked in _migrations table.
 */
require('dotenv').config();
const fs = require('fs');
const path = require('path');
const mysql = require('mysql2/promise');

const MIGRATIONS_DIR = path.join(__dirname, 'migrations');

async function getConnection() {
  return mysql.createConnection({
    host: process.env.DB_HOST || 'localhost',
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    database: process.env.DB_NAME,
    multipleStatements: true
  });
}

async function ensureMigrationsTable(conn) {
  await conn.execute(`
    CREATE TABLE IF NOT EXISTS _migrations (
      id INT AUTO_INCREMENT PRIMARY KEY,
      name VARCHAR(255) NOT NULL UNIQUE,
      applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
  `);
}

async function getAppliedMigrations(conn) {
  const [rows] = await conn.execute('SELECT name, applied_at FROM _migrations ORDER BY name');
  return new Map(rows.map(r => [r.name, r.applied_at]));
}

function getMigrationFiles() {
  return fs.readdirSync(MIGRATIONS_DIR)
    .filter(f => f.match(/^\d{3}_.*\.sql$/))
    .sort();
}

async function runMigration(conn, filename) {
  const filepath = path.join(MIGRATIONS_DIR, filename);
  const sql = fs.readFileSync(filepath, 'utf8');

  console.log(`  Running: ${filename}...`);

  // Split on semicolons, filter empty, execute each statement
  const statements = sql
    .split(';')
    .map(s => s.trim())
    .filter(s => s.length > 0 && !s.startsWith('--'));

  for (const stmt of statements) {
    try {
      await conn.execute(stmt);
    } catch (err) {
      // Skip "already exists" errors for idempotent migrations
      if (err.code === 'ER_DUP_FIELDNAME' || err.code === 'ER_DUP_KEYNAME') {
        console.log(`    (skipped: ${err.message.substring(0, 60)})`);
      } else {
        throw err;
      }
    }
  }

  await conn.execute('INSERT INTO _migrations (name) VALUES (?)', [filename]);
  console.log(`  Done: ${filename}`);
}

async function showStatus(conn) {
  const applied = await getAppliedMigrations(conn);
  const files = getMigrationFiles();

  console.log('\nMigration Status:');
  console.log('='.repeat(60));

  for (const file of files) {
    const appliedAt = applied.get(file);
    const status = appliedAt ? `Applied ${appliedAt.toISOString().split('T')[0]}` : 'PENDING';
    const icon = appliedAt ? '[OK]' : '[  ]';
    console.log(`  ${icon} ${file} - ${status}`);
  }

  const pending = files.filter(f => !applied.has(f));
  console.log(`\n  Total: ${files.length} | Applied: ${files.length - pending.length} | Pending: ${pending.length}`);
}

async function main() {
  const args = process.argv.slice(2);
  const isStatus = args.includes('--status');
  const forceIndex = args.indexOf('--force');
  const forceNum = forceIndex >= 0 ? args[forceIndex + 1] : null;

  let conn;
  try {
    conn = await getConnection();
    await ensureMigrationsTable(conn);

    if (isStatus) {
      await showStatus(conn);
      return;
    }

    const applied = await getAppliedMigrations(conn);
    const files = getMigrationFiles();

    if (forceNum) {
      const target = files.find(f => f.startsWith(forceNum));
      if (!target) {
        console.error(`Migration ${forceNum} not found`);
        process.exit(1);
      }
      console.log(`Force re-running: ${target}`);
      await conn.execute('DELETE FROM _migrations WHERE name = ?', [target]);
      await runMigration(conn, target);
      return;
    }

    const pending = files.filter(f => !applied.has(f));

    if (pending.length === 0) {
      console.log('All migrations up to date.');
      return;
    }

    console.log(`Running ${pending.length} pending migration(s):`);
    for (const file of pending) {
      await runMigration(conn, file);
    }
    console.log('\nAll migrations applied successfully.');

  } catch (err) {
    console.error('Migration error:', err.message);
    process.exit(1);
  } finally {
    if (conn) await conn.end();
  }
}

main();
