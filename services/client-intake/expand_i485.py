#!/usr/bin/env python3
"""Expand I-485 with ALL official USCIS fields - Part 8 has 80+ questions"""
import os
import json
from sqlalchemy import create_engine, text
from uscis_form_options import I485_OPTIONS_MAP

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/casehub")
engine = create_engine(DATABASE_URL)

I485_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT YOU (Applicant)
    # =========================================================================
    ("1A. Your Full Name", "p1_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("1A. Your Full Name", "p1_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("1A. Your Full Name", "p1_1c_middle_name", "1.c. Middle Name", "text", False),

    ("1B. Other Names Used", "p1_2a_other1_family", "2.a. Other Name 1 - Family Name", "text", False),
    ("1B. Other Names Used", "p1_2b_other1_given", "2.b. Other Name 1 - Given Name", "text", False),
    ("1B. Other Names Used", "p1_2c_other1_middle", "2.c. Other Name 1 - Middle Name", "text", False),
    ("1B. Other Names Used", "p1_3a_other2_family", "3.a. Other Name 2 - Family Name", "text", False),
    ("1B. Other Names Used", "p1_3b_other2_given", "3.b. Other Name 2 - Given Name", "text", False),
    ("1B. Other Names Used", "p1_3c_other2_middle", "3.c. Other Name 2 - Middle Name", "text", False),
    ("1B. Other Names Used", "p1_4a_maiden_family", "4.a. Maiden Name - Family Name", "text", False),
    ("1B. Other Names Used", "p1_4b_maiden_given", "4.b. Maiden Name - Given Name", "text", False),

    ("1C. Personal Information", "p1_5_dob", "5. Date of Birth (mm/dd/yyyy)", "date", True),
    ("1C. Personal Information", "p1_6_sex", "6. Sex", "select", True),
    ("1C. Personal Information", "p1_7_city_birth", "7. City/Town of Birth", "text", True),
    ("1C. Personal Information", "p1_8_country_birth", "8. Country of Birth", "text", True),
    ("1C. Personal Information", "p1_9_citizenship", "9. Country of Citizenship/Nationality", "text", True),
    ("1C. Personal Information", "p1_10_second_citizenship", "10. Second Country of Citizenship (if any)", "text", False),

    ("1D. Identification Numbers", "p1_11_a_number", "11. Alien Registration Number (A-Number)", "text", False),
    ("1D. Identification Numbers", "p1_12_uscis_account", "12. USCIS Online Account Number", "text", False),
    ("1D. Identification Numbers", "p1_13_ssn", "13. U.S. Social Security Number", "text", False),

    ("1E. U.S. Mailing Address", "p1_14a_care_of", "14.a. In Care Of Name (c/o)", "text", False),
    ("1E. U.S. Mailing Address", "p1_14b_street", "14.b. Street Number and Name", "text", True),
    ("1E. U.S. Mailing Address", "p1_14c_apt_type", "14.c. Apt/Ste/Flr Type", "select", False),
    ("1E. U.S. Mailing Address", "p1_14d_apt_number", "14.d. Apt/Ste/Flr Number", "text", False),
    ("1E. U.S. Mailing Address", "p1_14e_city", "14.e. City or Town", "text", True),
    ("1E. U.S. Mailing Address", "p1_14f_state", "14.f. State", "select", True),
    ("1E. U.S. Mailing Address", "p1_14g_zip", "14.g. ZIP Code", "text", True),

    ("1F. Safe Alternate Address", "p1_15_safe_address", "15. Do you want USCIS to send notices to a safe alternate address?", "radio", False),
    ("1F. Safe Alternate Address", "p1_16a_safe_care_of", "16.a. Safe Address - In Care Of Name", "text", False),
    ("1F. Safe Alternate Address", "p1_16b_safe_street", "16.b. Safe Address - Street", "text", False),
    ("1F. Safe Alternate Address", "p1_16c_safe_apt_type", "16.c. Safe Address - Apt/Ste/Flr Type", "select", False),
    ("1F. Safe Alternate Address", "p1_16d_safe_apt_number", "16.d. Safe Address - Apt/Ste/Flr Number", "text", False),
    ("1F. Safe Alternate Address", "p1_16e_safe_city", "16.e. Safe Address - City or Town", "text", False),
    ("1F. Safe Alternate Address", "p1_16f_safe_state", "16.f. Safe Address - State", "select", False),
    ("1F. Safe Alternate Address", "p1_16g_safe_zip", "16.g. Safe Address - ZIP Code", "text", False),

    ("1G. Travel Documents", "p1_17_passport_number", "17. Passport Number", "text", False),
    ("1G. Travel Documents", "p1_18_travel_doc_number", "18. Travel Document Number (if different)", "text", False),
    ("1G. Travel Documents", "p1_19_passport_exp", "19. Passport/Travel Document Expiration Date", "date", False),
    ("1G. Travel Documents", "p1_20_passport_country", "20. Country That Issued Passport/Travel Document", "text", False),
    ("1G. Travel Documents", "p1_21_nonimmigrant_visa", "21. Nonimmigrant Visa Number (if any)", "text", False),

    ("1H. Last Arrival Information", "p1_22a_arrival_city", "22.a. City or Town of Last Arrival", "text", True),
    ("1H. Last Arrival Information", "p1_22b_arrival_state", "22.b. State of Last Arrival", "select", False),
    ("1H. Last Arrival Information", "p1_23_arrival_date", "23. Date of Last Arrival (mm/dd/yyyy)", "date", True),
    ("1H. Last Arrival Information", "p1_24a_inspected_admitted", "24.a. I was inspected and admitted", "checkbox", False),
    ("1H. Last Arrival Information", "p1_24b_inspected_paroled", "24.b. I was inspected and paroled", "checkbox", False),
    ("1H. Last Arrival Information", "p1_24c_without_inspection", "24.c. I arrived without admission or parole", "checkbox", False),
    ("1H. Last Arrival Information", "p1_24d_other", "24.d. Other (explain)", "checkbox", False),
    ("1H. Last Arrival Information", "p1_24d_other_explain", "24.d. If Other, explain", "text", False),

    ("1I. Current Immigration Status", "p1_25_i94_number", "25. I-94 Arrival-Departure Record Number", "text", False),
    ("1I. Current Immigration Status", "p1_26_status_expires", "26. Date Authorized Stay Expires (or D/S)", "text", False),
    ("1I. Current Immigration Status", "p1_27_status_on_i94", "27. Immigration Status on Form I-94", "text", False),
    ("1I. Current Immigration Status", "p1_28_current_status", "28. Current Immigration Status", "text", True),
    ("1I. Current Immigration Status", "p1_29a_name_i94_family", "29.a. Name on I-94 if different - Family Name", "text", False),
    ("1I. Current Immigration Status", "p1_29b_name_i94_given", "29.b. Name on I-94 if different - Given Name", "text", False),

    # =========================================================================
    # PART 2: APPLICATION TYPE AND FILING CATEGORY
    # =========================================================================
    ("2A. Application Type", "p2_1_eoir_proceeding", "1. Are you filing this application with the Immigration Court (EOIR)?", "radio", True),

    ("2B. Filing Category", "p2_2a_immigrant_petition", "2.a. Immigrant petition (I-130, I-140, I-360, I-526, etc.)", "checkbox", False),
    ("2B. Filing Category", "p2_2b_diversity_visa", "2.b. Diversity Visa lottery winner", "checkbox", False),
    ("2B. Filing Category", "p2_2c_asylee_adjustment", "2.c. Asylee (1 year after asylum granted)", "checkbox", False),
    ("2B. Filing Category", "p2_2d_refugee_adjustment", "2.d. Refugee", "checkbox", False),
    ("2B. Filing Category", "p2_2e_cuban_adjustment", "2.e. Cuban Adjustment Act", "checkbox", False),
    ("2B. Filing Category", "p2_2f_hrifa", "2.f. Haitian Refugee Immigration Fairness Act (HRIFA)", "checkbox", False),
    ("2B. Filing Category", "p2_2g_indochinese", "2.g. Indochinese Parole Adjustment Act", "checkbox", False),
    ("2B. Filing Category", "p2_2h_lulac", "2.h. Lulac (Cuban/Haitian Entrant)", "checkbox", False),
    ("2B. Filing Category", "p2_2i_registry", "2.i. Registry (continuous residence since 01/01/1972)", "checkbox", False),
    ("2B. Filing Category", "p2_2j_special_immigrant", "2.j. Special Immigrant (not religious worker)", "checkbox", False),
    ("2B. Filing Category", "p2_2k_religious_worker", "2.k. Special Immigrant Religious Worker", "checkbox", False),
    ("2B. Filing Category", "p2_2l_other", "2.l. Other basis for eligibility", "checkbox", False),
    ("2B. Filing Category", "p2_2l_other_explain", "2.l. If Other, explain basis", "text", False),

    ("2C. INA 245(i) Adjustment", "p2_3a_245i_before_apr2001", "3.a. Petition filed on or before April 30, 2001", "checkbox", False),
    ("2C. INA 245(i) Adjustment", "p2_3b_245i_before_jan1998", "3.b. Petition filed on or before January 14, 1998", "checkbox", False),
    ("2C. INA 245(i) Adjustment", "p2_3c_grandfathered", "3.c. Grandfathered (petition between 01/15/1998 - 04/30/2001)", "checkbox", False),
    ("2C. INA 245(i) Adjustment", "p2_3d_not_245i", "3.d. I am NOT subject to INA section 245(i)", "checkbox", False),

    ("2D. Approved Petition", "p2_4_petition_receipt", "4. Receipt Number of Approved Petition", "text", False),
    ("2D. Approved Petition", "p2_5_priority_date", "5. Priority Date (mm/dd/yyyy)", "date", False),
    ("2D. Approved Petition", "p2_6_principal_applicant", "6. Are you the principal applicant?", "radio", True),
    ("2D. Approved Petition", "p2_7a_principal_family", "7.a. Principal Applicant - Family Name", "text", False),
    ("2D. Approved Petition", "p2_7b_principal_given", "7.b. Principal Applicant - Given Name", "text", False),
    ("2D. Approved Petition", "p2_7c_principal_middle", "7.c. Principal Applicant - Middle Name", "text", False),
    ("2D. Approved Petition", "p2_8_principal_a_number", "8. Principal Applicant's A-Number", "text", False),
    ("2D. Approved Petition", "p2_9_principal_dob", "9. Principal Applicant's Date of Birth", "date", False),
    ("2D. Approved Petition", "p2_10_relationship", "10. Your Relationship to Principal Applicant", "select", False),

    # =========================================================================
    # PART 3: ADDITIONAL INFORMATION ABOUT YOU
    # =========================================================================
    ("3A. I-864 Exemption", "p3_1_claiming_exemption", "1. Are you claiming exemption from I-864 Affidavit of Support?", "radio", True),
    ("3A. I-864 Exemption", "p3_2_40_quarters", "2. I have earned or can be credited with 40 qualifying quarters", "checkbox", False),
    ("3A. I-864 Exemption", "p3_3_vawa", "3. VAWA self-petitioner and able to be self-supporting", "checkbox", False),
    ("3A. I-864 Exemption", "p3_4_widower", "4. Widow(er) of U.S. citizen", "checkbox", False),
    ("3A. I-864 Exemption", "p3_5_child_abuse", "5. Child who was abused, abandoned, or neglected", "checkbox", False),
    ("3A. I-864 Exemption", "p3_6_sij", "6. Special Immigrant Juvenile", "checkbox", False),
    ("3A. I-864 Exemption", "p3_7_other_exemption", "7. Other exemption basis", "checkbox", False),

    ("3B. Visa Application History", "p3_8_applied_immigrant_visa", "8. Have you ever applied for an immigrant visa at a U.S. Embassy or Consulate?", "radio", True),
    ("3B. Visa Application History", "p3_9_consulate_city", "9. City where you applied", "text", False),
    ("3B. Visa Application History", "p3_10_consulate_country", "10. Country where you applied", "text", False),
    ("3B. Visa Application History", "p3_11_visa_approved", "11. Was your visa approved?", "radio", False),
    ("3B. Visa Application History", "p3_12_visa_refused", "12. Was your visa refused/denied?", "radio", False),
    ("3B. Visa Application History", "p3_13_visa_withdrawn", "13. Was your application withdrawn?", "radio", False),

    # =========================================================================
    # PART 4: PHYSICAL ADDRESSES (Last 5 Years)
    # =========================================================================
    ("4A. Current Physical Address", "p4_1a_street", "1.a. Street Number and Name", "text", True),
    ("4A. Current Physical Address", "p4_1b_apt_type", "1.b. Apt/Ste/Flr Type", "select", False),
    ("4A. Current Physical Address", "p4_1c_apt_number", "1.c. Apt/Ste/Flr Number", "text", False),
    ("4A. Current Physical Address", "p4_1d_city", "1.d. City or Town", "text", True),
    ("4A. Current Physical Address", "p4_1e_state", "1.e. State", "select", False),
    ("4A. Current Physical Address", "p4_1f_zip", "1.f. ZIP Code", "text", False),
    ("4A. Current Physical Address", "p4_1g_province", "1.g. Province (if outside U.S.)", "text", False),
    ("4A. Current Physical Address", "p4_1h_postal", "1.h. Postal Code (if outside U.S.)", "text", False),
    ("4A. Current Physical Address", "p4_1i_country", "1.i. Country", "text", True),
    ("4A. Current Physical Address", "p4_2_from_date", "2. Date From (mm/dd/yyyy)", "date", True),
    ("4A. Current Physical Address", "p4_3_to_date", "3. Date To (mm/dd/yyyy or PRESENT)", "text", True),

    ("4B. Previous Address 1", "p4_4a_prev1_street", "4.a. Previous Address 1 - Street", "text", False),
    ("4B. Previous Address 1", "p4_4b_prev1_apt", "4.b. Previous Address 1 - Apt/Ste/Flr", "text", False),
    ("4B. Previous Address 1", "p4_4c_prev1_city", "4.c. Previous Address 1 - City", "text", False),
    ("4B. Previous Address 1", "p4_4d_prev1_state", "4.d. Previous Address 1 - State", "select", False),
    ("4B. Previous Address 1", "p4_4e_prev1_zip", "4.e. Previous Address 1 - ZIP Code", "text", False),
    ("4B. Previous Address 1", "p4_4f_prev1_province", "4.f. Previous Address 1 - Province", "text", False),
    ("4B. Previous Address 1", "p4_4g_prev1_country", "4.g. Previous Address 1 - Country", "text", False),
    ("4B. Previous Address 1", "p4_5_prev1_from", "5. Previous Address 1 - Date From", "date", False),
    ("4B. Previous Address 1", "p4_6_prev1_to", "6. Previous Address 1 - Date To", "date", False),

    ("4C. Previous Address 2", "p4_7a_prev2_street", "7.a. Previous Address 2 - Street", "text", False),
    ("4C. Previous Address 2", "p4_7b_prev2_apt", "7.b. Previous Address 2 - Apt/Ste/Flr", "text", False),
    ("4C. Previous Address 2", "p4_7c_prev2_city", "7.c. Previous Address 2 - City", "text", False),
    ("4C. Previous Address 2", "p4_7d_prev2_state", "7.d. Previous Address 2 - State", "select", False),
    ("4C. Previous Address 2", "p4_7e_prev2_country", "7.e. Previous Address 2 - Country", "text", False),
    ("4C. Previous Address 2", "p4_8_prev2_from", "8. Previous Address 2 - Date From", "date", False),
    ("4C. Previous Address 2", "p4_9_prev2_to", "9. Previous Address 2 - Date To", "date", False),

    ("4D. Previous Address 3", "p4_10a_prev3_street", "10.a. Previous Address 3 - Street", "text", False),
    ("4D. Previous Address 3", "p4_10b_prev3_city", "10.b. Previous Address 3 - City", "text", False),
    ("4D. Previous Address 3", "p4_10c_prev3_country", "10.c. Previous Address 3 - Country", "text", False),
    ("4D. Previous Address 3", "p4_11_prev3_from", "11. Previous Address 3 - Date From", "date", False),
    ("4D. Previous Address 3", "p4_12_prev3_to", "12. Previous Address 3 - Date To", "date", False),

    # =========================================================================
    # PART 4E-F: EMPLOYMENT (Last 5 Years)
    # =========================================================================
    ("4E. Current Employment", "p4_13_employer_name", "13. Employer or Company Name", "text", True),
    ("4E. Current Employment", "p4_14a_emp_street", "14.a. Employer Address - Street", "text", True),
    ("4E. Current Employment", "p4_14b_emp_apt", "14.b. Employer Address - Suite", "text", False),
    ("4E. Current Employment", "p4_14c_emp_city", "14.c. Employer Address - City", "text", True),
    ("4E. Current Employment", "p4_14d_emp_state", "14.d. Employer Address - State", "select", False),
    ("4E. Current Employment", "p4_14e_emp_zip", "14.e. Employer Address - ZIP Code", "text", False),
    ("4E. Current Employment", "p4_14f_emp_province", "14.f. Employer Address - Province", "text", False),
    ("4E. Current Employment", "p4_14g_emp_country", "14.g. Employer Address - Country", "text", True),
    ("4E. Current Employment", "p4_15_occupation", "15. Your Occupation", "text", True),
    ("4E. Current Employment", "p4_16_emp_from", "16. Date From (mm/dd/yyyy)", "date", True),
    ("4E. Current Employment", "p4_17_emp_to", "17. Date To (mm/dd/yyyy or PRESENT)", "text", True),

    ("4F. Previous Employment 1", "p4_18_prev_emp1_name", "18. Previous Employer 1 - Name", "text", False),
    ("4F. Previous Employment 1", "p4_19a_prev_emp1_street", "19.a. Previous Employer 1 - Street", "text", False),
    ("4F. Previous Employment 1", "p4_19b_prev_emp1_city", "19.b. Previous Employer 1 - City", "text", False),
    ("4F. Previous Employment 1", "p4_19c_prev_emp1_state", "19.c. Previous Employer 1 - State", "select", False),
    ("4F. Previous Employment 1", "p4_19d_prev_emp1_country", "19.d. Previous Employer 1 - Country", "text", False),
    ("4F. Previous Employment 1", "p4_20_prev_emp1_occupation", "20. Previous Employer 1 - Occupation", "text", False),
    ("4F. Previous Employment 1", "p4_21_prev_emp1_from", "21. Previous Employment 1 - Date From", "date", False),
    ("4F. Previous Employment 1", "p4_22_prev_emp1_to", "22. Previous Employment 1 - Date To", "date", False),

    ("4G. Previous Employment 2", "p4_23_prev_emp2_name", "23. Previous Employer 2 - Name", "text", False),
    ("4G. Previous Employment 2", "p4_24_prev_emp2_city", "24. Previous Employer 2 - City", "text", False),
    ("4G. Previous Employment 2", "p4_25_prev_emp2_country", "25. Previous Employer 2 - Country", "text", False),
    ("4G. Previous Employment 2", "p4_26_prev_emp2_occupation", "26. Previous Employer 2 - Occupation", "text", False),
    ("4G. Previous Employment 2", "p4_27_prev_emp2_from", "27. Previous Employment 2 - Date From", "date", False),
    ("4G. Previous Employment 2", "p4_28_prev_emp2_to", "28. Previous Employment 2 - Date To", "date", False),

    # =========================================================================
    # PART 5: INFORMATION ABOUT YOUR PARENTS
    # =========================================================================
    ("5A. Parent 1 (Mother/Father)", "p5_1a_parent1_family", "1.a. Parent 1 - Family Name", "text", True),
    ("5A. Parent 1 (Mother/Father)", "p5_1b_parent1_given", "1.b. Parent 1 - Given Name", "text", True),
    ("5A. Parent 1 (Mother/Father)", "p5_1c_parent1_middle", "1.c. Parent 1 - Middle Name", "text", False),
    ("5A. Parent 1 (Mother/Father)", "p5_2_parent1_dob", "2. Parent 1 - Date of Birth", "date", True),
    ("5A. Parent 1 (Mother/Father)", "p5_3_parent1_sex", "3. Parent 1 - Sex", "select", True),
    ("5A. Parent 1 (Mother/Father)", "p5_4_parent1_city_birth", "4. Parent 1 - City/Town of Birth", "text", True),
    ("5A. Parent 1 (Mother/Father)", "p5_5_parent1_country_birth", "5. Parent 1 - Country of Birth", "text", True),
    ("5A. Parent 1 (Mother/Father)", "p5_6_parent1_city_residence", "6. Parent 1 - Current City of Residence", "text", False),
    ("5A. Parent 1 (Mother/Father)", "p5_7_parent1_country_residence", "7. Parent 1 - Current Country of Residence", "text", False),

    ("5B. Parent 2 (Mother/Father)", "p5_8a_parent2_family", "8.a. Parent 2 - Family Name", "text", True),
    ("5B. Parent 2 (Mother/Father)", "p5_8b_parent2_given", "8.b. Parent 2 - Given Name", "text", True),
    ("5B. Parent 2 (Mother/Father)", "p5_8c_parent2_middle", "8.c. Parent 2 - Middle Name", "text", False),
    ("5B. Parent 2 (Mother/Father)", "p5_9_parent2_dob", "9. Parent 2 - Date of Birth", "date", True),
    ("5B. Parent 2 (Mother/Father)", "p5_10_parent2_sex", "10. Parent 2 - Sex", "select", True),
    ("5B. Parent 2 (Mother/Father)", "p5_11_parent2_city_birth", "11. Parent 2 - City/Town of Birth", "text", True),
    ("5B. Parent 2 (Mother/Father)", "p5_12_parent2_country_birth", "12. Parent 2 - Country of Birth", "text", True),
    ("5B. Parent 2 (Mother/Father)", "p5_13_parent2_city_residence", "13. Parent 2 - Current City of Residence", "text", False),
    ("5B. Parent 2 (Mother/Father)", "p5_14_parent2_country_residence", "14. Parent 2 - Current Country of Residence", "text", False),

    # =========================================================================
    # PART 6: MARITAL HISTORY
    # =========================================================================
    ("6A. Your Marital Status", "p6_1_marital_status", "1. Current Marital Status", "select", True),
    ("6A. Your Marital Status", "p6_2_times_married", "2. How many times have you been married?", "number", True),

    ("6B. Current Spouse Information", "p6_3a_spouse_family", "3.a. Current Spouse - Family Name", "text", False),
    ("6B. Current Spouse Information", "p6_3b_spouse_given", "3.b. Current Spouse - Given Name", "text", False),
    ("6B. Current Spouse Information", "p6_3c_spouse_middle", "3.c. Current Spouse - Middle Name", "text", False),
    ("6B. Current Spouse Information", "p6_4_spouse_a_number", "4. Spouse's A-Number (if any)", "text", False),
    ("6B. Current Spouse Information", "p6_5_spouse_dob", "5. Spouse's Date of Birth", "date", False),
    ("6B. Current Spouse Information", "p6_6_spouse_country_birth", "6. Spouse's Country of Birth", "text", False),
    ("6B. Current Spouse Information", "p6_7_spouse_citizenship", "7. Spouse's Country of Citizenship", "text", False),
    ("6B. Current Spouse Information", "p6_8_marriage_date", "8. Date of Marriage (mm/dd/yyyy)", "date", False),
    ("6B. Current Spouse Information", "p6_9a_marriage_city", "9.a. Place of Marriage - City/Town", "text", False),
    ("6B. Current Spouse Information", "p6_9b_marriage_state", "9.b. Place of Marriage - State", "select", False),
    ("6B. Current Spouse Information", "p6_9c_marriage_country", "9.c. Place of Marriage - Country", "text", False),
    ("6B. Current Spouse Information", "p6_10_spouse_in_us", "10. Is your spouse currently in the United States?", "radio", False),
    ("6B. Current Spouse Information", "p6_11_spouse_applying_together", "11. Is your spouse applying for adjustment with you?", "radio", False),

    ("6C. Prior Spouse 1", "p6_12a_prior1_family", "12.a. Prior Spouse 1 - Family Name", "text", False),
    ("6C. Prior Spouse 1", "p6_12b_prior1_given", "12.b. Prior Spouse 1 - Given Name", "text", False),
    ("6C. Prior Spouse 1", "p6_13_prior1_dob", "13. Prior Spouse 1 - Date of Birth", "date", False),
    ("6C. Prior Spouse 1", "p6_14_prior1_marriage_date", "14. Date of Marriage to Prior Spouse 1", "date", False),
    ("6C. Prior Spouse 1", "p6_15_prior1_marriage_city", "15. City of Marriage to Prior Spouse 1", "text", False),
    ("6C. Prior Spouse 1", "p6_16_prior1_marriage_end", "16. Date Marriage to Prior Spouse 1 Ended", "date", False),
    ("6C. Prior Spouse 1", "p6_17a_prior1_divorce", "17.a. Marriage ended by Divorce", "checkbox", False),
    ("6C. Prior Spouse 1", "p6_17b_prior1_widowed", "17.b. Marriage ended - Widowed", "checkbox", False),
    ("6C. Prior Spouse 1", "p6_17c_prior1_annulled", "17.c. Marriage ended by Annulment", "checkbox", False),
    ("6C. Prior Spouse 1", "p6_17d_prior1_other", "17.d. Marriage ended - Other", "checkbox", False),

    ("6D. Prior Spouse 2", "p6_18a_prior2_family", "18.a. Prior Spouse 2 - Family Name", "text", False),
    ("6D. Prior Spouse 2", "p6_18b_prior2_given", "18.b. Prior Spouse 2 - Given Name", "text", False),
    ("6D. Prior Spouse 2", "p6_19_prior2_dob", "19. Prior Spouse 2 - Date of Birth", "date", False),
    ("6D. Prior Spouse 2", "p6_20_prior2_marriage_date", "20. Date of Marriage to Prior Spouse 2", "date", False),
    ("6D. Prior Spouse 2", "p6_21_prior2_marriage_end", "21. Date Marriage to Prior Spouse 2 Ended", "date", False),

    # =========================================================================
    # PART 7: INFORMATION ABOUT YOUR CHILDREN
    # =========================================================================
    ("7A. Children Summary", "p7_1_total_children", "1. Total Number of Children (include all)", "number", True),

    ("7B. Child 1", "p7_2a_child1_family", "2.a. Child 1 - Family Name", "text", False),
    ("7B. Child 1", "p7_2b_child1_given", "2.b. Child 1 - Given Name", "text", False),
    ("7B. Child 1", "p7_2c_child1_middle", "2.c. Child 1 - Middle Name", "text", False),
    ("7B. Child 1", "p7_3_child1_a_number", "3. Child 1 - A-Number (if any)", "text", False),
    ("7B. Child 1", "p7_4_child1_dob", "4. Child 1 - Date of Birth", "date", False),
    ("7B. Child 1", "p7_5_child1_country_birth", "5. Child 1 - Country of Birth", "text", False),
    ("7B. Child 1", "p7_6_child1_in_us", "6. Is Child 1 currently in the U.S.?", "radio", False),
    ("7B. Child 1", "p7_7_child1_applying", "7. Is Child 1 applying for adjustment with you?", "radio", False),

    ("7C. Child 2", "p7_8a_child2_family", "8.a. Child 2 - Family Name", "text", False),
    ("7C. Child 2", "p7_8b_child2_given", "8.b. Child 2 - Given Name", "text", False),
    ("7C. Child 2", "p7_9_child2_a_number", "9. Child 2 - A-Number (if any)", "text", False),
    ("7C. Child 2", "p7_10_child2_dob", "10. Child 2 - Date of Birth", "date", False),
    ("7C. Child 2", "p7_11_child2_country", "11. Child 2 - Country of Birth", "text", False),
    ("7C. Child 2", "p7_12_child2_in_us", "12. Is Child 2 currently in the U.S.?", "radio", False),
    ("7C. Child 2", "p7_13_child2_applying", "13. Is Child 2 applying for adjustment with you?", "radio", False),

    ("7D. Child 3", "p7_14a_child3_family", "14.a. Child 3 - Family Name", "text", False),
    ("7D. Child 3", "p7_14b_child3_given", "14.b. Child 3 - Given Name", "text", False),
    ("7D. Child 3", "p7_15_child3_dob", "15. Child 3 - Date of Birth", "date", False),
    ("7D. Child 3", "p7_16_child3_country", "16. Child 3 - Country of Birth", "text", False),
    ("7D. Child 3", "p7_17_child3_in_us", "17. Is Child 3 currently in the U.S.?", "radio", False),

    ("7E. Child 4", "p7_18a_child4_family", "18.a. Child 4 - Family Name", "text", False),
    ("7E. Child 4", "p7_18b_child4_given", "18.b. Child 4 - Given Name", "text", False),
    ("7E. Child 4", "p7_19_child4_dob", "19. Child 4 - Date of Birth", "date", False),
    ("7E. Child 4", "p7_20_child4_country", "20. Child 4 - Country of Birth", "text", False),

    # =========================================================================
    # PART 8: BIOGRAPHIC INFORMATION
    # =========================================================================
    ("8A. Ethnicity", "p8_1_ethnicity", "1. Ethnicity - Are you Hispanic or Latino?", "radio", True),

    ("8B. Race (select all that apply)", "p8_2a_race_white", "2.a. White", "checkbox", False),
    ("8B. Race (select all that apply)", "p8_2b_race_asian", "2.b. Asian", "checkbox", False),
    ("8B. Race (select all that apply)", "p8_2c_race_black", "2.c. Black or African American", "checkbox", False),
    ("8B. Race (select all that apply)", "p8_2d_race_native", "2.d. American Indian or Alaska Native", "checkbox", False),
    ("8B. Race (select all that apply)", "p8_2e_race_pacific", "2.e. Native Hawaiian or Other Pacific Islander", "checkbox", False),

    ("8C. Physical Description", "p8_3a_height_feet", "3.a. Height - Feet", "number", True),
    ("8C. Physical Description", "p8_3b_height_inches", "3.b. Height - Inches", "number", True),
    ("8C. Physical Description", "p8_4_weight_lbs", "4. Weight (in pounds)", "number", True),
    ("8C. Physical Description", "p8_5_eye_color", "5. Eye Color", "select", True),
    ("8C. Physical Description", "p8_6_hair_color", "6. Hair Color", "select", True),

    # =========================================================================
    # PART 9: GENERAL ELIGIBILITY AND INADMISSIBILITY GROUNDS
    # This is the largest section with 80+ questions
    # =========================================================================

    # SECTION A: ORGANIZATIONS AND MEMBERSHIPS
    ("9A. Organizations", "p9_1_member_org", "1. Have you EVER been a member of, involved in, or in any way associated with any organization, association, fund, foundation, party, club, society, or similar group?", "radio", True),
    ("9A. Organizations", "p9_2a_org1_name", "2.a. Organization 1 - Name", "text", False),
    ("9A. Organizations", "p9_2b_org1_city", "2.b. Organization 1 - City/Town", "text", False),
    ("9A. Organizations", "p9_2c_org1_state", "2.c. Organization 1 - State", "text", False),
    ("9A. Organizations", "p9_2d_org1_country", "2.d. Organization 1 - Country", "text", False),
    ("9A. Organizations", "p9_2e_org1_nature", "2.e. Organization 1 - Nature/Purpose", "text", False),
    ("9A. Organizations", "p9_2f_org1_from", "2.f. Organization 1 - Date From", "date", False),
    ("9A. Organizations", "p9_2g_org1_to", "2.g. Organization 1 - Date To", "date", False),

    ("9A. Organizations", "p9_3a_org2_name", "3.a. Organization 2 - Name", "text", False),
    ("9A. Organizations", "p9_3b_org2_country", "3.b. Organization 2 - Country", "text", False),
    ("9A. Organizations", "p9_3c_org2_nature", "3.c. Organization 2 - Nature/Purpose", "text", False),

    ("9B. Communist/Totalitarian Party", "p9_4_communist_totalitarian", "4. Have you EVER been a member of, or in any way affiliated with, the Communist Party or any other totalitarian party?", "radio", True),
    ("9B. Communist/Totalitarian Party", "p9_5_nazi_government", "5. Have you EVER been a member of, or in any way affiliated with, a Nazi government, Nazi political party, or any paramilitary unit associated with the Nazi government?", "radio", True),

    # SECTION B: MILITARY SERVICE
    ("9C. Military Service", "p9_6_military_service", "6. Have you EVER served in, been a member of, assisted, or participated in any military unit, paramilitary unit, police unit, self-defense unit, vigilante unit, rebel group, guerrilla group, militia, insurgent organization, or any other armed group?", "radio", True),
    ("9C. Military Service", "p9_7a_mil1_name", "7.a. Military Unit 1 - Name", "text", False),
    ("9C. Military Service", "p9_7b_mil1_country", "7.b. Military Unit 1 - Country", "text", False),
    ("9C. Military Service", "p9_7c_mil1_nature", "7.c. Military Unit 1 - Type of Organization", "text", False),
    ("9C. Military Service", "p9_7d_mil1_rank", "7.d. Military Unit 1 - Your Rank/Position", "text", False),
    ("9C. Military Service", "p9_7e_mil1_from", "7.e. Military Unit 1 - Date From", "date", False),
    ("9C. Military Service", "p9_7f_mil1_to", "7.f. Military Unit 1 - Date To", "date", False),

    ("9D. Weapons Training", "p9_8_weapons_training", "8. Have you EVER received any type of military, paramilitary, or weapons training?", "radio", True),
    ("9D. Weapons Training", "p9_9_weapons_explain", "9. If yes, explain type of training", "textarea", False),

    # SECTION C: IMMIGRATION VIOLATIONS
    ("9E. Immigration Violations", "p9_10_worked_unauthorized", "10. Have you EVER worked in the United States without authorization?", "radio", True),
    ("9E. Immigration Violations", "p9_11_violated_status", "11. Have you EVER violated the terms or conditions of your nonimmigrant status?", "radio", True),
    ("9E. Immigration Violations", "p9_12_immigration_fraud", "12. Have you EVER, by fraud or willful misrepresentation, sought to procure, or procured, a visa, other documentation, entry into the United States, or any other immigration benefit?", "radio", True),
    ("9E. Immigration Violations", "p9_13_falsely_claimed_citizen", "13. Have you EVER falsely claimed to be a U.S. citizen (in writing or any other way)?", "radio", True),
    ("9E. Immigration Violations", "p9_14_stowaway", "14. Have you EVER been a stowaway on a vessel or aircraft arriving in the United States?", "radio", True),
    ("9E. Immigration Violations", "p9_15_alien_smuggling", "15. Have you EVER knowingly encouraged, induced, assisted, abetted, or aided any alien to enter or try to enter the United States illegally?", "radio", True),
    ("9E. Immigration Violations", "p9_16_document_fraud", "16. Have you EVER submitted fraudulent documentation to the U.S. Government to obtain an immigration benefit?", "radio", True),

    # SECTION D: PREVIOUS IMMIGRATION PROCEEDINGS
    ("9F. Immigration Proceedings", "p9_17_removed_deported", "17. Have you EVER been removed, deported, or excluded from the United States?", "radio", True),
    ("9F. Immigration Proceedings", "p9_18_ordered_removed", "18. Have you EVER been ordered removed, deported, or excluded from the United States?", "radio", True),
    ("9F. Immigration Proceedings", "p9_19_voluntary_departure", "19. Have you EVER received or applied for voluntary departure from the United States?", "radio", True),
    ("9F. Immigration Proceedings", "p9_20_denied_visa", "20. Have you EVER been denied a visa to the United States?", "radio", True),
    ("9F. Immigration Proceedings", "p9_21_denied_admission", "21. Have you EVER been denied admission to the United States at a port of entry?", "radio", True),
    ("9F. Immigration Proceedings", "p9_22_denied_i485", "22. Have you EVER applied for adjustment of status to permanent resident (I-485) and been denied?", "radio", True),
    ("9F. Immigration Proceedings", "p9_23_in_proceedings", "23. Are you currently in removal, deportation, rescission, or exclusion proceedings?", "radio", True),
    ("9F. Immigration Proceedings", "p9_24_final_order", "24. Have you EVER had a final order of removal, deportation, or exclusion issued against you?", "radio", True),

    # SECTION E: CRIMINAL HISTORY - ARRESTS
    ("9G. Criminal - Arrests", "p9_25_arrested", "25. Have you EVER been arrested, cited, charged, or detained for any reason by any law enforcement official (including but not limited to any immigration official or any official of the U.S. armed forces or coast guard)?", "radio", True),
    ("9G. Criminal - Arrests", "p9_26_not_charged", "26. Have you EVER been arrested, cited, charged, or detained for any reason by any law enforcement official but NOT charged?", "radio", True),
    ("9G. Criminal - Arrests", "p9_27a_arrest1_date", "27.a. Arrest 1 - Date", "date", False),
    ("9G. Criminal - Arrests", "p9_27b_arrest1_location", "27.b. Arrest 1 - City, State/Province, Country", "text", False),
    ("9G. Criminal - Arrests", "p9_27c_arrest1_charges", "27.c. Arrest 1 - Charges/Reason", "text", False),
    ("9G. Criminal - Arrests", "p9_27d_arrest1_outcome", "27.d. Arrest 1 - Outcome/Disposition", "text", False),

    # SECTION F: CRIMINAL HISTORY - CONVICTIONS
    ("9H. Criminal - Convictions", "p9_28_convicted", "28. Have you EVER been convicted of, or pled guilty or nolo contendere to, any crime or offense (even if the violation was subsequently expunged, pardoned, or the conviction was set aside)?", "radio", True),
    ("9H. Criminal - Convictions", "p9_29_admitted_crime", "29. Have you EVER admitted committing any crime or offense for which you were not arrested?", "radio", True),
    ("9H. Criminal - Convictions", "p9_30_crime_moral_turpitude", "30. Have you EVER committed a crime involving moral turpitude (CIMT)?", "radio", True),
    ("9H. Criminal - Convictions", "p9_31_controlled_substance", "31. Have you EVER violated or conspired to violate any law or regulation relating to controlled substances (drugs)?", "radio", True),
    ("9H. Criminal - Convictions", "p9_32_drug_trafficker", "32. Have you EVER been a drug trafficker or assisted anyone in drug trafficking?", "radio", True),
    ("9H. Criminal - Convictions", "p9_33_drug_abuser", "33. Have you EVER been a drug abuser or addict?", "radio", True),
    ("9H. Criminal - Convictions", "p9_34_multiple_convictions", "34. Have you been convicted of 2 or more offenses for which the aggregate sentence was 5 years or more?", "radio", True),
    ("9H. Criminal - Convictions", "p9_35_prostitution", "35. Have you EVER engaged in prostitution, procured anyone for prostitution, or received proceeds from prostitution?", "radio", True),
    ("9H. Criminal - Convictions", "p9_36_commercialized_vice", "36. Have you EVER engaged in commercialized vice?", "radio", True),
    ("9H. Criminal - Convictions", "p9_37_human_trafficking", "37. Have you EVER been involved in human trafficking?", "radio", True),
    ("9H. Criminal - Convictions", "p9_38_money_laundering", "38. Have you EVER been involved in money laundering?", "radio", True),

    # SECTION G: CRIMINAL HISTORY - SPECIAL CRIMES
    ("9I. Criminal - Special", "p9_39_domestic_violence", "39. Have you EVER been convicted of, or pled guilty to, domestic violence, stalking, child abuse, child neglect, or child abandonment?", "radio", True),
    ("9I. Criminal - Special", "p9_40_restraining_order", "40. Have you EVER violated a protective order issued against you?", "radio", True),
    ("9I. Criminal - Special", "p9_41_juvenile_court", "41. Have you EVER been tried as an adult and convicted, or did you plead guilty, in juvenile court?", "radio", True),

    # SECTION H: NATIONAL SECURITY
    ("9J. National Security", "p9_42_espionage", "42. Have you EVER engaged in, conspired to engage in, or attempted to engage in espionage?", "radio", True),
    ("9J. National Security", "p9_43_sabotage", "43. Have you EVER engaged in, conspired to engage in, or attempted to engage in sabotage?", "radio", True),
    ("9J. National Security", "p9_44_overthrow_govt", "44. Have you EVER engaged in, conspired to engage in, or attempted to engage in any activity to overthrow the U.S. Government by force, violence, or other unlawful means?", "radio", True),
    ("9J. National Security", "p9_45_terrorist_activity", "45. Have you EVER engaged in, or do you intend to engage in, terrorist activity?", "radio", True),
    ("9J. National Security", "p9_46_terrorist_member", "46. Have you EVER been a member of, or in any way affiliated with, a terrorist organization?", "radio", True),
    ("9J. National Security", "p9_47_terrorist_support", "47. Have you EVER provided material support to any individual or organization that has engaged in terrorist activity?", "radio", True),
    ("9J. National Security", "p9_48_terrorist_training", "48. Have you EVER received military-type training from a terrorist organization?", "radio", True),

    # SECTION I: PERSECUTION AND GENOCIDE
    ("9K. Persecution", "p9_49_genocide", "49. Have you EVER ordered, incited, assisted, or otherwise participated in genocide?", "radio", True),
    ("9K. Persecution", "p9_50_torture", "50. Have you EVER ordered, incited, assisted, or otherwise participated in torture?", "radio", True),
    ("9K. Persecution", "p9_51_extrajudicial_killing", "51. Have you EVER ordered, incited, assisted, or otherwise participated in extrajudicial killings, political killings, or other acts of violence?", "radio", True),
    ("9K. Persecution", "p9_52_severe_violations", "52. Have you EVER engaged in particularly severe violations of religious freedom?", "radio", True),
    ("9K. Persecution", "p9_53_persecution", "53. Have you EVER persecuted any person or group because of race, religion, national origin, membership in a particular social group, or political opinion?", "radio", True),
    ("9K. Persecution", "p9_54_nazi_persecution", "54. Have you EVER participated in Nazi persecutions or genocide?", "radio", True),
    ("9K. Persecution", "p9_55_child_soldiers", "55. Have you EVER recruited or used child soldiers?", "radio", True),

    # SECTION J: PUBLIC CHARGE
    ("9L. Public Charge", "p9_56_public_benefits", "56. Are you likely at any time to become a public charge?", "radio", True),
    ("9L. Public Charge", "p9_57_received_benefits", "57. Have you EVER received public benefits in the United States?", "radio", False),
    ("9L. Public Charge", "p9_58_benefit_type", "58. If yes, type of public benefit(s) received", "text", False),

    # SECTION K: HEALTH-RELATED
    ("9M. Health", "p9_59_communicable_disease", "59. Do you have a communicable disease of public health significance?", "radio", True),
    ("9M. Health", "p9_60_physical_mental_disorder", "60. Do you have a physical or mental disorder that poses a threat to the safety of yourself or others?", "radio", True),
    ("9M. Health", "p9_61_drug_abuser", "61. Are you a drug abuser or drug addict?", "radio", True),

    # SECTION L: VOTING AND CITIZENSHIP
    ("9N. Voting", "p9_62_voted_illegally", "62. Have you EVER voted in violation of any Federal, State, or local constitutional provision, statute, ordinance, or regulation in the United States?", "radio", True),
    ("9N. Voting", "p9_63_renounced_citizenship", "63. Have you EVER renounced U.S. citizenship to avoid taxation?", "radio", True),

    # SECTION M: UNLAWFUL PRESENCE
    ("9O. Unlawful Presence", "p9_64_unlawful_180_days", "64. Have you EVER been unlawfully present in the United States for 180 days or more after your 18th birthday?", "radio", True),
    ("9O. Unlawful Presence", "p9_65_unlawful_1_year", "65. Have you EVER been unlawfully present in the United States for 1 year or more in the aggregate after your 18th birthday?", "radio", True),
    ("9O. Unlawful Presence", "p9_66_reenter_after_removal", "66. Have you EVER been unlawfully present in the U.S. for an aggregate of more than 1 year, then departed and sought to re-enter?", "radio", True),

    # SECTION N: ADDITIONAL GROUNDS
    ("9P. Additional Grounds", "p9_67_polygamy", "67. Do you intend to practice polygamy in the United States?", "radio", True),
    ("9P. Additional Grounds", "p9_68_guardian_custody", "68. Are you accompanying another alien who requires your protection or guardianship, but who is inadmissible?", "radio", True),
    ("9P. Additional Grounds", "p9_69_unlawful_voters", "69. Are you coming to the United States primarily for the purpose of engaging in unlawful gambling, prostitution, or other illicit activities?", "radio", True),
    ("9P. Additional Grounds", "p9_70_export_violations", "70. Have you EVER engaged in or do you intend to engage in export control violations?", "radio", True),
    ("9P. Additional Grounds", "p9_71_other_unlawful", "71. Have you EVER engaged in or do you intend to engage in any other unlawful activity?", "radio", True),

    # SECTION O: SELECTIVE SERVICE
    ("9Q. Selective Service", "p9_72_male_18_26", "72. Are you a male who lived in the U.S. between ages 18-26?", "radio", True),
    ("9Q. Selective Service", "p9_73_registered_selective", "73. If yes, did you register with the Selective Service System?", "radio", False),
    ("9Q. Selective Service", "p9_74_selective_number", "74. If registered, Selective Service Number", "text", False),

    # =========================================================================
    # PART 10: ACCOMMODATIONS FOR INDIVIDUALS WITH DISABILITIES
    # =========================================================================
    ("10A. Disability Accommodations", "p10_1_requesting", "1. Are you requesting an accommodation because of your disability?", "radio", True),
    ("10A. Disability Accommodations", "p10_2a_deaf", "2.a. I am deaf or hard of hearing and need a sign language interpreter", "checkbox", False),
    ("10A. Disability Accommodations", "p10_2b_blind", "2.b. I am blind or have low vision", "checkbox", False),
    ("10A. Disability Accommodations", "p10_2c_other", "2.c. I have another type of disability (explain)", "checkbox", False),
    ("10A. Disability Accommodations", "p10_3_explain", "3. If other disability, explain accommodation needed", "textarea", False),

    # =========================================================================
    # PART 11: APPLICANT'S STATEMENT, CONTACT, AND SIGNATURE
    # =========================================================================
    ("11A. Applicant Statement", "p11_1a_can_read", "1.a. I can read and understand English, and I have read this application", "checkbox", False),
    ("11A. Applicant Statement", "p11_1b_interpreter_read", "1.b. The interpreter named in Part 12 read to me every question and instruction in my language", "checkbox", False),
    ("11A. Applicant Statement", "p11_2_preparer_assisted", "2. At my request, the preparer named in Part 13 prepared this application for me", "checkbox", False),

    ("11B. Contact Information", "p11_3_daytime_phone", "3. Applicant's Daytime Telephone Number", "phone", True),
    ("11B. Contact Information", "p11_4_mobile_phone", "4. Applicant's Mobile Telephone Number", "phone", False),
    ("11B. Contact Information", "p11_5_email", "5. Applicant's Email Address", "email", False),

    ("11C. Signature", "p11_6_signature_date", "6. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 12: INTERPRETER'S CONTACT INFORMATION AND SIGNATURE
    # =========================================================================
    ("12A. Interpreter Information", "p12_1a_interp_family", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("12A. Interpreter Information", "p12_1b_interp_given", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("12A. Interpreter Information", "p12_2_interp_org", "2. Interpreter's Business or Organization Name", "text", False),
    ("12A. Interpreter Information", "p12_3a_interp_street", "3.a. Interpreter's Address - Street", "text", False),
    ("12A. Interpreter Information", "p12_3b_interp_apt", "3.b. Interpreter's Address - Apt/Ste/Flr", "text", False),
    ("12A. Interpreter Information", "p12_3c_interp_city", "3.c. Interpreter's Address - City", "text", False),
    ("12A. Interpreter Information", "p12_3d_interp_state", "3.d. Interpreter's Address - State", "select", False),
    ("12A. Interpreter Information", "p12_3e_interp_zip", "3.e. Interpreter's Address - ZIP Code", "text", False),
    ("12A. Interpreter Information", "p12_3f_interp_country", "3.f. Interpreter's Address - Country", "text", False),
    ("12B. Interpreter Contact", "p12_4_interp_phone", "4. Interpreter's Daytime Telephone Number", "phone", False),
    ("12B. Interpreter Contact", "p12_5_interp_mobile", "5. Interpreter's Mobile Telephone Number", "phone", False),
    ("12B. Interpreter Contact", "p12_6_interp_email", "6. Interpreter's Email Address", "email", False),
    ("12C. Interpreter Certification", "p12_7_language", "7. Language Interpreted", "text", False),
    ("12C. Interpreter Certification", "p12_8_signature_date", "8. Interpreter's Signature Date", "date", False),

    # =========================================================================
    # PART 13: PREPARER'S CONTACT INFORMATION AND SIGNATURE
    # =========================================================================
    ("13A. Preparer Information", "p13_1a_prep_not_attorney", "1.a. I am NOT an attorney or accredited representative", "checkbox", False),
    ("13A. Preparer Information", "p13_1b_prep_is_attorney", "1.b. I AM an attorney or accredited representative", "checkbox", False),
    ("13A. Preparer Information", "p13_2a_prep_family", "2.a. Preparer's Family Name (Last Name)", "text", False),
    ("13A. Preparer Information", "p13_2b_prep_given", "2.b. Preparer's Given Name (First Name)", "text", False),
    ("13A. Preparer Information", "p13_3_prep_org", "3. Preparer's Business or Organization Name", "text", False),
    ("13B. Preparer Address", "p13_4a_prep_street", "4.a. Preparer's Address - Street", "text", False),
    ("13B. Preparer Address", "p13_4b_prep_apt", "4.b. Preparer's Address - Apt/Ste/Flr", "text", False),
    ("13B. Preparer Address", "p13_4c_prep_city", "4.c. Preparer's Address - City", "text", False),
    ("13B. Preparer Address", "p13_4d_prep_state", "4.d. Preparer's Address - State", "select", False),
    ("13B. Preparer Address", "p13_4e_prep_zip", "4.e. Preparer's Address - ZIP Code", "text", False),
    ("13B. Preparer Address", "p13_4f_prep_country", "4.f. Preparer's Address - Country", "text", False),
    ("13C. Preparer Contact", "p13_5_prep_phone", "5. Preparer's Daytime Telephone Number", "phone", False),
    ("13C. Preparer Contact", "p13_6_prep_mobile", "6. Preparer's Mobile Telephone Number", "phone", False),
    ("13C. Preparer Contact", "p13_7_prep_email", "7. Preparer's Email Address", "email", False),
    ("13D. Preparer Certification", "p13_8_prep_extends", "8. Does your representation extend beyond this case?", "radio", False),
    ("13D. Preparer Certification", "p13_9_signature_date", "9. Preparer's Signature Date", "date", False),

    # =========================================================================
    # PART 14: ADDITIONAL INFORMATION
    # =========================================================================
    ("14. Additional Information", "p14_1a_page", "1.a. Page Number", "text", False),
    ("14. Additional Information", "p14_1b_part", "1.b. Part Number", "text", False),
    ("14. Additional Information", "p14_1c_item", "1.c. Item Number", "text", False),
    ("14. Additional Information", "p14_1d_info", "1.d. Additional Information", "textarea", False),
    ("14. Additional Information", "p14_2a_page", "2.a. Page Number", "text", False),
    ("14. Additional Information", "p14_2b_part", "2.b. Part Number", "text", False),
    ("14. Additional Information", "p14_2c_item", "2.c. Item Number", "text", False),
    ("14. Additional Information", "p14_2d_info", "2.d. Additional Information", "textarea", False),
    ("14. Additional Information", "p14_3a_page", "3.a. Page Number", "text", False),
    ("14. Additional Information", "p14_3b_part", "3.b. Part Number", "text", False),
    ("14. Additional Information", "p14_3c_item", "3.c. Item Number", "text", False),
    ("14. Additional Information", "p14_3d_info", "3.d. Additional Information", "textarea", False),
    ("14. Additional Information", "p14_4_info", "4. Additional Information (continue)", "textarea", False),
    ("14. Additional Information", "p14_5_info", "5. Additional Information (continue)", "textarea", False),
]

def update_i485():
    """Update I-485 with all fields including options for select/radio fields."""
    template_id = 40  # I-485 template ID

    with engine.connect() as conn:
        # Delete existing fields
        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        # Insert all fields
        for i, field in enumerate(I485_FIELDS):
            section, field_name, label, field_type, required = field
            # Get options from the options map if available
            options = I485_OPTIONS_MAP.get(field_name, None)
            options_json = json.dumps(options) if options else None

            conn.execute(text("""
                INSERT INTO questionnaire_fields
                (template_id, field_name, label, field_type, is_required, section, "order", options)
                VALUES (:tid, :fname, :label, :ftype, :req, :section, :ord, :options)
            """), {
                'tid': template_id,
                'fname': field_name,
                'label': label,
                'ftype': field_type,
                'req': required,
                'section': section,
                'ord': i + 1,
                'options': options_json
            })

        conn.commit()
        print(f"I-485 updated: {len(I485_FIELDS)} fields with options")

if __name__ == "__main__":
    update_i485()
