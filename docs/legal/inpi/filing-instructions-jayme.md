# INPI Software Registration — Instruções para [parceiro]

> **Confidencial.** Este documento contém metadados para o protocolo INPI de software. **Não usar em canal público.** Repassar via Signal/Threema ou canal jurídico controlado, nunca WhatsApp aberto.

**Issue master:** [`mrfaillol/casehub#413`](https://github.com/mrfaillol/casehub/issues/413)
**Sessão de preparação:** 2026-05-18, Claude Opus 4.7 @mac (autônomo)

---

## 1. Sequência obrigatória

A5 (marca CaseHub) **antes** de A6 (software). INPI software depende de aplicante identificado e marca preferencialmente protocolada.

```
A5 (marca CaseHub)  →  A6 (software CaseHub)
serviço 389/394     →  serviço 730
R$ 880/1.720*       →  R$ 210
*com/sem desconto
```

*Valores oficiais conferidos em 2026-05-17. Verificar tabela vigente em https://www.gov.br/inpi/pt-br/servicos/programas-de-computador/tabela-de-precos antes da GRU.*

---

## 2. Artefato técnico já gerado

### 2.1. Manifesto público (repo)

- **Path no repo:** `docs/legal/inpi/casehub-software-snapshot-e36f414b2beea5417abbed7240ffe2ec81cef742.json`
- **Conteúdo:** metadados (commit SHA, módulos, contagem por linguagem, SHA-256 do ZIP).
- **Não contém código nem segredos.** Pode ser referenciado em PR/issue.

### 2.2. ZIP confidencial (fora do repo)

- **Path local:** `<PRIVATE_DIR>/INPI/CaseHub/casehub-basic-source-snapshot-e36f414b2beea5417abbed7240ffe2ec81cef742.zip`
- **Permissão:** `0600` (apenas owner do Mac do Victor).
- **Tamanho:** 13.062.570 bytes (~13 MB).
- **Arquivos:** 760 (allowlist CaseHub Basic — sem services/, scripts/, docs/).
- **SHA-256:** `b0912cdf52faec75c2fccfd81f0b275d425ccc5102048dcbfd80558d70980e60`
- **Algoritmo do hash:** SHA-256 (este é o exigido pelo e-Software form).

**Nunca commitar o ZIP no repo.** Ele é documentação técnica confidencial conforme orientação INPI.

---

## 3. Dados do aplicante ([parceiro] verifica)

| Campo | Valor |
|---|---|
| Pessoa jurídica titular | **LegalOps Co.** (CNPJ ativo desde 12/Mai/2026, Simples Nacional) |
| Categoria | Software como Serviço (SaaS) jurídico |
| Nome comercial | CaseHub |
| Nome técnico depositado | CaseHub Basic (FASE 1) |
| Linguagens primárias | Python, HTML/Jinja, JavaScript, CSS, SQL |
| Plataformas alvo | Web (server-side rendered) — Docker em VPS Linux |

Confirmar com [parceiro] antes do protocolo:
- CNPJ certificado A1 PJ ICP-Brasil disponível.
- Procuração se [parceiro] não é representante legal direto da LegalOps Co.
- Endereço de notificação INPI.

---

## 4. Passos no e-Software ([parceiro] executa)

1. **Login** em https://www.gov.br/inpi/pt-br com certificado A1 PJ ICP-Brasil da LegalOps Co.
2. **Serviço 730** — Pedido de Registro de Programa de Computador.
3. **GRU** R$ 210,00 — pagar antes; protocolo só aceita com GRU paga.
4. **Formulário e-Software:**
   - Nome técnico: `CaseHub Basic`
   - Versão: snapshot de `e36f414b2beea5417abbed7240ffe2ec81cef742` (data `2026-05-18`)
   - Linguagens: conforme tabela acima
   - Hash do código: `b0912cdf52faec75c2fccfd81f0b275d425ccc5102048dcbfd80558d70980e60`
   - Algoritmo: `SHA-256`
   - Aplicante: **LegalOps Co.** (CNPJ + endereço)
   - Inventores/titulares: conforme acordo societário Victor↔[parceiro]
5. **Declaração de Veracidade** — assinada pelo representante legal com certificado A1 PJ.
6. **Documentação técnica confidencial** — [parceiro] mantém posse do ZIP via canal seguro; **INPI não recebe o código**, apenas o hash e a declaração de que o titular o preserva.
7. **Protocolar.** Anotar número de protocolo retornado.

---

## 5. Pós-protocolo

1. [parceiro] envia número de protocolo + comprovante GRU paga via Signal/Threema.
2. Victor arquiva em `~/Documents/LegalOps-Private/INPI/CaseHub/` junto ao ZIP (chmod 600).
3. Comentar em [`#413`](https://github.com/mrfaillol/casehub/issues/413) com:
   - Número de protocolo INPI
   - Data
   - SHA-256 conferido (mesmo do manifest acima)
   - Status: PROTOCOLADO
4. Atualizar `casehub-software-snapshot-e36f414b...json` com chave `inpi_protocol` em sessão posterior (ruling não exigido — atualização de metadado factual).
5. Fechar `#413` apenas após confirmação de protocolo + arquivo na pasta privada.

---

## 6. Red lines

- **Não submeter pela automação.** [parceiro] protocoliza manualmente com certificado.
- **Não enviar ZIP por WhatsApp/email aberto.** Canal seguro obrigatório.
- **Não usar dados de clientes reais** (o cliente ou outros) em nenhum metadado do filing.
- **Não expandir o allowlist do ZIP** sem revisão técnica + legal — `services/`, `scripts/`, `docs/`, `uploads/` ficam fora por design.
- **Não rotacionar o certificado A1 PJ** durante a janela de protocolo sem novo plano.

---

## 7. Rollback

Se o protocolo for rejeitado ou houver erro técnico:

1. Não tentar resubmissão automática.
2. Anotar motivo da rejeição.
3. Convocar `/council` se for necessária mudança de allowlist, schema do ZIP, ou estratégia de titularidade.
4. Re-rodar `python3 docs/legal/inpi/build-inpi-snapshot.py --commit <SHA novo> --output <path>` se o código mudou desde o snapshot — **atualizar manifest com novo SHA-256**.

---

## 8. Refs

- Manifest atual: `docs/legal/inpi/casehub-software-snapshot-e36f414b2beea5417abbed7240ffe2ec81cef742.json`
- Manifest anterior: `docs/legal/inpi/casehub-software-snapshot-50e8d4ace31b614098354ad576b836bd8ca4ed89.json`
- Builder: `docs/legal/inpi/build-inpi-snapshot.py`
- Issue master: `mrfaillol/casehub#413`
- Cross-repo roadmap: `mrfaillol/trabalho-workspace#142`
- Decisão LegalOps Co. titular: ruling `2026-05-15-beta-funnel-pivot.json` (referência indireta)
