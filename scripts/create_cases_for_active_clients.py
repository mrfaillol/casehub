#!/usr/bin/env python3
"""
Create Cases for Active Clients Without Cases

Finds all clients in the CaseHub DB that don't have a case and creates one.
Infers visa_type from the client's document folder name on disk.

Usage:
    python scripts/create_cases_for_active_clients.py --dry-run
    python scripts/create_cases_for_active_clients.py --live
"""
import os
import sys
import re
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(str(Path(__file__).parent.parent / ".env"))

from models.base import SessionLocal
from models.client import Client
from models.case import Case


# Document folders on disk
CLIENTS_DIR = Path("/var/www/immigrant.law/documents/clients")

# Visa type normalization
VISA_NORMALIZE = {
    "EB2-NIW": "EB-2 NIW",
    "EB2 NIW": "EB-2 NIW",
    "EB-2-NIW": "EB-2 NIW",
    "EB1A": "EB-1A",
    "EB1-A": "EB-1A",
    "EB-1A": "EB-1A",
    "I-130": "I-130",
    "I-130 + Consular Processing": "I-130",
    "B1": "B-1/B-2",
    "B-2": "B-1/B-2",
    "IR-1": "IR-1",
    "O-1A": "O-1A",
    "Family-Based": "Family-Based",
}


def normalize_visa(raw: str) -> str:
    """Normalize visa type string."""
    if not raw or raw == "UNKNOWN":
        return None
    return VISA_NORMALIZE.get(raw, raw)


def infer_visa_from_folders(client: Client) -> str:
    """Infer visa type from client document folder names on disk."""
    if not CLIENTS_DIR.exists():
        return None

    last = (client.last_name or "").upper()
    first = (client.first_name or "").strip()

    # Try multiple matching patterns
    candidates = []
    for folder in CLIENTS_DIR.iterdir():
        if not folder.is_dir():
            continue
        name = folder.name.upper()
        # Match by last name prefix
        if name.startswith(last + ",") or name.startswith(last + " "):
            # Extract visa from "LASTNAME, Firstname - VISA"
            match = re.search(r" - (.+)$", folder.name)
            if match:
                visa = match.group(1).strip()
                if visa != "UNKNOWN":
                    candidates.append(visa)

    if not candidates:
        return None

    # Pick the most specific/common visa type
    # Prefer normalized versions
    for c in candidates:
        normalized = normalize_visa(c)
        if normalized:
            return normalized

    return candidates[0]


def generate_case_number(db, client: Client) -> str:
    """Generate unique case number in format ILC-XXXX."""
    # Find the highest existing ILC-XXXX number
    existing = db.query(Case.case_number).filter(
        Case.case_number.like("ILC-%")
    ).all()

    max_num = 0
    for (cn,) in existing:
        if cn and cn.startswith("ILC-"):
            try:
                num = int(cn.split("-")[1])
                if num > max_num:
                    max_num = num
            except (ValueError, IndexError):
                pass

    # Also account for non-ILC case numbers to avoid gaps
    all_cases = db.query(Case).count()
    next_num = max(max_num + 1, all_cases + 1)

    return "ILC-{:04d}".format(next_num)


def main():
    parser = argparse.ArgumentParser(description="Create cases for clients without cases")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes")
    parser.add_argument("--live", action="store_true", help="Actually create cases")
    args = parser.parse_args()

    if not args.dry_run and not args.live:
        print("Must specify --dry-run or --live")
        parser.print_help()
        return

    db = SessionLocal()
    try:
        # Find clients without cases
        existing_case_client_ids = [cid for (cid,) in db.query(Case.client_id).all()]
        clients_without_cases = db.query(Client).filter(
            ~Client.id.in_(existing_case_client_ids) if existing_case_client_ids else True
        ).order_by(Client.id).all()

        print("=" * 70)
        print("CREATE CASES FOR ACTIVE CLIENTS")
        print("=" * 70)
        print("Total clients: {}".format(db.query(Client).count()))
        print("Clients WITH cases: {}".format(len(existing_case_client_ids)))
        print("Clients WITHOUT cases: {}".format(len(clients_without_cases)))
        print("Mode: {}".format("DRY RUN" if args.dry_run else "LIVE"))
        print()

        created = 0
        case_num_counter = 0
        # Pre-calculate starting number
        existing_ilc = db.query(Case.case_number).filter(
            Case.case_number.like("ILC-%")
        ).all()
        max_ilc = 0
        for (cn,) in existing_ilc:
            if cn:
                try:
                    num = int(cn.split("-")[1])
                    if num > max_ilc:
                        max_ilc = num
                except (ValueError, IndexError):
                    pass
        next_num = max(max_ilc + 1, len(existing_case_client_ids) + 1)

        for client in clients_without_cases:
            visa_type = infer_visa_from_folders(client)
            case_number = "ILC-{:04d}".format(next_num)
            next_num += 1

            full_name = "{} {}".format(client.first_name or "", client.last_name or "").strip()
            case_name = "{} - {}".format(full_name, visa_type or "Pending")

            print("  {} (id={}) | case_number={} | visa={} | case_name={}".format(
                full_name, client.id, case_number, visa_type or "None", case_name))

            if args.live:
                case = Case(
                    client_id=client.id,
                    case_number=case_number,
                    case_name=case_name,
                    visa_type=visa_type,
                    status="intake",
                    priority="medium",
                )
                db.add(case)
                created += 1

        if args.live:
            db.commit()
            print("\n{} cases created successfully.".format(created))
        else:
            print("\n[DRY RUN] Would create {} cases.".format(len(clients_without_cases)))

        # Verify
        remaining = db.query(Client).filter(
            ~Client.id.in_([cid for (cid,) in db.query(Case.client_id).all()])
        ).count()
        print("Clients still without cases: {}".format(remaining))

    except Exception as e:
        db.rollback()
        print("ERROR: {}".format(e))
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
