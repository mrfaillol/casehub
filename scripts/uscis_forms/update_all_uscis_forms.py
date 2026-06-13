#!/usr/bin/env python3
"""
Update ALL USCIS forms with complete fields and English sections.
ALL CONTENT MUST BE IN ENGLISH - NEVER PORTUGUESE.
"""
from sqlalchemy import create_engine, text
from config import settings

engine = create_engine(settings.DATABASE_URL)

# =============================================================================
# I-485 - APPLICATION TO REGISTER PERMANENT RESIDENCE (24 pages, ~300 fields)
# =============================================================================
I485_FIELDS = [
    # PART 1A: PERSONAL INFORMATION
    ("1A. Personal Information", "p1_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("1A. Personal Information", "p1_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("1A. Personal Information", "p1_1c_middle_name", "1.c. Middle Name", "text", False),
    ("1A. Personal Information", "p1_5_dob", "5. Date of Birth (mm/dd/yyyy)", "date", True),
    ("1A. Personal Information", "p1_6_sex", "6. Sex/Gender", "select", True),
    ("1A. Personal Information", "p1_7_city_birth", "7. City or Town of Birth", "text", True),
    ("1A. Personal Information", "p1_8_country_birth", "8. Country of Birth", "text", True),
    ("1A. Personal Information", "p1_9_citizenship", "9. Country of Citizenship or Nationality", "text", True),

    # PART 1B: OTHER NAMES USED
    ("1B. Other Names Used", "p1_2a_other_family_1", "2.a. Other Name 1 - Family Name", "text", False),
    ("1B. Other Names Used", "p1_2b_other_given_1", "2.b. Other Name 1 - Given Name", "text", False),
    ("1B. Other Names Used", "p1_2c_other_middle_1", "2.c. Other Name 1 - Middle Name", "text", False),
    ("1B. Other Names Used", "p1_3a_other_family_2", "3.a. Other Name 2 - Family Name", "text", False),
    ("1B. Other Names Used", "p1_3b_other_given_2", "3.b. Other Name 2 - Given Name", "text", False),
    ("1B. Other Names Used", "p1_3c_other_middle_2", "3.c. Other Name 2 - Middle Name", "text", False),

    # PART 1C: IDENTIFICATION NUMBERS
    ("1C. Identification Numbers", "p1_10_a_number", "10. Alien Registration Number (A-Number)", "text", False),
    ("1C. Identification Numbers", "p1_11_uscis_account", "11. USCIS Online Account Number", "text", False),
    ("1C. Identification Numbers", "p1_12_ssn", "12. U.S. Social Security Number", "text", False),

    # PART 1D: U.S. MAILING ADDRESS
    ("1D. U.S. Mailing Address", "p1_13a_mail_care_of", "13.a. In Care Of Name (c/o)", "text", False),
    ("1D. U.S. Mailing Address", "p1_13b_mail_street", "13.b. Street Number and Name", "text", True),
    ("1D. U.S. Mailing Address", "p1_13c_mail_apt", "13.c. Apt/Ste/Flr", "text", False),
    ("1D. U.S. Mailing Address", "p1_13d_mail_city", "13.d. City or Town", "text", True),
    ("1D. U.S. Mailing Address", "p1_13e_mail_state", "13.e. State", "select", True),
    ("1D. U.S. Mailing Address", "p1_13f_mail_zip", "13.f. ZIP Code", "text", True),

    # PART 1E: SAFE ALTERNATE ADDRESS (OPTIONAL)
    ("1E. Safe Alternate Address", "p1_14a_safe_care_of", "14.a. Safe Address - In Care Of Name", "text", False),
    ("1E. Safe Alternate Address", "p1_14b_safe_street", "14.b. Safe Address - Street", "text", False),
    ("1E. Safe Alternate Address", "p1_14c_safe_apt", "14.c. Safe Address - Apt/Ste/Flr", "text", False),
    ("1E. Safe Alternate Address", "p1_14d_safe_city", "14.d. Safe Address - City or Town", "text", False),
    ("1E. Safe Alternate Address", "p1_14e_safe_state", "14.e. Safe Address - State", "select", False),
    ("1E. Safe Alternate Address", "p1_14f_safe_zip", "14.f. Safe Address - ZIP Code", "text", False),

    # PART 1F: TRAVEL DOCUMENTS
    ("1F. Travel Documents", "p1_15_passport", "15. Passport Number", "text", False),
    ("1F. Travel Documents", "p1_16_travel_doc", "16. Travel Document Number", "text", False),
    ("1F. Travel Documents", "p1_17_passport_exp", "17. Passport Expiration Date", "date", False),
    ("1F. Travel Documents", "p1_18_passport_country", "18. Passport Country of Issuance", "text", False),
    ("1F. Travel Documents", "p1_19_visa_number", "19. Nonimmigrant Visa Number", "text", False),

    # PART 1G: LAST ARRIVAL IN THE U.S.
    ("1G. Last Arrival in U.S.", "p1_20a_arrival_city", "20.a. Place of Last Arrival - City or Town", "text", True),
    ("1G. Last Arrival in U.S.", "p1_20b_arrival_state", "20.b. Place of Last Arrival - State", "select", False),
    ("1G. Last Arrival in U.S.", "p1_21_arrival_date", "21. Date of Last Arrival (mm/dd/yyyy)", "date", True),
    ("1G. Last Arrival in U.S.", "p1_22a_inspected_admitted", "22.a. I was inspected and admitted", "checkbox", False),
    ("1G. Last Arrival in U.S.", "p1_22b_inspected_paroled", "22.b. I was inspected and paroled", "checkbox", False),
    ("1G. Last Arrival in U.S.", "p1_22c_without_inspection", "22.c. I arrived without admission or parole", "checkbox", False),
    ("1G. Last Arrival in U.S.", "p1_22d_other_inspection", "22.d. Other (explain)", "checkbox", False),

    # PART 1H: CURRENT IMMIGRATION STATUS
    ("1H. Current Immigration Status", "p1_23a_i94_number", "23.a. I-94 Arrival-Departure Record Number", "text", False),
    ("1H. Current Immigration Status", "p1_23b_admit_until", "23.b. Date Authorized Stay Expires", "text", False),
    ("1H. Current Immigration Status", "p1_23c_status_i94", "23.c. Status on Form I-94", "text", False),
    ("1H. Current Immigration Status", "p1_24_current_status", "24. Current Immigration Status", "text", True),
    ("1H. Current Immigration Status", "p1_25a_i94_family", "25.a. Name on I-94 - Family Name (if different)", "text", False),
    ("1H. Current Immigration Status", "p1_25b_i94_given", "25.b. Name on I-94 - Given Name (if different)", "text", False),

    # PART 2A: APPLICATION TYPE
    ("2A. Application Type", "p2_1_filing_eoir", "1. Filing with Immigration Court (EOIR)?", "radio", True),
    ("2A. Application Type", "p2_2a_immigrant_petition", "2.a. Based on immigrant petition (I-130, I-140, etc.)", "checkbox", False),
    ("2A. Application Type", "p2_2b_diversity_visa", "2.b. Diversity Visa Lottery winner", "checkbox", False),
    ("2A. Application Type", "p2_2c_asylee", "2.c. Asylee (1 year after asylum granted)", "checkbox", False),
    ("2A. Application Type", "p2_2d_refugee", "2.d. Refugee", "checkbox", False),
    ("2A. Application Type", "p2_2e_cuban_adj", "2.e. Cuban Adjustment Act", "checkbox", False),
    ("2A. Application Type", "p2_2f_registry", "2.f. Continuous Residence Before 01/01/1972", "checkbox", False),
    ("2A. Application Type", "p2_2g_other", "2.g. Other basis (specify)", "checkbox", False),
    ("2A. Application Type", "p2_2g_other_explain", "2.g. If Other, explain", "text", False),

    # PART 2B: INA SECTION 245(i)
    ("2B. INA Section 245(i)", "p2_3a_245i_before_apr2001", "3.a. I-130/I-140 filed on or before 04/30/2001", "checkbox", False),
    ("2B. INA Section 245(i)", "p2_3b_245i_before_jan1998", "3.b. I-130/I-140 filed on or before 01/14/1998", "checkbox", False),
    ("2B. INA Section 245(i)", "p2_3c_245i_grandfathered", "3.c. Grandfathered (01/15/1998 - 04/30/2001)", "checkbox", False),
    ("2B. INA Section 245(i)", "p2_3d_not_245i", "3.d. I am not subject to INA section 245(i)", "checkbox", False),

    # PART 2C: APPROVED PETITION
    ("2C. Approved Petition", "p2_4_receipt_number", "4. Receipt Number of Approved Petition", "text", False),
    ("2C. Approved Petition", "p2_5_priority_date", "5. Priority Date (mm/dd/yyyy)", "date", False),
    ("2C. Approved Petition", "p2_6_principal_applicant", "6. Are you the principal applicant?", "radio", True),
    ("2C. Approved Petition", "p2_7a_principal_family", "7.a. Principal Applicant - Family Name", "text", False),
    ("2C. Approved Petition", "p2_7b_principal_given", "7.b. Principal Applicant - Given Name", "text", False),
    ("2C. Approved Petition", "p2_8_principal_a_number", "8. Principal Applicant A-Number", "text", False),
    ("2C. Approved Petition", "p2_9_principal_dob", "9. Principal Applicant Date of Birth", "date", False),
    ("2C. Approved Petition", "p2_10_relationship", "10. Your Relationship to Principal", "select", False),

    # PART 3: AFFIDAVIT OF SUPPORT EXEMPTION
    ("3. Affidavit of Support Exemption", "p3_1_claiming_exemption", "1. Claiming exemption from I-864?", "radio", True),
    ("3. Affidavit of Support Exemption", "p3_2_40_quarters", "2. I have 40 qualifying quarters of work", "checkbox", False),
    ("3. Affidavit of Support Exemption", "p3_3_vawa", "3. Self-supporting VAWA applicant", "checkbox", False),
    ("3. Affidavit of Support Exemption", "p3_4_widow", "4. Widow(er) of U.S. citizen", "checkbox", False),
    ("3. Affidavit of Support Exemption", "p3_5_other_exemption", "5. Other exemption reason", "checkbox", False),

    # PART 4A: VISA HISTORY
    ("4A. Visa History", "p4_1_applied_visa", "1. Ever applied for immigrant visa at U.S. Embassy?", "radio", True),
    ("4A. Visa History", "p4_2_visa_approved", "2. If yes, was it approved?", "radio", False),
    ("4A. Visa History", "p4_3_visa_refused", "3. If yes, was it refused/denied?", "radio", False),
    ("4A. Visa History", "p4_4_visa_withdrawn", "4. If yes, was it withdrawn?", "radio", False),

    # PART 4B: CURRENT PHYSICAL ADDRESS
    ("4B. Current Physical Address", "p4_5a_curr_street", "5.a. Street Number and Name", "text", True),
    ("4B. Current Physical Address", "p4_5b_curr_apt", "5.b. Apt/Ste/Flr", "text", False),
    ("4B. Current Physical Address", "p4_5c_curr_city", "5.c. City or Town", "text", True),
    ("4B. Current Physical Address", "p4_5d_curr_state", "5.d. State", "select", True),
    ("4B. Current Physical Address", "p4_5e_curr_zip", "5.e. ZIP Code", "text", True),
    ("4B. Current Physical Address", "p4_5h_curr_country", "5.h. Country", "text", True),
    ("4B. Current Physical Address", "p4_5i_curr_from", "5.i. Date From (mm/dd/yyyy)", "date", True),
    ("4B. Current Physical Address", "p4_5j_curr_to", "5.j. Date To (Present)", "text", True),

    # PART 4C: PREVIOUS ADDRESS 1
    ("4C. Previous Address 1", "p4_6a_prev1_street", "6.a. Previous Address 1 - Street", "text", False),
    ("4C. Previous Address 1", "p4_6c_prev1_city", "6.c. Previous Address 1 - City", "text", False),
    ("4C. Previous Address 1", "p4_6d_prev1_state", "6.d. Previous Address 1 - State", "select", False),
    ("4C. Previous Address 1", "p4_6h_prev1_country", "6.h. Previous Address 1 - Country", "text", False),
    ("4C. Previous Address 1", "p4_6i_prev1_from", "6.i. Previous Address 1 - Date From", "date", False),
    ("4C. Previous Address 1", "p4_6j_prev1_to", "6.j. Previous Address 1 - Date To", "date", False),

    # PART 4D: PREVIOUS ADDRESS 2
    ("4D. Previous Address 2", "p4_7a_prev2_street", "7.a. Previous Address 2 - Street", "text", False),
    ("4D. Previous Address 2", "p4_7c_prev2_city", "7.c. Previous Address 2 - City", "text", False),
    ("4D. Previous Address 2", "p4_7d_prev2_state", "7.d. Previous Address 2 - State", "select", False),
    ("4D. Previous Address 2", "p4_7h_prev2_country", "7.h. Previous Address 2 - Country", "text", False),
    ("4D. Previous Address 2", "p4_7i_prev2_from", "7.i. Previous Address 2 - Date From", "date", False),
    ("4D. Previous Address 2", "p4_7j_prev2_to", "7.j. Previous Address 2 - Date To", "date", False),

    # PART 4E: CURRENT EMPLOYMENT
    ("4E. Current Employment", "p4_11a_emp_name", "11.a. Employer/School Name", "text", True),
    ("4E. Current Employment", "p4_11b_emp_street", "11.b. Employer - Street", "text", True),
    ("4E. Current Employment", "p4_11d_emp_city", "11.d. Employer - City", "text", True),
    ("4E. Current Employment", "p4_11e_emp_state", "11.e. Employer - State", "select", False),
    ("4E. Current Employment", "p4_11i_emp_country", "11.i. Employer - Country", "text", True),
    ("4E. Current Employment", "p4_12_occupation", "12. Your Occupation/Position", "text", True),
    ("4E. Current Employment", "p4_13a_emp_from", "13.a. Employment - Date From", "date", True),
    ("4E. Current Employment", "p4_13b_emp_to", "13.b. Employment - Date To", "text", True),

    # PART 4F: PREVIOUS EMPLOYMENT
    ("4F. Previous Employment", "p4_14a_prev_emp1_name", "14.a. Previous Employer 1 - Name", "text", False),
    ("4F. Previous Employment", "p4_14c_prev_emp1_city", "14.c. Previous Employer 1 - City", "text", False),
    ("4F. Previous Employment", "p4_14e_prev_emp1_country", "14.e. Previous Employer 1 - Country", "text", False),
    ("4F. Previous Employment", "p4_14f_prev_emp1_occupation", "14.f. Previous Employer 1 - Occupation", "text", False),
    ("4F. Previous Employment", "p4_15a_prev_emp1_from", "15.a. Previous Employment 1 - Date From", "date", False),
    ("4F. Previous Employment", "p4_15b_prev_emp1_to", "15.b. Previous Employment 1 - Date To", "date", False),

    # PART 5A: PARENT 1
    ("5A. Parent 1", "p5_1a_parent1_family", "1.a. Parent 1 - Family Name", "text", True),
    ("5A. Parent 1", "p5_1b_parent1_given", "1.b. Parent 1 - Given Name", "text", True),
    ("5A. Parent 1", "p5_1c_parent1_middle", "1.c. Parent 1 - Middle Name", "text", False),
    ("5A. Parent 1", "p5_3_parent1_dob", "3. Parent 1 - Date of Birth", "date", True),
    ("5A. Parent 1", "p5_4_parent1_sex", "4. Parent 1 - Sex", "select", True),
    ("5A. Parent 1", "p5_5_parent1_city_birth", "5. Parent 1 - City of Birth", "text", True),
    ("5A. Parent 1", "p5_6_parent1_country_birth", "6. Parent 1 - Country of Birth", "text", True),
    ("5A. Parent 1", "p5_7_parent1_city_residence", "7. Parent 1 - Current City of Residence", "text", False),
    ("5A. Parent 1", "p5_8_parent1_country_residence", "8. Parent 1 - Current Country of Residence", "text", False),

    # PART 5B: PARENT 2
    ("5B. Parent 2", "p5_9a_parent2_family", "9.a. Parent 2 - Family Name", "text", True),
    ("5B. Parent 2", "p5_9b_parent2_given", "9.b. Parent 2 - Given Name", "text", True),
    ("5B. Parent 2", "p5_9c_parent2_middle", "9.c. Parent 2 - Middle Name", "text", False),
    ("5B. Parent 2", "p5_11_parent2_dob", "11. Parent 2 - Date of Birth", "date", True),
    ("5B. Parent 2", "p5_12_parent2_sex", "12. Parent 2 - Sex", "select", True),
    ("5B. Parent 2", "p5_13_parent2_city_birth", "13. Parent 2 - City of Birth", "text", True),
    ("5B. Parent 2", "p5_14_parent2_country_birth", "14. Parent 2 - Country of Birth", "text", True),

    # PART 6A: MARITAL STATUS
    ("6A. Marital Status", "p6_1_marital_status", "1. Current Marital Status", "select", True),
    ("6A. Marital Status", "p6_2_times_married", "2. How many times married?", "number", True),

    # PART 6B: CURRENT SPOUSE
    ("6B. Current Spouse", "p6_3a_spouse_family", "3.a. Spouse - Family Name", "text", False),
    ("6B. Current Spouse", "p6_3b_spouse_given", "3.b. Spouse - Given Name", "text", False),
    ("6B. Current Spouse", "p6_4_spouse_dob", "4. Spouse - Date of Birth", "date", False),
    ("6B. Current Spouse", "p6_5_spouse_a_number", "5. Spouse - A-Number", "text", False),
    ("6B. Current Spouse", "p6_6_spouse_country_birth", "6. Spouse - Country of Birth", "text", False),
    ("6B. Current Spouse", "p6_8_marriage_date", "8. Date of Marriage", "date", False),
    ("6B. Current Spouse", "p6_9a_marriage_city", "9.a. Place of Marriage - City", "text", False),
    ("6B. Current Spouse", "p6_9c_marriage_country", "9.c. Place of Marriage - Country", "text", False),
    ("6B. Current Spouse", "p6_10_spouse_in_us", "10. Spouse currently in U.S.?", "radio", False),
    ("6B. Current Spouse", "p6_11_spouse_applying", "11. Spouse applying with you?", "radio", False),

    # PART 6C: PRIOR SPOUSE
    ("6C. Prior Spouse", "p6_12a_prior_family", "12.a. Prior Spouse - Family Name", "text", False),
    ("6C. Prior Spouse", "p6_12b_prior_given", "12.b. Prior Spouse - Given Name", "text", False),
    ("6C. Prior Spouse", "p6_14_prior_marriage_date", "14. Date of Marriage to Prior Spouse", "date", False),
    ("6C. Prior Spouse", "p6_15_prior_marriage_end", "15. Date Marriage Ended", "date", False),
    ("6C. Prior Spouse", "p6_16a_divorced", "16.a. Ended by Divorce", "checkbox", False),
    ("6C. Prior Spouse", "p6_16b_widowed", "16.b. Widowed", "checkbox", False),
    ("6C. Prior Spouse", "p6_16c_annulled", "16.c. Annulled", "checkbox", False),

    # PART 7: CHILDREN
    ("7A. Children - General", "p7_1_total_children", "1. Total Number of Children", "number", True),
    ("7B. Child 1", "p7_2a_child1_family", "2.a. Child 1 - Family Name", "text", False),
    ("7B. Child 1", "p7_2b_child1_given", "2.b. Child 1 - Given Name", "text", False),
    ("7B. Child 1", "p7_4_child1_dob", "4. Child 1 - Date of Birth", "date", False),
    ("7B. Child 1", "p7_5_child1_country_birth", "5. Child 1 - Country of Birth", "text", False),
    ("7B. Child 1", "p7_7_child1_in_us", "7. Child 1 - Currently in U.S.?", "radio", False),
    ("7B. Child 1", "p7_8_child1_applying", "8. Child 1 - Applying with you?", "radio", False),
    ("7C. Child 2", "p7_9a_child2_family", "9.a. Child 2 - Family Name", "text", False),
    ("7C. Child 2", "p7_9b_child2_given", "9.b. Child 2 - Given Name", "text", False),
    ("7C. Child 2", "p7_11_child2_dob", "11. Child 2 - Date of Birth", "date", False),
    ("7C. Child 2", "p7_12_child2_country", "12. Child 2 - Country of Birth", "text", False),

    # PART 8: BIOGRAPHIC INFORMATION
    ("8. Biographic Information", "p8_1_ethnicity", "1. Ethnicity - Hispanic or Latino?", "radio", True),
    ("8. Biographic Information", "p8_2a_race_white", "2.a. Race - White", "checkbox", False),
    ("8. Biographic Information", "p8_2b_race_asian", "2.b. Race - Asian", "checkbox", False),
    ("8. Biographic Information", "p8_2c_race_black", "2.c. Race - Black or African American", "checkbox", False),
    ("8. Biographic Information", "p8_2d_race_native", "2.d. Race - American Indian/Alaska Native", "checkbox", False),
    ("8. Biographic Information", "p8_2e_race_pacific", "2.e. Race - Native Hawaiian/Pacific Islander", "checkbox", False),
    ("8. Biographic Information", "p8_3a_height_feet", "3.a. Height - Feet", "number", True),
    ("8. Biographic Information", "p8_3b_height_inches", "3.b. Height - Inches", "number", True),
    ("8. Biographic Information", "p8_4_weight", "4. Weight (Pounds)", "number", True),
    ("8. Biographic Information", "p8_5_eye_color", "5. Eye Color", "select", True),
    ("8. Biographic Information", "p8_6_hair_color", "6. Hair Color", "select", True),

    # PART 9A: ORGANIZATIONS
    ("9A. Organizations", "p9_1_member_org", "1. Ever member of any organization, party, club?", "radio", True),
    ("9A. Organizations", "p9_2a_org1_name", "2.a. Organization 1 - Name", "text", False),
    ("9A. Organizations", "p9_2d_org1_country", "2.d. Organization 1 - Country", "text", False),
    ("9A. Organizations", "p9_5_communist", "5. Any communist or totalitarian party?", "radio", True),

    # PART 9B: MILITARY SERVICE
    ("9B. Military Service", "p9_6_military", "6. Served in military, police, militia?", "radio", True),
    ("9B. Military Service", "p9_7a_mil1_name", "7.a. Military Service 1 - Organization", "text", False),
    ("9B. Military Service", "p9_7b_mil1_country", "7.b. Military Service 1 - Country", "text", False),
    ("9B. Military Service", "p9_9_weapons_training", "9. Received weapons training?", "radio", True),

    # PART 9C: IMMIGRATION HISTORY
    ("9C. Immigration History", "p9_14_violated_status", "14. Ever violated nonimmigrant status?", "radio", True),
    ("9C. Immigration History", "p9_15_worked_unauthorized", "15. Ever worked in U.S. without authorization?", "radio", True),
    ("9C. Immigration History", "p9_16_visa_denied", "16. Ever been denied a U.S. visa?", "radio", True),
    ("9C. Immigration History", "p9_17_admission_denied", "17. Ever denied admission to U.S.?", "radio", True),
    ("9C. Immigration History", "p9_22_removed", "22. Ever removed or deported?", "radio", True),
    ("9C. Immigration History", "p9_24_proceedings", "24. Ever in removal proceedings?", "radio", True),

    # PART 9D: CRIMINAL HISTORY
    ("9D. Criminal History", "p9_25_arrested", "25. Ever arrested or detained?", "radio", True),
    ("9D. Criminal History", "p9_26_committed_crime", "26. Ever committed a crime?", "radio", True),
    ("9D. Criminal History", "p9_27_convicted", "27. Ever convicted of a crime?", "radio", True),
    ("9D. Criminal History", "p9_30_jail", "30. Ever been in jail or prison?", "radio", True),
    ("9D. Criminal History", "p9_31_drugs_law", "31. Ever violated controlled substance laws?", "radio", True),
    ("9D. Criminal History", "p9_36_prostitution", "36. Ever engaged in prostitution?", "radio", True),
    ("9D. Criminal History", "p9_42_money_laundering", "42. Ever engaged in money laundering?", "radio", True),

    # PART 9E: NATIONAL SECURITY
    ("9E. National Security", "p9_46a_espionage", "46.a. Ever engaged in espionage?", "radio", True),
    ("9E. National Security", "p9_48_terrorist_activity", "48. Ever engaged in terrorist activity?", "radio", True),
    ("9E. National Security", "p9_50_terrorist_member", "50. Ever member of terrorist organization?", "radio", True),
    ("9E. National Security", "p9_56_genocide", "56. Ever participated in genocide?", "radio", True),
    ("9E. National Security", "p9_57_torture", "57. Ever participated in torture?", "radio", True),

    # PART 9F: PUBLIC CHARGE
    ("9F. Public Charge", "p9_61_public_charge", "61. Subject to public charge inadmissibility?", "radio", True),
    ("9F. Public Charge", "p9_62_household_size", "62. Household Size", "number", False),
    ("9F. Public Charge", "p9_63_household_income", "63. Combined Annual Household Income", "text", False),

    # PART 9G: OTHER QUESTIONS
    ("9G. Other Questions", "p9_70_unlawful_presence", "70. Ever unlawfully present in U.S.?", "radio", True),
    ("9G. Other Questions", "p9_72_false_citizen", "72. Ever falsely claimed U.S. citizenship?", "radio", True),
    ("9G. Other Questions", "p9_77_voted_illegally", "77. Ever voted illegally?", "radio", True),
    ("9G. Other Questions", "p9_84_vaccinated", "84. Have required vaccinations?", "radio", True),

    # PART 10: ACCOMMODATIONS
    ("10. Disability Accommodations", "p10_1_accommodation", "1. Requesting accommodation?", "radio", True),
    ("10. Disability Accommodations", "p10_2a_deaf", "2.a. Deaf - need sign language interpreter", "checkbox", False),
    ("10. Disability Accommodations", "p10_2b_blind", "2.b. Blind or sight-impaired", "checkbox", False),

    # PART 11: APPLICANT STATEMENT
    ("11. Applicant Statement & Contact", "p11_1a_can_read", "1.a. I can read and understand English", "checkbox", False),
    ("11. Applicant Statement & Contact", "p11_1b_interpreter", "1.b. Someone interpreted this for me", "checkbox", False),
    ("11. Applicant Statement & Contact", "p11_3_phone", "3. Daytime Telephone Number", "phone", True),
    ("11. Applicant Statement & Contact", "p11_4_mobile", "4. Mobile Telephone Number", "phone", False),
    ("11. Applicant Statement & Contact", "p11_5_email", "5. Email Address", "email", False),
    ("11. Applicant Statement & Contact", "p11_6b_signature_date", "6.b. Date of Signature", "date", True),

    # PART 12: INTERPRETER
    ("12. Interpreter Information", "p12_1a_interp_family", "1.a. Interpreter's Family Name", "text", False),
    ("12. Interpreter Information", "p12_1b_interp_given", "1.b. Interpreter's Given Name", "text", False),
    ("12. Interpreter Information", "p12_4_interp_phone", "4. Interpreter's Phone", "phone", False),
    ("12. Interpreter Information", "p12_7_language", "7. Language Interpreted", "text", False),

    # PART 13: PREPARER
    ("13. Preparer Information", "p13_1b_is_attorney", "1.b. Preparer IS an attorney", "checkbox", False),
    ("13. Preparer Information", "p13_2a_prep_family", "2.a. Preparer's Family Name", "text", False),
    ("13. Preparer Information", "p13_2b_prep_given", "2.b. Preparer's Given Name", "text", False),
    ("13. Preparer Information", "p13_3_prep_org", "3. Preparer's Organization", "text", False),
    ("13. Preparer Information", "p13_5_prep_phone", "5. Preparer's Phone", "phone", False),

    # PART 14: ADDITIONAL INFORMATION
    ("14. Additional Information", "p15_1d_info", "Additional Information 1", "textarea", False),
    ("14. Additional Information", "p15_2d_info", "Additional Information 2", "textarea", False),
]

# =============================================================================
# I-130 - PETITION FOR ALIEN RELATIVE (12 pages, ~180 fields)
# =============================================================================
I130_FIELDS = [
    # PART 1: RELATIONSHIP
    ("1. Relationship", "p1_1_filing_for", "1. I am filing this petition for my:", "select", True),
    ("1. Relationship", "p1_2_child_type", "2. If filing for child, relationship type:", "select", False),
    ("1. Relationship", "p1_3_sibling_adoption", "3. If sibling, related by adoption?", "radio", False),
    ("1. Relationship", "p1_4_gained_lpr_adoption", "4. Did you gain LPR status through adoption?", "radio", False),

    # PART 2A: PETITIONER INFORMATION
    ("2A. Petitioner Information", "p2_1_a_number", "1. Alien Registration Number (A-Number)", "text", False),
    ("2A. Petitioner Information", "p2_2_uscis_account", "2. USCIS Online Account Number", "text", False),
    ("2A. Petitioner Information", "p2_3_ssn", "3. U.S. Social Security Number", "text", False),
    ("2A. Petitioner Information", "p2_4a_family_name", "4.a. Family Name (Last Name)", "text", True),
    ("2A. Petitioner Information", "p2_4b_given_name", "4.b. Given Name (First Name)", "text", True),
    ("2A. Petitioner Information", "p2_4c_middle_name", "4.c. Middle Name", "text", False),

    # PART 2B: PETITIONER MAILING ADDRESS
    ("2B. Petitioner Mailing Address", "p2_5a_street", "5.a. Street Number and Name", "text", True),
    ("2B. Petitioner Mailing Address", "p2_5b_apt", "5.b. Apt/Ste/Flr", "text", False),
    ("2B. Petitioner Mailing Address", "p2_5c_city", "5.c. City or Town", "text", True),
    ("2B. Petitioner Mailing Address", "p2_5d_state", "5.d. State", "select", True),
    ("2B. Petitioner Mailing Address", "p2_5e_zip", "5.e. ZIP Code", "text", True),
    ("2B. Petitioner Mailing Address", "p2_5f_province", "5.f. Province (if outside U.S.)", "text", False),
    ("2B. Petitioner Mailing Address", "p2_5g_postal", "5.g. Postal Code (if outside U.S.)", "text", False),
    ("2B. Petitioner Mailing Address", "p2_5h_country", "5.h. Country", "text", True),

    # PART 2C: PETITIONER PHYSICAL ADDRESS
    ("2C. Petitioner Physical Address", "p2_6_same_address", "6. Is physical address same as mailing?", "radio", True),
    ("2C. Petitioner Physical Address", "p2_7a_phys_street", "7.a. Physical Address - Street", "text", False),
    ("2C. Petitioner Physical Address", "p2_7b_phys_apt", "7.b. Physical Address - Apt/Ste/Flr", "text", False),
    ("2C. Petitioner Physical Address", "p2_7c_phys_city", "7.c. Physical Address - City", "text", False),
    ("2C. Petitioner Physical Address", "p2_7d_phys_state", "7.d. Physical Address - State", "select", False),
    ("2C. Petitioner Physical Address", "p2_7e_phys_zip", "7.e. Physical Address - ZIP Code", "text", False),

    # PART 2D: PETITIONER OTHER INFO
    ("2D. Petitioner Other Info", "p2_8_dob", "8. Date of Birth (mm/dd/yyyy)", "date", True),
    ("2D. Petitioner Other Info", "p2_9_city_birth", "9. City/Town of Birth", "text", True),
    ("2D. Petitioner Other Info", "p2_10_country_birth", "10. Country of Birth", "text", True),
    ("2D. Petitioner Other Info", "p2_11_citizenship", "11. Country of Citizenship/Nationality", "text", True),
    ("2D. Petitioner Other Info", "p2_12_status", "12. I am a U.S. Citizen / Lawful Permanent Resident", "select", True),
    ("2D. Petitioner Other Info", "p2_13_marital_status", "13. Current Marital Status", "select", True),
    ("2D. Petitioner Other Info", "p2_14_times_married", "14. How many times married?", "number", True),

    # PART 2E: PETITIONER EMPLOYMENT
    ("2E. Petitioner Employment", "p2_15_employer", "15. Employer or Company Name", "text", False),
    ("2E. Petitioner Employment", "p2_16a_emp_street", "16.a. Employer Address - Street", "text", False),
    ("2E. Petitioner Employment", "p2_16b_emp_city", "16.b. Employer Address - City", "text", False),
    ("2E. Petitioner Employment", "p2_16c_emp_state", "16.c. Employer Address - State", "select", False),
    ("2E. Petitioner Employment", "p2_16d_emp_zip", "16.d. Employer Address - ZIP Code", "text", False),

    # PART 3: BIOGRAPHIC INFORMATION
    ("3. Biographic Information", "p3_1_ethnicity", "1. Ethnicity - Hispanic or Latino?", "radio", True),
    ("3. Biographic Information", "p3_2a_race_white", "2.a. Race - White", "checkbox", False),
    ("3. Biographic Information", "p3_2b_race_asian", "2.b. Race - Asian", "checkbox", False),
    ("3. Biographic Information", "p3_2c_race_black", "2.c. Race - Black or African American", "checkbox", False),
    ("3. Biographic Information", "p3_2d_race_native", "2.d. Race - American Indian/Alaska Native", "checkbox", False),
    ("3. Biographic Information", "p3_2e_race_pacific", "2.e. Race - Native Hawaiian/Pacific Islander", "checkbox", False),
    ("3. Biographic Information", "p3_3a_height_feet", "3.a. Height - Feet", "number", True),
    ("3. Biographic Information", "p3_3b_height_inches", "3.b. Height - Inches", "number", True),
    ("3. Biographic Information", "p3_4_weight", "4. Weight (Pounds)", "number", True),
    ("3. Biographic Information", "p3_5_eye_color", "5. Eye Color", "select", True),
    ("3. Biographic Information", "p3_6_hair_color", "6. Hair Color", "select", True),

    # PART 4A: BENEFICIARY INFORMATION
    ("4A. Beneficiary Information", "p4_1_a_number", "1. Beneficiary's A-Number (if any)", "text", False),
    ("4A. Beneficiary Information", "p4_2_uscis_account", "2. Beneficiary's USCIS Online Account Number", "text", False),
    ("4A. Beneficiary Information", "p4_3_ssn", "3. Beneficiary's U.S. Social Security Number", "text", False),
    ("4A. Beneficiary Information", "p4_4a_family_name", "4.a. Beneficiary's Family Name (Last Name)", "text", True),
    ("4A. Beneficiary Information", "p4_4b_given_name", "4.b. Beneficiary's Given Name (First Name)", "text", True),
    ("4A. Beneficiary Information", "p4_4c_middle_name", "4.c. Beneficiary's Middle Name", "text", False),

    # PART 4B: BENEFICIARY OTHER NAMES
    ("4B. Beneficiary Other Names", "p4_5a_other_family", "5.a. Other Names Used - Family Name", "text", False),
    ("4B. Beneficiary Other Names", "p4_5b_other_given", "5.b. Other Names Used - Given Name", "text", False),
    ("4B. Beneficiary Other Names", "p4_5c_other_middle", "5.c. Other Names Used - Middle Name", "text", False),

    # PART 4C: BENEFICIARY ADDRESS
    ("4C. Beneficiary Address", "p4_6a_street", "6.a. Beneficiary's Address - Street", "text", True),
    ("4C. Beneficiary Address", "p4_6b_apt", "6.b. Beneficiary's Address - Apt/Ste/Flr", "text", False),
    ("4C. Beneficiary Address", "p4_6c_city", "6.c. Beneficiary's Address - City or Town", "text", True),
    ("4C. Beneficiary Address", "p4_6d_state", "6.d. Beneficiary's Address - State/Province", "text", False),
    ("4C. Beneficiary Address", "p4_6e_postal", "6.e. Beneficiary's Address - Postal Code", "text", False),
    ("4C. Beneficiary Address", "p4_6f_country", "6.f. Beneficiary's Address - Country", "text", True),

    # PART 4D: BENEFICIARY OTHER INFO
    ("4D. Beneficiary Other Info", "p4_7_dob", "7. Beneficiary's Date of Birth", "date", True),
    ("4D. Beneficiary Other Info", "p4_8_city_birth", "8. Beneficiary's City/Town of Birth", "text", True),
    ("4D. Beneficiary Other Info", "p4_9_country_birth", "9. Beneficiary's Country of Birth", "text", True),
    ("4D. Beneficiary Other Info", "p4_10_citizenship", "10. Beneficiary's Country of Citizenship", "text", True),
    ("4D. Beneficiary Other Info", "p4_11_sex", "11. Beneficiary's Sex", "select", True),
    ("4D. Beneficiary Other Info", "p4_12_marital_status", "12. Beneficiary's Marital Status", "select", True),
    ("4D. Beneficiary Other Info", "p4_13_times_married", "13. How many times has beneficiary been married?", "number", True),

    # PART 4E: BENEFICIARY U.S. ENTRY INFO
    ("4E. Beneficiary U.S. Entry", "p4_14_in_us", "14. Is beneficiary currently in the United States?", "radio", True),
    ("4E. Beneficiary U.S. Entry", "p4_15_last_entry_date", "15. Date of Last Entry to U.S.", "date", False),
    ("4E. Beneficiary U.S. Entry", "p4_16_last_entry_place", "16. Place of Last Entry (City, State)", "text", False),
    ("4E. Beneficiary U.S. Entry", "p4_17_i94_number", "17. I-94 Arrival-Departure Record Number", "text", False),
    ("4E. Beneficiary U.S. Entry", "p4_18_current_status", "18. Beneficiary's Current Immigration Status", "text", False),
    ("4E. Beneficiary U.S. Entry", "p4_19_status_expires", "19. Status Expiration Date", "date", False),

    # PART 4F: BENEFICIARY PASSPORT
    ("4F. Beneficiary Passport", "p4_20_passport", "20. Beneficiary's Passport Number", "text", False),
    ("4F. Beneficiary Passport", "p4_21_travel_doc", "21. Beneficiary's Travel Document Number", "text", False),
    ("4F. Beneficiary Passport", "p4_22_passport_country", "22. Country of Issuance", "text", False),
    ("4F. Beneficiary Passport", "p4_23_passport_expires", "23. Passport/Travel Document Expiration Date", "date", False),

    # PART 4G: BENEFICIARY'S FATHER
    ("4G. Beneficiary's Father", "p4_24a_father_family", "24.a. Father's Family Name (Last Name)", "text", True),
    ("4G. Beneficiary's Father", "p4_24b_father_given", "24.b. Father's Given Name (First Name)", "text", True),
    ("4G. Beneficiary's Father", "p4_25_father_dob", "25. Father's Date of Birth", "date", False),
    ("4G. Beneficiary's Father", "p4_26_father_country_birth", "26. Father's Country of Birth", "text", False),
    ("4G. Beneficiary's Father", "p4_27_father_city_residence", "27. Father's Current City of Residence", "text", False),

    # PART 4H: BENEFICIARY'S MOTHER
    ("4H. Beneficiary's Mother", "p4_28a_mother_family", "28.a. Mother's Family Name (Last Name)", "text", True),
    ("4H. Beneficiary's Mother", "p4_28b_mother_given", "28.b. Mother's Given Name (First Name)", "text", True),
    ("4H. Beneficiary's Mother", "p4_29_mother_dob", "29. Mother's Date of Birth", "date", False),
    ("4H. Beneficiary's Mother", "p4_30_mother_country_birth", "30. Mother's Country of Birth", "text", False),
    ("4H. Beneficiary's Mother", "p4_31_mother_city_residence", "31. Mother's Current City of Residence", "text", False),

    # PART 5: OTHER INFORMATION
    ("5. Other Information", "p5_1_previous_petition", "1. Has anyone else filed a petition for beneficiary?", "radio", True),
    ("5. Other Information", "p5_2_where_filed", "2. Where was petition filed?", "text", False),
    ("5. Other Information", "p5_3_result", "3. What was the result?", "text", False),

    # PART 6: PETITIONER STATEMENT & SIGNATURE
    ("6. Petitioner Statement", "p6_1_can_read", "1.a. I can read and understand English", "checkbox", False),
    ("6. Petitioner Statement", "p6_1b_interpreter", "1.b. Someone interpreted this for me", "checkbox", False),
    ("6. Petitioner Statement", "p6_2_interp_language", "2. Language used by interpreter", "text", False),
    ("6. Petitioner Statement", "p6_3_phone", "3. Petitioner's Daytime Telephone Number", "phone", True),
    ("6. Petitioner Statement", "p6_4_mobile", "4. Petitioner's Mobile Telephone Number", "phone", False),
    ("6. Petitioner Statement", "p6_5_email", "5. Petitioner's Email Address", "email", False),
    ("6. Petitioner Statement", "p6_6_signature_date", "6. Date of Signature", "date", True),

    # PART 7: INTERPRETER INFORMATION
    ("7. Interpreter Information", "p7_1a_interp_family", "1.a. Interpreter's Family Name", "text", False),
    ("7. Interpreter Information", "p7_1b_interp_given", "1.b. Interpreter's Given Name", "text", False),
    ("7. Interpreter Information", "p7_2_interp_org", "2. Interpreter's Organization Name", "text", False),
    ("7. Interpreter Information", "p7_3_interp_phone", "3. Interpreter's Phone Number", "phone", False),
    ("7. Interpreter Information", "p7_4_language", "4. Language Interpreted", "text", False),

    # PART 8: PREPARER INFORMATION
    ("8. Preparer Information", "p8_1_prep_family", "1.a. Preparer's Family Name", "text", False),
    ("8. Preparer Information", "p8_1b_prep_given", "1.b. Preparer's Given Name", "text", False),
    ("8. Preparer Information", "p8_2_prep_org", "2. Preparer's Organization Name", "text", False),
    ("8. Preparer Information", "p8_3_prep_phone", "3. Preparer's Phone Number", "phone", False),
    ("8. Preparer Information", "p8_4_prep_email", "4. Preparer's Email Address", "email", False),

    # PART 9: ADDITIONAL INFORMATION
    ("9. Additional Information", "p9_1_additional", "Additional Information", "textarea", False),
]

# =============================================================================
# I-130A - SUPPLEMENTAL INFORMATION FOR SPOUSE BENEFICIARY (6 pages)
# =============================================================================
I130A_FIELDS = [
    # PART 1A: BENEFICIARY INFORMATION
    ("1A. Beneficiary Information", "p1_1_a_number", "1. Alien Registration Number (A-Number)", "text", False),
    ("1A. Beneficiary Information", "p1_2_uscis_account", "2. USCIS Online Account Number", "text", False),
    ("1A. Beneficiary Information", "p1_3a_family_name", "3.a. Family Name (Last Name)", "text", True),
    ("1A. Beneficiary Information", "p1_3b_given_name", "3.b. Given Name (First Name)", "text", True),
    ("1A. Beneficiary Information", "p1_3c_middle_name", "3.c. Middle Name", "text", False),

    # PART 1B: CURRENT ADDRESS
    ("1B. Current U.S. Address", "p1_4a_street", "4.a. Street Number and Name", "text", True),
    ("1B. Current U.S. Address", "p1_4b_apt", "4.b. Apt/Ste/Flr", "text", False),
    ("1B. Current U.S. Address", "p1_4c_city", "4.c. City or Town", "text", True),
    ("1B. Current U.S. Address", "p1_4d_state", "4.d. State", "select", True),
    ("1B. Current U.S. Address", "p1_4e_zip", "4.e. ZIP Code", "text", True),
    ("1B. Current U.S. Address", "p1_5_from_date", "5. Date From (mm/dd/yyyy)", "date", True),
    ("1B. Current U.S. Address", "p1_6_to_date", "6. Date To (Present)", "text", True),

    # PART 1C: PREVIOUS ADDRESSES (LAST 5 YEARS)
    ("1C. Previous Address 1", "p1_7a_prev1_street", "7.a. Previous Address 1 - Street", "text", False),
    ("1C. Previous Address 1", "p1_7b_prev1_city", "7.b. Previous Address 1 - City", "text", False),
    ("1C. Previous Address 1", "p1_7c_prev1_state", "7.c. Previous Address 1 - State", "select", False),
    ("1C. Previous Address 1", "p1_7d_prev1_zip", "7.d. Previous Address 1 - ZIP", "text", False),
    ("1C. Previous Address 1", "p1_7e_prev1_country", "7.e. Previous Address 1 - Country", "text", False),
    ("1C. Previous Address 1", "p1_8_prev1_from", "8. Previous Address 1 - Date From", "date", False),
    ("1C. Previous Address 1", "p1_9_prev1_to", "9. Previous Address 1 - Date To", "date", False),

    ("1D. Previous Address 2", "p1_10a_prev2_street", "10.a. Previous Address 2 - Street", "text", False),
    ("1D. Previous Address 2", "p1_10b_prev2_city", "10.b. Previous Address 2 - City", "text", False),
    ("1D. Previous Address 2", "p1_10c_prev2_state", "10.c. Previous Address 2 - State", "select", False),
    ("1D. Previous Address 2", "p1_10d_prev2_country", "10.d. Previous Address 2 - Country", "text", False),
    ("1D. Previous Address 2", "p1_11_prev2_from", "11. Previous Address 2 - Date From", "date", False),
    ("1D. Previous Address 2", "p1_12_prev2_to", "12. Previous Address 2 - Date To", "date", False),

    # PART 2A: EMPLOYMENT HISTORY
    ("2A. Current Employment", "p2_1_employer", "1. Current Employer Name", "text", True),
    ("2A. Current Employment", "p2_2a_emp_street", "2.a. Employer Address - Street", "text", True),
    ("2A. Current Employment", "p2_2b_emp_city", "2.b. Employer Address - City", "text", True),
    ("2A. Current Employment", "p2_2c_emp_state", "2.c. Employer Address - State", "select", False),
    ("2A. Current Employment", "p2_2d_emp_country", "2.d. Employer Address - Country", "text", True),
    ("2A. Current Employment", "p2_3_occupation", "3. Your Occupation", "text", True),
    ("2A. Current Employment", "p2_4_emp_from", "4. Employment Date From", "date", True),
    ("2A. Current Employment", "p2_5_emp_to", "5. Employment Date To (Present)", "text", True),

    ("2B. Previous Employment 1", "p2_6_prev_emp1", "6. Previous Employer 1 Name", "text", False),
    ("2B. Previous Employment 1", "p2_7_prev_emp1_city", "7. Previous Employer 1 - City", "text", False),
    ("2B. Previous Employment 1", "p2_8_prev_emp1_country", "8. Previous Employer 1 - Country", "text", False),
    ("2B. Previous Employment 1", "p2_9_prev_emp1_occupation", "9. Previous Employer 1 - Occupation", "text", False),
    ("2B. Previous Employment 1", "p2_10_prev_emp1_from", "10. Previous Employment 1 - Date From", "date", False),
    ("2B. Previous Employment 1", "p2_11_prev_emp1_to", "11. Previous Employment 1 - Date To", "date", False),

    # PART 3: INFORMATION ABOUT PARENTS
    ("3A. Father Information", "p3_1a_father_family", "1.a. Father's Family Name", "text", True),
    ("3A. Father Information", "p3_1b_father_given", "1.b. Father's Given Name", "text", True),
    ("3A. Father Information", "p3_2_father_dob", "2. Father's Date of Birth", "date", False),
    ("3A. Father Information", "p3_3_father_sex", "3. Father's Sex", "select", False),
    ("3A. Father Information", "p3_4_father_country_birth", "4. Father's Country of Birth", "text", False),
    ("3A. Father Information", "p3_5_father_city_residence", "5. Father's Current City of Residence", "text", False),

    ("3B. Mother Information", "p3_6a_mother_family", "6.a. Mother's Family Name", "text", True),
    ("3B. Mother Information", "p3_6b_mother_given", "6.b. Mother's Given Name", "text", True),
    ("3B. Mother Information", "p3_7_mother_maiden", "7. Mother's Maiden Name", "text", False),
    ("3B. Mother Information", "p3_8_mother_dob", "8. Mother's Date of Birth", "date", False),
    ("3B. Mother Information", "p3_9_mother_sex", "9. Mother's Sex", "select", False),
    ("3B. Mother Information", "p3_10_mother_country_birth", "10. Mother's Country of Birth", "text", False),
    ("3B. Mother Information", "p3_11_mother_city_residence", "11. Mother's Current City of Residence", "text", False),

    # PART 4: BENEFICIARY STATEMENT
    ("4. Beneficiary Statement", "p4_1_can_read", "1.a. I can read and understand English", "checkbox", False),
    ("4. Beneficiary Statement", "p4_1b_interpreter", "1.b. Someone interpreted this for me", "checkbox", False),
    ("4. Beneficiary Statement", "p4_2_language", "2. Language used by interpreter", "text", False),
    ("4. Beneficiary Statement", "p4_3_phone", "3. Beneficiary's Daytime Phone", "phone", True),
    ("4. Beneficiary Statement", "p4_4_mobile", "4. Beneficiary's Mobile Phone", "phone", False),
    ("4. Beneficiary Statement", "p4_5_email", "5. Beneficiary's Email Address", "email", False),
    ("4. Beneficiary Statement", "p4_6_signature_date", "6. Date of Signature", "date", True),

    # PART 5: INTERPRETER
    ("5. Interpreter Information", "p5_1a_interp_family", "1.a. Interpreter's Family Name", "text", False),
    ("5. Interpreter Information", "p5_1b_interp_given", "1.b. Interpreter's Given Name", "text", False),
    ("5. Interpreter Information", "p5_2_interp_phone", "2. Interpreter's Phone", "phone", False),
    ("5. Interpreter Information", "p5_3_language", "3. Language Interpreted", "text", False),

    # PART 6: PREPARER
    ("6. Preparer Information", "p6_1a_prep_family", "1.a. Preparer's Family Name", "text", False),
    ("6. Preparer Information", "p6_1b_prep_given", "1.b. Preparer's Given Name", "text", False),
    ("6. Preparer Information", "p6_2_prep_org", "2. Preparer's Organization", "text", False),
    ("6. Preparer Information", "p6_3_prep_phone", "3. Preparer's Phone", "phone", False),

    # PART 7: ADDITIONAL INFORMATION
    ("7. Additional Information", "p7_1_additional", "Additional Information", "textarea", False),
]

# =============================================================================
# I-864 - AFFIDAVIT OF SUPPORT (13 pages, ~200 fields)
# =============================================================================
I864_FIELDS = [
    # PART 1: BASIS FOR FILING
    ("1. Basis for Filing", "p1_1a_petitioner", "1.a. I am the petitioner", "checkbox", False),
    ("1. Basis for Filing", "p1_1b_substitute_sponsor", "1.b. I am a substitute sponsor", "checkbox", False),
    ("1. Basis for Filing", "p1_1c_joint_sponsor", "1.c. I am a joint sponsor", "checkbox", False),
    ("1. Basis for Filing", "p1_1d_intending_immigrant", "1.d. I am the intending immigrant/petitioner", "checkbox", False),
    ("1. Basis for Filing", "p1_2_first_joint", "2. I am the first joint sponsor", "checkbox", False),
    ("1. Basis for Filing", "p1_3_second_joint", "3. I am the second joint sponsor", "checkbox", False),

    # PART 2: PRINCIPAL IMMIGRANT INFORMATION
    ("2A. Principal Immigrant", "p2_1_a_number", "1. Alien Registration Number (A-Number)", "text", False),
    ("2A. Principal Immigrant", "p2_2_uscis_account", "2. USCIS Online Account Number", "text", False),
    ("2A. Principal Immigrant", "p2_3a_family_name", "3.a. Family Name (Last Name)", "text", True),
    ("2A. Principal Immigrant", "p2_3b_given_name", "3.b. Given Name (First Name)", "text", True),
    ("2A. Principal Immigrant", "p2_3c_middle_name", "3.c. Middle Name", "text", False),
    ("2A. Principal Immigrant", "p2_4_dob", "4. Date of Birth", "date", True),
    ("2A. Principal Immigrant", "p2_5_relationship", "5. Relationship to Sponsor", "select", True),

    # PART 3: IMMIGRANTS YOU ARE SPONSORING
    ("3. Immigrants Sponsored", "p3_1_total_sponsored", "1. Total number of immigrants in this affidavit", "number", True),

    # PART 4A: SPONSOR INFORMATION
    ("4A. Sponsor Information", "p4_1_a_number", "1. Sponsor's A-Number (if any)", "text", False),
    ("4A. Sponsor Information", "p4_2_ssn", "2. Sponsor's U.S. Social Security Number", "text", True),
    ("4A. Sponsor Information", "p4_3a_family_name", "3.a. Sponsor's Family Name (Last Name)", "text", True),
    ("4A. Sponsor Information", "p4_3b_given_name", "3.b. Sponsor's Given Name (First Name)", "text", True),
    ("4A. Sponsor Information", "p4_3c_middle_name", "3.c. Sponsor's Middle Name", "text", False),

    # PART 4B: SPONSOR MAILING ADDRESS
    ("4B. Sponsor Mailing Address", "p4_4a_street", "4.a. Street Number and Name", "text", True),
    ("4B. Sponsor Mailing Address", "p4_4b_apt", "4.b. Apt/Ste/Flr", "text", False),
    ("4B. Sponsor Mailing Address", "p4_4c_city", "4.c. City or Town", "text", True),
    ("4B. Sponsor Mailing Address", "p4_4d_state", "4.d. State", "select", True),
    ("4B. Sponsor Mailing Address", "p4_4e_zip", "4.e. ZIP Code", "text", True),

    # PART 4C: SPONSOR OTHER INFO
    ("4C. Sponsor Other Info", "p4_5_phone", "5. Sponsor's Daytime Phone Number", "phone", True),
    ("4C. Sponsor Other Info", "p4_6_dob", "6. Sponsor's Date of Birth", "date", True),
    ("4C. Sponsor Other Info", "p4_7_city_birth", "7. Sponsor's City/Town of Birth", "text", True),
    ("4C. Sponsor Other Info", "p4_8_country_birth", "8. Sponsor's Country of Birth", "text", True),
    ("4C. Sponsor Other Info", "p4_9_us_citizen", "9. I am a U.S. citizen / U.S. national / LPR", "select", True),
    ("4C. Sponsor Other Info", "p4_10_marital_status", "10. Sponsor's Marital Status", "select", True),

    # PART 5: SPONSOR'S HOUSEHOLD SIZE
    ("5. Household Size", "p5_1_yourself", "1. Yourself (count as 1)", "number", True),
    ("5. Household Size", "p5_2_spouse", "2. Number of people related to you by marriage", "number", False),
    ("5. Household Size", "p5_3_children", "3. Number of unmarried children under 21", "number", False),
    ("5. Household Size", "p5_4_other_dependents", "4. Number of other dependents", "number", False),
    ("5. Household Size", "p5_5_immigrants", "5. Number of immigrants in this affidavit", "number", True),
    ("5. Household Size", "p5_6_other_i864", "6. Number in other I-864s you filed", "number", False),
    ("5. Household Size", "p5_7_total_household", "7. Total Household Size", "number", True),

    # PART 6A: SPONSOR'S EMPLOYMENT
    ("6A. Sponsor Employment", "p6_1_employed", "1. I am currently employed", "checkbox", False),
    ("6A. Sponsor Employment", "p6_2_self_employed", "2. I am self-employed", "checkbox", False),
    ("6A. Sponsor Employment", "p6_3_retired", "3. I am retired", "checkbox", False),
    ("6A. Sponsor Employment", "p6_4_unemployed", "4. I am unemployed", "checkbox", False),
    ("6A. Sponsor Employment", "p6_5a_employer1", "5.a. Current Employer 1 Name", "text", False),
    ("6A. Sponsor Employment", "p6_5b_emp1_street", "5.b. Employer 1 - Street", "text", False),
    ("6A. Sponsor Employment", "p6_5c_emp1_city", "5.c. Employer 1 - City", "text", False),
    ("6A. Sponsor Employment", "p6_5d_emp1_state", "5.d. Employer 1 - State", "select", False),
    ("6A. Sponsor Employment", "p6_5e_emp1_zip", "5.e. Employer 1 - ZIP", "text", False),

    # PART 6B: SPONSOR'S INCOME
    ("6B. Sponsor Income", "p6_6_income_type", "6. My current individual annual income", "select", True),
    ("6B. Sponsor Income", "p6_7_annual_income", "7. My current annual income is $", "text", True),
    ("6B. Sponsor Income", "p6_8_tax_year1", "8. Income from most recent tax year", "text", False),
    ("6B. Sponsor Income", "p6_9_tax_year2", "9. Income from 2nd most recent tax year", "text", False),
    ("6B. Sponsor Income", "p6_10_tax_year3", "10. Income from 3rd most recent tax year", "text", False),

    # PART 7: USE OF ASSETS
    ("7. Assets", "p7_1_using_assets", "1. I am using assets to supplement income", "radio", True),
    ("7. Assets", "p7_2_savings", "2. Balance of savings accounts", "text", False),
    ("7. Assets", "p7_3_stocks", "3. Value of stocks, bonds, CDs", "text", False),
    ("7. Assets", "p7_4_real_estate", "4. Value of real estate (minus mortgages)", "text", False),
    ("7. Assets", "p7_5_other_assets", "5. Value of other assets", "text", False),
    ("7. Assets", "p7_6_total_assets", "6. Total Value of Assets", "text", False),

    # PART 8: SPONSOR'S CONTRACT
    ("8. Sponsor's Contract", "p8_1_agree", "1. I agree to provide support", "checkbox", True),
    ("8. Sponsor's Contract", "p8_2_understand_obligations", "2. I understand my obligations", "checkbox", True),
    ("8. Sponsor's Contract", "p8_3_phone", "3. Sponsor's Daytime Phone", "phone", True),
    ("8. Sponsor's Contract", "p8_4_mobile", "4. Sponsor's Mobile Phone", "phone", False),
    ("8. Sponsor's Contract", "p8_5_email", "5. Sponsor's Email Address", "email", False),
    ("8. Sponsor's Contract", "p8_6_signature_date", "6. Date of Signature", "date", True),

    # PART 9: INTERPRETER
    ("9. Interpreter Information", "p9_1a_interp_family", "1.a. Interpreter's Family Name", "text", False),
    ("9. Interpreter Information", "p9_1b_interp_given", "1.b. Interpreter's Given Name", "text", False),
    ("9. Interpreter Information", "p9_2_interp_phone", "2. Interpreter's Phone", "phone", False),
    ("9. Interpreter Information", "p9_3_language", "3. Language Interpreted", "text", False),

    # PART 10: PREPARER
    ("10. Preparer Information", "p10_1a_prep_family", "1.a. Preparer's Family Name", "text", False),
    ("10. Preparer Information", "p10_1b_prep_given", "1.b. Preparer's Given Name", "text", False),
    ("10. Preparer Information", "p10_2_prep_org", "2. Preparer's Organization", "text", False),
    ("10. Preparer Information", "p10_3_prep_phone", "3. Preparer's Phone", "phone", False),

    # PART 11: ADDITIONAL INFORMATION
    ("11. Additional Information", "p11_1_additional", "Additional Information", "textarea", False),
]

# =============================================================================
# I-765 - APPLICATION FOR EMPLOYMENT AUTHORIZATION (7 pages, ~120 fields)
# =============================================================================
I765_FIELDS = [
    # PART 1: REASON FOR APPLYING
    ("1. Reason for Applying", "p1_1a_initial", "1.a. Initial permission to accept employment", "checkbox", False),
    ("1. Reason for Applying", "p1_1b_replacement", "1.b. Replacement of lost/stolen/damaged EAD", "checkbox", False),
    ("1. Reason for Applying", "p1_1c_renewal", "1.c. Renewal of my permission to accept employment", "checkbox", False),

    # PART 2A: APPLICANT INFORMATION
    ("2A. Applicant Information", "p2_1_a_number", "1. Alien Registration Number (A-Number)", "text", False),
    ("2A. Applicant Information", "p2_2_uscis_account", "2. USCIS Online Account Number", "text", False),
    ("2A. Applicant Information", "p2_3_ssn", "3. U.S. Social Security Number", "text", False),
    ("2A. Applicant Information", "p2_4a_family_name", "4.a. Family Name (Last Name)", "text", True),
    ("2A. Applicant Information", "p2_4b_given_name", "4.b. Given Name (First Name)", "text", True),
    ("2A. Applicant Information", "p2_4c_middle_name", "4.c. Middle Name", "text", False),

    # PART 2B: OTHER NAMES USED
    ("2B. Other Names Used", "p2_5a_other_family", "5.a. Other Names Used - Family Name", "text", False),
    ("2B. Other Names Used", "p2_5b_other_given", "5.b. Other Names Used - Given Name", "text", False),

    # PART 2C: APPLICANT ADDRESS
    ("2C. U.S. Mailing Address", "p2_6a_street", "6.a. Street Number and Name", "text", True),
    ("2C. U.S. Mailing Address", "p2_6b_apt", "6.b. Apt/Ste/Flr", "text", False),
    ("2C. U.S. Mailing Address", "p2_6c_city", "6.c. City or Town", "text", True),
    ("2C. U.S. Mailing Address", "p2_6d_state", "6.d. State", "select", True),
    ("2C. U.S. Mailing Address", "p2_6e_zip", "6.e. ZIP Code", "text", True),

    # PART 2D: PHYSICAL ADDRESS
    ("2D. Physical Address", "p2_7_same_address", "7. Is physical address same as mailing?", "radio", True),
    ("2D. Physical Address", "p2_8a_phys_street", "8.a. Physical Address - Street", "text", False),
    ("2D. Physical Address", "p2_8b_phys_city", "8.b. Physical Address - City", "text", False),
    ("2D. Physical Address", "p2_8c_phys_state", "8.c. Physical Address - State", "select", False),
    ("2D. Physical Address", "p2_8d_phys_zip", "8.d. Physical Address - ZIP Code", "text", False),

    # PART 2E: APPLICANT OTHER INFO
    ("2E. Applicant Other Info", "p2_9_dob", "9. Date of Birth (mm/dd/yyyy)", "date", True),
    ("2E. Applicant Other Info", "p2_10_country_birth", "10. Country of Birth", "text", True),
    ("2E. Applicant Other Info", "p2_11_citizenship", "11. Country of Citizenship/Nationality", "text", True),
    ("2E. Applicant Other Info", "p2_12_sex", "12. Sex", "select", True),
    ("2E. Applicant Other Info", "p2_13_marital_status", "13. Marital Status", "select", True),

    # PART 2F: ARRIVAL INFORMATION
    ("2F. Arrival Information", "p2_14_last_entry_date", "14. Date of Last Entry to U.S.", "date", False),
    ("2F. Arrival Information", "p2_15_last_entry_place", "15. Place of Last Entry (City, State)", "text", False),
    ("2F. Arrival Information", "p2_16_i94_number", "16. I-94 Arrival-Departure Record Number", "text", False),
    ("2F. Arrival Information", "p2_17_current_status", "17. Current Immigration Status", "text", True),
    ("2F. Arrival Information", "p2_18_status_expires", "18. Status Expiration Date", "date", False),

    # PART 2G: PASSPORT INFO
    ("2G. Passport Information", "p2_19_passport", "19. Passport Number", "text", False),
    ("2G. Passport Information", "p2_20_passport_country", "20. Passport Country of Issuance", "text", False),
    ("2G. Passport Information", "p2_21_passport_expires", "21. Passport Expiration Date", "date", False),

    # PART 2H: ELIGIBILITY
    ("2H. Eligibility Category", "p2_22_eligibility", "22. Eligibility Category (e.g., (c)(9))", "text", True),
    ("2H. Eligibility Category", "p2_23_receipt_number", "23. Receipt Number of Pending Application", "text", False),

    # PART 2I: PREVIOUS EAD
    ("2I. Previous EAD", "p2_24_previous_ead", "24. Have you ever been issued an EAD?", "radio", True),
    ("2I. Previous EAD", "p2_25_ead_number", "25. Previous EAD USCIS Number", "text", False),
    ("2I. Previous EAD", "p2_26_ead_expires", "26. Previous EAD Expiration Date", "date", False),

    # PART 3: APPLICANT STATEMENT
    ("3. Applicant Statement", "p3_1_can_read", "1.a. I can read and understand English", "checkbox", False),
    ("3. Applicant Statement", "p3_1b_interpreter", "1.b. Someone interpreted this for me", "checkbox", False),
    ("3. Applicant Statement", "p3_2_phone", "2. Applicant's Daytime Phone", "phone", True),
    ("3. Applicant Statement", "p3_3_mobile", "3. Applicant's Mobile Phone", "phone", False),
    ("3. Applicant Statement", "p3_4_email", "4. Applicant's Email Address", "email", False),
    ("3. Applicant Statement", "p3_5_signature_date", "5. Date of Signature", "date", True),

    # PART 4: INTERPRETER
    ("4. Interpreter Information", "p4_1a_interp_family", "1.a. Interpreter's Family Name", "text", False),
    ("4. Interpreter Information", "p4_1b_interp_given", "1.b. Interpreter's Given Name", "text", False),
    ("4. Interpreter Information", "p4_2_interp_phone", "2. Interpreter's Phone", "phone", False),
    ("4. Interpreter Information", "p4_3_language", "3. Language Interpreted", "text", False),

    # PART 5: PREPARER
    ("5. Preparer Information", "p5_1a_prep_family", "1.a. Preparer's Family Name", "text", False),
    ("5. Preparer Information", "p5_1b_prep_given", "1.b. Preparer's Given Name", "text", False),
    ("5. Preparer Information", "p5_2_prep_org", "2. Preparer's Organization", "text", False),
    ("5. Preparer Information", "p5_3_prep_phone", "3. Preparer's Phone", "phone", False),

    # PART 6: ADDITIONAL INFORMATION
    ("6. Additional Information", "p6_1_additional", "Additional Information", "textarea", False),
]

# =============================================================================
# I-131 - APPLICATION FOR TRAVEL DOCUMENT (8 pages, ~150 fields)
# =============================================================================
I131_FIELDS = [
    # PART 1: APPLICATION TYPE
    ("1. Application Type", "p1_1a_reentry", "1.a. Reentry Permit", "checkbox", False),
    ("1. Application Type", "p1_1b_refugee_travel", "1.b. Refugee Travel Document", "checkbox", False),
    ("1. Application Type", "p1_1c_advance_parole", "1.c. Advance Parole Document", "checkbox", False),
    ("1. Application Type", "p1_1d_tps_travel", "1.d. TPS Travel Authorization", "checkbox", False),

    # PART 2A: APPLICANT INFORMATION
    ("2A. Applicant Information", "p2_1_a_number", "1. Alien Registration Number (A-Number)", "text", False),
    ("2A. Applicant Information", "p2_2_uscis_account", "2. USCIS Online Account Number", "text", False),
    ("2A. Applicant Information", "p2_3_ssn", "3. U.S. Social Security Number", "text", False),
    ("2A. Applicant Information", "p2_4a_family_name", "4.a. Family Name (Last Name)", "text", True),
    ("2A. Applicant Information", "p2_4b_given_name", "4.b. Given Name (First Name)", "text", True),
    ("2A. Applicant Information", "p2_4c_middle_name", "4.c. Middle Name", "text", False),

    # PART 2B: OTHER NAMES
    ("2B. Other Names Used", "p2_5a_other_family", "5.a. Other Names Used - Family Name", "text", False),
    ("2B. Other Names Used", "p2_5b_other_given", "5.b. Other Names Used - Given Name", "text", False),

    # PART 2C: U.S. MAILING ADDRESS
    ("2C. U.S. Mailing Address", "p2_6a_street", "6.a. Street Number and Name", "text", True),
    ("2C. U.S. Mailing Address", "p2_6b_apt", "6.b. Apt/Ste/Flr", "text", False),
    ("2C. U.S. Mailing Address", "p2_6c_city", "6.c. City or Town", "text", True),
    ("2C. U.S. Mailing Address", "p2_6d_state", "6.d. State", "select", True),
    ("2C. U.S. Mailing Address", "p2_6e_zip", "6.e. ZIP Code", "text", True),

    # PART 2D: APPLICANT OTHER INFO
    ("2D. Applicant Other Info", "p2_7_dob", "7. Date of Birth (mm/dd/yyyy)", "date", True),
    ("2D. Applicant Other Info", "p2_8_country_birth", "8. Country of Birth", "text", True),
    ("2D. Applicant Other Info", "p2_9_citizenship", "9. Country of Citizenship/Nationality", "text", True),
    ("2D. Applicant Other Info", "p2_10_sex", "10. Sex", "select", True),
    ("2D. Applicant Other Info", "p2_11_marital_status", "11. Marital Status", "select", True),

    # PART 3: BIOGRAPHIC INFORMATION
    ("3. Biographic Information", "p3_1_ethnicity", "1. Ethnicity - Hispanic or Latino?", "radio", True),
    ("3. Biographic Information", "p3_2a_race_white", "2.a. Race - White", "checkbox", False),
    ("3. Biographic Information", "p3_2b_race_asian", "2.b. Race - Asian", "checkbox", False),
    ("3. Biographic Information", "p3_2c_race_black", "2.c. Race - Black or African American", "checkbox", False),
    ("3. Biographic Information", "p3_3a_height_feet", "3.a. Height - Feet", "number", True),
    ("3. Biographic Information", "p3_3b_height_inches", "3.b. Height - Inches", "number", True),
    ("3. Biographic Information", "p3_4_weight", "4. Weight (Pounds)", "number", True),
    ("3. Biographic Information", "p3_5_eye_color", "5. Eye Color", "select", True),
    ("3. Biographic Information", "p3_6_hair_color", "6. Hair Color", "select", True),

    # PART 4: PROCESSING INFORMATION
    ("4A. Processing Information", "p4_1_current_status", "1. Current Immigration Status", "text", True),
    ("4A. Processing Information", "p4_2_status_date", "2. Date status was granted", "date", False),
    ("4A. Processing Information", "p4_3_last_entry_date", "3. Date of Last Entry to U.S.", "date", False),
    ("4A. Processing Information", "p4_4_last_entry_place", "4. Place of Last Entry (City, State)", "text", False),
    ("4A. Processing Information", "p4_5_i94_number", "5. I-94 Arrival-Departure Record Number", "text", False),

    # PART 4B: PASSPORT INFO
    ("4B. Passport Information", "p4_6_passport", "6. Passport Number", "text", False),
    ("4B. Passport Information", "p4_7_passport_country", "7. Passport Country of Issuance", "text", False),
    ("4B. Passport Information", "p4_8_passport_expires", "8. Passport Expiration Date", "date", False),

    # PART 7: PROPOSED TRAVEL
    ("7A. Proposed Travel", "p7_1_departure_date", "1. Proposed Departure Date", "date", True),
    ("7A. Proposed Travel", "p7_2_return_date", "2. Expected Return Date", "date", True),
    ("7A. Proposed Travel", "p7_3_countries", "3. List countries you will visit", "text", True),
    ("7A. Proposed Travel", "p7_4_purpose", "4. Purpose of Travel", "textarea", True),

    # PART 10: APPLICANT STATEMENT
    ("10. Applicant Statement", "p10_1_can_read", "1.a. I can read and understand English", "checkbox", False),
    ("10. Applicant Statement", "p10_1b_interpreter", "1.b. Someone interpreted this for me", "checkbox", False),
    ("10. Applicant Statement", "p10_2_phone", "2. Applicant's Daytime Phone", "phone", True),
    ("10. Applicant Statement", "p10_3_mobile", "3. Applicant's Mobile Phone", "phone", False),
    ("10. Applicant Statement", "p10_4_email", "4. Applicant's Email Address", "email", False),
    ("10. Applicant Statement", "p10_5_signature_date", "5. Date of Signature", "date", True),

    # PART 11: INTERPRETER
    ("11. Interpreter Information", "p11_1a_interp_family", "1.a. Interpreter's Family Name", "text", False),
    ("11. Interpreter Information", "p11_1b_interp_given", "1.b. Interpreter's Given Name", "text", False),
    ("11. Interpreter Information", "p11_2_interp_phone", "2. Interpreter's Phone", "phone", False),
    ("11. Interpreter Information", "p11_3_language", "3. Language Interpreted", "text", False),

    # PART 12: PREPARER
    ("12. Preparer Information", "p12_1a_prep_family", "1.a. Preparer's Family Name", "text", False),
    ("12. Preparer Information", "p12_1b_prep_given", "1.b. Preparer's Given Name", "text", False),
    ("12. Preparer Information", "p12_2_prep_org", "2. Preparer's Organization", "text", False),
    ("12. Preparer Information", "p12_3_prep_phone", "3. Preparer's Phone", "phone", False),

    # PART 13: ADDITIONAL INFORMATION
    ("13. Additional Information", "p13_1_additional", "Additional Information", "textarea", False),
]


def update_template(template_id, fields, name):
    """Update a template with new fields."""
    with engine.connect() as conn:
        # Delete existing fields
        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        # Insert all fields
        for i, field in enumerate(fields):
            section, field_name, label, field_type, required = field
            conn.execute(text("""
                INSERT INTO questionnaire_fields
                (template_id, field_name, label, field_type, is_required, section, "order")
                VALUES (:tid, :fname, :label, :ftype, :req, :section, :ord)
            """), {
                'tid': template_id,
                'fname': field_name,
                'label': label,
                'ftype': field_type,
                'req': required,
                'section': section,
                'ord': i + 1
            })

        conn.commit()
        print(f"Updated {name}: {len(fields)} fields")


def main():
    print("=" * 60)
    print("UPDATING ALL USCIS FORMS WITH ENGLISH SECTIONS")
    print("=" * 60)

    # Template IDs (from database)
    update_template(38, I130_FIELDS, "I-130")
    update_template(39, I130A_FIELDS, "I-130A")
    update_template(40, I485_FIELDS, "I-485")
    update_template(41, I864_FIELDS, "I-864")
    update_template(42, I765_FIELDS, "I-765")
    update_template(43, I131_FIELDS, "I-131")

    print("=" * 60)
    print("ALL FORMS UPDATED SUCCESSFULLY!")
    print("=" * 60)

    # Count totals
    total = len(I130_FIELDS) + len(I130A_FIELDS) + len(I485_FIELDS) + len(I864_FIELDS) + len(I765_FIELDS) + len(I131_FIELDS)
    print(f"\nTotal fields across all forms: {total}")


if __name__ == "__main__":
    main()
