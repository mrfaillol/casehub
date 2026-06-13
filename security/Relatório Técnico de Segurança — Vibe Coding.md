# Relatório Técnico de Segurança — Análise de Vulnerabilidades e Melhores Práticas para Vibe Coding

## Sumário Executivo

Este relatório analisa as vulnerabilidades de segurança demonstradas no vídeo "H4CK3EI O CURSO DO RUYTER" (YuriRDev, novembro de 2025), no qual um pesquisador de segurança identificou e reportou responsavelmente múltiplas falhas críticas em uma plataforma de cursos online. Todas as vulnerabilidades foram corrigidas antes de qualquer exploração maliciosa real. O objetivo deste documento é mapear cada falha encontrada contra frameworks de segurança reconhecidos internacionalmente — especialmente o **OWASP API Security Top 10 2023** — e fornecer diretrizes práticas e aplicáveis a qualquer projeto de software construído com metodologia de vibe coding (desenvolvimento assistido por IA).

***

## 1. Contexto: O Risco de Segurança no Vibe Coding

Antes de detalhar as falhas específicas do caso, é fundamental compreender o cenário de risco do vibe coding como metodologia de desenvolvimento. Pesquisadores da Georgia Tech rastrearam aproximadamente 50 ferramentas de assistência à programação com IA e identificaram 74 vulnerabilidades confirmadas (CVEs) introduzidas diretamente por código gerado por essas ferramentas. Ferramentas como Claude Code, GitHub Copilot, Cursor e Amazon Q foram identificadas como responsáveis por introdução de falhas reais em projetos de produção.[^1]

Um estudo sistemático demonstrou que, quando o código gerado por IA passa por revisões iterativas via follow-up prompts, sua segurança se deteriora progressivamente: após apenas cinco iterações, o código continha **37% mais vulnerabilidades críticas** do que na versão inicial. As categorias mais comuns de falhas introduzidas por código de IA incluem:[^2]

- **CWE-94**: Injeção de código (code injection)
- **CWE-78**: Injeção de comandos do sistema operacional
- **CWE-190**: Overflow de inteiro
- **CWE-306**: Ausência de verificação de autenticação
- **CWE-434**: Upload irrestrito de arquivos

Adicionalmente, ferramentas de IA tendem a gerar código com lógica de autenticação implementada inteiramente no lado do cliente, chaves de API expostas diretamente no frontend, ausência de sanitização de inputs do usuário e dependências desatualizadas ou fictícias. Compreender esse risco estrutural é o primeiro passo para construir software seguro com auxílio de IA.[^2]

***

## 2. Inventário de Vulnerabilidades do Caso Analisado

O vídeo documentou, em ordem de descoberta, as seguintes falhas de segurança:

| # | Vulnerabilidade | Classificação OWASP API 2023 | Gravidade |
|---|-----------------|-------------------------------|-----------|
| V1 | Enumeração de subdomínios e endpoints admin expostos | API9:2023 — Improper Inventory Management | Alta |
| V2 | Supabase sem Row Level Security (RLS) configurado | API8:2023 — Security Misconfiguration | Crítica |
| V3 | Vazamento de PII (nome, e-mail, telefone) em API pública | API3:2023 — Broken Object Property Level Authorization | Crítica |
| V4 | Engenharia Social via dados vazados (phishing/pretexting) | (Ameaça derivada das anteriores) | Alta |
| V5 | Escalada de privilégios via manipulação de resposta HTTP (role no cliente) | API5:2023 — Broken Function Level Authorization | Crítica |
| V6 | Injeção de HTML/JS arbitrário sem sanitização (Stored XSS) | API8:2023 — Security Misconfiguration | Crítica |
| V7 | Token de acesso em cookie sem flag Secure/HttpOnly | API2:2023 — Broken Authentication | Alta |
| V8 | Contorno de restrições de conteúdo via manipulação de resposta (`released: false → true`) | API5:2023 — Broken Function Level Authorization | Média |

***

## 3. Análise Técnica Detalhada por Vulnerabilidade

### 3.1 — Enumeração de Subdomínios e Endpoints Admin Expostos (V1)

**O que aconteceu:** O pesquisador utilizou a ferramenta **Gobuster** para realizar enumeração de subdomínios DNS a partir apenas do domínio raiz público, descobrindo os subdomínios `comunidade.*` e `refunds.*`, além de endpoints administrativos comentados no código-fonte do frontend (visíveis no JavaScript servido ao navegador).[^3]

**Por que é perigoso:** Subdomínios frequentemente expõem serviços esquecidos, ambientes de desenvolvimento ou portais administrativos com segurança mais fraca. Endpoint paths de administração visíveis no código-fonte do cliente revelam a estrutura interna da API, facilitando ataques direcionados.[^4][^5]

**Classificação:** OWASP API9:2023 — *Improper Inventory Management*.[^6]

**Mitigações obrigatórias:**
- Nunca expor nomes de rotas administrativas, roles ou endpoints no bundle JavaScript do frontend.
- Separar completamente a URL base da API de admin da API pública; preferencialmente em domínio/subdomínio protegido por VPN ou allowlist de IPs.
- Realizar auditorias periódicas de surface de ataque com ferramentas como Shodan, Censys e subfinder para identificar exposições não intencionais.[^4]
- Implementar política de não-divulgação de estrutura de rotas (security through obscurity não é suficiente, mas não deve-se facilitar o trabalho do atacante).

***

### 3.2 — Banco de Dados Supabase sem Row Level Security (V2)

**O que aconteceu:** A plataforma utilizava Supabase como backend-as-a-service. O RLS (Row Level Security) — o mecanismo que define quem pode ler ou escrever em quais tabelas e linhas — estava desabilitado na tabela de respostas de reembolso (`refound_quiz_responses`). Qualquer pessoa com a URL da API e a `anon key` (que é pública e visível no código do frontend) conseguia ler todos os registros da tabela, incluindo dados pessoais sensíveis de centenas de usuários.

**Por que é perigoso:** No Supabase, a `anon key` é projetada para ser exposta publicamente no cliente — a segurança real depende **inteiramente** das políticas de RLS configuradas no banco de dados. Uma tabela com RLS desabilitado é acessível por qualquer pessoa com a URL do projeto.[^7]

**Classificação:** OWASP API8:2023 — *Security Misconfiguration*.[^6]

**Mitigações obrigatórias:**

```sql
-- 1. Habilitar RLS em TODAS as tabelas da schema pública
ALTER TABLE refound_quiz_responses ENABLE ROW LEVEL SECURITY;

-- 2. Política: apenas o próprio usuário autenticado pode ver seus dados
CREATE POLICY "users_own_data"
  ON refound_quiz_responses FOR ALL
  USING (user_id = auth.uid());

-- 3. Validar que o dado escrito pertence ao usuário autenticado
CREATE POLICY "insert_own_data" ON refound_quiz_responses FOR INSERT
  WITH CHECK (user_id = auth.uid());
```

- **NUNCA** incluir a `service_role key` no código cliente. Ela bypassa TODAS as políticas de RLS e deve ser tratada como segredo absoluto, existindo apenas em variáveis de ambiente no servidor.[^7]
- Testar as políticas de RLS impersonando diferentes roles diretamente no SQL Editor do Supabase (anon, authenticated, usuários específicos).[^7]
- Executar o **checklist de segurança do Supabase** após cada nova tabela criada:[^7]
  - ☑ RLS habilitado em todas as tabelas públicas
  - ☑ Pelo menos uma política por tabela
  - ☑ Service role key ausente no código cliente
  - ☑ Confirmação de e-mail habilitada
  - ☑ URLs de redirect em allowlist

***

### 3.3 — Vazamento de PII em Respostas de API (V3)

**O que aconteceu:** Ao visualizar comentários de aulas, a aba de Network do navegador revelava que a API retornava, para cada comentador, campos como **nome completo, e-mail, telefone e CPF** — dados completamente desnecessários para renderizar um comentário na interface. O frontend simplesmente ignorava esses campos ao renderizar, mas qualquer pessoa inspecionando o tráfego de rede tinha acesso a eles.[^8]

**Por que é perigoso:** Este é um padrão antipattern clássico: a API delega a filtragem de dados ao cliente, enviando muito mais informação do que necessário. Atacantes podem interceptar o tráfego bruto e coletar dados pessoais de todos os usuários que comentarem.[^8]

**Classificação:** OWASP API3:2023 — *Broken Object Property Level Authorization*.[^6]

**Implicações legais (LGPD):** CPF, e-mail, telefone e nome completo são dados pessoais sensíveis protegidos pela **Lei Geral de Proteção de Dados (Lei 13.709/2018)**. Uma exposição desse tipo pode resultar em multas de até 2% do faturamento da empresa, com teto de **R$ 50 milhões por infração**, além de publicação obrigatória do incidente pela ANPD. A partir de 2021, a ANPD está ativamente aplicando sanções.[^9][^10]

**Mitigações obrigatórias:**
- **Princípio do mínimo necessário:** cada endpoint de API deve retornar apenas os campos estritamente necessários para sua função. Para listar comentários, retornar somente `{id, author_display_name, content, created_at}`.[^11]
- Definir schemas de resposta explícitos (DTOs — Data Transfer Objects) e validar que nenhum campo sensível escape por eles.
- Realizar auditorias periódicas de todas as respostas de API em busca de campos não intencionais.[^12]
- Implementar **OpenAPI / Swagger** para documentar e enforçar contratos de API, incluindo o que cada endpoint pode retornar.[^8]
- Nunca deixar a filtragem de dados sensíveis a cargo do cliente.[^8]

***

### 3.4 — Engenharia Social Habilitada por Dados Vazados (V4)

**O que aconteceu:** Com os dados obtidos via V2 e V3 (nome, e-mail e telefone de pessoas que solicitaram reembolso), o pesquisador montou um ataque de **pretexting**: criou um número de WhatsApp com nome e foto da plataforma oficial, entrou em contato com usuários fingindo ser o suporte, e solicitou credenciais de acesso "para processar o reembolso". Uma das primeiras pessoas abordadas entregou suas credenciais sem hesitar.

**Por que é perigoso:** Este ataque não exige nenhuma habilidade técnica avançada. O acesso a dados pessoais como telefone e contexto da situação (pedido de reembolso) é suficiente para construir uma narrativa convincente. Engenharia social é responsável por uma parcela significativa dos incidentes de segurança mais sérios, como o vazamento da Qantas em 2025, que expôs dados de mais de 6 milhões de clientes via ataque de engenharia social em sistema terceirizado.[^13][^14]

**Mitigações obrigatórias:**
- Eliminar o vazamento de dados na fonte (V2 e V3 corrigidos eliminam a matéria-prima deste ataque).
- **Nunca solicitar senhas por canais externos** à plataforma. Comunicar isso claramente aos usuários na interface.
- Implementar avisos proativos no painel do usuário: "Nossa equipe NUNCA solicitará sua senha por WhatsApp, e-mail ou telefone."
- Treinar equipes de suporte para nunca pedir credenciais; usar fluxos de verificação de identidade internos à plataforma (tokens de reset, código OTP).[^15]
- Implementar autenticação multifator (MFA) para que credenciais sozinhas não sejam suficientes para comprometer contas.[^15]

***

### 3.5 — Escalada de Privilégios via Manipulação de Resposta HTTP (V5)

**O que aconteceu:** Após obter acesso à plataforma, o pesquisador utilizou o **Burp Suite** como proxy entre o navegador e o servidor. A resposta da API de autenticação retornava o campo `role: "student"`. Usando o recurso de Match & Replace do Burp Suite, ele substituiu automaticamente `"student"` por `"admin"` em todas as respostas. O frontend, ao receber o role `admin`, renderizou menus e botões de administração que estavam ocultos. Ao clicar nesses elementos, as chamadas de API — que deveriam ser protegidas no servidor — responderam com sucesso.

**Por que é perigoso:** Esta é a vulnerabilidade de **escalada de privilégios horizontal/vertical** mais clássica: a verificação de permissão existia apenas no frontend (renderização condicional), mas **nenhuma verificação de autorização era feita no servidor** para os endpoints administrativos. Qualquer proteção implementada apenas no cliente pode ser trivialmente contornada com um proxy HTTP.[^16][^17]

**Classificação:** OWASP API5:2023 — *Broken Function Level Authorization*.[^6]

**Princípio fundamental:** O cliente é não-confiável por definição. **Toda e qualquer verificação de permissão DEVE ser implementada e enforçada no servidor.** A renderização condicional de UI é um luxo de UX, nunca um controle de segurança.[^18][^19]

**Mitigações obrigatórias:**

```javascript
// ❌ ERRADO: Verificação apenas no cliente (JavaScript)
if (user.role === 'admin') {
  showAdminPanel(); // Facilmente contornável
}

// ✅ CORRETO: Middleware de autorização no servidor
// Express.js exemplo
function requireAdmin(req, res, next) {
  const userFromToken = verifyJWT(req.cookies.token); // Token do servidor
  if (!userFromToken || userFromToken.role !== 'admin') {
    return res.status(403).json({ error: 'Forbidden' });
  }
  next();
}

app.post('/api/admin/modules', requireAdmin, createModuleHandler);
app.delete('/api/admin/modules/:id', requireAdmin, deleteModuleHandler);
```

- Implementar **RBAC (Role-Based Access Control)** no servidor, verificando permissões em cada handler ou via middleware centralizado.[^20][^13]
- O role do usuário deve ser derivado exclusivamente do token de autenticação assinado pelo servidor (JWT com secret, ou sessão server-side), nunca de um campo enviado pelo cliente no corpo da requisição.[^21]
- Adotar o **princípio do menor privilégio**: cada conta e cada API deve ter acesso apenas ao mínimo estritamente necessário para sua função.[^22][^20]
- Realizar testes de penetração específicos para escalada de privilégios: tentar acessar rotas admin com tokens de usuários comuns.[^17]

***

### 3.6 — Injeção de HTML/JavaScript Arbitrário — Stored XSS (V6)

**O que aconteceu:** Com acesso de admin (obtido via V5), o pesquisador encontrou uma configuração de "HTML personalizado" que permitia inserir código HTML e JavaScript. Este código era salvo no banco de dados e injetado em **todas as páginas** da plataforma sem qualquer sanitização. O pesquisador demonstrou que poderia redirecionar usuários para páginas de pagamento falsas, roubar tokens de sessão e modificar completamente o conteúdo da plataforma.

**Por que é perigoso:** Este é um ataque de **Stored XSS (Cross-Site Scripting persistente)** de máxima gravidade. O código malicioso é armazenado no servidor e executado no navegador de **todos os usuários** que visitam a plataforma. Com XSS, um atacante pode: roubar cookies e tokens de sessão, redirecionar usuários, realizar ações em nome das vítimas, capturar credenciais via formulários falsos, e instalar malware via drive-by download.[^23]

**Classificação:** OWASP API8:2023 — *Security Misconfiguration*.[^6]

**Mitigações obrigatórias:**

1. **Sanitização de input:** Qualquer HTML inserido por usuário (mesmo admin) deve ser sanitizado com uma biblioteca como [DOMPurify](https://github.com/cure53/DOMPurify) antes de ser salvo:

```javascript
import DOMPurify from 'dompurify';

// Antes de salvar no banco:
const sanitizedHTML = DOMPurify.sanitize(userProvidedHTML, {
  ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'a', 'p', 'br'],
  ALLOWED_ATTR: ['href', 'class']
  // JavaScript e event handlers são removidos automaticamente
});
```

2. **Content Security Policy (CSP):** Implementar o header `Content-Security-Policy` que instrui o navegador a executar scripts apenas de origens explicitamente autorizadas:[^24][^25]

```
Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.trusted.com; object-src 'none'; base-uri 'self';
```

Uma CSP estrita protege contra XSS stored, reflected e DOM-based mesmo se a sanitização falhar como segunda linha de defesa.[^25]

3. **Nunca usar `innerHTML` diretamente** com conteúdo de usuário. Prefira `textContent` para texto puro, ou renderização controlada via framework (React, Vue já escapam por padrão).[^23]

4. Aplicar o header `X-Content-Type-Options: nosniff` para evitar MIME type sniffing.[^26]

***

### 3.7 — Token de Autenticação em Cookie Sem Flags de Segurança (V7)

**O que aconteceu:** O pesquisador observou que o token de acesso da sessão era armazenado em um cookie **sem as flags `HttpOnly` e `Secure`**. Isso significa que o token era acessível via `document.cookie` em JavaScript — tornando-o vulnerável a roubo por qualquer script XSS.[^27]

**Por que é perigoso:** Sem a flag `HttpOnly`, qualquer código JavaScript executado na página (incluindo via XSS) pode ler o token de sessão e usá-lo para sequestrar a conta do usuário em outro dispositivo/local. Sem a flag `Secure`, o cookie pode ser transmitido em conexões HTTP não-criptografadas.[^28][^27]

**Classificação:** OWASP API2:2023 — *Broken Authentication*.[^6]

**Configuração correta dos cookies de sessão/JWT:**

| Flag | Função | Obrigatório em Produção |
|------|---------|------------------------|
| `HttpOnly` | Impede acesso via JavaScript (`document.cookie`), protegendo contra XSS[^27] | ✅ Sim |
| `Secure` | Cookie só é enviado em conexões HTTPS[^29] | ✅ Sim |
| `SameSite=Strict` | Previne envio do cookie em requisições cross-site (proteção CSRF)[^29] | ✅ Sim |

```javascript
// Node.js / Express — configuração correta
res.cookie('access_token', jwt, {
  httpOnly: true,    // Inacessível via JS
  secure: true,      // Apenas HTTPS
  sameSite: 'strict', // Proteção CSRF
  maxAge: 3600000    // 1 hora
});
```

**Importante:** Cookies `HttpOnly` só podem ser definidos pelo servidor, **nunca pelo cliente**. Isso é uma característica de segurança, não uma limitação.[^30]

***

### 3.8 — Contorno de Restrições de Conteúdo via Manipulação de Resposta (V8)

**O que aconteceu:** A lista de módulos de aulas retornava um campo `released: false` para aulas ainda não liberadas, junto com um campo de `days_wait`. O pesquisador, usando Burp Suite, interceptou a resposta do servidor e substituiu `released: false` por `released: true` antes que chegasse ao navegador. O cliente aceitou a resposta modificada e liberou o acesso às aulas bloqueadas.

**Por que é perigoso:** Mais uma vez, a lógica de negócio estava implementada apenas no cliente. O servidor fornecia conteúdo bloqueado sem verificar se o usuário tinha direito de acessá-lo, delegando essa decisão ao frontend.[^19]

**Classificação:** OWASP API5:2023 — *Broken Function Level Authorization*.[^6]

**Mitigações obrigatórias:**
- A verificação de acesso a conteúdo **nunca deve ser baseada em campos retornados na listagem**. O servidor deve verificar, no endpoint de streaming/download do vídeo, se o usuário tem direito de acesso àquele conteúdo específico:

```javascript
// ✅ CORRETO: Verificação no servidor ao servir o conteúdo
app.get('/api/lessons/:lessonId/stream', authenticate, async (req, res) => {
  const lesson = await Lesson.findById(req.params.lessonId);
  const enrollment = await Enrollment.findOne({ userId: req.user.id });

  // Verificar se a aula foi liberada E se o usuário está inscrito
  if (!lesson.released || !enrollment || enrollment.createdAt > lesson.releaseDate) {
    return res.status(403).json({ error: 'Conteúdo não disponível' });
  }

  // Servir o conteúdo apenas se todas as verificações passaram
  streamVideo(lesson.videoUrl, res);
});
```

***

## 4. Mapeamento OWASP API Security Top 10 2023

O OWASP API Security Top 10 2023 é o framework de referência para segurança de APIs. Todas as vulnerabilidades encontradas no caso analisado se mapeiam diretamente nesse framework:[^6]

| Rank OWASP | Categoria | Presente no Caso? | Vulnerabilidades |
|------------|-----------|---------------------|-----------------|
| API1:2023 | Broken Object Level Authorization | Parcialmente | Acesso a registros de outros usuários via endpoint sem RLS |
| API2:2023 | Broken Authentication | ✅ Sim | Cookie sem HttpOnly/Secure (V7) |
| API3:2023 | Broken Object Property Level Authorization | ✅ Sim | PII retornada desnecessariamente (V3) |
| API4:2023 | Unrestricted Resource Consumption | — | Não identificado |
| API5:2023 | Broken Function Level Authorization | ✅ Sim | Escalada de privilégio (V5), bypass de conteúdo (V8) |
| API6:2023 | Unrestricted Access to Sensitive Business Flows | — | Não identificado |
| API7:2023 | Server Side Request Forgery | — | Não identificado |
| API8:2023 | Security Misconfiguration | ✅ Sim | RLS desabilitado (V2), Stored XSS (V6) |
| API9:2023 | Improper Inventory Management | ✅ Sim | Subdomínios e endpoints expostos (V1) |
| API10:2023 | Unsafe Consumption of APIs | — | Não identificado |

Das 10 categorias do OWASP API Security Top 10 2023, **6 foram identificadas** em uma única plataforma comercial com investimento significativo. Vale notar a observação do pesquisador: *"De 30 rotas, o admin acessa umas cinco. De 100 rotas, eu encontrei uma que vazava os dados. O desenvolvedor tem que se preocupar em proteger TODAS as rotas; o atacante precisa encontrar brecha em pelo menos UMA."*[^6]

***

## 5. Princípios Fundamentais de Segurança para Vibe Coding

### 5.1 — Regra de Ouro: Nunca Confie no Cliente

Este é o princípio que, se respeitado, teria eliminado as vulnerabilidades V5 e V8 diretamente:

> **Todo e qualquer dado ou parâmetro enviado pelo cliente pode ser forjado. Toda verificação de segurança (autenticação, autorização, validação de dados de negócio) deve ocorrer exclusivamente no servidor.**

O cliente (navegador, app mobile) é um ambiente hostil e não confiável por definição. Renderização condicional de elementos de UI baseada em roles é uma melhoria de UX, nunca um controle de segurança.[^18][^21]

### 5.2 — Checklist de Segurança para Prompts de IA

Ao usar ferramentas de vibe coding como Claude, Cursor ou Copilot, incluir estas instruções explícitas em cada sessão de desenvolvimento:

**Para autenticação e autorização:**
- "Implemente verificação de autorização no middleware do servidor para cada rota protegida. Nunca dependa apenas de flags do cliente."
- "O role do usuário deve ser derivado do JWT verificado pelo servidor, nunca de parâmetros enviados pelo cliente."
- "Todos os cookies de sessão devem ter as flags HttpOnly, Secure e SameSite=Strict."

**Para Supabase especificamente:**
- "Habilite RLS em TODAS as tabelas criadas. Escreva políticas explícitas para cada tabela antes de qualquer outra coisa."
- "NUNCA inclua a service_role key no código cliente."
- "Valide RLS como anon user após cada mudança de schema."

**Para APIs:**
- "Cada endpoint deve retornar apenas os campos necessários para seu propósito. Defina DTOs explícitos para as respostas."
- "Implemente rate limiting em todos os endpoints públicos."
- "Sanitize todo HTML inserido por usuário com DOMPurify antes de persistir."

**Para configuração de segurança:**
- "Implemente um header Content-Security-Policy restritivo."
- "Nunca exponha nomes de rotas administrativas no bundle JavaScript do cliente."

### 5.3 — Degradação de Segurança Iterativa

Como demonstrado pela pesquisa do Georgia Tech, código gerado por IA fica mais vulnerável a cada revisão. Para mitigar isso:[^2]

1. **Estabelecer um baseline de segurança** no início do projeto com regras inegociáveis (RLS sempre ativo, autorização sempre server-side, etc.).
2. **Revisar segurança após cada bloco de features**, não apenas ao final do projeto.
3. **Usar ferramentas de SAST** (análise estática) automatizadas no CI/CD para detectar regressões de segurança: Semgrep, Snyk, CodeQL.[^13]
4. **Incluir testes de autorização** na suíte de testes automatizados: testar que rotas admin retornam 403 para usuários sem privilégio.

***

## 6. Implicações Legais — LGPD

Para desenvolvedores e empresas brasileiras, o vazamento de dados pessoais como CPF, e-mail, telefone e nome — conforme ocorreu na plataforma analisada — tem implicações jurídicas sérias sob a **Lei Geral de Proteção de Dados (Lei 13.709/2018)**.[^9]

A ANPD (Autoridade Nacional de Proteção de Dados) está ativamente aplicando sanções desde agosto de 2021. As penalidades incluem:[^10][^31][^9]

- **Multa simples**: até 2% do faturamento, limitada a **R$ 50 milhões por infração**
- **Multa diária**: aplicável até a correção da violação
- **Publicação do incidente**: dano reputacional potencialmente mais grave que a multa financeira[^31]
- **Bloqueio ou exclusão forçada dos dados**
- **Suspensão das atividades de tratamento de dados**

Dados como CPF são considerados **identificadores diretos** sob a LGPD e exigem proteção especial. A ausência de controles técnicos adequados (como RLS no banco de dados) é explicitamente classificada como infração ao artigo 49 da LGPD, que exige que sistemas utilizem "padrões de boa prática e governança".[^32][^33]

**Obrigações práticas:**
- Implementar um **Data Protection by Design**: segurança embutida desde o início, não adicionada depois.[^34]
- Nomear um **DPO (Data Protection Officer)** ou responsável pelo tratamento de dados.[^34]
- Manter um **Registro de Operações de Tratamento (ROPA)** documentado.[^10]
- Notificar a ANPD em caso de incidente de segurança em "prazo razoável".[^33]

***

## 7. Checklist Final de Segurança para o Projeto

Use esta lista como prompt de instrução para o Claude (ou ferramenta de IA utilizada) no início de cada sessão de desenvolvimento:

### Autenticação e Sessão
- [ ] Cookies de sessão com HttpOnly + Secure + SameSite=Strict
- [ ] JWT verificado exclusivamente no servidor; role nunca vem do cliente
- [ ] MFA disponível para contas privilegiadas
- [ ] Rate limiting em endpoints de login (máx. N tentativas por IP/hora)
- [ ] Sessões invalidadas no logout (server-side)

### Autorização
- [ ] Middleware de autorização em TODAS as rotas protegidas
- [ ] Verificação de RBAC no servidor, nunca no cliente
- [ ] Princípio do menor privilégio aplicado a todas as roles
- [ ] Testes automatizados de autorização (403 para roles incorretas)

### Banco de Dados (Supabase)
- [ ] RLS habilitado em TODAS as tabelas públicas
- [ ] Políticas RLS escritas imediatamente após criar cada tabela
- [ ] Service role key NUNCA no código cliente
- [ ] Políticas testadas como usuário anônimo e autenticado

### APIs e Dados
- [ ] DTOs definidos: cada endpoint retorna apenas campos necessários
- [ ] CPF, senha, tokens e outros dados sensíveis NUNCA em respostas de listagem
- [ ] Sanitização de todo HTML com DOMPurify antes de persistir
- [ ] Rate limiting em endpoints públicos

### Frontend e Headers
- [ ] Content-Security-Policy restritivo configurado
- [ ] Sem rotas admin, IDs de banco ou secrets no bundle JS
- [ ] X-Content-Type-Options: nosniff
- [ ] HSTS habilitado em produção (Strict-Transport-Security)

### Infraestrutura
- [ ] Subdomínios de staging/admin protegidos por autenticação ou IP allowlist
- [ ] Auditoria periódica de surface de ataque (Shodan, Censys)
- [ ] SAST automatizado no CI/CD (Semgrep ou Snyk)
- [ ] Política de responsible disclosure para pesquisadores de segurança

***

## 8. Conclusão

O caso analisado demonstra que vulnerabilidades críticas de segurança podem surgir mesmo em plataformas com investimento financeiro substancial, desenvolvidas por equipes profissionais. A boa notícia é que o pesquisador agiu de forma ética, reportou responsavelmente todas as falhas e elas foram corrigidas sem impacto real aos usuários. A mensagem central permanece: **o atacante precisa encontrar apenas uma brecha; o desenvolvedor precisa proteger todas.**[^2]

No contexto de vibe coding, onde IA gera código em alta velocidade, o risco de introduzir essas falhas inadvertidamente é estruturalmente elevado. A mitigação não é evitar o uso de IA, mas sim estabelecer guardrails de segurança explícitos, imutáveis e verificáveis desde o início do projeto. As práticas documentadas neste relatório — especialmente a regra de ouro de autorização server-side, configuração obrigatória de RLS, sanitização de HTML e gestão adequada de cookies — são o conjunto mínimo de controles que qualquer software em produção deve implementar.[^1][^2]

---

## References

1. [Researchers Sound the Alarm on Vulnerabilities in AI-Generated ...](https://www.infosecurity-magazine.com/news/ai-generated-code-vulnerabilities/) - Vibe coding tools like Anthropic's Claude Code are flooding software with new vulnerabilities, Georg...

2. [Security risks of vibe coding and LLM assistants for developers](https://www.kaspersky.com/blog/vibe-coding-2025-risks/54584/) - How AI-generated code is changing cybersecurity — and what developers and “vibe coders” should expec...

3. [Gobuster](https://hackviser.com/tactics/tools/gobuster) - DNS Subdomain Enumeration: The tool can perform DNS subdomain enumeration to discover subdomains ass...

4. [Subdomain enumeration: expand attack surfaces with active, passive ...](https://www.yeswehack.com/learn-bug-bounty/subdomain-enumeration-expand-attack-surface) - Subdomain enumeration is a technique for collecting subdomains from a domain owned by the program yo...

5. [Subdomain Enumeration: Definition & Security Context](https://pentesterlab.com/glossary/subdomain-enumeration) - Subdomain Enumeration is the process of discovering subdomains belonging to a target domain during r...

6. [OWASP Top 10 API Security Risks 2023 - CloudDefense.AI](https://www.clouddefense.ai/owasp/2023) - Discover the most prevalent API security risks for 2023, including broken authentication, misconfigu...

7. [Supabase Security Best Practices - Complete Guide - SupaExplorer](https://supaexplorer.com/guides/supabase-security-best-practices) - Comprehensive guide to securing your Supabase application. Learn RLS best practices, API key managem...

8. [Top 5 Ways To Protect Against Data Exposure - Traceable](https://www.traceable.ai/blog-post/top-5-ways-to-protect-against-data-exposure) - 1. Stop Clients from Performing Data Filtering · 2. Minimize Return Responses · 3. Use Careful API D...

9. [Assessing Sanctions for Violations of Personal Data Protection ...](https://www.gtlawyers.com.br/en/noticia/assessing-sanctions-of-personal-data-violations-in-brazil-and-the-european-union-how-much-will-it-cost/) - Under the LGPD, fines may be up to 2% of the revenue of the company, group, or conglomerate earned i...

10. [Fines for infringing the General Personal Data Protection Law ...](https://ids.org.br/personal-data-protection-fines-for-infringing-the-general-personal-data-protection-law-lgpd-will-start-to-be-applied-in-brazil/) - The administrative penalties are set forth in Articles 52 and 53 of the LGPD, and range from a warni...

11. [Securing APIs: 10 Best Practices for Keeping Your Data and ... - F5](https://www.f5.com/labs/articles/securing-apis-10-best-practices-for-keeping-your-data-and-infrastructure-safe) - Validate and sanitize all data in API requests; limit response data to avoid unintentionally leaking...

12. [The 3 Best Practices for Preventing Data Leaks - PII Tools](https://pii-tools.com/the-3-best-practices-for-preventing-data-leaks/) - The first, and possibly most important, step of data leak prevention is performing regular, in-house...

13. [Broken Access Control: The #1 Security Risk in OWASP Top 10](https://sixthsense.rakuten.com/api-security/blog/broken-access-control-owasp-top-10) - Broken access control isn't just a technical flaw, it is a serious business threat. Left unresolved,...

14. [Phishing and Social Engineering Explained - YouTube](https://www.youtube.com/watch?v=xNJzaL17Ges) - Learn everything about Phishing and Social Engineering - the most dangerous human-targeted cyber att...

15. [OWASP Top 10 API security risks: Broken authentication](https://pt.blog.barracuda.com/2023/04/28/owasp-top-10-api-security-risks-broken-authentication) - Number two on the draft list of the Open Worldwide Application Security Project® (OWASP) Top 10 API ...

16. [Access control vulnerabilities and privilege escalation | Web Security ...](https://portswigger.net/web-security/access-control) - At its most basic, vertical privilege escalation arises where an application does not enforce any pr...

17. [Testing for Privilege Escalation](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/05-Authorization_Testing/03-Testing_for_Privilege_Escalation) - Privilege escalation occurs when a user gets access to more resources or functionality than they are...

18. [Privilege Escalation: how it can affect Application Security](https://blog.convisoappsec.com/privilege-escalation-how-it-can-affect-application-security/) - This type of exploit happens when a user can access other users' roles at their same level of privil...

19. [How to Prevent Response Manipulation with Burp Suite - LinkedIn](https://www.linkedin.com/posts/odepe-ali-647377225_response-manipulation-with-burp-suite-why-activity-7363733675231883265-0MIG) - Response Manipulation with Burp Suite: Why It Matters & How to Prevent It; Burp Suite lets you sit b...

20. [5 Common Privilege Escalation Attack Techniques with Examples](https://www.proofpoint.com/au/blog/identity-threat-defense/privilege-escalation-attack) - Tips to prevent privilege escalation techniques and attacks · Use MFA. · Implement privileged access...

21. [CVE-2025-14750: Privilege Escalation Vulnerability](https://www.sentinelone.com/vulnerability-database/cve-2025-14750/) - Low-privileged users can manipulate assumed-immutable parameters to escalate privileges and gain una...

22. [What is Privilege Escalation | Prevention Techniques](https://www.imperva.com/learn/data-security/privilege-escalation/) - A privilege escalation attack is a type of network intrusion that exploits system vulnerabilities to...

23. [Prevent Cross-Site Scripting (XSS) Attacks - LinkedIn](https://www.linkedin.com/pulse/safeguard-your-app-from-cross-site-scripting-xss-attack-sharma-ojq2c) - Stored XSS: The malicious script is permanently stored on the server. DOM-based XSS: The malicious s...

24. [How to Use Content Security Policy (CSP) to Prevent XSS Attacks](https://whatis.eokultv.com/wiki/679493-how-to-use-content-security-policy-csp-to-prevent-xss-attacks) - Want to master Content Security Policy (CSP)? Dive into our expert guide with clear examples and bes...

25. [A Guide to Content Security Policy (CSP) - CipherSend](https://ciphersend.link/knowledge-base/a-guide-to-content-security-policy-csp) - A strict CSP protects against classical stored, reflected, and some DOM-based XSS attacks and is the...

26. [Setting up a content security policy (CSP) - YouTube](https://www.youtube.com/watch?v=oyScLJH9sTs) - Content Security Policy, web security headers, XSS prevention, and protection from XSS attacks are e...

27. [The Power of httpOnly Cookies for Secure JWT Authentication](https://www.linkedin.com/pulse/power-httponly-cookies-secure-jwt-authentication-rajesh-kanna-ana3e) - By setting this flag when setting cookies (such as your JWT), you ensure that the cookie cannot be a...

28. [Secure JWT Storage: Best Practices | Syncfusion Blogs](https://www.syncfusion.com/blogs/post/secure-jwt-storage-best-practices) - Secure methods for storing JWTs include using HttpOnly cookies with the Secure flag, encrypting JWTs...

29. [JWT Authentication with HttpOnly Cookies - Crypto Shop Backend](https://www.mintlify.com/peLuis123/crypto-shop-backend/security/jwt-cookies) - Always use HTTPS in production. The secure flag will prevent cookies from being sent over unencrypte...

30. [Storing Jwt Token in Cookie with Http and Secure instead of ...](https://stackoverflow.com/questions/52829514/storing-jwt-token-in-cookie-with-http-and-secure-instead-of-localstorage-in-java) - You can't set a HttpOnly cookie from client end code (like Javascript). As such cookies are meant no...

31. [Fines in LGPD - What are they, amounts, and compliance deadlines](https://goadopt.io/en/blog/fines-in-LGPD/) - The maximum limit for fines under the LGPD is 50 million Brazilian reais. However, some of the penal...

32. [Brazilian Data Protection Authority applies the second penalty for ...](https://www.kasznarleonardos.com/en/brazilian-data-protection-authority-applies-the-second-penalty-for-non-compliance-with-lgpd/) - Brazilian Data Protection Authority applies the second penalty for non-compliance with LGPD. Three m...

33. [LGPD - Brazil's data protection law explained - Cookie Information](https://cookieinformation.com/regulations/lgpd/) - Penalties under the GDPR can reach up to 4% of global revenue or €20 million, whichever is higher. T...

34. [The General Data Protection Act (LGPD) in Brazil: “the Brazilian ...](https://intellectual-property-helpdesk.ec.europa.eu/news-events/news/general-data-protection-act-lgpd-brazil-brazilian-gdpr-2021-09-30_en) - The Brazilian LGPD imposes fines of up to 2% of a company's global revenue, or 50 million reals (app...

