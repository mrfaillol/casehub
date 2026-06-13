#!/usr/bin/env python3
"""
Expand I-864EZ (Affidavit of Support Under Section 213A of the INA - EZ Version)
Simplified version for sponsors who use only their own income. 5 pages, Parts 1-8.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I864EZ_FIELDS = [
    # =========================================================================
    # PART 1: BASIS FOR FILING
    # =========================================================================
    ("1. Filing Basis", "p1_1_petitioner", "1. I am the petitioner who filed or will file Form I-130", "checkbox", False),
    ("1. Filing Basis", "p1_2_substitute", "2. I am filing as a substitute sponsor", "checkbox", False),
    ("1. Filing Basis", "p1_3_joint_sponsor", "3. I am a joint sponsor", "checkbox", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT THE PRINCIPAL IMMIGRANT
    # =========================================================================
    ("2A. Immigrant Name", "p2_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("2A. Immigrant Name", "p2_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("2A. Immigrant Name", "p2_1c_middle_name", "1.c. Middle Name", "text", False),
    ("2A. Immigrant Address", "p2_2a_care_of", "2.a. In Care Of Name", "text", False),
    ("2A. Immigrant Address", "p2_2b_street", "2.b. Street Number and Name", "text", True),
    ("2A. Immigrant Address", "p2_2c_apt_type", "2.c. Apt/Ste/Flr Type", "select", False),
    ("2A. Immigrant Address", "p2_2d_apt_number", "2.d. Apt/Ste/Flr Number", "text", False),
    ("2A. Immigrant Address", "p2_2e_city", "2.e. City or Town", "text", True),
    ("2A. Immigrant Address", "p2_2f_state", "2.f. State", "select", False),
    ("2A. Immigrant Address", "p2_2g_zip", "2.g. ZIP Code", "text", False),
    ("2A. Immigrant Address", "p2_2h_province", "2.h. Province (foreign)", "text", False),
    ("2A. Immigrant Address", "p2_2i_postal", "2.i. Postal Code (foreign)", "text", False),
    ("2A. Immigrant Address", "p2_2j_country", "2.j. Country", "text", False),
    ("2A. Immigrant Details", "p2_3_dob", "3. Date of Birth (mm/dd/yyyy)", "date", True),
    ("2A. Immigrant Details", "p2_4_a_number", "4. Alien Registration Number (A-Number)", "text", False),
    ("2A. Immigrant Details", "p2_5_uscis_account", "5. USCIS Online Account Number", "text", False),

    # =========================================================================
    # PART 3: INFORMATION ABOUT THE SPONSOR
    # =========================================================================
    ("3A. Sponsor Name", "p3_1a_family_name", "1.a. Sponsor's Family Name (Last Name)", "text", True),
    ("3A. Sponsor Name", "p3_1b_given_name", "1.b. Sponsor's Given Name (First Name)", "text", True),
    ("3A. Sponsor Name", "p3_1c_middle_name", "1.c. Sponsor's Middle Name", "text", False),
    ("3A. Sponsor Address", "p3_2a_care_of", "2.a. In Care Of Name", "text", False),
    ("3A. Sponsor Address", "p3_2b_street", "2.b. Street Number and Name", "text", True),
    ("3A. Sponsor Address", "p3_2c_apt_type", "2.c. Apt/Ste/Flr Type", "select", False),
    ("3A. Sponsor Address", "p3_2d_apt_number", "2.d. Apt/Ste/Flr Number", "text", False),
    ("3A. Sponsor Address", "p3_2e_city", "2.e. City or Town", "text", True),
    ("3A. Sponsor Address", "p3_2f_state", "2.f. State", "select", True),
    ("3A. Sponsor Address", "p3_2g_zip", "2.g. ZIP Code", "text", True),
    ("3A. Sponsor Details", "p3_3_country_domicile", "3. Country of Domicile", "text", True),
    ("3A. Sponsor Details", "p3_4_dob", "4. Date of Birth (mm/dd/yyyy)", "date", True),
    ("3A. Sponsor Details", "p3_5_city_birth", "5. City/Town of Birth", "text", False),
    ("3A. Sponsor Details", "p3_6_state_birth", "6. State/Province of Birth", "text", False),
    ("3A. Sponsor Details", "p3_7_country_birth", "7. Country of Birth", "text", True),
    ("3A. Sponsor IDs", "p3_8_ssn", "8. U.S. Social Security Number", "text", True),
    ("3A. Sponsor IDs", "p3_9_uscis_account", "9. USCIS Online Account Number", "text", False),
    ("3A. Sponsor IDs", "p3_10_a_number", "10. Alien Registration Number (A-Number)", "text", False),
    ("3A. Sponsor Status", "p3_11_us_citizen", "11. I am a U.S. citizen", "checkbox", False),
    ("3A. Sponsor Status", "p3_12_lpr", "12. I am a lawful permanent resident", "checkbox", False),

    # =========================================================================
    # PART 4: SPONSOR'S HOUSEHOLD SIZE
    # =========================================================================
    ("4. Household Size", "p4_1_yourself", "1. Yourself (count 1)", "number", True),
    ("4. Household Size", "p4_2_spouse", "2. If married, count your spouse (0 or 1)", "number", False),
    ("4. Household Size", "p4_3_dependents", "3. Number of dependent children", "number", False),
    ("4. Household Size", "p4_4_other_dependents", "4. Number of other dependents", "number", False),
    ("4. Household Size", "p4_5_sponsored", "5. Number of immigrants being sponsored on this affidavit", "number", True),
    ("4. Household Size", "p4_6_total", "6. Total Household Size", "number", True),

    # =========================================================================
    # PART 5: SPONSOR'S EMPLOYMENT AND INCOME
    # =========================================================================
    ("5A. Employment", "p5_1_employed", "1. I am currently employed as a/an:", "text", False),
    ("5A. Employment", "p5_2_employer_name", "2. Name of Employer #1", "text", False),
    ("5A. Employment", "p5_3a_emp_street", "3.a. Employer Address - Street", "text", False),
    ("5A. Employment", "p5_3b_emp_city", "3.b. City or Town", "text", False),
    ("5A. Employment", "p5_3c_emp_state", "3.c. State", "select", False),
    ("5A. Employment", "p5_3d_emp_zip", "3.d. ZIP Code", "text", False),
    ("5A. Employment", "p5_4_employer2_name", "4. Name of Employer #2 (if applicable)", "text", False),
    ("5A. Employment", "p5_5_self_employed", "5. I am self-employed", "text", False),
    ("5A. Employment", "p5_6_retired", "6. I retired on (date)", "date", False),
    ("5A. Employment", "p5_7_unemployed", "7. I have been unemployed since (date)", "date", False),

    ("5B. Income", "p5_8_current_income", "8. My current individual annual income is ($)", "text", True),
    ("5B. Tax Returns", "p5_9_tax_year1", "9. Most Recent Tax Year", "text", False),
    ("5B. Tax Returns", "p5_10_tax_income1", "10. Total Income ($)", "text", False),
    ("5B. Tax Returns", "p5_11_tax_year2", "11. Second Most Recent Tax Year", "text", False),
    ("5B. Tax Returns", "p5_12_tax_income2", "12. Total Income ($)", "text", False),
    ("5B. Tax Returns", "p5_13_tax_year3", "13. Third Most Recent Tax Year", "text", False),
    ("5B. Tax Returns", "p5_14_tax_income3", "14. Total Income ($)", "text", False),

    # =========================================================================
    # PART 6: SPONSOR'S STATEMENT AND CONTACT
    # =========================================================================
    ("6. Statement", "p6_1a_english", "1.a. I can read and understand English", "checkbox", False),
    ("6. Statement", "p6_1b_interpreter", "1.b. Interpreter read form to me in (language)", "checkbox", False),
    ("6. Statement", "p6_1b_language", "1.b. Language", "text", False),
    ("6. Statement", "p6_2_preparer", "2. Preparer prepared this at my request", "checkbox", False),
    ("6. Contact", "p6_3_phone", "3. Daytime Telephone Number", "phone", False),
    ("6. Contact", "p6_4_mobile", "4. Mobile Telephone Number", "phone", False),
    ("6. Contact", "p6_5_email", "5. Email Address (if any)", "email", False),
    ("6. Signature", "p6_signature_date", "Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 7: INTERPRETER
    # =========================================================================
    ("7. Interpreter", "p7_1a_interp_family", "1.a. Interpreter's Family Name", "text", False),
    ("7. Interpreter", "p7_1b_interp_given", "1.b. Interpreter's Given Name", "text", False),
    ("7. Interpreter", "p7_2_interp_org", "2. Business or Organization Name", "text", False),
    ("7. Interpreter", "p7_3_interp_phone", "3. Telephone Number", "phone", False),
    ("7. Interpreter", "p7_4_interp_email", "4. Email Address", "email", False),
    ("7. Interpreter", "p7_5_language", "5. Language", "text", False),

    # =========================================================================
    # PART 8: PREPARER
    # =========================================================================
    ("8. Preparer", "p8_1a_prep_family", "1.a. Preparer's Family Name", "text", False),
    ("8. Preparer", "p8_1b_prep_given", "1.b. Preparer's Given Name", "text", False),
    ("8. Preparer", "p8_2_prep_org", "2. Business or Organization Name", "text", False),
    ("8. Preparer", "p8_3_prep_phone", "3. Telephone Number", "phone", False),
    ("8. Preparer", "p8_4_prep_email", "4. Email Address", "email", False),
]

# Total: 80+ fields

if __name__ == "__main__":
    print(f"I-864EZ fields defined: {len(I864EZ_FIELDS)}")
