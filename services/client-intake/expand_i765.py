#!/usr/bin/env python3
"""
Expand I-765 (Application for Employment Authorization) with ALL official USCIS fields
"""
import os
import json
from sqlalchemy import create_engine, text
from uscis_form_options import I765_OPTIONS_MAP

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/casehub")
engine = create_engine(DATABASE_URL)

I765_FIELDS = [
    # =========================================================================
    # PART 1: REASON FOR APPLYING
    # =========================================================================
    ("1. Reason for Applying", "p1_1a_initial", "1.a. Initial permission to accept employment", "checkbox", False),
    ("1. Reason for Applying", "p1_1b_replacement", "1.b. Replacement of lost, stolen, or damaged employment authorization document", "checkbox", False),
    ("1. Reason for Applying", "p1_1c_renewal", "1.c. Renewal of my permission to accept employment", "checkbox", False),
    ("1. Reason for Applying", "p1_2_previously_filed", "2. Have you previously filed Form I-765?", "radio", False),
    ("1. Reason for Applying", "p1_3_if_yes_result", "3. If Yes, result of previous application:", "text", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT YOU
    # =========================================================================
    # Full Name
    ("2A. Your Full Name", "p2_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("2A. Your Full Name", "p2_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("2A. Your Full Name", "p2_1c_middle_name", "1.c. Middle Name", "text", False),

    # Other Names
    ("2B. Other Names Used", "p2_2_other_names_used", "2. Have you used other names since birth?", "radio", False),
    ("2B. Other Names Used", "p2_3a_other1_family", "3.a. Other Name 1 - Family Name", "text", False),
    ("2B. Other Names Used", "p2_3b_other1_given", "3.b. Other Name 1 - Given Name", "text", False),
    ("2B. Other Names Used", "p2_3c_other1_middle", "3.c. Other Name 1 - Middle Name", "text", False),
    ("2B. Other Names Used", "p2_4a_other2_family", "4.a. Other Name 2 - Family Name", "text", False),
    ("2B. Other Names Used", "p2_4b_other2_given", "4.b. Other Name 2 - Given Name", "text", False),
    ("2B. Other Names Used", "p2_4c_other2_middle", "4.c. Other Name 2 - Middle Name", "text", False),

    # Mailing Address
    ("2C. U.S. Mailing Address", "p2_5a_care_of", "5.a. In Care Of Name (c/o)", "text", False),
    ("2C. U.S. Mailing Address", "p2_5b_street", "5.b. Street Number and Name", "text", True),
    ("2C. U.S. Mailing Address", "p2_5c_apt_type", "5.c. Apt/Ste/Flr Type", "select", False),
    ("2C. U.S. Mailing Address", "p2_5d_apt_number", "5.d. Apt/Ste/Flr Number", "text", False),
    ("2C. U.S. Mailing Address", "p2_5e_city", "5.e. City or Town", "text", True),
    ("2C. U.S. Mailing Address", "p2_5f_state", "5.f. State", "select", True),
    ("2C. U.S. Mailing Address", "p2_5g_zip", "5.g. ZIP Code", "text", True),
    ("2C. U.S. Mailing Address", "p2_6_safe_address", "6. Is your mailing address the same as your physical address?", "radio", False),

    # Physical Address
    ("2D. U.S. Physical Address", "p2_7a_phys_street", "7.a. Physical Address - Street Number and Name", "text", False),
    ("2D. U.S. Physical Address", "p2_7b_phys_apt_type", "7.b. Physical Address - Apt/Ste/Flr Type", "select", False),
    ("2D. U.S. Physical Address", "p2_7c_phys_apt_number", "7.c. Physical Address - Apt/Ste/Flr Number", "text", False),
    ("2D. U.S. Physical Address", "p2_7d_phys_city", "7.d. Physical Address - City or Town", "text", False),
    ("2D. U.S. Physical Address", "p2_7e_phys_state", "7.e. Physical Address - State", "select", False),
    ("2D. U.S. Physical Address", "p2_7f_phys_zip", "7.f. Physical Address - ZIP Code", "text", False),

    # Identification Numbers
    ("2E. Identification Numbers", "p2_8_a_number", "8. Alien Registration Number (A-Number)", "text", False),
    ("2E. Identification Numbers", "p2_9_uscis_account", "9. USCIS Online Account Number", "text", False),
    ("2E. Identification Numbers", "p2_10_i94_number", "10. Form I-94 Arrival-Departure Record Number", "text", False),
    ("2E. Identification Numbers", "p2_11_passport_number", "11. Passport Number", "text", False),
    ("2E. Identification Numbers", "p2_12_travel_doc_number", "12. Travel Document Number (if different)", "text", False),
    ("2E. Identification Numbers", "p2_13_passport_country", "13. Country That Issued Your Passport or Travel Document", "text", False),
    ("2E. Identification Numbers", "p2_14_passport_exp", "14. Passport or Travel Document Expiration Date", "date", False),
    ("2E. Identification Numbers", "p2_15_sevis_number", "15. Student and Exchange Visitor Information System (SEVIS) Number", "text", False),

    # Biographic Information
    ("2F. Biographic Information", "p2_16_dob", "16. Date of Birth (mm/dd/yyyy)", "date", True),
    ("2F. Biographic Information", "p2_17_sex", "17. Sex", "select", True),
    ("2F. Biographic Information", "p2_18_city_birth", "18. City/Town of Birth", "text", True),
    ("2F. Biographic Information", "p2_19_state_birth", "19. State/Province of Birth", "text", False),
    ("2F. Biographic Information", "p2_20_country_birth", "20. Country of Birth", "text", True),
    ("2F. Biographic Information", "p2_21_citizenship", "21. Country of Citizenship or Nationality", "text", True),

    # Social Security
    ("2G. Social Security", "p2_22_ssn_issued", "22. Has the SSA ever officially issued a Social Security card to you?", "radio", False),
    ("2G. Social Security", "p2_23_ssn", "23. U.S. Social Security Number", "text", False),
    ("2G. Social Security", "p2_24_want_ssn", "24. Do you want the SSA to issue you a Social Security card?", "radio", False),
    ("2G. Social Security", "p2_25_consent_ssa", "25. Consent for Disclosure: I authorize disclosure of information to SSA", "checkbox", False),
    ("2G. Social Security", "p2_26_father_family_name", "26. Father's Family Name at Birth", "text", False),
    ("2G. Social Security", "p2_27_mother_family_name", "27. Mother's Family Name at Birth", "text", False),

    # Immigration Information
    ("2H. Immigration Information", "p2_28_date_last_entry", "28. Date of Your Last Arrival Into the United States", "date", True),
    ("2H. Immigration Information", "p2_29_place_last_entry", "29. Place of Your Last Arrival Into the United States", "text", True),
    ("2H. Immigration Information", "p2_30_status_at_entry", "30. Immigration Status at Your Last Arrival", "text", True),
    ("2H. Immigration Information", "p2_31_current_status", "31. Your Current Immigration Status or Category", "text", True),
    ("2H. Immigration Information", "p2_32_status_exp_date", "32. Date Your Current Status Expires", "date", False),

    # Eligibility Category
    ("2I. Eligibility Category", "p2_33_eligibility_category", "33. Eligibility Category (e.g., (c)(9), (c)(10), (a)(12))", "select", True),
    ("2I. Eligibility Category", "p2_34_category_description", "34. Description of Eligibility Category (if applicable)", "text", False),

    # STEM OPT
    ("2J. STEM OPT Information", "p2_35_stem_opt", "35. Are you applying for a STEM OPT extension?", "radio", False),
    ("2J. STEM OPT Information", "p2_36_degree_from_stem", "36. STEM Degree - Name of School", "text", False),
    ("2J. STEM OPT Information", "p2_37_stem_degree_date", "37. Date STEM Degree Awarded", "date", False),
    ("2J. STEM OPT Information", "p2_38_employer_name", "38. Employer Name", "text", False),
    ("2J. STEM OPT Information", "p2_39_employer_address", "39. Employer Address", "text", False),
    ("2J. STEM OPT Information", "p2_40_employer_everify", "40. Employer E-Verify Company ID Number", "text", False),

    # Previous EAD Information
    ("2K. Previous EAD", "p2_41_prev_ead_category", "41. Previous EAD - Eligibility Category", "text", False),
    ("2K. Previous EAD", "p2_42_prev_ead_number", "42. Previous EAD - Card Number (from Card)", "text", False),
    ("2K. Previous EAD", "p2_43_prev_ead_exp", "43. Previous EAD - Expiration Date", "date", False),

    # Marital Status
    ("2L. Marital Status", "p2_44_marital_status", "44. Marital Status", "select", False),

    # =========================================================================
    # PART 3: APPLICANT'S STATEMENT, CONTACT, CERTIFICATION, AND SIGNATURE
    # =========================================================================
    ("3A. Applicant's Statement", "p3_1a_can_read", "1.a. I can read and understand English, and I have read this application", "checkbox", False),
    ("3A. Applicant's Statement", "p3_1b_interpreter_read", "1.b. The interpreter named in Part 4 read to me every question and instruction", "checkbox", False),
    ("3A. Applicant's Statement", "p3_2_preparer_assisted", "2. At my request, the preparer named in Part 5 prepared this application for me", "checkbox", False),
    ("3A. Applicant's Statement", "p3_3_abc_eligible", "3. I am eligible for benefits under ABC Settlement Agreement", "checkbox", False),

    ("3B. Contact Information", "p3_4_daytime_phone", "4. Applicant's Daytime Telephone Number", "phone", True),
    ("3B. Contact Information", "p3_5_mobile_phone", "5. Applicant's Mobile Telephone Number", "phone", False),
    ("3B. Contact Information", "p3_6_email", "6. Applicant's Email Address", "email", False),

    ("3C. Certification", "p3_7_signature_date", "7. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 4: INTERPRETER'S INFORMATION
    # =========================================================================
    ("4A. Interpreter's Name", "p4_1a_interp_family", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("4A. Interpreter's Name", "p4_1b_interp_given", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("4A. Interpreter's Name", "p4_2_interp_org", "2. Interpreter's Business or Organization Name", "text", False),
    ("4B. Interpreter's Address", "p4_3a_interp_street", "3.a. Interpreter's Street Number and Name", "text", False),
    ("4B. Interpreter's Address", "p4_3b_interp_apt", "3.b. Interpreter's Apt/Ste/Flr", "text", False),
    ("4B. Interpreter's Address", "p4_3c_interp_city", "3.c. Interpreter's City or Town", "text", False),
    ("4B. Interpreter's Address", "p4_3d_interp_state", "3.d. Interpreter's State", "select", False),
    ("4B. Interpreter's Address", "p4_3e_interp_zip", "3.e. Interpreter's ZIP Code", "text", False),
    ("4B. Interpreter's Address", "p4_3f_interp_province", "3.f. Interpreter's Province", "text", False),
    ("4B. Interpreter's Address", "p4_3g_interp_postal", "3.g. Interpreter's Postal Code", "text", False),
    ("4B. Interpreter's Address", "p4_3h_interp_country", "3.h. Interpreter's Country", "text", False),
    ("4C. Interpreter's Contact", "p4_4_interp_phone", "4. Interpreter's Daytime Telephone Number", "phone", False),
    ("4C. Interpreter's Contact", "p4_5_interp_mobile", "5. Interpreter's Mobile Telephone Number", "phone", False),
    ("4C. Interpreter's Contact", "p4_6_interp_email", "6. Interpreter's Email Address", "email", False),
    ("4D. Interpreter's Certification", "p4_7_language", "7. Language Interpreted", "text", False),
    ("4D. Interpreter's Certification", "p4_8_interp_signature_date", "8. Interpreter's Signature Date", "date", False),

    # =========================================================================
    # PART 5: PREPARER'S INFORMATION
    # =========================================================================
    ("5A. Preparer's Statement", "p5_1a_prep_not_attorney", "1.a. I am NOT an attorney or accredited representative", "checkbox", False),
    ("5A. Preparer's Statement", "p5_1b_prep_is_attorney", "1.b. I AM an attorney or accredited representative", "checkbox", False),
    ("5B. Preparer's Name", "p5_2a_prep_family", "2.a. Preparer's Family Name (Last Name)", "text", False),
    ("5B. Preparer's Name", "p5_2b_prep_given", "2.b. Preparer's Given Name (First Name)", "text", False),
    ("5B. Preparer's Name", "p5_3_prep_org", "3. Preparer's Business or Organization Name", "text", False),
    ("5C. Preparer's Address", "p5_4a_prep_street", "4.a. Preparer's Street Number and Name", "text", False),
    ("5C. Preparer's Address", "p5_4b_prep_apt", "4.b. Preparer's Apt/Ste/Flr", "text", False),
    ("5C. Preparer's Address", "p5_4c_prep_city", "4.c. Preparer's City or Town", "text", False),
    ("5C. Preparer's Address", "p5_4d_prep_state", "4.d. Preparer's State", "select", False),
    ("5C. Preparer's Address", "p5_4e_prep_zip", "4.e. Preparer's ZIP Code", "text", False),
    ("5C. Preparer's Address", "p5_4f_prep_province", "4.f. Preparer's Province", "text", False),
    ("5C. Preparer's Address", "p5_4g_prep_postal", "4.g. Preparer's Postal Code", "text", False),
    ("5C. Preparer's Address", "p5_4h_prep_country", "4.h. Preparer's Country", "text", False),
    ("5D. Preparer's Contact", "p5_5_prep_phone", "5. Preparer's Daytime Telephone Number", "phone", False),
    ("5D. Preparer's Contact", "p5_6_prep_mobile", "6. Preparer's Mobile Telephone Number", "phone", False),
    ("5D. Preparer's Contact", "p5_7_prep_email", "7. Preparer's Email Address", "email", False),
    ("5E. Preparer's Certification", "p5_8_prep_extends", "8. Does your representation extend beyond this case?", "radio", False),
    ("5E. Preparer's Certification", "p5_9_prep_signature_date", "9. Preparer's Signature Date", "date", False),

    # =========================================================================
    # PART 6: ADDITIONAL INFORMATION
    # =========================================================================
    ("6. Additional Information", "p6_1a_page", "1.a. Page Number", "text", False),
    ("6. Additional Information", "p6_1b_part", "1.b. Part Number", "text", False),
    ("6. Additional Information", "p6_1c_item", "1.c. Item Number", "text", False),
    ("6. Additional Information", "p6_1d_answer", "1.d. Additional Information", "textarea", False),
    ("6. Additional Information", "p6_2a_page", "2.a. Page Number", "text", False),
    ("6. Additional Information", "p6_2b_part", "2.b. Part Number", "text", False),
    ("6. Additional Information", "p6_2c_item", "2.c. Item Number", "text", False),
    ("6. Additional Information", "p6_2d_answer", "2.d. Additional Information", "textarea", False),
    ("6. Additional Information", "p6_3_additional", "3. Additional Information (continue)", "textarea", False),
]

def update_form(template_id: int, fields: list, form_name: str, options_map: dict):
    """Update a form with all fields including options for select/radio fields."""
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})
        for i, field in enumerate(fields):
            section, field_name, label, field_type, required = field
            # Get options from the options map if available
            options = options_map.get(field_name, None)
            options_json = json.dumps(options) if options else None

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
        print(f"{form_name} updated: {len(fields)} fields with options")

if __name__ == "__main__":
    update_form(42, I765_FIELDS, "I-765", I765_OPTIONS_MAP)
