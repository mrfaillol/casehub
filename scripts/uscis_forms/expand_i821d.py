#!/usr/bin/env python3
"""
Expand I-821D (Consideration of Deferred Action for Childhood Arrivals) with ALL official USCIS fields.
Edition 01/20/25 - 7 pages, Parts 1-8.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I821D_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT YOU (Pages 1-2)
    # =========================================================================
    ("1. Request Type", "p1_detention_not_in", "I am not in immigration detention", "checkbox", False),
    ("1. Request Type", "p1_detention_in", "I am in immigration detention", "checkbox", False),
    ("1. Request Type", "p1_1_initial", "1. Initial Request - Consideration of Deferred Action for Childhood Arrivals", "checkbox", False),
    ("1. Request Type", "p1_2_renewal", "2. Renewal Request - Consideration of Deferred Action for Childhood Arrivals", "checkbox", False),
    ("1. Request Type", "p1_renewal_expires", "For this Renewal request, my most recent period of Deferred Action for Childhood Arrivals expires on (mm/dd/yyyy)", "date", False),

    # Full Legal Name
    ("1. Full Legal Name", "p1_3a_family_name", "3.a. Family Name (Last Name)", "text", True),
    ("1. Full Legal Name", "p1_3b_given_name", "3.b. Given Name (First Name)", "text", True),
    ("1. Full Legal Name", "p1_3c_middle_name", "3.c. Middle Name", "text", False),

    # U.S. Mailing Address
    ("1. U.S. Mailing Address", "p1_4a_in_care_of", "4.a. In Care Of Name (if applicable)", "text", False),
    ("1. U.S. Mailing Address", "p1_4b_street", "4.b. Street Number and Name", "text", True),
    ("1. U.S. Mailing Address", "p1_4c_apt", "4.c. Apt. / Ste. / Flr.", "select", False),
    ("1. U.S. Mailing Address", "p1_4c_number", "4.c. Number", "text", False),
    ("1. U.S. Mailing Address", "p1_4d_city", "4.d. City or Town", "text", True),
    ("1. U.S. Mailing Address", "p1_4e_state", "4.e. State", "select", True),
    ("1. U.S. Mailing Address", "p1_4f_zip", "4.f. ZIP Code", "text", True),

    # Removal Proceedings Information
    ("1. Removal Proceedings", "p1_5_in_removal", "5. Are you NOW or have you EVER been in removal proceedings, or do you have a removal order issued in any other context?", "radio", True),
    ("1. Removal Proceedings", "p1_6a_currently_active", "6.a. Currently in Proceedings (Active)", "checkbox", False),
    ("1. Removal Proceedings", "p1_6b_currently_admin_closed", "6.b. Currently in Proceedings (Administratively Closed)", "checkbox", False),
    ("1. Removal Proceedings", "p1_6c_terminated", "6.c. Terminated", "checkbox", False),
    ("1. Removal Proceedings", "p1_6d_final_order", "6.d. Subject to a Final Order", "checkbox", False),
    ("1. Removal Proceedings", "p1_6e_other", "6.e. Other. Explain in Part 8. Additional Information.", "checkbox", False),
    ("1. Removal Proceedings", "p1_6f_most_recent_date", "6.f. Most Recent Date of Proceedings (mm/dd/yyyy)", "date", False),
    ("1. Removal Proceedings", "p1_6g_location", "6.g. Location of Proceedings", "text", False),

    # Other Information (Page 2)
    ("1. Other Information", "p1_7_a_number", "7. Alien Registration Number (A-Number) (if any)", "text", False),
    ("1. Other Information", "p1_8_ssn", "8. U.S. Social Security Number (if any)", "text", False),
    ("1. Other Information", "p1_9_sex", "9. Sex", "radio", True),
    ("1. Other Information", "p1_10_dob", "10. Date of Birth (mm/dd/yyyy)", "date", True),
    ("1. Other Information", "p1_11a_city_birth", "11.a. City/Town/Village of Birth", "text", True),
    ("1. Other Information", "p1_11b_country_birth", "11.b. Country of Birth", "text", True),
    ("1. Other Information", "p1_12_current_country", "12. Current Country of Residence", "text", True),
    ("1. Other Information", "p1_13_country_citizenship", "13. Country of Citizenship or Nationality", "text", True),
    ("1. Other Information", "p1_14_marital_status", "14. Marital Status", "radio", True),

    # Other Names Used
    ("1. Other Names", "p1_15a_other_family_name", "15.a. Other Names Used - Family Name (Last Name)", "text", False),
    ("1. Other Names", "p1_15b_other_given_name", "15.b. Other Names Used - Given Name (First Name)", "text", False),
    ("1. Other Names", "p1_15c_other_middle_name", "15.c. Other Names Used - Middle Name", "text", False),

    # Processing Information
    ("1. Processing Information", "p1_16_ethnicity", "16. Ethnicity", "radio", True),
    ("1. Processing Information", "p1_17_race_white", "17. Race - White", "checkbox", False),
    ("1. Processing Information", "p1_17_race_asian", "17. Race - Asian", "checkbox", False),
    ("1. Processing Information", "p1_17_race_black", "17. Race - Black or African American", "checkbox", False),
    ("1. Processing Information", "p1_17_race_native_american", "17. Race - American Indian or Alaska Native", "checkbox", False),
    ("1. Processing Information", "p1_17_race_pacific", "17. Race - Native Hawaiian or Other Pacific Islander", "checkbox", False),
    ("1. Processing Information", "p1_18_height_feet", "18. Height - Feet", "text", True),
    ("1. Processing Information", "p1_18_height_inches", "18. Height - Inches", "text", True),
    ("1. Processing Information", "p1_19_weight", "19. Weight - Pounds", "text", True),
    ("1. Processing Information", "p1_20_eye_color", "20. Eye Color", "radio", True),
    ("1. Processing Information", "p1_21_hair_color", "21. Hair Color", "radio", True),

    # =========================================================================
    # PART 2: RESIDENCE AND TRAVEL INFORMATION (Pages 2-3)
    # =========================================================================
    ("2. Continuous Residence", "p2_1_continuous_residence", "1. I have been continuously residing in the U.S. since at least June 15, 2007, up to the present time", "radio", True),

    # Present Address
    ("2. Present Address", "p2_2a_dates_from", "2.a. Present Address - Dates at this residence - From (mm/dd/yyyy)", "date", False),
    ("2. Present Address", "p2_2a_dates_to", "2.a. Present Address - Dates at this residence - To (Present)", "text", False),
    ("2. Present Address", "p2_2b_street", "2.b. Present Address - Street Number and Name", "text", False),
    ("2. Present Address", "p2_2c_apt", "2.c. Present Address - Apt. / Ste. / Flr.", "select", False),
    ("2. Present Address", "p2_2c_number", "2.c. Present Address - Number", "text", False),
    ("2. Present Address", "p2_2d_city", "2.d. Present Address - City or Town", "text", False),
    ("2. Present Address", "p2_2e_state", "2.e. Present Address - State", "select", False),
    ("2. Present Address", "p2_2f_zip", "2.f. Present Address - ZIP Code", "text", False),

    # Address 1
    ("2. Address 1", "p2_3a_dates_from", "3.a. Address 1 - Dates at this residence - From (mm/dd/yyyy)", "date", False),
    ("2. Address 1", "p2_3a_dates_to", "3.a. Address 1 - Dates at this residence - To (mm/dd/yyyy)", "date", False),
    ("2. Address 1", "p2_3b_street", "3.b. Address 1 - Street Number and Name", "text", False),
    ("2. Address 1", "p2_3c_apt", "3.c. Address 1 - Apt. / Ste. / Flr.", "select", False),
    ("2. Address 1", "p2_3c_number", "3.c. Address 1 - Number", "text", False),
    ("2. Address 1", "p2_3d_city", "3.d. Address 1 - City or Town", "text", False),
    ("2. Address 1", "p2_3e_state", "3.e. Address 1 - State", "select", False),
    ("2. Address 1", "p2_3f_zip", "3.f. Address 1 - ZIP Code", "text", False),

    # Address 2
    ("2. Address 2", "p2_4a_dates_from", "4.a. Address 2 - Dates at this residence - From (mm/dd/yyyy)", "date", False),
    ("2. Address 2", "p2_4a_dates_to", "4.a. Address 2 - Dates at this residence - To (mm/dd/yyyy)", "date", False),
    ("2. Address 2", "p2_4b_street", "4.b. Address 2 - Street Number and Name", "text", False),
    ("2. Address 2", "p2_4c_apt", "4.c. Address 2 - Apt. / Ste. / Flr.", "select", False),
    ("2. Address 2", "p2_4c_number", "4.c. Address 2 - Number", "text", False),
    ("2. Address 2", "p2_4d_city", "4.d. Address 2 - City or Town", "text", False),
    ("2. Address 2", "p2_4e_state", "4.e. Address 2 - State", "select", False),
    ("2. Address 2", "p2_4f_zip", "4.f. Address 2 - ZIP Code", "text", False),

    # Address 3
    ("2. Address 3", "p2_5a_dates_from", "5.a. Address 3 - Dates at this residence - From (mm/dd/yyyy)", "date", False),
    ("2. Address 3", "p2_5a_dates_to", "5.a. Address 3 - Dates at this residence - To (mm/dd/yyyy)", "date", False),
    ("2. Address 3", "p2_5b_street", "5.b. Address 3 - Street Number and Name", "text", False),
    ("2. Address 3", "p2_5c_apt", "5.c. Address 3 - Apt. / Ste. / Flr.", "select", False),
    ("2. Address 3", "p2_5c_number", "5.c. Address 3 - Number", "text", False),
    ("2. Address 3", "p2_5d_city", "5.d. Address 3 - City or Town", "text", False),
    ("2. Address 3", "p2_5e_state", "5.e. Address 3 - State", "select", False),
    ("2. Address 3", "p2_5f_zip", "5.f. Address 3 - ZIP Code", "text", False),

    # Travel Information
    ("2. Departure 1", "p2_6a_departure_date", "6.a. Departure 1 - Departure Date (mm/dd/yyyy)", "date", False),
    ("2. Departure 1", "p2_6b_return_date", "6.b. Departure 1 - Return Date (mm/dd/yyyy)", "date", False),
    ("2. Departure 1", "p2_6c_reason", "6.c. Departure 1 - Reason for Departure", "text", False),

    ("2. Departure 2", "p2_7a_departure_date", "7.a. Departure 2 - Departure Date (mm/dd/yyyy)", "date", False),
    ("2. Departure 2", "p2_7b_return_date", "7.b. Departure 2 - Return Date (mm/dd/yyyy)", "date", False),
    ("2. Departure 2", "p2_7c_reason", "7.c. Departure 2 - Reason for Departure", "text", False),

    ("2. Travel", "p2_8_left_without_parole", "8. Have you left the United States without advance parole on or after August 15, 2012?", "radio", False),

    # Passport Information
    ("2. Passport", "p2_9a_passport_country", "9.a. What country issued your last passport?", "text", False),
    ("2. Passport", "p2_9b_passport_number", "9.b. Passport Number", "text", False),
    ("2. Passport", "p2_9c_passport_expiration", "9.c. Passport Expiration Date (mm/dd/yyyy)", "date", False),
    ("2. Passport", "p2_10_border_crossing_card", "10. Border Crossing Card Number (if any)", "text", False),

    # =========================================================================
    # PART 3: FOR INITIAL REQUESTS ONLY (Page 4)
    # =========================================================================
    ("3. Initial Request", "p3_1_arrived_before_16", "1. I initially arrived and established residence in the U.S. prior to 16 years of age", "radio", False),
    ("3. Initial Request", "p3_2_date_initial_entry", "2. Date of Initial Entry into the United States (on or about) (mm/dd/yyyy)", "date", False),
    ("3. Initial Request", "p3_3_place_initial_entry", "3. Place of Initial Entry into the United States", "text", False),
    ("3. Initial Request", "p3_4_status_june_15_2012", "4. Immigration Status on June 15, 2012 (e.g., No Lawful Status, Status Expired, Parole Expired)", "text", False),
    ("3. Initial Request", "p3_5a_issued_i94", "5.a. Were you EVER issued an Arrival-Departure Record (Form I-94, I-94W, or I-95)?", "radio", False),
    ("3. Initial Request", "p3_5b_i94_number", "5.b. If you answered 'Yes' to Item Number 5.a., provide your Form I-94, I-94W, or I-95 number (if available)", "text", False),
    ("3. Initial Request", "p3_5c_authorized_stay_expired", "5.c. If you answered 'Yes' to Item Number 5.a., provide the date your authorized stay expired (mm/dd/yyyy)", "date", False),

    # Education Information
    ("3. Education", "p3_6_education_guideline", "6. Indicate how you meet the education guideline (e.g., Graduated from high school, Received a GED certificate, Currently in school)", "text", False),
    ("3. Education", "p3_7_school_name", "7. Name, City, and State of School Currently Attending or Where Education Received", "text", False),
    ("3. Education", "p3_8_graduation_date", "8. Date of Graduation (e.g., Receipt of a Certificate of Completion, GED certificate) or, if currently in school, date of last attendance (mm/dd/yyyy)", "date", False),

    # Military Service Information
    ("3. Military", "p3_9_military_service", "9. Were you a member of the U.S. Armed Forces or U.S. Coast Guard?", "radio", False),
    ("3. Military", "p3_9a_military_branch", "9.a. Military Branch", "text", False),
    ("3. Military", "p3_9b_service_start", "9.b. Service Start Date (mm/dd/yyyy)", "date", False),
    ("3. Military", "p3_9c_discharge_date", "9.c. Discharge Date (mm/dd/yyyy)", "date", False),
    ("3. Military", "p3_9d_discharge_type", "9.d. Type of Discharge", "text", False),

    # =========================================================================
    # PART 4: CRIMINAL, NATIONAL SECURITY, AND PUBLIC SAFETY INFORMATION (Page 4)
    # =========================================================================
    ("4. Criminal - US", "p4_1_arrested_us", "1. Have you EVER been arrested for, charged with, or convicted of a felony or misdemeanor in the United States? (Do not include minor traffic violations unless alcohol- or drug-related)", "radio", False),
    ("4. Criminal - Foreign", "p4_2_arrested_foreign", "2. Have you EVER been arrested for, charged with, or convicted of a crime in any country other than the United States?", "radio", False),
    ("4. Security", "p4_3_terrorist_activities", "3. Have you EVER engaged in, do you continue to engage in, or plan to engage in terrorist activities?", "radio", False),
    ("4. Security", "p4_4_gang_member", "4. Are you NOW or have you EVER been a member of a gang?", "radio", False),

    # Question 5 - Participated in harm
    ("4. Harm", "p4_5a_torture_genocide", "5.a. Have you EVER engaged in, ordered, incited, assisted, or otherwise participated in: Acts involving torture, genocide, or human trafficking?", "radio", False),
    ("4. Harm", "p4_5b_killing", "5.b. Killing any person?", "radio", False),
    ("4. Harm", "p4_5c_injuring", "5.c. Severely injuring any person?", "radio", False),
    ("4. Harm", "p4_5d_sexual_contact", "5.d. Any kind of sexual contact or relations with any person who was being forced or threatened?", "radio", False),

    # Child soldiers
    ("4. Children", "p4_6_recruited_under_15", "6. Have you EVER recruited, enlisted, conscripted, or used any person to serve in or help an armed force or group while such person was under age 15?", "radio", False),
    ("4. Children", "p4_7_used_under_15", "7. Have you EVER used any person under age 15 to take part in hostilities, or to help or provide services to people in combat?", "radio", False),

    # =========================================================================
    # PART 5: STATEMENT, CERTIFICATION, SIGNATURE (Pages 5)
    # =========================================================================
    ("5. Statement", "p5_1a_english", "1.a. I can read and understand English, and have read and understand each and every question and instruction on this form", "checkbox", False),
    ("5. Statement", "p5_1b_interpreter", "1.b. The interpreter named in Part 6. has read to me each and every question in [language], and I understood everything", "checkbox", False),
    ("5. Statement", "p5_1b_language", "1.b. Language in which interpreter read to requestor", "text", False),

    # Signature
    ("5. Signature", "p5_2a_signature", "2.a. Requestor's Signature", "text", True),
    ("5. Signature", "p5_2b_date", "2.b. Date of Signature (mm/dd/yyyy)", "date", True),

    # Contact Information
    ("5. Contact", "p5_3_daytime_phone", "3. Requestor's Daytime Telephone Number", "phone", False),
    ("5. Contact", "p5_4_mobile_phone", "4. Requestor's Mobile Telephone Number", "phone", False),
    ("5. Contact", "p5_5_email", "5. Requestor's Email Address", "text", False),

    # =========================================================================
    # PART 6: INTERPRETER (Pages 5-6)
    # =========================================================================
    ("6. Interpreter Name", "p6_1a_family_name", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("6. Interpreter Name", "p6_1b_given_name", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("6. Interpreter", "p6_2_organization", "2. Interpreter's Business or Organization Name (if any)", "text", False),

    # Interpreter Mailing Address
    ("6. Interpreter Address", "p6_3a_street", "3.a. Interpreter's Mailing Address - Street Number and Name", "text", False),
    ("6. Interpreter Address", "p6_3b_apt", "3.b. Interpreter's Mailing Address - Apt. / Ste. / Flr.", "select", False),
    ("6. Interpreter Address", "p6_3b_number", "3.b. Interpreter's Mailing Address - Number", "text", False),
    ("6. Interpreter Address", "p6_3c_city", "3.c. Interpreter's Mailing Address - City or Town", "text", False),
    ("6. Interpreter Address", "p6_3d_state", "3.d. Interpreter's Mailing Address - State", "select", False),
    ("6. Interpreter Address", "p6_3e_zip", "3.e. Interpreter's Mailing Address - ZIP Code", "text", False),
    ("6. Interpreter Address", "p6_3f_province", "3.f. Interpreter's Mailing Address - Province", "text", False),
    ("6. Interpreter Address", "p6_3g_postal", "3.g. Interpreter's Mailing Address - Postal Code", "text", False),
    ("6. Interpreter Address", "p6_3h_country", "3.h. Interpreter's Mailing Address - Country", "text", False),

    # Interpreter Contact
    ("6. Interpreter Contact", "p6_4_daytime_phone", "4. Interpreter's Daytime Telephone Number", "phone", False),
    ("6. Interpreter Contact", "p6_5_email", "5. Interpreter's Email Address", "text", False),

    # Interpreter Certification
    ("6. Interpreter Cert", "p6_cert_language", "Interpreter Certification - Language fluent in (same as Part 5, Item Number 1.b.)", "text", False),
    ("6. Interpreter Cert", "p6_6a_signature", "6.a. Interpreter's Signature", "text", False),
    ("6. Interpreter Cert", "p6_6b_date", "6.b. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 7: PREPARER (Page 6)
    # =========================================================================
    ("7. Preparer Name", "p7_1a_family_name", "1.a. Preparer's Family Name (Last Name)", "text", False),
    ("7. Preparer Name", "p7_1b_given_name", "1.b. Preparer's Given Name (First Name)", "text", False),
    ("7. Preparer", "p7_2_organization", "2. Preparer's Business or Organization Name", "text", False),

    # Preparer Mailing Address
    ("7. Preparer Address", "p7_3a_street", "3.a. Preparer's Mailing Address - Street Number and Name", "text", False),
    ("7. Preparer Address", "p7_3b_apt", "3.b. Preparer's Mailing Address - Apt. / Ste. / Flr.", "select", False),
    ("7. Preparer Address", "p7_3b_number", "3.b. Preparer's Mailing Address - Number", "text", False),
    ("7. Preparer Address", "p7_3c_city", "3.c. Preparer's Mailing Address - City or Town", "text", False),
    ("7. Preparer Address", "p7_3d_state", "3.d. Preparer's Mailing Address - State", "select", False),
    ("7. Preparer Address", "p7_3e_zip", "3.e. Preparer's Mailing Address - ZIP Code", "text", False),
    ("7. Preparer Address", "p7_3f_province", "3.f. Preparer's Mailing Address - Province", "text", False),
    ("7. Preparer Address", "p7_3g_postal", "3.g. Preparer's Mailing Address - Postal Code", "text", False),
    ("7. Preparer Address", "p7_3h_country", "3.h. Preparer's Mailing Address - Country", "text", False),

    # Preparer Contact
    ("7. Preparer Contact", "p7_4_daytime_phone", "4. Preparer's Daytime Telephone Number", "phone", False),
    ("7. Preparer Contact", "p7_5_fax", "5. Preparer's Fax Number", "text", False),
    ("7. Preparer Contact", "p7_6_email", "6. Preparer's Email Address", "text", False),

    # Preparer Declaration
    ("7. Preparer Declaration", "p7_7a_signature", "7.a. Preparer's Signature", "text", False),
    ("7. Preparer Declaration", "p7_7b_date", "7.b. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 8: ADDITIONAL INFORMATION (Page 7)
    # =========================================================================
    ("8. Additional Info 1", "p8_1a_family_name", "1.a. Family Name (Last Name)", "text", False),
    ("8. Additional Info 1", "p8_1b_given_name", "1.b. Given Name (First Name)", "text", False),
    ("8. Additional Info 1", "p8_1c_middle_name", "1.c. Middle Name", "text", False),
    ("8. Additional Info 1", "p8_2_a_number", "2. A-Number (if any)", "text", False),
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
]


def update_i821d(template_id=None):
    """Insert or update I-821D fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-821D%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('I-821D - Consideration of Deferred Action for Childhood Arrivals (EXPANDED)', "
                    "'Complete I-821D (DACA) with all official USCIS fields - Edition 01/20/25') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(I821D_FIELDS):
            conn.execute(text(
                "INSERT INTO questionnaire_fields (template_id, section, field_name, label, field_type, is_required, \"order\") "
                "VALUES (:tid, :section, :field_name, :label, :field_type, :is_required, :order)"
            ), {
                "tid": template_id, "section": section, "field_name": field_name,
                "label": label, "field_type": field_type, "is_required": required, "order": i + 1
            })

        conn.commit()
        print(f"I-821D expanded: template_id={template_id}, fields={len(I821D_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_i821d()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(I821D_FIELDS)}")

    sections = {}
    for section, _, _, _, _ in I821D_FIELDS:
        sections[section] = sections.get(section, 0) + 1

    print("\nFields by section:")
    for section, count in sections.items():
        print(f"  {section}: {count}")

    # Check for duplicates
    field_names = [fn for _, fn, _, _, _ in I821D_FIELDS]
    duplicates = [fn for fn in field_names if field_names.count(fn) > 1]
    if duplicates:
        print(f"\nWARNING: Duplicate field names found: {set(duplicates)}")
    else:
        print("\nNo duplicate field names detected.")
