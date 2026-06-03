# Version Drift Log

Registro de incoerências, drifts e bugs entre versões do CaseHub (VS-prod / dev OS-like / white-label / ILC histórico). Mantido pelo agente [casehub-version-analyst](../../agents/casehub-version-analyst.md).

---

## 2026-04-13 — scroll da sidebar não funciona em VS-prod

**Bug:** Victor reportou que a sidebar esquerda do dashboard de `cliente.example.com/casehub/dashboard` parou de responder a scroll interno. Inicialmente atribuído ao fix `liquid-glass-bg.js → backgrounds.css` da sessão anterior. **Investigação descartou essa causa** — `backgrounds.css` só é referenciado em `signup.html` e `forgot_password.html`, não toca o dashboard.

**Versões afetadas:** VS-prod (Hostinger). Dev OS-like usa arquitetura `.os-dock-bubble` diferente — não tem o mesmo código.

**Root cause identificada:** Script inline em `~/casehub/templates/base.html` linhas 183-203 (VS-prod). Handler `wheel` com `{passive: false}` implementando scroll-chaining manual:

```js
sb.addEventListener('wheel', function(e) {
  var canScroll = sb.scrollHeight > sb.clientHeight + 2;
  var atTop = sb.scrollTop <= 0;
  var atBottom = sb.scrollTop + sb.clientHeight >= sb.scrollHeight - 2;
  if (!canScroll || (e.deltaY < 0 && atTop) || (e.deltaY > 0 && atBottom)) {
    e.preventDefault();
    var scrollEl = document.scrollingElement || document.documentElement;
    scrollEl.scrollTop = scrollEl.scrollTop + e.deltaY;
  }
}, { passive: false });
```

**Problemas com essa abordagem:**

1. **`canScroll === false` intercepta TODOS os wheel events** da sidebar quando o conteúdo cabe sem overflow (caso comum em desktop com <18 itens). Isso é funcionalmente correto (delega ao body), mas se o body não tem scroll, parece que o wheel "não fez nada" — sensação de travamento.
2. **`{passive: false}` + `preventDefault()` degrada composite thread** — o browser espera o JS decidir antes de aceitar scroll nativo; com touchpad Mac (deltas inerciais pequenos e frequentes), dá sensação de lag/trava.
3. **Lógica manual de `scrollTop += deltaY`** não reproduz corretamente inertia/momentum nativos do touchpad.
4. Comentário no código cita "bug original do [parceiro]" — a intenção era corrigir que sidebar bloqueava scroll do body. Essa intenção é legítima, mas a solução escolhida é agressiva demais.

**Patch proposto (NÃO APLICADO, aguardando aprovação de Victor):**

**1.** Em `~/casehub/static/css/casehub-theme.css`, dentro da regra `.sidebar` (linha 234-245), adicionar:
```css
overscroll-behavior: contain;
```

`overscroll-behavior: contain` é a forma nativa moderna de resolver scroll-chaining: quando usuário bate no topo/fundo da sidebar, o scroll **não propaga** para o body. Funciona em Chrome 63+, Firefox 59+, Safari 16+ (suficiente pra CaseHub). Zero JS necessário, zero overhead no composite thread.

**2.** Em `~/casehub/templates/base.html`, **remover** o bloco `<script>` das linhas 183-203. O CSS sozinho resolve o problema do [parceiro] e não mexe em scroll interno.

**Impacto esperado:**
- Scroll interno da sidebar volta a funcionar 100% nativo (inertia Mac touchpad incluso)
- Scroll do body continua sendo bloqueado quando sidebar tem overflow e usuário está nos extremos
- Zero risco de regressão — `overscroll-behavior: contain` é declarativo e bem suportado

**Verificação pós-patch (Victor ou Playwright):**
1. Desktop: scroll com touchpad dentro da sidebar — rola suave
2. Desktop: scroll além do topo/fundo da sidebar — body NÃO rola (contenção ativa)
3. Mobile: sidebar fechada — body rola normal
4. Mobile: sidebar aberta + scroll interno — rola suave

**Arquivos a modificar (condicional à aprovação):**
- `~/casehub/static/css/casehub-theme.css:234-245` — adicionar uma linha
- `~/casehub/templates/base.html:183-203` — remover bloco script

**Status:** pendente-aprovação-victor.

---

## 2026-04-13 — dock OS-like quebrado (apps com texto, sobrepondo clock/avatar)

**Bug:** Victor enviou screenshot de `app.example.com/casehub/dashboard` com dock quebrado: apps mostrando labels textuais ("Documentos", "Clientes", "Processos", "Prazos") invadindo espaço do clock/avatar; cápsula de janelas vazias não colapsada.

**Versões afetadas:** Dev OS-like (Oracle). VS-prod não usa esse dock.

**Root cause:** Migração incompleta de nomenclatura do view-system. O `static/js/desktop/view-manager.js` aplica `body.view-os` / `body.view-web` (feat: `b731e40 view-system: Fase 1`). Mas 3 arquivos CSS do modo desktop **continuaram referenciando `body.desktop`** — classe que nenhum script aplica. Resultado: 260 regras órfãs, incluindo `font-size: 0` (icons-only), `max-width: 70vw`, `overflow-x: auto` do dock-apps-nav.

**Evidência:**
| Arquivo | `body.desktop` órfãs |
|---------|---------------------:|
| `static/css/desktop/glass-override.css` | 236 |
| `static/css/desktop/dock-apps-nav.css` | 18 |
| `static/css/desktop/wallpaper-sky.css` | 6 |

Compounds existentes (`body.desktop.viewport-mobile`, `.performance-mode`, `.iframe-mode`, `.dragging-active`) confirmaram que `.desktop` era alias do "modo view-os", não do viewport — substituição global preserva semântica.

**Patch aplicado (em dev, aprovado autonomamente):**
```bash
sed -i '' 's/body\.desktop\([^-A-Za-z0-9_]\)/body.view-os\1/g' \
  static/css/desktop/{glass-override,dock-apps-nav,wallpaper-sky}.css
rsync → ubuntu@REDACTED-HOST:~/casehub-dev/static/css/desktop/
```

260 regras reativadas. Dock volta a ícones-only, width constrangida, sem sobreposição.

**Audit recorrente proposto:** `grep -rn "body\.desktop\b" static/css/` deve retornar 0 em dev; qualquer ocorrência futura = red flag de rename incompleto. Aplicar também em `casehub-version-analyst.md` como check periódico.

**Status:** aplicado em dev 2026-04-13; aguarda validação visual de Victor (hard-refresh).
