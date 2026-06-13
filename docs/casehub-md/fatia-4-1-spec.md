# Fatia 4.1 — Template OAB.docx (refino da Fatia 4)

> **Objetivo:** entregar template DOCX canônico para petições brasileiras OAB, aplicado via parâmetro `template=oab` no endpoint export. Petições saem prontas pra protocolar, sem ajuste manual no Word.

## Critérios de pronto

1. `docs/casehub-md/templates/oab.docx` commitado — gerado via Pandoc default + customização ABNT/OAB.
2. Endpoint `POST /casehub-md/export/docx` aceita `{template: "oab"}` opcional.
3. Service `get_template_path(name)` resolve nome → path em disco; retorna None se inválido (graceful fallback).
4. Frontend: botão "⤓ OAB" no grupo Export (separado do "⤓ DOCX" default).
5. Diff <250 linhas.

## Especificação do template OAB

Por praxe forense brasileira (ABNT NBR 14724 + Estatuto da Advocacia):

| Atributo | Valor |
|---|---|
| Fonte corpo | Times New Roman 12pt |
| Headings | Times New Roman bold — 16/14/13pt (H1/H2/H3) |
| Espaçamento | 1.5 linhas |
| Alinhamento corpo | Justify |
| Margem superior | 3 cm |
| Margem esquerda | 3 cm |
| Margem inferior | 2 cm |
| Margem direita | 2 cm |
| Recuo primeira linha | 0 (paragrafação por bloco, sem indent) |
| Espaçamento entre parágrafos | 6pt depois |
| Citação (Quote) | 11pt, justify, line-spacing 1.5 |
| Code (verbatim) | Courier New 10pt — útil pra lei/jurisprudência verbatim |

## Como o template foi gerado

Pipeline reproduzível (commitado em `scripts/build-casehub-md-oab-template.py` — futuro):

```bash
# 1. Gerar reference.docx default do Pandoc
pandoc -o /tmp/pandoc-default-ref.docx --print-default-data-file reference.docx

# 2. Customizar com python-docx (margens, fonte, line-spacing)
python3 build-oab.py /tmp/pandoc-default-ref.docx \
    docs/casehub-md/templates/oab.docx

# 3. Testar conversão real
pandoc sample-peca.md \
    --reference-doc=docs/casehub-md/templates/oab.docx \
    --to=docx -o sample-peca-oab.docx
```

(Script `build-oab.py` em `/tmp/casehub-md-build-oab.py` na sessão 2026-05-23;
quando virar entrega permanente, mover para `scripts/`.)

## Como usar

**Backend (cURL):**
```bash
curl -X POST -H 'Content-Type: application/json' \
  -d '{"markdown": "# EXCELENTÍSSIMO...", "template": "oab", "filename": "embargos"}' \
  https://dev.vingren.me/casehub/casehub-md/export/docx \
  -o embargos.docx
```

**Frontend:**
- Botão **"⤓ OAB"** no toolbar Export envia `template=oab`.
- Filename auto: `casehub-md-oab-YYYY-MM-DD-HH-MM.docx`.
- Default (botão "⤓ DOCX"): template Pandoc neutro.

## Loop checkpoint

| Passo | Status | Evidência |
|---|---|---|
| 1. Spec | ✅ | este arquivo |
| 2. Template gerado | ✅ | `docs/casehub-md/templates/oab.docx` (10.9 KB) |
| 3. Service `get_template_path()` | ✅ | `services/casehub_md/docx_export.py` |
| 4. Endpoint aceita `template` | ✅ | `_DocxExportPayload.template: str | None` |
| 5. Frontend "⤓ OAB" botão | ✅ | toolbar group Export + `runDocxExport()` helper |
| 6. Smoke validation | ⚠️ defer | exigiria PDF parsing pra checar margens; uma conversão E2E manual basta pra fatia |
| 7. Commit | em curso | |

## Decisões diferidas

- Templates adicionais (TJ-SP, TJ-MG específicos com cabeçalho regional) — incremental quando user pedir.
- Logo do escritório no header — depende de `org.branding.logo` no DB; integrar quando Fatia 5.2 trouxer multi-tenant Drive.
- Footer com OAB do advogado — idem.
- Quebra de página antes de seção (`\newpage` markdown) — não há sintaxe markdown nativa; via comment HTML `<!-- pagebreak -->` é possível, mas adia.
- PDF export via XeLaTeX usando template OAB — Fatia 4.2.
