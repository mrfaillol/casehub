# Fatia 3 — Embeds: image, link, table, code-block

> **Objetivo:** habilitar inserção e edição de blocos ricos comuns ao Google Docs / Obsidian / Notion — imagem, link, tabela e código — usando extensions oficiais TipTap MIT. Sem features de upload/storage ainda (Fatia 5 Drive integra upload de imagem).

## Critérios de pronto

1. **Imagem**: inserir via URL (prompt simples — Fatia 5 substitui por upload Drive).
2. **Link**: selecionar texto → botão Link → prompt URL → aplica `<a href="...">`.
3. **Tabela**: inserir tabela 3×3 default; toolbar contextual para add row/col (mínimo viável).
4. **Code block**: StarterKit já trazia — agora com syntax-highlighting opcional via `lowlight` (MIT, ~80KB; toggle por feature flag se tamanho preocupar).
5. Markdown round-trip preserva os 4 tipos (turndown sabe lidar com img/a/table/pre/code; verificar).
6. Toolbar expande sem quebrar agrupamento Miller — 4º grupo `Embeds`.
7. Smoke test cobre pelo menos 1 inserção (link) sem quebrar.
8. Diff <300 linhas (alvo).

## Stack adicional (todas MIT)

```js
"@tiptap/extension-image":            // https://www.npmjs.com/package/@tiptap/extension-image
"@tiptap/extension-link":             // https://www.npmjs.com/package/@tiptap/extension-link
"@tiptap/extension-table":            // https://www.npmjs.com/package/@tiptap/extension-table
"@tiptap/extension-table-row":
"@tiptap/extension-table-cell":
"@tiptap/extension-table-header":
"@tiptap/extension-code-block-lowlight":  // opcional (Fatia 3.1 se grande)
"lowlight":                            // syntax highlighting MIT
```

Decisão lowlight: **adiar** para Fatia 3.1 — primeiro habilitar code-block StarterKit puro com font-mono + bg sunken (já está); lowlight quando o Victor pedir highlighting de cores explicitamente. Reduz bundle + complexidade da Fatia 3 atual.

## Markdown round-trip considerations

- `turndown` por default **NÃO** preserva tables nem GFM strikethrough. Precisamos:
  - `turndown-plugin-gfm` (MIT) — adiciona tables, strikethrough, task-lists.
- `marked` por default **suporta** tables com `gfm: true` (já habilitado).
- Imagem: turndown → `![](url)`, marked → `<img src="url">` — OK.
- Link: turndown → `[text](url)`, marked → `<a>` — OK.

## Leis UX aplicadas

- **Hick:** toolbar evita comandos raramente usados (não add separate buttons para subscript/superscript agora; só 4 embeds primários).
- **Fitts:** novo grupo "Embeds" mantém ≥36px hit targets.
- **Postel:** image insert aceita URL com/sem protocol; auto-prefix `https://` quando vier "example.com/foo.jpg".

## Arquivos a editar

```
templates/casehub_md/poc.html           # importmap + 4 botões + 1 grupo toolbar
static/js/casehub-md/poc.js             # 4 extensions + 4 comandos + URL prompts
static/css/casehub-md/poc.css           # estilos tabela + imagem responsive + link
docs/casehub-md/fatia-3-spec.md         # este arquivo
tests/smoke-casehub-md-poc.spec.js      # +1 assertion: inserir link funciona
```

## Loop checkpoint

| Passo | Status | Evidência |
|---|---|---|
| 1. Spec | ✅ | `docs/casehub-md/fatia-3-spec.md` |
| 2. Importmap + extensions | ✅ | 7 novas imports MIT (image/link/table×4/turndown-gfm) — JSON valid 11 imports |
| 3. Toolbar + comandos (image/link/table) | ✅ | novo grupo "Embeds" no template; comandos `link/image/table` + `normalizeUrl()` Postel |
| 4. CSS tabela/imagem/link | ✅ | `.md-img`, `.md-link`, `.md-table` + selectedCell, todos via tokens |
| 5. Smoke test ampliado | ✅ | step 5 valida insertion de link + Postel auto-prefix `https://` |
| 6. Commit pequeno | ✅ | 133 linhas (alvo <300) |
| 7. Checkpoint | ✅ | 2026-05-22 |

## Decisões diferidas

- **`lowlight` para syntax highlighting de code blocks:** adiado. CodeBlock StarterKit puro com font-mono + bg sunken já entrega leitura confortável. Quando Victor pedir cores, adicionar `@tiptap/extension-code-block-lowlight` + `lowlight` (+~80KB) numa Fatia 3.1 separada.
- **Tabela com toolbar contextual (add row/col):** insertTable cobre criação; edição via teclado/menu contextual ProseMirror já funciona out-of-box. UI dedicada de "+row/+col" fica para Fatia 7+ se virar atrito real.
- **Image upload (não URL):** Fatia 5 substitui o `window.prompt` por upload para Drive.
