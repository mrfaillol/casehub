# Proposta — Formalizar fallback OAB/DataJud como permanente FASE 1

> **Tipo:** proposta técnica/jurídica para Council.
> **Status:** DRAFT — aguarda deliberação `/council`.
> **Convocação:** companion PR [`mrfaillol/trabalho-workspace#197`](https://github.com/mrfaillol/trabalho-workspace/pull/197), arquivo `agents/knowledge/council/drafts/2026-05-18-fallback-oab-datajud.convocation.md`.
> **Issue master:** [`mrfaillol/casehub#342`](https://github.com/mrfaillol/casehub/issues/342)

---

## 1. Contexto

O módulo Controladoria do CaseHub Basic depende, por design original, do **PDPJ/CNJ** como fonte primária de intimações e movimentações processuais. Em **17/Mai/2026** o Codex confirmou que a pendência PDPJ é responsabilidade **Victor/CNJ** (não [parceiro]): o cliente OAuth2 PDPJ aguarda destravamento pelo CNJ, sem SLA conhecido.

Enquanto isso, o código em `routes/controladoria.py` já implementa cadeia transparente de fallback:

```
ComunicaAPI (PJE/CNJ)  →  DataJud (CNJ)  →  Escavador  →  JusBrasil
```

A rota autenticada `POST /casehub/controladoria/buscar-comunicaapi` retorna resultados marcados como `fallback_limited` quando PDPJ falha, sem quebrar a UX. Smoke técnico em dev e VS-prod (`f09a0b5f`) confirmou que a chain funciona.

**Hoje:** `#342` está OPEN com status `partial` aguardando PDPJ. **Risco:** se o CNJ não responder em janela razoável, o gate PAO `#347` fica preso indefinidamente sem alternativa formalizada.

## 2. Proposta

**Formalizar via ruling Council que, se o cliente OAuth2 PDPJ não for destravado até `2026-06-30`**, o fallback OAB/DataJud como cadeia primária passa a ser a estratégia **permanente** da FASE 1, com PDPJ relegado a "futuro reativável quando CNJ responder".

Termos do ruling proposto:

1. **Prazo gatilho:** `2026-06-30 23:59 BRT`. Antes disso, manter PDPJ como objetivo; após, fallback vira default formal.
2. **Aceitação técnica:** o status atual da cadeia (ComunicaAPI→DataJud→Escavador→JusBrasil) é declarado suficiente para FASE 1 Basic. Sem necessidade de implementação adicional pré-pivot.
3. **Marca de status:** resultados sem PDPJ continuam marcados `fallback_limited` na UI — usuário sempre sabe que está vendo fallback.
4. **UX**: copy do painel "Status das APIs de prazos" em Controladoria mobile explicita: "Operando sob fallback CNJ/OAB; PDPJ em hold até CNJ destravar".
5. **#342 elegível para fechamento** caso (a) ruling aprovado E (b) prazo gatilho atingido E (c) `#480` runner + PAO `#347` não introduzirem novos blockers no módulo.
6. **Reativação PDPJ no futuro:** quando CNJ responder, ativação não-quebra (mudança de boolean de feature flag); não é blocker de FASE 2.

## 3. Riscos & mitigação

| Risco | Probabilidade | Mitigação |
|---|---|---|
| Cliente sem PDPJ tem cobertura inferior de comarcas | Média | DataJud cobre TJs principais; Escavador/JusBrasil preenchem lacunas regionais. Documentar cobertura conhecida em `docs/integrations/controladoria-fallback-coverage.md` (próxima sessão). |
| o cliente ou cliente futuro exige PDPJ oficial | Baixa-Média | Cliente pode optar por "modo PDPJ-only" via setting (não implementado, mas reservado). Sem demanda confirmada hoje. |
| Reabertura PDPJ no futuro quebra fallback | Baixa | Cadeia atual é additive — PDPJ entra no topo, demais ficam como secondary. Toggle limpo. |
| Marca regulatória — uso intenso DataJud sem PDPJ pode atrair atenção | Baixa | DataJud é API pública oficial CNJ; uso conforme termos. Escavador/JusBrasil têm planos B2B com contrato. |

## 4. Por que ruling Council e não apenas decisão Victor

- Toca módulo **core de produto** (`Controladoria`), que é red line de produto para vendas.
- Define **superfície de fallback persistente** — decisão arquitetural com consequência de longo prazo.
- Afeta narrativa comercial [parceiro] — fallback formalizado é parte do framework jurídico oferecido.
- Council reconhece `Sentinela` (security) + `science-engineer` (performance/UX rigor) + `git-custodian` (audit trail).

## 5. Quórum sugerido

- `sentinela` (veto) — confirmar que cadeia fallback não introduz vazamento de dados nem expansion de surface (Escavador/JusBrasil são third-party).
- `git-custodian` (veto) — garantir append-only audit trail desta decisão.
- `workspace-janitor` (veto) — confirmar que ruling não fragmenta docs entre repos.
- `science-engineer` (voice) — sanity check de performance da cadeia em produção.

## 6. Outcomes possíveis

| Outcome | Significado |
|---|---|
| `approve` | Fallback permanente formalizado; `#342` ganha critério de fechamento condicional ao prazo gatilho. |
| `approve_with_conditions` | Aprovado com requisitos adicionais (ex: documentar cobertura, rate-limit Escavador). |
| `defer` | Aguardar +30d sem ruling; reavaliar em 2026-06-18. |
| `reject` | Manter `#342` OPEN sem prazo gatilho — risco de hold indefinido. |

## 7. Não-objetivos desta proposta

- **Não** remove PDPJ do roadmap FASE 2.
- **Não** autoriza desinstalar cliente OAuth2 PDPJ (mantém código pronto para reativar).
- **Não** decide sobre vendas para clientes que exijam PDPJ contratualmente — caso a caso.
- **Não** afeta `#478` (Google Calendar OAuth prod) — agendas separadas.

## 8. Refs

- Issue [`#342`](https://github.com/mrfaillol/casehub/issues/342)
- Comment Codex 2026-05-18 sobre OAB/DataJud fallback transparente
- `routes/controladoria.py` — chain ComunicaAPI→DataJud→Escavador→JusBrasil
- `agents/knowledge/council/principles.md` — protocolo Council
- Trilha handoff: `docs/handoff/claude-code-2026-05-18-alpha-closeout/30-controladoria-pdpj-oab-342.md`

— Drafted by Claude Opus 4.7 @mac, 2026-05-18, em sessão handoff alpha-closeout.
