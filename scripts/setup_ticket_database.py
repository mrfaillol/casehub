"""
One-time setup: Create the CaseHub Tickets database in Notion.
Run on VPS where NOTION_TOKEN is available in .env:
    cd /var/www/immigrant.law/casehub && python3 scripts/setup_ticket_database.py
"""
import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
if not NOTION_TOKEN:
    print("ERROR: NOTION_TOKEN not found in .env")
    sys.exit(1)

TARGET_PAGE_ID = "31dcd945-9a03-8050-bec0-e939803f034d"

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

payload = {
    "parent": {"page_id": TARGET_PAGE_ID},
    "title": [{"text": {"content": "CaseHub Tickets"}}],
    "icon": {"emoji": "\U0001f3ab"},
    "properties": {
        "Title": {"title": {}},
        "Description": {"rich_text": {}},
        "Category": {"select": {"options": [
            {"name": "Bug", "color": "red"},
            {"name": "Feature Request", "color": "blue"},
            {"name": "UI/UX Issue", "color": "yellow"},
            {"name": "Data Issue", "color": "orange"},
            {"name": "Performance", "color": "purple"},
            {"name": "Access/Permission", "color": "pink"},
            {"name": "Other", "color": "gray"}
        ]}},
        "Severity": {"select": {"options": [
            {"name": "Critical", "color": "red"},
            {"name": "High", "color": "orange"},
            {"name": "Medium", "color": "yellow"},
            {"name": "Low", "color": "green"}
        ]}},
        "Status": {"status": {}},
        "Reporter": {"rich_text": {}},
        "Reporter Name": {"rich_text": {}},
        "Page URL": {"url": {}},
        "Browser": {"rich_text": {}},
        "CaseHub Version": {"rich_text": {}},
        "Submitted At": {"rich_text": {}},
        "Environment": {"rich_text": {}}
    }
}

print(f"Creating 'CaseHub Tickets' database on page {TARGET_PAGE_ID}...")
response = requests.post("https://api.notion.com/v1/databases", headers=headers, json=payload)

if response.status_code in [200, 201]:
    data = response.json()
    db_id = data["id"]
    print(f"\nSUCCESS! Database created.")
    print(f"Database ID: {db_id}")
    print(f"URL: {data.get('url', 'N/A')}")
    print(f"\nAdd this to your .env:")
    print(f"NOTION_TICKET_DATABASE_ID={db_id}")
else:
    print(f"\nERROR {response.status_code}:")
    print(response.text)
    sys.exit(1)
