// CaseHub VPS Orchestrator - Canvas Visual Interface
let cy = null;
let selectedNode = null;
let dashboardData = {};

// Mapeamento de IDs do orchestrator para chaves da API
const DB_KEY_MAP = {
    'postgresql': 'postgres',
    'mariadb': 'mysql',
    'redis': 'redis'
};

const SERVICE_LAYOUT = {
    'casehub': { x: 400, y: 150, icon: 'fa-briefcase', color: '#58a6ff', deps: ['postgresql', 'redis'] },
    'ilc-tools': { x: 600, y: 150, icon: 'fa-tools', color: '#a371f7', deps: ['postgresql'] },
    'whatsapp-bot': { x: 200, y: 150, icon: 'fa-whatsapp', color: '#3fb950', deps: ['mariadb', 'gemini'] },
    'vps-monitor': { x: 400, y: 300, icon: 'fa-chart-line', color: '#d29922', deps: [] },
    'client-intake': { x: 600, y: 300, icon: 'fa-user-plus', color: '#f778ba', deps: ['postgresql'] },
    'document-watcher': { x: 200, y: 300, icon: 'fa-file-alt', color: '#79c0ff', deps: [] },
    'maestro': { x: 400, y: 450, icon: 'fa-robot', color: '#ffa657', deps: [] },
    'n8n': { x: 600, y: 450, icon: 'fa-cogs', color: '#ff7b72', deps: [] },
    'postgresql': { x: 500, y: 550, icon: 'fa-database', color: '#336791', type: 'database' },
    'mariadb': { x: 300, y: 550, icon: 'fa-database', color: '#c0765a', type: 'database' },
    'redis': { x: 700, y: 550, icon: 'fa-bolt', color: '#dc382d', type: 'database' },
    'gemini': { x: 100, y: 450, icon: 'fa-brain', color: '#4285f4', type: 'external' }
};

function initCytoscape() {
    cy = cytoscape({
        container: document.getElementById('cy'),
        style: [
            { selector: 'node', style: { 'background-color': 'data(color)', 'label': 'data(label)', 'color': '#c9d1d9', 'text-valign': 'bottom', 'text-margin-y': 8, 'font-size': '12px', 'width': 50, 'height': 50, 'border-width': 3, 'border-color': '#30363d' }},
            { selector: 'node[status="online"]', style: { 'border-color': '#3fb950' }},
            { selector: 'node[status="stopped"]', style: { 'border-color': '#f85149', 'opacity': 0.6 }},
            { selector: 'node[status="erroring"]', style: { 'border-color': '#d29922' }},
            { selector: 'node[type="database"]', style: { 'shape': 'barrel', 'width': 40, 'height': 50 }},
            { selector: 'node[type="external"]', style: { 'shape': 'diamond', 'width': 45, 'height': 45 }},
            { selector: 'edge', style: { 'width': 2, 'line-color': '#30363d', 'target-arrow-color': '#30363d', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'opacity': 0.5 }},
            { selector: 'node:selected', style: { 'border-width': 4, 'border-color': '#58a6ff' }}
        ],
        layout: { name: 'preset' },
        minZoom: 0.5, maxZoom: 2, wheelSensitivity: 0.2
    });
    cy.on('tap', 'node', function(evt) { selectedNode = evt.target.id(); showNodeDetails(evt.target.id(), evt.target.data()); });
    cy.on('tap', function(evt) { if (evt.target === cy) closeNodeDetails(); });
}

function buildGraph(pm2Data, dbData, integrationsData) {
    const elements = [];
    const processedNodes = new Set();
    if (pm2Data && pm2Data.processes) {
        pm2Data.processes.forEach(proc => {
            const layout = SERVICE_LAYOUT[proc.name] || { x: Math.random() * 600 + 100, y: Math.random() * 400 + 100, color: '#8b949e' };
            elements.push({ data: { id: proc.name, label: proc.name, color: layout.color, status: proc.status, cpu: proc.cpu, memory: proc.memory, memoryMB: (proc.memory / 1024 / 1024).toFixed(1), uptime: proc.uptime, restarts: proc.restart || 0, type: layout.type || 'service' }, position: { x: layout.x, y: layout.y } });
            processedNodes.add(proc.name);
        });
    }
    ['postgresql', 'mariadb', 'redis'].forEach(db => {
        if (!processedNodes.has(db)) {
            const layout = SERVICE_LAYOUT[db];
            const apiKey = DB_KEY_MAP[db];
            const dbInfo = dbData && dbData[apiKey];
            const dbStatus = dbInfo && dbInfo.status === 'healthy' ? 'online' : 'stopped';
            elements.push({ data: { id: db, label: db, color: layout.color, status: dbStatus, type: 'database' }, position: { x: layout.x, y: layout.y } });
        }
    });
    ['gemini'].forEach(ext => {
        if (!processedNodes.has(ext)) {
            const layout = SERVICE_LAYOUT[ext];
            const extStatus = integrationsData && integrationsData[ext];
            elements.push({ data: { id: ext, label: ext, color: layout.color, status: extStatus && extStatus.status === 'healthy' ? 'online' : 'stopped', type: 'external' }, position: { x: layout.x, y: layout.y } });
        }
    });
    Object.entries(SERVICE_LAYOUT).forEach(([service, config]) => {
        if (config.deps) config.deps.forEach(dep => elements.push({ data: { id: service + '-' + dep, source: service, target: dep } }));
    });
    if (cy.elements().length === 0) { cy.add(elements); cy.fit(50); }
    else elements.forEach(el => { if (el.data.id && !el.data.source) { const node = cy.getElementById(el.data.id); if (node.length) node.data(el.data); } });
}

function updateSidebar(pm2Data, dbData, integrationsData) {
    const servicesHtml = pm2Data.processes.map(proc => {
        const statusClass = proc.status === 'online' ? 'status-online' : proc.status === 'stopped' ? 'status-stopped' : 'status-error';
        const memMB = (proc.memory / 1024 / 1024).toFixed(1);
        return '<div class="service-item" onclick="focusNode(\'' + proc.name + '\')"><div class="service-name"><span class="status-dot ' + statusClass + '"></span>' + proc.name + '</div><div class="service-status">' + memMB + ' MB | ' + (proc.uptime || 'N/A') + '</div></div>';
    }).join('');
    document.getElementById('servicesList').innerHTML = servicesHtml;

    // Database mapping: [displayName, apiKey, nodeId]
    const databases = [
        ['PostgreSQL', 'postgres', 'postgresql'],
        ['MariaDB', 'mysql', 'mariadb'],
        ['Redis', 'redis', 'redis']
    ];
    const dbHtml = databases.map(([displayName, apiKey, nodeId]) => {
        const dbInfo = dbData && dbData[apiKey];
        const status = dbInfo && dbInfo.status === 'healthy' ? 'online' : 'stopped';
        const statusClass = status === 'online' ? 'status-online' : 'status-stopped';
        return '<div class="service-item" onclick="focusNode(\'' + nodeId + '\')"><div class="service-name"><span class="status-dot ' + statusClass + '"></span>' + displayName + '</div><div class="service-status">' + status + '</div></div>';
    }).join('');
    document.getElementById('databasesList').innerHTML = dbHtml;

    const intHtml = ['Gemini', 'Stripe', 'Calendly', 'Moskit'].map(int => {
        const key = int.toLowerCase();
        const data = integrationsData && integrationsData[key];
        const status = data && data.status === 'healthy' ? 'online' : 'stopped';
        const statusClass = status === 'online' ? 'status-online' : 'status-stopped';
        return '<div class="service-item"><div class="service-name"><span class="status-dot ' + statusClass + '"></span>' + int + '</div><div class="service-status">' + status + '</div></div>';
    }).join('');
    document.getElementById('integrationsList').innerHTML = intHtml;
}

function updateStatsBar(system, pm2Data) {
    if (system) {
        document.getElementById('systemCpu').textContent = (system.cpu?.percent || 0).toFixed(1) + '%';
        document.getElementById('systemRam').textContent = (system.memory?.percent || 0).toFixed(1) + '%';
        document.getElementById('systemDisk').textContent = (system.disk?.percent || 0).toFixed(1) + '%';
        document.getElementById('systemUptime').textContent = system.uptime?.uptime_formatted || 'N/A';
    }
    if (pm2Data) {
        const online = pm2Data.processes.filter(p => p.status === 'online').length;
        document.getElementById('servicesOnline').textContent = online + '/' + pm2Data.processes.length;
    }
}

function focusNode(nodeId) {
    const node = cy.getElementById(nodeId);
    if (node.length) { cy.animate({ fit: { eles: node, padding: 100 }, duration: 300 }); node.select(); showNodeDetails(nodeId, node.data()); }
}

function showNodeDetails(nodeId, data) {
    const panel = document.getElementById('nodeDetails');
    panel.classList.remove('hidden');
    document.getElementById('nodeTitle').textContent = nodeId;
    document.getElementById('nodeStatus').textContent = data.status || 'unknown';
    document.getElementById('nodeStatus').className = 'stat-value ' + (data.status === 'online' ? 'text-success' : 'text-danger');
    document.getElementById('nodeCpu').textContent = (data.cpu || 0) + '%';
    document.getElementById('nodeMemory').textContent = (data.memoryMB || 0) + ' MB';
    document.getElementById('nodeUptime').textContent = data.uptime || 'N/A';
    document.getElementById('nodeRestarts').textContent = data.restarts || 0;
    document.getElementById('nodeLogs').classList.add('hidden');
}

function closeNodeDetails() {
    document.getElementById('nodeDetails').classList.add('hidden');
    selectedNode = null;
    cy.elements().unselect();
}

async function serviceAction(action) {
    if (!selectedNode) return;
    const name = selectedNode;
    if (action === 'logs') {
        try {
            const response = await fetch('/monitor/api/pm2/' + name + '/logs?lines=100');
            const data = await response.json();
            document.getElementById('modalLogsContent').textContent = data.out?.join('\n') || data.combined?.join('\n') || 'No logs available';
            document.getElementById('logsModalTitle').textContent = 'Logs: ' + name;
            new bootstrap.Modal(document.getElementById('logsModal')).show();
        } catch (e) { alert('Error fetching logs: ' + e.message); }
        return;
    }
    if (action === 'restart' || action === 'stop') {
        if (!confirm('Are you sure you want to ' + action + ' ' + name + '?')) return;
        try {
            const response = await fetch('/monitor/api/pm2/' + name + '/' + action, { method: 'POST' });
            const data = await response.json();
            if (data.success) { alert(name + ' ' + action + 'ed successfully'); loadDashboardData(); }
            else alert('Error: ' + (data.error || 'Unknown error'));
        } catch (e) { alert('Error: ' + e.message); }
    }
}

async function loadDashboardData() {
    try {
        const response = await fetch('/monitor/api/dashboard');
        const data = await response.json();
        dashboardData = data;
        buildGraph(data.pm2, data.databases, data.integrations);
        updateSidebar(data.pm2, data.databases, data.integrations);
        updateStatsBar(data.system, data.pm2);
        document.getElementById('connectionStatus').innerHTML = '<i class="fas fa-circle me-1"></i>Conectado';
        document.getElementById('connectionStatus').className = 'badge bg-success';
    } catch (e) {
        console.error('Error loading data:', e);
        document.getElementById('connectionStatus').innerHTML = '<i class="fas fa-circle me-1"></i>Desconectado';
        document.getElementById('connectionStatus').className = 'badge bg-danger';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    initCytoscape();
    loadDashboardData();
    setInterval(loadDashboardData, 10000);
});
