"""
CaseHub - Moskit CRM Integration Service
Sync contacts, deals, and activities with Moskit CRM
"""
import os
import logging
import httpx
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import asyncio

logger = logging.getLogger(__name__)

from config import settings

# Moskit Configuration
MOSKIT_API_KEY = settings.MOSKIT_API_KEY
MOSKIT_BASE_URL = "https://api.moskitcrm.com/v2"
MOSKIT_RESPONSIBLE_ID = int(settings.MOSKIT_RESPONSIBLE_ID) if settings.MOSKIT_RESPONSIBLE_ID else 0

# Cache for leads (avoid fetching 2000+ contacts every time)
_leads_cache = {
    "data": None,
    "last_updated": None,
    "updating": False
}
CACHE_TTL_MINUTES = 10  # Cache valid for 10 minutes


class MoskitService:
    """Service for Moskit CRM integration."""

    def __init__(self):
        self.api_key = MOSKIT_API_KEY
        self.base_url = MOSKIT_BASE_URL
        self.responsible_id = MOSKIT_RESPONSIBLE_ID

    def is_configured(self) -> bool:
        """Check if Moskit is properly configured."""
        return bool(self.api_key)

    def _get_headers(self) -> dict:
        """Get API headers."""
        return {
            "Content-Type": "application/json",
            "apikey": self.api_key,
            "accept": "application/json"
        }

    async def get_contacts(self, limit: int = 50, page: int = 1, search: str = None) -> dict:
        """Get contacts from Moskit."""
        if not self.is_configured():
            return {"success": False, "error": "Moskit not configured"}

        try:
            params = {"limit": limit, "page": page}
            if search:
                params["search"] = search

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/contacts",
                    headers=self._get_headers(),
                    params=params
                )

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_contact(self, contact_id: int) -> dict:
        """Get a single contact by ID."""
        if not self.is_configured():
            return {"success": False, "error": "Moskit not configured"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/contacts/{contact_id}",
                    headers=self._get_headers()
                )

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def search_contact_by_phone(self, phone: str) -> dict:
        """Search contact by phone number."""
        if not self.is_configured():
            return {"success": False, "error": "Moskit not configured"}

        try:
            # Clean phone number
            clean_phone = ''.join(filter(str.isdigit, phone))[-10:]

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/contacts",
                    headers=self._get_headers(),
                    params={"phones": clean_phone}
                )

                if response.status_code == 200:
                    data = response.json()
                    if data and len(data) > 0:
                        return {"success": True, "data": data[0], "found": True}
                    return {"success": True, "data": None, "found": False}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def create_contact(self, contact_data: dict) -> dict:
        """Create a new contact in Moskit."""
        if not self.is_configured():
            return {"success": False, "error": "Moskit not configured"}

        try:
            # Build contact payload
            payload = {
                "name": contact_data.get("name", ""),
                "createdBy": {"id": self.responsible_id},
                "responsible": {"id": self.responsible_id}
            }

            # Add optional fields
            if contact_data.get("email"):
                payload["emails"] = [{"email": contact_data["email"]}]

            if contact_data.get("phone"):
                clean_phone = ''.join(filter(str.isdigit, contact_data["phone"]))
                payload["phones"] = [{"phone": clean_phone}]

            if contact_data.get("notes"):
                payload["observation"] = contact_data["notes"]

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/contacts",
                    headers=self._get_headers(),
                    json=payload
                )

                if response.status_code in (200, 201):
                    result = response.json()
                    return {"success": True, "data": result, "id": result.get("id")}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def update_contact(self, contact_id: int, contact_data: dict) -> dict:
        """Update an existing contact."""
        if not self.is_configured():
            return {"success": False, "error": "Moskit not configured"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.put(
                    f"{self.base_url}/contacts/{contact_id}",
                    headers=self._get_headers(),
                    json=contact_data
                )

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_deals(self, limit: int = 50, page: int = 1, status: str = None) -> dict:
        """Get deals/opportunities from Moskit."""
        if not self.is_configured():
            return {"success": False, "error": "Moskit not configured"}

        try:
            params = {"limit": limit, "page": page}
            if status:
                params["status"] = status

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/deals",
                    headers=self._get_headers(),
                    params=params
                )

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_deal(self, deal_id: int) -> dict:
        """Get a single deal by ID."""
        if not self.is_configured():
            return {"success": False, "error": "Moskit not configured"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/deals/{deal_id}",
                    headers=self._get_headers()
                )

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def create_deal(self, deal_data: dict) -> dict:
        """Create a new deal in Moskit."""
        if not self.is_configured():
            return {"success": False, "error": "Moskit not configured"}

        try:
            payload = {
                "name": deal_data.get("name", ""),
                "responsible": {"id": self.responsible_id},
                "createdBy": {"id": self.responsible_id}
            }

            if deal_data.get("contact_id"):
                payload["contact"] = {"id": deal_data["contact_id"]}

            if deal_data.get("value"):
                payload["price"] = deal_data["value"]

            if deal_data.get("stage_id"):
                payload["stage"] = {"id": deal_data["stage_id"]}

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/deals",
                    headers=self._get_headers(),
                    json=payload
                )

                if response.status_code in (200, 201):
                    result = response.json()
                    return {"success": True, "data": result, "id": result.get("id")}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_activities(self, contact_id: int = None, deal_id: int = None, limit: int = 50) -> dict:
        """Get activities from Moskit."""
        if not self.is_configured():
            return {"success": False, "error": "Moskit not configured"}

        try:
            params = {"limit": limit}
            if contact_id:
                params["contact"] = contact_id
            if deal_id:
                params["deal"] = deal_id

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/activities",
                    headers=self._get_headers(),
                    params=params
                )

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def create_activity(self, activity_data: dict) -> dict:
        """Create an activity in Moskit."""
        if not self.is_configured():
            return {"success": False, "error": "Moskit not configured"}

        try:
            payload = {
                "title": activity_data.get("title", "Activity"),
                "description": activity_data.get("description", ""),
                "type": {"id": activity_data.get("type_id", 1)},  # 1 = Note
                "responsible": {"id": self.responsible_id},
                "createdBy": {"id": self.responsible_id},
                "status": "done"
            }

            if activity_data.get("contact_id"):
                payload["contact"] = {"id": activity_data["contact_id"]}

            if activity_data.get("deal_id"):
                payload["deal"] = {"id": activity_data["deal_id"]}

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/activities",
                    headers=self._get_headers(),
                    json=payload
                )

                if response.status_code in (200, 201):
                    result = response.json()
                    return {"success": True, "data": result, "id": result.get("id")}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_pipelines(self) -> dict:
        """Get pipelines/stages from Moskit."""
        if not self.is_configured():
            return {"success": False, "error": "Moskit not configured"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/stages",
                    headers=self._get_headers()
                )

                if response.status_code == 200:
                    return {"success": True, "data": response.json()}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_stats(self) -> dict:
        """Get basic stats from Moskit."""
        if not self.is_configured():
            return {"success": False, "error": "Moskit not configured"}

        try:
            contacts = await self.get_contacts(limit=1)
            deals = await self.get_deals(limit=1)

            return {
                "success": True,
                "data": {
                    "contacts_count": len(contacts.get("data", [])) if contacts.get("success") else 0,
                    "deals_count": len(deals.get("data", [])) if deals.get("success") else 0
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


    async def get_all_contacts_paginated(self, search: str = None, max_pages: int = 200) -> dict:
        """Get all contacts using token-based pagination (Moskit API V2).

        The Moskit API uses cursor/token pagination via X-Moskit-Listing-Next-Page-Token header.
        The 'page' and 'limit' parameters are ignored by the API.
        Use 'nextPageToken' parameter to pass the token for the next page.
        """
        if not self.is_configured():
            return {"success": False, "error": "Moskit not configured"}

        all_contacts = []
        page_token = None
        pages_fetched = 0

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                while pages_fetched < max_pages:
                    # Build params - use nextPageToken (not pageToken!)
                    params = {}
                    if search:
                        params["search"] = search
                    if page_token:
                        params["nextPageToken"] = page_token

                    response = await client.get(
                        f"{self.base_url}/contacts",
                        headers=self._get_headers(),
                        params=params
                    )

                    if response.status_code == 200:
                        contacts = response.json()
                        if not contacts or len(contacts) == 0:
                            break

                        all_contacts.extend(contacts)
                        pages_fetched += 1

                        # Get next page token from response headers
                        next_token = response.headers.get("X-Moskit-Listing-Next-Page-Token")
                        if not next_token:
                            # No more pages
                            break

                        page_token = next_token
                        await asyncio.sleep(0.25)  # Rate limit protection
                    else:
                        # Log error but return what we have so far
                        logger.error(f"Moskit API error on page {pages_fetched + 1}: {response.status_code}")
                        break

            return {"success": True, "data": all_contacts, "total": len(all_contacts), "pages_fetched": pages_fetched}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_contacts_with_email(self) -> dict:
        """Get all contacts that have an email address."""
        result = await self.get_all_contacts_paginated()
        if not result.get("success"):
            return result

        contacts_with_email = []
        for contact in result.get("data", []):
            emails = contact.get("emails") or []
            if emails and len(emails) > 0:
                # Moskit uses "address" field for email, not "email"
                email = emails[0].get("address", "") or emails[0].get("email", "")
                if email and "@" in email:
                    # Get phone number
                    phones = contact.get("phones") or []
                    phone = phones[0].get("number", "") if phones else ""

                    contacts_with_email.append({
                        "id": contact.get("id"),
                        "name": contact.get("name", ""),
                        "email": email,
                        "phone": phone,
                        "phones": phones,
                        "createdAt": contact.get("createdAt"),
                        "observation": contact.get("observation", "")
                    })

        return {"success": True, "data": contacts_with_email, "total": len(contacts_with_email)}

    async def search_leads(self, prefix: str = "[LEAD", force_refresh: bool = False) -> dict:
        """Search for leads with a specific prefix in name.

        Uses caching to avoid fetching 2000+ contacts every time.
        Cache is valid for CACHE_TTL_MINUTES minutes.
        """
        global _leads_cache

        # Check if cache is valid
        cache_valid = (
            _leads_cache["data"] is not None and
            _leads_cache["last_updated"] is not None and
            datetime.now() - _leads_cache["last_updated"] < timedelta(minutes=CACHE_TTL_MINUTES)
        )

        if cache_valid and not force_refresh:
            # Return cached data
            return {
                "success": True,
                "data": _leads_cache["data"],
                "total": len(_leads_cache["data"]),
                "cached": True,
                "cache_age_seconds": int((datetime.now() - _leads_cache["last_updated"]).total_seconds())
            }

        # Prevent multiple simultaneous refreshes
        if _leads_cache["updating"]:
            # Return stale cache if available, otherwise wait
            if _leads_cache["data"]:
                return {
                    "success": True,
                    "data": _leads_cache["data"],
                    "total": len(_leads_cache["data"]),
                    "cached": True,
                    "updating": True
                }

        _leads_cache["updating"] = True

        try:
            # Fetch all contacts (this is slow but only happens every 10 min)
            result = await self.get_all_contacts_paginated(search=None, max_pages=200)
            if not result.get("success"):
                _leads_cache["updating"] = False
                return result

            import re
            leads = []
            for contact in result.get("data", []):
                name = contact.get("name", "")
                if prefix.lower() in name.lower():
                    lead_info = {
                        "id": contact.get("id"),
                        "name": name,
                        "phones": contact.get("phones", []),
                        "emails": contact.get("emails", []),
                        "createdAt": contact.get("createdAt"),
                        "score": None,
                        "pathway": None,
                        "source": None,
                        "clean_name": name
                    }

                    # Extract source, score and pathway/name from various formats:
                    # "[LEAD WPP 75 FAM] PessoaDemo Silva" - pathway + name outside
                    # "[LEAD META 45 Danilo]" - name inside brackets
                    # "[LEAD META 45 Wilson Didomenico]" - name with spaces inside brackets

                    # Try format: [LEAD SOURCE SCORE PATHWAY] Name (pathway is short code)
                    match = re.match(r'\[LEAD\s+(\w+)\s+(\d+)\s+([A-Z_]{1,10})\]\s*(.+)', name, re.IGNORECASE)
                    if match and len(match.group(4).strip()) > 0:
                        lead_info["source"] = match.group(1).upper()
                        lead_info["score"] = int(match.group(2))
                        lead_info["pathway"] = match.group(3).upper()
                        lead_info["clean_name"] = match.group(4).strip()
                    else:
                        # Try format: [LEAD SOURCE SCORE NAME] - name inside brackets (can have spaces)
                        match2 = re.match(r'\[LEAD\s+(\w+)\s+(\d+)\s+([^\]]+)\]', name, re.IGNORECASE)
                        if match2:
                            lead_info["source"] = match2.group(1).upper()
                            lead_info["score"] = int(match2.group(2))
                            name_or_pathway = match2.group(3).strip()
                            # If short and uppercase, treat as pathway; otherwise as name
                            if len(name_or_pathway) <= 4 and name_or_pathway.isupper():
                                lead_info["pathway"] = name_or_pathway
                            else:
                                lead_info["clean_name"] = name_or_pathway
                        else:
                            # Try simplest format: [LEAD SOURCE] Name
                            match3 = re.match(r'\[LEAD\s+(\w+)\]\s*(.*)', name, re.IGNORECASE)
                            if match3:
                                lead_info["source"] = match3.group(1).upper()
                                lead_info["clean_name"] = match3.group(2).strip() if match3.group(2) else name

                    leads.append(lead_info)

            # Sort by score descending (leads without score go to end)
            leads.sort(key=lambda x: x.get("score") or 0, reverse=True)

            # Update cache
            _leads_cache["data"] = leads
            _leads_cache["last_updated"] = datetime.now()
            _leads_cache["updating"] = False

            return {
                "success": True,
                "data": leads,
                "total": len(leads),
                "cached": False,
                "pages_fetched": result.get("pages_fetched", 0),
                "total_contacts_scanned": len(result.get("data", []))
            }
        except Exception as e:
            _leads_cache["updating"] = False
            return {"success": False, "error": str(e)}


    # ============================================
    # WEEKLY CHECK-IN METHODS
    # ============================================

    async def create_contact_for_checkin(self, email: str, name: str = None) -> dict:
        """Create a contact specifically for weekly check-in with [CHECKIN] tag."""
        if not self.is_configured():
            return {"success": False, "error": "Moskit not configured"}

        # Generate name from email if not provided
        if not name:
            name = email.split("@")[0].replace(".", " ").replace("_", " ").title()

        try:
            payload = {
                "name": f"[CHECKIN] {name}",
                "createdBy": {"id": self.responsible_id},
                "responsible": {"id": self.responsible_id},
                "emails": [{"address": email}],
                "observation": "Weekly Check-in Client - Managed by CaseHub Communications"
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/contacts",
                    headers=self._get_headers(),
                    json=payload
                )

                if response.status_code in (200, 201):
                    result = response.json()
                    return {"success": True, "data": result, "id": result.get("id")}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def delete_contact(self, contact_id: int) -> dict:
        """Delete a contact from Moskit."""
        if not self.is_configured():
            return {"success": False, "error": "Moskit not configured"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(
                    f"{self.base_url}/contacts/{contact_id}",
                    headers=self._get_headers()
                )

                if response.status_code in (200, 204):
                    return {"success": True}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_checkin_contacts(self) -> dict:
        """Get all contacts tagged for weekly check-in (with [CHECKIN] prefix)."""
        result = await self.get_all_contacts_paginated(search="[CHECKIN]")
        if not result.get("success"):
            return result

        checkin_contacts = []
        for contact in result.get("data", []):
            name = contact.get("name", "")
            if "[CHECKIN]" in name.upper():
                emails = contact.get("emails") or []
                email = ""
                if emails:
                    email = emails[0].get("address", "") or emails[0].get("email", "")

                # Remove [CHECKIN] prefix from display name
                clean_name = name.replace("[CHECKIN]", "").replace("[checkin]", "").strip()

                checkin_contacts.append({
                    "id": contact.get("id"),
                    "name": clean_name,
                    "email": email,
                    "moskit_id": contact.get("id"),
                    "createdAt": contact.get("createdAt"),
                    "observation": contact.get("observation", "")
                })

        return {"success": True, "data": checkin_contacts, "total": len(checkin_contacts)}

    async def search_contact_by_email(self, email: str) -> dict:
        """Search for a contact by email address."""
        if not self.is_configured():
            return {"success": False, "error": "Moskit not configured"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/contacts",
                    headers=self._get_headers(),
                    params={"emails": email}
                )

                if response.status_code == 200:
                    data = response.json()
                    if data and len(data) > 0:
                        return {"success": True, "data": data[0], "found": True}
                    return {"success": True, "data": None, "found": False}
                else:
                    return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}


# Singleton instance
moskit_service = MoskitService()
