"""
CaseHub - Twilio Integration Service
SMS, Voice Calls, WhatsApp, and Communication Management

Follows the same pattern as callhippo.py for consistency.
Uses Twilio REST API via httpx (not the Python SDK) to match existing codebase style.
"""
from dotenv import load_dotenv
load_dotenv()

import os
import httpx
import json
import base64
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import urlencode

# Twilio Configuration
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "")  # e.g. "whatsapp:+1..."
TWILIO_ALERT_NUMBER = os.getenv("TWILIO_ALERT_NUMBER", os.getenv("CALLHIPPO_ALERT_NUMBER", "+17272751816"))
TWILIO_BASE_URL = "https://api.twilio.com/2010-04-01"


class TwilioService:
    """Service for Twilio SMS, Voice, and WhatsApp integration."""

    def __init__(self):
        self.account_sid = TWILIO_ACCOUNT_SID
        self.auth_token = TWILIO_AUTH_TOKEN
        self.from_number = TWILIO_FROM_NUMBER
        self.whatsapp_from = TWILIO_WHATSAPP_FROM
        self.alert_number = TWILIO_ALERT_NUMBER
        self.base_url = f"{TWILIO_BASE_URL}/Accounts/{self.account_sid}"

    def is_configured(self) -> bool:
        """Check if Twilio is properly configured."""
        return bool(self.account_sid and self.auth_token and self.from_number)

    def _get_auth(self) -> tuple:
        """Get HTTP Basic Auth tuple for Twilio API."""
        return (self.account_sid, self.auth_token)

    def _get_headers(self) -> dict:
        """Get API headers with Basic Auth."""
        credentials = base64.b64encode(
            f"{self.account_sid}:{self.auth_token}".encode()
        ).decode()
        return {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

    # ── SMS ──────────────────────────────────────────────────────────────

    async def send_sms(self, to_number: str, message: str) -> dict:
        """Send SMS via Twilio."""
        if not self.is_configured():
            return {"success": False, "error": "Twilio not configured"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/Messages.json",
                    headers=self._get_headers(),
                    content=urlencode({
                        "From": self.from_number,
                        "To": to_number,
                        "Body": message,
                    }),
                )

                data = response.json()
                if response.status_code in (200, 201):
                    return {
                        "success": True,
                        "data": data,
                        "sid": data.get("sid", ""),
                        "status": data.get("status", ""),
                    }
                else:
                    return {
                        "success": False,
                        "error": data.get("message", response.text),
                        "code": data.get("code", ""),
                        "status": response.status_code,
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_sms_history(self, limit: int = 50) -> dict:
        """Get SMS message history from Twilio."""
        if not self.is_configured():
            return {"success": False, "error": "Twilio not configured"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/Messages.json",
                    headers=self._get_headers(),
                    params={"PageSize": limit},
                )

                if response.status_code == 200:
                    data = response.json()
                    return {"success": True, "data": data.get("messages", [])}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Voice Calls ──────────────────────────────────────────────────────

    async def make_call(self, to_number: str, twiml_url: str = None) -> dict:
        """Initiate outbound call via Twilio.

        Args:
            to_number: Phone number to call
            twiml_url: URL returning TwiML instructions. If None, uses a simple greeting.
        """
        if not self.is_configured():
            return {"success": False, "error": "Twilio not configured"}

        try:
            payload = {
                "From": self.from_number,
                "To": to_number,
            }

            if twiml_url:
                payload["Url"] = twiml_url
            else:
                # Simple TwiML that says a message
                payload["Twiml"] = '<Response><Say>Hello, please hold while we connect you.</Say></Response>'

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/Calls.json",
                    headers=self._get_headers(),
                    content=urlencode(payload),
                )

                data = response.json()
                if response.status_code in (200, 201):
                    return {
                        "success": True,
                        "data": data,
                        "sid": data.get("sid", ""),
                        "status": data.get("status", ""),
                    }
                else:
                    return {
                        "success": False,
                        "error": data.get("message", response.text),
                        "status": response.status_code,
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_call_logs(self, limit: int = 50, start_date: str = None, end_date: str = None) -> dict:
        """Get call history from Twilio."""
        if not self.is_configured():
            return {"success": False, "error": "Twilio not configured"}

        try:
            params = {"PageSize": limit}
            if start_date:
                params["StartTime>"] = start_date
            if end_date:
                params["EndTime<"] = end_date

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/Calls.json",
                    headers=self._get_headers(),
                    params=params,
                )

                if response.status_code == 200:
                    data = response.json()
                    return {"success": True, "data": data.get("calls", [])}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── WhatsApp ─────────────────────────────────────────────────────────

    async def send_whatsapp(self, to_number: str, message: str) -> dict:
        """Send WhatsApp message via Twilio.

        to_number should be E.164 format (e.g. +15551234567).
        Twilio requires "whatsapp:" prefix which is added automatically.
        """
        if not self.is_configured() or not self.whatsapp_from:
            return {"success": False, "error": "Twilio WhatsApp not configured"}

        wa_to = f"whatsapp:{to_number}" if not to_number.startswith("whatsapp:") else to_number
        wa_from = self.whatsapp_from if self.whatsapp_from.startswith("whatsapp:") else f"whatsapp:{self.whatsapp_from}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/Messages.json",
                    headers=self._get_headers(),
                    content=urlencode({
                        "From": wa_from,
                        "To": wa_to,
                        "Body": message,
                    }),
                )

                data = response.json()
                if response.status_code in (200, 201):
                    return {
                        "success": True,
                        "data": data,
                        "sid": data.get("sid", ""),
                        "status": data.get("status", ""),
                    }
                else:
                    return {
                        "success": False,
                        "error": data.get("message", response.text),
                        "code": data.get("code", ""),
                        "status": response.status_code,
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Account Info ─────────────────────────────────────────────────────

    async def get_account_info(self) -> dict:
        """Get Twilio account information."""
        if not self.is_configured():
            return {"success": False, "error": "Twilio not configured"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}.json",
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_numbers(self) -> dict:
        """Get list of phone numbers in Twilio account."""
        if not self.is_configured():
            return {"success": False, "error": "Twilio not configured"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/IncomingPhoneNumbers.json",
                    headers=self._get_headers(),
                )

                if response.status_code == 200:
                    data = response.json()
                    return {"success": True, "data": data.get("incoming_phone_numbers", [])}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Helper methods for common notifications ──────────────────────────

    async def notify_new_lead(self, lead_data: dict, to_number: str = None) -> dict:
        """Send SMS notification for new lead."""
        name = lead_data.get("name", "Unknown")
        phone = lead_data.get("phone", "N/A")
        interest = lead_data.get("visa_interest", "Not specified")
        source = lead_data.get("source", "Website")

        message = f"NEW LEAD CaseHub\nName: {name}\nPhone: {phone}\nInterest: {interest}\nSource: {source}"

        target = to_number or self.alert_number
        return await self.send_sms(target, message)

    async def notify_urgent(self, message: str, to_number: str = None) -> dict:
        """Send urgent SMS notification."""
        target = to_number or self.alert_number
        return await self.send_sms(target, f"URGENT CaseHub!\n{message}")

    async def send_client_sms(self, to_number: str, client_name: str, message: str) -> dict:
        """Send SMS to client with personalization."""
        formatted_message = f"CaseHub: Hi {client_name}, {message}"
        return await self.send_sms(to_number, formatted_message)

    async def send_appointment_reminder(self, to_number: str, client_name: str, date: str, time: str) -> dict:
        """Send appointment reminder SMS."""
        message = f"CaseHub Reminder: Hi {client_name}, you have an appointment on {date} at {time}. Reply CONFIRM to confirm or call us at {self.from_number}."
        return await self.send_sms(to_number, message)

    async def send_client_whatsapp(self, to_number: str, client_name: str, message: str) -> dict:
        """Send WhatsApp message to client with personalization."""
        formatted_message = f"CaseHub: Hi {client_name}, {message}"
        return await self.send_whatsapp(to_number, formatted_message)


# Singleton instance
twilio_service = TwilioService()
