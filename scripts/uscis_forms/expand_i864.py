#!/usr/bin/env python3
"""
Expand I-864 (Affidavit of Support) with ALL official USCIS fields
Form I-864 has 11 Parts covering sponsor information, household, income, assets
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I864_FIELDS = [
    # =========================================================================
    # PART 1: BASIS FOR FILING AFFIDAVIT OF SUPPORT
    # =========================================================================
    ("1. Basis for Filing", "p1_1a_petitioner", "1.a. I am the petitioner (filed or will file Form I-130)", "checkbox", False),
    ("1. Basis for Filing", "p1_1b_i140_filer", "1.b. I filed or will file Form I-140 and am related to the intending immigrant", "checkbox", False),
    ("1. Basis for Filing", "p1_1c_ownership", "1.c. I have 5%+ ownership in entity that filed I-140", "checkbox", False),
    ("1. Basis for Filing", "p1_1d_sole_joint", "1.d. I am the only joint sponsor", "checkbox", False),
    ("1. Basis for Filing", "p1_1e_first_joint", "1.e. I am the first of two joint sponsors", "checkbox", False),
    ("1. Basis for Filing", "p1_1f_second_joint", "1.f. I am the second of two joint sponsors", "checkbox", False),
    ("1. Basis for Filing", "p1_1g_substitute", "1.g. I am a substitute sponsor", "checkbox", False),
    ("1. Basis for Filing", "p1_2_relationship", "2. If 1.b or 1.c, specify relationship to immigrant", "text", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT THE PRINCIPAL IMMIGRANT
    # =========================================================================
    ("2A. Principal Immigrant's Name", "p2_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("2A. Principal Immigrant's Name", "p2_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("2A. Principal Immigrant's Name", "p2_1c_middle_name", "1.c. Middle Name", "text", False),
    ("2B. Mailing Address", "p2_2a_care_of", "2.a. In Care Of Name (c/o)", "text", False),
    ("2B. Mailing Address", "p2_2b_street", "2.b. Street Number and Name", "text", True),
    ("2B. Mailing Address", "p2_2c_apt_type", "2.c. Apt/Ste/Flr Type", "select", False),
    ("2B. Mailing Address", "p2_2d_apt_number", "2.d. Apt/Ste/Flr Number", "text", False),
    ("2B. Mailing Address", "p2_2e_city", "2.e. City or Town", "text", True),
    ("2B. Mailing Address", "p2_2f_state", "2.f. State", "select", False),
    ("2B. Mailing Address", "p2_2g_zip", "2.g. ZIP Code", "text", False),
    ("2B. Mailing Address", "p2_2h_province", "2.h. Province (if outside U.S.)", "text", False),
    ("2B. Mailing Address", "p2_2i_postal", "2.i. Postal Code (if outside U.S.)", "text", False),
    ("2B. Mailing Address", "p2_2j_country", "2.j. Country", "text", True),
    ("2C. Other Information", "p2_3_dob", "3. Date of Birth (mm/dd/yyyy)", "date", True),
    ("2C. Other Information", "p2_4_a_number", "4. Alien Registration Number (A-Number)", "text", False),
    ("2C. Other Information", "p2_5_uscis_account", "5. USCIS Online Account Number", "text", False),
    ("2C. Other Information", "p2_6_relationship", "6. Relationship to You (Sponsor)", "text", True),

    # =========================================================================
    # PART 3: INFORMATION ABOUT IMMIGRANTS BEING SPONSORED
    # =========================================================================
    ("3A. Family Members", "p3_1_sponsoring_immigrant_only", "1. I am NOT sponsoring accompanying family members", "checkbox", False),
    ("3A. Family Members", "p3_2_sponsoring_family", "2. I AM sponsoring the following family members", "checkbox", False),

    # Family Member 1
    ("3B. Family Member 1", "p3_3a_fm1_family_name", "3.a. Family Member 1 - Family Name", "text", False),
    ("3B. Family Member 1", "p3_3b_fm1_given_name", "3.b. Family Member 1 - Given Name", "text", False),
    ("3B. Family Member 1", "p3_3c_fm1_middle_name", "3.c. Family Member 1 - Middle Name", "text", False),
    ("3B. Family Member 1", "p3_4_fm1_relationship", "4. Family Member 1 - Relationship to Principal", "text", False),
    ("3B. Family Member 1", "p3_5_fm1_dob", "5. Family Member 1 - Date of Birth", "date", False),
    ("3B. Family Member 1", "p3_6_fm1_a_number", "6. Family Member 1 - A-Number", "text", False),

    # Family Member 2
    ("3C. Family Member 2", "p3_7a_fm2_family_name", "7.a. Family Member 2 - Family Name", "text", False),
    ("3C. Family Member 2", "p3_7b_fm2_given_name", "7.b. Family Member 2 - Given Name", "text", False),
    ("3C. Family Member 2", "p3_7c_fm2_middle_name", "7.c. Family Member 2 - Middle Name", "text", False),
    ("3C. Family Member 2", "p3_8_fm2_relationship", "8. Family Member 2 - Relationship to Principal", "text", False),
    ("3C. Family Member 2", "p3_9_fm2_dob", "9. Family Member 2 - Date of Birth", "date", False),
    ("3C. Family Member 2", "p3_10_fm2_a_number", "10. Family Member 2 - A-Number", "text", False),

    # Family Member 3
    ("3D. Family Member 3", "p3_11a_fm3_family_name", "11.a. Family Member 3 - Family Name", "text", False),
    ("3D. Family Member 3", "p3_11b_fm3_given_name", "11.b. Family Member 3 - Given Name", "text", False),
    ("3D. Family Member 3", "p3_11c_fm3_middle_name", "11.c. Family Member 3 - Middle Name", "text", False),
    ("3D. Family Member 3", "p3_12_fm3_relationship", "12. Family Member 3 - Relationship to Principal", "text", False),
    ("3D. Family Member 3", "p3_13_fm3_dob", "13. Family Member 3 - Date of Birth", "date", False),
    ("3D. Family Member 3", "p3_14_fm3_a_number", "14. Family Member 3 - A-Number", "text", False),

    # Family Member 4
    ("3E. Family Member 4", "p3_15a_fm4_family_name", "15.a. Family Member 4 - Family Name", "text", False),
    ("3E. Family Member 4", "p3_15b_fm4_given_name", "15.b. Family Member 4 - Given Name", "text", False),
    ("3E. Family Member 4", "p3_15c_fm4_middle_name", "15.c. Family Member 4 - Middle Name", "text", False),
    ("3E. Family Member 4", "p3_16_fm4_relationship", "16. Family Member 4 - Relationship to Principal", "text", False),
    ("3E. Family Member 4", "p3_17_fm4_dob", "17. Family Member 4 - Date of Birth", "date", False),
    ("3E. Family Member 4", "p3_18_fm4_a_number", "18. Family Member 4 - A-Number", "text", False),

    # Family Member 5
    ("3F. Family Member 5", "p3_19a_fm5_family_name", "19.a. Family Member 5 - Family Name", "text", False),
    ("3F. Family Member 5", "p3_19b_fm5_given_name", "19.b. Family Member 5 - Given Name", "text", False),
    ("3F. Family Member 5", "p3_19c_fm5_middle_name", "19.c. Family Member 5 - Middle Name", "text", False),
    ("3F. Family Member 5", "p3_20_fm5_relationship", "20. Family Member 5 - Relationship to Principal", "text", False),
    ("3F. Family Member 5", "p3_21_fm5_dob", "21. Family Member 5 - Date of Birth", "date", False),
    ("3F. Family Member 5", "p3_22_fm5_a_number", "22. Family Member 5 - A-Number", "text", False),

    ("3G. Total", "p3_23_total_immigrants", "23. Total Number of Immigrants Being Sponsored", "number", True),

    # =========================================================================
    # PART 4: INFORMATION ABOUT THE SPONSOR
    # =========================================================================
    ("4A. Sponsor's Full Name", "p4_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("4A. Sponsor's Full Name", "p4_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("4A. Sponsor's Full Name", "p4_1c_middle_name", "1.c. Middle Name", "text", False),
    ("4B. Mailing Address", "p4_2a_care_of", "2.a. In Care Of Name (c/o)", "text", False),
    ("4B. Mailing Address", "p4_2b_street", "2.b. Street Number and Name", "text", True),
    ("4B. Mailing Address", "p4_2c_apt_type", "2.c. Apt/Ste/Flr Type", "select", False),
    ("4B. Mailing Address", "p4_2d_apt_number", "2.d. Apt/Ste/Flr Number", "text", False),
    ("4B. Mailing Address", "p4_2e_city", "2.e. City or Town", "text", True),
    ("4B. Mailing Address", "p4_2f_state", "2.f. State", "select", True),
    ("4B. Mailing Address", "p4_2g_zip", "2.g. ZIP Code", "text", True),
    ("4C. Other Information", "p4_3_country_domicile", "3. Country of Domicile", "text", True),
    ("4C. Other Information", "p4_4_dob", "4. Date of Birth (mm/dd/yyyy)", "date", True),
    ("4C. Other Information", "p4_5_city_birth", "5. City/Town of Birth", "text", False),
    ("4C. Other Information", "p4_6_state_birth", "6. State/Province of Birth", "text", False),
    ("4C. Other Information", "p4_7_country_birth", "7. Country of Birth", "text", True),
    ("4C. Other Information", "p4_8_ssn", "8. U.S. Social Security Number", "text", True),
    ("4D. Citizenship/Residence", "p4_9a_us_citizen", "9.a. I am a U.S. Citizen", "checkbox", False),
    ("4D. Citizenship/Residence", "p4_9b_us_national", "9.b. I am a U.S. National", "checkbox", False),
    ("4D. Citizenship/Residence", "p4_9c_lpr", "9.c. I am a Lawful Permanent Resident", "checkbox", False),
    ("4D. Citizenship/Residence", "p4_10_a_number", "10. Alien Registration Number (A-Number)", "text", False),
    ("4D. Citizenship/Residence", "p4_11_uscis_account", "11. USCIS Online Account Number", "text", False),
    ("4E. Military Service", "p4_12_active_duty", "12. Are you on active duty (other than training)?", "radio", False),

    # =========================================================================
    # PART 5: SPONSOR'S HOUSEHOLD SIZE
    # =========================================================================
    ("5A. Persons to Include", "p5_1_yourself", "1. Yourself (count = 1)", "number", True),
    ("5A. Persons to Include", "p5_2_spouse", "2. Your spouse (if living with you, count = 1, else 0)", "number", True),
    ("5A. Persons to Include", "p5_3_dependents", "3. Number of dependent children under 21", "number", True),
    ("5A. Persons to Include", "p5_4_other_dependents", "4. Number of other dependents claimed on tax return", "number", False),
    ("5A. Persons to Include", "p5_5_sponsored_immigrants", "5. Number of immigrants you are sponsoring in this affidavit", "number", True),
    ("5A. Persons to Include", "p5_6_previous_sponsored", "6. Number of immigrants previously sponsored (obligation still applies)", "number", False),
    ("5A. Persons to Include", "p5_7_total_household", "7. Total Household Size (add 1-6)", "number", True),

    # =========================================================================
    # PART 6: SPONSOR'S EMPLOYMENT AND INCOME
    # =========================================================================
    ("6A. Employment Status", "p6_1_employed", "1. I am employed as a/an:", "text", False),
    ("6A. Employment Status", "p6_1a_employer_name", "1.a. Name of Employer 1", "text", False),
    ("6A. Employment Status", "p6_1b_employer_address", "1.b. Employer 1 Address", "text", False),
    ("6A. Employment Status", "p6_2_self_employed", "2. I am self-employed as a/an:", "text", False),
    ("6A. Employment Status", "p6_3_retired", "3. I am retired since (date):", "date", False),
    ("6A. Employment Status", "p6_4_unemployed", "4. I am unemployed since (date):", "date", False),

    ("6B. Current Income", "p6_5_current_annual_income", "5. My current individual annual income is: $", "number", True),

    ("6C. Income From Other Persons", "p6_6_income_from_others", "6. I am using income from other persons in my household", "checkbox", False),
    ("6C. Income From Other Persons", "p6_7a_person1_name", "7.a. Household Member 1 - Name", "text", False),
    ("6C. Income From Other Persons", "p6_7b_person1_relationship", "7.b. Household Member 1 - Relationship", "text", False),
    ("6C. Income From Other Persons", "p6_7c_person1_income", "7.c. Household Member 1 - Current Annual Income $", "number", False),
    ("6C. Income From Other Persons", "p6_8a_person2_name", "8.a. Household Member 2 - Name", "text", False),
    ("6C. Income From Other Persons", "p6_8b_person2_relationship", "8.b. Household Member 2 - Relationship", "text", False),
    ("6C. Income From Other Persons", "p6_8c_person2_income", "8.c. Household Member 2 - Current Annual Income $", "number", False),
    ("6C. Income From Other Persons", "p6_9a_person3_name", "9.a. Household Member 3 - Name", "text", False),
    ("6C. Income From Other Persons", "p6_9b_person3_relationship", "9.b. Household Member 3 - Relationship", "text", False),
    ("6C. Income From Other Persons", "p6_9c_person3_income", "9.c. Household Member 3 - Current Annual Income $", "number", False),

    ("6D. Total Income", "p6_10_total_household_income", "10. Total Household Income (add all) $", "number", True),

    ("6E. Federal Income Tax", "p6_11_filed_taxes", "11. I have filed a Federal income tax return for each of the 3 most recent years", "radio", True),
    ("6E. Federal Income Tax", "p6_12_tax_year1", "12. Most recent tax year filed", "text", False),
    ("6E. Federal Income Tax", "p6_13_tax_year1_income", "13. Most recent tax year - Total Income $", "number", False),
    ("6E. Federal Income Tax", "p6_14_tax_year2", "14. Second most recent tax year", "text", False),
    ("6E. Federal Income Tax", "p6_15_tax_year2_income", "15. Second most recent - Total Income $", "number", False),
    ("6E. Federal Income Tax", "p6_16_tax_year3", "16. Third most recent tax year", "text", False),
    ("6E. Federal Income Tax", "p6_17_tax_year3_income", "17. Third most recent - Total Income $", "number", False),

    ("6F. Documents", "p6_18a_irs_transcript", "18.a. I am submitting IRS tax return transcripts", "checkbox", False),
    ("6F. Documents", "p6_18b_tax_returns", "18.b. I am submitting photocopies of my tax returns", "checkbox", False),
    ("6F. Documents", "p6_19_w2_attached", "19. I am attaching W-2s and/or 1099s", "checkbox", False),

    # =========================================================================
    # PART 7: USE OF ASSETS TO SUPPLEMENT INCOME
    # =========================================================================
    ("7A. Assets", "p7_1_using_assets", "1. I am using assets to supplement my income", "checkbox", False),
    ("7B. Sponsor's Assets", "p7_2_savings", "2. Savings deposits $", "number", False),
    ("7B. Sponsor's Assets", "p7_3_stocks_bonds", "3. Stocks and bonds $", "number", False),
    ("7B. Sponsor's Assets", "p7_4_real_estate", "4. Real estate (equity) $", "number", False),
    ("7B. Sponsor's Assets", "p7_5_other_assets", "5. Other assets $", "number", False),
    ("7B. Sponsor's Assets", "p7_6_total_sponsor_assets", "6. Total Value of Sponsor's Assets $", "number", False),

    ("7C. Immigrant's Assets", "p7_7_immigrant_savings", "7. Immigrant's Savings deposits $", "number", False),
    ("7C. Immigrant's Assets", "p7_8_immigrant_stocks", "8. Immigrant's Stocks and bonds $", "number", False),
    ("7C. Immigrant's Assets", "p7_9_immigrant_real_estate", "9. Immigrant's Real estate (equity) $", "number", False),
    ("7C. Immigrant's Assets", "p7_10_immigrant_other", "10. Immigrant's Other assets $", "number", False),
    ("7C. Immigrant's Assets", "p7_11_total_immigrant_assets", "11. Total Value of Immigrant's Assets $", "number", False),

    ("7D. Total Assets", "p7_12_total_all_assets", "12. Total Value of All Assets $", "number", False),

    # =========================================================================
    # PART 8: SPONSOR'S CONTRACT
    # =========================================================================
    ("8A. Contract Terms", "p8_1_acknowledge_contract", "1. I agree to be legally responsible for the financial support of the immigrant", "checkbox", True),
    ("8A. Contract Terms", "p8_2_maintain_income", "2. I agree to maintain the immigrant at 125% of Federal Poverty Guidelines", "checkbox", True),
    ("8A. Contract Terms", "p8_3_reimburse_benefits", "3. I agree to reimburse any means-tested public benefits", "checkbox", True),
    ("8A. Contract Terms", "p8_4_submit_to_jurisdiction", "4. I submit to the jurisdiction of any Federal or State court", "checkbox", True),
    ("8A. Contract Terms", "p8_5_provide_documents", "5. I authorize release of any information for verification", "checkbox", True),

    ("8B. Contact Information", "p8_6_daytime_phone", "6. Sponsor's Daytime Telephone Number", "phone", True),
    ("8B. Contact Information", "p8_7_mobile_phone", "7. Sponsor's Mobile Telephone Number", "phone", False),
    ("8B. Contact Information", "p8_8_email", "8. Sponsor's Email Address", "email", False),

    ("8C. Certification", "p8_9_signature_date", "9. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 9: INTERPRETER'S INFORMATION
    # =========================================================================
    ("9A. Interpreter's Name", "p9_1a_interp_family", "1.a. Interpreter's Family Name", "text", False),
    ("9A. Interpreter's Name", "p9_1b_interp_given", "1.b. Interpreter's Given Name", "text", False),
    ("9A. Interpreter's Name", "p9_2_interp_org", "2. Interpreter's Business or Organization", "text", False),
    ("9B. Interpreter's Address", "p9_3a_interp_street", "3.a. Interpreter's Street Number and Name", "text", False),
    ("9B. Interpreter's Address", "p9_3b_interp_apt", "3.b. Interpreter's Apt/Ste/Flr", "text", False),
    ("9B. Interpreter's Address", "p9_3c_interp_city", "3.c. Interpreter's City or Town", "text", False),
    ("9B. Interpreter's Address", "p9_3d_interp_state", "3.d. Interpreter's State", "select", False),
    ("9B. Interpreter's Address", "p9_3e_interp_zip", "3.e. Interpreter's ZIP Code", "text", False),
    ("9B. Interpreter's Address", "p9_3f_interp_province", "3.f. Interpreter's Province", "text", False),
    ("9B. Interpreter's Address", "p9_3g_interp_postal", "3.g. Interpreter's Postal Code", "text", False),
    ("9B. Interpreter's Address", "p9_3h_interp_country", "3.h. Interpreter's Country", "text", False),
    ("9C. Interpreter's Contact", "p9_4_interp_phone", "4. Interpreter's Daytime Telephone", "phone", False),
    ("9C. Interpreter's Contact", "p9_5_interp_mobile", "5. Interpreter's Mobile Telephone", "phone", False),
    ("9C. Interpreter's Contact", "p9_6_interp_email", "6. Interpreter's Email Address", "email", False),
    ("9D. Interpreter's Certification", "p9_7_language", "7. Language Interpreted", "text", False),
    ("9D. Interpreter's Certification", "p9_8_interp_signature_date", "8. Interpreter's Signature Date", "date", False),

    # =========================================================================
    # PART 10: PREPARER'S INFORMATION
    # =========================================================================
    ("10A. Preparer's Statement", "p10_1a_prep_not_attorney", "1.a. I am NOT an attorney or accredited representative", "checkbox", False),
    ("10A. Preparer's Statement", "p10_1b_prep_is_attorney", "1.b. I AM an attorney or accredited representative", "checkbox", False),
    ("10B. Preparer's Name", "p10_2a_prep_family", "2.a. Preparer's Family Name", "text", False),
    ("10B. Preparer's Name", "p10_2b_prep_given", "2.b. Preparer's Given Name", "text", False),
    ("10B. Preparer's Name", "p10_3_prep_org", "3. Preparer's Business or Organization", "text", False),
    ("10C. Preparer's Address", "p10_4a_prep_street", "4.a. Preparer's Street Number and Name", "text", False),
    ("10C. Preparer's Address", "p10_4b_prep_apt", "4.b. Preparer's Apt/Ste/Flr", "text", False),
    ("10C. Preparer's Address", "p10_4c_prep_city", "4.c. Preparer's City or Town", "text", False),
    ("10C. Preparer's Address", "p10_4d_prep_state", "4.d. Preparer's State", "select", False),
    ("10C. Preparer's Address", "p10_4e_prep_zip", "4.e. Preparer's ZIP Code", "text", False),
    ("10C. Preparer's Address", "p10_4f_prep_province", "4.f. Preparer's Province", "text", False),
    ("10C. Preparer's Address", "p10_4g_prep_postal", "4.g. Preparer's Postal Code", "text", False),
    ("10C. Preparer's Address", "p10_4h_prep_country", "4.h. Preparer's Country", "text", False),
    ("10D. Preparer's Contact", "p10_5_prep_phone", "5. Preparer's Daytime Telephone", "phone", False),
    ("10D. Preparer's Contact", "p10_6_prep_mobile", "6. Preparer's Mobile Telephone", "phone", False),
    ("10D. Preparer's Contact", "p10_7_prep_email", "7. Preparer's Email Address", "email", False),
    ("10E. Preparer's Certification", "p10_8_prep_extends", "8. Does representation extend beyond this case?", "radio", False),
    ("10E. Preparer's Certification", "p10_9_prep_signature_date", "9. Preparer's Signature Date", "date", False),

    # =========================================================================
    # PART 11: ADDITIONAL INFORMATION
    # =========================================================================
    ("11. Additional Information", "p11_1a_page", "1.a. Page Number", "text", False),
    ("11. Additional Information", "p11_1b_part", "1.b. Part Number", "text", False),
    ("11. Additional Information", "p11_1c_item", "1.c. Item Number", "text", False),
    ("11. Additional Information", "p11_1d_answer", "1.d. Additional Information", "textarea", False),
    ("11. Additional Information", "p11_2a_page", "2.a. Page Number", "text", False),
    ("11. Additional Information", "p11_2b_part", "2.b. Part Number", "text", False),
    ("11. Additional Information", "p11_2c_item", "2.c. Item Number", "text", False),
    ("11. Additional Information", "p11_2d_answer", "2.d. Additional Information", "textarea", False),
    ("11. Additional Information", "p11_3a_page", "3.a. Page Number", "text", False),
    ("11. Additional Information", "p11_3b_part", "3.b. Part Number", "text", False),
    ("11. Additional Information", "p11_3c_item", "3.c. Item Number", "text", False),
    ("11. Additional Information", "p11_3d_answer", "3.d. Additional Information", "textarea", False),
    ("11. Additional Information", "p11_4_additional", "4. Additional Information (continue)", "textarea", False),
    ("11. Additional Information", "p11_5_additional", "5. Additional Information (continue)", "textarea", False),
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
    update_form(41, I864_FIELDS, "I-864")
