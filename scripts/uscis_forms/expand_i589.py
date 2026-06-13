#!/usr/bin/env python3
"""
Expand I-589 (Application for Asylum and for Withholding of Removal) with ALL official USCIS fields.
Edition 01/20/25 - 12 pages, Parts A.I through G + Supplements A & B.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I589_FIELDS = [
    # =========================================================================
    # PART A.I: INFORMATION ABOUT YOU (Page 1)
    # =========================================================================
    ("A.I. Information About You", "ai_cat_checkbox", "Check this box if you also want to apply for withholding of removal under the Convention Against Torture", "checkbox", False),
    ("A.I. Information About You", "ai_1_a_number", "1. Alien Registration Number(s) (A-Number) (if any)", "text", False),
    ("A.I. Information About You", "ai_2_ssn", "2. U.S. Social Security Number (if any)", "text", False),
    ("A.I. Information About You", "ai_3_uscis_account", "3. USCIS Online Account Number (if any)", "text", False),
    ("A.I. Information About You", "ai_4_last_name", "4. Complete Last Name", "text", True),
    ("A.I. Information About You", "ai_5_first_name", "5. First Name", "text", True),
    ("A.I. Information About You", "ai_6_middle_name", "6. Middle Name", "text", False),
    ("A.I. Information About You", "ai_7_other_names", "7. What other names have you used (include maiden name and aliases)?", "text", False),

    # Residence in the U.S.
    ("A.I. U.S. Residence", "ai_8_street", "8. Residence - Street Number and Name", "text", True),
    ("A.I. U.S. Residence", "ai_8_apt", "8. Residence - Apt. Number", "text", False),
    ("A.I. U.S. Residence", "ai_8_city", "8. Residence - City", "text", True),
    ("A.I. U.S. Residence", "ai_8_state", "8. Residence - State", "select", True),
    ("A.I. U.S. Residence", "ai_8_zip", "8. Residence - Zip Code", "text", True),
    ("A.I. U.S. Residence", "ai_8_phone", "8. Residence - Telephone Number", "phone", False),

    # Mailing Address
    ("A.I. Mailing Address", "ai_9_in_care_of", "9. Mailing Address - In Care Of (if applicable)", "text", False),
    ("A.I. Mailing Address", "ai_9_phone", "9. Mailing Address - Telephone Number", "phone", False),
    ("A.I. Mailing Address", "ai_9_street", "9. Mailing Address - Street Number and Name", "text", False),
    ("A.I. Mailing Address", "ai_9_apt", "9. Mailing Address - Apt. Number", "text", False),
    ("A.I. Mailing Address", "ai_9_city", "9. Mailing Address - City", "text", False),
    ("A.I. Mailing Address", "ai_9_state", "9. Mailing Address - State", "select", False),
    ("A.I. Mailing Address", "ai_9_zip", "9. Mailing Address - Zip Code", "text", False),

    # Personal Information
    ("A.I. Personal Information", "ai_10_sex", "10. Sex", "radio", True),
    ("A.I. Personal Information", "ai_11_marital_status", "11. Marital Status", "radio", True),
    ("A.I. Personal Information", "ai_12_dob", "12. Date of Birth (mm/dd/yyyy)", "date", True),
    ("A.I. Personal Information", "ai_13_city_country_birth", "13. City and Country of Birth", "text", True),
    ("A.I. Personal Information", "ai_14_nationality", "14. Present Nationality (Citizenship)", "text", True),
    ("A.I. Personal Information", "ai_15_nationality_birth", "15. Nationality at Birth", "text", True),
    ("A.I. Personal Information", "ai_16_race_ethnic", "16. Race, Ethnic, or Tribal Group", "text", False),
    ("A.I. Personal Information", "ai_17_religion", "17. Religion", "text", False),

    # Immigration Court Proceedings
    ("A.I. Court Proceedings", "ai_18_court_status", "18. Check the box that applies", "radio", True),

    # Entry to U.S.
    ("A.I. Entry Information", "ai_19a_last_leave_country", "19.a. When did you last leave your country? (mm/dd/yyyy)", "date", True),
    ("A.I. Entry Information", "ai_19b_i94_number", "19.b. What is your current I-94 Number, if any?", "text", False),
    # Entry 1
    ("A.I. U.S. Entry 1", "ai_19c1_date", "19.c. Entry 1 - Date (mm/dd/yyyy)", "date", False),
    ("A.I. U.S. Entry 1", "ai_19c1_place", "19.c. Entry 1 - Place", "text", False),
    ("A.I. U.S. Entry 1", "ai_19c1_status", "19.c. Entry 1 - Status", "text", False),
    ("A.I. U.S. Entry 1", "ai_19c1_status_expires", "19.c. Entry 1 - Date Status Expires", "date", False),
    # Entry 2
    ("A.I. U.S. Entry 2", "ai_19c2_date", "19.c. Entry 2 - Date (mm/dd/yyyy)", "date", False),
    ("A.I. U.S. Entry 2", "ai_19c2_place", "19.c. Entry 2 - Place", "text", False),
    ("A.I. U.S. Entry 2", "ai_19c2_status", "19.c. Entry 2 - Status", "text", False),
    # Entry 3
    ("A.I. U.S. Entry 3", "ai_19c3_date", "19.c. Entry 3 - Date (mm/dd/yyyy)", "date", False),
    ("A.I. U.S. Entry 3", "ai_19c3_place", "19.c. Entry 3 - Place", "text", False),
    ("A.I. U.S. Entry 3", "ai_19c3_status", "19.c. Entry 3 - Status", "text", False),

    # Passport / Travel Document
    ("A.I. Travel Documents", "ai_20_passport_country", "20. What country issued your last passport or travel document?", "text", False),
    ("A.I. Travel Documents", "ai_21_passport_number", "21. Passport Number", "text", False),
    ("A.I. Travel Documents", "ai_21_travel_doc_number", "21. Travel Document Number", "text", False),
    ("A.I. Travel Documents", "ai_22_expiration_date", "22. Expiration Date (mm/dd/yyyy)", "date", False),

    # Language
    ("A.I. Language", "ai_23_native_language", "23. What is your native language (include dialect, if applicable)?", "text", True),
    ("A.I. Language", "ai_24_fluent_english", "24. Are you fluent in English?", "radio", True),
    ("A.I. Language", "ai_25_other_languages", "25. What other languages do you speak fluently?", "text", False),

    # =========================================================================
    # PART A.II: INFORMATION ABOUT YOUR SPOUSE AND CHILDREN (Pages 2-3)
    # =========================================================================
    # Spouse
    ("A.II. Spouse", "aii_spouse_not_married", "I am not married (Skip to Your Children)", "checkbox", False),
    ("A.II. Spouse", "aii_sp_1_a_number", "1. Alien Registration Number (A-Number) (if any)", "text", False),
    ("A.II. Spouse", "aii_sp_2_passport", "2. Passport/ID Card Number (if any)", "text", False),
    ("A.II. Spouse", "aii_sp_3_dob", "3. Date of Birth (mm/dd/yyyy)", "date", False),
    ("A.II. Spouse", "aii_sp_4_ssn", "4. U.S. Social Security Number (if any)", "text", False),
    ("A.II. Spouse", "aii_sp_5_last_name", "5. Complete Last Name", "text", False),
    ("A.II. Spouse", "aii_sp_6_first_name", "6. First Name", "text", False),
    ("A.II. Spouse", "aii_sp_7_middle_name", "7. Middle Name", "text", False),
    ("A.II. Spouse", "aii_sp_8_other_names", "8. Other names used (include maiden name and aliases)", "text", False),
    ("A.II. Spouse", "aii_sp_9_marriage_date", "9. Date of Marriage (mm/dd/yyyy)", "date", False),
    ("A.II. Spouse", "aii_sp_10_marriage_place", "10. Place of Marriage", "text", False),
    ("A.II. Spouse", "aii_sp_11_city_country_birth", "11. City and Country of Birth", "text", False),
    ("A.II. Spouse", "aii_sp_12_nationality", "12. Nationality (Citizenship)", "text", False),
    ("A.II. Spouse", "aii_sp_13_race_ethnic", "13. Race, Ethnic, or Tribal Group", "text", False),
    ("A.II. Spouse", "aii_sp_14_sex", "14. Sex", "radio", False),
    ("A.II. Spouse", "aii_sp_15_in_us", "15. Is this person in the U.S.?", "radio", False),
    ("A.II. Spouse", "aii_sp_15_location", "15. If No, specify location", "text", False),
    ("A.II. Spouse", "aii_sp_16_place_last_entry", "16. Place of last entry into the U.S.", "text", False),
    ("A.II. Spouse", "aii_sp_17_date_last_entry", "17. Date of last entry into the U.S. (mm/dd/yyyy)", "date", False),
    ("A.II. Spouse", "aii_sp_18_i94_number", "18. I-94 Number (if any)", "text", False),
    ("A.II. Spouse", "aii_sp_19_status_admitted", "19. Status when last admitted (Visa type, if any)", "text", False),
    ("A.II. Spouse", "aii_sp_20_current_status", "20. What is your spouse's current status?", "text", False),
    ("A.II. Spouse", "aii_sp_21_expiration", "21. Expiration date of authorized stay (mm/dd/yyyy)", "date", False),
    ("A.II. Spouse", "aii_sp_22_court_proceedings", "22. Is your spouse in Immigration Court proceedings?", "radio", False),
    ("A.II. Spouse", "aii_sp_23_prev_arrival", "23. If previously in the U.S., date of previous arrival (mm/dd/yyyy)", "date", False),
    ("A.II. Spouse", "aii_sp_24_include_application", "24. Is your spouse to be included in this application?", "radio", False),

    # Children header
    ("A.II. Children", "aii_no_children", "I do not have any children (Skip to Part A.III)", "checkbox", False),
    ("A.II. Children", "aii_have_children", "I have children", "checkbox", False),
    ("A.II. Children", "aii_total_children", "Total number of children", "text", False),

    # Child 1
    ("A.II. Child 1", "aii_c1_1_a_number", "Child 1 - 1. Alien Registration Number (A-Number) (if any)", "text", False),
    ("A.II. Child 1", "aii_c1_2_passport", "Child 1 - 2. Passport/ID Card Number (if any)", "text", False),
    ("A.II. Child 1", "aii_c1_3_marital_status", "Child 1 - 3. Marital Status", "select", False),
    ("A.II. Child 1", "aii_c1_4_ssn", "Child 1 - 4. U.S. Social Security Number (if any)", "text", False),
    ("A.II. Child 1", "aii_c1_5_last_name", "Child 1 - 5. Complete Last Name", "text", False),
    ("A.II. Child 1", "aii_c1_6_first_name", "Child 1 - 6. First Name", "text", False),
    ("A.II. Child 1", "aii_c1_7_middle_name", "Child 1 - 7. Middle Name", "text", False),
    ("A.II. Child 1", "aii_c1_8_dob", "Child 1 - 8. Date of Birth (mm/dd/yyyy)", "date", False),
    ("A.II. Child 1", "aii_c1_9_city_country_birth", "Child 1 - 9. City and Country of Birth", "text", False),
    ("A.II. Child 1", "aii_c1_10_nationality", "Child 1 - 10. Nationality (Citizenship)", "text", False),
    ("A.II. Child 1", "aii_c1_11_race_ethnic", "Child 1 - 11. Race, Ethnic, or Tribal Group", "text", False),
    ("A.II. Child 1", "aii_c1_12_sex", "Child 1 - 12. Sex", "radio", False),
    ("A.II. Child 1", "aii_c1_13_in_us", "Child 1 - 13. Is this child in the U.S.?", "radio", False),
    ("A.II. Child 1", "aii_c1_13_location", "Child 1 - 13. If No, specify location", "text", False),
    ("A.II. Child 1", "aii_c1_14_place_last_entry", "Child 1 - 14. Place of last entry into the U.S.", "text", False),
    ("A.II. Child 1", "aii_c1_15_date_last_entry", "Child 1 - 15. Date of last entry into the U.S. (mm/dd/yyyy)", "date", False),
    ("A.II. Child 1", "aii_c1_16_i94_number", "Child 1 - 16. I-94 Number (if any)", "text", False),
    ("A.II. Child 1", "aii_c1_17_status_admitted", "Child 1 - 17. Status when last admitted (Visa type, if any)", "text", False),
    ("A.II. Child 1", "aii_c1_18_current_status", "Child 1 - 18. What is your child's current status?", "text", False),
    ("A.II. Child 1", "aii_c1_19_expiration", "Child 1 - 19. Expiration date of authorized stay (mm/dd/yyyy)", "date", False),
    ("A.II. Child 1", "aii_c1_20_court_proceedings", "Child 1 - 20. Is your child in Immigration Court proceedings?", "radio", False),
    ("A.II. Child 1", "aii_c1_21_include", "Child 1 - 21. Is this child to be included in this application?", "radio", False),

    # Child 2
    ("A.II. Child 2", "aii_c2_1_a_number", "Child 2 - 1. Alien Registration Number (A-Number) (if any)", "text", False),
    ("A.II. Child 2", "aii_c2_2_passport", "Child 2 - 2. Passport/ID Card Number (if any)", "text", False),
    ("A.II. Child 2", "aii_c2_3_marital_status", "Child 2 - 3. Marital Status", "select", False),
    ("A.II. Child 2", "aii_c2_4_ssn", "Child 2 - 4. U.S. Social Security Number (if any)", "text", False),
    ("A.II. Child 2", "aii_c2_5_last_name", "Child 2 - 5. Complete Last Name", "text", False),
    ("A.II. Child 2", "aii_c2_6_first_name", "Child 2 - 6. First Name", "text", False),
    ("A.II. Child 2", "aii_c2_7_middle_name", "Child 2 - 7. Middle Name", "text", False),
    ("A.II. Child 2", "aii_c2_8_dob", "Child 2 - 8. Date of Birth (mm/dd/yyyy)", "date", False),
    ("A.II. Child 2", "aii_c2_9_city_country_birth", "Child 2 - 9. City and Country of Birth", "text", False),
    ("A.II. Child 2", "aii_c2_10_nationality", "Child 2 - 10. Nationality (Citizenship)", "text", False),
    ("A.II. Child 2", "aii_c2_11_race_ethnic", "Child 2 - 11. Race, Ethnic, or Tribal Group", "text", False),
    ("A.II. Child 2", "aii_c2_12_sex", "Child 2 - 12. Sex", "radio", False),
    ("A.II. Child 2", "aii_c2_13_in_us", "Child 2 - 13. Is this child in the U.S.?", "radio", False),
    ("A.II. Child 2", "aii_c2_13_location", "Child 2 - 13. If No, specify location", "text", False),
    ("A.II. Child 2", "aii_c2_14_place_last_entry", "Child 2 - 14. Place of last entry into the U.S.", "text", False),
    ("A.II. Child 2", "aii_c2_15_date_last_entry", "Child 2 - 15. Date of last entry into the U.S. (mm/dd/yyyy)", "date", False),
    ("A.II. Child 2", "aii_c2_16_i94_number", "Child 2 - 16. I-94 Number (if any)", "text", False),
    ("A.II. Child 2", "aii_c2_17_status_admitted", "Child 2 - 17. Status when last admitted (Visa type, if any)", "text", False),
    ("A.II. Child 2", "aii_c2_18_current_status", "Child 2 - 18. What is your child's current status?", "text", False),
    ("A.II. Child 2", "aii_c2_19_expiration", "Child 2 - 19. Expiration date of authorized stay (mm/dd/yyyy)", "date", False),
    ("A.II. Child 2", "aii_c2_20_court_proceedings", "Child 2 - 20. Is your child in Immigration Court proceedings?", "radio", False),
    ("A.II. Child 2", "aii_c2_21_include", "Child 2 - 21. Is this child to be included in this application?", "radio", False),

    # Child 3
    ("A.II. Child 3", "aii_c3_1_a_number", "Child 3 - 1. Alien Registration Number (A-Number) (if any)", "text", False),
    ("A.II. Child 3", "aii_c3_2_passport", "Child 3 - 2. Passport/ID Card Number (if any)", "text", False),
    ("A.II. Child 3", "aii_c3_3_marital_status", "Child 3 - 3. Marital Status", "select", False),
    ("A.II. Child 3", "aii_c3_4_ssn", "Child 3 - 4. U.S. Social Security Number (if any)", "text", False),
    ("A.II. Child 3", "aii_c3_5_last_name", "Child 3 - 5. Complete Last Name", "text", False),
    ("A.II. Child 3", "aii_c3_6_first_name", "Child 3 - 6. First Name", "text", False),
    ("A.II. Child 3", "aii_c3_7_middle_name", "Child 3 - 7. Middle Name", "text", False),
    ("A.II. Child 3", "aii_c3_8_dob", "Child 3 - 8. Date of Birth (mm/dd/yyyy)", "date", False),
    ("A.II. Child 3", "aii_c3_9_city_country_birth", "Child 3 - 9. City and Country of Birth", "text", False),
    ("A.II. Child 3", "aii_c3_10_nationality", "Child 3 - 10. Nationality (Citizenship)", "text", False),
    ("A.II. Child 3", "aii_c3_11_race_ethnic", "Child 3 - 11. Race, Ethnic, or Tribal Group", "text", False),
    ("A.II. Child 3", "aii_c3_12_sex", "Child 3 - 12. Sex", "radio", False),
    ("A.II. Child 3", "aii_c3_13_in_us", "Child 3 - 13. Is this child in the U.S.?", "radio", False),
    ("A.II. Child 3", "aii_c3_13_location", "Child 3 - 13. If No, specify location", "text", False),
    ("A.II. Child 3", "aii_c3_14_place_last_entry", "Child 3 - 14. Place of last entry into the U.S.", "text", False),
    ("A.II. Child 3", "aii_c3_15_date_last_entry", "Child 3 - 15. Date of last entry into the U.S. (mm/dd/yyyy)", "date", False),
    ("A.II. Child 3", "aii_c3_16_i94_number", "Child 3 - 16. I-94 Number (if any)", "text", False),
    ("A.II. Child 3", "aii_c3_17_status_admitted", "Child 3 - 17. Status when last admitted (Visa type, if any)", "text", False),
    ("A.II. Child 3", "aii_c3_18_current_status", "Child 3 - 18. What is your child's current status?", "text", False),
    ("A.II. Child 3", "aii_c3_19_expiration", "Child 3 - 19. Expiration date of authorized stay (mm/dd/yyyy)", "date", False),
    ("A.II. Child 3", "aii_c3_20_court_proceedings", "Child 3 - 20. Is your child in Immigration Court proceedings?", "radio", False),
    ("A.II. Child 3", "aii_c3_21_include", "Child 3 - 21. Is this child to be included in this application?", "radio", False),

    # Child 4
    ("A.II. Child 4", "aii_c4_1_a_number", "Child 4 - 1. Alien Registration Number (A-Number) (if any)", "text", False),
    ("A.II. Child 4", "aii_c4_2_passport", "Child 4 - 2. Passport/ID Card Number (if any)", "text", False),
    ("A.II. Child 4", "aii_c4_3_marital_status", "Child 4 - 3. Marital Status", "select", False),
    ("A.II. Child 4", "aii_c4_4_ssn", "Child 4 - 4. U.S. Social Security Number (if any)", "text", False),
    ("A.II. Child 4", "aii_c4_5_last_name", "Child 4 - 5. Complete Last Name", "text", False),
    ("A.II. Child 4", "aii_c4_6_first_name", "Child 4 - 6. First Name", "text", False),
    ("A.II. Child 4", "aii_c4_7_middle_name", "Child 4 - 7. Middle Name", "text", False),
    ("A.II. Child 4", "aii_c4_8_dob", "Child 4 - 8. Date of Birth (mm/dd/yyyy)", "date", False),
    ("A.II. Child 4", "aii_c4_9_city_country_birth", "Child 4 - 9. City and Country of Birth", "text", False),
    ("A.II. Child 4", "aii_c4_10_nationality", "Child 4 - 10. Nationality (Citizenship)", "text", False),
    ("A.II. Child 4", "aii_c4_11_race_ethnic", "Child 4 - 11. Race, Ethnic, or Tribal Group", "text", False),
    ("A.II. Child 4", "aii_c4_12_sex", "Child 4 - 12. Sex", "radio", False),
    ("A.II. Child 4", "aii_c4_13_in_us", "Child 4 - 13. Is this child in the U.S.?", "radio", False),
    ("A.II. Child 4", "aii_c4_13_location", "Child 4 - 13. If No, specify location", "text", False),
    ("A.II. Child 4", "aii_c4_14_place_last_entry", "Child 4 - 14. Place of last entry into the U.S.", "text", False),
    ("A.II. Child 4", "aii_c4_15_date_last_entry", "Child 4 - 15. Date of last entry into the U.S. (mm/dd/yyyy)", "date", False),
    ("A.II. Child 4", "aii_c4_16_i94_number", "Child 4 - 16. I-94 Number (if any)", "text", False),
    ("A.II. Child 4", "aii_c4_17_status_admitted", "Child 4 - 17. Status when last admitted (Visa type, if any)", "text", False),
    ("A.II. Child 4", "aii_c4_18_current_status", "Child 4 - 18. What is your child's current status?", "text", False),
    ("A.II. Child 4", "aii_c4_19_expiration", "Child 4 - 19. Expiration date of authorized stay (mm/dd/yyyy)", "date", False),
    ("A.II. Child 4", "aii_c4_20_court_proceedings", "Child 4 - 20. Is your child in Immigration Court proceedings?", "radio", False),
    ("A.II. Child 4", "aii_c4_21_include", "Child 4 - 21. Is this child to be included in this application?", "radio", False),

    # =========================================================================
    # PART A.III: INFORMATION ABOUT YOUR BACKGROUND (Page 4)
    # =========================================================================
    # Last address before U.S. (2 rows)
    ("A.III. Last Address 1", "aiii_1a_street", "1. Last Address Before U.S. Row 1 - Number and Street", "text", False),
    ("A.III. Last Address 1", "aiii_1a_city", "1. Last Address Before U.S. Row 1 - City/Town", "text", False),
    ("A.III. Last Address 1", "aiii_1a_dept", "1. Last Address Before U.S. Row 1 - Department, Province, or State", "text", False),
    ("A.III. Last Address 1", "aiii_1a_country", "1. Last Address Before U.S. Row 1 - Country", "text", False),
    ("A.III. Last Address 1", "aiii_1a_from", "1. Last Address Before U.S. Row 1 - From (Mo/Yr)", "text", False),
    ("A.III. Last Address 1", "aiii_1a_to", "1. Last Address Before U.S. Row 1 - To (Mo/Yr)", "text", False),
    ("A.III. Last Address 2", "aiii_1b_street", "1. Last Address Before U.S. Row 2 - Number and Street", "text", False),
    ("A.III. Last Address 2", "aiii_1b_city", "1. Last Address Before U.S. Row 2 - City/Town", "text", False),
    ("A.III. Last Address 2", "aiii_1b_dept", "1. Last Address Before U.S. Row 2 - Department, Province, or State", "text", False),
    ("A.III. Last Address 2", "aiii_1b_country", "1. Last Address Before U.S. Row 2 - Country", "text", False),
    ("A.III. Last Address 2", "aiii_1b_from", "1. Last Address Before U.S. Row 2 - From (Mo/Yr)", "text", False),
    ("A.III. Last Address 2", "aiii_1b_to", "1. Last Address Before U.S. Row 2 - To (Mo/Yr)", "text", False),

    # Residences past 5 years (3 rows)
    ("A.III. Residence 1", "aiii_2a_street", "2. Residence Past 5 Years Row 1 - Number and Street", "text", False),
    ("A.III. Residence 1", "aiii_2a_city", "2. Residence Past 5 Years Row 1 - City/Town", "text", False),
    ("A.III. Residence 1", "aiii_2a_dept", "2. Residence Past 5 Years Row 1 - Department, Province, or State", "text", False),
    ("A.III. Residence 1", "aiii_2a_country", "2. Residence Past 5 Years Row 1 - Country", "text", False),
    ("A.III. Residence 1", "aiii_2a_from", "2. Residence Past 5 Years Row 1 - From (Mo/Yr)", "text", False),
    ("A.III. Residence 1", "aiii_2a_to", "2. Residence Past 5 Years Row 1 - To (Mo/Yr)", "text", False),
    ("A.III. Residence 2", "aiii_2b_street", "2. Residence Past 5 Years Row 2 - Number and Street", "text", False),
    ("A.III. Residence 2", "aiii_2b_city", "2. Residence Past 5 Years Row 2 - City/Town", "text", False),
    ("A.III. Residence 2", "aiii_2b_dept", "2. Residence Past 5 Years Row 2 - Department, Province, or State", "text", False),
    ("A.III. Residence 2", "aiii_2b_country", "2. Residence Past 5 Years Row 2 - Country", "text", False),
    ("A.III. Residence 2", "aiii_2b_from", "2. Residence Past 5 Years Row 2 - From (Mo/Yr)", "text", False),
    ("A.III. Residence 2", "aiii_2b_to", "2. Residence Past 5 Years Row 2 - To (Mo/Yr)", "text", False),
    ("A.III. Residence 3", "aiii_2c_street", "2. Residence Past 5 Years Row 3 - Number and Street", "text", False),
    ("A.III. Residence 3", "aiii_2c_city", "2. Residence Past 5 Years Row 3 - City/Town", "text", False),
    ("A.III. Residence 3", "aiii_2c_dept", "2. Residence Past 5 Years Row 3 - Department, Province, or State", "text", False),
    ("A.III. Residence 3", "aiii_2c_country", "2. Residence Past 5 Years Row 3 - Country", "text", False),
    ("A.III. Residence 3", "aiii_2c_from", "2. Residence Past 5 Years Row 3 - From (Mo/Yr)", "text", False),
    ("A.III. Residence 3", "aiii_2c_to", "2. Residence Past 5 Years Row 3 - To (Mo/Yr)", "text", False),

    # Education (3 rows)
    ("A.III. Education 1", "aiii_3a_school", "3. Education Row 1 - Name of School", "text", False),
    ("A.III. Education 1", "aiii_3a_type", "3. Education Row 1 - Type of School", "text", False),
    ("A.III. Education 1", "aiii_3a_location", "3. Education Row 1 - Location (Address)", "text", False),
    ("A.III. Education 1", "aiii_3a_from", "3. Education Row 1 - From (Mo/Yr)", "text", False),
    ("A.III. Education 1", "aiii_3a_to", "3. Education Row 1 - To (Mo/Yr)", "text", False),
    ("A.III. Education 2", "aiii_3b_school", "3. Education Row 2 - Name of School", "text", False),
    ("A.III. Education 2", "aiii_3b_type", "3. Education Row 2 - Type of School", "text", False),
    ("A.III. Education 2", "aiii_3b_location", "3. Education Row 2 - Location (Address)", "text", False),
    ("A.III. Education 2", "aiii_3b_from", "3. Education Row 2 - From (Mo/Yr)", "text", False),
    ("A.III. Education 2", "aiii_3b_to", "3. Education Row 2 - To (Mo/Yr)", "text", False),
    ("A.III. Education 3", "aiii_3c_school", "3. Education Row 3 - Name of School", "text", False),
    ("A.III. Education 3", "aiii_3c_type", "3. Education Row 3 - Type of School", "text", False),
    ("A.III. Education 3", "aiii_3c_location", "3. Education Row 3 - Location (Address)", "text", False),
    ("A.III. Education 3", "aiii_3c_from", "3. Education Row 3 - From (Mo/Yr)", "text", False),
    ("A.III. Education 3", "aiii_3c_to", "3. Education Row 3 - To (Mo/Yr)", "text", False),

    # Employment past 5 years (3 rows)
    ("A.III. Employment 1", "aiii_4a_employer", "4. Employment Row 1 - Name and Address of Employer", "text", False),
    ("A.III. Employment 1", "aiii_4a_occupation", "4. Employment Row 1 - Your Occupation", "text", False),
    ("A.III. Employment 1", "aiii_4a_from", "4. Employment Row 1 - From (Mo/Yr)", "text", False),
    ("A.III. Employment 1", "aiii_4a_to", "4. Employment Row 1 - To (Mo/Yr)", "text", False),
    ("A.III. Employment 2", "aiii_4b_employer", "4. Employment Row 2 - Name and Address of Employer", "text", False),
    ("A.III. Employment 2", "aiii_4b_occupation", "4. Employment Row 2 - Your Occupation", "text", False),
    ("A.III. Employment 2", "aiii_4b_from", "4. Employment Row 2 - From (Mo/Yr)", "text", False),
    ("A.III. Employment 2", "aiii_4b_to", "4. Employment Row 2 - To (Mo/Yr)", "text", False),
    ("A.III. Employment 3", "aiii_4c_employer", "4. Employment Row 3 - Name and Address of Employer", "text", False),
    ("A.III. Employment 3", "aiii_4c_occupation", "4. Employment Row 3 - Your Occupation", "text", False),
    ("A.III. Employment 3", "aiii_4c_from", "4. Employment Row 3 - From (Mo/Yr)", "text", False),
    ("A.III. Employment 3", "aiii_4c_to", "4. Employment Row 3 - To (Mo/Yr)", "text", False),

    # Parents and siblings (6 rows)
    ("A.III. Family - Mother", "aiii_5_mother_name", "5. Mother - Full Name", "text", False),
    ("A.III. Family - Mother", "aiii_5_mother_birth", "5. Mother - City/Town and Country of Birth", "text", False),
    ("A.III. Family - Mother", "aiii_5_mother_deceased", "5. Mother - Deceased", "checkbox", False),
    ("A.III. Family - Mother", "aiii_5_mother_location", "5. Mother - Current Location", "text", False),
    ("A.III. Family - Father", "aiii_5_father_name", "5. Father - Full Name", "text", False),
    ("A.III. Family - Father", "aiii_5_father_birth", "5. Father - City/Town and Country of Birth", "text", False),
    ("A.III. Family - Father", "aiii_5_father_deceased", "5. Father - Deceased", "checkbox", False),
    ("A.III. Family - Father", "aiii_5_father_location", "5. Father - Current Location", "text", False),
    ("A.III. Family - Sibling 1", "aiii_5_sib1_name", "5. Sibling 1 - Full Name", "text", False),
    ("A.III. Family - Sibling 1", "aiii_5_sib1_birth", "5. Sibling 1 - City/Town and Country of Birth", "text", False),
    ("A.III. Family - Sibling 1", "aiii_5_sib1_deceased", "5. Sibling 1 - Deceased", "checkbox", False),
    ("A.III. Family - Sibling 1", "aiii_5_sib1_location", "5. Sibling 1 - Current Location", "text", False),
    ("A.III. Family - Sibling 2", "aiii_5_sib2_name", "5. Sibling 2 - Full Name", "text", False),
    ("A.III. Family - Sibling 2", "aiii_5_sib2_birth", "5. Sibling 2 - City/Town and Country of Birth", "text", False),
    ("A.III. Family - Sibling 2", "aiii_5_sib2_deceased", "5. Sibling 2 - Deceased", "checkbox", False),
    ("A.III. Family - Sibling 2", "aiii_5_sib2_location", "5. Sibling 2 - Current Location", "text", False),
    ("A.III. Family - Sibling 3", "aiii_5_sib3_name", "5. Sibling 3 - Full Name", "text", False),
    ("A.III. Family - Sibling 3", "aiii_5_sib3_birth", "5. Sibling 3 - City/Town and Country of Birth", "text", False),
    ("A.III. Family - Sibling 3", "aiii_5_sib3_deceased", "5. Sibling 3 - Deceased", "checkbox", False),
    ("A.III. Family - Sibling 3", "aiii_5_sib3_location", "5. Sibling 3 - Current Location", "text", False),
    ("A.III. Family - Sibling 4", "aiii_5_sib4_name", "5. Sibling 4 - Full Name", "text", False),
    ("A.III. Family - Sibling 4", "aiii_5_sib4_birth", "5. Sibling 4 - City/Town and Country of Birth", "text", False),
    ("A.III. Family - Sibling 4", "aiii_5_sib4_deceased", "5. Sibling 4 - Deceased", "checkbox", False),
    ("A.III. Family - Sibling 4", "aiii_5_sib4_location", "5. Sibling 4 - Current Location", "text", False),

    # =========================================================================
    # PART B: INFORMATION ABOUT YOUR APPLICATION (Pages 5-6)
    # =========================================================================
    ("B. Basis for Claim", "b_1_race", "1. Basis - Race", "checkbox", False),
    ("B. Basis for Claim", "b_1_religion", "1. Basis - Religion", "checkbox", False),
    ("B. Basis for Claim", "b_1_nationality", "1. Basis - Nationality", "checkbox", False),
    ("B. Basis for Claim", "b_1_political_opinion", "1. Basis - Political opinion", "checkbox", False),
    ("B. Basis for Claim", "b_1_social_group", "1. Basis - Membership in a particular social group", "checkbox", False),
    ("B. Basis for Claim", "b_1_torture", "1. Basis - Torture Convention", "checkbox", False),
    ("B. Harm Experienced", "b_1a_harm", "A. Have you experienced harm or mistreatment?", "radio", True),
    ("B. Harm Experienced", "b_1a_harm_detail", "A. If Yes, explain in detail", "textarea", False),
    ("B. Fear of Harm", "b_1b_fear", "B. Do you fear harm if you return to your home country?", "radio", True),
    ("B. Fear of Harm", "b_1b_fear_detail", "B. If Yes, explain in detail", "textarea", False),
    ("B. Criminal History", "b_2_arrested", "2. Have you ever been accused, charged, arrested, detained, convicted or imprisoned?", "radio", True),
    ("B. Criminal History", "b_2_arrested_detail", "2. If Yes, explain the circumstances", "textarea", False),
    ("B. Organizations", "b_3a_organizations", "3.A. Have you or your family ever belonged to organizations or groups?", "radio", True),
    ("B. Organizations", "b_3a_organizations_detail", "3.A. If Yes, describe participation and positions", "textarea", False),
    ("B. Organizations", "b_3b_continue_participate", "3.B. Do you or your family members continue to participate?", "radio", False),
    ("B. Organizations", "b_3b_continue_detail", "3.B. If Yes, describe current participation", "textarea", False),
    ("B. Torture Fear", "b_4_torture_fear", "4. Are you afraid of being subjected to torture?", "radio", True),
    ("B. Torture Fear", "b_4_torture_detail", "4. If Yes, explain the nature of torture you fear", "textarea", False),

    # =========================================================================
    # PART C: ADDITIONAL INFORMATION (Pages 7-8)
    # =========================================================================
    ("C. Prior Applications", "c_1_prior_application", "1. Have you or family ever applied for refugee, asylum, or withholding status?", "radio", True),
    ("C. Prior Applications", "c_1_prior_detail", "1. If Yes, explain the decision", "textarea", False),
    ("C. Travel History", "c_2a_travel_through", "2.A. Did you travel through or reside in other countries before entering U.S.?", "radio", True),
    ("C. Travel History", "c_2b_family_lawful_status", "2.B. Have family members applied for lawful status in other countries?", "radio", False),
    ("C. Travel History", "c_2_travel_detail", "2. If Yes to 2A/2B, provide details (country, length, status, reasons)", "textarea", False),
    ("C. Causing Harm", "c_3_causing_harm", "3. Have you ever ordered, incited, or participated in causing harm based on protected grounds?", "radio", True),
    ("C. Causing Harm", "c_3_causing_harm_detail", "3. If Yes, describe in detail", "textarea", False),
    ("C. Return to Country", "c_4_return_country", "4. After leaving, did you return to the country where harmed?", "radio", True),
    ("C. Return to Country", "c_4_return_detail", "4. If Yes, describe circumstances of visits", "textarea", False),
    ("C. Filing Delay", "c_5_more_than_1_year", "5. Are you filing more than 1 year after last arrival in U.S.?", "radio", True),
    ("C. Filing Delay", "c_5_delay_detail", "5. If Yes, explain why you did not file within the first year", "textarea", False),
    ("C. Criminal Record", "c_6_criminal", "6. Have you or family committed any crime or been arrested/charged/convicted?", "radio", True),
    ("C. Criminal Record", "c_6_criminal_detail", "6. If Yes, specify each instance in detail", "textarea", False),

    # =========================================================================
    # PART D: YOUR SIGNATURE (Page 9)
    # =========================================================================
    ("D. Applicant Signature", "d_print_name", "Print your complete name", "text", True),
    ("D. Applicant Signature", "d_native_alphabet", "Write your name in your native alphabet", "text", False),
    ("D. Applicant Signature", "d_family_assisted", "Did your spouse, parent, or child(ren) assist you?", "radio", False),
    ("D. Applicant Signature", "d_assist1_name", "Assistant 1 - Name", "text", False),
    ("D. Applicant Signature", "d_assist1_relationship", "Assistant 1 - Relationship", "text", False),
    ("D. Applicant Signature", "d_assist2_name", "Assistant 2 - Name", "text", False),
    ("D. Applicant Signature", "d_assist2_relationship", "Assistant 2 - Relationship", "text", False),
    ("D. Applicant Signature", "d_other_prepared", "Did someone other than family prepare this application?", "radio", False),
    ("D. Applicant Signature", "d_counsel_list", "Have you been provided with a list of free/low-cost assistance?", "radio", False),
    ("D. Applicant Signature", "d_signature_date", "Date (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART E: DECLARATION OF PERSON PREPARING FORM (Page 9)
    # =========================================================================
    ("E. Preparer Declaration", "e_preparer_name", "Print Complete Name of Preparer", "text", False),
    ("E. Preparer Declaration", "e_preparer_phone", "Daytime Telephone Number", "phone", False),
    ("E. Preparer Declaration", "e_preparer_street", "Address - Street Number and Name", "text", False),
    ("E. Preparer Declaration", "e_preparer_apt", "Address - Apt. Number", "text", False),
    ("E. Preparer Declaration", "e_preparer_city", "Address - City", "text", False),
    ("E. Preparer Declaration", "e_preparer_state", "Address - State", "select", False),
    ("E. Preparer Declaration", "e_preparer_zip", "Address - Zip Code", "text", False),
    ("E. Preparer Declaration", "e_g28_attached", "Form G-28 is attached", "checkbox", False),
    ("E. Preparer Declaration", "e_attorney_bar", "Attorney State Bar Number (if applicable)", "text", False),
    ("E. Preparer Declaration", "e_attorney_uscis_account", "Attorney or Accredited Representative USCIS Online Account Number", "text", False),

    # =========================================================================
    # PART F: ASYLUM INTERVIEW (Page 10) - completed at interview
    # =========================================================================
    ("F. Asylum Interview", "f_signature_date", "Date (mm/dd/yyyy)", "date", False),
    ("F. Asylum Interview", "f_native_alphabet", "Write Your Name in Your Native Alphabet", "text", False),

    # =========================================================================
    # PART G: REMOVAL HEARING (Page 10) - completed at hearing
    # =========================================================================
    ("G. Removal Hearing", "g_signature_date", "Date (mm/dd/yyyy)", "date", False),
    ("G. Removal Hearing", "g_native_alphabet", "Write Your Name in Your Native Alphabet", "text", False),

    # =========================================================================
    # SUPPLEMENT B: ADDITIONAL INFORMATION (Page 12)
    # =========================================================================
    ("Supplement B", "supb_a_number", "A-Number (if available)", "text", False),
    ("Supplement B", "supb_date", "Date", "date", False),
    ("Supplement B", "supb_name", "Applicant's Name", "text", False),
    ("Supplement B", "supb_part", "Part", "text", False),
    ("Supplement B", "supb_question", "Question", "text", False),
    ("Supplement B", "supb_additional_info", "Additional Information", "textarea", False),
]


def update_i589(template_id=None):
    """Insert or update I-589 fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-589%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('I-589 - Application for Asylum and for Withholding of Removal (EXPANDED)', "
                    "'Complete I-589 with all official USCIS fields - Edition 01/20/25') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(I589_FIELDS):
            conn.execute(text(
                "INSERT INTO questionnaire_fields (template_id, section, field_name, label, field_type, is_required, \"order\") "
                "VALUES (:tid, :section, :field_name, :label, :field_type, :is_required, :order)"
            ), {
                "tid": template_id, "section": section, "field_name": field_name,
                "label": label, "field_type": field_type, "is_required": required, "order": i + 1
            })

        conn.commit()
        print(f"I-589 expanded: template_id={template_id}, fields={len(I589_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_i589()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(I589_FIELDS)}")

    sections = {}
    for section, _, _, _, _ in I589_FIELDS:
        sections[section] = sections.get(section, 0) + 1

    print("\nFields by section:")
    for section, count in sections.items():
        print(f"  {section}: {count}")
