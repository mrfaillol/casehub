/**
 * Maestro Knowledge Base v4
 * Base de conhecimento nativo do sistema WhatsApp Bot
 * CaseHub
 */

const SYSTEM_KNOWLEDGE = {
  // Arquivos principais do sistema
  files: {
    'server.js': {
      description: 'Entry point principal do bot',
      functions: ['handleIncomingMessage', 'APIs REST', 'WebSocket'],
      port: 3001,
      modifiable: true
    },
    'bot-flow.js': {
      description: 'State machine do bot',
      states: ['NEW', 'AWAITING_NAME', 'AWAITING_SERVICE', 'AWAITING_HUMAN', 'QUALIFIED'],
      modifiable: true
    },
    'llm-chatbot-v3.js': {
      description: 'Geração de respostas via Google Gemini',
      model: 'gemini-2.0-flash',
      functions: ['generateResponse', 'detectLanguage'],
      modifiable: true
    },
    'languages.js': {
      description: 'Templates de mensagens PT/EN/ES',
      sections: ['welcome', 'followup', 'qualification', 'errors'],
      modifiable: true
    },
    'bot-config.js': {
      description: 'Controle global on/off e horário comercial',
      config_file: 'bot-config.json',
      functions: ['shouldBotRespond', 'isBusinessHours', 'toggleBot'],
      modifiable: true
    },
    'auto-followup.js': {
      description: 'Sistema de follow-up automático',
      timing: '30 minutos após última mensagem humana',
      modifiable: true
    },
    'database.js': {
      description: 'Queries MySQL para leads/conversations',
      tables: ['leads', 'messages', 'conversations'],
      modifiable: true
    },
    'maestro-handler-v4.js': {
      description: 'Handler principal do Maestro (este sistema)',
      modifiable: false
    }
  },

  // Configurações do sistema
  configs: {
    botEnabled: {
      file: 'bot-config.json',
      key: 'globalEnabled',
      type: 'boolean',
      description: 'Liga/desliga o bot globalmente'
    },
    businessHours: {
      file: 'bot-config.json',
      key: 'businessHoursEnabled',
      type: 'boolean',
      description: 'Ativa horário comercial (12h-18h BRT = bot OFF)'
    },
    templates: {
      file: 'languages.js',
      key: 'MESSAGES',
      type: 'object',
      description: 'Mensagens por idioma (pt/en/es)'
    }
  },

  // Informações da infraestrutura
  infrastructure: {
    server: {
      ip: process.env.VPS_IP || 'localhost',
      user: 'root',
      os: 'Ubuntu'
    },
    services: {
      'whatsapp-bot': { port: 3001, pm2: true },
      'casehub': { port: 8001, pm2: true },
      'ilc-tools': { port: 8000, pm2: true }
    },
    database: {
      type: 'MySQL',
      host: 'localhost',
      database: 'whatsapp_bot'
    },
    paths: {
      bot: '${process.env.APP_BASE_PATH || "/opt/casehub"}/whatsapp-bot',
      casehub: '${process.env.APP_BASE_PATH || "/opt/casehub"}/casehub',
      backups: '${process.env.APP_BASE_PATH || "/opt/casehub"}/whatsapp-bot/backups/maestro'
    }
  },

  // Regras de negócio
  businessRules: {
    advogado: {
      referencia: 'nosso advogado',
      formato_formal: 'nosso advogado de imigração',
      NUNCA: 'nome do advogado, Dr., Esq.'
    },
    horario_bot: {
      ativo: '18h às 12h BRT',
      inativo: '12h às 18h BRT (horário comercial)',
      timezone: 'America/New_York'
    },
    mensagens: {
      sempre_terminar_com: [
        'Nossa equipe já vai te atender em breve!',
        'Já já alguém da nossa equipe vai te responder!',
        'Em breve nossa equipe entra em contato!'
      ]
    }
  },

  // Comandos rápidos do Maestro
  quickCommands: {
    'status': 'Mostra status do sistema (PM2, RAM, disco)',
    'templates': 'Lista templates de mensagens disponíveis',
    'ver [arquivo]': 'Mostra conteúdo de um arquivo',
    'buscar [termo]': 'Busca termo nos arquivos do bot',
    'reverter': 'Reverte última modificação',
    'backups': 'Lista backups disponíveis',
    'reiniciar [serviço]': 'Reinicia serviço PM2 (com confirmação)',
    'logs [serviço]': 'Mostra logs recentes',
    'sair': 'Desativa modo Maestro'
  }
};

// Arquivos protegidos (NUNCA modificar)
const PROTECTED_FILES = [
  '.env',
  '*.key',
  '*.pem',
  'credentials*.json',
  'package-lock.json',
  'node_modules/**',
  'maestro-handler-v4.js',
  'maestro-knowledge.js'
];

// Comandos shell proibidos
const FORBIDDEN_COMMANDS = [
  'rm -rf',
  'rm -r /',
  'dd if=',
  'mkfs',
  'chmod -R 777',
  ':(){:|:&};:',
  '> /dev/sda',
  'wget | sh',
  'curl | sh'
];

// Whitelist de comandos shell permitidos
const ALLOWED_SHELL_COMMANDS = [
  'pm2 status',
  'pm2 list',
  'pm2 logs',
  'pm2 restart',
  'pm2 reload',
  'cat',
  'head',
  'tail',
  'grep',
  'ls',
  'df -h',
  'free -m',
  'uptime',
  'date',
  'wc',
  'find',
  'node --version',
  'npm --version',
  'mysql --version'
];

// Telefones de administradores autorizados
const ADMIN_PHONES = [
  '5532991513405',
  '5519998523218',
  '19405550000' // placeholder para o +1 (940)
];

// Função para verificar se é admin
function isAdminPhone(phone) {
  const cleanPhone = phone.replace(/\D/g, '');
  return ADMIN_PHONES.some(admin => {
    const cleanAdmin = admin.replace(/\D/g, '');
    // Verifica últimos 8 dígitos
    return cleanPhone.endsWith(cleanAdmin.slice(-8)) ||
           cleanAdmin.endsWith(cleanPhone.slice(-8));
  });
}

// Função para verificar se arquivo é protegido
function isProtectedFile(filePath) {
  const fileName = filePath.split('/').pop();
  return PROTECTED_FILES.some(pattern => {
    if (pattern.includes('*')) {
      const regex = new RegExp('^' + pattern.replace(/\*/g, '.*') + '$');
      return regex.test(fileName) || regex.test(filePath);
    }
    return fileName === pattern || filePath.endsWith(pattern);
  });
}

// Função para verificar se comando é permitido
function isAllowedCommand(command) {
  // Verifica comandos proibidos
  if (FORBIDDEN_COMMANDS.some(forbidden => command.includes(forbidden))) {
    return { allowed: false, reason: 'Comando potencialmente destrutivo' };
  }

  // Verifica whitelist
  const isWhitelisted = ALLOWED_SHELL_COMMANDS.some(allowed =>
    command.trim().startsWith(allowed)
  );

  return {
    allowed: isWhitelisted,
    reason: isWhitelisted ? 'Comando permitido' : 'Comando não está na whitelist'
  };
}

// Função para obter descrição de arquivo
function getFileDescription(fileName) {
  const file = SYSTEM_KNOWLEDGE.files[fileName];
  if (!file) {
    return `Arquivo não documentado: ${fileName}`;
  }
  return `${fileName}: ${file.description}`;
}

// Função para listar todos os arquivos conhecidos
function listKnownFiles() {
  return Object.entries(SYSTEM_KNOWLEDGE.files).map(([name, info]) => ({
    name,
    description: info.description,
    modifiable: info.modifiable
  }));
}

module.exports = {
  SYSTEM_KNOWLEDGE,
  PROTECTED_FILES,
  FORBIDDEN_COMMANDS,
  ALLOWED_SHELL_COMMANDS,
  ADMIN_PHONES,
  isAdminPhone,
  isProtectedFile,
  isAllowedCommand,
  getFileDescription,
  listKnownFiles
};
