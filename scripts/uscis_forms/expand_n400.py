#!/usr/bin/env python3
"""
Expand N-400 (Application for Naturalization) with ALL official USCIS fields.
Edition 01/20/25 - 14 pages, 16 parts.
Part 9 has 37+ Yes/No questions covering criminal, moral, and civic eligibility.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

N400_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT YOUR ELIGIBILITY
    # =========================================================================
    ("1. Eligibility", "p1_a_number", "Your 9 Digit A-Number", "text", False),
    ("1. Eligibility", "p1_1_reason", "1. Reason for Filing", "radio", True),
    ("1. Eligibility", "p1_1a_general", "A. General Provision", "checkbox", False),
    ("1. Eligibility", "p1_1b_spouse", "B. Spouse of U.S. Citizen", "checkbox", False),
    ("1. Eligibility", "p1_1c_vawa", "C. VAWA", "checkbox", False),
    ("1. Eligibility", "p1_1d_spouse_outside", "D. Spouse of U.S. Citizen in Qualified Employment Outside the United States", "checkbox", False),
    ("1. Eligibility", "p1_1d_uscis_office", "D. USCIS Field Office for Interview", "text", False),
    ("1. Eligibility", "p1_1e_military_hostilities", "E. Military Service During Period of Hostilities", "checkbox", False),
    ("1. Eligibility", "p1_1f_military_one_year", "F. At Least One Year of Honorable Military Service at Any Time", "checkbox", False),
    ("1. Eligibility", "p1_1g_other", "G. Other Reason for Filing Not Listed Above", "checkbox", False),
    ("1. Eligibility", "p1_1g_other_text", "G. Other Reason (specify)", "text", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT YOU (Person applying for naturalization)
    # =========================================================================

    # 2A. Current Legal Name
    ("2A. Current Legal Name", "p2_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("2A. Current Legal Name", "p2_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("2A. Current Legal Name", "p2_1c_middle_name", "1.c. Middle Name (if applicable)", "text", False),

    # 2B. Other Names Used Since Birth
    ("2B. Other Names Since Birth", "p2_2a_other_family", "2.a. Family Name (Last Name)", "text", False),
    ("2B. Other Names Since Birth", "p2_2b_other_given", "2.b. Given Name (First Name)", "text", False),
    ("2B. Other Names Since Birth", "p2_2c_other_middle", "2.c. Middle Name (if applicable)", "text", False),

    # 2C. Name Change (Optional)
    ("2C. Name Change", "p2_3_change_name", "3. Would you like to legally change your name?", "radio", False),
    ("2C. Name Change", "p2_3a_new_family", "3. New Family Name (Last Name)", "text", False),
    ("2C. Name Change", "p2_3b_new_given", "3. New Given Name (First Name)", "text", False),
    ("2C. Name Change", "p2_3c_new_middle", "3. New Middle Name (if applicable)", "text", False),

    # 2D. Other Information
    ("2D. Other Information", "p2_4_uscis_account", "4. USCIS Online Account Number (if any)", "text", False),
    ("2D. Other Information", "p2_5_sex", "5. Sex", "radio", True),
    ("2D. Other Information", "p2_6_dob", "6. Date of Birth (mm/dd/yyyy)", "date", True),
    ("2D. Other Information", "p2_7_lpr_date", "7. Date You Became a Lawful Permanent Resident (mm/dd/yyyy)", "date", True),
    ("2D. Other Information", "p2_8_country_birth", "8. Country of Birth", "text", True),
    ("2D. Other Information", "p2_9_country_citizenship", "9. Country of Citizenship or Nationality", "text", True),
    ("2D. Other Information", "p2_10_parent_citizen", "10. Was your mother or father a U.S. citizen before your 18th birthday?", "radio", False),
    ("2D. Other Information", "p2_11_disability", "11. Do you have a physical or developmental disability or mental impairment?", "radio", False),

    # 2E. Social Security Update
    ("2E. Social Security Update", "p2_12a_ssa_card", "12.a. Do you want the SSA to issue you an original or replacement Social Security card?", "radio", False),
    ("2E. Social Security Update", "p2_12b_ssn", "12.b. Social Security Number (SSN) (if any)", "text", False),
    ("2E. Social Security Update", "p2_12c_consent", "12.c. Consent for Disclosure to SSA?", "radio", False),

    # =========================================================================
    # PART 3: BIOGRAPHIC INFORMATION
    # =========================================================================
    ("3. Biographic Information", "p3_1_ethnicity", "1. Ethnicity (Select only one box)", "radio", True),
    ("3. Biographic Information", "p3_2_race_ai_an", "2. Race - American Indian or Alaska Native", "checkbox", False),
    ("3. Biographic Information", "p3_2_race_asian", "2. Race - Asian", "checkbox", False),
    ("3. Biographic Information", "p3_2_race_black", "2. Race - Black or African American", "checkbox", False),
    ("3. Biographic Information", "p3_2_race_nhpi", "2. Race - Native Hawaiian or Other Pacific Islander", "checkbox", False),
    ("3. Biographic Information", "p3_2_race_white", "2. Race - White", "checkbox", False),
    ("3. Biographic Information", "p3_3_height_feet", "3. Height - Feet", "text", True),
    ("3. Biographic Information", "p3_3_height_inches", "3. Height - Inches", "text", True),
    ("3. Biographic Information", "p3_4_weight", "4. Weight (Pounds)", "text", True),
    ("3. Biographic Information", "p3_5_eye_color", "5. Eye Color (Select only one box)", "select", True),
    ("3. Biographic Information", "p3_6_hair_color", "6. Hair Color (Select only one box)", "select", True),

    # =========================================================================
    # PART 4: INFORMATION ABOUT YOUR RESIDENCE
    # =========================================================================

    # 4A. Current Physical Address
    ("4A. Current Physical Address", "p4_1_care_of", "1. In Care Of Name (if any)", "text", False),
    ("4A. Current Physical Address", "p4_1a_street", "1.a. Street Number and Name", "text", True),
    ("4A. Current Physical Address", "p4_1b_apt_type", "1.b. Apt./Ste./Flr.", "select", False),
    ("4A. Current Physical Address", "p4_1c_apt_number", "1.c. Number", "text", False),
    ("4A. Current Physical Address", "p4_1d_city", "1.d. City or Town", "text", True),
    ("4A. Current Physical Address", "p4_1e_state", "1.e. State", "select", True),
    ("4A. Current Physical Address", "p4_1f_zip", "1.f. ZIP Code", "text", True),
    ("4A. Current Physical Address", "p4_1g_province", "1.g. Province", "text", False),
    ("4A. Current Physical Address", "p4_1h_postal", "1.h. Postal Code", "text", False),
    ("4A. Current Physical Address", "p4_1i_country", "1.i. Country", "text", False),
    ("4A. Current Physical Address", "p4_1j_date_from", "1.j. Dates of Residence: From (mm/dd/yyyy)", "date", True),
    ("4A. Current Physical Address", "p4_1k_date_to", "1.k. Dates of Residence: To (mm/dd/yyyy)", "text", False),

    # 4B. Previous Address 1
    ("4B. Previous Address 1", "p4_prev1_street", "Previous Address 1 - Street Number and Name", "text", False),
    ("4B. Previous Address 1", "p4_prev1_city", "Previous Address 1 - City or Town", "text", False),
    ("4B. Previous Address 1", "p4_prev1_state", "Previous Address 1 - State/Province", "text", False),
    ("4B. Previous Address 1", "p4_prev1_zip", "Previous Address 1 - ZIP/Postal Code", "text", False),
    ("4B. Previous Address 1", "p4_prev1_country", "Previous Address 1 - Country", "text", False),
    ("4B. Previous Address 1", "p4_prev1_from", "Previous Address 1 - Date From (mm/dd/yyyy)", "date", False),
    ("4B. Previous Address 1", "p4_prev1_to", "Previous Address 1 - Date To (mm/dd/yyyy)", "date", False),

    # 4C. Previous Address 2
    ("4C. Previous Address 2", "p4_prev2_street", "Previous Address 2 - Street Number and Name", "text", False),
    ("4C. Previous Address 2", "p4_prev2_city", "Previous Address 2 - City or Town", "text", False),
    ("4C. Previous Address 2", "p4_prev2_state", "Previous Address 2 - State/Province", "text", False),
    ("4C. Previous Address 2", "p4_prev2_zip", "Previous Address 2 - ZIP/Postal Code", "text", False),
    ("4C. Previous Address 2", "p4_prev2_country", "Previous Address 2 - Country", "text", False),
    ("4C. Previous Address 2", "p4_prev2_from", "Previous Address 2 - Date From (mm/dd/yyyy)", "date", False),
    ("4C. Previous Address 2", "p4_prev2_to", "Previous Address 2 - Date To (mm/dd/yyyy)", "date", False),

    # 4D. Previous Address 3
    ("4D. Previous Address 3", "p4_prev3_street", "Previous Address 3 - Street Number and Name", "text", False),
    ("4D. Previous Address 3", "p4_prev3_city", "Previous Address 3 - City or Town", "text", False),
    ("4D. Previous Address 3", "p4_prev3_state", "Previous Address 3 - State/Province", "text", False),
    ("4D. Previous Address 3", "p4_prev3_zip", "Previous Address 3 - ZIP/Postal Code", "text", False),
    ("4D. Previous Address 3", "p4_prev3_country", "Previous Address 3 - Country", "text", False),
    ("4D. Previous Address 3", "p4_prev3_from", "Previous Address 3 - Date From (mm/dd/yyyy)", "date", False),
    ("4D. Previous Address 3", "p4_prev3_to", "Previous Address 3 - Date To (mm/dd/yyyy)", "date", False),

    # 4E. Mailing Address
    ("4E. Mailing Address", "p4_2_same_as_physical", "2. Is your current physical address also your current mailing address?", "radio", True),
    ("4E. Mailing Address", "p4_3_mail_care_of", "3. Mailing Address - In Care Of Name", "text", False),
    ("4E. Mailing Address", "p4_3a_mail_street", "3.a. Mailing Address - Street Number and Name", "text", False),
    ("4E. Mailing Address", "p4_3b_mail_apt_type", "3.b. Mailing Address - Apt./Ste./Flr.", "select", False),
    ("4E. Mailing Address", "p4_3c_mail_apt_number", "3.c. Mailing Address - Number", "text", False),
    ("4E. Mailing Address", "p4_3d_mail_city", "3.d. Mailing Address - City or Town", "text", False),
    ("4E. Mailing Address", "p4_3e_mail_state", "3.e. Mailing Address - State", "select", False),
    ("4E. Mailing Address", "p4_3f_mail_zip", "3.f. Mailing Address - ZIP Code", "text", False),
    ("4E. Mailing Address", "p4_3g_mail_province", "3.g. Mailing Address - Province", "text", False),
    ("4E. Mailing Address", "p4_3h_mail_postal", "3.h. Mailing Address - Postal Code", "text", False),
    ("4E. Mailing Address", "p4_3i_mail_country", "3.i. Mailing Address - Country", "text", False),

    # =========================================================================
    # PART 5: INFORMATION ABOUT YOUR MARITAL HISTORY
    # =========================================================================
    ("5A. Marital Status", "p5_1_marital_status", "1. What is your current marital status?", "select", True),
    ("5A. Marital Status", "p5_2_spouse_armed_forces", "2. Is your spouse a current member of the U.S. armed forces?", "radio", False),
    ("5A. Marital Status", "p5_3_times_married", "3. How many times have you been married?", "text", False),

    # 5B. Your Current Marriage
    ("5B. Current Marriage", "p5_4a_spouse_family", "4.a. Current Spouse's Family Name (Last Name)", "text", False),
    ("5B. Current Marriage", "p5_4a_spouse_given", "4.a. Current Spouse's Given Name (First Name)", "text", False),
    ("5B. Current Marriage", "p5_4a_spouse_middle", "4.a. Current Spouse's Middle Name (if applicable)", "text", False),
    ("5B. Current Marriage", "p5_4b_spouse_dob", "4.b. Current Spouse's Date of Birth (mm/dd/yyyy)", "date", False),
    ("5B. Current Marriage", "p5_4c_marriage_date", "4.c. Date You Entered into Marriage with Current Spouse (mm/dd/yyyy)", "date", False),
    ("5B. Current Marriage", "p5_4d_spouse_address_same", "4.d. Is your current spouse's present physical address the same as your physical address?", "radio", False),
    ("5B. Current Marriage", "p5_5a_spouse_citizen_how", "5.a. When did your current spouse become a U.S. citizen?", "radio", False),
    ("5B. Current Marriage", "p5_5b_spouse_citizen_date", "5.b. Date Your Current Spouse Became a U.S. Citizen (mm/dd/yyyy)", "date", False),
    ("5B. Current Marriage", "p5_6_spouse_a_number", "6. Current Spouse's Alien Registration Number (A-Number) (if any)", "text", False),
    ("5B. Current Marriage", "p5_7_spouse_times_married", "7. How many times has your current spouse been married?", "text", False),
    ("5B. Current Marriage", "p5_8_spouse_employer", "8. Current Spouse's Current Employer or Company", "text", False),

    # =========================================================================
    # PART 6: INFORMATION ABOUT YOUR CHILDREN
    # =========================================================================
    ("6. Children", "p6_1_total_children", "1. Indicate your total number of children under 18 years of age.", "text", False),

    # Child 1
    ("6A. Child 1", "p6_2_child1_name", "2. Child 1 - Son or Daughter's Name (First Name and Family Name)", "text", False),
    ("6A. Child 1", "p6_2_child1_dob", "2. Child 1 - Date of Birth (mm/dd/yyyy)", "date", False),
    ("6A. Child 1", "p6_2_child1_residence", "2. Child 1 - Residence", "select", False),
    ("6A. Child 1", "p6_2_child1_relationship", "2. Child 1 - Relationship", "select", False),
    ("6A. Child 1", "p6_2_child1_support", "2. Child 1 - Are you providing support?", "radio", False),

    # Child 2
    ("6B. Child 2", "p6_2_child2_name", "2. Child 2 - Son or Daughter's Name (First Name and Family Name)", "text", False),
    ("6B. Child 2", "p6_2_child2_dob", "2. Child 2 - Date of Birth (mm/dd/yyyy)", "date", False),
    ("6B. Child 2", "p6_2_child2_residence", "2. Child 2 - Residence", "select", False),
    ("6B. Child 2", "p6_2_child2_relationship", "2. Child 2 - Relationship", "select", False),
    ("6B. Child 2", "p6_2_child2_support", "2. Child 2 - Are you providing support?", "radio", False),

    # Child 3
    ("6C. Child 3", "p6_2_child3_name", "2. Child 3 - Son or Daughter's Name (First Name and Family Name)", "text", False),
    ("6C. Child 3", "p6_2_child3_dob", "2. Child 3 - Date of Birth (mm/dd/yyyy)", "date", False),
    ("6C. Child 3", "p6_2_child3_residence", "2. Child 3 - Residence", "select", False),
    ("6C. Child 3", "p6_2_child3_relationship", "2. Child 3 - Relationship", "select", False),
    ("6C. Child 3", "p6_2_child3_support", "2. Child 3 - Are you providing support?", "radio", False),

    # =========================================================================
    # PART 7: INFORMATION ABOUT YOUR EMPLOYMENT AND SCHOOLS YOU ATTENDED
    # =========================================================================

    # Employment/School 1 (Current)
    ("7A. Employment/School 1", "p7_1_emp1_name", "1. Employer or School 1 - Name", "text", False),
    ("7A. Employment/School 1", "p7_1_emp1_city", "1. Employer or School 1 - City/Town", "text", False),
    ("7A. Employment/School 1", "p7_1_emp1_state", "1. Employer or School 1 - State/Province", "text", False),
    ("7A. Employment/School 1", "p7_1_emp1_zip", "1. Employer or School 1 - ZIP/Postal Code", "text", False),
    ("7A. Employment/School 1", "p7_1_emp1_country", "1. Employer or School 1 - Country", "text", False),
    ("7A. Employment/School 1", "p7_1_emp1_from", "1. Employer or School 1 - Date From (mm/dd/yyyy)", "date", False),
    ("7A. Employment/School 1", "p7_1_emp1_to", "1. Employer or School 1 - Date To (mm/dd/yyyy)", "text", False),
    ("7A. Employment/School 1", "p7_1_emp1_occupation", "1. Employer or School 1 - Occupation or Field of Study", "text", False),

    # Employment/School 2
    ("7B. Employment/School 2", "p7_1_emp2_name", "1. Employer or School 2 - Name", "text", False),
    ("7B. Employment/School 2", "p7_1_emp2_city", "1. Employer or School 2 - City/Town", "text", False),
    ("7B. Employment/School 2", "p7_1_emp2_state", "1. Employer or School 2 - State/Province", "text", False),
    ("7B. Employment/School 2", "p7_1_emp2_zip", "1. Employer or School 2 - ZIP/Postal Code", "text", False),
    ("7B. Employment/School 2", "p7_1_emp2_country", "1. Employer or School 2 - Country", "text", False),
    ("7B. Employment/School 2", "p7_1_emp2_from", "1. Employer or School 2 - Date From (mm/dd/yyyy)", "date", False),
    ("7B. Employment/School 2", "p7_1_emp2_to", "1. Employer or School 2 - Date To (mm/dd/yyyy)", "date", False),
    ("7B. Employment/School 2", "p7_1_emp2_occupation", "1. Employer or School 2 - Occupation or Field of Study", "text", False),

    # Employment/School 3
    ("7C. Employment/School 3", "p7_1_emp3_name", "1. Employer or School 3 - Name", "text", False),
    ("7C. Employment/School 3", "p7_1_emp3_city", "1. Employer or School 3 - City/Town", "text", False),
    ("7C. Employment/School 3", "p7_1_emp3_state", "1. Employer or School 3 - State/Province", "text", False),
    ("7C. Employment/School 3", "p7_1_emp3_zip", "1. Employer or School 3 - ZIP/Postal Code", "text", False),
    ("7C. Employment/School 3", "p7_1_emp3_country", "1. Employer or School 3 - Country", "text", False),
    ("7C. Employment/School 3", "p7_1_emp3_from", "1. Employer or School 3 - Date From (mm/dd/yyyy)", "date", False),
    ("7C. Employment/School 3", "p7_1_emp3_to", "1. Employer or School 3 - Date To (mm/dd/yyyy)", "date", False),
    ("7C. Employment/School 3", "p7_1_emp3_occupation", "1. Employer or School 3 - Occupation or Field of Study", "text", False),

    # =========================================================================
    # PART 8: TIME OUTSIDE THE UNITED STATES
    # =========================================================================

    # Trip 1
    ("8A. Trip 1", "p8_trip1_left", "Trip 1 - Date You Left the United States (mm/dd/yyyy)", "date", False),
    ("8A. Trip 1", "p8_trip1_returned", "Trip 1 - Date You Returned to the United States (mm/dd/yyyy)", "date", False),
    ("8A. Trip 1", "p8_trip1_countries", "Trip 1 - Countries to Which You Traveled", "text", False),

    # Trip 2
    ("8B. Trip 2", "p8_trip2_left", "Trip 2 - Date You Left the United States (mm/dd/yyyy)", "date", False),
    ("8B. Trip 2", "p8_trip2_returned", "Trip 2 - Date You Returned to the United States (mm/dd/yyyy)", "date", False),
    ("8B. Trip 2", "p8_trip2_countries", "Trip 2 - Countries to Which You Traveled", "text", False),

    # Trip 3
    ("8C. Trip 3", "p8_trip3_left", "Trip 3 - Date You Left the United States (mm/dd/yyyy)", "date", False),
    ("8C. Trip 3", "p8_trip3_returned", "Trip 3 - Date You Returned to the United States (mm/dd/yyyy)", "date", False),
    ("8C. Trip 3", "p8_trip3_countries", "Trip 3 - Countries to Which You Traveled", "text", False),

    # Trip 4
    ("8D. Trip 4", "p8_trip4_left", "Trip 4 - Date You Left the United States (mm/dd/yyyy)", "date", False),
    ("8D. Trip 4", "p8_trip4_returned", "Trip 4 - Date You Returned to the United States (mm/dd/yyyy)", "date", False),
    ("8D. Trip 4", "p8_trip4_countries", "Trip 4 - Countries to Which You Traveled", "text", False),

    # Trip 5
    ("8E. Trip 5", "p8_trip5_left", "Trip 5 - Date You Left the United States (mm/dd/yyyy)", "date", False),
    ("8E. Trip 5", "p8_trip5_returned", "Trip 5 - Date You Returned to the United States (mm/dd/yyyy)", "date", False),
    ("8E. Trip 5", "p8_trip5_countries", "Trip 5 - Countries to Which You Traveled", "text", False),

    # =========================================================================
    # PART 9: ADDITIONAL INFORMATION ABOUT YOU
    # This is the critical eligibility section with 37+ Yes/No questions
    # =========================================================================

    # Civic Questions (1-4)
    ("9A. Civic Questions", "p9_1_claimed_citizen", "1. Have you EVER claimed to be a U.S. citizen (in writing or any other way)?", "radio", True),
    ("9A. Civic Questions", "p9_2_registered_vote", "2. Have you EVER registered to vote or voted in any Federal, state, or local election in the United States?", "radio", True),
    ("9A. Civic Questions", "p9_3_overdue_taxes", "3. Do you currently owe any overdue Federal, state, or local taxes in the United States?", "radio", True),
    ("9A. Civic Questions", "p9_4_nonresident_alien", "4. Since you became a lawful permanent resident, have you called yourself a \"nonresident alien\" on a Federal, state, or local tax return?", "radio", True),

    # Affiliations (5a-5b)
    ("9B. Affiliations", "p9_5a_communist", "5.a. Have you EVER been a member of, involved in, or associated with any Communist or totalitarian party anywhere in the world?", "radio", True),
    ("9B. Affiliations", "p9_5b_advocated", "5.b. Have you EVER advocated or been associated with any group that advocated: opposition to organized government, world communism, totalitarian dictatorship, overthrow by force, assaulting/killing government officers, or sabotage?", "radio", True),

    # Terrorism/Violence (6a-6c)
    ("9C. Terrorism/Violence", "p9_6a_weapon_explosive", "6.a. Have you EVER used a weapon or explosive with intent to harm another person or cause damage to property?", "radio", True),
    ("9C. Terrorism/Violence", "p9_6b_kidnapping", "6.b. Have you EVER engaged in kidnapping, assassination, or hijacking or sabotage of transportation?", "radio", True),
    ("9C. Terrorism/Violence", "p9_6c_threatened", "6.c. Have you EVER threatened, attempted, conspired, prepared, planned, advocated for, or incited others to commit any of the acts in 6.a. or 6.b.?", "radio", True),

    # Human Rights Violations (7a-7g)
    ("9D. Human Rights Violations", "p9_7a_torture", "7.a. Have you EVER ordered, incited, called for, committed, assisted, helped with, or otherwise participated in: Torture?", "radio", True),
    ("9D. Human Rights Violations", "p9_7b_genocide", "7.b. Genocide?", "radio", True),
    ("9D. Human Rights Violations", "p9_7c_killing", "7.c. Killing or trying to kill any person?", "radio", True),
    ("9D. Human Rights Violations", "p9_7d_injuring", "7.d. Intentionally and severely injuring or trying to injure any person?", "radio", True),
    ("9D. Human Rights Violations", "p9_7e_sexual_contact", "7.e. Any kind of sexual contact or activity with any person who did not consent or was unable to consent?", "radio", True),
    ("9D. Human Rights Violations", "p9_7f_religion", "7.f. Not letting someone practice his or her religion?", "radio", True),
    ("9D. Human Rights Violations", "p9_7g_persecution", "7.g. Causing harm or suffering to any person because of his or her race, religion, national origin, membership in a particular social group, or political opinion?", "radio", True),

    # Military/Armed Groups (8a-8b)
    ("9E. Military/Armed Groups", "p9_8a_military_police", "8.a. Have you EVER served in, been a member of, assisted, or participated in any military or police unit?", "radio", True),
    ("9E. Military/Armed Groups", "p9_8b_armed_group", "8.b. Have you EVER served in, been a member of, assisted, or participated in any armed group (paramilitary, self-defense, vigilante, rebel, guerrilla)?", "radio", True),

    # Detention/Weapons (9-14)
    ("9F. Detention/Weapons", "p9_9_detention", "9. Have you EVER worked, volunteered, or otherwise served in a place where people were detained (prison, jail, camp, detention facility)?", "radio", True),
    ("9F. Detention/Weapons", "p9_10a_group_weapons", "10.a. Were you EVER a part of any group that used a weapon against any person, or threatened to do so?", "radio", True),
    ("9F. Detention/Weapons", "p9_10b_used_weapon", "10.b. If 'Yes' to 10.a., did you ever use a weapon against another person?", "radio", False),
    ("9F. Detention/Weapons", "p9_10c_threatened_weapon", "10.c. If 'Yes' to 10.a., did you ever threaten to use a weapon against another person?", "radio", False),
    ("9F. Detention/Weapons", "p9_11_sold_weapons", "11. Have you EVER sold, provided, or transported weapons, or assisted any person in doing so?", "radio", True),
    ("9F. Detention/Weapons", "p9_12_weapons_training", "12. Have you EVER received any weapons training, paramilitary training, or other military-type training?", "radio", True),
    ("9F. Detention/Weapons", "p9_13_recruited_children", "13. Have you EVER recruited, enlisted, conscripted, or used any person under 15 years of age to serve in or help an armed group?", "radio", True),
    ("9F. Detention/Weapons", "p9_14_used_children", "14. Have you EVER used any person under 15 years of age to take part in hostilities or attempted or worked with others to do so?", "radio", True),

    # Criminal History (15a-16)
    ("9G. Criminal History", "p9_15a_crime_not_arrested", "15.a. Have you EVER committed, agreed to commit, asked someone else to commit, helped commit, or tried to commit a crime or offense for which you were NOT arrested?", "radio", True),
    ("9G. Criminal History", "p9_15b_ever_arrested", "15.b. Have you EVER been arrested, cited, detained or confined by any law enforcement officer, military official, or immigration official for any reason?", "radio", True),

    # Crime table - Row 1
    ("9G. Crime 1", "p9_crime1_offense", "Crime 1 - What was the crime or offense?", "text", False),
    ("9G. Crime 1", "p9_crime1_date", "Crime 1 - Date of the Crime or Offense (mm/dd/yyyy)", "date", False),
    ("9G. Crime 1", "p9_crime1_conviction_date", "Crime 1 - Date of conviction or guilty plea (mm/dd/yyyy)", "date", False),
    ("9G. Crime 1", "p9_crime1_place", "Crime 1 - Place of Crime or Offense (City or Town, State, Country)", "text", False),
    ("9G. Crime 1", "p9_crime1_result", "Crime 1 - Result or disposition of the arrest, citation, or charge", "text", False),
    ("9G. Crime 1", "p9_crime1_sentence", "Crime 1 - What was your sentence?", "text", False),

    # Crime table - Row 2
    ("9G. Crime 2", "p9_crime2_offense", "Crime 2 - What was the crime or offense?", "text", False),
    ("9G. Crime 2", "p9_crime2_date", "Crime 2 - Date of the Crime or Offense (mm/dd/yyyy)", "date", False),
    ("9G. Crime 2", "p9_crime2_conviction_date", "Crime 2 - Date of conviction or guilty plea (mm/dd/yyyy)", "date", False),
    ("9G. Crime 2", "p9_crime2_place", "Crime 2 - Place of Crime or Offense (City or Town, State, Country)", "text", False),
    ("9G. Crime 2", "p9_crime2_result", "Crime 2 - Result or disposition of the arrest, citation, or charge", "text", False),
    ("9G. Crime 2", "p9_crime2_sentence", "Crime 2 - What was your sentence?", "text", False),

    # Crime table - Row 3
    ("9G. Crime 3", "p9_crime3_offense", "Crime 3 - What was the crime or offense?", "text", False),
    ("9G. Crime 3", "p9_crime3_date", "Crime 3 - Date of the Crime or Offense (mm/dd/yyyy)", "date", False),
    ("9G. Crime 3", "p9_crime3_conviction_date", "Crime 3 - Date of conviction or guilty plea (mm/dd/yyyy)", "date", False),
    ("9G. Crime 3", "p9_crime3_place", "Crime 3 - Place of Crime or Offense (City or Town, State, Country)", "text", False),
    ("9G. Crime 3", "p9_crime3_result", "Crime 3 - Result or disposition of the arrest, citation, or charge", "text", False),
    ("9G. Crime 3", "p9_crime3_sentence", "Crime 3 - What was your sentence?", "text", False),

    # Crime table - Row 4
    ("9G. Crime 4", "p9_crime4_offense", "Crime 4 - What was the crime or offense?", "text", False),
    ("9G. Crime 4", "p9_crime4_date", "Crime 4 - Date of the Crime or Offense (mm/dd/yyyy)", "date", False),
    ("9G. Crime 4", "p9_crime4_conviction_date", "Crime 4 - Date of conviction or guilty plea (mm/dd/yyyy)", "date", False),
    ("9G. Crime 4", "p9_crime4_place", "Crime 4 - Place of Crime or Offense (City or Town, State, Country)", "text", False),
    ("9G. Crime 4", "p9_crime4_result", "Crime 4 - Result or disposition of the arrest, citation, or charge", "text", False),
    ("9G. Crime 4", "p9_crime4_sentence", "Crime 4 - What was your sentence?", "text", False),

    ("9G. Criminal History", "p9_16_completed_sentence", "16. If you received a suspended sentence, were placed on probation, or were paroled, have you completed your suspended sentence, probation, or parole?", "radio", False),

    # Moral Character (17a-19)
    ("9H. Moral Character", "p9_17a_prostitution", "17.a. Have you EVER engaged in prostitution, attempted to procure or import prostitutes, or received proceeds from prostitution?", "radio", True),
    ("9H. Moral Character", "p9_17b_drugs", "17.b. Have you EVER manufactured, cultivated, produced, distributed, dispensed, sold, or smuggled (trafficked) any controlled substances, illegal drugs, narcotics, or drug paraphernalia?", "radio", True),
    ("9H. Moral Character", "p9_17c_polygamy", "17.c. Have you EVER been married to more than one person at the same time?", "radio", True),
    ("9H. Moral Character", "p9_17d_marriage_fraud", "17.d. Have you EVER married someone in order to obtain an immigration benefit?", "radio", True),
    ("9H. Moral Character", "p9_17e_helped_enter", "17.e. Have you EVER helped anyone to enter, or try to enter, the United States illegally?", "radio", True),
    ("9H. Moral Character", "p9_17f_gambling", "17.f. Have you EVER gambled illegally or received income from illegal gambling?", "radio", True),
    ("9H. Moral Character", "p9_17g_support_dependents", "17.g. Have you EVER failed to support your dependents (pay child support) or to pay alimony (court-ordered financial support after divorce or separation)?", "radio", True),
    ("9H. Moral Character", "p9_17h_misrepresentation", "17.h. Have you EVER made any misrepresentation to obtain any public benefit in the United States?", "radio", True),
    ("9H. Moral Character", "p9_18_false_info", "18. Have you EVER given any U.S. Government officials any information or documentation that was false, fraudulent, or misleading?", "radio", True),
    ("9H. Moral Character", "p9_19_lied_for_entry", "19. Have you EVER lied to any U.S. Government officials to gain entry or admission into the United States or to gain immigration benefits while in the United States?", "radio", True),

    # Removal/Deportation (20-21)
    ("9I. Removal/Deportation", "p9_20_removal_proceedings", "20. Have you EVER been placed in removal, rescission, or deportation proceedings?", "radio", True),
    ("9I. Removal/Deportation", "p9_21_removed_deported", "21. Have you EVER been removed or deported from the United States?", "radio", True),

    # Selective Service (22a-22c)
    ("9J. Selective Service", "p9_22a_male_18_26", "22.a. Are you a male who lived in the United States at any time between your 18th and 26th birthdays?", "radio", False),
    ("9J. Selective Service", "p9_22b_registered_ss", "22.b. If 'Yes' to 22.a., did you register for the Selective Service?", "radio", False),
    ("9J. Selective Service", "p9_22c_date_registered", "22.c. Date Registered (mm/dd/yyyy)", "date", False),
    ("9J. Selective Service", "p9_22c_ss_number", "22.c. Selective Service Number", "text", False),

    # Military Service - Draft (23-24)
    ("9K. Draft/Military Exemption", "p9_23_left_to_avoid_draft", "23. Have you EVER left the United States to avoid being drafted into the U.S. armed forces?", "radio", True),
    ("9K. Draft/Military Exemption", "p9_24_exemption", "24. Have you EVER applied for any kind of exemption from military service in the U.S. armed forces?", "radio", True),

    # Military Service History (25-29)
    ("9L. Military Service", "p9_25_served", "25. Have you EVER served in the U.S. armed forces?", "radio", True),
    ("9L. Military Service", "p9_26a_currently_member", "26.a. Are you currently a member of the U.S. armed forces?", "radio", False),
    ("9L. Military Service", "p9_26b_deploy", "26.b. If 'Yes' to 26.a., are you scheduled to deploy outside the United States within the next 3 months?", "radio", False),
    ("9L. Military Service", "p9_26c_stationed_outside", "26.c. If 'Yes' to 26.a., are you currently stationed outside the United States?", "radio", False),
    ("9L. Military Service", "p9_26d_former_outside", "26.d. If 'No' to 26.a., are you a former U.S. military service member currently residing outside of the U.S.?", "radio", False),
    ("9L. Military Service", "p9_27_court_martialed", "27. Have you EVER been court-martialed or received a discharge characterized as other than honorable, bad conduct, or dishonorable?", "radio", False),
    ("9L. Military Service", "p9_28_discharged_alien", "28. Have you EVER been discharged from training or service in the U.S. armed forces because you were an alien?", "radio", False),
    ("9L. Military Service", "p9_29_deserted", "29. Have you EVER deserted from the U.S. armed forces?", "radio", False),

    # Oath of Allegiance (30a-37)
    ("9M. Oath of Allegiance", "p9_30a_title_nobility", "30.a. Do you now have, or did you EVER have, a hereditary title or an order of nobility in any foreign country?", "radio", True),
    ("9M. Oath of Allegiance", "p9_30b_give_up_titles", "30.b. If 'Yes' to 30.a., are you willing to give up any inherited titles or orders of nobility?", "radio", False),
    ("9M. Oath of Allegiance", "p9_30b_titles_list", "30.b. List titles that you have in a foreign country", "text", False),
    ("9M. Oath of Allegiance", "p9_31_support_constitution", "31. Do you support the Constitution and form of Government of the United States?", "radio", True),
    ("9M. Oath of Allegiance", "p9_32_understand_oath", "32. Do you understand the full Oath of Allegiance to the United States?", "radio", True),
    ("9M. Oath of Allegiance", "p9_33_unable_oath", "33. Are you unable to take the Oath of Allegiance because of a physical or developmental disability or mental impairment?", "radio", True),
    ("9M. Oath of Allegiance", "p9_34_willing_oath", "34. Are you willing to take the full Oath of Allegiance to the United States?", "radio", True),
    ("9M. Oath of Allegiance", "p9_35_bear_arms", "35. If the law requires it, are you willing to bear arms (carry weapons) on behalf of the United States?", "radio", True),
    ("9M. Oath of Allegiance", "p9_36_noncombatant", "36. If the law requires it, are you willing to perform noncombatant services in the U.S. armed forces?", "radio", True),
    ("9M. Oath of Allegiance", "p9_37_civilian_work", "37. If the law requires it, are you willing to perform work of national importance under civilian direction?", "radio", True),

    # =========================================================================
    # PART 10: REQUEST FOR A FEE REDUCTION
    # =========================================================================
    ("10. Fee Reduction", "p10_1_income_below_400", "1. My household income is less than or equal to 400% of the Federal Poverty Guidelines", "radio", False),
    ("10. Fee Reduction", "p10_2_total_income", "2. Total household income", "text", False),
    ("10. Fee Reduction", "p10_3_household_size", "3. My household size is", "text", False),
    ("10. Fee Reduction", "p10_4_members_earning", "4. Total number of household members earning income including yourself", "text", False),
    ("10. Fee Reduction", "p10_5a_head_household", "5.a. I am the head of household", "radio", False),
    ("10. Fee Reduction", "p10_5b_head_name", "5.b. Name of head of household (if you selected 'No' in 5.a.)", "text", False),

    # =========================================================================
    # PART 11: APPLICANT'S CONTACT INFORMATION, CERTIFICATION, AND SIGNATURE
    # =========================================================================
    ("11. Applicant Contact", "p11_1_daytime_phone", "1. Applicant's Daytime Telephone Number", "phone", True),
    ("11. Applicant Contact", "p11_2_mobile_phone", "2. Applicant's Mobile Telephone Number (if any)", "phone", False),
    ("11. Applicant Contact", "p11_3_email", "3. Applicant's Email Address (if any)", "email", False),
    ("11. Applicant Signature", "p11_4_signature_date", "4. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 12: INTERPRETER'S CONTACT INFORMATION, CERTIFICATION, AND SIGNATURE
    # =========================================================================
    ("12A. Interpreter Name", "p12_1a_interp_family", "1. Interpreter's Family Name (Last Name)", "text", False),
    ("12A. Interpreter Name", "p12_1b_interp_given", "1. Interpreter's Given Name (First Name)", "text", False),
    ("12A. Interpreter Name", "p12_2_interp_org", "2. Interpreter's Business or Organization Name", "text", False),
    ("12B. Interpreter Contact", "p12_3_interp_phone", "3. Interpreter's Daytime Telephone Number", "phone", False),
    ("12B. Interpreter Contact", "p12_4_interp_mobile", "4. Interpreter's Mobile Telephone Number (if any)", "phone", False),
    ("12B. Interpreter Contact", "p12_5_interp_email", "5. Interpreter's Email Address (if any)", "email", False),
    ("12C. Interpreter Certification", "p12_language", "Language I am fluent in (besides English)", "text", False),
    ("12C. Interpreter Certification", "p12_6_interp_sig_date", "6. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 13: CONTACT INFORMATION OF THE PERSON PREPARING THIS APPLICATION
    # =========================================================================
    ("13A. Preparer Name", "p13_1a_prep_family", "1. Preparer's Family Name (Last Name)", "text", False),
    ("13A. Preparer Name", "p13_1b_prep_given", "1. Preparer's Given Name (First Name)", "text", False),
    ("13A. Preparer Name", "p13_2_prep_org", "2. Preparer's Business or Organization Name", "text", False),
    ("13B. Preparer Contact", "p13_3_prep_phone", "3. Preparer's Daytime Telephone Number", "phone", False),
    ("13B. Preparer Contact", "p13_4_prep_mobile", "4. Preparer's Mobile Telephone Number (if any)", "phone", False),
    ("13B. Preparer Contact", "p13_5_prep_email", "5. Preparer's Email Address (if any)", "email", False),
    ("13C. Preparer Certification", "p13_6_prep_sig_date", "6. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 14: ADDITIONAL INFORMATION
    # =========================================================================
    ("14. Additional Information", "p14_1a_family_name", "1. Family Name (Last Name)", "text", False),
    ("14. Additional Information", "p14_1b_given_name", "1. Given Name (First Name)", "text", False),
    ("14. Additional Information", "p14_1c_middle_name", "1. Middle (if applicable)", "text", False),

    ("14. Additional Information 2", "p14_2_page", "2. Page Number", "text", False),
    ("14. Additional Information 2", "p14_2_part", "2. Part Number", "text", False),
    ("14. Additional Information 2", "p14_2_item", "2. Item Number", "text", False),
    ("14. Additional Information 2", "p14_2_info", "2. Additional Information", "textarea", False),

    ("14. Additional Information 3", "p14_3_page", "3. Page Number", "text", False),
    ("14. Additional Information 3", "p14_3_part", "3. Part Number", "text", False),
    ("14. Additional Information 3", "p14_3_item", "3. Item Number", "text", False),
    ("14. Additional Information 3", "p14_3_info", "3. Additional Information", "textarea", False),

    ("14. Additional Information 4", "p14_4_page", "4. Page Number", "text", False),
    ("14. Additional Information 4", "p14_4_part", "4. Part Number", "text", False),
    ("14. Additional Information 4", "p14_4_item", "4. Item Number", "text", False),
    ("14. Additional Information 4", "p14_4_info", "4. Additional Information", "textarea", False),

    ("14. Additional Information 5", "p14_5_page", "5. Page Number", "text", False),
    ("14. Additional Information 5", "p14_5_part", "5. Part Number", "text", False),
    ("14. Additional Information 5", "p14_5_item", "5. Item Number", "text", False),
    ("14. Additional Information 5", "p14_5_info", "5. Additional Information", "textarea", False),
]


def update_n400():
    """Update N-400 with all official USCIS fields."""
    # Use template_id 15 (existing N-400 basic template) OR create new expanded one
    # We'll create a new expanded template to avoid breaking the basic one
    template_id = None

    with engine.connect() as conn:
        # Check if expanded N-400 template already exists
        result = conn.execute(text(
            "SELECT id FROM questionnaire_templates WHERE name LIKE '%N-400%Expanded%' LIMIT 1"
        ))
        row = result.fetchone()

        if row:
            template_id = row[0]
            print(f"Found existing expanded N-400 template: ID {template_id}")
        else:
            # Create new expanded template
            result = conn.execute(text("""
                INSERT INTO questionnaire_templates (name, description, category, is_active, is_required)
                VALUES (
                    'Form N-400 - Application for Naturalization (Expanded)',
                    'Complete N-400 with ALL official USCIS fields. Edition 01/20/25. 14 pages, 16 parts, 300+ fields.',
                    'USCIS Naturalization',
                    true,
                    true
                )
                RETURNING id
            """))
            template_id = result.fetchone()[0]
            print(f"Created new expanded N-400 template: ID {template_id}")

        # Delete existing fields for this template
        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        # Insert all fields
        for i, field in enumerate(N400_FIELDS):
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
        print(f"N-400 updated: {len(N400_FIELDS)} fields inserted into template {template_id}")

    return template_id


if __name__ == "__main__":
    tid = update_n400()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(N400_FIELDS)}")

    # Print summary by section
    sections = {}
    for section, _, _, _, _ in N400_FIELDS:
        sections[section] = sections.get(section, 0) + 1

    print("\nFields by section:")
    for section, count in sections.items():
        print(f"  {section}: {count}")
