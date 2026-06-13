#!/usr/bin/env python3
"""
Expand I-90 (Application to Replace Permanent Resident Card) with ALL official USCIS fields.
Edition 01/20/25 - 7 pages, Parts 1-8.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I90_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT YOU (Pages 1-2)
    # =========================================================================
    ("1. Basic Info", "p1_1_a_number", "1. Alien Registration Number (A-Number)", "text", True),
    ("1. Basic Info", "p1_2_uscis_account", "2. USCIS Online Account Number (if any)", "text", False),

    # Your Full Name
    ("1. Your Full Name", "p1_3a_family_name", "3.a. Family Name (Last Name)", "text", True),
    ("1. Your Full Name", "p1_3b_given_name", "3.b. Given Name (First Name)", "text", True),
    ("1. Your Full Name", "p1_3c_middle_name", "3.c. Middle Name", "text", False),

    # Name Change
    ("1. Name Change", "p1_4_name_changed", "4. Has your name legally changed since the issuance of your Permanent Resident Card?", "radio", True),

    # Name on Current Card (if name changed)
    ("1. Name on Current Card", "p1_5a_family_name", "5.a. Name on Current Card - Family Name (Last Name)", "text", False),
    ("1. Name on Current Card", "p1_5b_given_name", "5.b. Name on Current Card - Given Name (First Name)", "text", False),
    ("1. Name on Current Card", "p1_5c_middle_name", "5.c. Name on Current Card - Middle Name", "text", False),

    # Mailing Address
    ("1. Mailing Address", "p1_6a_in_care_of", "6.a. In Care Of Name", "text", False),
    ("1. Mailing Address", "p1_6b_street", "6.b. Street Number and Name", "text", True),
    ("1. Mailing Address", "p1_6c_apt", "6.c. Apt. / Ste. / Flr.", "select", False),
    ("1. Mailing Address", "p1_6c_number", "6.c. Number", "text", False),
    ("1. Mailing Address", "p1_6d_city", "6.d. City or Town", "text", True),
    ("1. Mailing Address", "p1_6e_state", "6.e. State", "select", True),
    ("1. Mailing Address", "p1_6f_zip", "6.f. ZIP Code", "text", True),
    ("1. Mailing Address", "p1_6g_province", "6.g. Province", "text", False),
    ("1. Mailing Address", "p1_6h_postal_code", "6.h. Postal Code", "text", False),
    ("1. Mailing Address", "p1_6i_country", "6.i. Country", "text", False),

    # Physical Address
    ("1. Physical Address", "p1_7a_street", "7.a. Street Number and Name", "text", False),
    ("1. Physical Address", "p1_7b_apt", "7.b. Apt. / Ste. / Flr.", "select", False),
    ("1. Physical Address", "p1_7b_number", "7.b. Number", "text", False),
    ("1. Physical Address", "p1_7c_city", "7.c. City or Town", "text", False),
    ("1. Physical Address", "p1_7d_state", "7.d. State", "select", False),
    ("1. Physical Address", "p1_7e_zip", "7.e. ZIP Code", "text", False),
    ("1. Physical Address", "p1_7f_province", "7.f. Province", "text", False),
    ("1. Physical Address", "p1_7g_postal_code", "7.g. Postal Code", "text", False),
    ("1. Physical Address", "p1_7h_country", "7.h. Country", "text", False),

    # Additional Information
    ("1. Additional Info", "p1_8_sex", "8. Sex", "radio", True),
    ("1. Additional Info", "p1_9_dob", "9. Date of Birth (mm/dd/yyyy)", "date", True),
    ("1. Additional Info", "p1_10_city_birth", "10. City/Town/Village of Birth", "text", True),
    ("1. Additional Info", "p1_11_country_birth", "11. Country of Birth", "text", True),

    # Parents
    ("1. Parents", "p1_12_mother_given_name", "12. Mother's Given Name (First Name)", "text", False),
    ("1. Parents", "p1_13_father_given_name", "13. Father's Given Name (First Name)", "text", False),

    # Immigration Info
    ("1. Immigration Info", "p1_14_class_admission", "14. Class of Admission", "text", False),
    ("1. Immigration Info", "p1_15_date_admission", "15. Date of Admission (mm/dd/yyyy)", "date", False),
    ("1. Immigration Info", "p1_16_ssn", "16. U.S. Social Security Number (if any)", "text", False),

    # =========================================================================
    # PART 2: APPLICATION TYPE (Pages 2-3)
    # =========================================================================
    # My Status Is
    ("2. Status", "p2_1a_lpr", "1.a. Lawful Permanent Resident (Proceed to Section A.)", "checkbox", False),
    ("2. Status", "p2_1b_commuter", "1.b. Permanent Resident - In Commuter Status (Proceed to Section A.)", "checkbox", False),
    ("2. Status", "p2_1c_conditional", "1.c. Conditional Permanent Resident (Proceed to Section B.)", "checkbox", False),

    # Section A - Reason for Application (LPR/Commuter)
    ("2A. Reason - LPR", "p2_2a_lost", "2.a. My previous card has been lost, stolen, or destroyed.", "checkbox", False),
    ("2A. Reason - LPR", "p2_2b_never_received", "2.b. My previous card was issued but never received.", "checkbox", False),
    ("2A. Reason - LPR", "p2_2c_mutilated", "2.c. My existing card has been mutilated.", "checkbox", False),
    ("2A. Reason - LPR", "p2_2d_dhs_error", "2.d. My existing card has incorrect data because of Department of Homeland Security (DHS) error.", "checkbox", False),
    ("2A. Reason - LPR", "p2_2e_bio_changed", "2.e. My name or other biographic information has been legally changed since issuance of my existing card.", "checkbox", False),
    ("2A. Reason - LPR", "p2_2f_expired", "2.f. My existing card has already expired or will expire within six months.", "checkbox", False),
    ("2A. Reason - LPR", "p2_2g1_14th_after_16", "2.g.1. I have reached my 14th birthday and am registering as required. My existing card will expire AFTER my 16th birthday.", "checkbox", False),
    ("2A. Reason - LPR", "p2_2g2_14th_before_16", "2.g.2. I have reached my 14th birthday and am registering as required. My existing card will expire BEFORE my 16th birthday.", "checkbox", False),
    ("2A. Reason - LPR", "p2_2h1_taking_commuter", "2.h.1. I am a permanent resident who is taking up commuter status.", "checkbox", False),
    ("2A. Reason - LPR", "p2_2h1a_poe", "2.h.1.a. My Port-of-Entry (POE) into the United States will be: City or Town and State", "text", False),
    ("2A. Reason - LPR", "p2_2h2_taking_residence", "2.h.2. I am a commuter who is taking up actual residence in the United States.", "checkbox", False),
    ("2A. Reason - LPR", "p2_2i_auto_converted", "2.i. I have been automatically converted to lawful permanent resident status.", "checkbox", False),
    ("2A. Reason - LPR", "p2_2j_other_reason", "2.j. I have a prior edition of the Alien Registration Card, or I am applying to replace my current Permanent Resident Card for a reason that is not specified above.", "checkbox", False),

    # Section B - Reason for Application (Conditional PR)
    ("2B. Reason - Conditional", "p2_3a_lost", "3.a. My previous card has been lost, stolen, or destroyed.", "checkbox", False),
    ("2B. Reason - Conditional", "p2_3b_never_received", "3.b. My previous card was issued but never received.", "checkbox", False),
    ("2B. Reason - Conditional", "p2_3c_mutilated", "3.c. My existing card has been mutilated.", "checkbox", False),
    ("2B. Reason - Conditional", "p2_3d_dhs_error", "3.d. My existing card has incorrect data because of DHS error.", "checkbox", False),
    ("2B. Reason - Conditional", "p2_3e_bio_changed", "3.e. My name or other biographic information has legally changed since the issuance of my existing card.", "checkbox", False),

    # =========================================================================
    # PART 3: PROCESSING INFORMATION (Page 3)
    # =========================================================================
    ("3. Processing", "p3_1_location_applied", "1. Location where you applied for an immigrant visa or adjustment of status:", "text", False),
    ("3. Processing", "p3_2_location_issued", "2. Location where your immigrant visa was issued or USCIS office where you were granted adjustment of status:", "text", False),
    ("3. Processing", "p3_3a_destination", "3.a. Destination in the United States at time of admission", "text", False),
    ("3. Processing", "p3_3a1_poe", "3.a.1. Port-of-Entry where admitted to the United States: City or Town and State", "text", False),
    ("3. Processing", "p3_4_removal_proceedings", "4. Have you ever been in exclusion, deportation, or removal proceedings or ordered removed from the United States?", "radio", False),
    ("3. Processing", "p3_5_abandoned_status", "5. Since you were granted permanent residence, have you ever filed Form I-407, Abandonment by Alien of Status as Lawful Permanent Resident, or otherwise been determined to have abandoned your status?", "radio", False),

    # Biographic Information
    ("3. Biographic", "p3_6_ethnicity", "6. Ethnicity", "radio", True),
    ("3. Biographic", "p3_7_race_white", "7. Race - White", "checkbox", False),
    ("3. Biographic", "p3_7_race_asian", "7. Race - Asian", "checkbox", False),
    ("3. Biographic", "p3_7_race_black", "7. Race - Black or African American", "checkbox", False),
    ("3. Biographic", "p3_7_race_native_american", "7. Race - American Indian or Alaska Native", "checkbox", False),
    ("3. Biographic", "p3_7_race_pacific", "7. Race - Native Hawaiian or Other Pacific Islander", "checkbox", False),
    ("3. Biographic", "p3_8_height_feet", "8. Height - Feet", "text", True),
    ("3. Biographic", "p3_8_height_inches", "8. Height - Inches", "text", True),
    ("3. Biographic", "p3_9_weight", "9. Weight - Pounds", "text", True),
    ("3. Biographic", "p3_10_eye_color", "10. Eye Color", "radio", True),
    ("3. Biographic", "p3_11_hair_color", "11. Hair Color", "radio", True),

    # =========================================================================
    # PART 4: ACCOMMODATIONS FOR INDIVIDUALS WITH DISABILITIES (Pages 3-4)
    # =========================================================================
    ("4. Accommodations", "p4_1_requesting", "1. Are you requesting an accommodation because of your disabilities and/or impairments?", "radio", False),
    ("4. Accommodations", "p4_1a_deaf", "1.a. I am deaf or hard of hearing and request the following accommodation (If you are requesting a sign-language interpreter, indicate for which language):", "textarea", False),
    ("4. Accommodations", "p4_1b_blind", "1.b. I am blind or have low vision and request the following accommodation:", "textarea", False),
    ("4. Accommodations", "p4_1c_other", "1.c. I have another type of disability and/or impairment (Describe the nature of your disability and/or impairment and the accommodation you are requesting):", "textarea", False),

    # =========================================================================
    # PART 5: APPLICANT'S STATEMENT, CONTACT INFO, CERTIFICATION, SIGNATURE (Page 4)
    # =========================================================================
    # Applicant's Statement
    ("5. Statement", "p5_1a_english", "1.a. I can read and understand English, and I have read and understand every question and instruction on this application and my answer to every question.", "checkbox", False),
    ("5. Statement", "p5_1b_interpreter", "1.b. The interpreter named in Part 6. read to me every question and instruction on this application and my answer to every question in [language], a language in which I am fluent and I understood everything.", "checkbox", False),
    ("5. Statement", "p5_1b_language", "1.b. Language", "text", False),
    ("5. Statement", "p5_2_preparer", "2. At my request, the preparer named in Part 7., prepared this application for me based only upon information I provided or authorized.", "checkbox", False),

    # Applicant's Contact Information
    ("5. Contact", "p5_3_phone", "3. Applicant's Daytime Telephone Number", "phone", False),
    ("5. Contact", "p5_4_mobile", "4. Applicant's Mobile Telephone Number (if any)", "phone", False),
    ("5. Contact", "p5_5_email", "5. Applicant's Email Address (if any)", "text", False),

    # Applicant's Signature
    ("5. Signature", "p5_6a_signature", "6.a. Applicant's Signature", "text", True),
    ("5. Signature", "p5_6b_date", "6.b. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 6: INTERPRETER'S CONTACT INFORMATION, CERTIFICATION, AND SIGNATURE (Page 5)
    # =========================================================================
    # Interpreter's Full Name
    ("6. Interpreter Name", "p6_1a_family_name", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("6. Interpreter Name", "p6_1b_given_name", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("6. Interpreter Name", "p6_2_organization", "2. Interpreter's Business or Organization Name (if any)", "text", False),

    # Interpreter's Mailing Address
    ("6. Interpreter Address", "p6_3a_street", "3.a. Street Number and Name", "text", False),
    ("6. Interpreter Address", "p6_3b_apt", "3.b. Apt. / Ste. / Flr.", "select", False),
    ("6. Interpreter Address", "p6_3b_number", "3.b. Number", "text", False),
    ("6. Interpreter Address", "p6_3c_city", "3.c. City or Town", "text", False),
    ("6. Interpreter Address", "p6_3d_state", "3.d. State", "select", False),
    ("6. Interpreter Address", "p6_3e_zip", "3.e. ZIP Code", "text", False),
    ("6. Interpreter Address", "p6_3f_province", "3.f. Province", "text", False),
    ("6. Interpreter Address", "p6_3g_postal_code", "3.g. Postal Code", "text", False),
    ("6. Interpreter Address", "p6_3h_country", "3.h. Country", "text", False),

    # Interpreter's Contact Information
    ("6. Interpreter Contact", "p6_4_phone", "4. Interpreter's Daytime Telephone Number", "phone", False),
    ("6. Interpreter Contact", "p6_5_mobile", "5. Interpreter's Mobile Telephone Number (if any)", "phone", False),
    ("6. Interpreter Contact", "p6_6_email", "6. Interpreter's Email Address (if any)", "text", False),

    # Interpreter's Certification and Signature
    ("6. Interpreter Signature", "p6_7a_signature", "7.a. Interpreter's Signature", "text", False),
    ("6. Interpreter Signature", "p6_7b_date", "7.b. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 7: PREPARER'S CONTACT INFORMATION, DECLARATION, AND SIGNATURE (Pages 5-6)
    # =========================================================================
    # Preparer's Full Name
    ("7. Preparer Name", "p7_1a_family_name", "1.a. Preparer's Family Name (Last Name)", "text", False),
    ("7. Preparer Name", "p7_1b_given_name", "1.b. Preparer's Given Name (First Name)", "text", False),
    ("7. Preparer Name", "p7_2_organization", "2. Preparer's Business or Organization Name (if any)", "text", False),

    # Preparer's Mailing Address
    ("7. Preparer Address", "p7_3a_street", "3.a. Street Number and Name", "text", False),
    ("7. Preparer Address", "p7_3b_apt", "3.b. Apt. / Ste. / Flr.", "select", False),
    ("7. Preparer Address", "p7_3b_number", "3.b. Number", "text", False),
    ("7. Preparer Address", "p7_3c_city", "3.c. City or Town", "text", False),
    ("7. Preparer Address", "p7_3d_state", "3.d. State", "select", False),
    ("7. Preparer Address", "p7_3e_zip", "3.e. ZIP Code", "text", False),
    ("7. Preparer Address", "p7_3f_province", "3.f. Province", "text", False),
    ("7. Preparer Address", "p7_3g_postal_code", "3.g. Postal Code", "text", False),
    ("7. Preparer Address", "p7_3h_country", "3.h. Country", "text", False),

    # Preparer's Contact Information
    ("7. Preparer Contact", "p7_4_phone", "4. Preparer's Daytime Telephone Number", "phone", False),
    ("7. Preparer Contact", "p7_5_mobile", "5. Preparer's Mobile Telephone Number (if any)", "phone", False),
    ("7. Preparer Contact", "p7_6_email", "6. Preparer's Email Address (if any)", "text", False),

    # Preparer's Statement
    ("7. Preparer Statement", "p7_7a_not_attorney", "7.a. I am not an attorney or accredited representative but have prepared this application on behalf of the applicant and with the applicant's consent.", "checkbox", False),
    ("7. Preparer Statement", "p7_7b_attorney", "7.b. I am an attorney or accredited representative and my representation of the applicant in this case", "checkbox", False),
    ("7. Preparer Statement", "p7_7b_extends", "7.b. extends beyond the preparation of this application", "checkbox", False),
    ("7. Preparer Statement", "p7_7b_not_extend", "7.b. does not extend beyond the preparation of this application", "checkbox", False),

    # Preparer's Signature
    ("7. Preparer Signature", "p7_8a_signature", "8.a. Preparer's Signature", "text", False),
    ("7. Preparer Signature", "p7_8b_date", "8.b. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 8: ADDITIONAL INFORMATION (Page 7)
    # =========================================================================
    # Your Full Name (for Additional Info)
    ("8. Additional Info Header", "p8_1a_family_name", "1.a. Family Name (Last Name)", "text", False),
    ("8. Additional Info Header", "p8_1b_given_name", "1.b. Given Name (First Name)", "text", False),
    ("8. Additional Info Header", "p8_1c_middle_name", "1.c. Middle Name", "text", False),
    ("8. Additional Info Header", "p8_2_a_number", "2. A-Number (if any)", "text", False),

    # Additional Information Fields (7 sets)
    ("8. Additional Info 1", "p8_3a_page", "3.a. Page Number", "text", False),
    ("8. Additional Info 1", "p8_3b_part", "3.b. Part Number", "text", False),
    ("8. Additional Info 1", "p8_3c_item", "3.c. Item Number", "text", False),
    ("8. Additional Info 1", "p8_3d_additional", "3.d. Additional Information", "textarea", False),

    ("8. Additional Info 2", "p8_4a_page", "4.a. Page Number", "text", False),
    ("8. Additional Info 2", "p8_4b_part", "4.b. Part Number", "text", False),
    ("8. Additional Info 2", "p8_4c_item", "4.c. Item Number", "text", False),
    ("8. Additional Info 2", "p8_4d_additional", "4.d. Additional Information", "textarea", False),

    ("8. Additional Info 3", "p8_5a_page", "5.a. Page Number", "text", False),
    ("8. Additional Info 3", "p8_5b_part", "5.b. Part Number", "text", False),
    ("8. Additional Info 3", "p8_5c_item", "5.c. Item Number", "text", False),
    ("8. Additional Info 3", "p8_5d_additional", "5.d. Additional Information", "textarea", False),

    ("8. Additional Info 4", "p8_6a_page", "6.a. Page Number", "text", False),
    ("8. Additional Info 4", "p8_6b_part", "6.b. Part Number", "text", False),
    ("8. Additional Info 4", "p8_6c_item", "6.c. Item Number", "text", False),
    ("8. Additional Info 4", "p8_6d_additional", "6.d. Additional Information", "textarea", False),

    ("8. Additional Info 5", "p8_7a_page", "7.a. Page Number", "text", False),
    ("8. Additional Info 5", "p8_7b_part", "7.b. Part Number", "text", False),
    ("8. Additional Info 5", "p8_7c_item", "7.c. Item Number", "text", False),
    ("8. Additional Info 5", "p8_7d_additional", "7.d. Additional Information", "textarea", False),
]


def update_i90(template_id=None):
    """Insert or update I-90 fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-90%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('I-90 - Application to Replace Permanent Resident Card (EXPANDED)', "
                    "'Complete I-90 with all official USCIS fields - Edition 01/20/25') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(I90_FIELDS):
            conn.execute(text(
                "INSERT INTO questionnaire_fields (template_id, section, field_name, label, field_type, is_required, \"order\") "
                "VALUES (:tid, :section, :field_name, :label, :field_type, :is_required, :order)"
            ), {
                "tid": template_id, "section": section, "field_name": field_name,
                "label": label, "field_type": field_type, "is_required": required, "order": i + 1
            })

        conn.commit()
        print(f"I-90 expanded: template_id={template_id}, fields={len(I90_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_i90()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(I90_FIELDS)}")

    sections = {}
    for section, _, _, _, _ in I90_FIELDS:
        sections[section] = sections.get(section, 0) + 1

    print("\nFields by section:")
    for section, count in sections.items():
        print(f"  {section}: {count}")

    # Check for duplicates
    field_names = [field_name for _, field_name, _, _, _ in I90_FIELDS]
    duplicates = [name for name in field_names if field_names.count(name) > 1]
    if duplicates:
        print(f"\nWARNING: Duplicate field names found: {set(duplicates)}")
    else:
        print("\nNo duplicate field names - validation passed!")
