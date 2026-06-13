#!/usr/bin/env python3
"""
Expand I-129S (Nonimmigrant Petition Based on Blanket L Petition)
Supplement for individual L-1 beneficiaries under an approved blanket L petition.
7 pages, 6 sections.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I129S_FIELDS = [
    # =========================================================================
    # SECTION 1: INFORMATION ABOUT THE EMPLOYER (Petitioner)
    # =========================================================================
    ("1A. Employer Info", "s1_1_company_name", "1. Company or Organization Name", "text", True),
    ("1A. Employer Info", "s1_2_ein", "2. IRS Employer Identification Number (EIN)", "text", True),
    ("1A. Employer Info", "s1_3_blanket_receipt", "3. Blanket Petition Receipt Number", "text", True),
    ("1A. Employer Info", "s1_4_blanket_approval_date", "4. Blanket Petition Approval Date (mm/dd/yyyy)", "date", True),
    ("1A. Employer Info", "s1_5_blanket_expiration", "5. Blanket Petition Expiration Date (mm/dd/yyyy)", "date", False),
    ("1A. Employer Address", "s1_6a_street", "6.a. U.S. Address - Street Number and Name", "text", True),
    ("1A. Employer Address", "s1_6b_apt", "6.b. Apt/Ste/Flr Number", "text", False),
    ("1A. Employer Address", "s1_6c_city", "6.c. City or Town", "text", True),
    ("1A. Employer Address", "s1_6d_state", "6.d. State", "select", True),
    ("1A. Employer Address", "s1_6e_zip", "6.e. ZIP Code", "text", True),
    ("1A. Employer Contact", "s1_7_phone", "7. Telephone Number", "phone", True),
    ("1A. Employer Contact", "s1_8_fax", "8. Fax Number", "text", False),

    # =========================================================================
    # SECTION 2: INFORMATION ABOUT THE BENEFICIARY
    # =========================================================================
    ("2A. Beneficiary Name", "s2_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("2A. Beneficiary Name", "s2_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("2A. Beneficiary Name", "s2_1c_middle_name", "1.c. Middle Name", "text", False),
    ("2A. Beneficiary IDs", "s2_2_a_number", "2. Alien Registration Number (A-Number)", "text", False),
    ("2A. Beneficiary IDs", "s2_3_dob", "3. Date of Birth (mm/dd/yyyy)", "date", True),
    ("2A. Beneficiary IDs", "s2_4_country_birth", "4. Country of Birth", "text", True),
    ("2A. Beneficiary IDs", "s2_5_citizenship", "5. Country of Citizenship or Nationality", "text", True),
    ("2A. Beneficiary IDs", "s2_6_sex", "6. Sex", "select", True),
    ("2A. Beneficiary IDs", "s2_7_passport_number", "7. Passport Number", "text", True),
    ("2A. Beneficiary IDs", "s2_8_passport_country", "8. Country That Issued Passport", "text", True),
    ("2A. Beneficiary IDs", "s2_9_passport_exp", "9. Passport Expiration Date (mm/dd/yyyy)", "date", True),

    # Beneficiary Address Abroad
    ("2B. Address Abroad", "s2_10a_street", "10.a. Address Abroad - Street Number and Name", "text", False),
    ("2B. Address Abroad", "s2_10b_city", "10.b. City or Town", "text", False),
    ("2B. Address Abroad", "s2_10c_province", "10.c. Province/State", "text", False),
    ("2B. Address Abroad", "s2_10d_postal", "10.d. Postal Code", "text", False),
    ("2B. Address Abroad", "s2_10e_country", "10.e. Country", "text", False),

    # Beneficiary U.S. Address (if in U.S.)
    ("2C. U.S. Address", "s2_11a_us_street", "11.a. Current U.S. Address - Street", "text", False),
    ("2C. U.S. Address", "s2_11b_us_apt", "11.b. Apt/Ste/Flr Number", "text", False),
    ("2C. U.S. Address", "s2_11c_us_city", "11.c. City or Town", "text", False),
    ("2C. U.S. Address", "s2_11d_us_state", "11.d. State", "select", False),
    ("2C. U.S. Address", "s2_11e_us_zip", "11.e. ZIP Code", "text", False),

    # Current Immigration Status
    ("2D. Immigration", "s2_12_current_status", "12. Current Immigration Status", "text", False),
    ("2D. Immigration", "s2_13_i94_number", "13. I-94 Arrival-Departure Record Number", "text", False),
    ("2D. Immigration", "s2_14_last_entry_date", "14. Date of Last Entry (mm/dd/yyyy)", "date", False),
    ("2D. Immigration", "s2_15_port_of_entry", "15. Port of Entry", "text", False),
    ("2D. Immigration", "s2_16_status_expires", "16. Date Status Expires or D/S", "text", False),

    # =========================================================================
    # SECTION 3: QUALIFYING INFORMATION
    # =========================================================================
    ("3A. L-1 Classification", "s3_1_l1a_manager", "1. L-1A: Manager or Executive", "checkbox", False),
    ("3A. L-1 Classification", "s3_2_l1b_specialized", "2. L-1B: Specialized Knowledge Worker", "checkbox", False),
    ("3A. Qualifying Employment", "s3_3_foreign_employer", "3. Name of Foreign Employer", "text", True),
    ("3A. Qualifying Employment", "s3_4_foreign_position", "4. Position/Title with Foreign Employer", "text", True),
    ("3A. Qualifying Employment", "s3_5_foreign_dates_from", "5. Employment Dates From (mm/dd/yyyy)", "date", True),
    ("3A. Qualifying Employment", "s3_6_foreign_dates_to", "6. Employment Dates To (mm/dd/yyyy)", "date", False),
    ("3A. Qualifying Employment", "s3_7_foreign_duties", "7. Description of Duties with Foreign Employer", "textarea", True),

    ("3B. Foreign Address", "s3_8a_foreign_emp_street", "8.a. Foreign Employer Address - Street", "text", False),
    ("3B. Foreign Address", "s3_8b_foreign_emp_city", "8.b. City or Town", "text", False),
    ("3B. Foreign Address", "s3_8c_foreign_emp_province", "8.c. Province/State", "text", False),
    ("3B. Foreign Address", "s3_8d_foreign_emp_postal", "8.d. Postal Code", "text", False),
    ("3B. Foreign Address", "s3_8e_foreign_emp_country", "8.e. Country", "text", False),

    # =========================================================================
    # SECTION 4: U.S. POSITION DETAILS
    # =========================================================================
    ("4A. U.S. Position", "s4_1_us_position_title", "1. Position/Title in the United States", "text", True),
    ("4A. U.S. Position", "s4_2_us_duties", "2. Description of Duties in U.S. Position", "textarea", True),
    ("4A. U.S. Position", "s4_3_us_salary", "3. Annual Salary/Compensation ($)", "text", True),
    ("4A. U.S. Position", "s4_4_us_hours", "4. Hours per Week", "number", True),
    ("4A. U.S. Position", "s4_5_start_date", "5. Proposed Start Date (mm/dd/yyyy)", "date", True),
    ("4A. U.S. Position", "s4_6_end_date", "6. Proposed End Date (mm/dd/yyyy)", "date", True),

    # U.S. Worksite
    ("4B. U.S. Worksite", "s4_7a_worksite_street", "7.a. U.S. Worksite - Street Number and Name", "text", True),
    ("4B. U.S. Worksite", "s4_7b_worksite_city", "7.b. City or Town", "text", True),
    ("4B. U.S. Worksite", "s4_7c_worksite_state", "7.c. State", "select", True),
    ("4B. U.S. Worksite", "s4_7d_worksite_zip", "7.d. ZIP Code", "text", True),

    # =========================================================================
    # SECTION 5: PREVIOUS L-1 APPROVALS
    # =========================================================================
    ("5. Previous L-1", "s5_1_prior_l1", "1. Has the beneficiary previously been granted L-1 status?", "radio", True),
    ("5. Previous L-1", "s5_2_prior_receipt", "2. Prior L-1 Receipt Number", "text", False),
    ("5. Previous L-1", "s5_3_prior_from", "3. Prior L-1 Valid From (mm/dd/yyyy)", "date", False),
    ("5. Previous L-1", "s5_4_prior_to", "4. Prior L-1 Valid To (mm/dd/yyyy)", "date", False),
    ("5. Previous L-1", "s5_5_total_time_us", "5. Total Time Spent in L-1 Status in the U.S.", "text", False),

    # =========================================================================
    # SECTION 6: CERTIFICATION
    # =========================================================================
    ("6. Certification", "s6_1a_auth_family", "1.a. Authorized Signatory - Family Name", "text", True),
    ("6. Certification", "s6_1b_auth_given", "1.b. Authorized Signatory - Given Name", "text", True),
    ("6. Certification", "s6_2_auth_title", "2. Title", "text", True),
    ("6. Certification", "s6_3_auth_phone", "3. Daytime Telephone Number", "phone", True),
    ("6. Certification", "s6_4_auth_email", "4. Email Address", "email", False),
    ("6. Certification", "s6_signature_date", "Date of Signature (mm/dd/yyyy)", "date", True),
]

# Total: 75+ fields

if __name__ == "__main__":
    print(f"I-129S fields defined: {len(I129S_FIELDS)}")
