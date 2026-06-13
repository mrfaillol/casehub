#!/usr/bin/env python3
"""
Expand I-129F (Petition for Alien Fiancé(e)) with ALL official USCIS fields.
Edition 04/10/23 - 16 pages, Parts 1-9.
"""
import json
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I129F_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT YOU (THE PETITIONER) (Pages 1-3)
    # =========================================================================
    ("Part 1. Information About You", "p1_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("Part 1. Information About You", "p1_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("Part 1. Information About You", "p1_1c_middle_name", "1.c. Middle Name", "text", False),
    ("Part 1. Other Names Used", "p1_2a_family_name", "2.a. Other Family Names Used (if any)", "text", False),
    ("Part 1. Other Names Used", "p1_2b_given_name", "2.b. Other Given Names Used (if any)", "text", False),
    ("Part 1. Other Names Used", "p1_2c_middle_name", "2.c. Other Middle Names Used (if any)", "text", False),
    ("Part 1. Information About You", "p1_3_dob", "3. Date of Birth (mm/dd/yyyy)", "date", True),
    ("Part 1. Information About You", "p1_4_gender_male", "4. Gender - Male", "radio", False),
    ("Part 1. Information About You", "p1_4_gender_female", "4. Gender - Female", "radio", False),
    ("Part 1. Information About You", "p1_5_city_of_birth", "5. City/Town/Village of Birth", "text", True),
    ("Part 1. Information About You", "p1_6_state_of_birth", "6. State/Province of Birth", "text", False),
    ("Part 1. Information About You", "p1_7_country_of_birth", "7. Country of Birth", "text", True),
    ("Part 1. Information About You", "p1_8_country_of_citizenship", "8. Country of Citizenship or Nationality", "text", True),
    ("Part 1. Information About You", "p1_9_a_number", "9. Alien Registration Number (A-Number) (if any)", "text", False),
    ("Part 1. Information About You", "p1_10_uscis_account", "10. USCIS Online Account Number (if any)", "text", False),
    ("Part 1. Information About You", "p1_11_ssn", "11. U.S. Social Security Number (if any)", "text", False),

    # Mailing Address
    ("Part 1. Mailing Address", "p1_12a_in_care_of", "12.a. In Care Of Name (if any)", "text", False),
    ("Part 1. Mailing Address", "p1_12b_street", "12.b. Street Number and Name", "text", True),
    ("Part 1. Mailing Address", "p1_12c_apt_type", "12.c. Apt./Ste./Flr.", "select", False),
    ("Part 1. Mailing Address", "p1_12c_apt_number", "12.c. Number", "text", False),
    ("Part 1. Mailing Address", "p1_12d_city", "12.d. City or Town", "text", True),
    ("Part 1. Mailing Address", "p1_12e_state", "12.e. State", "select", True),
    ("Part 1. Mailing Address", "p1_12f_zip", "12.f. ZIP Code", "text", True),
    ("Part 1. Mailing Address", "p1_12g_province", "12.g. Province (if applicable)", "text", False),
    ("Part 1. Mailing Address", "p1_12h_postal_code", "12.h. Postal Code (if applicable)", "text", False),
    ("Part 1. Mailing Address", "p1_12i_country", "12.i. Country", "text", False),

    # Physical Address (if different from mailing)
    ("Part 1. Physical Address", "p1_13a_street", "13.a. Street Number and Name", "text", False),
    ("Part 1. Physical Address", "p1_13b_apt_type", "13.b. Apt./Ste./Flr.", "select", False),
    ("Part 1. Physical Address", "p1_13b_apt_number", "13.b. Number", "text", False),
    ("Part 1. Physical Address", "p1_13c_city", "13.c. City or Town", "text", False),
    ("Part 1. Physical Address", "p1_13d_state", "13.d. State", "select", False),
    ("Part 1. Physical Address", "p1_13e_zip", "13.e. ZIP Code", "text", False),

    # Contact
    ("Part 1. Contact Information", "p1_14_daytime_phone", "14. Daytime Telephone Number", "phone", True),
    ("Part 1. Contact Information", "p1_15_mobile_phone", "15. Mobile Telephone Number (if any)", "phone", False),
    ("Part 1. Contact Information", "p1_16_email", "16. Email Address (if any)", "email", False),

    # =========================================================================
    # PART 2: ADDITIONAL INFORMATION ABOUT YOU (Pages 3-5)
    # =========================================================================
    ("Part 2. Additional Information About You", "p2_1_last_entry_city", "1. City/Town Where You Last Entered the United States", "text", False),
    ("Part 2. Additional Information About You", "p2_2_last_entry_state", "2. State Where You Last Entered the United States", "select", False),
    ("Part 2. Additional Information About You", "p2_3_last_entry_date", "3. Date of Last Entry Into the United States (mm/dd/yyyy)", "date", False),
    ("Part 2. Additional Information About You", "p2_4_i94_number", "4. I-94 Arrival-Departure Record Number", "text", False),
    ("Part 2. Additional Information About You", "p2_5_passport_number", "5. Passport or Travel Document Number", "text", False),
    ("Part 2. Additional Information About You", "p2_6_travel_doc_country", "6. Country That Issued Your Passport or Travel Document", "text", False),
    ("Part 2. Additional Information About You", "p2_7_passport_expiration", "7. Expiration Date for Passport or Travel Document (mm/dd/yyyy)", "date", False),
    ("Part 2. Additional Information About You", "p2_8_current_status", "8. Current Immigration Status", "text", False),

    # Previous Petitions Filed
    ("Part 2. Previous Petitions", "p2_9_prev_petition_filed", "9. Have you EVER previously filed a Form I-129F or Form I-130 for any person?", "select", True),
    ("Part 2. Previous Petitions", "p2_10a_prev_name_family", "10.a. Family Name of Prior Beneficiary", "text", False),
    ("Part 2. Previous Petitions", "p2_10b_prev_name_given", "10.b. Given Name of Prior Beneficiary", "text", False),
    ("Part 2. Previous Petitions", "p2_10c_prev_name_middle", "10.c. Middle Name of Prior Beneficiary", "text", False),
    ("Part 2. Previous Petitions", "p2_11_prev_city", "11. City or Town Where Prior Petition Was Filed", "text", False),
    ("Part 2. Previous Petitions", "p2_12_prev_state", "12. State Where Prior Petition Was Filed", "text", False),
    ("Part 2. Previous Petitions", "p2_13_prev_date", "13. Date Prior Petition Was Filed (mm/dd/yyyy)", "date", False),
    ("Part 2. Previous Petitions", "p2_14_prev_result", "14. Result of Prior Petition", "text", False),

    # Marital History
    ("Part 2. Marital History", "p2_15_times_married", "15. How many times have you been married?", "number", True),
    ("Part 2. Marital History", "p2_16_current_marital_status", "16. Current Marital Status", "select", True),

    # Prior Spouse 1
    ("Part 2. Prior Spouse 1", "p2_17a_prior_spouse1_family", "17.a. Prior Spouse 1 - Family Name", "text", False),
    ("Part 2. Prior Spouse 1", "p2_17b_prior_spouse1_given", "17.b. Prior Spouse 1 - Given Name", "text", False),
    ("Part 2. Prior Spouse 1", "p2_17c_prior_spouse1_middle", "17.c. Prior Spouse 1 - Middle Name", "text", False),
    ("Part 2. Prior Spouse 1", "p2_18_prior_spouse1_dob", "18. Prior Spouse 1 - Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 2. Prior Spouse 1", "p2_19_prior_spouse1_marriage_date", "19. Prior Spouse 1 - Date of Marriage (mm/dd/yyyy)", "date", False),
    ("Part 2. Prior Spouse 1", "p2_20_prior_spouse1_marriage_city", "20. Prior Spouse 1 - City/Town Where Marriage Took Place", "text", False),
    ("Part 2. Prior Spouse 1", "p2_21_prior_spouse1_marriage_state", "21. Prior Spouse 1 - State/Province Where Marriage Took Place", "text", False),
    ("Part 2. Prior Spouse 1", "p2_22_prior_spouse1_marriage_country", "22. Prior Spouse 1 - Country Where Marriage Took Place", "text", False),
    ("Part 2. Prior Spouse 1", "p2_23_prior_spouse1_end_date", "23. Prior Spouse 1 - Date Marriage Ended (mm/dd/yyyy)", "date", False),
    ("Part 2. Prior Spouse 1", "p2_24_prior_spouse1_end_city", "24. Prior Spouse 1 - City/Town Where Marriage Ended", "text", False),
    ("Part 2. Prior Spouse 1", "p2_25_prior_spouse1_end_state", "25. Prior Spouse 1 - State/Province Where Marriage Ended", "text", False),
    ("Part 2. Prior Spouse 1", "p2_26_prior_spouse1_end_country", "26. Prior Spouse 1 - Country Where Marriage Ended", "text", False),

    # Prior Spouse 2
    ("Part 2. Prior Spouse 2", "p2_27a_prior_spouse2_family", "27.a. Prior Spouse 2 - Family Name", "text", False),
    ("Part 2. Prior Spouse 2", "p2_27b_prior_spouse2_given", "27.b. Prior Spouse 2 - Given Name", "text", False),
    ("Part 2. Prior Spouse 2", "p2_27c_prior_spouse2_middle", "27.c. Prior Spouse 2 - Middle Name", "text", False),
    ("Part 2. Prior Spouse 2", "p2_28_prior_spouse2_dob", "28. Prior Spouse 2 - Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 2. Prior Spouse 2", "p2_29_prior_spouse2_marriage_date", "29. Prior Spouse 2 - Date of Marriage (mm/dd/yyyy)", "date", False),
    ("Part 2. Prior Spouse 2", "p2_30_prior_spouse2_marriage_city", "30. Prior Spouse 2 - City/Town Where Marriage Took Place", "text", False),
    ("Part 2. Prior Spouse 2", "p2_31_prior_spouse2_marriage_state", "31. Prior Spouse 2 - State/Province Where Marriage Took Place", "text", False),
    ("Part 2. Prior Spouse 2", "p2_32_prior_spouse2_marriage_country", "32. Prior Spouse 2 - Country Where Marriage Took Place", "text", False),
    ("Part 2. Prior Spouse 2", "p2_33_prior_spouse2_end_date", "33. Prior Spouse 2 - Date Marriage Ended (mm/dd/yyyy)", "date", False),
    ("Part 2. Prior Spouse 2", "p2_34_prior_spouse2_end_city", "34. Prior Spouse 2 - City/Town Where Marriage Ended", "text", False),
    ("Part 2. Prior Spouse 2", "p2_35_prior_spouse2_end_state", "35. Prior Spouse 2 - State/Province Where Marriage Ended", "text", False),
    ("Part 2. Prior Spouse 2", "p2_36_prior_spouse2_end_country", "36. Prior Spouse 2 - Country Where Marriage Ended", "text", False),

    # =========================================================================
    # PART 3: INFORMATION ABOUT YOUR FIANCÉ(E) / BENEFICIARY (Pages 5-7)
    # =========================================================================
    ("Part 3. Information About Your Fiancé(e)", "p3_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("Part 3. Information About Your Fiancé(e)", "p3_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("Part 3. Information About Your Fiancé(e)", "p3_1c_middle_name", "1.c. Middle Name", "text", False),
    ("Part 3. Other Names Used", "p3_2a_family_name", "2.a. Other Family Names Used (if any)", "text", False),
    ("Part 3. Other Names Used", "p3_2b_given_name", "2.b. Other Given Names Used (if any)", "text", False),
    ("Part 3. Other Names Used", "p3_2c_middle_name", "2.c. Other Middle Names Used (if any)", "text", False),
    ("Part 3. Information About Your Fiancé(e)", "p3_3_dob", "3. Date of Birth (mm/dd/yyyy)", "date", True),
    ("Part 3. Information About Your Fiancé(e)", "p3_4_gender_male", "4. Gender - Male", "radio", False),
    ("Part 3. Information About Your Fiancé(e)", "p3_4_gender_female", "4. Gender - Female", "radio", False),
    ("Part 3. Information About Your Fiancé(e)", "p3_5_city_of_birth", "5. City/Town/Village of Birth", "text", True),
    ("Part 3. Information About Your Fiancé(e)", "p3_6_state_of_birth", "6. State/Province of Birth", "text", False),
    ("Part 3. Information About Your Fiancé(e)", "p3_7_country_of_birth", "7. Country of Birth", "text", True),
    ("Part 3. Information About Your Fiancé(e)", "p3_8_country_of_citizenship", "8. Country of Citizenship or Nationality", "text", True),
    ("Part 3. Information About Your Fiancé(e)", "p3_9_a_number", "9. Alien Registration Number (A-Number) (if any)", "text", False),
    ("Part 3. Information About Your Fiancé(e)", "p3_10_uscis_account", "10. USCIS Online Account Number (if any)", "text", False),
    ("Part 3. Information About Your Fiancé(e)", "p3_11_ssn", "11. U.S. Social Security Number (if any)", "text", False),

    # Fiancé(e) Address Abroad
    ("Part 3. Fiancé(e) Address Abroad", "p3_12a_street", "12.a. Street Number and Name", "text", False),
    ("Part 3. Fiancé(e) Address Abroad", "p3_12b_apt_type", "12.b. Apt./Ste./Flr.", "select", False),
    ("Part 3. Fiancé(e) Address Abroad", "p3_12b_apt_number", "12.b. Number", "text", False),
    ("Part 3. Fiancé(e) Address Abroad", "p3_12c_city", "12.c. City or Town", "text", False),
    ("Part 3. Fiancé(e) Address Abroad", "p3_12d_province", "12.d. Province", "text", False),
    ("Part 3. Fiancé(e) Address Abroad", "p3_12e_postal_code", "12.e. Postal Code", "text", False),
    ("Part 3. Fiancé(e) Address Abroad", "p3_12f_country", "12.f. Country", "text", False),

    # Fiancé(e) U.S. Address (if any)
    ("Part 3. Fiancé(e) U.S. Address", "p3_13a_street", "13.a. Street Number and Name (if in the U.S.)", "text", False),
    ("Part 3. Fiancé(e) U.S. Address", "p3_13b_apt_type", "13.b. Apt./Ste./Flr.", "select", False),
    ("Part 3. Fiancé(e) U.S. Address", "p3_13b_apt_number", "13.b. Number", "text", False),
    ("Part 3. Fiancé(e) U.S. Address", "p3_13c_city", "13.c. City or Town", "text", False),
    ("Part 3. Fiancé(e) U.S. Address", "p3_13d_state", "13.d. State", "select", False),
    ("Part 3. Fiancé(e) U.S. Address", "p3_13e_zip", "13.e. ZIP Code", "text", False),

    # Contact
    ("Part 3. Contact Information", "p3_14_daytime_phone", "14. Daytime Telephone Number", "phone", False),
    ("Part 3. Contact Information", "p3_15_mobile_phone", "15. Mobile Telephone Number (if any)", "phone", False),
    ("Part 3. Contact Information", "p3_16_email", "16. Email Address (if any)", "email", False),

    # =========================================================================
    # PART 4: ADDITIONAL INFORMATION ABOUT YOUR FIANCÉ(E) (Pages 7-10)
    # =========================================================================
    ("Part 4. Additional Info About Fiancé(e)", "p4_1_passport_number", "1. Passport or Travel Document Number", "text", False),
    ("Part 4. Additional Info About Fiancé(e)", "p4_2_travel_doc_country", "2. Country That Issued Passport or Travel Document", "text", False),
    ("Part 4. Additional Info About Fiancé(e)", "p4_3_passport_expiration", "3. Expiration Date (mm/dd/yyyy)", "date", False),
    ("Part 4. Additional Info About Fiancé(e)", "p4_4_current_status", "4. Current Immigration Status or Nonimmigrant Category", "text", False),

    # Consular Processing
    ("Part 4. Consular Processing", "p4_5_consulate_city", "5. City or Town Where You Want to File Your Visa Application", "text", False),
    ("Part 4. Consular Processing", "p4_6_consulate_country", "6. Country Where You Want to File Your Visa Application", "text", False),

    # Marital History of Fiancé(e)
    ("Part 4. Fiancé(e) Marital History", "p4_7_times_married", "7. How many times has your fiancé(e) been previously married?", "number", True),
    ("Part 4. Fiancé(e) Marital History", "p4_8_current_marital_status", "8. Current Marital Status of Fiancé(e)", "select", True),

    # Prior Spouse 1 of Fiancé(e)
    ("Part 4. Fiancé(e) Prior Spouse 1", "p4_9a_prior_spouse1_family", "9.a. Prior Spouse 1 - Family Name", "text", False),
    ("Part 4. Fiancé(e) Prior Spouse 1", "p4_9b_prior_spouse1_given", "9.b. Prior Spouse 1 - Given Name", "text", False),
    ("Part 4. Fiancé(e) Prior Spouse 1", "p4_9c_prior_spouse1_middle", "9.c. Prior Spouse 1 - Middle Name", "text", False),
    ("Part 4. Fiancé(e) Prior Spouse 1", "p4_10_prior_spouse1_dob", "10. Prior Spouse 1 - Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 4. Fiancé(e) Prior Spouse 1", "p4_11_prior_spouse1_marriage_date", "11. Prior Spouse 1 - Date of Marriage (mm/dd/yyyy)", "date", False),
    ("Part 4. Fiancé(e) Prior Spouse 1", "p4_12_prior_spouse1_marriage_city", "12. Prior Spouse 1 - City/Town Where Marriage Took Place", "text", False),
    ("Part 4. Fiancé(e) Prior Spouse 1", "p4_13_prior_spouse1_marriage_state", "13. Prior Spouse 1 - State/Province Where Marriage Took Place", "text", False),
    ("Part 4. Fiancé(e) Prior Spouse 1", "p4_14_prior_spouse1_marriage_country", "14. Prior Spouse 1 - Country Where Marriage Took Place", "text", False),
    ("Part 4. Fiancé(e) Prior Spouse 1", "p4_15_prior_spouse1_end_date", "15. Prior Spouse 1 - Date Marriage Ended (mm/dd/yyyy)", "date", False),
    ("Part 4. Fiancé(e) Prior Spouse 1", "p4_16_prior_spouse1_end_city", "16. Prior Spouse 1 - City/Town Where Marriage Ended", "text", False),
    ("Part 4. Fiancé(e) Prior Spouse 1", "p4_17_prior_spouse1_end_state", "17. Prior Spouse 1 - State/Province Where Marriage Ended", "text", False),
    ("Part 4. Fiancé(e) Prior Spouse 1", "p4_18_prior_spouse1_end_country", "18. Prior Spouse 1 - Country Where Marriage Ended", "text", False),

    # Prior Spouse 2 of Fiancé(e)
    ("Part 4. Fiancé(e) Prior Spouse 2", "p4_19a_prior_spouse2_family", "19.a. Prior Spouse 2 - Family Name", "text", False),
    ("Part 4. Fiancé(e) Prior Spouse 2", "p4_19b_prior_spouse2_given", "19.b. Prior Spouse 2 - Given Name", "text", False),
    ("Part 4. Fiancé(e) Prior Spouse 2", "p4_19c_prior_spouse2_middle", "19.c. Prior Spouse 2 - Middle Name", "text", False),
    ("Part 4. Fiancé(e) Prior Spouse 2", "p4_20_prior_spouse2_dob", "20. Prior Spouse 2 - Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 4. Fiancé(e) Prior Spouse 2", "p4_21_prior_spouse2_marriage_date", "21. Prior Spouse 2 - Date of Marriage (mm/dd/yyyy)", "date", False),
    ("Part 4. Fiancé(e) Prior Spouse 2", "p4_22_prior_spouse2_marriage_city", "22. Prior Spouse 2 - City/Town Where Marriage Took Place", "text", False),
    ("Part 4. Fiancé(e) Prior Spouse 2", "p4_23_prior_spouse2_marriage_state", "23. Prior Spouse 2 - State/Province Where Marriage Took Place", "text", False),
    ("Part 4. Fiancé(e) Prior Spouse 2", "p4_24_prior_spouse2_marriage_country", "24. Prior Spouse 2 - Country Where Marriage Took Place", "text", False),
    ("Part 4. Fiancé(e) Prior Spouse 2", "p4_25_prior_spouse2_end_date", "25. Prior Spouse 2 - Date Marriage Ended (mm/dd/yyyy)", "date", False),
    ("Part 4. Fiancé(e) Prior Spouse 2", "p4_26_prior_spouse2_end_city", "26. Prior Spouse 2 - City/Town Where Marriage Ended", "text", False),
    ("Part 4. Fiancé(e) Prior Spouse 2", "p4_27_prior_spouse2_end_state", "27. Prior Spouse 2 - State/Province Where Marriage Ended", "text", False),
    ("Part 4. Fiancé(e) Prior Spouse 2", "p4_28_prior_spouse2_end_country", "28. Prior Spouse 2 - Country Where Marriage Ended", "text", False),

    # Children of Fiancé(e)
    ("Part 4. Fiancé(e) Children", "p4_29_has_children", "29. Does your fiancé(e) have any children?", "select", True),

    # Child 1
    ("Part 4. Child 1", "p4_30a_child1_family", "30.a. Child 1 - Family Name", "text", False),
    ("Part 4. Child 1", "p4_30b_child1_given", "30.b. Child 1 - Given Name", "text", False),
    ("Part 4. Child 1", "p4_30c_child1_middle", "30.c. Child 1 - Middle Name", "text", False),
    ("Part 4. Child 1", "p4_31_child1_dob", "31. Child 1 - Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 4. Child 1", "p4_32_child1_country_of_birth", "32. Child 1 - Country of Birth", "text", False),
    ("Part 4. Child 1", "p4_33_child1_applying_with", "33. Child 1 - Is this child applying with the beneficiary?", "select", False),

    # Child 2
    ("Part 4. Child 2", "p4_34a_child2_family", "34.a. Child 2 - Family Name", "text", False),
    ("Part 4. Child 2", "p4_34b_child2_given", "34.b. Child 2 - Given Name", "text", False),
    ("Part 4. Child 2", "p4_34c_child2_middle", "34.c. Child 2 - Middle Name", "text", False),
    ("Part 4. Child 2", "p4_35_child2_dob", "35. Child 2 - Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 4. Child 2", "p4_36_child2_country_of_birth", "36. Child 2 - Country of Birth", "text", False),
    ("Part 4. Child 2", "p4_37_child2_applying_with", "37. Child 2 - Is this child applying with the beneficiary?", "select", False),

    # Child 3
    ("Part 4. Child 3", "p4_38a_child3_family", "38.a. Child 3 - Family Name", "text", False),
    ("Part 4. Child 3", "p4_38b_child3_given", "38.b. Child 3 - Given Name", "text", False),
    ("Part 4. Child 3", "p4_38c_child3_middle", "38.c. Child 3 - Middle Name", "text", False),
    ("Part 4. Child 3", "p4_39_child3_dob", "39. Child 3 - Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 4. Child 3", "p4_40_child3_country_of_birth", "40. Child 3 - Country of Birth", "text", False),
    ("Part 4. Child 3", "p4_41_child3_applying_with", "41. Child 3 - Is this child applying with the beneficiary?", "select", False),

    # Child 4
    ("Part 4. Child 4", "p4_42a_child4_family", "42.a. Child 4 - Family Name", "text", False),
    ("Part 4. Child 4", "p4_42b_child4_given", "42.b. Child 4 - Given Name", "text", False),
    ("Part 4. Child 4", "p4_42c_child4_middle", "42.c. Child 4 - Middle Name", "text", False),
    ("Part 4. Child 4", "p4_43_child4_dob", "43. Child 4 - Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 4. Child 4", "p4_44_child4_country_of_birth", "44. Child 4 - Country of Birth", "text", False),
    ("Part 4. Child 4", "p4_45_child4_applying_with", "45. Child 4 - Is this child applying with the beneficiary?", "select", False),

    # =========================================================================
    # PART 5: OTHER INFORMATION (Pages 10-12)
    # =========================================================================
    # How you met
    ("Part 5. Other Information", "p5_1_met_in_person", "1. Have you and your fiancé(e) met each other in person during the 2-year period before filing?", "select", True),
    ("Part 5. Other Information", "p5_2_met_date", "2. Date you met your fiancé(e) in person (mm/dd/yyyy)", "date", False),
    ("Part 5. Other Information", "p5_3_met_desc", "3. Describe the circumstances under which you met your fiancé(e)", "textarea", False),

    # Waiver of in-person meeting
    ("Part 5. Meeting Waiver", "p5_4_waiver_requested", "4. If you have not met in person, are you requesting a waiver?", "select", False),
    ("Part 5. Meeting Waiver", "p5_5_waiver_extreme_hardship", "5.a. Waiver based on extreme hardship", "checkbox", False),
    ("Part 5. Meeting Waiver", "p5_5_waiver_custom_practice", "5.b. Waiver based on customary practice", "checkbox", False),

    # How you know each other
    ("Part 5. Relationship", "p5_6_how_related", "6. How did you and your fiancé(e) meet?", "textarea", False),
    ("Part 5. Relationship", "p5_7_engaged_date", "7. Date of engagement (mm/dd/yyyy)", "date", False),
    ("Part 5. Relationship", "p5_8_has_met_family", "8. Have you or your fiancé(e) met the other's family members?", "select", False),

    # International Marriage Broker
    ("Part 5. Marriage Broker", "p5_9_imb_used", "9. Did you meet through an international marriage broker?", "select", True),
    ("Part 5. Marriage Broker", "p5_10_imb_name", "10. Name of International Marriage Broker (if applicable)", "text", False),
    ("Part 5. Marriage Broker", "p5_11_imb_address", "11. Address of International Marriage Broker", "text", False),

    # Criminal History / IMBRA Disclosures
    ("Part 5. Criminal History Disclosures", "p5_12_arrested", "12. Have you EVER been arrested, cited, charged, or detained for any reason by law enforcement?", "select", True),
    ("Part 5. Criminal History Disclosures", "p5_13_convicted_dv", "13. Have you EVER been convicted of domestic violence, sexual assault, child abuse, or elder abuse?", "select", True),
    ("Part 5. Criminal History Disclosures", "p5_14_convicted_homicide", "14. Have you EVER been convicted of homicide, murder, manslaughter, or any attempt thereof?", "select", True),
    ("Part 5. Criminal History Disclosures", "p5_15_convicted_stalking", "15. Have you EVER been convicted of stalking?", "select", True),
    ("Part 5. Criminal History Disclosures", "p5_16_restraining_order", "16. Have you EVER had a restraining order, protection order, or injunction issued against you?", "select", True),
    ("Part 5. Criminal History Disclosures", "p5_17_convicted_three_plus", "17. Have you EVER been convicted of three or more crimes involving controlled substances or alcohol?", "select", True),
    ("Part 5. Criminal History Disclosures", "p5_18_other_criminal", "18. Have you EVER been convicted of a crime not listed above?", "select", True),
    ("Part 5. Criminal History Disclosures", "p5_19_criminal_explain", "19. If you answered yes to any of items 12-18, provide explanation", "textarea", False),

    # =========================================================================
    # PART 6: PETITIONER'S STATEMENT, CONTACT, DECLARATION, AND SIGNATURE (Pages 12-13)
    # =========================================================================
    ("Part 6. Petitioner's Statement, Contact, Declaration, and Signature", "p6_1_language_read", "1. I can read and understand English, and I have read this petition", "checkbox", False),
    ("Part 6. Petitioner's Statement, Contact, Declaration, and Signature", "p6_1b_interpreter_used", "1.b. The interpreter named in Part 7 read to me every question and instruction in a language I understand", "checkbox", False),
    ("Part 6. Petitioner's Statement, Contact, Declaration, and Signature", "p6_2_preparer_used", "2. At my request, the preparer named in Part 8 prepared this petition for me", "checkbox", False),
    ("Part 6. Petitioner's Statement, Contact, Declaration, and Signature", "p6_3a_daytime_phone", "3.a. Petitioner's Daytime Telephone Number", "phone", False),
    ("Part 6. Petitioner's Statement, Contact, Declaration, and Signature", "p6_3b_mobile_phone", "3.b. Petitioner's Mobile Telephone Number", "phone", False),
    ("Part 6. Petitioner's Statement, Contact, Declaration, and Signature", "p6_3c_email", "3.c. Petitioner's Email Address", "email", False),
    ("Part 6. Petitioner's Statement, Contact, Declaration, and Signature", "p6_4_signature", "4. Petitioner's Signature", "text", False),
    ("Part 6. Petitioner's Statement, Contact, Declaration, and Signature", "p6_5_signature_date", "5. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 7: INTERPRETER'S CONTACT INFORMATION (Page 14)
    # =========================================================================
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_1a_family_name", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_1b_given_name", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_2_business_name", "2. Interpreter's Business or Organization Name (if any)", "text", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_3a_street", "3.a. Interpreter's Street Number and Name", "text", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_3b_apt_number", "3.b. Number", "text", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_3c_city", "3.c. City or Town", "text", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_3d_state", "3.d. State", "select", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_3f_province", "3.f. Province (if applicable)", "text", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_3g_postal_code", "3.g. Postal Code (if applicable)", "text", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_3h_country", "3.h. Country", "text", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_4a_daytime_phone", "4.a. Interpreter's Daytime Telephone Number", "phone", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_4b_mobile_phone", "4.b. Interpreter's Mobile Telephone Number", "phone", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_4c_email", "4.c. Interpreter's Email Address", "email", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_5_language", "5. Language Interpreted", "text", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_6_signature", "6. Interpreter's Signature", "text", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_7_signature_date", "7. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 8: CONTACT INFORMATION, DECLARATION, AND SIGNATURE OF PREPARER (Pages 14-15)
    # =========================================================================
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_1a_family_name", "1.a. Preparer's Family Name (Last Name)", "text", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_1b_given_name", "1.b. Preparer's Given Name (First Name)", "text", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_2_business_name", "2. Preparer's Business or Organization Name (if any)", "text", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_3a_street", "3.a. Preparer's Street Number and Name", "text", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_3b_apt_number", "3.b. Number", "text", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_3c_city", "3.c. City or Town", "text", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_3d_state", "3.d. State", "select", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_3f_province", "3.f. Province (if applicable)", "text", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_3g_postal_code", "3.g. Postal Code (if applicable)", "text", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_3h_country", "3.h. Country", "text", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_4a_daytime_phone", "4.a. Preparer's Daytime Telephone Number", "phone", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_4b_mobile_phone", "4.b. Preparer's Mobile Telephone Number", "phone", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_4c_email", "4.c. Preparer's Email Address", "email", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_5_is_attorney", "5. Is the preparer an attorney or accredited representative?", "select", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_6_signature", "6. Preparer's Signature", "text", False),
    ("Part 8. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p8_7_signature_date", "7. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 9: ADDITIONAL INFORMATION (Page 16)
    # =========================================================================
    ("Part 9. Additional Information", "p9_1a_page_number", "1.a. Page Number", "text", False),
    ("Part 9. Additional Information", "p9_1b_part_number", "1.b. Part Number", "text", False),
    ("Part 9. Additional Information", "p9_1c_item_number", "1.c. Item Number", "text", False),
    ("Part 9. Additional Information", "p9_1d_additional_info", "1.d. Additional Information", "textarea", False),
    ("Part 9. Additional Information", "p9_2a_page_number", "2.a. Page Number", "text", False),
    ("Part 9. Additional Information", "p9_2b_part_number", "2.b. Part Number", "text", False),
    ("Part 9. Additional Information", "p9_2c_item_number", "2.c. Item Number", "text", False),
    ("Part 9. Additional Information", "p9_2d_additional_info", "2.d. Additional Information", "textarea", False),
    ("Part 9. Additional Information", "p9_3a_page_number", "3.a. Page Number", "text", False),
    ("Part 9. Additional Information", "p9_3b_part_number", "3.b. Part Number", "text", False),
    ("Part 9. Additional Information", "p9_3c_item_number", "3.c. Item Number", "text", False),
    ("Part 9. Additional Information", "p9_3d_additional_info", "3.d. Additional Information", "textarea", False),
]

OPTIONS_MAP = {
    "p1_12c_apt_type": ["Apt.", "Ste.", "Flr."],
    "p1_13b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p3_12b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p3_13b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p7_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p8_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p2_9_prev_petition_filed": ["Yes", "No"],
    "p2_16_current_marital_status": ["Single, Never Married", "Married", "Divorced", "Widowed", "Marriage Annulled"],
    "p4_8_current_marital_status": ["Single, Never Married", "Married", "Divorced", "Widowed", "Marriage Annulled"],
    "p4_29_has_children": ["Yes", "No"],
    "p4_33_child1_applying_with": ["Yes", "No"],
    "p4_37_child2_applying_with": ["Yes", "No"],
    "p4_41_child3_applying_with": ["Yes", "No"],
    "p4_45_child4_applying_with": ["Yes", "No"],
    "p5_1_met_in_person": ["Yes", "No"],
    "p5_4_waiver_requested": ["Yes", "No"],
    "p5_8_has_met_family": ["Yes", "No"],
    "p5_9_imb_used": ["Yes", "No"],
    "p5_12_arrested": ["Yes", "No"],
    "p5_13_convicted_dv": ["Yes", "No"],
    "p5_14_convicted_homicide": ["Yes", "No"],
    "p5_15_convicted_stalking": ["Yes", "No"],
    "p5_16_restraining_order": ["Yes", "No"],
    "p5_17_convicted_three_plus": ["Yes", "No"],
    "p5_18_other_criminal": ["Yes", "No"],
    "p8_5_is_attorney": ["Yes", "No"],
}


def expand():
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-129F%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
        ))
        row = result.fetchone()
        if not row:
            print("I-129F template not found!")
            return
        tid = row[0]
        print(f"Found I-129F template id={tid}")

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": tid})

        for i, (section, fname, label, ftype, req) in enumerate(I129F_FIELDS, 1):
            options = OPTIONS_MAP.get(fname)
            conn.execute(text("""
                INSERT INTO questionnaire_fields
                (template_id, field_name, label, field_type, is_required, section, "order", options)
                VALUES (:tid, :fn, :lbl, :ft, :req, :sec, :ord, :opts)
            """), {
                "tid": tid, "fn": fname, "lbl": label, "ft": ftype,
                "req": req, "sec": section, "ord": i,
                "opts": json.dumps(options) if options else None
            })

        conn.commit()
        print(f"Expanded I-129F: {len(I129F_FIELDS)} fields inserted for template {tid}")


if __name__ == "__main__":
    expand()
