# CaseHub.md — Editor Markdown WYSIWYG

> **Status:** em desenvolvimento (Fatia 1 em curso 2026-05-22). Branch dedicada paralela: `session-2026-05-22-casehub-md-poc` (worktree `casehub-worktrees/casehub-md-poc-20260522`). Alpha 25/05 NÃO depende deste módulo.

CaseHub.md é o editor markdown WYSIWYG nativo do CaseHub. Mimica Google Docs visualmente (serif, ruler, page-width 8.5×11"), traz features Obsidian+Notion (wiki-links, blocos, embeds), e integra com OCR, Drive sync e Maestro (AI assist por parágrafo). Visualmente **respeita o design system Basic** (data-theme="neuromorphic") — a "folha" Google Docs vive dentro do shell neumórfico.

## Stack canônico

| Camada | Tecnologia | Licença | Razão |
|---|---|---|---|
| Editor frontend | TipTap (`@tiptap/core` + StarterKit) | MIT | Headless, markdown↔JSON bidirecional, plugin API rica |
| Markdown bridge | marked + turndown (POC) → prosemirror-markdown (Fatia 3+) | MIT | Markdown é **fonte canônica**; JSON é runtime |
| Runtime UI (POC) | TipTap puro via ESM CDN (jsdelivr) | — | Sem build pipeline novo. Vue 3 entra quando precisar de componentes (Fatia 3+). |
| Collab (v2 opcional) | Hocuspocus + Yjs | MIT | Ponte FastAPI via Redis/Postgres snapshot |
| Export DOCX | @tiptap-pro/extension-export ou Pandoc backend | misto | Council se @tiptap-pro exigir license server |
| OCR PDF | Endpoint FastAPI async (Tesseract/EasyOCR) | Apache 2.0 / GPL | NÃO vendorizar Tesseract no repo |
| Drive sync | Reusa `gdrive_sync_ui.js` + OAuth CaseHub | — | Endpoint FastAPI grava `/CaseHubMD/<doc-id>.md` |
| Maestro | Extension TipTap → `POST /maestro/suggest` com `case_id` | — | AI assist por parágrafo |

## Red lines

1. **Markdown é fonte canônica.** JSON ProseMirror é runtime — nunca persistir como source-of-truth.
2. **Sem AGPL/BSL no core.** TipTap MIT + Hocuspocus MIT travados. Qualquer extensão licença diferente passa por Council.
3. **PDF/OCR é endpoint backend**, não vendoriza Tesseract no repo.
4. **Não quebrar alpha** (25/05). Branch paralela, rotas isoladas sob `/casehub-md/*`, sem editar templates/módulos alpha-críticos.
5. **Sem commit de credenciais Google API.** OAuth flow no `.env` VPS (reusar o existente).
6. **Não declarar pronto sem peças jurídicas reais testadas + lawyer feedback.**
7. **Respeitar design system Basic.** Shell neumórfico (tokens canônicos), nada de hex/px cru. Cita lei UX aplicada na proposta.

## Fatias por ordem

| # | Fatia | Status | Commit |
|---|---|---|---|
| 1 | POC TipTap standalone, markdown round-trip (shell neumórfico) | ✅ | `e2ddea7` + `78c499d` |
| 2 | "Folha" Google Docs dentro do shell (serif, page 8.5×11, ruler) | ✅ | `2c16e7e` |
| 3 | Embed image/link/table (TipTap built-in + turndown-gfm) | ✅ | `1f10268` |
| 4 | Export DOCX via Pandoc backend (rejected @tiptap-pro) | ✅ | `ad1e421` |
| 5 | Drive sync (`/CaseHubMD/<doc-id>.md`) auto-save 3s debounce | ✅ | `92fdb89` |
| 6 | PDF+OCR endpoint (Tesseract + Poppler, hybrid pdftotext→OCR) | ✅ | `0a3ac8c` |
| 7 | Maestro integration (HTTPx proxy + modal aceitar/descartar) | ✅ | `ecc9d33` |
| 8 | Collab Hocuspocus + Yjs (opcional v2) | **DEFERRED** | — |

Branch: `session-2026-05-22-casehub-md-poc` (worktree
`casehub-worktrees/casehub-md-poc-20260522/`).
Origin: https://github.com/mrfaillol/casehub-prod/tree/session-2026-05-22-casehub-md-poc

## Loop 7 passos por fatia

`spec → poc → estética → integração CaseHub backend → testes → 1 PR pequeno → checkpoint`

Cada fatia produz **um único PR pequeno** (objetivo: <300 linhas diff, cirúrgico, reversível).

## Divisão de runtimes

- **Claude (este runtime, sessão 2026-05-22):** spec, rotas FastAPI, endpoints, OCR worker, Drive sync backend, Maestro bridge, smoke tests.
- **Codex:** componentes Vue 3, mount TipTap rico, extensions custom, CSS estética avançada (Fatia 2 — folha Google Docs com ruler SVG), polish UI.

Per [feedback_codex_primary_state](../../../memory/feedback_codex_primary_state.md): Codex 5x Pro é throughput default desde 2026-05-01. Claude faz arquitetura/spec/security/review denso. O frontend rico das fatias 2-3 e estética deve sair do Codex via task envelope.

## Referências externas (consultadas no plan 22/05)

- TipTap: https://github.com/ueberdosis/tiptap
- @tiptap/vue-3: https://www.npmjs.com/package/@tiptap/vue-3
- Hocuspocus: https://tiptap.dev/docs/hocuspocus
- Pandoc DOCX templates: https://pandoc.org/MANUAL.html#templates

## Arquivos do módulo

- `docs/casehub-md/` — esta pasta (spec + fatias)
- `routes/casehub_md.py` — router FastAPI
- `templates/casehub_md/` — templates Jinja2
- `static/js/casehub-md/` — ESM modules (mount + extensions)
- `static/css/casehub-md/` — CSS (consome `tokens.css` + `themes/neuromorphic.css`)
- `services/casehub_md/` — backend (OCR worker, Drive sync, Maestro bridge — fatias 5-7)
- `tests/smoke-casehub-md-*.spec.js` — Playwright smoke tests
