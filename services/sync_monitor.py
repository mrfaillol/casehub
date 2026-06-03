"""
CaseHub - Email Sync Monitor
Monitors email sync health and alerts if issues are detected
"""
import os
import logging
from datetime import datetime, timedelta
from sqlalchemy import text
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

# Thresholds
MAX_SYNC_AGE_MINUTES = 10  # Alert if no sync in 10 minutes
MAX_ALLOWED_ERRORS = 3     # Alert after 3 consecutive errors


class SyncMonitor:
    """Monitors email sync health"""
    
    def __init__(self, db):
        self.db = db
        self._consecutive_errors = 0
    
    def check_sync_health(self) -> Tuple[bool, str, Dict]:
        """
        Check if email sync is healthy.
        
        Returns:
            Tuple of (is_healthy, status_message, details)
        """
        details = {
            "last_sync": None,
            "last_error": None,
            "minutes_since_sync": None,
            "total_emails": 0,
            "recent_emails_24h": 0,
            "health_score": 100
        }
        
        try:
            # Get account status
            result = self.db.execute(text("""
                SELECT last_sync_at, last_error 
                FROM email_accounts WHERE id = 1
            """)).fetchone()
            
            if not result:
                return (False, "No email account configured", details)
            
            details["last_sync"] = str(result.last_sync_at) if result.last_sync_at else None
            details["last_error"] = result.last_error
            
            # Check last sync time
            if result.last_sync_at:
                minutes_ago = (datetime.utcnow() - result.last_sync_at).total_seconds() / 60
                details["minutes_since_sync"] = round(minutes_ago, 1)
                
                if minutes_ago > MAX_SYNC_AGE_MINUTES:
                    details["health_score"] -= 30
            else:
                details["health_score"] -= 50
            
            # Check for errors
            if result.last_error:
                details["health_score"] -= 40
                self._consecutive_errors += 1
            else:
                self._consecutive_errors = 0
            
            # Get email counts
            count_result = self.db.execute(text("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours') as recent
                FROM email_messages
            """)).fetchone()
            
            details["total_emails"] = count_result.total
            details["recent_emails_24h"] = count_result.recent
            
            # Determine health status
            is_healthy = details["health_score"] >= 70 and not result.last_error
            
            if is_healthy:
                status = f"Healthy - Last sync {details['minutes_since_sync']:.0f}min ago, {details['recent_emails_24h']} emails in 24h"
            else:
                issues = []
                if result.last_error:
                    issues.append(f"Error: {result.last_error[:100]}")
                if details["minutes_since_sync"] and details["minutes_since_sync"] > MAX_SYNC_AGE_MINUTES:
                    issues.append(f"No sync in {details['minutes_since_sync']:.0f} minutes")
                status = "UNHEALTHY - " + "; ".join(issues)
            
            return (is_healthy, status, details)
            
        except Exception as e:
            logger.error(f"Error checking sync health: {e}")
            return (False, f"Monitor error: {str(e)}", details)
    
    def should_trigger_manual_sync(self) -> Tuple[bool, str]:
        """
        AI-like decision: Should we trigger a manual sync?
        
        Returns:
            Tuple of (should_sync, reason)
        """
        is_healthy, status, details = self.check_sync_health()
        
        # Decision logic
        reasons_to_sync = []
        
        # 1. If there's an error, try to recover
        if details["last_error"]:
            reasons_to_sync.append("Error detected - attempting recovery")
        
        # 2. If no sync in too long
        if details["minutes_since_sync"] and details["minutes_since_sync"] > MAX_SYNC_AGE_MINUTES:
            reasons_to_sync.append(f"No sync in {details['minutes_since_sync']:.0f} minutes")
        
        # 3. If no recent emails (might indicate problem)
        if details["recent_emails_24h"] == 0 and details["total_emails"] > 0:
            reasons_to_sync.append("No emails received in 24h - unusual")
        
        if reasons_to_sync:
            return (True, "; ".join(reasons_to_sync))
        
        return (False, "System healthy - no action needed")
    
    def auto_recover(self) -> Dict:
        """
        Attempt automatic recovery if issues detected.
        
        Returns:
            Dict with recovery results
        """
        from routes.emails import sync_emails_from_account
        
        should_sync, reason = self.should_trigger_manual_sync()
        
        result = {
            "action_taken": False,
            "reason": reason,
            "success": False,
            "message": ""
        }
        
        if should_sync:
            result["action_taken"] = True
            logger.info(f"Auto-recovery triggered: {reason}")
            
            try:
                # Clear any existing error first
                self.db.execute(text("UPDATE email_accounts SET last_error = NULL WHERE id = 1"))
                self.db.commit()
                
                # Trigger sync
                sync_emails_from_account(1, "INBOX", 100)
                
                # Check if it worked
                check_result = self.db.execute(text(
                    "SELECT last_error FROM email_accounts WHERE id = 1"
                )).fetchone()
                
                if check_result and not check_result.last_error:
                    result["success"] = True
                    result["message"] = "Recovery successful - sync completed without errors"
                else:
                    result["message"] = f"Recovery attempted but error persists: {check_result.last_error if check_result else 'unknown'}"
                    
            except Exception as e:
                result["message"] = f"Recovery failed: {str(e)}"
                logger.error(f"Auto-recovery failed: {e}")
        else:
            result["message"] = "No recovery needed"
        
        return result


def get_sync_status(db) -> Dict:
    """Quick status check for API endpoint"""
    monitor = SyncMonitor(db)
    is_healthy, status, details = monitor.check_sync_health()
    return {
        "healthy": is_healthy,
        "status": status,
        "details": details
    }


def check_and_recover(db) -> Dict:
    """Check health and auto-recover if needed"""
    monitor = SyncMonitor(db)
    return monitor.auto_recover()
