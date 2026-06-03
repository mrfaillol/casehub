/**
 * MAESTRO Perplexity - Modulo de pesquisa web
 * Usa Perplexity Sonar para busca inteligente
 */

const PERPLEXITY_API_KEY = process.env.PERPLEXITY_API_KEY;
const PERPLEXITY_URL = 'https://api.perplexity.ai/chat/completions';

class MaestroPerplexity {
  constructor() {
    if (!PERPLEXITY_API_KEY) {
      throw new Error("PERPLEXITY_API_KEY nao configurada");
    }
    console.log("[MAESTRO-PERPLEXITY] Inicializado com Sonar");
  }

  async search(query) {
    try {
      const response = await fetch(PERPLEXITY_URL, {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer ' + PERPLEXITY_API_KEY,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          model: 'sonar',
          messages: [
            {
              role: 'system',
              content: 'Voce e assistente de pesquisa para um escritorio de advocacia de imigracao nos EUA (${process.env.ORG_NAME || "CaseHub"}). Responda em portugues brasileiro de forma clara e concisa. Inclua fontes quando relevante.'
            },
            {
              role: 'user',
              content: query
            }
          ],
          max_tokens: 2000
        })
      });

      if (!response.ok) {
        throw new Error('Perplexity API error: ' + response.status);
      }

      const data = await response.json();

      var messageText = '';
      if (data.choices && data.choices[0] && data.choices[0].message) {
        messageText = data.choices[0].message.content;
      }

      // Formatar para WhatsApp
      var formattedMsg = "*MAESTRO - Resultado da Pesquisa*\n\n";
      formattedMsg += messageText.substring(0, 3500);

      // Adicionar citacoes se disponiveis
      if (data.citations && data.citations.length > 0) {
        formattedMsg += "\n\n*Fontes:*\n";
        for (var i = 0; i < Math.min(data.citations.length, 5); i++) {
          formattedMsg += (i + 1) + ". " + data.citations[i] + "\n";
        }
      }

      return {
        type: "info",
        message: formattedMsg,
        provider_used: "perplexity",
        raw: data
      };

    } catch (e) {
      console.error("[MAESTRO-PERPLEXITY] Erro:", e.message);
      throw e;
    }
  }
}

var instance = null;
try {
  instance = new MaestroPerplexity();
} catch (e) {
  console.log("[MAESTRO-PERPLEXITY] Nao inicializado:", e.message);
}

module.exports = instance;
