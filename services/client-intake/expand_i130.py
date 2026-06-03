#!/usr/bin/env python3
"""
Expand I-130 with ALL official USCIS fields and OPTIONS
Updated: Includes dropdown options for all select/radio fields
"""
import os
import json
from sqlalchemy import create_engine, text

# Import options from centralized options file
from uscis_form_options import I130_OPTIONS_MAP

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/casehub")
engine = create_engine(DATABASE_URL)

I130_FIELDS = [
    # =========================================================================
    # PART 1: RELATIONSHIP
    # =========================================================================
    ("1. Relationship", "p1_1_filing_for", "1. I am filing this petition for my:", "select", True),
    ("1. Relationship", "p1_2a_child_unmarried_21", "2.a. If Child - Unmarried child under 21", "checkbox", False),
    ("1. Relationship", "p1_2b_child_unmarried_over21", "2.b. If Child - Unmarried child 21 or older", "checkbox", False),
    ("1. Relationship", "p1_2c_child_married", "2.c. If Child - Married child of any age", "checkbox", False),
    ("1. Relationship", "p1_3_sibling_adoption", "3. If Sibling - Are you related by adoption?", "radio", False),
    ("1. Relationship", "p1_4_lpr_adoption", "4. Did you gain LPR status through adoption?", "radio", False),
    ("1. Relationship", "p1_5_step_relationship", "5. If step relationship, was it created before beneficiary turned 18?", "radio", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT YOU (Petitioner)
    # =========================================================================
    ("2A. Petitioner ID Numbers", "p2_1_a_number", "1. Alien Registration Number (A-Number)", "text", False),
    ("2A. Petitioner ID Numbers", "p2_2_uscis_account", "2. USCIS Online Account Number", "text", False),
    ("2A. Petitioner ID Numbers", "p2_3_ssn", "3. U.S. Social Security Number", "text", False),

    ("2B. Petitioner Name", "p2_4a_family_name", "4.a. Family Name (Last Name)", "text", True),
    ("2B. Petitioner Name", "p2_4b_given_name", "4.b. Given Name (First Name)", "text", True),
    ("2B. Petitioner Name", "p2_4c_middle_name", "4.c. Middle Name", "text", False),

    ("2C. Other Names Used", "p2_5a_other1_family", "5.a. Other Name 1 - Family Name", "text", False),
    ("2C. Other Names Used", "p2_5b_other1_given", "5.b. Other Name 1 - Given Name", "text", False),
    ("2C. Other Names Used", "p2_5c_other1_middle", "5.c. Other Name 1 - Middle Name", "text", False),
    ("2C. Other Names Used", "p2_6a_other2_family", "6.a. Other Name 2 - Family Name", "text", False),
    ("2C. Other Names Used", "p2_6b_other2_given", "6.b. Other Name 2 - Given Name", "text", False),

    ("2D. Petitioner Mailing Address", "p2_7a_mail_care_of", "7.a. In Care Of Name (c/o)", "text", False),
    ("2D. Petitioner Mailing Address", "p2_7b_mail_street", "7.b. Street Number and Name", "text", True),
    ("2D. Petitioner Mailing Address", "p2_7c_mail_apt_type", "7.c. Apt/Ste/Flr Type", "select", False),
    ("2D. Petitioner Mailing Address", "p2_7d_mail_apt_number", "7.d. Apt/Ste/Flr Number", "text", False),
    ("2D. Petitioner Mailing Address", "p2_7e_mail_city", "7.e. City or Town", "text", True),
    ("2D. Petitioner Mailing Address", "p2_7f_mail_state", "7.f. State", "select", True),
    ("2D. Petitioner Mailing Address", "p2_7g_mail_zip", "7.g. ZIP Code", "text", True),
    ("2D. Petitioner Mailing Address", "p2_7h_mail_province", "7.h. Province (if outside U.S.)", "text", False),
    ("2D. Petitioner Mailing Address", "p2_7i_mail_postal", "7.i. Postal Code (if outside U.S.)", "text", False),
    ("2D. Petitioner Mailing Address", "p2_7j_mail_country", "7.j. Country", "text", True),

    ("2E. Petitioner Physical Address", "p2_8_same_as_mailing", "8. Is your physical address the same as mailing address?", "radio", True),
    ("2E. Petitioner Physical Address", "p2_9a_phys_street", "9.a. Physical Address - Street Number and Name", "text", False),
    ("2E. Petitioner Physical Address", "p2_9b_phys_apt_type", "9.b. Physical Address - Apt/Ste/Flr Type", "select", False),
    ("2E. Petitioner Physical Address", "p2_9c_phys_apt_number", "9.c. Physical Address - Apt/Ste/Flr Number", "text", False),
    ("2E. Petitioner Physical Address", "p2_9d_phys_city", "9.d. Physical Address - City or Town", "text", False),
    ("2E. Petitioner Physical Address", "p2_9e_phys_state", "9.e. Physical Address - State", "select", False),
    ("2E. Petitioner Physical Address", "p2_9f_phys_zip", "9.f. Physical Address - ZIP Code", "text", False),
    ("2E. Petitioner Physical Address", "p2_9g_phys_province", "9.g. Physical Address - Province", "text", False),
    ("2E. Petitioner Physical Address", "p2_9h_phys_country", "9.h. Physical Address - Country", "text", False),

    ("2F. Petitioner Personal Info", "p2_10_dob", "10. Date of Birth (mm/dd/yyyy)", "date", True),
    ("2F. Petitioner Personal Info", "p2_11_city_birth", "11. City/Town of Birth", "text", True),
    ("2F. Petitioner Personal Info", "p2_12_state_birth", "12. State/Province of Birth", "text", False),
    ("2F. Petitioner Personal Info", "p2_13_country_birth", "13. Country of Birth", "text", True),
    ("2F. Petitioner Personal Info", "p2_14_citizenship", "14. Country of Citizenship or Nationality", "text", True),

    ("2G. Petitioner Immigration Status", "p2_15a_us_citizen", "15.a. I am a U.S. Citizen", "checkbox", False),
    ("2G. Petitioner Immigration Status", "p2_15b_lpr", "15.b. I am a Lawful Permanent Resident", "checkbox", False),
    ("2G. Petitioner Immigration Status", "p2_16_citizenship_how", "16. If U.S. citizen, how did you become a citizen?", "select", False),
    ("2G. Petitioner Immigration Status", "p2_17_certificate_number", "17. Certificate of Citizenship or Naturalization Number", "text", False),
    ("2G. Petitioner Immigration Status", "p2_18_certificate_place", "18. Place Certificate Issued", "text", False),
    ("2G. Petitioner Immigration Status", "p2_19_certificate_date", "19. Date Certificate Issued", "date", False),
    ("2G. Petitioner Immigration Status", "p2_20_class_admission", "20. If LPR - Class of Admission", "select", False),
    ("2G. Petitioner Immigration Status", "p2_21_lpr_date", "21. If LPR - Date of Admission", "date", False),

    ("2H. Petitioner Marital Status", "p2_22_marital_status", "22. Current Marital Status", "select", True),
    ("2H. Petitioner Marital Status", "p2_23_times_married", "23. How many times have you been married?", "number", True),

    ("2I. Petitioner Employment", "p2_24_employer_name", "24. Employer Name (or Self-Employed)", "text", False),
    ("2I. Petitioner Employment", "p2_25a_emp_street", "25.a. Employer Address - Street", "text", False),
    ("2I. Petitioner Employment", "p2_25b_emp_apt", "25.b. Employer Address - Suite", "text", False),
    ("2I. Petitioner Employment", "p2_25c_emp_city", "25.c. Employer Address - City", "text", False),
    ("2I. Petitioner Employment", "p2_25d_emp_state", "25.d. Employer Address - State", "select", False),
    ("2I. Petitioner Employment", "p2_25e_emp_zip", "25.e. Employer Address - ZIP Code", "text", False),
    ("2I. Petitioner Employment", "p2_25f_emp_province", "25.f. Employer Address - Province", "text", False),
    ("2I. Petitioner Employment", "p2_25g_emp_country", "25.g. Employer Address - Country", "text", False),

    # =========================================================================
    # PART 3: BIOGRAPHIC INFORMATION (Petitioner)
    # =========================================================================
    ("3A. Ethnicity", "p3_1_ethnicity", "1. Ethnicity - Are you Hispanic or Latino?", "radio", True),

    ("3B. Race", "p3_2a_race_white", "2.a. Race - White", "checkbox", False),
    ("3B. Race", "p3_2b_race_asian", "2.b. Race - Asian", "checkbox", False),
    ("3B. Race", "p3_2c_race_black", "2.c. Race - Black or African American", "checkbox", False),
    ("3B. Race", "p3_2d_race_native", "2.d. Race - American Indian or Alaska Native", "checkbox", False),
    ("3B. Race", "p3_2e_race_pacific", "2.e. Race - Native Hawaiian or Other Pacific Islander", "checkbox", False),

    ("3C. Physical", "p3_3a_height_feet", "3.a. Height - Feet", "number", True),
    ("3C. Physical", "p3_3b_height_inches", "3.b. Height - Inches", "number", True),
    ("3C. Physical", "p3_4_weight", "4. Weight (in pounds)", "number", True),
    ("3C. Physical", "p3_5_eye_color", "5. Eye Color", "select", True),
    ("3C. Physical", "p3_6_hair_color", "6. Hair Color", "select", True),

    # =========================================================================
    # PART 4: INFORMATION ABOUT BENEFICIARY
    # =========================================================================
    ("4A. Beneficiary ID Numbers", "p4_1_a_number", "1. Beneficiary's A-Number (if any)", "text", False),
    ("4A. Beneficiary ID Numbers", "p4_2_uscis_account", "2. Beneficiary's USCIS Online Account Number", "text", False),
    ("4A. Beneficiary ID Numbers", "p4_3_ssn", "3. Beneficiary's U.S. Social Security Number (if any)", "text", False),

    ("4B. Beneficiary Name", "p4_4a_family_name", "4.a. Beneficiary's Family Name (Last Name)", "text", True),
    ("4B. Beneficiary Name", "p4_4b_given_name", "4.b. Beneficiary's Given Name (First Name)", "text", True),
    ("4B. Beneficiary Name", "p4_4c_middle_name", "4.c. Beneficiary's Middle Name", "text", False),

    ("4C. Beneficiary Other Names", "p4_5a_other1_family", "5.a. Beneficiary Other Name 1 - Family Name", "text", False),
    ("4C. Beneficiary Other Names", "p4_5b_other1_given", "5.b. Beneficiary Other Name 1 - Given Name", "text", False),
    ("4C. Beneficiary Other Names", "p4_5c_other1_middle", "5.c. Beneficiary Other Name 1 - Middle Name", "text", False),
    ("4C. Beneficiary Other Names", "p4_6a_other2_family", "6.a. Beneficiary Other Name 2 - Family Name", "text", False),
    ("4C. Beneficiary Other Names", "p4_6b_other2_given", "6.b. Beneficiary Other Name 2 - Given Name", "text", False),

    ("4D. Beneficiary Address", "p4_7a_street", "7.a. Beneficiary's Address - Street", "text", True),
    ("4D. Beneficiary Address", "p4_7b_apt_type", "7.b. Beneficiary's Address - Apt/Ste/Flr Type", "select", False),
    ("4D. Beneficiary Address", "p4_7c_apt_number", "7.c. Beneficiary's Address - Apt/Ste/Flr Number", "text", False),
    ("4D. Beneficiary Address", "p4_7d_city", "7.d. Beneficiary's Address - City or Town", "text", True),
    ("4D. Beneficiary Address", "p4_7e_state", "7.e. Beneficiary's Address - State/Province", "text", False),
    ("4D. Beneficiary Address", "p4_7f_postal", "7.f. Beneficiary's Address - Postal Code", "text", False),
    ("4D. Beneficiary Address", "p4_7g_country", "7.g. Beneficiary's Address - Country", "text", True),

    ("4E. Beneficiary Personal Info", "p4_8_dob", "8. Beneficiary's Date of Birth (mm/dd/yyyy)", "date", True),
    ("4E. Beneficiary Personal Info", "p4_9_city_birth", "9. Beneficiary's City/Town of Birth", "text", True),
    ("4E. Beneficiary Personal Info", "p4_10_state_birth", "10. Beneficiary's State/Province of Birth", "text", False),
    ("4E. Beneficiary Personal Info", "p4_11_country_birth", "11. Beneficiary's Country of Birth", "text", True),
    ("4E. Beneficiary Personal Info", "p4_12_citizenship", "12. Beneficiary's Country of Citizenship/Nationality", "text", True),
    ("4E. Beneficiary Personal Info", "p4_13_sex", "13. Beneficiary's Sex", "select", True),

    ("4F. Beneficiary Marital Info", "p4_14_marital_status", "14. Beneficiary's Current Marital Status", "select", True),
    ("4F. Beneficiary Marital Info", "p4_15_times_married", "15. How many times has beneficiary been married?", "number", True),

    ("4G. Beneficiary in U.S.", "p4_16_in_us", "16. Is beneficiary currently in the United States?", "radio", True),
    ("4G. Beneficiary in U.S.", "p4_17_last_entry_date", "17. If yes, date of last arrival in U.S.", "date", False),
    ("4G. Beneficiary in U.S.", "p4_18_last_entry_city", "18. City/Town of last arrival", "text", False),
    ("4G. Beneficiary in U.S.", "p4_19_last_entry_state", "19. State of last arrival", "select", False),
    ("4G. Beneficiary in U.S.", "p4_20_i94_number", "20. I-94 Arrival-Departure Record Number", "text", False),
    ("4G. Beneficiary in U.S.", "p4_21_current_status", "21. Current Immigration Status", "text", False),
    ("4G. Beneficiary in U.S.", "p4_22_status_expires", "22. Date Status Expires (or D/S)", "text", False),

    ("4H. Beneficiary Travel Documents", "p4_23_passport_number", "23. Beneficiary's Passport Number", "text", False),
    ("4H. Beneficiary Travel Documents", "p4_24_travel_doc_number", "24. Travel Document Number (if different)", "text", False),
    ("4H. Beneficiary Travel Documents", "p4_25_passport_country", "25. Country That Issued Passport/Travel Doc", "text", False),
    ("4H. Beneficiary Travel Documents", "p4_26_passport_exp", "26. Passport/Travel Document Expiration Date", "date", False),

    ("4I. Beneficiary's Father", "p4_27a_father_family", "27.a. Beneficiary's Father - Family Name", "text", True),
    ("4I. Beneficiary's Father", "p4_27b_father_given", "27.b. Beneficiary's Father - Given Name", "text", True),
    ("4I. Beneficiary's Father", "p4_27c_father_middle", "27.c. Beneficiary's Father - Middle Name", "text", False),
    ("4I. Beneficiary's Father", "p4_28_father_dob", "28. Father's Date of Birth", "date", False),
    ("4I. Beneficiary's Father", "p4_29_father_sex", "29. Father's Sex", "select", False),
    ("4I. Beneficiary's Father", "p4_30_father_country_birth", "30. Father's Country of Birth", "text", False),
    ("4I. Beneficiary's Father", "p4_31_father_city_residence", "31. Father's Current City of Residence", "text", False),
    ("4I. Beneficiary's Father", "p4_32_father_country_residence", "32. Father's Current Country of Residence", "text", False),

    ("4J. Beneficiary's Mother", "p4_33a_mother_family", "33.a. Beneficiary's Mother - Family Name (Current)", "text", True),
    ("4J. Beneficiary's Mother", "p4_33b_mother_given", "33.b. Beneficiary's Mother - Given Name", "text", True),
    ("4J. Beneficiary's Mother", "p4_33c_mother_middle", "33.c. Beneficiary's Mother - Middle Name", "text", False),
    ("4J. Beneficiary's Mother", "p4_34_mother_maiden", "34. Mother's Maiden Name (Last Name at Birth)", "text", False),
    ("4J. Beneficiary's Mother", "p4_35_mother_dob", "35. Mother's Date of Birth", "date", False),
    ("4J. Beneficiary's Mother", "p4_36_mother_sex", "36. Mother's Sex", "select", False),
    ("4J. Beneficiary's Mother", "p4_37_mother_country_birth", "37. Mother's Country of Birth", "text", False),
    ("4J. Beneficiary's Mother", "p4_38_mother_city_residence", "38. Mother's Current City of Residence", "text", False),
    ("4J. Beneficiary's Mother", "p4_39_mother_country_residence", "39. Mother's Current Country of Residence", "text", False),

    # =========================================================================
    # PART 5: OTHER INFORMATION
    # =========================================================================
    ("5A. Prior Petitions", "p5_1_prior_petition", "1. Have you EVER previously filed a petition for this beneficiary or any other alien?", "radio", True),
    ("5A. Prior Petitions", "p5_2_prior_family", "2. If yes, beneficiary's family name", "text", False),
    ("5A. Prior Petitions", "p5_3_prior_given", "3. If yes, beneficiary's given name", "text", False),
    ("5A. Prior Petitions", "p5_4_prior_relationship", "4. Relationship to prior beneficiary", "text", False),
    ("5A. Prior Petitions", "p5_5_prior_date", "5. Date petition was filed", "date", False),
    ("5A. Prior Petitions", "p5_6_prior_result", "6. Result (approved, denied, withdrawn)", "select", False),

    ("5B. Immigration Violations", "p5_7_beneficiary_proceedings", "7. Is beneficiary in removal, deportation, or exclusion proceedings?", "radio", True),
    ("5B. Immigration Violations", "p5_8_beneficiary_removed", "8. Has beneficiary EVER been removed or deported from the U.S.?", "radio", True),
    ("5B. Immigration Violations", "p5_9_beneficiary_ina212", "9. Does INA section 212(a)(3)(C) apply to beneficiary?", "radio", True),

    # =========================================================================
    # PART 6: PETITIONER'S STATEMENT, CONTACT, AND SIGNATURE
    # =========================================================================
    ("6A. Petitioner Statement", "p6_1a_can_read", "1.a. I can read and understand English", "checkbox", False),
    ("6A. Petitioner Statement", "p6_1b_interpreter", "1.b. The interpreter read every question and instruction to me", "checkbox", False),
    ("6A. Petitioner Statement", "p6_2_preparer_assisted", "2. At my request, preparer prepared this petition for me", "checkbox", False),

    ("6B. Contact Information", "p6_3_daytime_phone", "3. Petitioner's Daytime Telephone Number", "phone", True),
    ("6B. Contact Information", "p6_4_mobile_phone", "4. Petitioner's Mobile Telephone Number", "phone", False),
    ("6B. Contact Information", "p6_5_email", "5. Petitioner's Email Address", "email", False),

    ("6C. Signature", "p6_6_signature_date", "6. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 7: INTERPRETER'S INFORMATION
    # =========================================================================
    ("7A. Interpreter Info", "p7_1a_interp_family", "1.a. Interpreter's Family Name", "text", False),
    ("7A. Interpreter Info", "p7_1b_interp_given", "1.b. Interpreter's Given Name", "text", False),
    ("7A. Interpreter Info", "p7_2_interp_org", "2. Interpreter's Business or Organization Name", "text", False),
    ("7B. Interpreter Address", "p7_3a_interp_street", "3.a. Interpreter's Address - Street", "text", False),
    ("7B. Interpreter Address", "p7_3b_interp_apt", "3.b. Interpreter's Address - Apt/Ste/Flr", "text", False),
    ("7B. Interpreter Address", "p7_3c_interp_city", "3.c. Interpreter's Address - City", "text", False),
    ("7B. Interpreter Address", "p7_3d_interp_state", "3.d. Interpreter's Address - State", "select", False),
    ("7B. Interpreter Address", "p7_3e_interp_zip", "3.e. Interpreter's Address - ZIP Code", "text", False),
    ("7B. Interpreter Address", "p7_3f_interp_country", "3.f. Interpreter's Address - Country", "text", False),
    ("7C. Interpreter Contact", "p7_4_interp_phone", "4. Interpreter's Daytime Telephone Number", "phone", False),
    ("7C. Interpreter Contact", "p7_5_interp_mobile", "5. Interpreter's Mobile Telephone Number", "phone", False),
    ("7C. Interpreter Contact", "p7_6_interp_email", "6. Interpreter's Email Address", "email", False),
    ("7D. Interpreter Certification", "p7_7_language", "7. Language Interpreted", "text", False),
    ("7D. Interpreter Certification", "p7_8_signature_date", "8. Interpreter's Signature Date", "date", False),

    # =========================================================================
    # PART 8: PREPARER'S INFORMATION
    # =========================================================================
    ("8A. Preparer Info", "p8_1a_prep_not_attorney", "1.a. I am NOT an attorney or accredited representative", "checkbox", False),
    ("8A. Preparer Info", "p8_1b_prep_is_attorney", "1.b. I AM an attorney or accredited representative", "checkbox", False),
    ("8A. Preparer Info", "p8_2a_prep_family", "2.a. Preparer's Family Name", "text", False),
    ("8A. Preparer Info", "p8_2b_prep_given", "2.b. Preparer's Given Name", "text", False),
    ("8A. Preparer Info", "p8_3_prep_org", "3. Preparer's Business or Organization Name", "text", False),
    ("8B. Preparer Address", "p8_4a_prep_street", "4.a. Preparer's Address - Street", "text", False),
    ("8B. Preparer Address", "p8_4b_prep_apt", "4.b. Preparer's Address - Apt/Ste/Flr", "text", False),
    ("8B. Preparer Address", "p8_4c_prep_city", "4.c. Preparer's Address - City", "text", False),
    ("8B. Preparer Address", "p8_4d_prep_state", "4.d. Preparer's Address - State", "select", False),
    ("8B. Preparer Address", "p8_4e_prep_zip", "4.e. Preparer's Address - ZIP Code", "text", False),
    ("8B. Preparer Address", "p8_4f_prep_country", "4.f. Preparer's Address - Country", "text", False),
    ("8C. Preparer Contact", "p8_5_prep_phone", "5. Preparer's Daytime Telephone Number", "phone", False),
    ("8C. Preparer Contact", "p8_6_prep_mobile", "6. Preparer's Mobile Telephone Number", "phone", False),
    ("8C. Preparer Contact", "p8_7_prep_email", "7. Preparer's Email Address", "email", False),
    ("8D. Preparer Certification", "p8_8_prep_extends", "8. Does your representation extend beyond preparation?", "radio", False),
    ("8D. Preparer Certification", "p8_9_signature_date", "9. Preparer's Signature Date", "date", False),

    # =========================================================================
    # PART 9: ADDITIONAL INFORMATION
    # =========================================================================
    ("9. Additional Information", "p9_1a_page", "1.a. Page Number", "text", False),
    ("9. Additional Information", "p9_1b_part", "1.b. Part Number", "text", False),
    ("9. Additional Information", "p9_1c_item", "1.c. Item Number", "text", False),
    ("9. Additional Information", "p9_1d_info", "1.d. Additional Information", "textarea", False),
    ("9. Additional Information", "p9_2a_page", "2.a. Page Number", "text", False),
    ("9. Additional Information", "p9_2b_part", "2.b. Part Number", "text", False),
    ("9. Additional Information", "p9_2c_item", "2.c. Item Number", "text", False),
    ("9. Additional Information", "p9_2d_info", "2.d. Additional Information", "textarea", False),
    ("9. Additional Information", "p9_3_info", "3. Additional Information (continue)", "textarea", False),
    ("9. Additional Information", "p9_4_info", "4. Additional Information (continue)", "textarea", False),
]


def update_i130():
    """Update I-130 questionnaire fields with options from USCIS forms"""
    template_id = 38  # I-130 template ID
    fields_with_options = 0

    with engine.connect() as conn:
        # Delete existing fields
        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, field in enumerate(I130_FIELDS):
            section, field_name, label, field_type, required = field

            # Get options for this field from the options map
            options = I130_OPTIONS_MAP.get(field_name, None)
            options_json = json.dumps(options) if options else None

            if options:
                fields_with_options += 1

            conn.execute(text("""
                INSERT INTO questionnaire_fields
                (template_id, field_name, label, field_type, is_required, section, "order", options)
                VALUES (:tid, :fname, :label, :ftype, :req, :section, :ord, :options)
            """), {
                'tid': template_id,
                'fname': field_name,
                'label': label,
                'ftype': field_type,
                'req': required,
                'section': section,
                'ord': i + 1,
                'options': options_json
            })

        conn.commit()
        print(f"I-130 updated: {len(I130_FIELDS)} fields total, {fields_with_options} with options")


if __name__ == "__main__":
    update_i130()
