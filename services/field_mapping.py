"""
CaseHub - Centralized Field Mapping Service
Maps fields between questionnaires, intake forms, and letter templates.

This service provides a unified way to access client/case data across
different modules (intake packages, letters, questionnaires, documents).
"""

# Standard USCIS Form Field Mappings
# Maps common field names to standard names for consistency

STANDARD_FIELDS = {
    # Personal Information
    "first_name": ["given_name", "petitioner_first_name", "ben_given_name", "applicant_first_name"],
    "last_name": ["family_name", "petitioner_last_name", "ben_family_name", "applicant_last_name"],
    "middle_name": ["petitioner_middle_name", "ben_middle_name", "applicant_middle_name"],
    "date_of_birth": ["dob", "petitioner_dob", "ben_dob", "birth_date"],
    "country_of_birth": ["country_birth", "ben_country_birth", "birth_country"],
    "country_of_citizenship": ["citizenship", "country_citizenship", "ben_country_citizenship"],
    "gender": ["sex"],
    "ssn": ["social_security_number", "ssn_number"],
    "a_number": ["alien_number", "uscis_number", "alien_registration_number"],

    # Address Fields
    "street_address": ["address", "current_address", "residence_address"],
    "city": ["current_city", "residence_city"],
    "state": ["current_state", "residence_state"],
    "zip_code": ["zip", "postal_code"],
    "country": ["current_country", "residence_country"],
    "apt_suite": ["apt", "suite", "unit"],

    # Contact Information
    "email": ["email_address", "contact_email"],
    "phone": ["phone_number", "contact_phone", "daytime_phone"],
    "mobile_phone": ["cell_phone", "mobile"],

    # Immigration Status
    "current_status": ["immigration_status", "current_immigration_status"],
    "class_of_admission": ["admission_class", "entry_class"],
    "date_of_entry": ["entry_date", "last_entry_date", "date_of_last_entry"],
    "i94_number": ["i94", "arrival_departure_number"],
    "visa_type": ["visa_classification", "nonimmigrant_visa_number"],

    # Employment
    "employer_name": ["company_name", "current_employer"],
    "job_title": ["position", "occupation", "current_position"],
    "employer_address": ["company_address"],
    "employer_phone": ["company_phone"],

    # Family Information
    "marital_status": ["marriage_status"],
    "spouse_name": ["spouse_full_name"],
    "spouse_dob": ["spouse_date_of_birth"],
    "date_of_marriage": ["marriage_date"],
    "children_count": ["number_of_children"],

    # Case Information
    "case_number": ["case_id", "receipt_number"],
    "priority_date": ["pd"],
    "petition_type": ["form_type", "application_type"],
}


def normalize_field_name(field_name: str) -> str:
    """
    Convert a field name to its standard form.
    Returns the original name if no mapping exists.
    """
    field_lower = field_name.lower().replace("-", "_").replace(" ", "_")

    # Check if it's already a standard field
    if field_lower in STANDARD_FIELDS:
        return field_lower

    # Check if it's an alias
    for standard, aliases in STANDARD_FIELDS.items():
        if field_lower in [a.lower() for a in aliases]:
            return standard

    return field_lower


def merge_field_data(sources: list[dict]) -> dict:
    """
    Merge field data from multiple sources (questionnaire responses, client data, etc.)
    Later sources override earlier ones.
    """
    merged = {}

    for source in sources:
        for key, value in source.items():
            if value:  # Only add non-empty values
                normalized_key = normalize_field_name(key)
                merged[normalized_key] = value
                # Also keep original key for backwards compatibility
                if key != normalized_key:
                    merged[key] = value

    return merged


def get_field_value(data: dict, field_name: str, default=None):
    """
    Get a field value, checking standard name and all aliases.
    """
    # First try the exact field name
    if field_name in data and data[field_name]:
        return data[field_name]

    # Try the normalized name
    normalized = normalize_field_name(field_name)
    if normalized in data and data[normalized]:
        return data[normalized]

    # If it's a standard field, check all its aliases
    if normalized in STANDARD_FIELDS:
        for alias in STANDARD_FIELDS[normalized]:
            if alias in data and data[alias]:
                return data[alias]

    return default


def build_letter_context(client: dict, case: dict = None, responses: dict = None) -> dict:
    """
    Build a context dictionary for letter template rendering.
    Combines client data, case data, and questionnaire responses.
    """
    sources = []

    if responses:
        sources.append(responses)
    if case:
        sources.append(case)
    if client:
        sources.append(client)

    merged = merge_field_data(sources)

    # Add computed/formatted fields
    context = {
        "client": client,
        "case": case,
        **merged,
    }

    # Add full name if parts exist
    if "first_name" in context and "last_name" in context:
        parts = [context.get("first_name", ""), context.get("middle_name", ""), context.get("last_name", "")]
        context["full_name"] = " ".join(p for p in parts if p)

    # Format address if parts exist
    address_parts = []
    if context.get("street_address"):
        addr = context["street_address"]
        if context.get("apt_suite"):
            addr += f", {context['apt_suite']}"
        address_parts.append(addr)
    if context.get("city") or context.get("state") or context.get("zip_code"):
        city_state = f"{context.get('city', '')}, {context.get('state', '')} {context.get('zip_code', '')}"
        address_parts.append(city_state.strip(", "))
    if context.get("country") and context.get("country") != "United States":
        address_parts.append(context["country"])
    context["formatted_address"] = "\n".join(address_parts)

    return context


# Letter template variable extraction
def extract_template_variables(template_body: str) -> list[str]:
    """
    Extract variable names from a letter template.
    Supports {{ variable }} and {variable} syntax.
    """
    import re

    # Match {{ variable }} or {{ variable|filter }}
    jinja_vars = re.findall(r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)', template_body)

    # Match {variable}
    simple_vars = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', template_body)

    return list(set(jinja_vars + simple_vars))


# Field documentation generator
def generate_field_documentation() -> str:
    """
    Generate documentation of all standard fields and their aliases.
    """
    doc = "# CaseHub Standard Field Reference\n\n"
    doc += "This document lists all standard fields and their aliases.\n\n"

    categories = {
        "Personal Information": ["first_name", "last_name", "middle_name", "date_of_birth",
                                  "country_of_birth", "country_of_citizenship", "gender", "ssn", "a_number"],
        "Address": ["street_address", "city", "state", "zip_code", "country", "apt_suite"],
        "Contact": ["email", "phone", "mobile_phone"],
        "Immigration": ["current_status", "class_of_admission", "date_of_entry", "i94_number", "visa_type"],
        "Employment": ["employer_name", "job_title", "employer_address", "employer_phone"],
        "Family": ["marital_status", "spouse_name", "spouse_dob", "date_of_marriage", "children_count"],
        "Case": ["case_number", "priority_date", "petition_type"],
    }

    for category, fields in categories.items():
        doc += f"## {category}\n\n"
        for field in fields:
            if field in STANDARD_FIELDS:
                aliases = STANDARD_FIELDS[field]
                doc += f"- **{field}**\n"
                doc += f"  - Aliases: {', '.join(aliases)}\n"
        doc += "\n"

    return doc
