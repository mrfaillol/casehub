/**
 * CaseHub.md — Editor frontend (Fatias 1-7 + 9)
 *
 * TipTap mount puro (sem Vue) com markdown round-trip via marked + turndown.
 * Stack via importmap jsdelivr (TipTap MIT + StarterKit + extensions + marked + turndown).
 * Sem build pipeline; Vue 3 entra se Fatia 3+ exigir SFC.
 *
 * Leis UX aplicadas:
 *   - Doherty: mirror reflete digitação em <500ms (sync onUpdate sem debounce).
 *   - Fitts: hit targets ≥36px desktop / ≥44px mobile (CSS via tokens).
 *   - Miller: toolbar em grupos ≤4 itens (markup no template).
 *   - Hick: modais reduzidos a 2 ações (Aceitar/Descartar, Abrir/Fechar).
 *   - Postel: ?doc=, ?doc_id=, ?d= aceitos; URL com/sem scheme.
 *
 * A11y:
 *   - Skip-link no topo (WCAG 2.4.1)
 *   - <dialog> nativos (focus trap automático, ESC fecha)
 *   - aria-live status bar; role=status nas atualizações
 *   - Keyboard shortcuts: Cmd/Ctrl+S = save Drive
 */

import { Editor } from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import Image from '@tiptap/extension-image';
import Link from '@tiptap/extension-link';
import Table from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableCell from '@tiptap/extension-table-cell';
import TableHeader from '@tiptap/extension-table-header';
import { marked } from 'marked';
import TurndownService from 'turndown';
import * as turndownGfm from '@joplin/turndown-plugin-gfm';

marked.use({ gfm: true, breaks: false });

const turndown = new TurndownService({
    headingStyle: 'atx',
    codeBlockStyle: 'fenced',
    bulletListMarker: '-',
    emDelimiter: '*',
});
// GFM plugin: tables, strikethrough, task-lists, autolinks
if (turndownGfm.gfm) turndown.use(turndownGfm.gfm);
else if (typeof turndownGfm.default === 'function') turndown.use(turndownGfm.default);

const DEFAULT_MD = `# CaseHub.md — Editor

Bem-vindo. Este é o editor de documentos markdown WYSIWYG do CaseHub.

## O que dá pra fazer

- escrever em **negrito**, *itálico*, ~~tachado~~ e [links](https://example.com)
- listas, citações, tabelas, code blocks
- exportar **DOCX** (Pandoc backend) para enviar ao Word
- **OCR** de PDF/imagem para extrair texto automaticamente
- pedir **sugestões do Maestro** AI para qualquer parágrafo
- salvar no **Google Drive** automaticamente (auto-save 3s)

> "Markdown é fonte canônica. JSON é runtime."

Atalhos:

| Ação | Atalho |
|---|---|
| Negrito | Cmd/Ctrl + B |
| Itálico | Cmd/Ctrl + I |
| Salvar no Drive | Cmd/Ctrl + S |

\`\`\`python
# code blocks com syntax básico
def hello():
    return "casehub.md"
\`\`\`
`;

const editorEl = document.getElementById('poc-editor');
const mdEl = document.getElementById('poc-markdown');
const toolbarEl = document.getElementById('poc-toolbar');
const loadBtn = document.getElementById('poc-load-md');
const docIdEl = document.getElementById('poc-doc-id');
const driveStatusEl = document.getElementById('poc-drive-status');
const mobileToggleBtn = document.getElementById('poc-mobile-toggle');
const mirrorCard = document.getElementById('poc-mirror-card');

/**
 * Resolve CaseHub PREFIX. Tries, in order:
 *   1. data-prefix em .casehub-md-shell (template app/casehub_md/index.html)
 *   2. window.CASEHUB_PREFIX (definido por app/base.html)
 */
function _shellEl() {
    return document.querySelector('.casehub-md-shell');
}
function resolvePrefix() {
    const fromShell = _shellEl()?.dataset?.prefix;
    if (typeof fromShell === 'string') return fromShell;
    if (typeof window.CASEHUB_PREFIX === 'string') return window.CASEHUB_PREFIX;
    return '';
}

/** Resolve the doc_id to load on mount, prefering server-provided ?doc=. */
const DOC_ID_STORAGE = 'casehub-md-doc-id';
function ensureDocId() {
    // 1. Server hint via .casehub-md-shell data-initial-doc-id.
    const fromBody = (_shellEl()?.dataset?.initialDocId || '').trim();
    if (fromBody) {
        localStorage.setItem(DOC_ID_STORAGE, fromBody);
        if (docIdEl) docIdEl.textContent = fromBody;
        return { id: fromBody, fromServer: true };
    }
    // 2. Persisted from previous session.
    let id = localStorage.getItem(DOC_ID_STORAGE);
    if (!id) {
        // 3. Generate fresh.
        id = (crypto?.randomUUID?.() || `doc-${Date.now()}`).slice(0, 36);
        localStorage.setItem(DOC_ID_STORAGE, id);
    }
    if (docIdEl) docIdEl.textContent = id;
    return { id, fromServer: false };
}

function setDriveStatus(symbol, label, tone = 'idle') {
    if (!driveStatusEl) return;
    driveStatusEl.textContent = `${symbol} Drive — ${label}`;
    driveStatusEl.dataset.tone = tone;
}

let syncing = false;

/** Update active-state of toolbar buttons based on current editor selection. */
function refreshToolbar(editor) {
    const buttons = toolbarEl.querySelectorAll('button[data-cmd]');
    buttons.forEach((btn) => {
        const cmd = btn.getAttribute('data-cmd');
        let active = false;
        switch (cmd) {
            case 'bold': active = editor.isActive('bold'); break;
            case 'italic': active = editor.isActive('italic'); break;
            case 'strike': active = editor.isActive('strike'); break;
            case 'h1': active = editor.isActive('heading', { level: 1 }); break;
            case 'h2': active = editor.isActive('heading', { level: 2 }); break;
            case 'h3': active = editor.isActive('heading', { level: 3 }); break;
            case 'bulletList': active = editor.isActive('bulletList'); break;
            case 'orderedList': active = editor.isActive('orderedList'); break;
            case 'blockquote': active = editor.isActive('blockquote'); break;
            case 'codeBlock': active = editor.isActive('codeBlock'); break;
            case 'link': active = editor.isActive('link'); break;
            case 'image': active = editor.isActive('image'); break;
            case 'table': active = editor.isActive('table'); break;
        }
        btn.classList.toggle('is-active', active);
    });
}

const editor = new Editor({
    element: editorEl,
    extensions: [
        StarterKit.configure({
            heading: { levels: [1, 2, 3, 4] },
        }),
        Image.configure({
            inline: false,
            allowBase64: false,
            HTMLAttributes: { class: 'md-img' },
        }),
        Link.configure({
            openOnClick: false,
            autolink: true,
            linkOnPaste: true,
            HTMLAttributes: { class: 'md-link', rel: 'noopener noreferrer', target: '_blank' },
        }),
        Table.configure({ resizable: false, HTMLAttributes: { class: 'md-table' } }),
        TableRow,
        TableHeader,
        TableCell,
    ],
    content: marked.parse(DEFAULT_MD),
    onUpdate({ editor }) {
        if (syncing) return;
        const html = editor.getHTML();
        const md = turndown.turndown(html);
        syncing = true;
        mdEl.value = md;
        syncing = false;
        refreshToolbar(editor);
    },
    onSelectionUpdate({ editor }) {
        refreshToolbar(editor);
    },
    onCreate({ editor }) {
        mdEl.value = turndown.turndown(editor.getHTML());
        // Smoke-test hook: signal readiness via attribute (Playwright waits on this).
        editorEl.setAttribute('data-tiptap-ready', 'true');
        refreshToolbar(editor);
    },
});

// Markdown → editor (manual trigger to avoid feedback loop).
loadBtn.addEventListener('click', () => {
    const md = mdEl.value;
    const html = marked.parse(md);
    syncing = true;
    editor.commands.setContent(html, false);
    syncing = false;
    refreshToolbar(editor);
});

/** Postel: aceitar URL com/sem protocol; auto-prefix https:// quando faltar. */
function normalizeUrl(raw) {
    const v = (raw || '').trim();
    if (!v) return null;
    if (/^[a-z][a-z0-9+.-]*:/i.test(v)) return v; // já tem scheme
    if (v.startsWith('//')) return `https:${v}`;
    if (v.startsWith('mailto:') || v.startsWith('#') || v.startsWith('/')) return v;
    return `https://${v}`;
}

const COMMANDS = {
    bold: (e) => e.chain().focus().toggleBold().run(),
    italic: (e) => e.chain().focus().toggleItalic().run(),
    strike: (e) => e.chain().focus().toggleStrike().run(),
    h1: (e) => e.chain().focus().toggleHeading({ level: 1 }).run(),
    h2: (e) => e.chain().focus().toggleHeading({ level: 2 }).run(),
    h3: (e) => e.chain().focus().toggleHeading({ level: 3 }).run(),
    bulletList: (e) => e.chain().focus().toggleBulletList().run(),
    orderedList: (e) => e.chain().focus().toggleOrderedList().run(),
    blockquote: (e) => e.chain().focus().toggleBlockquote().run(),
    codeBlock: (e) => e.chain().focus().toggleCodeBlock().run(),
    // Fatia 3 — embeds
    link: (e) => {
        // Toggle: se já tiver link no cursor, remove; senão prompt URL.
        if (e.isActive('link')) {
            e.chain().focus().unsetLink().run();
            return;
        }
        const url = normalizeUrl(window.prompt('URL do link:'));
        if (!url) return;
        e.chain().focus().extendMarkRange('link').setLink({ href: url }).run();
    },
    image: (e) => {
        const url = normalizeUrl(window.prompt('URL da imagem (Fatia 5 troca por upload Drive):'));
        if (!url) return;
        e.chain().focus().setImage({ src: url, alt: 'imagem' }).run();
    },
    table: (e) => {
        e.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run();
    },
    // Fatia 5 — Drive sync (manual save)
    driveSave: async (_editor, btn) => {
        await saveToDrive({ manual: true, btn });
    },
    // Fatia 9 — Abrir doc do Drive
    driveOpen: async (_editor, _btn) => {
        await openDocDialog();
    },
    // Fatia 7 — Maestro suggestion para parágrafo atual
    maestro: async (editorInstance, btn) => {
        await requestMaestroSuggestion(editorInstance, btn);
    },
    // Fatia 6 — OCR PDF/imagem via Tesseract backend
    ocr: async (e, btn) => {
        const input = document.getElementById('poc-ocr-input');
        if (!input) return;
        // Reset value so picking the same file again still triggers `change`.
        input.value = '';
        input.click();
        input.onchange = async () => {
            const f = input.files && input.files[0];
            if (!f) return;
            await runOcr(e, btn, f);
        };
    },
    // Fatia 4 — export DOCX via backend Pandoc (template default Pandoc)
    exportDocx: async (_editor, btn) => {
        await runDocxExport(btn, null);
    },
    // Fatia 4.1 — export DOCX com template OAB (Times 12pt, margens 3/3/2/2cm, justify, 1.5)
    exportDocxOab: async (_editor, btn) => {
        await runDocxExport(btn, 'oab');
    },
};

toolbarEl.addEventListener('click', (ev) => {
    const btn = ev.target.closest('button[data-cmd]');
    if (!btn) return;
    const cmd = btn.getAttribute('data-cmd');
    const fn = COMMANDS[cmd];
    if (fn) fn(editor, btn);
});

// ---------- Fatia 4 + 4.1 — DOCX export helper ----------

async function runDocxExport(btn, template /* null | 'oab' */) {
    if (btn) {
        btn.disabled = true;
        btn.dataset.prevLabel = btn.textContent;
        btn.textContent = '… exportando';
    }
    try {
        const markdown = mdEl.value;
        const prefix = resolvePrefix();
        const url = `${prefix}/casehub-md/export/docx`;
        const ts = new Date().toISOString().replace(/[:T]/g, '-').slice(0, 16);
        const tag = template ? `-${template}` : '';
        const filename = `casehub-md${tag}-${ts}`;

        const body = { markdown, filename };
        if (template) body.template = template;

        const resp = await fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        if (resp.status === 503) {
            alert(
                'Pandoc não está instalado no servidor.\n\n' +
                'Peça ao admin: apt install pandoc'
            );
            return;
        }
        if (!resp.ok) {
            const text = await resp.text().catch(() => '');
            alert(`Export DOCX falhou (HTTP ${resp.status}). ${text.slice(0, 200)}`);
            return;
        }

        const blob = await resp.blob();
        const dlUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = dlUrl;
        a.download = `${filename}.docx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(dlUrl), 1000);
    } catch (err) {
        alert(`Erro inesperado no export: ${err.message || err}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            if (btn.dataset.prevLabel) {
                btn.textContent = btn.dataset.prevLabel;
                delete btn.dataset.prevLabel;
            }
        }
    }
}

// ---------- Fatia 7 — Maestro suggestion (proxy → Maestro backend) ----------

/** Read the current paragraph text from TipTap. Falls back to user selection. */
function currentParagraphText(editorInstance) {
    const { from, to, empty } = editorInstance.state.selection;
    if (!empty) {
        return editorInstance.state.doc.textBetween(from, to, '\n', '\n').trim();
    }
    // Walk up the node tree to find the enclosing paragraph/heading.
    const $pos = editorInstance.state.doc.resolve(from);
    for (let depth = $pos.depth; depth > 0; depth--) {
        const node = $pos.node(depth);
        if (['paragraph', 'heading', 'blockquote', 'listItem'].includes(node.type.name)) {
            return node.textContent.trim();
        }
    }
    return editorInstance.state.doc.textBetween(0, editorInstance.state.doc.content.size, '\n', '\n').trim();
}

function getCaseIdFromUrl() {
    const params = new URLSearchParams(window.location.search);
    // Postel: aceita ?case_id= ou ?case=
    return params.get('case_id') || params.get('case') || null;
}

async function requestMaestroSuggestion(editorInstance, btn) {
    const paragraph = currentParagraphText(editorInstance);
    if (!paragraph || paragraph.length < 4) {
        alert('Selecione um parágrafo ou posicione o cursor num parágrafo com pelo menos 4 caracteres.');
        return;
    }
    if (btn) {
        btn.disabled = true;
        btn.dataset.prevLabel = btn.textContent;
        btn.textContent = '… pensando';
    }
    try {
        const prefix = resolvePrefix();
        const url = `${prefix}/casehub-md/maestro/suggest`;
        const resp = await fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                paragraph,
                case_id: getCaseIdFromUrl(),
            }),
        });

        if (resp.status === 503) {
            alert('Maestro indisponível (backend offline ou ainda em desenvolvimento).');
            return;
        }
        if (resp.status === 504) { alert('Maestro demorou demais (timeout).'); return; }
        if (resp.status === 413) { alert('Parágrafo grande demais (limite 16 KB).'); return; }
        if (!resp.ok) {
            const text = await resp.text().catch(() => '');
            alert(`Maestro falhou (HTTP ${resp.status}). ${text.slice(0, 200)}`);
            return;
        }

        const data = await resp.json();
        const suggestion = (data.suggestion || '').trim();
        if (!suggestion) {
            alert('Maestro respondeu vazio. Tente um parágrafo mais específico.');
            return;
        }
        openMaestroDialog({
            editorInstance,
            paragraph,
            suggestion,
            model: data.model || '',
            tookMs: data.took_ms || 0,
        });
    } catch (err) {
        alert(`Erro inesperado no Maestro: ${err.message || err}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            if (btn.dataset.prevLabel) {
                btn.textContent = btn.dataset.prevLabel;
                delete btn.dataset.prevLabel;
            }
        }
    }
}

const maestroDialog = document.getElementById('poc-maestro-dialog');
const maestroOriginalEl = document.getElementById('poc-maestro-original');
const maestroSuggestionEl = document.getElementById('poc-maestro-suggestion');
const maestroMetaEl = document.getElementById('poc-maestro-meta');
let maestroPending = null; // {editor, paragraph, suggestion, ...}

function openMaestroDialog(payload) {
    maestroPending = payload;
    if (maestroOriginalEl) maestroOriginalEl.textContent = payload.paragraph;
    if (maestroSuggestionEl) maestroSuggestionEl.innerHTML = marked.parse(payload.suggestion);
    if (maestroMetaEl) {
        const meta = [
            payload.model && `model: ${payload.model}`,
            payload.tookMs && `${payload.tookMs}ms`,
        ].filter(Boolean).join(' · ');
        maestroMetaEl.textContent = meta;
    }
    if (maestroDialog && typeof maestroDialog.showModal === 'function') {
        maestroDialog.showModal();
    } else if (maestroDialog) {
        maestroDialog.setAttribute('open', '');
    }
}

function closeMaestroDialog() {
    maestroPending = null;
    if (maestroDialog) {
        if (typeof maestroDialog.close === 'function') maestroDialog.close();
        else maestroDialog.removeAttribute('open');
    }
}

if (maestroDialog) {
    maestroDialog.addEventListener('click', (ev) => {
        const target = ev.target.closest('[data-action]');
        if (!target) return;
        const action = target.getAttribute('data-action');
        if (action === 'close' || action === 'discard') {
            closeMaestroDialog();
            return;
        }
        if (action === 'accept' && maestroPending) {
            const { editorInstance, suggestion } = maestroPending;
            const html = marked.parse('\n\n' + suggestion + '\n');
            editorInstance.chain().focus().insertContent(html).run();
            closeMaestroDialog();
        }
    });
}

// ---------- Fatia 6 — OCR (PDF/image → markdown via Tesseract backend) ----------

async function runOcr(editorInstance, btn, file) {
    if (btn) {
        btn.disabled = true;
        btn.dataset.prevLabel = btn.textContent;
        btn.textContent = '… OCR';
    }
    try {
        const prefix = resolvePrefix();
        const url = `${prefix}/casehub-md/ocr?lang=por%2Beng`;
        const form = new FormData();
        form.append('file', file, file.name);
        const resp = await fetch(url, { method: 'POST', credentials: 'same-origin', body: form });

        if (resp.status === 503) {
            alert(
                'OCR backend offline.\n\n' +
                'Peça ao admin: apt install tesseract-ocr poppler-utils tesseract-ocr-por'
            );
            return;
        }
        if (resp.status === 413) { alert('Arquivo grande demais (limite 10 MB).'); return; }
        if (resp.status === 422) { alert('PDF longo demais (limite 50 páginas).'); return; }
        if (resp.status === 415) { alert('Tipo de arquivo não suportado.'); return; }
        if (resp.status === 504) { alert('OCR demorou demais (timeout). Tente um arquivo menor.'); return; }
        if (!resp.ok) {
            const text = await resp.text().catch(() => '');
            alert(`OCR falhou (HTTP ${resp.status}). ${text.slice(0, 200)}`);
            return;
        }

        const data = await resp.json();
        const md = (data.markdown || '').trim();
        if (!md) {
            alert('OCR não retornou texto. Arquivo pode estar em branco ou ilegível.');
            return;
        }
        // Insert into the editor at the current cursor as parsed HTML.
        const html = marked.parse(md);
        editorInstance.chain().focus().insertContent(html).run();

        // Confirm in the markdown mirror & status bar.
        const tag = data.pages ? `${data.source} · ${data.pages}p · ${data.took_ms}ms` : `${data.source} · ${data.took_ms}ms`;
        setDriveStatus('●', `OCR inserido (${tag})`, 'ok');
    } catch (err) {
        alert(`Erro inesperado no OCR: ${err.message || err}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            if (btn.dataset.prevLabel) {
                btn.textContent = btn.dataset.prevLabel;
                delete btn.dataset.prevLabel;
            }
        }
    }
}

// ---------- Fatia 5 — Drive sync (auto-save debounced + manual button) ----------
// ---------- Fatia 5.1 — load on mount via ?doc=<id> -----------------------------
// ---------- Fatia 9 — Abrir doc do Drive (listagem modal) -----------------------

const { id: DOC_ID, fromServer: DOC_FROM_SERVER } = ensureDocId();
const PREFIX = resolvePrefix();
const DRIVE_SAVE_URL = `${PREFIX}/casehub-md/drive/save`;
const DRIVE_LIST_URL = `${PREFIX}/casehub-md/drive/list`;
const DRIVE_LOAD_URL = (id) => `${PREFIX}/casehub-md/drive/${encodeURIComponent(id)}`;
const AUTOSAVE_DEBOUNCE_MS = 3000;

let autosaveTimer = null;
let saveInFlight = false;
let lastSavedMd = null;
let suppressAutosaveOnce = false;

async function saveToDrive({ manual = false, btn = null } = {}) {
    if (saveInFlight) return;
    const markdown = mdEl.value;
    if (!manual && markdown === lastSavedMd) return; // nothing to save

    saveInFlight = true;
    if (btn) {
        btn.disabled = true;
        btn.dataset.prevLabel = btn.textContent;
        btn.textContent = '… salvando';
    }
    setDriveStatus('⟳', 'salvando…', 'busy');

    try {
        const resp = await fetch(DRIVE_SAVE_URL, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ doc_id: DOC_ID, markdown }),
        });
        if (resp.status === 503) {
            setDriveStatus('○', 'offline (sem credenciais)', 'offline');
            if (manual) alert('Drive offline. Verifique credentials/token no servidor.');
            return;
        }
        if (!resp.ok) {
            const text = await resp.text().catch(() => '');
            setDriveStatus('✕', `falhou HTTP ${resp.status}`, 'error');
            if (manual) alert(`Drive save falhou (${resp.status}). ${text.slice(0, 200)}`);
            return;
        }
        const data = await resp.json();
        lastSavedMd = markdown;
        const ts = (data.updated_at || new Date().toISOString()).slice(11, 16);
        setDriveStatus('●', `salvo às ${ts}`, 'ok');
    } catch (err) {
        setDriveStatus('✕', `erro: ${err.message || err}`, 'error');
        if (manual) alert(`Erro inesperado: ${err.message || err}`);
    } finally {
        saveInFlight = false;
        if (btn) {
            btn.disabled = false;
            if (btn.dataset.prevLabel) {
                btn.textContent = btn.dataset.prevLabel;
                delete btn.dataset.prevLabel;
            }
        }
    }
}

/** Debounce wrapper called every editor onUpdate. */
function scheduleAutosave() {
    if (suppressAutosaveOnce) { suppressAutosaveOnce = false; return; }
    if (autosaveTimer) clearTimeout(autosaveTimer);
    autosaveTimer = setTimeout(() => saveToDrive({ manual: false }), AUTOSAVE_DEBOUNCE_MS);
}

// Hook into editor lifecycle.
editor.on('update', scheduleAutosave);

// Fatia 5.1 — load on mount. If doc_id came from server (?doc=) ou existia em
// localStorage, tenta carregar do Drive. Falha 404 = doc novo, sem barulho.
async function loadDocOnMount() {
    try {
        const resp = await fetch(DRIVE_LOAD_URL(DOC_ID), { credentials: 'same-origin' });
        if (resp.status === 503) { setDriveStatus('○', 'offline (sem credenciais)', 'offline'); return; }
        if (resp.status === 404) { setDriveStatus('○', 'doc novo', 'idle'); return; }
        if (resp.ok) {
            const data = await resp.json();
            const md = (data.markdown || '').trim();
            if (md) {
                suppressAutosaveOnce = true;
                const html = marked.parse(md);
                syncing = true;
                editor.commands.setContent(html, false);
                mdEl.value = md;
                lastSavedMd = md;
                syncing = false;
                refreshToolbar(editor);
                const ts = (data.updated_at || '').slice(11, 16);
                setDriveStatus('●', `carregado · ${ts || 'recente'}`, 'ok');
                return;
            }
            setDriveStatus('○', 'doc vazio', 'idle');
            return;
        }
        setDriveStatus('○', `indisponível (${resp.status})`, 'offline');
    } catch {
        setDriveStatus('○', 'erro de rede', 'offline');
    }
}

// Initial probe + load. Always run; safe if Drive offline (503 graceful).
loadDocOnMount();

// ---------- Modal "Abrir doc" (Fatia 9) ----------------------------------------

const openDialog = document.getElementById('poc-open-dialog');
const openListEl = document.getElementById('poc-open-list');
const openStatusEl = document.getElementById('poc-open-status');

function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

async function openDocDialog() {
    if (!openDialog || !openListEl) return;
    openListEl.innerHTML = '';
    if (openStatusEl) openStatusEl.textContent = 'Carregando lista do Drive…';
    if (typeof openDialog.showModal === 'function') openDialog.showModal();
    else openDialog.setAttribute('open', '');

    try {
        const resp = await fetch(DRIVE_LIST_URL, { credentials: 'same-origin' });
        if (resp.status === 503) {
            if (openStatusEl) openStatusEl.textContent = 'Drive offline (sem credenciais).';
            return;
        }
        if (!resp.ok) {
            if (openStatusEl) openStatusEl.textContent = `Falhou (HTTP ${resp.status}).`;
            return;
        }
        const data = await resp.json();
        const items = data.items || [];
        if (!items.length) {
            if (openStatusEl) openStatusEl.textContent = 'Nenhum documento ainda em /CaseHubMD/.';
            return;
        }
        if (openStatusEl) openStatusEl.textContent = `${items.length} documento${items.length === 1 ? '' : 's'} recente${items.length === 1 ? '' : 's'}.`;
        const frag = document.createDocumentFragment();
        for (const it of items) {
            const li = document.createElement('li');
            li.className = 'md-doc-list-item';
            li.setAttribute('role', 'option');
            li.setAttribute('tabindex', '0');
            li.dataset.docId = it.doc_id || '';
            li.innerHTML = `
                <span class="md-doc-list-name">${(it.filename || it.doc_id || '').replace(/[<>&]/g, c => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))}</span>
                <span class="md-doc-list-meta">${formatDate(it.updated_at)}</span>
            `;
            const choose = () => switchToDoc(it.doc_id);
            li.addEventListener('click', choose);
            li.addEventListener('keydown', (ev) => {
                if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); choose(); }
            });
            frag.appendChild(li);
        }
        openListEl.appendChild(frag);
    } catch (err) {
        if (openStatusEl) openStatusEl.textContent = `Erro: ${err.message || err}`;
    }
}

function closeOpenDialog() {
    if (!openDialog) return;
    if (typeof openDialog.close === 'function') openDialog.close();
    else openDialog.removeAttribute('open');
}

async function switchToDoc(newDocId) {
    if (!newDocId || newDocId === DOC_ID) { closeOpenDialog(); return; }
    // Navigation via querystring keeps URL shareable + triggers full reload (safe state).
    const url = new URL(window.location.href);
    url.searchParams.set('doc', newDocId);
    window.location.href = url.toString();
}

if (openDialog) {
    openDialog.addEventListener('click', (ev) => {
        const action = ev.target.closest('[data-action]')?.getAttribute('data-action');
        if (action === 'close') closeOpenDialog();
    });
}

// ---------- Mobile mirror toggle -----------------------------------------------

if (mobileToggleBtn && mirrorCard) {
    mobileToggleBtn.addEventListener('click', () => {
        const open = mirrorCard.classList.toggle('is-open');
        mobileToggleBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
}

// ---------- Keyboard shortcut Cmd/Ctrl+S = save Drive --------------------------

document.addEventListener('keydown', (ev) => {
    if ((ev.metaKey || ev.ctrlKey) && (ev.key === 's' || ev.key === 'S')) {
        ev.preventDefault();
        const btn = toolbarEl?.querySelector('button[data-cmd="driveSave"]');
        saveToDrive({ manual: true, btn });
    }
});

// Debug/test handle.
window.__casehubMd = {
    editor, marked, turndown, refreshToolbar, saveToDrive, openDocDialog,
    DOC_ID, DOC_FROM_SERVER, PREFIX,
};
// Backward-compat alias.
window.__casehubMdPoc = window.__casehubMd;
