#!/usr/bin/env python3
"""
Expand I-601 (Application for Waiver of Grounds of Inadmissibility) with ALL official USCIS fields.
Edition 09/21/22 - 8 pages, Parts 1-8.
"""
import json
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I601_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT YOU (Pages 1-2)
    # =========================================================================
    ("Part 1. Information About You", "p1_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("Part 1. Information About You", "p1_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("Part 1. Information About You", "p1_1c_middle_name", "1.c. Middle Name", "text", False),
    ("Part 1. Other Names Used", "p1_2a_family_name", "2.a. Family Name (Last Name) used at other times", "text", False),
    ("Part 1. Other Names Used", "p1_2b_given_name", "2.b. Given Name (First Name) used at other times", "text", False),
    ("Part 1. Other Names Used", "p1_2c_middle_name", "2.c. Middle Name used at other times", "text", False),
    ("Part 1. Information About You", "p1_3_dob", "3. Date of Birth (mm/dd/yyyy)", "date", True),
    ("Part 1. Information About You", "p1_4_country_of_birth", "4. Country of Birth", "text", True),
    ("Part 1. Information About You", "p1_5_country_of_citizenship", "5. Country of Citizenship or Nationality", "text", True),
    ("Part 1. Information About You", "p1_6_gender_male", "6. Gender - Male", "radio", False),
    ("Part 1. Information About You", "p1_6_gender_female", "6. Gender - Female", "radio", False),
    ("Part 1. Information About You", "p1_7_a_number", "7. Alien Registration Number (A-Number) (if any)", "text", False),
    ("Part 1. Information About You", "p1_8_uscis_account", "8. USCIS Online Account Number (if any)", "text", False),
    ("Part 1. Information About You", "p1_9_ssn", "9. U.S. Social Security Number (if any)", "text", False),
    ("Part 1. Information About You", "p1_10_passport_number", "10. Passport Number", "text", False),
    ("Part 1. Information About You", "p1_11_travel_doc_number", "11. Travel Document Number (if any)", "text", False),
    ("Part 1. Information About You", "p1_12_passport_country", "12. Country of Issuance for Passport or Travel Document", "text", False),
    ("Part 1. Information About You", "p1_13_passport_expiration", "13. Expiration Date for Passport or Travel Document (mm/dd/yyyy)", "date", False),

    # Mailing Address
    ("Part 1. Mailing Address", "p1_14a_street", "14.a. Street Number and Name", "text", True),
    ("Part 1. Mailing Address", "p1_14b_apt_type", "14.b. Apt./Ste./Flr.", "select", False),
    ("Part 1. Mailing Address", "p1_14b_apt_number", "14.b. Number", "text", False),
    ("Part 1. Mailing Address", "p1_14c_city", "14.c. City or Town", "text", True),
    ("Part 1. Mailing Address", "p1_14d_state", "14.d. State", "select", False),
    ("Part 1. Mailing Address", "p1_14e_zip", "14.e. ZIP Code", "text", False),
    ("Part 1. Mailing Address", "p1_14f_province", "14.f. Province (foreign address only)", "text", False),
    ("Part 1. Mailing Address", "p1_14g_postal_code", "14.g. Postal Code (foreign address only)", "text", False),
    ("Part 1. Mailing Address", "p1_14h_country", "14.h. Country", "text", True),

    # Contact
    ("Part 1. Contact Information", "p1_15_phone", "15. Daytime Telephone Number", "phone", False),
    ("Part 1. Contact Information", "p1_16_mobile", "16. Mobile Telephone Number (if any)", "phone", False),
    ("Part 1. Contact Information", "p1_17_email", "17. Email Address (if any)", "email", False),

    # Immigration History
    ("Part 1. Immigration History", "p1_18_immigration_status", "18. Current Immigration Status", "text", False),
    ("Part 1. Immigration History", "p1_19_i94_number", "19. I-94 Arrival-Departure Record Number", "text", False),
    ("Part 1. Immigration History", "p1_20_date_last_arrival", "20. Date of Last Arrival into the United States (mm/dd/yyyy)", "date", False),
    ("Part 1. Immigration History", "p1_21_place_last_entry", "21. Place of Last Entry into the United States (City and State)", "text", False),
    ("Part 1. Immigration History", "p1_22_status_at_entry", "22. Immigration Status at Last Entry", "text", False),
    ("Part 1. Immigration History", "p1_23_current_proceedings", "23. Are you currently in removal, deportation, rescission, or exclusion proceedings?", "radio", False),
    ("Part 1. Immigration History", "p1_24_previously_applied", "24. Have you previously applied for a waiver of inadmissibility?", "radio", False),
    ("Part 1. Immigration History", "p1_24a_where_applied", "24.a. Where did you apply? (City/Town, State, Country)", "text", False),
    ("Part 1. Immigration History", "p1_24b_date_applied", "24.b. Date of previous application (mm/dd/yyyy)", "date", False),
    ("Part 1. Immigration History", "p1_24c_result", "24.c. Result of previous application", "text", False),

    # =========================================================================
    # PART 2: GROUNDS OF INADMISSIBILITY (Pages 2-3)
    # =========================================================================
    ("Part 2. Grounds of Inadmissibility", "p2_1a_health", "1.a. Health-related grounds (INA 212(a)(1))", "checkbox", False),
    ("Part 2. Grounds of Inadmissibility", "p2_1b_criminal", "1.b. Criminal and related grounds (INA 212(a)(2))", "checkbox", False),
    ("Part 2. Grounds of Inadmissibility", "p2_1c_security", "1.c. Security and related grounds (INA 212(a)(3))", "checkbox", False),
    ("Part 2. Grounds of Inadmissibility", "p2_1d_public_charge", "1.d. Public charge (INA 212(a)(4))", "checkbox", False),
    ("Part 2. Grounds of Inadmissibility", "p2_1e_labor_cert", "1.e. Labor certification and qualifications for certain immigrants (INA 212(a)(5))", "checkbox", False),
    ("Part 2. Grounds of Inadmissibility", "p2_1f_illegal_entrants", "1.f. Illegal entrants and immigration violators (INA 212(a)(6))", "checkbox", False),
    ("Part 2. Grounds of Inadmissibility", "p2_1g_documentation", "1.g. Documentation requirements for immigrants (INA 212(a)(7))", "checkbox", False),
    ("Part 2. Grounds of Inadmissibility", "p2_1h_ineligible_citizenship", "1.h. Ineligible for citizenship (INA 212(a)(8))", "checkbox", False),
    ("Part 2. Grounds of Inadmissibility", "p2_1i_previously_removed", "1.i. Aliens previously removed (INA 212(a)(9))", "checkbox", False),
    ("Part 2. Grounds of Inadmissibility", "p2_1j_miscellaneous", "1.j. Miscellaneous grounds (INA 212(a)(10))", "checkbox", False),
    ("Part 2. Grounds of Inadmissibility", "p2_2_explain_grounds", "2. Explain the grounds of inadmissibility that apply to you. Include dates, details, and outcome.", "textarea", True),

    # =========================================================================
    # PART 3: INFORMATION ABOUT QUALIFYING RELATIVE(S) (Pages 3-4)
    # =========================================================================
    # Qualifying Relative 1
    ("Part 3. Qualifying Relative 1", "p3_1a_family_name", "1.a. Family Name (Last Name) of Qualifying Relative", "text", True),
    ("Part 3. Qualifying Relative 1", "p3_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("Part 3. Qualifying Relative 1", "p3_1c_middle_name", "1.c. Middle Name", "text", False),
    ("Part 3. Qualifying Relative 1", "p3_2_relationship", "2. Relationship to You", "select", True),
    ("Part 3. Qualifying Relative 1", "p3_3_status", "3. Immigration Status", "text", True),
    ("Part 3. Qualifying Relative 1", "p3_4_dob", "4. Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 3. Qualifying Relative 1", "p3_5_a_number", "5. A-Number (if any)", "text", False),

    # Qualifying Relative 2
    ("Part 3. Qualifying Relative 2", "p3_6a_family_name", "6.a. Family Name (Last Name) of Second Qualifying Relative", "text", False),
    ("Part 3. Qualifying Relative 2", "p3_6b_given_name", "6.b. Given Name (First Name)", "text", False),
    ("Part 3. Qualifying Relative 2", "p3_6c_middle_name", "6.c. Middle Name", "text", False),
    ("Part 3. Qualifying Relative 2", "p3_7_relationship", "7. Relationship to You", "select", False),
    ("Part 3. Qualifying Relative 2", "p3_8_status", "8. Immigration Status", "text", False),
    ("Part 3. Qualifying Relative 2", "p3_9_dob", "9. Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 3. Qualifying Relative 2", "p3_10_a_number", "10. A-Number (if any)", "text", False),

    # Hardship Statement
    ("Part 3. Hardship Statement", "p3_11_hardship_statement", "11. Explain how your qualifying relative(s) would experience extreme hardship if the waiver is not granted. Include details about financial, medical, educational, and other hardship factors.", "textarea", True),

    # =========================================================================
    # PART 4: ADDITIONAL INFORMATION ABOUT YOU (Page 5)
    # =========================================================================
    ("Part 4. Additional Information", "p4_1_additional_facts", "1. Provide any additional facts or information that support your application for a waiver", "textarea", False),
    ("Part 4. Additional Information", "p4_2_favorable_factors", "2. Describe any favorable factors that demonstrate you deserve a favorable exercise of discretion (e.g., family ties, length of residence, hardship, etc.)", "textarea", False),

    # =========================================================================
    # PART 5: APPLICANT'S STATEMENT, CONTACT, SIGNATURE (Page 5-6)
    # =========================================================================
    ("Part 5. Applicant Statement", "p5_1a_read_english", "1.a. I can read and understand English, and I have read and understand every question and instruction on this form", "checkbox", False),
    ("Part 5. Applicant Statement", "p5_1b_interpreter_read", "1.b. The interpreter named in Part 6 read to me every question and instruction on this form in a language in which I am fluent", "checkbox", False),
    ("Part 5. Applicant Statement", "p5_1b_language", "1.b. Language interpreted", "text", False),
    ("Part 5. Applicant Statement", "p5_2_preparer_assisted", "2. At my request, the preparer named in Part 7 prepared this form for me", "checkbox", False),
    ("Part 5. Contact Information", "p5_3_phone", "3. Daytime Telephone Number", "phone", False),
    ("Part 5. Contact Information", "p5_4_mobile", "4. Mobile Telephone Number (if any)", "phone", False),
    ("Part 5. Contact Information", "p5_5_email", "5. Email Address (if any)", "email", False),
    ("Part 5. Signature", "p5_6_signature", "6. Signature of Applicant", "text", True),
    ("Part 5. Signature", "p5_6_date", "6. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 6: INTERPRETER (Page 6)
    # =========================================================================
    ("Part 6. Interpreter Info", "p6_1a_family_name", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("Part 6. Interpreter Info", "p6_1b_given_name", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("Part 6. Interpreter Info", "p6_2_business_name", "2. Interpreter's Business or Organization Name (if any)", "text", False),
    ("Part 6. Interpreter Address", "p6_3a_street", "3.a. Street Number and Name", "text", False),
    ("Part 6. Interpreter Address", "p6_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 6. Interpreter Address", "p6_3b_apt_number", "3.b. Number", "text", False),
    ("Part 6. Interpreter Address", "p6_3c_city", "3.c. City or Town", "text", False),
    ("Part 6. Interpreter Address", "p6_3d_state", "3.d. State", "select", False),
    ("Part 6. Interpreter Address", "p6_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 6. Interpreter Address", "p6_3f_province", "3.f. Province (foreign address only)", "text", False),
    ("Part 6. Interpreter Address", "p6_3g_postal_code", "3.g. Postal Code (foreign address only)", "text", False),
    ("Part 6. Interpreter Address", "p6_3h_country", "3.h. Country (foreign address only)", "text", False),
    ("Part 6. Interpreter Contact", "p6_4_phone", "4. Interpreter's Daytime Telephone Number", "phone", False),
    ("Part 6. Interpreter Contact", "p6_5_mobile", "5. Interpreter's Mobile Telephone Number (if any)", "phone", False),
    ("Part 6. Interpreter Contact", "p6_6_email", "6. Interpreter's Email Address (if any)", "email", False),
    ("Part 6. Interpreter Certification", "p6_7_language", "7. Language interpreted", "text", False),
    ("Part 6. Interpreter Signature", "p6_8_signature", "8. Signature of Interpreter", "text", False),
    ("Part 6. Interpreter Signature", "p6_8_date", "8. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 7: PREPARER (Page 7)
    # =========================================================================
    ("Part 7. Preparer Info", "p7_1a_family_name", "1.a. Preparer's Family Name (Last Name)", "text", False),
    ("Part 7. Preparer Info", "p7_1b_given_name", "1.b. Preparer's Given Name (First Name)", "text", False),
    ("Part 7. Preparer Info", "p7_2_business_name", "2. Preparer's Business or Organization Name (if any)", "text", False),
    ("Part 7. Preparer Address", "p7_3a_street", "3.a. Street Number and Name", "text", False),
    ("Part 7. Preparer Address", "p7_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 7. Preparer Address", "p7_3b_apt_number", "3.b. Number", "text", False),
    ("Part 7. Preparer Address", "p7_3c_city", "3.c. City or Town", "text", False),
    ("Part 7. Preparer Address", "p7_3d_state", "3.d. State", "select", False),
    ("Part 7. Preparer Address", "p7_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 7. Preparer Address", "p7_3f_province", "3.f. Province (foreign address only)", "text", False),
    ("Part 7. Preparer Address", "p7_3g_postal_code", "3.g. Postal Code (foreign address only)", "text", False),
    ("Part 7. Preparer Address", "p7_3h_country", "3.h. Country (foreign address only)", "text", False),
    ("Part 7. Preparer Contact", "p7_4_phone", "4. Preparer's Daytime Telephone Number", "phone", False),
    ("Part 7. Preparer Contact", "p7_5_mobile", "5. Preparer's Mobile Telephone Number (if any)", "phone", False),
    ("Part 7. Preparer Contact", "p7_6_email", "6. Preparer's Email Address (if any)", "email", False),
    ("Part 7. Preparer Declaration", "p7_7a_not_attorney", "7.a. I am not an attorney or accredited representative but have prepared this form on behalf of the applicant", "checkbox", False),
    ("Part 7. Preparer Declaration", "p7_7b_is_attorney", "7.b. I am an attorney or accredited representative", "checkbox", False),
    ("Part 7. Preparer Signature", "p7_8_signature", "8. Signature of Preparer", "text", False),
    ("Part 7. Preparer Signature", "p7_8_date", "8. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 8: ADDITIONAL INFORMATION (Page 8)
    # =========================================================================
    ("Part 8. Additional Information", "p8_1a_family_name", "1.a. Family Name (Last Name)", "text", False),
    ("Part 8. Additional Information", "p8_1b_given_name", "1.b. Given Name (First Name)", "text", False),
    ("Part 8. Additional Information", "p8_1c_middle_name", "1.c. Middle Name", "text", False),
    ("Part 8. Additional Information", "p8_2_a_number", "2. A-Number (if any)", "text", False),
    ("Part 8. Additional Information", "p8_3a_page_1", "3.a. Page Number", "text", False),
    ("Part 8. Additional Information", "p8_3b_part_1", "3.b. Part Number", "text", False),
    ("Part 8. Additional Information", "p8_3c_item_1", "3.c. Item Number", "text", False),
    ("Part 8. Additional Information", "p8_3d_info_1", "3.d. Additional Information", "textarea", False),
    ("Part 8. Additional Information", "p8_4a_page_2", "4.a. Page Number", "text", False),
    ("Part 8. Additional Information", "p8_4b_part_2", "4.b. Part Number", "text", False),
    ("Part 8. Additional Information", "p8_4c_item_2", "4.c. Item Number", "text", False),
    ("Part 8. Additional Information", "p8_4d_info_2", "4.d. Additional Information", "textarea", False),
    ("Part 8. Additional Information", "p8_5a_page_3", "5.a. Page Number", "text", False),
    ("Part 8. Additional Information", "p8_5b_part_3", "5.b. Part Number", "text", False),
    ("Part 8. Additional Information", "p8_5c_item_3", "5.c. Item Number", "text", False),
    ("Part 8. Additional Information", "p8_5d_info_3", "5.d. Additional Information", "textarea", False),
]

OPTIONS_MAP = {
    "p1_14b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p1_14d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"],
    "p3_2_relationship": ["Spouse", "Parent", "Son/Daughter"],
    "p3_7_relationship": ["Spouse", "Parent", "Son/Daughter"],
    "p6_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p6_3d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"],
    "p7_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p7_3d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"],
}


def update_i601(template_id=None):
    """Insert or update I-601 fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-601 -%' AND name NOT LIKE '%I-601A%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('I-601 - Application for Waiver of Grounds of Inadmissibility (EXPANDED)', "
                    "'Complete I-601 with all official USCIS fields - Edition 09/21/22') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(I601_FIELDS):
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
        print(f"I-601 expanded: template_id={template_id}, fields={len(I601_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_i601()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(I601_FIELDS)}")

    sections = {}
    for section, _, _, _, _ in I601_FIELDS:
        sections[section] = sections.get(section, 0) + 1
    print("\nFields by section:")
    for section, count in sections.items():
        print(f"  {section}: {count}")

    field_names = [fn for _, fn, _, _, _ in I601_FIELDS]
    duplicates = [n for n in field_names if field_names.count(n) > 1]
    if duplicates:
        print(f"\nWARNING: Duplicate field names: {set(duplicates)}")
    else:
        print("\nNo duplicate field names found.")
