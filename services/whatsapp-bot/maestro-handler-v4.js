/**
 * Maestro Handler v4
 * Sistema de administração avançado via WhatsApp
 * Com capacidade de modificação de código e backups automáticos
 * CaseHub
 */

const fs = require('fs').promises;
const path = require('path');
const { exec } = require('child_process');
const util = require('util');
const execAsync = util.promisify(exec);

const {
  SYSTEM_KNOWLEDGE,
  ADMIN_PHONES,
  isAdminPhone,
  isProtectedFile,
  isAllowedCommand,
  getFileDescription,
  listKnownFiles
} = require('./maestro-knowledge');

// Google Gemini
const { GoogleGenerativeAI } = require('@google/generative-ai');

// Configurações
const BOT_PATH = '${process.env.APP_BASE_PATH || "/opt/casehub"}/whatsapp-bot';
const BACKUP_PATH = '${process.env.APP_BASE_PATH || "/opt/casehub"}/whatsapp-bot/backups/maestro';
const MAX_WHATSAPP_LENGTH = 4000;
const PLAN_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutos

// Estado das sessões do Maestro (por telefone)
const maestroSessions = new Map();

// Estado dos planos pendentes
const pendingPlans = new Map();

// Histórico de modificações para reverter
const modificationHistory = [];

// Sistema de log de auditoria
async function auditLog(action, details, phone) {
  const timestamp = new Date().toISOString();
  const logEntry = `[${timestamp}] [${phone}] ${action}: ${JSON.stringify(details)}\n`;
  const logPath = path.join(BACKUP_PATH, 'audit.log');

  try {
    await fs.appendFile(logPath, logEntry);
  } catch (error) {
    console.error('[MAESTRO] Erro ao escrever audit log:', error);
  }
}

// Prompt do sistema para o Gemini
const MAESTRO_SYSTEM_PROMPT = `Você é o Maestro, assistente de administração do sistema WhatsApp Bot do ${process.env.ORG_NAME || "CaseHub"}.

VOCÊ TEM ACESSO A:
- Leitura de qualquer arquivo do sistema
- Modificação de arquivos (com aprovação e backup)
- Reinício de serviços PM2 (com confirmação extra)
- Configurações do bot

ARQUIVOS PRINCIPAIS:
- server.js: Entry point, APIs, handleIncomingMessage (porta 3001)
- bot-flow.js: State machine (estados: NEW, AWAITING_NAME, AWAITING_SERVICE, AWAITING_HUMAN)
- llm-chatbot-v3.js: Respostas automáticas via Gemini 2.0 Flash
- languages.js: Templates PT/EN/ES
- bot-config.js: Controle on/off, horário comercial
- auto-followup.js: Sistema de follow-up automático
- database.js: Queries MySQL (leads, messages, conversations)

REGRAS IMPORTANTES:
1. SEMPRE mostre um plano antes de modificar código
2. SEMPRE faça backup antes de modificar
3. NUNCA modifique .env, credenciais ou arquivos protegidos
4. Para modificações, peça confirmação explícita (SIM/NÃO)
5. Se não tiver certeza, pergunte ao usuário
6. Respostas devem ser formatadas para WhatsApp (max 4000 chars)
7. NUNCA mencione o nome do advogado em mensagens automaticas. Use "nosso advogado" ou "nosso advogado de imigracao"

COMANDOS RÁPIDOS:
- status: Mostra status do sistema
- templates: Lista templates disponíveis
- ver [arquivo]: Mostra conteúdo
- buscar [termo]: Busca nos arquivos
- reverter: Reverte última modificação
- backups: Lista backups
- reiniciar [serviço]: Reinicia PM2 (com confirmação)
- logs [serviço]: Mostra logs
- sair: Desativa Maestro

FORMATO DE RESPOSTA:
Sempre responda em JSON com um dos formatos:

Para informações simples:
{"type": "info", "message": "Resposta formatada para WhatsApp"}

Para planos de modificação:
{"type": "plan", "id": "uuid", "summary": "Resumo", "files": ["arquivo.js"], "changes": [{"file": "arquivo.js", "line": 123, "old": "código antigo", "new": "código novo", "description": "O que muda"}], "impact": "baixo|médio|alto", "needs_restart": false}

Para execução de comandos:
{"type": "command", "command": "pm2 status", "requires_confirmation": false}

Para erros:
{"type": "error", "message": "Descrição do erro"}`;

class MaestroHandler {
  constructor() {
    this.genAI = null;
    this.model = null;
  }

  async initialize() {
    const apiKey = process.env.GOOGLE_API_KEY || process.env.GEMINI_API_KEY;
    if (!apiKey) {
      throw new Error('GOOGLE_API_KEY não configurada');
    }

    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({
      model: 'gemini-2.0-flash',
      generationConfig: {
        temperature: 0.7,
        maxOutputTokens: 2000
      }
    });
  }

  // Verifica se a mensagem é ativação do Maestro
  static isActivation(message) {
    const patterns = [
      /^ol[aá],?\s*maestro/i,
      /^hey,?\s*maestro/i,
      /^oi,?\s*maestro/i,
      /^maestro$/i
    ];
    return patterns.some(p => p.test(message.trim()));
  }

  // Verifica se é resposta de confirmação
  static isConfirmation(message) {
    const msg = message.trim().toLowerCase();
    return ['sim', 'yes', 's', 'y', 'confirmo', 'autorizo'].includes(msg);
  }

  static isDenial(message) {
    const msg = message.trim().toLowerCase();
    return ['não', 'nao', 'no', 'n', 'cancela', 'cancelar'].includes(msg);
  }

  // Ativa sessão do Maestro
  activateSession(phone) {
    maestroSessions.set(phone, {
      active: true,
      startedAt: new Date(),
      history: []
    });
    console.log(`[MAESTRO] Sessão ativada para ${phone}`);
  }

  // Desativa sessão do Maestro
  deactivateSession(phone) {
    maestroSessions.delete(phone);
    pendingPlans.delete(phone);
    console.log(`[MAESTRO] Sessão desativada para ${phone}`);
  }

  // Verifica se sessão está ativa
  isSessionActive(phone) {
    const session = maestroSessions.get(phone);
    return session && session.active;
  }

  // Lê arquivo do sistema
  async readFile(filePath) {
    try {
      const fullPath = filePath.startsWith('/') ? filePath : path.join(BOT_PATH, filePath);
      const content = await fs.readFile(fullPath, 'utf-8');

      // Limita tamanho para WhatsApp
      if (content.length > MAX_WHATSAPP_LENGTH) {
        return content.substring(0, MAX_WHATSAPP_LENGTH) + '\n\n[... truncado ...]';
      }
      return content;
    } catch (error) {
      throw new Error(`Erro ao ler ${filePath}: ${error.message}`);
    }
  }

  // Lista arquivos de um diretório
  async listFiles(directory = BOT_PATH) {
    try {
      const files = await fs.readdir(directory);
      const stats = await Promise.all(
        files.map(async (file) => {
          const filePath = path.join(directory, file);
          const stat = await fs.stat(filePath);
          return {
            name: file,
            size: stat.size,
            isDirectory: stat.isDirectory(),
            modified: stat.mtime
          };
        })
      );
      return stats;
    } catch (error) {
      throw new Error(`Erro ao listar ${directory}: ${error.message}`);
    }
  }

  // Busca em arquivos
  async searchInFiles(pattern, directory = BOT_PATH) {
    try {
      const { stdout } = await execAsync(
        `grep -rn "${pattern}" ${directory}/*.js --include="*.js" 2>/dev/null | head -20`
      );
      return stdout || 'Nenhum resultado encontrado';
    } catch (error) {
      return 'Nenhum resultado encontrado';
    }
  }

  // Cria backup de arquivo
  async createBackup(filePath) {
    const fileName = path.basename(filePath);
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const backupName = `${fileName}.${timestamp}.bak`;
    const backupPath = path.join(BACKUP_PATH, backupName);

    const fullPath = filePath.startsWith('/') ? filePath : path.join(BOT_PATH, filePath);
    await fs.copyFile(fullPath, backupPath);

    console.log(`[MAESTRO] Backup criado: ${backupPath}`);
    return backupPath;
  }

  // Lista backups disponíveis
  async listBackups() {
    try {
      const files = await fs.readdir(BACKUP_PATH);
      const backups = files.filter(f => f.endsWith('.bak'));
      return backups.sort().reverse().slice(0, 20); // Últimos 20
    } catch (error) {
      return [];
    }
  }

  // Reverte para backup
  async revertToBackup(backupName) {
    const backupPath = path.join(BACKUP_PATH, backupName);
    const originalName = backupName.split('.').slice(0, -2).join('.');
    const originalPath = path.join(BOT_PATH, originalName);

    // Cria backup do arquivo atual antes de reverter
    await this.createBackup(originalName);

    // Restaura o backup
    await fs.copyFile(backupPath, originalPath);

    return { restored: originalPath, from: backupPath };
  }

  // Aplica modificação em arquivo
  async applyModification(filePath, oldContent, newContent, reason) {
    if (isProtectedFile(filePath)) {
      throw new Error(`Arquivo protegido: ${filePath}`);
    }

    const fullPath = filePath.startsWith('/') ? filePath : path.join(BOT_PATH, filePath);

    // Lê conteúdo atual
    const currentContent = await fs.readFile(fullPath, 'utf-8');

    // Verifica se old_content existe no arquivo
    if (!currentContent.includes(oldContent)) {
      throw new Error('Conteúdo original não encontrado no arquivo. Verifique o plano.');
    }

    // Cria backup
    const backupPath = await this.createBackup(filePath);

    // Aplica modificação
    const modifiedContent = currentContent.replace(oldContent, newContent);
    await fs.writeFile(fullPath, modifiedContent, 'utf-8');

    // Valida sintaxe JS
    if (filePath.endsWith('.js')) {
      try {
        await execAsync(`node --check ${fullPath}`);
      } catch (syntaxError) {
        // Reverte se tiver erro de sintaxe
        await fs.copyFile(backupPath, fullPath);
        throw new Error(`Erro de sintaxe detectado. Modificação revertida.\n${syntaxError.stderr}`);
      }
    }

    // Registra no histórico
    modificationHistory.unshift({
      timestamp: new Date(),
      file: filePath,
      backup: backupPath,
      reason,
      oldContent,
      newContent
    });

    // Mantém apenas últimas 50 modificações
    if (modificationHistory.length > 50) {
      modificationHistory.pop();
    }

    return { success: true, backup: backupPath };
  }

  // Executa comando shell
  async executeCommand(command, phone) {
    const check = isAllowedCommand(command);
    if (!check.allowed) {
      throw new Error(check.reason);
    }

    await auditLog('COMMAND_EXEC', { command }, phone);

    try {
      const { stdout, stderr } = await execAsync(command, {
        cwd: BOT_PATH,
        timeout: 30000
      });

      let result = stdout || stderr || 'Comando executado sem output';
      if (result.length > MAX_WHATSAPP_LENGTH) {
        result = result.substring(0, MAX_WHATSAPP_LENGTH) + '\n\n[... truncado ...]';
      }
      return result;
    } catch (error) {
      throw new Error(`Erro ao executar: ${error.message}`);
    }
  }

  // Obtém status do sistema
  async getSystemStatus() {
    try {
      const [pm2Status, memory, disk, uptime] = await Promise.all([
        execAsync('pm2 jlist').then(r => JSON.parse(r.stdout)).catch(() => []),
        execAsync('free -m').then(r => r.stdout).catch(() => 'N/A'),
        execAsync('df -h /').then(r => r.stdout).catch(() => 'N/A'),
        execAsync('uptime').then(r => r.stdout.trim()).catch(() => 'N/A')
      ]);

      const services = pm2Status.map(s => ({
        name: s.name,
        status: s.pm2_env?.status || 'unknown',
        memory: Math.round((s.monit?.memory || 0) / 1024 / 1024) + 'MB',
        uptime: s.pm2_env?.pm_uptime ?
          Math.round((Date.now() - s.pm2_env.pm_uptime) / 1000 / 60) + ' min' : 'N/A'
      }));

      return {
        services,
        memory: memory.split('\n')[1] || 'N/A',
        disk: disk.split('\n')[1] || 'N/A',
        uptime
      };
    } catch (error) {
      return { error: error.message };
    }
  }

  // Processa comandos rápidos
  async processQuickCommand(message, phone) {
    const msg = message.toLowerCase().trim();

    // Comando: sair
    if (msg === 'sair' || msg === 'exit') {
      this.deactivateSession(phone);
      return '👋 Maestro desativado. Até a próxima!';
    }

    // Comando: status
    if (msg === 'status') {
      const status = await this.getSystemStatus();
      let response = '📊 *STATUS DO SISTEMA*\n\n';

      response += '*Serviços PM2:*\n';
      for (const svc of status.services) {
        const icon = svc.status === 'online' ? '✅' : '❌';
        response += `${icon} ${svc.name}: ${svc.status} (${svc.memory})\n`;
      }

      response += `\n*Memória:* ${status.memory}\n`;
      response += `*Disco:* ${status.disk}\n`;
      response += `*Uptime:* ${status.uptime}`;

      return response;
    }

    // Comando: backups
    if (msg === 'backups') {
      const backups = await this.listBackups();
      if (backups.length === 0) {
        return '📂 Nenhum backup encontrado.';
      }
      return '📂 *BACKUPS DISPONÍVEIS*\n\n' + backups.map(b => `• ${b}`).join('\n');
    }

    // Comando: templates
    if (msg === 'templates') {
      const files = listKnownFiles();
      return '📄 *ARQUIVOS DO SISTEMA*\n\n' +
        files.map(f => `• *${f.name}*\n  ${f.description}\n  ${f.modifiable ? '✏️ Editável' : '🔒 Protegido'}`).join('\n\n');
    }

    // Comando: ver [arquivo]
    if (msg.startsWith('ver ')) {
      const fileName = msg.substring(4).trim();
      try {
        const content = await this.readFile(fileName);
        return `📄 *${fileName}*\n\n\`\`\`\n${content}\n\`\`\``;
      } catch (error) {
        return `❌ ${error.message}`;
      }
    }

    // Comando: buscar [termo]
    if (msg.startsWith('buscar ')) {
      const term = msg.substring(7).trim();
      const results = await this.searchInFiles(term);
      return `🔍 *BUSCA: ${term}*\n\n\`\`\`\n${results}\n\`\`\``;
    }

    // Comando: logs [serviço]
    if (msg.startsWith('logs')) {
      const service = msg.substring(4).trim() || 'whatsapp-bot';
      try {
        const { stdout } = await execAsync(`pm2 logs ${service} --nostream --lines 30`);
        return `📋 *LOGS: ${service}*\n\n\`\`\`\n${stdout.substring(0, MAX_WHATSAPP_LENGTH)}\n\`\`\``;
      } catch (error) {
        return `❌ Erro ao obter logs: ${error.message}`;
      }
    }

    // Comando: reverter
    if (msg === 'reverter') {
      if (modificationHistory.length === 0) {
        return '❌ Nenhuma modificação para reverter.';
      }

      const last = modificationHistory[0];
      const backupName = path.basename(last.backup);

      // Armazena plano de reversão
      pendingPlans.set(phone, {
        type: 'revert',
        backup: backupName,
        file: last.file,
        createdAt: new Date()
      });

      return `🔄 *REVERTER ÚLTIMA MODIFICAÇÃO*\n\n` +
        `Arquivo: ${last.file}\n` +
        `Data: ${last.timestamp.toLocaleString()}\n` +
        `Motivo: ${last.reason}\n` +
        `Backup: ${backupName}\n\n` +
        `⚠️ Deseja reverter? Responda *SIM* ou *NÃO*`;
    }

    // Comando: reiniciar [serviço]
    if (msg.startsWith('reiniciar')) {
      const service = msg.substring(9).trim() || 'whatsapp-bot';

      pendingPlans.set(phone, {
        type: 'restart',
        service,
        createdAt: new Date()
      });

      return `🔄 *REINICIAR SERVIÇO*\n\n` +
        `Serviço: ${service}\n\n` +
        `⚠️ Isso pode causar interrupção temporária.\n` +
        `Confirma? Responda *SIM* ou *NÃO*`;
    }

    return null; // Não é comando rápido
  }

  // Processa confirmação de plano pendente
  async processConfirmation(message, phone) {
    const pending = pendingPlans.get(phone);
    if (!pending) return null;

    // Verifica timeout
    if (Date.now() - pending.createdAt.getTime() > PLAN_TIMEOUT_MS) {
      pendingPlans.delete(phone);
      return '⏰ Plano expirado (timeout de 5 minutos). Por favor, solicite novamente.';
    }

    if (MaestroHandler.isConfirmation(message)) {
      pendingPlans.delete(phone);

      if (pending.type === 'revert') {
        const result = await this.revertToBackup(pending.backup);
        await auditLog('REVERT', result, phone);
        return `✅ Arquivo restaurado com sucesso!\n\nArquivo: ${result.restored}\nDe: ${result.from}`;
      }

      if (pending.type === 'restart') {
        await auditLog('RESTART', { service: pending.service }, phone);
        const result = await this.executeCommand(`pm2 restart ${pending.service}`, phone);
        return `✅ Serviço ${pending.service} reiniciado!\n\n${result}`;
      }

      if (pending.type === 'modification') {
        try {
          for (const change of pending.changes) {
            await this.applyModification(
              change.file,
              change.old,
              change.new,
              pending.summary
            );
          }

          await auditLog('MODIFICATION', pending, phone);

          let response = `✅ *MODIFICAÇÃO APLICADA COM SUCESSO!*\n\n`;
          response += `Resumo: ${pending.summary}\n`;
          response += `Arquivos: ${pending.files.join(', ')}\n\n`;
          response += `Backups criados automaticamente.\n`;
          response += `Para reverter: digite *reverter*`;

          if (pending.needs_restart) {
            response += `\n\n⚠️ Reinício necessário para aplicar mudanças.\nDigite *reiniciar ${pending.service || 'whatsapp-bot'}* para reiniciar.`;
          }

          return response;
        } catch (error) {
          return `❌ Erro ao aplicar modificação: ${error.message}`;
        }
      }
    }

    if (MaestroHandler.isDenial(message)) {
      pendingPlans.delete(phone);
      return '❌ Operação cancelada.';
    }

    return null; // Não é confirmação/negação
  }

  // Processa mensagem com IA
  async processWithAI(message, phone) {
    if (!this.model) {
      await this.initialize();
    }

    const session = maestroSessions.get(phone);

    // Contexto adicional
    let context = '';

    // Se a mensagem menciona um arquivo específico, lê o conteúdo
    const fileMatch = message.match(/(?:arquivo|file|ver|olhar|checar|modificar|mudar)\s+(\w+\.js)/i);
    if (fileMatch) {
      try {
        const content = await this.readFile(fileMatch[1]);
        context += `\n\nConteúdo atual de ${fileMatch[1]}:\n\`\`\`javascript\n${content.substring(0, 3000)}\n\`\`\``;
      } catch (e) {
        context += `\n\nErro ao ler ${fileMatch[1]}: ${e.message}`;
      }
    }

    const prompt = `${MAESTRO_SYSTEM_PROMPT}

CONTEXTO ATUAL:
- Telefone do admin: ${phone}
- Sessão ativa há: ${Math.round((Date.now() - session.startedAt.getTime()) / 1000 / 60)} minutos
${context}

MENSAGEM DO USUÁRIO:
${message}

Responda em JSON válido.`;

    try {
      const result = await this.model.generateContent(prompt);
      const responseText = result.response.text();

      // Tenta parsear como JSON
      let parsed;
      try {
        // Remove possíveis marcadores de código
        const cleanJson = responseText.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim();
        parsed = JSON.parse(cleanJson);
      } catch {
        // Se não for JSON válido, retorna como mensagem de info
        return responseText;
      }

      // Processa resposta baseado no tipo
      if (parsed.type === 'info') {
        return parsed.message;
      }

      if (parsed.type === 'error') {
        return `❌ ${parsed.message}`;
      }

      if (parsed.type === 'command') {
        if (parsed.requires_confirmation) {
          pendingPlans.set(phone, {
            type: 'command',
            command: parsed.command,
            createdAt: new Date()
          });
          return `🔧 *COMANDO*\n\n\`${parsed.command}\`\n\n⚠️ Confirma execução? *SIM* ou *NÃO*`;
        }

        const result = await this.executeCommand(parsed.command, phone);
        return `🔧 *RESULTADO*\n\n\`\`\`\n${result}\n\`\`\``;
      }

      if (parsed.type === 'plan') {
        // Armazena plano para confirmação
        pendingPlans.set(phone, {
          type: 'modification',
          id: parsed.id || Date.now().toString(),
          summary: parsed.summary,
          files: parsed.files,
          changes: parsed.changes,
          impact: parsed.impact,
          needs_restart: parsed.needs_restart,
          service: parsed.service,
          createdAt: new Date()
        });

        let response = `📋 *PLANO DE MODIFICAÇÃO*\n\n`;
        response += `*Objetivo:* ${parsed.summary}\n\n`;
        response += `*Arquivos afetados:*\n`;
        for (const file of parsed.files) {
          response += `• ${file}\n`;
        }
        response += `\n*Modificações:*\n`;
        for (const change of parsed.changes) {
          response += `\n📄 ${change.file} (linha ~${change.line || '?'})\n`;
          response += `${change.description || ''}\n`;
          response += `\`\`\`\n- ${change.old.substring(0, 100)}${change.old.length > 100 ? '...' : ''}\n+ ${change.new.substring(0, 100)}${change.new.length > 100 ? '...' : ''}\n\`\`\`\n`;
        }
        response += `\n*Impacto:* ${parsed.impact?.toUpperCase() || 'MÉDIO'}`;
        response += `\n*Requer reinício:* ${parsed.needs_restart ? 'SIM' : 'NÃO'}\n`;
        response += `\n⚠️ Será criado backup antes da modificação.\n`;
        response += `\nAutoriza? Responda *SIM* ou *NÃO*`;

        return response;
      }

      return responseText;
    } catch (error) {
      console.error('[MAESTRO] Erro ao processar com IA:', error);
      return `❌ Erro ao processar: ${error.message}`;
    }
  }

  // Método principal: processa mensagem
  async handleMessage(phone, message) {
    // Verifica se é admin
    if (!isAdminPhone(phone)) {
      console.log(`[MAESTRO] Tentativa de acesso não autorizado: ${phone}`);
      return null; // Silenciosamente ignora
    }

    // Verifica se é ativação
    if (MaestroHandler.isActivation(message)) {
      this.activateSession(phone);
      await auditLog('SESSION_START', {}, phone);

      return `🎭 *MAESTRO ATIVADO*\n\n` +
        `Olá! Sou o Maestro, seu assistente de administração do sistema.\n\n` +
        `*Comandos rápidos:*\n` +
        `• status - Status do sistema\n` +
        `• templates - Listar arquivos\n` +
        `• ver [arquivo] - Ver conteúdo\n` +
        `• buscar [termo] - Buscar código\n` +
        `• backups - Listar backups\n` +
        `• logs [serviço] - Ver logs\n` +
        `• reverter - Desfazer mudança\n` +
        `• sair - Desativar Maestro\n\n` +
        `Ou me diga o que precisa em linguagem natural!`;
    }

    // Se não tem sessão ativa, ignora
    if (!this.isSessionActive(phone)) {
      return null;
    }

    // Verifica se há plano pendente
    const confirmResponse = await this.processConfirmation(message, phone);
    if (confirmResponse) {
      return confirmResponse;
    }

    // Tenta processar como comando rápido
    const quickResponse = await this.processQuickCommand(message, phone);
    if (quickResponse) {
      return quickResponse;
    }

    // Processa com IA
    return await this.processWithAI(message, phone);
  }
}

// Singleton
const maestroHandler = new MaestroHandler();

module.exports = {
  MaestroHandler,
  maestroHandler,
  isActivation: MaestroHandler.isActivation
};
