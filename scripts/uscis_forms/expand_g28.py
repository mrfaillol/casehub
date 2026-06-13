#!/usr/bin/env python3
"""
Expand G-28 (Notice of Entry of Appearance as Attorney or Accredited Representative)
with ALL official USCIS fields.
Edition 09/17/18 - 4 pages, Parts 1-6.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

G28_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT ATTORNEY OR ACCREDITED REPRESENTATIVE (Page 1)
    # =========================================================================
    ("Part 1. Attorney/Representative Info", "p1_1a_eligibility_attorney", "1.a. I am an attorney eligible to practice law in, and a member in good standing of, the bar of the highest court(s) of the following State(s)", "checkbox", False),
    ("Part 1. Attorney/Representative Info", "p1_1a_state_bar", "1.a. State(s) of the bar of the highest court(s)", "text", False),
    ("Part 1. Attorney/Representative Info", "p1_1b_accredited_rep", "1.b. I am an accredited representative of the following qualified organization", "checkbox", False),
    ("Part 1. Attorney/Representative Info", "p1_1b_organization", "1.b. Name of recognized organization", "text", False),
    ("Part 1. Attorney/Representative Info", "p1_1c_law_student", "1.c. I am a law student or law graduate under the direct supervision of the attorney or accredited representative named in Item Number 2.", "checkbox", False),
    ("Part 1. Attorney/Representative Info", "p1_1d_not_yet_admitted", "1.d. I am a person who has not yet been admitted to the bar but who is authorized under 8 CFR 1292.1(a)(2) to appear on behalf of a party", "checkbox", False),

    # Attorney/Representative Name
    ("Part 1. Attorney/Representative Info", "p1_2a_family_name", "2.a. Attorney or Accredited Representative's Family Name (Last Name)", "text", True),
    ("Part 1. Attorney/Representative Info", "p1_2b_given_name", "2.b. Attorney or Accredited Representative's Given Name (First Name)", "text", True),
    ("Part 1. Attorney/Representative Info", "p1_2c_middle_name", "2.c. Attorney or Accredited Representative's Middle Name", "text", False),

    # Attorney State Bar Number / USCIS Accredited Rep
    ("Part 1. Attorney/Representative Info", "p1_3a_attorney_bar_number", "3.a. Attorney State Bar Number (if applicable)", "text", False),
    ("Part 1. Attorney/Representative Info", "p1_3b_uscis_account", "3.b. Attorney or Accredited Representative USCIS Online Account Number (if any)", "text", False),

    # Firm/Organization
    ("Part 1. Attorney/Representative Info", "p1_4_firm_name", "4. Name of Law Firm, Organization, or Company (if applicable)", "text", False),

    # Mailing Address
    ("Part 1. Mailing Address", "p1_5a_street", "5.a. Street Number and Name", "text", True),
    ("Part 1. Mailing Address", "p1_5b_apt_type", "5.b. Apt./Ste./Flr.", "select", False),
    ("Part 1. Mailing Address", "p1_5b_apt_number", "5.b. Number", "text", False),
    ("Part 1. Mailing Address", "p1_5c_city", "5.c. City or Town", "text", True),
    ("Part 1. Mailing Address", "p1_5d_state", "5.d. State", "select", True),
    ("Part 1. Mailing Address", "p1_5e_zip", "5.e. ZIP Code", "text", True),
    ("Part 1. Mailing Address", "p1_5f_province", "5.f. Province (foreign address only)", "text", False),
    ("Part 1. Mailing Address", "p1_5g_postal_code", "5.g. Postal Code (foreign address only)", "text", False),
    ("Part 1. Mailing Address", "p1_5h_country", "5.h. Country (foreign address only)", "text", False),

    # Contact Information
    ("Part 1. Contact Information", "p1_6_phone", "6. Telephone Number (with area code)", "phone", True),
    ("Part 1. Contact Information", "p1_7_mobile", "7. Mobile Telephone Number (if any)", "phone", False),
    ("Part 1. Contact Information", "p1_8_email", "8. Email Address (if any)", "email", False),
    ("Part 1. Contact Information", "p1_9_fax", "9. Fax Number (if any)", "text", False),

    # =========================================================================
    # PART 2: ELIGIBILITY INFORMATION FOR ATTORNEY OR ACCREDITED REPRESENTATIVE (Page 1-2)
    # =========================================================================
    ("Part 2. Eligibility", "p2_1a_subject_to_order", "1.a. I am not subject to any order of any court or administrative agency disbarring, suspending, enjoining, restraining, or otherwise restricting me in the practice of law", "checkbox", True),
    ("Part 2. Eligibility", "p2_1b_subject_to_order_yes", "1.b. I am subject to an order. Explain circumstances on Part 6. Additional Information.", "checkbox", False),
    ("Part 2. Eligibility", "p2_1c_held_in_contempt", "1.c. I am not subject to any order suspending, enjoining, restraining, disbarring, or otherwise restricting me from practice before any immigration court, the Board, or DHS", "checkbox", True),
    ("Part 2. Eligibility", "p2_1d_held_in_contempt_yes", "1.d. I am subject to an order restricting practice. Explain circumstances on Part 6. Additional Information.", "checkbox", False),

    # =========================================================================
    # PART 3: NOTICE OF APPEARANCE AS ATTORNEY OR ACCREDITED REPRESENTATIVE (Pages 2-3)
    # =========================================================================
    # Representation Type
    ("Part 3. Notice of Appearance", "p3_1a_representation_extends_proceedings", "1.a. Select this box if this appearance relates to immigration proceedings before an Immigration Judge or the Board of Immigration Appeals (BIA)", "checkbox", False),
    ("Part 3. Notice of Appearance", "p3_1b_representation_extends_uscis", "1.b. Select this box if this appearance relates to a matter before USCIS", "checkbox", False),

    # Person Being Represented Information
    ("Part 3. Person Being Represented", "p3_2a_family_name", "2.a. Family Name (Last Name) of Person Being Represented", "text", True),
    ("Part 3. Person Being Represented", "p3_2b_given_name", "2.b. Given Name (First Name) of Person Being Represented", "text", True),
    ("Part 3. Person Being Represented", "p3_2c_middle_name", "2.c. Middle Name of Person Being Represented", "text", False),

    # Person's Identification
    ("Part 3. Person Being Represented", "p3_3_a_number", "3. Alien Registration Number (A-Number) (if any)", "text", False),
    ("Part 3. Person Being Represented", "p3_4_uscis_account", "4. USCIS Online Account Number (if any)", "text", False),

    # Receipt Number / Case Type
    ("Part 3. Case Information", "p3_5_receipt_number", "5. Receipt Number (if any)", "text", False),
    ("Part 3. Case Information", "p3_6_form_number", "6. This appearance relates to the following form or type of case (specify)", "text", False),

    # Address of Person Being Represented
    ("Part 3. Person's Address", "p3_7a_street", "7.a. Street Number and Name", "text", True),
    ("Part 3. Person's Address", "p3_7b_apt_type", "7.b. Apt./Ste./Flr.", "select", False),
    ("Part 3. Person's Address", "p3_7b_apt_number", "7.b. Number", "text", False),
    ("Part 3. Person's Address", "p3_7c_city", "7.c. City or Town", "text", True),
    ("Part 3. Person's Address", "p3_7d_state", "7.d. State", "select", True),
    ("Part 3. Person's Address", "p3_7e_zip", "7.e. ZIP Code", "text", True),
    ("Part 3. Person's Address", "p3_7f_province", "7.f. Province (foreign address only)", "text", False),
    ("Part 3. Person's Address", "p3_7g_postal_code", "7.g. Postal Code (foreign address only)", "text", False),
    ("Part 3. Person's Address", "p3_7h_country", "7.h. Country (foreign address only)", "text", False),

    # Contact of Person Being Represented
    ("Part 3. Person's Contact", "p3_8_phone", "8. Telephone Number (with area code) of Person Being Represented", "phone", False),
    ("Part 3. Person's Contact", "p3_9_mobile", "9. Mobile Telephone Number (if any) of Person Being Represented", "phone", False),
    ("Part 3. Person's Contact", "p3_10_email", "10. Email Address (if any) of Person Being Represented", "email", False),

    # =========================================================================
    # PART 4: APPLICANT/PETITIONER/REQUESTOR'S CONSENT TO REPRESENTATION AND SIGNATURE (Page 3)
    # =========================================================================
    ("Part 4. Client Consent", "p4_1_consent_representation", "1. I have requested the representation of and consented to being represented by the attorney or accredited representative named in Part 1.", "checkbox", True),
    ("Part 4. Client Consent", "p4_2_consent_notices_to_attorney", "2. I request that USCIS send original notices on my case to my attorney or accredited representative (check this box only if you want USCIS to send original notices to your attorney instead of you)", "checkbox", False),
    ("Part 4. Client Consent", "p4_3_consent_secure_docs_to_attorney", "3. I request that USCIS send any secure identity document(s) to the attorney or accredited representative named in Part 1. (if applicable)", "checkbox", False),

    # Client Signature
    ("Part 4. Client Signature", "p4_4_signature", "4. Signature of Applicant/Petitioner/Requestor", "text", True),
    ("Part 4. Client Signature", "p4_4_date", "4. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 5: SIGNATURE OF ATTORNEY OR ACCREDITED REPRESENTATIVE (Page 3)
    # =========================================================================
    ("Part 5. Attorney Signature", "p5_1_extending_representation", "1. Select one: My representation extends beyond this form.", "checkbox", False),
    ("Part 5. Attorney Signature", "p5_1_not_extending_representation", "1. Select one: My representation does NOT extend beyond this form.", "checkbox", False),
    ("Part 5. Attorney Signature", "p5_2_subject_to_regulation", "2. Pursuant to the privacy waiver contained in Part 4., I may receive copies of the notices and documents sent to the person I represent.", "checkbox", True),
    ("Part 5. Attorney Signature", "p5_3_signature", "3. Signature of Attorney or Accredited Representative", "text", True),
    ("Part 5. Attorney Signature", "p5_3_date", "3. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 6: ADDITIONAL INFORMATION (Page 4)
    # =========================================================================
    ("Part 6. Additional Information", "p6_1a_family_name", "1.a. Family Name (Last Name) of Applicant/Petitioner/Requestor", "text", False),
    ("Part 6. Additional Information", "p6_1b_given_name", "1.b. Given Name (First Name) of Applicant/Petitioner/Requestor", "text", False),
    ("Part 6. Additional Information", "p6_1c_middle_name", "1.c. Middle Name of Applicant/Petitioner/Requestor", "text", False),
    ("Part 6. Additional Information", "p6_2_a_number", "2. A-Number (if any)", "text", False),
    ("Part 6. Additional Information", "p6_3a_page_number_1", "3.a. Page Number", "text", False),
    ("Part 6. Additional Information", "p6_3b_part_number_1", "3.b. Part Number", "text", False),
    ("Part 6. Additional Information", "p6_3c_item_number_1", "3.c. Item Number", "text", False),
    ("Part 6. Additional Information", "p6_3d_additional_info_1", "3.d. Additional Information", "textarea", False),
    ("Part 6. Additional Information", "p6_4a_page_number_2", "4.a. Page Number", "text", False),
    ("Part 6. Additional Information", "p6_4b_part_number_2", "4.b. Part Number", "text", False),
    ("Part 6. Additional Information", "p6_4c_item_number_2", "4.c. Item Number", "text", False),
    ("Part 6. Additional Information", "p6_4d_additional_info_2", "4.d. Additional Information", "textarea", False),
    ("Part 6. Additional Information", "p6_5a_page_number_3", "5.a. Page Number", "text", False),
    ("Part 6. Additional Information", "p6_5b_part_number_3", "5.b. Part Number", "text", False),
    ("Part 6. Additional Information", "p6_5c_item_number_3", "5.c. Item Number", "text", False),
    ("Part 6. Additional Information", "p6_5d_additional_info_3", "5.d. Additional Information", "textarea", False),
]

# Options for select fields
OPTIONS_MAP = {
    "p1_5b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p1_5d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","PR","VI","GU","AS","MP"],
    "p3_7b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p3_7d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","PR","VI","GU","AS","MP"],
}


def update_g28(template_id=None):
    """Insert or update G-28 fields in the database."""
    import json

    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%G-28%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('G-28 - Notice of Entry of Appearance as Attorney or Accredited Representative (EXPANDED)', "
                    "'Complete G-28 with all official USCIS fields - Edition 09/17/18') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(G28_FIELDS):
            options = OPTIONS_MAP.get(field_name)
            conn.execute(text(
                "INSERT INTO questionnaire_fields (template_id, section, field_name, label, field_type, is_required, \"order\", options) "
                "VALUES (:tid, :section, :field_name, :label, :field_type, :is_required, :order, :options)"
            ), {
                "tid": template_id, "section": section, "field_name": field_name,
                "label": label, "field_type": field_type, "is_required": required, "order": i + 1,
                "options": json.dumps(options) if options else None
            })

        conn.commit()
        print(f"G-28 expanded: template_id={template_id}, fields={len(G28_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_g28()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(G28_FIELDS)}")

    sections = {}
    for section, _, _, _, _ in G28_FIELDS:
        sections[section] = sections.get(section, 0) + 1

    print("\nFields by section:")
    for section, count in sections.items():
        print(f"  {section}: {count}")

    # Check for duplicates
    field_names = [field_name for _, field_name, _, _, _ in G28_FIELDS]
    duplicates = [name for name in field_names if field_names.count(name) > 1]
    if duplicates:
        print(f"\nWARNING: Duplicate field names found: {set(duplicates)}")
    else:
        print("\nNo duplicate field names found.")
