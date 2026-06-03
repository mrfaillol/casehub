"""
CaseHub - CallHippo Integration Service
SMS, Voice Calls, and Call Management
"""
import os
import httpx
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

from config import settings

# CallHippo Configuration
CALLHIPPO_API_KEY = settings.CALLHIPPO_API_KEY
CALLHIPPO_FROM = settings.CALLHIPPO_FROM
CALLHIPPO_EMAIL = settings.CALLHIPPO_EMAIL
CALLHIPPO_BASE_URL = "https://web.callhippo.com"


class CallHippoService:
    """Service for CallHippo SMS and Voice integration."""

    def __init__(self):
        self.api_key = CALLHIPPO_API_KEY
        self.from_number = CALLHIPPO_FROM
        self.user_email = CALLHIPPO_EMAIL
        self.base_url = CALLHIPPO_BASE_URL

    def is_configured(self) -> bool:
        """Check if CallHippo is properly configured."""
        return bool(self.api_key and self.from_number)

    def _get_headers(self) -> dict:
        """Get API headers."""
        return {
            "Content-Type": "application/json",
            "apitoken": self.api_key,
            "accept": "application/json"
        }

    async def send_sms(self, to_number: str, message: str) -> dict:
        """Send SMS via CallHippo."""
        if not self.is_configured():
            return {"success": False, "error": "CallHippo not configured"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/v1/sms/send",
                    headers=self._get_headers(),
                    json={
                        "from": self.from_number,
                        "to": to_number,
                        "userEmail": self.user_email,
                        "smsBody": message
                    }
                )

                if response.status_code in (200, 201):
                    return {"success": True, "data": response.json()}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def make_call(self, to_number: str, caller_id: str = None) -> dict:
        """Initiate outbound call via CallHippo."""
        if not self.is_configured():
            return {"success": False, "error": "CallHippo not configured"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/v1/call/initiate",
                    headers=self._get_headers(),
                    json={
                        "from": caller_id or self.from_number,
                        "to": to_number,
                        "userEmail": self.user_email
                    }
                )

                if response.status_code in (200, 201):
                    return {"success": True, "data": response.json()}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_call_logs(self, limit: int = 50, start_date: str = None, end_date: str = None) -> dict:
        """Get call history from CallHippo."""
        if not self.is_configured():
            return {"success": False, "error": "CallHippo not configured"}

        try:
            params = {"limit": limit}
            if start_date:
                params["startDate"] = start_date
            if end_date:
                params["endDate"] = end_date

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/v1/call/logs",
                    headers=self._get_headers(),
                    params=params
                )

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_sms_history(self, limit: int = 50) -> dict:
        """Get SMS history from CallHippo."""
        if not self.is_configured():
            return {"success": False, "error": "CallHippo not configured"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/v1/sms/history",
                    headers=self._get_headers(),
                    params={"limit": limit}
                )

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_account_info(self) -> dict:
        """Get CallHippo account information."""
        if not self.is_configured():
            return {"success": False, "error": "CallHippo not configured"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/v1/account/info",
                    headers=self._get_headers()
                )

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_numbers(self) -> dict:
        """Get list of phone numbers in account."""
        if not self.is_configured():
            return {"success": False, "error": "CallHippo not configured"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/v1/numbers",
                    headers=self._get_headers()
                )

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # Helper methods for common notifications
    async def notify_new_lead(self, lead_data: dict, to_number: str = None) -> dict:
        """Send SMS notification for new lead."""
        name = lead_data.get("name", "Unknown")
        phone = lead_data.get("phone", "N/A")
        interest = lead_data.get("visa_interest", "Not specified")
        source = lead_data.get("source", "Website")

        message = f"NEW LEAD {settings.ORG_NAME}\nName: {name}\nPhone: {phone}\nInterest: {interest}\nSource: {source}"

        # Default to configured alert number if not specified
        target = to_number or settings.ALERT_PHONE
        return await self.send_sms(target, message)

    async def notify_urgent(self, message: str, to_number: str = None) -> dict:
        """Send urgent SMS notification."""
        target = to_number or settings.ALERT_PHONE
        return await self.send_sms(target, f"URGENT {settings.ORG_NAME}!\n{message}")

    async def send_client_sms(self, to_number: str, client_name: str, message: str) -> dict:
        """Send SMS to client with personalization."""
        formatted_message = f"{settings.ORG_NAME}: Hi {client_name}, {message}"
        return await self.send_sms(to_number, formatted_message)

    async def send_appointment_reminder(self, to_number: str, client_name: str, date: str, time: str) -> dict:
        """Send appointment reminder SMS."""
        message = f"{settings.ORG_NAME} Reminder: Hi {client_name}, you have an appointment on {date} at {time}. Reply CONFIRM to confirm or call us at {self.from_number}."
        return await self.send_sms(to_number, message)


# Singleton instance
callhippo_service = CallHippoService()
