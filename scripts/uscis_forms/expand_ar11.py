#!/usr/bin/env python3
"""
Expand AR-11 (Alien's Change of Address Card) with ALL official USCIS fields.
Edition 11/02/22 - 2 pages
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

AR11_FIELDS = [
    # =========================================================================
    # INFORMATION ABOUT YOU (Page 1)
    # =========================================================================
    ("Information About You", "family_name", "*Family Name (Last Name)", "text", True),
    ("Information About You", "given_name", "*Given Name (First Name)", "text", True),
    ("Information About You", "middle_name", "Middle Name (if applicable)", "text", False),
    ("Information About You", "date_of_birth", "*Date of Birth (mm/dd/yyyy)", "date", True),
    ("Information About You", "a_number", "Alien Registration Number (A-Number) (if any)", "text", False),

    # =========================================================================
    # INFORMATION ABOUT YOUR ADDRESS (Page 1)
    # =========================================================================
    # Present Physical Address
    ("Present Physical Address", "present_street_number", "*Present Physical Address - Street Number and Name (No PO Boxes)", "text", True),
    ("Present Physical Address", "present_apt_ste_flr", "Present Physical Address - Apt. Ste. Flr.", "select", False),
    ("Present Physical Address", "present_apt_number", "Present Physical Address - Apt./Ste./Flr. Number", "text", False),
    ("Present Physical Address", "present_city", "*City or Town", "text", True),
    ("Present Physical Address", "present_state", "*State", "select", True),
    ("Present Physical Address", "present_zip", "*ZIP Code", "text", True),

    # Previous Physical Address
    ("Previous Physical Address", "previous_street_number", "Previous Physical Address - Street Number and Name", "text", False),
    ("Previous Physical Address", "previous_apt_ste_flr", "Previous Physical Address - Apt. Ste. Flr.", "select", False),
    ("Previous Physical Address", "previous_apt_number", "Previous Physical Address - Apt./Ste./Flr. Number", "text", False),
    ("Previous Physical Address", "previous_city", "City or Town", "text", False),
    ("Previous Physical Address", "previous_state", "State", "select", False),
    ("Previous Physical Address", "previous_zip", "ZIP Code", "text", False),

    # Mailing Address (optional)
    ("Mailing Address", "mailing_street_number", "Mailing Address - Street Number and Name (optional)", "text", False),
    ("Mailing Address", "mailing_apt_ste_flr", "Mailing Address - Apt. Ste. Flr.", "select", False),
    ("Mailing Address", "mailing_apt_number", "Mailing Address - Apt./Ste./Flr. Number", "text", False),
    ("Mailing Address", "mailing_city", "City or Town", "text", False),
    ("Mailing Address", "mailing_state", "State", "select", False),
    ("Mailing Address", "mailing_zip", "ZIP Code", "text", False),

    # =========================================================================
    # YOUR SIGNATURE (Page 1)
    # =========================================================================
    ("Your Signature", "signature", "*Your Signature", "signature", True),
    ("Your Signature", "signature_date", "Date of Signature (mm/dd/yyyy)", "date", True),
]


def update_ar11(template_id=None):
    """Insert or update AR-11 fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%AR-11%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('AR-11 - Alien''s Change of Address Card (EXPANDED)', "
                    "'Complete AR-11 with all official USCIS fields - Edition 11/02/22') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(AR11_FIELDS):
            conn.execute(text(
                "INSERT INTO questionnaire_fields (template_id, section, field_name, label, field_type, is_required, \"order\") "
                "VALUES (:tid, :section, :field_name, :label, :field_type, :is_required, :order)"
            ), {
                "tid": template_id, "section": section, "field_name": field_name,
                "label": label, "field_type": field_type, "is_required": required, "order": i + 1
            })

        conn.commit()
        print(f"AR-11 expanded: template_id={template_id}, fields={len(AR11_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_ar11()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(AR11_FIELDS)}")

    sections = {}
    for section, _, _, _, _ in AR11_FIELDS:
        sections[section] = sections.get(section, 0) + 1

    print("\nFields by section:")
    for section, count in sections.items():
        print(f"  {section}: {count}")

    # Check for duplicates
    field_names = [field_name for _, field_name, _, _, _ in AR11_FIELDS]
    duplicates = [name for name in field_names if field_names.count(name) > 1]
    if duplicates:
        print(f"\nWARNING: Duplicate field names found: {set(duplicates)}")
    else:
        print("\nNo duplicate field names found.")
