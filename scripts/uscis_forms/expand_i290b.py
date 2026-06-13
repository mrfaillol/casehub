#!/usr/bin/env python3
"""
Expand I-290B (Notice of Appeal or Motion) with ALL official USCIS fields.
Edition 05/31/24 - 5 pages, Parts 1-7.
"""
import json
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I290B_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT YOU (Page 1)
    # =========================================================================
    ("Part 1. Information About You", "p1_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("Part 1. Information About You", "p1_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("Part 1. Information About You", "p1_1c_middle_name", "1.c. Middle Name", "text", False),
    ("Part 1. Information About You", "p1_2_dob", "2. Date of Birth (mm/dd/yyyy)", "date", True),
    ("Part 1. Information About You", "p1_3_business_name", "3. Business or Organization Name (if applicable)", "text", False),
    ("Part 1. Information About You", "p1_4_a_number", "4. Alien Registration Number (A-Number) (if any)", "text", False),
    ("Part 1. Information About You", "p1_5_uscis_account", "5. USCIS Online Account Number (if any)", "text", False),

    # Mailing Address
    ("Part 1. Mailing Address", "p1_6a_street", "6.a. Street Number and Name", "text", True),
    ("Part 1. Mailing Address", "p1_6b_apt_type", "6.b. Apt./Ste./Flr.", "select", False),
    ("Part 1. Mailing Address", "p1_6b_apt_number", "6.b. Number", "text", False),
    ("Part 1. Mailing Address", "p1_6c_city", "6.c. City or Town", "text", True),
    ("Part 1. Mailing Address", "p1_6d_state", "6.d. State", "select", True),
    ("Part 1. Mailing Address", "p1_6e_zip", "6.e. ZIP Code", "text", True),
    ("Part 1. Mailing Address", "p1_6f_province", "6.f. Province (foreign address only)", "text", False),
    ("Part 1. Mailing Address", "p1_6g_postal_code", "6.g. Postal Code (foreign address only)", "text", False),
    ("Part 1. Mailing Address", "p1_6h_country", "6.h. Country (foreign address only)", "text", False),

    # Contact
    ("Part 1. Contact Information", "p1_7_phone", "7. Daytime Telephone Number", "phone", False),
    ("Part 1. Contact Information", "p1_8_mobile", "8. Mobile Telephone Number (if any)", "phone", False),
    ("Part 1. Contact Information", "p1_9_email", "9. Email Address (if any)", "email", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT THE UNFAVORABLE DECISION (Page 2)
    # =========================================================================
    ("Part 2. Unfavorable Decision", "p2_1_receipt_number", "1. Receipt Number of the unfavorable decision", "text", True),
    ("Part 2. Unfavorable Decision", "p2_2_decision_date", "2. Date of the unfavorable decision (mm/dd/yyyy)", "date", True),
    ("Part 2. Unfavorable Decision", "p2_3_uscis_office", "3. USCIS Office that made the unfavorable decision", "text", True),
    ("Part 2. Unfavorable Decision", "p2_4_form_type", "4. Form type for which the unfavorable decision was made", "text", True),

    # Filing Type
    ("Part 2. Filing Type", "p2_5a_appeal", "5.a. I am filing an appeal", "checkbox", False),
    ("Part 2. Filing Type", "p2_5b_motion_reopen", "5.b. I am filing a motion to reopen", "checkbox", False),
    ("Part 2. Filing Type", "p2_5c_motion_reconsider", "5.c. I am filing a motion to reconsider", "checkbox", False),

    # =========================================================================
    # PART 3: BASIS FOR THE APPEAL OR MOTION (Page 2-3)
    # =========================================================================
    ("Part 3. Basis for Appeal/Motion", "p3_1_basis_statement", "1. Provide a statement that specifically identifies an erroneous conclusion of law or fact in the decision being appealed", "textarea", True),
    ("Part 3. Basis for Appeal/Motion", "p3_2_submitting_brief", "2. I am also submitting a separate brief and/or additional evidence with this form", "checkbox", False),
    ("Part 3. Basis for Appeal/Motion", "p3_3_oral_argument", "3. I am requesting oral argument before the AAO", "checkbox", False),

    # =========================================================================
    # PART 4: APPLICANT'S/PETITIONER'S STATEMENT, CONTACT, SIGNATURE (Page 3)
    # =========================================================================
    ("Part 4. Applicant Statement", "p4_1a_read_english", "1.a. I can read and understand English, and I have read and understand every question and instruction on this form and my answer to every question", "checkbox", False),
    ("Part 4. Applicant Statement", "p4_1b_interpreter_read", "1.b. The interpreter named in Part 5 read to me every question and instruction on this form and my answer to every question in a language in which I am fluent", "checkbox", False),
    ("Part 4. Applicant Statement", "p4_1b_language", "1.b. Language interpreted", "text", False),
    ("Part 4. Applicant Statement", "p4_2_preparer_assisted", "2. At my request, the preparer named in Part 6 prepared this form for me based only upon information I provided or authorized", "checkbox", False),

    # Contact
    ("Part 4. Contact Information", "p4_3_phone", "3. Daytime Telephone Number", "phone", False),
    ("Part 4. Contact Information", "p4_4_mobile", "4. Mobile Telephone Number (if any)", "phone", False),
    ("Part 4. Contact Information", "p4_5_email", "5. Email Address (if any)", "email", False),

    # Signature
    ("Part 4. Signature", "p4_6_signature", "6. Signature of Applicant or Petitioner", "text", True),
    ("Part 4. Signature", "p4_6_date", "6. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 5: INTERPRETER'S CONTACT INFORMATION, CERTIFICATION, SIGNATURE (Page 3-4)
    # =========================================================================
    ("Part 5. Interpreter Info", "p5_1a_family_name", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("Part 5. Interpreter Info", "p5_1b_given_name", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("Part 5. Interpreter Info", "p5_2_business_name", "2. Interpreter's Business or Organization Name (if any)", "text", False),

    # Interpreter Address
    ("Part 5. Interpreter Address", "p5_3a_street", "3.a. Street Number and Name", "text", False),
    ("Part 5. Interpreter Address", "p5_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 5. Interpreter Address", "p5_3b_apt_number", "3.b. Number", "text", False),
    ("Part 5. Interpreter Address", "p5_3c_city", "3.c. City or Town", "text", False),
    ("Part 5. Interpreter Address", "p5_3d_state", "3.d. State", "select", False),
    ("Part 5. Interpreter Address", "p5_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 5. Interpreter Address", "p5_3f_province", "3.f. Province (foreign address only)", "text", False),
    ("Part 5. Interpreter Address", "p5_3g_postal_code", "3.g. Postal Code (foreign address only)", "text", False),
    ("Part 5. Interpreter Address", "p5_3h_country", "3.h. Country (foreign address only)", "text", False),

    # Interpreter Contact
    ("Part 5. Interpreter Contact", "p5_4_phone", "4. Interpreter's Daytime Telephone Number", "phone", False),
    ("Part 5. Interpreter Contact", "p5_5_mobile", "5. Interpreter's Mobile Telephone Number (if any)", "phone", False),
    ("Part 5. Interpreter Contact", "p5_6_email", "6. Interpreter's Email Address (if any)", "email", False),

    # Interpreter Certification
    ("Part 5. Interpreter Certification", "p5_7_language", "7. Language interpreted", "text", False),
    ("Part 5. Interpreter Signature", "p5_8_signature", "8. Signature of Interpreter", "text", False),
    ("Part 5. Interpreter Signature", "p5_8_date", "8. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 6: PREPARER'S CONTACT INFORMATION, DECLARATION, CERTIFICATION, SIGNATURE (Page 4)
    # =========================================================================
    ("Part 6. Preparer Info", "p6_1a_family_name", "1.a. Preparer's Family Name (Last Name)", "text", False),
    ("Part 6. Preparer Info", "p6_1b_given_name", "1.b. Preparer's Given Name (First Name)", "text", False),
    ("Part 6. Preparer Info", "p6_2_business_name", "2. Preparer's Business or Organization Name (if any)", "text", False),

    # Preparer Address
    ("Part 6. Preparer Address", "p6_3a_street", "3.a. Street Number and Name", "text", False),
    ("Part 6. Preparer Address", "p6_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 6. Preparer Address", "p6_3b_apt_number", "3.b. Number", "text", False),
    ("Part 6. Preparer Address", "p6_3c_city", "3.c. City or Town", "text", False),
    ("Part 6. Preparer Address", "p6_3d_state", "3.d. State", "select", False),
    ("Part 6. Preparer Address", "p6_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 6. Preparer Address", "p6_3f_province", "3.f. Province (foreign address only)", "text", False),
    ("Part 6. Preparer Address", "p6_3g_postal_code", "3.g. Postal Code (foreign address only)", "text", False),
    ("Part 6. Preparer Address", "p6_3h_country", "3.h. Country (foreign address only)", "text", False),

    # Preparer Contact
    ("Part 6. Preparer Contact", "p6_4_phone", "4. Preparer's Daytime Telephone Number", "phone", False),
    ("Part 6. Preparer Contact", "p6_5_mobile", "5. Preparer's Mobile Telephone Number (if any)", "phone", False),
    ("Part 6. Preparer Contact", "p6_6_email", "6. Preparer's Email Address (if any)", "email", False),

    # Preparer Declaration
    ("Part 6. Preparer Declaration", "p6_7a_not_attorney", "7.a. I am not an attorney or accredited representative but have prepared this form on behalf of the applicant", "checkbox", False),
    ("Part 6. Preparer Declaration", "p6_7b_is_attorney", "7.b. I am an attorney or accredited representative and my representation extends/does not extend beyond preparation of this form", "checkbox", False),
    ("Part 6. Preparer Signature", "p6_8_signature", "8. Signature of Preparer", "text", False),
    ("Part 6. Preparer Signature", "p6_8_date", "8. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 7: ADDITIONAL INFORMATION (Page 5)
    # =========================================================================
    ("Part 7. Additional Information", "p7_1a_family_name", "1.a. Family Name (Last Name)", "text", False),
    ("Part 7. Additional Information", "p7_1b_given_name", "1.b. Given Name (First Name)", "text", False),
    ("Part 7. Additional Information", "p7_1c_middle_name", "1.c. Middle Name", "text", False),
    ("Part 7. Additional Information", "p7_2_a_number", "2. A-Number (if any)", "text", False),
    ("Part 7. Additional Information", "p7_3a_page_number_1", "3.a. Page Number", "text", False),
    ("Part 7. Additional Information", "p7_3b_part_number_1", "3.b. Part Number", "text", False),
    ("Part 7. Additional Information", "p7_3c_item_number_1", "3.c. Item Number", "text", False),
    ("Part 7. Additional Information", "p7_3d_additional_info_1", "3.d. Additional Information", "textarea", False),
    ("Part 7. Additional Information", "p7_4a_page_number_2", "4.a. Page Number", "text", False),
    ("Part 7. Additional Information", "p7_4b_part_number_2", "4.b. Part Number", "text", False),
    ("Part 7. Additional Information", "p7_4c_item_number_2", "4.c. Item Number", "text", False),
    ("Part 7. Additional Information", "p7_4d_additional_info_2", "4.d. Additional Information", "textarea", False),
    ("Part 7. Additional Information", "p7_5a_page_number_3", "5.a. Page Number", "text", False),
    ("Part 7. Additional Information", "p7_5b_part_number_3", "5.b. Part Number", "text", False),
    ("Part 7. Additional Information", "p7_5c_item_number_3", "5.c. Item Number", "text", False),
    ("Part 7. Additional Information", "p7_5d_additional_info_3", "5.d. Additional Information", "textarea", False),
    ("Part 7. Additional Information", "p7_6a_page_number_4", "6.a. Page Number", "text", False),
    ("Part 7. Additional Information", "p7_6b_part_number_4", "6.b. Part Number", "text", False),
    ("Part 7. Additional Information", "p7_6c_item_number_4", "6.c. Item Number", "text", False),
    ("Part 7. Additional Information", "p7_6d_additional_info_4", "6.d. Additional Information", "textarea", False),
]

OPTIONS_MAP = {
    "p1_6b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p1_6d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"],
    "p5_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p5_3d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"],
    "p6_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p6_3d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"],
}


def update_i290b(template_id=None):
    """Insert or update I-290B fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-290B%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('I-290B - Notice of Appeal or Motion (EXPANDED)', "
                    "'Complete I-290B with all official USCIS fields - Edition 05/31/24') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(I290B_FIELDS):
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
        print(f"I-290B expanded: template_id={template_id}, fields={len(I290B_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_i290b()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(I290B_FIELDS)}")

    sections = {}
    for section, _, _, _, _ in I290B_FIELDS:
        sections[section] = sections.get(section, 0) + 1
    print("\nFields by section:")
    for section, count in sections.items():
        print(f"  {section}: {count}")

    field_names = [fn for _, fn, _, _, _ in I290B_FIELDS]
    duplicates = [n for n in field_names if field_names.count(n) > 1]
    if duplicates:
        print(f"\nWARNING: Duplicate field names: {set(duplicates)}")
    else:
        print("\nNo duplicate field names found.")
