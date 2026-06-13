#!/usr/bin/env python3
"""
Expand N-336 (Request for a Hearing on a Decision in Naturalization Proceedings) with ALL official USCIS fields.
Edition 04/01/24 - 7 pages, Parts 1-8.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

N336_FIELDS = [
    # =========================================================================
    # HEADER - For USCIS Use Only & Attorney Information
    # =========================================================================
    ("Header - Attorney", "header_g28_attached", "Select this box if Form G-28 is attached", "checkbox", False),
    ("Header - Attorney", "header_attorney_bar_number", "Attorney State Bar Number (if applicable)", "text", False),
    ("Header - Attorney", "header_attorney_uscis_account", "Attorney or Accredited Representative USCIS Online Account Number (if any)", "text", False),

    # =========================================================================
    # PART 1: INFORMATION ABOUT YOU, THE NATURALIZATION APPLICANT (Pages 1-2)
    # =========================================================================
    # Current Legal Name
    ("1. Current Legal Name", "p1_1_family_name", "1. Family Name (Last Name)", "text", True),
    ("1. Current Legal Name", "p1_1_given_name", "1. Given Name (First Name)", "text", True),
    ("1. Current Legal Name", "p1_1_middle_name", "1. Middle Name", "text", False),

    # Other Names Used
    ("1. Other Names", "p1_2_other_family_name", "2. Other Names Used - Family Name (Last Name)", "text", False),
    ("1. Other Names", "p1_2_other_given_name", "2. Other Names Used - Given Name (First Name)", "text", False),
    ("1. Other Names", "p1_2_other_middle_name", "2. Other Names Used - Middle Name", "text", False),

    # A-Number and USCIS Account
    ("1. Identification", "p1_3_dob", "3. Date of Birth (mm/dd/yyyy)", "date", True),
    ("1. Identification", "p1_4_uscis_account", "4. USCIS Online Account Number (if any)", "text", False),
    ("1. Identification", "p1_a_number", "Enter Your 9 Digit A-Number", "text", True),

    # Physical Address
    ("1. Physical Address", "p1_5_street", "5. Physical Address - Street Number and Name", "text", True),
    ("1. Physical Address", "p1_5_apt", "5. Physical Address - Apt./Ste./Flr.", "select", False),
    ("1. Physical Address", "p1_5_number", "5. Physical Address - Number", "text", False),
    ("1. Physical Address", "p1_5_city", "5. Physical Address - City or Town", "text", True),
    ("1. Physical Address", "p1_5_county", "5. Physical Address - County", "text", False),
    ("1. Physical Address", "p1_5_state", "5. Physical Address - State", "select", True),
    ("1. Physical Address", "p1_5_zip", "5. Physical Address - ZIP Code", "text", True),
    ("1. Physical Address", "p1_5_province", "5. Physical Address - Province or Region", "text", False),
    ("1. Physical Address", "p1_5_postal", "5. Physical Address - Postal Code", "text", False),
    ("1. Physical Address", "p1_5_country", "5. Physical Address - Country", "text", False),

    # Mailing Address
    ("1. Mailing Address", "p1_6_in_care_of", "6. Mailing Address - In Care Of Name (if any)", "text", False),
    ("1. Mailing Address", "p1_6_street", "6. Mailing Address - Street Number and Name", "text", False),
    ("1. Mailing Address", "p1_6_apt", "6. Mailing Address - Apt./Ste./Flr.", "select", False),
    ("1. Mailing Address", "p1_6_number", "6. Mailing Address - Number", "text", False),
    ("1. Mailing Address", "p1_6_city", "6. Mailing Address - City or Town", "text", False),
    ("1. Mailing Address", "p1_6_county", "6. Mailing Address - County", "text", False),
    ("1. Mailing Address", "p1_6_state", "6. Mailing Address - State", "select", False),
    ("1. Mailing Address", "p1_6_zip", "6. Mailing Address - ZIP Code", "text", False),
    ("1. Mailing Address", "p1_6_province", "6. Mailing Address - Province or Region", "text", False),
    ("1. Mailing Address", "p1_6_postal", "6. Mailing Address - Postal Code", "text", False),
    ("1. Mailing Address", "p1_6_country", "6. Mailing Address - Country", "text", False),

    # Contact Information
    ("1. Contact Information", "p1_7a_work_phone", "7.A. Work Telephone Number", "phone", False),
    ("1. Contact Information", "p1_7b_evening_phone", "7.B. Evening Telephone Number", "phone", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT FORM N-400 DENIAL (Page 2)
    # =========================================================================
    ("2. N-400 Denial Information", "p2_1_receipt_number", "1. Form N-400 Receipt Number", "text", True),
    ("2. N-400 Denial Information", "p2_2_denial_date", "2. Date of Form N-400 Denial Notice (mm/dd/yyyy)", "date", True),
    ("2. N-400 Denial Information", "p2_3_uscis_office", "3. USCIS Office That Issued Form N-400 Denial Notice", "text", True),
    ("2. N-400 Denial Information", "p2_4_military_service", "4. Did you file your Form N-400 on the basis of qualifying military service?", "radio", True),

    # =========================================================================
    # PART 3: BIOGRAPHIC INFORMATION (Page 2)
    # =========================================================================
    # Ethnicity
    ("3. Biographic - Ethnicity", "p3_1_hispanic", "1. Ethnicity - Hispanic or Latino", "checkbox", False),
    ("3. Biographic - Ethnicity", "p3_1_not_hispanic", "1. Ethnicity - Not Hispanic or Latino", "checkbox", False),

    # Race
    ("3. Biographic - Race", "p3_2_american_indian", "2. Race - American Indian or Alaska Native", "checkbox", False),
    ("3. Biographic - Race", "p3_2_asian", "2. Race - Asian", "checkbox", False),
    ("3. Biographic - Race", "p3_2_black", "2. Race - Black or African American", "checkbox", False),
    ("3. Biographic - Race", "p3_2_pacific", "2. Race - Native Hawaiian or Other Pacific Islander", "checkbox", False),
    ("3. Biographic - Race", "p3_2_white", "2. Race - White", "checkbox", False),

    # Physical Description
    ("3. Biographic - Physical", "p3_3_height_feet", "3. Height - Feet", "text", True),
    ("3. Biographic - Physical", "p3_3_height_inches", "3. Height - Inches", "text", True),
    ("3. Biographic - Physical", "p3_4_weight", "4. Weight - Pounds", "text", True),

    # Eye Color
    ("3. Biographic - Eye Color", "p3_5_eye_black", "5. Eye Color - Black", "checkbox", False),
    ("3. Biographic - Eye Color", "p3_5_eye_blue", "5. Eye Color - Blue", "checkbox", False),
    ("3. Biographic - Eye Color", "p3_5_eye_brown", "5. Eye Color - Brown", "checkbox", False),
    ("3. Biographic - Eye Color", "p3_5_eye_gray", "5. Eye Color - Gray", "checkbox", False),
    ("3. Biographic - Eye Color", "p3_5_eye_green", "5. Eye Color - Green", "checkbox", False),
    ("3. Biographic - Eye Color", "p3_5_eye_hazel", "5. Eye Color - Hazel", "checkbox", False),
    ("3. Biographic - Eye Color", "p3_5_eye_maroon", "5. Eye Color - Maroon", "checkbox", False),
    ("3. Biographic - Eye Color", "p3_5_eye_pink", "5. Eye Color - Pink", "checkbox", False),
    ("3. Biographic - Eye Color", "p3_5_eye_unknown", "5. Eye Color - Unknown/Other", "checkbox", False),

    # Hair Color
    ("3. Biographic - Hair Color", "p3_6_hair_bald", "6. Hair Color - Bald (No hair)", "checkbox", False),
    ("3. Biographic - Hair Color", "p3_6_hair_black", "6. Hair Color - Black", "checkbox", False),
    ("3. Biographic - Hair Color", "p3_6_hair_blond", "6. Hair Color - Blond", "checkbox", False),
    ("3. Biographic - Hair Color", "p3_6_hair_brown", "6. Hair Color - Brown", "checkbox", False),
    ("3. Biographic - Hair Color", "p3_6_hair_gray", "6. Hair Color - Gray", "checkbox", False),
    ("3. Biographic - Hair Color", "p3_6_hair_red", "6. Hair Color - Red", "checkbox", False),
    ("3. Biographic - Hair Color", "p3_6_hair_sandy", "6. Hair Color - Sandy", "checkbox", False),
    ("3. Biographic - Hair Color", "p3_6_hair_white", "6. Hair Color - White", "checkbox", False),
    ("3. Biographic - Hair Color", "p3_6_hair_unknown", "6. Hair Color - Unknown/Other", "checkbox", False),

    # =========================================================================
    # PART 4: REASON YOU ARE REQUESTING A HEARING (Page 3)
    # =========================================================================
    ("4. Reason for Hearing", "p4_reason_text", "Provide the reasons you are requesting a hearing on your denied Form N-400", "textarea", True),

    # =========================================================================
    # PART 5: NATURALIZATION APPLICANT'S STATEMENT, CONTACT INFORMATION, CERTIFICATION, AND SIGNATURE (Page 4)
    # =========================================================================
    # Applicant's Statement
    ("5. Applicant Statement", "p5_1a_english", "1.A. I can read and understand English, and I have read and understand every question and instruction on this request and my answer to every question", "checkbox", False),
    ("5. Applicant Statement", "p5_1b_interpreter", "1.B. The interpreter named in Part 6. read to me every question and instruction on this request and my answer to every question in [language], and I understood everything", "checkbox", False),
    ("5. Applicant Statement", "p5_1b_language", "1.B. Language in which interpreted", "text", False),
    ("5. Applicant Statement", "p5_2_preparer", "2. At my request, the preparer named in Part 7. prepared this request for me based only upon information I provided or authorized", "checkbox", False),
    ("5. Applicant Statement", "p5_2_preparer_name", "2. Preparer's name", "text", False),

    # Contact Information
    ("5. Contact Information", "p5_3_daytime_phone", "3. Naturalization Applicant's Daytime Telephone Number", "phone", False),
    ("5. Contact Information", "p5_4_mobile_phone", "4. Naturalization Applicant's Mobile Telephone Number (if any)", "phone", False),
    ("5. Contact Information", "p5_5_email", "5. Naturalization Applicant's Email Address (if any)", "text", False),

    # Signature
    ("5. Signature", "p5_6_signature", "6. Naturalization Applicant's Signature", "text", True),
    ("5. Signature", "p5_6_signature_date", "6. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 6: INTERPRETER'S CONTACT INFORMATION, CERTIFICATION, AND SIGNATURE (Page 5)
    # =========================================================================
    # Interpreter's Full Name
    ("6. Interpreter - Name", "p6_1_family_name", "1. Interpreter's Family Name (Last Name)", "text", False),
    ("6. Interpreter - Name", "p6_1_given_name", "1. Interpreter's Given Name (First Name)", "text", False),
    ("6. Interpreter - Name", "p6_2_organization", "2. Interpreter's Business or Organization Name (if any)", "text", False),

    # Interpreter's Mailing Address
    ("6. Interpreter - Address", "p6_3_street", "3. Interpreter's Mailing Address - Street Number and Name", "text", False),
    ("6. Interpreter - Address", "p6_3_apt", "3. Interpreter's Mailing Address - Apt./Ste./Flr.", "select", False),
    ("6. Interpreter - Address", "p6_3_number", "3. Interpreter's Mailing Address - Number", "text", False),
    ("6. Interpreter - Address", "p6_3_city", "3. Interpreter's Mailing Address - City or Town", "text", False),
    ("6. Interpreter - Address", "p6_3_state", "3. Interpreter's Mailing Address - State", "select", False),
    ("6. Interpreter - Address", "p6_3_zip", "3. Interpreter's Mailing Address - ZIP Code", "text", False),
    ("6. Interpreter - Address", "p6_3_province", "3. Interpreter's Mailing Address - Province or Region", "text", False),
    ("6. Interpreter - Address", "p6_3_postal", "3. Interpreter's Mailing Address - Postal Code", "text", False),
    ("6. Interpreter - Address", "p6_3_country", "3. Interpreter's Mailing Address - Country", "text", False),

    # Interpreter's Contact Information
    ("6. Interpreter - Contact", "p6_4_daytime_phone", "4. Interpreter's Daytime Telephone Number", "phone", False),
    ("6. Interpreter - Contact", "p6_5_mobile_phone", "5. Interpreter's Mobile Telephone Number (if any)", "phone", False),
    ("6. Interpreter - Contact", "p6_6_email", "6. Interpreter's Email Address (if any)", "text", False),

    # Interpreter's Certification
    ("6. Interpreter - Certification", "p6_cert_language", "I am fluent in English and [language]", "text", False),

    # Interpreter's Signature
    ("6. Interpreter - Signature", "p6_7_signature", "7. Interpreter's Signature", "text", False),
    ("6. Interpreter - Signature", "p6_7_signature_date", "7. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 7: CONTACT INFORMATION, DECLARATION, AND SIGNATURE OF THE PERSON PREPARING THIS REQUEST (Page 6)
    # =========================================================================
    # Preparer's Full Name
    ("7. Preparer - Name", "p7_1_family_name", "1. Preparer's Family Name (Last Name)", "text", False),
    ("7. Preparer - Name", "p7_1_given_name", "1. Preparer's Given Name (First Name)", "text", False),
    ("7. Preparer - Name", "p7_2_organization", "2. Preparer's Business or Organization Name (if any)", "text", False),

    # Preparer's Mailing Address
    ("7. Preparer - Address", "p7_3_street", "3. Preparer's Mailing Address - Street Number and Name", "text", False),
    ("7. Preparer - Address", "p7_3_apt", "3. Preparer's Mailing Address - Apt./Ste./Flr.", "select", False),
    ("7. Preparer - Address", "p7_3_number", "3. Preparer's Mailing Address - Number", "text", False),
    ("7. Preparer - Address", "p7_3_city", "3. Preparer's Mailing Address - City or Town", "text", False),
    ("7. Preparer - Address", "p7_3_state", "3. Preparer's Mailing Address - State", "select", False),
    ("7. Preparer - Address", "p7_3_zip", "3. Preparer's Mailing Address - ZIP Code", "text", False),
    ("7. Preparer - Address", "p7_3_province", "3. Preparer's Mailing Address - Province or Region", "text", False),
    ("7. Preparer - Address", "p7_3_postal", "3. Preparer's Mailing Address - Postal Code", "text", False),
    ("7. Preparer - Address", "p7_3_country", "3. Preparer's Mailing Address - Country", "text", False),

    # Preparer's Contact Information
    ("7. Preparer - Contact", "p7_4_daytime_phone", "4. Preparer's Daytime Telephone Number", "phone", False),
    ("7. Preparer - Contact", "p7_5_mobile_phone", "5. Preparer's Mobile Telephone Number (if any)", "phone", False),
    ("7. Preparer - Contact", "p7_6_email", "6. Preparer's Email Address (if any)", "text", False),

    # Preparer's Statement
    ("7. Preparer - Statement", "p7_7a_not_attorney", "7.A. I am not an attorney or accredited representative but have prepared this request on behalf of the naturalization applicant and with the naturalization applicant's consent", "checkbox", False),
    ("7. Preparer - Statement", "p7_7b_attorney_extends", "7.B. I am an attorney or accredited representative and my representation of the naturalization applicant in this case extends beyond the preparation of this request", "checkbox", False),
    ("7. Preparer - Statement", "p7_7b_attorney_not_extend", "7.B. I am an attorney or accredited representative and my representation does not extend beyond the preparation of this request", "checkbox", False),

    # Preparer's Signature
    ("7. Preparer - Signature", "p7_8_signature", "8. Preparer's Signature", "text", False),
    ("7. Preparer - Signature", "p7_8_signature_date", "8. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 8: ADDITIONAL INFORMATION (Page 7)
    # =========================================================================
    # Applicant Identification (for additional info)
    ("8. Additional Info - Header", "p8_1_family_name", "1. Family Name (Last Name)", "text", False),
    ("8. Additional Info - Header", "p8_1_given_name", "1. Given Name (First Name)", "text", False),
    ("8. Additional Info - Header", "p8_1_middle_name", "1. Middle Name", "text", False),
    ("8. Additional Info - Header", "p8_2_a_number", "2. A-Number (if any)", "text", False),

    # Additional Information Entry 1
    ("8. Additional Info 1", "p8_3a_page", "3.A. Page Number", "text", False),
    ("8. Additional Info 1", "p8_3b_part", "3.B. Part Number", "text", False),
    ("8. Additional Info 1", "p8_3c_item", "3.C. Item Number", "text", False),
    ("8. Additional Info 1", "p8_3d_text", "3.D. Additional Information", "textarea", False),

    # Additional Information Entry 2
    ("8. Additional Info 2", "p8_4a_page", "4.A. Page Number", "text", False),
    ("8. Additional Info 2", "p8_4b_part", "4.B. Part Number", "text", False),
    ("8. Additional Info 2", "p8_4c_item", "4.C. Item Number", "text", False),
    ("8. Additional Info 2", "p8_4d_text", "4.D. Additional Information", "textarea", False),

    # Additional Information Entry 3
    ("8. Additional Info 3", "p8_5a_page", "5.A. Page Number", "text", False),
    ("8. Additional Info 3", "p8_5b_part", "5.B. Part Number", "text", False),
    ("8. Additional Info 3", "p8_5c_item", "5.C. Item Number", "text", False),
    ("8. Additional Info 3", "p8_5d_text", "5.D. Additional Information", "textarea", False),

    # Additional Information Entry 4
    ("8. Additional Info 4", "p8_6a_page", "6.A. Page Number", "text", False),
    ("8. Additional Info 4", "p8_6b_part", "6.B. Part Number", "text", False),
    ("8. Additional Info 4", "p8_6c_item", "6.C. Item Number", "text", False),
    ("8. Additional Info 4", "p8_6d_text", "6.D. Additional Information", "textarea", False),
]


def update_n336(template_id=None):
    """Insert or update N-336 fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%N-336%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('N-336 - Request for a Hearing on a Decision in Naturalization Proceedings (EXPANDED)', "
                    "'Complete N-336 with all official USCIS fields - Edition 04/01/24') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(N336_FIELDS):
            conn.execute(text(
                "INSERT INTO questionnaire_fields (template_id, section, field_name, label, field_type, is_required, \"order\") "
                "VALUES (:tid, :section, :field_name, :label, :field_type, :is_required, :order)"
            ), {
                "tid": template_id, "section": section, "field_name": field_name,
                "label": label, "field_type": field_type, "is_required": required, "order": i + 1
            })

        conn.commit()
        print(f"N-336 expanded: template_id={template_id}, fields={len(N336_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_n336()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(N336_FIELDS)}")

    sections = {}
    for section, _, _, _, _ in N336_FIELDS:
        sections[section] = sections.get(section, 0) + 1

    print("\nFields by section:")
    for section, count in sections.items():
        print(f"  {section}: {count}")

    # Check for duplicate field names
    field_names = [field_name for _, field_name, _, _, _ in N336_FIELDS]
    duplicates = [name for name in field_names if field_names.count(name) > 1]
    if duplicates:
        print(f"\nWARNING: Duplicate field names found: {set(duplicates)}")
    else:
        print("\nValidation: No duplicate field names found.")
