# Checklist — Vídeo de verificação OAuth Google (CaseHub)

Marque tudo antes de submeter ao Google. Roteiro completo: [roteiro.md](roteiro.md).

## Pré-gravação
- [ ] App "In production" no Console (console.cloud.google.com/auth/audience)
- [ ] Conta Google de **teste** logada (não usar conta com PII real)
- [ ] Pasta/cliente **FICTÍCIO** no Drive ("Active Clients / Cliente Demo")
- [ ] Fluxo testado UMA vez sem gravar (login → Calendar connect → Drive connect → /files → disconnect)
- [ ] macOS: Não Perturbe ON, abas/extensões/badges fechados, zoom 100%
- [ ] Permissão de Gravação de Tela dada ao Terminal/app de captura
- [ ] Deslogado do CaseHub (vídeo começa no login)

## Conteúdo obrigatório no vídeo (Google exige)
- [ ] Cena C: consent do **Calendar** com nome "CaseHub" + scopes `calendar.readonly` e `calendar.events` visíveis
- [ ] Cena D: agenda do Google **dentro** do CaseHub
- [ ] Cena E: consent do **Drive** (`/auth/drive`, RESTRICTED) — **NÃO PULAR**
- [ ] Cena E: arquivos do Drive **dentro** do CaseHub (/casehub/files)
- [ ] Cena F: **revogação/disconnect** funcionando (status volta a "desconectado")
- [ ] Sem nenhuma PII real em frame (scrub antes de subir)
- [ ] ≥ 720p, áudio claro (se narrar)

## Pós
- [ ] YouTube: **NÃO LISTADO** (Unlisted), "não é para crianças"
- [ ] Link colado em console.cloud.google.com/auth/scopes (campo "Vídeo de demonstração") + Salvar
- [ ] /auth/verification → "Preparar para verificação" → submeter
- [ ] Conferir e-mail victor@vingren.me para respostas do review (responder rápido acelera)

## Como gravar
```
cd docs/google-oauth-verification
chmod +x record-screen.sh        # primeira vez
./record-screen.sh --list        # confirma o índice da tela
./record-screen.sh               # grava (Ctrl+C para parar) — arquivo em takes/
./record-screen.sh --audio       # com narração
```
Sem instalar nada: `Cmd+Shift+5` → Gravar Tela Inteira.
