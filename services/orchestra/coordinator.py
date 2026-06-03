"""
Orchestra Coordinator - Multi-AI Task Distribution Service
Handles communication between Claude, Gemini, Perplexity, and other AI agents
Includes Maestro Dashboard for visual control
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import os
import redis
import uuid
import yaml
import httpx
import asyncio

# Configuration
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

app = FastAPI(title="Orchestra Coordinator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and templates
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Redis connection
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# File paths
STATE_FILE = os.getenv("APP_BASE_PATH", "/opt/casehub") + "/orchestra/.orchestra/state.json"
CONFIG_FILE = os.getenv("APP_BASE_PATH", "/opt/casehub") + "/orchestra/.orchestra/config.yaml"
SNAPSHOTS_DIR = os.getenv("APP_BASE_PATH", "/opt/casehub") + "/orchestra/.orchestra/snapshots"
CONTEXT_FILE = os.getenv("APP_BASE_PATH", "/opt/casehub") + "/casehub/ORCHESTRA_STATUS.md"
ACTIVITY_FILE = os.getenv("APP_BASE_PATH", "/opt/casehub") + "/orchestra/.orchestra/activity.json"

# Models
class Task(BaseModel):
    from_agent: str
    to_agent: str
    task_type: str
    payload: Dict[str, Any]
    priority: str = "normal"  # low, normal, high, critical
    context: Optional[Dict[str, Any]] = None

class TaskResponse(BaseModel):
    task_id: str
    result: str  # success, failed, pending
    output: Optional[Dict[str, Any]] = None
    files_created: Optional[List[str]] = None
    error: Optional[str] = None

class Interruption(BaseModel):
    triggered_by: str
    target_agent: str
    justification: str
    severity: str  # low, medium, high, critical
    evidence: List[str]

class Vote(BaseModel):
    task_id: str
    voter: str
    vote: str  # FOR, AGAINST, ABSTAIN
    reason: Optional[str] = None

class RelationshipUpdate(BaseModel):
    from_agent: str
    to_agent: str
    allowed: bool
    communication_type: str = "all"  # all, api_contracts_only, none

class AgentConfigUpdate(BaseModel):
    status: Optional[str] = None
    capabilities: Optional[List[str]] = None
    constraints: Optional[List[str]] = None
    has_veto_power: Optional[bool] = None
    can_interrupt: Optional[List[str]] = None

# Helper functions
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {
        "project": "CaseHub",
        "current_phase": "Phase1-Orchestra",
        "agents": {},
        "tasks": [],
        "interruptions": [],
        "votes": [],
        "activity_log": [], # Initialize activity_log
        "last_updated": datetime.now().isoformat()
    }

def save_state(state):
    state["last_updated"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return yaml.safe_load(f)
    return {
        "version": "1.0",
        "project": "CaseHub",
        "ai_agents": {},
        "governance_rules": {},
        "relationships": {}
    }

def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

def log_activity(action: str, agent: str = None, details: str = None):
    # Append to recent activity
    activity_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": action,
        "agent": agent,
        "details": details
    }
    
    # Keep only last 50 entries
    state = load_state()
    if "activity_log" not in state:
        state["activity_log"] = []
    
    state["activity_log"].insert(0, activity_entry)
    state["activity_log"] = state["activity_log"][:50]
    save_state(state)
    
    # Sync to Shared Context File for Claude
    sync_to_context_file(state)

def sync_to_context_file(state):
    """Updates the ORCHESTRA_STATUS.md file for other agents to read"""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(CONTEXT_FILE), exist_ok=True)
        
        with open(CONTEXT_FILE, 'w') as f:
            f.write(f"# 🎻 Orchestra Status Report\n")
            f.write(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            f.write(f"## 🤖 Agent Status\n")
            f.write("| Agent | Status | Role |\n")
            f.write("|-------|--------|------|\n")
            for agent_id, data in state.get("agents", {}).items():
                status = data.get("status", "unknown").upper()
                role = data.get("role", "unknown")
                f.write(f"| {agent_id.capitalize()} | {status} | {role} |\n")
            
            f.write(f"\n## 📋 Pending Tasks\n")
            pending_tasks = [t for t in state.get("tasks", []) if t["status"] == "pending"]
            if pending_tasks:
                for t in pending_tasks:
                    f.write(f"- [{t['priority'].upper()}] **{t['task_type']}** (to {t['to_agent']}) - {t['id']}\n")
            else:
                f.write("No pending tasks.\n")
                
            f.write(f"\n## 📜 Recent Activity\n")
            for entry in state.get("activity_log", [])[:10]:
                timestamp = entry.get("timestamp", "").split("T")[1][:8]
                f.write(f"- `{timestamp}` **{entry['agent'].upper()}**: {entry['details']} ({entry['type']})\n")
                
    except Exception as e:
        print(f"Failed to sync context file: {e}")

def create_snapshot(name: str, files: List[str] = None):
    snapshot_id = f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{name}"
    snapshot_dir = f"{SNAPSHOTS_DIR}/critical/{snapshot_id}"
    os.makedirs(snapshot_dir, exist_ok=True)

    # Save current state
    state = load_state()
    with open(f"{snapshot_dir}/state.json", 'w') as f:
        json.dump(state, f, indent=2)

    return snapshot_id

# ============================================
# DASHBOARD ENDPOINTS
# ============================================

@app.get("/", response_class=HTMLResponse)
async def root_redirect(request: Request):
    """Redirect root to dashboard"""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "state": load_state(),
        "config": load_config()
    })

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve the Maestro Dashboard"""
    state = load_state()
    config = load_config()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "state": state,
        "config": config
    })

@app.get("/health")
async def health():
    try:
        redis_client.ping()
        redis_status = "connected"
    except:
        redis_status = "disconnected"

    return {
        "status": "healthy",
        "redis": redis_status,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/state")
async def get_state():
    return load_state()

@app.get("/config")
async def get_config():
    """Get current configuration"""
    return load_config()

@app.get("/activity")
async def get_activity(limit: int = 50):
    """Get recent activity log"""
    activity_data = load_activity()
    return {"activities": activity_data["activities"][:limit]}

# ============================================
# CONFIGURATION ENDPOINTS
# ============================================

@app.post("/config/relationship")
async def update_relationship(update: RelationshipUpdate):
    """Update relationship between two agents"""
    config = load_config()

    if "relationships" not in config:
        config["relationships"] = {}

    key = f"{update.from_agent}_to_{update.to_agent}"
    config["relationships"][key] = {
        "allowed": update.allowed,
        "type": update.communication_type,
        "updated_at": datetime.now().isoformat()
    }

    save_config(config)
    log_activity(
        "relationship_updated",
        update.from_agent,
        f"{update.from_agent} -> {update.to_agent}: {update.communication_type if update.allowed else 'blocked'}"
    )

    return {"status": "updated", "relationship": key}

@app.post("/config/agent/{agent_id}")
async def update_agent_config(agent_id: str, update: AgentConfigUpdate):
    """Update configuration for a specific agent"""
    config = load_config()
    state = load_state()

    if "ai_agents" not in config:
        config["ai_agents"] = {}

    if agent_id not in config["ai_agents"]:
        config["ai_agents"][agent_id] = {}

    # Update config fields
    if update.capabilities is not None:
        config["ai_agents"][agent_id]["capabilities"] = update.capabilities
    if update.constraints is not None:
        config["ai_agents"][agent_id]["constraints"] = update.constraints
    if update.has_veto_power is not None:
        config["ai_agents"][agent_id]["has_veto_power"] = update.has_veto_power
    if update.can_interrupt is not None:
        config["ai_agents"][agent_id]["can_interrupt"] = update.can_interrupt

    # Update state status
    if update.status is not None:
        if agent_id not in state["agents"]:
            state["agents"][agent_id] = {"id": agent_id}
        state["agents"][agent_id]["status"] = update.status
        save_state(state)

    save_config(config)
    log_activity("agent_config_updated", agent_id, f"Agent {agent_id} configuration updated")

    return {"status": "updated", "agent_id": agent_id}

@app.post("/config/agent/{agent_id}/status")
async def update_agent_status(agent_id: str, status: str):
    """Quick update for agent status"""
    state = load_state()

    if agent_id not in state["agents"]:
        state["agents"][agent_id] = {"id": agent_id}

    state["agents"][agent_id]["status"] = status
    save_state(state)
    log_activity("status_changed", agent_id, f"Status changed to {status}")

    return {"status": "updated", "agent_id": agent_id, "new_status": status}

# ============================================
# TASK MANAGEMENT ENDPOINTS
# ============================================

@app.post("/task")
async def create_task(task: Task, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())[:8]

    task_data = {
        "id": task_id,
        "from_agent": task.from_agent,
        "to_agent": task.to_agent,
        "task_type": task.task_type,
        "payload": task.payload,
        "priority": task.priority,
        "context": task.context,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }

    # Store in Redis queue
    redis_client.lpush(f"tasks:{task.to_agent}", json.dumps(task_data))
    redis_client.set(f"task:{task_id}", json.dumps(task_data))

    # Trigger immediate execution if agent is Perplexity
    if task.to_agent == "perplexity" and task.task_type == "research":
        query = task.payload.get("query") or task.payload.get("instruction")
        if query:
            background_tasks.add_task(execute_perplexity_search, task_id, query)

    # Update state file
    state = load_state()
    state["tasks"].append(task_data)
    save_state(state)

    # Log activity
    log_activity(
        "task_created",
        task.from_agent,
        f"Task for {task.to_agent}: {task.task_type}"
    )

    return {"task_id": task_id, "status": "queued", "to_agent": task.to_agent}

def build_shared_context() -> str:
    """Build shared context from recent activity of all agents"""
    state = load_state()
    activity_log = state.get("activity_log", [])[:10]
    agents = state.get("agents", {})
    
    # Build agent status summary
    agent_status = []
    for agent_id, data in agents.items():
        status = data.get("status", "unknown")
        agent_status.append(f"- {agent_id.upper()}: {status.upper()}")
    
    # Build recent actions
    recent_actions = []
    for entry in activity_log[:5]:
        timestamp = entry.get("timestamp", "").split("T")[1][:8] if "T" in entry.get("timestamp", "") else "--:--:--"
        agent = entry.get("agent", "system").upper()
        details = entry.get("details", "")
        recent_actions.append(f"- [{timestamp}] {agent}: {details}")
    
    context = f"""
## 🎻 CONTEXTO ORCHESTRA (Multi-IA System)
Você faz parte de um sistema orquestrado com múltiplas IAs trabalhando juntas.

### Status dos Agentes Agora:
{chr(10).join(agent_status) if agent_status else "- Nenhum agente registrado"}

### Últimas Ações (Tempo Real):
{chr(10).join(recent_actions) if recent_actions else "- Nenhuma ação recente"}

### Seu Papel:
Você é Perplexity, especialista em pesquisa. Claude é o desenvolvedor backend. Gemini é o desenvolvedor frontend.
Você pode mencionar o que as outras IAs fizeram se for relevante para a pergunta do usuário.

---
## Tarefa do Usuário:
"""
    return context

async def execute_perplexity_search(task_id: str, query: str):
    """Execute a Perplexity search task with shared context"""
    log_activity("agent_execution_start", "perplexity", f"Starting search for task {task_id}")
    
    # Build shared context from other agents
    shared_context = build_shared_context()
    full_query = shared_context + query
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                PERPLEXITY_API_URL,
                headers={
                    "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "sonar",
                    "messages": [
                        {"role": "system", "content": "Você é Perplexity, parte do sistema Orchestra. Você tem conhecimento das ações das outras IAs (Claude, Gemini) através do contexto fornecido. Responda em português quando apropriado."},
                        {"role": "user", "content": full_query}
                    ]
                }
            )
            
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # Update task with result
            task_json = redis_client.get(f"task:{task_id}")
            if task_json:
                task_data = json.loads(task_json)
                task_data["status"] = "completed"
                task_data["result"] = {"output": content}
                task_data["completed_at"] = datetime.now().isoformat()
                redis_client.set(f"task:{task_id}", json.dumps(task_data))
                
                # Update State
                state = load_state()
                for i, t in enumerate(state["tasks"]):
                    if t["id"] == task_id:
                        state["tasks"][i] = task_data
                        break
                save_state(state)
                
            log_activity("task_completed", "perplexity", f"Search completed for task {task_id}")
            
    except Exception as e:
        log_activity("agent_execution_error", "perplexity", f"Error executing task {task_id}: {str(e)}")

@app.get("/tasks/pending")
async def get_pending_tasks(agent: str):
    tasks = []
    while True:
        task_json = redis_client.rpop(f"tasks:{agent}")
        if not task_json:
            break
        tasks.append(json.loads(task_json))
    return {"agent": agent, "tasks": tasks, "count": len(tasks)}

@app.get("/task/{task_id}")
async def get_task(task_id: str):
    task_json = redis_client.get(f"task:{task_id}")
    if not task_json:
        raise HTTPException(status_code=404, detail="Task not found")
    return json.loads(task_json)

@app.post("/task/{task_id}/complete")
async def complete_task(task_id: str, response: TaskResponse):
    task_json = redis_client.get(f"task:{task_id}")
    if not task_json:
        raise HTTPException(status_code=404, detail="Task not found")

    task_data = json.loads(task_json)
    task_data["status"] = "completed" if response.result == "success" else "failed"
    task_data["result"] = response.dict()
    task_data["completed_at"] = datetime.now().isoformat()

    redis_client.set(f"task:{task_id}", json.dumps(task_data))

    # Update state
    state = load_state()
    for i, t in enumerate(state["tasks"]):
        if t["id"] == task_id:
            state["tasks"][i] = task_data
            break
    save_state(state)

    # Log activity
    log_activity(
        f"task_{task_data['status']}",
        task_data.get("to_agent"),
        f"Task {task_id}: {task_data['task_type']}"
    )

    return {"task_id": task_id, "status": task_data["status"]}

# ============================================
# INTERRUPTION & VOTING ENDPOINTS
# ============================================

@app.post("/interrupt")
async def create_interruption(interruption: Interruption):
    interrupt_id = str(uuid.uuid4())[:8]

    # Create snapshot before interruption
    snapshot_id = create_snapshot(f"interrupt_{interrupt_id}")

    interrupt_data = {
        "id": interrupt_id,
        "triggered_by": interruption.triggered_by,
        "target_agent": interruption.target_agent,
        "justification": interruption.justification,
        "severity": interruption.severity,
        "evidence": interruption.evidence,
        "snapshot_id": snapshot_id,
        "status": "pending_investigation",
        "created_at": datetime.now().isoformat(),
        "votes": []
    }

    # Store
    redis_client.set(f"interrupt:{interrupt_id}", json.dumps(interrupt_data))

    state = load_state()
    state["interruptions"].append(interrupt_data)
    save_state(state)

    log_activity(
        "interruption_created",
        interruption.triggered_by,
        f"Interruption on {interruption.target_agent}: {interruption.severity}"
    )

    return {"interrupt_id": interrupt_id, "snapshot_id": snapshot_id, "status": "pending_investigation"}

@app.post("/vote")
async def cast_vote(vote: Vote):
    # Get the interruption or task being voted on
    interrupt_json = redis_client.get(f"interrupt:{vote.task_id}")
    if not interrupt_json:
        raise HTTPException(status_code=404, detail="Interruption not found")

    interrupt_data = json.loads(interrupt_json)

    vote_data = {
        "voter": vote.voter,
        "vote": vote.vote,
        "reason": vote.reason,
        "timestamp": datetime.now().isoformat()
    }

    interrupt_data["votes"].append(vote_data)

    # Check if we have enough votes (majority)
    votes_for = sum(1 for v in interrupt_data["votes"] if v["vote"] == "FOR")
    votes_against = sum(1 for v in interrupt_data["votes"] if v["vote"] == "AGAINST")

    if len(interrupt_data["votes"]) >= 2:  # Minimum 2 votes
        if votes_for > votes_against:
            interrupt_data["status"] = "approved"
            interrupt_data["resolution"] = "Action approved by majority"
        elif votes_against > votes_for:
            interrupt_data["status"] = "rejected"
            interrupt_data["resolution"] = "Action rejected by majority"

    redis_client.set(f"interrupt:{vote.task_id}", json.dumps(interrupt_data))

    # Update state
    state = load_state()
    for i, inter in enumerate(state["interruptions"]):
        if inter["id"] == vote.task_id:
            state["interruptions"][i] = interrupt_data
            break
    save_state(state)

    log_activity(
        "vote_cast",
        vote.voter,
        f"Vote {vote.vote} on {vote.task_id}"
    )

    return {
        "interrupt_id": vote.task_id,
        "votes_for": votes_for,
        "votes_against": votes_against,
        "status": interrupt_data["status"]
    }

# ============================================
# AGENT MANAGEMENT ENDPOINTS
# ============================================

@app.get("/agents")
async def list_agents():
    state = load_state()
    config = load_config()

    # Merge state and config data
    agents = {}
    for agent_id, agent_state in state.get("agents", {}).items():
        agents[agent_id] = {**agent_state}
        if agent_id in config.get("ai_agents", {}):
            agents[agent_id].update(config["ai_agents"][agent_id])

    # Add agents from config that aren't in state
    for agent_id, agent_config in config.get("ai_agents", {}).items():
        if agent_id not in agents:
            agents[agent_id] = {**agent_config, "id": agent_id, "status": "unknown"}

    return agents

@app.post("/agents/{agent_id}/register")
async def register_agent(agent_id: str, capabilities: Dict[str, Any]):
    state = load_state()
    state["agents"][agent_id] = {
        "id": agent_id,
        "capabilities": capabilities,
        "registered_at": datetime.now().isoformat(),
        "last_seen": datetime.now().isoformat(),
        "status": "active"
    }
    save_state(state)
    log_activity("agent_registered", agent_id, f"Agent {agent_id} registered")
    return {"agent_id": agent_id, "status": "registered"}

@app.post("/agents/{agent_id}/heartbeat")
async def agent_heartbeat(agent_id: str):
    state = load_state()
    if agent_id in state.get("agents", {}):
        state["agents"][agent_id]["last_seen"] = datetime.now().isoformat()
        save_state(state)
        return {"agent_id": agent_id, "status": "alive"}
    raise HTTPException(status_code=404, detail="Agent not registered")

@app.get("/snapshots")
async def list_snapshots():
    snapshots = []
    for category in ["critical", "weekly"]:
        category_dir = f"{SNAPSHOTS_DIR}/{category}"
        if os.path.exists(category_dir):
            for snapshot in os.listdir(category_dir):
                snapshots.append({"category": category, "id": snapshot})
    return {"snapshots": snapshots}

@app.get("/relationships")
async def get_relationships():
    """Get all configured relationships"""
    config = load_config()
    return config.get("relationships", {})

@app.post("/config/agent/{agent_id}")
async def update_agent_config(agent_id: str, updates: Dict[str, Any]):
    config = load_config()
    
    if "ai_agents" not in config:
        config["ai_agents"] = {}
        
    if agent_id not in config["ai_agents"]:
        config["ai_agents"][agent_id] = {}
        
    # Update allowed fields
    allowed_fields = ["has_veto_power", "can_interrupt", "constraints", "capabilities"]
    for field in allowed_fields:
        if field in updates:
            config["ai_agents"][agent_id][field] = updates[field]
            
    save_config(config)
    
    # Also update state if needed
    state = load_state()
    if agent_id in state.get("agents", {}):
        state["agents"][agent_id].update(updates)
        save_state(state)
        
    log_activity("config_update", agent_id, f"Configuration updated for {agent_id}")
    return {"status": "updated", "agent_id": agent_id, "config": config["ai_agents"][agent_id]}

@app.post("/config/relationship")
async def update_relationship(data: Dict[str, Any]):
    # data: {from: str, to: str, type: str, enabled: bool}
    config = load_config()
    
    if "relationships" not in config:
        config["relationships"] = []
        
    # Update or add relationship rule
    # This is a simplfied implementation - storing as list of rules
    rule = {
        "from": data.get("from"),
        "to": data.get("to"),
        "type": data.get("type", "all"),
        "enabled": data.get("enabled", True)
    }
    
    # Remove existing conflicting rules
    config["relationships"] = [r for r in config["relationships"] 
                              if not (r["from"] == rule["from"] and r["to"] == rule["to"])]
    
    config["relationships"].append(rule)
    save_config(config)
    
    log_activity("relationship_update", "system", f"Relationship {rule['from']}->{rule['to']} updated")
    return {"status": "updated", "rule": rule}

# Helper for YAML config
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return yaml.safe_load(f) or {}
    return {}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
