/**
 * Known Clients Protection - CaseHub WhatsApp Bot
 * v1.0 - Protecao contra tratar clientes como leads
 * 
 * REGRA CRITICA: Clientes NUNCA devem receber respostas automaticas do bot
 */

// Lista de clientes conhecidos com seus telefones.
// Formato: telefone (normalizado, apenas numeros) -> info do cliente.
// Nao commitar clientes reais neste arquivo; alimente em runtime/config local.
const KNOWN_CLIENTS = {
  // "5511999999999": { name: "Cliente Demo", language: "pt", case: "demo" },
};

// Palavras-chave que indicam que é um cliente existente
const CLIENT_INDICATORS = [
  /my case/i,
  /meu caso/i,
  /mi caso/i,
  /case number/i,
  /numero do caso/i,
  /already.*client/i,
  /ja sou cliente/i,
  /I-\d{3}/i,  // Formularios como I-130, I-485, etc
  /receipt.*number/i,
  /numero de recibo/i,
  /document.*sent/i,
  /documento.*enviado/i
];

/**
 * Normaliza numero de telefone removendo caracteres especiais
 */
function normalizePhone(phone) {
  return (phone || '').replace(/\D/g, '');
}

/**
 * Verifica se o telefone pertence a um cliente conhecido
 * Retorna info do cliente ou null
 */
function checkKnownClient(phone) {
  const normalized = normalizePhone(phone);
  
  // Verificar match exato
  if (KNOWN_CLIENTS[normalized]) {
    return KNOWN_CLIENTS[normalized];
  }
  
  // Verificar se termina com o numero (caso tenha prefixo diferente)
  for (const [clientPhone, info] of Object.entries(KNOWN_CLIENTS)) {
    if (normalized.endsWith(clientPhone) || clientPhone.endsWith(normalized)) {
      return info;
    }
  }
  
  return null;
}

/**
 * Verifica se a mensagem indica que é um cliente existente
 */
function messageIndicatesClient(message) {
  if (!message) return false;
  return CLIENT_INDICATORS.some(pattern => pattern.test(message));
}

/**
 * Verifica se deve bloquear resposta automatica
 * Retorna { shouldBlock: boolean, reason: string, clientInfo: object|null }
 */
function shouldBlockAutoResponse(phone, message, lead) {
  // 1. Verificar lista de clientes conhecidos
  const knownClient = checkKnownClient(phone);
  if (knownClient) {
    return {
      shouldBlock: true,
      reason: 'Cliente conhecido: ' + knownClient.name,
      clientInfo: knownClient
    };
  }
  
  // 2. Verificar se ja esta marcado como active_client
  if (lead && lead.contact_type === 'active_client') {
    return {
      shouldBlock: true,
      reason: 'Marcado como cliente ativo no banco',
      clientInfo: null
    };
  }
  
  // 3. Verificar se mensagem indica cliente existente
  if (messageIndicatesClient(message)) {
    return {
      shouldBlock: true,
      reason: 'Mensagem indica cliente existente',
      clientInfo: null
    };
  }
  
  return { shouldBlock: false, reason: null, clientInfo: null };
}

/**
 * Adiciona um cliente a lista de conhecidos (em runtime)
 */
function addKnownClient(phone, info) {
  const normalized = normalizePhone(phone);
  KNOWN_CLIENTS[normalized] = info;
  console.log('[KNOWN-CLIENTS] Adicionado:', normalized, '-', info.name);
}

module.exports = {
  checkKnownClient,
  messageIndicatesClient,
  shouldBlockAutoResponse,
  addKnownClient,
  normalizePhone,
  KNOWN_CLIENTS
};
