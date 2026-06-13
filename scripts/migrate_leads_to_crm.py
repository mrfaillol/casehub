#!/usr/bin/env python3
"""
Migration Script: MySQL + Moskit → leads_crm.json
Uses MySQL leads table as primary source, enriches with Moskit contact data.
Run from ilc-case-management directory: python3 scripts/migrate_leads_to_crm.py
"""

import asyncio
import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Add parent dir to path so we can import from services
sys.path.insert(0, str(Path(__file__).parent.parent))

from services import leads_manager
import httpx

# MySQL config (from WhatsApp bot .env)
MYSQL_CMD = [
    "mysql", "-u", "immigrant_bot", f"-p{os.environ.get('DB_PASSWORD', '')}",
    "immigrant_whatsapp", "--batch", "--skip-column-names"
]


def query_mysql(sql: str) -> list:
    """Run a MySQL query and return rows as list of lists."""
    result = subprocess.run(
        MYSQL_CMD + ["-e", sql],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  MySQL error: {result.stderr.strip()}")
        return []
    rows = []
    for line in result.stdout.strip().split("\n"):
        if line:
            rows.append(line.split("\t"))
    return rows


async def fetch_moskit_contact(contact_id: int) -> dict:
    """Fetch a single Moskit contact by ID."""
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            response = await client.get(
                f"{leads_manager.MOSKIT_BASE_URL}/contacts/{contact_id}",
                headers={"apikey": leads_manager.MOSKIT_API_KEY},
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            pass
    return {}


def map_source(source_platform: str, source: str) -> str:
    """Map MySQL source fields to CRM source code."""
    if source_platform == "messenger":
        return "MSG"
    if source and "meta" in source.lower():
        return "META"
    if source and "instagram" in source.lower():
        return "IG"
    if source and "site" in source.lower():
        return "SITE"
    return "WPP"


async def run_migration():
    print("=" * 70)
    print("  MIGRATION: MySQL + Moskit → leads_crm.json")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Step 1: Backup current CRM
    print("\n[1/6] Backing up current leads_crm.json...")
    data = leads_manager.load_leads()
    before_count = len(data.get("leads", {}))
    print(f"  Current leads in CRM: {before_count}")

    if before_count > 0:
        backup_path = leads_manager.BACKUP_DIR / f"leads_crm_pre_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        leads_manager.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        with open(backup_path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  Backup saved: {backup_path}")

    # Step 2: Fetch all leads from MySQL
    print("\n[2/6] Fetching leads from MySQL...")
    sql = """
    SELECT id, phone, IFNULL(name, ''), IFNULL(client_name, ''), IFNULL(email, ''),
           IFNULL(whatsapp_name, ''), IFNULL(language, 'en'),
           IFNULL(source, ''), IFNULL(source_platform, 'whatsapp'),
           IFNULL(lead_score, 0), IFNULL(lead_status, 'cold'),
           IFNULL(status, 'new'), IFNULL(visa_interest, ''),
           IFNULL(profession, ''), IFNULL(is_urgent, 0),
           IFNULL(consultation_type, ''), IFNULL(consultation_datetime, ''),
           IFNULL(payment_status, ''), IFNULL(message_count, 0),
           IFNULL(notes, ''), IFNULL(moskit_id, 0), IFNULL(moskit_sent, 0),
           IFNULL(first_contact, ''), IFNULL(last_interaction, ''),
           IFNULL(intake_form_final_score, 0),
           IFNULL(intake_form_primary_pathway, ''),
           IFNULL(intake_form_state, 'not_started'),
           IFNULL(created_at, ''), IFNULL(updated_at, '')
    FROM leads ORDER BY id DESC
    """
    rows = query_mysql(sql)
    print(f"  Total MySQL leads: {len(rows)}")

    # Step 3: Preview
    print("\n[3/6] Preview of leads to import:")
    print(f"  {'#':>3}  {'MySQL ID':>8}  {'Phone':<15}  {'Name':<30}  {'Score':>5}  {'Source':<8}  {'Moskit ID':>10}")
    print("  " + "-" * 100)

    for i, row in enumerate(rows[:20], 1):
        mysql_id = row[0]
        phone = row[1][:14]
        name = (row[2] or row[3] or row[5])[:29]
        score = row[9]
        source = row[8]
        moskit_id = row[20] if row[20] != "0" else "-"
        print(f"  {i:>3}  {mysql_id:>8}  {phone:<15}  {name:<30}  {score:>5}  {source:<8}  {moskit_id:>10}")

    if len(rows) > 20:
        print(f"  ... and {len(rows) - 20} more")

    # Step 4: Import each lead
    print(f"\n[4/6] Importing {len(rows)} leads into CRM...")
    imported = 0
    updated = 0
    enriched = 0
    errors = []

    for i, row in enumerate(rows):
        try:
            # Parse MySQL row
            mysql_id = int(row[0])
            phone = row[1].strip()
            name = row[2] or row[3] or ""
            client_name = row[3] or ""
            email = row[4] or ""
            whatsapp_name = row[5] or ""
            language = row[6] or "en"
            source = row[7] or ""
            source_platform = row[8] or "whatsapp"
            lead_score = int(row[9]) if row[9] else 0
            lead_status = row[10] or "cold"
            status = row[11] or "new"
            visa_interest = row[12] or ""
            profession = row[13] or ""
            is_urgent = bool(int(row[14])) if row[14] else False
            consultation_type = row[15] or ""
            consultation_datetime = row[16] or ""
            payment_status = row[17] or ""
            message_count = int(row[18]) if row[18] else 0
            notes = row[19] or ""
            moskit_id = int(row[20]) if row[20] and row[20] != "0" else None
            moskit_sent = bool(int(row[21])) if row[21] else False
            first_contact = row[22] or ""
            last_interaction = row[23] or ""
            intake_form_final_score = int(row[24]) if row[24] else 0
            intake_form_primary_pathway = row[25] or ""
            intake_form_state = row[26] or "not_started"
            created_at = row[27] or ""
            updated_at = row[28] or ""

            # Use intake form score if higher than lead_score
            effective_score = max(lead_score, intake_form_final_score)

            # Check if lead already exists by phone
            existing = leads_manager.find_by_phone(data, phone) if phone else None
            if not existing and moskit_id:
                existing = leads_manager.find_by_moskit_id(data, moskit_id)

            crm_source = map_source(source_platform, source)

            # Determine display name
            display_name = name or client_name or whatsapp_name or ""

            lead_info = {
                "name": display_name,
                "phone": phone,
                "email": email,
                "whatsapp_name": whatsapp_name,
                "language": language,
                "source": crm_source,
                "source_detail": f"{source_platform}/{source}" if source else source_platform,
                "lead_score": effective_score,
                "lead_status": leads_manager.get_score_status(effective_score),
                "pipeline_stage": leads_manager.get_stage_from_score(effective_score),
                "status": status,
                "visa_interest": visa_interest,
                "profession": profession,
                "is_urgent": is_urgent,
                "consultation_type": consultation_type,
                "consultation_date": consultation_datetime,
                "payment_status": payment_status,
                "message_count": message_count,
                "notes": notes,
                "moskit_contact_id": moskit_id,
                "moskit_sent": moskit_sent,
                "intake_form_final_score": intake_form_final_score,
                "intake_form_primary_pathway": intake_form_primary_pathway,
                "first_contact_at": first_contact or created_at,
            }

            if existing:
                # Update existing lead with MySQL data
                updates = {}
                if not existing.get("phone") and phone:
                    updates["phone"] = phone
                if not existing.get("email") and email:
                    updates["email"] = email
                if not existing.get("name") and display_name:
                    updates["name"] = display_name
                if moskit_id and not existing.get("moskit_contact_id"):
                    updates["moskit_contact_id"] = moskit_id
                if effective_score > existing.get("lead_score", 0):
                    updates["lead_score"] = effective_score
                    updates["lead_status"] = leads_manager.get_score_status(effective_score)
                if updates:
                    leads_manager.update_lead(data, existing["id"], updates)
                updated += 1
            else:
                leads_manager.create_lead(data, lead_info)
                imported += 1

            # Enrich with Moskit data (fetch individual contact for [LEAD] name format and deal info)
            if moskit_id and (i < 200):  # Rate limit: only first 200
                moskit_contact = await fetch_moskit_contact(moskit_id)
                if moskit_contact:
                    moskit_name = moskit_contact.get("name", "")
                    if moskit_name.startswith("[LEAD"):
                        parsed = leads_manager.parse_lead_name(moskit_name)
                        # Find the lead we just created/updated
                        lead_entry = leads_manager.find_by_phone(data, phone) if phone else None
                        if not lead_entry and moskit_id:
                            lead_entry = leads_manager.find_by_moskit_id(data, moskit_id)
                        if lead_entry:
                            enrich_updates = {}
                            if parsed.get("clean_name") and not lead_entry.get("name"):
                                enrich_updates["name"] = parsed["clean_name"]
                            if parsed.get("source") and lead_entry.get("source") == "WPP":
                                enrich_updates["source"] = parsed["source"]
                            if parsed.get("pathway_code"):
                                pathway = leads_manager.PATHWAY_CODES.get(
                                    parsed["pathway_code"], ""
                                )
                                if pathway and not lead_entry.get("intake_form_primary_pathway"):
                                    enrich_updates["intake_form_primary_pathway"] = pathway
                            if enrich_updates:
                                leads_manager.update_lead(data, lead_entry["id"], enrich_updates)
                                enriched += 1

                    # Also get deal info for pipeline stage
                    deals = moskit_contact.get("deals", [])
                    if deals:
                        deal_id = deals[0].get("id")
                        lead_entry = leads_manager.find_by_moskit_id(data, moskit_id)
                        if lead_entry and deal_id:
                            deal_data = await leads_manager.fetch_moskit_deals_for_contact(moskit_id)
                            if deal_data:
                                deal = deal_data[0]
                                stage_id = deal.get("stage", {}).get("id")
                                if stage_id:
                                    stage_name = leads_manager.MOSKIT_STAGE_NAMES.get(stage_id)
                                    if stage_name:
                                        leads_manager.update_lead(data, lead_entry["id"], {
                                            "pipeline_stage": stage_name,
                                            "moskit_deal_id": deal.get("id"),
                                        })

                # Small delay to avoid rate limiting
                if i % 10 == 0:
                    await asyncio.sleep(0.5)

            # Progress indicator
            if (i + 1) % 25 == 0:
                print(f"  ... processed {i + 1}/{len(rows)}")

        except Exception as e:
            errors.append(f"MySQL ID {row[0]}: {str(e)}")
            if len(errors) <= 5:
                print(f"  Error: {e}")

    # Step 5: Rebuild indexes and save
    print("\n[5/6] Rebuilding indexes and saving...")
    data = leads_manager.rebuild_indexes(data)

    # Add sync log entry
    sync_entry = {
        "timestamp": datetime.now().isoformat(),
        "type": "mysql_migration",
        "leads_imported": imported,
        "leads_updated": updated,
        "leads_enriched": enriched,
        "errors": errors[:10],
    }
    data["sync_log"].append(sync_entry)
    data["last_moskit_sync"] = datetime.now().isoformat()
    data["last_updated"] = datetime.now().isoformat()

    leads_manager.save_leads(data)

    # Step 6: Final report
    print("\n[6/6] Migration Results:")
    print("  " + "-" * 50)
    print(f"  Leads imported (new):    {imported}")
    print(f"  Leads updated:           {updated}")
    print(f"  Leads enriched (Moskit): {enriched}")
    print(f"  Errors:                  {len(errors)}")

    if errors:
        print("\n  Errors:")
        for err in errors[:10]:
            print(f"    - {err}")

    # Reload final state
    data = leads_manager.load_leads()
    active_leads = [l for l in data.get("leads", {}).values() if not l.get("is_deleted")]
    print(f"\n  Total leads in CRM now:  {len(active_leads)}")
    print(f"  New leads added:         {len(active_leads) - before_count}")

    # Source breakdown
    sources = {}
    stages = {}
    for lead in active_leads:
        src = lead.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
        stg = lead.get("pipeline_stage", "unknown")
        stages[stg] = stages.get(stg, 0) + 1

    print("\n  By Source:")
    for src, count in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"    {src:<12} {count}")

    print("\n  By Pipeline Stage:")
    for stg, count in sorted(stages.items(), key=lambda x: -x[1]):
        print(f"    {stg:<25} {count}")

    # Score distribution
    scores = [l.get("lead_score", 0) for l in active_leads]
    if scores:
        avg_score = sum(scores) / len(scores)
        hot = len([s for s in scores if s >= 75])
        qualified = len([s for s in scores if 50 <= s < 75])
        warm = len([s for s in scores if 25 <= s < 50])
        cold = len([s for s in scores if s < 25])
        print(f"\n  Score Distribution (avg: {avg_score:.1f}):")
        print(f"    Hot (75+):       {hot}")
        print(f"    Qualified (50+): {qualified}")
        print(f"    Warm (25+):      {warm}")
        print(f"    Cold (<25):      {cold}")

    # Moskit status
    with_moskit = len([l for l in active_leads if l.get("moskit_contact_id")])
    print(f"\n  Leads with Moskit ID:    {with_moskit}")

    print("\n" + "=" * 70)
    print(f"  Migration completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    return sync_entry


if __name__ == "__main__":
    result = asyncio.run(run_migration())
