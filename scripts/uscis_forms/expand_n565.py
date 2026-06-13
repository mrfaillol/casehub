#!/usr/bin/env python3
"""
Expand N-565 (Application for Replacement Naturalization/Citizenship Document) with ALL official USCIS fields.
Edition 02/27/25 - 7 pages, Parts 1-12.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

N565_FIELDS = [
    # =========================================================================
    # ATTORNEY/REPRESENTATIVE (Top of Page 1)
    # =========================================================================
    ("Attorney/Representative", "g28_attached", "Select this box if Form G-28 is attached", "checkbox", False),
    ("Attorney/Representative", "attorney_bar_number", "Attorney State Bar Number (if applicable)", "text", False),
    ("Attorney/Representative", "attorney_uscis_account", "Attorney or Accredited Representative USCIS Online Account Number (if any)", "text", False),

    # =========================================================================
    # PART 1: INFORMATION FROM CURRENT CERTIFICATE OR DECLARATION (Page 1)
    # =========================================================================
    ("Part 1. Current Certificate Info", "p1_1_last_name", "1. Your Full Name - Family Name (Last Name)", "text", True),
    ("Part 1. Current Certificate Info", "p1_1_first_name", "1. Your Full Name - Given Name (First Name)", "text", True),
    ("Part 1. Current Certificate Info", "p1_1_middle_name", "1. Your Full Name - Middle Name (if applicable)", "text", False),
    ("Part 1. Current Certificate Info", "p1_2_dob", "2. Date of Birth on Certificate or Declaration (mm/dd/yyyy)", "date", True),
    ("Part 1. Current Certificate Info", "p1_3_country_birth", "3. Country of Birth", "text", True),
    ("Part 1. Current Certificate Info", "p1_4_country_former_citizenship", "4. Country of Former Citizenship or Nationality", "text", True),
    ("Part 1. Current Certificate Info", "p1_5_certificate_number", "5. Certificate or Declaration Number", "text", True),
    ("Part 1. Current Certificate Info", "p1_6_a_number", "6. Alien Registration Number (A-Number) (if any)", "text", False),
    ("Part 1. Current Certificate Info", "p1_7_uscis_office_court", "7. U.S. Citizenship and Immigration Services (USCIS) Office or Name of Court", "text", True),
    ("Part 1. Current Certificate Info", "p1_7_issuance_date", "7. Certificate or Declaration Issuance - Date (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 2: CURRENT INFORMATION ABOUT YOU (Pages 1-2)
    # =========================================================================
    ("Part 2. Current Info", "p2_1_last_name", "1. Your Full Legal Name - Family Name (Last Name)", "text", True),
    ("Part 2. Current Info", "p2_1_first_name", "1. Your Full Legal Name - Given Name (First Name)", "text", True),
    ("Part 2. Current Info", "p2_1_middle_name", "1. Your Full Legal Name - Middle Name (if applicable)", "text", False),

    # Other Names Used (up to 3 rows)
    ("Part 2. Other Names 1", "p2_2a_last_name", "2. Other Names Used - Row 1 - Family Name (Last Name)", "text", False),
    ("Part 2. Other Names 1", "p2_2a_first_name", "2. Other Names Used - Row 1 - Given Name (First Name)", "text", False),
    ("Part 2. Other Names 1", "p2_2a_middle_name", "2. Other Names Used - Row 1 - Middle Name (if applicable)", "text", False),
    ("Part 2. Other Names 2", "p2_2b_last_name", "2. Other Names Used - Row 2 - Family Name (Last Name)", "text", False),
    ("Part 2. Other Names 2", "p2_2b_first_name", "2. Other Names Used - Row 2 - Given Name (First Name)", "text", False),
    ("Part 2. Other Names 2", "p2_2b_middle_name", "2. Other Names Used - Row 2 - Middle Name (if applicable)", "text", False),
    ("Part 2. Other Names 3", "p2_2c_last_name", "2. Other Names Used - Row 3 - Family Name (Last Name)", "text", False),
    ("Part 2. Other Names 3", "p2_2c_first_name", "2. Other Names Used - Row 3 - Given Name (First Name)", "text", False),
    ("Part 2. Other Names 3", "p2_2c_middle_name", "2. Other Names Used - Row 3 - Middle Name (if applicable)", "text", False),

    # Current Mailing Address
    ("Part 2. Mailing Address", "p2_3_in_care_of", "3. Current Mailing Address - In Care Of Name (if any)", "text", False),
    ("Part 2. Mailing Address", "p2_3_street", "3. Current Mailing Address - Street Number and Name", "text", True),
    ("Part 2. Mailing Address", "p2_3_apt_ste_flr", "3. Current Mailing Address - Apt. Ste. Flr.", "select", False),
    ("Part 2. Mailing Address", "p2_3_number", "3. Current Mailing Address - Number", "text", False),
    ("Part 2. Mailing Address", "p2_3_city", "3. Current Mailing Address - City or Town", "text", True),
    ("Part 2. Mailing Address", "p2_3_state", "3. Current Mailing Address - State", "select", False),
    ("Part 2. Mailing Address", "p2_3_zip", "3. Current Mailing Address - ZIP Code", "text", False),
    ("Part 2. Mailing Address", "p2_3_province", "3. Current Mailing Address - Province", "text", False),
    ("Part 2. Mailing Address", "p2_3_postal_code", "3. Current Mailing Address - Postal Code", "text", False),
    ("Part 2. Mailing Address", "p2_3_country", "3. Current Mailing Address - Country", "text", False),

    # Marital Status and Citizenship
    ("Part 2. Personal Info", "p2_4_marital_status", "4. Your Current Marital Status", "radio", True),
    ("Part 2. Personal Info", "p2_5_lost_renounced", "5. Since becoming a U.S. citizen, have you lost or renounced your U.S. citizenship in any manner?", "radio", True),

    # =========================================================================
    # PART 3: TYPE OF APPLICATION (Pages 2-3)
    # =========================================================================
    # Type of application
    ("Part 3. Application Type", "p3_1a_citizenship", "1.a. New Certificate of Citizenship", "checkbox", False),
    ("Part 3. Application Type", "p3_1b_naturalization", "1.b. New Certificate of Naturalization", "checkbox", False),
    ("Part 3. Application Type", "p3_1c_repatriation", "1.c. New Certificate of Repatriation", "checkbox", False),
    ("Part 3. Application Type", "p3_1d_declaration", "1.d. New Declaration of Intention", "checkbox", False),
    ("Part 3. Application Type", "p3_1e_special_certificate", "1.e. Special Certificate of Naturalization to Obtain Recognition of My U.S. Citizenship by a Foreign Country", "checkbox", False),

    # Basis for Application
    ("Part 3. Basis", "p3_2a_lost_stolen", "2.a. My certificate or declaration was lost, stolen, or destroyed", "checkbox", False),
    ("Part 3. Basis", "p3_2a_explanation", "2.a.(1) Provide an explanation of when, where, and how this happened", "textarea", False),
    ("Part 3. Basis", "p3_2b_mutilated", "2.b. My certificate or declaration is mutilated", "checkbox", False),
    ("Part 3. Basis", "p3_2c_uscis_error", "2.c. My certificate or declaration is incorrect due to a typographical or clerical error by USCIS", "checkbox", False),
    ("Part 3. Basis", "p3_2c_explanation", "2.c.(2) Provide an explanation of what is incorrect", "textarea", False),
    ("Part 3. Basis", "p3_2d_name_change", "2.d. My name has legally changed", "checkbox", False),
    ("Part 3. Basis", "p3_2e_dob_change", "2.e. My date of birth has legally changed through a court order or U.S. Government-issued document", "checkbox", False),
    ("Part 3. Basis", "p3_2f_sex_incorrect", "2.f. My certificate or declaration is incorrect because my sex listed on the document does not reflect my biological sex at birth", "checkbox", False),
    ("Part 3. Basis", "p3_2g_other_reason", "2.g. My reason for applying for a new document is not listed above", "checkbox", False),
    ("Part 3. Basis", "p3_2g_explanation", "2.g.(1) Provide an explanation", "textarea", False),

    # =========================================================================
    # PART 4: USCIS TYPOGRAPHICAL OR CLERICAL ERROR (Page 3)
    # =========================================================================
    ("Part 4. USCIS Error", "p4_1_name", "1. Typographical or clerical error - Name", "checkbox", False),
    ("Part 4. USCIS Error", "p4_1_dob", "1. Typographical or clerical error - Date of Birth", "checkbox", False),
    ("Part 4. USCIS Error", "p4_1_sex", "1. Typographical or clerical error - Sex", "checkbox", False),
    ("Part 4. USCIS Error", "p4_1_other", "1. Typographical or clerical error - Other", "checkbox", False),
    ("Part 4. USCIS Error", "p4_2_explanation", "2. Provide an explanation of what is incorrect on your current certificate or declaration", "textarea", False),

    # =========================================================================
    # PART 5: NAME CHANGE (Page 4)
    # =========================================================================
    ("Part 5. Name Change", "p5_1a_marriage", "1.a. My name changed through - Marriage, Divorce, or Annulment", "checkbox", False),
    ("Part 5. Name Change", "p5_1a_date", "1.a. Date of Event (mm/dd/yyyy)", "date", False),
    ("Part 5. Name Change", "p5_1b_court_order", "1.b. My name changed through - Court Order", "checkbox", False),
    ("Part 5. Name Change", "p5_1b_date", "1.b. Date of Court Order (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 6: DATE OF BIRTH CHANGE (Page 4)
    # =========================================================================
    ("Part 6. DOB Change", "p6_1a_court_order", "1.a. My date of birth changed through - Court Order", "checkbox", False),
    ("Part 6. DOB Change", "p6_1a_date", "1.a. Date of Court Order (mm/dd/yyyy)", "date", False),
    ("Part 6. DOB Change", "p6_1b_govt_document", "1.b. My date of birth changed through - U.S. Government-Issued Document", "checkbox", False),
    ("Part 6. DOB Change", "p6_1b_date", "1.b. Date of U.S. Government-Issued Document (mm/dd/yyyy)", "date", False),
    ("Part 6. DOB Change", "p6_2_new_dob", "2. My new date of birth is (as shown in the court order or U.S. Government-issued document) (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 7: SEX AT BIRTH (Page 4)
    # =========================================================================
    ("Part 7. Sex at Birth", "p7_1_sex", "1. My biological sex at birth", "radio", False),

    # =========================================================================
    # PART 8: SPECIAL CERTIFICATE FOR FOREIGN RECOGNITION (Pages 4-5)
    # =========================================================================
    ("Part 8. Foreign Recognition", "p8_1_country", "1. Name of Foreign Country", "text", False),
    ("Part 8. Foreign Recognition", "p8_2_official_last_name", "2. Information About Foreign Official - Family Name (Last Name)", "text", False),
    ("Part 8. Foreign Recognition", "p8_2_official_first_name", "2. Information About Foreign Official - Given Name (First Name)", "text", False),
    ("Part 8. Foreign Recognition", "p8_2_official_middle_name", "2. Information About Foreign Official - Middle Name (if applicable)", "text", False),
    ("Part 8. Foreign Recognition", "p8_2_official_title", "2. Information About Foreign Official - Official Title", "text", False),
    ("Part 8. Foreign Recognition", "p8_2_agency", "2. Information About Foreign Official - Name of Government Agency", "text", False),

    # Foreign Official's Address
    ("Part 8. Official Address", "p8_3_street", "3. Foreign Official's Address - Street Number and Name", "text", False),
    ("Part 8. Official Address", "p8_3_apt_ste_flr", "3. Foreign Official's Address - Apt. Ste. Flr.", "select", False),
    ("Part 8. Official Address", "p8_3_number", "3. Foreign Official's Address - Number", "text", False),
    ("Part 8. Official Address", "p8_3_city", "3. Foreign Official's Address - City or Town", "text", False),
    ("Part 8. Official Address", "p8_3_state", "3. Foreign Official's Address - State", "select", False),
    ("Part 8. Official Address", "p8_3_zip", "3. Foreign Official's Address - ZIP Code", "text", False),
    ("Part 8. Official Address", "p8_3_province", "3. Foreign Official's Address - Province", "text", False),
    ("Part 8. Official Address", "p8_3_postal_code", "3. Foreign Official's Address - Postal Code", "text", False),
    ("Part 8. Official Address", "p8_3_country", "3. Foreign Official's Address - Country", "text", False),

    # USCIS or Consular Official's Certification
    ("Part 8. USCIS Certification", "p8_4_uscis_signature", "4. USCIS or Consular Official's Certification - Signature", "text", False),
    ("Part 8. USCIS Certification", "p8_4_uscis_date", "4. USCIS or Consular Official's Certification - Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 9: APPLICANT'S CONTACT INFORMATION, CERTIFICATION, AND SIGNATURE (Page 5)
    # =========================================================================
    ("Part 9. Applicant Contact", "p9_1_daytime_phone", "1. Applicant's Daytime Telephone Number", "phone", True),
    ("Part 9. Applicant Contact", "p9_2_mobile_phone", "2. Applicant's Mobile Telephone Number (if any)", "phone", False),
    ("Part 9. Applicant Contact", "p9_3_email", "3. Applicant's Email Address (if any)", "email", False),
    ("Part 9. Applicant Contact", "p9_4_signature_date", "4. Applicant's Signature - Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 10: INTERPRETER'S CONTACT INFORMATION, CERTIFICATION, AND SIGNATURE (Page 6)
    # =========================================================================
    ("Part 10. Interpreter", "p10_1_last_name", "1. Interpreter's Full Name - Family Name (Last Name)", "text", False),
    ("Part 10. Interpreter", "p10_1_first_name", "1. Interpreter's Full Name - Given Name (First Name)", "text", False),
    ("Part 10. Interpreter", "p10_2_business", "2. Interpreter's Business or Organization Name", "text", False),
    ("Part 10. Interpreter", "p10_3_daytime_phone", "3. Interpreter's Daytime Telephone Number", "phone", False),
    ("Part 10. Interpreter", "p10_4_mobile_phone", "4. Interpreter's Mobile Telephone Number (if any)", "phone", False),
    ("Part 10. Interpreter", "p10_5_email", "5. Interpreter's Email Address (if any)", "email", False),
    ("Part 10. Interpreter", "p10_language", "Language (I am fluent in English and...)", "text", False),
    ("Part 10. Interpreter", "p10_6_signature_date", "6. Interpreter's Signature - Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 11: PREPARER'S CONTACT INFORMATION, DECLARATION, AND SIGNATURE (Page 6)
    # =========================================================================
    ("Part 11. Preparer", "p11_1_last_name", "1. Preparer's Full Name - Family Name (Last Name)", "text", False),
    ("Part 11. Preparer", "p11_1_first_name", "1. Preparer's Full Name - Given Name (First Name)", "text", False),
    ("Part 11. Preparer", "p11_2_business", "2. Preparer's Business or Organization Name", "text", False),
    ("Part 11. Preparer", "p11_3_daytime_phone", "3. Preparer's Daytime Telephone Number", "phone", False),
    ("Part 11. Preparer", "p11_4_mobile_phone", "4. Preparer's Mobile Telephone Number (if any)", "phone", False),
    ("Part 11. Preparer", "p11_5_email", "5. Preparer's Email Address (if any)", "email", False),
    ("Part 11. Preparer", "p11_6_signature_date", "6. Signature of Preparer - Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 12: ADDITIONAL INFORMATION (Page 7)
    # =========================================================================
    ("Part 12. Additional Info 1", "p12_1_last_name", "1. Family Name (Last Name)", "text", False),
    ("Part 12. Additional Info 1", "p12_1_first_name", "1. Given Name (First Name)", "text", False),
    ("Part 12. Additional Info 1", "p12_1_middle_name", "1. Middle Name", "text", False),
    ("Part 12. Additional Info 1", "p12_2_a_number", "2. A-Number (if any)", "text", False),
    ("Part 12. Additional Info 1", "p12_3_page", "3. Page Number", "text", False),
    ("Part 12. Additional Info 1", "p12_3_part", "3. Part Number", "text", False),
    ("Part 12. Additional Info 1", "p12_3_item", "3. Item Number", "text", False),
    ("Part 12. Additional Info 1", "p12_3_explanation", "3. Additional Information", "textarea", False),

    ("Part 12. Additional Info 2", "p12_4_page", "4. Page Number", "text", False),
    ("Part 12. Additional Info 2", "p12_4_part", "4. Part Number", "text", False),
    ("Part 12. Additional Info 2", "p12_4_item", "4. Item Number", "text", False),
    ("Part 12. Additional Info 2", "p12_4_explanation", "4. Additional Information", "textarea", False),

    ("Part 12. Additional Info 3", "p12_5_page", "5. Page Number", "text", False),
    ("Part 12. Additional Info 3", "p12_5_part", "5. Part Number", "text", False),
    ("Part 12. Additional Info 3", "p12_5_item", "5. Item Number", "text", False),
    ("Part 12. Additional Info 3", "p12_5_explanation", "5. Additional Information", "textarea", False),

    ("Part 12. Additional Info 4", "p12_6_page", "6. Page Number", "text", False),
    ("Part 12. Additional Info 4", "p12_6_part", "6. Part Number", "text", False),
    ("Part 12. Additional Info 4", "p12_6_item", "6. Item Number", "text", False),
    ("Part 12. Additional Info 4", "p12_6_explanation", "6. Additional Information", "textarea", False),
]


def update_n565(template_id=None):
    """Insert or update N-565 fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%N-565%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('N-565 - Application for Replacement Naturalization/Citizenship Document (EXPANDED)', "
                    "'Complete N-565 with all official USCIS fields - Edition 02/27/25') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(N565_FIELDS):
            conn.execute(text(
                "INSERT INTO questionnaire_fields (template_id, section, field_name, label, field_type, is_required, \"order\") "
                "VALUES (:tid, :section, :field_name, :label, :field_type, :is_required, :order)"
            ), {
                "tid": template_id, "section": section, "field_name": field_name,
                "label": label, "field_type": field_type, "is_required": required, "order": i + 1
            })

        conn.commit()
        print(f"N-565 expanded: template_id={template_id}, fields={len(N565_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_n565()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(N565_FIELDS)}")

    # Check for duplicate field names
    field_names = [f[1] for f in N565_FIELDS]
    duplicates = [name for name in field_names if field_names.count(name) > 1]
    if duplicates:
        print(f"\nWARNING: Duplicate field names found: {set(duplicates)}")
    else:
        print("\nNo duplicate field names found.")

    sections = {}
    for section, _, _, _, _ in N565_FIELDS:
        sections[section] = sections.get(section, 0) + 1

    print("\nFields by section:")
    for section, count in sorted(sections.items()):
        print(f"  {section}: {count}")
