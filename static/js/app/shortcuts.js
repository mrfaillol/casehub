/* CaseHub App · Keyboard shortcuts (Doherty threshold)
 *   cmd+k / ctrl+k → command palette open (dispatches casehub:palette:open)
 *   ?              → help overlay (casehub:help:open)
 *   g d / g c / g p / g t → quick goto Dashboard/Clients/Processes/Tasks (sequence)
 *
 * Theme/Eco shortcuts (T/E) live in theme.js.
 */
(function () {
  'use strict';

  function isTypingTarget(t) {
    if (!t) return false;
    var tag = (t.tagName || '').toLowerCase();
    return tag === 'input' || tag === 'textarea' || tag === 'select' || t.isContentEditable;
  }

  var sequence = [];
  var seqTimer = null;
  function pushSeq(key) {
    sequence.push(key);
    clearTimeout(seqTimer);
    seqTimer = setTimeout(function () { sequence = []; }, 600);
    return sequence.join('');
  }

  function goto(path) {
    if (window.CASEHUB_PREFIX != null) path = window.CASEHUB_PREFIX + path;
    window.location.href = path;
  }

  document.addEventListener('keydown', function (e) {
    if (isTypingTarget(e.target)) {
      // allow esc to blur typing targets quickly
      if (e.key === 'Escape') { try { e.target.blur(); } catch (_) {} }
      return;
    }

    // cmd+k / ctrl+k → palette
    if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      document.dispatchEvent(new CustomEvent('casehub:palette:open'));
      return;
    }
    if (e.metaKey || e.ctrlKey || e.altKey) return;

    // ?
    if (e.key === '?' || (e.key === '/' && e.shiftKey)) {
      e.preventDefault();
      document.dispatchEvent(new CustomEvent('casehub:help:open'));
      return;
    }

    // g + letter
    var seq = pushSeq(e.key.toLowerCase());
    if (seq === 'gd') { e.preventDefault(); goto('/dashboard'); }
    else if (seq === 'gc') { e.preventDefault(); goto('/clients'); }
    else if (seq === 'gp') { e.preventDefault(); goto('/processes'); }
    else if (seq === 'gt') { e.preventDefault(); goto('/tasks'); }
    else if (seq === 'ga') { e.preventDefault(); goto('/calendar'); }
  });

  // Wire palette open click
  document.addEventListener('click', function (e) {
    var trigger = e.target.closest && e.target.closest('[data-action="palette-open"]');
    if (trigger) {
      e.preventDefault();
      document.dispatchEvent(new CustomEvent('casehub:palette:open'));
    }
  });

  window.CHShortcuts = {
    goto: goto
  };
})();
