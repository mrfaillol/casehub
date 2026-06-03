/**
 * Stripe Integration Module
 * CaseHub - WhatsApp Bot
 * v1.0
 */

const stripeSecretKey = process.env.STRIPE_SECRET_KEY;
if (!stripeSecretKey) throw new Error("STRIPE_SECRET_KEY environment variable is required");

const stripePublishableKey = process.env.STRIPE_PUBLISHABLE_KEY;
if (!stripePublishableKey) throw new Error("STRIPE_PUBLISHABLE_KEY environment variable is required");

const STRIPE_CONFIG = {
  secretKey: stripeSecretKey,
  publishableKey: stripePublishableKey,
  webhookSecret: process.env.STRIPE_WEBHOOK_SECRET || "",

  // Produtos/Precos
  consultationPrice: {
    usd: 9900,  // $99.00 em centavos
    brl: 49900  // R$499.00 em centavos
  },

  // URLs de retorno
  successUrl: process.env.STRIPE_SUCCESS_URL || `${process.env.ORG_WEBSITE || "https://casehub.app"}/payment-success`,
  cancelUrl: process.env.STRIPE_CANCEL_URL || `${process.env.ORG_WEBSITE || "https://casehub.app"}/payment-cancelled`
};

// Cache para links de pagamento (phone -> session)
const paymentSessions = new Map();

/**
 * Criar sessao de pagamento Stripe Checkout
 * @param {Object} leadData - Dados do lead
 * @param {string} currency - Moeda (usd ou brl)
 * @returns {Object} { success, url, sessionId }
 */
async function createCheckoutSession(leadData, currency = "usd") {
  try {
    const price = currency === "brl"
      ? STRIPE_CONFIG.consultationPrice.brl
      : STRIPE_CONFIG.consultationPrice.usd;

    const currencyLabel = currency === "brl" ? "BRL" : "USD";
    const priceLabel = currency === "brl" ? "R$499" : "US$99";

    // Montar dados do cliente
    const customerData = {};
    if (leadData.email) {
      customerData.email = leadData.email;
    }

    // Metadata para identificar o lead
    const metadata = {
      phone: leadData.phone || "",
      name: leadData.client_name || leadData.name || "",
      source: "whatsapp_bot",
      consultation_type: "paid"
    };

    const body = {
      payment_method_types: ["card"],
      line_items: [{
        price_data: {
          currency: currency,
          product_data: {
            name: "Consulta com Advogado",
            description: `Consulta juridica de imigracao (30 minutos) - ${priceLabel}`
          },
          unit_amount: price
        },
        quantity: 1
      }],
      mode: "payment",
      success_url: `${STRIPE_CONFIG.successUrl}?session_id={CHECKOUT_SESSION_ID}&phone=${encodeURIComponent(leadData.phone || "")}`,
      cancel_url: STRIPE_CONFIG.cancelUrl,
      metadata: metadata
    };

    if (customerData.email) {
      body.customer_email = customerData.email;
    }

    const response = await fetch("https://api.stripe.com/v1/checkout/sessions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${STRIPE_CONFIG.secretKey}`,
        "Content-Type": "application/x-www-form-urlencoded"
      },
      body: encodeFormData(body)
    });

    const session = await response.json();

    if (session.error) {
      console.error("[STRIPE] Erro:", session.error.message);
      return { success: false, error: session.error.message };
    }

    // Salvar sessao no cache
    if (leadData.phone) {
      paymentSessions.set(leadData.phone, {
        sessionId: session.id,
        status: "pending",
        createdAt: new Date(),
        currency: currency
      });
    }

    console.log("[STRIPE] Sessao criada:", session.id);

    return {
      success: true,
      url: session.url,
      sessionId: session.id
    };

  } catch (error) {
    console.error("[STRIPE] Erro ao criar sessao:", error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Verificar status de uma sessao de pagamento
 * @param {string} sessionId - ID da sessao Stripe
 * @returns {Object} Dados da sessao
 */
async function getSessionStatus(sessionId) {
  try {
    const response = await fetch(`https://api.stripe.com/v1/checkout/sessions/${sessionId}`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${STRIPE_CONFIG.secretKey}`
      }
    });

    const session = await response.json();

    if (session.error) {
      return { success: false, error: session.error.message };
    }

    return {
      success: true,
      status: session.payment_status,
      isPaid: session.payment_status === "paid",
      customerEmail: session.customer_email,
      metadata: session.metadata
    };

  } catch (error) {
    console.error("[STRIPE] Erro ao verificar sessao:", error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Verificar se um lead ja pagou
 * @param {string} phone - Numero de telefone do lead
 * @returns {boolean}
 */
async function hasLeadPaid(phone) {
  const cached = paymentSessions.get(phone);
  if (!cached) return false;

  if (cached.status === "paid") return true;

  // Verificar status atualizado
  const status = await getSessionStatus(cached.sessionId);
  if (status.isPaid) {
    cached.status = "paid";
    paymentSessions.set(phone, cached);
    return true;
  }

  return false;
}

/**
 * Obter sessao de pagamento de um lead
 * @param {string} phone - Numero de telefone
 */
function getLeadPaymentSession(phone) {
  return paymentSessions.get(phone) || null;
}

/**
 * Marcar pagamento como confirmado (chamado pelo webhook ou manualmente)
 * @param {string} phone - Numero de telefone
 */
function markPaymentConfirmed(phone) {
  const cached = paymentSessions.get(phone);
  if (cached) {
    cached.status = "paid";
    cached.paidAt = new Date();
    paymentSessions.set(phone, cached);
  }
}

/**
 * Processar webhook do Stripe
 * @param {Object} event - Evento do webhook
 */
async function processWebhook(event) {
  switch (event.type) {
    case "checkout.session.completed":
      const session = event.data.object;
      if (session.payment_status === "paid" && session.metadata.phone) {
        markPaymentConfirmed(session.metadata.phone);
        console.log("[STRIPE] Pagamento confirmado para:", session.metadata.phone);
        return {
          type: "payment_success",
          phone: session.metadata.phone,
          sessionId: session.id
        };
      }
      break;

    case "checkout.session.expired":
      const expiredSession = event.data.object;
      if (expiredSession.metadata.phone) {
        const cached = paymentSessions.get(expiredSession.metadata.phone);
        if (cached) {
          cached.status = "expired";
          paymentSessions.set(expiredSession.metadata.phone, cached);
        }
      }
      break;
  }

  return null;
}

/**
 * Gerar mensagem de pagamento para WhatsApp
 * @param {string} paymentUrl - URL de pagamento
 * @param {string} currency - Moeda
 */
function formatPaymentMessage(paymentUrl, currency = "usd") {
  const priceLabel = currency === "brl" ? "R$499" : "US$99";

  return `Para agendar a consulta com advogado (${priceLabel}), clique no link abaixo:

${paymentUrl}

Apos o pagamento, voce recebera automaticamente os horarios disponiveis para agendamento.

Se preferir pagar em ${currency === "usd" ? "reais" : "dolares"}, digite "${currency === "usd" ? "BRL" : "USD"}".`;
}

/**
 * Converter objeto para x-www-form-urlencoded
 * Suporta objetos aninhados no formato Stripe
 */
function encodeFormData(data, prefix = "") {
  const pairs = [];

  for (const key in data) {
    if (data.hasOwnProperty(key)) {
      const value = data[key];
      const fullKey = prefix ? `${prefix}[${key}]` : key;

      if (Array.isArray(value)) {
        value.forEach((item, index) => {
          if (typeof item === "object") {
            pairs.push(encodeFormData(item, `${fullKey}[${index}]`));
          } else {
            pairs.push(`${encodeURIComponent(`${fullKey}[${index}]`)}=${encodeURIComponent(item)}`);
          }
        });
      } else if (typeof value === "object" && value !== null) {
        pairs.push(encodeFormData(value, fullKey));
      } else if (value !== undefined && value !== null) {
        pairs.push(`${encodeURIComponent(fullKey)}=${encodeURIComponent(value)}`);
      }
    }
  }

  return pairs.join("&");
}

/**
 * Limpar sessoes antigas (mais de 24h)
 */
function cleanupOldSessions() {
  const now = Date.now();
  const maxAge = 24 * 60 * 60 * 1000; // 24 horas

  for (const [phone, session] of paymentSessions) {
    if (now - session.createdAt.getTime() > maxAge) {
      paymentSessions.delete(phone);
    }
  }
}

// Limpar sessoes antigas a cada hora
setInterval(cleanupOldSessions, 60 * 60 * 1000);

module.exports = {
  STRIPE_CONFIG,
  createCheckoutSession,
  getSessionStatus,
  hasLeadPaid,
  getLeadPaymentSession,
  markPaymentConfirmed,
  processWebhook,
  formatPaymentMessage
};
