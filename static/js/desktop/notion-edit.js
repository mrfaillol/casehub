/* ==========================================================================
 * notion-edit.js — camada de edit inline tipo Notion pra templates CaseHub
 *
 * Templates opt-in marcando blocos: <div data-editable-block="intro">...</div>
 * Suporta: bold/italic/underline, H1-H3, bullet/numbered list, link, markdown-aware.
 * Persiste via POST /casehub/api/notes/<key>/<blockId> (user-scoped, best-effort).
 *
 * Requisitos do plano: `agents/curator-ui-ux.md` + trilha B.4 do plano master.
 * Budget: ≤5MB heap delta, ≤3 GPU layers, ≤16ms/frame p95.
 * ======================================================================== */

(function() {
  'use strict';

  const TOOLBAR_HTML = `
    <button data-cmd="bold" title="Negrito (⌘B)"><b>B</b></button>
    <button data-cmd="italic" title="Itálico (⌘I)"><i>I</i></button>
    <button data-cmd="underline" title="Sublinhado (⌘U)"><u>U</u></button>
    <span class="sep"></span>
    <button data-cmd="h1" title="Título 1">H1</button>
    <button data-cmd="h2" title="Título 2">H2</button>
    <button data-cmd="h3" title="Título 3">H3</button>
    <span class="sep"></span>
    <button data-cmd="ul" title="Lista">•</button>
    <button data-cmd="ol" title="Numerada">1.</button>
    <button data-cmd="link" title="Link (⌘K)">🔗</button>
  `;

  const TOOLBAR_CSS = `
    .ne-toolbar {
      position: fixed; display: none; gap: 2px;
      background: var(--surface-2, rgba(20,20,25,0.92));
      color: var(--text, #fff);
      border: 1px solid var(--border, rgba(255,255,255,0.08));
      border-radius: 10px;
      padding: 4px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.3);
      backdrop-filter: blur(20px);
      z-index: 100000;
      font-size: 13px;
      opacity: 0;
      transform: translateY(4px);
      transition: opacity 150ms, transform 150ms;
    }
    .ne-toolbar.visible { display: flex; opacity: 1; transform: translateY(0); }
    .ne-toolbar button {
      background: transparent; border: none; color: inherit;
      padding: 6px 10px; border-radius: 6px; cursor: pointer;
      min-width: 28px; font-family: inherit; font-size: inherit;
      transition: background 150ms;
    }
    .ne-toolbar button:hover { background: rgba(255,255,255,0.08); }
    .ne-toolbar .sep { width: 1px; background: rgba(255,255,255,0.12); margin: 4px 2px; }
    [data-editable-block] {
      outline: none; border-radius: 6px;
      padding: 4px 8px; margin: -4px -8px;
      transition: background 150ms;
    }
    [data-editable-block]:hover:not(:focus) {
      background: var(--surface-3, rgba(0,0,0,0.03));
    }
    [data-editable-block]:focus {
      background: var(--surface-2, rgba(0,0,0,0.04));
      box-shadow: inset 0 0 0 1px var(--accent, #0EA5E9);
    }
  `;

  let toolbar = null;
  let currentBlock = null;
  let saveTimer = null;

  function injectToolbar() {
    if (toolbar) return toolbar;
    const style = document.createElement('style');
    style.textContent = TOOLBAR_CSS;
    document.head.appendChild(style);

    toolbar = document.createElement('div');
    toolbar.className = 'ne-toolbar';
    toolbar.innerHTML = TOOLBAR_HTML;
    document.body.appendChild(toolbar);

    toolbar.addEventListener('mousedown', (e) => e.preventDefault()); // não tira foco
    toolbar.addEventListener('click', (e) => {
      const btn = e.target.closest('button');
      if (!btn || !currentBlock) return;
      applyCommand(btn.dataset.cmd);
      scheduleSave();
    });
    return toolbar;
  }

  function applyCommand(cmd) {
    currentBlock.focus();
    switch (cmd) {
      case 'bold':
      case 'italic':
      case 'underline':
        document.execCommand(cmd);
        break;
      case 'h1': case 'h2': case 'h3':
        document.execCommand('formatBlock', false, cmd.toUpperCase());
        break;
      case 'ul': document.execCommand('insertUnorderedList'); break;
      case 'ol': document.execCommand('insertOrderedList'); break;
      case 'link': {
        const url = prompt('URL do link:');
        if (url) document.execCommand('createLink', false, url);
        break;
      }
    }
  }

  function showToolbar() {
    const sel = window.getSelection();
    if (!sel.rangeCount || sel.isCollapsed || !currentBlock) {
      hideToolbar();
      return;
    }
    const range = sel.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    if (!rect.width && !rect.height) { hideToolbar(); return; }
    injectToolbar();
    toolbar.classList.add('visible');
    const tbRect = toolbar.getBoundingClientRect();
    const top = Math.max(8, rect.top - tbRect.height - 8);
    const left = Math.max(8, Math.min(window.innerWidth - tbRect.width - 8, rect.left + rect.width / 2 - tbRect.width / 2));
    toolbar.style.top = top + 'px';
    toolbar.style.left = left + 'px';
  }

  function hideToolbar() {
    if (toolbar) toolbar.classList.remove('visible');
  }

  function scheduleSave() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(persistBlock, 800);
  }

  async function persistBlock() {
    if (!currentBlock) return;
    const key = currentBlock.dataset.editableBlock;
    const content = currentBlock.innerHTML;
    const pageKey = (location.pathname.replace(/^\/casehub\/?/, '').replace(/\/+$/, '').replace(/\//g, '-') || 'home');
    try {
      await fetch(`/casehub/api/notes/${encodeURIComponent(pageKey)}/${encodeURIComponent(key)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      });
    } catch(e) { /* best-effort — não bloqueia UX */ }
  }

  function enableBlock(el) {
    if (el.dataset.neEnabled) return;
    el.dataset.neEnabled = '1';
    el.contentEditable = 'true';
    el.spellcheck = true;
    el.addEventListener('focus', () => { currentBlock = el; });
    el.addEventListener('mouseup', showToolbar);
    el.addEventListener('keyup', (e) => {
      if (['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) showToolbar();
      scheduleSave();
    });
    el.addEventListener('blur', () => {
      setTimeout(() => { if (!toolbar || !toolbar.contains(document.activeElement)) hideToolbar(); }, 150);
      scheduleSave();
    });
    // Keyboard shortcut: ⌘K para link
    el.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        applyCommand('link');
        scheduleSave();
      }
    });
  }

  function scan(root = document) {
    root.querySelectorAll('[data-editable-block]').forEach(enableBlock);
  }

  // Hidrata blocos persistidos do backend na inicialização (1 GET por página)
  async function hydrate() {
    const pageKey = (location.pathname.replace(/^\/casehub\/?/, '').replace(/\/+$/, '').replace(/\//g, '-') || 'home');
    try {
      const r = await fetch(`/casehub/api/notes/${encodeURIComponent(pageKey)}`, { credentials: 'same-origin' });
      if (!r.ok) return;
      const { blocks = {} } = await r.json();
      Object.entries(blocks).forEach(([k, html]) => {
        document.querySelectorAll(`[data-editable-block="${CSS.escape(k)}"]`).forEach(el => {
          // Só sobrescreve se ainda não editado nesta sessão
          if (!el.dataset.neHydrated) { el.innerHTML = html; el.dataset.neHydrated = '1'; }
        });
      });
    } catch(e) { /* best-effort */ }
  }

  // Auto-scan on DOM ready + hidratação inicial + observa mutations
  const boot = () => { scan(); hydrate(); };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  const mo = new MutationObserver((mutations) => {
    for (const m of mutations) {
      m.addedNodes.forEach(n => {
        if (n.nodeType === 1) {
          if (n.matches?.('[data-editable-block]')) enableBlock(n);
          n.querySelectorAll?.('[data-editable-block]').forEach(enableBlock);
        }
      });
    }
  });
  mo.observe(document.body, { childList: true, subtree: true });

  // Expose pra debug / opt-in programático
  window.NotionEdit = { scan, enableBlock };
})();
