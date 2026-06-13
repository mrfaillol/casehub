#!/usr/bin/env python3
"""
Auto-Healer Engine for CaseHub VPS
===============================
Monitors PM2 services, matches errors against playbooks, and executes
graduated responses (P3) while respecting all 8 healing principles.

Principles:
  P1 - Reversibility: backup before any action
  P2 - No collateral damage: check dependencies before acting
  P3 - Graduated response: levels 0-4
  P4 - Idempotency: safe to run repeatedly
  P5 - Rate limiting: max 3 attempts/hr, max 1 restart/10min per service
  P6 - Full audit trail
  P7 - Dependency awareness
  P8 - Post-action verification

Usage:
  python3 healer.py
  python3 healer.py --dry-run
  python3 healer.py --verbose
  python3 healer.py --dry-run --verbose
"""

import argparse
import copy
import datetime
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request
import urllib.error

try:
    import yaml
except ImportError:
    print("FATAL: pyyaml not installed. Run: pip3 install pyyaml", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_DIR = os.getenv("APP_BASE_PATH", "/opt/casehub") + "/auto-healer"
DEFAULT_CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
DEFAULT_PLAYBOOKS_PATH = os.path.join(BASE_DIR, "playbooks.yaml")
DEFAULT_STATE_PATH = os.path.join(BASE_DIR, "state.json")
DEFAULT_AUDIT_LOG = os.path.join(BASE_DIR, "audit.log")
DEFAULT_BACKUP_DIR = os.path.join(BASE_DIR, "backups")
ALERT_SCRIPT = os.getenv("APP_BASE_PATH", "/opt/casehub") + "/send_alert_email.py"
WHATSAPP_ADMIN = "5532991513405"
WHATSAPP_API = "http://localhost:3001/api/send-message"
PM2_LOG_DIR = "/root/.pm2/logs"

MAX_ATTEMPTS_PER_HOUR = 3
MAX_RESTART_PER_10MIN = 1

LEVEL_NAMES = {
    0: "OBSERVE",
    1: "NOTIFY",
    2: "MITIGATE",
    3: "REMEDIATE",
    4: "ESCALATE",
}


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(verbose=False):
    """Configure logger with both console and file handlers."""
    logger = logging.getLogger("auto-healer")
    logger.setLevel(logging.DEBUG)

    # Remove existing handlers to support idempotent calls
    logger.handlers.clear()

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(ch)

    # File handler (audit log - P6)
    try:
        os.makedirs(os.path.dirname(DEFAULT_AUDIT_LOG), exist_ok=True)
        fh = logging.FileHandler(DEFAULT_AUDIT_LOG, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)-8s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(fh)
    except Exception as exc:
        logger.warning("Could not open audit log file: %s", exc)

    return logger


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def now_iso():
    """Return current time as ISO string."""
    return datetime.datetime.now().isoformat()


def now_ts():
    """Return current time as Unix timestamp."""
    return time.time()


def run_cmd(cmd, timeout=30):
    """Run a shell command. Returns (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out after {}s".format(timeout)
    except Exception as exc:
        return -1, "", str(exc)


def http_get(url, timeout=10):
    """HTTP GET. Returns (status_code, body). Returns (-1, error) on failure."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, str(exc)
    except Exception as exc:
        return -1, str(exc)


def http_post_json(url, data, timeout=10):
    """HTTP POST with JSON body. Returns (status_code, body)."""
    try:
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, str(exc)
    except Exception as exc:
        return -1, str(exc)


def shell_quote(s):
    """Shell-quote a string for safe passing to subprocess."""
    return "'" + s.replace("'", "'\\''") + "'"


# ---------------------------------------------------------------------------
# State management (P4 - idempotent via state tracking)
# ---------------------------------------------------------------------------

def load_state(path):
    """Load persisted state from JSON file."""
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"services": {}, "playbooks": {}, "last_run_time": None}


def save_state(state, path):
    """Atomically save state to JSON file."""
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_yaml_file(path):
    """Load a YAML file, returning empty dict on failure."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_pm2_status(logger):
    """Collect PM2 process list via pm2 jlist."""
    rc, stdout, stderr = run_cmd("pm2 jlist", timeout=15)
    if rc != 0:
        logger.error("pm2 jlist failed: %s", stderr)
        return []
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse pm2 jlist output: %s", exc)
        return []


def collect_service_error_logs(service_name, lines=50, logger=None):
    """Read last N lines of a PM2 service error log."""
    candidates = [
        os.path.join(PM2_LOG_DIR, "{}-error.log".format(service_name)),
        os.path.join(PM2_LOG_DIR, "{}-err.log".format(service_name)),
        os.path.join(PM2_LOG_DIR, "{}-error-0.log".format(service_name)),
    ]
    log_file = None
    for c in candidates:
        if os.path.exists(c):
            log_file = c
            break

    if not log_file:
        return ""

    rc, stdout, _ = run_cmd("tail -n {} '{}'".format(lines, log_file), timeout=10)
    return stdout if rc == 0 else ""


def collect_system_metrics(logger):
    """Collect RAM and disk metrics."""
    metrics = {"ram": {}, "disk": {}}

    # RAM via free
    rc, stdout, _ = run_cmd("free -m", timeout=10)
    if rc == 0:
        for line in stdout.splitlines():
            if line.startswith("Mem:"):
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        total = int(parts[1])
                        used = int(parts[2])
                        metrics["ram"]["total_mb"] = total
                        metrics["ram"]["used_mb"] = used
                        metrics["ram"]["pct"] = round(used / total * 100, 1) if total else 0
                    except ValueError:
                        pass

    # Disk via df
    rc, stdout, _ = run_cmd("df -h / | tail -1", timeout=10)
    if rc == 0:
        parts = stdout.split()
        if len(parts) >= 5:
            metrics["disk"]["use_pct"] = parts[4].replace("%", "")

    return metrics


def collect_postgres_errors(logger):
    """Collect recent PostgreSQL errors from journalctl or pg logs."""
    rc, stdout, _ = run_cmd(
        "journalctl -u postgresql --since '1 hour ago' --no-pager -q 2>/dev/null"
        " | grep -iE 'error|fatal|panic' | tail -20",
        timeout=15
    )
    if rc == 0 and stdout:
        return stdout

    rc, stdout, _ = run_cmd(
        "find /var/log/postgresql/ -name '*.log' -mmin -60 2>/dev/null"
        " | head -1 | xargs -I{} tail -30 {} 2>/dev/null"
        " | grep -iE 'error|fatal|panic'",
        timeout=15
    )
    return stdout if rc == 0 else ""


# ---------------------------------------------------------------------------
# Delta calculation
# ---------------------------------------------------------------------------

def calc_restart_delta(pm2_procs, prev_state):
    """Calculate restart count delta for each service since last check."""
    deltas = {}
    for proc in pm2_procs:
        name = proc.get("name", "unknown")
        pm2_env = proc.get("pm2_env", {})
        current_restarts = pm2_env.get("restart_time", 0)
        prev = prev_state.get("services", {}).get(name, {})
        prev_restarts = prev.get("last_restarts", 0)
        delta = max(0, current_restarts - prev_restarts)
        deltas[name] = {
            "current_restarts": current_restarts,
            "prev_restarts": prev_restarts,
            "delta": delta,
            "status": pm2_env.get("status", "unknown"),
            "pid": proc.get("pid", None),
        }
    return deltas


# ---------------------------------------------------------------------------
# Playbook matching
# ---------------------------------------------------------------------------

def _extract_snippet(log_text, pattern, context_lines=3):
    """Extract lines around the first occurrence of a pattern."""
    lines = log_text.splitlines()
    for i, line in enumerate(lines):
        if pattern.lower() in line.lower():
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            return "\n".join(lines[start:end])
    return ""


def match_playbooks(playbooks, error_logs, deltas, system_metrics,
                    pg_errors, logger):
    """
    Match current conditions against playbook triggers.
    Returns list of (playbook_id, playbook_config, matched_context).
    """
    matches = []
    pb_list = playbooks.get("playbooks", [])
    if not isinstance(pb_list, list):
        pb_list = []

    for pb in pb_list:
        pb_id = pb.get("id", "unknown")
        trigger = pb.get("trigger", {})
        trigger_type = trigger.get("type", "")
        matched = False
        context = {}

        try:
            if trigger_type == "error_pattern":
                pattern = trigger.get("pattern", "")
                service = trigger.get("service", "")
                if pattern and service and service in error_logs:
                    if pattern.lower() in error_logs[service].lower():
                        matched = True
                        context["service"] = service
                        context["pattern"] = pattern
                        context["log_snippet"] = _extract_snippet(
                            error_logs[service], pattern)

            elif trigger_type == "restart_delta":
                service = trigger.get("service", "")
                threshold = trigger.get("threshold", 3)
                if service in deltas and deltas[service]["delta"] >= threshold:
                    matched = True
                    context["service"] = service
                    context["delta"] = deltas[service]["delta"]

            elif trigger_type == "service_stopped":
                service = trigger.get("service", "")
                if service in deltas and deltas[service]["status"] == "stopped":
                    matched = True
                    context["service"] = service

            elif trigger_type == "service_errored":
                service = trigger.get("service", "")
                if service in deltas and deltas[service]["status"] == "errored":
                    matched = True
                    context["service"] = service

            elif trigger_type == "ram_threshold":
                threshold = trigger.get("pct", 90)
                current = system_metrics.get("ram", {}).get("pct", 0)
                if current >= threshold:
                    matched = True
                    context["ram_pct"] = current
                    context["threshold"] = threshold

            elif trigger_type == "disk_threshold":
                threshold = trigger.get("pct", 90)
                try:
                    current = float(
                        system_metrics.get("disk", {}).get("use_pct", 0))
                except (ValueError, TypeError):
                    current = 0
                if current >= threshold:
                    matched = True
                    context["disk_pct"] = current
                    context["threshold"] = threshold

            elif trigger_type == "pg_error":
                pattern = trigger.get("pattern", "")
                if pattern and pg_errors and pattern.lower() in pg_errors.lower():
                    matched = True
                    context["pattern"] = pattern
                    context["pg_log"] = pg_errors[:500]

        except Exception as exc:
            logger.error("Error matching playbook '%s': %s", pb_id, exc)
            continue

        if matched:
            logger.debug("Playbook '%s' matched: %s", pb_id, context)
            matches.append((pb_id, pb, context))

    return matches


# ---------------------------------------------------------------------------
# Rate limiting (P5)
# ---------------------------------------------------------------------------

def is_rate_limited(pb_id, service, state, logger):
    """
    Check P5 rate limits:
      - Max 3 attempts per hour per playbook
      - Max 1 restart per 10 minutes per service
    """
    now = now_ts()
    pb_state = state.get("playbooks", {}).get(pb_id, {})

    # Check per-playbook hourly limit
    attempts = pb_state.get("attempts_in_window", [])
    recent = [t for t in attempts if now - t < 3600]
    if len(recent) >= MAX_ATTEMPTS_PER_HOUR:
        logger.warning(
            "Rate limited: playbook '%s' has %d attempts in last hour",
            pb_id, len(recent))
        return True

    # Check per-service 10-minute restart limit
    if service:
        svc_state = state.get("services", {}).get(service, {})
        last_restart_time = svc_state.get("last_restart_action_time", 0)
        if now - last_restart_time < 600:
            elapsed = int(now - last_restart_time)
            logger.warning(
                "Rate limited: service '%s' was restarted %ds ago (min 600s)",
                service, elapsed)
            return True

    return False


def record_attempt(pb_id, state):
    """Record an attempt timestamp for rate limiting."""
    now = now_ts()
    if "playbooks" not in state:
        state["playbooks"] = {}
    if pb_id not in state["playbooks"]:
        state["playbooks"][pb_id] = {}
    pb = state["playbooks"][pb_id]
    attempts = pb.get("attempts_in_window", [])
    # Keep only last hour
    attempts = [t for t in attempts if now - t < 3600]
    attempts.append(now)
    pb["attempts_in_window"] = attempts
    pb["last_attempt_time"] = now_iso()
    pb["attempt_count"] = pb.get("attempt_count", 0) + 1


# ---------------------------------------------------------------------------
# Notification (Level 1 + Level 4)
# ---------------------------------------------------------------------------

def send_email_alert(subject, body, logger):
    """Send email alert via the alert script."""
    if not os.path.exists(ALERT_SCRIPT):
        logger.error("Alert script not found: %s", ALERT_SCRIPT)
        return False
    rc, stdout, stderr = run_cmd(
        "python3 {} --subject {} --body {}".format(
            ALERT_SCRIPT, shell_quote(subject), shell_quote(body)),
        timeout=30
    )
    if rc != 0:
        logger.error("Email alert failed: %s", stderr)
        return False
    logger.info("Email alert sent: %s", subject)
    return True


def send_whatsapp_alert(message, logger):
    """Send WhatsApp alert to admin."""
    data = {
        "chatId": "{}@c.us".format(WHATSAPP_ADMIN),
        "message": message
    }
    status, resp = http_post_json(WHATSAPP_API, data, timeout=15)
    if status in (200, 201):
        logger.info("WhatsApp alert sent to %s", WHATSAPP_ADMIN)
        return True
    logger.error("WhatsApp alert failed (status %s): %s", status, resp)
    return False


def notify(subject, body, level, logger):
    """Send notifications via email and WhatsApp."""
    prefix = "[Auto-Healer L{}]".format(level)
    full_subject = "{} {}".format(prefix, subject)
    wa_msg = "{} {}\n\n{}".format(prefix, subject, body[:1500])

    send_email_alert(full_subject, body, logger)
    send_whatsapp_alert(wa_msg, logger)


# ---------------------------------------------------------------------------
# Backup helpers (P1 - Reversibility)
# ---------------------------------------------------------------------------

def backup_state_file(logger):
    """Backup current state.json before modification."""
    src = DEFAULT_STATE_PATH
    if not os.path.exists(src):
        return ""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(DEFAULT_BACKUP_DIR, "state_{}.json".format(ts))
    try:
        shutil.copy2(src, dst)
        logger.debug("State backup: %s", dst)
        return dst
    except Exception as exc:
        logger.error("Failed to backup state: %s", exc)
        return ""


def backup_file(filepath, logger):
    """Backup an arbitrary file before remediation (P1)."""
    if not os.path.exists(filepath):
        logger.warning("Cannot backup non-existent file: %s", filepath)
        return ""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = os.path.basename(filepath)
    dst = os.path.join(DEFAULT_BACKUP_DIR, "{}_{}.bak".format(basename, ts))
    try:
        shutil.copy2(filepath, dst)
        logger.info("File backup: %s -> %s", filepath, dst)
        return dst
    except Exception as exc:
        logger.error("Failed to backup file %s: %s", filepath, exc)
        return ""


# ---------------------------------------------------------------------------
# Dependency checking (P2 + P7)
# ---------------------------------------------------------------------------

DEPENDENCY_MAP = {
    "casehub": ["whatsapp-bot"],
    "ilc-tools": [],
    "whatsapp-bot": [],
    "vps-monitor": [],
    "client-intake": ["whatsapp-bot"],
    "n8n": [],
}


def check_dependencies(service, pm2_procs, logger):
    """
    Check if restarting a service would affect dependent services.
    Returns list of warnings (empty = safe to proceed).
    """
    warnings = []
    deps = DEPENDENCY_MAP.get(service, [])
    proc_map = {p.get("name"): p for p in pm2_procs}

    for dep in deps:
        if dep in proc_map:
            dep_status = proc_map[dep].get("pm2_env", {}).get("status", "unknown")
            if dep_status == "online":
                warnings.append(
                    "Service '{}' depends on '{}' which is online. "
                    "Restarting '{}' may briefly disrupt dependent "
                    "connections.".format(service, dep, service)
                )
    return warnings


# ---------------------------------------------------------------------------
# Health verification (P8)
# ---------------------------------------------------------------------------

def verify_health(service, config, logger, wait=0):
    """
    Verify service health after an action (P8).
    Checks health endpoint if configured, otherwise checks PM2 status.
    """
    svc_cfg = config.get("services", {}).get(service, {})
    health_url = svc_cfg.get("health", "")
    restart_wait = svc_cfg.get("restart_wait", wait) or 10

    logger.info("Waiting %ds for '%s' to initialize...", restart_wait, service)
    time.sleep(restart_wait)

    if health_url:
        status, body = http_get(health_url, timeout=15)
        if 200 <= status < 400:
            logger.info("Health check PASSED for '%s': HTTP %d", service, status)
            return True
        logger.warning(
            "Health check FAILED for '%s': HTTP %d - %s",
            service, status, body[:200])
        return False

    # Fallback: check PM2 status
    rc, stdout, _ = run_cmd("pm2 jlist", timeout=15)
    if rc == 0:
        try:
            procs = json.loads(stdout)
            for p in procs:
                if p.get("name") == service:
                    st = p.get("pm2_env", {}).get("status", "")
                    if st == "online":
                        logger.info(
                            "PM2 status check PASSED for '%s': online", service)
                        return True
                    logger.warning(
                        "PM2 status check FAILED for '%s': %s", service, st)
                    return False
        except json.JSONDecodeError:
            pass

    logger.warning("Could not verify health of '%s'", service)
    return False


# ---------------------------------------------------------------------------
# Action executors (per level)
# ---------------------------------------------------------------------------

def execute_level_0(pb_id, pb, context, state, dry_run, logger):
    """Level 0: OBSERVE - log only."""
    service = context.get("service", "system")
    msg = ("[L0 OBSERVE] Playbook '{}' triggered for '{}'. "
           "Context: {}".format(pb_id, service,
                                json.dumps(context, default=str)))
    logger.info(msg)
    record_attempt(pb_id, state)
    state["playbooks"][pb_id]["last_result"] = "observed"
    return "observed"


def execute_level_1(pb_id, pb, context, state, dry_run, logger):
    """Level 1: NOTIFY - send alert to admin."""
    service = context.get("service", "system")
    desc = pb.get("description", pb_id)
    subject = "{}: {}".format(service, desc)
    body = (
        "Auto-Healer detected an issue.\n\n"
        "Playbook: {pb}\n"
        "Service: {svc}\n"
        "Description: {desc}\n"
        "Level: 1 (NOTIFY)\n"
        "Context: {ctx}\n"
        "Time: {ts}\n"
    ).format(pb=pb_id, svc=service, desc=desc,
             ctx=json.dumps(context, indent=2, default=str), ts=now_iso())

    if dry_run:
        logger.info("[DRY-RUN] Would send notification: %s", subject)
    else:
        notify(subject, body, 1, logger)

    record_attempt(pb_id, state)
    state["playbooks"][pb_id]["last_result"] = "notified"
    return "notified"


def execute_level_2(pb_id, pb, context, state, config, pm2_procs,
                    dry_run, logger):
    """Level 2: MITIGATE - backup state, restart service, verify health."""
    service = context.get("service", "")
    if not service:
        logger.error("Level 2 action requires a service name")
        return "error_no_service"

    # P2: Check dependencies
    dep_warnings = check_dependencies(service, pm2_procs, logger)
    for w in dep_warnings:
        logger.warning("Dependency warning: %s", w)

    # CRITICAL: Never pm2 delete whatsapp-bot (or any service)
    action = pb.get("action", {})
    cmd_override = action.get("command", "")
    if "pm2 delete" in cmd_override:
        logger.error(
            "BLOCKED: pm2 delete is FORBIDDEN. Using pm2 restart instead.")
        cmd_override = ""

    # P1: Backup state
    if not dry_run:
        backup_state_file(logger)

    restart_cmd = cmd_override if cmd_override else "pm2 restart {}".format(
        service)

    if dry_run:
        logger.info("[DRY-RUN] Would execute: %s", restart_cmd)
        record_attempt(pb_id, state)
        state["playbooks"][pb_id]["last_result"] = "dry_run_mitigate"
        return "dry_run_mitigate"

    # Execute restart
    logger.info("Executing: %s", restart_cmd)
    rc, stdout, stderr = run_cmd(restart_cmd, timeout=30)
    if rc != 0:
        logger.error("Restart command failed: %s", stderr)
        notify("Restart FAILED: {}".format(service),
               "Command: {}\nError: {}".format(restart_cmd, stderr),
               2, logger)
        record_attempt(pb_id, state)
        state["playbooks"][pb_id]["last_result"] = "restart_failed"
        return "restart_failed"

    logger.info("Restart command succeeded for '%s'", service)

    # Record restart time for rate limiting
    if "services" not in state:
        state["services"] = {}
    if service not in state["services"]:
        state["services"][service] = {}
    state["services"][service]["last_restart_action_time"] = now_ts()

    # P8: Verify health
    svc_cfg = config.get("services", {}).get(service, {})
    wait_time = svc_cfg.get("restart_wait", 10)
    healthy = verify_health(service, config, logger, wait=wait_time)

    if not healthy:
        logger.warning(
            "Health check failed after restart of '%s'. Sending notification.",
            service)
        notify(
            "Health check FAILED after restart: {}".format(service),
            "Service '{}' did not pass health check after restart.\n"
            "Playbook: {}\nTime: {}".format(service, pb_id, now_iso()),
            2, logger)
        record_attempt(pb_id, state)
        state["playbooks"][pb_id]["last_result"] = "restart_unhealthy"
        return "restart_unhealthy"

    logger.info("Service '%s' is healthy after restart.", service)
    record_attempt(pb_id, state)
    state["playbooks"][pb_id]["last_result"] = "mitigated"
    return "mitigated"


def execute_level_3(pb_id, pb, context, state, config, pm2_procs,
                    dry_run, logger):
    """Level 3: REMEDIATE - backup file, revert from backup source,
    restart, verify."""
    service = context.get("service", "")
    action = pb.get("action", {})
    target_file = action.get("target_file", "")
    backup_source = action.get("backup_source", "")
    restart_after = action.get("restart_service", service)

    if not target_file or not backup_source:
        logger.error(
            "Level 3 requires 'target_file' and 'backup_source' in action")
        return "error_config"

    # P2: dependency check
    if restart_after:
        dep_warnings = check_dependencies(restart_after, pm2_procs, logger)
        for w in dep_warnings:
            logger.warning("Dependency warning: %s", w)

    if dry_run:
        logger.info(
            "[DRY-RUN] Would revert '%s' from '%s' and restart '%s'",
            target_file, backup_source, restart_after)
        record_attempt(pb_id, state)
        state["playbooks"][pb_id]["last_result"] = "dry_run_remediate"
        return "dry_run_remediate"

    # P1: Backup current file
    bak_path = backup_file(target_file, logger)
    if not bak_path and os.path.exists(target_file):
        logger.error("Cannot proceed without backup. Aborting remediation.")
        return "error_backup"

    # Revert file
    if not os.path.exists(backup_source):
        logger.error("Backup source not found: %s", backup_source)
        return "error_no_source"

    try:
        shutil.copy2(backup_source, target_file)
        logger.info("Reverted '%s' from '%s'", target_file, backup_source)
    except Exception as exc:
        logger.error("Failed to revert file: %s. Restoring original.", exc)
        if bak_path:
            try:
                shutil.copy2(bak_path, target_file)
                logger.info("Restored original file from backup.")
            except Exception as exc2:
                logger.error("CRITICAL: Could not restore original: %s", exc2)
        return "error_revert"

    # Restart service (CRITICAL: Never pm2 delete)
    if restart_after:
        restart_cmd = "pm2 restart {}".format(restart_after)
        logger.info("Executing: %s", restart_cmd)
        rc, _, stderr = run_cmd(restart_cmd, timeout=30)
        if rc != 0:
            logger.error("Restart failed after revert: %s", stderr)

        # Record restart time
        if "services" not in state:
            state["services"] = {}
        if restart_after not in state["services"]:
            state["services"][restart_after] = {}
        state["services"][restart_after]["last_restart_action_time"] = now_ts()

    # P8: Verify health
    if restart_after:
        svc_cfg = config.get("services", {}).get(restart_after, {})
        wait_time = svc_cfg.get("restart_wait", 10)
        healthy = verify_health(restart_after, config, logger, wait=wait_time)
        if not healthy:
            logger.warning(
                "Health check failed after remediation. "
                "Rolling back to original file.")
            if bak_path:
                try:
                    shutil.copy2(bak_path, target_file)
                    run_cmd("pm2 restart {}".format(restart_after), timeout=30)
                    logger.info(
                        "Rolled back file and restarted '%s'", restart_after)
                except Exception as exc:
                    logger.error("Rollback failed: %s", exc)

            notify(
                "Remediation FAILED + rolled back: {}".format(restart_after),
                "Playbook '{}' remediation failed health check.\n"
                "Original file restored.\nTime: {}".format(pb_id, now_iso()),
                3, logger)
            record_attempt(pb_id, state)
            state["playbooks"][pb_id]["last_result"] = "remediate_rolled_back"
            return "remediate_rolled_back"

    logger.info("Remediation succeeded for playbook '%s'.", pb_id)
    notify(
        "Remediation OK: {}".format(service or restart_after),
        "Playbook '{}' executed successfully.\n"
        "File reverted: {}\nTime: {}".format(pb_id, target_file, now_iso()),
        3, logger)
    record_attempt(pb_id, state)
    state["playbooks"][pb_id]["last_result"] = "remediated"
    return "remediated"


def execute_level_4(pb_id, pb, context, state, dry_run, logger):
    """Level 4: ESCALATE - send urgent escalation with full context."""
    service = context.get("service", "system")
    desc = pb.get("description", pb_id)

    separator = "=" * 40
    body = (
        "URGENT ESCALATION REQUIRED\n"
        "{sep}\n\n"
        "Playbook: {pb}\n"
        "Service: {svc}\n"
        "Description: {desc}\n"
        "Level: 4 (ESCALATE)\n"
        "Time: {ts}\n\n"
        "Context:\n{ctx}\n\n"
        "Previous attempts: {att}\n\n"
        "This issue requires manual intervention. The auto-healer has "
        "exhausted automated responses or this playbook is configured "
        "for immediate escalation.\n"
    ).format(
        sep=separator,
        pb=pb_id, svc=service, desc=desc, ts=now_iso(),
        ctx=json.dumps(context, indent=2, default=str),
        att=state.get("playbooks", {}).get(pb_id, {}).get("attempt_count", 0)
    )
    subject = "URGENT - {}: {}".format(service, desc)

    if dry_run:
        logger.info("[DRY-RUN] Would send URGENT escalation: %s", subject)
    else:
        send_email_alert(
            "[Auto-Healer L4 ESCALATE] {}".format(subject), body, logger)
        send_whatsapp_alert(
            "*URGENT ESCALATION*\n\n{}\n\n{}".format(subject, body[:1200]),
            logger)

    record_attempt(pb_id, state)
    state["playbooks"][pb_id]["last_result"] = "escalated"
    return "escalated"


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def execute_playbook(pb_id, pb, context, state, config, pm2_procs,
                     dry_run, logger):
    """Route a matched playbook to the correct level executor."""
    level = pb.get("level", 0)
    service = context.get("service", "")

    logger.info(
        "Executing playbook '%s' at level %d (%s) for service '%s'",
        pb_id, level, LEVEL_NAMES.get(level, "?"), service)

    # P6: Audit trail
    audit_entry = {
        "timestamp": now_iso(),
        "playbook": pb_id,
        "level": level,
        "service": service,
        "context": context,
        "dry_run": dry_run,
    }

    # P5: Rate limiting (skip for level 0 observe-only)
    if level > 0 and is_rate_limited(pb_id, service, state, logger):
        logger.warning(
            "Playbook '%s' is rate-limited. Skipping execution.", pb_id)
        audit_entry["result"] = "rate_limited"
        logger.debug("AUDIT: %s", json.dumps(audit_entry, default=str))
        return "rate_limited"

    try:
        if level == 0:
            result = execute_level_0(
                pb_id, pb, context, state, dry_run, logger)
        elif level == 1:
            result = execute_level_1(
                pb_id, pb, context, state, dry_run, logger)
        elif level == 2:
            result = execute_level_2(
                pb_id, pb, context, state, config, pm2_procs, dry_run, logger)
        elif level == 3:
            result = execute_level_3(
                pb_id, pb, context, state, config, pm2_procs, dry_run, logger)
        elif level == 4:
            result = execute_level_4(
                pb_id, pb, context, state, dry_run, logger)
        else:
            logger.error("Unknown level %d for playbook '%s'", level, pb_id)
            result = "unknown_level"
    except Exception as exc:
        logger.error(
            "Exception executing playbook '%s': %s\n%s",
            pb_id, exc, traceback.format_exc())
        result = "error: {}".format(exc)

    audit_entry["result"] = result
    logger.debug("AUDIT: %s", json.dumps(audit_entry, default=str))
    return result


def run_healer(dry_run=False, verbose=False):
    """Main healer entry point."""
    logger = setup_logging(verbose=verbose)
    logger.info("=" * 60)
    logger.info("Auto-Healer starting%s", " (DRY-RUN)" if dry_run else "")
    logger.info("=" * 60)

    # Load configuration
    config = load_yaml_file(DEFAULT_CONFIG_PATH)
    playbooks = load_yaml_file(DEFAULT_PLAYBOOKS_PATH)
    state = load_state(DEFAULT_STATE_PATH)

    if not playbooks:
        logger.warning(
            "No playbooks loaded from %s. Nothing to check.",
            DEFAULT_PLAYBOOKS_PATH)

    # Ensure backup directory exists
    os.makedirs(DEFAULT_BACKUP_DIR, exist_ok=True)

    # ---------------------------------------------------------------
    # Phase 1: Collect data
    # ---------------------------------------------------------------
    logger.info("Phase 1: Collecting data...")

    pm2_procs = collect_pm2_status(logger)
    if not pm2_procs:
        logger.warning("No PM2 processes found. Services may be down.")

    # Collect error logs for each known service
    known_services = list(config.get("services", {}).keys())
    for p in pm2_procs:
        name = p.get("name", "")
        if name and name not in known_services:
            known_services.append(name)

    error_logs = {}
    for svc in known_services:
        error_logs[svc] = collect_service_error_logs(
            svc, lines=50, logger=logger)

    system_metrics = collect_system_metrics(logger)
    pg_errors = collect_postgres_errors(logger)

    logger.info(
        "Collected: %d PM2 procs, %d error logs, RAM %s%%, Disk %s%%",
        len(pm2_procs), len(error_logs),
        system_metrics.get("ram", {}).get("pct", "?"),
        system_metrics.get("disk", {}).get("use_pct", "?"))
    if pg_errors:
        logger.info("PostgreSQL errors detected in last hour.")

    # ---------------------------------------------------------------
    # Phase 2: Calculate deltas
    # ---------------------------------------------------------------
    logger.info("Phase 2: Calculating restart deltas...")
    deltas = calc_restart_delta(pm2_procs, state)
    for svc, d in deltas.items():
        if d["delta"] > 0:
            logger.warning(
                "Service '%s' restarted %d times since last check "
                "(total: %d)", svc, d["delta"], d["current_restarts"])
        elif verbose:
            logger.debug(
                "Service '%s': status=%s, restarts=%d (delta=%d)",
                svc, d["status"], d["current_restarts"], d["delta"])

    # ---------------------------------------------------------------
    # Phase 3: Match playbooks
    # ---------------------------------------------------------------
    logger.info("Phase 3: Matching playbooks...")
    matches = match_playbooks(
        playbooks, error_logs, deltas, system_metrics, pg_errors, logger)
    logger.info("Matched %d playbook(s).", len(matches))

    # ---------------------------------------------------------------
    # Phase 4: Execute matched playbooks (graduated response - P3)
    # ---------------------------------------------------------------
    if matches:
        logger.info("Phase 4: Executing playbooks...")
        # Sort by level ascending (observe first, escalate last)
        matches.sort(key=lambda x: x[1].get("level", 0))

        results = []
        for pb_id, pb, context in matches:
            result = execute_playbook(
                pb_id, pb, context, state, config, pm2_procs, dry_run, logger)
            results.append((pb_id, result))
            logger.info("Playbook '%s' result: %s", pb_id, result)
    else:
        logger.info("Phase 4: No playbooks matched. System looks healthy.")

    # ---------------------------------------------------------------
    # Phase 5: Update state
    # ---------------------------------------------------------------
    logger.info("Phase 5: Saving state...")

    if "services" not in state:
        state["services"] = {}
    for proc in pm2_procs:
        name = proc.get("name", "")
        if not name:
            continue
        if name not in state["services"]:
            state["services"][name] = {}
        state["services"][name]["last_restarts"] = (
            proc.get("pm2_env", {}).get("restart_time", 0)
        )
        state["services"][name]["last_status"] = (
            proc.get("pm2_env", {}).get("status", "unknown")
        )
        state["services"][name]["last_check_time"] = now_iso()

    state["last_run_time"] = now_iso()

    if not dry_run:
        save_state(state, DEFAULT_STATE_PATH)
        logger.info("State saved to %s", DEFAULT_STATE_PATH)
    else:
        logger.info("[DRY-RUN] State not saved.")

    logger.info("Auto-Healer completed successfully.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Auto-Healer Engine for CaseHub VPS services"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Diagnose issues but do not execute any actions"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable detailed debug output"
    )
    args = parser.parse_args()

    try:
        run_healer(dry_run=args.dry_run, verbose=args.verbose)
    except Exception as exc:
        # The healer itself must NEVER crash
        print(
            "[FATAL] Auto-Healer encountered an unhandled exception: {}".format(
                exc),
            file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        # Try to log to audit file as last resort
        try:
            with open(DEFAULT_AUDIT_LOG, "a") as f:
                f.write("[{}] FATAL    Unhandled exception: {}\n".format(
                    now_iso(), exc))
                f.write(traceback.format_exc() + "\n")
        except Exception:
            pass
        # Exit 0 even on fatal - the healer must not crash cron/systemd
        sys.exit(0)


if __name__ == "__main__":
    main()
