"""
CaseHub - USCIS Case Status Service
Check case status directly from USCIS
"""
import re
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class USCISStatusChecker:
    """Service to check USCIS case status."""

    BASE_URL = "https://egov.uscis.gov/casestatus/mycasestatus.do"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    # Status mappings to our internal status
    STATUS_MAP = {
        "Case Was Received": "received",
        "Case Was Approved": "approved",
        "Request for Evidence Was Sent": "rfe",
        "Request for Initial Evidence Was Sent": "rfe",
        "Case Was Denied": "denied",
        "Case Was Transferred": "transferred",
        "Interview Was Scheduled": "interview_scheduled",
        "Card Is Being Produced": "approved",
        "Card Was Mailed To Me": "approved",
        "Card Was Picked Up By The United States Postal Service": "approved",
        "Card Was Delivered": "approved",
        "Case Is Being Actively Reviewed": "pending",
        "Case Is Ready To Be Scheduled For An Interview": "pending",
    }

    def check_status(self, receipt_number: str) -> Dict[str, Any]:
        """
        Check the status of a case by receipt number.

        Args:
            receipt_number: USCIS receipt number (e.g., EAC2190123456)

        Returns:
            Dict with status info or error
        """
        # Validate receipt number format
        receipt_number = receipt_number.strip().upper().replace("-", "").replace(" ", "")

        if not self._validate_receipt_number(receipt_number):
            return {
                "success": False,
                "error": "Invalid receipt number format. Expected format: ABC1234567890 (3 letters + 10 digits)"
            }

        try:
            # Make request to USCIS
            response = requests.post(
                self.BASE_URL,
                data={
                    "appReceiptNum": receipt_number,
                    "caseStatusSearchBtn": "CHECK STATUS"
                },
                headers=self.HEADERS,
                timeout=30
            )

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"USCIS returned status code {response.status_code}"
                }

            # Parse response
            return self._parse_response(response.text, receipt_number)

        except requests.Timeout:
            return {
                "success": False,
                "error": "Request timed out. USCIS may be experiencing issues."
            }
        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"Connection error: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error checking status: {str(e)}"
            }

    def _validate_receipt_number(self, receipt_number: str) -> bool:
        """Validate receipt number format."""
        # Format: 3 letters (service center) + 10 digits
        pattern = r'^[A-Z]{3}\d{10}$'
        return bool(re.match(pattern, receipt_number))

    def _parse_response(self, html: str, receipt_number: str) -> Dict[str, Any]:
        """Parse USCIS response HTML."""
        soup = BeautifulSoup(html, 'html.parser')

        # Find status title
        status_title = soup.find('h1')
        if not status_title:
            return {
                "success": False,
                "error": "Could not find status information in response"
            }

        title_text = status_title.get_text(strip=True)

        # Find status details
        status_details = soup.find('p', class_='text-center')
        details_text = status_details.get_text(strip=True) if status_details else ""

        # Extract date from details if present
        date_match = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}', details_text)
        status_date = None
        if date_match:
            try:
                status_date = datetime.strptime(date_match.group(), "%B %d, %Y").date()
            except:
                pass

        # Map to internal status
        internal_status = "pending"
        for uscis_status, mapped_status in self.STATUS_MAP.items():
            if uscis_status.lower() in title_text.lower():
                internal_status = mapped_status
                break

        return {
            "success": True,
            "receipt_number": receipt_number,
            "status_title": title_text,
            "status_details": details_text,
            "status_date": status_date.isoformat() if status_date else None,
            "internal_status": internal_status,
            "checked_at": datetime.now().isoformat(),
            "raw_html": html[:5000]  # Store first 5000 chars for debugging
        }

    def get_service_center(self, receipt_number: str) -> str:
        """Get service center name from receipt number prefix."""
        prefix = receipt_number[:3].upper()
        centers = {
            "EAC": "Vermont Service Center",
            "WAC": "California Service Center",
            "LIN": "Nebraska Service Center",
            "SRC": "Texas Service Center",
            "MSC": "National Benefits Center",
            "NBC": "National Benefits Center",
            "IOE": "USCIS Electronic Immigration System",
            "YSC": "Potomac Service Center",
        }
        return centers.get(prefix, "Unknown Service Center")


# Route handlers for USCIS status checking
def create_uscis_status_routes():
    """Create routes for USCIS status checking."""
    from fastapi import APIRouter, Depends, Request, Form
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.templating import Jinja2Templates
    from sqlalchemy.orm import Session
    from sqlalchemy import text

    from models import get_db, Case
    from auth import get_current_user

    router = APIRouter(prefix="/uscis-status", tags=["uscis-status"])
    templates = Jinja2Templates(directory="templates")
    checker = USCISStatusChecker()

    @router.get("", response_class=HTMLResponse)
    async def uscis_status_page(request: Request, db: Session = Depends(get_db)):
        """USCIS status checker page."""
        from config import settings as app_settings
        user = get_current_user(request, db)
        if not user:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=f"{app_settings.PREFIX}/login", status_code=302)

        # Get cases with receipt numbers
        cases_with_receipts = db.query(Case).filter(
            Case.receipt_number.isnot(None),
            Case.receipt_number != ""
        ).order_by(Case.created_at.desc()).all()

        # Get recent status checks
        try:
            recent_checks = db.execute(text("""
                SELECT * FROM uscis_status_checks
                ORDER BY checked_at DESC
                LIMIT 20
            """)).fetchall()
        except:
            recent_checks = []

        from i18n import get_translations
        lang = request.cookies.get("lang", "en")

        return templates.TemplateResponse("uscis_status/index.html", {
            "request": request,
            "user": user,
            "PREFIX": app_settings.PREFIX,
            "t": get_translations(lang),
            "cases_with_receipts": cases_with_receipts,
            "recent_checks": recent_checks
        })

    @router.post("/check")
    async def check_uscis_status(
        request: Request,
        receipt_number: str = Form(...),
        case_id: int = Form(None),
        db: Session = Depends(get_db)
    ):
        """Check status and optionally update case."""
        user = get_current_user(request, db)
        if not user:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        # Check status
        result = checker.check_status(receipt_number)

        # Log the check
        try:
            db.execute(text("""
                INSERT INTO uscis_status_checks
                (receipt_number, case_id, user_id, status_title, status_details, internal_status, checked_at, success)
                VALUES (:receipt, :case_id, :user_id, :title, :details, :internal, NOW(), :success)
            """), {
                "receipt": receipt_number,
                "case_id": case_id,
                "user_id": user.id,
                "title": result.get("status_title", ""),
                "details": result.get("status_details", "")[:1000],
                "internal": result.get("internal_status", ""),
                "success": result.get("success", False)
            })

            # Update case if requested and status changed
            if case_id and result.get("success"):
                case = db.query(Case).filter(Case.id == case_id).first()
                if case:
                    # Only update if status indicates a change
                    internal_status = result.get("internal_status")
                    if internal_status in ["approved", "denied", "rfe"]:
                        case.status = internal_status

            db.commit()
        except Exception as e:
            logger.error(f"Error logging USCIS check: {e}")

        return JSONResponse(result)

    @router.get("/api/check/{receipt_number}")
    async def api_check_status(receipt_number: str, db: Session = Depends(get_db)):
        """API endpoint to check status."""
        result = checker.check_status(receipt_number)
        return JSONResponse(result)

    @router.post("/bulk-check")
    async def bulk_check_status(request: Request, db: Session = Depends(get_db)):
        """Check status for all cases with receipt numbers."""
        user = get_current_user(request, db)
        if not user or user.user_type != "admin":
            return JSONResponse({"error": "Admin access required"}, status_code=403)

        cases = db.query(Case).filter(
            Case.receipt_number.isnot(None),
            Case.receipt_number != "",
            Case.status.notin_(["approved", "denied", "closed"])
        ).all()

        results = []
        for case in cases:
            result = checker.check_status(case.receipt_number)
            result["case_id"] = case.id
            result["case_name"] = case.case_name or case.case_number
            results.append(result)

            # Update case if status changed
            if result.get("success"):
                internal_status = result.get("internal_status")
                if internal_status in ["approved", "denied", "rfe"] and case.status != internal_status:
                    case.status = internal_status

        db.commit()

        return JSONResponse({
            "checked": len(results),
            "results": results
        })

    return router


# Singleton instance
uscis_checker = USCISStatusChecker()
