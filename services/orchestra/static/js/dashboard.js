// Orchestra Dashboard - Versão Funcional
// Todas as chamadas usam /orchestra/ para o proxy do Nginx

const API_BASE = '/orchestra';

// =====================================
// INICIALIZAÇÃO
// =====================================

document.addEventListener('DOMContentLoaded', () => {
    loadAgents();
    loadActivity();
    
    // Atualizar a cada 5 segundos
    setInterval(loadAgents, 5000);
    setInterval(loadActivity, 5000);
    
    // Configurar envio de comando
    document.getElementById('send-command').addEventListener('click', sendCommand);
    
    // Enter para enviar
    document.getElementById('command-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && e.ctrlKey) {
            sendCommand();
        }
    });
});

// =====================================
// CARREGAR AGENTES
// =====================================

async function loadAgents() {
    try {
        const response = await fetch(`${API_BASE}/agents`);
        if (!response.ok) throw new Error('Falha ao carregar agentes');
        
        const agents = await response.json();
        
        // Atualizar status de cada agente
        for (const [id, agent] of Object.entries(agents)) {
            const statusEl = document.getElementById(`${id}-status`);
            if (statusEl) {
                const status = agent.status || 'unknown';
                statusEl.textContent = status.toUpperCase();
                statusEl.className = `status-badge ${status}`;
            }
        }
    } catch (error) {
        console.error('Erro ao carregar agentes:', error);
    }
}

// =====================================
// CARREGAR ATIVIDADE
// =====================================

async function loadActivity() {
    try {
        const response = await fetch(`${API_BASE}/state`);
        if (!response.ok) throw new Error('Falha ao carregar estado');
        
        const state = await response.json();
        const activityLog = document.getElementById('activity-log');
        
        // Pegar activity_log do state
        const activities = state.activity_log || [];
        
        if (activities.length === 0) {
            activityLog.innerHTML = '<div class="loading">Nenhuma atividade registrada ainda.</div>';
            return;
        }
        
        // Renderizar atividades
        activityLog.innerHTML = activities.slice(0, 20).map(a => {
            const time = a.timestamp ? a.timestamp.split('T')[1]?.substring(0, 8) : '--:--:--';
            const agent = a.agent || 'system';
            const details = a.details || a.type || 'Ação';
            
            return `
                <div class="activity-item">
                    <span class="activity-time">${time}</span>
                    <span class="activity-agent ${agent.toLowerCase()}">${agent.toUpperCase()}</span>
                    <span class="activity-msg">${details}</span>
                </div>
            `;
        }).join('');
        
    } catch (error) {
        console.error('Erro ao carregar atividade:', error);
        document.getElementById('activity-log').innerHTML = 
            '<div class="loading">Erro ao conectar com o servidor.</div>';
    }
}

// =====================================
// ENVIAR COMANDO
// =====================================

async function sendCommand() {
    const input = document.getElementById('command-input');
    const select = document.getElementById('agent-select');
    const button = document.getElementById('send-command');
    
    const query = input.value.trim();
    const targetAgent = select.value;
    
    if (!query) {
        alert('Digite um comando primeiro.');
        return;
    }
    
    // Desabilitar enquanto envia
    button.disabled = true;
    button.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Enviando...';
    
    try {
        const response = await fetch(`${API_BASE}/task`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                from_agent: 'user',
                to_agent: targetAgent,
                task_type: 'research',
                payload: { query: query },
                priority: 'high'
            })
        });
        
        if (!response.ok) throw new Error('Falha ao enviar comando');
        
        const result = await response.json();
        
        // Limpar input
        input.value = '';
        
        // Mostrar confirmação
        alert(`Comando enviado para ${targetAgent.toUpperCase()}!\nTask ID: ${result.task_id}`);
        
        // Recarregar atividade
        loadActivity();
        
        // Aguardar resultado (polling simples)
        setTimeout(() => checkTaskResult(result.task_id), 3000);
        
    } catch (error) {
        console.error('Erro ao enviar comando:', error);
        alert('Erro ao enviar comando. Verifique a conexão.');
    } finally {
        button.disabled = false;
        button.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Enviar';
    }
}

// =====================================
// VERIFICAR RESULTADO
// =====================================

async function checkTaskResult(taskId) {
    try {
        const response = await fetch(`${API_BASE}/task/${taskId}`);
        if (!response.ok) return;
        
        const task = await response.json();
        
        if (task.status === 'completed' && task.result?.output) {
            const resultSection = document.getElementById('result-section');
            const resultContent = document.getElementById('result-content');
            
            resultContent.textContent = task.result.output;
            resultSection.style.display = 'block';
            
            // Scroll para resultado
            resultSection.scrollIntoView({ behavior: 'smooth' });
        } else if (task.status === 'pending') {
            // Tentar novamente em 2 segundos
            setTimeout(() => checkTaskResult(taskId), 2000);
        }
    } catch (error) {
        console.error('Erro ao verificar resultado:', error);
    }
}

// =====================================
// ALTERNAR STATUS DO AGENTE
// =====================================

window.toggleAgent = async function(agentId) {
    const statusEl = document.getElementById(`${agentId}-status`);
    const currentStatus = statusEl.textContent.toLowerCase();
    const newStatus = currentStatus === 'active' ? 'standby' : 'active';
    
    try {
        const response = await fetch(`${API_BASE}/config/agent/${agentId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus })
        });
        
        if (response.ok) {
            statusEl.textContent = newStatus.toUpperCase();
            statusEl.className = `status-badge ${newStatus}`;
        }
    } catch (error) {
        console.error('Erro ao alterar status:', error);
    }
}

// =====================================
// ALTERNAR RELACIONAMENTO
// =====================================

window.toggleRelationship = async function(from, to, enabled) {
    try {
        await fetch(`${API_BASE}/config/relationship`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                from_agent: from,
                to_agent: to,
                allowed: enabled,
                communication_type: 'all'
            })
        });
        
        // Recarregar atividade para mostrar a mudança
        loadActivity();
        
    } catch (error) {
        console.error('Erro ao alterar relacionamento:', error);
    }
}
