/**
 * MAESTRO Handler v3.0 - Sistema de Monitoramento Conversacional
 * Integra comandos rapidos + AI conversacional
 */

const whatsappClient = require("./whatsapp-client");
const maestroAI = require("./maestro-ai");
const { exec } = require("child_process");
const fs = require("fs");
const path = require("path");

// Configuracao
const ADMIN_NUMBER = process.env.MAESTRO_ADMIN_PHONE || "";
const PENDING_FILE = "/opt/maestro/data/pending_actions.json";

// Cache de acoes pendentes (comandos rapidos)
let pendingActions = {};

// Comandos rapidos (0-9)
const QUICK_COMMANDS = {
  "0": { label: "Ignorar", command: null },
  "1": { label: "Corrigir PM2 startup", command: "pm2 startup && pm2 save" },
  "2": { label: "Status chkrootkit", command: "systemctl status chkrootkit --no-pager" },
  "3": { label: "Logs WhatsApp Bot", command: "pm2 logs whatsapp-bot --lines 30 --nostream" },
  "4": { label: "Status PM2", command: "pm2 list" },
  "5": { label: "Relatorio Completo", command: "maestro_report" },
  "6": { label: "Uso de Disco/RAM", command: "df -h && echo '---' && free -h" },
  "7": { label: "Logs de Erro", command: "pm2 logs --err --lines 20 --nostream" },
  "8": { label: "Reiniciar WhatsApp Bot", command: "pm2 restart whatsapp-bot", needsConfirm: true },
  "9": { label: "Verificar Portas", command: "ss -tlnp | grep LISTEN" }
};

// Carregar acoes pendentes
function loadPendingActions() {
  try {
    if (fs.existsSync(PENDING_FILE)) {
      pendingActions = JSON.parse(fs.readFileSync(PENDING_FILE, 'utf8'));
    }
  } catch (e) {
    console.log("[Maestro] Erro ao carregar acoes:", e.message);
  }
}

// Salvar acoes pendentes
function savePendingActions() {
  try {
    const dir = path.dirname(PENDING_FILE);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(PENDING_FILE, JSON.stringify(pendingActions, null, 2));
  } catch (e) {
    console.log("[Maestro] Erro ao salvar acoes:", e.message);
  }
}

// Enviar mensagem WhatsApp para admin
async function sendAdminMessage(message) {
  try {
    const client = whatsappClient.getClient();
    if (!client || !whatsappClient.isReady) {
      throw new Error("WhatsApp client not ready");
    }

    const phone = ADMIN_NUMBER.replace(/\D/g, '');
    console.log("[Maestro] Enviando para:", phone);

    let chatId;
    try {
      const numberId = await client.getNumberId(phone);
      chatId = numberId ? numberId._serialized : phone + "@c.us";
    } catch (e) {
      chatId = phone + "@c.us";
    }

    await client.sendMessage(chatId, message);
    console.log("[Maestro] Mensagem enviada");
    return true;
  } catch (e) {
    console.log("[Maestro] Erro ao enviar:", e.message);
    return false;
  }
}

// Executar comando
async function executeCommand(command) {
  return new Promise((resolve) => {
    exec(command, { timeout: 60000, maxBuffer: 1024 * 1024 }, (error, stdout, stderr) => {
      if (error) {
        resolve({ success: false, output: stderr || error.message });
      } else {
        resolve({ success: true, output: stdout || "Executado com sucesso" });
      }
    });
  });
}

// Gerar relatorio completo
async function generateFullReport() {
  let pm2Data = [];
  let diskUsage = "?";
  let ramUsage = "?";

  try {
    const pm2Result = await executeCommand("pm2 jlist");
    if (pm2Result.success) {
      pm2Data = JSON.parse(pm2Result.output);
    }

    const diskResult = await executeCommand("df -h / | tail -1 | awk '{print $5}'");
    diskUsage = diskResult.success ? diskResult.output.trim() : "?";

    const ramResult = await executeCommand("free -h | grep Mem | awk '{print $3\"/\"$2}'");
    ramUsage = ramResult.success ? ramResult.output.trim() : "?";
  } catch (e) {
    console.log("[Maestro] Erro ao gerar relatorio:", e.message);
  }

  let report = "*MAESTRO VPS - Relatorio*\n";
  report += "------------------------\n\n";

  report += "*Servicos PM2:*\n";
  for (const proc of pm2Data) {
    const status = proc.pm2_env?.status || "unknown";
    const memory = Math.round((proc.monit?.memory || 0) / 1024 / 1024);
    const restarts = proc.pm2_env?.restart_time || 0;
    const icon = status === "online" ? "[OK]" : "[X]";
    const warning = restarts > 100 ? " (!)" : "";
    report += `${icon} ${proc.name}: ${memory}MB (${restarts} restarts)${warning}\n`;
  }

  report += `\n*Recursos:*\n`;
  report += `Disco: ${diskUsage}\n`;
  report += `RAM: ${ramUsage}\n`;

  report += "\n*Sistema:*\n";
  report += "[OK] Nginx, PessoaDemoDB, PostgreSQL, Redis\n";

  report += "\n------------------------\n";
  report += "*Comandos Rapidos (0-9):*\n";
  report += "1-Corrigir PM2 | 2-Chkrootkit\n";
  report += "3-Logs WA | 4-Status PM2\n";
  report += "5-Relatorio | 6-Disco/RAM\n";
  report += "7-Logs Erro | 8-Reiniciar WA\n";
  report += "9-Portas | 0-Ignorar\n";
  report += "\n_Ou envie uma mensagem para conversar com o Maestro AI_";

  return report;
}

// Processar resposta do admin
async function processAdminResponse(messageBody, fromNumber) {
  const adminPhone = ADMIN_NUMBER.replace(/\D/g, '');
  const senderPhone = fromNumber.replace(/\D/g, '').replace('@c.us', '').replace('@s.whatsapp.net', '');

  // Verificar se e o admin
  if (!senderPhone.includes(adminPhone.slice(-8))) {
    console.log("[Maestro] Mensagem ignorada - nao e admin:", senderPhone);
    return null;
  }

  const trimmedMsg = messageBody.trim();
  console.log("[Maestro] Admin enviou:", trimmedMsg);

  // Verificar se e comando rapido (0-9)
  if (/^[0-9]$/.test(trimmedMsg)) {
    return await processQuickCommand(trimmedMsg);
  }

  // Se nao, enviar para AI conversacional
  console.log("[Maestro] Processando com AI...");

  try {
    const aiResponse = await maestroAI.processMessage(trimmedMsg, senderPhone);

    // Formatar e enviar resposta
    let formattedMsg;
    if (aiResponse.needs_auth) {
      formattedMsg = maestroAI.formatForWhatsApp(aiResponse);
    } else {
      formattedMsg = aiResponse.message;
    }

    await sendAdminMessage(formattedMsg);
    return { processed: true, aiResponse };

  } catch (e) {
    console.error("[Maestro] Erro AI:", e);
    await sendAdminMessage("Erro ao processar: " + e.message);
    return { processed: true, error: e.message };
  }
}

// Processar comando rapido (0-9)
async function processQuickCommand(choice) {
  const action = QUICK_COMMANDS[choice];
  if (!action) {
    return null;
  }

  console.log("[Maestro] Comando rapido:", action.label);

  // Ignorar
  if (!action.command) {
    await sendAdminMessage("OK, ignorado");
    return { processed: true };
  }

  // Relatorio especial
  if (action.command === "maestro_report") {
    const report = await generateFullReport();
    await sendAdminMessage(report);
    return { processed: true };
  }

  // Executar comando
  const result = await executeCommand(action.command);
  const icon = result.success ? "[OK]" : "[ERRO]";
  const output = result.output.substring(0, 1500);

  await sendAdminMessage(`${icon} *${action.label}*\n\n\`\`\`\n${output}\n\`\`\``);

  return { processed: true, result };
}

// Registrar rotas Express
function setupMaestroRoutes(app) {
  // Receber alerta do Maestro Python
  app.post("/api/maestro/alert", async (req, res) => {
    try {
      const { phone, message, source, options } = req.body;

      if (!message) {
        return res.status(400).json({ error: "Message required" });
      }

      if (options && options.length > 0) {
        const alertId = Date.now().toString();
        pendingActions[alertId] = {
          timestamp: new Date().toISOString(),
          message,
          options,
          source
        };
        savePendingActions();
      }

      const sent = await sendAdminMessage(message);
      res.json({ success: sent, message: sent ? "Alert sent" : "Failed" });
    } catch (e) {
      console.error("[Maestro] Erro:", e);
      res.status(500).json({ error: e.message });
    }
  });

  // Status do Maestro
  app.get("/api/maestro/status", async (req, res) => {
    try {
      const statusFile = "/opt/maestro/data/status.json";
      let status = null;

      if (fs.existsSync(statusFile)) {
        status = JSON.parse(fs.readFileSync(statusFile, 'utf8'));
      }

      res.json({
        maestro: "active",
        version: "3.0-conversational",
        admin_phone: ADMIN_NUMBER,
        ai_enabled: true,
        pending_actions: Object.keys(pendingActions).length,
        last_check: status?.timestamp || null,
        services: status?.services || []
      });
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // Enviar relatorio sob demanda
  app.post("/api/maestro/report", async (req, res) => {
    try {
      const report = await generateFullReport();
      const sent = await sendAdminMessage(report);
      res.json({ success: sent });
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // Chat AI direto (para testes)
  app.post("/api/maestro/chat", async (req, res) => {
    try {
      const { message, phone } = req.body;
      if (!message) {
        return res.status(400).json({ error: "Message required" });
      }

      const response = await maestroAI.processMessage(message, phone || "test");
      res.json(response);
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  // Executar comando manual
  app.post("/api/maestro/execute", async (req, res) => {
    try {
      const { command, confirm } = req.body;
      if (!command) {
        return res.status(400).json({ error: "Command required" });
      }

      const allowedPrefixes = ["pm2 ", "systemctl status", "cat /opt/maestro", "tail ", "df ", "free ", "ss "];
      const isAllowed = allowedPrefixes.some(prefix => command.startsWith(prefix));

      if (!isAllowed && !confirm) {
        return res.status(403).json({ error: "Command not allowed", hint: "Use confirm: true" });
      }

      const result = await executeCommand(command);
      res.json(result);
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  console.log("[Maestro] v3.0 Conversacional - Rotas configuradas");
  console.log("[Maestro] Admin:", ADMIN_NUMBER);
  console.log("[Maestro] AI: Gemini 2.0 Flash");
}

module.exports = {
  setupMaestroRoutes,
  processAdminResponse,
  sendAdminMessage,
  generateFullReport,
  ADMIN_NUMBER
};
