#!/usr/bin/env python3
"""
Expand I-601A (Application for Provisional Unlawful Presence Waiver) with ALL official USCIS fields.
Edition 03/08/23 - 9 pages, Parts 1-8.
"""
import json
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I601A_FIELDS = [
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
    ("Part 1. Information About You", "p1_7_marital_status", "7. Marital Status", "select", True),
    ("Part 1. Information About You", "p1_8_a_number", "8. Alien Registration Number (A-Number) (if any)", "text", False),
    ("Part 1. Information About You", "p1_9_uscis_account", "9. USCIS Online Account Number (if any)", "text", False),
    ("Part 1. Information About You", "p1_10_ssn", "10. U.S. Social Security Number (if any)", "text", False),

    # Mailing Address
    ("Part 1. Mailing Address", "p1_11a_street", "11.a. Street Number and Name", "text", True),
    ("Part 1. Mailing Address", "p1_11b_apt_type", "11.b. Apt./Ste./Flr.", "select", False),
    ("Part 1. Mailing Address", "p1_11b_apt_number", "11.b. Number", "text", False),
    ("Part 1. Mailing Address", "p1_11c_city", "11.c. City or Town", "text", True),
    ("Part 1. Mailing Address", "p1_11d_state", "11.d. State", "select", True),
    ("Part 1. Mailing Address", "p1_11e_zip", "11.e. ZIP Code", "text", True),
    ("Part 1. Mailing Address", "p1_11f_province", "11.f. Province (foreign address only)", "text", False),
    ("Part 1. Mailing Address", "p1_11g_postal_code", "11.g. Postal Code (foreign address only)", "text", False),
    ("Part 1. Mailing Address", "p1_11h_country", "11.h. Country", "text", False),

    # Contact
    ("Part 1. Contact Information", "p1_12_phone", "12. Daytime Telephone Number", "phone", False),
    ("Part 1. Contact Information", "p1_13_mobile", "13. Mobile Telephone Number (if any)", "phone", False),
    ("Part 1. Contact Information", "p1_14_email", "14. Email Address (if any)", "email", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT YOUR IMMIGRANT VISA CASE (Pages 2-3)
    # =========================================================================
    ("Part 2. Immigrant Visa Case", "p2_1_approved_petition", "1. Do you have an approved immigrant visa petition?", "radio", True),
    ("Part 2. Immigrant Visa Case", "p2_2_receipt_number", "2. Receipt Number of approved immigrant visa petition", "text", False),
    ("Part 2. Immigrant Visa Case", "p2_3_petition_type", "3. Type of immigrant visa petition approved", "text", False),
    ("Part 2. Immigrant Visa Case", "p2_4_priority_date", "4. Priority Date (mm/dd/yyyy)", "date", False),
    ("Part 2. Immigrant Visa Case", "p2_5_consular_post", "5. U.S. Embassy or Consulate where you will apply for your immigrant visa", "text", False),
    ("Part 2. Immigrant Visa Case", "p2_6_dos_case_number", "6. Department of State (DOS) Case Number (if known)", "text", False),
    ("Part 2. Immigrant Visa Case", "p2_7_nvc_case_number", "7. National Visa Center (NVC) Case Number (if known)", "text", False),
    ("Part 2. Immigrant Visa Case", "p2_8_visa_category", "8. Immigrant Visa Category", "text", False),

    # Unlawful Presence Information
    ("Part 2. Unlawful Presence", "p2_9_entry_without_inspection", "9. Did you enter the United States without inspection?", "radio", False),
    ("Part 2. Unlawful Presence", "p2_10_date_unlawful_presence_began", "10. Date your unlawful presence began (mm/dd/yyyy)", "date", False),
    ("Part 2. Unlawful Presence", "p2_11_still_present", "11. Are you still unlawfully present in the United States?", "radio", False),
    ("Part 2. Unlawful Presence", "p2_12_date_left_us", "12. If no, date you departed the United States (mm/dd/yyyy)", "date", False),
    ("Part 2. Unlawful Presence", "p2_13_removal_proceedings", "13. Have you ever been in removal proceedings?", "radio", False),
    ("Part 2. Unlawful Presence", "p2_14_previous_waiver", "14. Have you previously filed Form I-601A?", "radio", False),
    ("Part 2. Unlawful Presence", "p2_14a_previous_result", "14.a. Result of previous Form I-601A", "text", False),

    # =========================================================================
    # PART 3: INFORMATION ABOUT YOUR QUALIFYING RELATIVE (Pages 3-4)
    # =========================================================================
    ("Part 3. Qualifying Relative", "p3_1a_family_name", "1.a. Family Name (Last Name) of Qualifying Relative", "text", True),
    ("Part 3. Qualifying Relative", "p3_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("Part 3. Qualifying Relative", "p3_1c_middle_name", "1.c. Middle Name", "text", False),
    ("Part 3. Qualifying Relative", "p3_2_relationship", "2. Relationship to You", "select", True),
    ("Part 3. Qualifying Relative", "p3_3_dob", "3. Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 3. Qualifying Relative", "p3_4_country_of_birth", "4. Country of Birth", "text", False),
    ("Part 3. Qualifying Relative", "p3_5_citizenship_status", "5. U.S. Citizenship/Lawful Permanent Resident Status", "select", True),
    ("Part 3. Qualifying Relative", "p3_6_a_number", "6. A-Number (if any)", "text", False),
    ("Part 3. Qualifying Relative", "p3_7_ssn", "7. U.S. Social Security Number (if any)", "text", False),

    # Qualifying Relative Address
    ("Part 3. Qualifying Relative Address", "p3_8a_street", "8.a. Street Number and Name", "text", False),
    ("Part 3. Qualifying Relative Address", "p3_8b_apt_type", "8.b. Apt./Ste./Flr.", "select", False),
    ("Part 3. Qualifying Relative Address", "p3_8b_apt_number", "8.b. Number", "text", False),
    ("Part 3. Qualifying Relative Address", "p3_8c_city", "8.c. City or Town", "text", False),
    ("Part 3. Qualifying Relative Address", "p3_8d_state", "8.d. State", "select", False),
    ("Part 3. Qualifying Relative Address", "p3_8e_zip", "8.e. ZIP Code", "text", False),

    # Hardship
    ("Part 3. Extreme Hardship", "p3_9_hardship_statement", "9. Explain the extreme hardship your qualifying relative would suffer if the waiver is not granted", "textarea", True),

    # =========================================================================
    # PART 4: ADDITIONAL INFORMATION (Page 5)
    # =========================================================================
    ("Part 4. Additional Information", "p4_1_additional_facts", "1. Provide any additional information that supports your application", "textarea", False),

    # =========================================================================
    # PART 5: APPLICANT'S STATEMENT, CONTACT, SIGNATURE (Pages 5-6)
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
    # PART 6: INTERPRETER (Page 7)
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
    # PART 7: PREPARER (Pages 7-8)
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
    # PART 8: ADDITIONAL INFORMATION (Page 9)
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
    "p1_7_marital_status": ["Single, Never Married", "Married", "Divorced", "Widowed", "Separated", "Marriage Annulled"],
    "p1_11b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p1_11d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"],
    "p3_2_relationship": ["Spouse", "Parent"],
    "p3_5_citizenship_status": ["U.S. Citizen", "Lawful Permanent Resident"],
    "p3_8b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p3_8d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"],
    "p6_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p6_3d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"],
    "p7_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p7_3d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"],
}


def update_i601a(template_id=None):
    """Insert or update I-601A fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-601A%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('I-601A - Application for Provisional Unlawful Presence Waiver (EXPANDED)', "
                    "'Complete I-601A with all official USCIS fields - Edition 03/08/23') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(I601A_FIELDS):
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
        print(f"I-601A expanded: template_id={template_id}, fields={len(I601A_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_i601a()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(I601A_FIELDS)}")

    sections = {}
    for section, _, _, _, _ in I601A_FIELDS:
        sections[section] = sections.get(section, 0) + 1
    print("\nFields by section:")
    for section, count in sections.items():
        print(f"  {section}: {count}")

    field_names = [fn for _, fn, _, _, _ in I601A_FIELDS]
    duplicates = [n for n in field_names if field_names.count(n) > 1]
    if duplicates:
        print(f"\nWARNING: Duplicate field names: {set(duplicates)}")
    else:
        print("\nNo duplicate field names found.")
