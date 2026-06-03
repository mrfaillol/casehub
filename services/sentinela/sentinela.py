"""
Sentinela - Main Daemon
Unified auto-healing and auto-diagnosis system for CaseHub VPS.
Runs 5 async loops at different intervals and exposes HTTP API on port 8015.

Usage: python3 sentinela.py
"""
import os

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from aiohttp import web

from incident_db import IncidentDB
from health_scorer import compute_health_score, severity_from_score, get_criticality
from signal_collector import SignalCollector
from canary_checker import CanaryChecker
from alert_manager import AlertManager
from smart_healer import SmartHealer
from trend_analyzer import TrendAnalyzer

# Logging setup
LOG_DIR = Path(os.getenv("APP_BASE_PATH", "/opt/casehub") + "/sentinela/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "sentinela.log"),
    ]
)
logger = logging.getLogger("sentinela")


class Sentinela:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        sentinela_cfg = self.config.get("sentinela", {})
        self.port = sentinela_cfg.get("port", 8015)
        db_path = sentinela_cfg.get("db_path", os.getenv("APP_BASE_PATH", "/opt/casehub") + "/sentinela/sentinela.db")

        # Initialize components
        self.db = IncidentDB(db_path)
        self.collector = SignalCollector(self.config)
        self.canary = CanaryChecker(self.config)
        self.alerts = AlertManager(self.config, self.db)
        self.healer = SmartHealer(self.config, self.db, self.alerts)
        self.trends = TrendAnalyzer(self.config, self.db)

        # State
        self._latest_scores = {}
        self._latest_canaries = []
        self._latest_trends = []
        self._running = False

    async def start(self):
        """Initialize DB and start all loops + HTTP server."""
        logger.info("Sentinela starting...")
        await self.db.initialize()
        self._running = True

        intervals = self.config.get("intervals", {})

        # Start all loops as tasks
        tasks = [
            asyncio.create_task(self._health_loop(intervals.get("health_snapshot", 30))),
            asyncio.create_task(self._canary_loop(intervals.get("canary_check", 300))),
            asyncio.create_task(self._trend_loop(intervals.get("trend_analysis", 600))),
            asyncio.create_task(self._digest_loop(intervals.get("daily_digest", ["08:00", "18:00"]))),
            asyncio.create_task(self._cleanup_loop(intervals.get("cleanup_retention_days", 30))),
        ]

        # Start HTTP server
        app = self._create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", self.port)
        await site.start()
        logger.info(f"Sentinela HTTP API listening on 127.0.0.1:{self.port}")

        # Wait for all tasks
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Sentinela shutting down...")
        finally:
            await self._cleanup()

    async def _cleanup(self):
        await self.collector.close()
        await self.canary.close()
        await self.alerts.close()
        await self.db.close()

    # --- Loop 1: Health Snapshot (every 30s) ---

    async def _health_loop(self, interval: int):
        logger.info(f"Health loop started (interval: {interval}s)")
        while self._running:
            try:
                await self._collect_and_score()
            except Exception as e:
                logger.error(f"Health loop error: {e}", exc_info=True)
            await asyncio.sleep(interval)

    async def _collect_and_score(self):
        """Collect signals, compute scores, evaluate healing."""
        signals = await self.collector.collect_all()

        # Inject latest canary results into signals
        for service, svc_signals in signals.items():
            svc_signals["canaries"] = self.canary.get_canaries_for_service(
                self._latest_canaries, service
            )

        scores = {}
        for service, svc_signals in signals.items():
            score, dimensions = compute_health_score(service, svc_signals)
            scores[service] = {"score": score, "dimensions": dimensions}
            await self.db.save_snapshot(service, score, dimensions)

            # Auto-resolve open incidents when score recovers to GREEN
            severity = severity_from_score(score)
            if severity == "GREEN":
                open_incidents = await self.db.get_open_incidents(service)
                if open_incidents:
                    for inc in open_incidents:
                        await self.db.resolve_incident(inc["id"])
                    logger.info(
                        f"Auto-resolved {len(open_incidents)} incident(s) for {service} "
                        f"(score recovered to {score:.0f})"
                    )

            # Evaluate healing need
            if severity in ("RED", "CRITICAL"):
                await self.healer.evaluate_and_heal(
                    service, score, dimensions, scores
                )
            elif severity == "YELLOW":
                criticality = get_criticality(service)
                if criticality >= 1.3:
                    await self.alerts.alert(
                        "YELLOW",
                        f"Score {score:.0f}/100 (priority service)",
                        service
                    )

        self._latest_scores = scores

    # --- Loop 2: Canary Checks (every 5min) ---

    async def _canary_loop(self, interval: int):
        logger.info(f"Canary loop started (interval: {interval}s)")
        # Wait a bit on startup to let services settle
        await asyncio.sleep(30)
        while self._running:
            try:
                await self._run_canaries()
            except Exception as e:
                logger.error(f"Canary loop error: {e}", exc_info=True)
            await asyncio.sleep(interval)

    async def _run_canaries(self):
        """Run all canary checks and store results."""
        results = await self.canary.run_all()
        self._latest_canaries = results

        for result in results:
            await self.db.save_canary_result(
                check_name=result["check_name"],
                passed=result["passed"],
                latency_ms=result["latency_ms"],
                error=result["error"]
            )

            if not result["passed"]:
                severity = "RED" if result["check_name"] in (
                    "whatsapp_connected", "casehub_login_renders", "mariadb_responsive"
                ) else "YELLOW"
                await self.alerts.alert(
                    severity,
                    f"Canary FAILED: {result['check_name']} - {result['error']}",
                    result["check_name"].split("_")[0]
                )

        passed = sum(1 for r in results if r["passed"])
        logger.info(f"Canary results: {passed}/{len(results)} passed")

    # --- Loop 3: Trend Analysis (every 10min) ---

    async def _trend_loop(self, interval: int):
        logger.info(f"Trend loop started (interval: {interval}s)")
        # Wait for some data to accumulate
        await asyncio.sleep(600)
        while self._running:
            try:
                await self._analyze_trends()
            except Exception as e:
                logger.error(f"Trend loop error: {e}", exc_info=True)
            await asyncio.sleep(interval)

    async def _analyze_trends(self):
        """Run trend analysis and alert on warnings."""
        services = list(self.config.get("services", {}).keys())
        warnings = await self.trends.analyze_all(services)
        self._latest_trends = warnings

        for warning in warnings:
            await self.alerts.alert(
                warning["severity"],
                warning["message"],
                warning["service"]
            )

        if warnings:
            logger.info(f"Trend analysis: {len(warnings)} warning(s)")

    # --- Loop 4: Daily Digest (8h and 18h) ---

    async def _digest_loop(self, digest_times: list):
        logger.info(f"Digest loop started (times: {digest_times})")
        while self._running:
            now = datetime.now()
            # Check if current time matches any digest time (within 1 minute)
            current_time = now.strftime("%H:%M")
            if current_time in digest_times:
                try:
                    scores = await self.db.get_latest_scores()
                    open_incidents = await self.db.get_open_incidents()
                    canary_failures = await self.db.get_canary_failures(hours=24)
                    await self.alerts.send_daily_digest(scores, open_incidents, canary_failures)
                    logger.info("Daily digest sent")
                except Exception as e:
                    logger.error(f"Digest error: {e}", exc_info=True)
                # Sleep past this minute to avoid duplicate sends
                await asyncio.sleep(90)
            else:
                await asyncio.sleep(30)

    # --- Loop 5: Cleanup (daily) ---

    async def _cleanup_loop(self, retention_days: int):
        logger.info(f"Cleanup loop started (retention: {retention_days} days)")
        while self._running:
            # Run once per day
            await asyncio.sleep(86400)
            try:
                await self.db.cleanup_old_data(retention_days)
                logger.info(f"Cleanup completed (retention: {retention_days} days)")
            except Exception as e:
                logger.error(f"Cleanup error: {e}", exc_info=True)

    # --- HTTP API ---

    def _create_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/", self._api_dashboard)
        app.router.add_get("/health", self._api_health)
        app.router.add_get("/scores", self._api_scores)
        app.router.add_get("/canaries", self._api_canaries)
        app.router.add_get("/trends", self._api_trends)
        app.router.add_get("/incidents", self._api_incidents)
        app.router.add_get("/status", self._api_full_status)
        return app

    async def _api_dashboard(self, request):
        html = DASHBOARD_HTML
        return web.Response(text=html, content_type="text/html")

    async def _api_health(self, request):
        return web.json_response({
            "status": "ok",
            "uptime": "running",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def _api_scores(self, request):
        return web.json_response(self._latest_scores)

    async def _api_canaries(self, request):
        return web.json_response(self._latest_canaries)

    async def _api_trends(self, request):
        return web.json_response(self._latest_trends)

    async def _api_incidents(self, request):
        incidents = await self.db.get_open_incidents()
        return web.json_response(incidents)

    async def _api_full_status(self, request):
        return web.json_response({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scores": self._latest_scores,
            "canaries": self._latest_canaries,
            "trends": self._latest_trends,
            "open_incidents": await self.db.get_open_incidents(),
        })


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sentinela - CaseHub VPS</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f1117;color:#e1e4e8;min-height:100vh}
.header{background:linear-gradient(135deg,#1a1e2e,#2d1f3d);padding:20px 30px;border-bottom:1px solid #30363d;display:flex;justify-content:space-between;align-items:center}
.header h1{font-size:22px;font-weight:600;color:#f0f6fc}
.header .subtitle{color:#8b949e;font-size:13px;margin-top:2px}
.header .refresh{color:#8b949e;font-size:12px}
.header .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.container{max-width:1200px;margin:0 auto;padding:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-bottom:24px}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:18px;transition:border-color .2s}
.card:hover{border-color:#58a6ff}
.card .name{font-size:13px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px}
.card .score{font-size:36px;font-weight:700;line-height:1}
.card .bar{height:4px;border-radius:2px;background:#21262d;margin-top:12px;overflow:hidden}
.card .bar-fill{height:100%;border-radius:2px;transition:width .5s ease}
.card .dims{margin-top:10px;font-size:11px;color:#8b949e}
.card .dims span{display:inline-block;margin-right:8px}
.green{color:#3fb950}.yellow{color:#d29922}.red{color:#f85149}.critical{color:#ff7b72}
.bg-green{background:#3fb950}.bg-yellow{background:#d29922}.bg-red{background:#f85149}.bg-critical{background:#ff7b72}
.section{margin-bottom:24px}
.section h2{font-size:16px;font-weight:600;color:#c9d1d9;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.canary-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:8px}
.canary{display:flex;align-items:center;gap:10px;padding:10px 14px;background:#161b22;border:1px solid #30363d;border-radius:8px;font-size:13px}
.canary .icon{font-size:16px;flex-shrink:0}
.canary .cname{flex:1;color:#c9d1d9}
.canary .latency{color:#8b949e;font-size:11px}
.canary.fail{border-color:#f8514933}
.canary.fail .cname{color:#f85149}
.incidents{background:#161b22;border:1px solid #30363d;border-radius:10px;overflow:hidden}
.incidents .row{padding:12px 16px;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:12px;font-size:13px}
.incidents .row:last-child{border-bottom:none}
.badge{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;text-transform:uppercase}
.badge.RED{background:#f8514922;color:#f85149}.badge.YELLOW{background:#d2992222;color:#d29922}
.badge.CRITICAL{background:#ff7b7222;color:#ff7b72}.badge.GREEN{background:#3fb95022;color:#3fb950}
.empty{color:#484f58;text-align:center;padding:30px;font-size:13px}
.trend-item{padding:10px 14px;background:#161b22;border:1px solid #30363d;border-radius:8px;font-size:13px;margin-bottom:6px;display:flex;align-items:center;gap:10px}
</style>
</head>
<body>
<div class="header">
 <div>
  <h1><span class="dot bg-green" id="pulse"></span>Sentinela</h1>
  <div class="subtitle">CaseHub VPS Auto-Healing Dashboard</div>
 </div>
 <div class="refresh" id="ts">Loading...</div>
</div>
<div class="container">
 <div class="grid" id="scores"></div>
 <div class="section">
  <h2>Canary Checks</h2>
  <div class="canary-grid" id="canaries"></div>
 </div>
 <div class="section" id="trends-section" style="display:none">
  <h2>Trend Warnings</h2>
  <div id="trends"></div>
 </div>
 <div class="section">
  <h2>Open Incidents</h2>
  <div class="incidents" id="incidents"><div class="empty">No open incidents</div></div>
 </div>
</div>
<script>
const CLS = {GREEN:'green',YELLOW:'yellow',RED:'red',CRITICAL:'critical'};
const BG = {GREEN:'bg-green',YELLOW:'bg-yellow',RED:'bg-red',CRITICAL:'bg-critical'};
function sev(s){return s>=80?'GREEN':s>=50?'YELLOW':s>=20?'RED':'CRITICAL'}
function fmt(n){return Math.round(n)}

async function load(){
 try{
  const r=await fetch('status');
  const d=await r.json();
  renderScores(d.scores);
  renderCanaries(d.canaries);
  renderTrends(d.trends);
  renderIncidents(d.open_incidents);
  const t=new Date(d.timestamp);
  document.getElementById('ts').textContent='Updated: '+t.toLocaleTimeString();
  const worst=Math.min(...Object.values(d.scores).map(s=>s.score));
  const p=document.getElementById('pulse');
  p.className='dot '+BG[sev(worst)];
 }catch(e){document.getElementById('ts').textContent='Error: '+e.message}
}

function renderScores(scores){
 const el=document.getElementById('scores');
 el.innerHTML=Object.entries(scores).sort((a,b)=>b[1].score-a[1].score).map(([name,data])=>{
  const s=data.score,sv=sev(s),d=data.dimensions;
  return `<div class="card">
   <div class="name">${name}</div>
   <div class="score ${CLS[sv]}">${fmt(s)}</div>
   <div class="bar"><div class="bar-fill ${BG[sv]}" style="width:${s}%"></div></div>
   <div class="dims">
    ${Object.entries(d).map(([k,v])=>`<span title="${k}">${k.replace('_',' ')}: ${fmt(v)}</span>`).join('')}
   </div>
  </div>`;
 }).join('');
}

function renderCanaries(canaries){
 const el=document.getElementById('canaries');
 if(!canaries||!canaries.length){el.innerHTML='<div class="empty">Waiting for first canary cycle...</div>';return}
 el.innerHTML=canaries.map(c=>{
  const icon=c.passed?'<span style="color:#3fb950">&#10003;</span>':'<span style="color:#f85149">&#10007;</span>';
  return `<div class="canary ${c.passed?'':'fail'}">
   <span class="icon">${icon}</span>
   <span class="cname">${c.check_name.replace(/_/g,' ')}</span>
   <span class="latency">${c.latency_ms}ms</span>
  </div>`;
 }).join('');
}

function renderTrends(trends){
 const sec=document.getElementById('trends-section');
 const el=document.getElementById('trends');
 if(!trends||!trends.length){sec.style.display='none';return}
 sec.style.display='block';
 el.innerHTML=trends.map(t=>`<div class="trend-item">
  <span class="badge ${t.severity}">${t.severity}</span>
  <span>${t.service}: ${t.message}</span>
 </div>`).join('');
}

function renderIncidents(incidents){
 const el=document.getElementById('incidents');
 if(!incidents||!incidents.length){el.innerHTML='<div class="empty">No open incidents</div>';return}
 el.innerHTML=incidents.map(i=>`<div class="row">
  <span class="badge ${i.severity}">${i.severity}</span>
  <span style="flex:1">${i.service} - ${i.type}</span>
  <span style="color:#8b949e;font-size:11px">${i.created_at||''}</span>
 </div>`).join('');
}

load();
setInterval(load,30000);
</script>
</body>
</html>"""


async def main():
    config_path = Path(__file__).parent / "config.yaml"
    sentinela = Sentinela(str(config_path))
    await sentinela.start()


if __name__ == "__main__":
    asyncio.run(main())
