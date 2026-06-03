/**
 * Generate WhatsApp Pairing Code using Baileys
 * Número: +1 (940) 618-3140
 */

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const pino = require('pino');

const PHONE_NUMBER = process.argv[2] || '19406183140';

async function generatePairingCode() {
  console.log('[BAILEYS] Iniciando para número:', PHONE_NUMBER);
  
  // Cria pasta de sessão temporária
  const sessionDir = '/tmp/baileys-session-' + Date.now();
  const fs = require('fs');
  fs.mkdirSync(sessionDir, { recursive: true });
  
  try {
    const { state, saveCreds } = await useMultiFileAuthState(sessionDir);
    
    const sock = makeWASocket({
      auth: state,
      printQRInTerminal: false,
      logger: pino({ level: 'silent' }),
      browser: ['CaseHub Bot', 'Chrome', '120.0.0']
    });
    
    // Quando não está registrado, solicita o código de pareamento
    sock.ev.on('connection.update', async (update) => {
      const { connection, lastDisconnect, qr } = update;
      
      if (qr) {
        console.log('[BAILEYS] QR Code disponível, mas vamos usar pairing code...');
        
        // Solicita código de pareamento
        try {
          console.log('[BAILEYS] Solicitando código de pareamento para:', PHONE_NUMBER);
          const code = await sock.requestPairingCode(PHONE_NUMBER);
          
          console.log('[BAILEYS] ================================================');
          console.log('[BAILEYS] CÓDIGO DE PAREAMENTO: ' + code);
          console.log('[BAILEYS] ================================================');
          console.log('[BAILEYS] Use este código no WhatsApp do celular:');
          console.log('[BAILEYS] 1. Abra WhatsApp');
          console.log('[BAILEYS] 2. Vá em Configurações > Dispositivos Vinculados');
          console.log('[BAILEYS] 3. Toque em "Vincular Dispositivo"');
          console.log('[BAILEYS] 4. Escolha "Vincular com número de telefone"');
          console.log('[BAILEYS] 5. Digite o código: ' + code);
          console.log('[BAILEYS] ================================================');
          
        } catch (err) {
          console.error('[BAILEYS] Erro ao solicitar código:', err.message);
        }
      }
      
      if (connection === 'close') {
        const reason = lastDisconnect?.error?.output?.statusCode;
        console.log('[BAILEYS] Conexão fechada, razão:', reason);
        
        if (reason === DisconnectReason.restartRequired) {
          console.log('[BAILEYS] Restart necessário, reiniciando...');
          // Não reinicia automaticamente
        }
      }
      
      if (connection === 'open') {
        console.log('[BAILEYS] Conectado com sucesso!');
        process.exit(0);
      }
    });
    
    sock.ev.on('creds.update', saveCreds);
    
    // Aguarda 60 segundos para dar tempo de usar o código
    await new Promise(resolve => setTimeout(resolve, 60000));
    
  } catch (error) {
    console.error('[BAILEYS] Erro:', error.message);
  }
  
  // Limpa a sessão temporária
  try {
    const fs = require('fs');
    fs.rmSync(sessionDir, { recursive: true, force: true });
  } catch (e) {}
}

generatePairingCode();
