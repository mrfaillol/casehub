#!/usr/bin/env python3
"""
Expand I-600 (Petition to Classify Orphan as an Immediate Relative)
Non-Hague Convention adoption petition. 10 pages, Parts 1-7.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I600_FIELDS = [
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
    ("1A. Petitioner Personal", "p1_9_citizenship", "9. Country of Citizenship/Nationality", "text", True),
    ("1A. Petitioner Personal", "p1_10_sex", "10. Sex", "select", True),
    ("1A. Petitioner Personal", "p1_11_marital_status", "11. Marital Status", "select", True),

    # Petitioner Address
    ("1B. Petitioner Address", "p1_12a_street", "12.a. Street Number and Name", "text", True),
    ("1B. Petitioner Address", "p1_12b_apt_type", "12.b. Apt/Ste/Flr Type", "select", False),
    ("1B. Petitioner Address", "p1_12c_apt_number", "12.c. Apt/Ste/Flr Number", "text", False),
    ("1B. Petitioner Address", "p1_12d_city", "12.d. City or Town", "text", True),
    ("1B. Petitioner Address", "p1_12e_state", "12.e. State", "select", True),
    ("1B. Petitioner Address", "p1_12f_zip", "12.f. ZIP Code", "text", True),

    # Petitioner Contact
    ("1C. Contact", "p1_13_phone", "13. Daytime Telephone Number", "phone", True),
    ("1C. Contact", "p1_14_mobile", "14. Mobile Telephone Number", "phone", False),
    ("1C. Contact", "p1_15_email", "15. Email Address", "email", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT THE PETITIONER'S SPOUSE (if married)
    # =========================================================================
    ("2A. Spouse Name", "p2_1a_spouse_family", "1.a. Spouse's Family Name (Last Name)", "text", False),
    ("2A. Spouse Name", "p2_1b_spouse_given", "1.b. Spouse's Given Name (First Name)", "text", False),
    ("2A. Spouse Name", "p2_1c_spouse_middle", "1.c. Spouse's Middle Name", "text", False),
    ("2A. Spouse Details", "p2_2_spouse_dob", "2. Spouse's Date of Birth (mm/dd/yyyy)", "date", False),
    ("2A. Spouse Details", "p2_3_spouse_country_birth", "3. Spouse's Country of Birth", "text", False),
    ("2A. Spouse Details", "p2_4_spouse_citizenship", "4. Spouse's Country of Citizenship", "text", False),
    ("2A. Spouse Details", "p2_5_spouse_ssn", "5. Spouse's SSN", "text", False),
    ("2A. Spouse Details", "p2_6_marriage_date", "6. Date of Marriage (mm/dd/yyyy)", "date", False),
    ("2A. Spouse Details", "p2_7_marriage_city", "7. City/Town of Marriage", "text", False),
    ("2A. Spouse Details", "p2_8_marriage_state", "8. State/Province of Marriage", "text", False),
    ("2A. Spouse Details", "p2_9_marriage_country", "9. Country of Marriage", "text", False),

    # =========================================================================
    # PART 3: INFORMATION ABOUT THE ORPHAN
    # =========================================================================
    ("3A. Orphan Name", "p3_1a_orphan_family", "1.a. Orphan's Family Name (Last Name) at birth", "text", True),
    ("3A. Orphan Name", "p3_1b_orphan_given", "1.b. Orphan's Given Name (First Name) at birth", "text", True),
    ("3A. Orphan Name", "p3_1c_orphan_middle", "1.c. Orphan's Middle Name at birth", "text", False),
    ("3A. Orphan Name", "p3_2a_orphan_new_family", "2.a. New Family Name (after adoption, if known)", "text", False),
    ("3A. Orphan Name", "p3_2b_orphan_new_given", "2.b. New Given Name (after adoption)", "text", False),
    ("3A. Orphan Name", "p3_2c_orphan_new_middle", "2.c. New Middle Name (after adoption)", "text", False),
    ("3A. Orphan Details", "p3_3_dob", "3. Date of Birth (mm/dd/yyyy)", "date", True),
    ("3A. Orphan Details", "p3_4_city_birth", "4. City/Town of Birth", "text", True),
    ("3A. Orphan Details", "p3_5_country_birth", "5. Country of Birth", "text", True),
    ("3A. Orphan Details", "p3_6_sex", "6. Sex", "select", True),
    ("3A. Orphan Details", "p3_7_citizenship", "7. Country of Citizenship/Nationality", "text", True),

    # Orphan's Current Address
    ("3B. Orphan Address", "p3_8a_street", "8.a. Current Address - Street", "text", False),
    ("3B. Orphan Address", "p3_8b_city", "8.b. City or Town", "text", False),
    ("3B. Orphan Address", "p3_8c_province", "8.c. Province/State", "text", False),
    ("3B. Orphan Address", "p3_8d_postal", "8.d. Postal Code", "text", False),
    ("3B. Orphan Address", "p3_8e_country", "8.e. Country", "text", False),

    # =========================================================================
    # PART 4: INFORMATION ABOUT THE ORPHAN'S PARENTS
    # =========================================================================
    ("4A. Birth Parent 1", "p4_1a_parent1_family", "1.a. Birth Parent 1 - Family Name", "text", False),
    ("4A. Birth Parent 1", "p4_1b_parent1_given", "1.b. Birth Parent 1 - Given Name", "text", False),
    ("4A. Birth Parent 1", "p4_2_parent1_country", "2. Birth Parent 1 - Country of Birth", "text", False),
    ("4A. Birth Parent 1", "p4_3_parent1_status", "3. Birth Parent 1 - Deceased/Incapacity/Sole Parent/Both", "select", False),
    ("4A. Birth Parent 1", "p4_4_parent1_irrevocable_release", "4. Has Birth Parent 1 provided irrevocable release?", "radio", False),
    ("4B. Birth Parent 2", "p4_5a_parent2_family", "5.a. Birth Parent 2 - Family Name", "text", False),
    ("4B. Birth Parent 2", "p4_5b_parent2_given", "5.b. Birth Parent 2 - Given Name", "text", False),
    ("4B. Birth Parent 2", "p4_6_parent2_country", "6. Birth Parent 2 - Country of Birth", "text", False),
    ("4B. Birth Parent 2", "p4_7_parent2_status", "7. Birth Parent 2 - Status", "select", False),
    ("4B. Birth Parent 2", "p4_8_parent2_irrevocable_release", "8. Has Birth Parent 2 provided irrevocable release?", "radio", False),

    # =========================================================================
    # PART 5: ADOPTION INFORMATION
    # =========================================================================
    ("5. Adoption Info", "p5_1_adoption_completed", "1. Has the adoption been completed?", "radio", True),
    ("5. Adoption Info", "p5_2_adoption_date", "2. Date of Adoption (mm/dd/yyyy)", "date", False),
    ("5. Adoption Info", "p5_3_adoption_city", "3. City/Town Where Adopted", "text", False),
    ("5. Adoption Info", "p5_4_adoption_country", "4. Country Where Adopted", "text", False),
    ("5. Adoption Info", "p5_5_pre_adoption_reqs", "5. Have all pre-adoption requirements been met?", "radio", False),
    ("5. Adoption Info", "p5_6_orphan_in_custody", "6. Is the orphan in your legal custody?", "radio", False),
    ("5. Adoption Info", "p5_7_home_study_completed", "7. Has a home study been completed?", "radio", True),
    ("5. Adoption Info", "p5_8_home_study_date", "8. Date of Home Study (mm/dd/yyyy)", "date", False),
    ("5. Adoption Info", "p5_9_home_study_agency", "9. Name of Home Study Agency", "text", False),

    # =========================================================================
    # PART 6: PETITIONER'S STATEMENT AND SIGNATURE
    # =========================================================================
    ("6. Statement", "p6_1a_english", "1.a. I can read and understand English", "checkbox", False),
    ("6. Statement", "p6_1b_interpreter", "1.b. Interpreter read form to me", "checkbox", False),
    ("6. Statement", "p6_1b_language", "1.b. Language", "text", False),
    ("6. Statement", "p6_2_preparer", "2. Preparer prepared this at my request", "checkbox", False),
    ("6. Statement", "p6_3_phone", "3. Daytime Telephone Number", "phone", False),
    ("6. Statement", "p6_4_email", "4. Email Address", "email", False),
    ("6. Signature", "p6_signature_date", "Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 7: ADDITIONAL INFORMATION
    # =========================================================================
    ("7. Additional", "p7_1a_page_1", "1.a. Page Number", "text", False),
    ("7. Additional", "p7_1b_part_1", "1.b. Part Number", "text", False),
    ("7. Additional", "p7_1c_item_1", "1.c. Item Number", "text", False),
    ("7. Additional", "p7_1d_info_1", "1.d. Additional Information", "textarea", False),
    ("7. Additional", "p7_2a_page_2", "2.a. Page Number", "text", False),
    ("7. Additional", "p7_2b_part_2", "2.b. Part Number", "text", False),
    ("7. Additional", "p7_2c_item_2", "2.c. Item Number", "text", False),
    ("7. Additional", "p7_2d_info_2", "2.d. Additional Information", "textarea", False),
]

# Total: 85+ fields

if __name__ == "__main__":
    print(f"I-600 fields defined: {len(I600_FIELDS)}")
