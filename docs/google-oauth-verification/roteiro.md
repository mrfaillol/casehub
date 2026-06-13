# Roteiro — Vídeo de verificação OAuth do Google (CaseHub)

> Objetivo: gravar o vídeo exigido pelo Google em console.cloud.google.com/auth/scopes
> para verificar o app CaseHub. Mostra o fluxo OAuth real de Google Calendar E Google Drive,
> o uso dos dados dentro do CaseHub, e a revogação.
> Duração alvo: 2:30–3:30. Cru, sem edição. YouTube: NÃO LISTADO.

---

## Scopes que PRECISAM aparecer no consent (exatos, do código)

Calendar (services/google_calendar.py):
- https://www.googleapis.com/auth/calendar.readonly   (ver agenda)
- https://www.googleapis.com/auth/calendar.events     (criar/editar eventos)

Drive (services/google_drive_handler.py):
- https://www.googleapis.com/auth/drive               (acesso aos arquivos do escritório)

ATENCAO: /auth/drive e RESTRICTED. O video TEM que mostrar uso real do Drive
dentro do CaseHub (Cena E), senao o review trava ou pede security assessment.
Nao pule a Cena E.

---

## O que o Google exige ver
1. O app (CaseHub) iniciando o pedido de acesso OAuth.
2. A tela de consentimento do Google com o NOME do app (CaseHub) e os SCOPES exatos.
3. O usuario CONCEDENDO o acesso.
4. O app USANDO os dados — agenda do Calendar e arquivos do Drive dentro do CaseHub.
5. O usuario conseguindo REVOGAR / desconectar.

As cenas C (consent) e E (uso do Drive) sao o coracao do video. Mostre com calma.

---

## Antes de gravar (preparacao — 5 min)
1. Conta Google de teste logada no navegador. Use pasta/cliente FICTICIO no Drive. Sem PII real.
2. App em "In production" no Console (tokens nao expiram).
3. Teste o fluxo UMA VEZ sem gravar, ponta a ponta:
   - https://casehub.legal/casehub/login -> logar
   - https://casehub.legal/casehub/google-calendar/settings -> Conectar (Calendar)
   - Google -> escolher conta -> Permitir -> volta "conectado"
   - Confirme agenda em /casehub/google-calendar/events
   - Confirme arquivos do Drive em /casehub/files
   - Se travar no callback, PARE e avise antes de gravar.
4. Deslogar do CaseHub depois do teste (o video comeca pela tela de login).
5. macOS: ligar Nao Perturbe/Foco; fechar abas, extensoes, apps com badges.
6. Janela do navegador limpa, zoom 100%, uma aba so.

---

## Roteiro de gravacao (cena a cena)

Inicie a gravacao: `./record-screen.sh`  OU  Cmd+Shift+5 -> Gravar Tela Inteira.

### Cena A — Login no CaseHub (0:00–0:15)
- Barra de endereco: digite `casehub.legal` + Enter. Deixe a URL visivel ~2s.
- Digite e-mail + senha -> Entrar. Cai no dashboard.
- Fala: "Este e o CaseHub, plataforma de gestao juridica. Vou conectar a conta Google."

### Cena B — Iniciar OAuth do Calendar (0:15–0:35)
- Barra de endereco: `casehub.legal/casehub/google-calendar/settings` + Enter. Pause ~2s.
- Clique "Conectar" de uma das agendas. Redireciona para accounts.google.com.

### Cena C — Consent screen do CALENDAR (0:35–1:05) [CORACAO 1]
- Clique na conta a conectar.
- PAUSE ~6s no consent. Mostre: "CaseHub quer acessar sua Conta do Google" +
  permissoes (ver eventos do Google Agenda = calendar.readonly; ver/editar eventos = calendar.events).
- Clique "Continuar"/"Permitir". Redireciona de volta.
- No CaseHub: status CONECTADO (verde). Pause ~2s.

### Cena D — Uso real do CALENDAR no CaseHub (1:05–1:30) [USO DOS DADOS]
- Va para `casehub.legal/casehub/google-calendar/events` (ou aba "Agenda"/"Ver eventos").
- Mostre os eventos do Google Calendar DENTRO do CaseHub ~4s.
- (Opcional, reforca calendar.events) crie/edite um compromisso de teste no CaseHub e mostre sincronizando pro Google. Evento ficticio.
- Fala: "A agenda do Google aparece dentro do CaseHub e os prazos do CaseHub viram eventos no Google Agenda."

### Cena E — Consent + uso real do DRIVE (1:30–2:30) [CORACAO 2 — NAO PULE]
- Inicie a conexao do Drive a partir do CaseHub (Integracoes/Documentos). Vai pro accounts.google.com.
- PAUSE ~6s no consent do Drive: "CaseHub quer ver, editar, criar e apagar todos os seus arquivos do Google Drive" (texto do scope /auth/drive). Clique "Permitir".
- Volte e abra `casehub.legal/casehub/files`.
- Mostre ~6s os arquivos/pastas do Drive (pasta ficticia "Active Clients / Cliente Demo") DENTRO do CaseHub — comprova o full-access.
- Fala: "O CaseHub acessa e organiza os documentos do escritorio no Google Drive — por isso o acesso completo, para ler e organizar as pastas de clientes ja existentes."

### Cena F — Revogacao / Disconnect (2:30–3:00) [EXIGIDO]
- Volte em `casehub.legal/casehub/google-calendar/settings`.
- Clique "Desconectar" (rota real POST /casehub/google-calendar/disconnect — revoga em oauth2.googleapis.com/revoke).
- Mostre o status voltando para "desconectado". Pause ~3s.
- Fala: "O usuario pode revogar o acesso a qualquer momento direto no CaseHub."

### Fim (3:00)
- Pare a gravacao (Ctrl+C no script, ou Cmd+Shift+5 -> parar).

> Se nao houver botao separado de Drive connect, mostre /casehub/files com os arquivos do Drive ja listados — ja comprova uso. Mas o consent do Drive (topo da Cena E) e fortemente recomendado por ser scope restricted.

---

## Subir no YouTube
1. youtube.com -> icone de camera -> "Enviar video".
2. Selecione o arquivo de final/ (ou ~/Desktop).
3. Titulo: CaseHub — Google OAuth demo (Calendar + Drive) — verification
4. Visibilidade: NAO LISTADO (Unlisted).
5. "Nao, nao e conteudo para criancas".
6. Publicar -> copiar o link.

## Depois
- Cole o link em console.cloud.google.com/auth/scopes -> campo "Video de demonstracao". Salve.
- console.cloud.google.com/auth/verification -> "Preparar para verificacao" -> submeter.
- E-mails do review chegam em victor@vingren.me. Responder rapido acelera.

## Por que nao da pra automatizar
O consent real do Google exige login humano e bloqueia navegadores automatizados (anti-bot + 2FA).
A gravacao tem que ser num navegador real, sessao humana.

— Roteiro consolidado, 2026-05-29 (incorpora docs/casehub-alpha/roteiro-video-oauth-verification.md + Drive + revogacao).
