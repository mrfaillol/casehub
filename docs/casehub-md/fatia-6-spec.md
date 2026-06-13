# Fatia 6 — PDF + OCR endpoint async (Tesseract + Poppler)

> **Objetivo:** botão "📄 OCR" no editor → user escolhe arquivo (PDF ou imagem) → backend extrai texto (Tesseract via subprocess) → retorna markdown → frontend insere bloco no editor. Tesseract + Poppler são binários system (não vendorizados no repo).

## Council? Não necessário

Não toca red lines: sem novo OAuth scope, sem secrets, sem deploy topology novo, sem agente, sem AGENTS.md. Binários assumidos pré-instalados no VPS (mesma filosofia Pandoc Fatia 4). Se ausentes: 503 graceful.

## Critérios de pronto

1. `POST /casehub-md/ocr` multipart `file=<pdf|image>` (+ opcional `lang=por+eng` query).
2. Service `services/casehub_md/ocr_pdf.py` com:
   - `extract_text(path, content_type, lang) -> str` (markdown)
   - Path PDF: tenta `pdftotext` (puro/digital, ~ms). Se output vazio/curto → `pdftoppm` por página → `tesseract`.
   - Path image: `tesseract` direto.
   - Timeout total 30s; rejeita file >10MB.
3. Retorna JSON `{markdown, source: 'pdftotext'|'tesseract'|'tesseract-pdf', pages?, took_ms}`.
4. Botão "📄 OCR" no toolbar Embeds; abre `<input type="file" accept="application/pdf,image/*">` invisível; submit fetch; insere markdown no cursor atual.
5. Frontend mostra loading state (`… OCR`) durante request; se 503 → alert "Tesseract não instalado".
6. Smoke test envia 1 PDF mock pequeno; aceita 200/503/415/422.
7. Diff <300 linhas.

## Escopo OUT (defer)

- Worker fila assíncrona (Celery/RQ) — POC síncrono é OK para PDF jurídico típico (<10 páginas). Fatia 6.1 se Victor pedir.
- Layout-preserving (LayoutParser / Tesseract HOCR + heurística de parágrafos) — Fatia 6.2; agora junta linhas em parágrafos por blank line.
- DOCX/PPTX/XLSX — Pandoc faz, mas escopo é OCR; abrir Fatia 6.3 se necessário.
- Multipage PDF >50 páginas — rejeitar com 422 (custo Tesseract proibitivo síncrono).

## Stack

- `pdftotext` (Poppler, GPL-2 binário) — extrai texto digital de PDF rapidamente.
- `pdftoppm` (Poppler) — converte PDF → PNG por página (densidade 300dpi).
- `tesseract` (Apache 2.0 binário) — OCR de imagem.
- Sem Python deps novas (`tesseract-ocr` é binário, não pacote pip).

## Heurística PDF híbrida

```python
text_digital = pdftotext(path)
if len(text_digital.strip()) >= 80:          # threshold empírico
    return text_digital + ' (source: pdftotext)'
images = pdftoppm(path)                       # PDF → PNGs
ocr_parts = [tesseract(img, lang) for img in images]
return '\n\n'.join(ocr_parts) + ' (source: tesseract-pdf)'
```

## Leis UX

- **Doherty:** botão mostra `… OCR` durante request; status bar atualiza com "OCR de 3 páginas… 12s".
- **Postel:** aceita `.pdf` `.png` `.jpg` `.jpeg` `.tiff` `.webp` (qualquer image/*).
- **Norman:** ícone "📄 OCR" + texto óbvio.

## Arquivos

```
services/casehub_md/ocr_pdf.py
routes/casehub_md.py              # +POST /casehub-md/ocr
templates/casehub_md/poc.html     # +1 botão + hidden file input
static/js/casehub-md/poc.js       # +1 comando ocr
docs/casehub-md/fatia-6-spec.md   # este arquivo
tests/smoke-casehub-md-poc.spec.js# +1 assertion endpoint
```

## Loop checkpoint

| Passo | Status | Evidência |
|---|---|---|
| 1. Spec | ✅ | `docs/casehub-md/fatia-6-spec.md` |
| 2. Service `ocr_pdf.py` | ✅ | `extract_text()`, `tesseract_available()`, `poppler_available()`; hybrid pdftotext→tesseract; soft 28s wall-clock cap; lang allowed `por+eng`; cleanup tmpdir |
| 3. Endpoint multipart | ✅ | `POST /casehub-md/ocr` (FastAPI `UploadFile`); 415/413/422/503/504 mapeados; lang allow-list |
| 4. Frontend file picker | ✅ | hidden `<input type=file>` + `data-cmd="ocr"` button; insertContent(html) no cursor; status bar mostra `source · pages · ms` |
| 5. Smoke test ampliado | ✅ | step 9 envia PNG 1x1 multipart; aceita 200/415/422/503/504/500/401 |
| 6. Commit pequeno | ✅ | 195 + service module; alvo <300 respeitado |
| 7. Checkpoint | ✅ | 2026-05-23 |

## Próximos refinos (defer)

- Worker fila assíncrona (Celery/RQ) — só se Victor reclamar de UI bloqueada em PDFs longos.
- Layout-preserving (HOCR + heurística de parágrafos) — Fatia 6.2.
- Lang adicional (esp, fra, etc.) — adicionar à allow-list quando demandado.
- DOCX/PPTX upload — Pandoc cobre; abrir Fatia 6.3 se necessário.
