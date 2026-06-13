#!/usr/bin/env python3
"""
Expand remaining USCIS forms with ALL official fields:
- I-130A (ID 39): ~90 fields
- I-864 (ID 41): ~200 fields
- I-765 (ID 42): ~120 fields
- I-131 (ID 43): ~150 fields
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

# =============================================================================
# FORM I-130A - Supplemental Information for Spouse Beneficiary
# =============================================================================
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

    # Previous Address 1 (within last 5 years)
    ("1C. Previous Address 1", "p1_6a_prev1_street", "6.a. Previous Address 1 - Street Number and Name", "text", False),
    ("1C. Previous Address 1", "p1_6b_prev1_apt_type", "6.b. Previous Address 1 - Apt/Ste/Flr Type", "select", False),
    ("1C. Previous Address 1", "p1_6c_prev1_apt_number", "6.c. Previous Address 1 - Apt/Ste/Flr Number", "text", False),
    ("1C. Previous Address 1", "p1_6d_prev1_city", "6.d. Previous Address 1 - City or Town", "text", False),
    ("1C. Previous Address 1", "p1_6e_prev1_state", "6.e. Previous Address 1 - State", "select", False),
    ("1C. Previous Address 1", "p1_6f_prev1_zip", "6.f. Previous Address 1 - ZIP Code", "text", False),
    ("1C. Previous Address 1", "p1_6g_prev1_province", "6.g. Previous Address 1 - Province", "text", False),
    ("1C. Previous Address 1", "p1_6h_prev1_postal", "6.h. Previous Address 1 - Postal Code", "text", False),
    ("1C. Previous Address 1", "p1_6i_prev1_country", "6.i. Previous Address 1 - Country", "text", False),
    ("1C. Previous Address 1", "p1_7_prev1_from", "7. Previous Address 1 - Date From (mm/dd/yyyy)", "date", False),
    ("1C. Previous Address 1", "p1_8_prev1_to", "8. Previous Address 1 - Date To (mm/dd/yyyy)", "date", False),

    # Previous Address 2
    ("1D. Previous Address 2", "p1_9a_prev2_street", "9.a. Previous Address 2 - Street Number and Name", "text", False),
    ("1D. Previous Address 2", "p1_9b_prev2_apt_type", "9.b. Previous Address 2 - Apt/Ste/Flr Type", "select", False),
    ("1D. Previous Address 2", "p1_9c_prev2_apt_number", "9.c. Previous Address 2 - Apt/Ste/Flr Number", "text", False),
    ("1D. Previous Address 2", "p1_9d_prev2_city", "9.d. Previous Address 2 - City or Town", "text", False),
    ("1D. Previous Address 2", "p1_9e_prev2_state", "9.e. Previous Address 2 - State", "select", False),
    ("1D. Previous Address 2", "p1_9f_prev2_zip", "9.f. Previous Address 2 - ZIP Code", "text", False),
    ("1D. Previous Address 2", "p1_9g_prev2_province", "9.g. Previous Address 2 - Province", "text", False),
    ("1D. Previous Address 2", "p1_9h_prev2_postal", "9.h. Previous Address 2 - Postal Code", "text", False),
    ("1D. Previous Address 2", "p1_9i_prev2_country", "9.i. Previous Address 2 - Country", "text", False),
    ("1D. Previous Address 2", "p1_10_prev2_from", "10. Previous Address 2 - Date From", "date", False),
    ("1D. Previous Address 2", "p1_11_prev2_to", "11. Previous Address 2 - Date To", "date", False),

    # Previous Address 3
    ("1E. Previous Address 3", "p1_12a_prev3_street", "12.a. Previous Address 3 - Street", "text", False),
    ("1E. Previous Address 3", "p1_12b_prev3_city", "12.b. Previous Address 3 - City or Town", "text", False),
    ("1E. Previous Address 3", "p1_12c_prev3_state", "12.c. Previous Address 3 - State", "select", False),
    ("1E. Previous Address 3", "p1_12d_prev3_country", "12.d. Previous Address 3 - Country", "text", False),
    ("1E. Previous Address 3", "p1_13_prev3_from", "13. Previous Address 3 - Date From", "date", False),
    ("1E. Previous Address 3", "p1_14_prev3_to", "14. Previous Address 3 - Date To", "date", False),

    # Last Address Outside U.S.
    ("1F. Last Address Outside U.S.", "p1_15a_outside_street", "15.a. Last Address Outside U.S. - Street", "text", False),
    ("1F. Last Address Outside U.S.", "p1_15b_outside_city", "15.b. Last Address Outside U.S. - City or Town", "text", False),
    ("1F. Last Address Outside U.S.", "p1_15c_outside_province", "15.c. Last Address Outside U.S. - Province", "text", False),
    ("1F. Last Address Outside U.S.", "p1_15d_outside_postal", "15.d. Last Address Outside U.S. - Postal Code", "text", False),
    ("1F. Last Address Outside U.S.", "p1_15e_outside_country", "15.e. Last Address Outside U.S. - Country", "text", False),
    ("1F. Last Address Outside U.S.", "p1_16_outside_from", "16. Last Address Outside U.S. - Date From", "date", False),
    ("1F. Last Address Outside U.S.", "p1_17_outside_to", "17. Last Address Outside U.S. - Date To", "date", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT YOUR EMPLOYMENT
    # =========================================================================
    # Current Employment
    ("2A. Current Employment", "p2_1_employer", "1. Employer or Company Name", "text", False),
    ("2A. Current Employment", "p2_2a_emp_street", "2.a. Employer Address - Street Number and Name", "text", False),
    ("2A. Current Employment", "p2_2b_emp_apt_type", "2.b. Employer Address - Apt/Ste/Flr Type", "select", False),
    ("2A. Current Employment", "p2_2c_emp_apt_number", "2.c. Employer Address - Apt/Ste/Flr Number", "text", False),
    ("2A. Current Employment", "p2_2d_emp_city", "2.d. Employer Address - City or Town", "text", False),
    ("2A. Current Employment", "p2_2e_emp_state", "2.e. Employer Address - State", "select", False),
    ("2A. Current Employment", "p2_2f_emp_zip", "2.f. Employer Address - ZIP Code", "text", False),
    ("2A. Current Employment", "p2_2g_emp_province", "2.g. Employer Address - Province", "text", False),
    ("2A. Current Employment", "p2_2h_emp_postal", "2.h. Employer Address - Postal Code", "text", False),
    ("2A. Current Employment", "p2_2i_emp_country", "2.i. Employer Address - Country", "text", False),
    ("2A. Current Employment", "p2_3_occupation", "3. Your Occupation", "text", False),
    ("2A. Current Employment", "p2_4_emp_from", "4. Date From (mm/dd/yyyy)", "date", False),
    ("2A. Current Employment", "p2_5_emp_to", "5. Date To (Present if currently employed)", "text", False),

    # Previous Employment 1
    ("2B. Previous Employment 1", "p2_6_prev_emp1_name", "6. Previous Employer 1 - Company Name", "text", False),
    ("2B. Previous Employment 1", "p2_7a_prev_emp1_street", "7.a. Previous Employer 1 - Street", "text", False),
    ("2B. Previous Employment 1", "p2_7b_prev_emp1_city", "7.b. Previous Employer 1 - City", "text", False),
    ("2B. Previous Employment 1", "p2_7c_prev_emp1_state", "7.c. Previous Employer 1 - State", "select", False),
    ("2B. Previous Employment 1", "p2_7d_prev_emp1_country", "7.d. Previous Employer 1 - Country", "text", False),
    ("2B. Previous Employment 1", "p2_8_prev_emp1_occupation", "8. Previous Employer 1 - Your Occupation", "text", False),
    ("2B. Previous Employment 1", "p2_9_prev_emp1_from", "9. Previous Employment 1 - Date From", "date", False),
    ("2B. Previous Employment 1", "p2_10_prev_emp1_to", "10. Previous Employment 1 - Date To", "date", False),

    # Previous Employment 2
    ("2C. Previous Employment 2", "p2_11_prev_emp2_name", "11. Previous Employer 2 - Company Name", "text", False),
    ("2C. Previous Employment 2", "p2_12a_prev_emp2_street", "12.a. Previous Employer 2 - Street", "text", False),
    ("2C. Previous Employment 2", "p2_12b_prev_emp2_city", "12.b. Previous Employer 2 - City", "text", False),
    ("2C. Previous Employment 2", "p2_12c_prev_emp2_state", "12.c. Previous Employer 2 - State", "select", False),
    ("2C. Previous Employment 2", "p2_12d_prev_emp2_country", "12.d. Previous Employer 2 - Country", "text", False),
    ("2C. Previous Employment 2", "p2_13_prev_emp2_occupation", "13. Previous Employer 2 - Your Occupation", "text", False),
    ("2C. Previous Employment 2", "p2_14_prev_emp2_from", "14. Previous Employment 2 - Date From", "date", False),
    ("2C. Previous Employment 2", "p2_15_prev_emp2_to", "15. Previous Employment 2 - Date To", "date", False),

    # =========================================================================
    # PART 3: INFORMATION ABOUT YOUR PARENTS
    # =========================================================================
    # Father's Information
    ("3A. Father's Information", "p3_1a_father_family", "1.a. Father's Family Name (Last Name)", "text", False),
    ("3A. Father's Information", "p3_1b_father_given", "1.b. Father's Given Name (First Name)", "text", False),
    ("3A. Father's Information", "p3_1c_father_middle", "1.c. Father's Middle Name", "text", False),
    ("3A. Father's Information", "p3_2_father_dob", "2. Father's Date of Birth (mm/dd/yyyy)", "date", False),
    ("3A. Father's Information", "p3_3_father_sex", "3. Father's Sex", "select", False),
    ("3A. Father's Information", "p3_4_father_country_birth", "4. Father's Country of Birth", "text", False),
    ("3A. Father's Information", "p3_5_father_city_residence", "5. Father's City/Town of Current Residence", "text", False),
    ("3A. Father's Information", "p3_6_father_country_residence", "6. Father's Country of Current Residence", "text", False),

    # Mother's Information
    ("3B. Mother's Information", "p3_7a_mother_family", "7.a. Mother's Family Name (Last Name)", "text", False),
    ("3B. Mother's Information", "p3_7b_mother_given", "7.b. Mother's Given Name (First Name)", "text", False),
    ("3B. Mother's Information", "p3_7c_mother_middle", "7.c. Mother's Middle Name", "text", False),
    ("3B. Mother's Information", "p3_8_mother_maiden", "8. Mother's Maiden Family Name", "text", False),
    ("3B. Mother's Information", "p3_9_mother_dob", "9. Mother's Date of Birth (mm/dd/yyyy)", "date", False),
    ("3B. Mother's Information", "p3_10_mother_sex", "10. Mother's Sex", "select", False),
    ("3B. Mother's Information", "p3_11_mother_country_birth", "11. Mother's Country of Birth", "text", False),
    ("3B. Mother's Information", "p3_12_mother_city_residence", "12. Mother's City/Town of Current Residence", "text", False),
    ("3B. Mother's Information", "p3_13_mother_country_residence", "13. Mother's Country of Current Residence", "text", False),

    # =========================================================================
    # PART 4: SPOUSE BENEFICIARY'S STATEMENT
    # =========================================================================
    ("4A. Statement", "p4_1a_can_read", "1.a. I can read and understand English", "checkbox", False),
    ("4A. Statement", "p4_1b_interpreter_read", "1.b. The interpreter named in Part 5 read to me", "checkbox", False),
    ("4A. Statement", "p4_2_preparer_assisted", "2. At my request, the preparer named in Part 6 prepared this form", "checkbox", False),
    ("4B. Contact Information", "p4_3_daytime_phone", "3. Beneficiary's Daytime Telephone Number", "phone", False),
    ("4B. Contact Information", "p4_4_mobile_phone", "4. Beneficiary's Mobile Telephone Number", "phone", False),
    ("4B. Contact Information", "p4_5_email", "5. Beneficiary's Email Address", "email", False),
    ("4C. Certification", "p4_6_signature_date", "6. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 5: INTERPRETER'S INFORMATION
    # =========================================================================
    ("5A. Interpreter's Full Name", "p5_1a_interp_family", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("5A. Interpreter's Full Name", "p5_1b_interp_given", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("5A. Interpreter's Full Name", "p5_2_interp_org", "2. Interpreter's Business or Organization Name", "text", False),
    ("5B. Interpreter's Address", "p5_3a_interp_street", "3.a. Interpreter's Street Number and Name", "text", False),
    ("5B. Interpreter's Address", "p5_3b_interp_apt", "3.b. Interpreter's Apt/Ste/Flr", "text", False),
    ("5B. Interpreter's Address", "p5_3c_interp_city", "3.c. Interpreter's City or Town", "text", False),
    ("5B. Interpreter's Address", "p5_3d_interp_state", "3.d. Interpreter's State", "select", False),
    ("5B. Interpreter's Address", "p5_3e_interp_zip", "3.e. Interpreter's ZIP Code", "text", False),
    ("5B. Interpreter's Address", "p5_3f_interp_province", "3.f. Interpreter's Province", "text", False),
    ("5B. Interpreter's Address", "p5_3g_interp_postal", "3.g. Interpreter's Postal Code", "text", False),
    ("5B. Interpreter's Address", "p5_3h_interp_country", "3.h. Interpreter's Country", "text", False),
    ("5C. Interpreter's Contact", "p5_4_interp_phone", "4. Interpreter's Daytime Telephone Number", "phone", False),
    ("5C. Interpreter's Contact", "p5_5_interp_mobile", "5. Interpreter's Mobile Telephone Number", "phone", False),
    ("5C. Interpreter's Contact", "p5_6_interp_email", "6. Interpreter's Email Address", "email", False),
    ("5D. Interpreter's Certification", "p5_7_language", "7. Language Interpreted", "text", False),
    ("5D. Interpreter's Certification", "p5_8_interp_signature_date", "8. Interpreter's Signature Date", "date", False),

    # =========================================================================
    # PART 6: PREPARER'S INFORMATION
    # =========================================================================
    ("6A. Preparer's Statement", "p6_1a_prep_not_attorney", "1.a. I am NOT an attorney or accredited representative", "checkbox", False),
    ("6A. Preparer's Statement", "p6_1b_prep_is_attorney", "1.b. I AM an attorney or accredited representative", "checkbox", False),
    ("6B. Preparer's Full Name", "p6_2a_prep_family", "2.a. Preparer's Family Name (Last Name)", "text", False),
    ("6B. Preparer's Full Name", "p6_2b_prep_given", "2.b. Preparer's Given Name (First Name)", "text", False),
    ("6B. Preparer's Full Name", "p6_3_prep_org", "3. Preparer's Business or Organization Name", "text", False),
    ("6C. Preparer's Address", "p6_4a_prep_street", "4.a. Preparer's Street Number and Name", "text", False),
    ("6C. Preparer's Address", "p6_4b_prep_apt", "4.b. Preparer's Apt/Ste/Flr", "text", False),
    ("6C. Preparer's Address", "p6_4c_prep_city", "4.c. Preparer's City or Town", "text", False),
    ("6C. Preparer's Address", "p6_4d_prep_state", "4.d. Preparer's State", "select", False),
    ("6C. Preparer's Address", "p6_4e_prep_zip", "4.e. Preparer's ZIP Code", "text", False),
    ("6C. Preparer's Address", "p6_4f_prep_province", "4.f. Preparer's Province", "text", False),
    ("6C. Preparer's Address", "p6_4g_prep_postal", "4.g. Preparer's Postal Code", "text", False),
    ("6C. Preparer's Address", "p6_4h_prep_country", "4.h. Preparer's Country", "text", False),
    ("6D. Preparer's Contact", "p6_5_prep_phone", "5. Preparer's Daytime Telephone Number", "phone", False),
    ("6D. Preparer's Contact", "p6_6_prep_mobile", "6. Preparer's Mobile Telephone Number", "phone", False),
    ("6D. Preparer's Contact", "p6_7_prep_email", "7. Preparer's Email Address", "email", False),
    ("6E. Preparer's Certification", "p6_8_prep_extends", "8. Does representation extend beyond this case?", "radio", False),
    ("6E. Preparer's Certification", "p6_9_prep_signature_date", "9. Preparer's Signature Date", "date", False),

    # =========================================================================
    # PART 7: ADDITIONAL INFORMATION
    # =========================================================================
    ("7. Additional Information", "p7_1a_page", "1.a. Page Number", "text", False),
    ("7. Additional Information", "p7_1b_part", "1.b. Part Number", "text", False),
    ("7. Additional Information", "p7_1c_item", "1.c. Item Number", "text", False),
    ("7. Additional Information", "p7_1d_answer", "1.d. Additional Information", "textarea", False),
    ("7. Additional Information", "p7_2a_page", "2.a. Page Number", "text", False),
    ("7. Additional Information", "p7_2b_part", "2.b. Part Number", "text", False),
    ("7. Additional Information", "p7_2c_item", "2.c. Item Number", "text", False),
    ("7. Additional Information", "p7_2d_answer", "2.d. Additional Information", "textarea", False),
    ("7. Additional Information", "p7_3_additional", "3. Additional Information (continue)", "textarea", False),
]

def update_form(template_id: int, fields: list, form_name: str):
    """Update a form with all fields."""
    with engine.connect() as conn:
        # Delete existing fields
        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        # Insert all fields
        for i, field in enumerate(fields):
            section, field_name, label, field_type, required = field
            conn.execute(text("""
                INSERT INTO questionnaire_fields
                (template_id, field_name, label, field_type, is_required, section, "order")
                VALUES (:tid, :fname, :label, :ftype, :req, :section, :ord)
            """), {
                'tid': template_id,
                'fname': field_name,
                'label': label,
                'ftype': field_type,
                'req': required,
                'section': section,
                'ord': i + 1
            })

        conn.commit()
        print(f"{form_name} updated: {len(fields)} fields")

if __name__ == "__main__":
    # Update I-130A
    update_form(39, I130A_FIELDS, "I-130A")
