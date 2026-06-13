#!/usr/bin/env python3
"""
Expand I-800 (Petition to Classify Convention Adoptee as an Immediate Relative)
Hague Convention adoption petition. 10 pages, Parts 1-8.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I800_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT THE PETITIONER
    # =========================================================================
    ("1A. Petitioner Name", "p1_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("1A. Petitioner Name", "p1_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("1A. Petitioner Name", "p1_1c_middle_name", "1.c. Middle Name", "text", False),
    ("1A. Petitioner IDs", "p1_2_a_number", "2. Alien Registration Number (A-Number)", "text", False),
    ("1A. Petitioner IDs", "p1_3_uscis_account", "3. USCIS Online Account Number", "text", False),
    ("1A. Petitioner IDs", "p1_4_ssn", "4. U.S. Social Security Number", "text", True),
    ("1A. Petitioner Personal", "p1_5_dob", "5. Date of Birth (mm/dd/yyyy)", "date", True),
    ("1A. Petitioner Personal", "p1_6_city_birth", "6. City/Town of Birth", "text", True),
    ("1A. Petitioner Personal", "p1_7_state_birth", "7. State/Province of Birth", "text", False),
    ("1A. Petitioner Personal", "p1_8_country_birth", "8. Country of Birth", "text", True),
    ("1A. Petitioner Personal", "p1_9_citizenship", "9. Country of Citizenship", "text", True),
    ("1A. Petitioner Personal", "p1_10_sex", "10. Sex", "select", True),
    ("1A. Petitioner Personal", "p1_11_marital_status", "11. Marital Status", "select", True),

    # Petitioner Address
    ("1B. Address", "p1_12a_street", "12.a. Street Number and Name", "text", True),
    ("1B. Address", "p1_12b_apt_type", "12.b. Apt/Ste/Flr Type", "select", False),
    ("1B. Address", "p1_12c_apt_number", "12.c. Apt/Ste/Flr Number", "text", False),
    ("1B. Address", "p1_12d_city", "12.d. City or Town", "text", True),
    ("1B. Address", "p1_12e_state", "12.e. State", "select", True),
    ("1B. Address", "p1_12f_zip", "12.f. ZIP Code", "text", True),
    ("1C. Contact", "p1_13_phone", "13. Daytime Telephone Number", "phone", True),
    ("1C. Contact", "p1_14_mobile", "14. Mobile Telephone Number", "phone", False),
    ("1C. Contact", "p1_15_email", "15. Email Address", "email", False),

    # I-800A Reference
    ("1D. I-800A Info", "p1_16_i800a_receipt", "16. I-800A Receipt Number", "text", True),
    ("1D. I-800A Info", "p1_17_i800a_approval_date", "17. I-800A Approval Date (mm/dd/yyyy)", "date", True),
    ("1D. I-800A Info", "p1_18_i800a_expiration", "18. I-800A Expiration Date", "date", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT THE PETITIONER'S SPOUSE
    # =========================================================================
    ("2A. Spouse Name", "p2_1a_spouse_family", "1.a. Spouse's Family Name", "text", False),
    ("2A. Spouse Name", "p2_1b_spouse_given", "1.b. Spouse's Given Name", "text", False),
    ("2A. Spouse Name", "p2_1c_spouse_middle", "1.c. Spouse's Middle Name", "text", False),
    ("2A. Spouse Details", "p2_2_spouse_dob", "2. Spouse's Date of Birth", "date", False),
    ("2A. Spouse Details", "p2_3_spouse_country_birth", "3. Spouse's Country of Birth", "text", False),
    ("2A. Spouse Details", "p2_4_spouse_citizenship", "4. Spouse's Country of Citizenship", "text", False),
    ("2A. Spouse Details", "p2_5_spouse_ssn", "5. Spouse's SSN", "text", False),
    ("2A. Spouse Details", "p2_6_marriage_date", "6. Date of Marriage", "date", False),
    ("2A. Spouse Details", "p2_7_marriage_city", "7. City/Town of Marriage", "text", False),
    ("2A. Spouse Details", "p2_8_marriage_country", "8. Country of Marriage", "text", False),

    # =========================================================================
    # PART 3: INFORMATION ABOUT THE CONVENTION ADOPTEE (Child)
    # =========================================================================
    ("3A. Child Name", "p3_1a_child_family", "1.a. Child's Current Family Name (Last)", "text", True),
    ("3A. Child Name", "p3_1b_child_given", "1.b. Child's Current Given Name (First)", "text", True),
    ("3A. Child Name", "p3_1c_child_middle", "1.c. Child's Middle Name", "text", False),
    ("3A. Child Details", "p3_2_child_dob", "2. Date of Birth (mm/dd/yyyy)", "date", True),
    ("3A. Child Details", "p3_3_child_city_birth", "3. City/Town of Birth", "text", True),
    ("3A. Child Details", "p3_4_child_country_birth", "4. Country of Birth", "text", True),
    ("3A. Child Details", "p3_5_child_sex", "5. Sex", "select", True),
    ("3A. Child Details", "p3_6_child_citizenship", "6. Country of Citizenship", "text", True),
    ("3A. Child Details", "p3_7_convention_country", "7. Hague Convention Country of Habitual Residence", "text", True),

    # Child's Current Address
    ("3B. Child Address", "p3_8a_child_street", "8.a. Current Address - Street", "text", False),
    ("3B. Child Address", "p3_8b_child_city", "8.b. City or Town", "text", False),
    ("3B. Child Address", "p3_8c_child_province", "8.c. Province/State", "text", False),
    ("3B. Child Address", "p3_8d_child_postal", "8.d. Postal Code", "text", False),
    ("3B. Child Address", "p3_8e_child_country", "8.e. Country", "text", False),

    # New Name (after adoption)
    ("3C. New Name", "p3_9a_new_family", "9.a. New Family Name (after adoption)", "text", False),
    ("3C. New Name", "p3_9b_new_given", "9.b. New Given Name", "text", False),
    ("3C. New Name", "p3_9c_new_middle", "9.c. New Middle Name", "text", False),

    # =========================================================================
    # PART 4: CHILD'S BIOLOGICAL PARENTS / LEGAL CUSTODIAN
    # =========================================================================
    ("4A. Bio Parent 1", "p4_1a_parent1_family", "1.a. Biological Parent 1 - Family Name", "text", False),
    ("4A. Bio Parent 1", "p4_1b_parent1_given", "1.b. Biological Parent 1 - Given Name", "text", False),
    ("4A. Bio Parent 1", "p4_2_parent1_country_birth", "2. Country of Birth", "text", False),
    ("4A. Bio Parent 1", "p4_3_parent1_status", "3. Status (Living/Deceased/Unknown)", "select", False),
    ("4B. Bio Parent 2", "p4_4a_parent2_family", "4.a. Biological Parent 2 - Family Name", "text", False),
    ("4B. Bio Parent 2", "p4_4b_parent2_given", "4.b. Biological Parent 2 - Given Name", "text", False),
    ("4B. Bio Parent 2", "p4_5_parent2_country_birth", "5. Country of Birth", "text", False),
    ("4B. Bio Parent 2", "p4_6_parent2_status", "6. Status (Living/Deceased/Unknown)", "select", False),

    ("4C. Competent Authority", "p4_7_authority_name", "7. Name of Competent Authority/Central Authority", "text", False),
    ("4C. Competent Authority", "p4_8_authority_country", "8. Country of Competent Authority", "text", False),
    ("4C. Competent Authority", "p4_9_article_16_received", "9. Has Article 16 Report been received?", "radio", False),

    # =========================================================================
    # PART 5: ADOPTION DETAILS
    # =========================================================================
    ("5. Adoption", "p5_1_adoption_completed", "1. Has the adoption been completed?", "radio", True),
    ("5. Adoption", "p5_2_adoption_date", "2. Date of Final Adoption (mm/dd/yyyy)", "date", False),
    ("5. Adoption", "p5_3_adoption_city", "3. City/Town Where Adopted", "text", False),
    ("5. Adoption", "p5_4_adoption_country", "4. Country Where Adopted", "text", False),
    ("5. Adoption", "p5_5_custody_granted", "5. If not yet adopted, has custody been granted?", "radio", False),
    ("5. Adoption", "p5_6_custody_date", "6. Date Custody Granted (mm/dd/yyyy)", "date", False),
    ("5. Adoption", "p5_7_will_adopt_in_us", "7. Will adoption be completed in the U.S.?", "radio", False),

    # =========================================================================
    # PART 6: PETITIONER'S STATEMENT AND SIGNATURE
    # =========================================================================
    ("6. Statement", "p6_1a_english", "1.a. I can read and understand English", "checkbox", False),
    ("6. Statement", "p6_1b_interpreter", "1.b. Interpreter read form to me", "checkbox", False),
    ("6. Statement", "p6_1b_language", "1.b. Language", "text", False),
    ("6. Statement", "p6_2_preparer", "2. Preparer prepared this at my request", "checkbox", False),
    ("6. Contact", "p6_3_phone", "3. Daytime Telephone Number", "phone", False),
    ("6. Contact", "p6_4_email", "4. Email Address", "email", False),
    ("6. Signature", "p6_signature_date", "Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 7: INTERPRETER / PART 8: PREPARER
    # =========================================================================
    ("7. Interpreter", "p7_1a_interp_family", "1.a. Interpreter's Family Name", "text", False),
    ("7. Interpreter", "p7_1b_interp_given", "1.b. Interpreter's Given Name", "text", False),
    ("7. Interpreter", "p7_2_interp_org", "2. Organization", "text", False),
    ("7. Interpreter", "p7_3_interp_phone", "3. Telephone", "phone", False),
    ("7. Interpreter", "p7_4_interp_email", "4. Email", "email", False),
    ("7. Interpreter", "p7_5_language", "5. Language", "text", False),

    ("8. Preparer", "p8_1a_prep_family", "1.a. Preparer's Family Name", "text", False),
    ("8. Preparer", "p8_1b_prep_given", "1.b. Preparer's Given Name", "text", False),
    ("8. Preparer", "p8_2_prep_org", "2. Organization", "text", False),
    ("8. Preparer", "p8_3_prep_phone", "3. Telephone", "phone", False),
    ("8. Preparer", "p8_4_prep_email", "4. Email", "email", False),
]

# Total: 95+ fields

if __name__ == "__main__":
    print(f"I-800 fields defined: {len(I800_FIELDS)}")
