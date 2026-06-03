"""
Sentinela - Health Scorer
Composite 0-100 health score per service with 6 weighted dimensions.
"""


# Dimension weights (must sum to 100)
DIMENSION_WEIGHTS = {
    "pm2_status": 30,
    "http_health": 20,
    "response_time": 10,
    "canary": 25,
    "resources": 10,
    "stability": 5,
}

# Criticality multipliers for priority services
CRITICALITY = {
    "whatsapp-bot": 1.5,
    "casehub": 1.3,
    "ilc-tools": 1.0,
    "n8n": 0.8,
    "vps-monitor": 0.7,
}

# Thresholds
GREEN = 80
YELLOW = 50
RED = 20


def severity_from_score(score: float) -> str:
    if score >= GREEN:
        return "GREEN"
    elif score >= YELLOW:
        return "YELLOW"
    elif score >= RED:
        return "RED"
    return "CRITICAL"


def score_pm2_status(pm2_data: dict) -> float:
    """Score based on PM2 process status. Returns 0-100."""
    status = pm2_data.get("status", "unknown")
    if status == "online":
        return 100.0
    elif status == "stopping":
        return 50.0
    elif status == "stopped":
        return 10.0
    elif status == "errored":
        return 0.0
    return 0.0


def score_http_health(http_data: dict) -> float:
    """Score based on HTTP health check response."""
    status_code = http_data.get("status_code", 0)
    body_valid = http_data.get("body_valid", False)

    if status_code == 0:
        return 0.0
    if 200 <= status_code < 300:
        return 100.0 if body_valid else 70.0
    if 300 <= status_code < 400:
        return 60.0
    if status_code == 503:
        return 20.0
    if status_code >= 500:
        return 10.0
    if status_code >= 400:
        return 30.0
    return 0.0


def score_response_time(response_ms: float, threshold_ms: float = 2000) -> float:
    """Score based on response time vs threshold."""
    if response_ms <= 0:
        return 0.0
    if response_ms <= threshold_ms * 0.3:
        return 100.0
    if response_ms <= threshold_ms * 0.6:
        return 80.0
    if response_ms <= threshold_ms:
        return 60.0
    if response_ms <= threshold_ms * 2:
        return 30.0
    return 10.0


def score_canary(canary_results: list[dict]) -> float:
    """Score based on canary check results for this service."""
    if not canary_results:
        return 50.0  # no canaries = neutral
    passed = sum(1 for c in canary_results if c.get("passed"))
    return (passed / len(canary_results)) * 100.0


def score_resources(cpu_percent: float, memory_mb: float, memory_limit_mb: float = 300) -> float:
    """Score based on CPU and memory usage."""
    cpu_score = max(0, 100 - cpu_percent)  # 0% CPU = 100 score
    mem_ratio = memory_mb / memory_limit_mb if memory_limit_mb > 0 else 1.0
    if mem_ratio < 0.5:
        mem_score = 100.0
    elif mem_ratio < 0.7:
        mem_score = 80.0
    elif mem_ratio < 0.9:
        mem_score = 50.0
    else:
        mem_score = 20.0
    return (cpu_score + mem_score) / 2.0


def score_stability(restart_count_24h: int) -> float:
    """Score based on number of restarts in last 24 hours."""
    if restart_count_24h == 0:
        return 100.0
    elif restart_count_24h == 1:
        return 80.0
    elif restart_count_24h <= 3:
        return 50.0
    elif restart_count_24h <= 5:
        return 20.0
    return 0.0


def compute_health_score(service: str, signals: dict) -> tuple[float, dict]:
    """
    Compute composite health score for a service.

    Args:
        service: Service name
        signals: Dict with keys matching dimension names, each containing
                 the data needed by that dimension's scorer.

    Returns:
        (score, dimensions_dict) where score is 0-100 and dimensions_dict
        has individual dimension scores.
    """
    dimensions = {}

    # PM2 status
    dimensions["pm2_status"] = score_pm2_status(signals.get("pm2", {}))

    # HTTP health
    dimensions["http_health"] = score_http_health(signals.get("http", {}))

    # Response time
    rt = signals.get("response_time_ms", 0)
    dimensions["response_time"] = score_response_time(rt)

    # Canary
    dimensions["canary"] = score_canary(signals.get("canaries", []))

    # Resources
    res = signals.get("resources", {})
    dimensions["resources"] = score_resources(
        res.get("cpu_percent", 0),
        res.get("memory_mb", 0),
        res.get("memory_limit_mb", 300)
    )

    # Stability
    dimensions["stability"] = score_stability(signals.get("restart_count_24h", 0))

    # Weighted sum
    total = 0.0
    for dim, weight in DIMENSION_WEIGHTS.items():
        total += dimensions[dim] * (weight / 100.0)

    # Apply criticality multiplier for alerting priority
    # (score itself stays 0-100, criticality affects alert routing)
    score = max(0.0, min(100.0, total))

    return score, dimensions


def get_criticality(service: str) -> float:
    return CRITICALITY.get(service, 1.0)
