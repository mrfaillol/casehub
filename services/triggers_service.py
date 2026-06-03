"""
CaseHub - Case Triggers Service
Automation triggers for case status changes.
"""
from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum
import json


class TriggerEvent(str, Enum):
    STATUS_CHANGED = "status_changed"
    CASE_CREATED = "case_created"
    DOCUMENT_UPLOADED = "document_uploaded"
    TASK_COMPLETED = "task_completed"
    DEADLINE_APPROACHING = "deadline_approaching"
    PAYMENT_RECEIVED = "payment_received"


class ActionType(str, Enum):
    CREATE_TASK = "create_task"
    SEND_EMAIL = "send_email"
    UPDATE_STATUS = "update_status"
    ADD_NOTE = "add_note"
    SEND_NOTIFICATION = "send_notification"
    CREATE_REMINDER = "create_reminder"
    WEBHOOK = "webhook"


class TriggersService:
    """Service for managing case automation triggers."""

    # Default triggers for common visa types
    DEFAULT_TRIGGERS = {
        "H-1B": [
            {
                "event": TriggerEvent.STATUS_CHANGED,
                "condition": {"from_status": "intake", "to_status": "document_collection"},
                "action": ActionType.CREATE_TASK,
                "action_config": {
                    "title": "Collect required H-1B documents",
                    "description": "Collect: Passport, Diplomas, Resume, LCA, Job description",
                    "priority": "high"
                }
            },
            {
                "event": TriggerEvent.STATUS_CHANGED,
                "condition": {"from_status": "document_collection", "to_status": "drafting"},
                "action": ActionType.CREATE_TASK,
                "action_config": {
                    "title": "Draft H-1B Petition",
                    "description": "Prepare I-129, support letter, and exhibits"
                }
            },
            {
                "event": TriggerEvent.STATUS_CHANGED,
                "condition": {"to_status": "filed"},
                "action": ActionType.SEND_EMAIL,
                "action_config": {
                    "template": "case_filed_notification",
                    "to": "client"
                }
            }
        ],
        "EB-1A": [
            {
                "event": TriggerEvent.STATUS_CHANGED,
                "condition": {"from_status": "intake", "to_status": "document_collection"},
                "action": ActionType.CREATE_TASK,
                "action_config": {
                    "title": "Collect EB-1A evidence",
                    "description": "Gather evidence for at least 3 criteria",
                    "priority": "high"
                }
            },
            {
                "event": TriggerEvent.STATUS_CHANGED,
                "condition": {"to_status": "rfe"},
                "action": ActionType.CREATE_TASK,
                "action_config": {
                    "title": "Respond to RFE",
                    "description": "Review RFE and prepare response",
                    "priority": "urgent"
                }
            }
        ]
    }

    def get_triggers_for_case(self, db_session, case_id: int) -> List[Dict]:
        """Get all triggers for a specific case."""
        from sqlalchemy import text

        try:
            result = db_session.execute(text("""
                SELECT * FROM case_triggers
                WHERE case_id = :cid AND enabled = true
                ORDER BY created_at
            """), {"cid": case_id})

            return [dict(row._mapping) for row in result.fetchall()]
        except:
            return []

    def get_triggers_by_visa_type(self, visa_type: str) -> List[Dict]:
        """Get default triggers for a visa type."""
        return self.DEFAULT_TRIGGERS.get(visa_type, [])

    def create_trigger(
        self,
        db_session,
        case_id: int,
        event: TriggerEvent,
        condition: Dict,
        action: ActionType,
        action_config: Dict,
        name: str = None,
        user_id: int = None
    ) -> Dict:
        """Create a new trigger for a case."""
        from sqlalchemy import text
        import uuid

        trigger_id = str(uuid.uuid4())[:8]

        try:
            db_session.execute(text("""
                INSERT INTO case_triggers
                (trigger_id, case_id, name, event, condition_config, action, action_config, created_by)
                VALUES (:tid, :cid, :name, :event, :condition, :action, :config, :uid)
            """), {
                "tid": trigger_id,
                "cid": case_id,
                "name": name or f"{event} -> {action}",
                "event": event,
                "condition": json.dumps(condition),
                "action": action,
                "config": json.dumps(action_config),
                "uid": user_id
            })
            db_session.commit()

            return {"success": True, "trigger_id": trigger_id}
        except Exception as e:
            db_session.rollback()
            return {"success": False, "error": str(e)}

    def evaluate_triggers(
        self,
        db_session,
        case_id: int,
        event: TriggerEvent,
        event_data: Dict
    ) -> List[Dict]:
        """Evaluate and execute matching triggers for an event."""
        from sqlalchemy import text

        executed = []

        # Get triggers for this case and event
        try:
            result = db_session.execute(text("""
                SELECT * FROM case_triggers
                WHERE case_id = :cid AND event = :event AND enabled = true
            """), {"cid": case_id, "event": event})

            triggers = result.fetchall()
        except:
            triggers = []

        for trigger in triggers:
            condition = json.loads(trigger.condition_config) if trigger.condition_config else {}

            if self._check_condition(condition, event_data):
                action_config = json.loads(trigger.action_config) if trigger.action_config else {}
                result = self._execute_action(db_session, case_id, trigger.action, action_config, event_data)

                # Log execution
                self._log_trigger_execution(db_session, trigger.id, result)

                executed.append({
                    "trigger_id": trigger.trigger_id,
                    "action": trigger.action,
                    "result": result
                })

        return executed

    def _check_condition(self, condition: Dict, event_data: Dict) -> bool:
        """Check if condition matches event data."""
        if not condition:
            return True

        for key, expected in condition.items():
            actual = event_data.get(key)
            if actual != expected:
                return False

        return True

    def _execute_action(
        self,
        db_session,
        case_id: int,
        action: str,
        config: Dict,
        event_data: Dict
    ) -> Dict:
        """Execute a trigger action."""
        from sqlalchemy import text

        try:
            if action == ActionType.CREATE_TASK:
                db_session.execute(text("""
                    INSERT INTO tasks (case_id, title, description, priority, status)
                    VALUES (:cid, :title, :desc, :priority, 'todo')
                """), {
                    "cid": case_id,
                    "title": config.get("title", "Auto-created task"),
                    "desc": config.get("description", ""),
                    "priority": config.get("priority", "medium")
                })
                db_session.commit()
                return {"success": True, "action": "task_created"}

            elif action == ActionType.ADD_NOTE:
                db_session.execute(text("""
                    INSERT INTO case_notes (case_id, content, note_type)
                    VALUES (:cid, :content, 'system')
                """), {
                    "cid": case_id,
                    "content": config.get("content", f"Trigger executed: {event_data}")
                })
                db_session.commit()
                return {"success": True, "action": "note_added"}

            elif action == ActionType.SEND_NOTIFICATION:
                # Add to alerts
                db_session.execute(text("""
                    INSERT INTO alert_notifications (alert_id, alert_type, title, message, entity_type, entity_id)
                    VALUES (:aid, 'status_change', :title, :msg, 'case', :cid)
                """), {
                    "aid": str(datetime.now().timestamp())[:8],
                    "title": config.get("title", "Case Status Changed"),
                    "msg": config.get("message", f"Case status was updated"),
                    "cid": case_id
                })
                db_session.commit()
                return {"success": True, "action": "notification_sent"}

            elif action == ActionType.CREATE_REMINDER:
                from datetime import timedelta
                days = config.get("days", 7)
                due_date = datetime.now() + timedelta(days=days)

                db_session.execute(text("""
                    INSERT INTO reminders (case_id, title, description, due_date)
                    VALUES (:cid, :title, :desc, :due)
                """), {
                    "cid": case_id,
                    "title": config.get("title", "Reminder"),
                    "desc": config.get("description", ""),
                    "due": due_date
                })
                db_session.commit()
                return {"success": True, "action": "reminder_created"}

            return {"success": False, "error": "Unknown action type"}

        except Exception as e:
            db_session.rollback()
            return {"success": False, "error": str(e)}

    def _log_trigger_execution(self, db_session, trigger_id: int, result: Dict):
        """Log trigger execution."""
        from sqlalchemy import text

        try:
            db_session.execute(text("""
                INSERT INTO trigger_executions (trigger_id, result, executed_at)
                VALUES (:tid, :result, NOW())
            """), {
                "tid": trigger_id,
                "result": json.dumps(result)
            })

            db_session.execute(text("""
                UPDATE case_triggers SET last_executed = NOW(), execution_count = execution_count + 1
                WHERE id = :tid
            """), {"tid": trigger_id})

            db_session.commit()
        except:
            db_session.rollback()

    def get_available_events(self) -> List[Dict]:
        """Get list of available trigger events."""
        return [
            {"value": e.value, "label": e.value.replace("_", " ").title()}
            for e in TriggerEvent
        ]

    def get_available_actions(self) -> List[Dict]:
        """Get list of available trigger actions."""
        return [
            {"value": a.value, "label": a.value.replace("_", " ").title()}
            for a in ActionType
        ]


# SQL for triggers tables
CREATE_TRIGGERS_TABLE = """
CREATE TABLE IF NOT EXISTS case_triggers (
    id SERIAL PRIMARY KEY,
    trigger_id VARCHAR(20) UNIQUE NOT NULL,
    case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE,
    name VARCHAR(200),
    event VARCHAR(50) NOT NULL,
    condition_config JSONB,
    action VARCHAR(50) NOT NULL,
    action_config JSONB,
    enabled BOOLEAN DEFAULT true,
    last_executed TIMESTAMP,
    execution_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_triggers_case ON case_triggers(case_id);
CREATE INDEX IF NOT EXISTS idx_triggers_event ON case_triggers(event);

CREATE TABLE IF NOT EXISTS trigger_executions (
    id SERIAL PRIMARY KEY,
    trigger_id INTEGER REFERENCES case_triggers(id) ON DELETE CASCADE,
    result JSONB,
    executed_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_executions_trigger ON trigger_executions(trigger_id);
"""


# Singleton instance
triggers_service = TriggersService()
