/**
 * Bot Configuration - Global Control
 * CaseHub
 * v5.0 - Hard OFF mode (kill-switch confiável)
 *
 * REGRA:
 * - Bot DESLIGADO: 12h-18h (Seg-Sex) - atendimento humano
 * - Bot LIGADO: 18h-12h (Seg-Sex) - fora do expediente
 * - Bot LIGADO: Sábado e Domingo (24h)
 * - HARD OFF: desligamento permanente, sem auto-reativação, sem catch-up
 *   Quando desligado manualmente, fica OFF até ser ligado manualmente.
 */

const fs = require("fs");
const path = require("path");

const CONFIG_FILE = path.join(__dirname, "bot-config.json");

const DEFAULT_CONFIG = {
  globalEnabled: true,
  hardOff: false,
  hardOffAt: null,
  hardOffBy: null,
  businessHoursEnabled: true,
  businessHoursStart: 12,
  businessHoursEnd: 18,
  timezone: "America/Sao_Paulo",
  disabledAt: null,
  lastUpdated: null,
  updatedBy: null
};

/**
 * NEVER_CONTACT - Lista de telefones que NUNCA devem receber resposta automática
 * Bot será bloqueado permanentemente para estes números
 * Daniel pediu 3-4x para desativar bot para Fabio (cliente VIP)
 */
const NEVER_CONTACT = [
  '5532991234567',  // Fabio - cliente VIP (pedido Daniel 3-4x)
  // Adicionar outros números conforme necessário
];

/**
 * Verifica se número está na lista never-contact
 * @param {string} phoneNumber - Número de telefone (com ou sem formatação)
 * @returns {boolean} true se está bloqueado, false caso contrário
 */
function isNeverContact(phoneNumber) {
  if (!phoneNumber) return false;
  const cleanPhone = phoneNumber.replace(/\D/g, '');
  return NEVER_CONTACT.some(blocked => {
    const cleanBlocked = blocked.replace(/\D/g, '');
    return cleanPhone.includes(cleanBlocked) || cleanBlocked.includes(cleanPhone);
  });
}

function loadConfig() {
  try {
    if (fs.existsSync(CONFIG_FILE)) {
      const data = fs.readFileSync(CONFIG_FILE, "utf8");
      return { ...DEFAULT_CONFIG, ...JSON.parse(data) };
    }
  } catch (err) {
    console.error("[BOT-CONFIG] Erro ao carregar config:", err.message);
  }
  return { ...DEFAULT_CONFIG };
}

function saveConfig(config) {
  try {
    config.lastUpdated = new Date().toISOString();
    fs.writeFileSync(CONFIG_FILE, JSON.stringify(config, null, 2));
    return true;
  } catch (err) {
    console.error("[BOT-CONFIG] Erro ao salvar config:", err.message);
    return false;
  }
}

let currentConfig = loadConfig();

// Flag interna: indica que o bot acabou de ser reativado e precisa fazer catch-up
let _catchUpPending = false;
let _catchUpDisabledAt = null; // periodo que ficou desativado

function getCurrentHourInTZ(date) {
  const options = { timeZone: currentConfig.timezone, hour: "numeric", hour12: false };
  return parseInt(new Intl.DateTimeFormat("en-US", options).format(date || new Date()));
}

function isBusinessHours() {
  if (!currentConfig.businessHoursEnabled) {
    return false;
  }

  const now = new Date();
  const currentHour = getCurrentHourInTZ(now);

  const dayOptions = { timeZone: currentConfig.timezone, weekday: "short" };
  const dayOfWeek = new Intl.DateTimeFormat("en-US", dayOptions).format(now);
  const isWeekend = ["Sat", "Sun"].includes(dayOfWeek);

  if (isWeekend) {
    return false;
  }

  return currentHour >= currentConfig.businessHoursStart && 
         currentHour < currentConfig.businessHoursEnd;
}

/**
 * AUTO-REATIVAÇÃO + sinalização de catch-up
 * NOTA v5.0: Desabilitada quando hardOff === true
 */
function checkAutoReactivation() {
  // HARD OFF: NUNCA auto-reativar
  if (currentConfig.hardOff) return;

  if (currentConfig.globalEnabled || !currentConfig.disabledAt) return;

  const now = new Date();
  const disabledAt = new Date(currentConfig.disabledAt);
  const hoursSinceDisable = (now - disabledAt) / (1000 * 60 * 60);

  let shouldReactivate = false;
  let reason = "";

  if (hoursSinceDisable >= 6) {
    shouldReactivate = true;
    reason = "desativado há " + Math.round(hoursSinceDisable) + " horas (limite: 6h)";
  } else if (!isBusinessHours()) {
    const disabledHour = getCurrentHourInTZ(disabledAt);
    const currentHour = getCurrentHourInTZ(now);

    if (disabledHour >= currentConfig.businessHoursStart &&
        disabledHour < currentConfig.businessHoursEnd &&
        currentHour >= currentConfig.businessHoursEnd) {
      shouldReactivate = true;
      reason = "desativado às " + disabledHour + "h durante expediente, agora são " + currentHour + "h (expediente acabou)";
    }
  }

  if (shouldReactivate) {
    console.log("[BOT-CONFIG] AUTO-REATIVAÇÃO: " + reason + ". Bot reativado automaticamente.");
    
    // Sinalizar catch-up ANTES de limpar disabledAt
    _catchUpPending = true;
    _catchUpDisabledAt = currentConfig.disabledAt;
    
    currentConfig.globalEnabled = true;
    currentConfig.disabledAt = null;
    currentConfig.updatedBy = "auto-reativacao";
    saveConfig(currentConfig);
    
    console.log("[BOT-CONFIG] Catch-up sinalizado para mensagens desde " + _catchUpDisabledAt);
  }
}

/**
 * Consumir evento de catch-up (chamado uma vez pelo server.js)
 * Retorna { pending: true, disabledAt: ISO } se há catch-up pendente
 * Retorna { pending: false } se não há
 */
function consumeCatchUpEvent() {
  if (_catchUpPending) {
    const event = { pending: true, disabledAt: _catchUpDisabledAt };
    _catchUpPending = false;
    _catchUpDisabledAt = null;
    return event;
  }
  return { pending: false };
}

function shouldBotRespond(phoneNumber) {
  checkAutoReactivation();

  // CRITICAL: Verificar never-contact list PRIMEIRO (Correção #4)
  // Cliente na lista never-contact NUNCA recebe resposta automática
  if (phoneNumber && isNeverContact(phoneNumber)) {
    return {
      shouldRespond: false,
      reason: "Cliente na lista never-contact - atendimento humano OBRIGATÓRIO (não pode ser overridado)"
    };
  }

  // v5.0: HARD OFF - bot completamente desativado, sem exceções
  if (currentConfig.hardOff) {
    return {
      shouldRespond: false,
      reason: "Bot em HARD OFF - desativado permanentemente por " + (currentConfig.hardOffBy || "admin")
    };
  }

  if (!currentConfig.globalEnabled) {
    const info = currentConfig.disabledAt
      ? " (desativado há " + Math.round((new Date() - new Date(currentConfig.disabledAt)) / (1000*60)) + " min, reativa em até 6h)"
      : "";
    return {
      shouldRespond: false,
      reason: "Bot desativado manualmente (toggle global OFF)" + info
    };
  }

  if (isBusinessHours()) {
    return {
      shouldRespond: false,
      reason: "Horário comercial (12h-18h Seg-Sex) - atendimento humano"
    };
  }

  return {
      shouldRespond: true,
    reason: "Bot ativo - fora do horário comercial"
  };
}

function getStatus() {
  const inBusinessHours = isBusinessHours();
  const check = shouldBotRespond();

  const now = new Date();
  const timeOptions = { 
    timeZone: currentConfig.timezone, 
    hour: "2-digit", 
    minute: "2-digit",
    hour12: false 
  };
  const currentTime = new Intl.DateTimeFormat("en-US", timeOptions).format(now);

  const dayOptions = { timeZone: currentConfig.timezone, weekday: "long" };
  const dayOfWeek = new Intl.DateTimeFormat("pt-BR", dayOptions).format(now);

  return {
    globalEnabled: currentConfig.globalEnabled,
    hardOff: currentConfig.hardOff || false,
    hardOffAt: currentConfig.hardOffAt || null,
    hardOffBy: currentConfig.hardOffBy || null,
    businessHoursEnabled: currentConfig.businessHoursEnabled,
    isBusinessHours: inBusinessHours,
    botIsActive: check.shouldRespond,
    reason: check.reason,
    currentTime: currentTime + " BRT",
    dayOfWeek: dayOfWeek,
    businessHoursStart: currentConfig.businessHoursStart + ":00",
    businessHoursEnd: currentConfig.businessHoursEnd + ":00",
    schedule: "Bot LIGADO: 18h-12h (Seg-Sex) + 24h (Sab/Dom)",
    catchUpPending: _catchUpPending,
    disabledAt: currentConfig.disabledAt || null,
    lastUpdated: currentConfig.lastUpdated,
    updatedBy: currentConfig.updatedBy
  };
}

/**
 * v5.0: Hard OFF - desligamento permanente
 * Sem auto-reativação, sem catch-up, sem bypass
 */
function setHardOff(enabled, updatedBy = "API") {
  currentConfig.hardOff = enabled;
  currentConfig.updatedBy = updatedBy;

  if (enabled) {
    currentConfig.globalEnabled = false;
    currentConfig.hardOffAt = new Date().toISOString();
    currentConfig.hardOffBy = updatedBy;
    currentConfig.disabledAt = new Date().toISOString();
    // Limpar catch-up pendente
    _catchUpPending = false;
    _catchUpDisabledAt = null;
    console.log("[BOT-CONFIG] HARD OFF ativado por " + updatedBy + ". Bot PERMANENTEMENTE desativado.");
  } else {
    currentConfig.hardOff = false;
    currentConfig.hardOffAt = null;
    currentConfig.hardOffBy = null;
    currentConfig.globalEnabled = true;
    currentConfig.disabledAt = null;
    console.log("[BOT-CONFIG] HARD OFF desativado por " + updatedBy + ". Bot REATIVADO.");
  }

  const saved = saveConfig(currentConfig);
  return { success: saved, status: getStatus() };
}

/**
 * v5.0: Getter simples para outros módulos verificarem hard off
 */
function isHardOff() {
  return currentConfig.hardOff === true;
}

/**
 * v5.0: setGlobalEnabled agora usa Hard OFF para garantir que o bot
 * não se reative sozinho quando desligado manualmente.
 */
function setGlobalEnabled(enabled, updatedBy = "API") {
  if (!enabled) {
    // Desligar = Hard OFF (sem auto-reativação)
    return setHardOff(true, updatedBy);
  } else {
    // Ligar = desativar Hard OFF
    return setHardOff(false, updatedBy);
  }
}

function setBusinessHoursEnabled(enabled, updatedBy = "API") {
  currentConfig.businessHoursEnabled = enabled;
  currentConfig.updatedBy = updatedBy;
  const saved = saveConfig(currentConfig);
  console.log("[BOT-CONFIG] Business hours: " + (enabled ? "ON" : "OFF") + " por " + updatedBy);
  return { success: saved, status: getStatus() };
}

function updateConfig(updates, updatedBy = "API") {
  currentConfig = { ...currentConfig, ...updates };
  currentConfig.updatedBy = updatedBy;
  const saved = saveConfig(currentConfig);
  return { success: saved, status: getStatus() };
}

module.exports = {
  shouldBotRespond,
  isBusinessHours,
  isHardOff,
  getStatus,
  setGlobalEnabled,
  setHardOff,
  setBusinessHoursEnabled,
  updateConfig,
  loadConfig,
  consumeCatchUpEvent,
  isNeverContact
};
