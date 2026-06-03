(function () {
  'use strict';

  var root = document.querySelector('[data-casehub-md]');
  if (!root) return;

  var prefix = root.getAttribute('data-prefix') || window.CASEHUB_PREFIX || '/casehub';
  var source = document.getElementById('chMdSource');
  var preview = document.getElementById('chMdPreview');
  var titleInput = document.getElementById('chMdTitle');
  var docIdEl = document.getElementById('chMdDocId');
  var statusEl = document.getElementById('chMdStatus');
  var docList = document.getElementById('chMdDocList');
  var folderList = document.getElementById('chMdExplorerFolders');
  var ocrInput = document.getElementById('chMdOcrInput');

  var storageKey = 'casehub.md.inline';
  var docId = root.getAttribute('data-doc-id') || '';
  var syncingPreview = false;
  var driveItems = [];
  var explorerSource = 'all';
  var explorerFolder = 'recent';

  var defaultMarkdown = [
    '# CaseHub.md',
    '',
    '## Resumo',
    '',
    '- Cliente:',
    '- Caso:',
    '- Proxima acao:',
    '',
    '## Notas',
    '',
    'Digite aqui.'
  ].join('\n');

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function setStatus(text, tone) {
    if (!statusEl) return;
    statusEl.textContent = text;
    statusEl.dataset.tone = tone || 'idle';
  }

  function ensureDocId() {
    if (docId) return docId;
    try {
      docId = localStorage.getItem('casehub.md.docId') || '';
      if (!docId && window.crypto && window.crypto.randomUUID) {
        docId = window.crypto.randomUUID().slice(0, 36);
      }
    } catch (err) {}
    if (!docId) docId = 'doc-' + Date.now();
    try { localStorage.setItem('casehub.md.docId', docId); } catch (err) {}
    return docId;
  }

  function inlineMarkdown(text) {
    var html = escapeHtml(text);
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+|mailto:[^)\s]+)\)/g, function (_m, label, href) {
      return '<a href="' + escapeHtml(href) + '" target="_blank" rel="noopener noreferrer">' + label + '</a>';
    });
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/~~([^~]+)~~/g, '<del>$1</del>');
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    return html;
  }

  function closeList(state, out) {
    if (state.list) {
      out.push('</' + state.list + '>');
      state.list = '';
    }
  }

  function renderTable(lines, start) {
    var rows = [];
    var i = start;
    while (i < lines.length && /\|/.test(lines[i])) {
      rows.push(lines[i]);
      i += 1;
    }
    if (rows.length < 2 || !/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(rows[1])) {
      return null;
    }
    var bodyRows = rows.slice(0, 1).concat(rows.slice(2));
    var html = ['<table>'];
    bodyRows.forEach(function (row, idx) {
      var cells = row.replace(/^\||\|$/g, '').split('|').map(function (cell) { return inlineMarkdown(cell.trim()); });
      html.push(idx === 0 ? '<thead><tr>' : '<tr>');
      cells.forEach(function (cell) { html.push(idx === 0 ? '<th>' + cell + '</th>' : '<td>' + cell + '</td>'); });
      html.push(idx === 0 ? '</tr></thead><tbody>' : '</tr>');
    });
    html.push('</tbody></table>');
    return { html: html.join(''), next: i };
  }

  function renderMarkdown(md) {
    var lines = String(md || '').split(/\r?\n/);
    var out = [];
    var state = { list: '', code: false, codeLines: [] };

    for (var i = 0; i < lines.length; i += 1) {
      var line = lines[i];

      if (/^```/.test(line.trim())) {
        if (state.code) {
          out.push('<pre><code>' + escapeHtml(state.codeLines.join('\n')) + '</code></pre>');
          state.code = false;
          state.codeLines = [];
        } else {
          closeList(state, out);
          state.code = true;
        }
        continue;
      }

      if (state.code) {
        state.codeLines.push(line);
        continue;
      }

      if (!line.trim()) {
        closeList(state, out);
        continue;
      }

      var table = renderTable(lines, i);
      if (table) {
        closeList(state, out);
        out.push(table.html);
        i = table.next - 1;
        continue;
      }

      var heading = line.match(/^(#{1,3})\s+(.+)$/);
      if (heading) {
        closeList(state, out);
        var level = heading[1].length;
        out.push('<h' + level + '>' + inlineMarkdown(heading[2]) + '</h' + level + '>');
        continue;
      }

      var quote = line.match(/^>\s?(.+)$/);
      if (quote) {
        closeList(state, out);
        out.push('<blockquote>' + inlineMarkdown(quote[1]) + '</blockquote>');
        continue;
      }

      var unordered = line.match(/^\s*[-*]\s+(.+)$/);
      var ordered = line.match(/^\s*\d+\.\s+(.+)$/);
      if (unordered || ordered) {
        var type = unordered ? 'ul' : 'ol';
        if (state.list && state.list !== type) closeList(state, out);
        if (!state.list) {
          state.list = type;
          out.push('<' + type + '>');
        }
        out.push('<li>' + inlineMarkdown((unordered || ordered)[1]) + '</li>');
        continue;
      }

      closeList(state, out);
      out.push('<p>' + inlineMarkdown(line) + '</p>');
    }

    closeList(state, out);
    if (state.code) out.push('<pre><code>' + escapeHtml(state.codeLines.join('\n')) + '</code></pre>');
    return out.join('\n') || '<p></p>';
  }

  function saveLocal() {
    try {
      localStorage.setItem(storageKey, JSON.stringify({
        docId: ensureDocId(),
        title: getFilenameBase(),
        markdown: source.value || '',
        updatedAt: new Date().toISOString()
      }));
    } catch (err) {}
  }

  function getFilenameBase() {
    var raw = (titleInput && titleInput.value ? titleInput.value : 'CaseHub.md').trim();
    return raw.replace(/\.(md|docx)$/i, '') || 'CaseHub.md';
  }

  function getMarkdownFilename() {
    return getFilenameBase().replace(/\.md$/i, '') + '.md';
  }

  function getLocalDocItem() {
    var updatedAt = '';
    try {
      var restored = JSON.parse(localStorage.getItem(storageKey) || 'null');
      updatedAt = restored && restored.updatedAt ? restored.updatedAt : '';
    } catch (err) {}
    return {
      doc_id: ensureDocId(),
      filename: getMarkdownFilename(),
      updated_at: updatedAt || 'Local',
      source: 'local',
      folder: 'Rascunhos'
    };
  }

  function normalizeDocItem(item) {
    var filename = item.filename || item.name || item.title || item.doc_id || 'Documento';
    var sourceName = item.source || item.provider || (item.drive_id || item.google_doc_url ? 'drive' : 'drive');
    var folder = item.folder || item.folder_name || item.parent_name || item.category || '';
    if (!folder && filename.indexOf('/') > -1) folder = filename.split('/').slice(0, -1).join('/');
    if (!folder) folder = sourceName === 'local' ? 'Rascunhos' : 'Recentes';
    return {
      doc_id: item.doc_id || item.id || item.drive_id || filename,
      filename: filename.split('/').pop(),
      updated_at: item.updated_at || item.modified_time || item.modifiedTime || '',
      source: sourceName,
      folder: folder
    };
  }

  function formatDocDate(value) {
    if (!value) return '';
    if (value === 'Local') return value;
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
  }

  function getExplorerItems() {
    var local = getLocalDocItem();
    var items = driveItems.map(normalizeDocItem);
    if (!items.some(function (item) { return item.source === 'local' && item.doc_id === local.doc_id; })) {
      items.unshift(local);
    }
    return items.filter(function (item) {
      return explorerSource === 'all' || item.source === explorerSource;
    });
  }

  function renderExplorer() {
    if (!docList) return;
    var items = getExplorerItems();
    var folders = ['Recentes'].concat(Array.from(new Set(items.map(function (item) { return item.folder || 'Recentes'; })))).filter(Boolean);
    folders = folders.filter(function (folder, index) { return folders.indexOf(folder) === index; });
    if (folders.indexOf(explorerFolder) === -1) explorerFolder = folders[0] || 'Recentes';

    if (folderList) {
      folderList.innerHTML = folders.map(function (folder) {
        var count = folder === 'Recentes' ? items.length : items.filter(function (item) { return item.folder === folder; }).length;
        return '<button type="button" class="ch-md__explorer-item ' + (folder === explorerFolder ? 'is-active' : '') + '" data-md-folder="' + escapeHtml(folder) + '">' +
          '<i data-lucide="' + (folder === 'Recentes' ? 'clock-3' : 'folder') + '"></i>' +
          '<span>' + escapeHtml(folder) + '</span>' +
          '<small>' + count + '</small>' +
          '</button>';
      }).join('');
    }

    var docs = explorerFolder === 'Recentes'
      ? items.slice(0, 12)
      : items.filter(function (item) { return item.folder === explorerFolder; });
    if (!docs.length) {
      docList.innerHTML = '<div class="ch-md__empty">Nenhum documento.</div>';
    } else {
      docList.innerHTML = docs.map(function (item) {
        var icon = item.source === 'local' ? 'file-pen-line' : 'file-text';
        return '<button type="button" class="ch-md__doc" data-doc-id="' + escapeHtml(item.doc_id) + '" data-doc-source="' + escapeHtml(item.source) + '">' +
          '<i data-lucide="' + icon + '"></i>' +
          '<span class="ch-md__doc-main">' +
          '<strong>' + escapeHtml(item.filename || item.doc_id) + '</strong>' +
          '<small>' + escapeHtml(item.source === 'local' ? 'Local' : 'Drive') + ' · ' + escapeHtml(formatDocDate(item.updated_at)) + '</small>' +
          '</span>' +
          '</button>';
      }).join('');
    }
    if (window.CHLucide) window.CHLucide.mount(root);
  }

  function render(options) {
    var preservePreview = options && options.preserveFocusedPreview && document.activeElement === preview;
    if (!preservePreview) {
      preview.innerHTML = renderMarkdown(source.value);
    }
    saveLocal();
    setStatus('Local salvo', 'ok');
  }

  function inlineToMarkdown(node) {
    if (!node) return '';
    if (node.nodeType === Node.TEXT_NODE) return node.textContent || '';
    if (node.nodeType !== Node.ELEMENT_NODE) return '';

    var tag = node.tagName.toLowerCase();
    var text = Array.prototype.map.call(node.childNodes, inlineToMarkdown).join('');
    if (tag === 'strong' || tag === 'b') return '**' + text + '**';
    if (tag === 'em' || tag === 'i') return '*' + text + '*';
    if (tag === 'del' || tag === 's') return '~~' + text + '~~';
    if (tag === 'code' && node.parentElement && node.parentElement.tagName.toLowerCase() !== 'pre') return '`' + text + '`';
    if (tag === 'a') {
      var href = node.getAttribute('href') || '';
      return href ? '[' + text + '](' + href + ')' : text;
    }
    if (tag === 'br') return '\n';
    return text;
  }

  function blockToMarkdown(node) {
    if (!node) return '';
    if (node.nodeType === Node.TEXT_NODE) return (node.textContent || '').trim();
    if (node.nodeType !== Node.ELEMENT_NODE) return '';

    var tag = node.tagName.toLowerCase();
    if (/^h[1-6]$/.test(tag)) {
      return new Array(Number(tag.charAt(1)) + 1).join('#') + ' ' + inlineToMarkdown(node).trim();
    }
    if (tag === 'ul' || tag === 'ol') {
      return Array.prototype.map.call(node.children, function (child, index) {
        if (child.tagName.toLowerCase() !== 'li') return '';
        return (tag === 'ol' ? (index + 1) + '. ' : '- ') + inlineToMarkdown(child).trim();
      }).filter(Boolean).join('\n');
    }
    if (tag === 'blockquote') {
      return inlineToMarkdown(node).trim().split(/\n/).map(function (line) { return '> ' + line; }).join('\n');
    }
    if (tag === 'pre') {
      return '```\n' + (node.textContent || '').trim() + '\n```';
    }
    if (tag === 'table') {
      var rows = Array.prototype.map.call(node.querySelectorAll('tr'), function (row) {
        return '| ' + Array.prototype.map.call(row.children, function (cell) {
          return inlineToMarkdown(cell).trim();
        }).join(' | ') + ' |';
      });
      if (rows.length > 1) rows.splice(1, 0, '| ' + Array.prototype.map.call(node.querySelectorAll('tr:first-child > *'), function () { return '---'; }).join(' | ') + ' |');
      return rows.join('\n');
    }
    if (tag === 'div' || tag === 'section' || tag === 'article') {
      var nested = Array.prototype.map.call(node.childNodes, blockToMarkdown).filter(Boolean);
      return nested.length ? nested.join('\n\n') : inlineToMarkdown(node).trim();
    }
    return inlineToMarkdown(node).trim();
  }

  function previewToMarkdown() {
    return Array.prototype.map.call(preview.childNodes, blockToMarkdown)
      .filter(function (part) { return part && part.trim(); })
      .join('\n\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  function syncPreviewToSource() {
    if (syncingPreview) return;
    syncingPreview = true;
    source.value = previewToMarkdown();
    saveLocal();
    setStatus('Preview editado', 'ok');
    syncingPreview = false;
  }

  function previewIsActive() {
    return preview && (document.activeElement === preview || preview.contains(document.activeElement));
  }

  function getPreviewSelection() {
    var selection = window.getSelection ? window.getSelection() : null;
    if (!selection || !selection.rangeCount) return null;
    if (!preview.contains(selection.anchorNode)) return null;
    return selection;
  }

  function insertPreviewHtml(html) {
    preview.focus();
    document.execCommand('insertHTML', false, html);
    syncPreviewToSource();
  }

  function runPreviewAction(action) {
    if (!previewIsActive()) return false;
    preview.focus();
    var selection = getPreviewSelection();
    var selected = selection ? selection.toString() : '';

    if (action === 'bold') document.execCommand('bold', false, null);
    else if (action === 'italic') document.execCommand('italic', false, null);
    else if (action === 'strike') document.execCommand('strikeThrough', false, null);
    else if (action === 'h1') document.execCommand('formatBlock', false, 'h1');
    else if (action === 'h2') document.execCommand('formatBlock', false, 'h2');
    else if (action === 'h3') document.execCommand('formatBlock', false, 'h3');
    else if (action === 'bullet') document.execCommand('insertUnorderedList', false, null);
    else if (action === 'ordered') document.execCommand('insertOrderedList', false, null);
    else if (action === 'quote') document.execCommand('formatBlock', false, 'blockquote');
    else if (action === 'code') insertPreviewHtml('<pre><code>' + escapeHtml(selected || 'codigo') + '</code></pre>');
    else if (action === 'link') {
      if (!selected) insertPreviewHtml('<a href="https://" target="_blank" rel="noopener noreferrer">link</a>');
      else document.execCommand('createLink', false, 'https://');
    } else if (action === 'table') {
      insertPreviewHtml('<table><thead><tr><th>Campo</th><th>Valor</th></tr></thead><tbody><tr><td>Cliente</td><td></td></tr><tr><td>Caso</td><td></td></tr></tbody></table>');
    } else {
      return false;
    }

    syncPreviewToSource();
    return true;
  }

  function getPreviewBlock(node) {
    var current = node && node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
    while (current && current !== preview && current.parentElement !== preview) {
      current = current.parentElement;
    }
    return current && current !== preview ? current : null;
  }

  function clearBlockAndFormat(block, tagName) {
    if (!block) return;
    block.textContent = '';
    var replacement = document.createElement(tagName);
    replacement.innerHTML = '<br>';
    preview.replaceChild(replacement, block);
    var range = document.createRange();
    range.selectNodeContents(replacement);
    range.collapse(true);
    var selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    syncPreviewToSource();
  }

  function handlePreviewMarkdownShortcut(event) {
    if (event.key !== ' ') return;
    var selection = getPreviewSelection();
    if (!selection || !selection.isCollapsed) return;
    var block = getPreviewBlock(selection.anchorNode);
    if (!block) return;
    var marker = (block.textContent || '').trim();
    if (!/^(#{1,3}|[-*]|1\.|>)$/.test(marker)) return;

    event.preventDefault();
    if (marker === '#') clearBlockAndFormat(block, 'h1');
    else if (marker === '##') clearBlockAndFormat(block, 'h2');
    else if (marker === '###') clearBlockAndFormat(block, 'h3');
    else if (marker === '>') clearBlockAndFormat(block, 'blockquote');
    else if (marker === '-' || marker === '*') {
      block.textContent = '';
      document.execCommand('insertUnorderedList', false, null);
      syncPreviewToSource();
    } else if (marker === '1.') {
      block.textContent = '';
      document.execCommand('insertOrderedList', false, null);
      syncPreviewToSource();
    }
  }

  function restore() {
    ensureDocId();
    if (docIdEl) docIdEl.textContent = docId;
    var restored = null;
    try { restored = JSON.parse(localStorage.getItem(storageKey) || 'null'); } catch (err) {}
    titleInput.value = (restored && restored.title) || 'CaseHub.md';
    source.value = (restored && restored.markdown) || defaultMarkdown;
    render();
  }

  function withSelection(before, after, placeholder) {
    var start = source.selectionStart;
    var end = source.selectionEnd;
    var selected = source.value.slice(start, end) || placeholder || '';
    var next = before + selected + (after || '');
    source.setRangeText(next, start, end, 'select');
    source.focus();
    render();
  }

  function prefixLines(prefixText) {
    var start = source.selectionStart;
    var end = source.selectionEnd;
    var selected = source.value.slice(start, end) || 'Texto';
    var next = selected.split(/\r?\n/).map(function (line) { return prefixText + line.replace(/^#{1,6}\s+|^[-*]\s+|^\d+\.\s+|^>\s?/, ''); }).join('\n');
    source.setRangeText(next, start, end, 'select');
    source.focus();
    render();
  }

  function insertBlock(text) {
    var pos = source.selectionStart;
    var needsBreak = pos > 0 && source.value.charAt(pos - 1) !== '\n';
    source.setRangeText((needsBreak ? '\n\n' : '') + text, pos, source.selectionEnd, 'end');
    source.focus();
    render();
  }

  async function saveDrive() {
    setStatus('Salvando Drive...', 'warn');
    var response = await fetch(prefix + '/casehub-md/drive/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        doc_id: ensureDocId(),
        filename: getMarkdownFilename(),
        markdown: source.value || ''
      })
    });
    if (!response.ok) throw new Error('drive-save-' + response.status);
    var data = await response.json();
    if (data.updated_at) setStatus('Drive sincronizado', 'ok');
    refreshDocs();
  }

  async function exportGoogleDoc() {
    setStatus('Exportando Google Docs...', 'warn');
    var response = await fetch(prefix + '/casehub-md/drive/export-google-doc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        doc_id: ensureDocId(),
        filename: getFilenameBase(),
        markdown: source.value || '',
        html: preview ? preview.innerHTML : ''
      })
    });
    if (!response.ok) throw new Error('google-doc-' + response.status);
    var data = await response.json();
    setStatus('Google Docs exportado', 'ok');
    if (data.google_doc_url) {
      window.open(data.google_doc_url, '_blank', 'noopener');
    }
    refreshDocs();
  }

  async function refreshDocs() {
    if (!docList) return;
    docList.innerHTML = '<div class="ch-md__empty">Carregando...</div>';
    try {
      var response = await fetch(prefix + '/casehub-md/drive/list');
      if (!response.ok) throw new Error('drive-list-' + response.status);
      var data = await response.json();
      driveItems = Array.isArray(data.items) ? data.items : [];
      renderExplorer();
    } catch (err) {
      driveItems = [];
      renderExplorer();
    }
  }

  async function loadDriveDoc(nextDocId) {
    if (!nextDocId) return;
    setStatus('Abrindo Drive...', 'warn');
    var response = await fetch(prefix + '/casehub-md/drive/' + encodeURIComponent(nextDocId));
    if (!response.ok) throw new Error('drive-load-' + response.status);
    var data = await response.json();
    docId = nextDocId;
    if (docIdEl) docIdEl.textContent = docId;
    titleInput.value = (data.filename || nextDocId).replace(/\.md$/i, '');
    source.value = data.markdown || '';
    try { localStorage.setItem('casehub.md.docId', docId); } catch (err) {}
    render();
    setStatus('Documento aberto', 'ok');
  }

  async function exportDocx(template) {
    setStatus('Gerando DOCX...', 'warn');
    var response = await fetch(prefix + '/casehub-md/export/docx', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        markdown: source.value || '',
        filename: getFilenameBase() || 'casehub-md',
        template: template || null
      })
    });
    if (!response.ok) throw new Error('docx-' + response.status);
    var blob = await response.blob();
    var url = URL.createObjectURL(blob);
    var link = document.createElement('a');
    link.href = url;
    link.download = getFilenameBase().replace(/\.docx$/i, '') + '.docx';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    setStatus('DOCX gerado', 'ok');
  }

  async function runOcr(file) {
    if (!file) return;
    setStatus('OCR em processamento...', 'warn');
    var form = new FormData();
    form.append('file', file);
    var response = await fetch(prefix + '/casehub-md/ocr', { method: 'POST', body: form });
    if (!response.ok) throw new Error('ocr-' + response.status);
    var data = await response.json();
    insertBlock('\n\n' + (data.markdown || data.text || '').trim() + '\n');
    setStatus('OCR inserido', 'ok');
  }

  async function askMaestro() {
    var selected = source.value.slice(source.selectionStart, source.selectionEnd).trim();
    if (!selected) selected = source.value.split(/\n\s*\n/).find(function (part) { return part.trim(); }) || '';
    if (!selected) return;
    setStatus('Maestro...', 'warn');
    var response = await fetch(prefix + '/casehub-md/maestro/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paragraph: selected, kind: 'rewrite' })
    });
    if (!response.ok) throw new Error('maestro-' + response.status);
    var data = await response.json();
    insertBlock('\n\n> Maestro\n>\n> ' + String(data.suggestion || '').replace(/\n/g, '\n> ') + '\n');
    setStatus('Sugestao inserida', 'ok');
  }

  function handleAction(action) {
    try {
      if (runPreviewAction(action)) return;
      if (action === 'bold') withSelection('**', '**', 'texto');
      if (action === 'italic') withSelection('*', '*', 'texto');
      if (action === 'strike') withSelection('~~', '~~', 'texto');
      if (action === 'h1') prefixLines('# ');
      if (action === 'h2') prefixLines('## ');
      if (action === 'h3') prefixLines('### ');
      if (action === 'bullet') prefixLines('- ');
      if (action === 'ordered') prefixLines('1. ');
      if (action === 'quote') prefixLines('> ');
      if (action === 'code') insertBlock('```\n' + (source.value.slice(source.selectionStart, source.selectionEnd) || 'codigo') + '\n```');
      if (action === 'link') withSelection('[', '](https://)', 'link');
      if (action === 'table') insertBlock('| Campo | Valor |\n|---|---|\n| Cliente | |\n| Caso | |');
      if (action === 'save') saveDrive().catch(function () { setStatus('Drive offline', 'error'); });
      if (action === 'google-doc') exportGoogleDoc().catch(function () { setStatus('Google Docs indisponivel', 'error'); });
      if (action === 'refresh') refreshDocs();
      if (action === 'docx') exportDocx().catch(function () { setStatus('DOCX indisponivel', 'error'); });
      if (action === 'docx-oab') exportDocx('oab').catch(function () { setStatus('DOCX indisponivel', 'error'); });
      if (action === 'ocr' && ocrInput) ocrInput.click();
      if (action === 'maestro') askMaestro().catch(function () { setStatus('Maestro indisponivel', 'error'); });
    } catch (err) {
      setStatus('Erro na acao', 'error');
    }
  }

  root.addEventListener('click', function (event) {
    var button = event.target.closest('[data-md-action]');
    if (!button) return;
    event.preventDefault();
    handleAction(button.getAttribute('data-md-action'));
  });

  if (docList) {
    docList.addEventListener('click', function (event) {
      var item = event.target.closest('[data-doc-id]');
      if (!item) return;
      if (item.getAttribute('data-doc-source') === 'local') {
        restore();
        setStatus('Documento local aberto', 'ok');
        return;
      }
      loadDriveDoc(item.getAttribute('data-doc-id')).catch(function () { setStatus('Nao abriu Drive', 'error'); });
    });
  }

  root.addEventListener('click', function (event) {
    var sourceButton = event.target.closest('[data-md-explorer-source]');
    if (sourceButton) {
      explorerSource = sourceButton.getAttribute('data-md-explorer-source') || 'all';
      explorerFolder = 'Recentes';
      Array.prototype.forEach.call(root.querySelectorAll('[data-md-explorer-source]'), function (button) {
        button.classList.toggle('is-active', button === sourceButton);
      });
      renderExplorer();
      event.preventDefault();
      return;
    }
    var folderButton = event.target.closest('[data-md-folder]');
    if (folderButton) {
      explorerFolder = folderButton.getAttribute('data-md-folder') || 'Recentes';
      renderExplorer();
      event.preventDefault();
    }
  });

  if (ocrInput) {
    ocrInput.addEventListener('change', function () {
      runOcr(ocrInput.files && ocrInput.files[0]).catch(function () { setStatus('OCR indisponivel', 'error'); });
      ocrInput.value = '';
    });
  }

  source.addEventListener('input', render);
  preview.addEventListener('input', syncPreviewToSource);
  preview.addEventListener('keydown', handlePreviewMarkdownShortcut);
  preview.addEventListener('blur', function () { render(); });
  titleInput.addEventListener('input', saveLocal);
  source.addEventListener('keydown', function (event) {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
      event.preventDefault();
      saveDrive().catch(function () { setStatus('Drive offline', 'error'); });
    }
  });

  restore();
  renderExplorer();
  refreshDocs();
  if (window.CHLucide) window.CHLucide.mount();
})();
