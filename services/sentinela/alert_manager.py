"""
Sentinela - Alert Manager
Consolidated alerting with deduplication, severity-based routing,
and escalation. Uses WhatsApp + email channels with fallback.
"""
import os

import asyncio
import hashlib
import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

import aiohttp

logger = logging.getLogger("sentinela.alerts")


class AlertManager:
    def __init__(self, config: dict, incident_db):
        self.config = config
        self.db = incident_db
        alerts_cfg = config.get("alerts", {})
        self.whatsapp_api = alerts_cfg.get("whatsapp_api", "http://127.0.0.1:3001/api/send")
        self.admin_phone = alerts_cfg.get("whatsapp_admin_phone", "")
        self.email_from = alerts_cfg.get("email_from", os.getenv("ORG_EMAIL", "info@casehub.app"))
        self.dedup_window = alerts_cfg.get("dedup_window_minutes", 30)
        self._session = None
        # Buffer for RED alerts (2min delay for consolidation)
        self._red_buffer = []
        self._red_flush_task = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    @staticmethod
    def _hash_message(message: str) -> str:
        return hashlib.md5(message.encode()).hexdigest()[:12]

    async def alert(self, severity: str, message: str, service: str = ""):
        """
        Route alert based on severity:
        - CRITICAL: WhatsApp immediate + email
        - RED: WhatsApp with 2min consolidation delay + email
        - YELLOW: email only (hourly digest)
        - GREEN: log only
        """
        msg_hash = self._hash_message(f"{severity}:{service}:{message}")

        # Check dedup
        if await self.db.was_alert_sent_recently(msg_hash, self.dedup_window):
            logger.debug(f"Alert deduplicated: {message[:50]}")
            return

        # Per-service throttle: max 5 alerts per service per hour
        if service:
            import time
            if not hasattr(self, "_service_alert_times"):
                self._service_alert_times = {}
            now = time.time()
            times = self._service_alert_times.get(service, [])
            times = [t for t in times if now - t < 3600]  # last hour
            if len(times) >= 5:
                logger.warning(f"Throttled: {service} has {len(times)} alerts in last hour")
                return
            times.append(now)
            self._service_alert_times[service] = times

        full_msg = f"[{severity}] {service}: {message}" if service else f"[{severity}] {message}"

        if severity == "CRITICAL":
            await self._send_whatsapp(full_msg)
            await self._send_email(f"CRITICAL: {service}", full_msg)
            await self.db.log_alert("whatsapp+email", severity, msg_hash, full_msg)

        elif severity == "RED":
            self._red_buffer.append(full_msg)
            if self._red_flush_task is None or self._red_flush_task.done():
                self._red_flush_task = asyncio.create_task(self._flush_red_buffer())
            await self.db.log_alert("buffered", severity, msg_hash, full_msg)

        elif severity == "YELLOW":
            await self._send_email(f"Warning: {service}", full_msg)
            await self.db.log_alert("email", severity, msg_hash, full_msg)

        else:  # GREEN
            logger.info(f"GREEN alert (log only): {full_msg}")

    async def _flush_red_buffer(self):
        """Wait 2 minutes then send consolidated RED alerts."""
        await asyncio.sleep(120)
        if not self._red_buffer:
            return
        consolidated = "\n---\n".join(self._red_buffer)
        count = len(self._red_buffer)
        self._red_buffer = []

        header = f"[RED] {count} alert(s) in last 2 minutes:"
        full = f"{header}\n\n{consolidated}"
        await self._send_whatsapp(full)
        await self._send_email(f"RED Alert: {count} issues", full)

    async def _send_whatsapp(self, message: str):
        """Send alert via WhatsApp Bot API."""
        if not self.admin_phone:
            logger.warning("No admin phone configured for WhatsApp alerts")
            return
        try:
            session = await self._get_session()
            payload = {"phone": self.admin_phone, "message": message}
            async with session.post(self.whatsapp_api, json=payload) as resp:
                if resp.status == 200:
                    logger.info(f"WhatsApp alert sent ({len(message)} chars)")
                else:
                    body = await resp.text()
                    logger.error(f"WhatsApp send failed: HTTP {resp.status} - {body[:200]}")
                    # Fallback to email
                    await self._send_email("WhatsApp Alert Fallback", message)
        except Exception as e:
            logger.error(f"WhatsApp send error: {e}")
            await self._send_email("WhatsApp Alert Fallback", message)

    async def _send_email(self, subject: str, body: str):
        """Send alert via SMTP email. Runs in executor to not block async loop."""
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._send_email_sync, subject, body
            )
        except Exception as e:
            logger.error(f"Email send failed: {e}")

    def _send_email_sync(self, subject: str, body: str):
        """Synchronous email send."""
        gmail_user = self.email_from
        gmail_pass = self.config.get("smtp_app_password", "")
        if not gmail_pass:
            logger.warning("No SMTP password configured - email alert skipped")
            return

        msg = MIMEText(body)
        msg["Subject"] = f"Sentinela VPS: {subject}"
        msg["From"] = f"Sentinela <{gmail_user}>"
        msg["To"] = gmail_user  # Send to self (info@casehub.app)

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(gmail_user, gmail_pass)
                server.send_message(msg)
                logger.info(f"Email alert sent: {subject}")
        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP auth failed - check app password")
        except Exception as e:
            logger.error(f"SMTP error: {e}")

    async def send_daily_digest(self, scores: dict, open_incidents: list,
                                canary_failures: list):
        """Send daily summary digest."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"Sentinela Daily Digest - {now}", "=" * 40, ""]

        # Health scores
        lines.append("HEALTH SCORES:")
        for service, data in sorted(scores.items()):
            score = data.get("score", 0)
            status = "OK" if score >= 80 else "WARN" if score >= 50 else "FAIL"
            lines.append(f"  {service}: {score:.0f}/100 [{status}]")

        # Open incidents
        if open_incidents:
            lines.append(f"\nOPEN INCIDENTS ({len(open_incidents)}):")
            for inc in open_incidents[:10]:
                lines.append(f"  - [{inc.get('severity')}] {inc.get('service')}: "
                             f"{inc.get('type')} (since {inc.get('created_at', '?')})")

        # Canary failures
        if canary_failures:
            lines.append(f"\nCANARY FAILURES ({len(canary_failures)}):")
            for cf in canary_failures:
                lines.append(f"  - {cf.get('check_name')}: "
                             f"{cf.get('fail_count')} failures in last hour")

        if not open_incidents and not canary_failures:
            lines.append("\nAll systems operational.")

        digest = "\n".join(lines)

        # Send via both channels
        await self._send_whatsapp(digest)
        await self._send_email("Daily Digest", digest)
