#!/usr/bin/env python3
"""
Expand I-134A (Online Request to be a Supporter and Declaration of Financial Support)
Used for Uniting for Ukraine, CHNV humanitarian parole processes.
8 pages equivalent (online form with PDF printout).
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I134A_FIELDS = [
    # =========================================================================
    # PART 1: SUPPORTER INFORMATION
    # =========================================================================
    ("1A. Supporter Name", "p1_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("1A. Supporter Name", "p1_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("1A. Supporter Name", "p1_1c_middle_name", "1.c. Middle Name", "text", False),
    ("1A. Supporter IDs", "p1_2_a_number", "2. Alien Registration Number (A-Number)", "text", False),
    ("1A. Supporter IDs", "p1_3_uscis_account", "3. USCIS Online Account Number", "text", False),
    ("1A. Supporter IDs", "p1_4_ssn", "4. U.S. Social Security Number", "text", True),
    ("1A. Supporter Personal", "p1_5_dob", "5. Date of Birth (mm/dd/yyyy)", "date", True),
    ("1A. Supporter Personal", "p1_6_country_birth", "6. Country of Birth", "text", True),
    ("1A. Supporter Personal", "p1_7_citizenship", "7. Country of Citizenship or Nationality", "text", True),
    ("1A. Supporter Personal", "p1_8_sex", "8. Sex", "select", True),

    # Supporter Address
    ("1B. Supporter Address", "p1_9a_street", "9.a. Street Number and Name", "text", True),
    ("1B. Supporter Address", "p1_9b_apt_type", "9.b. Apt/Ste/Flr Type", "select", False),
    ("1B. Supporter Address", "p1_9c_apt_number", "9.c. Apt/Ste/Flr Number", "text", False),
    ("1B. Supporter Address", "p1_9d_city", "9.d. City or Town", "text", True),
    ("1B. Supporter Address", "p1_9e_state", "9.e. State", "select", True),
    ("1B. Supporter Address", "p1_9f_zip", "9.f. ZIP Code", "text", True),

    # Supporter Contact
    ("1C. Contact", "p1_10_phone", "10. Daytime Telephone Number", "phone", True),
    ("1C. Contact", "p1_11_mobile", "11. Mobile Telephone Number", "phone", False),
    ("1C. Contact", "p1_12_email", "12. Email Address", "email", True),

    # Immigration Status
    ("1D. Status", "p1_13_us_citizen", "13. I am a U.S. citizen", "checkbox", False),
    ("1D. Status", "p1_14_us_national", "14. I am a U.S. national", "checkbox", False),
    ("1D. Status", "p1_15_lpr", "15. I am a lawful permanent resident", "checkbox", False),
    ("1D. Status", "p1_16_nonimmigrant", "16. I am in valid nonimmigrant status", "checkbox", False),
    ("1D. Status", "p1_17_parolee", "17. I am a parolee or TPS holder", "checkbox", False),
    ("1D. Status", "p1_18_daca", "18. I have a pending asylum application or DACA", "checkbox", False),

    # =========================================================================
    # PART 2: BENEFICIARY INFORMATION
    # =========================================================================
    ("2A. Beneficiary Name", "p2_1a_family_name", "1.a. Beneficiary - Family Name (Last Name)", "text", True),
    ("2A. Beneficiary Name", "p2_1b_given_name", "1.b. Beneficiary - Given Name (First Name)", "text", True),
    ("2A. Beneficiary Name", "p2_1c_middle_name", "1.c. Beneficiary - Middle Name", "text", False),
    ("2A. Beneficiary Details", "p2_2_dob", "2. Beneficiary - Date of Birth (mm/dd/yyyy)", "date", True),
    ("2A. Beneficiary Details", "p2_3_country_birth", "3. Beneficiary - Country of Birth", "text", True),
    ("2A. Beneficiary Details", "p2_4_citizenship", "4. Beneficiary - Country of Citizenship", "text", True),
    ("2A. Beneficiary Details", "p2_5_sex", "5. Beneficiary - Sex", "select", True),
    ("2A. Beneficiary Details", "p2_6_passport", "6. Beneficiary - Passport Number", "text", False),
    ("2A. Beneficiary Details", "p2_7_passport_country", "7. Beneficiary - Country That Issued Passport", "text", False),
    ("2A. Beneficiary Details", "p2_8_passport_exp", "8. Beneficiary - Passport Expiration Date", "date", False),
    ("2A. Beneficiary Details", "p2_9_relationship", "9. Relationship to Supporter", "text", True),

    # Beneficiary Address Abroad
    ("2B. Beneficiary Address", "p2_10a_street", "10.a. Current Address Abroad - Street", "text", False),
    ("2B. Beneficiary Address", "p2_10b_city", "10.b. City or Town", "text", False),
    ("2B. Beneficiary Address", "p2_10c_province", "10.c. Province/State", "text", False),
    ("2B. Beneficiary Address", "p2_10d_postal", "10.d. Postal Code", "text", False),
    ("2B. Beneficiary Address", "p2_10e_country", "10.e. Country", "text", False),

    # Additional Beneficiaries (family members)
    ("2C. Additional Beneficiary 1", "p2_11a_add1_family", "11.a. Additional Beneficiary 1 - Family Name", "text", False),
    ("2C. Additional Beneficiary 1", "p2_11b_add1_given", "11.b. Additional Beneficiary 1 - Given Name", "text", False),
    ("2C. Additional Beneficiary 1", "p2_12_add1_dob", "12. Additional Beneficiary 1 - Date of Birth", "date", False),
    ("2C. Additional Beneficiary 1", "p2_13_add1_relationship", "13. Additional Beneficiary 1 - Relationship", "text", False),
    ("2C. Additional Beneficiary 1", "p2_14_add1_country_birth", "14. Additional Beneficiary 1 - Country of Birth", "text", False),

    ("2D. Additional Beneficiary 2", "p2_15a_add2_family", "15.a. Additional Beneficiary 2 - Family Name", "text", False),
    ("2D. Additional Beneficiary 2", "p2_15b_add2_given", "15.b. Additional Beneficiary 2 - Given Name", "text", False),
    ("2D. Additional Beneficiary 2", "p2_16_add2_dob", "16. Additional Beneficiary 2 - Date of Birth", "date", False),
    ("2D. Additional Beneficiary 2", "p2_17_add2_relationship", "17. Additional Beneficiary 2 - Relationship", "text", False),

    # =========================================================================
    # PART 3: FINANCIAL SUPPORT DECLARATION
    # =========================================================================
    ("3A. Employment", "p3_1_employer_name", "1. Current Employer Name", "text", False),
    ("3A. Employment", "p3_2_occupation", "2. Occupation/Position", "text", False),
    ("3A. Employment", "p3_3_annual_income", "3. Current Annual Household Income ($)", "text", True),
    ("3A. Employment", "p3_4_self_employed", "4. Are you self-employed?", "radio", False),

    ("3B. Household Income", "p3_5_household_size", "5. Total Household Size", "number", True),
    ("3B. Household Income", "p3_6_total_household_income", "6. Total Annual Household Income ($)", "text", True),
    ("3B. Household Income", "p3_7_tax_year", "7. Most Recent Federal Income Tax Return Year", "text", False),
    ("3B. Household Income", "p3_8_tax_total_income", "8. Total Income on Federal Tax Return ($)", "text", False),

    ("3C. Assets", "p3_9_savings", "9. Checking/Savings Account Balance ($)", "text", False),
    ("3C. Assets", "p3_10_real_estate", "10. Value of Real Estate ($)", "text", False),
    ("3C. Assets", "p3_11_stocks_bonds", "11. Value of Stocks, Bonds, CDs ($)", "text", False),
    ("3C. Assets", "p3_12_other_assets", "12. Other Assets (describe and amount)", "text", False),
    ("3C. Assets", "p3_13_total_assets", "13. Total Value of Assets ($)", "text", False),

    # =========================================================================
    # PART 4: HOUSING PLAN
    # =========================================================================
    ("4. Housing", "p4_1_will_reside_with", "1. Beneficiary will reside with me", "checkbox", False),
    ("4. Housing", "p4_2_other_housing", "2. Other housing arrangement (explain)", "text", False),
    ("4. Housing", "p4_3a_housing_street", "3.a. Address Where Beneficiary Will Live - Street", "text", True),
    ("4. Housing", "p4_3b_housing_city", "3.b. City or Town", "text", True),
    ("4. Housing", "p4_3c_housing_state", "3.c. State", "select", True),
    ("4. Housing", "p4_3d_housing_zip", "3.d. ZIP Code", "text", True),
    ("4. Housing", "p4_4_num_bedrooms", "4. Number of Bedrooms", "number", False),
    ("4. Housing", "p4_5_num_occupants", "5. Number of Current Occupants", "number", False),

    # =========================================================================
    # PART 5: SUPPORTER'S STATEMENT AND CERTIFICATION
    # =========================================================================
    ("5. Certification", "p5_1_agree_support", "1. I agree to provide financial support", "checkbox", True),
    ("5. Certification", "p5_2_agree_notify", "2. I agree to notify USCIS of any changes", "checkbox", True),
    ("5. Certification", "p5_3_agree_housing", "3. I agree to provide initial housing", "checkbox", True),
    ("5. Certification", "p5_4_agree_healthcare", "4. I agree to help beneficiary access healthcare", "checkbox", False),
    ("5. Certification", "p5_5_understand_obligations", "5. I understand my obligations as a supporter", "checkbox", True),
    ("5. Certification", "p5_signature_date", "Date of Signature (mm/dd/yyyy)", "date", True),
]

# Total: 85+ fields

if __name__ == "__main__":
    print(f"I-134A fields defined: {len(I134A_FIELDS)}")
