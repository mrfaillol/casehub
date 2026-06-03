"""
CaseHub - Deadline Calculator Service
Calculate processing times and deadlines based on visa type
"""
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from models.tenant import tenant_query
from sqlalchemy import text


# Processing time estimates per visa type (in days)
# Source: USCIS processing times (estimates, may vary)
PROCESSING_TIMES = {
    "EB-1A": {
        "name": "EB-1A Extraordinary Ability",
        "premium_available": True,
        "regular_min": 180,
        "regular_max": 365,
        "premium": 45,
        "stages": {
            "document_collection": {"min": 30, "max": 90, "name": "Document Collection"},
            "petition_drafting": {"min": 14, "max": 45, "name": "Petition Drafting"},
            "attorney_review": {"min": 7, "max": 14, "name": "Attorney Review"},
            "client_review": {"min": 3, "max": 7, "name": "Client Review"},
            "uscis_processing": {"min": 180, "max": 365, "name": "USCIS Processing"},
            "rfe_response": {"min": 30, "max": 87, "name": "RFE Response (if applicable)"}
        },
        "rfe_deadline_days": 87,
        "appeal_deadline_days": 30
    },
    "EB-1B": {
        "name": "EB-1B Outstanding Researcher",
        "premium_available": True,
        "regular_min": 180,
        "regular_max": 365,
        "premium": 45,
        "stages": {
            "document_collection": {"min": 30, "max": 90, "name": "Document Collection"},
            "petition_drafting": {"min": 14, "max": 45, "name": "Petition Drafting"},
            "uscis_processing": {"min": 180, "max": 365, "name": "USCIS Processing"}
        },
        "rfe_deadline_days": 87,
        "appeal_deadline_days": 30
    },
    "EB-2 NIW": {
        "name": "EB-2 National Interest Waiver",
        "premium_available": True,
        "regular_min": 365,
        "regular_max": 730,
        "premium": 45,
        "stages": {
            "document_collection": {"min": 45, "max": 120, "name": "Document Collection"},
            "petition_drafting": {"min": 21, "max": 60, "name": "Petition Drafting"},
            "uscis_processing": {"min": 365, "max": 730, "name": "USCIS Processing"}
        },
        "rfe_deadline_days": 87,
        "appeal_deadline_days": 30
    },
    "H-1B": {
        "name": "H-1B Specialty Occupation",
        "premium_available": True,
        "regular_min": 90,
        "regular_max": 180,
        "premium": 15,
        "stages": {
            "lca_filing": {"min": 7, "max": 14, "name": "LCA Filing"},
            "document_collection": {"min": 14, "max": 30, "name": "Document Collection"},
            "petition_preparation": {"min": 7, "max": 21, "name": "Petition Preparation"},
            "uscis_processing": {"min": 90, "max": 180, "name": "USCIS Processing"}
        },
        "rfe_deadline_days": 60,
        "appeal_deadline_days": 30,
        "cap_deadline": "March 31",  # Registration deadline
        "cap_season": True
    },
    "L-1A": {
        "name": "L-1A Intracompany Manager",
        "premium_available": True,
        "regular_min": 60,
        "regular_max": 180,
        "premium": 15,
        "stages": {
            "document_collection": {"min": 21, "max": 60, "name": "Document Collection"},
            "petition_preparation": {"min": 14, "max": 30, "name": "Petition Preparation"},
            "uscis_processing": {"min": 60, "max": 180, "name": "USCIS Processing"}
        },
        "rfe_deadline_days": 60,
        "appeal_deadline_days": 30
    },
    "O-1A": {
        "name": "O-1A Extraordinary Ability",
        "premium_available": True,
        "regular_min": 60,
        "regular_max": 120,
        "premium": 15,
        "stages": {
            "consultation_letter": {"min": 14, "max": 30, "name": "Peer Consultation"},
            "document_collection": {"min": 21, "max": 45, "name": "Document Collection"},
            "petition_drafting": {"min": 14, "max": 30, "name": "Petition Drafting"},
            "uscis_processing": {"min": 60, "max": 120, "name": "USCIS Processing"}
        },
        "rfe_deadline_days": 60,
        "appeal_deadline_days": 30
    },
    "I-485": {
        "name": "Adjustment of Status",
        "premium_available": False,
        "regular_min": 365,
        "regular_max": 730,
        "stages": {
            "document_collection": {"min": 30, "max": 60, "name": "Document Collection"},
            "medical_exam": {"min": 7, "max": 30, "name": "Medical Exam"},
            "filing": {"min": 7, "max": 14, "name": "Filing"},
            "biometrics": {"min": 30, "max": 90, "name": "Biometrics Appointment"},
            "interview": {"min": 180, "max": 365, "name": "Interview Scheduling"},
            "uscis_processing": {"min": 365, "max": 730, "name": "USCIS Processing"}
        },
        "rfe_deadline_days": 87,
        "appeal_deadline_days": 30
    },
    "default": {
        "name": "Standard Processing",
        "premium_available": False,
        "regular_min": 90,
        "regular_max": 365,
        "stages": {
            "document_collection": {"min": 30, "max": 60, "name": "Document Collection"},
            "processing": {"min": 60, "max": 300, "name": "Processing"}
        },
        "rfe_deadline_days": 87,
        "appeal_deadline_days": 30
    }
}


class DeadlineCalculator:
    """Calculate case deadlines and processing times."""

    def __init__(self, db: Session, org_id: int = None):
        self.db = db
        self.org_id = org_id

    def get_visa_config(self, visa_type: str) -> Dict:
        """Get configuration for a visa type."""
        visa_type_upper = (visa_type or "").upper().replace("-", " ").replace("_", " ")
        
        for key, config in PROCESSING_TIMES.items():
            key_normalized = key.upper().replace("-", " ").replace("_", " ")
            if key_normalized == visa_type_upper or key_normalized in visa_type_upper:
                return config
        
        return PROCESSING_TIMES["default"]

    def calculate_deadlines(self, case_id: int) -> Dict[str, Any]:
        """Calculate all relevant deadlines for a case."""
        from models import Case
        
        case = tenant_query(self.db, Case, self.org_id).filter(Case.id == case_id).first()
        if not case:
            return {"error": "Case not found"}

        config = self.get_visa_config(case.visa_type or "default")
        today = date.today()
        
        deadlines = {
            "case_id": case_id,
            "visa_type": case.visa_type,
            "config_name": config["name"],
            "filing_date": case.filing_date.isoformat() if case.filing_date else None,
            "deadlines": [],
            "estimates": {}
        }

        # Calculate estimates based on current status
        if case.filing_date:
            filing_date = case.filing_date if isinstance(case.filing_date, date) else case.filing_date.date()
            
            # Estimated approval date
            est_approval_min = filing_date + timedelta(days=config["regular_min"])
            est_approval_max = filing_date + timedelta(days=config["regular_max"])
            
            deadlines["estimates"]["approval_min"] = est_approval_min.isoformat()
            deadlines["estimates"]["approval_max"] = est_approval_max.isoformat()
            
            # Premium processing estimate if available
            if config.get("premium_available"):
                est_premium = filing_date + timedelta(days=config.get("premium", 15))
                deadlines["estimates"]["premium_approval"] = est_premium.isoformat()
                deadlines["premium_available"] = True
            
            # Days since filing
            days_since_filing = (today - filing_date).days
            deadlines["days_since_filing"] = days_since_filing
            deadlines["processing_progress"] = min(100, round(days_since_filing / config["regular_min"] * 100))

        # Check for RFE deadline
        if case.status == "rfe" and case.rfe_date:
            rfe_date = case.rfe_date if isinstance(case.rfe_date, date) else case.rfe_date.date()
            rfe_deadline = rfe_date + timedelta(days=config.get("rfe_deadline_days", 87))
            days_until_rfe = (rfe_deadline - today).days
            
            deadlines["deadlines"].append({
                "type": "rfe_response",
                "name": "RFE Response Deadline",
                "date": rfe_deadline.isoformat(),
                "days_remaining": days_until_rfe,
                "urgent": days_until_rfe <= 14,
                "critical": days_until_rfe <= 7
            })

        # Document expiration deadlines
        try:
            docs = self.db.execute(text("""
                SELECT id, name, expiration_date FROM documents 
                WHERE case_id = :case_id AND expiration_date IS NOT NULL
                ORDER BY expiration_date
            """), {"case_id": case_id}).fetchall()
            
            for doc in docs:
                if doc.expiration_date:
                    exp_date = doc.expiration_date if isinstance(doc.expiration_date, date) else doc.expiration_date.date()
                    days_until = (exp_date - today).days
                    
                    if days_until <= 90:  # Only show if expiring within 90 days
                        deadlines["deadlines"].append({
                            "type": "document_expiration",
                            "name": f"{doc.name} expires",
                            "date": exp_date.isoformat(),
                            "days_remaining": days_until,
                            "urgent": days_until <= 30,
                            "critical": days_until <= 14
                        })
        except Exception:
            self.db.rollback()
            pass

        # Task deadlines
        try:
            tasks = self.db.execute(text("""
                SELECT id, title, deadline FROM tasks 
                WHERE case_id = :case_id AND deadline IS NOT NULL AND status != 'completed'
                ORDER BY deadline
            """), {"case_id": case_id}).fetchall()
            
            for task in tasks:
                if task.deadline:
                    task_date = task.deadline if isinstance(task.deadline, date) else task.deadline.date()
                    days_until = (task_date - today).days
                    
                    deadlines["deadlines"].append({
                        "type": "task",
                        "name": task.title,
                        "date": task_date.isoformat(),
                        "days_remaining": days_until,
                        "urgent": days_until <= 7,
                        "critical": days_until <= 3
                    })
        except Exception:
            self.db.rollback()
            pass

        # Sort by date
        deadlines["deadlines"].sort(key=lambda x: x["date"])

        return deadlines

    def get_stage_estimates(self, visa_type: str, current_stage: str = None) -> List[Dict]:
        """Get time estimates for each stage of a visa type."""
        config = self.get_visa_config(visa_type)
        stages = config.get("stages", {})
        
        result = []
        cumulative_min = 0
        cumulative_max = 0
        
        for stage_key, stage_info in stages.items():
            cumulative_min += stage_info["min"]
            cumulative_max += stage_info["max"]
            
            result.append({
                "key": stage_key,
                "name": stage_info["name"],
                "min_days": stage_info["min"],
                "max_days": stage_info["max"],
                "cumulative_min": cumulative_min,
                "cumulative_max": cumulative_max,
                "is_current": stage_key == current_stage
            })
        
        return result

    def get_upcoming_deadlines(self, days: int = 30) -> List[Dict]:
        """Get all upcoming deadlines across all cases."""
        from models import Case, Task, Document
        
        today = date.today()
        deadline_date = today + timedelta(days=days)
        
        deadlines = []
        
        # RFE deadlines
        try:
            rfe_cases = self.db.execute(text("""
                SELECT c.id, c.case_number, c.case_name, c.rfe_date, c.visa_type, cl.first_name, cl.last_name
                FROM cases c
                LEFT JOIN clients cl ON c.client_id = cl.id
                WHERE c.status = 'rfe' AND c.rfe_date IS NOT NULL
            """)).fetchall()
            
            for case in rfe_cases:
                config = self.get_visa_config(case.visa_type)
                rfe_date = case.rfe_date if isinstance(case.rfe_date, date) else case.rfe_date.date()
                rfe_deadline = rfe_date + timedelta(days=config.get("rfe_deadline_days", 87))
                
                if rfe_deadline <= deadline_date:
                    days_remaining = (rfe_deadline - today).days
                    deadlines.append({
                        "type": "rfe_response",
                        "case_id": case.id,
                        "case_name": case.case_name or case.case_number,
                        "client_name": f"{case.first_name} {case.last_name}",
                        "deadline": rfe_deadline.isoformat(),
                        "days_remaining": days_remaining,
                        "urgent": days_remaining <= 14,
                        "critical": days_remaining <= 7
                    })
        except Exception:
            self.db.rollback()
            pass

        # Task deadlines
        try:
            tasks = self.db.execute(text("""
                SELECT t.id, t.title, t.deadline, c.id as case_id, c.case_number, c.case_name
                FROM tasks t
                LEFT JOIN cases c ON t.case_id = c.id
                WHERE t.deadline IS NOT NULL AND t.status != 'completed'
                AND t.deadline <= :deadline_date
                ORDER BY t.deadline
            """), {"deadline_date": deadline_date}).fetchall()
            
            for task in tasks:
                task_date = task.deadline if isinstance(task.deadline, date) else task.deadline.date()
                days_remaining = (task_date - today).days
                
                deadlines.append({
                    "type": "task",
                    "case_id": task.case_id,
                    "case_name": task.case_name or task.case_number,
                    "title": task.title,
                    "deadline": task_date.isoformat(),
                    "days_remaining": days_remaining,
                    "urgent": days_remaining <= 7,
                    "critical": days_remaining <= 3
                })
        except Exception:
            self.db.rollback()
            pass

        # Sort by deadline
        deadlines.sort(key=lambda x: x["deadline"])
        
        return deadlines

    def estimate_completion(self, visa_type: str, start_date: date = None, premium: bool = False) -> Dict:
        """Estimate case completion date."""
        if start_date is None:
            start_date = date.today()
        
        config = self.get_visa_config(visa_type)
        
        if premium and config.get("premium_available"):
            est_days = config.get("premium", 15)
            est_date = start_date + timedelta(days=est_days)
            return {
                "processing_type": "premium",
                "estimated_date": est_date.isoformat(),
                "estimated_days": est_days
            }
        else:
            return {
                "processing_type": "regular",
                "estimated_date_min": (start_date + timedelta(days=config["regular_min"])).isoformat(),
                "estimated_date_max": (start_date + timedelta(days=config["regular_max"])).isoformat(),
                "estimated_days_min": config["regular_min"],
                "estimated_days_max": config["regular_max"]
            }
