# Fatia 5 — Drive sync (`/CaseHubMD/<doc-id>.md`)

> **Objetivo:** docs CaseHub.md salvam automaticamente no Google Drive do user em `/CaseHubMD/<doc-id>.md`. Sem novos OAuth scopes (reusa `https://www.googleapis.com/auth/drive` já presente no CaseHub).

## Council? Não necessário

Inspecionei `services/google_drive_handler.py:46`: scope atual já é `drive` full-access. Fatia 5 **não amplia scope**, **não toca `.env`/secrets**, **não muda OAuth flow**. Apenas adiciona pasta nova (`CaseHubMD/`) e arquivos `.md` dentro dela. Sem red line tocada.

Inventário do existente:
- `services/google_drive_handler.py` — `GoogleDriveHandler` class, `get_drive_service()` token loader.
- `routes/gdrive_sync_routes.py` — rotas existentes (não reutilizadas; CaseHub.md fica isolado).
- `static/js/gdrive_sync_ui.js` — UI legacy (não reutilizada; nosso fetch é direto e enxuto).

## Critérios de pronto

1. Pasta `/CaseHubMD/` criada idempotentemente na raiz do Drive (cache do folder_id em memória).
2. `POST /casehub-md/drive/save` body `{doc_id, markdown, filename?}` → cria-ou-atualiza `<filename or doc_id>.md`, retorna `{file_id, drive_url, updated_at}`.
3. `GET /casehub-md/drive/<doc_id>` → retorna `{markdown, updated_at}` ou 404 se ausente.
4. `GET /casehub-md/drive/list` → lista os 100 docs mais recentes.
5. Frontend: botão "💾 Drive" no toolbar Export + auto-save debounce 3s (depois de qualquer mudança no editor; pausa quando mirror está sendo manipulado externamente).
6. `doc_id` gerado client-side via `crypto.randomUUID()` na primeira save, persistido em `localStorage` por sessão (Fatia 5.1: `?doc=` na URL).
7. Drive indisponível (sem credentials/token) → endpoint 503 graceful + botão UI mostra "Drive offline".
8. Smoke test: POST save retorna 200 ou 503 (aceita ambos).
9. Diff <350 linhas (alvo um pouco maior; serviço novo).

## Escopo OUT (defer)

- Multi-user OAuth (cada user com seu token) — handler atual é org-wide; Fatia 5.2 se necessário.
- Conflict resolution (etag/version) — adicionar quando colab Fatia 8 entrar.
- Diff/history viewer — Drive API tem `revisions().list()`; expor via UI fica para Fatia 5.3.
- Load on mount via `?doc=` querystring — Fatia 5.1.
- Move para sub-pasta `/CaseHubMD/<case_id>/` quando Maestro Fatia 7 entrar.

## Arquitetura

```
services/casehub_md/drive_sync.py
    DriveSync.ensure_root_folder() -> str
    DriveSync.save_markdown(doc_id, markdown, filename) -> SaveResult
    DriveSync.load_markdown(doc_id) -> Optional[LoadResult]
    DriveSync.list_recent(limit=100) -> List[DocSummary]
    DriveSync.is_available() -> bool

routes/casehub_md.py
    POST /casehub-md/drive/save
    GET  /casehub-md/drive/{doc_id}
    GET  /casehub-md/drive/list
```

Pasta convention: nome `CaseHubMD` na raiz "My Drive" do service account. Cada doc é arquivo `<doc_id>.md` (mime `text/markdown`) com `appProperties.casehub_md_doc_id = doc_id` para indexar em vez de filename.

## Leis UX

- **Doherty:** auto-save debounced 3s evita feedback prematuro (digitar continua fluido). Save manual responde <1s.
- **Postel:** filename opcional; aceita sem `.md` (auto-append); aceita doc_id como UUID ou slug.
- **Norman:** label "💾 Drive" cobre intent claro (não só ícone).

## Loop checkpoint

| Passo | Status |
|---|---|
| 1. Spec (este doc) | em curso |
| 2. Service `drive_sync.py` | pendente |
| 3. Endpoints FastAPI (save/load/list) | pendente |
| 4. Frontend botão + auto-save debounce | pendente |
| 5. Smoke test ampliado | pendente |
| 6. Commit pequeno | pendente |
| 7. Checkpoint | pendente |
