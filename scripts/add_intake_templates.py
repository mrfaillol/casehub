"""
Incremental script to add G-28, COMMON-INFO, and I-907-specific templates
to the questionnaire database WITHOUT deleting existing data.

Run on VPS: cd /var/www/immigrant.law/casehub && python scripts/add_intake_templates.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.base import SessionLocal
from models.questionnaire import QuestionnaireTemplate, QuestionnaireField
from models import User
from sqlalchemy import text


# Common field names that are collected via COMMON-INFO
# These will be excluded from "specific-only" form variants
COMMON_FIELD_NAMES = {
    "family_name", "given_name", "middle_name", "date_of_birth",
    "country_of_birth", "country_of_citizenship",
    "street_address", "apt_suite", "city", "state", "zip_code",
    "daytime_phone", "mobile_phone", "email",
    "alien_number", "uscis_account_number", "ssn",
    "gender", "marital_status",
}

# Section names that are just headers for common fields
COMMON_SECTION_HEADERS = {
    "section_personal", "section_contact", "section_ids",
}


NEW_TEMPLATES = [
    {
        "form_number": "G-28",
        "name": "G-28 - Notice of Entry of Appearance as Attorney or Accredited Representative",
        "description": "Authorization for attorney representation before USCIS.",
        "category": "representation",
        "fields": [
            {"field_name": "section_client", "label": "Client Information", "field_type": "section", "is_required": False},
            {"field_name": "client_full_name", "label": "Your Full Legal Name", "field_type": "text", "is_required": True, "section": "Client Information"},
            {"field_name": "alien_number", "label": "Alien Registration Number (A-Number)", "field_type": "text", "is_required": False, "section": "Client Information"},
            {"field_name": "uscis_account_number", "label": "USCIS Online Account Number", "field_type": "text", "is_required": False, "section": "Client Information"},
            {"field_name": "receipt_number", "label": "USCIS Receipt Number (if applicable)", "field_type": "text", "is_required": False, "section": "Case Information"},
            {"field_name": "section_consent", "label": "Authorization", "field_type": "section", "is_required": False},
            {"field_name": "consent_representation", "label": "I authorize Immigration Law Center to represent me before USCIS in all matters related to my immigration case", "field_type": "checkbox", "is_required": True, "section": "Authorization"},
            {"field_name": "consent_access_records", "label": "I authorize my representative to access my USCIS records and receive correspondence on my behalf", "field_type": "checkbox", "is_required": True, "section": "Authorization"},
            {"field_name": "signature_date", "label": "Date of Authorization", "field_type": "date", "is_required": True, "section": "Authorization"},
        ]
    },
    {
        "form_number": "COMMON-INFO",
        "name": "Client Personal Information",
        "description": "Basic personal and contact information collected once and shared across all forms in this package.",
        "category": "common",
        "fields": [
            {"field_name": "section_personal", "label": "Personal Information", "field_type": "section", "is_required": False},
            {"field_name": "family_name", "label": "Family Name (Last Name)", "field_type": "text", "is_required": True, "section": "Personal Information"},
            {"field_name": "given_name", "label": "Given Name (First Name)", "field_type": "text", "is_required": True, "section": "Personal Information"},
            {"field_name": "middle_name", "label": "Middle Name", "field_type": "text", "is_required": False, "section": "Personal Information"},
            {"field_name": "date_of_birth", "label": "Date of Birth", "field_type": "date", "is_required": True, "section": "Personal Information"},
            {"field_name": "country_of_birth", "label": "Country of Birth", "field_type": "text", "is_required": True, "section": "Personal Information"},
            {"field_name": "country_of_citizenship", "label": "Country of Citizenship/Nationality", "field_type": "text", "is_required": True, "section": "Personal Information"},
            {"field_name": "gender", "label": "Gender", "field_type": "select", "is_required": True, "section": "Personal Information",
             "options": [{"value": "male", "label": "Male"}, {"value": "female", "label": "Female"}]},
            {"field_name": "marital_status", "label": "Marital Status", "field_type": "select", "is_required": True, "section": "Personal Information",
             "options": [{"value": "single", "label": "Single"}, {"value": "married", "label": "Married"}, {"value": "divorced", "label": "Divorced"}, {"value": "widowed", "label": "Widowed"}]},
            {"field_name": "section_ids", "label": "Identification Numbers", "field_type": "section", "is_required": False},
            {"field_name": "alien_number", "label": "Alien Registration Number (A-Number)", "field_type": "text", "is_required": False, "section": "USCIS Information"},
            {"field_name": "uscis_account_number", "label": "USCIS Online Account Number", "field_type": "text", "is_required": False, "section": "USCIS Information"},
            {"field_name": "ssn", "label": "U.S. Social Security Number", "field_type": "text", "is_required": False, "section": "Identification"},
            {"field_name": "section_contact", "label": "Contact Information", "field_type": "section", "is_required": False},
            {"field_name": "street_address", "label": "Street Number and Name", "field_type": "text", "is_required": True, "section": "Contact Information"},
            {"field_name": "apt_suite", "label": "Apt/Ste/Flr", "field_type": "text", "is_required": False, "section": "Contact Information"},
            {"field_name": "city", "label": "City or Town", "field_type": "text", "is_required": True, "section": "Contact Information"},
            {"field_name": "state", "label": "State", "field_type": "text", "is_required": True, "section": "Contact Information"},
            {"field_name": "zip_code", "label": "ZIP Code", "field_type": "text", "is_required": True, "section": "Contact Information"},
            {"field_name": "daytime_phone", "label": "Daytime Phone Number", "field_type": "phone", "is_required": True, "section": "Contact Information"},
            {"field_name": "mobile_phone", "label": "Mobile Phone Number", "field_type": "phone", "is_required": False, "section": "Contact Information"},
            {"field_name": "email", "label": "Email Address", "field_type": "email", "is_required": True, "section": "Contact Information"},
        ]
    },
]


def create_specific_variant(db, original_name_pattern: str, variant_suffix: str = "Specific"):
    """
    Create a 'specific-only' variant of an existing form by copying its fields
    but excluding common fields (personal info, contact info, etc.).

    Returns the new template ID or None if original not found.
    """
    # Find original template
    original = db.query(QuestionnaireTemplate).filter(
        QuestionnaireTemplate.name.ilike(f"%{original_name_pattern}%")
    ).first()

    if not original:
        print(f"  ⚠ Original template '{original_name_pattern}' not found, skipping specific variant")
        return None

    # Check if variant already exists
    variant_name = f"{original.name} (Petition Details Only)"
    existing = db.query(QuestionnaireTemplate).filter(
        QuestionnaireTemplate.name == variant_name
    ).first()
    if existing:
        print(f"  ℹ Variant '{variant_name}' already exists (id={existing.id}), skipping")
        return existing.id

    # Get original fields
    original_fields = db.query(QuestionnaireField).filter(
        QuestionnaireField.template_id == original.id
    ).order_by(QuestionnaireField.order).all()

    # Filter out common fields
    specific_fields = []
    for f in original_fields:
        # Skip common field names
        if f.field_name in COMMON_FIELD_NAMES:
            continue
        # Skip section headers that only introduce common fields
        if f.field_name in COMMON_SECTION_HEADERS:
            continue
        # Skip section headers for personal/contact sections
        if f.field_type == "section" and f.field_name in ("section_personal", "section_contact", "section_ids"):
            continue
        specific_fields.append(f)

    if not specific_fields:
        print(f"  ⚠ No specific fields found for '{original_name_pattern}', skipping")
        return None

    # Create variant template
    variant = QuestionnaireTemplate(
        name=variant_name,
        description=f"{original.description} (Excludes personal/contact info collected separately.)",
        category=original.category,
        target_type="client",
        is_active=True,
        is_required=False,
        created_by=original.created_by
    )
    db.add(variant)
    db.flush()

    # Copy specific fields
    for order, orig_field in enumerate(specific_fields):
        field = QuestionnaireField(
            template_id=variant.id,
            field_name=orig_field.field_name,
            label=orig_field.label,
            field_type=orig_field.field_type,
            is_required=orig_field.is_required,
            section=orig_field.section,
            options=orig_field.options,
            order=order
        )
        db.add(field)

    print(f"  ✓ Created variant '{variant_name}' (id={variant.id}): {len(specific_fields)} fields (was {len(original_fields)})")
    return variant.id


def add_templates():
    """Add new templates incrementally (does not delete existing data)."""
    db = SessionLocal()

    try:
        admin = db.query(User).filter(User.email == "admin@immigrant.law").first()
        admin_id = admin.id if admin else 1

        template_ids = {}

        # Step 1: Add G-28 and COMMON-INFO templates
        print("\n=== Step 1: Adding G-28 and COMMON-INFO templates ===\n")
        for form_data in NEW_TEMPLATES:
            # Check if already exists
            existing = db.query(QuestionnaireTemplate).filter(
                QuestionnaireTemplate.name.ilike(f"%{form_data['form_number']}%")
            ).first()

            if existing:
                print(f"  ℹ {form_data['form_number']} already exists (id={existing.id}), skipping")
                template_ids[form_data['form_number']] = existing.id
                continue

            template = QuestionnaireTemplate(
                name=form_data["name"],
                description=form_data["description"],
                category=form_data["category"],
                target_type="client",
                is_active=True,
                is_required=False,
                created_by=admin_id
            )
            db.add(template)
            db.flush()

            for order, field_data in enumerate(form_data["fields"]):
                field = QuestionnaireField(
                    template_id=template.id,
                    field_name=field_data["field_name"],
                    label=field_data["label"],
                    field_type=field_data["field_type"],
                    is_required=field_data.get("is_required", False),
                    section=field_data.get("section"),
                    options=field_data.get("options"),
                    order=order
                )
                db.add(field)

            template_ids[form_data['form_number']] = template.id
            print(f"  ✓ {form_data['form_number']}: {form_data['name']} (id={template.id}, {len(form_data['fields'])} fields)")

        db.flush()

        # Step 2: Create specific-only variants for forms used in packages
        print("\n=== Step 2: Creating specific-only form variants ===\n")

        forms_to_create_variants = [
            "I-140",  # EB-1A, EB-2 NIW
            "I-907",  # Premium Processing
            "I-485",  # Adjustment of Status
            "I-765",  # Employment Authorization
            "I-131",  # Advance Parole
        ]

        for form_number in forms_to_create_variants:
            variant_id = create_specific_variant(db, form_number)
            if variant_id:
                template_ids[f"{form_number}-specific"] = variant_id

        db.commit()

        # Step 3: Print ID mapping for intake_service.py
        print("\n=== Template IDs for intake_service.py ===\n")
        for key, tid in sorted(template_ids.items()):
            print(f"  {key}: {tid}")

        print("\n✅ Done! Update intake_service.py PACKAGE_TEMPLATES with these IDs.")

    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    add_templates()
