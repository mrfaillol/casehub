/**
 * MAESTRO AI v4.0 - Agente Conversacional Full-Access
 * Tri-hibrido: Gemini (simples) + Claude (complexo) + Perplexity (pesquisa)
 */

const { GoogleGenerativeAI } = require("@google/generative-ai");
const { exec } = require("child_process");
const fs = require("fs");
const path = require("path");

// Configuracao
const GEMINI_API_KEY = process.env.GEMINI_API_KEY;

// Carregar modulos opcionais
let maestroClaude = null;
let maestroPerplexity = null;
let maestroAudit = null;

try { maestroClaude = require("./maestro-claude"); } catch (e) {
  console.log("[MAESTRO-AI] Claude module not available");
}
try { maestroPerplexity = require("./maestro-perplexity"); } catch (e) {
  console.log("[MAESTRO-AI] Perplexity module not available");
}
try { maestroAudit = require("./maestro-audit"); } catch (e) {
  console.log("[MAESTRO-AI] Audit module not available");
}

// ============================================================
// SEGURANCA: Comandos bloqueados (verificados PRIMEIRO)
// ============================================================
const BLOCKED_PATTERNS = [
  /rm\s+-rf/i,
  /rm\s+--no-preserve-root/i,
  /rm\s+-r\s+\//i,
  /dd\s+if=/i,
  /mkfs/i,
  /:\(\)\{\s*:\|:\&\s*\};:/,
  />(\/dev\/sda|\/dev\/nvme)/i,
  /chmod\s+-R\s+777\s+\//i,
  /wget.*\|.*sh/i,
  /curl.*\|.*bash/i,
  /eval\s*\(/i,
  /shutdown/i,
  /reboot(?!\s+whatsapp)/i,
  /init\s+0/i,
  /halt/i,
  /DROP\s+(TABLE|DATABASE)/i,
  /TRUNCATE/i,
  /DELETE\s+FROM.*WHERE\s+1/i,
];

// ============================================================
// SEGURANCA: Comandos permitidos (whitelist expandida v4)
// ============================================================
const ALLOWED_COMMANDS = [
  /^pm2\s+/i,
  /^systemctl\s+(status|restart|start|stop|is-active|list-units)/i,
  /^ls($|\s)/i,
  /^cat\s/i,
  /^head\s/i,
  /^tail\s/i,
  /^find\s/i,
  /^tree($|\s)/i,
  /^wc\s/i,
  /^du\s/i,
  /^stat\s/i,
  /^file\s/i,
  /^md5sum\s/i,
  /^diff\s/i,
  /^grep\s/i,
  /^awk\s/i,
  /^sort\s/i,
  /^df($|\s)/i,
  /^free($|\s)/i,
  /^ss\s/i,
  /^uptime($|\s)/i,
  /^top\s/i,
  /^ps\s/i,
  /^lsof\s/i,
  /^id$/i,
  /^whoami$/i,
  /^hostname($|\s)/i,
  /^uname($|\s)/i,
  /^date$/i,
  /^nginx\s/i,
  /^psql\s/i,
  /^mysql\s/i,
  /^git\s+(status|log|diff|show|branch|remote|stash)/i,
  /^curl\s/i,
  /^ping\s/i,
  /^dig\s/i,
  /^nslookup\s/i,
  /^cp\s/i,
  /^mv\s/i,
  /^mkdir\s/i,
  /^touch\s/i,
  /^sed\s/i,
  /^tee\s/i,
  /^echo\s/i,
  /^node\s/i,
  /^python3?\s/i,
  /^pip3?\s/i,
  /^npm\s/i,
];

// ============================================================
// NIVEIS DE APROVACAO
// ============================================================
const APPROVAL_LEVELS = { AUTO: 1, NOTIFY: 2, APPROVE: 3, BLOCKED: 4 };

function getApprovalLevel(command) {
  for (const pattern of BLOCKED_PATTERNS) {
    if (pattern.test(command)) return APPROVAL_LEVELS.BLOCKED;
  }

  const readOnlyPatterns = [
    /^ls($|\s)/i, /^cat\s/i, /^head\s/i, /^tail\s/i, /^find\s/i, /^tree($|\s)/i,
    /^wc\s/i, /^du\s/i, /^stat\s/i, /^file\s/i, /^grep\s/i, /^diff\s/i,
    /^df($|\s)/i, /^free($|\s)/i, /^ss\s/i, /^uptime/i, /^ps\s/i,
    /^pm2\s+(list|ls|status|logs|show|jlist|monit|prettylist)/i,
    /^systemctl\s+(status|is-active)/i,
    /^git\s+(status|log|diff|show|branch|remote)/i,
    /^curl\s/i, /^ping\s/i, /^dig\s/i, /^nslookup\s/i,
    /^id$/i, /^whoami$/i, /^hostname/i, /^uname/i, /^date$/i,
    /^sort\s/i, /^awk\s/i, /^md5sum\s/i,
  ];
  if (readOnlyPatterns.some(p => p.test(command))) return APPROVAL_LEVELS.AUTO;

  const notifyPatterns = [
    /^pm2\s+(restart|reload|save|startup)/i,
    /^systemctl\s+(restart|start|stop)/i,
    /^nginx\s+-s\s+reload/i,
  ];
  if (notifyPatterns.some(p => p.test(command))) return APPROVAL_LEVELS.NOTIFY;

  return APPROVAL_LEVELS.APPROVE;
}

// ============================================================
// CLASSIFICADOR DE PROVEDOR
// ============================================================
function classifyProvider(message) {
  // SIMPLE primeiro (prioridade alta - comandos de VPS)
  const simplePatterns = [
    /^[0-9]$/,
    /status|como est[aá]/i,
    /restart|reinici/i,
    /logs?\b/i,
    /disco|ram|memoria|cpu/i,
    /mostr[ae]|lista|ver\s/i,
    /arvore|tree|diretorio/i,
    /arquivo|pasta|folder/i,
    /porta|port|servico|pm2/i,
    /var\/www|immigrant\.law/i,
  ];
  if (simplePatterns.some(p => p.test(message))) return 'simple';

  // RESEARCH (pesquisa web)
  const researchPatterns = [
    /pesquis|busca|procur/i,
    /\buscis\b|immigration\b|visto\b|visa\b/i,
    /processing time|tempo de process/i,
    /notic[ia]|news|atualiz/i,
    /documentac|regulament|\blei\b/i,
    /como funciona.*uscis|o que [eé].*uscis/i,
  ];
  if (researchPatterns.some(p => p.test(message))) return 'research';

  // COMPLEX (debug, code, planejamento)
  const complexPatterns = [
    /debug|investig|analise|por qu[eê]/i,
    /implement|cri[ae]|desenvolv/i,
    /refactor|otimiz|melhor/i,
    /plano|planeja|estrateg/i,
    /codigo|code|script|review/i,
    /erro|bug|fix|corrij/i,
    /configur|deploy|migra/i,
    /explic|entend|arquitetura/i,
  ];
  if (complexPatterns.some(p => p.test(message))) return 'complex';

  return 'simple';
}

// ============================================================
// SYSTEM PROMPT
// ============================================================
const SYSTEM_PROMPT = [
  "Voce e o MAESTRO v4.0, assistente inteligente de administracao de VPS e do projeto CaseHub.",
  "Conversa em portugues brasileiro, claro, objetivo e conciso.",
  "Pode ler arquivos, executar comandos, investigar problemas e fazer alteracoes.",
  "",
  "SISTEMA:",
  `- VPS: ${process.env.VPS_IP || "localhost"} (${process.env.ORG_NAME || "CaseHub"})`,
  "- PM2: whatsapp-bot (3001), casehub (8001), ilc-tools (8000), vps-monitor (8010), maestro",
  "- Bancos: MariaDB (3306), PostgreSQL (5432), Redis (6379)",
  "- Web: Nginx (80/443)",
  "- Codigo: ${process.env.APP_BASE_PATH || "/opt/casehub"}/{casehub,ilc-tools,whatsapp-bot}",
  "",
  "COMANDOS: pm2, systemctl, ls, cat, head, tail, find, tree, grep, diff, df, free, ss,",
  "uptime, ps, git, curl, ping, cp, mv, mkdir, sed, echo, node, python, pip, npm.",
  "BLOQUEADOS: rm -rf, dd, mkfs, shutdown, reboot, DROP TABLE, TRUNCATE.",
  "",
  "NIVEIS DE APROVACAO:",
  "- Nivel 1 (AUTO): Leitura - executa automaticamente",
  "- Nivel 2 (NOTIFICA): Restart/reload - executa e avisa",
  "- Nivel 3 (APROVACAO): Edicao, deploy - mostra plano e pede autorizacao",
  "- Nivel 4 (BLOQUEADO): Destrutivos - recusa",
  "",
  "FORMATO DE RESPOSTA - SEMPRE JSON VALIDO:",
  '{"type":"action|info|clarify|error|plan",',
  '"message":"mensagem para WhatsApp",',
  '"plan":{"summary":"...","steps":["..."],"commands":["..."],"impact":"...","risk":"low|medium|high"},',
  '"needs_auth":true/false}',
  "",
  "REGRAS:",
  "1. Leitura: needs_auth=false, execute e mostre",
  "2. Acoes (restart, edit): needs_auth=true, mostre plano",
  "3. Se nao entender: type=clarify",
  "4. NUNCA comandos destrutivos",
  "5. Max 5 comandos por plano",
  "6. Use *bold* para WhatsApp",
  "7. Para investigar, execute VARIOS comandos de leitura antes de responder",
  "8. Quando faltar info, PERGUNTE ao admin",
].join("\n");

// ============================================================
// MAESTRO AI CLASS
// ============================================================
class MaestroAI {
  constructor() {
    this.genAI = null;
    this.model = null;
    this.pendingPlans = new Map();
    this.conversationHistory = new Map();
    this.initialized = false;
  }

  async initialize() {
    if (!GEMINI_API_KEY) {
      console.log("[MAESTRO-AI] GEMINI_API_KEY nao configurada");
      return false;
    }

    try {
      this.genAI = new GoogleGenerativeAI(GEMINI_API_KEY);
      this.model = this.genAI.getGenerativeModel({
        model: "gemini-2.0-flash",
        generationConfig: { temperature: 0.3, maxOutputTokens: 4096 }
      });
      this.initialized = true;
      console.log("[MAESTRO-AI] v4.0 Inicializado - Gemini 2.0 Flash");
      if (maestroClaude) console.log("[MAESTRO-AI] Claude: disponivel");
      if (maestroPerplexity) console.log("[MAESTRO-AI] Perplexity: disponivel");
      return true;
    } catch (e) {
      console.log("[MAESTRO-AI] Erro ao inicializar:", e.message);
      return false;
    }
  }

  isCommandSafe(command) {
    for (const pattern of BLOCKED_PATTERNS) {
      if (pattern.test(command)) {
        console.log("[MAESTRO-AI] Comando BLOQUEADO:", command);
        return false;
      }
    }

    for (const pattern of ALLOWED_COMMANDS) {
      if (pattern.test(command.trim())) return true;
    }

    // Pipes: cada parte deve ser segura
    if (command.includes('|')) {
      const parts = command.split('|').map(p => p.trim());
      return parts.every(part => {
        for (const bp of BLOCKED_PATTERNS) { if (bp.test(part)) return false; }
        for (const ap of ALLOWED_COMMANDS) { if (ap.test(part)) return true; }
        return false;
      });
    }

    // &&: cada parte deve ser segura
    if (command.includes('&&')) {
      const parts = command.split('&&').map(p => p.trim());
      return parts.every(part => {
        for (const bp of BLOCKED_PATTERNS) { if (bp.test(part)) return false; }
        for (const ap of ALLOWED_COMMANDS) { if (ap.test(part)) return true; }
        return false;
      });
    }

    console.log("[MAESTRO-AI] Comando nao permitido:", command);
    return false;
  }

  async executeCommand(command) {
    return new Promise((resolve) => {
      if (!this.isCommandSafe(command)) {
        resolve({ success: false, output: "Comando nao permitido por razoes de seguranca" });
        return;
      }

      exec(command, { timeout: 60000, maxBuffer: 1024 * 1024 }, (error, stdout, stderr) => {
        if (error) {
          resolve({ success: false, output: stderr || error.message });
        } else {
          resolve({ success: true, output: stdout || "Executado com sucesso" });
        }
      });
    });
  }

  // File tools
  readFile(filePath, maxLines) {
    maxLines = maxLines || 100;
    try {
      var resolved = path.resolve(filePath);
      var content = fs.readFileSync(resolved, 'utf8');
      var lines = content.split('\n');
      if (lines.length > maxLines) {
        return { success: true, content: lines.slice(0, maxLines).join('\n'), truncated: true, totalLines: lines.length };
      }
      return { success: true, content: content, truncated: false, totalLines: lines.length };
    } catch (e) {
      return { success: false, error: e.message };
    }
  }

  writeFile(filePath, content) {
    try {
      var resolved = path.resolve(filePath);
      if (fs.existsSync(resolved)) {
        var backupPath = resolved + '.bak.' + Date.now();
        fs.copyFileSync(resolved, backupPath);
        console.log("[MAESTRO-AI] Backup criado:", backupPath);
      }
      fs.writeFileSync(resolved, content, 'utf8');
      return { success: true };
    } catch (e) {
      return { success: false, error: e.message };
    }
  }

  async getSystemContext() {
    var context = "ESTADO ATUAL DO SISTEMA:\n";

    // PM2 status
    try {
      var pm2Result = await this.executeCommand("pm2 jlist");
      if (pm2Result.success) {
        var procs = JSON.parse(pm2Result.output);
        context += "\nServicos PM2:\n";
        for (var i = 0; i < procs.length; i++) {
          var p = procs[i];
          var mem = Math.round((p.monit && p.monit.memory || 0) / 1024 / 1024);
          var status = (p.pm2_env && p.pm2_env.status) || "unknown";
          var restarts = (p.pm2_env && p.pm2_env.restart_time) || 0;
          var uptime = (p.pm2_env && p.pm2_env.pm_uptime)
            ? Math.round((Date.now() - p.pm2_env.pm_uptime) / 1000 / 60) + "min"
            : "?";
          context += "- " + p.name + ": " + status + " (" + mem + "MB, " + restarts + " restarts, up " + uptime + ")\n";
        }
      }
    } catch (e) {
      context += "PM2: erro\n";
    }

    // Disk and RAM
    try {
      var diskResult = await this.executeCommand("df -h / | tail -1");
      if (diskResult.success) context += "Disco: " + diskResult.output.trim() + "\n";
    } catch (e) {}

    try {
      var ramResult = await this.executeCommand("free -h | grep Mem");
      if (ramResult.success) context += "RAM: " + ramResult.output.trim() + "\n";
    } catch (e) {}

    // CLAUDE.md
    var claudePaths = ['${process.env.APP_BASE_PATH || "/opt/casehub"}/CLAUDE.md', '${process.env.APP_BASE_PATH || "/opt/casehub"}/casehub/CLAUDE.md'];
    for (var j = 0; j < claudePaths.length; j++) {
      try {
        if (fs.existsSync(claudePaths[j])) {
          var claudeMd = fs.readFileSync(claudePaths[j], 'utf8');
          context += "\n\nCONTEXTO DO PROJETO (CLAUDE.md):\n" + claudeMd.substring(0, 4000);
          break;
        }
      } catch (e) {}
    }

    return context;
  }

  async processMessage(message, phoneNumber) {
    if (!this.initialized) await this.initialize();
    if (!this.initialized) {
      return { type: "error", message: "Maestro AI nao configurado. Verifique GEMINI_API_KEY." };
    }

    var startTime = Date.now();

    try {
      var lowerMsg = message.toLowerCase().trim();

      // Resposta de autorizacao
      if (this.pendingPlans.has(phoneNumber)) {
        if (["sim", "s", "yes", "autorizo", "pode", "vai", "manda"].indexOf(lowerMsg) >= 0) {
          var execResult = await this.executePendingPlan(phoneNumber);
          if (maestroAudit) maestroAudit.log({ type: "plan_executed", input: message, approved: true, duration_ms: Date.now() - startTime });
          return execResult;
        } else if (["nao", "n", "no", "cancela", "para"].indexOf(lowerMsg) >= 0) {
          this.pendingPlans.delete(phoneNumber);
          if (maestroAudit) maestroAudit.log({ type: "plan_cancelled", input: message });
          return { type: "info", message: "Plano cancelado. Como posso ajudar?" };
        }
      }

      var provider = classifyProvider(message);
      console.log("[MAESTRO-AI] Provider: " + provider + " | Msg: " + message.substring(0, 50));

      // PERPLEXITY
      if (provider === 'research' && maestroPerplexity) {
        try {
          var searchResult = await maestroPerplexity.search(message);
          if (maestroAudit) maestroAudit.log({ type: "research", input: message, ai_provider: "perplexity", duration_ms: Date.now() - startTime });
          return { type: "info", message: searchResult.message || JSON.stringify(searchResult), provider_used: "perplexity" };
        } catch (e) {
          console.log("[MAESTRO-AI] Perplexity erro, fallback Gemini:", e.message);
        }
      }

      // CLAUDE
      if (provider === 'complex' && maestroClaude) {
        try {
          var systemContext = await this.getSystemContext();
          var history = this.conversationHistory.get(phoneNumber) || [];
          var claudeResult = await maestroClaude.processComplexTask(message, systemContext, history);

          history.push({ role: "user", content: message });
          history.push({ role: "assistant", content: claudeResult.message || "" });
          if (history.length > 20) history = history.slice(-20);
          this.conversationHistory.set(phoneNumber, history);

          if (maestroAudit) maestroAudit.log({ type: "complex_task", input: message, ai_provider: "claude", duration_ms: Date.now() - startTime });

          if (claudeResult.needs_auth && claudeResult.plan) {
            this.pendingPlans.set(phoneNumber, { plan: claudeResult.plan, timestamp: Date.now() });
          }
          return claudeResult;
        } catch (e) {
          console.log("[MAESTRO-AI] Claude erro, fallback Gemini:", e.message);
        }
      }

      // GEMINI (default + fallback)
      var sysCtx = await this.getSystemContext();
      var hist = this.conversationHistory.get(phoneNumber) || [];
      hist.push({ role: "user", content: message });
      if (hist.length > 10) hist = hist.slice(-10);

      var histStr = "";
      for (var k = 0; k < hist.length; k++) {
        histStr += hist[k].role + ": " + hist[k].content + "\n";
      }

      var prompt = SYSTEM_PROMPT + "\n\n" + sysCtx + "\n\nHISTORICO:\n" + histStr + "\n\nMENSAGEM DO ADMIN: " + message + "\n\nResponda em JSON valido:";

      var result = await this.model.generateContent(prompt);
      var responseText = result.response.text();

      var response;
      try {
        var jsonMatch = responseText.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          response = JSON.parse(jsonMatch[0]);
        } else {
          throw new Error("JSON nao encontrado");
        }
      } catch (e) {
        console.log("[MAESTRO-AI] Erro JSON parse:", responseText.substring(0, 200));
        response = {
          type: "info",
          message: responseText.replace(/```json?/g, "").replace(/```/g, "").trim().substring(0, 2000)
        };
      }

      hist.push({ role: "assistant", content: response.message || "" });
      this.conversationHistory.set(phoneNumber, hist);

      if (response.needs_auth && response.plan) {
        this.pendingPlans.set(phoneNumber, { plan: response.plan, timestamp: Date.now() });
      }

      // Auto-exec comandos de leitura
      if (!response.needs_auth && response.plan && response.plan.commands && response.plan.commands.length > 0) {
        var allAuto = response.plan.commands.every(function(cmd) {
          return getApprovalLevel(cmd) === APPROVAL_LEVELS.AUTO;
        });

        if (allAuto) {
          var autoResult = await this.executeInfoCommands(response);
          if (maestroAudit) maestroAudit.log({ type: "auto_exec", input: message, ai_provider: "gemini", commands: response.plan.commands, duration_ms: Date.now() - startTime });
          return autoResult;
        }
      }

      if (maestroAudit) maestroAudit.log({ type: "info", input: message, ai_provider: "gemini", duration_ms: Date.now() - startTime });
      return response;

    } catch (e) {
      console.error("[MAESTRO-AI] Erro:", e);
      return { type: "error", message: "Erro ao processar: " + e.message };
    }
  }

  async executeInfoCommands(response) {
    var results = [];
    var commands = response.plan.commands.slice(0, 5);

    for (var i = 0; i < commands.length; i++) {
      var result = await this.executeCommand(commands[i]);
      results.push({ command: commands[i], success: result.success, output: result.output.substring(0, 500) });
    }

    var outputMsg = response.message + "\n\n";
    for (var j = 0; j < results.length; j++) {
      var r = results[j];
      var icon = r.success ? "[OK]" : "[X]";
      outputMsg += icon + " `" + r.command + "`\n```\n" + r.output + "\n```\n\n";
    }

    return { type: "info", message: outputMsg.substring(0, 4000), executed: results };
  }

  async executePendingPlan(phoneNumber) {
    var pending = this.pendingPlans.get(phoneNumber);
    if (!pending) return { type: "error", message: "Nao ha plano pendente." };

    if (Date.now() - pending.timestamp > 10 * 60 * 1000) {
      this.pendingPlans.delete(phoneNumber);
      return { type: "error", message: "Plano expirado (>10 min). Faca o pedido novamente." };
    }

    var plan = pending.plan;
    this.pendingPlans.delete(phoneNumber);

    var msg = "*Executando plano...*\n\n";
    var results = [];

    for (var i = 0; i < plan.commands.length && i < 5; i++) {
      var cmd = plan.commands[i];
      var step = (plan.steps && plan.steps[i]) || ("Passo " + (i + 1));

      msg += (i + 1) + ". " + step + "\n";

      var result = await this.executeCommand(cmd);
      results.push({ step: step, command: cmd, success: result.success, output: result.output.substring(0, 300) });

      var icon = result.success ? "[OK]" : "[ERRO]";
      msg += icon + " `" + cmd + "`\n";
      if (result.output && result.output.trim()) {
        msg += "```\n" + result.output.substring(0, 300) + "\n```\n";
      }
      msg += "\n";
    }

    var allSuccess = results.every(function(r) { return r.success; });
    msg += allSuccess ? "\n*Plano executado com sucesso!*" : "\n*Plano executado com alguns erros.*";

    return { type: "result", message: msg.substring(0, 4000), results: results, success: allSuccess };
  }

  formatForWhatsApp(response) {
    if ((response.type === "action" || response.type === "plan") && response.needs_auth) {
      var msg = "*MAESTRO - Plano de Acao*\n\n";
      msg += response.message + "\n\n";

      if (response.plan) {
        if (response.plan.summary) msg += "*Resumo:* " + response.plan.summary + "\n\n";
        msg += "*Passos:*\n";
        if (response.plan.steps) {
          for (var i = 0; i < response.plan.steps.length; i++) {
            msg += (i + 1) + ". " + response.plan.steps[i] + "\n";
          }
        }
        msg += "\n";
        if (response.plan.impact) msg += "*Impacto:* " + response.plan.impact + "\n";
        if (response.plan.risk) {
          var riskLabel = { low: "[BAIXO]", medium: "[MEDIO]", high: "[ALTO]" };
          msg += "*Risco:* " + (riskLabel[response.plan.risk] || response.plan.risk) + "\n";
        }
      }

      msg += "\n---\nAutoriza? Responda *sim* ou *nao*";
      return msg;
    }

    if (response.type === "clarify") {
      var clMsg = "*MAESTRO - Preciso de mais informacao*\n\n";
      clMsg += response.message + "\n\n";
      if (response.options) {
        for (var j = 0; j < response.options.length; j++) {
          clMsg += "[" + (j + 1) + "] " + response.options[j] + "\n";
        }
      }
      return clMsg;
    }

    return response.message;
  }
}

const maestroAI = new MaestroAI();
module.exports = maestroAI;
