<div align="center">

<img src="static/brand-kit/logo/casehub-logo-login-blue.svg" alt="CaseHub" width="180" />

### A norma é código. O código é a norma.

**O framework jurídico** — uma plataforma de gestão e operações jurídicas para escritórios
de direito público e privado. O app vivo está em produção controlada como CaseHub `2.0.0`;
servidor MCP, SDK e CLI próprios estão em `0.1.0` de validação, mas ainda não são API pública
estável neste snapshot.

[![Licença: AGPL-3.0](https://img.shields.io/badge/licen%C3%A7a-AGPL--3.0-1E4890.svg)](LICENSE)
[![Status: Alpha](https://img.shields.io/badge/status-alpha-6FBE54.svg)](#status)
[![LGPD](https://img.shields.io/badge/LGPD-alinhado-001F3E.svg)](SECURITY.md)

[casehub.legal](https://casehub.legal) · [Documentação](docs/) · [Segurança](SECURITY.md) · [Contribuir](CONTRIBUTING.md)

</div>

---

## O que é o CaseHub

O CaseHub é uma plataforma de gestão jurídica multilocatária (multitenant) que trata a operação
de um escritório como um sistema. Prazos, processos, clientes, agenda, peças e auditoria deixam
de ser planilhas dispersas e passam a ser entidades versionadas, rastreáveis e governadas por
regras — porque, em direito, **a norma é código e o código é a norma**.

A premissa é simples: um escritório de advocacia roda sobre normas, prazos e procedimentos.
Quando esses elementos são modelados com o mesmo rigor de um sistema de software — com tipos,
validações, trilha de auditoria e integrações declarativas — o trabalho jurídico ganha
previsibilidade, transparência e escala.

O CaseHub nasceu da prática real de escritórios brasileiros e hoje opera em **alpha** com cliente
ativo em produção. O foco é o mercado jurídico do Brasil: integração com o ecossistema do CNJ,
controle de prazos processuais, gestão de clientes e agenda — entregues como produto único,
configurável e auditável.

> **Por que "framework"?** Porque a intenção do CaseHub é ser uma base composável, não só um
> aplicativo. As superfícies de extensão — servidor MCP, SDK e CLI — estão em **validação 0.1.0**
> para que qualquer escritório ou firma, de direito público ou privado, possa estender e automatizar
> a própria operação sobre uma fundação comum, aberta e auditável.

---

## Status

**Alpha — em produção controlada.** O CaseHub está em uso real por escritório cliente, com release
público progressivo. O **núcleo** (gestão de casos, clientes, prazos, agenda, auditoria) está em
operação como app `2.0.0` no ambiente vivo. As **superfícies de extensão (servidor MCP, SDK, CLI)**
existem como implementação `0.1.0` em validação no repositório privado de produto, mas ainda não
foram promovidas para este snapshot público nem devem ser tratadas como contrato estável. Interfaces
podem mudar entre versões do alpha.

O escopo atual concentra-se em quatro módulos integrados:

| Módulo | O que faz | Status |
|---|---|---|
| **Controladoria** | Painel de operações jurídicas: prazos, processos e acompanhamento alinhados ao CNJ | ✅ em produção |
| **Kanban** | Fluxo de trabalho visual por caso, equipe e etapa | ✅ em produção |
| **Clientes (CRM)** | Cadastro e relacionamento de clientes em base unificada | ✅ em produção |
| **Agenda** | Calendário com integração ao Google Calendar | ✅ em produção |

---

## Versionamento real

O CaseHub separa versões de produto, snapshot público e ferramentas de plataforma:

- **App vivo:** `/casehub/healthz` em `casehub.legal` e `vieirasalles.casehub.legal` reporta
  `product=lite`, `version=2.0.0`.
- **Snapshot público:** este repositório é o release público AGPL inicial; ele não é o mesmo branch
  privado usado para deploy do alpha vivo.
- **MCP, SDK e CLI:** implementações `0.1.0` em validação privada. Elas ainda não são contrato
  público estável.

---

## As superfícies de plataforma (0.1.0 em validação)

A intenção do CaseHub é oferecer não só uma aplicação, mas uma **superfície de plataforma** com
pontos de entrada coerentes entre si. O estado honesto em 2026-06-03 é: há implementação `0.1.0`
em validação, mas ela ainda não foi publicada neste repositório público.

### 1. Servidor MCP &nbsp;`0.1.0 em validação`

Um servidor [Model Context Protocol](https://modelcontextprotocol.io) read-only, tenant-scoped,
stdio e default-off está em validação. Ele expõe consultas operacionais com autenticação,
redação de argumentos e auditoria best-effort; não está montado no `app_factory` e não é dependência
do app vivo.

### 2. SDK &nbsp;`0.1.0 em validação`

Há um exportador OpenAPI e um cliente Python fino para autenticação e GETs JSON autenticados em
validação. SDKs gerados permanecem como artefato de CI/roadmap até a publicação de um contrato
externo estável.

### 3. CLI &nbsp;`0.1.0 em validação`

Uma CLI Typer/Rich para fluxos operacionais restritos (`migrate`, `seed`, `deploy`) está em
validação com `--dry-run` e testes. Ela embrulha caminhos existentes; não substitui o processo de
deploy governado nem autoriza produção automaticamente.

> Quando prontas, as três superfícies compartilharão o mesmo núcleo de domínio, as mesmas regras de
> permissão (RBAC) e a mesma trilha de auditoria. Não há "porta dos fundos": toda capacidade exposta
> passa pelas mesmas garantias.

---

## Quickstart

> Pré-requisitos: Python 3.12+. O CaseHub é uma aplicação [FastAPI](https://fastapi.tiangolo.com/) servida via ASGI.

```bash
# 1. Clone o repositório
git clone https://github.com/mrfaillol/casehub.git
cd casehub

# 2. Crie e ative um ambiente virtual
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure o ambiente a partir do exemplo
cp .env.example .env
#   edite .env com suas credenciais e segredos locais

# 5. Suba a aplicação
uvicorn app:app --reload --port 8000
```

A aplicação ficará disponível em `http://localhost:8000`. Consulte [`docs/`](docs/) para o guia de
configuração completo, modelo de dados e referência de API.

> **Nunca** versione o arquivo `.env`, segredos, chaves ou dados reais de clientes. Use sempre
> `.env.example` como modelo e mantenha os valores sensíveis fora do controle de versão.

---

## Arquitetura em alto nível

O CaseHub é um monólito modular construído sobre FastAPI, organizado em torno de um *app factory*
que compõe a aplicação a partir de domínios bem delimitados.

```
┌───────────────────────────────────────────────────────────┐
│                    Superfícies de acesso                    │
│     Web (UI)  ·  API REST     [ MCP · SDK · CLI: 0.1.0 ]    │
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
- **Trilha de auditoria escopada.** Ações relevantes são registradas e consultáveis apenas dentro
  da organização que as gerou.
- **Dados sensíveis criptografados em repouso.** Identificadores pessoais são protegidos por
  criptografia simétrica.
- **Integrações declarativas e desligadas por padrão.** Conectores externos exigem ativação
  explícita e credenciais escopadas.

> A configuração de produção, a topologia de implantação e os controles de defesa **não** são
> documentados publicamente. Operadores recebem essa orientação por canais apropriados.

---

## Auditabilidade e licença

A auditabilidade é um princípio de design, não um recurso adicional. Em um sistema que modela
normas e prazos, **ser verificável é parte de ser correto**: ações deixam rastro, decisões têm
contexto e o comportamento do sistema pode ser inspecionado.

Por isso o código é aberto sob uma licença que preserva essa transparência mesmo quando o software
é oferecido como serviço.

### Licença

**[AGPL-3.0](https://www.gnu.org/licenses/agpl-3.0.html).**

A AGPL-3.0 é a única licença aprovada pela OSI que estende as obrigações de transparência ao uso em
rede (cláusula 13): quem operar o CaseHub como serviço deve disponibilizar o código correspondente
aos usuários daquele serviço. Isso mantém o framework genuinamente auditável por toda a cadeia.

> Consulte o arquivo [`LICENSE`](LICENSE) para o texto vigente; em caso de divergência entre este
> README e o `LICENSE`, **prevalece o `LICENSE`**.

---

## Segurança e LGPD

O CaseHub processa dados de natureza sensível e foi desenhado com postura de privacidade desde a
concepção (*privacy by design*).

- Dados pessoais identificáveis são criptografados em repouso.
- A separação entre locatários é uma invariante de segurança, validada continuamente.
- Integrações de IA e provedores externos são **agnósticas**, desligadas por padrão, com
  consentimento granular e operadas sob acordo de tratamento de dados (DPA) quando aplicável.
- O tratamento de dados pessoais segue a **LGPD** (Lei nº 13.709/2018) e as diretrizes da ANPD.

**Divulgação responsável.** Encontrou uma vulnerabilidade? **Não** abra uma issue pública. Siga o
processo descrito em [`SECURITY.md`](SECURITY.md) para divulgação coordenada.

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

<div align="center">

## English (short)

**CaseHub** is a multitenant legal operations platform — *the legal framework* — built for law firms
in public and private practice. Its core (case management, clients, deadlines, calendar, audit) is in
production as app **2.0.0**; its own **MCP server, SDK, and CLI have 0.1.0 implementations under validation**.
They are not yet a stable public API in this snapshot.

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
