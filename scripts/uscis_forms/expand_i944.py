#!/usr/bin/env python3
"""
Expand I-944 (Declaration of Self-Sufficiency)
NOTE: Form I-944 was RESCINDED effective March 9, 2021 when the public charge
final rule was vacated. USCIS no longer accepts this form.
This file is kept for historical reference and in case the form is reinstated.

If reinstated, the form would cover: income, assets, health insurance, education,
skills, financial liabilities, and public benefits usage.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

# NOTE: Form rescinded as of 03/09/2021. Fields preserved for reference.
I944_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT YOU (Applicant)
    # =========================================================================
    ("1A. Your Name", "p1_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("1A. Your Name", "p1_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("1A. Your Name", "p1_1c_middle_name", "1.c. Middle Name", "text", False),
    ("1A. IDs", "p1_2_a_number", "2. Alien Registration Number (A-Number)", "text", False),
    ("1A. IDs", "p1_3_uscis_account", "3. USCIS Online Account Number", "text", False),
    ("1A. IDs", "p1_4_ssn", "4. U.S. Social Security Number", "text", False),
    ("1A. Personal", "p1_5_dob", "5. Date of Birth (mm/dd/yyyy)", "date", True),
    ("1A. Personal", "p1_6_country_birth", "6. Country of Birth", "text", True),
    ("1A. Personal", "p1_7_citizenship", "7. Country of Citizenship", "text", True),

    # Address
    ("1B. Address", "p1_8a_street", "8.a. Street Number and Name", "text", True),
    ("1B. Address", "p1_8b_apt_type", "8.b. Apt/Ste/Flr Type", "select", False),
    ("1B. Address", "p1_8c_apt_number", "8.c. Apt/Ste/Flr Number", "text", False),
    ("1B. Address", "p1_8d_city", "8.d. City or Town", "text", True),
    ("1B. Address", "p1_8e_state", "8.e. State", "select", True),
    ("1B. Address", "p1_8f_zip", "8.f. ZIP Code", "text", True),

    # =========================================================================
    # PART 2: HOUSEHOLD INFORMATION
    # =========================================================================
    ("2. Household", "p2_1_marital_status", "1. Marital Status", "select", True),
    ("2. Household", "p2_2_household_size", "2. Total Household Size", "number", True),
    ("2. Household", "p2_3_num_dependents", "3. Number of Dependents", "number", False),

    # =========================================================================
    # PART 3: ASSETS, RESOURCES, AND FINANCIAL STATUS
    # =========================================================================
    ("3A. Income", "p3_1_annual_gross_income", "1. Annual Gross Household Income ($)", "text", True),
    ("3A. Income", "p3_2_income_source_employment", "2. Income Source: Employment", "checkbox", False),
    ("3A. Income", "p3_3_income_source_self_employment", "3. Income Source: Self-Employment", "checkbox", False),
    ("3A. Income", "p3_4_income_source_other", "4. Income Source: Other (explain)", "text", False),
    ("3A. Income", "p3_5_tax_year1", "5. Most Recent Tax Year", "text", False),
    ("3A. Income", "p3_6_tax_income1", "6. Total Income on Tax Return ($)", "text", False),
    ("3A. Income", "p3_7_tax_year2", "7. Second Most Recent Tax Year", "text", False),
    ("3A. Income", "p3_8_tax_income2", "8. Total Income ($)", "text", False),
    ("3A. Income", "p3_9_tax_year3", "9. Third Most Recent Tax Year", "text", False),
    ("3A. Income", "p3_10_tax_income3", "10. Total Income ($)", "text", False),

    ("3B. Assets", "p3_11_checking_savings", "11. Checking and Savings Account Balance ($)", "text", False),
    ("3B. Assets", "p3_12_real_estate", "12. Value of Real Estate ($)", "text", False),
    ("3B. Assets", "p3_13_stocks_bonds", "13. Value of Stocks, Bonds, Investments ($)", "text", False),
    ("3B. Assets", "p3_14_retirement", "14. Value of Retirement Accounts ($)", "text", False),
    ("3B. Assets", "p3_15_other_assets", "15. Other Assets (describe)", "text", False),
    ("3B. Assets", "p3_16_total_assets", "16. Total Assets ($)", "text", False),

    ("3C. Liabilities", "p3_17_credit_card_debt", "17. Credit Card Debt ($)", "text", False),
    ("3C. Liabilities", "p3_18_mortgage", "18. Mortgage Balance ($)", "text", False),
    ("3C. Liabilities", "p3_19_car_loans", "19. Auto Loan Balance ($)", "text", False),
    ("3C. Liabilities", "p3_20_student_loans", "20. Student Loan Balance ($)", "text", False),
    ("3C. Liabilities", "p3_21_other_liabilities", "21. Other Liabilities ($)", "text", False),
    ("3C. Liabilities", "p3_22_total_liabilities", "22. Total Liabilities ($)", "text", False),
    ("3C. Liabilities", "p3_23_net_worth", "23. Net Worth (Assets minus Liabilities) ($)", "text", False),

    # =========================================================================
    # PART 4: HEALTH INSURANCE
    # =========================================================================
    ("4. Health Insurance", "p4_1_has_insurance", "1. Do you currently have health insurance?", "radio", True),
    ("4. Health Insurance", "p4_2_provider_name", "2. Health Insurance Provider Name", "text", False),
    ("4. Health Insurance", "p4_3_policy_number", "3. Policy Number", "text", False),
    ("4. Health Insurance", "p4_4_coverage_type", "4. Type of Coverage (Individual/Family/Employer)", "select", False),
    ("4. Health Insurance", "p4_5_insurance_start", "5. Coverage Start Date", "date", False),

    # =========================================================================
    # PART 5: EDUCATION AND SKILLS
    # =========================================================================
    ("5. Education", "p5_1_highest_education", "1. Highest Level of Education", "select", False),
    ("5. Education", "p5_2_certifications", "2. Professional Certifications or Licenses", "text", False),
    ("5. Education", "p5_3_english_proficiency", "3. English Language Proficiency Level", "select", False),
    ("5. Education", "p5_4_other_languages", "4. Other Languages Spoken", "text", False),

    # =========================================================================
    # PART 6: CONTACT AND SIGNATURE
    # =========================================================================
    ("6. Contact", "p6_1_phone", "1. Daytime Telephone Number", "phone", False),
    ("6. Contact", "p6_2_mobile", "2. Mobile Telephone Number", "phone", False),
    ("6. Contact", "p6_3_email", "3. Email Address", "email", False),
    ("6. Signature", "p6_signature_date", "Date of Signature (mm/dd/yyyy)", "date", True),
]

# Total: 60+ fields (form is rescinded, kept for reference)

if __name__ == "__main__":
    print(f"I-944 fields defined: {len(I944_FIELDS)}")
    print("NOTE: Form I-944 was RESCINDED effective March 9, 2021.")
