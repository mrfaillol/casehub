#!/usr/bin/env python3
"""
Expand I-130A (Supplemental Information for Spouse Beneficiary) with ALL official USCIS fields.
Edition 04/01/24 - 6 pages, Parts 1-7.
Used with I-130 for spouse petitions. Collects detailed beneficiary info.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I130A_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT YOU (Spouse Beneficiary)
    # =========================================================================
    ("1A. Beneficiary Information", "p1_1_a_number", "1. Alien Registration Number (A-Number)", "text", False),
    ("1A. Beneficiary Information", "p1_2_uscis_account", "2. USCIS Online Account Number", "text", False),
    ("1A. Beneficiary Information", "p1_3a_family_name", "3.a. Family Name (Last Name)", "text", True),
    ("1A. Beneficiary Information", "p1_3b_given_name", "3.b. Given Name (First Name)", "text", True),
    ("1A. Beneficiary Information", "p1_3c_middle_name", "3.c. Middle Name", "text", False),

    # Current Physical Address
    ("1B. Current Physical Address", "p1_4a_street", "4.a. Street Number and Name", "text", True),
    ("1B. Current Physical Address", "p1_4b_apt_type", "4.b. Apt/Ste/Flr Type", "select", False),
    ("1B. Current Physical Address", "p1_4c_apt_number", "4.c. Apt/Ste/Flr Number", "text", False),
    ("1B. Current Physical Address", "p1_4d_city", "4.d. City or Town", "text", True),
    ("1B. Current Physical Address", "p1_4e_state", "4.e. State", "select", False),
    ("1B. Current Physical Address", "p1_4f_zip", "4.f. ZIP Code", "text", False),
    ("1B. Current Physical Address", "p1_4g_province", "4.g. Province (if outside U.S.)", "text", False),
    ("1B. Current Physical Address", "p1_4h_postal", "4.h. Postal Code (if outside U.S.)", "text", False),
    ("1B. Current Physical Address", "p1_4i_country", "4.i. Country", "text", True),
    ("1B. Current Physical Address", "p1_5_date_from", "5. Date You Began Living at This Address (mm/dd/yyyy)", "date", True),

    # Previous Address 1
    ("1C. Previous Address 1", "p1_6a_prev1_street", "6.a. Previous Address 1 - Street Number and Name", "text", False),
    ("1C. Previous Address 1", "p1_6b_prev1_apt_type", "6.b. Apt/Ste/Flr Type", "select", False),
    ("1C. Previous Address 1", "p1_6c_prev1_apt_number", "6.c. Apt/Ste/Flr Number", "text", False),
    ("1C. Previous Address 1", "p1_6d_prev1_city", "6.d. City or Town", "text", False),
    ("1C. Previous Address 1", "p1_6e_prev1_state", "6.e. State", "select", False),
    ("1C. Previous Address 1", "p1_6f_prev1_zip", "6.f. ZIP Code", "text", False),
    ("1C. Previous Address 1", "p1_6g_prev1_province", "6.g. Province", "text", False),
    ("1C. Previous Address 1", "p1_6h_prev1_postal", "6.h. Postal Code", "text", False),
    ("1C. Previous Address 1", "p1_6i_prev1_country", "6.i. Country", "text", False),
    ("1C. Previous Address 1", "p1_7_prev1_from", "7. Date From (mm/dd/yyyy)", "date", False),
    ("1C. Previous Address 1", "p1_8_prev1_to", "8. Date To (mm/dd/yyyy)", "date", False),

    # Previous Address 2
    ("1D. Previous Address 2", "p1_9a_prev2_street", "9.a. Previous Address 2 - Street Number and Name", "text", False),
    ("1D. Previous Address 2", "p1_9b_prev2_apt_type", "9.b. Apt/Ste/Flr Type", "select", False),
    ("1D. Previous Address 2", "p1_9c_prev2_apt_number", "9.c. Apt/Ste/Flr Number", "text", False),
    ("1D. Previous Address 2", "p1_9d_prev2_city", "9.d. City or Town", "text", False),
    ("1D. Previous Address 2", "p1_9e_prev2_state", "9.e. State", "select", False),
    ("1D. Previous Address 2", "p1_9f_prev2_zip", "9.f. ZIP Code", "text", False),
    ("1D. Previous Address 2", "p1_9g_prev2_province", "9.g. Province", "text", False),
    ("1D. Previous Address 2", "p1_9h_prev2_postal", "9.h. Postal Code", "text", False),
    ("1D. Previous Address 2", "p1_9i_prev2_country", "9.i. Country", "text", False),
    ("1D. Previous Address 2", "p1_10_prev2_from", "10. Date From (mm/dd/yyyy)", "date", False),
    ("1D. Previous Address 2", "p1_11_prev2_to", "11. Date To (mm/dd/yyyy)", "date", False),

    # Beneficiary's Last Spouse
    ("1E. Last Spouse Info", "p1_12a_spouse_family", "12.a. Last Spouse - Family Name (Last Name)", "text", False),
    ("1E. Last Spouse Info", "p1_12b_spouse_given", "12.b. Last Spouse - Given Name (First Name)", "text", False),
    ("1E. Last Spouse Info", "p1_12c_spouse_middle", "12.c. Last Spouse - Middle Name", "text", False),
    ("1E. Last Spouse Info", "p1_13_spouse_dob", "13. Date of Birth of Last Spouse (mm/dd/yyyy)", "date", False),
    ("1E. Last Spouse Info", "p1_14_spouse_city_birth", "14. City/Town of Birth of Last Spouse", "text", False),
    ("1E. Last Spouse Info", "p1_15_spouse_country_birth", "15. Country of Birth of Last Spouse", "text", False),
    ("1E. Last Spouse Info", "p1_16_spouse_nationality", "16. Nationality of Last Spouse", "text", False),
    ("1E. Last Spouse Info", "p1_17_spouse_country_residence", "17. Country of Residence of Last Spouse", "text", False),
    ("1E. Last Spouse Info", "p1_18_marriage_date", "18. Date of Marriage to Last Spouse (mm/dd/yyyy)", "date", False),
    ("1E. Last Spouse Info", "p1_19_marriage_city", "19. City of Marriage to Last Spouse", "text", False),
    ("1E. Last Spouse Info", "p1_20_marriage_state", "20. State/Province of Marriage", "text", False),
    ("1E. Last Spouse Info", "p1_21_marriage_country", "21. Country of Marriage", "text", False),
    ("1E. Last Spouse Info", "p1_22_marriage_end_date", "22. Date Marriage Ended (mm/dd/yyyy)", "date", False),
    ("1E. Last Spouse Info", "p1_23_marriage_end_how", "23. How Marriage Ended (Annulled, Divorced, Other)", "select", False),

    # Father Information
    ("1F. Father Information", "p1_24a_father_family", "24.a. Father's Family Name (Last Name)", "text", False),
    ("1F. Father Information", "p1_24b_father_given", "24.b. Father's Given Name (First Name)", "text", False),
    ("1F. Father Information", "p1_24c_father_middle", "24.c. Father's Middle Name", "text", False),
    ("1F. Father Information", "p1_25_father_dob", "25. Father's Date of Birth (mm/dd/yyyy)", "date", False),
    ("1F. Father Information", "p1_26_father_sex", "26. Father's Sex", "select", False),
    ("1F. Father Information", "p1_27_father_country_birth", "27. Father's Country of Birth", "text", False),
    ("1F. Father Information", "p1_28_father_city_residence", "28. Father's City/Town of Residence", "text", False),
    ("1F. Father Information", "p1_29_father_country_residence", "29. Father's Country of Residence", "text", False),

    # Mother Information
    ("1G. Mother Information", "p1_30a_mother_family", "30.a. Mother's Current Legal Family Name (Last Name)", "text", False),
    ("1G. Mother Information", "p1_30b_mother_given", "30.b. Mother's Given Name (First Name)", "text", False),
    ("1G. Mother Information", "p1_30c_mother_middle", "30.c. Mother's Middle Name", "text", False),
    ("1G. Mother Information", "p1_31_mother_dob", "31. Mother's Date of Birth (mm/dd/yyyy)", "date", False),
    ("1G. Mother Information", "p1_32_mother_sex", "32. Mother's Sex", "select", False),
    ("1G. Mother Information", "p1_33_mother_country_birth", "33. Mother's Country of Birth", "text", False),
    ("1G. Mother Information", "p1_34_mother_city_residence", "34. Mother's City/Town of Residence", "text", False),
    ("1G. Mother Information", "p1_35_mother_country_residence", "35. Mother's Country of Residence", "text", False),

    # =========================================================================
    # PART 2: BENEFICIARY'S EMPLOYMENT HISTORY
    # =========================================================================
    # Employer 1
    ("2A. Employer 1", "p2_1_employer1_name", "1. Employer 1 - Name of Employer/Company", "text", False),
    ("2A. Employer 1", "p2_2a_emp1_street", "2.a. Employer 1 - Street Number and Name", "text", False),
    ("2A. Employer 1", "p2_2b_emp1_apt", "2.b. Employer 1 - Apt/Ste/Flr Number", "text", False),
    ("2A. Employer 1", "p2_2c_emp1_city", "2.c. Employer 1 - City or Town", "text", False),
    ("2A. Employer 1", "p2_2d_emp1_state", "2.d. Employer 1 - State", "select", False),
    ("2A. Employer 1", "p2_2e_emp1_zip", "2.e. Employer 1 - ZIP Code", "text", False),
    ("2A. Employer 1", "p2_2f_emp1_province", "2.f. Employer 1 - Province", "text", False),
    ("2A. Employer 1", "p2_2g_emp1_postal", "2.g. Employer 1 - Postal Code", "text", False),
    ("2A. Employer 1", "p2_2h_emp1_country", "2.h. Employer 1 - Country", "text", False),
    ("2A. Employer 1", "p2_3_emp1_occupation", "3. Employer 1 - Your Occupation", "text", False),
    ("2A. Employer 1", "p2_4a_emp1_date_from", "4.a. Employer 1 - Date From (mm/dd/yyyy)", "date", False),
    ("2A. Employer 1", "p2_4b_emp1_date_to", "4.b. Employer 1 - Date To (mm/dd/yyyy)", "date", False),

    # Employer 2
    ("2B. Employer 2", "p2_5_employer2_name", "5. Employer 2 - Name of Employer/Company", "text", False),
    ("2B. Employer 2", "p2_6a_emp2_street", "6.a. Employer 2 - Street Number and Name", "text", False),
    ("2B. Employer 2", "p2_6b_emp2_city", "6.b. Employer 2 - City or Town", "text", False),
    ("2B. Employer 2", "p2_6c_emp2_state", "6.c. Employer 2 - State", "select", False),
    ("2B. Employer 2", "p2_6d_emp2_zip", "6.d. Employer 2 - ZIP Code", "text", False),
    ("2B. Employer 2", "p2_6e_emp2_province", "6.e. Employer 2 - Province", "text", False),
    ("2B. Employer 2", "p2_6f_emp2_country", "6.f. Employer 2 - Country", "text", False),
    ("2B. Employer 2", "p2_7_emp2_occupation", "7. Employer 2 - Your Occupation", "text", False),
    ("2B. Employer 2", "p2_8a_emp2_date_from", "8.a. Employer 2 - Date From (mm/dd/yyyy)", "date", False),
    ("2B. Employer 2", "p2_8b_emp2_date_to", "8.b. Employer 2 - Date To (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 3: ADDITIONAL EMPLOYMENT (if needed)
    # =========================================================================
    ("3. Additional Employment", "p3_1_employer3_name", "1. Employer 3 - Name of Employer/Company", "text", False),
    ("3. Additional Employment", "p3_2a_emp3_street", "2.a. Employer 3 - Street Number and Name", "text", False),
    ("3. Additional Employment", "p3_2b_emp3_city", "2.b. Employer 3 - City or Town", "text", False),
    ("3. Additional Employment", "p3_2c_emp3_country", "2.c. Employer 3 - Country", "text", False),
    ("3. Additional Employment", "p3_3_emp3_occupation", "3. Employer 3 - Your Occupation", "text", False),
    ("3. Additional Employment", "p3_4a_emp3_date_from", "4.a. Employer 3 - Date From (mm/dd/yyyy)", "date", False),
    ("3. Additional Employment", "p3_4b_emp3_date_to", "4.b. Employer 3 - Date To (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 4: BENEFICIARY'S STATEMENT, CONTACT, DECLARATION, AND SIGNATURE
    # =========================================================================
    ("4. Statement & Contact", "p4_1a_english", "1.a. I can read and understand English", "checkbox", False),
    ("4. Statement & Contact", "p4_1b_interpreter", "1.b. Interpreter read form to me in (language)", "checkbox", False),
    ("4. Statement & Contact", "p4_1b_language", "1.b. Language", "text", False),
    ("4. Statement & Contact", "p4_2_preparer", "2. At my request, the preparer named in Part 6 prepared this supplement for me", "checkbox", False),
    ("4. Statement & Contact", "p4_3_phone_day", "3. Daytime Telephone Number", "phone", False),
    ("4. Statement & Contact", "p4_4_phone_mobile", "4. Mobile Telephone Number (if any)", "phone", False),
    ("4. Statement & Contact", "p4_5_email", "5. Email Address (if any)", "email", False),

    # =========================================================================
    # PART 5: INTERPRETER'S CONTACT INFORMATION
    # =========================================================================
    ("5. Interpreter", "p5_1a_interp_family", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("5. Interpreter", "p5_1b_interp_given", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("5. Interpreter", "p5_2_interp_org", "2. Name of Business or Organization (if any)", "text", False),
    ("5. Interpreter", "p5_3a_interp_street", "3.a. Street Number and Name", "text", False),
    ("5. Interpreter", "p5_3b_interp_apt", "3.b. Apt/Ste/Flr Number", "text", False),
    ("5. Interpreter", "p5_3c_interp_city", "3.c. City or Town", "text", False),
    ("5. Interpreter", "p5_3d_interp_state", "3.d. State", "select", False),
    ("5. Interpreter", "p5_3e_interp_zip", "3.e. ZIP Code", "text", False),
    ("5. Interpreter", "p5_3f_interp_province", "3.f. Province", "text", False),
    ("5. Interpreter", "p5_3g_interp_postal", "3.g. Postal Code", "text", False),
    ("5. Interpreter", "p5_3h_interp_country", "3.h. Country", "text", False),
    ("5. Interpreter", "p5_4_interp_phone", "4. Daytime Telephone Number", "phone", False),
    ("5. Interpreter", "p5_5_interp_mobile", "5. Mobile Telephone Number", "phone", False),
    ("5. Interpreter", "p5_6_interp_email", "6. Email Address (if any)", "email", False),
    ("5. Interpreter", "p5_7_language", "7. Language", "text", False),

    # =========================================================================
    # PART 6: PREPARER CONTACT INFORMATION
    # =========================================================================
    ("6. Preparer", "p6_1_preparer_not_attorney", "1. Preparer is not an attorney or accredited representative", "checkbox", False),
    ("6. Preparer", "p6_2a_prep_family", "2.a. Preparer's Family Name (Last Name)", "text", False),
    ("6. Preparer", "p6_2b_prep_given", "2.b. Preparer's Given Name (First Name)", "text", False),
    ("6. Preparer", "p6_3_prep_org", "3. Name of Business or Organization (if any)", "text", False),
    ("6. Preparer", "p6_4a_prep_street", "4.a. Street Number and Name", "text", False),
    ("6. Preparer", "p6_4b_prep_apt", "4.b. Apt/Ste/Flr Number", "text", False),
    ("6. Preparer", "p6_4c_prep_city", "4.c. City or Town", "text", False),
    ("6. Preparer", "p6_4d_prep_state", "4.d. State", "select", False),
    ("6. Preparer", "p6_4e_prep_zip", "4.e. ZIP Code", "text", False),
    ("6. Preparer", "p6_4f_prep_province", "4.f. Province", "text", False),
    ("6. Preparer", "p6_4g_prep_postal", "4.g. Postal Code", "text", False),
    ("6. Preparer", "p6_4h_prep_country", "4.h. Country", "text", False),
    ("6. Preparer", "p6_5_prep_phone", "5. Daytime Telephone Number", "phone", False),
    ("6. Preparer", "p6_6_prep_mobile", "6. Mobile Telephone Number", "phone", False),
    ("6. Preparer", "p6_7_prep_email", "7. Email Address (if any)", "email", False),

    # =========================================================================
    # PART 7: ADDITIONAL INFORMATION
    # =========================================================================
    ("7. Additional Information", "p7_1a_page_1", "1.a. Page Number", "text", False),
    ("7. Additional Information", "p7_1b_part_1", "1.b. Part Number", "text", False),
    ("7. Additional Information", "p7_1c_item_1", "1.c. Item Number", "text", False),
    ("7. Additional Information", "p7_1d_info_1", "1.d. Additional Information", "textarea", False),
    ("7. Additional Information", "p7_2a_page_2", "2.a. Page Number", "text", False),
    ("7. Additional Information", "p7_2b_part_2", "2.b. Part Number", "text", False),
    ("7. Additional Information", "p7_2c_item_2", "2.c. Item Number", "text", False),
    ("7. Additional Information", "p7_2d_info_2", "2.d. Additional Information", "textarea", False),
    ("7. Additional Information", "p7_3a_page_3", "3.a. Page Number", "text", False),
    ("7. Additional Information", "p7_3b_part_3", "3.b. Part Number", "text", False),
    ("7. Additional Information", "p7_3c_item_3", "3.c. Item Number", "text", False),
    ("7. Additional Information", "p7_3d_info_3", "3.d. Additional Information", "textarea", False),
]

# Total: 120+ fields

def update_i130a(template_id=None):
    """Insert or update I-130A fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM intake_templates WHERE name ILIKE '%I-130A%' LIMIT 1"
            ))
            row = result.fetchone()
            template_id = row[0] if row else None

        if template_id is None:
            print("No template found for I-130A")
            return

        for section, field_name, label, field_type, is_required in I130A_FIELDS:
            conn.execute(text("""
                INSERT INTO intake_fields (template_id, section, field_name, label, field_type, is_required, sort_order)
                VALUES (:tid, :section, :field_name, :label, :field_type, :required, :sort)
                ON CONFLICT (template_id, field_name) DO UPDATE
                SET section = :section, label = :label, field_type = :field_type, is_required = :required
            """), {
                "tid": template_id, "section": section, "field_name": field_name,
                "label": label, "field_type": field_type, "required": is_required,
                "sort": I130A_FIELDS.index((section, field_name, label, field_type, is_required))
            })
        conn.commit()
        print(f"I-130A: {len(I130A_FIELDS)} fields inserted/updated for template {template_id}")


if __name__ == "__main__":
    update_i130a()
