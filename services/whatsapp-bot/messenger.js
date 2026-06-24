/**
 * Modulo Messenger - Facebook Bot
 * CaseHub
 * v2.0 - Integracao completa com fluxo de conversas
 */

const https = require('https');

const MESSENGER_CONFIG = {
  pageAccessToken: process.env.FB_PAGE_ACCESS_TOKEN || '',
  appSecret: process.env.FB_APP_SECRET || '',
  verifyToken: process.env.FB_VERIFY_TOKEN || 'ilc_messenger_verify_2024',
  pageId: process.env.FB_PAGE_ID || '111602090579376'
};

const isConfigured = Boolean(MESSENGER_CONFIG.pageAccessToken && MESSENGER_CONFIG.appSecret);

function requireConfigured() {
  if (!isConfigured) {
    throw new Error('FB_PAGE_ACCESS_TOKEN and FB_APP_SECRET env vars are required to use Messenger notifications.');
  }
}

/**
 * Enviar mensagem via Messenger
 */
async function sendMessage(recipientId, text) {
  if (!isConfigured) {
    return { success: false, error: 'messenger_not_configured' };
  }
  return new Promise((resolve, reject) => {
    const data = JSON.stringify({
      recipient: { id: recipientId },
      message: { text: text }
    });

    const options = {
      hostname: 'graph.facebook.com',
      port: 443,
      path: '/v18.0/me/messages?access_token=' + MESSENGER_CONFIG.pageAccessToken,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data)
      }
    };

    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(body);
          if (result.message_id) {
            console.log('[MESSENGER] Mensagem enviada:', result.message_id);
            resolve({ success: true, messageId: result.message_id });
          } else {
            console.error('[MESSENGER] Erro:', body);
            resolve({ success: false, error: body });
          }
        } catch (e) {
          resolve({ success: false, error: e.message });
        }
      });
    });

    req.on('error', (e) => {
      console.error('[MESSENGER] Erro de conexao:', e.message);
      resolve({ success: false, error: e.message });
    });

    req.write(data);
    req.end();
  });
}

/**
 * Enviar mensagem com botoes
 */
async function sendButtonMessage(recipientId, text, buttons) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify({
      recipient: { id: recipientId },
      message: {
        attachment: {
          type: 'template',
          payload: {
            template_type: 'button',
            text: text,
            buttons: buttons
          }
        }
      }
    });

    const options = {
      hostname: 'graph.facebook.com',
      port: 443,
      path: '/v18.0/me/messages?access_token=' + MESSENGER_CONFIG.pageAccessToken,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data)
      }
    };

    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(body);
          if (result.message_id) {
            resolve({ success: true, messageId: result.message_id });
          } else {
            resolve({ success: false, error: body });
          }
        } catch (e) {
          resolve({ success: false, error: e.message });
        }
      });
    });

    req.on('error', (e) => resolve({ success: false, error: e.message }));
    req.write(data);
    req.end();
  });
}

/**
 * Obter perfil do usuario
 */
async function getUserProfile(userId) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'graph.facebook.com',
      port: 443,
      path: '/v18.0/' + userId + '?fields=first_name,last_name,profile_pic&access_token=' + MESSENGER_CONFIG.pageAccessToken,
      method: 'GET'
    };

    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(body);
          if (result.first_name) {
            console.log('[MESSENGER] Perfil obtido:', result.first_name);
          }
          resolve(result);
        } catch (e) {
          resolve({ first_name: 'Usuario', last_name: '' });
        }
      });
    });

    req.on('error', () => resolve({ first_name: 'Usuario', last_name: '' }));
    req.end();
  });
}

/**
 * Buscar conversas da pagina
 */
async function getConversations(limit = 50) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'graph.facebook.com',
      port: 443,
      path: '/v18.0/me/conversations?fields=participants,messages.limit(5){message,from,created_time},updated_time,unread_count&limit=' + limit + '&access_token=' + MESSENGER_CONFIG.pageAccessToken,
      method: 'GET'
    };

    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          const result = JSON.parse(body);
          if (result.data) {
            resolve({ success: true, conversations: result.data });
          } else {
            console.error('[MESSENGER] Erro ao buscar conversas:', body);
            resolve({ success: false, error: body, conversations: [] });
          }
        } catch (e) {
          resolve({ success: false, error: e.message, conversations: [] });
        }
      });
    });

    req.on('error', (e) => resolve({ success: false, error: e.message, conversations: [] }));
    req.end();
  });
}

/**
 * Identificar conversas nao respondidas
 * Uma conversa e nao respondida se a ultima mensagem foi do usuario (nao da pagina)
 */
async function getUnreadConversations() {
  const result = await getConversations(100);

  if (!result.success || !result.conversations) {
    return [];
  }

  const unread = [];

  for (const conv of result.conversations) {
    try {
      // Verificar se tem mensagens
      if (!conv.messages || !conv.messages.data || conv.messages.data.length === 0) {
        continue;
      }

      // Pegar a ultima mensagem
      const lastMessage = conv.messages.data[0];

      // Verificar se a ultima mensagem foi do usuario (nao da pagina)
      const isFromUser = lastMessage.from && lastMessage.from.id !== MESSENGER_CONFIG.pageId;

      if (isFromUser) {
        // Pegar o ID do participante (usuario)
        const participant = conv.participants?.data?.find(p => p.id !== MESSENGER_CONFIG.pageId);

        if (participant) {
          unread.push({
            conversationId: conv.id,
            participantId: participant.id,
            participantName: participant.name || 'Usuario',
            lastMessage: lastMessage.message,
            lastMessageTime: lastMessage.created_time,
            unreadCount: conv.unread_count || 0
          });
        }
      }
    } catch (e) {
      console.error('[MESSENGER] Erro ao processar conversa:', e.message);
    }
  }

  console.log('[MESSENGER] Conversas nao respondidas:', unread.length);
  return unread;
}

/**
 * Processar mensagem recebida do webhook
 */
function parseWebhookMessage(body) {
  const messages = [];

  if (body.object === 'page' && body.entry) {
    body.entry.forEach(entry => {
      if (entry.messaging) {
        entry.messaging.forEach(event => {
          if (event.message && event.message.text) {
            messages.push({
              senderId: event.sender.id,
              recipientId: event.recipient.id,
              text: event.message.text,
              messageId: event.message.mid,
              timestamp: event.timestamp
            });
          }
        });
      }
    });
  }

  return messages;
}

/**
 * Marcar mensagens como lidas
 */
async function markSeen(recipientId) {
  return new Promise((resolve) => {
    const data = JSON.stringify({
      recipient: { id: recipientId },
      sender_action: 'mark_seen'
    });

    const options = {
      hostname: 'graph.facebook.com',
      port: 443,
      path: '/v18.0/me/messages?access_token=' + MESSENGER_CONFIG.pageAccessToken,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data)
      }
    };

    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => resolve({ success: true }));
    });

    req.on('error', () => resolve({ success: false }));
    req.write(data);
    req.end();
  });
}

/**
 * Mostrar indicador de digitacao
 */
async function showTyping(recipientId, on = true) {
  return new Promise((resolve) => {
    const data = JSON.stringify({
      recipient: { id: recipientId },
      sender_action: on ? 'typing_on' : 'typing_off'
    });

    const options = {
      hostname: 'graph.facebook.com',
      port: 443,
      path: '/v18.0/me/messages?access_token=' + MESSENGER_CONFIG.pageAccessToken,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(data)
      }
    };

    const req = https.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => resolve({ success: true }));
    });

    req.on('error', () => resolve({ success: false }));
    req.write(data);
    req.end();
  });
}

module.exports = {
  sendMessage,
  sendButtonMessage,
  getUserProfile,
  getConversations,
  getUnreadConversations,
  parseWebhookMessage,
  markSeen,
  showTyping,
  MESSENGER_CONFIG,
  isConfigured,
  requireConfigured
};
