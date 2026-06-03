"""
Sentinela - Incident Database (SQLite)
Persistent memory of health snapshots, incidents, canary results, alerts, and learned patterns.
Uses aiosqlite for async access. WAL mode for concurrent reads.
"""

import aiosqlite
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


class IncidentDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db = None

    async def initialize(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA busy_timeout=5000")
        await self._create_tables()

    async def _create_tables(self):
        await self.db.executescript("""
            CREATE TABLE IF NOT EXISTS health_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT NOT NULL,
                score REAL NOT NULL,
                dimensions TEXT NOT NULL,
                timestamp TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT NOT NULL,
                type TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                severity TEXT NOT NULL,
                details TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                resolved_at TEXT
            );

            CREATE TABLE IF NOT EXISTS canary_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                check_name TEXT NOT NULL,
                passed INTEGER NOT NULL,
                latency_ms REAL,
                error TEXT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS alert_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                severity TEXT NOT NULL,
                message_hash TEXT NOT NULL,
                message TEXT,
                sent_at TEXT NOT NULL DEFAULT (datetime('now')),
                acknowledged INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                fix_action TEXT,
                occurrence_count INTEGER DEFAULT 1,
                success_rate REAL DEFAULT 0.0,
                last_seen TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS healing_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id INTEGER,
                service TEXT NOT NULL,
                action TEXT NOT NULL,
                result TEXT,
                duration_ms REAL,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (incident_id) REFERENCES incidents(id)
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_service_ts ON health_snapshots(service, timestamp);
            CREATE INDEX IF NOT EXISTS idx_incidents_fingerprint ON incidents(fingerprint);
            CREATE INDEX IF NOT EXISTS idx_incidents_service ON incidents(service, created_at);
            CREATE INDEX IF NOT EXISTS idx_canary_check ON canary_results(check_name, timestamp);
            CREATE INDEX IF NOT EXISTS idx_alert_hash ON alert_log(message_hash, sent_at);
            CREATE INDEX IF NOT EXISTS idx_healing_service ON healing_actions(service, timestamp);
        """)
        await self.db.commit()

    @staticmethod
    def make_fingerprint(service: str, error_type: str, symptoms: str) -> str:
        raw = f"{service}:{error_type}:{symptoms}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # --- Health Snapshots ---

    async def save_snapshot(self, service: str, score: float, dimensions: dict):
        await self.db.execute(
            "INSERT INTO health_snapshots (service, score, dimensions) VALUES (?, ?, ?)",
            (service, score, json.dumps(dimensions))
        )
        await self.db.commit()

    async def get_recent_scores(self, service: str, hours: int = 24) -> list:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        cursor = await self.db.execute(
            "SELECT score, dimensions, timestamp FROM health_snapshots "
            "WHERE service = ? AND timestamp > ? ORDER BY timestamp DESC",
            (service, cutoff)
        )
        rows = await cursor.fetchall()
        return [{"score": r["score"], "dimensions": json.loads(r["dimensions"]),
                 "timestamp": r["timestamp"]} for r in rows]

    async def get_latest_scores(self) -> dict:
        cursor = await self.db.execute(
            "SELECT service, score, dimensions, timestamp FROM health_snapshots "
            "WHERE id IN (SELECT MAX(id) FROM health_snapshots GROUP BY service)"
        )
        rows = await cursor.fetchall()
        return {r["service"]: {"score": r["score"],
                               "dimensions": json.loads(r["dimensions"]),
                               "timestamp": r["timestamp"]} for r in rows}

    # --- Incidents ---

    async def create_incident(self, service: str, incident_type: str,
                              severity: str, details: str = None,
                              symptoms: str = "") -> int:
        fingerprint = self.make_fingerprint(service, incident_type, symptoms)
        cursor = await self.db.execute(
            "INSERT INTO incidents (service, type, fingerprint, severity, details) "
            "VALUES (?, ?, ?, ?, ?)",
            (service, incident_type, fingerprint, severity, details)
        )
        await self.db.commit()
        # Update pattern count
        await self.db.execute(
            "INSERT INTO patterns (fingerprint, description, last_seen) "
            "VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(fingerprint) DO UPDATE SET "
            "occurrence_count = occurrence_count + 1, last_seen = datetime('now')",
            (fingerprint, f"{service}:{incident_type}")
        )
        await self.db.commit()
        return cursor.lastrowid

    async def resolve_incident(self, incident_id: int):
        await self.db.execute(
            "UPDATE incidents SET resolved_at = datetime('now') WHERE id = ?",
            (incident_id,)
        )
        await self.db.commit()

    async def get_open_incidents(self, service: str = None) -> list:
        if service:
            cursor = await self.db.execute(
                "SELECT * FROM incidents WHERE resolved_at IS NULL AND service = ? "
                "ORDER BY created_at DESC", (service,)
            )
        else:
            cursor = await self.db.execute(
                "SELECT * FROM incidents WHERE resolved_at IS NULL ORDER BY created_at DESC"
            )
        return [dict(r) for r in await cursor.fetchall()]

    # --- Canary Results ---

    async def save_canary_result(self, check_name: str, passed: bool,
                                 latency_ms: float = None, error: str = None):
        await self.db.execute(
            "INSERT INTO canary_results (check_name, passed, latency_ms, error) "
            "VALUES (?, ?, ?, ?)",
            (check_name, int(passed), latency_ms, error)
        )
        await self.db.commit()

    async def get_canary_failures(self, hours: int = 1) -> list:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        cursor = await self.db.execute(
            "SELECT check_name, COUNT(*) as fail_count FROM canary_results "
            "WHERE passed = 0 AND timestamp > ? GROUP BY check_name",
            (cutoff,)
        )
        return [dict(r) for r in await cursor.fetchall()]

    # --- Alert Log ---

    async def was_alert_sent_recently(self, message_hash: str, window_minutes: int = 30) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()
        cursor = await self.db.execute(
            "SELECT COUNT(*) as cnt FROM alert_log "
            "WHERE message_hash = ? AND sent_at > ?",
            (message_hash, cutoff)
        )
        row = await cursor.fetchone()
        return row["cnt"] > 0

    async def log_alert(self, channel: str, severity: str,
                        message_hash: str, message: str = None):
        await self.db.execute(
            "INSERT INTO alert_log (channel, severity, message_hash, message) "
            "VALUES (?, ?, ?, ?)",
            (channel, severity, message_hash, message)
        )
        await self.db.commit()

    # --- Patterns ---

    async def get_pattern(self, fingerprint: str) -> dict | None:
        cursor = await self.db.execute(
            "SELECT * FROM patterns WHERE fingerprint = ?", (fingerprint,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def update_pattern_fix(self, fingerprint: str, fix_action: str, success: bool):
        pattern = await self.get_pattern(fingerprint)
        if pattern:
            count = pattern["occurrence_count"]
            old_rate = pattern["success_rate"]
            new_rate = ((old_rate * (count - 1)) + (1.0 if success else 0.0)) / count
            await self.db.execute(
                "UPDATE patterns SET fix_action = ?, success_rate = ? WHERE fingerprint = ?",
                (fix_action, new_rate, fingerprint)
            )
            await self.db.commit()

    # --- Healing Actions ---

    async def log_healing_action(self, incident_id: int, service: str,
                                 action: str, result: str, duration_ms: float):
        await self.db.execute(
            "INSERT INTO healing_actions (incident_id, service, action, result, duration_ms) "
            "VALUES (?, ?, ?, ?, ?)",
            (incident_id, service, action, result, duration_ms)
        )
        await self.db.commit()

    async def get_recent_healing_count(self, service: str, hours: int = 1) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        cursor = await self.db.execute(
            "SELECT COUNT(*) as cnt FROM healing_actions "
            "WHERE service = ? AND timestamp > ?",
            (service, cutoff)
        )
        row = await cursor.fetchone()
        return row["cnt"]

    # --- Cleanup ---

    async def cleanup_old_data(self, retention_days: int = 30):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        await self.db.execute("DELETE FROM health_snapshots WHERE timestamp < ?", (cutoff,))
        await self.db.execute("DELETE FROM canary_results WHERE timestamp < ?", (cutoff,))
        await self.db.execute("DELETE FROM alert_log WHERE sent_at < ?", (cutoff,))
        await self.db.execute(
            "DELETE FROM incidents WHERE resolved_at IS NOT NULL AND resolved_at < ?",
            (cutoff,)
        )
        await self.db.commit()

    async def close(self):
        if self.db:
            await self.db.close()
