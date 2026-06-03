/**
 * Baileys Pairing Service
 * Serviço para gerar códigos de pareamento via Baileys
 */

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require("@whiskeysockets/baileys");
const pino = require("pino");
const fs = require("fs");
const path = require("path");

const SESSION_DIR = `${process.env.APP_BASE_PATH || "/opt/casehub"}/whatsapp-bot/.baileys-session`;

let currentSocket = null;
let connectionStatus = "disconnected";
let lastQR = null;

// Garantir que o diretório de sessão existe
if (!fs.existsSync(SESSION_DIR)) {
  fs.mkdirSync(SESSION_DIR, { recursive: true });
}

/**
 * Gera código de pareamento
 */
async function generatePairingCode(phoneNumber) {
  return new Promise(async (resolve, reject) => {
    try {
      // Limpar número
      const cleanPhone = phoneNumber.replace(/\D/g, "");
      
      console.log("[BAILEYS-SERVICE] Gerando código para:", cleanPhone);
      
      // Criar nova sessão temporária para pareamento
      const tempDir = `/tmp/baileys-pairing-${Date.now()}`;
      fs.mkdirSync(tempDir, { recursive: true });
      
      const { state, saveCreds } = await useMultiFileAuthState(tempDir);
      
      const sock = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        logger: pino({ level: "silent" }),
        browser: ["CaseHub Bot", "Chrome", "120.0.0"],
      });
      
      let codeGenerated = false;
      let timeout = setTimeout(() => {
        if (!codeGenerated) {
          sock.end();
          fs.rmSync(tempDir, { recursive: true, force: true });
          reject(new Error("Timeout ao gerar código"));
        }
      }, 30000);
      
      sock.ev.on("creds.update", saveCreds);
      
      sock.ev.on("connection.update", async (update) => {
        const { connection, lastDisconnect, qr } = update;
        
        if (qr && !codeGenerated) {
          try {
            const code = await sock.requestPairingCode(cleanPhone);
            codeGenerated = true;
            clearTimeout(timeout);
            
            console.log("[BAILEYS-SERVICE] Código gerado:", code);
            
            // Manter conexão aberta por 2 minutos para o usuário digitar o código
            setTimeout(() => {
              sock.end();
              fs.rmSync(tempDir, { recursive: true, force: true });
            }, 120000);
            
            resolve({ success: true, code: code });
          } catch (e) {
            clearTimeout(timeout);
            sock.end();
            fs.rmSync(tempDir, { recursive: true, force: true });
            reject(e);
          }
        }
        
        if (connection === "open") {
          console.log("[BAILEYS-SERVICE] CONECTADO!");
          clearTimeout(timeout);
          
          // Salvar sessão permanente
          const files = fs.readdirSync(tempDir);
          for (const file of files) {
            fs.copyFileSync(
              path.join(tempDir, file),
              path.join(SESSION_DIR, file)
            );
          }
          
          sock.end();
          fs.rmSync(tempDir, { recursive: true, force: true });
          
          resolve({ success: true, connected: true, message: "WhatsApp conectado!" });
        }
        
        if (connection === "close") {
          const reason = lastDisconnect?.error?.output?.statusCode;
          console.log("[BAILEYS-SERVICE] Conexão fechada:", reason);
        }
      });
      
    } catch (error) {
      console.error("[BAILEYS-SERVICE] Erro:", error.message);
      reject(error);
    }
  });
}

/**
 * Verifica se há sessão salva
 */
function hasSession() {
  try {
    const files = fs.readdirSync(SESSION_DIR);
    return files.length > 0;
  } catch {
    return false;
  }
}

/**
 * Limpa sessão
 */
function clearSession() {
  try {
    fs.rmSync(SESSION_DIR, { recursive: true, force: true });
    fs.mkdirSync(SESSION_DIR, { recursive: true });
    return true;
  } catch {
    return false;
  }
}

module.exports = {
  generatePairingCode,
  hasSession,
  clearSession,
  SESSION_DIR
};
