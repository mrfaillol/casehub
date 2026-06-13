/**
 * MAESTRO Claude - Modulo para tarefas complexas
 * Usa Claude Sonnet para raciocinio avancado, code review, planejamento
 */

var Anthropic;
try {
  Anthropic = require('@anthropic-ai/sdk');
} catch (e) {
  console.log("[MAESTRO-CLAUDE] @anthropic-ai/sdk nao instalado. Execute: npm install @anthropic-ai/sdk");
  module.exports = null;
  return;
}

const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY;

const MAESTRO_SYSTEM_PROMPT = [
  "Voce e o MAESTRO, assistente inteligente de administracao de VPS para o ${process.env.ORG_NAME || "CaseHub"}.",
  "Voce e especialista em debug, code review, planejamento e resolucao de problemas.",
  "Responda em portugues brasileiro, de forma clara e tecnica.",
  "",
  "Sua resposta DEVE ser JSON valido com esta estrutura:",
  '{"type":"action|info|clarify|plan",',
  '"message":"mensagem formatada para WhatsApp com *bold*",',
  '"plan":{"summary":"...","steps":["..."],"commands":["..."],"impact":"...","risk":"low|medium|high"},',
  '"needs_auth":true/false}',
  "",
  "REGRAS:",
  "- Para acoes que modificam o sistema: needs_auth=true, mostre plano detalhado",
  "- Para informacoes: needs_auth=false",
  "- Quando nao entender: type=clarify, faca perguntas",
  "- Max 5 comandos por plano",
  "- Sempre explique o raciocinio",
].join("\n");

class MaestroClaude {
  constructor() {
    if (!ANTHROPIC_API_KEY) {
      throw new Error("ANTHROPIC_API_KEY nao configurada");
    }
    this.client = new Anthropic({ apiKey: ANTHROPIC_API_KEY });
    console.log("[MAESTRO-CLAUDE] Inicializado com Claude Sonnet");
  }

  async processComplexTask(message, systemContext, conversationHistory) {
    try {
      var messages = [];

      // Adicionar historico
      if (conversationHistory && conversationHistory.length > 0) {
        for (var i = 0; i < conversationHistory.length; i++) {
          var h = conversationHistory[i];
          messages.push({ role: h.role, content: h.content });
        }
      }

      // Mensagem atual
      messages.push({ role: "user", content: message });

      var response = await this.client.messages.create({
        model: "claude-sonnet-4-20250514",
        max_tokens: 4096,
        system: MAESTRO_SYSTEM_PROMPT + "\n\n" + systemContext,
        messages: messages
      });

      var responseText = '';
      if (response.content && response.content[0]) {
        responseText = response.content[0].text;
      }

      // Parsear JSON
      try {
        var jsonMatch = responseText.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          return JSON.parse(jsonMatch[0]);
        }
      } catch (e) {
        // Se nao conseguir parsear JSON, retornar como texto
      }

      return {
        type: "info",
        message: responseText.substring(0, 3500),
        needs_auth: false
      };

    } catch (e) {
      console.error("[MAESTRO-CLAUDE] Erro:", e.message);
      throw e;
    }
  }
}

var instance = null;
try {
  instance = new MaestroClaude();
} catch (e) {
  console.log("[MAESTRO-CLAUDE] Nao inicializado:", e.message);
}

module.exports = instance;
