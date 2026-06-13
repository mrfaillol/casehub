#!/usr/bin/env python3
"""
Expand I-526 (Immigrant Petition by Standalone Investor) with ALL official USCIS fields.
Edition 03/05/24 - 11 pages, Parts 1-9.
Note: As of March 2022, USCIS replaced I-526 with I-526E for new filings under the
EB-5 Reform and Integrity Act. This script covers the I-526 fields for legacy cases.
"""
import json
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I526_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT YOU (Pages 1-2)
    # =========================================================================
    ("Part 1. Information About You", "p1_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("Part 1. Information About You", "p1_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("Part 1. Information About You", "p1_1c_middle_name", "1.c. Middle Name", "text", False),
    ("Part 1. Other Names Used", "p1_2a_family_name", "2.a. Other Family Names Used (if any)", "text", False),
    ("Part 1. Other Names Used", "p1_2b_given_name", "2.b. Other Given Names Used (if any)", "text", False),
    ("Part 1. Information About You", "p1_3_dob", "3. Date of Birth (mm/dd/yyyy)", "date", True),
    ("Part 1. Information About You", "p1_4_country_of_birth", "4. Country of Birth", "text", True),
    ("Part 1. Information About You", "p1_5_country_of_citizenship", "5. Country of Citizenship or Nationality", "text", True),
    ("Part 1. Information About You", "p1_6_gender_male", "6. Gender - Male", "radio", False),
    ("Part 1. Information About You", "p1_6_gender_female", "6. Gender - Female", "radio", False),
    ("Part 1. Information About You", "p1_7_a_number", "7. Alien Registration Number (A-Number) (if any)", "text", False),
    ("Part 1. Information About You", "p1_8_uscis_account", "8. USCIS Online Account Number (if any)", "text", False),
    ("Part 1. Information About You", "p1_9_ssn", "9. U.S. Social Security Number (if any)", "text", False),

    # Physical Address Abroad
    ("Part 1. Address Abroad", "p1_10a_street", "10.a. Street Number and Name", "text", False),
    ("Part 1. Address Abroad", "p1_10b_apt_type", "10.b. Apt./Ste./Flr.", "select", False),
    ("Part 1. Address Abroad", "p1_10b_apt_number", "10.b. Number", "text", False),
    ("Part 1. Address Abroad", "p1_10c_city", "10.c. City or Town", "text", False),
    ("Part 1. Address Abroad", "p1_10d_province", "10.d. Province", "text", False),
    ("Part 1. Address Abroad", "p1_10e_postal_code", "10.e. Postal Code", "text", False),
    ("Part 1. Address Abroad", "p1_10f_country", "10.f. Country", "text", False),

    # U.S. Address
    ("Part 1. U.S. Address", "p1_11a_street", "11.a. Street Number and Name", "text", False),
    ("Part 1. U.S. Address", "p1_11b_apt_type", "11.b. Apt./Ste./Flr.", "select", False),
    ("Part 1. U.S. Address", "p1_11b_apt_number", "11.b. Number", "text", False),
    ("Part 1. U.S. Address", "p1_11c_city", "11.c. City or Town", "text", False),
    ("Part 1. U.S. Address", "p1_11d_state", "11.d. State", "select", False),
    ("Part 1. U.S. Address", "p1_11e_zip", "11.e. ZIP Code", "text", False),

    # Contact
    ("Part 1. Contact Information", "p1_12_phone", "12. Daytime Telephone Number", "phone", False),
    ("Part 1. Contact Information", "p1_13_mobile", "13. Mobile Telephone Number (if any)", "phone", False),
    ("Part 1. Contact Information", "p1_14_email", "14. Email Address (if any)", "email", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT THE PETITION (Pages 3-4)
    # =========================================================================
    ("Part 2. Petition Type", "p2_1a_new_commercial_enterprise", "1.a. I am filing this petition based on my investment in a new commercial enterprise that I established", "checkbox", False),
    ("Part 2. Petition Type", "p2_1b_regional_center", "1.b. I am filing this petition based on my investment in a new commercial enterprise associated with an approved Regional Center", "checkbox", False),
    ("Part 2. Petition Type", "p2_2_tea", "2. Is the new commercial enterprise located in a Targeted Employment Area (TEA)?", "radio", False),
    ("Part 2. Petition Type", "p2_3_investment_amount", "3. Amount of my investment in U.S. dollars ($)", "text", True),
    ("Part 2. Petition Type", "p2_4_jobs_created", "4. Number of full-time jobs to be created", "number", True),
    ("Part 2. Petition Type", "p2_5_jobs_created_directly", "5. How many jobs will be created directly?", "number", False),
    ("Part 2. Petition Type", "p2_6_jobs_created_indirectly", "6. How many jobs will be created indirectly?", "number", False),

    # =========================================================================
    # PART 3: INFORMATION ABOUT THE NEW COMMERCIAL ENTERPRISE (Pages 4-5)
    # =========================================================================
    ("Part 3. New Commercial Enterprise", "p3_1_enterprise_name", "1. Name of the New Commercial Enterprise", "text", True),
    ("Part 3. New Commercial Enterprise", "p3_2_type_of_entity", "2. Type of Business Entity", "select", True),
    ("Part 3. New Commercial Enterprise", "p3_3_date_established", "3. Date Enterprise Was Established (mm/dd/yyyy)", "date", False),
    ("Part 3. New Commercial Enterprise", "p3_4_ein", "4. Employer Identification Number (EIN)", "text", False),

    # Enterprise Address
    ("Part 3. Enterprise Address", "p3_5a_street", "5.a. Street Number and Name", "text", True),
    ("Part 3. Enterprise Address", "p3_5b_apt_type", "5.b. Ste./Flr.", "select", False),
    ("Part 3. Enterprise Address", "p3_5b_apt_number", "5.b. Number", "text", False),
    ("Part 3. Enterprise Address", "p3_5c_city", "5.c. City or Town", "text", True),
    ("Part 3. Enterprise Address", "p3_5d_state", "5.d. State", "select", True),
    ("Part 3. Enterprise Address", "p3_5e_zip", "5.e. ZIP Code", "text", True),

    # Enterprise Details
    ("Part 3. Enterprise Details", "p3_6_naics_code", "6. NAICS Code", "text", False),
    ("Part 3. Enterprise Details", "p3_7_nature_of_business", "7. Nature of Business", "text", True),
    ("Part 3. Enterprise Details", "p3_8_date_investment", "8. Date of Investment (mm/dd/yyyy)", "date", False),
    ("Part 3. Enterprise Details", "p3_9_currently_employees", "9. Current number of employees", "number", False),

    # =========================================================================
    # PART 4: INFORMATION ABOUT THE JOB-CREATING ENTITY (Pages 5-6)
    # =========================================================================
    ("Part 4. Job-Creating Entity", "p4_1_same_as_enterprise", "1. Is the job-creating entity the same as the new commercial enterprise?", "radio", False),
    ("Part 4. Job-Creating Entity", "p4_2_entity_name", "2. Name of Job-Creating Entity (if different)", "text", False),
    ("Part 4. Job-Creating Entity", "p4_3_type_of_entity", "3. Type of Business Entity", "select", False),
    ("Part 4. Job-Creating Entity", "p4_4_ein", "4. Employer Identification Number (EIN)", "text", False),

    # Job-Creating Entity Address
    ("Part 4. Entity Address", "p4_5a_street", "5.a. Street Number and Name", "text", False),
    ("Part 4. Entity Address", "p4_5b_apt_type", "5.b. Ste./Flr.", "select", False),
    ("Part 4. Entity Address", "p4_5b_apt_number", "5.b. Number", "text", False),
    ("Part 4. Entity Address", "p4_5c_city", "5.c. City or Town", "text", False),
    ("Part 4. Entity Address", "p4_5d_state", "5.d. State", "select", False),
    ("Part 4. Entity Address", "p4_5e_zip", "5.e. ZIP Code", "text", False),

    ("Part 4. Entity Details", "p4_6_nature_of_business", "6. Nature of Business", "text", False),
    ("Part 4. Entity Details", "p4_7_current_employees", "7. Current number of employees", "number", False),
    ("Part 4. Entity Details", "p4_8_naics_code", "8. NAICS Code", "text", False),

    # =========================================================================
    # PART 5: REGIONAL CENTER INFORMATION (Page 6)
    # =========================================================================
    ("Part 5. Regional Center", "p5_1_rc_name", "1. Name of Regional Center", "text", False),
    ("Part 5. Regional Center", "p5_2_rc_id", "2. Regional Center ID Number", "text", False),
    ("Part 5. Regional Center", "p5_3_rc_approval_date", "3. Date of Regional Center Approval (mm/dd/yyyy)", "date", False),
    ("Part 5. Regional Center", "p5_4_project_name", "4. Name of the Investment Project", "text", False),

    # =========================================================================
    # PART 6: PETITIONER'S STATEMENT, CONTACT, SIGNATURE (Pages 7-8)
    # =========================================================================
    ("Part 6. Petitioner Statement", "p6_1a_read_english", "1.a. I can read and understand English, and I have read and understand every question and instruction on this form", "checkbox", False),
    ("Part 6. Petitioner Statement", "p6_1b_interpreter_read", "1.b. The interpreter named in Part 7 read to me every question and instruction on this form in a language in which I am fluent", "checkbox", False),
    ("Part 6. Petitioner Statement", "p6_1b_language", "1.b. Language interpreted", "text", False),
    ("Part 6. Petitioner Statement", "p6_2_preparer_assisted", "2. At my request, the preparer named in Part 8 prepared this form for me", "checkbox", False),
    ("Part 6. Contact Information", "p6_3_phone", "3. Daytime Telephone Number", "phone", False),
    ("Part 6. Contact Information", "p6_4_mobile", "4. Mobile Telephone Number (if any)", "phone", False),
    ("Part 6. Contact Information", "p6_5_email", "5. Email Address (if any)", "email", False),
    ("Part 6. Signature", "p6_6_signature", "6. Signature of Petitioner", "text", True),
    ("Part 6. Signature", "p6_6_date", "6. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 7: INTERPRETER (Page 8)
    # =========================================================================
    ("Part 7. Interpreter Info", "p7_1a_family_name", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("Part 7. Interpreter Info", "p7_1b_given_name", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("Part 7. Interpreter Info", "p7_2_business_name", "2. Interpreter's Business or Organization Name (if any)", "text", False),
    ("Part 7. Interpreter Address", "p7_3a_street", "3.a. Street Number and Name", "text", False),
    ("Part 7. Interpreter Address", "p7_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 7. Interpreter Address", "p7_3b_apt_number", "3.b. Number", "text", False),
    ("Part 7. Interpreter Address", "p7_3c_city", "3.c. City or Town", "text", False),
    ("Part 7. Interpreter Address", "p7_3d_state", "3.d. State", "select", False),
    ("Part 7. Interpreter Address", "p7_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 7. Interpreter Address", "p7_3f_province", "3.f. Province (foreign address only)", "text", False),
    ("Part 7. Interpreter Address", "p7_3g_postal_code", "3.g. Postal Code (foreign address only)", "text", False),
    ("Part 7. Interpreter Address", "p7_3h_country", "3.h. Country (foreign address only)", "text", False),
    ("Part 7. Interpreter Contact", "p7_4_phone", "4. Interpreter's Daytime Telephone Number", "phone", False),
    ("Part 7. Interpreter Contact", "p7_5_mobile", "5. Interpreter's Mobile Telephone Number (if any)", "phone", False),
    ("Part 7. Interpreter Contact", "p7_6_email", "6. Interpreter's Email Address (if any)", "email", False),
    ("Part 7. Interpreter Certification", "p7_7_language", "7. Language interpreted", "text", False),
    ("Part 7. Interpreter Signature", "p7_8_signature", "8. Signature of Interpreter", "text", False),
    ("Part 7. Interpreter Signature", "p7_8_date", "8. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 8: PREPARER (Pages 8-9)
    # =========================================================================
    ("Part 8. Preparer Info", "p8_1a_family_name", "1.a. Preparer's Family Name (Last Name)", "text", False),
    ("Part 8. Preparer Info", "p8_1b_given_name", "1.b. Preparer's Given Name (First Name)", "text", False),
    ("Part 8. Preparer Info", "p8_2_business_name", "2. Preparer's Business or Organization Name (if any)", "text", False),
    ("Part 8. Preparer Address", "p8_3a_street", "3.a. Street Number and Name", "text", False),
    ("Part 8. Preparer Address", "p8_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 8. Preparer Address", "p8_3b_apt_number", "3.b. Number", "text", False),
    ("Part 8. Preparer Address", "p8_3c_city", "3.c. City or Town", "text", False),
    ("Part 8. Preparer Address", "p8_3d_state", "3.d. State", "select", False),
    ("Part 8. Preparer Address", "p8_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 8. Preparer Address", "p8_3f_province", "3.f. Province (foreign address only)", "text", False),
    ("Part 8. Preparer Address", "p8_3g_postal_code", "3.g. Postal Code (foreign address only)", "text", False),
    ("Part 8. Preparer Address", "p8_3h_country", "3.h. Country (foreign address only)", "text", False),
    ("Part 8. Preparer Contact", "p8_4_phone", "4. Preparer's Daytime Telephone Number", "phone", False),
    ("Part 8. Preparer Contact", "p8_5_mobile", "5. Preparer's Mobile Telephone Number (if any)", "phone", False),
    ("Part 8. Preparer Contact", "p8_6_email", "6. Preparer's Email Address (if any)", "email", False),
    ("Part 8. Preparer Declaration", "p8_7a_not_attorney", "7.a. I am not an attorney or accredited representative but have prepared this form on behalf of the petitioner", "checkbox", False),
    ("Part 8. Preparer Declaration", "p8_7b_is_attorney", "7.b. I am an attorney or accredited representative", "checkbox", False),
    ("Part 8. Preparer Signature", "p8_8_signature", "8. Signature of Preparer", "text", False),
    ("Part 8. Preparer Signature", "p8_8_date", "8. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 9: ADDITIONAL INFORMATION (Pages 10-11)
    # =========================================================================
    ("Part 9. Additional Information", "p9_1a_family_name", "1.a. Family Name (Last Name)", "text", False),
    ("Part 9. Additional Information", "p9_1b_given_name", "1.b. Given Name (First Name)", "text", False),
    ("Part 9. Additional Information", "p9_1c_middle_name", "1.c. Middle Name", "text", False),
    ("Part 9. Additional Information", "p9_2_a_number", "2. A-Number (if any)", "text", False),
    ("Part 9. Additional Information", "p9_3a_page_1", "3.a. Page Number", "text", False),
    ("Part 9. Additional Information", "p9_3b_part_1", "3.b. Part Number", "text", False),
    ("Part 9. Additional Information", "p9_3c_item_1", "3.c. Item Number", "text", False),
    ("Part 9. Additional Information", "p9_3d_info_1", "3.d. Additional Information", "textarea", False),
    ("Part 9. Additional Information", "p9_4a_page_2", "4.a. Page Number", "text", False),
    ("Part 9. Additional Information", "p9_4b_part_2", "4.b. Part Number", "text", False),
    ("Part 9. Additional Information", "p9_4c_item_2", "4.c. Item Number", "text", False),
    ("Part 9. Additional Information", "p9_4d_info_2", "4.d. Additional Information", "textarea", False),
    ("Part 9. Additional Information", "p9_5a_page_3", "5.a. Page Number", "text", False),
    ("Part 9. Additional Information", "p9_5b_part_3", "5.b. Part Number", "text", False),
    ("Part 9. Additional Information", "p9_5c_item_3", "5.c. Item Number", "text", False),
    ("Part 9. Additional Information", "p9_5d_info_3", "5.d. Additional Information", "textarea", False),
]

OPTIONS_MAP = {
    "p1_10b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p1_11b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p1_11d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"],
    "p3_2_type_of_entity": ["Corporation", "LLC", "Partnership", "Sole Proprietorship", "Joint Venture", "Other"],
    "p3_5b_apt_type": ["Ste.", "Flr."],
    "p3_5d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"],
    "p4_3_type_of_entity": ["Corporation", "LLC", "Partnership", "Sole Proprietorship", "Joint Venture", "Other"],
    "p4_5b_apt_type": ["Ste.", "Flr."],
    "p4_5d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"],
    "p7_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p7_3d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"],
    "p8_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p8_3d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"],
}


def update_i526(template_id=None):
    """Insert or update I-526 fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-526%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('I-526 - Immigrant Petition by Standalone Investor (EXPANDED)', "
                    "'Complete I-526 with all official USCIS fields - Edition 03/05/24') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(I526_FIELDS):
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
        print(f"I-526 expanded: template_id={template_id}, fields={len(I526_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_i526()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(I526_FIELDS)}")

    field_names = [fn for _, fn, _, _, _ in I526_FIELDS]
    duplicates = [n for n in field_names if field_names.count(n) > 1]
    if duplicates:
        print(f"\nWARNING: Duplicate field names: {set(duplicates)}")
    else:
        print("\nNo duplicate field names found.")
