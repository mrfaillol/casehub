/**
 * VPS Monitor - Real-time Dashboard JavaScript
 */

// Chart instances
let cpuChart = null;
let ramChart = null;
let networkChart = null;

// Data history for charts
const chartHistory = {
    cpu: [],
    ram: [],
    networkIn: [],
    networkOut: [],
    maxPoints: 30
};

// SSE connection
let eventSource = null;
let usePolling = false;
let pollInterval = null;
let updateCount = 0;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    loadInitialData();
    connectSSE();
    startPolling();
});

/**
 * Initialize Chart.js charts
 */
function initCharts() {
    const chartConfig = {
        type: 'line',
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { display: false },
                y: { display: false, min: 0, max: 100 }
            },
            elements: {
                point: { radius: 0 },
                line: { tension: 0.4, borderWidth: 2 }
            },
            animation: { duration: 0 }
        }
    };

    const cpuCtx = document.getElementById('cpu-chart');
    if (cpuCtx) {
        cpuChart = new Chart(cpuCtx.getContext('2d'), {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    borderColor: '#58a6ff',
                    backgroundColor: 'rgba(88, 166, 255, 0.1)',
                    fill: true
                }]
            }
        });
    }

    const ramCtx = document.getElementById('ram-chart');
    if (ramCtx) {
        ramChart = new Chart(ramCtx.getContext('2d'), {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [{
                    data: [],
                    borderColor: '#a371f7',
                    backgroundColor: 'rgba(163, 113, 247, 0.1)',
                    fill: true
                }]
            }
        });
    }

    const netCtx = document.getElementById('network-chart');
    if (netCtx) {
        networkChart = new Chart(netCtx.getContext('2d'), {
            ...chartConfig,
            data: {
                labels: [],
                datasets: [
                    { data: [], borderColor: '#3fb950', backgroundColor: 'rgba(63, 185, 80, 0.1)', fill: true },
                    { data: [], borderColor: '#f85149', backgroundColor: 'rgba(248, 81, 73, 0.1)', fill: true }
                ]
            },
            options: {
                ...chartConfig.options,
                scales: { x: { display: false }, y: { display: false, min: 0 } }
            }
        });
    }
}

function connectSSE() {
    if (eventSource) eventSource.close();
    try {
        eventSource = new EventSource('/monitor/api/stream');
        eventSource.onopen = () => {
            setConnectionStatus(true, 'SSE');
            usePolling = false;
        };
        eventSource.addEventListener('update', (e) => {
            try {
                const data = JSON.parse(e.data);
                updateDashboard(data);
                updateCount++;
            } catch (err) { console.error('SSE parse error:', err); }
        });
        eventSource.onerror = () => {
            setConnectionStatus(true, 'Polling');
            usePolling = true;
        };
    } catch (err) {
        usePolling = true;
    }
}

function startPolling() {
    pollInterval = setInterval(async () => {
        if (usePolling || !eventSource || eventSource.readyState !== EventSource.OPEN) {
            await fetchDashboardData();
        }
    }, 5000);

    // Refresh apps + activity every 15 seconds
    setInterval(async () => {
        try {
            const response = await fetch('/monitor/api/apps');
            const data = await response.json();
            updateApplicationMetrics(data);
            if (data.recent_activity) {
                updateRecentActivity(data.recent_activity);
            }
        } catch (error) { console.error('Failed to refresh app metrics:', error); }
    }, 15000);
}

async function fetchDashboardData() {
    try {
        const response = await fetch('/monitor/api/dashboard');
        const data = await response.json();
        updateDashboard(data);
        updateApplicationMetrics(data.applications);
        if (data.applications?.recent_activity) {
            updateRecentActivity(data.applications.recent_activity);
        }
        setConnectionStatus(true, 'Polling');
    } catch (error) {
        console.error('Failed to fetch dashboard:', error);
        setConnectionStatus(false);
    }
}

function setConnectionStatus(connected, mode = '') {
    const elem = document.getElementById('connection-status');
    if (connected) {
        elem.className = 'badge bg-success';
        elem.innerHTML = '<i class="fas fa-circle"></i> ' + (mode || 'Connected');
    } else {
        elem.className = 'badge bg-danger';
        elem.innerHTML = '<i class="fas fa-circle"></i> Offline';
    }
}

async function loadInitialData() {
    try {
        const response = await fetch('/monitor/api/dashboard');
        const data = await response.json();
        updateDashboard(data);
        updateApplicationMetrics(data.applications);
        if (data.applications?.recent_activity) {
            updateRecentActivity(data.applications.recent_activity);
        }
        addLogEntry('system', 'Dashboard inicializado');
    } catch (error) {
        console.error('Failed to load initial data:', error);
        addLogEntry('error', 'Falha ao carregar dados iniciais');
    }
}

async function refreshAll() {
    await loadInitialData();
    addLogEntry('user', 'Dashboard atualizado manualmente');
}

function updateDashboard(data) {
    if (data.system) updateSystemMetrics(data.system);
    if (data.pm2) updatePM2Services(data.pm2);
    if (data.services) updateServicesHealth(data.services);
    
    const now = new Date();
    document.getElementById('last-update').textContent = 'Atualizado: ' + now.toLocaleTimeString();
}

function updateSystemMetrics(system) {
    const cpuPercent = system.cpu.percent;
    document.getElementById('cpu-value').textContent = cpuPercent.toFixed(1);
    if (cpuChart) updateChartData(cpuChart, chartHistory.cpu, cpuPercent);

    const ramPercent = system.memory.percent;
    document.getElementById('ram-value').textContent = ramPercent.toFixed(1) + '%';
    document.getElementById('ram-detail').textContent = system.memory.used_gb + ' / ' + system.memory.total_gb + ' GB';
    if (ramChart) updateChartData(ramChart, chartHistory.ram, ramPercent);

    document.getElementById('disk-value').textContent = system.disk.percent + '%';
    document.getElementById('disk-detail').textContent = system.disk.used_gb + ' / ' + system.disk.total_gb + ' GB';
    const diskBar = document.getElementById('disk-bar');
    diskBar.style.width = system.disk.percent + '%';
    diskBar.className = 'progress-bar';
    if (system.disk.percent > 90) diskBar.classList.add('danger');
    else if (system.disk.percent > 75) diskBar.classList.add('warning');

    document.getElementById('load-value').textContent = system.load['1min'];
    document.getElementById('load-5m').textContent = '5m: ' + system.load['5min'];
    document.getElementById('load-15m').textContent = '15m: ' + system.load['15min'];

    document.getElementById('net-in').textContent = system.network.mb_in_per_sec;
    document.getElementById('net-out').textContent = system.network.mb_out_per_sec;
    if (networkChart) updateNetworkChart(system.network.mb_in_per_sec, system.network.mb_out_per_sec);

    document.getElementById('uptime-value').textContent = system.uptime.uptime_formatted;
    document.getElementById('connections-count').textContent = system.network.connections + ' conexoes';
}

// Store current PM2 data for modal
let currentPM2Data = null;
let currentModalProcess = null;

function updatePM2Services(pm2Data) {
    const container = document.getElementById('pm2-services');
    currentPM2Data = pm2Data;  // Store for modal use
    if (pm2Data.error) {
        container.innerHTML = '<div class="col-12"><div class="alert alert-danger">' + pm2Data.error + '</div></div>';
        return;
    }
    let html = '';
    for (const proc of pm2Data.processes) {
        const statusClass = proc.status === 'online' ? 'online' : proc.status === 'errored' ? 'errored' : 'stopped';
        const isOnline = proc.status === 'online';
        html += '<div class="col-md-3 col-sm-6 col-12"><div class="service-card">' +
            '<div class="service-card-header">' +
            '<div class="service-status ' + statusClass + '"></div>' +
            '<div class="service-info"><div class="service-name">' + proc.name + '</div>' +
            '<div class="service-details">' +
            '<span class="service-detail"><i class="fas fa-microchip"></i> ' + proc.cpu + '%</span>' +
            '<span class="service-detail"><i class="fas fa-memory"></i> ' + proc.memory_mb + 'MB</span>' +
            '</div>' +
            '<div class="service-details">' +
            '<span class="service-detail"><i class="fas fa-clock"></i> ' + proc.uptime_formatted + '</span>' +
            '<span class="service-detail"><i class="fas fa-redo"></i> ' + proc.restarts + '</span>' +
            '</div></div></div>' +
            '<div class="service-actions">' +
            (isOnline ?
                '<button class="btn-action btn-stop" onclick="stopService(\'' + proc.name + '\')" title="Stop"><i class="fas fa-stop"></i></button>' :
                '<button class="btn-action btn-start" onclick="startService(\'' + proc.name + '\')" title="Start"><i class="fas fa-play"></i></button>') +
            '<button class="btn-action btn-restart" onclick="restartService(\'' + proc.name + '\')" title="Restart"><i class="fas fa-sync-alt"></i></button>' +
            (isOnline ? '<button class="btn-action btn-reload" onclick="reloadService(\'' + proc.name + '\')" title="Reload"><i class="fas fa-redo-alt"></i></button>' : '') +
            '<button class="btn-action btn-logs" onclick="viewLogs(\'' + proc.name + '\')" title="Logs"><i class="fas fa-file-alt"></i></button>' +
            '<button class="btn-action btn-manage" onclick="openProcessModal(\'' + proc.name + '\')" title="Gerenciar"><i class="fas fa-cog"></i></button>' +
            '</div></div></div>';
    }
    container.innerHTML = html;
}

function updateServicesHealth(services) {
    const serviceMap = { 'casehub': 'casehub-health', 'ilc-tools': 'tools-health' };
    for (const [key, elemId] of Object.entries(serviceMap)) {
        const service = services.services[key];
        const elem = document.getElementById(elemId);
        if (elem && service) {
            elem.textContent = service.status.toUpperCase();
            elem.className = 'health-badge ' + service.status;
            if (key === 'ilc-tools' && service.response_time_ms) {
                const responseElem = document.getElementById('tools-response');
                if (responseElem) responseElem.textContent = Math.round(service.response_time_ms) + 'ms';
            }
        }
    }
}

function updateApplicationMetrics(apps) {
    if (!apps) return;

    // CaseHub
    if (apps.casehub && !apps.casehub.error) {
        document.getElementById('casehub-cases').textContent = apps.casehub.cases?.total || '0';
        document.getElementById('casehub-active').textContent = apps.casehub.cases?.active || '0';
        document.getElementById('casehub-clients').textContent = apps.casehub.clients?.total || '0';
        document.getElementById('casehub-sessions').textContent = apps.casehub.activity?.active_sessions || '0';
    }

    // Intake
    if (apps.intake && !apps.intake.error) {
        document.getElementById('intake-packages').textContent = apps.intake.packages?.total || '0';
        document.getElementById('intake-pending').textContent =
            (apps.intake.packages?.by_status?.sent || 0) + (apps.intake.packages?.by_status?.in_progress || 0);
        document.getElementById('intake-today').textContent = apps.intake.packages?.today || '0';
        document.getElementById('intake-rate').textContent = (apps.intake.metrics?.completion_rate || 0) + '%';
    }

    // Tools
    if (apps.tools && !apps.tools.error) {
        document.getElementById('tools-docs-today').textContent = apps.tools.documents?.generated_today || '0';
        document.getElementById('tools-docs-total').textContent = apps.tools.documents?.total_files || '0';
        document.getElementById('tools-requests').textContent = apps.tools.requests?.last_hour || '0';
    }
}

/**
 * Update recent activity log from server data
 */
function updateRecentActivity(activities) {
    if (!activities || activities.length === 0) return;
    
    const log = document.getElementById('activity-log');
    
    // Clear placeholder
    const placeholder = log.querySelector('.log-entry');
    if (placeholder && placeholder.textContent.includes('Aguardando')) {
        log.innerHTML = '';
    }
    
    // Build activity entries
    let html = '';
    for (const activity of activities) {
        const serviceStyles = {
            'tools': { icon: 'fa-tools', color: '#3fb950' },
            'casehub': { icon: 'fa-briefcase', color: '#58a6ff' },
            'intake': { icon: 'fa-clipboard-list', color: '#a371f7' },
            'system': { icon: 'fa-server', color: '#8b949e' },
        };
        const style = serviceStyles[activity.service] || { icon: 'fa-info-circle', color: '#8b949e' };
        
        // Format timestamp (handle both HH:MM:SS and full datetime)
        let timeStr = activity.timestamp;
        if (timeStr.includes(' ')) {
            timeStr = timeStr.split(' ')[1].substring(0, 8);
        }
        
        html += '<div class="log-entry">' +
            '<span class="log-time">' + timeStr + '</span>' +
            '<span class="log-service" style="color: ' + style.color + '">' +
            '<i class="fas ' + style.icon + '"></i> ' + activity.service + '</span>' +
            '<span class="log-message">' + activity.message + '</span></div>';
    }
    
    log.innerHTML = html;
}

async function restartService(name) {
    if (!confirm('Reiniciar ' + name + '?')) return;
    addLogEntry('pm2', 'Reiniciando ' + name + '...');
    try {
        const response = await fetch('/monitor/api/pm2/' + name + '/restart', { method: 'POST' });
        const result = await response.json();
        if (result.success) addLogEntry('pm2', name + ' reiniciado com sucesso');
        else addLogEntry('error', 'Falha ao reiniciar ' + name + ': ' + result.message);
        await fetchDashboardData();
    } catch (error) {
        addLogEntry('error', 'Erro ao reiniciar ' + name + ': ' + error.message);
    }
}

async function stopService(name) {
    if (!confirm('Parar ' + name + '? O servico ficara offline.')) return;
    addLogEntry('pm2', 'Parando ' + name + '...');
    try {
        const response = await fetch('/monitor/api/pm2/' + name + '/stop', { method: 'POST' });
        const result = await response.json();
        if (result.success) addLogEntry('pm2', name + ' parado com sucesso');
        else addLogEntry('error', 'Falha ao parar ' + name + ': ' + result.message);
        await fetchDashboardData();
    } catch (error) {
        addLogEntry('error', 'Erro ao parar ' + name + ': ' + error.message);
    }
}

async function startService(name) {
    addLogEntry('pm2', 'Iniciando ' + name + '...');
    try {
        const response = await fetch('/monitor/api/pm2/' + name + '/start', { method: 'POST' });
        const result = await response.json();
        if (result.success) addLogEntry('pm2', name + ' iniciado com sucesso');
        else addLogEntry('error', 'Falha ao iniciar ' + name + ': ' + result.message);
        await fetchDashboardData();
    } catch (error) {
        addLogEntry('error', 'Erro ao iniciar ' + name + ': ' + error.message);
    }
}

async function viewLogs(name) {
    addLogEntry('pm2', 'Carregando logs de ' + name + '...');
    try {
        const response = await fetch('/monitor/api/pm2/' + name + '/logs?lines=100');
        const result = await response.json();
        if (result.success) {
            showModal('Logs: ' + name, '<pre class="log-content">' + escapeHtml(result.logs) + '</pre>', [
                { label: 'Limpar Logs', class: 'btn-warning', onclick: () => flushLogs(name) },
                { label: 'Fechar', class: 'btn-secondary', onclick: closeModal }
            ]);
        } else {
            addLogEntry('error', 'Falha ao carregar logs: ' + result.error);
        }
    } catch (error) {
        addLogEntry('error', 'Erro ao carregar logs: ' + error.message);
    }
}

async function viewProcessInfo(name) {
    addLogEntry('pm2', 'Carregando info de ' + name + '...');
    try {
        const response = await fetch('/monitor/api/pm2/' + name + '/info');
        const result = await response.json();
        let content = '<pre class="log-content">' + escapeHtml(result.raw_output || 'Sem dados') + '</pre>';
        if (result.env_vars) {
            content += '<h6 class="mt-3">Variaveis de Ambiente:</h6><div class="env-vars">';
            for (const [key, value] of Object.entries(result.env_vars)) {
                // Hide sensitive values
                const displayValue = key.includes('TOKEN') || key.includes('SECRET') || key.includes('PASSWORD') || key.includes('KEY')
                    ? '********' : value;
                content += '<div class="env-var"><strong>' + escapeHtml(key) + ':</strong> ' + escapeHtml(displayValue) + '</div>';
            }
            content += '</div>';
        }
        showModal('Info: ' + name, content, [
            { label: 'Fechar', class: 'btn-secondary', onclick: closeModal }
        ]);
    } catch (error) {
        addLogEntry('error', 'Erro ao carregar info: ' + error.message);
    }
}

async function flushLogs(name) {
    if (!confirm('Limpar todos os logs de ' + name + '?')) return;
    try {
        const response = await fetch('/monitor/api/pm2/' + name + '/flush', { method: 'POST' });
        const result = await response.json();
        if (result.success) {
            addLogEntry('pm2', 'Logs de ' + name + ' limpos');
            closeModal();
        } else {
            addLogEntry('error', 'Falha ao limpar logs: ' + result.message);
        }
    } catch (error) {
        addLogEntry('error', 'Erro ao limpar logs: ' + error.message);
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showModal(title, content, buttons) {
    // Remove existing modal
    const existing = document.getElementById('pm2-modal');
    if (existing) existing.remove();

    let buttonsHtml = '';
    for (const btn of buttons) {
        buttonsHtml += '<button class="btn ' + btn.class + '" id="modal-btn-' + btn.label.replace(/\s/g, '') + '">' + btn.label + '</button>';
    }

    const modal = document.createElement('div');
    modal.id = 'pm2-modal';
    modal.className = 'pm2-modal';
    modal.innerHTML = '<div class="pm2-modal-content">' +
        '<div class="pm2-modal-header"><h5>' + title + '</h5><button class="btn-close" onclick="closeModal()"></button></div>' +
        '<div class="pm2-modal-body">' + content + '</div>' +
        '<div class="pm2-modal-footer">' + buttonsHtml + '</div></div>';

    document.body.appendChild(modal);

    // Attach button handlers
    for (const btn of buttons) {
        const btnElem = document.getElementById('modal-btn-' + btn.label.replace(/\s/g, ''));
        if (btnElem && btn.onclick) btnElem.onclick = btn.onclick;
    }
}

function closeModal() {
    const modal = document.getElementById('pm2-modal');
    if (modal) modal.remove();
}

function updateChartData(chart, history, value) {
    history.push(value);
    if (history.length > chartHistory.maxPoints) history.shift();
    chart.data.labels = history.map((_, i) => i);
    chart.data.datasets[0].data = history;
    chart.update('none');
}

function updateNetworkChart(inValue, outValue) {
    chartHistory.networkIn.push(inValue);
    chartHistory.networkOut.push(outValue);
    if (chartHistory.networkIn.length > chartHistory.maxPoints) {
        chartHistory.networkIn.shift();
        chartHistory.networkOut.shift();
    }
    networkChart.data.labels = chartHistory.networkIn.map((_, i) => i);
    networkChart.data.datasets[0].data = chartHistory.networkIn;
    networkChart.data.datasets[1].data = chartHistory.networkOut;
    networkChart.update('none');
}

function addLogEntry(type, message) {
    const log = document.getElementById('activity-log');
    const now = new Date();
    const time = now.toLocaleTimeString();
    const typeStyles = {
        'system': { icon: 'fa-server', color: '#58a6ff' },
        'pm2': { icon: 'fa-cubes', color: '#3fb950' },
        'error': { icon: 'fa-exclamation-triangle', color: '#f85149' },
        'user': { icon: 'fa-user', color: '#a371f7' },
    };
    const style = typeStyles[type] || { icon: 'fa-info-circle', color: '#8b949e' };

    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = '<span class="log-time">' + time + '</span>' +
        '<span class="log-service" style="color: ' + style.color + '">' +
        '<i class="fas ' + style.icon + '"></i> ' + type + '</span>' +
        '<span class="log-message">' + message + '</span>';

    log.insertBefore(entry, log.firstChild);
    while (log.children.length > 50) log.removeChild(log.lastChild);
}

// === New PM2 Control Functions ===

async function reloadService(name) {
    if (!confirm('Reload ' + name + ' com 0-downtime?')) return;
    addLogEntry('pm2', 'Reload ' + name + '...');
    try {
        const response = await fetch('/monitor/api/pm2/' + name + '/reload', { method: 'POST' });
        const result = await response.json();
        if (result.success) addLogEntry('pm2', name + ' reload concluido');
        else addLogEntry('error', 'Falha no reload de ' + name + ': ' + result.message);
        await fetchDashboardData();
    } catch (error) {
        addLogEntry('error', 'Erro no reload: ' + error.message);
    }
}

async function savePM2State() {
    addLogEntry('pm2', 'Salvando estado do PM2...');
    try {
        const response = await fetch('/monitor/api/pm2/save', { method: 'POST' });
        const result = await response.json();
        if (result.success) addLogEntry('pm2', 'Estado do PM2 salvo com sucesso');
        else addLogEntry('error', 'Falha ao salvar estado: ' + result.message);
    } catch (error) {
        addLogEntry('error', 'Erro ao salvar estado: ' + error.message);
    }
}

async function flushAllLogs() {
    if (!confirm('Limpar logs de todos os processos PM2?')) return;
    addLogEntry('pm2', 'Limpando todos os logs...');
    try {
        const response = await fetch('/monitor/api/pm2/flush', { method: 'POST' });
        const result = await response.json();
        if (result.success) addLogEntry('pm2', 'Todos os logs foram limpos');
        else addLogEntry('error', 'Falha ao limpar logs: ' + result.message);
    } catch (error) {
        addLogEntry('error', 'Erro ao limpar logs: ' + error.message);
    }
}

// === Process Modal Functions ===

async function openProcessModal(name) {
    currentModalProcess = name;
    const modal = document.getElementById('processModal');
    modal.style.display = 'flex';
    document.getElementById('modal-process-name').textContent = name;

    // Set tab listeners
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.onclick = () => switchTab(btn.dataset.tab);
    });

    // Load process data
    await refreshModalData();
}

function closeProcessModal() {
    document.getElementById('processModal').style.display = 'none';
    currentModalProcess = null;
}

function switchTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.style.display = pane.id === 'tab-' + tabName ? 'block' : 'none';
    });

    // Load data for specific tabs
    if (tabName === 'logs') refreshModalLogs();
}

async function refreshModalData() {
    if (!currentModalProcess) return;

    // Find process in current data
    const proc = currentPM2Data?.processes?.find(p => p.name === currentModalProcess);
    if (proc) {
        document.getElementById('modal-status').textContent = proc.status.toUpperCase();
        document.getElementById('modal-status').className = 'metric-value status-' + proc.status;
        document.getElementById('modal-cpu').textContent = proc.cpu + '%';
        document.getElementById('modal-memory').textContent = proc.memory_mb + ' MB';
        document.getElementById('modal-uptime').textContent = proc.uptime_formatted;
        document.getElementById('modal-restarts').textContent = proc.restarts;
        document.getElementById('modal-pid').textContent = proc.pid || 'N/A';
    }

    // Load describe data
    try {
        const response = await fetch('/monitor/api/pm2/' + currentModalProcess + '/describe');
        const result = await response.json();
        document.getElementById('modal-describe').innerHTML =
            '<pre>' + escapeHtml(result.describe || 'Sem dados') + '</pre>';
    } catch (error) {
        document.getElementById('modal-describe').innerHTML = '<pre>Erro ao carregar dados</pre>';
    }
}

async function refreshModalLogs() {
    if (!currentModalProcess) return;
    const lines = document.getElementById('log-lines').value;
    try {
        const response = await fetch('/monitor/api/pm2/' + currentModalProcess + '/logs?lines=' + lines);
        const result = await response.json();
        document.getElementById('modal-logs').innerHTML =
            '<pre>' + escapeHtml(result.logs || 'Sem logs') + '</pre>';
    } catch (error) {
        document.getElementById('modal-logs').innerHTML = '<pre>Erro ao carregar logs</pre>';
    }
}

async function flushProcessLogs() {
    if (!currentModalProcess) return;
    if (!confirm('Limpar logs de ' + currentModalProcess + '?')) return;
    try {
        const response = await fetch('/monitor/api/pm2/' + currentModalProcess + '/flush', { method: 'POST' });
        const result = await response.json();
        if (result.success) {
            addLogEntry('pm2', 'Logs de ' + currentModalProcess + ' limpos');
            await refreshModalLogs();
        }
    } catch (error) {
        addLogEntry('error', 'Erro ao limpar logs: ' + error.message);
    }
}

async function modalAction(action) {
    if (!currentModalProcess) return;

    const actionNames = {
        'start': 'Iniciar',
        'stop': 'Parar',
        'restart': 'Reiniciar',
        'reload': 'Reload',
        'reset': 'Zerar restarts de',
        'delete': 'Deletar'
    };

    if (action === 'delete' && !confirm('ATENCAO: Isso vai remover ' + currentModalProcess + ' do PM2. Continuar?')) return;
    if (action === 'stop' && !confirm('Parar ' + currentModalProcess + '? O servico ficara offline.')) return;

    addLogEntry('pm2', actionNames[action] + ' ' + currentModalProcess + '...');

    try {
        const endpoint = action === 'reset'
            ? '/monitor/api/pm2/' + currentModalProcess + '/reset'
            : '/monitor/api/pm2/' + currentModalProcess + '/' + action;
        const response = await fetch(endpoint, { method: action === 'delete' ? 'DELETE' : 'POST' });
        const result = await response.json();

        if (result.success) {
            addLogEntry('pm2', currentModalProcess + ': ' + action + ' concluido');
            if (action === 'delete') closeProcessModal();
        } else {
            addLogEntry('error', 'Falha: ' + result.message);
        }

        await fetchDashboardData();
        await refreshModalData();
    } catch (error) {
        addLogEntry('error', 'Erro: ' + error.message);
    }
}

async function scaleProcess() {
    if (!currentModalProcess) return;
    const instances = parseInt(document.getElementById('scale-instances').value);
    if (isNaN(instances) || instances < 1 || instances > 16) {
        alert('Numero de instancias deve ser entre 1 e 16');
        return;
    }

    addLogEntry('pm2', 'Escalando ' + currentModalProcess + ' para ' + instances + ' instancia(s)...');

    try {
        const response = await fetch('/monitor/api/pm2/' + currentModalProcess + '/scale/' + instances, { method: 'POST' });
        const result = await response.json();
        if (result.success) {
            addLogEntry('pm2', currentModalProcess + ' escalado para ' + instances + ' instancia(s)');
        } else {
            addLogEntry('error', 'Falha ao escalar: ' + result.message);
        }
        await fetchDashboardData();
        await refreshModalData();
    } catch (error) {
        addLogEntry('error', 'Erro ao escalar: ' + error.message);
    }
}

async function setMemoryLimit() {
    if (!currentModalProcess) return;
    const limit = document.getElementById('memory-limit').value.trim().toUpperCase();
    if (!limit || !/^\d+[MGK]$/.test(limit)) {
        alert('Formato invalido. Use: 500M, 1G, etc.');
        return;
    }

    if (!confirm('Definir limite de memoria de ' + limit + ' para ' + currentModalProcess + '? O processo sera reiniciado.')) return;

    addLogEntry('pm2', 'Definindo limite de memoria ' + limit + ' para ' + currentModalProcess + '...');

    try {
        const response = await fetch('/monitor/api/pm2/' + currentModalProcess + '/memory-limit/' + limit, { method: 'POST' });
        const result = await response.json();
        if (result.success) {
            addLogEntry('pm2', 'Limite de memoria definido para ' + currentModalProcess);
        } else {
            addLogEntry('error', 'Falha: ' + result.message);
        }
        await fetchDashboardData();
        await refreshModalData();
    } catch (error) {
        addLogEntry('error', 'Erro: ' + error.message);
    }
}

// Close modal on outside click
document.addEventListener('click', (e) => {
    const modal = document.getElementById('processModal');
    if (e.target === modal) closeProcessModal();
});

// Close modal on escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeProcessModal();
});

// ========== USER ACTIVITY MONITORING ==========

let activityEventSource = null;

/**
 * Initialize user activity monitoring
 */
function initActivityMonitoring() {
    // Initial fetch
    fetchActivityData();

    // Connect to activity SSE stream
    connectActivitySSE();

    // Fallback polling every 3 seconds
    setInterval(() => {
        if (!activityEventSource || activityEventSource.readyState !== EventSource.OPEN) {
            fetchActivityData();
        }
    }, 3000);
}

/**
 * Connect to activity SSE stream
 */
function connectActivitySSE() {
    if (activityEventSource) activityEventSource.close();

    try {
        activityEventSource = new EventSource('/monitor/api/activity/stream');

        activityEventSource.addEventListener('activity_update', (e) => {
            try {
                const data = JSON.parse(e.data);
                updateActivityUI(data);
            } catch (err) {
                console.error('Activity SSE parse error:', err);
            }
        });

        activityEventSource.onerror = () => {
            console.log('Activity SSE disconnected, using polling');
        };
    } catch (err) {
        console.error('Activity SSE connection failed:', err);
    }
}

/**
 * Fetch activity data via API
 */
async function fetchActivityData() {
    try {
        const [usersResponse, feedResponse] = await Promise.all([
            fetch('/monitor/api/activity/users?minutes=5'),
            fetch('/monitor/api/activity/feed?limit=20')
        ]);

        const usersData = await usersResponse.json();
        const feedData = await feedResponse.json();

        updateActivityUI({
            active_count: usersData.total_active || 0,
            by_source: usersData.by_source || {},
            users: usersData.users || [],
            recent_events: feedData.events || []
        });
    } catch (error) {
        console.error('Failed to fetch activity data:', error);
    }
}

/**
 * Update the activity UI with new data
 */
function updateActivityUI(data) {
    // Update online count
    const totalOnline = data.active_count || 0;
    document.getElementById('total-online').textContent = totalOnline;
    document.getElementById('online-count').textContent = totalOnline;

    // Update source breakdown
    const sources = data.by_source || {};
    const sourceBreakdown = document.getElementById('source-breakdown');
    sourceBreakdown.innerHTML =
        '<span class="source-badge wp">WP: ' + (sources.wordpress || 0) + '</span>' +
        '<span class="source-badge ch">CH: ' + (sources.casehub || 0) + '</span>' +
        '<span class="source-badge tools">Tools: ' + (sources['ilc-tools'] || 0) + '</span>';

    // Update users list
    updateUsersList(data.users || []);

    // Update activity feed
    updateActivityFeed(data.recent_events || []);
}

/**
 * Update the active users list
 */
function updateUsersList(users) {
    const container = document.getElementById('active-users-list');

    if (!users || users.length === 0) {
        container.innerHTML = '<div class="user-item empty">Nenhum usuario ativo</div>';
        return;
    }

    let html = '';
    for (const user of users) {
        const isAdmin = user.is_admin || user.user_type === 'admin';
        const sourceClass = user.source || 'wordpress';

        html += '<div class="user-item' + (isAdmin ? ' admin' : '') + '">' +
            '<div class="user-info">' +
            '<div class="user-name">' +
            escapeHtml(user.user_name || 'Visitante') +
            (isAdmin ? ' <span class="admin-badge">ADMIN</span>' : '') +
            '</div>' +
            '<div class="user-page" title="' + escapeHtml(user.current_page || '') + '">' +
            escapeHtml(user.current_page_title || user.current_page || '/') +
            '</div>' +
            '</div>' +
            '<div class="user-meta">' +
            '<div class="user-source ' + sourceClass + '">' + sourceClass.toUpperCase() + '</div>' +
            '<div>' + (user.time_on_site || '0m') + ' | ' + (user.page_views || 0) + ' pgs</div>' +
            '</div>' +
            '</div>';
    }

    container.innerHTML = html;
}

/**
 * Update the activity feed
 */
function updateActivityFeed(events) {
    const container = document.getElementById('user-activity-feed');

    if (!events || events.length === 0) {
        container.innerHTML = '<div class="feed-item empty">Aguardando atividade...</div>';
        return;
    }

    let html = '';
    for (const event of events) {
        const eventType = event.event_type || 'unknown';
        const timestamp = event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : '';

        // Build action text based on event type
        let actionText = '';
        switch (eventType) {
            case 'pageview':
                actionText = 'abriu <span class="feed-detail">' + escapeHtml(event.page_title || event.page_url || '') + '</span>';
                break;
            case 'click':
                actionText = 'clicou em <span class="feed-detail">' + escapeHtml(event.element_text || 'botao') + '</span>';
                break;
            case 'form_submit':
                actionText = 'enviou formulario';
                break;
            case 'form_interaction':
                actionText = 'preencheu campo';
                break;
            case 'scroll':
                const depth = event.metadata?.scroll_depth || '';
                actionText = 'scroll ' + depth + '%';
                break;
            case 'navigation':
                actionText = 'navegou para <span class="feed-detail">' + escapeHtml(event.page_url || '') + '</span>';
                break;
            default:
                actionText = eventType;
        }

        html += '<div class="feed-item ' + eventType + '">' +
            '<span class="feed-time">' + timestamp + '</span>' +
            '<span class="feed-user">' + escapeHtml(event.user_name || 'Visitante') + '</span> ' +
            '<span class="feed-action">' + actionText + '</span>' +
            '</div>';
    }

    container.innerHTML = html;
}

// Start activity monitoring when page loads
document.addEventListener('DOMContentLoaded', () => {
    initActivityMonitoring();
});

// ============================================
// WhatsApp & Lead Monitor Integration
// ============================================

const WHATSAPP_API_BASE = "";  // Same origin, proxied via nginx

/**
 * Fetch WhatsApp bot status
 */
async function fetchWhatsAppStatus() {
    try {
        const response = await fetch("/whatsapp-api/");
        if (response.ok) {
            const data = await response.json();
            updateWhatsAppStatus(data);
        }
    } catch (error) {
        console.error("Error fetching WhatsApp status:", error);
        const healthEl = document.getElementById("whatsapp-health");
        if (healthEl) {
            healthEl.textContent = "ERROR";
            healthEl.className = "health-badge bg-danger";
        }
    }
}

/**
 * Update WhatsApp status in UI
 */
function updateWhatsAppStatus(data) {
    const healthEl = document.getElementById("whatsapp-health");
    const connectedEl = document.getElementById("whatsapp-connected");

    if (!healthEl || !connectedEl) return;

    if (data.isReady) {
        healthEl.textContent = "ONLINE";
        healthEl.className = "health-badge bg-success";
        connectedEl.textContent = "Sim";
    } else {
        healthEl.textContent = "OFFLINE";
        healthEl.className = "health-badge bg-danger";
        connectedEl.textContent = "Nao";
    }
}

/**
 * Fetch Lead Monitor status
 */
async function fetchLeadMonitorStatus() {
    try {
        const response = await fetch("/whatsapp-api/api/monitor/status");
        if (response.ok) {
            const data = await response.json();
            updateLeadMonitorStatus(data);
        }
    } catch (error) {
        console.error("Error fetching lead monitor status:", error);
    }
}

/**
 * Update Lead Monitor status in UI
 */
function updateLeadMonitorStatus(data) {
    const healthEl = document.getElementById("lead-monitor-health");
    const statusEl = document.getElementById("lead-monitor-status");
    const lastEl = document.getElementById("lead-monitor-last");

    if (!healthEl) return;

    if (data.scheduler && data.scheduler.isRunning !== false) {
        healthEl.textContent = "ATIVO";
        healthEl.className = "health-badge bg-success";
        if (statusEl) statusEl.textContent = "Rodando";
    } else {
        healthEl.textContent = "PARADO";
        healthEl.className = "health-badge bg-warning";
        if (statusEl) statusEl.textContent = "Inativo";
    }

    if (data.scheduler && data.scheduler.lastCheck && lastEl) {
        const lastCheck = new Date(data.scheduler.lastCheck);
        lastEl.textContent = lastCheck.toLocaleTimeString();
    }
}

/**
 * Fetch leads needing attention
 */
async function fetchLeadsNeedingAttention() {
    try {
        const response = await fetch("/whatsapp-api/api/monitor/leads-needing-attention");
        if (response.ok) {
            const data = await response.json();
            updateLeadsAttention(data.leads || []);
        }
    } catch (error) {
        console.error("Error fetching leads:", error);
    }
}

/**
 * Update leads needing attention list
 */
function updateLeadsAttention(leads) {
    const countEl = document.getElementById("leads-attention-count");
    const listEl = document.getElementById("leads-attention-list");

    if (!countEl || !listEl) return;

    countEl.textContent = leads.length;

    if (leads.length === 0) {
        listEl.innerHTML = '<div class="text-success small"><i class="fas fa-check"></i> Nenhuma lead precisando de atencao</div>';
        return;
    }

    let html = "";
    for (const lead of leads.slice(0, 5)) {
        const name = lead.client_name || lead.whatsapp_name || lead.phone;
        const minutes = lead.minutes_since_last_message || 0;
        const urgentClass = lead.is_urgent ? "text-danger" : "";

        html += '<div class="lead-item d-flex justify-content-between align-items-center py-1 border-bottom">' +
            '<span class="' + urgentClass + '">' +
            (lead.is_urgent ? '<i class="fas fa-exclamation-circle text-danger"></i> ' : '') +
            escapeHtml(name) + '</span>' +
            '<small class="text-muted">' + minutes + ' min</small>' +
            '</div>';
    }

    if (leads.length > 5) {
        html += '<div class="text-center mt-2"><a href="/whatsapp/monitor" target="_blank" class="btn btn-sm btn-outline-warning">Ver todas (' + leads.length + ')</a></div>';
    }

    listEl.innerHTML = html;
}

/**
 * Initialize WhatsApp monitoring
 */
function initWhatsAppMonitoring() {
    // Initial fetch
    fetchWhatsAppStatus();
    fetchWhatsAppMetrics();
    fetchLeadMonitorStatus();
    fetchLeadsNeedingAttention();

    // Refresh every 30 seconds
    setInterval(function() {
        fetchWhatsAppStatus();
    fetchWhatsAppMetrics();
        fetchLeadMonitorStatus();
        fetchLeadsNeedingAttention();
    }, 30000);
}

// Start WhatsApp monitoring when page loads
document.addEventListener("DOMContentLoaded", function() {
    initWhatsAppMonitoring();
});

// ============================================
// Email Worker Monitoring
// ============================================

/**
 * Fetch Email Worker status from CaseHub
 */
async function fetchEmailWorkerStatus() {
    try {
        const response = await fetch("/casehub/api/email-worker/status");
        if (response.ok) {
            const data = await response.json();
            updateEmailWorkerStatus(data);
        } else {
            setEmailWorkerError("API Error");
        }
    } catch (error) {
        console.error("Error fetching email worker status:", error);
        setEmailWorkerError("Connection Error");
    }
}

/**
 * Update Email Worker status in UI
 */
function updateEmailWorkerStatus(data) {
    // Health badge
    const healthEl = document.getElementById("email-worker-health");
    if (healthEl) {
        if (data.status === "healthy") {
            healthEl.textContent = "ONLINE";
            healthEl.className = "health-badge bg-success";
        } else if (data.status === "warning") {
            healthEl.textContent = "WARNING";
            healthEl.className = "health-badge bg-warning";
        } else {
            healthEl.textContent = "CRITICAL";
            healthEl.className = "health-badge bg-danger";
        }
    }

    // Status text
    const statusEl = document.getElementById("email-worker-status");
    if (statusEl) {
        statusEl.textContent = data.worker_active ? "Ativo" : "Inativo";
    }

    // Pending emails
    const pendingEl = document.getElementById("email-worker-pending");
    if (pendingEl) {
        pendingEl.textContent = data.pending_emails || 0;
        pendingEl.className = data.pending_emails > 5 ? "stat-value text-warning" : "stat-value text-success";
    }

    // Emails today
    const emailsTodayEl = document.getElementById("emails-today");
    if (emailsTodayEl) {
        emailsTodayEl.textContent = data.emails_today || 0;
    }

    // Tasks today
    const tasksTodayEl = document.getElementById("tasks-today");
    if (tasksTodayEl) {
        tasksTodayEl.textContent = data.tasks_today || 0;
    }

    // Last task time
    const lastTaskEl = document.getElementById("last-task-time");
    if (lastTaskEl && data.last_task_created) {
        const lastTask = new Date(data.last_task_created);
        lastTaskEl.textContent = lastTask.toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'});
    }

    // Recent emails list
    updateRecentEmailsList(data.recent_emails || []);
}

/**
 * Update recent emails list
 */
function updateRecentEmailsList(emails) {
    const listEl = document.getElementById("recent-emails-list");
    if (!listEl) return;

    if (emails.length === 0) {
        listEl.innerHTML = '<div class="text-muted small">Nenhum email recente</div>';
        return;
    }

    let html = "";
    for (const email of emails) {
        const statusIcon = email.has_task 
            ? '<i class="fas fa-check-circle text-success"></i>' 
            : '<i class="fas fa-clock text-warning"></i>';
        
        const sender = email.sender || "Unknown";
        const time = email.received ? new Date(email.received).toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'}) : "--";
        
        html += '<div class="d-flex justify-content-between align-items-center py-1 border-bottom">' +
            '<span class="small">' + statusIcon + ' ' + escapeHtml(sender.substring(0, 35)) + '</span>' +
            '<small class="text-muted">' + time + '</small>' +
            '</div>';
    }

    listEl.innerHTML = html;
}

/**
 * Set error state for email worker
 */
function setEmailWorkerError(message) {
    const healthEl = document.getElementById("email-worker-health");
    if (healthEl) {
        healthEl.textContent = "ERROR";
        healthEl.className = "health-badge bg-danger";
    }
    
    const statusEl = document.getElementById("email-worker-status");
    if (statusEl) {
        statusEl.textContent = message;
    }
}

/**
 * Initialize Email Worker monitoring
 */
function initEmailWorkerMonitoring() {
    // Initial fetch
    fetchEmailWorkerStatus();
    
    // Refresh every 30 seconds
    setInterval(fetchEmailWorkerStatus, 30000);
}

// Add to page load
document.addEventListener("DOMContentLoaded", function() {
    initEmailWorkerMonitoring();
});

/**
 * Fetch WhatsApp metrics from VPS Monitor API
 */
async function fetchWhatsAppMetrics() {
    try {
        const response = await fetch("/monitor/api/whatsapp");
        if (response.ok) {
            const data = await response.json();
            updateWhatsAppMetrics(data);
            updateExtraWhatsAppMetrics(data);
        }
    } catch (error) {
        console.error("Error fetching WhatsApp metrics:", error);
    }
}

/**
 * Update WhatsApp metrics in UI
 */
function updateWhatsAppMetrics(data) {
    // Get all UI elements
    const weekEl = document.getElementById("whatsapp-leads-week");
    const awaitingEl = document.getElementById("whatsapp-awaiting");
    const activeEl = document.getElementById("whatsapp-active");
    const totalEl = document.getElementById("whatsapp-total");
    const healthEl = document.getElementById("whatsapp-health");
    const connectedEl = document.getElementById("whatsapp-connected");
    const leadsEl = document.getElementById("whatsapp-leads-today");
    const msgsEl = document.getElementById("whatsapp-msgs-today");
    const modeEl = document.getElementById("whatsapp-bot-mode");

    // Update connection status
    if (healthEl) {
        if (data.isReady && data.connected) {
            healthEl.textContent = "ONLINE";
            healthEl.className = "health-badge bg-success";
        } else if (data.hasQrCode) {
            healthEl.textContent = "QR CODE";
            healthEl.className = "health-badge bg-warning";
        } else {
            healthEl.textContent = "OFFLINE";
            healthEl.className = "health-badge bg-danger";
        }
    }

    if (connectedEl) {
        connectedEl.textContent = data.connected ? "Sim" : "Nao";
    }

    if (leadsEl) {
        leadsEl.textContent = data.leads_today || "0";
    }

    if (msgsEl) {
        msgsEl.textContent = data.messages_today || "0";
    }

    if (modeEl) {
        modeEl.textContent = data.ok ? "Ativo" : "Inativo";
    }
}

// Additional WhatsApp metrics updates (called after main updateWhatsAppMetrics)
function updateExtraWhatsAppMetrics(data) {
    const weekEl = document.getElementById("whatsapp-leads-week");
    const awaitingEl = document.getElementById("whatsapp-awaiting");
    const activeEl = document.getElementById("whatsapp-active");
    const totalEl = document.getElementById("whatsapp-total");

    if (weekEl) weekEl.textContent = data.leads_week || "0";
    if (awaitingEl) awaitingEl.textContent = data.awaiting_human || "0";
    if (activeEl) activeEl.textContent = data.active_conversations || "0";
    if (totalEl) totalEl.textContent = data.total_leads || "0";
}

/**
 * Fetch external integrations health
 */
async function fetchIntegrationsHealth() {
    try {
        const response = await fetch("/monitor/api/integrations");
        if (response.ok) {
            const data = await response.json();
            updateIntegrationsHealth(data);
        }
    } catch (error) {
        console.error("Error fetching integrations health:", error);
    }
}

/**
 * Update integrations health in UI
 */
function updateIntegrationsHealth(data) {
    // Moskit
    const moskitHealth = document.getElementById("moskit-health");
    const moskitResponse = document.getElementById("moskit-response");
    const moskitUsers = document.getElementById("moskit-users");
    
    if (moskitHealth && data.moskit) {
        const m = data.moskit;
        moskitHealth.textContent = m.status === "healthy" ? "OK" : m.status.toUpperCase();
        moskitHealth.className = "health-badge " + (m.status === "healthy" ? "bg-success" : "bg-danger");
        if (moskitResponse) moskitResponse.textContent = m.response_time_ms ? m.response_time_ms + "ms" : "--";
        if (moskitUsers) moskitUsers.textContent = m.total_users || "--";
    }
    
    // Gemini
    const geminiHealth = document.getElementById("gemini-health");
    const geminiResponse = document.getElementById("gemini-response");
    const geminiModels = document.getElementById("gemini-models");
    
    if (geminiHealth && data.gemini) {
        const g = data.gemini;
        geminiHealth.textContent = g.status === "healthy" ? "OK" : g.status.toUpperCase();
        geminiHealth.className = "health-badge " + (g.status === "healthy" ? "bg-success" : "bg-danger");
        if (geminiResponse) geminiResponse.textContent = g.response_time_ms ? g.response_time_ms + "ms" : "--";
        if (geminiModels) geminiModels.textContent = g.models_available || "--";
    }
    
    // Stripe
    const stripeHealth = document.getElementById("stripe-health");
    const stripeResponse = document.getElementById("stripe-response");
    const stripeStatus = document.getElementById("stripe-status");
    
    if (stripeHealth && data.stripe) {
        const s = data.stripe;
        stripeHealth.textContent = s.status === "reachable" ? "OK" : s.status.toUpperCase();
        stripeHealth.className = "health-badge " + (s.status === "reachable" ? "bg-success" : "bg-warning");
        if (stripeResponse) stripeResponse.textContent = s.response_time_ms ? s.response_time_ms + "ms" : "--";
        if (stripeStatus) stripeStatus.textContent = s.status === "reachable" ? "Ativo" : s.status;
    }
    
    // Calendly
    const calendlyHealth = document.getElementById("calendly-health");
    const calendlyStatus = document.getElementById("calendly-status");
    
    if (calendlyHealth && data.calendly) {
        const c = data.calendly;
        calendlyHealth.textContent = c.status === "not_configured" ? "N/C" : c.status.toUpperCase();
        calendlyHealth.className = "health-badge " + (c.status === "not_configured" ? "bg-secondary" : "bg-success");
        if (calendlyStatus) calendlyStatus.textContent = c.message || c.status;
    }
}

// Add to initialization
document.addEventListener("DOMContentLoaded", function() {
    fetchIntegrationsHealth();
    setInterval(fetchIntegrationsHealth, 60000); // Refresh every minute
});

/**
 * Fetch database metrics
 */
async function fetchDatabaseMetrics() {
    try {
        const response = await fetch("/monitor/api/databases");
        if (response.ok) {
            const data = await response.json();
            updateDatabaseMetrics(data);
        }
    } catch (error) {
        console.error("Error fetching database metrics:", error);
    }
}

/**
 * Update database metrics in UI
 */
function updateDatabaseMetrics(data) {
    // MySQL
    const mysqlHealth = document.getElementById("mysql-health");
    const mysqlConnections = document.getElementById("mysql-connections");
    const mysqlSize = document.getElementById("mysql-size");
    const mysqlLeads = document.getElementById("mysql-leads");
    const mysqlMsgs = document.getElementById("mysql-msgs");
    
    if (mysqlHealth && data.mysql) {
        const m = data.mysql;
        mysqlHealth.textContent = m.status === "healthy" ? "OK" : "ERROR";
        mysqlHealth.className = "health-badge " + (m.status === "healthy" ? "bg-success" : "bg-danger");
        if (mysqlConnections) mysqlConnections.textContent = m.active_connections || "0";
        if (mysqlSize) mysqlSize.textContent = (m.database_size_mb || 0).toFixed(1) + " MB";
        if (mysqlLeads) mysqlLeads.textContent = m.leads_total || "0";
        if (mysqlMsgs) mysqlMsgs.textContent = m.conversations_total || "0";
    }
    
    // PostgreSQL
    const pgHealth = document.getElementById("postgres-health");
    const pgConnections = document.getElementById("postgres-connections");
    const pgSize = document.getElementById("postgres-size");
    const pgClients = document.getElementById("postgres-clients");
    const pgCases = document.getElementById("postgres-cases");
    
    if (pgHealth && data.postgres) {
        const p = data.postgres;
        pgHealth.textContent = p.status === "healthy" ? "OK" : "ERROR";
        pgHealth.className = "health-badge " + (p.status === "healthy" ? "bg-success" : "bg-danger");
        if (pgConnections) pgConnections.textContent = p.active_connections + "/" + p.total_connections;
        if (pgSize) pgSize.textContent = p.database_size || "--";
        if (pgClients) pgClients.textContent = p.clients_total || "0";
        if (pgCases) pgCases.textContent = p.cases_total || "0";
    }
}

// Add database monitoring to initialization
document.addEventListener("DOMContentLoaded", function() {
    fetchDatabaseMetrics();
    setInterval(fetchDatabaseMetrics, 30000); // Refresh every 30 seconds
});

async function fetchNginxMetrics() {
    try {
        const response = await fetch("/monitor/api/nginx");
        const data = await response.json();
        updateNginxMetrics(data);
    } catch (error) {
        console.error("Error fetching Nginx metrics:", error);
        const healthBadge = document.getElementById("nginx-health");
        if (healthBadge) {
            healthBadge.textContent = "ERROR";
            healthBadge.className = "health-badge bg-danger";
        }
    }
}

function updateNginxMetrics(data) {
    // Health badge
    const healthBadge = document.getElementById("nginx-health");
    if (healthBadge) {
        healthBadge.textContent = data.status === "healthy" ? "OK" : data.status === "warning" ? "WARN" : "ERR";
        healthBadge.className = "health-badge " + 
            (data.status === "healthy" ? "bg-success" : data.status === "warning" ? "bg-warning" : "bg-danger");
    }
    
    // Requests
    const requests5min = document.getElementById("nginx-requests-5min");
    const requestsPerMin = document.getElementById("nginx-requests-per-min");
    if (data.requests) {
        if (requests5min) requests5min.textContent = data.requests.requests_last_5min || "0";
        if (requestsPerMin) requestsPerMin.textContent = (data.requests.requests_per_minute || 0).toFixed(1);
    }
    
    // Status codes
    const codes = data.status_codes || {};
    const code2xx = document.getElementById("nginx-2xx");
    const code3xx = document.getElementById("nginx-3xx");
    const code4xx = document.getElementById("nginx-4xx");
    const code5xx = document.getElementById("nginx-5xx");
    if (code2xx) code2xx.textContent = codes["2xx"] || "0";
    if (code3xx) code3xx.textContent = codes["3xx"] || "0";
    if (code4xx) code4xx.textContent = codes["4xx"] || "0";
    if (code5xx) code5xx.textContent = codes["5xx"] || "0";
    
    // Errors
    const errorCount = document.getElementById("nginx-error-count");
    const errorRate = document.getElementById("nginx-error-rate");
    if (data.errors && errorCount) {
        errorCount.textContent = data.errors.error_count_recent || "0";
    }
    if (errorRate) {
        errorRate.textContent = (data.error_rate_percent || 0).toFixed(1) + "%";
    }
    
    // Top Endpoints
    const topEndpoints = document.getElementById("nginx-top-endpoints");
    if (topEndpoints && data.top_endpoints && data.top_endpoints.length > 0) {
        let html = "";
        for (const ep of data.top_endpoints) {
            html += "<div class=\"d-flex justify-content-between border-bottom py-1\">";
            html += "<span class=\"text-truncate\" style=\"max-width:150px;\">" + ep.path + "</span>";
            html += "<span class=\"text-muted\">" + ep.count + "</span></div>";
        }
        topEndpoints.innerHTML = html;
    } else if (topEndpoints) {
        topEndpoints.innerHTML = "<div class=\"text-muted\">Sem dados</div>";
    }
}

// Initialize Nginx metrics
(function initNginxMetrics() {
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function() {
            fetchNginxMetrics();
            setInterval(fetchNginxMetrics, 30000);
        });
    } else {
        fetchNginxMetrics();
        setInterval(fetchNginxMetrics, 30000);
    }
})();


// ============================================
// Sentinela Auto-Healing Integration
// ============================================

let sentinelaData = null;

function switchMainTab(tab) {
    var overviewPanel = document.getElementById("overview-panel");
    var sentinelaPanel = document.getElementById("sentinela-panel");
    var maestroPanel = document.getElementById("maestro-panel");
    var btnOverview = document.getElementById("btn-tab-overview");
    var btnSentinela = document.getElementById("btn-tab-sentinela");
    var btnMaestro = document.getElementById("btn-tab-maestro");
    var secSection = document.getElementById("security-section");

    if (overviewPanel) overviewPanel.style.display = "none";
    if (sentinelaPanel) sentinelaPanel.style.display = "none";
    if (maestroPanel) maestroPanel.style.display = "none";
    if (btnOverview) btnOverview.classList.remove("active");
    if (btnSentinela) btnSentinela.classList.remove("active");
    if (btnMaestro) btnMaestro.classList.remove("active");

    if (tab === "sentinela") {
        if (sentinelaPanel) sentinelaPanel.style.display = "block";
        if (btnSentinela) btnSentinela.classList.add("active");
        if (secSection) secSection.style.display = "none";
        fetchSentinelaData();
    } else if (tab === "maestro") {
        if (maestroPanel) maestroPanel.style.display = "block";
        if (btnMaestro) btnMaestro.classList.add("active");
        if (secSection) secSection.style.display = "none";
        fetchMaestroData();
    } else {
        if (overviewPanel) overviewPanel.style.display = "block";
        if (btnOverview) btnOverview.classList.add("active");
        if (secSection) secSection.style.display = "block";
    }
}
async function fetchSentinelaData() {
    try {
        const [statusRes, canaryRes, trendsRes, incidentsRes] = await Promise.all([
            fetch("/monitor/api/sentinela/status"),
            fetch("/monitor/api/sentinela/canaries"),
            fetch("/monitor/api/sentinela/trends"),
            fetch("/monitor/api/sentinela/incidents")
        ]);

        if (statusRes.ok) {
            const status = await statusRes.json();
            sentinelaData = status;
            renderSentinelaScores(status);
            renderSentinelaHealingStatus(status);
            updateSentinelaDot(status);

            const updateEl = document.getElementById("snt-last-update");
            if (updateEl) {
                updateEl.textContent = "Atualizado " + new Date().toLocaleTimeString("pt-BR", {hour:"2-digit", minute:"2-digit"});
                updateEl.className = "badge bg-success ms-2";
            }
        }

        if (canaryRes.ok) {
            const canaries = await canaryRes.json();
            renderSentinelaCanaries(canaries);
        }

        if (trendsRes.ok) {
            const trends = await trendsRes.json();
            renderSentinelaTrends(trends);
        }

        if (incidentsRes.ok) {
            const incidents = await incidentsRes.json();
            renderSentinelaIncidents(incidents);
        }

    } catch (e) {
        console.error("Sentinela fetch error:", e);
        const dot = document.getElementById("sentinela-health-dot");
        if (dot) dot.className = "snt-status-dot offline";

        const updateEl = document.getElementById("snt-last-update");
        if (updateEl) {
            updateEl.textContent = "Sentinela Offline";
            updateEl.className = "badge bg-danger ms-2";
        }
    }
}

function renderSentinelaScores(data) {
    const grid = document.getElementById("snt-scores-grid");
    if (!grid) return;

    const scores = data.scores || data.services || {};
    let html = "";

    for (const [name, info] of Object.entries(scores)) {
        const score = typeof info === "object" ? (info.score || 0) : info;
        const severity = typeof info === "object" ? (info.severity || getSeverity(score)) : getSeverity(score);
        const colorClass = severityColor(severity);
        const barColor = severityBarColor(severity);

        html += '<div class="col-md-4 col-sm-6">';
        html += '<div class="snt-score-card">';
        html += '<div class="snt-score-header">';
        html += '<span class="snt-service-name">' + escapeHtml(name) + '</span>';
        html += '<span class="snt-severity-badge ' + colorClass + '">' + severity.toUpperCase() + '</span>';
        html += '</div>';
        html += '<div class="snt-score-value ' + colorClass + '">' + Math.round(score) + '</div>';
        html += '<div class="progress" style="height:6px">';
        html += '<div class="progress-bar ' + barColor + '" style="width:' + score + '%"></div>';
        html += '</div>';
        html += '</div></div>';
    }

    grid.innerHTML = html || '<div class="col-12 text-muted text-center py-3">Sem dados de scores</div>';
}

function renderSentinelaCanaries(data) {
    const grid = document.getElementById("snt-canaries-grid");
    const countEl = document.getElementById("snt-canary-count");
    if (!grid) return;

    const canaries = data.canaries || data || [];
    if (!Array.isArray(canaries)) return;

    let passed = 0;
    let html = "";

    for (const c of canaries) {
        const ok = c.passed;
        if (ok) passed++;
        const icon = ok ? "check-circle" : "times-circle";
        const color = ok ? "text-success" : "text-danger";
        const latency = c.latency_ms ? c.latency_ms.toFixed(0) + "ms" : "--";

        html += '<div class="col-md-3 col-sm-4 col-6">';
        html += '<div class="snt-canary-item ' + (ok ? "" : "snt-canary-fail") + '">';
        html += '<i class="fas fa-' + icon + ' ' + color + '"></i> ';
        html += '<span class="snt-canary-name">' + escapeHtml(c.check_name || "") + '</span>';
        html += '<span class="snt-canary-latency">' + latency + '</span>';
        if (!ok && c.error) {
            html += '<div class="snt-canary-error">' + escapeHtml(c.error) + '</div>';
        }
        html += '</div></div>';
    }

    grid.innerHTML = html;

    if (countEl) {
        countEl.textContent = passed + "/" + canaries.length;
        countEl.className = "badge ms-2 " + (passed === canaries.length ? "bg-success" : "bg-warning");
    }
}

function renderSentinelaTrends(data) {
    const section = document.getElementById("snt-trends-section");
    const list = document.getElementById("snt-trends-list");
    if (!section || !list) return;

    const warnings = data.warnings || data.trends || [];
    if (!Array.isArray(warnings) || warnings.length === 0) {
        section.style.display = "none";
        return;
    }

    section.style.display = "block";
    let html = "";

    for (const w of warnings) {
        const sev = w.severity || "yellow";
        const colorClass = severityColor(sev);
        html += '<div class="snt-trend-item">';
        html += '<span class="snt-severity-badge ' + colorClass + '">' + sev.toUpperCase() + '</span> ';
        html += '<strong>' + escapeHtml(w.service || "") + '</strong>: ';
        html += escapeHtml(w.message || w.warning || "");
        html += '</div>';
    }

    list.innerHTML = html;
}

function renderSentinelaIncidents(data) {
    const list = document.getElementById("snt-incidents-list");
    const countEl = document.getElementById("snt-incident-count");
    if (!list) return;

    const incidents = data.incidents || data || [];
    if (!Array.isArray(incidents)) return;

    // Filter open incidents
    const open = incidents.filter(function(i) { return i.status === "open" || !i.resolved_at; });

    if (countEl) {
        countEl.textContent = open.length;
        countEl.className = "badge ms-2 " + (open.length === 0 ? "bg-success" : "bg-danger");
    }

    if (open.length === 0) {
        list.innerHTML = '<div class="text-center text-muted py-3"><i class="fas fa-check-circle text-success"></i> Nenhum incidente aberto</div>';
        return;
    }

    let html = "";
    for (const inc of open) {
        const sev = inc.severity || "yellow";
        const colorClass = severityColor(sev);
        const started = inc.started_at || inc.created_at || "";
        const timeStr = started ? new Date(started).toLocaleString("pt-BR") : "--";

        html += '<div class="snt-incident-row">';
        html += '<span class="snt-severity-badge ' + colorClass + '">' + sev.toUpperCase() + '</span> ';
        html += '<strong>' + escapeHtml(inc.service || "") + '</strong> - ';
        html += escapeHtml(inc.description || inc.message || "Incidente aberto");
        html += '<span class="snt-incident-time">' + timeStr + '</span>';
        html += '</div>';
    }

    list.innerHTML = html;
}

function renderSentinelaHealingStatus(data) {
    const healEl = document.getElementById("snt-heal-status");
    const circuitEl = document.getElementById("snt-circuit-status");
    const uptimeEl = document.getElementById("snt-uptime");

    if (healEl) {
        const enabled = data.healing_enabled !== undefined ? data.healing_enabled : true;
        healEl.textContent = enabled ? "ATIVO" : "DESATIVADO";
        healEl.className = "metric-value " + (enabled ? "text-success" : "text-danger");
        healEl.style.fontSize = "1.2rem";
    }

    if (circuitEl) {
        const tripped = data.circuit_breakers_tripped || 0;
        circuitEl.textContent = tripped > 0 ? tripped + " TRIPPED" : "OK";
        circuitEl.className = "metric-value " + (tripped > 0 ? "text-warning" : "text-success");
        circuitEl.style.fontSize = "1.2rem";
    }

    if (uptimeEl) {
        const uptime = data.uptime || data.uptime_seconds || 0;
        if (uptime > 86400) {
            uptimeEl.textContent = Math.floor(uptime / 86400) + "d " + Math.floor((uptime % 86400) / 3600) + "h";
        } else if (uptime > 3600) {
            uptimeEl.textContent = Math.floor(uptime / 3600) + "h " + Math.floor((uptime % 3600) / 60) + "m";
        } else if (uptime > 0) {
            uptimeEl.textContent = Math.floor(uptime / 60) + "m";
        }
    }
}

function updateSentinelaDot(data) {
    const dot = document.getElementById("sentinela-health-dot");
    if (!dot) return;

    const scores = data.scores || data.services || {};
    let worstSeverity = "green";

    for (const [name, info] of Object.entries(scores)) {
        const sev = typeof info === "object" ? (info.severity || "green") : "green";
        if (sev === "critical" || sev === "red") { worstSeverity = "red"; break; }
        if (sev === "yellow" && worstSeverity !== "red") worstSeverity = "yellow";
    }

    dot.className = "snt-status-dot " + worstSeverity;
}

function getSeverity(score) {
    if (score >= 80) return "green";
    if (score >= 50) return "yellow";
    if (score >= 20) return "red";
    return "critical";
}

function severityColor(severity) {
    switch (severity.toLowerCase()) {
        case "green": return "snt-green";
        case "yellow": return "snt-yellow";
        case "red": return "snt-red";
        case "critical": return "snt-critical";
        default: return "snt-green";
    }
}

function severityBarColor(severity) {
    switch (severity.toLowerCase()) {
        case "green": return "bg-success";
        case "yellow": return "bg-warning";
        case "red": return "bg-danger";
        case "critical": return "bg-danger";
        default: return "bg-success";
    }
}

// Ensure escapeHtml exists
if (typeof escapeHtml !== "function") {
    function escapeHtml(str) {
        var div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }
}

// Auto-fetch sentinela data in background (for the dot indicator)
document.addEventListener("DOMContentLoaded", function() {
    // Initial quick check for the dot
    fetch("/monitor/api/sentinela/status")
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(data) { if (data) updateSentinelaDot(data); })
        .catch(function() {
            var dot = document.getElementById("sentinela-health-dot");
            if (dot) dot.className = "snt-status-dot offline";
        });

    // Refresh every 30s
    setInterval(function() {
        fetch("/monitor/api/sentinela/status")
            .then(function(r) { return r.ok ? r.json() : null; })
            .then(function(data) {
                if (data) {
                    updateSentinelaDot(data);
                    // If sentinela tab is active, refresh full data
                    var panel = document.getElementById("sentinela-panel");
                    if (panel && panel.style.display !== "none") {
                        fetchSentinelaData();
                    }
                }
            })
            .catch(function() {});
    }, 30000);
});


// ============================================
// CaseHub Leads CRM (replaces WhatsApp lead monitor)
// ============================================

async function fetchCaseHubLeads() {
    try {
        const response = await fetch("/monitor/api/leads/summary");
        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                updateCaseHubLeads(data);
            }
        }
    } catch (error) {
        console.error("Error fetching CaseHub leads:", error);
    }
}

function updateCaseHubLeads(data) {
    // Update Lead Monitor card -> CRM Status
    const monitorHealth = document.getElementById("lead-monitor-health");
    const monitorStatus = document.getElementById("lead-monitor-status");
    const monitorLastCheck = document.getElementById("lead-monitor-last-check");

    if (monitorHealth) {
        monitorHealth.textContent = "CRM";
        monitorHealth.className = "health-badge bg-info";
    }
    if (monitorStatus) {
        monitorStatus.textContent = data.total + " leads";
    }
    if (monitorLastCheck) {
        if (data.last_updated) {
            var d = new Date(data.last_updated);
            monitorLastCheck.textContent = d.toLocaleDateString("pt-BR") + " " + d.toLocaleTimeString("pt-BR", {hour:"2-digit", minute:"2-digit"});
        }
    }

    // Update leads needing attention
    var countEl = document.getElementById("leads-attention-count");
    var listEl = document.getElementById("leads-attention-list");

    if (countEl) {
        countEl.textContent = data.needs_attention_count || 0;
    }

    if (listEl) {
        var leads = data.needs_attention || [];
        if (leads.length === 0) {
            // Show recent leads instead
            var recent = data.recent || [];
            if (recent.length === 0) {
                listEl.innerHTML = "<div class=\"text-success small\"><i class=\"fas fa-check\"></i> Nenhuma lead recente</div>";
                return;
            }
            var html = "";
            for (var i = 0; i < recent.length; i++) {
                var r = recent[i];
                var name = r.name || "?";
                var source = r.source || "";
                var created = r.created_at ? new Date(r.created_at).toLocaleDateString("pt-BR") : "";
                html += "<div class=\"d-flex justify-content-between align-items-center py-1 border-bottom\">";
                html += "<span class=\"small\">" + escapeHtml(name) + "</span>";
                html += "<small class=\"text-muted\">" + escapeHtml(source) + " " + created + "</small>";
                html += "</div>";
            }
            listEl.innerHTML = html;
        } else {
            var html = "";
            for (var i = 0; i < Math.min(leads.length, 5); i++) {
                var lead = leads[i];
                var name = lead.name || "?";
                var state = lead.conversation_state || "";
                html += "<div class=\"d-flex justify-content-between align-items-center py-1 border-bottom\">";
                html += "<span class=\"small\"><i class=\"fas fa-exclamation-circle text-warning\"></i> " + escapeHtml(name) + "</span>";
                html += "<small class=\"text-muted\">" + escapeHtml(state) + "</small>";
                html += "</div>";
            }
            if (leads.length > 5) {
                html += "<div class=\"text-center mt-2\"><small class=\"text-muted\">+" + (leads.length - 5) + " mais</small></div>";
            }
            listEl.innerHTML = html;
        }
    }
}

// Override the WhatsApp lead monitor functions
document.addEventListener("DOMContentLoaded", function() {
    // Initial fetch
    fetchCaseHubLeads();
    // Refresh every 60s
    setInterval(fetchCaseHubLeads, 60000);
});


// ============================================
// Maestro WhatsApp Admin Integration
// ============================================

var maestroData = null;

var MAESTRO_KNOWN_DATA = {
    admins: [
        { phone: "REDACTED-PHONE", label: "Victor" },
        { phone: "5519998523218", label: "Admin 2" },
        { phone: "+1 (940) ***", label: "Daniel" }
    ],
    protectedFiles: [".env", "*.key", "*.pem", "credentials*.json",
        "package-lock.json", "node_modules/**",
        "maestro-handler-v4.js", "maestro-knowledge.js"],
    allowedCommands: ["pm2 status", "pm2 list", "pm2 logs", "pm2 restart",
        "pm2 reload", "cat", "head", "tail", "grep", "ls",
        "df -h", "free -m", "uptime", "date", "wc", "find",
        "node --version", "npm --version", "mysql --version"]
};

async function fetchMaestroData() {
    try {
        var results = await Promise.all([
            fetch("/monitor/api/maestro-tab/status"),
            fetch("/monitor/api/maestro-tab/audit?limit=30")
        ]);

        var statusRes = results[0];
        var auditRes = results[1];

        if (statusRes.ok) {
            var status = await statusRes.json();
            maestroData = status;
            renderMaestroStatus(status);
            updateMaestroDot(status);

            var updateEl = document.getElementById("mst-last-update");
            if (updateEl) {
                updateEl.textContent = "Atualizado " + new Date().toLocaleTimeString("pt-BR", {hour:"2-digit", minute:"2-digit"});
                updateEl.className = "badge bg-success ms-2";
            }
        }

        if (auditRes.ok) {
            var audit = await auditRes.json();
            renderMaestroAudit(audit);
            renderMaestroSessions(audit);
        }

        renderMaestroQuickInfo();

    } catch (e) {
        console.error("Maestro fetch error:", e);
        var dot = document.getElementById("maestro-health-dot");
        if (dot) dot.className = "snt-status-dot offline";
        var updateEl = document.getElementById("mst-last-update");
        if (updateEl) {
            updateEl.textContent = "Maestro Offline";
            updateEl.className = "badge bg-danger ms-2";
        }
    }
}

function renderMaestroStatus(data) {
    var versionEl = document.getElementById("mst-version");
    var statusEl = document.getElementById("mst-status");
    var aiEl = document.getElementById("mst-ai-enabled");
    var pendingEl = document.getElementById("mst-pending");

    if (versionEl) versionEl.textContent = data.version || "--";
    if (statusEl) {
        statusEl.textContent = (data.maestro || "unknown").toUpperCase();
        statusEl.className = "metric-value";
        statusEl.style.fontSize = "1.2rem";
        statusEl.style.color = data.maestro === "active" ? "var(--accent-green)" : "var(--accent-red)";
    }
    if (aiEl) {
        aiEl.textContent = data.ai_enabled ? "Gemini ON" : "OFF";
        aiEl.style.fontSize = "1.2rem";
        aiEl.style.color = data.ai_enabled ? "var(--accent-green)" : "var(--accent-yellow)";
    }
    if (pendingEl) {
        var count = data.pending_actions || 0;
        pendingEl.textContent = count;
        pendingEl.style.fontSize = "1.2rem";
        pendingEl.style.color = count > 0 ? "var(--accent-yellow)" : "var(--accent-green)";
    }
}

function renderMaestroAudit(data) {
    var list = document.getElementById("mst-audit-list");
    var countEl = document.getElementById("mst-audit-count");
    if (!list) return;

    var entries = data.entries || [];
    if (countEl) countEl.textContent = entries.length;

    if (entries.length === 0) {
        list.innerHTML = '<div class="text-center text-muted py-3"><i class="fas fa-check-circle"></i> Nenhuma atividade recente</div>';
        return;
    }

    var html = "";
    for (var i = 0; i < entries.length; i++) {
        var entry = entries[i];
        var timestamp = entry.timestamp || "--";
        var timeStr = timestamp.indexOf("T") >= 0 ? new Date(timestamp).toLocaleString("pt-BR") : timestamp;
        var type = entry.type || "unknown";
        var phone = entry.phone || "";
        var details = entry.details || entry.input || "";

        var typeColor = getMaestroActionColor(type);

        html += '<div class="mst-audit-row">';
        html += '<span class="mst-audit-time">' + escapeHtml(timeStr) + '</span>';
        html += '<span class="mst-audit-type ' + typeColor + '">' + escapeHtml(type) + '</span>';
        if (phone) {
            html += '<span class="mst-audit-phone">' + escapeHtml(maskPhone(phone)) + '</span>';
        }
        if (details) {
            html += '<span class="mst-audit-detail">' + escapeHtml(String(details).substring(0, 100)) + '</span>';
        }
        html += '</div>';
    }

    list.innerHTML = html;
}

function renderMaestroSessions(auditData) {
    var list = document.getElementById("mst-sessions-list");
    var countEl = document.getElementById("mst-session-count");
    if (!list) return;

    var entries = auditData.entries || [];
    var fiveMinAgo = new Date(Date.now() - 5 * 60 * 1000);
    var activePhones = {};

    for (var i = 0; i < entries.length; i++) {
        var entry = entries[i];
        if (!entry.timestamp || !entry.phone) continue;
        var ts = new Date(entry.timestamp);
        if (ts > fiveMinAgo) {
            if (!activePhones[entry.phone]) {
                activePhones[entry.phone] = { phone: entry.phone, lastAction: entry.timestamp, actions: 0 };
            }
            activePhones[entry.phone].actions++;
        }
    }

    var sessions = Object.values(activePhones);
    if (countEl) countEl.textContent = sessions.length;

    if (sessions.length === 0) {
        list.innerHTML = '<div class="text-center text-muted py-3"><i class="fas fa-check-circle text-success"></i> Nenhuma sessao ativa</div>';
        return;
    }

    var html = "";
    for (var j = 0; j < sessions.length; j++) {
        var s = sessions[j];
        html += '<div class="mst-session-row">';
        html += '<i class="fas fa-user-circle" style="color: var(--accent-purple)"></i> ';
        html += '<span class="mst-session-phone">' + escapeHtml(maskPhone(s.phone)) + '</span>';
        html += '<span class="mst-session-actions">' + s.actions + ' acoes</span>';
        html += '<span class="mst-session-time">Ultimo: ' + new Date(s.lastAction).toLocaleTimeString("pt-BR") + '</span>';
        html += '</div>';
    }

    list.innerHTML = html;
}

function renderMaestroQuickInfo() {
    var adminsList = document.getElementById("mst-admins-list");
    if (adminsList) {
        var html = "";
        for (var i = 0; i < MAESTRO_KNOWN_DATA.admins.length; i++) {
            var admin = MAESTRO_KNOWN_DATA.admins[i];
            html += '<div class="mst-info-item"><i class="fas fa-user-shield" style="color: var(--accent-blue)"></i> ';
            html += escapeHtml(admin.phone) + ' <small style="color: var(--text-secondary)">(' + admin.label + ')</small></div>';
        }
        adminsList.innerHTML = html;
    }

    var protectedList = document.getElementById("mst-protected-list");
    if (protectedList) {
        var html2 = "";
        for (var j = 0; j < MAESTRO_KNOWN_DATA.protectedFiles.length; j++) {
            var file = MAESTRO_KNOWN_DATA.protectedFiles[j];
            html2 += '<div class="mst-info-item"><i class="fas fa-lock" style="color: var(--accent-yellow)"></i> <code>' + escapeHtml(file) + '</code></div>';
        }
        protectedList.innerHTML = html2;
    }

    var commandsList = document.getElementById("mst-commands-list");
    if (commandsList) {
        var html3 = "";
        for (var k = 0; k < MAESTRO_KNOWN_DATA.allowedCommands.length; k++) {
            var cmd = MAESTRO_KNOWN_DATA.allowedCommands[k];
            html3 += '<div class="mst-info-item"><code style="color: var(--accent-green)">' + escapeHtml(cmd) + '</code></div>';
        }
        commandsList.innerHTML = html3;
    }
}

function updateMaestroDot(data) {
    var dot = document.getElementById("maestro-health-dot");
    if (!dot) return;

    if (data.error) {
        dot.className = "snt-status-dot offline";
    } else if (data.maestro === "active") {
        dot.className = "snt-status-dot mst-purple";
    } else {
        dot.className = "snt-status-dot yellow";
    }
}

function getMaestroActionColor(type) {
    switch ((type || "").toUpperCase()) {
        case "COMMAND": case "COMMAND_EXEC": return "mst-type-command";
        case "PLAN": return "mst-type-plan";
        case "MODIFICATION": return "mst-type-modification";
        case "RESTART": return "mst-type-restart";
        case "SESSION_START": case "SESSION_END": return "mst-type-info";
        case "REVERT": return "mst-type-modification";
        default: return "mst-type-default";
    }
}

function maskPhone(phone) {
    if (!phone || phone.length < 8) return phone || "";
    return phone.substring(0, 4) + "****" + phone.substring(phone.length - 4);
}

// Maestro health dot on page load + auto-refresh
(function() {
    fetch("/monitor/api/maestro-tab/status")
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(data) { if (data) updateMaestroDot(data); })
        .catch(function() {
            var dot = document.getElementById("maestro-health-dot");
            if (dot) dot.className = "snt-status-dot offline";
        });

    setInterval(function() {
        fetch("/monitor/api/maestro-tab/status")
            .then(function(r) { return r.ok ? r.json() : null; })
            .then(function(data) {
                if (data) {
                    updateMaestroDot(data);
                    var panel = document.getElementById("maestro-panel");
                    if (panel && panel.style.display !== "none") {
                        fetchMaestroData();
                    }
                }
            })
            .catch(function() {});
    }, 30000);
})();
