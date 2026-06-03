/**
 * CaseHub Visual Component Editor
 * Loads design-system snippets, toggles theme/mode/viewport, live-edits CSS variables.
 */
(function () {
  'use strict';

  /* ── State ── */
  const state = {
    activeCategory: null,
    theme: 'glass',        // 'glass' | 'neuromorphic'
    mode: 'dark',          // 'light' | 'dark'
    viewport: 'desktop',   // 'desktop' | 'mobile'
    sideBySide: false,
    customVars: {},
  };

  /* ── DOM refs ── */
  const $tree = document.getElementById('de-tree');
  const $preview = document.getElementById('de-preview');
  const $previewB = document.getElementById('de-preview-b');
  const $controls = document.getElementById('de-controls');
  const $themeToggle = document.getElementById('de-toggle-theme');
  const $modeToggle = document.getElementById('de-toggle-mode');
  const $vpToggle = document.getElementById('de-toggle-viewport');
  const $sbsToggle = document.getElementById('de-toggle-sbs');
  const $resetBtn = document.getElementById('de-reset');
  const $exportBtn = document.getElementById('de-export');
  const $previewWrap = document.getElementById('de-preview-wrap');
  const $labelTheme = document.getElementById('de-label-theme');
  const $labelMode = document.getElementById('de-label-mode');
  const $labelVp = document.getElementById('de-label-viewport');

  /* ── Component tree data ── */
  const TREE = {
    Tokens:     { id: 'tokens',     items: ['Colors', 'Typography', 'Spacing', 'Shadows'] },
    Surfaces:   { id: 'surfaces',   items: ['Cards', 'Panels', 'Backgrounds'] },
    Buttons:    { id: 'buttons',    items: ['Primary', 'Secondary', 'Success', 'Danger', 'Ghost', 'Sizes', 'States'] },
    Forms:      { id: 'forms',      items: ['Inputs', 'Selects', 'Toggles', 'Checkboxes', 'Radios', 'File Upload'] },
    Navigation: { id: 'navigation', items: ['Sidebar', 'Topbar', 'Tab Bar', 'Breadcrumbs', 'Stepper'] },
    Feedback:   { id: 'feedback',   items: ['Toasts', 'Modals', 'Tooltips', 'Progress', 'Alerts'] },
    Data:       { id: 'data',       items: ['Tables', 'Bar Chart', 'Donut Chart', 'Badges'] },
  };

  /* ── Editable CSS variables grouped by category ── */
  const EDITABLE_VARS = {
    tokens: [
      { var: '--accent-aqua',   label: 'Accent Aqua',   type: 'color' },
      { var: '--accent-violet', label: 'Accent Violet',  type: 'color' },
      { var: '--accent-rose',   label: 'Accent Rose',    type: 'color' },
      { var: '--accent-amber',  label: 'Accent Amber',   type: 'color' },
      { var: '--accent-lime',   label: 'Accent Lime',    type: 'color' },
      { var: '--color-bg',      label: 'Background',     type: 'color' },
      { var: '--neu-primary',   label: 'Neu Primary',    type: 'color' },
      { var: '--neu-success',   label: 'Neu Success',    type: 'color' },
      { var: '--neu-danger',    label: 'Neu Danger',     type: 'color' },
      { var: '--neu-warning',   label: 'Neu Warning',    type: 'color' },
    ],
    surfaces: [
      { var: '--neu-radius-sm', label: 'Radius SM',  type: 'range', min: 0, max: 32, unit: 'px' },
      { var: '--neu-radius-md', label: 'Radius MD',  type: 'range', min: 0, max: 32, unit: 'px' },
      { var: '--neu-radius-lg', label: 'Radius LG',  type: 'range', min: 0, max: 48, unit: 'px' },
      { var: '--neu-radius-xl', label: 'Radius XL',  type: 'range', min: 0, max: 48, unit: 'px' },
    ],
    buttons: [
      { var: '--neu-primary',      label: 'Primary Color',   type: 'color' },
      { var: '--neu-primary-dark', label: 'Primary Dark',    type: 'color' },
      { var: '--neu-radius-md',    label: 'Button Radius',   type: 'range', min: 0, max: 32, unit: 'px' },
    ],
    forms: [
      { var: '--neu-radius-md',    label: 'Input Radius',    type: 'range', min: 0, max: 24, unit: 'px' },
      { var: '--neu-primary',      label: 'Focus Color',     type: 'color' },
    ],
    navigation: [
      { var: '--neu-primary',      label: 'Active Color',    type: 'color' },
      { var: '--neu-primary-dark', label: 'Active Dark',     type: 'color' },
      { var: '--neu-radius-lg',    label: 'Nav Radius',      type: 'range', min: 0, max: 32, unit: 'px' },
    ],
    feedback: [
      { var: '--neu-success',  label: 'Success',  type: 'color' },
      { var: '--neu-danger',   label: 'Danger',   type: 'color' },
      { var: '--neu-warning',  label: 'Warning',  type: 'color' },
      { var: '--neu-info',     label: 'Info',      type: 'color' },
      { var: '--neu-radius-lg', label: 'Toast Radius', type: 'range', min: 0, max: 32, unit: 'px' },
    ],
    data: [
      { var: '--neu-primary',  label: 'Chart Primary', type: 'color' },
      { var: '--neu-success',  label: 'Chart Success', type: 'color' },
      { var: '--neu-danger',   label: 'Chart Danger',  type: 'color' },
      { var: '--neu-warning',  label: 'Chart Warning', type: 'color' },
      { var: '--neu-info',     label: 'Chart Info',    type: 'color' },
    ],
  };

  /* ── Helpers ── */
  const PREFIX = document.body.dataset.prefix || '';

  function resolveVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function parseNumeric(val) {
    return parseFloat(val) || 0;
  }

  /* ── Build tree ── */
  function buildTree() {
    $tree.innerHTML = '';
    for (const [group, info] of Object.entries(TREE)) {
      const section = document.createElement('div');
      section.className = 'de-tree-section';

      const heading = document.createElement('button');
      heading.className = 'de-tree-heading';
      heading.textContent = group;
      heading.dataset.category = info.id;
      heading.addEventListener('click', () => loadCategory(info.id));

      const list = document.createElement('ul');
      list.className = 'de-tree-list';
      for (const item of info.items) {
        const li = document.createElement('li');
        li.className = 'de-tree-item';
        li.textContent = item;
        li.addEventListener('click', () => loadCategory(info.id));
        list.appendChild(li);
      }

      section.appendChild(heading);
      section.appendChild(list);
      $tree.appendChild(section);
    }
  }

  /* ── Load category snippet ── */
  async function loadCategory(cat) {
    state.activeCategory = cat;
    updateTreeActive();

    try {
      const res = await fetch(`${PREFIX}/admin/design-editor/snippets/${cat}`);
      if (!res.ok) throw new Error(res.statusText);
      const html = await res.text();
      $preview.innerHTML = html;
      if (state.sideBySide) $previewB.innerHTML = html;
    } catch (e) {
      $preview.innerHTML = `<p style="color:#f87171;padding:24px;">Failed to load snippet: ${e.message}</p>`;
    }

    applyThemeClasses();
    buildControls(cat);
  }

  function updateTreeActive() {
    $tree.querySelectorAll('.de-tree-heading').forEach(h => {
      h.classList.toggle('is-active', h.dataset.category === state.activeCategory);
    });
  }

  /* ── Theme / Mode / Viewport ── */
  function applyThemeClasses() {
    // Preview A
    $preview.className = 'de-preview-area';
    if (state.theme === 'neuromorphic') $preview.classList.add('neuromorphic');
    $preview.setAttribute('data-theme', state.mode);

    // Preview B (side-by-side: always the opposite theme)
    if (state.sideBySide) {
      $previewB.className = 'de-preview-area';
      const other = state.theme === 'glass' ? 'neuromorphic' : '';
      if (other) $previewB.classList.add('neuromorphic');
      $previewB.setAttribute('data-theme', state.mode);
      $previewB.style.display = '';
    } else {
      $previewB.style.display = 'none';
    }

    // Viewport
    if (state.viewport === 'mobile') {
      $previewWrap.style.maxWidth = '390px';
    } else {
      $previewWrap.style.maxWidth = '';
    }

    // Labels
    $labelTheme.textContent = state.theme === 'glass' ? 'Glass' : 'Neuro';
    $labelMode.textContent = state.mode === 'dark' ? 'Dark' : 'Light';
    $labelVp.textContent = state.viewport === 'desktop' ? 'Desktop' : 'Mobile';
  }

  $themeToggle.addEventListener('click', () => {
    state.theme = state.theme === 'glass' ? 'neuromorphic' : 'glass';
    applyThemeClasses();
  });

  $modeToggle.addEventListener('click', () => {
    state.mode = state.mode === 'dark' ? 'light' : 'dark';
    applyThemeClasses();
  });

  $vpToggle.addEventListener('click', () => {
    state.viewport = state.viewport === 'desktop' ? 'mobile' : 'desktop';
    applyThemeClasses();
  });

  $sbsToggle.addEventListener('click', () => {
    state.sideBySide = !state.sideBySide;
    $sbsToggle.classList.toggle('is-active', state.sideBySide);
    if (state.sideBySide && state.activeCategory) {
      $previewB.innerHTML = $preview.innerHTML;
    }
    applyThemeClasses();
  });

  /* ── Controls panel ── */
  function buildControls(cat) {
    const vars = EDITABLE_VARS[cat] || [];
    $controls.innerHTML = '';

    if (!vars.length) {
      $controls.innerHTML = '<p class="de-controls-empty">No editable variables for this category.</p>';
      return;
    }

    const heading = document.createElement('h4');
    heading.className = 'de-controls-heading';
    heading.textContent = 'Edit Variables';
    $controls.appendChild(heading);

    for (const v of vars) {
      const row = document.createElement('div');
      row.className = 'de-control-row';

      const label = document.createElement('label');
      label.className = 'de-control-label';
      label.textContent = v.label;

      const varName = document.createElement('code');
      varName.className = 'de-control-var';
      varName.textContent = v.var;

      if (v.type === 'color') {
        const current = state.customVars[v.var] || resolveVar(v.var) || '#7c3aed';
        const input = document.createElement('input');
        input.type = 'color';
        input.className = 'de-control-color';
        input.value = current;
        input.addEventListener('input', (e) => {
          setVar(v.var, e.target.value);
        });
        row.appendChild(label);
        row.appendChild(varName);
        row.appendChild(input);
      } else if (v.type === 'range') {
        const current = state.customVars[v.var] || resolveVar(v.var) || `${v.min}${v.unit}`;
        const num = parseNumeric(current);
        const input = document.createElement('input');
        input.type = 'range';
        input.className = 'de-control-range';
        input.min = v.min;
        input.max = v.max;
        input.value = num;

        const valSpan = document.createElement('span');
        valSpan.className = 'de-control-value';
        valSpan.textContent = `${num}${v.unit}`;

        input.addEventListener('input', (e) => {
          const val = `${e.target.value}${v.unit}`;
          valSpan.textContent = val;
          setVar(v.var, val);
        });
        row.appendChild(label);
        row.appendChild(varName);
        row.appendChild(input);
        row.appendChild(valSpan);
      }

      $controls.appendChild(row);
    }
  }

  function setVar(name, value) {
    state.customVars[name] = value;
    document.documentElement.style.setProperty(name, value);
  }

  /* ── Reset ── */
  $resetBtn.addEventListener('click', () => {
    for (const name of Object.keys(state.customVars)) {
      document.documentElement.style.removeProperty(name);
    }
    state.customVars = {};
    if (state.activeCategory) buildControls(state.activeCategory);
  });

  /* ── Export ── */
  $exportBtn.addEventListener('click', () => {
    const data = { ...state.customVars };
    if (!Object.keys(data).length) {
      alert('No custom variables to export.');
      return;
    }
    const json = JSON.stringify(data, null, 2);

    // Copy to clipboard
    navigator.clipboard.writeText(json).then(() => {
      alert('Design tokens copied to clipboard as JSON.');
    }).catch(() => {
      // Fallback: download
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'design-tokens.json';
      a.click();
      URL.revokeObjectURL(url);
    });
  });

  /* ── Save to server ── */
  const $saveBtn = document.getElementById('de-save');
  if ($saveBtn) {
    $saveBtn.addEventListener('click', async () => {
      const data = { ...state.customVars };
      if (!Object.keys(data).length) {
        alert('No custom variables to save.');
        return;
      }
      try {
        const res = await fetch(`${PREFIX}/admin/design-editor/tokens`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ design_tokens: data }),
        });
        if (!res.ok) throw new Error(res.statusText);
        alert('Tokens saved successfully.');
      } catch (e) {
        alert('Failed to save: ' + e.message);
      }
    });
  }

  /* ── Init ── */
  buildTree();
  loadCategory('tokens');
  applyThemeClasses();

})();
