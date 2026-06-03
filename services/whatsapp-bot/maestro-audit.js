/**
 * MAESTRO Audit - Log de auditoria de todas as acoes
 */

const fs = require("fs");
const path = require("path");

const AUDIT_FILE = "/opt/maestro/logs/audit.jsonl";
const LOG_DIR = path.dirname(AUDIT_FILE);

class MaestroAudit {
  constructor() {
    // Criar diretorio se nao existir
    if (!fs.existsSync(LOG_DIR)) {
      fs.mkdirSync(LOG_DIR, { recursive: true });
    }
    console.log("[MAESTRO-AUDIT] Auditoria ativa:", AUDIT_FILE);
  }

  log(entry) {
    try {
      var record = {
        timestamp: new Date().toISOString(),
        type: entry.type || "unknown",
        input: entry.input || "",
        ai_provider: entry.ai_provider || "gemini",
        approved: entry.approved !== undefined ? entry.approved : null,
        commands: entry.commands || null,
        duration_ms: entry.duration_ms || null,
        success: entry.success !== undefined ? entry.success : null,
      };

      fs.appendFileSync(AUDIT_FILE, JSON.stringify(record) + "\n");
    } catch (e) {
      console.error("[MAESTRO-AUDIT] Erro ao gravar:", e.message);
    }
  }

  getRecent(count) {
    count = count || 20;
    try {
      if (!fs.existsSync(AUDIT_FILE)) return [];

      var content = fs.readFileSync(AUDIT_FILE, 'utf8');
      var lines = content.trim().split('\n').filter(function(l) { return l.length > 0; });
      var recent = lines.slice(-count);

      return recent.map(function(line) {
        try { return JSON.parse(line); } catch (e) { return null; }
      }).filter(function(r) { return r !== null; });
    } catch (e) {
      return [];
    }
  }
}

module.exports = new MaestroAudit();
