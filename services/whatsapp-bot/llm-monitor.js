/**
 * LLM Chatbot Monitor - Activity Logging & Dashboard
 * CaseHub - WhatsApp Bot
 * v1.0 - 30/01/2026
 */

const fs = require('fs');
const path = require('path');

// Log file path
const LOG_FILE = path.join(__dirname, 'logs', 'llm-activity.json');
const MAX_ENTRIES = 500;

// In-memory cache for recent activity
let activityCache = [];

// Ensure logs directory exists
function ensureLogDir() {
    const logDir = path.join(__dirname, 'logs');
    if (!fs.existsSync(logDir)) {
        fs.mkdirSync(logDir, { recursive: true });
    }
}

// Load existing logs on startup
function loadLogs() {
    try {
        ensureLogDir();
        if (fs.existsSync(LOG_FILE)) {
            const data = fs.readFileSync(LOG_FILE, 'utf8');
            activityCache = JSON.parse(data);
            console.log('[LLM-MONITOR] Loaded ' + activityCache.length + ' log entries');
        }
    } catch (e) {
        console.log('[LLM-MONITOR] Error loading logs:', e.message);
        activityCache = [];
    }
}

// Save logs to file
function saveLogs() {
    try {
        ensureLogDir();
        // Keep only last MAX_ENTRIES
        if (activityCache.length > MAX_ENTRIES) {
            activityCache = activityCache.slice(-MAX_ENTRIES);
        }
        fs.writeFileSync(LOG_FILE, JSON.stringify(activityCache, null, 2));
    } catch (e) {
        console.log('[LLM-MONITOR] Error saving logs:', e.message);
    }
}

/**
 * Log LLM activity
 */
function logActivity(data) {
    const entry = {
        id: Date.now() + '-' + Math.random().toString(36).substr(2, 9),
        timestamp: new Date().toISOString(),
        phone: data.phone || 'unknown',
        clientName: data.clientName || 'Unknown',
        messageIn: data.messageIn || '',
        messageOut: data.messageOut || '',
        intent: data.intent || 'unknown',
        template: data.template || 'none',
        language: data.language || 'pt',
        needsHuman: data.needsHuman || false,
        success: data.success !== false,
        error: data.error || null
    };

    activityCache.push(entry);
    
    // Save periodically (every 5 entries)
    if (activityCache.length % 5 === 0) {
        saveLogs();
    }

    console.log('[LLM-MONITOR] Logged: ' + entry.phone + ' | ' + entry.intent + ' | Human: ' + entry.needsHuman);
    
    return entry;
}

/**
 * Get recent activity
 */
function getActivity(options = {}) {
    const { limit = 50, phone = null, needsHuman = null } = options;
    
    let results = [...activityCache].reverse();
    
    // Filter by phone
    if (phone) {
        results = results.filter(e => e.phone.includes(phone));
    }
    
    // Filter by needsHuman
    if (needsHuman !== null) {
        results = results.filter(e => e.needsHuman === needsHuman);
    }
    
    return results.slice(0, limit);
}

/**
 * Get statistics
 */
function getStats() {
    const now = new Date();
    const last24h = new Date(now - 24 * 60 * 60 * 1000);
    const lastHour = new Date(now - 60 * 60 * 1000);
    
    const recent24h = activityCache.filter(e => new Date(e.timestamp) > last24h);
    const recentHour = activityCache.filter(e => new Date(e.timestamp) > lastHour);
    
    // Count intents
    const intentCounts = {};
    recent24h.forEach(e => {
        intentCounts[e.intent] = (intentCounts[e.intent] || 0) + 1;
    });
    
    return {
        total: activityCache.length,
        last24h: recent24h.length,
        lastHour: recentHour.length,
        needsHumanCount: recent24h.filter(e => e.needsHuman).length,
        successRate: recent24h.length > 0 
            ? Math.round((recent24h.filter(e => e.success).length / recent24h.length) * 100) 
            : 0,
        topIntents: Object.entries(intentCounts)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 5)
            .map(([intent, count]) => ({ intent, count }))
    };
}

/**
 * Setup API routes
 */
function setupRoutes(app) {
    // Get activity log
    app.get('/api/llm-monitor/activity', (req, res) => {
        const { limit, phone, needsHuman } = req.query;
        const activity = getActivity({
            limit: parseInt(limit) || 50,
            phone: phone || null,
            needsHuman: needsHuman === 'true' ? true : (needsHuman === 'false' ? false : null)
        });
        res.json({ success: true, data: activity });
    });
    
    // Get stats
    app.get('/api/llm-monitor/stats', (req, res) => {
        res.json({ success: true, data: getStats() });
    });
    
    // Dashboard HTML
    app.get('/llm-monitor', (req, res) => {
        res.send(getDashboardHTML());
    });
    
    console.log('[LLM-MONITOR] API routes configured:');
    console.log('  GET  /api/llm-monitor/activity');
    console.log('  GET  /api/llm-monitor/stats');
    console.log('  GET  /llm-monitor (dashboard)');
}

/**
 * Dashboard HTML
 */
function getDashboardHTML() {
    return `<!DOCTYPE html>
<html>
<head>
    <title>LLM Chatbot Monitor</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a0a; 
            color: #e0e0e0;
            padding: 20px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid #333;
        }
        h1 { color: #00a884; font-size: 24px; }
        .refresh-btn {
            background: #00a884;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
        }
        .refresh-btn:hover { background: #00c896; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }
        .stat-card {
            background: #1a1a1a;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            border: 1px solid #333;
        }
        .stat-value {
            font-size: 28px;
            font-weight: bold;
            color: #00a884;
        }
        .stat-label {
            font-size: 12px;
            color: #888;
            margin-top: 5px;
        }
        .activity-list {
            background: #1a1a1a;
            border-radius: 8px;
            border: 1px solid #333;
            overflow: hidden;
        }
        .activity-header {
            display: grid;
            grid-template-columns: 140px 120px 100px 80px 1fr;
            padding: 12px 15px;
            background: #252525;
            font-weight: 600;
            font-size: 13px;
            color: #888;
            border-bottom: 1px solid #333;
        }
        .activity-item {
            display: grid;
            grid-template-columns: 140px 120px 100px 80px 1fr;
            padding: 12px 15px;
            border-bottom: 1px solid #222;
            font-size: 13px;
            transition: background 0.2s;
        }
        .activity-item:hover { background: #222; }
        .activity-item.needs-human { 
            border-left: 3px solid #f15c6d;
            background: rgba(241, 92, 109, 0.05);
        }
        .activity-item .time { color: #666; font-family: monospace; }
        .activity-item .phone { color: #888; }
        .activity-item .intent { 
            color: #00a884; 
            font-weight: 500;
        }
        .activity-item .human-badge {
            background: #f15c6d;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
        }
        .activity-item .auto-badge {
            background: #00a884;
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
        }
        .activity-item .message {
            color: #aaa;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .filter-bar {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }
        .filter-bar select, .filter-bar input {
            background: #1a1a1a;
            border: 1px solid #333;
            color: #e0e0e0;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 13px;
        }
        .empty-state {
            text-align: center;
            padding: 40px;
            color: #666;
        }
        .live-indicator {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            color: #00a884;
        }
        .live-dot {
            width: 8px;
            height: 8px;
            background: #00a884;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>🤖 LLM Chatbot Monitor</h1>
            <span class="live-indicator"><span class="live-dot"></span> Live - Auto-refresh 10s</span>
        </div>
        <button class="refresh-btn" onclick="loadData()">↻ Refresh</button>
    </div>

    <div class="stats-grid" id="stats">
        <div class="stat-card"><div class="stat-value">-</div><div class="stat-label">Ultima Hora</div></div>
        <div class="stat-card"><div class="stat-value">-</div><div class="stat-label">24 Horas</div></div>
        <div class="stat-card"><div class="stat-value">-</div><div class="stat-label">Precisa Humano</div></div>
        <div class="stat-card"><div class="stat-value">-%</div><div class="stat-label">Taxa Sucesso</div></div>
    </div>

    <div class="filter-bar">
        <select id="filterHuman" onchange="loadData()">
            <option value="">Todos</option>
            <option value="true">Precisa Humano</option>
            <option value="false">Auto-respondido</option>
        </select>
        <input type="text" id="filterPhone" placeholder="Filtrar por telefone..." onkeyup="debounceLoad()">
    </div>

    <div class="activity-list">
        <div class="activity-header">
            <div>Horario</div>
            <div>Cliente</div>
            <div>Intent</div>
            <div>Status</div>
            <div>Mensagem</div>
        </div>
        <div id="activity-body"></div>
    </div>

    <script>
        let debounceTimer;
        function debounceLoad() {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(loadData, 300);
        }

        async function loadData() {
            try {
                // Load stats
                const statsRes = await fetch('/api/llm-monitor/stats');
                const statsData = await statsRes.json();
                if (statsData.success) {
                    const s = statsData.data;
                    document.getElementById('stats').innerHTML = \`
                        <div class="stat-card"><div class="stat-value">\${s.lastHour}</div><div class="stat-label">Ultima Hora</div></div>
                        <div class="stat-card"><div class="stat-value">\${s.last24h}</div><div class="stat-label">24 Horas</div></div>
                        <div class="stat-card"><div class="stat-value">\${s.needsHumanCount}</div><div class="stat-label">Precisa Humano</div></div>
                        <div class="stat-card"><div class="stat-value">\${s.successRate}%</div><div class="stat-label">Taxa Sucesso</div></div>
                    \`;
                }

                // Load activity
                const filterHuman = document.getElementById('filterHuman').value;
                const filterPhone = document.getElementById('filterPhone').value;
                let url = '/api/llm-monitor/activity?limit=100';
                if (filterHuman) url += '&needsHuman=' + filterHuman;
                if (filterPhone) url += '&phone=' + encodeURIComponent(filterPhone);

                const actRes = await fetch(url);
                const actData = await actRes.json();
                
                const body = document.getElementById('activity-body');
                if (actData.success && actData.data.length > 0) {
                    body.innerHTML = actData.data.map(item => {
                        const time = new Date(item.timestamp).toLocaleString('pt-BR', {
                            day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
                        });
                        const badge = item.needsHuman 
                            ? '<span class="human-badge">HUMANO</span>'
                            : '<span class="auto-badge">AUTO</span>';
                        return \`
                            <div class="activity-item \${item.needsHuman ? 'needs-human' : ''}">
                                <div class="time">\${time}</div>
                                <div class="phone">\${item.clientName || item.phone}</div>
                                <div class="intent">\${item.intent}</div>
                                <div>\${badge}</div>
                                <div class="message" title="\${item.messageIn}">\${item.messageIn}</div>
                            </div>
                        \`;
                    }).join('');
                } else {
                    body.innerHTML = '<div class="empty-state">Nenhuma atividade registrada ainda</div>';
                }
            } catch (e) {
                console.error('Error loading data:', e);
            }
        }

        // Initial load
        loadData();
        
        // Auto-refresh every 10 seconds
        setInterval(loadData, 10000);
    </script>
</body>
</html>`;
}

// Initialize
loadLogs();

module.exports = {
    logActivity,
    getActivity,
    getStats,
    setupRoutes
};
