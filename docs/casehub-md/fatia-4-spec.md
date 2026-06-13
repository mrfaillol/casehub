# Fatia 4 — Export DOCX (Pandoc backend) + template OAB

> **Objetivo:** botão "Exportar DOCX" no editor envia markdown atual para o backend, que usa Pandoc no VPS para gerar `.docx`. Pandoc é binário GPL-2 instalado no sistema (não vendorizado no repo). Template OAB definido em `docs/casehub-md/templates/oab-default.docx` (placeholder na Fatia 4; geração via reference.docx do Pandoc na Fatia 4.1).

## Decisão de licença (sem Council)

Pandoc backend escolhido sobre @tiptap-pro / docx npm porque:

1. **@tiptap-pro/extension-export** exige license server + custo proprietário — red line de licença (vendor lock + extension dep externa).
2. **`docx` npm package (MIT)** seria viável, mas duplica esforço: marked já converte md→HTML; Pandoc converte md→docx nativamente com fidelidade muito superior (tables, footnotes, headings, code blocks com syntax style).
3. **Pandoc**: GPL-2 binário do sistema. Não distribuído no repo (`subprocess.run(["pandoc", ...])`). GPL-2 binário system NÃO contamina código Python da aplicação (linker boundary). Aligned com red line do goal: "PDF/OCR é endpoint, NÃO vendora Tesseract no repo" — mesma filosofia.

**Council não necessário** porque:
- não toca memory/, secrets, deploy topology, hooks, agentes, AGENTS.md
- não adiciona dep Python runtime (Pandoc é system binary, chamado via subprocess)
- escopo isolado (rota nova sob `/casehub-md/*`, alpha intocada)

Se VPS NÃO tiver Pandoc instalado, fallback graceful: endpoint retorna `503 pandoc-not-available` com instrução de install. Detecção via `which pandoc` no startup do módulo.

## Critérios de pronto

1. Endpoint `POST /casehub-md/export/docx` aceita JSON `{markdown: str, filename?: str}` e retorna `application/vnd.openxmlformats-officedocument.wordprocessingml.document` com header `Content-Disposition: attachment`.
2. Pandoc invocado via `subprocess.run` com timeout 10s, captura stderr para logging, sem shell injection.
3. Botão "⤓ DOCX" no toolbar Embeds → fetch backend → `<a download>` blob.
4. Se Pandoc indisponível: endpoint 503 + frontend mostra mensagem "Pandoc não instalado no VPS — peça ao admin".
5. Auth-gate herdando do CaseHub (cookie token).
6. Smoke test: POST com markdown trivial → 200 + bytes DOCX (verifica magic header `PK\x03\x04` — DOCX é zip).
7. Diff <300 linhas.

## Escopo OUT (não fazer agora)

- Template `.docx` OAB completo (margens, fonte, logo) — Fatia 4.1: gerar reference.docx via Pandoc + abrir no Word + estilizar + commitar.
- Upload Drive automático após export — Fatia 5.
- Export PDF (Pandoc faz, mas requer xelatex installed; defer pra Fatia 4.2).
- Streaming / chunked response — markdown raramente passa 1MB, simple buffered response suffice.

## Backend (FastAPI)

```
services/casehub_md/
    __init__.py
    docx_export.py       # convert_markdown_to_docx(md: str, reference: Optional[Path]) -> bytes

routes/casehub_md.py    # adiciona POST /casehub-md/export/docx
```

Função `convert_markdown_to_docx`:
- Escreve markdown em arquivo temp (`tempfile.NamedTemporaryFile`).
- `subprocess.run(["pandoc", tmp_md, "-o", tmp_docx, "--from=gfm+pipe_tables+task_lists", "--to=docx"], timeout=10)`.
- Lê bytes do tmp_docx, return.
- Cleanup garantido em `try/finally`.

Segurança:
- markdown vai em arquivo, não em command-line — sem injection.
- Tamanho máximo: 2MB do payload JSON (FastAPI default ou explícito via middleware existente).
- Pandoc não executa código arbitrário em GFM (modo seguro por default; sem `--from=html` aceitando script tags).

## Frontend

- Botão "⤓ DOCX" no grupo Embeds (após image/table) ou novo grupo "Export".
- Comando handler: `fetch(`${PREFIX}/casehub-md/export/docx`, { method, body: JSON.stringify({markdown}), credentials: 'include' })` → blob → trigger download.
- Filename default: `casehub-md-${YYYYMMDD-HHmm}.docx`.

## Leis UX aplicadas

- **Doherty:** botão dá feedback visual imediato (disabled + "Exportando…" enquanto fetch in-flight).
- **Postel:** endpoint aceita markdown com ou sem trailing newline; filename opcional.
- **Norman:** label "⤓ DOCX" usa download glyph + texto óbvio (não só ícone).

## Arquivos a criar/editar

```
services/casehub_md/__init__.py
services/casehub_md/docx_export.py
routes/casehub_md.py             # adiciona endpoint
templates/casehub_md/poc.html    # +1 botão na toolbar
static/js/casehub-md/poc.js      # +1 comando exportDocx
static/css/casehub-md/poc.css    # leve estilo "loading state"
docs/casehub-md/fatia-4-spec.md  # este arquivo
tests/smoke-casehub-md-poc.spec.js  # +1 assertion: POST endpoint, 200/503
```

## Loop checkpoint

| Passo | Status | Evidência |
|---|---|---|
| 1. Spec | ✅ | `docs/casehub-md/fatia-4-spec.md` |
| 2. Backend service | ✅ | `services/casehub_md/docx_export.py` — `convert_markdown_to_docx`, `pandoc_available`, 4 exception classes; sem shell=True; timeout 10s; cleanup garantido |
| 3. Endpoint FastAPI | ✅ | `routes/casehub_md.py` — POST `/casehub-md/export/docx` auth-gated; 503/413/504/500 mapeados |
| 4. Botão + fetch frontend | ✅ | toolbar group "Export", `exportDocx` handler com loading state via `btn.disabled` |
| 5. Smoke test ampliado | ✅ | step 6 testa endpoint via `page.request.post`; aceita 200 (DOCX magic header `PK\x03\x04`) ou 503 (pandoc-not-available) |
| 6. Commit pequeno | ✅ | 179 + service files; alvo <300 respeitado |
| 7. Checkpoint | ✅ | 2026-05-22 |

## Próximos refinos (Fatia 4.1+)

- **Template OAB:** gerar `reference.docx` via Pandoc default (`pandoc -o ref.docx --print-default-data-file reference.docx`), abrir no LibreOffice/Word, ajustar margens 2.5cm/2cm/3cm, fonte Times New Roman 12pt, header com timbre do escritório, commitar em `docs/casehub-md/templates/oab.docx`. Endpoint passa a aceitar `template=oab` no payload.
- **Streaming response:** raramente útil (markdown <1MB), mas trivial via `StreamingResponse` se medirmos contention.
- **Export PDF via Pandoc:** requer `xelatex` + fonte legal instalados no VPS — defer pra Fatia 4.2.
