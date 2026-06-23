/**
 * CaseHub Lite - Widget Dashboard System
 * Uses Gridstack.js for drag-and-drop + resize
 */

var WIDGET_REGISTRY = {
    'prazo-countdown': { title: 'Proximos Prazos', icon: '\u23F0', w: 4, h: 4, minW: 3, minH: 3 },
    'process-status': { title: 'Status Processos', icon: '\uD83D\uDCCB', w: 4, h: 3, minW: 3, minH: 2 },
    'revenue-chart': { title: 'Receita (30 dias)', icon: '\uD83D\uDCB0', w: 4, h: 4, minW: 3, minH: 3 },
    'task-kanban': { title: 'Tarefas Hoje', icon: '\u2713', w: 4, h: 4, minW: 3, minH: 3 },
    'calendar-events': { title: 'Proximos Eventos', icon: '\uD83D\uDCC5', w: 4, h: 4, minW: 3, minH: 3 },
    'activity-feed': { title: 'Atividade Recente', icon: '\uD83D\uDC65', w: 4, h: 4, minW: 3, minH: 3 },
    'upload-dropzone': { title: 'Upload Documentos', icon: '\uD83D\uDCE4', w: 4, h: 3, minW: 3, minH: 2 },
    'tribunal-search': { title: 'Busca Tribunal', icon: '\uD83D\uDD0D', w: 4, h: 3, minW: 3, minH: 2 },
    'indices-mini': { title: 'Indices', icon: '\uD83D\uDCCA', w: 6, h: 4, minW: 4, minH: 3 },
    'clock': { title: 'Relogio', icon: '\uD83D\uDD50', w: 3, h: 2, minW: 2, minH: 2 },
    'notes': { title: 'Notas Rapidas', icon: '\uD83D\uDCDD', w: 4, h: 3, minW: 3, minH: 2 },
    'welcome': { title: 'Bem-vindo', icon: '\uD83D\uDC4B', w: 6, h: 2, minW: 4, minH: 2 },
};

var DASHBOARD_LAYOUT_VERSION = 'v2';
var LEGACY_STORAGE_KEY = 'casehub-dashboard-layout';
var STORAGE_PREFIX = `casehub-dashboard-layout:${DASHBOARD_LAYOUT_VERSION}:`;

var BREAKPOINTS = {
    desktop: { min: 1200, columns: 12, cellHeight: 72, drag: true },
    tablet: { min: 768, columns: 6, cellHeight: 74, drag: true },
    mobile: { min: 0, columns: 1, cellHeight: 82, drag: false },
};

var DEFAULT_LAYOUTS = {
    desktop: [
        { id: 'welcome', x: 0, y: 0, w: 4, h: 2 },
        { id: 'process-status', x: 4, y: 0, w: 4, h: 2 },
        { id: 'prazo-countdown', x: 8, y: 0, w: 4, h: 3 },
        { id: 'task-kanban', x: 0, y: 2, w: 4, h: 4 },
        { id: 'revenue-chart', x: 4, y: 2, w: 4, h: 3 },
        { id: 'calendar-events', x: 8, y: 3, w: 4, h: 3 },
    ],
    tablet: [
        { id: 'welcome', x: 0, y: 0, w: 6, h: 2 },
        { id: 'process-status', x: 0, y: 2, w: 3, h: 2 },
        { id: 'prazo-countdown', x: 3, y: 2, w: 3, h: 3 },
        { id: 'task-kanban', x: 0, y: 4, w: 3, h: 4 },
        { id: 'calendar-events', x: 3, y: 5, w: 3, h: 3 },
        { id: 'revenue-chart', x: 0, y: 8, w: 6, h: 3 },
    ],
    mobile: [
        { id: 'welcome', x: 0, y: 0, w: 1, h: 2 },
        { id: 'process-status', x: 0, y: 2, w: 1, h: 2 },
        { id: 'prazo-countdown', x: 0, y: 4, w: 1, h: 3 },
        { id: 'task-kanban', x: 0, y: 7, w: 1, h: 4 },
        { id: 'calendar-events', x: 0, y: 11, w: 1, h: 3 },
        { id: 'revenue-chart', x: 0, y: 14, w: 1, h: 3 },
    ],
};

var grid;
var currentBreakpoint = getBreakpoint();
var usingStaticGrid = false;

function initDashboard() {
    const gridEl = document.getElementById('dashboard-grid');
    if (!gridEl) return;

    currentBreakpoint = getBreakpoint();
    const cfg = BREAKPOINTS[currentBreakpoint];
    usingStaticGrid = false;

    if (document.body.classList.contains('casehub-browser-basic')) {
        grid = null;
        renderStaticLayout(readLayout(currentBreakpoint));
        return;
    }

    if (typeof GridStack === 'undefined') {
        renderStaticLayout(readLayout(currentBreakpoint));
        return;
    }

    try {
        grid = GridStack.init({
            column: cfg.columns,
            cellHeight: cfg.cellHeight,
            float: true,
            animate: true,
            margin: 8,
            resizable: { handles: 'se,sw,ne,nw,e,w,s,n' },
            removable: false,
        }, gridEl);
    } catch (e) {
        console.warn('Dashboard GridStack unavailable; rendering static widgets.', e);
        grid = null;
        renderStaticLayout(readLayout(currentBreakpoint));
        return;
    }

    loadLayout(readLayout(currentBreakpoint));
    applyBreakpointMode(currentBreakpoint);

    // Auto-save on change
    grid.on('change', saveLayout);

    // Responsive
    window.addEventListener('resize', debounce(updateResponsive, 180));
}

function getBreakpoint() {
    const width = window.innerWidth || document.documentElement.clientWidth || 1440;
    if (width >= BREAKPOINTS.desktop.min) return 'desktop';
    if (width >= BREAKPOINTS.tablet.min) return 'tablet';
    return 'mobile';
}

function storageKey(bp = currentBreakpoint) {
    return STORAGE_PREFIX + bp;
}

function readLayout(bp = currentBreakpoint) {
    const saved = localStorage.getItem(storageKey(bp));
    if (!saved) return DEFAULT_LAYOUTS[bp];
    try {
        const parsed = JSON.parse(saved);
        return (Array.isArray(parsed) && parsed.length > 0) ? parsed : DEFAULT_LAYOUTS[bp];
    } catch (e) {
        return DEFAULT_LAYOUTS[bp];
    }
}

function applyBreakpointMode(bp = currentBreakpoint) {
    if (!grid) return;
    const cfg = BREAKPOINTS[bp];
    grid.column(cfg.columns);
    if (typeof grid.cellHeight === 'function') grid.cellHeight(cfg.cellHeight);
    if (cfg.drag) {
        grid.enable();
    } else {
        grid.disable();
    }
}

function debounce(fn, delay) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = window.setTimeout(() => fn(...args), delay);
    };
}

function loadLayout(layout) {
    if (!grid) {
        renderStaticLayout(layout);
        return;
    }
    grid.removeAll();
    layout.forEach(item => {
        const reg = WIDGET_REGISTRY[item.id];
        if (!reg) return;
        const columns = BREAKPOINTS[currentBreakpoint].columns;
        const el = createWidgetElement(item.id, reg);
        grid.addWidget(el, {
            x: item.x, y: item.y,
            w: Math.min(item.w || reg.w, columns),
            h: item.h || reg.h,
            minW: Math.min(reg.minW, columns), minH: reg.minH,
            id: item.id
        });
    });
    // Load widget content
    layout.forEach(item => loadWidgetContent(item.id));
}

function createWidgetElement(id, reg) {
    const div = document.createElement('div');
    div.classList.add('grid-stack-item');
    div.setAttribute('gs-id', id);
    div.innerHTML = `
        <div class="grid-stack-item-content">
            <div class="widget-container" id="widget-${id}">
                <div class="widget-header">
                    <span><span class="widget-icon">${reg.icon}</span><span class="widget-title">${reg.title}</span></span>
                    <button class="widget-menu" onclick="removeWidget('${id}')" title="Remover">\u2715</button>
                </div>
                <div class="widget-body" id="widget-body-${id}">
                    <div class="widget-empty">Carregando...</div>
                </div>
            </div>
        </div>
    `;
    return div;
}

function renderStaticLayout(layout) {
    const gridEl = document.getElementById('dashboard-grid');
    if (!gridEl) return;
    usingStaticGrid = true;
    gridEl.classList.add('basic-widget-fallback');
    gridEl.innerHTML = '';
    layout.forEach(item => {
        const reg = WIDGET_REGISTRY[item.id];
        if (!reg) return;
        gridEl.appendChild(createWidgetElement(item.id, reg));
    });
    layout.forEach(item => loadWidgetContent(item.id));
}

async function loadWidgetContent(id) {
    const body = document.getElementById('widget-body-' + id);
    if (!body) return;
    try {
        const resp = await fetch(PREFIX + '/api/widget/' + id);
        if (resp.ok) {
            body.innerHTML = await resp.text();
        } else {
            body.innerHTML = getStaticWidgetContent(id);
        }
    } catch (e) {
        body.innerHTML = getStaticWidgetContent(id);
    }
}

function getStaticWidgetContent(id) {
    // Fallback static content for each widget
    const contents = {
        'welcome': (() => {
            const h = new Date().getHours();
            const g = h < 12 ? 'Bom dia' : h < 18 ? 'Boa tarde' : 'Boa noite';
            return `<div class="widget-welcome"><h2>${g}, Equipe CaseHub</h2><p>Painel de controle do escritorio</p></div>`;
        })(),
        'clock': `<div class="widget-clock"><div id="clock-time"></div><div id="clock-date" class="widget-muted"></div></div><script>setInterval(()=>{const d=new Date();const t=document.getElementById('clock-time');const dt=document.getElementById('clock-date');if(t)t.textContent=d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});if(dt)dt.textContent=d.toLocaleDateString('pt-BR',{weekday:'long',day:'numeric',month:'long',year:'numeric'});},1000);<\/script>`,
        'notes': `<textarea class="widget-textarea" id="quick-notes" placeholder="Notas rapidas..." oninput="localStorage.setItem('casehub-notes',this.value)">${localStorage.getItem('casehub-notes')||''}</textarea>`,
        'prazo-countdown': `<div class="widget-empty">Nenhum prazo cadastrado.<br><a class="widget-link" href="${PREFIX}/controladoria">Ir para Controladoria</a></div>`,
        'process-status': `<div class="widget-empty">Nenhum processo cadastrado.<br><a class="widget-link" href="${PREFIX}/cases">Cadastrar processo</a></div>`,
        'revenue-chart': `<div class="widget-empty">Dados financeiros aparecem aqui.<br><a class="widget-link" href="${PREFIX}/billing">Ir para Faturamento</a></div>`,
        'task-kanban': `<div class="widget-empty">Nenhuma tarefa para hoje.<br><a class="widget-link" href="${PREFIX}/tasks/kanban">Ver Kanban</a></div>`,
        'calendar-events': `<div class="widget-empty">Nenhum evento proximo.<br><a class="widget-link" href="${PREFIX}/calendar">Abrir Agenda</a></div>`,
        'activity-feed': `<div class="widget-empty">Atividade recente aparece aqui.</div>`,
        'upload-dropzone': `<button class="widget-dropzone" type="button" onclick="document.getElementById('drop-input').click()"><span class="widget-dropzone__icon">\uD83D\uDCC1</span><span>Arraste documentos aqui</span><input type="file" id="drop-input" hidden multiple></button>`,
        'tribunal-search': `<div class="widget-form"><input class="widget-input" type="text" placeholder="N\u00BA processo ou OAB..."><div class="widget-form__link"><a class="widget-link" href="${PREFIX}/tribunal">Busca avancada \u2192</a></div></div>`,
        'indices-mini': `<div class="widget-empty"><a class="widget-link" href="${PREFIX}/controladoria/indices">Ver Indices Completos \u2192</a></div>`,
    };
    return contents[id] || '<div class="widget-empty">Widget</div>';
}

function saveLayout() {
    if (!grid || usingStaticGrid) return;
    const items = grid.getGridItems();
    const layout = items.map(el => {
        const node = el.gridstackNode;
        return { id: node.id || el.getAttribute('gs-id'), x: node.x, y: node.y, w: node.w, h: node.h };
    });
    localStorage.setItem(storageKey(), JSON.stringify(layout));
}

function addWidget(id) {
    const reg = WIDGET_REGISTRY[id];
    if (!reg) return;
    if (!grid || usingStaticGrid) {
        const layout = readLayout(currentBreakpoint).slice();
        if (!layout.some(item => item.id === id)) {
            layout.push({ id, w: reg.w, h: reg.h });
            localStorage.setItem(storageKey(), JSON.stringify(layout));
        }
        renderStaticLayout(layout);
        closeWidgetPicker();
        return;
    }
    const columns = BREAKPOINTS[currentBreakpoint].columns;
    const el = createWidgetElement(id, reg);
    grid.addWidget(el, {
        w: Math.min(reg.w, columns),
        h: reg.h,
        minW: Math.min(reg.minW, columns),
        minH: reg.minH,
        id: id,
        autoPosition: true
    });
    loadWidgetContent(id);
    saveLayout();
    closeWidgetPicker();
}

function removeWidget(id) {
    const el = document.querySelector(`[gs-id="${id}"]`);
    if (!grid || usingStaticGrid) {
        const layout = readLayout(currentBreakpoint).filter(item => item.id !== id);
        localStorage.setItem(storageKey(), JSON.stringify(layout.length ? layout : DEFAULT_LAYOUTS[currentBreakpoint]));
        renderStaticLayout(readLayout(currentBreakpoint));
        return;
    }
    if (el) { grid.removeWidget(el); saveLayout(); }
}

function resetLayout() {
    if (confirm('Resetar layout para o padrao?')) {
        localStorage.removeItem(LEGACY_STORAGE_KEY);
        Object.keys(BREAKPOINTS).forEach(bp => localStorage.removeItem(storageKey(bp)));
        loadLayout(DEFAULT_LAYOUTS[currentBreakpoint]);
        applyBreakpointMode(currentBreakpoint);
    }
}

function openWidgetPicker() {
    document.getElementById('widget-picker').classList.add('active');
}
function closeWidgetPicker() {
    document.getElementById('widget-picker').classList.remove('active');
}

function updateResponsive() {
    const nextBreakpoint = getBreakpoint();
    if (nextBreakpoint === currentBreakpoint) {
        applyBreakpointMode(currentBreakpoint);
        return;
    }
    saveLayout();
    currentBreakpoint = nextBreakpoint;
    loadLayout(readLayout(currentBreakpoint));
    applyBreakpointMode(currentBreakpoint);
}

// Initialize on DOM ready
window.initDashboardWidgets = initDashboard;
document.addEventListener('DOMContentLoaded', initDashboard);
document.addEventListener('casehub:soft-navigation', initDashboard);
