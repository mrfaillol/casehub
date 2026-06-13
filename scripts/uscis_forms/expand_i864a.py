#!/usr/bin/env python3
"""
Expand I-864A (Contract Between Sponsor and Household Member)
Used with I-864 for joint sponsorship. 4 pages, Parts 1-8.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I864A_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT THE SPONSOR (Principal I-864 filer)
    # =========================================================================
    ("1A. Sponsor Name", "p1_1a_family_name", "1.a. Sponsor's Family Name (Last Name)", "text", True),
    ("1A. Sponsor Name", "p1_1b_given_name", "1.b. Sponsor's Given Name (First Name)", "text", True),
    ("1A. Sponsor Name", "p1_1c_middle_name", "1.c. Sponsor's Middle Name", "text", False),
    ("1A. Sponsor Address", "p1_2a_street", "2.a. Sponsor's Street Number and Name", "text", True),
    ("1A. Sponsor Address", "p1_2b_apt_type", "2.b. Apt/Ste/Flr Type", "select", False),
    ("1A. Sponsor Address", "p1_2c_apt_number", "2.c. Apt/Ste/Flr Number", "text", False),
    ("1A. Sponsor Address", "p1_2d_city", "2.d. City or Town", "text", True),
    ("1A. Sponsor Address", "p1_2e_state", "2.e. State", "select", True),
    ("1A. Sponsor Address", "p1_2f_zip", "2.f. ZIP Code", "text", True),

    # =========================================================================
    # PART 2: INFORMATION ABOUT THE HOUSEHOLD MEMBER
    # =========================================================================
    ("2A. Household Member Name", "p2_1a_family_name", "1.a. Household Member - Family Name (Last Name)", "text", True),
    ("2A. Household Member Name", "p2_1b_given_name", "1.b. Household Member - Given Name (First Name)", "text", True),
    ("2A. Household Member Name", "p2_1c_middle_name", "1.c. Household Member - Middle Name", "text", False),
    ("2A. Household Member IDs", "p2_2_a_number", "2. Alien Registration Number (A-Number)", "text", False),
    ("2A. Household Member IDs", "p2_3_uscis_account", "3. USCIS Online Account Number", "text", False),
    ("2A. Household Member IDs", "p2_4_ssn", "4. U.S. Social Security Number", "text", True),
    ("2A. Household Member Details", "p2_5_dob", "5. Date of Birth (mm/dd/yyyy)", "date", True),
    ("2A. Household Member Details", "p2_6_relationship", "6. Relationship to Sponsor", "text", True),

    # Household Member Address
    ("2B. Household Member Address", "p2_7a_street", "7.a. Street Number and Name", "text", True),
    ("2B. Household Member Address", "p2_7b_apt_type", "7.b. Apt/Ste/Flr Type", "select", False),
    ("2B. Household Member Address", "p2_7c_apt_number", "7.c. Apt/Ste/Flr Number", "text", False),
    ("2B. Household Member Address", "p2_7d_city", "7.d. City or Town", "text", True),
    ("2B. Household Member Address", "p2_7e_state", "7.e. State", "select", True),
    ("2B. Household Member Address", "p2_7f_zip", "7.f. ZIP Code", "text", True),

    # =========================================================================
    # PART 3: HOUSEHOLD MEMBER'S STATUS
    # =========================================================================
    ("3. Member Status", "p3_1_us_citizen", "1. I am a U.S. citizen", "checkbox", False),
    ("3. Member Status", "p3_2_us_national", "2. I am a U.S. national", "checkbox", False),
    ("3. Member Status", "p3_3_lpr", "3. I am a lawful permanent resident", "checkbox", False),
    ("3. Member Status", "p3_4_intending_immigrant", "4. I am an intending immigrant sponsored on the I-864", "checkbox", False),
    ("3. Member Status", "p3_5_other", "5. Other (explain)", "text", False),

    # =========================================================================
    # PART 4: HOUSEHOLD MEMBER'S EMPLOYMENT AND INCOME
    # =========================================================================
    ("4A. Employment", "p4_1_employed", "1. I am currently employed as a/an:", "text", False),
    ("4A. Employment", "p4_2_employer_name", "2. Name of Employer #1 (if applicable)", "text", False),
    ("4A. Employment", "p4_3a_emp_street", "3.a. Employer Street Number and Name", "text", False),
    ("4A. Employment", "p4_3b_emp_city", "3.b. City or Town", "text", False),
    ("4A. Employment", "p4_3c_emp_state", "3.c. State", "select", False),
    ("4A. Employment", "p4_3d_emp_zip", "3.d. ZIP Code", "text", False),
    ("4A. Employment", "p4_4_employer2_name", "4. Name of Employer #2 (if applicable)", "text", False),
    ("4A. Employment", "p4_5_self_employed", "5. I am self-employed as a/an:", "text", False),
    ("4A. Employment", "p4_6_retired", "6. I am retired. Date of Retirement:", "date", False),
    ("4A. Employment", "p4_7_unemployed", "7. I am currently unemployed. Date unemployed since:", "date", False),

    ("4B. Income", "p4_8_current_annual_income", "8. My current individual annual income is ($)", "text", True),
    ("4B. Federal Tax Returns", "p4_9_tax_year1", "9. Most Recent Tax Year", "text", False),
    ("4B. Federal Tax Returns", "p4_10_tax_year1_income", "10. Total Income on Tax Return ($)", "text", False),
    ("4B. Federal Tax Returns", "p4_11_tax_year2", "11. Second Most Recent Tax Year", "text", False),
    ("4B. Federal Tax Returns", "p4_12_tax_year2_income", "12. Total Income ($)", "text", False),
    ("4B. Federal Tax Returns", "p4_13_tax_year3", "13. Third Most Recent Tax Year", "text", False),
    ("4B. Federal Tax Returns", "p4_14_tax_year3_income", "14. Total Income ($)", "text", False),

    # =========================================================================
    # PART 5: HOUSEHOLD MEMBER'S ASSETS
    # =========================================================================
    ("5. Assets", "p5_1_savings", "1. Balance of Savings and Checking Accounts ($)", "text", False),
    ("5. Assets", "p5_2_real_estate", "2. Net Value of Real Estate ($)", "text", False),
    ("5. Assets", "p5_3_stocks_bonds", "3. Net Value of Stocks, Bonds, CDs ($)", "text", False),
    ("5. Assets", "p5_4_other", "4. Other Assets (describe)", "text", False),
    ("5. Assets", "p5_5_total_assets", "5. Total Value of Assets ($)", "text", False),

    # =========================================================================
    # PART 6: HOUSEHOLD MEMBER'S STATEMENT, CONTACT, AND SIGNATURE
    # =========================================================================
    ("6. Statement", "p6_1a_english", "1.a. I can read and understand English", "checkbox", False),
    ("6. Statement", "p6_1b_interpreter", "1.b. Interpreter read this form to me in (language)", "checkbox", False),
    ("6. Statement", "p6_1b_language", "1.b. Language", "text", False),
    ("6. Statement", "p6_2_preparer", "2. Preparer prepared this form at my request", "checkbox", False),
    ("6. Contact", "p6_3_phone", "3. Household Member's Daytime Telephone Number", "phone", False),
    ("6. Contact", "p6_4_mobile", "4. Mobile Telephone Number", "phone", False),
    ("6. Contact", "p6_5_email", "5. Email Address (if any)", "email", False),
    ("6. Signature", "p6_signature_date", "Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 7: INTERPRETER
    # =========================================================================
    ("7. Interpreter", "p7_1a_interp_family", "1.a. Interpreter's Family Name", "text", False),
    ("7. Interpreter", "p7_1b_interp_given", "1.b. Interpreter's Given Name", "text", False),
    ("7. Interpreter", "p7_2_interp_org", "2. Business or Organization Name", "text", False),
    ("7. Interpreter", "p7_3_interp_phone", "3. Daytime Telephone Number", "phone", False),
    ("7. Interpreter", "p7_4_interp_email", "4. Email Address", "email", False),
    ("7. Interpreter", "p7_5_language", "5. Language", "text", False),

    # =========================================================================
    # PART 8: PREPARER
    # =========================================================================
    ("8. Preparer", "p8_1a_prep_family", "1.a. Preparer's Family Name", "text", False),
    ("8. Preparer", "p8_1b_prep_given", "1.b. Preparer's Given Name", "text", False),
    ("8. Preparer", "p8_2_prep_org", "2. Business or Organization Name", "text", False),
    ("8. Preparer", "p8_3_prep_phone", "3. Daytime Telephone Number", "phone", False),
    ("8. Preparer", "p8_4_prep_email", "4. Email Address", "email", False),
]

# Total: 75+ fields

if __name__ == "__main__":
    print(f"I-864A fields defined: {len(I864A_FIELDS)}")
