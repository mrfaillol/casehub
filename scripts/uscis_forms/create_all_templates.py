#!/usr/bin/env python3
"""
Master script to create all USCIS QuestionnaireTemplates in CaseHub.

Usage:
    python create_all_templates.py [--dry-run]

This script creates the following forms:
- I-130: Petition for Alien Relative (237 fields)
- I-130A: Supplemental Information for Spouse Beneficiary (141 fields)
- I-485: Application to Register Permanent Residence (201 fields)
- I-864: Affidavit of Support (161 fields)
- I-765: Application for Employment Authorization (63 fields)
- I-131: Application for Travel Document (91 fields)

Total: 894 fields across 6 forms
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False
    print("Warning: SQLAlchemy not available. Install with: pip install sqlalchemy psycopg2-binary")


# Form metadata
FORMS = {
    "I-130": {
        "name": "Form I-130 - Petition for Alien Relative",
        "description": "Use this form to petition for an alien relative to become a lawful permanent resident.",
        "category": "USCIS Family-Based",
        "visa_types": ["IR-1", "CR-1", "F1", "F2A", "F2B", "F3", "F4"],
        "is_required": True,
        "edition": "04/01/24",
        "json_file": "i-130-structured.json",
    },
    "I-130A": {
        "name": "Form I-130A - Supplemental Information for Spouse Beneficiary",
        "description": "Supplemental form for spouse beneficiaries of Form I-130.",
        "category": "USCIS Family-Based",
        "visa_types": ["IR-1", "CR-1"],
        "is_required": True,
        "edition": "04/01/24",
        "json_file": "i-130a-structured.json",
    },
    "I-485": {
        "name": "Form I-485 - Application to Register Permanent Residence",
        "description": "Use this form to apply for lawful permanent resident status (Green Card).",
        "category": "USCIS Adjustment of Status",
        "visa_types": ["All"],
        "is_required": True,
        "edition": "01/20/25",
        "json_file": "i-485-structured.json",
    },
    "I-864": {
        "name": "Form I-864 - Affidavit of Support",
        "description": "Affidavit of Support required for most family-based immigration cases.",
        "category": "USCIS Family-Based",
        "visa_types": ["IR-1", "CR-1", "F1", "F2A", "F2B", "F3", "F4"],
        "is_required": True,
        "edition": "03/22/24",
        "json_file": "i-864-structured.json",
    },
    "I-765": {
        "name": "Form I-765 - Application for Employment Authorization",
        "description": "Application for Employment Authorization Document (EAD/Work Permit).",
        "category": "USCIS Employment",
        "visa_types": ["All"],
        "is_required": False,
        "edition": "01/20/23",
        "json_file": "i-765-structured.json",
    },
    "I-131": {
        "name": "Form I-131 - Application for Travel Document",
        "description": "Application for Advance Parole or Re-entry Permit.",
        "category": "USCIS Travel",
        "visa_types": ["All"],
        "is_required": False,
        "edition": "04/01/24",
        "json_file": "i-131-structured.json",
    },
}

# Part titles for each form
PART_TITLES = {
    "I-130": {
        1: "Relationship",
        2: "Information About You (Petitioner)",
        3: "Biographic Information",
        4: "Information About Beneficiary",
        5: "Other Information",
        6: "Petitioner's Statement, Contact Information, Declaration, and Signature",
        7: "Interpreter's Contact Information, Certification, and Signature",
        8: "Contact Information, Declaration, and Signature of the Person Preparing this Petition",
        9: "Additional Information",
    },
    "I-130A": {
        1: "Information About You (Spouse Beneficiary)",
        2: "Employment History",
        3: "Information About Your Parents",
        4: "Spouse Beneficiary's Statement, Contact Information, Declaration, and Signature",
        5: "Interpreter's Contact Information, Certification, and Signature",
        6: "Contact Information, Declaration, and Signature of the Person Preparing the Form",
        7: "Additional Information",
    },
    "I-485": {
        1: "Information About You",
        2: "Application Type or Filing Category",
        3: "Additional Information About You",
        4: "Information About Your Parents",
        5: "Information About Your Marital History",
        6: "Information About Your Children",
        7: "Biographic Information",
        8: "General Eligibility and Inadmissibility Grounds",
        9: "Accommodations for Individuals With Disabilities and/or Impairments",
        10: "Applicant's Statement, Contact Information, Certification, and Signature",
        11: "Interpreter's Contact Information, Certification, and Signature",
        12: "Contact Information, Declaration, and Signature of the Person Preparing this Application",
        13: "Signature at Interview",
        14: "Additional Information",
    },
    "I-864": {
        1: "Basis for Filing Affidavit of Support",
        2: "Information About the Principal Immigrant",
        3: "Information About the Immigrants You Are Sponsoring",
        4: "Information About You (the Sponsor)",
        5: "Sponsor's Household Size",
        6: "Sponsor's Employment and Income",
        7: "Use of Assets to Supplement Income",
        8: "Sponsor's Contract",
        9: "Sponsor's Statement, Contact Information, Declaration, Certification, and Signature",
        10: "Interpreter's Contact Information, Certification, and Signature",
        11: "Contact Information, Declaration, and Signature of the Person Preparing this Affidavit",
    },
    "I-765": {
        1: "Reason for Applying",
        2: "Information About You",
        3: "Applicant's Statement, Contact Information, Certification, and Signature",
        4: "Interpreter's Contact Information, Certification, and Signature",
        5: "Contact Information, Declaration, and Signature of the Person Preparing this Application",
        6: "Additional Information",
    },
    "I-131": {
        1: "Application Type",
        2: "Information About You",
        3: "Biographic Information",
        4: "Processing Information",
        5: "Complete Only If Applying for a Reentry Permit",
        6: "Complete Only If Applying for a Refugee Travel Document",
        7: "Information About Your Proposed Travel",
        8: "Complete Only If Applying for Parole Document or Re-parole",
        9: "Employment Authorization for New Period of Parole",
        10: "Applicant's Statement, Contact Information, Certification, and Signature",
        11: "Interpreter's Contact Information, Certification, and Signature",
        12: "Contact Information, Declaration, and Signature of the Person Preparing this Application",
        13: "Additional Information",
    },
}


def get_database_url():
    """Get database URL from environment or config."""
    # Try environment variable first
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        return db_url

    # Try to read from config file
    config_path = Path(__file__).parent.parent.parent / 'config.py'
    if config_path.exists():
        # Parse config file for DATABASE_URL
        with open(config_path) as f:
            content = f.read()
            import re
            match = re.search(r'DATABASE_URL\s*=\s*["\'](.+?)["\']', content)
            if match:
                return match.group(1)

    # Default local PostgreSQL
    return os.getenv("DATABASE_URL", "postgresql://localhost/casehub")


def load_form_data(form_key: str) -> dict:
    """Load structured form data from JSON file."""
    script_dir = Path(__file__).parent
    json_file = script_dir / FORMS[form_key]["json_file"]

    if not json_file.exists():
        raise FileNotFoundError(f"JSON file not found: {json_file}")

    with open(json_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def create_template_with_orm(db, form_key: str, data: dict, dry_run: bool = False):
    """Create QuestionnaireTemplate using SQLAlchemy ORM."""
    from models.questionnaire import QuestionnaireTemplate, QuestionnaireField

    meta = FORMS[form_key]
    part_titles = PART_TITLES.get(form_key, {})
    casehub_fields = data.get("casehub_fields", [])

    print(f"\nCreating {form_key}...")
    print(f"  Name: {meta['name']}")
    print(f"  Fields: {len(casehub_fields)}")

    if dry_run:
        print("  [DRY RUN - No changes made]")
        return None

    # Check if template already exists
    existing = db.query(QuestionnaireTemplate).filter(
        QuestionnaireTemplate.name == meta['name']
    ).first()

    if existing:
        print(f"  WARNING: Template already exists (ID: {existing.id}). Skipping...")
        return existing

    # Create template
    template = QuestionnaireTemplate(
        name=meta['name'],
        description=meta['description'],
        category=meta['category'],
        target_type='case',
        visa_types=meta['visa_types'],
        is_active=True,
        is_required=meta['is_required'],
        allow_multiple=False,
    )
    db.add(template)
    db.flush()  # Get template ID

    print(f"  Template ID: {template.id}")

    # Create fields
    fields = []
    for field_data in casehub_fields:
        field_name = field_data.get("field_name", "")[:100]
        label = field_data.get("label", field_name)[:255]
        field_type = field_data.get("field_type", "text")
        is_required = field_data.get("is_required", False)
        section = field_data.get("section", "")
        order = field_data.get("order", 0)
        options = field_data.get("options")

        # Get proper part title for section
        if section and section.startswith("Part "):
            try:
                part_num = int(section.split()[1])
                section = f"Part {part_num}. {part_titles.get(part_num, section)}"
            except (ValueError, IndexError):
                pass

        field = QuestionnaireField(
            template_id=template.id,
            field_name=field_name,
            label=label,
            field_type=field_type,
            is_required=is_required,
            options=options,
            order=order,
            section=section[:100] if section else None,
            width="full",
        )
        fields.append(field)

    db.add_all(fields)
    print(f"  Created {len(fields)} fields")

    return template


def create_template_with_raw_sql(db_url: str, form_key: str, data: dict, dry_run: bool = False):
    """Create QuestionnaireTemplate using raw SQL (fallback method)."""
    meta = FORMS[form_key]
    part_titles = PART_TITLES.get(form_key, {})
    casehub_fields = data.get("casehub_fields", [])

    print(f"\nCreating {form_key}...")
    print(f"  Name: {meta['name']}")
    print(f"  Fields: {len(casehub_fields)}")

    if dry_run:
        print("  [DRY RUN - No changes made]")
        return None

    engine = create_engine(db_url)

    with engine.connect() as conn:
        # Check if template exists
        result = conn.execute(text(
            "SELECT id FROM questionnaire_templates WHERE name = :name"
        ), {"name": meta['name']})
        existing = result.fetchone()

        if existing:
            print(f"  WARNING: Template already exists (ID: {existing[0]}). Skipping...")
            return existing[0]

        # Create template
        result = conn.execute(text("""
            INSERT INTO questionnaire_templates (
                name, description, category, target_type, visa_types,
                is_active, is_required, allow_multiple, created_at, updated_at
            ) VALUES (
                :name, :description, :category, 'case', :visa_types,
                true, :is_required, false, NOW(), NOW()
            ) RETURNING id
        """), {
            "name": meta['name'],
            "description": meta['description'],
            "category": meta['category'],
            "visa_types": json.dumps(meta['visa_types']),
            "is_required": meta['is_required'],
        })
        template_id = result.fetchone()[0]
        print(f"  Template ID: {template_id}")

        # Create fields
        for field_data in casehub_fields:
            field_name = field_data.get("field_name", "")[:100]
            label = field_data.get("label", field_name)[:255]
            field_type = field_data.get("field_type", "text")
            is_required = field_data.get("is_required", False)
            section = field_data.get("section", "")
            order = field_data.get("order", 0)
            options = field_data.get("options")

            # Get proper part title
            if section and section.startswith("Part "):
                try:
                    part_num = int(section.split()[1])
                    section = f"Part {part_num}. {part_titles.get(part_num, section)}"
                except (ValueError, IndexError):
                    pass

            conn.execute(text("""
                INSERT INTO questionnaire_fields (
                    template_id, field_name, label, field_type, is_required,
                    options, "order", section, width
                ) VALUES (
                    :template_id, :field_name, :label, :field_type, :is_required,
                    :options, :order, :section, 'full'
                )
            """), {
                "template_id": template_id,
                "field_name": field_name,
                "label": label,
                "field_type": field_type,
                "is_required": is_required,
                "options": json.dumps(options) if options else None,
                "order": order,
                "section": section[:100] if section else None,
            })

        conn.commit()
        print(f"  Created {len(casehub_fields)} fields")

        return template_id


def main():
    dry_run = "--dry-run" in sys.argv

    print("=" * 60)
    print("USCIS Forms QuestionnaireTemplates Creator")
    print("=" * 60)
    print(f"Date: {datetime.now().isoformat()}")
    print(f"Dry Run: {dry_run}")
    print()

    # Get database URL
    db_url = get_database_url()
    print(f"Database: {db_url.split('@')[-1] if '@' in db_url else db_url}")
    print()

    if not SQLALCHEMY_AVAILABLE:
        print("ERROR: SQLAlchemy not available. Cannot continue.")
        sys.exit(1)

    # Summary of forms to create
    total_fields = 0
    print("Forms to create:")
    for form_key, meta in FORMS.items():
        try:
            data = load_form_data(form_key)
            field_count = len(data.get("casehub_fields", []))
            total_fields += field_count
            print(f"  - {form_key}: {meta['name']} ({field_count} fields)")
        except FileNotFoundError as e:
            print(f"  - {form_key}: ERROR - {e}")

    print(f"\nTotal fields to create: {total_fields}")
    print()

    if not dry_run:
        response = input("Continue? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            sys.exit(0)

    # Create templates
    print("\n" + "=" * 60)
    print("Creating Templates...")
    print("=" * 60)

    created = 0
    skipped = 0
    errors = 0

    for form_key in FORMS.keys():
        try:
            data = load_form_data(form_key)
            result = create_template_with_raw_sql(db_url, form_key, data, dry_run)
            if result:
                created += 1
            else:
                skipped += 1
        except FileNotFoundError:
            print(f"\n{form_key}: SKIPPED - JSON file not found")
            skipped += 1
        except Exception as e:
            print(f"\n{form_key}: ERROR - {e}")
            errors += 1

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Created: {created}")
    print(f"Skipped: {skipped}")
    print(f"Errors: {errors}")

    if dry_run:
        print("\n[DRY RUN - No actual changes were made]")


if __name__ == "__main__":
    main()
