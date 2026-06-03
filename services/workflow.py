"""
CaseHub - Case Workflow Service
Automated case status transitions and workflow management
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import text


# Define workflow configurations per visa type
WORKFLOW_CONFIGS = {
    "EB-1A": {
        "name": "EB-1A Extraordinary Ability",
        "statuses": ["intake", "document_collection", "petition_drafting", "review", "filed", "rfe", "rfe_response", "approved", "denied", "closed"],
        "transitions": {
            "intake": ["document_collection", "closed"],
            "document_collection": ["petition_drafting", "intake", "closed"],
            "petition_drafting": ["review", "document_collection", "closed"],
            "review": ["filed", "petition_drafting", "closed"],
            "filed": ["rfe", "approved", "denied"],
            "rfe": ["rfe_response"],
            "rfe_response": ["filed", "approved", "denied"],
            "approved": ["closed"],
            "denied": ["closed"]
        },
        "auto_tasks": {
            "intake": [
                {"title": "Initial consultation completed", "type": "consultation"},
                {"title": "Engagement letter signed", "type": "document"},
                {"title": "Retainer payment received", "type": "billing"}
            ],
            "document_collection": [
                {"title": "Collect passport copy", "type": "document"},
                {"title": "Collect diplomas and transcripts", "type": "document"},
                {"title": "Collect employment letters", "type": "document"},
                {"title": "Collect recommendation letters", "type": "document"},
                {"title": "Collect evidence of extraordinary ability", "type": "document"}
            ],
            "petition_drafting": [
                {"title": "Draft I-140 petition letter", "type": "drafting"},
                {"title": "Prepare exhibit list", "type": "drafting"},
                {"title": "Compile supporting evidence", "type": "drafting"}
            ],
            "review": [
                {"title": "Attorney review of petition", "type": "review"},
                {"title": "Client review and approval", "type": "review"}
            ],
            "filed": [
                {"title": "File petition with USCIS", "type": "filing"},
                {"title": "Send filing confirmation to client", "type": "communication"}
            ],
            "rfe": [
                {"title": "Analyze RFE requirements", "type": "review"},
                {"title": "Collect additional evidence", "type": "document"},
                {"title": "Draft RFE response", "type": "drafting"}
            ]
        }
    },
    "EB-1B": {
        "name": "EB-1B Outstanding Researcher",
        "statuses": ["intake", "document_collection", "petition_drafting", "review", "filed", "rfe", "rfe_response", "approved", "denied", "closed"],
        "transitions": {
            "intake": ["document_collection", "closed"],
            "document_collection": ["petition_drafting", "intake", "closed"],
            "petition_drafting": ["review", "document_collection", "closed"],
            "review": ["filed", "petition_drafting", "closed"],
            "filed": ["rfe", "approved", "denied"],
            "rfe": ["rfe_response"],
            "rfe_response": ["filed", "approved", "denied"],
            "approved": ["closed"],
            "denied": ["closed"]
        },
        "auto_tasks": {
            "intake": [
                {"title": "Initial consultation completed", "type": "consultation"},
                {"title": "Engagement letter signed", "type": "document"},
                {"title": "Retainer payment received", "type": "billing"}
            ],
            "document_collection": [
                {"title": "Collect passport copy", "type": "document"},
                {"title": "Collect employer support letter", "type": "document"},
                {"title": "Collect research publications", "type": "document"},
                {"title": "Collect citation evidence", "type": "document"},
                {"title": "Collect peer review evidence", "type": "document"}
            ]
        }
    },
    "H-1B": {
        "name": "H-1B Specialty Occupation",
        "statuses": ["intake", "lca_filing", "document_collection", "petition_drafting", "review", "filed", "rfe", "rfe_response", "approved", "denied", "closed"],
        "transitions": {
            "intake": ["lca_filing", "closed"],
            "lca_filing": ["document_collection", "intake", "closed"],
            "document_collection": ["petition_drafting", "lca_filing", "closed"],
            "petition_drafting": ["review", "document_collection", "closed"],
            "review": ["filed", "petition_drafting", "closed"],
            "filed": ["rfe", "approved", "denied"],
            "rfe": ["rfe_response"],
            "rfe_response": ["filed", "approved", "denied"],
            "approved": ["closed"],
            "denied": ["closed"]
        },
        "auto_tasks": {
            "intake": [
                {"title": "Initial consultation completed", "type": "consultation"},
                {"title": "Engagement letter signed", "type": "document"}
            ],
            "lca_filing": [
                {"title": "Prepare LCA application", "type": "filing"},
                {"title": "File LCA with DOL", "type": "filing"},
                {"title": "Wait for LCA certification", "type": "waiting"}
            ],
            "document_collection": [
                {"title": "Collect passport copy", "type": "document"},
                {"title": "Collect degree certificates", "type": "document"},
                {"title": "Collect employment letter", "type": "document"},
                {"title": "Obtain credential evaluation", "type": "document"}
            ]
        }
    },
    "L-1A": {
        "name": "L-1A Intracompany Manager",
        "statuses": ["intake", "document_collection", "petition_drafting", "review", "filed", "rfe", "rfe_response", "approved", "denied", "closed"],
        "transitions": {
            "intake": ["document_collection", "closed"],
            "document_collection": ["petition_drafting", "intake", "closed"],
            "petition_drafting": ["review", "document_collection", "closed"],
            "review": ["filed", "petition_drafting", "closed"],
            "filed": ["rfe", "approved", "denied"],
            "rfe": ["rfe_response"],
            "rfe_response": ["filed", "approved", "denied"],
            "approved": ["closed"],
            "denied": ["closed"]
        },
        "auto_tasks": {
            "document_collection": [
                {"title": "Collect organizational charts", "type": "document"},
                {"title": "Collect company financials", "type": "document"},
                {"title": "Collect job descriptions", "type": "document"}
            ]
        }
    },
    "O-1A": {
        "name": "O-1A Extraordinary Ability",
        "statuses": ["intake", "consultation_letter", "document_collection", "petition_drafting", "review", "filed", "rfe", "rfe_response", "approved", "denied", "closed"],
        "transitions": {
            "intake": ["consultation_letter", "closed"],
            "consultation_letter": ["document_collection", "intake", "closed"],
            "document_collection": ["petition_drafting", "consultation_letter", "closed"],
            "petition_drafting": ["review", "document_collection", "closed"],
            "review": ["filed", "petition_drafting", "closed"],
            "filed": ["rfe", "approved", "denied"],
            "rfe": ["rfe_response"],
            "rfe_response": ["filed", "approved", "denied"],
            "approved": ["closed"],
            "denied": ["closed"]
        },
        "auto_tasks": {
            "consultation_letter": [
                {"title": "Draft advisory opinion request", "type": "drafting"},
                {"title": "Obtain peer group consultation letter", "type": "document"}
            ]
        }
    },
    "default": {
        "name": "Standard Case",
        "statuses": ["intake", "document_collection", "processing", "review", "filed", "rfe", "approved", "denied", "closed"],
        "transitions": {
            "intake": ["document_collection", "closed"],
            "document_collection": ["processing", "intake", "closed"],
            "processing": ["review", "document_collection", "closed"],
            "review": ["filed", "processing", "closed"],
            "filed": ["rfe", "approved", "denied"],
            "rfe": ["filed", "approved", "denied"],
            "approved": ["closed"],
            "denied": ["closed"]
        },
        "auto_tasks": {}
    }
}


class WorkflowService:
    """Service for managing case workflows and status transitions."""

    def __init__(self, db: Session):
        self.db = db

    def get_workflow_config(self, visa_type: str) -> Dict:
        """Get workflow configuration for a visa type."""
        # Normalize visa type
        visa_type_upper = (visa_type or "").upper().replace("-", "").replace(" ", "")
        
        for key, config in WORKFLOW_CONFIGS.items():
            key_normalized = key.upper().replace("-", "").replace(" ", "")
            if key_normalized == visa_type_upper:
                return config
        
        return WORKFLOW_CONFIGS["default"]

    def get_allowed_transitions(self, visa_type: str, current_status: str) -> List[str]:
        """Get list of allowed next statuses."""
        config = self.get_workflow_config(visa_type)
        transitions = config.get("transitions", {})
        return transitions.get(current_status, [])

    def can_transition(self, visa_type: str, from_status: str, to_status: str) -> bool:
        """Check if a status transition is allowed."""
        allowed = self.get_allowed_transitions(visa_type, from_status)
        return to_status in allowed

    def transition_case(self, case_id: int, new_status: str, user_id: int, notes: str = None) -> Dict[str, Any]:
        """
        Transition a case to a new status with validation and side effects.
        Returns success/error and any tasks created.
        """
        from models import Case, Task
        
        case = self.db.query(Case).filter(Case.id == case_id).first()
        if not case:
            return {"success": False, "error": "Case not found"}

        old_status = case.status
        visa_type = case.visa_type or "default"

        # Validate transition
        if not self.can_transition(visa_type, old_status, new_status):
            allowed = self.get_allowed_transitions(visa_type, old_status)
            return {
                "success": False,
                "error": f"Cannot transition from '{old_status}' to '{new_status}'. Allowed: {allowed}"
            }

        # Perform transition
        case.status = new_status
        case.updated_at = datetime.now()

        # Log the transition
        try:
            self.db.execute(text("""
                INSERT INTO audit_log (action, entity_type, entity_id, user_id, description, details, created_at)
                VALUES ('status_change', 'case', :case_id, :user_id, :description, :details, NOW())
            """), {
                "case_id": case_id,
                "user_id": user_id,
                "description": f"Status changed from '{old_status}' to '{new_status}'",
                "details": f'{{"from": "{old_status}", "to": "{new_status}", "notes": "{notes or ""}"}}'
            })
        except:
            pass

        # Create auto-generated tasks for new status
        tasks_created = []
        config = self.get_workflow_config(visa_type)
        auto_tasks = config.get("auto_tasks", {}).get(new_status, [])
        
        for task_def in auto_tasks:
            # Check if task already exists
            existing = self.db.query(Task).filter(
                Task.case_id == case_id,
                Task.title == task_def["title"],
                Task.status != "completed"
            ).first()
            
            if not existing:
                new_task = Task(
                    case_id=case_id,
                    client_id=case.client_id,
                    title=task_def["title"],
                    type=task_def.get("type", "general"),
                    status="todo",
                    priority="medium",
                    created_at=datetime.now()
                )
                self.db.add(new_task)
                tasks_created.append(task_def["title"])

        self.db.commit()

        return {
            "success": True,
            "from_status": old_status,
            "to_status": new_status,
            "tasks_created": tasks_created
        }

    def get_workflow_progress(self, case_id: int) -> Dict[str, Any]:
        """Get workflow progress for a case."""
        from models import Case, Task
        
        case = self.db.query(Case).filter(Case.id == case_id).first()
        if not case:
            return {"error": "Case not found"}

        config = self.get_workflow_config(case.visa_type or "default")
        statuses = config.get("statuses", [])
        current_index = statuses.index(case.status) if case.status in statuses else 0
        
        # Get task completion stats per status
        status_tasks = {}
        for status in statuses:
            tasks = self.db.query(Task).filter(Task.case_id == case_id).all()
            # This is simplified - in practice you'd track which tasks belong to which status
        
        return {
            "case_id": case_id,
            "visa_type": case.visa_type,
            "current_status": case.status,
            "workflow_name": config.get("name"),
            "statuses": statuses,
            "current_index": current_index,
            "total_steps": len(statuses),
            "progress_percent": round((current_index / (len(statuses) - 1)) * 100) if len(statuses) > 1 else 0,
            "allowed_transitions": self.get_allowed_transitions(case.visa_type, case.status)
        }

    def get_status_history(self, case_id: int) -> List[Dict]:
        """Get status change history for a case."""
        history = self.db.execute(text("""
            SELECT * FROM audit_log 
            WHERE entity_type = 'case' AND entity_id = :case_id AND action = 'status_change'
            ORDER BY created_at DESC
        """), {"case_id": case_id}).fetchall()
        
        return [{
            "id": h.id,
            "description": h.description,
            "details": h.details,
            "created_at": h.created_at.isoformat() if h.created_at else None
        } for h in history]


def get_all_visa_types() -> List[Dict]:
    """Get list of all visa types with their workflows."""
    return [
        {"code": key, "name": config["name"], "statuses": config["statuses"]}
        for key, config in WORKFLOW_CONFIGS.items()
        if key != "default"
    ]
