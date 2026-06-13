# Templates de Atendimento - Immigrant Law Center
## Referencia para WhatsApp Bot e LLM Chatbot
### Atualizado: 30/01/2026

---

## 1. PRIMEIRO CONTATO (Greeting)

| ID | Nome | Idioma | Descricao |
|----|------|--------|-----------|
| 1 | Clientes Novos (EN) | EN | Saudacao inicial em ingles |
| 2 | Clientes Novos (PT) | PT | Saudacao inicial em portugues |
| 3 | Free Intro Call Offer | EN/PT | Oferta de chamada gratuita |

---

## 2. AGENDAMENTO (Agenda)

| ID | Nome | Idioma | Descricao |
|----|------|--------|-----------|
| 5 | Confirmacao de Reuniao (EN) | EN | Confirmar horario agendado |
| 6 | Confirmacao de Reuniao (PT) | PT | Confirmar horario agendado |
| 7 | Marcando Reuniao (EN) | EN | Enviar link de agendamento |
| 32 | Marcando Reuniao (PT) | PT | Enviar link de agendamento |
| 8 | Reagendando Reuniao | PT/EN | Reagendar horario existente |
| 40 | Incentivar Agendamento | PT | Template para incentivar agendamento |

**Link Gratuito:** https://calendly.com/center-immigrant/15min
**Link Pago ($99):** https://calendly.com/immigrant-info-swfe/consultation

---

## 3. INFORMACOES DE VISTOS

| ID | Nome | Idioma | Descricao |
|----|------|--------|-----------|
| 16 | Info EB-2 NIW | PT | Informacoes sobre visto EB-2 NIW |
| 17 | Info EB-1A | PT | Informacoes sobre visto EB-1A |
| 18 | Processo NIW Detalhado | PT | Explicacao detalhada do processo NIW |

---

## 4. PAGAMENTO

| ID | Nome | Idioma | Descricao |
|----|------|--------|-----------|
| 9 | Info Pagamento (EN) | EN | Informacoes de pagamento |
| 33 | Valores NIW (PT) | PT | Valores para processo NIW |
| 10 | Cobranca Segunda Parcela | PT | Lembrete de pagamento |
| 11 | Confirmacao Pagamento | PT | Confirmar recebimento |

**Regra LLM:** NUNCA mencionar valores exatos de honorarios

---

## 5. FOLLOW-UP

| ID | Nome | Idioma | Descricao |
|----|------|--------|-----------|
| 19 | Encaminhamento (EN) | EN | Encaminhar para proximo passo |
| 20 | Encaminhamento (PT) | PT | Encaminhar para proximo passo |
| 21 | Follow-up 1 (4 dias) | PT | Lembrete apos 4 dias |
| 22 | Follow-up 2 (7 dias) | PT | Lembrete apos 7 dias |
| 23 | Aguardando Docs | PT | Solicitar documentos |
| 38 | Desculpas Demora | PT | Pedir desculpas por atraso |

---

## 6. SUPORTE

| ID | Nome | Idioma | Descricao |
|----|------|--------|-----------|
| 34 | Credenciais/Legitimidade | PT | Responder sobre legitimidade |
| 35 | Suporte Tecnico / Link Quebrado | PT | Ajuda com problemas tecnicos |
| 39 | Verificando Info | PT | Sinalizar que vai verificar com equipe |

---

## 7. CASOS ESPECIAIS

| ID | Nome | Idioma | Descricao |
|----|------|--------|-----------|
| 36 | Caso Urgente (EN) | EN | Atendimento prioritario |
| 37 | Visto Revogado / Caso Complexo | PT | Casos complexos (precisa humano) |

**Regra LLM:** Estes casos SEMPRE sinalizam [PRECISA_HUMANO]

---

## 8. HANDOFF (Transicao Humano/Bot)

| ID | Nome | Idioma | Descricao |
|----|------|--------|-----------|
| 26 | Assumindo Conversa | PT | Humano assume atendimento |
| 27 | Voltando ao Bot | PT | Transferir de volta ao bot |

---

## MAPEAMENTO DE INTENTS (template-matcher.js)

| Intent | Templates Usados | Idioma |
|--------|------------------|--------|
| greeting | 1, 2 | PT/EN |
| price_inquiry | 9, 33 | PT/EN |
| schedule_request | 7, 32 | PT/EN |
| confirmation | 5, 6 | PT/EN |
| niw_inquiry | 18 | PT |
| eb1a_inquiry | 17 | PT |
| greencard_inquiry | 16 | PT |
| technical_issue | 35 | PT |
| legitimacy_inquiry | 34 | PT |
| urgent_case | 36 | EN |
| visa_issue | 37 | PT |
| thanks | 19, 20 | PT/EN |

---

## REGRAS DO LLM CHATBOT

### NUNCA fazer:
1. Mencionar ser IA/bot/automatizado
2. Mencionar localizacao (Connecticut, EUA)
3. Mencionar valores exatos de honorarios
4. Dar conselhos juridicos especificos

### SEMPRE fazer:
1. Usar template como BASE soberana
2. Incentivar agendamento de reuniao
3. Assinar como "Immigrant Law Center"
4. Usar idioma do cliente

### Sinalizar [PRECISA_HUMANO] quando:
- Perguntas sobre estrategia especifica
- Valores detalhados de honorarios
- Prazos especificos de processo
- Questoes juridicas complexas
- Cliente insistente ou irritado
- Qualquer duvida

---

## VARIAVEIS DISPONIVEIS

| Variavel | Descricao | Exemplo |
|----------|-----------|---------|
| [NOME] | Nome do cliente | "Joao" |
| [NAME] | Nome do cliente (EN) | "John" |
| [DATA] | Data atual (PT) | "30/01/2026" |
| [DATE] | Data atual (EN) | "01/30/2026" |
| [HORARIO] | Horario agendado | "14:00" |
| [TIME] | Horario (EN) | "2:00 PM" |
| [EMAIL] | Email do cliente | "joao@email.com" |
| [TELEFONE] | Telefone do cliente | "+5511999999999" |
| [VALOR] | Valor (quando aplicavel) | "$99" |

---

## ARQUIVOS RELACIONADOS

- `/var/www/immigrant.law/whatsapp-bot/templates.js` - Definicao dos templates
- `/var/www/immigrant.law/whatsapp-bot/template-matcher.js` - Classificacao de intents
- `/var/www/immigrant.law/whatsapp-bot/llm-chatbot.js` - Chatbot LLM (Gemini)
- `/var/www/immigrant.law/whatsapp-bot/server.js` - Servidor principal

---

*Documento gerado automaticamente. Para alteracoes, editar templates.js*
