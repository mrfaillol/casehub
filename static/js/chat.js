// ============================================
// STATE MANAGER - Centralized State
// ============================================
// v13.1: Debug logs removed for clean console

const State = {
    isConnected: false,
    selectedPhone: null,
    conversations: [],
    messages: [],
    botEnabled: true,
    neverContact: false,
    currentLeadData: null,  // Cached lead data for templates

    // Polling state
    statusPoller: null,
    messagesPoller: null,
    lastConversationsLoad: 0,  // Debounce para loadConversations
    qrPoller: null,

    // v13.0: SSE state
    messagesSSE: null,
    conversationsSSE: null,
    sseConnected: false,

    // Backoff
    backoff: 1000,
    maxBackoff: 30000,

    setConnected(connected) {
        this.isConnected = connected;
        updateStatusUI();
    },

    setSelectedPhone(phone) {
        this.selectedPhone = phone;
    },

    cleanup() {
        if (this.statusPoller) clearTimeout(this.statusPoller);
        if (this.messagesPoller) clearInterval(this.messagesPoller);
        if (this.qrPoller) clearInterval(this.qrPoller);
        if (this.messagesSSE) { this.messagesSSE.close(); this.messagesSSE = null; }
        if (this.conversationsSSE) { this.conversationsSSE.close(); this.conversationsSSE = null; }
    }
};
window.State = State;

// ============================================
// TEMPLATES OFICIAIS (extraídos do Google Docs Admin/Templates)
// Atualizado em: 2026-01-29
// ============================================
const TEMPLATES = [
    // Templates Example Legal Advogados (advocacia BR) — PIX, horário de Brasília
    { id: 1, cat: "Saudação", name: "Primeiro Contato", text: "Olá! Seja bem-vindo(a) ao escritório Example Legal Advogados. 👋\n\nObrigado pelo seu contato. Para que possamos te ajudar da melhor forma, poderia nos informar seu nome completo e um breve resumo da sua questão?\n\nAssim direcionamos seu atendimento ao advogado da área adequada (cível, trabalhista, família, empresarial, entre outras).\n\nEstamos à disposição!" },
    { id: 2, cat: "Saudação", name: "Resposta Rápida", text: "Prezado(a) [NOME],\n\nMuito obrigado pelo seu retorno.\n\nCaso surja qualquer dúvida ou precise de informações adicionais, estamos à inteira disposição.\n\nAtenciosamente,\nExample Legal Advogados" },
    { id: 3, cat: "Agenda", name: "Confirmação de Reunião", text: "Prezado(a) [NOME],\n\nSua reunião com o(a) Dr.(a) [ADVOGADO] está confirmada para o dia [DATA], às [HORARIO] (horário de Brasília).\n\nLocal/link: [LOCAL]\n\nCaso precise remarcar, por gentileza nos avise com antecedência. Até lá!\n\nAtenciosamente,\nExample Legal Advogados" },
    { id: 4, cat: "Agenda", name: "Sugestão de Horário", text: "Olá, [NOME]!\n\nTemos disponibilidade para sua reunião com o(a) Dr.(a) [ADVOGADO] no dia [DATA], às [HORARIO] (horário de Brasília).\n\nEsse horário funciona para você? Se preferir, indique outras opções e nos ajustamos.\n\nApós a confirmação, enviaremos o convite com todos os detalhes." },
    { id: 5, cat: "Agenda", name: "Lembrete de Audiência", text: "Prezado(a) [NOME],\n\nLembrete importante: sua audiência do processo [PROCESSO] está marcada para o dia [DATA], às [HORARIO] (horário de Brasília), na [VARA].\n\nOrientações:\n• Chegue com 30 min de antecedência (ou conecte-se ao link 10 min antes, se virtual);\n• Leve documento de identificação com foto;\n• Em caso de dúvida, fale conosco.\n\nEstamos à disposição." },
    { id: 6, cat: "Agenda", name: "Reagendamento", text: "Prezado(a) [NOME],\n\nComo não recebemos a confirmação, a reunião não foi mantida na agenda. Teremos prazer em remarcar no melhor horário para você.\n\nPodemos reagendar para [DATA] às [HORARIO] (horário de Brasília)? Caso não seja conveniente, indique duas ou três alternativas.\n\nAgradecemos a compreensão." },
    { id: 7, cat: "Honorários", name: "Proposta de Honorários", text: "Prezado(a) [NOME],\n\nConforme conversamos, segue a proposta de honorários para a sua demanda ([ASSUNTO]):\n\n• Valor: R$ [VALOR]\n• Forma de pagamento: à vista (com desconto) ou parcelado\n\nOs valores seguem os parâmetros da Tabela da OAB. Após o aceite, formalizamos o contrato de prestação de serviços.\n\nFico à disposição para esclarecer qualquer ponto." },
    { id: 8, cat: "Honorários", name: "Dados para Pagamento (PIX)", text: "Prezado(a) [NOME],\n\nSegue abaixo os dados para pagamento dos honorários:\n\n💳 PIX\nChave: [CHAVE_PIX]\nFavorecido: Example Legal Advogados\nValor: R$ [VALOR]\n\nApós o pagamento, por gentileza envie o comprovante para darmos andamento.\n\nObrigado!" },
    { id: 9, cat: "Honorários", name: "Confirmação de Pagamento", text: "Prezado(a) [NOME],\n\nConfirmamos o recebimento do seu pagamento. ✅\n\nMuito obrigado pela confiança. Seguimos cuidando do seu caso com toda a atenção.\n\nQualquer dúvida, estamos à disposição.\n\nAtenciosamente,\nExample Legal Advogados" },
    { id: 10, cat: "Honorários", name: "Lembrete de Parcela", text: "Olá, [NOME]!\n\nLembrete amigável: a parcela no valor de R$ [VALOR] referente aos honorários vence em [DATA].\n\nDados para pagamento (PIX):\nChave: [CHAVE_PIX]\nFavorecido: Example Legal Advogados\n\nAssim que efetuar, é só nos enviar o comprovante. Obrigado!" },
    { id: 11, cat: "Documentos", name: "Solicitação de Documentos", text: "Olá, [NOME]! Esperamos que esteja bem.\n\nPara darmos andamento ao seu caso, precisamos dos seguintes documentos:\n\n[LISTA_DOCUMENTOS]\n\nVocê pode enviá-los aqui mesmo pelo WhatsApp (foto ou PDF). Se tiver dúvida sobre algum, é só perguntar!\n\nObrigado." },
    { id: 12, cat: "Documentos", name: "Confirmação de Recebimento", text: "Prezado(a) [NOME],\n\nRecebemos os documentos enviados — muito obrigado. ✅\n\nNossa equipe fará a conferência e, havendo qualquer pendência, entraremos em contato.\n\nSeguimos à disposição." },
    { id: 13, cat: "Processo", name: "Atualização de Andamento", text: "Prezado(a) [NOME],\n\nAtualização do seu processo [PROCESSO]:\n\n[ANDAMENTO]\n\nSeguiremos acompanhando e informaremos qualquer novidade relevante. Caso tenha dúvidas, estamos à disposição.\n\nAtenciosamente,\nExample Legal Advogados" },
    { id: 14, cat: "Processo", name: "Decisão Publicada", text: "Prezado(a) [NOME],\n\nInformamos que houve uma nova decisão no processo [PROCESSO]:\n\n[RESUMO_DECISAO]\n\nJá estamos analisando os próximos passos e em breve traremos nossa recomendação. Qualquer dúvida, conte conosco." },
    { id: 15, cat: "Processo", name: "Providência / Prazo", text: "Prezado(a) [NOME],\n\nPrecisamos de uma providência sua para cumprir um prazo do processo [PROCESSO]:\n\n[PROVIDENCIA]\n\nPrazo para nos retornar: até [DATA].\n\nÉ importante para mantermos tudo em dia. Qualquer dúvida, estamos aqui!" },
    { id: 16, cat: "Follow-up", name: "Sem Retorno", text: "Olá, [NOME]!\n\nAinda não tivemos seu retorno e gostaríamos de saber se podemos ajudar em algo.\n\nSe preferir, podemos agendar uma conversa com um de nossos advogados. É só nos dizer o melhor horário.\n\nEstamos à disposição!" },
    { id: 17, cat: "Follow-up", name: "Encaminhado ao Jurídico", text: "Olá!\n\nSua mensagem foi encaminhada à nossa equipe jurídica para análise. Retornaremos com um posicionamento o mais breve possível.\n\nAgradecemos o contato e a confiança.\n\nAtenciosamente,\nExample Legal Advogados" },
    { id: 18, cat: "Atendimento", name: "Assumindo Conversa", text: "Olá! Meu nome é [ADVOGADO] e darei sequência ao seu atendimento a partir de agora.\n\nJá revisei o histórico da conversa. Como posso ajudá-lo(a) hoje?" },
    { id: 19, cat: "Atendimento", name: "Fora do Horário", text: "Olá! Obrigado pelo seu contato. 🙏\n\nNosso horário de atendimento é de segunda a sexta, das 9h às 18h (horário de Brasília).\n\nSua mensagem foi registrada e retornaremos no próximo dia útil. Em caso de urgência, deixe o assunto detalhado que daremos prioridade.\n\nAtenciosamente,\nExample Legal Advogados" },
    { id: 20, cat: "Consulta", name: "Confirmação de Consulta", text: "Prezado(a) [NOME],\n\nSua consulta está confirmada:\n• Data: [DATA]\n• Horário: [HORARIO] (horário de Brasília)\n• Com: Dr.(a) [ADVOGADO]\n\nPara aproveitarmos melhor o tempo, se possível envie com antecedência os documentos e um resumo do que deseja tratar.\n\nAté lá!" },
    { id: 21, cat: "Consulta", name: "Pós-Consulta", text: "Olá, [NOME]! Obrigado pela consulta de hoje.\n\nResumo do que conversamos:\n• [PONTO_1]\n• [PONTO_2]\n\nPróximos passos:\n1. [ACAO_1]\n2. [ACAO_2]\n\nQualquer dúvida, estamos à disposição!" },
    { id: 22, cat: "Encerramento", name: "Padrão", text: "Obrigado pelo contato! 🙏\n\nSe tiver mais dúvidas, estaremos à disposição.\n\nTenha um excelente dia!\nExample Legal Advogados" }
];

const CATEGORIES = ['Greeting', 'Agenda', 'Pagamento', 'Onboarding', 'Vistos', 'Follow-up', 'Consulta', 'Handoff', 'Final', 'Interno'];

// ============================================
// API FUNCTIONS - With proper error handling
// ============================================
// Timeout values by operation type (in ms)
const API_TIMEOUTS = {
    default: 15000,       // 15s for simple operations
    send: 30000,          // 30s for sending messages
    ai: 30000,            // 30s for AI operations
    media: 60000,         // 60s for media uploads
    pairing: 60000        // 60s for pairing code
};
const WHATSAPP_API_BASE =
    (typeof window !== 'undefined' && window.WA_API_BASE) ||
    (typeof WA_API_BASE !== 'undefined' && WA_API_BASE) ||
    ((typeof CASEHUB_PREFIX !== 'undefined' ? CASEHUB_PREFIX : '/casehub') + '/whatsapp-chat');

async function fetchAPI(url, options = {}, timeoutMs = API_TIMEOUTS.default) {
    // Route /api/* calls to the WhatsApp page router (the complete API)
    if (url.startsWith('/api/')) {
        url = WHATSAPP_API_BASE + url;
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    try {
        const response = await fetch(url, {
            ...options,
            signal: controller.signal
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        // Verify server returned JSON before parsing
        const contentType = response.headers.get('content-type') || '';
        if (!contentType.includes('application/json')) {
            const text = await response.text();
            console.error('[fetchAPI] Server returned non-JSON:', response.status, text.substring(0, 200));
            throw new Error(`Servidor indisponível (${response.status})`);
        }
        return await response.json();
    } finally {
        clearTimeout(timeout);
    }
}

// ============================================
// STATUS CHECK
// ============================================
async function checkStatus() {
    try {
        const data = await fetchAPI('/api/status');
        const connected = data.connected || data.ok;

        State.status = data.status || (connected ? 'ready' : 'unknown');
        State.setConnected(connected);
        State.backoff = 1000; // Reset backoff on success

        if (connected) {
            loadConversations(true);
            startConversationsSSE(); // v13.1: Keep conversation list live
            // v13.0: Use SSE first, polling as fallback
            if (State.selectedPhone) startMessagesSSE();
            stopQRPolling();
        } else {
            stopMessagesSSE();
            stopMessagesPolling();
            startQRPolling();
            // #5 — durante o boot da sessao (connecting/loading), antes de
            // qualquer fetch bem-sucedido, mostra o aviso de carregamento na
            // lista em vez de deixar o "Carregando..." generico do template.
            if (!conversationsLoaded && isBotLoading()) renderConversations();
        }
    } catch (error) {
        console.error('[Status] Error:', error.message);
        State.status = 'timeout';
        State.setConnected(false);
        State.backoff = Math.min(State.backoff * 2, State.maxBackoff);
        if (!conversationsLoaded && isBotLoading()) renderConversations();
    }

    // Schedule next check
    State.statusPoller = setTimeout(checkStatus, State.backoff < 15000 ? 15000 : State.backoff);
}

// Force reconnect function
async function forceReconnect() {
    console.log("[RECONNECT] Forcing reconnect...");
    const btn = document.getElementById("reconnectBtn");
    if (btn) {
        btn.textContent = "Reconectando...";
        btn.disabled = true;
    }
    
    // Clear state
    State.isConnected = false;
    State.messages = [];
    State.conversations = [];
    State.backoff = 1000;
    
    // Stop all pollers and SSE
    stopMessagesSSE();
    stopMessagesPolling();
    stopConversationsSSE();
    stopQRPolling();
    if (State.statusPoller) clearTimeout(State.statusPoller);
    
    try {
        const data = await fetchAPI('/api/reconnect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        }, API_TIMEOUTS.send);
        State.status = data.status || 'reconnecting';
    } catch (error) {
        console.error("[RECONNECT] Error:", error.message);
        State.status = 'timeout';
    } finally {
        await checkStatus();
        if (btn) {
            btn.textContent = "Reconectar";
            btn.disabled = false;
        }
        console.log("[RECONNECT] Done, connected:", State.isConnected);
    }
}


// #5 (Example User 02/06) — true enquanto o bot esta subindo a sessao (conectando/
// carregando) mas ainda nao caiu nem pediu QR. Usado para mostrar o aviso
// "Carregando conversas… (primeira conexao pode levar alguns segundos)".
// 'qr'/'awaiting_scan'/'disconnected' tem fluxo proprio (QR) e NAO contam.
function isBotLoading() {
    if (State.isConnected) return false;
    const s = String(State.status || '').toLowerCase();
    if (s === 'qr' || s === 'awaiting_scan' || s === 'auth_failed') return false;
    // Treats 'disconnected' as partially loading/reconnecting unless confirmed dead.
    return s === '' || s === 'connecting' || s === 'loading' || s === 'starting' ||
        s === 'initializing' || s === 'unknown' || s === 'timeout' || s === 'disconnected';
}

function disconnectReason(status) {
    switch (String(status || '').toLowerCase()) {
        case 'awaiting_scan':
        case 'qr': return 'aguardando a leitura do QR Code';
        case 'timeout': return 'sem resposta do servidor do WhatsApp';
        case 'connecting': return 'conectando…';
        case 'disconnected': return 'a sessão foi encerrada';
        case 'unknown': return 'status indisponível';
        default: return status ? ('estado: ' + status) : 'motivo desconhecido';
    }
}

function setConnectStateText(text) {
    const el = document.getElementById('waConnectStateText');
    if (el) el.textContent = text;
}
window.setConnectStateText = setConnectStateText;

function updateStatusUI() {
    const badge = document.getElementById('statusBadge');
    const text = document.getElementById('statusText');
    const emptyState = document.getElementById('emptyState');
    const qrState = document.getElementById('qrState');
    const activeChat = document.getElementById('activeChat');
    const discBar = document.getElementById('waDisconnectBar');

    if (State.isConnected) {
        setConnectStateText('Conectado');
        if (discBar) discBar.hidden = true;
        badge.className = 'wa-status connected';
        text.textContent = 'Conectado';
        // Deixa claro que a sessão é da firma (compartilhada com toda a equipe).
        if (badge) badge.title = 'WhatsApp da firma — conectado e compartilhado com toda a equipe';
        const reconnectBtn = document.getElementById('reconnectBtn');
        if (reconnectBtn) reconnectBtn.style.display = 'none';
        // Hide QR; show empty state only when no conversation is open.
        if (qrState) qrState.classList.remove('show');
        if (!State.selectedPhone) {
            if (emptyState) emptyState.style.display = 'flex';
            if (activeChat) { activeChat.hidden = true; activeChat.style.display = 'none'; }
        }
    } else {
        setConnectStateText(disconnectReason(State.status));
        if (discBar) {
            if (isBotLoading()) {
                discBar.hidden = true;
            } else {
                discBar.hidden = false;
                const rEl = document.getElementById('waDisconnectReason');
                if (rEl) rEl.textContent = disconnectReason(State.status);
            }
        }
        badge.className = 'wa-status disconnected';
        text.textContent = (State.selectedPhone ? 'Desconectado' : 'Reconectando — escaneie o QR');
        const reconnectBtn2 = document.getElementById('reconnectBtn');
        if (reconnectBtn2) reconnectBtn2.style.display = 'inline-block';
        // Disconnected: the chat pane shows the QR/pairing flow.
        if (emptyState) emptyState.style.display = 'none';
        if (!State.selectedPhone) {
            if (activeChat) { activeChat.hidden = true; activeChat.style.display = 'none'; }
            if (qrState) qrState.classList.add('show');
            loadQRCode();
        }
    }
}

// ============================================
// QR CODE
// ============================================
async function loadQRCode() {
    const container = document.getElementById('qrCode');
    if (!container) return;

    try {
        const data = await fetchAPI('/api/qr');

        if (data.qr) {
            // data.qr is a data: URI (image) produced by the bot.
            setConnectStateText('Aguardando leitura do QR');
            container.innerHTML = `<img src="${escapeHtml(data.qr)}" alt="QR code para conectar o WhatsApp">`;
        } else if (data.connected) {
            // Bot connected between polls — reflect it immediately.
            setConnectStateText('Conectado');
            container.innerHTML = `<div class="wa-loading"><div class="wa-spinner" aria-hidden="true"></div>Conectando...</div>`;
        } else {
            setConnectStateText(disconnectReason(data.status || State.status));
            container.innerHTML = `<p style="color: var(--wa-text-secondary);">QR indisponível</p>`;
        }

        // Pairing-code fallback (bot may emit it alongside the QR).
        // Guard typeof: updatePairingCode pode não estar definida em todos os
        // builds. Sem guard era ReferenceError → catch → QR nunca renderizava.
        if (typeof updatePairingCode === 'function') {
            updatePairingCode(data.pairingCode || data.code || data.pairing_code);
        }
    } catch (error) {
        // Race condition: bot pode estar iniciando session na primeira carga
        // do tenant. Mostrar mensagem mais útil + auto-retry em 3s.
        console.warn('[loadQRCode] retry em 3s:', error && error.message);
        container.innerHTML = `<div class="wa-loading"><div class="wa-spinner" aria-hidden="true"></div>Aguardando QR…</div>`;
        setTimeout(() => { loadQRCode(); }, 3000);
    }
}

function startQRPolling() {
    if (State.qrPoller) return;

    State.qrPoller = setInterval(() => {
        if (!State.isConnected) {
            loadQRCode();
        } else {
            stopQRPolling();
        }
    }, 5000);
}

function stopQRPolling() {
    if (State.qrPoller) {
        clearInterval(State.qrPoller);
        State.qrPoller = null;
    }
}

function setConnectMode(mode) {
    // Plano B sempre visível: mostra o seletor QR/Telefone quando o painel de
    // conexão aparece (antes ficava hidden e o pareamento por código nunca era
    // alcançável — útil quando o WhatsApp bloqueia novos dispositivos no QR).
    const modeBar = document.getElementById('waConnectMode');
    if (modeBar) modeBar.hidden = false;
    const qrCode = document.getElementById('qrCode');
    const phonePairing = document.getElementById('phonePairing');
    const qrHint = document.getElementById('qrRefreshHint');
    const qrBtn = document.getElementById('waQrModeBtn');
    const phoneBtn = document.getElementById('waPhoneModeBtn');
    const isPhone = mode === 'phone';

    if (qrCode) qrCode.hidden = isPhone;
    if (phonePairing) phonePairing.hidden = !isPhone;
    setConnectStateText(isPhone ? 'Aguardando código por telefone' : 'Aguardando leitura do QR');
    if (qrHint) qrHint.textContent = isPhone
        ? 'Use o codigo exibido no WhatsApp do celular para parear este navegador.'
        : 'Abra o WhatsApp no celular > Aparelhos conectados > Conectar aparelho.';
    if (qrBtn) {
        qrBtn.classList.toggle('active', !isPhone);
        qrBtn.setAttribute('aria-pressed', String(!isPhone));
    }
    if (phoneBtn) {
        phoneBtn.classList.toggle('active', isPhone);
        phoneBtn.setAttribute('aria-pressed', String(isPhone));
    }
}

function showQrConnect() {
    const emptyState = document.getElementById('emptyState');
    const qrState = document.getElementById('qrState');
    if (emptyState) emptyState.style.display = 'none';
    if (qrState) {
        qrState.hidden = false;
        qrState.style.display = 'flex';
    }
    setConnectMode('qr');
    loadQRCode();
    startQRPolling();
}

function showPhoneConnect() {
    const emptyState = document.getElementById('emptyState');
    const qrState = document.getElementById('qrState');
    if (emptyState) emptyState.style.display = 'none';
    if (qrState) {
        qrState.hidden = false;
        qrState.style.display = 'flex';
    }
    stopQRPolling();
    setConnectMode('phone');
    const input = document.getElementById('pairingPhone');
    if (input) input.focus();
}

async function requestPairingCode() {
    const input = document.getElementById('pairingPhone');
    const resultEl = document.getElementById('pairingResult');
    const btn = document.getElementById('pairingCodeBtn');
    const phone = input ? input.value.trim() : '';
    if (!phone) {
        if (resultEl) resultEl.textContent = 'Digite o numero com DDD e pais.';
        if (input) input.focus();
        return;
    }
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Gerando...';
    }
    if (resultEl) resultEl.textContent = 'Solicitando codigo de pareamento...';
    try {
        const data = await fetchAPI('/api/pairing-code', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone })
        }, API_TIMEOUTS.pairing);
        const code = data.pairingCode || data.code || data.pairing_code;
        if (code) {
            if (resultEl) {
                resultEl.innerHTML = 'Codigo de pareamento:<br><code>' + escapeHtml(String(code)) + '</code>';
            }
            State.setConnected(false);
        } else {
            const msg = data.error || 'Codigo ainda nao disponivel. Tente novamente em alguns segundos.';
            if (resultEl) resultEl.textContent = msg;
        }
    } catch (error) {
        if (resultEl) resultEl.textContent = 'Nao foi possivel gerar o codigo agora.';
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Gerar codigo';
        }
    }
}

function applyConnectionQueryMode() {
    const params = new URLSearchParams(window.location.search || '');
    const mode = params.get('connect');
    if (mode === 'phone') {
        showPhoneConnect();
    } else if (mode === 'qr') {
        showQrConnect();
    }
}

// ============================================
// CONVERSATIONS
// ============================================
let profilePicRefreshDone = false;
let conversationsLoaded = false;          // true once a fetch has ever succeeded
let conversationsRetry = null;            // pending retry timer
let conversationsBackoff = 2000;          // ms, doubles up to 30s
let initialPhoneSelectionDone = false;    // deep-link ?phone=<number>
const CONV_MAX_BACKOFF = 30000;

// Renders an error state into the conversation list so the sidebar
// never hangs on "Carregando...". Doherty: a visible state + auto-retry
// keeps the user informed instead of staring at a dead spinner.
function renderConversationsError(message) {
    const container = document.getElementById('conversationsList');
    if (!container) return;
    container.setAttribute('aria-busy', 'false');
    const secs = Math.round(conversationsBackoff / 1000);
    container.innerHTML = `
        <div class="wa-error-state" role="alert">
            <i class="fas fa-triangle-exclamation wa-error-icon" aria-hidden="true"></i>
            <div class="wa-error-title">Não foi possível carregar as conversas</div>
            <div class="wa-error-desc">${escapeHtml(message || 'Falha de conexão com o servidor.')}</div>
            <button type="button" class="wa-error-retry" onclick="loadConversations(true)">
                <i class="fas fa-rotate-right" aria-hidden="true"></i> Tentar agora
            </button>
            <span class="wa-error-auto">
                <i class="fas fa-spinner" aria-hidden="true"></i>
                Nova tentativa automática em ~${secs}s
            </span>
        </div>`;
}

function phoneDigits(value) {
    return String(value || '').replace(/\D/g, '');
}

function selectInitialPhoneFromQuery() {
    if (initialPhoneSelectionDone || !Array.isArray(State.conversations) || !State.conversations.length) return;
    const params = new URLSearchParams(window.location.search || '');
    const target = params.get('phone');
    if (!target) return;
    const targetDigits = phoneDigits(target);
    const match = State.conversations.find(c =>
        c.phone === target ||
        phoneDigits(c.phone).endsWith(targetDigits) ||
        targetDigits.endsWith(phoneDigits(c.phone))
    );
    if (!match) return;
    initialPhoneSelectionDone = true;
    selectConversation(match.phone);
}

async function loadConversations(force = false) {
    // Debounce: só carregar a cada 30 segundos (exceto se forçado)
    const now = Date.now();
    if (!force && (now - State.lastConversationsLoad) < 30000) {
        return;
    }
    State.lastConversationsLoad = now;

    // Cancel any pending retry — this call supersedes it.
    if (conversationsRetry) { clearTimeout(conversationsRetry); conversationsRetry = null; }

    const container = document.getElementById('conversationsList');
    if (container && !conversationsLoaded) container.setAttribute('aria-busy', 'true');

    try {
        const data = await fetchAPI('/api/conversations');
        State.conversations = Array.isArray(data) ? data : [];
        conversationsLoaded = true;
        conversationsBackoff = 2000; // reset backoff on success
        renderConversations();
        selectInitialPhoneFromQuery();
        if (container) container.setAttribute('aria-busy', 'false');
        // v13.1: First load triggers profile pic fetch in backend.
        // Refetch after 8s to pick up cached pics.
        if (!profilePicRefreshDone && State.conversations.some(c => !c.profilePic)) {
            profilePicRefreshDone = true;
            setTimeout(() => loadConversations(true), 8000);
        }
    } catch (error) {
        console.error('[Conversations] Error:', error.message);
        // If we already have data, keep showing it; otherwise show the
        // error state so the page never hangs on "Carregando...".
        if (!conversationsLoaded) {
            renderConversationsError(
                error.name === 'AbortError'
                    ? 'O servidor demorou demais para responder.'
                    : error.message
            );
        } else if (error.name === 'AbortError') {
            showNotification('Timeout ao carregar conversas', 'warning');
        }
        // Schedule an automatic retry with exponential backoff.
        conversationsRetry = setTimeout(() => {
            conversationsRetry = null;
            loadConversations(true);
        }, conversationsBackoff);
        conversationsBackoff = Math.min(conversationsBackoff * 2, CONV_MAX_BACKOFF);
    }
}

// ============================================
// CONTACT TYPE BADGES
// ============================================
const CONTACT_TYPE_LABELS = {
    lead: "Lead",
    active_client: "Cliente",
    past_client: "Ex-Cliente",
    partner: "Parceiro",
    other: "Outro",
    blocked: "Bloqueado"
};

function getContactTypeBadge(type) {
    if (!type || type === "lead") return ""; // Leads não mostram badge (é o padrão)
    const label = CONTACT_TYPE_LABELS[type] || type;
    const safeType = String(type).replace(/[^a-z0-9_-]/gi, '');
    return ` <span class="contact-type-badge ${safeType}">${escapeHtml(label)}</span>`;
}

function getConversationTimestamp(conversation) {
    const raw = conversation.lastMessageTime || conversation.last_message_time || conversation.last_message_at ||
        conversation.updated_at || conversation.created_at || conversation.timestamp;
    if (!raw) return 0;
    const time = new Date(raw).getTime();
    return Number.isFinite(time) ? time : 0;
}

function getConversationTime(conversation) {
    const raw = conversation.lastMessageTime || conversation.last_message_time || conversation.last_message_at ||
        conversation.updated_at || conversation.created_at || conversation.timestamp;
    return raw ? formatTime(raw) : '';
}

function getLinkedBadges(conversation) {
    const clientRef = conversation.client_name || conversation.clientName ||
        conversation.client_id || conversation.clientId || conversation.client?.name || conversation.client?.id;
    const caseRef = conversation.case_number || conversation.caseNumber || conversation.case_id || conversation.caseId ||
        conversation.process_number || conversation.processNumber || conversation.process_id || conversation.processId;
    const badges = [];

    if (clientRef || conversation.contact_type === 'active_client') {
        badges.push('<span class="wa-link-badge wa-link-badge--client">Cliente</span>');
    }
    if (caseRef) {
        badges.push('<span class="wa-link-badge wa-link-badge--case">Processo</span>');
    }
    if (!badges.length && conversation.contact_type === 'lead') {
        badges.push('<span class="wa-link-badge wa-link-badge--lead">Lead</span>');
    }
    if (!badges.length) {
        badges.push('<span class="wa-link-badge wa-link-badge--muted">Sem vínculo</span>');
    }
    return badges.join('');
}

// NOTA: ha uma segunda declaracao de renderAvatarContent mais abaixo (com o
// suporte completo a foto/grupo/maestro) que prevalece em runtime por hoisting.
// Esta mantem o mesmo comportamento para nao divergir caso seja chamada antes.
function renderAvatarContent(conversation, name) {
    const initials = escapeHtml(getInitials(name));
    const kind = classifyAvatarKind(conversation, name);

    if (kind === 'maestro') {
        return `<img class="wa-avatar-img wa-avatar--maestro" src="${MAESTRO_AVATAR_SRC}" alt="${escapeHtml(name)}" `
            + `onerror="this.hidden=true;this.nextElementSibling.hidden=false">`
            + `<span class="wa-avatar-icon" hidden aria-hidden="true"><i class="fas fa-robot"></i></span>`;
    }

    if (kind === 'group') {
        return `<span class="wa-avatar-icon" aria-hidden="true"><i class="fas fa-users"></i></span>`;
    }

    const profilePic = getConversationPhoto(conversation);
    if (profilePic) {
        return `<img class="wa-avatar-img" src="${escapeHtml(profilePic)}" alt="${escapeHtml(name)}" onerror="this.hidden=true;this.nextElementSibling.hidden=false">` +
            `<span class="wa-avatar-fallback" hidden>${initials}</span>`;
    }
    return `<span class="wa-avatar-fallback">${initials}</span>`;
}

function normalizeSearchValue(value) {
    return value == null ? '' : String(value).toLowerCase();
}

function renderConversations() {
    const container = document.getElementById('conversationsList');
    const searchQuery = normalizeSearchValue(document.getElementById('searchInput').value);

    let filtered = State.conversations;
    if (searchQuery) {
        filtered = filtered.filter(c =>
            normalizeSearchValue(c.name).includes(searchQuery) ||
            normalizeSearchValue(c.whatsapp_name).includes(searchQuery) ||
            normalizeSearchValue(c.phone).includes(searchQuery) ||
            normalizeSearchValue(c.lastMessage).includes(searchQuery) ||
            normalizeSearchValue(c.client_name || c.clientName).includes(searchQuery) ||
            normalizeSearchValue(c.case_number || c.caseNumber || c.process_number || c.processNumber).includes(searchQuery)
        );
    }

    switch (currentFilter) {
        case 'unread':
            filtered = filtered.filter(c => parseInt(c.unread) > 0);
            break;
        case 'needs-response':
            filtered = filtered.filter(c => (c.from_bot === 0 || c.from_bot === false) && parseInt(c.unread) > 0);
            break;
        case 'human':
            filtered = filtered.filter(c => c.human_takeover === 1 || c.human_takeover === true);
            break;
        case 'urgent':
            filtered = filtered.filter(c => urgentConversations.has(c.phone));
            break;
    }

    if (filtered.length === 0) {
        // #5 (Example User 02/06) — primeira conexao: enquanto o bot ainda esta
        // conectando/carregando e nenhuma conversa foi buscada com sucesso,
        // mostra um aviso de carregamento em vez de "Nenhuma conversa ainda".
        // Doherty: estado visivel evita a percepcao de tela vazia/travada.
        if (State.conversations.length === 0 && !conversationsLoaded && isBotLoading()) {
            container.innerHTML = `
                <div class="wa-loading" role="status" aria-live="polite">
                    <div class="wa-spinner" aria-hidden="true"></div>
                    <div>Carregando conversas…</div>
                    <small class="wa-loading-hint">A primeira conexão pode levar alguns segundos.</small>
                </div>`;
            return;
        }
        container.innerHTML = `<div class="wa-empty-list">
            ${State.conversations.length === 0 ? 'Nenhuma conversa ainda' : 'Nenhum resultado encontrado'}
        </div>`;
        return;
    }

    container.innerHTML = filtered.map(c => {
        const name = getConversationDisplayName(c);
        const phoneLabel = formatPhone(c.phone);
        const time = c.lastMessageTime ? formatTime(c.lastMessageTime) : '';
        const isActive = c.phone === State.selectedPhone;
        const preview = c.lastMessage ? truncate(c.lastMessage, 54) : 'Sem mensagens';
        const isPinned = pinnedSet.has(c.phone);
        const isMuted = mutedSet.has(c.phone);

        // Indicadores de status
        const needsResponse = c.from_bot === 0 || c.from_bot === false;
        const unreadCount = parseInt(c.unread) || 0;
        const isHumanTakeover = c.human_takeover === 1 || c.human_takeover === true;
        const isNeverContact = c.never_contact === 1 || c.never_contact === true;
        const isUrgent = urgentConversations.has(c.phone);
        let responseTimeBadge = '';
        if (needsResponse && c.updated_at) {
            const hoursSince = (Date.now() - new Date(c.updated_at).getTime()) / (1000 * 60 * 60);
            if (hoursSince > 24) {
                responseTimeBadge = `<span class="wa-response-time urgent">${Math.floor(hoursSince / 24)}d</span>`;
            } else if (hoursSince > 4) {
                responseTimeBadge = `<span class="wa-response-time">${Math.floor(hoursSince)}h</span>`;
            }
        }

        // Classes adicionais baseadas no status
        const extraClasses = [];
        if (needsResponse && unreadCount > 0) extraClasses.push('needs-response');
        if (isHumanTakeover) extraClasses.push('human-takeover');
        if (isNeverContact) extraClasses.push('never-contact');
        if (isUrgent) extraClasses.push('urgent');
        if (isPinned) extraClasses.push('pinned');

        const avatarContent = renderAvatarContent(c, name);
        const avatarStyle = getAvatarGradientStyle(c.phone || name);
        const avatarWrapClass = getAvatarWrapperClass(c, name);

        return `
            <div class="wa-conversation ${isActive ? 'active' : ''} ${extraClasses.join(' ')}" onclick="selectConversation('${c.phone}')">
                <div class="wa-avatar${avatarWrapClass}" style="${avatarStyle}">${avatarContent}</div>
                <div class="wa-conv-info">
                    <div class="wa-conv-header">
                        <span class="wa-conv-name">${isUrgent ? '<i class="fas fa-exclamation-triangle wa-urgent-icon" aria-hidden="true"></i>' : ''}<span class="wa-conv-name-text">${escapeHtml(name)}</span>${getContactTypeBadge(c.contact_type)}${getOwnerBadge(c)}${isHumanTakeover ? ' <span class="human-badge" title="Atendimento humano"><i class="fas fa-user" aria-hidden="true"></i></span>' : ''}${isNeverContact ? ' <span class="never-contact-badge" title="Assistente pausado"><i class="fas fa-ban" aria-hidden="true"></i></span>' : ''}</span>
                        <span class="wa-conv-time">${time}${responseTimeBadge}${isMuted ? '<i class="fas fa-bell-slash wa-conv-mute" title="Silenciada" aria-hidden="true"></i>' : ''}${isPinned ? '<i class="fas fa-thumbtack wa-conv-pin" title="Fixada" aria-hidden="true"></i>' : ''}</span>
                    </div>
                    ${phoneLabel !== name ? `<div class="wa-conv-phone">${escapeHtml(phoneLabel)}</div>` : ''}
                    <div class="wa-conv-preview">
                        ${needsResponse ? '<span class="needs-reply-indicator" title="Aguardando equipe"><i class="fas fa-clock"></i></span>' : ''}
                        ${escapeHtml(preview)}
                        ${unreadCount > 0 ? `<span class="wa-unread${isMuted ? ' muted' : ''}">${unreadCount}</span>` : ''}
                    </div>
                    <div class="wa-conv-meta">${getLinkedBadges(c)}</div>
                </div>
            </div>
        `;
    }).join('');
}

function filterConversations() {
    renderConversations();
}

// ============================================
// SELECT CONVERSATION - No race conditions
// ============================================
let currentLoadId = 0;

async function selectConversation(phone) {
    // Clear previous selection
    State.setSelectedPhone(phone);
    State.botEnabled = true;

    // Tier-2: reset per-conversation composer state.
    cancelReply();
    cancelMediaComposer();

    // Update UI immediately
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('qrState').classList.remove('show');
    // #activeChat tem o atributo `hidden` no HTML e o app tem uma regra
    // [hidden]{display:none!important} que vence style.display inline — por
    // isso a conversa nunca abria. Remover o atributo `hidden` e o painel
    // aparece (display:flex aplica normalmente).
    const activeChatEl = document.getElementById('activeChat');
    activeChatEl.hidden = false;
    activeChatEl.style.display = 'flex';

    // Marcar conversa como lida
    try {
        await fetch(`${WHATSAPP_API_BASE}/api/mark-read/${phone}`, { method: 'POST' });
        // Atualizar contador local
        const conv = State.conversations.find(c => c.phone === phone);
        if (conv) conv.unread = 0;
    } catch (e) {
        console.warn('[Mark Read] Error:', e.message);
    }

    // Update conversation list highlight
    renderConversations();

    // Find conversation data
    const conv = State.conversations.find(c => c.phone === phone);
    const name = conv ? getConversationDisplayName(conv) : formatPhone(phone);

    document.getElementById('chatName').textContent = name;
    const ownerBadgeEl = document.getElementById('chatOwnerBadge');
    if (ownerBadgeEl) ownerBadgeEl.innerHTML = conv ? getOwnerBadge(conv, true) : '';
    // v13.1: Chat header avatar with profile pic
    const avatarEl = document.getElementById('chatAvatar');
    avatarEl.setAttribute('style', getAvatarGradientStyle((conv && conv.phone) || phone || name));
    avatarEl.innerHTML = conv ? renderAvatarContent(conv, name) : `<span class="wa-avatar-initials">${escapeHtml(getInitials(name))}</span>`;
    // Tint de grupo no disco do cabecalho quando for um canal de equipe (#equipe).
    avatarEl.classList.toggle('wa-avatar--group', !!conv && getAvatarWrapperClass(conv, name) !== '');
    document.getElementById('chatStatus').textContent = phone;

    // Update bot toggle based on conversation
    if (conv) {
        State.botEnabled = conv.bot_enabled !== false && conv.bot_enabled !== 0;
        State.neverContact = conv.never_contact === 1 || conv.never_contact === true;
        updateBotToggleUI();
        updateNeverContactUI();
        checkFollowupStatus();
    }

    // Load messages with race condition protection
    const loadId = ++currentLoadId;
    await loadMessages(phone, loadId);

    // Real-time da conversa aberta: SSE para latencia baixa + poller de 5s
    // como rede de seguranca (o SSE do bot e instavel — bug #9). Sem o
    // poller, mensagens recebidas so apareciam ao reabrir a conversa.
    stopMessagesPolling();
    startMessagesSSE();
    startMessagesPolling();

    // Load AI conversation context (async, doesn't block)
    loadConversationContext(phone);

    // Pre-load lead data for templates (async, doesn't block)
    try {
        const response = await fetch(`${WHATSAPP_API_BASE}/api/lead/${phone}`);
        if (response.ok) {
            State.currentLeadData = { ...(await response.json()), phone };
            // Lead data loaded
        } else {
            State.currentLeadData = null;
        }
    } catch (e) {
        // Lead data not available
        State.currentLeadData = null;
    }
}

/**
 * B10 helper (26/05): mescla mensagens vindas do backend com otimisticas
 * locais que ainda não foram confirmadas pelo bot.
 *
 * Sem esse merge, qualquer refresh (loadMessages, polling, troca de
 * conversa) sobrescrevia State.messages e a msg que o user acabou de
 * enviar SUMIA da tela apesar de já ter chegado no destinatário —
 * exatamente o que o Example User reportou na reunião 25/05 [01:10:33].
 *
 * Política: mantém otimisticas com idade ≤ 60s que NÃO têm correspondente
 * no fresh (matched por content+role + janela de tempo de 30s). Acima de
 * 60s a otimista é considerada perdida (timeout) e descartada.
 */
function _mergeWithPendingOptimistic(fresh, current) {
    if (!Array.isArray(current) || current.length === 0) return fresh;
    const cutoff = Date.now() - 60_000;
    const pending = current.filter(m => {
        if (!m || !m._isOptimistic) return false;
        const ts = new Date(m.created_at).getTime();
        if (isNaN(ts) || ts < cutoff) return false;
        const confirmed = fresh.some(n =>
            n.content === m.content && n.role === m.role &&
            Math.abs(new Date(n.created_at).getTime() - ts) < 30_000
        );
        return !confirmed;
    });
    return pending.length ? [...fresh, ...pending] : fresh;
}

async function loadMessages(phone, loadId) {
    const container = document.getElementById('messagesContainer');
    container.innerHTML = `<div class="wa-loading"><div class="wa-spinner"></div>Carregando...</div>`;

    try {
        const data = await fetchAPI(`/api/messages/${phone}`);

        // Check if this is still the current conversation
        if (loadId !== currentLoadId || phone !== State.selectedPhone) {
            return; // Discard stale data
        }

        const fresh = Array.isArray(data) ? data : [];
        // B10 (26/05): preserva otimisticas pendentes (< 60s) que o bot ainda
        // não confirmou — antes, sobrescrever State.messages cega apagava a msg
        // recém-enviada da tela do CaseHub. Reunião Example User [01:10:33].
        State.messages = _mergeWithPendingOptimistic(fresh, State.messages);
        renderWhatsAppMessages();

        // Check for AI suggestion on last user message
        if (State.messages.length > 0) {
            const lastMsg = State.messages[State.messages.length - 1];
            if (lastMsg.role === 'user') {
                getAISuggestion(phone, lastMsg.content);
            }
        }
    } catch (error) {
        console.error("[Messages] Error:", error.name, error.message, error.stack);
        container.innerHTML = `<div class="wa-empty-list">
            Error loading messages
        </div>`;
        if (error.name === 'AbortError') {
            showNotification('Timeout ao carregar mensagens', 'warning');
        }
    }
}

// Retry handler bound to the in-chat error state button.
function retryLoadMessages() {
    if (!State.selectedPhone) return;
    const loadId = ++currentLoadId;
    loadMessages(State.selectedPhone, loadId);
}

function renderWhatsAppMessages() {
    if (!State || !Array.isArray(State.messages)) {
        if (State) State.messages = [];
        else return;
    }
    const container = document.getElementById('messagesContainer');

    if (!State.messages || State.messages.length === 0) {
        container.innerHTML = `<div style="padding: 20px; text-align: center; color: var(--wa-text-secondary);">
            Nenhuma mensagem ainda
        </div>`;
        return;
    }

    container.innerHTML = State.messages.map(m => {
        const isOutgoing = m.role === 'assistant';
        const time = m.created_at ? formatMessageTime(m.created_at) : '';
        const ackHtml = isOutgoing ? ' ' + getAckIcon(m.ack) : '';

        return `
            <div class="wa-message ${isOutgoing ? 'outgoing' : 'incoming'}" data-msg-id="${m.id || m.wid || ''}">
                ${renderMessageContent(m)}
                <div class="wa-message-time">${time}${ackHtml}</div>
            </div>
        `;
    }).join('');

    // Scroll to bottom
    container.scrollTop = container.scrollHeight;

    // Check if quick action should be shown
    checkShowQuickAction();
}

// ============================================
// v13.0: SSE (Server-Sent Events) for real-time messages
// ============================================
function startMessagesSSE() {
    if (State.messagesSSE) State.messagesSSE.close();
    if (!State.selectedPhone) return;

    const url = `${WA_API_BASE}/api/events/messages/${State.selectedPhone}`;
    const es = new EventSource(url);

    es.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.type === 'connected') {
                State.sseConnected = true;
                return;
            }
            if (msg.type === 'error') {
                console.warn('[SSE] Error:', msg.message);
                return;
            }

            // Deduplicate: check if message already exists
            const isDuplicate = State.messages.some(m =>
                m.content === msg.content && m.role === msg.role &&
                Math.abs(new Date(m.created_at) - new Date(msg.created_at)) < 5000
            );

            // v13.1: Handle typing indicator
            if (msg.type === 'typing') {
                showTypingIndicator(msg.isTyping);
                // Reflect typing in the header presence line too.
                updatePresence({ phone: msg.phone, typing: msg.isTyping });
                return;
            }

            // Tier-2: presence (online / last-seen) in the chat header.
            if (msg.type === 'presence') {
                updatePresence(msg);
                return;
            }

            // v13.1: Handle message ack (delivery status)
            if (msg.type === 'ack') {
                updateMessageAck(msg);
                return;
            }

            // Tier-2: live reaction / edit / delete events re-render the bubble.
            if (msg.type === 'reaction' || msg.type === 'edited' || msg.type === 'deleted') {
                applyMessageMutation(msg);
                return;
            }

            // Also remove any optimistic message that matches
            if (!isDuplicate) {
                // Remove optimistic version if exists
                const optIdx = State.messages.findIndex(m =>
                    m._isOptimistic && m.content === msg.content && m.role === msg.role
                );
                if (optIdx >= 0) {
                    State.messages.splice(optIdx, 1);
                }

                // If an incoming message arrives while the user is scrolled
                // up, bump the scroll-to-bottom badge (Doherty: keep them
                // aware without yanking their scroll position).
                const mc = document.getElementById('messagesContainer');
                const nearBottom = mc
                    ? mc.scrollHeight - mc.scrollTop - mc.clientHeight < 120
                    : true;
                if (msg.role === 'user' && !nearBottom) {
                    newMessageCount++;
                    updateScrollBadge();
                }

                State.messages.push(msg);
                renderWhatsAppMessages();

                // v13.1: Browser notification for incoming messages
                if (msg.role === 'user' && document.hidden) {
                    showBrowserNotification(msg);
                }
            }
        } catch (e) {
            // Ignore parse errors
        }
    };

    es.onerror = () => {
        State.sseConnected = false;
        // Fallback to polling if SSE fails
        console.warn('[SSE] Connection lost, falling back to polling');
        startMessagesPolling();
    };

    State.messagesSSE = es;
}

function stopMessagesSSE() {
    if (State.messagesSSE) {
        State.messagesSSE.close();
        State.messagesSSE = null;
        State.sseConnected = false;
    }
}

// Poller da conversa aberta. 5s: o SSE do bot e instavel (bug #9), entao o
// poller e a rede de seguranca que mantem a cronologia viva — sem ele, uma
// mensagem recebida so aparecia ao reabrir a conversa. Roda junto com o SSE;
// o setInterval so re-renderiza quando ha mensagem nova (guard abaixo).
function startMessagesPolling() {
    if (State.messagesPoller) return;

    State.messagesPoller = setInterval(async () => {
        if (State.selectedPhone && State.isConnected && !document.hidden) {
            try {
                const data = await fetchAPI(`/api/messages/${State.selectedPhone}`);
                const newMessages = Array.isArray(data) ? data : [];

                // Better comparison: check last message ID/timestamp
                const lastExisting = State.messages.length > 0 ? State.messages[State.messages.length - 1] : null;
                const lastNew = newMessages.length > 0 ? newMessages[newMessages.length - 1] : null;

                if (!lastExisting || !lastNew ||
                    (lastNew.id && lastNew.id !== lastExisting.id) ||
                    newMessages.length !== State.messages.length) {
                    // B10 (26/05): preservar otimisticas pendentes na mesclagem.
                    State.messages = _mergeWithPendingOptimistic(newMessages, State.messages);
                    renderWhatsAppMessages();
                }
            } catch (error) {
                // Silent fail for polling
            }
        }
    }, 5000);
}

function stopMessagesPolling() {
    if (State.messagesPoller) {
        clearInterval(State.messagesPoller);
        State.messagesPoller = null;
    }
}

// ============================================
// v13.1: CONVERSATIONS SSE - Real-time conversation list ordering
// ============================================
function startConversationsSSE() {
    if (State.conversationsSSE) State.conversationsSSE.close();

    const url = `${WA_API_BASE}/api/events/conversations`;
    const es = new EventSource(url);

    es.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'connected' || data.type === 'error') return;

            if (data.type === 'conversation_update') {
                // Update conversation in list and move to top
                const idx = State.conversations.findIndex(c => c.phone === data.phone);
                if (idx >= 0) {
                    // Update existing conversation
                    State.conversations[idx].lastMessage = data.lastMessage;
                    State.conversations[idx].lastMessageTime = data.timestamp;
                    // If incoming message (user), increment unread if not currently viewing
                    if (data.role === 'user' && data.phone !== State.selectedPhone) {
                        State.conversations[idx].unread = (parseInt(State.conversations[idx].unread) || 0) + 1;
                        State.conversations[idx].from_bot = 0;
                        // v13.2: Browser notification for messages in other conversations
                        showBrowserNotification({
                            content: data.lastMessage,
                            phone: data.phone,
                            role: data.role
                        });
                    }
                    // Move conversation to top of list
                    const conv = State.conversations.splice(idx, 1)[0];
                    State.conversations.unshift(conv);
                } else {
                    // New conversation - add to top
                    State.conversations.unshift({
                        phone: data.phone,
                        lastMessage: data.lastMessage,
                        lastMessageTime: data.timestamp,
                        unread: data.role === 'user' ? 1 : 0,
                        from_bot: data.role === 'user' ? 0 : 1,
                    });
                }
                renderConversations();
            }
        } catch (e) {
            // Ignore parse errors
        }
    };

    es.onerror = () => {
        // Silently reconnect - conversations still load via polling
    };

    State.conversationsSSE = es;
}

function stopConversationsSSE() {
    if (State.conversationsSSE) {
        State.conversationsSSE.close();
        State.conversationsSSE = null;
    }
}

// ============================================
// SEND MESSAGE
// ============================================
async function sendMessage() {
    const input = document.getElementById('messageInput');
    const text = input.value.trim();

    if (!text || !State.selectedPhone) return;

    // Snapshot the reply context, then clear the composer state.
    const replyTo = replyContext ? replyContext.id : null;
    const replyToWa = replyContext ? replyContext.waMessageId : null;

    // Optimistic update (v13.0: mark as optimistic for SSE dedup)
    const tempMsg = {
        content: text,
        role: 'assistant',
        created_at: new Date().toISOString(),
        from_bot: false,
        _isOptimistic: true,
        reply_to_message_id: replyTo
    };
    State.messages.push(tempMsg);
    renderWhatsAppMessages();
    input.value = '';
    cancelReply();

    // Hide AI suggestion
    document.getElementById('aiSuggestion').classList.remove('show');

    try {
        const body = {
            phone: State.selectedPhone,
            message: text, fromHuman: true
        };
        // Tier-2: carry the quoted-message id so the bot sends a reply.
        if (replyTo) body.reply_to_message_id = replyTo;
        if (replyToWa) body.reply_to_wa_message_id = replyToWa;

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), API_TIMEOUTS.send);

        const response = await fetch(WHATSAPP_API_BASE + '/api/send', {
            method: 'POST',
            headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
            signal: controller.signal
        });
        clearTimeout(timeout);

        if (!response.ok) {
            throw new Error('Send failed');
        }

        showNotification('Message sent');
    } catch (error) {
        // Rollback
        State.messages.pop();
        renderWhatsAppMessages();
        input.value = text;
        const errMsg = error.name === 'AbortError' ? 'Timeout - try again' : 'Failed to send message';
        showNotification(errMsg, 'error');
    }
}

function handleInputKey(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

// ============================================
// BOT TOGGLE
// ============================================
async function toggleBot() {
    if (!State.selectedPhone) return;

    const newState = !State.botEnabled;

    // Optimistic update
    State.botEnabled = newState;
    updateBotToggleUI();
        checkFollowupStatus();

    try {
        const response = await fetch(WHATSAPP_API_BASE + '/api/bot-control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formData.toString()
        });

        if (!response.ok) {
            throw new Error('Toggle failed');
        }

        showNotification(newState ? 'Sugestões ativadas' : 'Modo humano - sugestões pausadas');
    } catch (error) {
        // Rollback
        State.botEnabled = !newState;
        updateBotToggleUI();
        checkFollowupStatus();
        showNotification('Erro ao trocar modo', 'error');
    }
}

function updateBotToggleUI() {
    const toggle = document.getElementById('botToggle');
    const text = document.getElementById('botToggleText');

    if (State.botEnabled) {
        toggle.className = 'wa-bot-toggle bot-active';
        toggle.innerHTML = '<i class="fas fa-robot" aria-hidden="true"></i><span>Sugestões</span>';
    } else {
        toggle.className = 'wa-bot-toggle human-active';
        toggle.innerHTML = '<i class="fas fa-user" aria-hidden="true"></i><span>Humano</span>';
    }
}

// ============================================
// AI SUGGESTION

// ============================================
// NEVER CONTACT TOGGLE
// ============================================
async function toggleNeverContact() {
    if (!State.selectedPhone) return;

    const currentState = State.neverContact;
    const action = currentState ? 'reativar sugestões para' : 'pausar sugestões para';
    const name = State.currentLeadData?.client_name || State.currentLeadData?.whatsapp_name || State.selectedPhone;

    if (!confirm('Tem certeza que deseja ' + action + ' ' + name + '?\n\n' +
        (currentState
            ? 'A equipe voltara a ver rascunhos do assistente para este contato.'
            : 'O assistente ficara pausado para este contato.\nA equipe continua responsavel por revisar e responder.'))) {
        return;
    }

    const newState = !currentState;
    State.neverContact = newState;
    updateNeverContactUI();

    try {
        const response = await fetch(WHATSAPP_API_BASE + '/api/leads/' + State.selectedPhone + '/bot-settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                never_contact: newState,
                bot_enabled: !newState,
                human_takeover: newState ? 1 : 0
            })
        });
        if (!response.ok) throw new Error('Toggle failed');

        // Update conversation in sidebar
        const conv = State.conversations.find(c => c.phone === State.selectedPhone);
        if (conv) {
            conv.never_contact = newState ? 1 : 0;
            conv.bot_enabled = newState ? 0 : 1;
            conv.human_takeover = newState ? 1 : 0;
        }
        renderConversations();

        if (newState) {
            State.botEnabled = false;
            updateBotToggleUI();
        }

        showNotification(
            newState ? 'Sugestões pausadas para ' + name : 'Sugestões reativadas para ' + name,
            newState ? 'warning' : 'success'
        );
    } catch (error) {
        State.neverContact = !newState;
        updateNeverContactUI();
        showNotification('Erro ao atualizar configuração', 'error');
    }
}

function updateNeverContactUI() {
    const toggle = document.getElementById('neverContactToggle');
    if (!toggle) return;
    if (State.neverContact) {
        toggle.className = 'wa-never-contact active';
        toggle.innerHTML = '<i class="fas fa-ban" aria-hidden="true"></i><span>Assistente pausado</span>';
    } else {
        toggle.className = 'wa-never-contact';
        toggle.innerHTML = '<i class="fas fa-ban" aria-hidden="true"></i><span>Pausar assistente</span>';
    }
}

// ============================================
// AUTO FOLLOW-UP CONTROL
// ============================================
let followupMarked = false;

async function toggleFollowup() {
    if (!State.selectedPhone) return;

    const btn = document.getElementById("followupBtn");
    const text = document.getElementById("followupBtnText");

    btn.style.opacity = "0.5";
    btn.style.pointerEvents = "none";

    try {
        const endpoint = followupMarked ? "/api/followup/unmark" : "/api/followup/mark";
        const response = await fetch(WA_API_BASE + endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ phone: State.selectedPhone })
        });

        if (!response.ok) throw new Error("Failed");

        followupMarked = !followupMarked;
        updateFollowupUI();
        showNotification(followupMarked ? "Marcado para acompanhamento (30 min)" : "Acompanhamento cancelado");
    } catch (error) {
        console.error("Error toggling followup:", error);
        showNotification("Erro ao marcar follow-up", "error");
    } finally {
        btn.style.opacity = "1";
        btn.style.pointerEvents = "auto";
    }
}

window.markForFollowup = async function markForFollowup(phone) {
    const targetPhone = phone || State.selectedPhone;
    if (!targetPhone) return false;
    const response = await fetch(WA_API_BASE + "/api/followup/mark", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone: targetPhone })
    });
    if (!response.ok) throw new Error("Failed to mark followup");
    if (targetPhone === State.selectedPhone) {
        followupMarked = true;
        updateFollowupUI();
    }
    showNotification("Marcado para acompanhamento (30 min)");
    return true;
};

function updateFollowupUI() {
    const btn = document.getElementById("followupBtn");
    const text = document.getElementById("followupBtnText");

    if (followupMarked) {
        btn.classList.add("marked");
        text.textContent = "Aguardando";
    } else {
        btn.classList.remove("marked");
        text.textContent = "Acompanhar";
    }
}

async function checkFollowupStatus() {
    if (!State.selectedPhone) return;

    try {
        const response = await fetch(`${WHATSAPP_API_BASE}/api/followup/check/${State.selectedPhone}`);
        if (response.ok) {
            const data = await response.json();
            followupMarked = data.marked;
            updateFollowupUI();
        }
    } catch (error) {
        console.error("Error checking followup:", error);
    }
}
// ============================================
async function getAISuggestion(phone, lastMessage) {
    const container = document.getElementById('aiSuggestion');
    const textEl = document.getElementById('aiText');

    try {
        // Bugfix: previously referenced an undefined `text` variable here,
        // which threw a ReferenceError and silently killed AI suggestions.
        const body = {
            phone: phone,
            message: lastMessage || '',
            fromHuman: true
        };

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), API_TIMEOUTS.ai);

        const response = await fetch(WHATSAPP_API_BASE + '/api/suggest-response', {
            method: 'POST',
            headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
            signal: controller.signal
        });
        clearTimeout(timeout);

        if (!response.ok) return;

        const data = await response.json();

        if (data.suggestion && phone === State.selectedPhone) {
            textEl.textContent = data.suggestion;
            container.classList.add('show');
        }
    } catch (error) {
        // Silent fail for AI suggestions
    }
}

function useSuggestion() {
    const text = document.getElementById('aiText').textContent;
    document.getElementById('messageInput').value = text;
    document.getElementById('aiSuggestion').classList.remove('show');
    document.getElementById('messageInput').focus();
}

// ============================================
// QUICK ACTION - First Response
// ============================================
const QUICK_GREETING = `Oi! Como podemos ajudar você hoje?`;

function checkShowQuickAction() {
    const quickAction = document.getElementById('quickAction');
    if (!quickAction || !State.messages || State.messages.length === 0) {
        if (quickAction) quickAction.classList.remove('show');
        return;
    }

    // Check if last message is from user (incoming)
    const lastMsg = State.messages[State.messages.length - 1];
    const isLastIncoming = lastMsg.role === 'user';

    // Check if there's any human response (outgoing that's not from bot)
    // For now, we show if last message is incoming and there are few messages
    const hasHumanResponse = State.messages.some(m =>
        m.role === 'assistant' && m.content && !m.content.includes('Olá!') && !m.content.includes('Hello.')
    );

    // Show quick action if:
    // - Last message is from client (incoming)
    // - Conversation is relatively new (less than 10 messages)
    // - No substantial human response yet
    if (isLastIncoming && State.messages.length < 10 && !hasHumanResponse) {
        quickAction.classList.add('show');
    } else {
        quickAction.classList.remove('show');
    }
}

async function sendQuickGreeting() {
    const phone = State.selectedPhone;
    if (!phone) return;

    const btn = document.getElementById('quickActionBtn');
    btn.disabled = true;
    btn.textContent = 'Enviando...';

    try {
        // Bugfix: `text` was undefined here — the greeting never sent.
        const body = {
            phone: phone,
            message: QUICK_GREETING,
            fromHuman: true
        };

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), API_TIMEOUTS.send);

        await fetch(WHATSAPP_API_BASE + '/api/send', {
            method: 'POST',
            headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
            signal: controller.signal
        });
        clearTimeout(timeout);

        document.getElementById('quickAction').classList.remove('show');

        // Reload messages
        const loadId = ++currentLoadId;
        await loadMessages(phone, loadId);

    } catch (error) {
        console.error('[Quick Action] Error:', error);
        btn.disabled = false;
        btn.textContent = 'Enviar Saudação';
        const errMsg = error.name === 'AbortError' ? 'Timeout - tente novamente' : 'Erro ao enviar mensagem';
        showNotification(errMsg, 'error');
    }
}

// ============================================
// CONVERSATION CONTEXT (AI Summary)
// ============================================
async function loadConversationContext(phone) {
    const contextEl = document.getElementById('conversationContext');
    if (!contextEl) return;

    // Show panel and start loading
    contextEl.classList.add('show');

    // First load basic context (fast)
    try {
        const lastMsg = State.messages && State.messages.length > 0 
            ? State.messages[State.messages.length - 1]?.content || '' 
            : '';
        const response = await fetch(WHATSAPP_API_BASE + '/api/conversation-context', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({
                phone: State.selectedPhone || '',
                last_message: lastMsg || ''
            })
        });

        if (response.ok) {
            const ctx = await response.json();
            if (ctx) {
                const lead = ctx.lead || {};
                document.getElementById('ctxStage').textContent =
                    ctx.stage || lead.stage || lead.lead_stage || '-';
                document.getElementById('ctxInterest').textContent =
                    ctx.interest || lead.interest || lead.visa_interest || '-';
            }
        }
    } catch (e) {
        console.log('[Context] Basic context error:', e.message);
    }

    // Then load detailed summary (may take longer)
    loadConversationSummary();
}

// Load detailed conversation summary from lead-monitor
// Toggle summary collapse/expand
function toggleSummaryCollapse() {
    const ctx = document.getElementById('conversationContext');
    if (ctx) {
        ctx.classList.toggle('collapsed');
        // Save preference
        localStorage.setItem('summaryCollapsed', ctx.classList.contains('collapsed'));
    }
}

// Restore collapse state on load
function restoreSummaryCollapseState() {
    const collapsed = localStorage.getItem('summaryCollapsed') === 'true';
    const ctx = document.getElementById('conversationContext');
    if (ctx && collapsed) {
        ctx.classList.add('collapsed');
    }
}

// Call on page load
document.addEventListener('DOMContentLoaded', restoreSummaryCollapseState);

async function loadConversationSummary() {
    const phone = State.selectedPhone;
    if (!phone) return;

    const summaryContent = document.getElementById('summaryContent');
    const summaryLoading = document.getElementById('summaryLoading');
    const contextEl = document.getElementById('conversationContext');

    // Show loading. Estes elementos tem atributo `hidden` no HTML + a regra
    // global [hidden]{display:none!important} — alternar `hidden`, nao display.
    if (summaryLoading) {
        summaryLoading.hidden = false;
    }

    // Hide expanded sections during loading
    ['summaryCurrentSection', 'summaryHistorySection', 'summaryNextStepsSection',
     'summaryPendingSection', 'summaryStatusSection'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.hidden = true;
    });

    try {
        const response = await fetch(`${WHATSAPP_API_BASE}/api/lead-summary/${phone}`);

        if (!response.ok) {
            if (summaryLoading) summaryLoading.style.display = 'none';
            return;
        }

        const data = await response.json();

        // Hide loading
        if (summaryLoading) summaryLoading.style.display = 'none';

        if (data.error) {
            console.log('[Summary] No summary available:', data.error);
            return;
        }

        // Update lead info
        if (data.lead) {
            document.getElementById('ctxScore').textContent = data.lead.score ? `${data.lead.score}/100 (${data.lead.status})` : '-';

            // If urgent, highlight
            if (data.lead.urgent) {
                document.getElementById('ctxScore').innerHTML = `<span class="wa-score-urgent">🚨 ${data.lead.score}/100 URGENTE</span>`;
            }
        }

        // Update summary sections
        if (data.summary) {
            // Current Situation
            if (data.summary.currentSituation && data.summary.currentSituation !== 'Resumo nao disponivel') {
                const section = document.getElementById('summaryCurrentSection');
                document.getElementById('summaryCurrentSituation').textContent = data.summary.currentSituation;
                if (section) section.hidden = false;
            }

            // History
            if (data.summary.history && data.summary.history.length > 0) {
                const section = document.getElementById('summaryHistorySection');
                const container = document.getElementById('summaryHistory');
                container.innerHTML = data.summary.history.map(h =>
                    `<div class="wa-summary-history-item">
                        <span class="wa-summary-history-time">${h.time || '-'}</span>
                        <span class="wa-summary-history-event">${escapeHtml(h.event || '')}</span>
                    </div>`
                ).join('');
                if (section) section.hidden = false;
            }

            // Next Steps
            if (data.summary.nextSteps && data.summary.nextSteps.length > 0) {
                const section = document.getElementById('summaryNextStepsSection');
                const container = document.getElementById('summaryNextSteps');
                container.innerHTML = data.summary.nextSteps.map((step, i) =>
                    `<div class="wa-summary-step">${i + 1}. ${escapeHtml(step)}</div>`
                ).join('');
                if (section) section.hidden = false;
            }

            // Pending Questions
            if (data.summary.pendingQuestions && data.summary.pendingQuestions.length > 0) {
                const section = document.getElementById('summaryPendingSection');
                const container = document.getElementById('summaryPending');
                container.innerHTML = data.summary.pendingQuestions.map(q =>
                    `<div class="wa-summary-pending-item">${escapeHtml(q)}</div>`
                ).join('');
                if (section) section.hidden = false;
            }

            // Status
            const statusSection = document.getElementById('summaryStatusSection');
            const statusBadge = document.getElementById('summaryStatusBadge');
            const timeAgo = document.getElementById('summaryTimeAgo');

            if (statusSection && statusBadge && timeAgo) {
                const status = data.summary.status || 'unknown';
                const minutes = data.summary.minutesSinceLastActivity;

                statusBadge.className = 'wa-summary-status-badge ' + status;
                statusBadge.textContent = status === 'responded' ? 'Respondida' :
                                           status === 'pending' ? 'Aguardando' :
                                           status === 'needs_attention' ? 'Precisa Atencao' : '-';

                if (minutes !== null && minutes !== undefined) {
                    if (minutes < 60) {
                        timeAgo.textContent = `${minutes} min atras`;
                    } else if (minutes < 1440) {
                        timeAgo.textContent = `${Math.floor(minutes / 60)}h atras`;
                    } else {
                        timeAgo.textContent = `${Math.floor(minutes / 1440)}d atras`;
                    }
                } else {
                    timeAgo.textContent = '';
                }

                statusSection.hidden = false;
            }
        }

        if (summaryLoading) summaryLoading.hidden = true;
        contextEl.classList.add('show');

    } catch (e) {
        console.log('[Summary] Error loading summary:', e.message);
        if (summaryLoading) summaryLoading.hidden = true;
    }
}

// ============================================
// TEMPLATE PREVIEW MODAL (with edit capability)
// ============================================
function previewTemplate(id) {
    const template = TEMPLATES.find(t => t.id === id);
    if (!template) return;

    // Close templates menu
    const menu = document.getElementById('templatesMenu');
    if (menu) menu.classList.remove('show');

    const modal = document.createElement('div');
    modal.className = 'wa-template-modal';
    modal.id = 'templatePreviewModal';
    modal.innerHTML = `
        <div class="wa-template-modal-content">
            <div class="wa-template-modal-header">
                <span class="wa-template-modal-title">${escapeHtml(template.name)}</span>
                <span class="wa-template-modal-cat">${escapeHtml(template.cat)}</span>
            </div>
            <div class="wa-template-modal-body">
                <textarea id="templatePreviewText" class="wa-template-textarea">${escapeHtml(template.text)}</textarea>
            </div>
            <div class="wa-template-modal-hint">
                <i class="fas fa-info-circle"></i> Use os botões abaixo. Variáveis: [NOME], [DATA], [HORARIO], [LINK], [VALOR]
            </div>
            <div class="wa-template-modal-actions">
                <button class="wa-template-action-btn" onclick="copyTemplateText()" title="Copiar texto">
                    <i class="fas fa-copy"></i> Copiar
                </button>
                <button class="wa-template-action-btn" onclick="fillClientData()" title="Preencher dados do cliente">
                    <i class="fas fa-user-edit"></i> Preencher Dados
                </button>
            </div>
            <div class="wa-template-modal-footer">
                <button class="wa-template-modal-btn cancel" onclick="closePreviewModal()">
                    <i class="fas fa-times"></i> Cancelar
                </button>
                <button class="wa-template-modal-btn secondary" onclick="useInTextField()">
                    <i class="fas fa-edit"></i> Usar no Campo
                </button>
                <button class="wa-template-modal-btn accent" onclick="fillAndSend()">
                    <i class="fas fa-magic"></i> Preencher e Enviar
                </button>
                <button class="wa-template-modal-btn primary" onclick="sendTemplateNow()">
                    <i class="fas fa-paper-plane"></i> Enviar Agora
                </button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    // Focus textarea
    setTimeout(() => {
        const textarea = document.getElementById('templatePreviewText');
        if (textarea) {
            textarea.focus();
            textarea.setSelectionRange(0, 0);
        }
    }, 100);

    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closePreviewModal();
    });

    // Close on Escape key
    const escHandler = (e) => {
        if (e.key === 'Escape') {
            closePreviewModal();
            document.removeEventListener('keydown', escHandler);
        }
    };
    document.addEventListener('keydown', escHandler);
}

// Get client data from current conversation (async - fetches from API)
async function getClientData() {
    const phone = State.selectedPhone;
    if (!phone) return getDefaultClientData();

    // Try cached data first
    if (State.currentLeadData && State.currentLeadData.phone === phone) {
        return formatLeadData(State.currentLeadData);
    }

    // Fetch from API
    try {
        const response = await fetch(`${WHATSAPP_API_BASE}/api/lead/${phone}`);
        if (response.ok) {
            const data = await response.json();
            State.currentLeadData = { ...data, phone };
            console.log('[Template] Lead data loaded:', data.lead?.client_name || 'N/A');
            return formatLeadData(data);
        }
    } catch (e) {
        console.error('[Template] Error fetching lead data:', e);
    }

    return getDefaultClientData();
}

function getDefaultClientData() {
    const conv = State.conversations.find(c => c.phone === State.selectedPhone);
    const now = new Date();
    return {
        nome: conv?.name || conv?.whatsapp_name || '[NOME]',
        data: now.toLocaleDateString('pt-BR'),
        horario: now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
        email: '[EMAIL]',
        telefone: State.selectedPhone || '[TELEFONE]',
        interesse: '[INTERESSE]',
        link_gratuita: 'CALENDLY_FREE_URL',
        link_paga: 'CALENDLY_PAID_URL',
        valor: '[VALOR]',
        servico: '[SERVICO]'
    };
}

function formatLeadData(data) {
    const now = new Date();
    const lead = data.lead || {};
    const conv = State.conversations.find(c => c.phone === State.selectedPhone);

    return {
        nome: lead.client_name || lead.whatsapp_name || conv?.name || conv?.whatsapp_name || '[NOME]',
        data: now.toLocaleDateString('pt-BR'),
        horario: now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }),
        email: lead.email || '[EMAIL]',
        telefone: lead.phone || State.selectedPhone || '[TELEFONE]',
        interesse: lead.visa_interest || '[INTERESSE]',
        link_gratuita: 'CALENDLY_FREE_URL',
        link_paga: 'CALENDLY_PAID_URL',
        valor: '[VALOR]',
        servico: lead.visa_interest || '[SERVICO]'
    };
}

// Replace placeholders with client data (async)
async function replaceTemplateVars(text) {
    const data = await getClientData();
    return text
        .replace(/\[NOME\]/gi, data.nome)
        .replace(/\[DATA\]/gi, data.data)
        .replace(/\[HORARIO\]/gi, data.horario)
        .replace(/\[EMAIL\]/gi, data.email)
        .replace(/\[TELEFONE\]/gi, data.telefone)
        .replace(/\[INTERESSE\]/gi, data.interesse)
        .replace(/\[LINK_GRATUITA\]/gi, data.link_gratuita)
        .replace(/\[LINK_PAGA\]/gi, data.link_paga)
        .replace(/\[LINK\]/gi, data.link_gratuita)
        .replace(/\[VALOR\]/gi, data.valor)
        .replace(/\[SERVICO\]/gi, data.servico);
}

// Copy template text to clipboard
async function copyTemplateText() {
    const textarea = document.getElementById('templatePreviewText');
    if (!textarea) return;

    try {
        await navigator.clipboard.writeText(textarea.value);
        showNotification('Texto copiado!', 'success');
    } catch (err) {
        // Fallback for older browsers
        textarea.select();
        document.execCommand('copy');
        showNotification('Texto copiado!', 'success');
    }
}

// Fill in client data in textarea (async with loading state)
async function fillClientData() {
    const textarea = document.getElementById('templatePreviewText');
    if (!textarea) return;

    // Find the button and show loading
    const btns = document.querySelectorAll('.wa-template-action-btn');
    const btn = btns[1]; // Second button is "Preencher Dados"
    const originalHtml = btn ? btn.innerHTML : '';

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Carregando...';
    }

    try {
        textarea.value = await replaceTemplateVars(textarea.value);
        showNotification('Dados preenchidos!', 'success');
    } catch (e) {
        console.error('[Template] Error filling data:', e);
        showNotification('Erro ao preencher dados', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    }
}

// Fill client data and send immediately (async)
async function fillAndSend() {
    const textarea = document.getElementById('templatePreviewText');
    if (!textarea) return;

    // Find the button and show loading
    const btn = document.querySelector('.wa-template-modal-btn.accent');
    const originalHtml = btn ? btn.innerHTML : '';

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Preenchendo...';
    }

    try {
        // First fill the data
        textarea.value = await replaceTemplateVars(textarea.value);

        // Update button for sending phase
        if (btn) {
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Enviando...';
        }

        // Then send
        await sendTemplateNow();
    } catch (e) {
        console.error('[Template] Error in fillAndSend:', e);
        showNotification('Erro ao preencher e enviar', 'error');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
    }
}

function closePreviewModal() {
    const modal = document.getElementById('templatePreviewModal');
    if (modal) modal.remove();
}

function useInTextField() {
    const textarea = document.getElementById('templatePreviewText');
    if (textarea) {
        const messageInput = document.getElementById('messageInput');
        if (messageInput) {
            messageInput.value = textarea.value;
            messageInput.focus();
        }
    }
    closePreviewModal();
}

async function sendTemplateNow() {
    const textarea = document.getElementById('templatePreviewText');
    if (!textarea || !textarea.value.trim()) return;

    const phone = State.selectedPhone;
    if (!phone) {
        showNotification('Selecione uma conversa primeiro', 'error');
        return;
    }

    const text = textarea.value.trim();
    const btn = document.querySelector('.wa-template-modal-btn.primary');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Enviando...';
    }

    try {
        const body = {
            phone: State.selectedPhone,
            message: text, fromHuman: true
        };

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), API_TIMEOUTS.send);

        const response = await fetch(WHATSAPP_API_BASE + '/api/send', {
            method: 'POST',
            headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
            signal: controller.signal
        });
        clearTimeout(timeout);

        if (response.ok) {
            closePreviewModal();
            const loadId = ++currentLoadId;
            loadMessages(phone, loadId);
            showNotification('Mensagem enviada!', 'success');
        } else {
            throw new Error('Erro ao enviar');
        }
    } catch (error) {
        console.error('Send error:', error);
        const errMsg = error.name === 'AbortError' ? 'Timeout - tente novamente' : 'Erro ao enviar mensagem';
        showNotification(errMsg, 'error');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-paper-plane"></i> Enviar Agora';
        }
    }
}

// Keep old function for backwards compatibility
function closeTemplateModal() {
    closePreviewModal();
}

function useTemplateFromModal(id) {
    useTemplate(id);
    closePreviewModal();
}

// ============================================
// TEMPLATES
// ============================================
function toggleTemplates() {
    const menu = document.getElementById('templatesMenu');
    menu.classList.toggle('show');

    if (menu.classList.contains('show')) {
        renderTemplates();
        document.getElementById('templateSearch').focus();
    }
}

function renderTemplates() {
    const container = document.getElementById('templatesList');
    const query = document.getElementById('templateSearch').value.toLowerCase();

    let filtered = TEMPLATES;
    if (query) {
        filtered = TEMPLATES.filter(t =>
            t.name.toLowerCase().includes(query) ||
            t.text.toLowerCase().includes(query) ||
            t.cat.toLowerCase().includes(query)
        );
    }

    // Group by category
    const grouped = {};
    filtered.forEach(t => {
        if (!grouped[t.cat]) grouped[t.cat] = [];
        grouped[t.cat].push(t);
    });

    let html = '';
    CATEGORIES.forEach(cat => {
        if (grouped[cat] && grouped[cat].length > 0) {
            html += `<div class="wa-template-category">${cat}</div>`;
            grouped[cat].forEach(t => {
                html += `
                    <div class="wa-template-item" onclick="previewTemplate(${t.id})">
                        <div class="wa-template-name">${escapeHtml(t.name)}</div>
                        <div class="wa-template-preview">${escapeHtml(truncate(t.text, 80))}</div>
                    </div>
                `;
            });
        }
    });

    container.innerHTML = html || '<div class="wa-empty-list">No templates found</div>';
}

function filterTemplates() {
    renderTemplates();
}

function useTemplate(id) {
    const template = TEMPLATES.find(t => t.id === id);
    if (template) {
        document.getElementById('messageInput').value = template.text;
        document.getElementById('templatesMenu').classList.remove('show');
        document.getElementById('messageInput').focus();
    }
}

// Close templates when clicking outside
document.addEventListener('click', (e) => {
    const menu = document.getElementById('templatesMenu');
    const btn = e.target.closest('[onclick*="toggleTemplates"]') || e.target.closest('.wa-templates-btn');
    const menuEl = e.target.closest('.wa-templates-menu');

    if (!btn && !menuEl && menu.classList.contains('show')) {
        menu.classList.remove('show');
    }
});

// ============================================
// VISIBILITY API - Stop polling when hidden
// ============================================
document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
        // v13.0: Keep SSE alive but stop polling when tab hidden
        stopMessagesPolling();
    } else {
        if (State.isConnected && State.selectedPhone) {
            // v13.0: Reconnect SSE if needed, polling as fallback
            if (!State.sseConnected) startMessagesSSE();
        }
        // Refresh status
        checkStatus();
    }
});

// ============================================
// UTILITY FUNCTIONS
// ============================================
function formatPhone(phone) {
    if (!phone) return 'Unknown';
    if (phone.length === 13 && phone.startsWith('55')) {
        return `+${phone.slice(0,2)} (${phone.slice(2,4)}) ${phone.slice(4,9)}-${phone.slice(9)}`;
    }
    return phone;
}

// Fuso de Brasília (Victor 10/06). O backend grava UTC (datetime.utcnow), às
// vezes SEM designador de fuso ('Z'). new Date() interpreta string naive como
// horário LOCAL do navegador -> horários errados e variando por máquina.
// parseServerDate trata a string naive como UTC; os formatadores SEMPRE exibem
// em America/Sao_Paulo, independente de onde o usuário esteja.
const BR_TZ = 'America/Sao_Paulo';
function parseServerDate(s) {
    if (s instanceof Date) return s;
    if (!s) return new Date(NaN);
    // Epoch numérico (ms ou segundos) — getMessageTs e o balão otimista passam
    // NÚMERO; antes virava "Invalid date" (String(1718..)+'Z' não parseia).
    if (typeof s === 'number' || /^\d{9,}$/.test(String(s).trim())) {
        let n = Number(s);
        if (n < 1e12) n *= 1000; // epoch em segundos -> ms
        return new Date(n);
    }
    let str = String(s);
    if (!/([zZ])|([+-]\d{2}:?\d{2})$/.test(str)) {
        str = str.replace(' ', 'T') + 'Z'; // naive => trata como UTC
    }
    return new Date(str);
}

function formatTime(dateStr) {
    if (!dateStr) return '';
    const date = parseServerDate(dateStr);
    const now = new Date();
    const diff = now - date;

    // mesmo dia em Brasília (compara via string localizada no fuso BR)
    const sameDayBr = date.toLocaleDateString('pt-BR', { timeZone: BR_TZ })
        === now.toLocaleDateString('pt-BR', { timeZone: BR_TZ });
    if (diff < 86400000 && sameDayBr) {
        return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: BR_TZ });
    }
    if (diff < 172800000) {
        return 'Ontem';
    }
    return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', timeZone: BR_TZ });
}

function formatMessageTime(dateStr) {
    if (!dateStr) return '';
    const date = parseServerDate(dateStr);
    // Brasília (era America/New_York — leftover ILC immigration v13.0)
    return date.toLocaleTimeString('pt-BR', {
        hour: '2-digit', minute: '2-digit',
        timeZone: BR_TZ
    });
}

function getConversationDisplayName(conversation) {
    if (!conversation) return 'Unknown';
    // Backend resolves `name` = linked Client.full_name > WhatsApp display_name >
    // phone, so prefer it over the raw WhatsApp pushname.
    return conversation.name || conversation.whatsapp_name || formatPhone(conversation.phone);
}

// Marca do Maestro nas abas do chat de bandeja. `/static/` direto (regra de
// paths do CaseHub — nunca PREFIX/static).
const MAESTRO_AVATAR_SRC = '/static/img/maestro.png';

// Classifica a conversa para escolher o avatar das abas internas do chat de
// bandeja (#equipe, @Maestro, @Example User...). Retorna 'maestro' p/ o Maestro,
// 'group' p/ canais de equipe (#...), ou 'person' p/ pessoas/contatos normais.
// So olha nome/flags da conversa — nao toca em socket/conexao do WhatsApp.
function classifyAvatarKind(conversation, displayName) {
    const rawName = (conversation && (conversation.name || conversation.whatsapp_name)) || displayName || '';
    const name = String(rawName).trim();
    const lower = name.toLowerCase();

    // Maestro: aba @Maestro (ou flag explicita do backend).
    if ((conversation && (conversation.is_maestro === true || conversation.isMaestro === true))
        || lower === '@maestro' || lower === 'maestro'
        || lower.replace(/^@/, '') === 'maestro') {
        return 'maestro';
    }

    // Grupo/canal de equipe: #equipe e similares (ou flag de grupo do backend).
    if ((conversation && (conversation.is_group === true || conversation.isGroup === true))
        || name.startsWith('#')) {
        return 'group';
    }

    return 'person';
}

// Resolve a foto da conversa, aceitando os varios nomes de campo que o backend
// pode usar (profilePic / profile_pic / profile_picture / photo_url / photoUrl).
function getConversationPhoto(conversation) {
    if (!conversation) return '';
    return conversation.profilePic
        || conversation.profile_pic
        || conversation.profile_picture
        || conversation.photo_url
        || conversation.photoUrl
        || '';
}

// Owner-tag chip: colored badge showing who "owns" this contact (CRM owner).
// `full` => first name; otherwise initials (compact, for the conversation list).
function getOwnerBadge(conversation, full) {
    const o = conversation && conversation.owner;
    if (!o || !o.name) return '';
    const color = /^#[0-9a-fA-F]{3,8}$/.test(o.color || '') ? o.color : '#7c3aed';
    const safeName = escapeHtml(o.name);
    const label = full ? escapeHtml(o.name.split(' ')[0]) : escapeHtml(getInitials(o.name));
    return `<span class="wa-owner-badge${full ? ' wa-owner-badge--full' : ''}" style="background:${color}" title="Dono: ${safeName}">${label}</span>`;
}

// Apply an owner change (from the CRM panel) to the sidebar + open-chat header
// without a full network reload.
window.applyCrmOwner = function (phone, owner) {
    const conv = (State.conversations || []).find(c => c.phone === phone);
    if (conv) conv.owner = owner || null;
    try { renderConversations(); } catch (e) {}
    if (State.selectedPhone === phone) {
        const el = document.getElementById('chatOwnerBadge');
        if (el) el.innerHTML = conv ? getOwnerBadge(conv, true) : '';
    }
};

function getInitials(name) {
    if (!name) return '?';
    const parts = name.split(' ').filter(p => p.length > 0);
    if (parts.length >= 2) {
        return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
}

function hashString(value) {
    const str = String(value || '');
    let hash = 0;
    for (let i = 0; i < str.length; i += 1) {
        hash = ((hash << 5) - hash) + str.charCodeAt(i);
        hash |= 0;
    }
    return Math.abs(hash);
}

function getAvatarGradientStyle(seed) {
    const gradients = [
        ['#008C4D', '#DBE64C', '#1E4890'],
        ['#1E4890', '#25D366', '#FAFBF7'],
        ['#001F3E', '#6FBE54', '#E6E2DA'],
        ['#4F4B51', '#DBE64C', '#008C4D'],
        ['#0B1426', '#1E4890', '#6FBE54'],
        ['#25D366', '#F2F49B', '#1E4890']
    ];
    const selected = gradients[hashString(seed) % gradients.length];
    return `--wa-avatar-gradient: linear-gradient(135deg, ${selected[0]} 0%, ${selected[1]} 58%, ${selected[2]} 100%);`;
}

// Conteudo interno do disco de avatar. Renderiza FOTO redonda p/ pessoa
// (fallback iniciais se sem foto), icone de grupo p/ #equipe, e a marca do
// Maestro p/ a aba @Maestro — nunca um "@"/"#" cru. So mexe no render do
// avatar; nenhuma logica de socket/conexao do WhatsApp e tocada aqui.
function renderAvatarContent(conversation, displayName) {
    const initials = escapeHtml(getInitials(displayName));
    const kind = classifyAvatarKind(conversation, displayName);

    if (kind === 'maestro') {
        return `<img class="wa-avatar-img wa-avatar--maestro" src="${MAESTRO_AVATAR_SRC}" alt="${escapeHtml(displayName)}" `
            + `onerror="this.hidden=true;this.nextElementSibling.hidden=false">`
            + `<span class="wa-avatar-icon" hidden aria-hidden="true"><i class="fas fa-robot"></i></span>`;
    }

    if (kind === 'group') {
        return `<span class="wa-avatar-icon" aria-hidden="true"><i class="fas fa-users"></i></span>`;
    }

    const profilePic = getConversationPhoto(conversation);
    if (profilePic) {
        return `<img class="wa-avatar-img" src="${escapeHtml(profilePic)}" alt="${escapeHtml(displayName)}" onerror="this.hidden=true;this.nextElementSibling.hidden=false">`
            + `<span class="wa-avatar-initials" hidden>${initials}</span>`;
    }
    return `<span class="wa-avatar-initials">${initials}</span>`;
}

// Classe extra do disco (.wa-avatar). Grupos (#equipe) ganham o tint verde do
// .wa-avatar--group; pessoas/maestro ficam com o relevo neumorfico padrao.
function getAvatarWrapperClass(conversation, displayName) {
    return classifyAvatarKind(conversation, displayName) === 'group' ? ' wa-avatar--group' : '';
}

function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.slice(0, len) + '...' : str;
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;')
              .replace(/</g, '&lt;')
              .replace(/>/g, '&gt;')
              .replace(/"/g, '&quot;')
              .replace(/'/g, '&#039;');
}

function showNotification(message, type = 'success') {
    // Ensure toast container exists
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'wa-toast-container';
        document.body.appendChild(container);
    }

    // Icon mapping
    const icons = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle',
        info: 'fa-info-circle'
    };

    const notification = document.createElement('div');
    notification.className = `wa-notification ${type}`;
    notification.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i><span>${escapeHtml(message)}</span>`;
    container.appendChild(notification);

    // Auto-remove with animation
    setTimeout(() => {
        notification.classList.add('removing');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// ============================================
// v13.2: BROWSER NOTIFICATIONS
// ============================================
function requestNotificationPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
}

function showBrowserNotification(msg) {
    // Respeita os toggles das settings (antes eram decorativos — notificava
    // sempre, ignorando a preferência do usuário).
    if (typeof SettingsState !== 'undefined' && !SettingsState.notifyNewMsg) return;
    if (!('Notification' in window) || Notification.permission !== 'granted') return;
    if (!document.hidden) return;

    const conv = State.conversations.find(c => c.phone === (msg.phone || State.selectedPhone));
    const name = conv ? (conv.name || conv.whatsapp_name || formatPhone(msg.phone || State.selectedPhone)) : 'Nova mensagem';
    const body = (msg.content || '').substring(0, 100);
    const icon = conv?.profilePic || '/casehub/static/img/whatsapp-icon.png';

    const notification = new Notification(name, {
        body: body,
        icon: icon,
        tag: 'wa-msg-' + (msg.phone || State.selectedPhone),
        silent: (typeof SettingsState !== 'undefined') ? !SettingsState.notifySound : false
    });

    notification.onclick = () => {
        window.focus();
        if (msg.phone && msg.phone !== State.selectedPhone) {
            selectConversation(msg.phone);
        }
        notification.close();
    };

    setTimeout(() => notification.close(), 8000);
}

// ============================================
// v13.2: TYPING INDICATOR
// ============================================
let typingTimeout = null;

function showTypingIndicator(isTyping) {
    const indicator = document.getElementById('typingIndicator');
    if (!indicator) return;

    if (isTyping) {
        indicator.classList.add('show');
        // Auto-hide after 10 seconds if no update
        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(() => {
            indicator.classList.remove('show');
        }, 10000);
    } else {
        indicator.classList.remove('show');
        clearTimeout(typingTimeout);
    }
}

// ============================================
// v13.2: MESSAGE DELIVERY STATUS (ACK)
// ============================================
function getAckIcon(ack) {
    // ack: -1=failed, 0=pending, 1=sent(server), 2=delivered, 3=read, 4=played(audio)
    if (ack === undefined || ack === null) return '<span class="wa-message-status delivered">&#10003;&#10003;</span>';
    if (ack === 'failed' || Number(ack) === -1) return '<span class="wa-message-status failed">!</span>';
    ack = Number(ack);
    if (ack === 0) return '<span class="wa-message-status pending">&#128337;</span>';
    if (ack === 1) return '<span class="wa-message-status sent">&#10003;</span>';
    if (ack === 2) return '<span class="wa-message-status delivered">&#10003;&#10003;</span>';
    if (ack >= 3) return '<span class="wa-message-status read">&#10003;&#10003;</span>';
    return '<span class="wa-message-status delivered">&#10003;&#10003;</span>';
}

function updateMessageAck(data) {
    if (!data.messageId && !data.id) return;
    const msgId = data.messageId || data.id;
    const ack = data.ack;

    // Update in State
    const msg = State.messages.find(m => m.id === msgId || m.wid === msgId);
    if (msg) {
        msg.ack = ack;
    }

    // Update in DOM without full re-render
    const msgEl = document.querySelector(`[data-msg-id="${msgId}"]`);
    if (msgEl) {
        const statusEl = msgEl.querySelector('.wa-message-status');
        if (statusEl) {
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = getAckIcon(ack);
            statusEl.replaceWith(tempDiv.firstElementChild);
        }
    }
}

// ============================================
// Tier-2: live message mutations (reaction / edit / delete)
// ============================================
// A reaction/edit/delete SSE event mutates the matching message in
// State and re-renders. Keeps reactions, edited tags and the deleted
// placeholder in sync without a full reload.
function applyMessageMutation(msg) {
    const id = msg.messageId || msg.id || msg.wa_message_id;
    if (!id) return;
    const m = State.messages.find(x =>
        String(x.id) === String(id) || String(x.wa_message_id) === String(id));
    if (!m) return;

    if (msg.type === 'reaction') {
        m.reactions = Array.isArray(m.reactions) ? m.reactions : [];
        if (msg.removed) {
            const idx = m.reactions.findIndex(r =>
                (r.emoji || r) === msg.emoji && !r.from_me);
            if (idx >= 0) m.reactions.splice(idx, 1);
        } else if (msg.emoji) {
            m.reactions.push({ emoji: msg.emoji, from_me: false });
        }
    } else if (msg.type === 'edited') {
        m.content = msg.content !== undefined ? msg.content : m.content;
        m.edited_at = msg.edited_at || new Date().toISOString();
    } else if (msg.type === 'deleted') {
        m.deleted_at = msg.deleted_at || new Date().toISOString();
    }
    renderWhatsAppMessages();
}

// ============================================
// v13.2: IMAGE LIGHTBOX
// ============================================
function openLightbox(src) {
    const lightbox = document.getElementById('imageLightbox');
    const img = document.getElementById('lightboxImage');
    img.src = src;
    lightbox.classList.add('show');
    document.body.style.overflow = 'hidden';
}

function closeLightbox() {
    const lightbox = document.getElementById('imageLightbox');
    lightbox.classList.remove('show');
    document.body.style.overflow = '';
}

document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    // Tier-2: Escape closes the top-most transient surface.
    const reactionPicker = document.getElementById('reactionPicker');
    if (reactionPicker && reactionPicker.classList.contains('show')) {
        closeReactionPicker(); return;
    }
    const forwardModal = document.getElementById('forwardModal');
    if (forwardModal && forwardModal.classList.contains('show')) {
        closeForwardModal(); return;
    }
    const mediaComposer = document.getElementById('mediaComposer');
    if (mediaComposer && mediaComposer.classList.contains('show')) {
        cancelMediaComposer(); return;
    }
    const lightbox = document.getElementById('imageLightbox');
    if (lightbox && lightbox.classList.contains('show')) {
        closeLightbox(); return;
    }
    if (replyContext) { cancelReply(); return; }
});

// ============================================
// MEDIA CONTENT RENDERER — Tier-2 full fidelity
// Images (click-to-lightbox), video (inline player), voice (CSS
// waveform, NO WebGL), audio, documents, stickers, location and
// contact-card. Caption is rendered below the media block.
// ============================================

// Normalizes the message's media kind into a coarse bucket. The
// backend may send `media_type` (text/image/audio/video/document/
// sticker) OR a raw `mimetype` — handle both.
function getMediaKind(m) {
    const t = (m.media_type || '').toLowerCase();
    const mime = (m.mimetype || '').toLowerCase();
    if (t === 'sticker' || mime === 'image/webp' && m.is_sticker) return 'sticker';
    if (t === 'image' || mime.startsWith('image/')) return 'image';
    if (t === 'video' || mime.startsWith('video/')) return 'video';
    if (t === 'audio' || t === 'ptt' || t === 'voice' || mime.startsWith('audio/')) return 'audio';
    if (t === 'location') return 'location';
    if (t === 'vcard' || t === 'contact') return 'contact';
    if (t === 'document' || t === 'file' || m.filename) return 'document';
    return 'document';
}

// Deterministic pseudo-random waveform when the backend gives no
// peak data: a hash of the message id seeds the bar heights so the
// same voice note always renders the same shape.
function buildWaveformBars(seedKey, count) {
    const peaks = [];
    let h = 2166136261;
    const s = String(seedKey || 'wa');
    for (let i = 0; i < s.length; i++) {
        h ^= s.charCodeAt(i);
        h = Math.imul(h, 16777619);
    }
    for (let i = 0; i < count; i++) {
        h = Math.imul(h ^ (h >>> 13), 16777619);
        const v = ((h >>> 0) % 70) + 25; // 25%..95%
        peaks.push(v);
    }
    return peaks;
}

function renderVoiceBubble(m, mediaUrl, isVoice) {
    const id = escapeHtml(String(m.id || m.wa_message_id || m.wid || Math.random()));
    const bars = buildWaveformBars(id, 32);
    const barsHtml = bars.map(h =>
        `<span class="wa-voice-bar" style="height:${h}%"></span>`).join('');
    const dur = m.duration ? formatDuration(m.duration) : '0:00';
    return `<div class="wa-voice" data-voice-id="${id}">
        <button class="wa-voice-play" type="button" aria-label="Reproduzir áudio"
                onclick="toggleVoicePlayback(this, '${escapeHtml(mediaUrl)}')">
            <i class="fas fa-play" aria-hidden="true"></i>
        </button>
        <div class="wa-voice-body">
            <div class="wa-voice-wave" onclick="scrubVoice(event, this)" role="slider"
                 aria-label="Progresso do áudio" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
                ${barsHtml}
            </div>
            <div class="wa-voice-meta">
                <span>${isVoice ? '<i class="fas fa-microphone wa-voice-mic" aria-hidden="true"></i>' : '<i class="fas fa-music wa-voice-mic" aria-hidden="true"></i>'}<span class="wa-voice-current">0:00</span></span>
                <span class="wa-voice-duration">${escapeHtml(dur)}</span>
            </div>
        </div>
        <audio preload="metadata" class="wa-voice-audio"
               onloadedmetadata="updateVoiceDuration(this)">
            <source src="${escapeHtml(mediaUrl)}">
        </audio>
    </div>`;
}

// Link-preview card extracted from message metadata. The backend may
// attach `link_preview` {url,title,image,domain}; we only RENDER it.
function renderLinkPreview(m) {
    const lp = m.link_preview || m.preview;
    if (!lp || !lp.url) return '';
    const domain = escapeHtml(lp.domain || (() => {
        try { return new URL(lp.url).hostname.replace(/^www\./, ''); }
        catch (e) { return lp.url; }
    })());
    const img = lp.image
        ? `<img class="wa-link-preview-img" src="${escapeHtml(lp.image)}" alt="" loading="lazy" onerror="this.remove()">`
        : '';
    return `<a class="wa-link-preview" href="${escapeHtml(lp.url)}" target="_blank" rel="noopener noreferrer">
        ${img}
        <span class="wa-link-preview-text">
            <span class="wa-link-preview-title">${escapeHtml(lp.title || lp.url)}</span>
            <span class="wa-link-preview-domain">${domain}</span>
        </span>
    </a>`;
}

function renderMessageContent(m) {
    const caption = m.caption || m.content || '';
    const captionHtml = (caption && caption !== m.media_url)
        ? `<div class="wa-message-content">${linkifyText(escapeHtml(caption))}</div>`
        : '';

    // ── Media messages ──────────────────────────────────────
    // `media_type` pode chegar como 'chat'/'text' — esse e o tipo de uma
    // mensagem de TEXTO comum do WhatsApp, NAO midia. Tratar como midia
    // apenas tipos reais, senao um "Oi" vira um documento com spinner.
    const REAL_MEDIA = ['image','video','audio','ptt','voice','document','file','sticker','location','vcard','contact'];
    const mtKind = (m.media_type || '').toLowerCase();
    if (m.hasMedia || REAL_MEDIA.includes(mtKind) || m.media_url) {
        let mediaUrl = m.media_url || m.mediaUrl;

        // Ensure media requests route through the proxy so images/videos appear correctly
        if (mediaUrl && mediaUrl.startsWith('/api/')) {
            mediaUrl = '/whatsapp-api' + mediaUrl;
        }

        const kind = getMediaKind(m);

        if (mediaUrl) {
            if (kind === 'sticker') {
                return `<img class="wa-sticker" src="${escapeHtml(mediaUrl)}" alt="Sticker" loading="lazy">`;
            }
            if (kind === 'image') {
                return `<div class="wa-message-media">
                    <img src="${escapeHtml(mediaUrl)}" alt="Imagem"
                         onclick="openLightbox('${escapeHtml(mediaUrl)}')" loading="lazy">
                </div>${captionHtml}`;
            }
            if (kind === 'video') {
                const mime = (m.mimetype || '').startsWith('video/') ? m.mimetype : 'video/mp4';
                return `<div class="wa-message-media">
                    <div class="wa-video" onclick="playInlineVideo(this)">
                        <video preload="metadata" playsinline>
                            <source src="${escapeHtml(mediaUrl)}" type="${escapeHtml(mime)}">
                        </video>
                        <div class="wa-video-play"><i class="fas fa-play" aria-hidden="true"></i></div>
                    </div>
                </div>${captionHtml}`;
            }
            if (kind === 'audio') {
                const isVoice = ['ptt', 'voice'].includes((m.media_type || '').toLowerCase());
                return `<div class="wa-message-media">${renderVoiceBubble(m, mediaUrl, isVoice)}</div>${captionHtml}`;
            }
            // document / file
            const fileName = m.filename || m.file_name || caption || 'Documento';
            const fileIcon = getFileIcon(m.mimetype || m.media_type);
            // OCR (Fase 3): PDF recebido traz o texto extraído — bloco
            // expansível nativo (<details>), buscável pelo Ctrl+F do operador.
            const ocrHtml = m.ocr_text
                ? `<details class="wa-doc-ocr">
                    <summary><i class="fas fa-file-lines" aria-hidden="true"></i> Texto extraído do PDF</summary>
                    <div class="wa-doc-ocr-text">${linkifyText(escapeHtml(m.ocr_text))}</div>
                </details>`
                : '';
            return `<div class="wa-message-media">
                <a href="${escapeHtml(mediaUrl)}" target="_blank" rel="noopener" class="wa-message-media-link">
                    <div class="wa-message-media-doc">
                        <i class="fas ${fileIcon}" aria-hidden="true"></i>
                        <div class="wa-message-media-doc-info">
                            <div class="wa-message-media-doc-name">${escapeHtml(fileName)}</div>
                            <div class="wa-message-media-doc-size">${m.file_size || m.filesize ? formatFileSize(m.file_size || m.filesize) : 'Documento'}</div>
                        </div>
                        <i class="fas fa-download wa-message-media-download-icon"></i>
                    </div>
                </a>
                ${ocrHtml}
            </div>`;
        }

        // Media exists but no URL yet (still downloading on the bot side)
        if (m.hasMedia && !mediaUrl) {
            return `<div class="wa-message-media">
                <div class="wa-message-media-doc">
                    <i class="fas fa-spinner fa-spin" aria-hidden="true"></i>
                    <div class="wa-message-media-doc-info">
                        <div class="wa-message-media-doc-name">Carregando mídia...</div>
                    </div>
                </div>
            </div>${captionHtml}`;
        }
    }

    // ── Location / contact-card (no media_url) ──────────────
    if ((m.media_type || '').toLowerCase() === 'location' && (m.location || m.latitude)) {
        const loc = m.location || {};
        const label = loc.name || loc.address || m.content || 'Localização compartilhada';
        return `<div class="wa-location">
            <div class="wa-location-map" aria-hidden="true"><i class="fas fa-location-dot"></i></div>
            <span class="wa-location-label">${escapeHtml(label)}</span>
        </div>`;
    }
    if (['vcard', 'contact'].includes((m.media_type || '').toLowerCase())) {
        const c = m.contact_card || m.vcard || {};
        const cName = c.name || m.content || 'Contato';
        const cPhone = c.phone || '';
        return `<div class="wa-contact-card">
            <span class="wa-contact-card-avatar" aria-hidden="true">${escapeHtml(getInitials(cName))}</span>
            <div>
                <div class="wa-contact-card-name">${escapeHtml(cName)}</div>
                <div class="wa-contact-card-phone">${escapeHtml(cPhone)}</div>
            </div>
        </div>`;
    }

    // ── Regular text — link preview card (if any) + linkified body ──
    const previewHtml = renderLinkPreview(m);
    const text = escapeHtml(m.content || '');
    return `${previewHtml}<div class="wa-message-content">${linkifyText(text)}</div>`;
}

// Inline video — swap to native controls once the operator taps play.
function playInlineVideo(wrap) {
    const video = wrap.querySelector('video');
    if (!video) return;
    wrap.classList.add('playing');
    video.controls = true;
    video.play().catch(() => {});
}

// Voice playback — one <audio> per bubble; the waveform bars recolour
// as playback progresses. transform/opacity-free, 60fps-safe.
let activeVoiceAudio = null;
function toggleVoicePlayback(btn, url) {
    const wrap = btn.closest('.wa-voice');
    const audio = wrap.querySelector('.wa-voice-audio');
    const icon = btn.querySelector('i');

    if (audio.paused) {
        // Pause any other playing voice note first.
        if (activeVoiceAudio && activeVoiceAudio !== audio) {
            activeVoiceAudio.pause();
        }
        activeVoiceAudio = audio;
        audio.play().then(() => {
            icon.className = 'fas fa-pause';
        }).catch(() => {
            showNotification('Não foi possível reproduzir o áudio', 'error');
        });

        audio.ontimeupdate = () => {
            const pct = audio.duration ? audio.currentTime / audio.duration : 0;
            paintWaveform(wrap, pct);
            const cur = wrap.querySelector('.wa-voice-current');
            if (cur) cur.textContent = formatDuration(audio.currentTime);
        };
        audio.onended = () => {
            icon.className = 'fas fa-play';
            paintWaveform(wrap, 0);
            const cur = wrap.querySelector('.wa-voice-current');
            if (cur) cur.textContent = '0:00';
        };
    } else {
        audio.pause();
        icon.className = 'fas fa-play';
    }
}

function paintWaveform(wrap, pct) {
    const bars = wrap.querySelectorAll('.wa-voice-bar');
    const cut = Math.round(bars.length * pct);
    bars.forEach((b, i) => b.classList.toggle('played', i < cut));
    const wave = wrap.querySelector('.wa-voice-wave');
    if (wave) wave.setAttribute('aria-valuenow', Math.round(pct * 100));
}

// Preenche a duração real da nota de voz quando os metadados carregam —
// o backend não envia `duration`, então o balão nasce com 0:00.
function updateVoiceDuration(audio) {
    const wrap = audio.closest('.wa-voice');
    if (!wrap || !isFinite(audio.duration) || audio.duration <= 0) return;
    const dur = wrap.querySelector('.wa-voice-duration');
    if (dur) dur.textContent = formatDuration(audio.duration);
}

// Click-to-scrub on the waveform track.
function scrubVoice(event, wave) {
    const wrap = wave.closest('.wa-voice');
    const audio = wrap.querySelector('.wa-voice-audio');
    const rect = wave.getBoundingClientRect();
    const pct = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    if (audio.duration) {
        audio.currentTime = pct * audio.duration;
        paintWaveform(wrap, pct);
    }
}

function formatDuration(seconds) {
    const s = Math.max(0, Math.floor(seconds || 0));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

function getFileIcon(mimeType) {
    if (!mimeType) return 'fa-file';
    if (mimeType.includes('pdf')) return 'fa-file-pdf';
    if (mimeType.includes('word') || mimeType.includes('document')) return 'fa-file-word';
    if (mimeType.includes('sheet') || mimeType.includes('excel')) return 'fa-file-excel';
    if (mimeType.includes('presentation') || mimeType.includes('powerpoint')) return 'fa-file-powerpoint';
    if (mimeType.includes('zip') || mimeType.includes('rar') || mimeType.includes('tar')) return 'fa-file-archive';
    return 'fa-file-alt';
}

function formatFileSize(bytes) {
    if (!bytes) return '';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let size = parseInt(bytes);
    while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
    return size.toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
}

function linkifyText(text) {
    // Convert URLs to clickable links
    return text.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener" class="wa-message-link">$1</a>');
}

// ============================================
// TAB SWITCHING
// ============================================
let currentTab = 'chat';

function switchTab(tab) {
    currentTab = tab;

    // Update tab buttons
    document.querySelectorAll('.wa-tab').forEach(t => t.classList.remove('active'));
    document.getElementById('tab' + tab.charAt(0).toUpperCase() + tab.slice(1)).classList.add('active');

    // Update tab content. Each panel is declared `role="tabpanel" hidden` in
    // chat.html — toggle BOTH the `hidden` attribute (a11y / aria-controls) and
    // inline display so screen readers and layout agree.
    const panels = {
        chat: ['tabContentChat', 'flex'],
        settings: ['tabContentSettings', 'block'],
        templates: ['tabContentTemplates', 'block'],
    };
    Object.entries(panels).forEach(([name, [id, disp]]) => {
        const el = document.getElementById(id);
        if (!el) return;
        const on = name === tab;
        el.hidden = !on;
        el.style.display = on ? disp : 'none';
    });

    // Load data for specific tabs
    if (tab === 'settings') {
        loadSettings();
        loadStats();
    } else if (tab === 'templates') {
        renderTemplatesGrid();
    }
}

// ============================================
// SETTINGS FUNCTIONS
// ============================================
const SettingsState = {
    globalBotEnabled: true,
    notifyNewMsg: false,
    notifySound: true
};

async function loadSettings() {
    // Load bot config from server API
    try {
        const response = await fetch(WHATSAPP_API_BASE + "/api/config");
        if (response.ok) {
            const config = await response.json();
            // Convert hour numbers to time strings
            const startHour = String(config.businessHoursStart || 9).padStart(2, "0");
            const endHour = String(config.businessHoursEnd || 18).padStart(2, "0");
            document.getElementById("workHoursStart").value = startHour + ":00";
            document.getElementById("workHoursEnd").value = endHour + ":00";
            console.log("[Settings] Loaded from server:", config);
        }
    } catch (e) {
        console.warn("[Settings] Failed to load from server, using defaults:", e.message);
    }
    
    // Also load local settings (notifications, etc)
    const saved = localStorage.getItem("waSettings");
    if (saved) {
        const settings = JSON.parse(saved);
        SettingsState.globalBotEnabled = settings.globalBotEnabled !== false;
        SettingsState.notifyNewMsg = settings.notifyNewMsg || false;
        SettingsState.notifySound = settings.notifySound !== false;
        document.getElementById("humanTimeout").value = settings.humanTimeout || 5;
        document.getElementById("calendlyFree").value = settings.calendlyFree || "CALENDLY_FREE_URL";
        document.getElementById("calendlyPaid").value = settings.calendlyPaid || "CALENDLY_PAID_URL";
    }

    // Update UI
    updateSettingsUI();
}


function updateSettingsUI() {
    document.getElementById('globalBotToggle').classList.toggle('active', SettingsState.globalBotEnabled);
    document.getElementById('notifyNewMsg').classList.toggle('active', SettingsState.notifyNewMsg);
    document.getElementById('notifySound').classList.toggle('active', SettingsState.notifySound);
    document.getElementById('connectionStatus').textContent = State.isConnected ? 'Conectado' : 'Desconectado';
}

function toggleGlobalBot() {
    SettingsState.globalBotEnabled = !SettingsState.globalBotEnabled;
    updateSettingsUI();
}

function toggleNotifyNewMsg() {
    SettingsState.notifyNewMsg = !SettingsState.notifyNewMsg;
    updateSettingsUI();

    // Request notification permission if enabling
    if (SettingsState.notifyNewMsg && Notification.permission === 'default') {
        Notification.requestPermission();
    }
}

function toggleNotifySound() {
    SettingsState.notifySound = !SettingsState.notifySound;
    updateSettingsUI();
}

function saveSettings() {
    const settings = {
        globalBotEnabled: SettingsState.globalBotEnabled,
        notifyNewMsg: SettingsState.notifyNewMsg,
        notifySound: SettingsState.notifySound,
        workHoursStart: document.getElementById('workHoursStart').value,
        workHoursEnd: document.getElementById('workHoursEnd').value,
        humanTimeout: document.getElementById('humanTimeout').value,
        calendlyFree: document.getElementById('calendlyFree').value,
        calendlyPaid: document.getElementById('calendlyPaid').value
    };

    localStorage.setItem('waSettings', JSON.stringify(settings));
    showNotification('Configurações salvas!');
}

async function loadStats() {
    try {
        // Update stats with conversation data
        document.getElementById('statTotalLeads').textContent = State.conversations.length;
        document.getElementById('statActiveConvs').textContent = State.conversations.filter(c => {
            const updated = new Date(c.updated_at);
            const dayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
            return updated > dayAgo;
        }).length;
        document.getElementById('statBotResponses').textContent = '--';
        document.getElementById('statHumanHandoffs').textContent = State.conversations.filter(c => !c.bot_enabled).length;
    } catch (error) {
        console.error('[Stats] Error:', error);
    }
}

async function checkWhatsAppStatus() {
    try {
        const data = await fetchAPI('/api/status');
        const connected = data.connected || data.ok;
        document.getElementById('connectionStatus').textContent = connected ? 'Conectado' : 'Desconectado';
        showNotification(connected ? 'WhatsApp conectado!' : 'WhatsApp desconectado');
    } catch (error) {
        document.getElementById('connectionStatus').textContent = 'Erro ao verificar';
        showNotification('Erro ao verificar conexão', 'error');
    }
}

async function restartWhatsApp() {
    if (!confirm('Tem certeza? Isso irá desconectar o WhatsApp e você precisará escanear o QR novamente.')) {
        return;
    }

    try {
        await fetch(WHATSAPP_API_BASE + '/api/restart', { method: 'POST' });
        showNotification('WhatsApp reiniciando...');
        setTimeout(() => location.reload(), 2000);
    } catch (error) {
        showNotification('Erro ao reiniciar', 'error');
    }
}

// ============================================
// TEMPLATES MANAGEMENT
// ============================================
let selectedCategory = 'all';
let editingTemplateId = null;

function filterTemplatesByCategory(category) {
    selectedCategory = category;

    // Update filter buttons
    document.querySelectorAll('.wa-filter-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.cat === category);
    });

    renderTemplatesGrid();
}

function renderTemplatesGrid() {
    const container = document.getElementById('templatesGrid');

    let filtered = TEMPLATES;
    if (selectedCategory !== 'all') {
        filtered = TEMPLATES.filter(t => t.cat === selectedCategory);
    }

    if (filtered.length === 0) {
        container.innerHTML = `<div class="wa-empty-list wa-empty-list--grid">
            Nenhum template encontrado nesta categoria
        </div>`;
        return;
    }

    container.innerHTML = filtered.map(t => `
        <div class="wa-template-card">
            <div class="wa-template-card-header">
                <div class="wa-template-card-title">${escapeHtml(t.name)}</div>
                <div class="wa-template-card-cat">${escapeHtml(t.cat)}</div>
            </div>
            <div class="wa-template-card-text">${escapeHtml(t.text)}</div>
            <div class="wa-template-card-actions">
                <button class="wa-template-card-btn edit" onclick="editTemplate(${t.id})">
                    <i class="fas fa-edit"></i> Editar
                </button>
                <button class="wa-template-card-btn delete" onclick="deleteTemplate(${t.id})">
                    <i class="fas fa-trash"></i> Excluir
                </button>
            </div>
        </div>
    `).join('');
}

function openAddTemplateModal() {
    editingTemplateId = null;
    document.getElementById('modalTitle').textContent = 'Novo Template';
    document.getElementById('editTemplateId').value = '';
    document.getElementById('editTemplateName').value = '';
    document.getElementById('editTemplateCategory').value = 'Greeting';
    document.getElementById('editTemplateText').value = '';
    document.getElementById('templateModal').classList.add('show');
}

function editTemplate(id) {
    const template = TEMPLATES.find(t => t.id === id);
    if (!template) return;

    editingTemplateId = id;
    document.getElementById('modalTitle').textContent = 'Editar Template';
    document.getElementById('editTemplateId').value = id;
    document.getElementById('editTemplateName').value = template.name;
    document.getElementById('editTemplateCategory').value = template.cat;
    document.getElementById('editTemplateText').value = template.text;
    document.getElementById('templateModal').classList.add('show');
}

function closeEditTemplateModal() {
    document.getElementById('templateModal').classList.remove('show');
    editingTemplateId = null;
}

function saveTemplate() {
    const name = document.getElementById('editTemplateName').value.trim();
    const category = document.getElementById('editTemplateCategory').value;
    const text = document.getElementById('editTemplateText').value.trim();

    if (!name || !text) {
        showNotification('Preencha todos os campos', 'error');
        return;
    }

    if (editingTemplateId) {
        // Update existing
        const template = TEMPLATES.find(t => t.id === editingTemplateId);
        if (template) {
            template.name = name;
            template.cat = category;
            template.text = text;
        }
        showNotification('Template atualizado!');
    } else {
        // Add new. IDs custom começam em >100 para que loadCustomTemplates os
        // reconheça e persista (antes pegava o próximo id sequencial — ex. 23 —
        // que era ignorado no reload e o template recém-criado sumia).
        const newId = Math.max(100, ...TEMPLATES.map(t => t.id)) + 1;
        TEMPLATES.push({ id: newId, cat: category, name: name, text: text });
        showNotification('Template adicionado!');
    }

    // Persiste SÓ os templates criados pelo usuário (id>100). Salvar o array
    // inteiro fazia os defaults antigos (imigração US) ressuscitarem sobre os
    // novos defaults BR vindos do código.
    localStorage.setItem('customTemplates', JSON.stringify(TEMPLATES.filter(t => t.id > 100)));

    closeEditTemplateModal();
    renderTemplatesGrid();
    renderTemplates(); // Update inline templates menu too
}

function deleteTemplate(id) {
    if (!confirm('Tem certeza que deseja excluir este template?')) {
        return;
    }

    const index = TEMPLATES.findIndex(t => t.id === id);
    if (index > -1) {
        TEMPLATES.splice(index, 1);
        localStorage.setItem('customTemplates', JSON.stringify(TEMPLATES.filter(t => t.id > 100)));
        renderTemplatesGrid();
        renderTemplates();
        showNotification('Template excluído!');
    }
}

// Load custom templates from localStorage on init
function loadCustomTemplates() {
    const saved = localStorage.getItem('customTemplates');
    if (saved) {
        try {
            const customTemplates = JSON.parse(saved);
            // Só re-injeta os templates CRIADOS pelo usuário (id>100). Os defaults
            // (id<=100) vêm sempre do código (BR atuais) — não deixa edição antiga
            // em localStorage sobrescrever/ressuscitar defaults trocados.
            customTemplates.forEach(ct => {
                if (ct && ct.id > 100 && !TEMPLATES.some(t => t.id === ct.id)) {
                    TEMPLATES.push(ct);
                }
            });
        } catch (e) {
            console.error('Error loading custom templates:', e);
        }
    }
}

// ============================================
// INITIALIZATION
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    // Fix: Add click listener for templates button
    const templatesBtn = document.querySelector('button[title="Templates (T)"]');
    if (templatesBtn) templatesBtn.addEventListener('click', toggleTemplates);
    loadCustomTemplates();
    checkStatus();
    setTimeout(applyConnectionQueryMode, 100);
    loadConversations(true);
    startConversationsSSE(); // v13.1: Real-time conversation list updates
    renderTemplates();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    State.cleanup();
    stopMessagesPolling();
    stopConversationsSSE();
    stopQRPolling();
});

// ============================================
// TEXTAREA AUTO-RESIZE
// ============================================
function autoResizeTextarea(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
}

// Add auto-resize to messageInput
document.getElementById('messageInput').addEventListener('input', function() {
    autoResizeTextarea(this);
});

// Reset height when message is sent
const originalSendMessage = sendMessage;
sendMessage = async function() {
    await originalSendMessage();
    const input = document.getElementById('messageInput');
    input.style.height = 'auto';
};

// ============================================
// NOVAS FUNCIONALIDADES - Fase 2 e 3
// ============================================

// ============================================
// FILTROS AVANCADOS
// ============================================
let currentFilter = 'all';
let urgentConversations = new Set();

// Load urgent conversations from localStorage
function loadUrgentConversations() {
    const saved = localStorage.getItem('urgentConversations');
    if (saved) {
        try {
            urgentConversations = new Set(JSON.parse(saved));
        } catch (e) {
            urgentConversations = new Set();
        }
    }
}

function saveUrgentConversations() {
    localStorage.setItem('urgentConversations', JSON.stringify([...urgentConversations]));
}

// Abas de tag (Victor 10/06): separa conversas por tag/cliente. Aditivo e
// defensivo — tags podem vir como array, string CSV ou ausentes; sem tags a
// barra fica escondida (degrada graciosamente, nunca quebra). escapeHtml em
// todo conteúdo de tag (evita XSS via nome de tag vindo do backend).
function convTags(c) {
    const t = c && c.tags;
    if (Array.isArray(t)) return t.map(x => String(x).trim()).filter(Boolean);
    if (typeof t === 'string') return t.split(',').map(x => x.trim()).filter(Boolean);
    return [];
}

function renderTagChips() {
    const bar = document.getElementById('tagFilterBar');
    if (!bar) return;
    const counts = {};
    (State.conversations || []).forEach(c => convTags(c).forEach(t => { counts[t] = (counts[t] || 0) + 1; }));
    const tags = Object.keys(counts).sort((a, b) => a.localeCompare(b, 'pt-BR'));
    if (!tags.length) { bar.hidden = true; bar.innerHTML = ''; return; }
    bar.hidden = false;
    bar.innerHTML = '<span class="wa-tagbar-label"><i class="fas fa-tags" aria-hidden="true"></i> Tags</span>' +
        tags.map(t => {
            const f = 'tag:' + t;
            const on = currentFilter === f;
            return '<button class="wa-filter-chip wa-tag-chip' + (on ? ' active' : '') + '" type="button"'
                + ' data-filter="' + escapeHtml(f) + '" onclick="applyFilter(this.dataset.filter)"'
                + ' aria-pressed="' + on + '" title="Conversas com a tag ' + escapeHtml(t) + '">'
                + escapeHtml(t) + ' <span class="wa-tag-chip__count">' + counts[t] + '</span></button>';
        }).join('');
}

function applyFilter(filter) {
    currentFilter = filter;

    // Update filter buttons (inclui as wa-tag-chip, que tambem sao wa-filter-chip)
    document.querySelectorAll('.wa-filter-chip').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === filter);
    });

    renderConversations();
}

// Override renderConversations to support filters
const originalRenderConversations = renderConversations;
renderConversations = function() {
    const container = document.getElementById('conversationsList');
    const searchQuery = document.getElementById('searchInput').value.toLowerCase();

    let filtered = State.conversations;

    // Apply search filter
    if (searchQuery) {
        filtered = filtered.filter(c =>
            (c.name || '').toLowerCase().includes(searchQuery) ||
            (c.whatsapp_name || '').toLowerCase().includes(searchQuery) ||
            (c.phone || '').includes(searchQuery) ||
            (c.lastMessage || '').toLowerCase().includes(searchQuery)
        );
    }

    // Apply status filter
    switch (currentFilter) {
        case 'unread':
            filtered = filtered.filter(c => parseInt(c.unread) > 0);
            break;
        case 'needs-response':
            filtered = filtered.filter(c => (c.from_bot === 0 || c.from_bot === false) && parseInt(c.unread) > 0);
            break;
        case 'human':
            filtered = filtered.filter(c => c.human_takeover === 1 || c.human_takeover === true);
            break;
        case 'urgent':
            filtered = filtered.filter(c => urgentConversations.has(c.phone));
            break;
    }

    // Abas de tag: filtra por tag selecionada (separa conversas por cliente/tag).
    if (typeof currentFilter === 'string' && currentFilter.indexOf('tag:') === 0) {
        const wantTag = currentFilter.slice(4);
        filtered = filtered.filter(c => convTags(c).indexOf(wantTag) !== -1);
    }

    renderTagChips();

    if (filtered.length === 0) {
        container.innerHTML = `<div style="padding: 20px; text-align: center; color: var(--wa-text-secondary);">
            ${State.conversations.length === 0 ? 'Nenhuma conversa ainda' : 'Nenhum resultado encontrado'}
        </div>`;
        return;
    }

    container.innerHTML = filtered.map(c => {
        const name = getConversationDisplayName(c);
        const phoneLabel = formatPhone(c.phone);
        const time = c.lastMessageTime ? formatTime(c.lastMessageTime) : '';
        const isActive = c.phone === State.selectedPhone;
        const preview = c.lastMessage ? truncate(c.lastMessage, 40) : 'Sem mensagens';

        // Indicadores de status
        const needsResponse = c.from_bot === 0 || c.from_bot === false;
        const unreadCount = parseInt(c.unread) || 0;
        const isHumanTakeover = c.human_takeover === 1 || c.human_takeover === true;
        const isNeverContact = c.never_contact === 1 || c.never_contact === true;
        const isUrgent = urgentConversations.has(c.phone);

        // Classes adicionais baseadas no status
        const extraClasses = [];
        if (needsResponse && unreadCount > 0) extraClasses.push('needs-response');
        if (isHumanTakeover) extraClasses.push('human-takeover');
        if (isNeverContact) extraClasses.push('never-contact');
        if (isUrgent) extraClasses.push('urgent');

        // Calculate response time
        let responseTimeBadge = '';
        if (needsResponse && c.updated_at) {
            const hoursSince = (Date.now() - new Date(c.updated_at).getTime()) / (1000 * 60 * 60);
            if (hoursSince > 24) {
                responseTimeBadge = `<span class="wa-response-time urgent">${Math.floor(hoursSince / 24)}d</span>`;
            } else if (hoursSince > 4) {
                responseTimeBadge = `<span class="wa-response-time">${Math.floor(hoursSince)}h</span>`;
            }
        }

        const avatarContent2 = renderAvatarContent(c, name);
        const avatarStyle = getAvatarGradientStyle(c.phone || name);
        const avatarWrapClass = getAvatarWrapperClass(c, name);

        return `
            <div class="wa-conversation ${isActive ? 'active' : ''} ${extraClasses.join(' ')}" onclick="selectConversation('${c.phone}')">
                <div class="wa-avatar${avatarWrapClass}" style="${avatarStyle}">${avatarContent2}</div>
                <div class="wa-conv-info">
                    <div class="wa-conv-header">
                        <span class="wa-conv-name">
                            ${isUrgent ? '<i class="fas fa-exclamation-triangle" style="color: var(--wa-red); margin-right: 4px;"></i>' : ''}
                            ${escapeHtml(name)}
                            ${getOwnerBadge(c)}
                            ${isHumanTakeover ? ' <span class="human-badge">👤</span>' : ''}
                            ${isNeverContact ? ' <span class="never-contact-badge"><i class="fas fa-ban"></i></span>' : ''}
                        </span>
                        <span class="wa-conv-time">${time}${responseTimeBadge}</span>
                    </div>
                    ${phoneLabel !== name ? `<div class="wa-conv-phone">${escapeHtml(phoneLabel)}</div>` : ''}
                    <div class="wa-conv-preview">
                        ${needsResponse ? '<span class="needs-reply-indicator">⚠️</span>' : ''}
                        ${escapeHtml(preview)}
                        ${unreadCount > 0 ? `<span class="wa-unread">${unreadCount}</span>` : ''}
                    </div>
                </div>
            </div>
        `;
    }).join('');
};

// ============================================
// EMOJI PICKER — categorized + searchable (Tier-2)
// Hick's Law: category tabs cut the visual search cost; the search
// box collapses the choice space to a query. Keyword index lets the
// operator type "thumbs", "heart", "fogo" instead of scanning a grid.
// ============================================
const EMOJI_CATEGORIES = [
    {
        id: 'recent', icon: '🕓', label: 'Recentes',
        emojis: [] // filled from localStorage at runtime
    },
    {
        id: 'smileys', icon: '😀', label: 'Smileys e pessoas',
        emojis: [
            ['😀','grin sorriso'],['😃','smile feliz'],['😄','laugh riso'],['😁','beam'],
            ['😅','sweat'],['😂','joy lol chorando rindo'],['🤣','rofl rindo'],['😊','blush'],
            ['😇','angel anjo'],['🙂','slight'],['🙃','upside'],['😉','wink piscada'],
            ['😍','heart eyes amor'],['🥰','love amor'],['😘','kiss beijo'],['😗','kiss'],
            ['😋','yum delicia'],['😛','tongue'],['😜','wink tongue'],['🤪','zany doido'],
            ['🤔','think pensar duvida'],['🤨','raised'],['😐','neutral'],['😑','expressionless'],
            ['😶','no mouth'],['🙄','roll eyes'],['😏','smirk'],['😣','persevere'],
            ['😥','sad triste'],['😮','open mouth surpresa'],['🤐','zipper'],['😯','hushed'],
            ['😪','sleepy sono'],['😫','tired cansado'],['🥱','yawn bocejo'],['😴','sleep dormir'],
            ['😌','relieved'],['😔','pensive'],['😟','worried preocupado'],['😕','confused'],
            ['🙁','frown'],['☹️','frowning'],['😦','anguished'],['😧','anguished'],
            ['😢','cry chorar'],['😭','sob choro'],['😤','triumph raiva'],['😠','angry bravo'],
            ['😡','rage furia'],['🤬','curse'],['😈','devil diabo'],['👿','imp'],
            ['🥳','party festa'],['🥺','pleading'],['😎','cool oculos'],['🤓','nerd'],
            ['🤗','hug abraco'],['🤭','hand mouth'],['🤫','shh'],['😬','grimace'],
            ['😱','scream susto'],['😳','flushed'],['🥵','hot calor'],['🥶','cold frio'],
            ['🤒','sick doente'],['🤕','hurt'],['🤧','sneeze'],['😷','mask mascara'],
            ['👋','wave aceno tchau'],['🤝','handshake aperto'],['👍','thumbs up joia ok positivo'],
            ['👎','thumbs down negativo'],['👌','ok perfeito'],['✌️','peace paz'],['🤞','fingers crossed'],
            ['🙏','pray reza obrigado please'],['👏','clap palmas'],['💪','muscle forca'],['🤙','call me'],
            ['🫶','heart hands'],['👀','eyes olhos'],['🧠','brain cerebro']
        ]
    },
    {
        id: 'gestures', icon: '❤️', label: 'Coração e símbolos',
        emojis: [
            ['❤️','heart amor vermelho'],['🧡','orange heart'],['💛','yellow heart'],
            ['💚','green heart'],['💙','blue heart'],['💜','purple heart'],['🖤','black heart'],
            ['🤍','white heart'],['🤎','brown heart'],['💔','broken heart'],['❣️','heart exclamation'],
            ['💕','two hearts'],['💖','sparkle heart'],['💗','growing heart'],['💝','gift heart'],
            ['⭐','star estrela'],['🌟','glowing star'],['✨','sparkles brilho'],['💫','dizzy'],
            ['🔥','fire fogo quente'],['💯','hundred cem'],['✅','check ok feito'],['❌','cross x errado'],
            ['❗','exclamation'],['❓','question duvida'],['⚠️','warning aviso'],['💡','idea ideia'],
            ['🎉','party tada festa'],['🎊','confetti'],['🎁','gift presente'],['🏆','trophy'],
            ['💰','money dinheiro'],['💳','card cartao'],['📈','chart up'],['📉','chart down']
        ]
    },
    {
        id: 'objects', icon: '📎', label: 'Objetos e trabalho',
        emojis: [
            ['📌','pin'],['📎','clip clipe'],['📝','memo nota'],['📅','calendar agenda'],
            ['📆','calendar'],['🗓️','calendar'],['📞','phone telefone'],['☎️','phone'],
            ['📱','mobile celular'],['💬','speech chat mensagem'],['💭','thought'],['📧','email'],
            ['✉️','envelope'],['📤','outbox'],['📥','inbox'],['📁','folder pasta'],
            ['📄','document documento'],['📃','page'],['🔗','link'],['🔒','lock cadeado'],
            ['🔑','key chave'],['⏰','alarm'],['⏳','hourglass'],['⌛','hourglass'],
            ['🕓','clock relogio'],['📍','location local'],['🗺️','map mapa'],['🏠','home casa'],
            ['🏢','office escritorio'],['✈️','plane aviao viagem'],['🚗','car carro'],['💼','briefcase'],
            ['⚖️','scale justica advogado'],['🇧🇷','brazil brasil'],['🇺🇸','usa eua estados unidos']
        ]
    }
];

const EMOJI_RECENT_KEY = 'waEmojiRecent';
let currentEmojiCategory = 'smileys';

function getRecentEmojis() {
    try {
        const r = JSON.parse(localStorage.getItem(EMOJI_RECENT_KEY) || '[]');
        return Array.isArray(r) ? r.slice(0, 24) : [];
    } catch (e) { return []; }
}

function pushRecentEmoji(emoji) {
    const recent = getRecentEmojis().filter(e => e !== emoji);
    recent.unshift(emoji);
    try { localStorage.setItem(EMOJI_RECENT_KEY, JSON.stringify(recent.slice(0, 24))); } catch (e) {}
}

function initEmojiPicker() {
    const cats = document.getElementById('emojiCategories');
    if (cats && !cats.children.length) {
        cats.innerHTML = EMOJI_CATEGORIES.map(c =>
            `<button class="wa-emoji-cat-btn${c.id === currentEmojiCategory ? ' active' : ''}"
                     type="button" role="tab" data-cat="${c.id}"
                     aria-label="${escapeHtml(c.label)}"
                     onclick="selectEmojiCategory('${c.id}')">${c.icon}</button>`
        ).join('');
    }
    renderEmojiGrid();
}

function selectEmojiCategory(catId) {
    currentEmojiCategory = catId;
    const search = document.getElementById('emojiSearch');
    if (search) search.value = '';
    document.querySelectorAll('.wa-emoji-cat-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.cat === catId));
    renderEmojiGrid();
}

// Renders either the active category, or — when a search query is
// present — a flat keyword-filtered result set across all categories.
function renderEmojiGrid() {
    const grid = document.getElementById('emojiGrid');
    if (!grid) return;
    const query = (document.getElementById('emojiSearch')?.value || '').toLowerCase().trim();

    let html = '';
    if (query) {
        const seen = new Set();
        const hits = [];
        EMOJI_CATEGORIES.forEach(c => {
            (c.emojis || []).forEach(pair => {
                if (!Array.isArray(pair) || !pair[0]) return;
                const [emoji, keywords] = pair;
                if (seen.has(emoji)) return;
                if ((keywords || '').includes(query) || emoji === query) {
                    seen.add(emoji);
                    hits.push(emoji);
                }
            });
        });
        html = hits.length
            ? hits.map(emojiBtn).join('')
            : '<div class="wa-emoji-empty">Nenhum emoji encontrado</div>';
    } else if (currentEmojiCategory === 'recent') {
        const recent = getRecentEmojis();
        html = recent.length
            ? recent.map(emojiBtn).join('')
            : '<div class="wa-emoji-empty">Seus emojis recentes aparecem aqui</div>';
    } else {
        const cat = EMOJI_CATEGORIES.find(c => c.id === currentEmojiCategory);
        html = (cat?.emojis || [])
            .filter(p => Array.isArray(p) && p[0])
            .map(p => emojiBtn(p[0]))
            .join('');
    }
    grid.innerHTML = html;
}

function emojiBtn(emoji) {
    const safe = emoji.replace(/'/g, "\\'");
    return `<button class="wa-emoji-btn" type="button" role="option" onclick="insertEmoji('${safe}')" aria-label="emoji ${emoji}">${emoji}</button>`;
}

function filterEmojis() {
    renderEmojiGrid();
}

function toggleEmojiPicker() {
    const picker = document.getElementById('emojiPicker');
    const isShowing = picker.classList.contains('show');

    document.getElementById('templatesMenu').classList.remove('show');
    closeAttachMenu();

    picker.classList.toggle('show');

    if (!isShowing) {
        initEmojiPicker();
        const search = document.getElementById('emojiSearch');
        if (search) setTimeout(() => search.focus(), 50);
    }
}

function insertEmoji(emoji) {
    const input = document.getElementById('messageInput');
    const start = input.selectionStart;
    const end = input.selectionEnd;
    const text = input.value;

    input.value = text.substring(0, start) + emoji + text.substring(end);
    input.focus();
    input.setSelectionRange(start + emoji.length, start + emoji.length);
    pushRecentEmoji(emoji);

    // Don't close picker so user can insert multiple emojis
}

// Close emoji picker when clicking outside
document.addEventListener('click', (e) => {
    const picker = document.getElementById('emojiPicker');
    const btn = e.target.closest('.wa-toolbar-btn');
    const pickerEl = e.target.closest('.wa-emoji-picker');

    if (!btn && !pickerEl && picker && picker.classList.contains('show')) {
        picker.classList.remove('show');
    }
});

// ============================================
// FILE ATTACHMENT — opens the media composer (preview + caption)
// ============================================
function triggerFileUpload(accept) {
    const input = document.getElementById('fileInput');
    if (accept) input.setAttribute('accept', accept);
    closeAttachMenu();
    input.click();
}

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    // Validate file size (max 16MB — WhatsApp media limit)
    if (file.size > 16 * 1024 * 1024) {
        showNotification('Arquivo muito grande (máx 16MB)', 'error');
        event.target.value = '';
        return;
    }

    if (!State.selectedPhone) {
        showNotification('Selecione uma conversa primeiro', 'error');
        event.target.value = '';
        return;
    }

    // Open the composer so the operator confirms + captions the file.
    openMediaComposer(file);
}

async function uploadFile(file) {
    if (!State.selectedPhone) {
        showNotification('Selecione uma conversa primeiro', 'error');
        return;
    }

    showNotification('Enviando arquivo...', 'info');

    try {
        // v13.1: Fixed - use FormData for file upload (was sending JSON with undefined text)
        const formData = new FormData();
        formData.append('file', file);
        formData.append('phone', State.selectedPhone);
        formData.append('caption', file.name);

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 30000);

        const response = await fetch(WHATSAPP_API_BASE + '/api/send-media', {
            method: 'POST',
            body: formData,
            signal: controller.signal
        });
        clearTimeout(timeout);

        if (response.ok) {
            showNotification('Arquivo enviado!', 'success');
            const loadId = ++currentLoadId;
            loadMessages(State.selectedPhone, loadId);
        } else {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error || 'Falha no envio');
        }
    } catch (error) {
        const errMsg = error.name === 'AbortError' ? 'Timeout - tente novamente' : error.message || 'Erro ao enviar arquivo';
        showNotification(errMsg, 'error');
    }
}

// ============================================
// SEARCH IN MESSAGES
// ============================================
let searchResults = [];
let currentSearchIndex = -1;

function toggleSearchMessages() {
    const bar = document.getElementById('searchMessagesBar');
    const btn = document.getElementById('btnSearchMessages');
    const isShowing = bar.classList.contains('show');

    bar.classList.toggle('show');
    btn.classList.toggle('active');

    if (!isShowing) {
        document.getElementById('searchMessagesInput').focus();
    } else {
        clearSearchHighlights();
        document.getElementById('searchMessagesInput').value = '';
        document.getElementById('searchMessagesCount').textContent = '0/0';
    }
}

function searchInMessages() {
    const query = document.getElementById('searchMessagesInput').value.toLowerCase().trim();
    searchResults = [];
    currentSearchIndex = -1;

    clearSearchHighlights();

    if (!query || query.length < 2) {
        document.getElementById('searchMessagesCount').textContent = '0/0';
        return;
    }

    const messages = document.querySelectorAll('.wa-message');
    messages.forEach((msg, index) => {
        const content = msg.querySelector('.wa-message-content');
        if (content && content.textContent.toLowerCase().includes(query)) {
            searchResults.push({ element: msg, index });
            msg.classList.add('search-match');
        }
    });

    document.getElementById('searchMessagesCount').textContent =
        searchResults.length > 0 ? `0/${searchResults.length}` : '0/0';

    if (searchResults.length > 0) {
        navigateSearchResult(1);
    }
}

function navigateSearchResult(direction) {
    if (searchResults.length === 0) return;

    // Remove current highlight
    if (currentSearchIndex >= 0 && searchResults[currentSearchIndex]) {
        searchResults[currentSearchIndex].element.classList.remove('highlighted');
    }

    // Calculate new index
    currentSearchIndex += direction;
    if (currentSearchIndex >= searchResults.length) currentSearchIndex = 0;
    if (currentSearchIndex < 0) currentSearchIndex = searchResults.length - 1;

    // Highlight and scroll to result
    const result = searchResults[currentSearchIndex];
    result.element.classList.add('highlighted');
    result.element.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // Update counter
    document.getElementById('searchMessagesCount').textContent =
        `${currentSearchIndex + 1}/${searchResults.length}`;
}

function clearSearchHighlights() {
    document.querySelectorAll('.wa-message.search-match').forEach(msg => {
        msg.classList.remove('search-match', 'highlighted');
    });
}

// Keyboard shortcut for search (Ctrl+F)
document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'f' && State.selectedPhone) {
        e.preventDefault();
        const bar = document.getElementById('searchMessagesBar');
        if (!bar.classList.contains('show')) {
            toggleSearchMessages();
        } else {
            document.getElementById('searchMessagesInput').focus();
        }
    }
    // Escape to close search
    if (e.key === 'Escape') {
        const bar = document.getElementById('searchMessagesBar');
        if (bar && bar.classList.contains('show')) {
            toggleSearchMessages();
        }
    }
});

// ============================================
// URGENT & ARCHIVE ACTIONS
// ============================================
function toggleUrgent() {
    if (!State.selectedPhone) return;

    const btn = document.getElementById('btnUrgent');
    const isUrgent = urgentConversations.has(State.selectedPhone);

    if (isUrgent) {
        urgentConversations.delete(State.selectedPhone);
        btn.classList.remove('urgent');
        showNotification('Urgencia removida');
    } else {
        urgentConversations.add(State.selectedPhone);
        btn.classList.add('urgent');
        showNotification('Marcado como urgente!', 'warning');
    }

    saveUrgentConversations();
    renderConversations();
}

function archiveConversation() {
    if (!State.selectedPhone) return;

    if (!confirm('Arquivar esta conversa?')) return;

    // For now, just hide from the list (would need backend support for real archiving)
    showNotification('Conversa arquivada');

    // Clear selection
    State.setSelectedPhone(null);
    const ac = document.getElementById('activeChat');
    ac.hidden = true;
    ac.style.display = 'none';
    document.getElementById('emptyState').style.display = 'flex';
    renderConversations();
}

// ============================================
// CLIENT INFO PANEL
// ============================================
function toggleClientInfo() {
    const panel = document.getElementById('clientInfoPanel');
    const btn = document.getElementById('btnClientInfo');
    const isShowing = panel.classList.contains('show');

    panel.classList.toggle('show');
    btn.classList.toggle('active');

    if (!isShowing && State.selectedPhone) {
        loadClientInfoPanel();
    }
}

async function loadClientInfoPanel() {
    const conv = State.conversations.find(c => c.phone === State.selectedPhone);
    const name = conv?.name || conv?.whatsapp_name || formatPhone(State.selectedPhone);

    // Set basic info
    document.getElementById('infoClientMsgCount').textContent = State.messages.length;

    // Hero — profile pic + name + phone.
    const avatarSection = document.getElementById('infoAvatarSection');
    if (avatarSection) {
        const initials = escapeHtml(getInitials(name));
        avatarSection.innerHTML = conv?.profilePic
            ? `<img class="wa-info-hero-avatar" src="${escapeHtml(conv.profilePic)}" alt="${escapeHtml(name)}" onerror="this.outerHTML='<div class=\\'wa-info-hero-avatar-fallback\\'>${initials}</div>'">`
            : `<div class="wa-info-hero-avatar-fallback">${initials}</div>`;
    }
    const avatarName = document.getElementById('infoAvatarName');
    if (avatarName) avatarName.textContent = name;
    const heroPhone = document.getElementById('infoHeroPhone');
    if (heroPhone) heroPhone.textContent = formatPhone(State.selectedPhone);

    // Tier-2: shared-media gallery, starred count, pin/mute toggle states.
    renderSharedMediaGallery();
    updateStarredCount();
    updatePinMuteUI();
    const archiveToggle = document.getElementById('infoArchiveToggle');
    if (archiveToggle && conv) {
        const archived = conv.archived === 1 || conv.archived === true;
        archiveToggle.classList.toggle('active', archived);
        archiveToggle.setAttribute('aria-checked', String(archived));
    }

    // Update CaseHub links
    const linksSection = document.getElementById('infoLinksSection');
    if (linksSection) linksSection.innerHTML = '';

    // Try to get more info from lead data
    if (State.currentLeadData && State.currentLeadData.lead) {
        const lead = State.currentLeadData.lead;
        document.getElementById('infoClientEmail').textContent = lead.email || '-';
        document.getElementById('infoClientInterest').textContent = lead.visa_interest || '-';
        document.getElementById('infoClientFirstContact').textContent =
            lead.created_at ? new Date(lead.created_at).toLocaleDateString('pt-BR') : '-';
        // Show CaseHub links
        if (linksSection && lead.id) {
            linksSection.innerHTML = `<a href="${CASEHUB_PREFIX}/leads#lead-${lead.id}" class="wa-client-info-link"><i class="fas fa-user-tag"></i> Ver Lead</a>`;
        }
    } else {
        document.getElementById('infoClientEmail').textContent = '-';
        document.getElementById('infoClientInterest').textContent = '-';
        document.getElementById('infoClientFirstContact').textContent =
            conv?.created_at ? new Date(conv.created_at).toLocaleDateString('pt-BR') : '-';
    }
}

// Update urgent button state when selecting conversation
const originalSelectConversation = selectConversation;
selectConversation = async function(phone) {
    await originalSelectConversation(phone);

    // Update urgent button
    const btn = document.getElementById('btnUrgent');
    if (btn) {
        btn.classList.toggle('urgent', urgentConversations.has(phone));
    }

    // Tier-2: sync pin/mute header state + starred count for this chat.
    updatePinMuteUI();
    updateStarredCount();

    // Close client info panel
    document.getElementById('clientInfoPanel').classList.remove('show');
    document.getElementById('btnClientInfo').classList.remove('active');
};

// ============================================
// MESSAGE CONTEXT MENU
// ============================================
let contextMenuTarget = null;

function showContextMenu(event, messageElement) {
    event.preventDefault();

    contextMenuTarget = messageElement;
    const menu = document.getElementById('messageContextMenu');

    // Position menu at click location
    menu.style.left = event.clientX + 'px';
    menu.style.top = event.clientY + 'px';

    // Ensure menu stays within viewport
    const rect = menu.getBoundingClientRect();
    if (rect.right > window.innerWidth) {
        menu.style.left = (event.clientX - rect.width) + 'px';
    }
    if (rect.bottom > window.innerHeight) {
        menu.style.top = (event.clientY - rect.height) + 'px';
    }

    menu.classList.add('show');
}

function hideContextMenu() {
    const menu = document.getElementById('messageContextMenu');
    menu.classList.remove('show');
    contextMenuTarget = null;
}

function copyMessageText() {
    if (!contextMenuTarget) return;

    const content = contextMenuTarget.querySelector('.wa-message-content');
    if (content) {
        navigator.clipboard.writeText(content.textContent)
            .then(() => showNotification('Texto copiado!'))
            .catch(() => showNotification('Erro ao copiar', 'error'));
    }
    hideContextMenu();
}

// Tier-2: context-menu reply opens the proper quoted-reply composer.
function replyToMessage() {
    if (!contextMenuTarget) return;
    const msgId = contextMenuTarget.dataset.msgId;
    hideContextMenu();
    if (msgId) startReplyTo(msgId);
}
// forwardMessage / toggleStarMessage / openReactionPickerFromMenu
// are defined in the Tier-2 section below.

// Hide context menu on click outside
document.addEventListener('click', (e) => {
    if (!e.target.closest('.wa-context-menu')) {
        hideContextMenu();
    }
});

// ============================================
// SCROLL TO BOTTOM BUTTON
// ============================================
let scrollListenerBound = false;
function setupScrollButton() {
    const container = document.getElementById('messagesContainer');
    const btn = document.getElementById('scrollBottomBtn');
    if (!container || !btn) return;

    // Bind the scroll listener once — re-renders replace innerHTML but
    // the container element itself persists, so the listener survives.
    if (scrollListenerBound) return;
    scrollListenerBound = true;

    container.addEventListener('scroll', () => {
        const isNearBottom =
            container.scrollHeight - container.scrollTop - container.clientHeight < 100;
        btn.classList.toggle('show', !isNearBottom);
        if (isNearBottom) {
            newMessageCount = 0;
            updateScrollBadge();
        }
    }, { passive: true });
}

function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    if (container) {
        container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
    }
    const btn = document.getElementById('scrollBottomBtn');
    if (btn) btn.classList.remove('show');
    newMessageCount = 0;
    updateScrollBadge();
}

// ============================================
// MESSAGE RENDER — day separators + WhatsApp-Web bubble grouping
// ============================================
let newMessageCount = 0;  // tracked for the scroll-to-bottom badge

// Returns the sort-authority timestamp for a message (ms since epoch).
// `sent_at` is the WhatsApp-side timestamp and wins; falls back to
// created_at so legacy rows still order correctly.
function getMessageTs(m) {
    const raw = m.sent_at || m.created_at || m.timestamp;
    // parseServerDate trata string naive como UTC e número como epoch — antes
    // new Date(raw) cru lia o naive como horário LOCAL (3h erradas no sort).
    const t = raw ? parseServerDate(raw).getTime() : 0;
    return Number.isFinite(t) ? t : 0;
}

const originalRenderMessages = renderWhatsAppMessages;
renderWhatsAppMessages = function() {
    const container = document.getElementById('messagesContainer');
    if (!container) return;

    if (State.messages.length === 0) {
        container.innerHTML = `<div class="wa-empty-list">
            Nenhuma mensagem ainda
        </div>`;
        return;
    }

    // Chronological order — sent_at is the authority (chat.js may receive
    // SSE pushes out of order). Stable sort keeps optimistic msgs in place.
    const ordered = State.messages
        .map((m, i) => ({ m, i }))
        .sort((a, b) => (getMessageTs(a.m) - getMessageTs(b.m)) || (a.i - b.i))
        .map(x => x.m);

    // Was the user already near the bottom before we re-render?
    const wasNearBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight < 120;

    let html = '';
    let lastDate = null;
    let prevSender = null;

    ordered.forEach((m, index) => {
        const msgDate = m.sent_at || m.created_at ? new Date(getMessageTs(m)) : new Date();
        const dateStr = msgDate.toLocaleDateString('pt-BR');

        // Day separator when the date changes.
        if (dateStr !== lastDate) {
            html += `<div class="wa-date-separator"><span class="wa-date-separator-text">${escapeHtml(getDateLabel(msgDate))}</span></div>`;
            lastDate = dateStr;
            prevSender = null; // a separator always breaks a run
        }

        const isOutgoing = m.role === 'assistant' || m.from_me === true || m.direction === 'out';
        const sender = isOutgoing ? 'out' : 'in';
        // First bubble of a same-sender run gets the tail; the rest are
        // "grouped" with tighter spacing — WhatsApp-Web behaviour.
        const isRunStart = sender !== prevSender;
        prevSender = sender;

        const msgId = String(m.id || m.wa_message_id || m.wid || index);
        const time = (m.sent_at || m.created_at) ? formatMessageTime(getMessageTs(m)) : '';
        const ackHtml = isOutgoing ? getAckIcon(m.ack ?? m.status) : '';
        const editedHtml = m.edited_at ? '<span class="wa-message-edited">editada</span>' : '';
        const deletedClass = m.deleted_at ? ' deleted' : '';
        const starredClass = isMessageStarred(msgId) ? ' starred' : '';
        const stickerClass = getMediaKind(m) === 'sticker' && (m.media_url || m.hasMedia) ? ' has-sticker' : '';

        // Reply / quote preview — resolves reply_to_message_id against
        // the loaded message set, OR uses an embedded reply_to object.
        let quoteHtml = '';
        const replied = resolveReplyTarget(m);
        if (replied) {
            quoteHtml = `<button type="button" class="wa-message-quote" onclick="jumpToMessage('${escapeHtml(replied.id)}')">
                <span class="wa-message-quote-author">${escapeHtml(replied.author)}</span>
                ${escapeHtml(replied.text)}
            </button>`;
        }

        // Forwarded tag.
        const forwardedClass = (m.is_forwarded || m.forwarded) ? ' forwarded' : '';
        const forwardedHtml = (m.is_forwarded || m.forwarded)
            ? '<span class="wa-forwarded-tag"><i class="fas fa-share" aria-hidden="true"></i> Encaminhada</span>'
            : '';

        // Reactions chip — grouped by emoji with a count.
        const reactionsHtml = renderReactionsChip(m, msgId);

        // Hover/swipe-to-reply affordance — reply + react quick buttons.
        const actionsHtml = m.deleted_at ? '' : `
            <div class="wa-message-actions" aria-hidden="true">
                <button class="wa-msg-action-btn" type="button" title="Responder"
                        onclick="event.stopPropagation();startReplyTo('${escapeHtml(msgId)}')">
                    <i class="fas fa-reply"></i>
                </button>
                <button class="wa-msg-action-btn" type="button" title="Reagir"
                        onclick="event.stopPropagation();openReactionPicker(event,'${escapeHtml(msgId)}')">
                    <i class="fas fa-face-smile"></i>
                </button>
            </div>`;

        html += `
            <div class="wa-message ${sender === 'out' ? 'outgoing' : 'incoming'}${isRunStart ? ' tail' : ' grouped'}${deletedClass}${starredClass}${stickerClass}${forwardedClass}"
                 oncontextmenu="showContextMenu(event, this)"
                 data-msg-id="${escapeHtml(msgId)}">
                ${forwardedHtml}
                ${quoteHtml}
                ${m.deleted_at ? '<div class="wa-message-content"><i class="fas fa-ban" aria-hidden="true"></i> Esta mensagem foi apagada</div>' : renderMessageContent(m)}
                <div class="wa-message-time">${editedHtml}<span>${escapeHtml(time)}</span>${ackHtml}</div>
                ${reactionsHtml}
                ${actionsHtml}
            </div>
        `;
    });

    container.innerHTML = html;

    // Smart scroll: jump to bottom if the user was already there;
    // otherwise keep position and surface the scroll-to-bottom badge.
    if (wasNearBottom) {
        container.scrollTop = container.scrollHeight;
        newMessageCount = 0;
        updateScrollBadge();
    }

    checkShowQuickAction();
    setupScrollButton();
    bindSwipeToReply();
};

// Keeps the scroll-to-bottom button's unread badge in sync.
function updateScrollBadge() {
    const badge = document.getElementById('newMsgCount');
    if (!badge) return;
    if (newMessageCount > 0) {
        badge.textContent = newMessageCount > 99 ? '99+' : String(newMessageCount);
        badge.hidden = false;
    } else {
        badge.hidden = true;
    }
}

function getDateLabel(date) {
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    const dateStr = date.toLocaleDateString('pt-BR');
    const todayStr = today.toLocaleDateString('pt-BR');
    const yesterdayStr = yesterday.toLocaleDateString('pt-BR');

    if (dateStr === todayStr) return 'Hoje';
    if (dateStr === yesterdayStr) return 'Ontem';

    return date.toLocaleDateString('pt-BR', {
        weekday: 'long',
        day: 'numeric',
        month: 'long'
    });
}

// ============================================
// KEYBOARD SHORTCUTS
// ============================================
document.addEventListener('keydown', (e) => {
    // T for templates
    if (e.key === 't' && !e.ctrlKey && !e.metaKey && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
        e.preventDefault();
        toggleTemplates();
    }

    // E for emoji
    if (e.key === 'e' && !e.ctrlKey && !e.metaKey && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
        e.preventDefault();
        toggleEmojiPicker();
    }
});

// ============================================
// MOBILE SIDEBAR TOGGLE
// ============================================
function syncMobileSidebarToggle(sidebar, btn) {
    if (!sidebar || !btn) return;

    const expanded = !sidebar.classList.contains('collapsed');
    btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');

    const icon = btn.querySelector('i');
    if (icon) icon.className = expanded ? 'fas fa-times' : 'fas fa-comments';
}

function toggleMobileSidebar() {
    const sidebar = document.querySelector('.wa-sidebar');
    const btn = document.querySelector('.wa-toggle-sidebar');
    if (!sidebar || !btn) return;

    sidebar.classList.toggle('collapsed');
    syncMobileSidebarToggle(sidebar, btn);
}

// Auto-collapse sidebar when selecting conversation on mobile
const originalSelectConvMobile = selectConversation;
selectConversation = async function(phone) {
    await originalSelectConvMobile(phone);

    // On mobile, collapse sidebar after selecting
    if (window.innerWidth <= 768) {
        const sidebar = document.querySelector('.wa-sidebar');
        const btn = document.querySelector('.wa-toggle-sidebar');
        if (sidebar) sidebar.classList.add('collapsed');
        syncMobileSidebarToggle(sidebar, btn);
    }
};

// Keep the CRM contact panel synced to the open conversation. PR #733 mounted
// the panel + buttons but it never re-rendered on conversation switch, so the
// owner / lead-stage / notes stayed pinned to the previously-opened phone
// (Fase 1+2 "inacessível": clicking a new chat left the CRM card stale).
// Additive + guarded: if whatsapp-crm.js is absent or the panel is closed this
// is a no-op and never throws.
const originalSelectConvCrm = selectConversation;
selectConversation = async function(phone) {
    await originalSelectConvCrm(phone);
    try {
        if (!window.WhatsAppCRM || !phone) return;
        // Refresh the CRM panel only if it is currently visible — never force it
        // open over the user's layout, just keep an open panel in sync.
        const panelHost = document.getElementById('wacPanelHost');
        if (panelHost && !panelHost.hidden) {
            window.WhatsAppCRM.openContactPanel(phone);
        }
        // If the funnel kanban is open, refresh it so a new lead/stage shows up.
        const pipeHost = document.getElementById('wacPipelineHost');
        if (pipeHost && !pipeHost.hidden && window.WhatsAppCRM.refreshPipeline) {
            window.WhatsAppCRM.refreshPipeline();
        }
    } catch (e) {
        console.warn('[wa-crm] panel sync skipped:', e && e.message);
    }
};

// ============================================
// ACCESSIBILITY - Update ARIA attributes on tab switch
// ============================================
const originalSwitchTab = switchTab;
switchTab = function(tab) {
    originalSwitchTab(tab);

    // Update ARIA attributes
    document.querySelectorAll('.wa-tab').forEach(t => {
        t.setAttribute('aria-selected', t.classList.contains('active') ? 'true' : 'false');
    });
};

// ============================================
// INITIALIZATION - Load additional features
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    // Fix: Add click listener for templates button
    const templatesBtn = document.querySelector('button[title="Templates (T)"]');
    if (templatesBtn) templatesBtn.addEventListener('click', toggleTemplates);
    syncMobileSidebarToggle(document.querySelector('.wa-sidebar'), document.querySelector('.wa-toggle-sidebar'));
    loadUrgentConversations();
    initEmojiPicker();
    setupScrollButton();
    requestNotificationPermission();

    // Tier-2: forward modal closes on backdrop click.
    const forwardModal = document.getElementById('forwardModal');
    if (forwardModal) {
        forwardModal.addEventListener('click', (e) => {
            if (e.target === forwardModal) closeForwardModal();
        });
    }
    // Reposition the reaction picker / hide transient popovers on scroll.
    const mc = document.getElementById('messagesContainer');
    if (mc) mc.addEventListener('scroll', () => closeReactionPicker(), { passive: true });

    // Add keyboard navigation to conversation list
    const convList = document.getElementById('conversationsList');
    convList.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            const convs = convList.querySelectorAll('.wa-conversation');
            const current = convList.querySelector('.wa-conversation.active');
            const currentIndex = Array.from(convs).indexOf(current);
            let newIndex = currentIndex;

            if (e.key === 'ArrowDown' && currentIndex < convs.length - 1) {
                newIndex = currentIndex + 1;
            } else if (e.key === 'ArrowUp' && currentIndex > 0) {
                newIndex = currentIndex - 1;
            }

            if (newIndex !== currentIndex && convs[newIndex]) {
                convs[newIndex].click();
                convs[newIndex].focus();
            }
        }
    });
});

// ════════════════════════════════════════════════════════════
// TIER-2 — reply / quote / forward, reactions, presence, media
// composer, contact-info gallery, pin/archive/mute/star.
// All API calls keep the WA_API_BASE + '/api/...' contract.
// ════════════════════════════════════════════════════════════

// ── Reply / quote ────────────────────────────────────────────
let replyContext = null;  // { id, author, text }

// Resolves a reply target for rendering: prefers an embedded
// reply_to object, else looks up reply_to_message_id in State.messages.
function resolveReplyTarget(m) {
    if (m.reply_to && (m.reply_to.body || m.reply_to.content)) {
        return {
            id: String(m.reply_to.id || m.reply_to_message_id || ''),
            author: m.reply_to.author || (m.reply_to.from_me ? 'Você' : 'Contato'),
            text: truncate(m.reply_to.body || m.reply_to.content, 80)
        };
    }
    const rid = m.reply_to_message_id;
    if (!rid) return null;
    const target = State.messages.find(x =>
        String(x.id) === String(rid) || String(x.wa_message_id) === String(rid));
    if (!target) {
        return { id: String(rid), author: 'Mensagem', text: 'Mensagem original' };
    }
    const tOut = target.role === 'assistant' || target.from_me === true;
    return {
        id: String(target.id || target.wa_message_id),
        author: tOut ? 'Você' : 'Contato',
        text: truncate(messagePreviewText(target), 80)
    };
}

// A short text label for any message kind (used in quotes/forward list).
function messagePreviewText(m) {
    if (m.deleted_at) return 'Mensagem apagada';
    const kind = getMediaKind(m);
    if (m.hasMedia || m.media_type) {
        const labels = {
            image: '📷 Foto', video: '🎬 Vídeo', audio: '🎵 Áudio',
            sticker: '🩷 Figurinha', document: '📄 Documento',
            location: '📍 Localização', contact: '👤 Contato'
        };
        return (m.caption || m.content) || labels[kind] || '📎 Mídia';
    }
    return m.content || '';
}

function startReplyTo(msgId) {
    const m = State.messages.find(x =>
        String(x.id) === String(msgId) || String(x.wa_message_id) === String(msgId));
    if (!m) return;
    const isOut = m.role === 'assistant' || m.from_me === true;
    replyContext = {
        id: m.id ? String(m.id) : null,
        waMessageId: m.wa_message_id || m.wid || null,
        author: isOut ? 'Você' : (document.getElementById('chatName')?.textContent || 'Contato'),
        text: messagePreviewText(m)
    };
    const bar = document.getElementById('replyBar');
    document.getElementById('replyBarAuthor').textContent = replyContext.author;
    document.getElementById('replyBarText').textContent = truncate(replyContext.text, 90);
    bar.classList.add('show');
    const input = document.getElementById('messageInput');
    if (input) input.focus();
}

function cancelReply() {
    replyContext = null;
    document.getElementById('replyBar')?.classList.remove('show');
}

// Scrolls to and flashes a quoted message when its preview is clicked.
function jumpToMessage(msgId) {
    const el = document.querySelector(`.wa-message[data-msg-id="${CSS.escape(msgId)}"]`);
    if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.remove('highlighted');
        void el.offsetWidth; // restart the flash animation
        el.classList.add('highlighted');
    }
}

// ── Swipe / drag to reply ────────────────────────────────────
// Touch swipe (mobile) + a subtle desktop drag both arm a reply
// when the bubble is pulled past the threshold.
function bindSwipeToReply() {
    const container = document.getElementById('messagesContainer');
    if (!container || container._swipeBound) return;
    container._swipeBound = true;

    let startX = 0, startY = 0, target = null, dragging = false;
    const THRESHOLD = 56;

    container.addEventListener('touchstart', (e) => {
        const bubble = e.target.closest('.wa-message');
        if (!bubble || bubble.classList.contains('deleted')) return;
        target = bubble;
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
        dragging = false;
    }, { passive: true });

    container.addEventListener('touchmove', (e) => {
        if (!target) return;
        const dx = e.touches[0].clientX - startX;
        const dy = e.touches[0].clientY - startY;
        if (Math.abs(dy) > Math.abs(dx)) { target = null; return; }
        const dir = target.classList.contains('outgoing') ? -1 : 1;
        const pull = dir > 0 ? Math.max(0, dx) : Math.min(0, dx);
        if (Math.abs(pull) > 8) {
            dragging = true;
            target.classList.add('swiping');
            target.style.transform = `translateX(${Math.max(-THRESHOLD, Math.min(THRESHOLD, pull))}px)`;
            target.classList.toggle('reply-armed', Math.abs(pull) >= THRESHOLD);
        }
    }, { passive: true });

    container.addEventListener('touchend', () => {
        if (target && dragging) {
            if (target.classList.contains('reply-armed')) {
                startReplyTo(target.dataset.msgId);
            }
            target.style.transform = '';
            target.classList.remove('swiping', 'reply-armed');
        }
        target = null;
    });
}

// ── Forward flow ─────────────────────────────────────────────
let forwardMessageData = null;
const forwardSelection = new Set();

function forwardMessage() {
    // contextMenuTarget set by showContextMenu
    if (!contextMenuTarget) return;
    const msgId = contextMenuTarget.dataset.msgId;
    const m = State.messages.find(x =>
        String(x.id) === String(msgId) || String(x.wa_message_id) === String(msgId));
    hideContextMenu();
    if (!m) return;
    forwardMessageData = m;
    forwardSelection.clear();
    document.getElementById('forwardSearch').value = '';
    renderForwardList();
    document.getElementById('forwardModal').classList.add('show');
}

function renderForwardList() {
    const list = document.getElementById('forwardList');
    if (!list) return;
    const q = (document.getElementById('forwardSearch')?.value || '').toLowerCase();
    const convs = State.conversations
        .filter(c => {
            const name = (c.name || c.whatsapp_name || c.phone || '').toLowerCase();
            return !q || name.includes(q) || (c.phone || '').includes(q);
        })
        .slice(0, 60);

    list.innerHTML = convs.map(c => {
        const name = c.name || c.whatsapp_name || formatPhone(c.phone);
        const sel = forwardSelection.has(c.phone);
        return `<div class="wa-forward-item${sel ? ' selected' : ''}" role="option"
                     aria-selected="${sel}" data-phone="${escapeHtml(c.phone)}"
                     onclick="toggleForwardTarget(this.dataset.phone)">
            <span class="wa-forward-item-avatar" aria-hidden="true">${escapeHtml(getInitials(name))}</span>
            <span class="wa-forward-item-name">${escapeHtml(name)}</span>
            <i class="fas fa-check-circle wa-forward-item-check" aria-hidden="true"></i>
        </div>`;
    }).join('') || '<div class="wa-emoji-empty">Nenhuma conversa encontrada</div>';
}

function toggleForwardTarget(phone) {
    if (forwardSelection.has(phone)) forwardSelection.delete(phone);
    else forwardSelection.add(phone);
    renderForwardList();
}

function closeForwardModal() {
    document.getElementById('forwardModal')?.classList.remove('show');
    forwardMessageData = null;
    forwardSelection.clear();
}

async function confirmForward() {
    if (!forwardMessageData || forwardSelection.size === 0) {
        showNotification('Selecione ao menos uma conversa', 'warning');
        return;
    }
    const btn = document.getElementById('forwardSendBtn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Enviando...'; }

    const m = forwardMessageData;
    const targets = [...forwardSelection];
    let ok = 0;

    for (const phone of targets) {
        try {
            // Media is re-sent by URL reference; text is sent as-is. Both
            // go through the existing /api/send contract (no new endpoint).
            const body = m.media_url
                ? { phone, message: m.caption || m.content || '', fromHuman: true,
                    media_url: m.media_url, media_type: m.media_type, forwarded: true }
                : { phone, message: m.content || '', fromHuman: true, forwarded: true };
            const r = await fetch(WA_API_BASE + '/api/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            if (r.ok) ok++;
        } catch (e) { /* count failures by omission */ }
    }

    if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-share"></i> Encaminhar'; }
    closeForwardModal();
    showNotification(
        ok === targets.length
            ? `Mensagem encaminhada para ${ok} conversa(s)`
            : `Encaminhada para ${ok} de ${targets.length}`,
        ok === targets.length ? 'success' : 'warning'
    );
}

// ── Reactions ────────────────────────────────────────────────
const REACTION_EMOJIS = ['👍', '❤️', '😂', '😮', '😢', '🙏'];
let reactionTargetId = null;

// Groups a message's reactions array into {emoji: count} and renders
// the chip. Backend sends `reactions` as an array of strings or
// {emoji,...} objects — handle both.
function renderReactionsChip(m, msgId) {
    const reactions = Array.isArray(m.reactions) ? m.reactions : [];
    if (!reactions.length) return '';
    const counts = {};
    reactions.forEach(r => {
        const e = (typeof r === 'string') ? r : (r.emoji || r.reaction || '');
        if (e) counts[e] = (counts[e] || 0) + 1;
    });
    const pills = Object.entries(counts).map(([emoji, n]) =>
        `<span class="wa-reaction-pill">${escapeHtml(emoji)}${n > 1 ? `<span class="wa-reaction-count">${n}</span>` : ''}</span>`
    ).join('');
    return `<button type="button" class="wa-message-reactions has-reactions"
                    onclick="event.stopPropagation();openReactionPicker(event,'${escapeHtml(msgId)}')"
                    aria-label="Reações da mensagem">${pills}</button>`;
}

function openReactionPicker(event, msgId) {
    event.stopPropagation();
    reactionTargetId = msgId;
    const picker = document.getElementById('reactionPicker');
    if (!picker) return;
    picker.innerHTML = REACTION_EMOJIS.map(e =>
        `<button class="wa-reaction-opt" type="button" role="menuitem"
                 onclick="applyReaction('${e.replace(/'/g, "\\'")}')" aria-label="Reagir com ${e}">${e}</button>`
    ).join('');
    // Position above the originating element, clamped to viewport.
    picker.classList.add('show');
    const rect = picker.getBoundingClientRect();
    let x = event.clientX - rect.width / 2;
    let y = event.clientY - rect.height - 8;
    x = Math.max(8, Math.min(x, window.innerWidth - rect.width - 8));
    if (y < 8) y = event.clientY + 16;
    picker.style.left = x + 'px';
    picker.style.top = y + 'px';
}

function openReactionPickerFromMenu() {
    if (!contextMenuTarget) return;
    const id = contextMenuTarget.dataset.msgId;
    const rect = contextMenuTarget.getBoundingClientRect();
    hideContextMenu();
    openReactionPicker({ clientX: rect.left + rect.width / 2, clientY: rect.top, stopPropagation() {} }, id);
}

function closeReactionPicker() {
    document.getElementById('reactionPicker')?.classList.remove('show');
    reactionTargetId = null;
}

async function applyReaction(emoji) {
    const msgId = reactionTargetId;
    closeReactionPicker();
    if (!msgId) return;

    // Optimistic: append the reaction locally so the chip updates now.
    const m = State.messages.find(x =>
        String(x.id) === String(msgId) || String(x.wa_message_id) === String(msgId));
    if (m) {
        m.reactions = Array.isArray(m.reactions) ? m.reactions : [];
        m.reactions.push({ emoji, from_me: true });
        renderWhatsAppMessages();
    }

    try {
        const r = await fetch(WA_API_BASE + '/api/react', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone: State.selectedPhone, message_id: msgId, emoji })
        });
        if (!r.ok) throw new Error('react failed');
        showNotification('Reação enviada');
    } catch (e) {
        // Roll back the optimistic reaction; the backend rejected it.
        if (m && Array.isArray(m.reactions)) {
            const idx = m.reactions.findIndex(x => x && x.emoji === emoji && x.from_me);
            if (idx >= 0) m.reactions.splice(idx, 1);
            renderWhatsAppMessages();
        }
        showNotification('Não foi possível enviar a reação', 'error');
    }
}

document.addEventListener('click', (e) => {
    const picker = document.getElementById('reactionPicker');
    if (picker && picker.classList.contains('show') &&
        !e.target.closest('.wa-reaction-picker') && !e.target.closest('.wa-message-actions') &&
        !e.target.closest('.wa-message-reactions')) {
        closeReactionPicker();
    }
});

// ── Starred messages (favorites) ─────────────────────────────
// Star state is local-per-browser (WhatsApp-native, no CRM coupling).
function getStarredSet() {
    try {
        return new Set(JSON.parse(localStorage.getItem('waStarredMessages') || '[]'));
    } catch (e) { return new Set(); }
}
function isMessageStarred(msgId) {
    return getStarredSet().has(`${State.selectedPhone}:${msgId}`);
}
function toggleStarMessage() {
    if (!contextMenuTarget) return;
    const msgId = contextMenuTarget.dataset.msgId;
    const key = `${State.selectedPhone}:${msgId}`;
    const set = getStarredSet();
    if (set.has(key)) { set.delete(key); showNotification('Removido dos favoritos'); }
    else { set.add(key); showNotification('Mensagem favoritada'); }
    try { localStorage.setItem('waStarredMessages', JSON.stringify([...set])); } catch (e) {}
    hideContextMenu();
    renderWhatsAppMessages();
    updateStarredCount();
}
function updateStarredCount() {
    const el = document.getElementById('infoStarredCount');
    if (!el) return;
    const prefix = `${State.selectedPhone}:`;
    el.textContent = [...getStarredSet()].filter(k => k.startsWith(prefix)).length;
}

// ── Pin / mute / archive ─────────────────────────────────────
// Pin/mute are stored locally and reflected in the sidebar ordering
// and badges. Archive uses the existing flow.
function getPinnedSet() {
    try { return new Set(JSON.parse(localStorage.getItem('waPinnedConvs') || '[]')); }
    catch (e) { return new Set(); }
}
function getMutedSet() {
    try { return new Set(JSON.parse(localStorage.getItem('waMutedConvs') || '[]')); }
    catch (e) { return new Set(); }
}
function savePinned(set) { try { localStorage.setItem('waPinnedConvs', JSON.stringify([...set])); } catch (e) {} }
function saveMuted(set) { try { localStorage.setItem('waMutedConvs', JSON.stringify([...set])); } catch (e) {} }

function togglePin() {
    if (!State.selectedPhone) return;
    const set = getPinnedSet();
    const pinned = set.has(State.selectedPhone);
    if (pinned) set.delete(State.selectedPhone);
    else set.add(State.selectedPhone);
    savePinned(set);
    updatePinMuteUI();
    renderConversations();
    showNotification(pinned ? 'Conversa desafixada' : 'Conversa fixada');
}
function toggleMute() {
    if (!State.selectedPhone) return;
    const set = getMutedSet();
    const muted = set.has(State.selectedPhone);
    if (muted) set.delete(State.selectedPhone);
    else set.add(State.selectedPhone);
    saveMuted(set);
    updatePinMuteUI();
    renderConversations();
    showNotification(muted ? 'Notificações ativadas' : 'Conversa silenciada');
}
function togglePinFromInfo() { togglePin(); }
function toggleMuteFromInfo() { toggleMute(); }
function toggleArchiveFromInfo() { archiveConversation(); }

function updatePinMuteUI() {
    const pinned = getPinnedSet().has(State.selectedPhone);
    const muted = getMutedSet().has(State.selectedPhone);

    const btnPin = document.getElementById('btnPin');
    if (btnPin) {
        btnPin.classList.toggle('toggled', pinned);
        btnPin.setAttribute('aria-pressed', String(pinned));
    }
    const btnMute = document.getElementById('btnMute');
    if (btnMute) {
        btnMute.classList.toggle('toggled', muted);
        btnMute.setAttribute('aria-pressed', String(muted));
        btnMute.querySelector('i').className = muted ? 'fas fa-bell-slash' : 'fas fa-bell';
    }
    const infoPin = document.getElementById('infoPinToggle');
    if (infoPin) { infoPin.classList.toggle('active', pinned); infoPin.setAttribute('aria-checked', String(pinned)); }
    const infoMute = document.getElementById('infoMuteToggle');
    if (infoMute) { infoMute.classList.toggle('active', muted); infoMute.setAttribute('aria-checked', String(muted)); }
}

// ── Presence / last-seen in the chat header ──────────────────
// The backend pushes presence over SSE (type:'presence'). Until a
// presence event arrives the header shows the phone number.
function updatePresence(data) {
    const statusEl = document.getElementById('chatStatus');
    if (!statusEl || !data) return;
    if (data.phone && data.phone !== State.selectedPhone) return;

    let html = '';
    if (data.isTyping || data.typing) {
        html = '<span class="wa-presence typing">digitando...</span>';
    } else if (data.online || data.isOnline) {
        html = '<span class="wa-presence online"><span class="wa-presence-dot"></span>online</span>';
    } else if (data.lastSeen || data.last_seen) {
        const seen = new Date(data.lastSeen || data.last_seen);
        html = `<span class="wa-presence"><span class="wa-presence-dot"></span>visto por último ${escapeHtml(formatLastSeen(seen))}</span>`;
    }
    // Keep the existing phone + CRM-link row, prepend presence.
    const conv = State.conversations.find(c => c.phone === State.selectedPhone);
    statusEl.innerHTML =
        (html ? html + ' ' : '') +
        `${escapeHtml(formatPhone(State.selectedPhone))}` +
        `${conv ? `<span class="wa-chat-link-row">${getLinkedBadges(conv)}</span>` : ''}`;
}

function formatLastSeen(date) {
    date = parseServerDate(date);
    const now = new Date();
    const sameDay = date.toLocaleDateString('pt-BR', { timeZone: BR_TZ })
        === now.toLocaleDateString('pt-BR', { timeZone: BR_TZ });
    const time = date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', timeZone: BR_TZ });
    if (sameDay) return `hoje às ${time}`;
    const y = new Date(now); y.setDate(y.getDate() - 1);
    if (date.toLocaleDateString('pt-BR', { timeZone: BR_TZ }) === y.toLocaleDateString('pt-BR', { timeZone: BR_TZ })) return `ontem às ${time}`;
    return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', timeZone: BR_TZ }) + ` às ${time}`;
}

// ── Attach menu + media composer ─────────────────────────────
function toggleAttachMenu() {
    const menu = document.getElementById('attachMenu');
    const btn = document.getElementById('attachBtn');
    if (!menu) return;
    const open = menu.classList.toggle('show');
    if (btn) btn.setAttribute('aria-expanded', String(open));
    document.getElementById('emojiPicker')?.classList.remove('show');
    document.getElementById('templatesMenu')?.classList.remove('show');
}
function closeAttachMenu() {
    const menu = document.getElementById('attachMenu');
    if (menu) menu.classList.remove('show');
    document.getElementById('attachBtn')?.setAttribute('aria-expanded', 'false');
}

document.addEventListener('click', (e) => {
    const menu = document.getElementById('attachMenu');
    if (menu && menu.classList.contains('show') &&
        !e.target.closest('.wa-attach-menu') && !e.target.closest('#attachBtn')) {
        closeAttachMenu();
    }
});

let pendingMediaFile = null;
let pendingMediaUrl = null;

// Media composer — preview + caption confirmation before /api/send-media.
function openMediaComposer(file) {
    pendingMediaFile = file;
    const composer = document.getElementById('mediaComposer');
    const body = document.getElementById('mediaComposerBody');
    const caption = document.getElementById('mediaComposerCaption');
    if (!composer || !body) return;

    if (pendingMediaUrl) { URL.revokeObjectURL(pendingMediaUrl); pendingMediaUrl = null; }

    if (file.type.startsWith('image/')) {
        pendingMediaUrl = URL.createObjectURL(file);
        body.innerHTML = `<img class="wa-media-composer-preview" src="${pendingMediaUrl}" alt="Pré-visualização">`;
    } else if (file.type.startsWith('video/')) {
        pendingMediaUrl = URL.createObjectURL(file);
        body.innerHTML = `<video class="wa-media-composer-preview" src="${pendingMediaUrl}" controls></video>`;
    } else {
        const icon = getFileIcon(file.type);
        body.innerHTML = `<div class="wa-media-composer-fileicon">
            <i class="fas ${icon}" aria-hidden="true"></i>
            <div>${escapeHtml(file.name)}</div>
            <div class="wa-message-media-doc-size">${formatFileSize(file.size)}</div>
        </div>`;
    }
    if (caption) caption.value = '';
    composer.classList.add('show');
    if (caption) setTimeout(() => caption.focus(), 50);
}

function cancelMediaComposer() {
    document.getElementById('mediaComposer')?.classList.remove('show');
    if (pendingMediaUrl) { URL.revokeObjectURL(pendingMediaUrl); pendingMediaUrl = null; }
    pendingMediaFile = null;
    const fi = document.getElementById('fileInput');
    if (fi) fi.value = '';
}

async function confirmSendMedia() {
    if (!pendingMediaFile || !State.selectedPhone) return;
    const caption = document.getElementById('mediaComposerCaption')?.value || '';
    const sendBtn = document.getElementById('mediaComposerSend');
    if (sendBtn) sendBtn.disabled = true;

    try {
        const formData = new FormData();
        formData.append('file', pendingMediaFile);
        formData.append('phone', State.selectedPhone);
        formData.append('caption', caption);

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), API_TIMEOUTS.media);

        const response = await fetch(WA_API_BASE + '/api/send-media', {
            method: 'POST',
            body: formData,
            signal: controller.signal
        });
        clearTimeout(timeout);

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error || 'Falha no envio');
        }
        showNotification('Arquivo enviado!', 'success');
        cancelMediaComposer();
        const loadId = ++currentLoadId;
        loadMessages(State.selectedPhone, loadId);
    } catch (error) {
        const msg = error.name === 'AbortError' ? 'Timeout - tente novamente' : (error.message || 'Erro ao enviar arquivo');
        showNotification(msg, 'error');
    } finally {
        if (sendBtn) sendBtn.disabled = false;
    }
}

// ── Contact-info: shared-media gallery ───────────────────────
// Pulls image/video/document messages from the loaded set — no extra
// backend call; the data is already in State.messages.
function renderSharedMediaGallery() {
    const gallery = document.getElementById('infoMediaGallery');
    const countEl = document.getElementById('infoMediaCount');
    if (!gallery) return;

    const mediaMsgs = State.messages.filter(m => {
        if (m.deleted_at) return false;
        const kind = getMediaKind(m);
        return (m.hasMedia || m.media_url) && ['image', 'video', 'document'].includes(kind);
    });

    if (countEl) countEl.textContent = mediaMsgs.length;

    if (!mediaMsgs.length) {
        gallery.innerHTML = '<div class="wa-media-gallery-empty">Nenhuma mídia compartilhada ainda</div>';
        return;
    }

    gallery.innerHTML = mediaMsgs.slice(-12).reverse().map(m => {
        const kind = getMediaKind(m);
        const url = m.media_url || m.mediaUrl;
        if (kind === 'image' && url) {
            return `<div class="wa-media-gallery-item" onclick="openLightbox('${escapeHtml(url)}')">
                <img src="${escapeHtml(url)}" alt="Imagem compartilhada" loading="lazy">
            </div>`;
        }
        const icon = kind === 'video' ? 'fa-play' : getFileIcon(m.mimetype || m.media_type);
        const click = url
            ? (kind === 'video'
                ? `onclick="window.open('${escapeHtml(url)}','_blank')"`
                : `onclick="window.open('${escapeHtml(url)}','_blank')"`)
            : '';
        return `<div class="wa-media-gallery-item" ${click}>
            <span class="wa-media-gallery-icon"><i class="fas ${icon}" aria-hidden="true"></i></span>
        </div>`;
    }).join('');
}

// ════════════════════════════════════════════════════════════
// LEGAL ADVICE GUARD - Feb 2026
// Protects against sending legal advice via WhatsApp
// ============================================

const LEGAL_ADVICE_TERMS = [
    "adjustment of status", "change of status", "mudança de status", "mudanca de status",
    "ajuste de status", "90-day rule", "regra dos 90", "90 dias",
    "i-130", "i-485", "i-140", "i-129", "i-765", "i-131", "i-20",
    "i-539", "i-290b", "i-864", "i-134", "i-693", "i-94",
    "ina ", "uscis guideline", "uscis requirement",
    "you need to file", "voce precisa protocolar", "você precisa protocolar",
    "processing time", "tempo de processamento",
    "elegibilidade", "eligibility requirement", "eligibility for",
    "petition", "petição", "peticao",
    "dual intent", "dupla intenção", "dupla intencao",
    "labor certification", "perm ",
    "priority date", "data de prioridade",
    "consular processing", "processamento consular",
    "green card", "residência permanente", "residencia permanente",
    "deportation", "deportação", "deportacao", "removal proceedings",
    "asylum", "asilo político", "asilo politico",
    "work permit", "permissão de trabalho", "permissao de trabalho",
    "visa bulletin", "national visa center",
    "inadmissibility", "inadmissibilidade",
    "waiver", "perdão imigratório", "perdao imigratorio",
    "naturalization", "naturalização", "naturalizacao",
    "ead card", "advance parole"
];

function checkLegalAdvice(message) {
    const msgLower = message.toLowerCase();
    return LEGAL_ADVICE_TERMS.filter(term => msgLower.includes(term));
}

// Store pending message for after modal confirmation
let pendingLegalAdviceAction = null;

function showLegalAdviceWarning(termsFound, onConfirm) {
    const modal = document.getElementById("legalAdviceModal");
    const termsList = document.getElementById("legalAdviceTerms");
    termsList.textContent = termsFound.join(", ");
    pendingLegalAdviceAction = onConfirm;
    modal.classList.add("show");
}

function closeLegalAdviceModal() {
    const modal = document.getElementById("legalAdviceModal");
    modal.classList.remove("show");
    pendingLegalAdviceAction = null;
}

function confirmSendDespiteWarning() {
    const modal = document.getElementById("legalAdviceModal");
    modal.classList.remove("show");
    if (pendingLegalAdviceAction) {
        console.warn("[LEGAL ADVICE GUARD] User acknowledged warning and chose to send anyway.");
        pendingLegalAdviceAction();
        pendingLegalAdviceAction = null;
    }
}

// Wrap sendMessage with legal advice check
const _sendMessageBeforeLegalGuard = sendMessage;
sendMessage = async function() {
    const input = document.getElementById("messageInput");
    const text = (input ? input.value : "").trim();
    if (!text) { return _sendMessageBeforeLegalGuard(); }

    const termsFound = checkLegalAdvice(text);
    if (termsFound.length > 0) {
        showLegalAdviceWarning(termsFound, () => _sendMessageBeforeLegalGuard());
        return;
    }
    return _sendMessageBeforeLegalGuard();
};

// Wrap sendTemplateNow with legal advice check
const _sendTemplateBeforeLegalGuard = sendTemplateNow;
sendTemplateNow = async function() {
    const textarea = document.getElementById("templatePreviewText");
    const text = (textarea ? textarea.value : "").trim();
    if (!text) { return _sendTemplateBeforeLegalGuard(); }

    const termsFound = checkLegalAdvice(text);
    if (termsFound.length > 0) {
        showLegalAdviceWarning(termsFound, () => _sendTemplateBeforeLegalGuard());
        return;
    }
    return _sendTemplateBeforeLegalGuard();
};

// Legal advice guard active
