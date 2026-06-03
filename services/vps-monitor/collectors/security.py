"""
Security Status Collector
Checks all security layers implemented on the VPS
"""
import os
import subprocess
import re
from datetime import datetime
from typing import Dict, Any
from pathlib import Path


class SecurityCollector:
    """Collects security status from all hardening layers"""

    def collect(self) -> Dict[str, Any]:
        """Collect all security checks"""
        checks = {
            "ufw": self._check_ufw(),
            "fail2ban": self._check_fail2ban(),
            "ssh": self._check_ssh(),
            "nginx_headers": self._check_nginx_headers(),
            "php": self._check_php(),
            "tls": self._check_tls(),
            "service_binding": self._check_binding(),
            "wordpress": self._check_wordpress(),
            "kernel": self._check_kernel(),
            "backups": self._check_backups(),
            "malware_tools": self._check_malware_tools(),
            "auditd": self._check_auditd(),
        }

        # Calculate score
        passed = sum(1 for c in checks.values() if c.get("status") == "ok")
        total = len(checks)
        score = round(passed / total * 100) if total > 0 else 0

        return {
            "timestamp": datetime.now().isoformat(),
            "score": score,
            "passed": passed,
            "total": total,
            "checks": checks,
        }

    def get_score(self) -> Dict[str, Any]:
        """Get just the security score"""
        data = self.collect()
        return {
            "score": data["score"],
            "passed": data["passed"],
            "total": data["total"],
            "timestamp": data["timestamp"],
        }

    def _run(self, cmd: str) -> str:
        """Run a shell command and return output"""
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def _check_ufw(self) -> Dict[str, Any]:
        output = self._run("ufw status")
        active = "Status: active" in output
        rules = [l.strip() for l in output.split("\n") if "ALLOW" in l or "LIMIT" in l]
        return {
            "status": "ok" if active else "fail",
            "label": "Firewall (UFW)",
            "active": active,
            "rules_count": len(rules),
            "rules": rules[:10],
        }

    def _check_fail2ban(self) -> Dict[str, Any]:
        output = self._run("fail2ban-client status 2>/dev/null")
        match = re.search(r"Number of jail:\s+(\d+)", output)
        jails_count = int(match.group(1)) if match else 0
        match2 = re.search(r"Jail list:\s+(.*)", output)
        jails = match2.group(1).split(", ") if match2 else []

        banned = 0
        for jail in jails[:7]:
            jail_out = self._run(f"fail2ban-client status {jail.strip()} 2>/dev/null")
            m = re.search(r"Currently banned:\s+(\d+)", jail_out)
            if m:
                banned += int(m.group(1))

        return {
            "status": "ok" if jails_count >= 5 else "warn" if jails_count > 0 else "fail",
            "label": "Fail2Ban",
            "jails_count": jails_count,
            "jails": jails,
            "total_banned": banned,
        }

    def _check_ssh(self) -> Dict[str, Any]:
        config = self._run("grep -E '^PermitRootLogin|^PasswordAuthentication|^MaxAuthTries' /etc/ssh/sshd_config")
        permit_root = "prohibit-password" in config or "no" in config.split("PermitRootLogin")[-1].split("\n")[0] if "PermitRootLogin" in config else False
        pass_auth = "no" in config.split("PasswordAuthentication")[-1].split("\n")[0] if "PasswordAuthentication" in config else False
        ok = permit_root and pass_auth
        return {
            "status": "ok" if ok else "fail",
            "label": "SSH Hardening",
            "permit_root_login": "prohibit-password" if permit_root else "INSECURE",
            "password_auth": "disabled" if pass_auth else "ENABLED",
        }

    def _check_nginx_headers(self) -> Dict[str, Any]:
        output = self._run("curl -sI https://casehub.app 2>/dev/null | grep -iE 'x-frame|x-content|strict-transport|referrer-policy|permissions-policy'")
        headers_found = len(output.strip().split("\n")) if output.strip() else 0
        return {
            "status": "ok" if headers_found >= 4 else "warn" if headers_found > 0 else "fail",
            "label": "Nginx Security Headers",
            "headers_found": headers_found,
            "expected": 5,
        }

    def _check_php(self) -> Dict[str, Any]:
        expose = self._run("grep '^expose_php' /etc/php/8.3/fpm/php.ini 2>/dev/null")
        disable = self._run("grep '^disable_functions' /etc/php/8.3/fpm/php.ini 2>/dev/null")
        expose_off = "Off" in expose
        has_disable = len(disable.split("=")[-1].strip()) > 10 if "=" in disable else False
        return {
            "status": "ok" if expose_off and has_disable else "warn",
            "label": "PHP Hardening",
            "expose_php": "Off" if expose_off else "On",
            "disable_functions": "configured" if has_disable else "EMPTY",
        }

    def _check_tls(self) -> Dict[str, Any]:
        output = self._run("grep 'ssl_protocols' /etc/nginx/nginx.conf 2>/dev/null")
        has_old = "TLSv1 " in output or "TLSv1.1" in output
        has_modern = "TLSv1.2" in output or "TLSv1.3" in output
        return {
            "status": "ok" if has_modern and not has_old else "fail",
            "label": "TLS Configuration",
            "protocols": output.strip().split("ssl_protocols")[-1].strip().rstrip(";") if output else "unknown",
            "legacy_disabled": not has_old,
        }

    def _check_binding(self) -> Dict[str, Any]:
        output = self._run("ss -tlnp | grep -E '8000|8001|8003|3001|8010'")
        lines = output.strip().split("\n") if output.strip() else []
        bound_localhost = sum(1 for l in lines if "127.0.0.1" in l)
        bound_wildcard = sum(1 for l in lines if "0.0.0.0" in l and "127.0.0.1" not in l)
        return {
            "status": "ok" if bound_wildcard == 0 else "warn",
            "label": "Service Binding",
            "localhost": bound_localhost,
            "wildcard": bound_wildcard,
        }

    def _check_wordpress(self) -> Dict[str, Any]:
        config = self._run("grep -E 'DISALLOW_FILE_EDIT|FORCE_SSL_ADMIN|DISABLE_WP_CRON' /opt/casehub/wp-config.php 2>/dev/null")
        constants = len(config.strip().split("\n")) if config.strip() else 0
        readme = Path(os.getenv("APP_BASE_PATH", "/opt/casehub") + "/readme.html").exists()
        return {
            "status": "ok" if constants >= 3 and not readme else "warn",
            "label": "WordPress Hardening",
            "security_constants": constants,
            "readme_removed": not readme,
        }

    def _check_kernel(self) -> Dict[str, Any]:
        exists = Path("/etc/sysctl.d/99-security.conf").exists()
        syncookies = self._run("sysctl -n net.ipv4.tcp_syncookies 2>/dev/null")
        aslr = self._run("sysctl -n kernel.randomize_va_space 2>/dev/null")
        return {
            "status": "ok" if exists and syncookies == "1" else "warn",
            "label": "Kernel Hardening",
            "sysctl_file": exists,
            "tcp_syncookies": syncookies == "1",
            "aslr": aslr == "2",
        }

    def _check_backups(self) -> Dict[str, Any]:
        cron = self._run("crontab -l 2>/dev/null | grep backup.sh")
        has_cron = bool(cron.strip())
        latest = self._run("ls -t /root/backups/mariadb_all_*.sql.gz 2>/dev/null | head -1")
        return {
            "status": "ok" if has_cron and latest else "warn" if has_cron else "fail",
            "label": "Automated Backups",
            "cron_active": has_cron,
            "latest_backup": latest.split("/")[-1] if latest else None,
        }

    def _check_malware_tools(self) -> Dict[str, Any]:
        rkhunter = bool(self._run("which rkhunter 2>/dev/null"))
        chkrootkit = bool(self._run("which chkrootkit 2>/dev/null"))
        clamav = bool(self._run("which clamscan 2>/dev/null"))
        return {
            "status": "ok" if rkhunter and chkrootkit and clamav else "warn",
            "label": "Malware Scanning",
            "rkhunter": rkhunter,
            "chkrootkit": chkrootkit,
            "clamav": clamav,
        }

    def _check_auditd(self) -> Dict[str, Any]:
        active = self._run("systemctl is-active auditd 2>/dev/null") == "active"
        rules = self._run("auditctl -l 2>/dev/null | wc -l")
        rules_count = int(rules) if rules.isdigit() else 0
        return {
            "status": "ok" if active and rules_count > 0 else "warn" if active else "fail",
            "label": "Audit Daemon",
            "active": active,
            "rules_count": rules_count,
        }


# Singleton
security_collector = SecurityCollector()
