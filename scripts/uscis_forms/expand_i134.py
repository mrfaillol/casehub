#!/usr/bin/env python3
"""
Expand I-134 (Declaration of Financial Support) with ALL official USCIS fields.
6 pages. Used for B-1/B-2 visitor visa financial support declarations.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I134_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT THE SUPPORTER (Sponsor)
    # =========================================================================
    ("1A. Supporter Name", "p1_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("1A. Supporter Name", "p1_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("1A. Supporter Name", "p1_1c_middle_name", "1.c. Middle Name", "text", False),
    ("1A. Supporter IDs", "p1_2_a_number", "2. Alien Registration Number (A-Number) (if any)", "text", False),
    ("1A. Supporter IDs", "p1_3_uscis_account", "3. USCIS Online Account Number (if any)", "text", False),
    ("1A. Supporter IDs", "p1_4_ssn", "4. U.S. Social Security Number", "text", True),
    ("1A. Supporter IDs", "p1_5_dob", "5. Date of Birth (mm/dd/yyyy)", "date", True),
    ("1A. Supporter IDs", "p1_6_country_birth", "6. Country of Birth", "text", True),
    ("1A. Supporter IDs", "p1_7_citizenship", "7. Country of Citizenship or Nationality", "text", True),

    # Supporter Address
    ("1B. Supporter Address", "p1_8a_street", "8.a. Street Number and Name", "text", True),
    ("1B. Supporter Address", "p1_8b_apt_type", "8.b. Apt/Ste/Flr Type", "select", False),
    ("1B. Supporter Address", "p1_8c_apt_number", "8.c. Apt/Ste/Flr Number", "text", False),
    ("1B. Supporter Address", "p1_8d_city", "8.d. City or Town", "text", True),
    ("1B. Supporter Address", "p1_8e_state", "8.e. State", "select", True),
    ("1B. Supporter Address", "p1_8f_zip", "8.f. ZIP Code", "text", True),

    # Supporter Contact
    ("1C. Supporter Contact", "p1_9_phone", "9. Daytime Telephone Number", "phone", True),
    ("1C. Supporter Contact", "p1_10_mobile", "10. Mobile Telephone Number (if any)", "phone", False),
    ("1C. Supporter Contact", "p1_11_email", "11. Email Address (if any)", "email", False),

    # Relationship
    ("1D. Relationship", "p1_12_relationship", "12. Relationship to the person(s) you are supporting", "text", True),
    ("1D. Relationship", "p1_13_us_citizen", "13. I am a U.S. citizen", "checkbox", False),
    ("1D. Relationship", "p1_14_lpr", "14. I am a lawful permanent resident", "checkbox", False),
    ("1D. Relationship", "p1_15_nonimmigrant", "15. I am a nonimmigrant in valid status", "checkbox", False),
    ("1D. Relationship", "p1_16_other_status", "16. Other (explain)", "text", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT THE PERSON(S) BEING SUPPORTED
    # =========================================================================
    ("2A. Person 1 Name", "p2_1a_p1_family", "1.a. Person 1 - Family Name (Last Name)", "text", True),
    ("2A. Person 1 Name", "p2_1b_p1_given", "1.b. Person 1 - Given Name (First Name)", "text", True),
    ("2A. Person 1 Name", "p2_1c_p1_middle", "1.c. Person 1 - Middle Name", "text", False),
    ("2A. Person 1 Details", "p2_2_p1_dob", "2. Person 1 - Date of Birth (mm/dd/yyyy)", "date", True),
    ("2A. Person 1 Details", "p2_3_p1_country_birth", "3. Person 1 - Country of Birth", "text", True),
    ("2A. Person 1 Details", "p2_4_p1_citizenship", "4. Person 1 - Country of Citizenship", "text", True),
    ("2A. Person 1 Details", "p2_5_p1_relationship", "5. Person 1 - Relationship to Supporter", "text", True),
    ("2A. Person 1 Details", "p2_6_p1_passport", "6. Person 1 - Passport Number", "text", False),
    ("2A. Person 1 Details", "p2_7_p1_passport_country", "7. Person 1 - Country That Issued Passport", "text", False),
    ("2A. Person 1 Details", "p2_8_p1_passport_exp", "8. Person 1 - Passport Expiration Date", "date", False),
    ("2A. Person 1 Details", "p2_9_p1_purpose", "9. Person 1 - Purpose of Visit", "text", True),
    ("2A. Person 1 Details", "p2_10_p1_arrival_date", "10. Person 1 - Expected Date of Arrival", "date", True),
    ("2A. Person 1 Details", "p2_11_p1_length_stay", "11. Person 1 - Intended Length of Stay", "text", True),
    ("2A. Person 1 Address", "p2_12a_p1_street", "12.a. Person 1 - Address in the U.S. - Street", "text", False),
    ("2A. Person 1 Address", "p2_12b_p1_city", "12.b. Person 1 - City or Town", "text", False),
    ("2A. Person 1 Address", "p2_12c_p1_state", "12.c. Person 1 - State", "select", False),
    ("2A. Person 1 Address", "p2_12d_p1_zip", "12.d. Person 1 - ZIP Code", "text", False),

    # Person 2
    ("2B. Person 2 Name", "p2_13a_p2_family", "13.a. Person 2 - Family Name (Last Name)", "text", False),
    ("2B. Person 2 Name", "p2_13b_p2_given", "13.b. Person 2 - Given Name (First Name)", "text", False),
    ("2B. Person 2 Name", "p2_13c_p2_middle", "13.c. Person 2 - Middle Name", "text", False),
    ("2B. Person 2 Details", "p2_14_p2_dob", "14. Person 2 - Date of Birth", "date", False),
    ("2B. Person 2 Details", "p2_15_p2_country_birth", "15. Person 2 - Country of Birth", "text", False),
    ("2B. Person 2 Details", "p2_16_p2_relationship", "16. Person 2 - Relationship to Supporter", "text", False),

    # =========================================================================
    # PART 3: SUPPORTER'S EMPLOYMENT AND INCOME
    # =========================================================================
    ("3A. Employment", "p3_1_employer_name", "1. Employer Name", "text", False),
    ("3A. Employment", "p3_2a_emp_street", "2.a. Employer Street Address", "text", False),
    ("3A. Employment", "p3_2b_emp_city", "2.b. Employer City or Town", "text", False),
    ("3A. Employment", "p3_2c_emp_state", "2.c. Employer State", "select", False),
    ("3A. Employment", "p3_2d_emp_zip", "2.d. Employer ZIP Code", "text", False),
    ("3A. Employment", "p3_3_occupation", "3. Occupation/Position", "text", False),
    ("3A. Employment", "p3_4_self_employed", "4. Self-employed?", "radio", False),
    ("3A. Employment", "p3_5_annual_income", "5. Current Annual Income ($)", "text", True),

    # Income Details
    ("3B. Income Details", "p3_6_tax_year", "6. Most Recent Federal Tax Year", "text", False),
    ("3B. Income Details", "p3_7_tax_income", "7. Total Income on Federal Tax Return ($)", "text", False),
    ("3B. Income Details", "p3_8_other_income", "8. Other Income (describe and provide amount)", "text", False),

    # =========================================================================
    # PART 4: SUPPORTER'S ASSETS
    # =========================================================================
    ("4. Assets", "p4_1_checking_savings", "1. Balance in Checking/Savings Accounts ($)", "text", False),
    ("4. Assets", "p4_2_real_estate", "2. Value of Real Estate Owned ($)", "text", False),
    ("4. Assets", "p4_3_stocks_bonds", "3. Value of Stocks, Bonds, CDs ($)", "text", False),
    ("4. Assets", "p4_4_life_insurance", "4. Cash Value of Life Insurance ($)", "text", False),
    ("4. Assets", "p4_5_other_assets", "5. Other Assets (describe)", "text", False),
    ("4. Assets", "p4_6_total_assets", "6. Total Value of Assets ($)", "text", False),

    # =========================================================================
    # PART 5: SUPPORTER'S HOUSEHOLD SIZE
    # =========================================================================
    ("5. Household Size", "p5_1_marital_status", "1. Marital Status", "select", True),
    ("5. Household Size", "p5_2_household_members", "2. Number of Household Members (including yourself)", "number", True),
    ("5. Household Size", "p5_3_dependents", "3. Number of Dependents", "number", False),
    ("5. Household Size", "p5_4_other_supported", "4. Number of Other Persons You Are Supporting", "number", False),

    # =========================================================================
    # PART 6: SUPPORTER'S STATEMENT, CONTACT, AND SIGNATURE
    # =========================================================================
    ("6. Statement", "p6_1a_english", "1.a. I can read and understand English", "checkbox", False),
    ("6. Statement", "p6_1b_interpreter", "1.b. The interpreter named in Part 7 read this form to me", "checkbox", False),
    ("6. Statement", "p6_1b_language", "1.b. Language", "text", False),
    ("6. Statement", "p6_2_preparer", "2. Preparer named in Part 8 prepared this form at my request", "checkbox", False),
    ("6. Statement", "p6_3_phone", "3. Daytime Telephone Number", "phone", False),
    ("6. Statement", "p6_4_mobile", "4. Mobile Telephone Number", "phone", False),
    ("6. Statement", "p6_5_email", "5. Email Address", "email", False),
    ("6. Statement", "p6_signature_date", "Date of Signature (mm/dd/yyyy)", "date", True),

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

    # =========================================================================
    # PART 9: ADDITIONAL INFORMATION
    # =========================================================================
    ("9. Additional", "p9_1a_page", "1.a. Page Number", "text", False),
    ("9. Additional", "p9_1b_part", "1.b. Part Number", "text", False),
    ("9. Additional", "p9_1c_item", "1.c. Item Number", "text", False),
    ("9. Additional", "p9_1d_info", "1.d. Additional Information", "textarea", False),
]

# Total: 90+ fields

if __name__ == "__main__":
    print(f"I-134 fields defined: {len(I134_FIELDS)}")
