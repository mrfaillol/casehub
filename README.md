<div align="center">

<img src="static/brand-kit/favicon/casehub-favicon-degrade-4.svg" alt="CaseHub" width="180" />

# CaseHub

### A norma é código. O código é a norma.

**Versão pública:** `0.9.12-alpha` · **Snapshot:** 2026-06-23 · **Estado:** alpha em desenvolvimento ativo,
com acesso manual para escritórios aprovados.

CaseHub é o **framework jurídico** para escritórios brasileiros: prazos, processos, documentos,
agenda, comunicação e IA contextual no mesmo ambiente. Este repositório público é um snapshot
sanitizado do produto alpha — sem dados de clientes, segredos, sessões WhatsApp, uploads, logs,
backups ou topologia de produção.

[![Licença: AGPL-3.0](https://img.shields.io/badge/licen%C3%A7a-AGPL--3.0-1E4890.svg)](LICENSE)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-6FBE54.svg)](#status)
[![LGPD](https://img.shields.io/badge/LGPD-conforme-001F3E.svg)](SECURITY.md)

[casehub.legal](https://casehub.legal) · [Documentação](docs/) · [Segurança](SECURITY.md) · [Contribuir](CONTRIBUTING.md)

</div>

---

## O que é o CaseHub

CaseHub é uma plataforma de gestão jurídica multilocatária (multitenant) que trata a operação de um
escritório como um sistema. Prazos, processos, clientes, agenda, peças e auditoria deixam de ser
planilhas dispersas e passam a ser entidades versionadas, rastreáveis e governadas por regras —
porque, em direito, **a norma é código e o código é a norma**.

Nasceu da prática real de escritórios brasileiros e hoje opera em **alpha** com cliente ativo em
produção. O foco é o mercado jurídico do Brasil: integração com o ecossistema do CNJ, controle de
prazos processuais, gestão de clientes e agenda — entregues como produto único, configurável e
auditável.

> **Por que "framework"?** Porque a intenção do CaseHub é ser uma base composável, não só um
> aplicativo. As superfícies de extensão — servidor MCP, SDK e CLI — estão **em construção** para
> que qualquer escritório ou firma possa estender e automatizar a própria operação sobre uma
> fundação comum, aberta e auditável.

---

## Status

**Alpha — em produção controlada.** O **núcleo** (gestão de casos, clientes, prazos, agenda,
auditoria) está em operação. As **superfícies de extensão (servidor MCP, SDK, CLI) ainda não estão
prontas — estão em construção ativa** e amadurecem junto com o produto. Interfaces podem mudar entre
versões do alpha.

O escopo atual concentra-se nos módulos integrados abaixo:

| Módulo | O que faz | Status |
|---|---|---|
| **Controladoria** | Prazos fatais, responsáveis, fontes e status alinhados ao CNJ | ✅ em produção |
| **Kanban** | Tarefas, anexos, multi-responsável e arquivamento reversível | ✅ em produção |
| **Clientes e processos** | Cadastro, histórico, documentos e filtros | ✅ em produção |
| **Agenda** | Compromissos, audiências e sincronização Google Calendar | ✅ em produção |
| **Documentos** | Drive, Docs, upload, modelos e trilha de auditoria | ✅ em produção |
| **Gmail/SMTP** | Leitura, envio e configuração por tenant | ✅ em produção |
| **WhatsApp Chat** | Conversas, mídia, follow-up, avatar e proxy multi-tenant | ✅ em produção |
| **WhatsApp Bot** | `whatsapp-web.js`, sessões isoladas por org e HMAC inbound | ✅ em produção |
| **Maestro** | Assistente contextual, com política de IA por escritório | ✅ em produção |

---

## IA e provedores

CaseHub não depende de um único provedor de IA. A camada Maestro pode ser configurada por escritório
conforme política de dados, custo e preferência:

- local/self-hosted, incluindo modelos estilo Hermes via runtime compatível;
- NVIDIA API;
- OpenRouter ou gateway compatível;
- Gemini;
- Claude, Codex, GLM ou outro provedor via adaptador apropriado.

Dados reais de clientes não devem sair do tenant sem configuração explícita, base legal e política do
escritório. Repos públicos devem usar apenas fixtures sintéticas.

---

## As superfícies de plataforma (em construção)

A intenção do CaseHub é oferecer não só uma aplicação, mas uma **superfície de plataforma** com pontos
de entrada coerentes entre si. **Estes ainda estão sendo construídos** — descritos aqui como o
desenho pretendido, não como recurso já disponível:

### 1. Servidor MCP &nbsp;`🚧 em construção`

Um servidor [Model Context Protocol](https://modelcontextprotocol.io) que exporá as capacidades do
CaseHub como ferramentas invocáveis, de forma padronizada, governada por política e auditável.
Versão atual `0.2.0` (MCP stdio, read-only, 6 ferramentas *allowlisted*):

- `search_cases` · `get_case` · `list_clients` · `validate_documento` · `get_system_status` · `list_templates`

### 2. SDK &nbsp;`🚧 em construção`

Uma biblioteca (`casehub-sdk-py` `0.1.x`) para consumir o CaseHub de forma tipada e segura, com
limites claros entre domínios (clientes, casos, documentos, prazos, agenda).

### 3. CLI &nbsp;`🚧 em construção`

Uma ferramenta de linha de comando (`casehub-cli` `0.1.x`), sobre o SDK, para operar o CaseHub
direto do terminal: gerenciar clientes e casos, gerar documentos e acompanhar prazos.

> Quando prontas, as três superfícies compartilharão o mesmo núcleo de domínio, as mesmas regras de
> permissão (RBAC) e a mesma trilha de auditoria. Não há "porta dos fundos": toda capacidade exposta
> passa pelas mesmas garantias.

---

## Quickstart

> Pré-requisitos: Python 3.12+, PostgreSQL 15+. Node.js 20+ apenas para o bot WhatsApp. O CaseHub é
> uma aplicação [FastAPI](https://fastapi.tiangolo.com/) servida via ASGI.

### Docker (recomendado)

```bash
git clone https://github.com/mrfaillol/casehub.git
cd casehub
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.lite.yml up --build
```

Abra `http://localhost:8001/casehub`. No primeiro run, uma conta admin é criada a partir de
`ADMIN_EMAIL` (senha impressa no stdout).

### Local

```bash
# 1. Clone e instale
git clone https://github.com/mrfaillol/casehub.git
cd casehub
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure o ambiente a partir do exemplo
cp .env.example .env
#   defina no mínimo SECRET_KEY, DATABASE_URL, ADMIN_EMAIL

# 3. Suba a aplicação
make dev          # produto immigration
make dev-lite     # produto lite (escritórios brasileiros)
```

Ambos expandem para `CASEHUB_PRODUCT=<product> uvicorn app:app --host 0.0.0.0 --port 8001 --reload`.

> **Nunca** versione o arquivo `.env`, segredos, chaves ou dados reais de clientes. Use sempre
> `.env.example` como modelo e mantenha os valores sensíveis fora do controle de versão.

---

## Arquitetura em alto nível

CaseHub é um monólito modular construído sobre FastAPI, organizado em torno de um *app factory*
que compõe a aplicação a partir de domínios bem delimitados. A variável `CASEHUB_PRODUCT` seleciona
qual produto bootar:

```
CASEHUB_PRODUCT=immigration  ->  core routers + immigration routers + communication routers
CASEHUB_PRODUCT=lite         ->  core routers + communication routers
```

```
┌───────────────────────────────────────────────────────────┐
│                    Superfícies de acesso                    │
│     Web (UI)  ·  API REST     [ SDK · CLI · MCP: 🚧 ]       │
└───────────────────────────────────────────────────────────┘
                              │
┌───────────────────────────────────────────────────────────┐
│                    Núcleo de aplicação                      │
│   app factory · roteadores por domínio · middleware         │
│   (locatário · permissões · feature flags · rate limit)     │
└───────────────────────────────────────────────────────────┘
                              │
┌───────────────────────────────────────────────────────────┐
│                       Domínios                              │
│  Clientes · Casos · Documentos · Prazos · Agenda · Auditoria│
└───────────────────────────────────────────────────────────┘
                              │
┌───────────────────────────────────────────────────────────┐
│        Persistência · criptografia de dados sensíveis       │
│           (PII em repouso) · integrações externas           │
└───────────────────────────────────────────────────────────┘
```

**Princípios estruturais:**

- **Multilocatário por desenho.** Cada requisição é resolvida para uma organização; consultas são
  escopadas por locatário e a separação de dados é uma invariante, não um detalhe.
- **Controle de acesso por papéis (RBAC).** Permissões são aplicadas em camada de middleware.
- **Trilha de auditoria escopada.** Ações relevantes são registradas e consultáveis apenas dentro da
  organização que as gerou.
- **Dados sensíveis criptografados em repouso.** Identificadores pessoais são protegidos por
  criptografia simétrica (Fernet).
- **Integrações declarativas e desligadas por padrão.** Conectores externos exigem ativação
  explícita e credenciais escopadas.

> A configuração de produção, a topologia de implantação e os controles de defesa **não** são
> documentados publicamente. Operadores recebem essa orientação por canais apropriados.

---

## Configuração mínima

| Variável | Uso |
| --- | --- |
| `SECRET_KEY` | Assinatura de sessões e tokens (o app encerra se ausente) |
| `DATABASE_URL` | Conexão PostgreSQL |
| `ADMIN_EMAIL` | Conta admin criada no primeiro run |
| `CASEHUB_PRODUCT` | `lite`, `immigration` ou `whitelabel` |
| `PREFIX` | Prefixo HTTP, padrão `/casehub` |

Integrações opcionais usam variáveis por provedor, por exemplo `GOOGLE_*`, `GMAIL_*`,
`OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, `GEMINI_API_KEY`, `SMTP_*`, `PDPJ_*`, `CALENDLY_*`,
`NOTION_*` e `CASEHUB_INBOUND_HMAC_SECRET`. Veja `.env.example` para todas as variáveis.

---

## Auditabilidade e licença

A auditabilidade é um princípio de design, não um recurso adicional. Em um sistema que modela normas
e prazos, **ser verificável é parte de ser correto**: ações deixam rastro, decisões têm contexto e o
comportamento do sistema pode ser inspecionado.

Por isso o código é aberto sob uma licença que preserva essa transparência mesmo quando o software é
oferecido como serviço.

### Licença

**[AGPL-3.0](https://www.gnu.org/licenses/agpl-3.0.html).**

A AGPL-3.0 é a única licença aprovada pela OSI que estende as obrigações de transparência ao uso em
rede (cláusula 13): quem operar o CaseHub como serviço deve disponibilizar o código correspondente aos
usuários daquele serviço. Isso mantém o framework genuinamente auditável por toda a cadeia.

> Consulte o arquivo [`LICENSE`](LICENSE) para o texto vigente; em caso de divergência entre este
> README e o `LICENSE`, **prevalece o `LICENSE`**.

---

## Segurança e LGPD

CaseHub processa dados de natureza sensível e foi desenhado com postura de privacidade desde a
concepção (*privacy by design*).

- Dados pessoais identificáveis são criptografados em repouso.
- A separação entre locatários é uma invariante de segurança, validada continuamente.
- Integrações de IA e provedores externos são **agnósticas**, desligadas por padrão, com
  consentimento granular e operadas sob acordo de tratamento de dados (DPA) quando aplicável.
- O tratamento de dados pessoais segue a **LGPD** (Lei nº 13.709/2018) e as diretrizes da ANPD.

**Divulgação responsável.** Encontrou uma vulnerabilidade? **Não** abra uma issue pública. Siga o
processo descrito em [`SECURITY.md`](SECURITY.md) para divulgação coordenada.

---

## Política do repositório público

Antes de publicar qualquer mudança:

- rodar scan de segredo e PII;
- remover logs, uploads, backups, caches, sessões e dados de cliente;
- usar apenas dados demonstrativos;
- não commitar `.env`, credenciais Google, tokens WhatsApp, `.wwebjs_auth`, dumps de banco,
  screenshots reais com nomes ou artefatos de VPS.

---

## Contribuição

Contribuições são bem-vindas. Antes de abrir um PR, leia o guia em [`CONTRIBUTING.md`](CONTRIBUTING.md).

- **DCO obrigatório.** Todo commit deve ser assinado com `Signed-off-by` (Developer Certificate of
  Origin) via `git commit -s`.
- **Sem segredos, sem PII.** Nenhuma contribuição pode introduzir credenciais, dados reais de
  clientes, arquivos de ambiente (`.env`) ou ambientes virtuais (`.venv`).
- **Qualidade antes do merge.** Mudanças de interface e comportamento passam por validação visual e
  de desempenho antes de serem consideradas concluídas.

---

## Marca registrada

**CaseHub** é uma marca de seus respectivos detentores. A licença de software AGPL-3.0 cobre o
**código-fonte** — ela **não** concede direitos sobre a marca nominativa, o logotipo ou a identidade
visual do CaseHub.

Você pode usar, estudar, modificar e redistribuir o código conforme a licença, mas **não** pode usar
o nome ou os logotipos "CaseHub" de forma que sugira endosso, afiliação ou origem oficial sem
autorização. Forks e distribuições derivadas devem adotar identidade própria.

Os ativos de marca em `static/brand-kit/` seguem regras específicas de uso documentadas em
[`static/brand-kit/README.md`](static/brand-kit/README.md) e **não** estão sob a licença de software.

---

## Documentação

- [Arquitetura](docs/ARCHITECTURE.md)
- [Setup local](docs/DEVELOPER_SETUP.md)
- [API](docs/API_REFERENCE.md)
- [Manual do usuário](docs/USER_MANUAL.md)
- [White-label](docs/WHITE_LABEL_GUIDE.md)
- [Segurança](SECURITY.md)

---

<div align="center">

## English (short)

**CaseHub** is a multitenant legal operations platform — *the legal framework* — built for Brazilian
law firms. Its core (case management, clients, deadlines, calendar, audit) is in production; its own
**MCP server, SDK, and CLI are under active construction**, all to share one audited core with tenant
isolation and role-based access control.

Currently in **alpha**, in controlled production, focused on the Brazilian legal market.

- **License:** AGPL-3.0 — the OSI-approved license that extends transparency obligations to
  networked/SaaS use. The [`LICENSE`](LICENSE) file prevails.
- **Security & privacy:** PII encrypted at rest, tenant isolation, LGPD-aligned. Report
  vulnerabilities privately via [`SECURITY.md`](SECURITY.md) — do not open public issues.
- **Contributing:** see [`CONTRIBUTING.md`](CONTRIBUTING.md). DCO sign-off required (`git commit -s`).
- **Trademark:** "CaseHub" and its logos are not covered by the software license; forks must adopt
  their own identity.

> *The norm is code. The code is the norm.* — [casehub.legal](https://casehub.legal)

<sub>© LegalOps Co. · CaseHub é uma marca de seus detentores.</sub>

</div>
