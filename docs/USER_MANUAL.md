# CaseHub -- User Manual / Manual do Usuario

> **Version 2.0** | Last updated: 2026-03-25

This manual covers both CaseHub products:

- **CaseHub Immigration** (English) -- For U.S. immigration law firms handling visa petitions, USCIS tracking, and naturalization cases.
- **CaseHub Lite** (Portugues) -- Para escritorios de advocacia brasileiros que gerenciam processos civeis, trabalhistas, penais e de outras areas.

Each section is presented in **both English and Portuguese**. Language is kept simple -- this manual is written for lawyers and staff, not developers.

---

## Table of Contents / Sumario

1. [Getting Started / Primeiros Passos](#1-getting-started--primeiros-passos)
2. [Dashboard / Painel](#2-dashboard--painel)
3. [Clients / Clientes](#3-clients--clientes)
4. [Cases / Processos](#4-cases--processos)
5. [Documents / Documentos](#5-documents--documentos)
6. [Tasks & Calendar / Tarefas & Calendario](#6-tasks--calendar--tarefas--calendario)
7. [Billing & Invoices / Financeiro & Faturas](#7-billing--invoices--financeiro--faturas)
8. [Email](#8-email)
9. [Leads CRM](#9-leads-crm)
10. [Settings & Administration / Configuracoes & Administracao](#10-settings--administration--configuracoes--administracao)
11. [Tips & Tricks / Dicas Uteis](#11-tips--tricks--dicas-uteis)

---

# 1. Getting Started / Primeiros Passos

## EN: First Login

1. Open CaseHub in your browser. You will see the login screen with your organization's logo (or the default scales-of-justice icon).
2. Enter the **email** and **password** provided by your administrator.
3. Click **Login**.
4. **First-time users**: A modal window will appear asking you to change your password. This is mandatory.
   - Enter your current (temporary) password.
   - Choose a new password (minimum 8 characters).
   - Confirm the new password.
   - Click **Alterar Senha** (Change Password).
5. After login, you will see the Dashboard. A welcome toast will confirm you are logged in.

**Forgot your password?** Click the "Forgot your password?" link below the Login button.

## PT-BR: Primeiro Acesso

1. Abra o CaseHub no seu navegador. Voce vera a tela de login com o logo do seu escritorio (ou o icone padrao de balanca).
2. Digite o **email** e a **senha** fornecidos pelo administrador.
3. Clique em **Login**.
4. **Primeiro acesso**: Uma janela modal aparecera pedindo para alterar sua senha. Isso e obrigatorio.
   - Digite a senha atual (temporaria).
   - Escolha uma nova senha (minimo 8 caracteres).
   - Confirme a nova senha.
   - Clique em **Alterar Senha**.
5. Apos o login, voce vera o Dashboard. Um aviso de boas-vindas confirmara que voce esta logado.

**Esqueceu a senha?** Clique em "Forgot your password?" abaixo do botao de Login.

---

## EN: Dark/Light Mode

- In the **top bar** (upper-right corner), click the **sun/moon icon** to toggle between light and dark themes.
- Your preference is saved in your browser and persists across sessions.

## PT-BR: Modo Claro/Escuro

- Na **barra superior** (canto superior direito), clique no **icone de sol/lua** para alternar entre tema claro e escuro.
- Sua preferencia e salva no navegador e persiste entre sessoes.

---

## EN: Language Switching

- In the top bar, you will see two flag icons: the Brazilian flag and the American flag.
- Click the **Brazilian flag** for Portuguese (PT-BR).
- Click the **American flag** for English (EN).
- The interface labels, menus, and buttons will update accordingly.

## PT-BR: Trocar Idioma

- Na barra superior, voce vera duas bandeiras: Brasil e EUA.
- Clique na **bandeira do Brasil** para Portugues (PT-BR).
- Clique na **bandeira dos EUA** para Ingles (EN).
- Os menus, botoes e rotulos da interface serao atualizados.

---

## EN: Sidebar Navigation

The left sidebar is your main navigation. It is organized into sections:

**Main Section:**
- **Dashboard** -- Overview and statistics
- **Clients** -- Client management
- **Documents** -- Document management
- **File Manager** -- Browse files by folder
- **Tasks** -- Task tracking (list and kanban)
- **Calendar** -- Calendar view
- **Emails** -- Email inbox and compose
- **Leads CRM** -- Lead tracking and pipeline

**Juridico Section** (collapsible):
- **Cases** -- Case management
- **Tools** -- Utility tools
- **Client Intakes** -- Intake forms
- **Checklists** -- Document checklists
- **LOR Maker** -- Letter of recommendation builder (Immigration)
- **PS Maker** -- Personal statement builder (Immigration)
- **Package Maker** -- Filing package builder (Immigration)
- **Processes** -- Process tracking (Lite)
- **Letters** -- Letter templates
- **Questionnaires** -- Client questionnaires
- **Custom Fields** -- Define custom data fields
- **USCIS** -- USCIS status tracking (Immigration)

**Admin Section** (collapsible):
- **Webhooks** -- Integration webhooks
- **Communications** -- Communication center
- **Reports** -- Reports and analytics
- **WhatsApp Chat** -- WhatsApp integration
- **Billing** -- Billing dashboard
- **Notifications** -- Notification center
- **Admin** -- Administration panel (admin users only)

On mobile, tap the **hamburger menu** (three lines) to open the sidebar. Tap outside the sidebar to close it.

## PT-BR: Navegacao pela Barra Lateral

A barra lateral esquerda e sua navegacao principal. Ela e organizada em secoes:

**Secao Principal:**
- **Dashboard** -- Visao geral e estatisticas
- **Clientes** -- Gestao de clientes
- **Documentos** -- Gestao de documentos
- **File Manager** -- Navegar arquivos por pasta
- **Tarefas** -- Acompanhamento de tarefas (lista e kanban)
- **Calendario** -- Visualizacao do calendario
- **Emails** -- Caixa de entrada e composicao
- **Leads CRM** -- Acompanhamento de leads

**Secao Juridico** (recolhivel):
- **Casos** -- Gestao de casos/processos
- **Tools** -- Ferramentas utilitarias
- **Client Intakes** -- Formularios de admissao
- **Checklists** -- Checklists de documentos
- **Processos** -- Acompanhamento de processos (Lite)
- **Letras** -- Modelos de cartas
- **Questionarios** -- Questionarios para clientes
- **Campos Personalizados** -- Definir campos de dados customizados

**Secao Admin** (recolhivel):
- **Webhooks** -- Webhooks de integracao
- **Comunicacoes** -- Central de comunicacao
- **Relatorios** -- Relatorios e analiticos
- **WhatsApp Chat** -- Integracao com WhatsApp
- **Financeiro** -- Painel financeiro
- **Notificacoes** -- Central de notificacoes
- **Admin** -- Painel de administracao (apenas administradores)

No celular, toque no **menu hamburguer** (tres linhas) para abrir a barra lateral. Toque fora para fechar.

---

# 2. Dashboard / Painel

## EN: Dashboard Overview

The Dashboard is the first screen after login. It provides:

- **WhatsApp Bot Control** (admin only): Toggle the WhatsApp bot on/off, enable/disable business hours mode, and see the current BRT time.
- **World Clock Map**: An interactive world map showing current time in New York, Sao Paulo, London, and Tokyo. Hover over any country to see its local time.
- **Statistics Cards**: Quick counts of clients, cases, tasks, and other key metrics.

## PT-BR: Visao Geral do Dashboard

O Dashboard e a primeira tela apos o login. Ele oferece:

- **Controle do Bot WhatsApp** (apenas admin): Ligar/desligar o bot do WhatsApp, ativar/desativar modo horario comercial, e ver a hora atual BRT.
- **Mapa com Relogios Mundiais**: Um mapa interativo mostrando a hora atual em Nova York, Sao Paulo, Londres e Toquio. Passe o mouse sobre qualquer pais para ver o horario local.
- **Cartoes de Estatisticas**: Contagens rapidas de clientes, casos, tarefas e outras metricas.

---

# 3. Clients / Clientes

## EN: Managing Clients

### Viewing Clients

- Click **Clients** in the sidebar.
- You will see a table with all clients, showing: Name, Email, Phone, A# (Alien Number), Status, Country, and Created date.
- The header shows the total count of clients.

### Searching and Filtering

- Use the **search box** to search by name, email, or A# (alien number).
- Use the **Status dropdown** to filter by: Lead, Prospect, Active, Approved, Denied, or Closed.
- Click **Filter** to apply.

### Adding a New Client

1. Click the **+ New Client** button (top right).
2. Fill in the form, which has two sections:

**Personal Information:**
- First Name (required)
- Last Name (required)
- Email
- Phone
- WhatsApp number
- Date of Birth
- Country of Origin
- Address

**Immigration Information** (Immigration product):
- Alien Number (A#)
- Passport Number
- SSN

**Status & Notes:**
- Status: Lead, Prospect, Active, Approved, Denied, Closed
- Notes (free text)

3. Click **Save** at the bottom.

### Client Profile

Click any client row to open their profile. The detail page shows:

- **Personal Information** card with all contact details
- **Immigration Information** card (A#, passport, SSN)
- **Portal Access** button -- Grant the client access to the self-service portal and send them an email invitation.
- **Open Drive Folder** -- Open the client's Google Drive folder directly.
- **Edit** and **Delete** buttons
- **WhatsApp Bot toggle** -- Enable or disable the bot for this client's phone number.
- Related cases, documents, tasks, and notes for this client.

### Client Types (Lite)

For CaseHub Lite (Brazilian law firms):
- **Pessoa Fisica** -- Individual clients (CPF)
- **Pessoa Juridica** -- Company clients (CNPJ)

## PT-BR: Gerenciando Clientes

### Visualizando Clientes

- Clique em **Clientes** na barra lateral.
- Voce vera uma tabela com todos os clientes: Nome, Email, Telefone, A# (Alien Number), Status, Pais e Data de Criacao.
- O cabecalho mostra a contagem total de clientes.

### Buscando e Filtrando

- Use a **caixa de busca** para pesquisar por nome, email ou A#.
- Use o **dropdown de Status** para filtrar: Lead, Prospect, Ativo, Aprovado, Negado ou Encerrado.
- Clique em **Filter** para aplicar.

### Adicionando um Novo Cliente

1. Clique no botao **+ New Client** (canto superior direito).
2. Preencha o formulario com as secoes:

**Informacoes Pessoais:**
- Nome (obrigatorio)
- Sobrenome (obrigatorio)
- Email
- Telefone
- WhatsApp
- Data de Nascimento
- Pais de Origem
- Endereco

**Status & Notas:**
- Status: Lead, Prospect, Ativo, Aprovado, Negado, Encerrado
- Notas (texto livre)

3. Clique em **Save**.

### Perfil do Cliente

Clique em qualquer linha da tabela para abrir o perfil. A pagina de detalhes mostra:

- Cartao de **Informacoes Pessoais** com todos os dados de contato
- Botao **Portal Access** -- Conceder ao cliente acesso ao portal de autoatendimento
- Botao **Open Drive Folder** -- Abrir a pasta do Google Drive do cliente
- Botoes de **Edit** e **Delete**
- **Toggle do Bot WhatsApp** -- Ativar ou desativar o bot para o numero do cliente
- Casos, documentos, tarefas e notas relacionados

### Tipos de Cliente (Lite)

Para CaseHub Lite (escritorios brasileiros):
- **Pessoa Fisica** -- Clientes individuais (CPF)
- **Pessoa Juridica** -- Clientes empresariais (CNPJ)

---

# 4. Cases / Processos

## EN: Managing Cases

### Viewing Cases

- Click **Cases** under the Juridico section in the sidebar.
- The cases table shows: Case #, Client, Type, Status, Priority, Receipt #, and Created date.

### Searching and Filtering

- **Search**: Type any keyword to search across cases.
- **Status filter**: Intake, Document Collection, Drafting, Review, Filed, RFE, Approved, Denied.
- **Visa Type filter** (Immigration): EB-2 NIW, EB-1A, H-1B, L-1, O-1, F-1, B-1/B-2, Green Card.
- Click **Filter** to apply.

### Creating a Case

1. Click **+ New Case**.
2. Fill in the form:

**Case Information:**
- Client (required) -- Select from dropdown
- Case Number -- Auto-generated or manual
- Receipt Number -- USCIS receipt number (Immigration)
- Case Name
- Visa Type (Immigration): EB-2 NIW, EB-1A, EB-1B, H-1B, L-1A, L-1B, O-1A, O-1B, J-1, F-1 OPT, F-1 STEM OPT, B-1/B-2, Green Card, I-485 AOS, I-140, I-130, Naturalization

**Status & Priority:**
- Status: Intake, Document Collection, Drafting, Review, Filed, RFE, Approved, Denied, Closed
- Priority: Low, Medium, High, Urgent
- Case Value ($)

**Important Dates:**
- Filing Date
- Priority Date
- Expiration Date

3. Click **Save**.

### Case Detail Page

Click any case to view its details:

- **Case Information** card: Case number, name, receipt number, visa type, status, priority, case value.
- **Important Dates** card: Filing date, priority date, expiration date, created date. Expired dates are flagged with a red "Expired" badge.
- **Check USCIS** button (appears when a receipt number is set) -- Check the case status directly with USCIS.
- **Document Checklist** button -- View and manage the required documents for this case.
- **Edit** and **Delete** buttons.

### Case Workflow (Status Progression)

A typical immigration case moves through these stages:

1. **Intake** -- Client onboarded, initial consultation
2. **Document Collection** -- Gathering required documents from client
3. **Drafting** -- Preparing the petition and supporting documents
4. **Review** -- Attorney review before filing
5. **Filed** -- Petition submitted to USCIS
6. **RFE** -- Request for Evidence received (requires response)
7. **Approved** or **Denied** -- Final decision
8. **Closed** -- Case archived

### Immigration-Specific: USCIS Tracking

- Navigate to **USCIS** in the sidebar to check case statuses with USCIS.
- From a case detail page, click **Check USCIS** to query the status using the receipt number.
- RFE (Request for Evidence) cases are highlighted in yellow for visibility.

### Lite-Specific: Brazilian Process Tracking

For CaseHub Lite, cases use Brazilian legal terminology:
- **Numero do Processo** -- Court case number
- **Tribunal** -- Court (e.g., TJMG, TRF)
- **Vara** -- Court division
- **Comarca** -- Judicial district

## PT-BR: Gerenciando Casos/Processos

### Visualizando Casos

- Clique em **Casos** na secao Juridico da barra lateral.
- A tabela mostra: Numero, Cliente, Tipo, Status, Prioridade, Receipt # e Data de Criacao.

### Buscando e Filtrando

- **Busca**: Digite qualquer palavra-chave.
- **Filtro de Status**: Intake, Coleta de Documentos, Elaboracao, Revisao, Protocolado, RFE, Aprovado, Negado.
- **Filtro de Tipo de Visto** (Immigration): EB-2 NIW, EB-1A, H-1B, L-1, O-1, F-1, B-1/B-2, Green Card.
- Clique em **Filter** para aplicar.

### Criando um Caso

1. Clique em **+ New Case**.
2. Preencha o formulario:

**Informacoes do Caso:**
- Cliente (obrigatorio) -- Selecionar no dropdown
- Numero do Caso
- Nome do Caso
- Valor do Caso

**Status & Prioridade:**
- Status: Intake, Coleta de Documentos, Elaboracao, Revisao, Protocolado, RFE, Aprovado, Negado, Encerrado
- Prioridade: Baixa, Media, Alta, Urgente

**Datas Importantes:**
- Data de Protocolo
- Data de Prioridade
- Data de Vencimento

3. Clique em **Save**.

### Fluxo de Trabalho do Caso

Um caso tipico passa pelas seguintes etapas:

1. **Intake** -- Cliente integrado, consulta inicial
2. **Coleta de Documentos** -- Reunindo documentos necessarios
3. **Elaboracao** -- Preparando a peticao
4. **Revisao** -- Revisao do advogado antes do protocolo
5. **Protocolado** -- Peticao submetida
6. **Aprovado** ou **Negado** -- Decisao final
7. **Encerrado** -- Caso arquivado

### Lite: Acompanhamento de Processos Brasileiros

Para CaseHub Lite, os casos usam terminologia juridica brasileira:
- **Numero do Processo** -- Numero do processo judicial
- **Tribunal** -- Tribunal (ex: TJMG, TRF)
- **Vara** -- Vara judicial
- **Comarca** -- Comarca

---

# 5. Documents / Documentos

## EN: Document Management

### Viewing Documents

- Click **Documents** in the sidebar.
- You can switch between three view modes using the buttons at the top:
  - **List** -- Table view (default)
  - **Grid** -- Card/thumbnail view
  - **Tree** -- Organized by client

### Google Drive Sync

- An info banner at the top shows the sync status: **Google Drive <-> CaseHub** -- synchronized every 15 minutes.
- Documents uploaded to Google Drive automatically appear in CaseHub, and vice versa.

### Searching and Filtering

- **Search box**: Search by document name or keywords.
- **Document Type filter**: Passaporte, Resume, LOR, Diploma, Tax, Photo, USCIS Form, Outro.
- **Status filter**: Aprovado (Approved), Pendente (Pending Review), Novo (Uploaded), Rejeitado (Rejected).
- **Per page**: Show 50, 100, or 200 documents per page.

### Uploading Documents

1. Click the **Upload** button (top right).
2. Select the file(s) from your computer.
3. Choose the client and case to associate with.
4. Select a document type/category.
5. Click **Upload**.

Alternatively, use the **Upload Local** button to upload files from your local storage.

### Document Workflow States

Each document has a workflow state:
- **Novo (Uploaded)** -- Just uploaded, not yet reviewed
- **Pendente (Pending Review)** -- Awaiting attorney review
- **Aprovado (Approved)** -- Document reviewed and accepted
- **Rejeitado (Rejected)** -- Document needs to be replaced or corrected

### Bulk Operations

- Select multiple documents using checkboxes.
- A bulk action bar appears at the top showing the count of selected items.
- **Bulk Delete** -- Delete multiple documents at once.

### Client Portal

Clients with portal access can upload documents directly. When a client uploads a document, it appears with the "Novo" (Uploaded) status for your review.

## PT-BR: Gestao de Documentos

### Visualizando Documentos

- Clique em **Documentos** na barra lateral.
- Voce pode alternar entre tres modos de visualizacao:
  - **Lista** -- Visualizacao em tabela (padrao)
  - **Grid** -- Visualizacao em cartoes/miniaturas
  - **Arvore** -- Organizado por cliente

### Sincronizacao com Google Drive

- Um banner informativo no topo mostra o status da sincronizacao: **Google Drive <-> CaseHub** -- sincronizado a cada 15 minutos.
- Documentos enviados ao Google Drive aparecem automaticamente no CaseHub e vice-versa.

### Buscando e Filtrando

- **Caixa de busca**: Pesquise por nome ou palavras-chave.
- **Filtro de Tipo**: Passaporte, Resume, LOR, Diploma, Tax, Photo, USCIS Form, Outro.
- **Filtro de Status**: Aprovado, Pendente, Novo, Rejeitado.
- **Por pagina**: Exibir 50, 100 ou 200 documentos por pagina.

### Enviando Documentos

1. Clique no botao **Upload** (canto superior direito).
2. Selecione o(s) arquivo(s) do seu computador.
3. Escolha o cliente e o caso para associar.
4. Selecione um tipo/categoria de documento.
5. Clique em **Upload**.

Use o botao **Upload Local** para enviar arquivos do armazenamento local.

### Estados do Workflow de Documentos

Cada documento tem um estado:
- **Novo (Uploaded)** -- Recem-enviado, ainda nao revisado
- **Pendente (Pending Review)** -- Aguardando revisao do advogado
- **Aprovado (Approved)** -- Documento revisado e aceito
- **Rejeitado (Rejected)** -- Documento precisa ser substituido ou corrigido

### Operacoes em Massa

- Selecione multiplos documentos usando as caixas de selecao.
- Uma barra de acoes em massa aparece no topo mostrando a contagem.
- **Deletar em massa** -- Excluir multiplos documentos de uma vez.

### Portal do Cliente

Clientes com acesso ao portal podem enviar documentos diretamente. Quando um cliente envia um documento, ele aparece com status "Novo" para sua revisao.

---

# 6. Tasks & Calendar / Tarefas & Calendario

## EN: Task Management

### Viewing Tasks

- Click **Tasks** in the sidebar.
- The task page shows four summary cards at the top:
  - **Overdue** (red) -- Tasks past their due date
  - **Due Today** (yellow) -- Tasks due today
  - **Total Active** (blue) -- All active tasks
  - **Show Completed** -- Link to view completed tasks

### List vs. Kanban View

- **List view** (default): A table showing Task, Client/Case, Due Date, Priority, and Status.
- **Kanban view**: A drag-and-drop board with columns for each status (Pending, In Progress, Completed, Blocked). Click the **Kanban** button at the top to switch.

### Task Sources

CaseHub supports two task sources, shown as tabs:
- **Notion Tasks** -- Tasks synced from Notion (for teams using Notion).
- **Tasks Locais (Local Tasks)** -- Tasks created directly in CaseHub.

### Creating a Task

1. Click **+ New Task**.
2. Fill in the form:

**Task Details:**
- Title (required)
- Description
- Task Type: Document Collection, Form Preparation, Review, Filing, Follow-up, Communication, Meeting, Reminder, Other
- Assigned To -- Select a team member

**Status & Priority:**
- Status: Pending, In Progress, Completed, Blocked
- Priority: Low, Medium, High, Urgent

**Dates:**
- Due Date

**Linking:**
- Link to a Client and/or Case

3. Click **Save**.

### Calendar

- Click **Calendar** in the sidebar to see tasks and deadlines in a calendar view.
- Google Calendar integration is available under Calendar settings.

### Reminders and Deadlines

- Tasks with due dates appear in the calendar.
- Overdue tasks are highlighted in red on the task list.
- The notification bell in the top bar shows alerts for upcoming deadlines.

### Lite: Prazos Processuais

For CaseHub Lite, task types include court deadlines (prazos processuais). Set due dates carefully to track filing deadlines, hearings, and response periods.

## PT-BR: Gestao de Tarefas

### Visualizando Tarefas

- Clique em **Tarefas** na barra lateral.
- A pagina mostra quatro cartoes resumo no topo:
  - **Atrasadas** (vermelho) -- Tarefas com prazo vencido
  - **Vencem Hoje** (amarelo) -- Tarefas que vencem hoje
  - **Total Ativas** (azul) -- Todas as tarefas ativas
  - **Mostrar Concluidas** -- Link para ver tarefas concluidas

### Visualizacao em Lista vs. Kanban

- **Lista** (padrao): Tabela com Tarefa, Cliente/Caso, Data de Vencimento, Prioridade e Status.
- **Kanban**: Quadro com colunas para cada status (Pendente, Em Progresso, Concluida, Bloqueada). Clique em **Kanban** para alternar.

### Criando uma Tarefa

1. Clique em **+ New Task**.
2. Preencha o formulario:

**Detalhes da Tarefa:**
- Titulo (obrigatorio)
- Descricao
- Tipo: Coleta de Documentos, Preparacao de Formulario, Revisao, Protocolo, Follow-up, Comunicacao, Reuniao, Lembrete, Outro
- Atribuir a -- Selecione um membro da equipe

**Status & Prioridade:**
- Status: Pendente, Em Progresso, Concluida, Bloqueada
- Prioridade: Baixa, Media, Alta, Urgente

**Datas:**
- Data de Vencimento

3. Clique em **Save**.

### Calendario

- Clique em **Calendario** na barra lateral para ver tarefas e prazos na visualizacao de calendario.
- Integracao com Google Calendar disponivel nas configuracoes.

### Prazos Processuais (Lite)

No CaseHub Lite, os tipos de tarefa incluem prazos processuais. Defina as datas de vencimento com cuidado para acompanhar prazos de protocolo, audiencias e periodos de resposta.

---

# 7. Billing & Invoices / Financeiro & Faturas

## EN: Billing Dashboard

Click **Billing** in the Admin section of the sidebar. The billing dashboard shows four summary cards:

- **Pending** -- Total amount of unpaid billing items
- **Paid** -- Total amount already paid
- **Payments Received** -- Total payments received
- **Billable Hours** -- Total hours logged

### Creating a Billing Item (Charge)

1. Click **+ New Charge**.
2. Select the **Case** this charge relates to.
3. Enter a **Description** of the charge.
4. Select the **Type**: Payment, Filing Fee, or Expense.
5. Enter the **Amount**.
6. Click **Save**.

### Logging Time

1. Click **Log Time** (green button).
2. Select the **Case**.
3. Describe **what you worked on**.
4. Enter the **Date**, **Hours** (in 0.25-hour increments), and optionally a **Rate** ($/hr).
5. Select the **Staff Member** (defaults to you).
6. Check **Billable** if this time should be billed.
7. Click **Save**.

### Filtering Billing Items

Use the status dropdown to filter by: All, Pending, Invoiced, or Paid.

### Creating an Invoice

1. Navigate to **Invoices** (from the billing area) and click **Create Invoice**.
2. Select the **Case**.
3. Choose which **billing items** to include (checkboxes).
4. Optionally include **time entries** with an hourly rate.
5. Set the **Due Date**.
6. Add optional **Notes**.
7. Click **Create Invoice**.

Each invoice gets an auto-generated invoice number. You can print invoices using the print view.

### Payment Recording

Record payments against invoices to track what has been collected.

### Currency

- **Immigration**: Currency is **USD** (US Dollars) by default.
- **Lite**: Currency is **BRL** (Brazilian Reais) by default.

## PT-BR: Painel Financeiro

Clique em **Financeiro** na secao Admin da barra lateral. O painel mostra quatro cartoes:

- **Pendente** -- Valor total de itens nao pagos
- **Pago** -- Valor total ja pago
- **Pagamentos Recebidos** -- Total de pagamentos recebidos
- **Horas Faturáveis** -- Total de horas registradas

### Criando uma Cobranca

1. Clique em **+ New Charge**.
2. Selecione o **Caso** ao qual esta cobranca se refere.
3. Digite uma **Descricao**.
4. Selecione o **Tipo**: Pagamento, Taxa de Protocolo ou Despesa.
5. Digite o **Valor**.
6. Clique em **Save**.

### Registrando Tempo

1. Clique em **Log Time** (botao verde).
2. Selecione o **Caso**.
3. Descreva **o que voce trabalhou**.
4. Informe a **Data**, **Horas** (em incrementos de 0,25 hora) e opcionalmente uma **Taxa** (R$/hr).
5. Selecione o **Membro da Equipe** (padrao: voce).
6. Marque **Faturavel** se esse tempo deve ser cobrado.
7. Clique em **Save**.

### Criando uma Fatura

1. Navegue ate **Invoices** e clique em **Create Invoice**.
2. Selecione o **Caso**.
3. Escolha quais **itens de cobranca** incluir (caixas de selecao).
4. Opcionalmente inclua **entradas de tempo** com uma taxa por hora.
5. Defina a **Data de Vencimento**.
6. Adicione **Notas** opcionais.
7. Clique em **Create Invoice**.

Cada fatura recebe um numero automatico. Voce pode imprimir faturas usando a visualizacao de impressao.

### Moeda

- **Immigration**: Moeda padrao e **USD** (Dolares Americanos).
- **Lite**: Moeda padrao e **BRL** (Reais Brasileiros).

---

# 8. Email

## EN: Email Management

### Viewing Emails

- Click **Emails** in the sidebar.
- The email list shows all emails in a table format with: Sender, Subject, Date, and Read/Unread status.
- **Unread emails** are shown in bold with a blue left border indicator.
- Emails are color-coded by paralegal assignment (red, yellow, blue, purple borders).

### Composing an Email

1. Click **Compose** to open the compose form.
2. Fill in:
   - **To** (required) -- Recipient email. Separate multiple addresses with commas.
   - **CC** (optional) -- CC recipients.
   - **Subject** (required)
   - **Body** -- Write your message.
3. Use **Quick Templates** to insert pre-written email templates (available in English and Portuguese).
4. Emails can be linked to a specific **Client** and/or **Case** for record-keeping.
5. Click **Send**.

### Email Accounts

- Navigate to **Emails > Accounts** to manage connected email accounts.
- SMTP configuration is required for sending emails (configured by your administrator).

### Auto-Linking

Emails sent from CaseHub are automatically linked to the relevant client and case. Incoming emails are matched based on the sender's email address.

## PT-BR: Gestao de Emails

### Visualizando Emails

- Clique em **Emails** na barra lateral.
- A lista mostra todos os emails em formato de tabela: Remetente, Assunto, Data e status Lido/Nao Lido.
- **Emails nao lidos** aparecem em negrito com um indicador azul na borda esquerda.
- Emails sao codificados por cor conforme a atribuicao do paralegal.

### Compondo um Email

1. Clique em **Compose** para abrir o formulario.
2. Preencha:
   - **Para** (obrigatorio) -- Email do destinatario. Separe multiplos enderecos com virgula.
   - **CC** (opcional) -- Destinatarios em copia.
   - **Assunto** (obrigatorio)
   - **Corpo** -- Escreva sua mensagem.
3. Use **Quick Templates** para inserir modelos pre-escritos (disponiveis em ingles e portugues).
4. Emails podem ser vinculados a um **Cliente** e/ou **Caso** especifico.
5. Clique em **Send**.

### Contas de Email

- Navegue ate **Emails > Contas** para gerenciar contas de email conectadas.
- Configuracao SMTP e necessaria para envio (feita pelo administrador).

---

# 9. Leads CRM

## EN: Lead Management

- Click **Leads CRM** in the sidebar.
- The Leads CRM provides a pipeline view for tracking potential clients from initial contact through conversion.
- Leads can come from:
  - Website intake forms
  - WhatsApp bot interactions
  - Manual entry
  - Moskit CRM integration

## PT-BR: Gestao de Leads

- Clique em **Leads CRM** na barra lateral.
- O CRM de Leads oferece uma visualizacao de pipeline para acompanhar potenciais clientes desde o primeiro contato ate a conversao.
- Leads podem vir de:
  - Formularios do site
  - Interacoes com o bot do WhatsApp
  - Entrada manual
  - Integracao com Moskit CRM

---

# 10. Settings & Administration / Configuracoes & Administracao

## EN: Settings

Click **Settings** (gear icon) in the sidebar. The settings page has cards for:

- **Auto-Numbering** -- Configure automatic numbering formats for cases and clients. Preview how numbers will look (e.g., `CASE-2026-001`).
- **Email Settings** -- Configure SMTP server, templates, and notification preferences.
- **WhatsApp** -- Configure WhatsApp integration for client messaging.
- **Backups** -- Daily backups are enabled by default.
- **Security** -- Two-factor authentication (2FA) setup and access controls.

### Administration (Admin Users Only)

Click **Admin** in the sidebar. The admin panel shows:

- **Summary Statistics**: Total Users, Clients, Cases, and Documents.
- **User Management**: View all users, add new users, edit or delete users.
- **Application Settings**: Access all system settings.
- **Branding**: Customize your organization's appearance.

### User Management

1. Go to **Admin > Manage Users**.
2. The user list shows: Name, Email, Type (admin/staff), and Status (Active/Disabled).
3. Click **+ New User** to add a staff member.
4. Click the **Edit** icon to modify a user.
5. Click the **Delete** icon to remove a user (you cannot delete yourself).

### Branding

Go to **Admin > Branding** to customize:

- **Organization Name** -- Displayed in the sidebar and login page.
- **Logo** -- Upload your firm's logo (drag-and-drop zone). Shown in the sidebar and login screen.
- **Colors** -- Choose primary and secondary brand colors. A live preview shows how the sidebar and header will look.
- **Favicon** -- Upload a custom browser tab icon.

### Notifications

- Click the **bell icon** in the top bar to see recent notifications.
- Click "Mark all read" to clear the badge count.
- Click "View all notifications" to see the full notification history.

### Reports

- Navigate to **Reports** in the sidebar.
- Reports are organized by category (e.g., Clients, Cases, Billing).
- Click any report to view it. Reports support both English and Portuguese labels.

## PT-BR: Configuracoes

Clique em **Settings** (icone de engrenagem) na barra lateral. A pagina mostra cartoes para:

- **Auto-Numeracao** -- Configure formatos automaticos de numeracao para casos e clientes. Visualize como os numeros ficam (ex: `CASO-2026-001`).
- **Config. de Email** -- Configure servidor SMTP, templates e preferencias de notificacao.
- **WhatsApp** -- Configure integracao WhatsApp para mensagens com clientes.
- **Backups** -- Backups diarios habilitados por padrao.
- **Seguranca** -- Configuracao de autenticacao em dois fatores (2FA).

### Administracao (Apenas Administradores)

Clique em **Admin** na barra lateral. O painel mostra:

- **Estatisticas Resumidas**: Total de Usuarios, Clientes, Casos e Documentos.
- **Gestao de Usuarios**: Ver todos, adicionar, editar ou excluir usuarios.
- **Configuracoes do Sistema**: Acesso a todas as configuracoes.
- **Branding**: Personalizar a aparencia do escritorio.

### Gestao de Usuarios

1. Va em **Admin > Manage Users**.
2. A lista mostra: Nome, Email, Tipo (admin/staff) e Status (Ativo/Desabilitado).
3. Clique em **+ New User** para adicionar um membro da equipe.
4. Clique no icone de **Editar** para modificar.
5. Clique no icone de **Excluir** para remover (voce nao pode excluir a si mesmo).

### Branding / Marca

Va em **Admin > Branding** para personalizar:

- **Nome da Organizacao** -- Exibido na barra lateral e na tela de login.
- **Logo** -- Envie o logo do escritorio (zona de arrastar e soltar). Aparece na barra lateral e no login.
- **Cores** -- Escolha cores pripessoa_demo e secundaria. Uma pre-visualizacao ao vivo mostra como ficara.
- **Favicon** -- Envie um icone personalizado para a aba do navegador.

### Notificacoes

- Clique no **icone de sino** na barra superior para ver notificacoes recentes.
- Clique em "Mark all read" para limpar a contagem.
- Clique em "View all notifications" para ver o historico completo.

### Relatorios

- Navegue ate **Relatorios** na barra lateral.
- Relatorios sao organizados por categoria (ex: Clientes, Casos, Financeiro).
- Clique em qualquer relatorio para visualiza-lo. Os relatorios suportam rotulos em ingles e portugues.

---

# 11. Tips & Tricks / Dicas Uteis

## EN: Tips & Tricks

### Quick Navigation
- Use the sidebar sections (Juridico, Admin) which are collapsible -- click the header to expand or collapse.
- On mobile, the hamburger menu opens the sidebar. Tap outside to close.

### Dark Mode
- Toggle dark/light mode with the sun/moon icon in the top bar. The setting persists in your browser.

### Feedback
- Notice the **Feedback** button at the bottom of every page (in the alpha banner).
- Click it to report bugs, suggest features, or ask questions. Include the type (Bug, Suggestion, Question, Other) and a description.

### Document Views
- Switch between List, Grid, and Tree views in Documents to find the view that works best for you.
- Tree view groups documents by client, which is useful for finding all documents for a specific person.

### Task Kanban
- The Kanban board lets you drag and drop tasks between columns (Pending, In Progress, Completed, Blocked).
- This is especially useful for team standups and sprint planning.

### Bulk Document Operations
- Select multiple documents with checkboxes for bulk actions like delete.
- Use the "per page" dropdown to show up to 200 documents at once.

### Client Portal
- Grant portal access from the client detail page to let clients upload documents and check case status on their own.

### USCIS Status Check (Immigration)
- Use the USCIS integration to check case status directly from CaseHub. No need to visit the USCIS website separately.

### Reports & Exports
- Use the Reports section for pre-built reports organized by category.
- Reports render in both English and Portuguese based on your language setting.

### Auto-Numbering
- Configure auto-numbering in Settings to maintain consistent case and client numbering across your firm.

## PT-BR: Dicas Uteis

### Navegacao Rapida
- As secoes da barra lateral (Juridico, Admin) sao recolhiveis -- clique no cabecalho para expandir ou recolher.
- No celular, o menu hamburguer abre a barra lateral. Toque fora para fechar.

### Modo Escuro
- Alterne entre modo claro/escuro com o icone de sol/lua na barra superior. A configuracao persiste no navegador.

### Feedback
- Note o botao **Feedback** no rodape de cada pagina.
- Clique para reportar bugs, sugerir funcionalidades ou fazer perguntas. Inclua o tipo (Bug, Sugestao, Duvida, Outro) e uma descricao.

### Visualizacao de Documentos
- Alterne entre Lista, Grid e Arvore na pagina de Documentos.
- A visualizacao em Arvore agrupa documentos por cliente, util para encontrar todos os documentos de uma pessoa.

### Kanban de Tarefas
- O quadro Kanban permite arrastar e soltar tarefas entre colunas (Pendente, Em Progresso, Concluida, Bloqueada).
- Muito util para reunioes de equipe e planejamento.

### Operacoes em Massa
- Selecione multiplos documentos com caixas de selecao para acoes como exclusao em massa.
- Use o dropdown "por pagina" para mostrar ate 200 documentos de uma vez.

### Portal do Cliente
- Conceda acesso ao portal pela pagina de detalhes do cliente para que ele envie documentos e acompanhe o status do caso por conta propria.

### Relatorios e Exportacoes
- Use a secao de Relatorios para relatorios pre-configurados organizados por categoria.
- Os relatorios renderizam em ingles e portugues conforme sua configuracao de idioma.

### Auto-Numeracao
- Configure a auto-numeracao em Configuracoes para manter numeracao consistente de casos e clientes no escritorio.

---

> **Need help?** / **Precisa de ajuda?**
>
> Use the **Feedback** button at the bottom of any CaseHub page to report issues or ask questions.
>
> Use o botao **Feedback** no rodape de qualquer pagina do CaseHub para reportar problemas ou fazer perguntas.
