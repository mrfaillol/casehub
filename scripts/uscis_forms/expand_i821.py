#!/usr/bin/env python3
"""
Expand I-821 (Application for Temporary Protected Status) with ALL official USCIS fields.
Edition 01/20/25 - 13 pages, Parts 1-11.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I821_FIELDS = [
    # =========================================================================
    # PART 1: TYPE OF APPLICATION (Page 1)
    # =========================================================================
    ("1. Type of Application", "p1_1a_initial", "1.a. This is my initial (first time) application for TPS. I do not currently have TPS.", "checkbox", False),
    ("1. Type of Application", "p1_1b_reregistration", "1.b. This is my re-registration application for TPS. I currently have TPS, and am applying to re-register.", "checkbox", False),
    ("1. Type of Application", "p1_2_granted_by", "2. If you selected Item Number 1.b., who granted you TPS?", "radio", False),
    ("1. Type of Application", "p1_3a_ead_yes", "3.a. Yes, I am requesting an Employment Authorization Document (EAD)", "checkbox", False),
    ("1. Type of Application", "p1_3b_ead_no", "3.b. No, I am not currently requesting an EAD", "checkbox", False),
    ("1. Type of Application", "p1_4_tps_country", "4. Name of designated TPS country under which you are applying", "text", True),

    # =========================================================================
    # PART 2: INFORMATION ABOUT YOU (Pages 1-3)
    # =========================================================================
    # Your Full Name
    ("2A. Your Full Name", "p2_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("2A. Your Full Name", "p2_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("2A. Your Full Name", "p2_1c_middle_name", "1.c. Middle Name", "text", False),

    # Other Names Used
    ("2B. Other Names", "p2_2a_family_name", "2.a. Other Name 1 - Family Name", "text", False),
    ("2B. Other Names", "p2_2b_given_name", "2.b. Other Name 1 - Given Name", "text", False),
    ("2B. Other Names", "p2_2c_middle_name", "2.c. Other Name 1 - Middle Name", "text", False),
    ("2B. Other Names", "p2_3a_family_name", "3.a. Other Name 2 - Family Name", "text", False),
    ("2B. Other Names", "p2_3b_given_name", "3.b. Other Name 2 - Given Name", "text", False),
    ("2B. Other Names", "p2_3c_middle_name", "3.c. Other Name 2 - Middle Name", "text", False),

    # U.S. Mailing Address
    ("2C. U.S. Mailing Address", "p2_4a_in_care_of", "4.a. In Care Of Name", "text", False),
    ("2C. U.S. Mailing Address", "p2_4b_street", "4.b. Street Number and Name", "text", True),
    ("2C. U.S. Mailing Address", "p2_4c_apt", "4.c. Apt. / Ste. / Flr.", "select", False),
    ("2C. U.S. Mailing Address", "p2_4c_number", "4.c. Number", "text", False),
    ("2C. U.S. Mailing Address", "p2_4d_city", "4.d. City or Town", "text", True),
    ("2C. U.S. Mailing Address", "p2_4e_state", "4.e. State", "select", True),
    ("2C. U.S. Mailing Address", "p2_4f_zip", "4.f. ZIP Code", "text", True),
    ("2C. U.S. Mailing Address", "p2_5_same_physical", "5. Is your current mailing address the same as your physical address (where you live)?", "radio", True),

    # U.S. Physical Address (if different)
    ("2D. U.S. Physical Address", "p2_6a_street", "6.a. Street Number and Name", "text", False),
    ("2D. U.S. Physical Address", "p2_6b_apt", "6.b. Apt. / Ste. / Flr.", "select", False),
    ("2D. U.S. Physical Address", "p2_6b_number", "6.b. Number", "text", False),
    ("2D. U.S. Physical Address", "p2_6c_city", "6.c. City or Town", "text", False),
    ("2D. U.S. Physical Address", "p2_6d_state", "6.d. State", "select", False),
    ("2D. U.S. Physical Address", "p2_6e_zip", "6.e. ZIP Code", "text", False),

    # Other Information
    ("2E. Other Information", "p2_7_a_number", "7. Alien Registration Number (A-Number) (if any)", "text", False),
    ("2E. Other Information", "p2_8_uscis_account", "8. USCIS Online Account Number (if any)", "text", False),
    ("2E. Other Information", "p2_9_ssn", "9. U.S. Social Security Number (if any)", "text", False),
    ("2E. Other Information", "p2_10_dob", "10. Date of Birth (mm/dd/yyyy)", "date", True),
    ("2E. Other Information", "p2_11a_other_dob1", "11.a. Other Date of Birth 1 (mm/dd/yyyy)", "date", False),
    ("2E. Other Information", "p2_11b_other_dob2", "11.b. Other Date of Birth 2 (mm/dd/yyyy)", "date", False),
    ("2E. Other Information", "p2_12_sex", "12. Sex", "radio", True),
    ("2E. Other Information", "p2_13_city_birth", "13. City/Town/Village of Birth", "text", True),
    ("2E. Other Information", "p2_14_country_birth", "14. Country of Birth", "text", True),

    # Countries of Residence (Before U.S.)
    ("2F. Countries of Residence", "p2_15a_country1", "15.a. Country of Residence 1", "text", False),
    ("2F. Countries of Residence", "p2_15b_country2", "15.b. Country of Residence 2", "text", False),
    ("2F. Countries of Residence", "p2_15c_country3", "15.c. Country of Residence 3", "text", False),
    ("2F. Countries of Residence", "p2_15d_country4", "15.d. Country of Residence 4", "text", False),

    # Country or Countries of Citizenship or Nationality
    ("2G. Citizenship/Nationality", "p2_16a_country1", "16.a. Country of Citizenship/Nationality 1", "text", True),
    ("2G. Citizenship/Nationality", "p2_16b_country2", "16.b. Country of Citizenship/Nationality 2", "text", False),
    ("2G. Citizenship/Nationality", "p2_16c_country3", "16.c. Country of Citizenship/Nationality 3", "text", False),
    ("2G. Citizenship/Nationality", "p2_16d_country4", "16.d. Country of Citizenship/Nationality 4", "text", False),

    # Your Marital Information
    ("2H. Marital Information", "p2_17_marital_status", "17. Current Marital Status", "radio", True),
    ("2H. Marital Information", "p2_18_marriage_date", "18. Date of Current Marriage (if currently married) (mm/dd/yyyy)", "date", False),

    # U.S. Entry Information
    ("2I. U.S. Entry", "p2_19_last_entry_date", "19. Date of Last Entry into the United States (mm/dd/yyyy)", "date", True),
    ("2I. U.S. Entry", "p2_20_status_last_entry", "20. Immigration Status (or Lack of Status) When You Last Entered the United States", "text", True),
    ("2I. U.S. Entry", "p2_21_port_of_entry", "21. U.S. Port of Entry (if any)", "text", False),
    ("2I. U.S. Entry", "p2_22a_city", "22.a. Place of Last Entry - City or Town", "text", False),
    ("2I. U.S. Entry", "p2_22b_state", "22.b. Place of Last Entry - State", "select", False),
    ("2I. U.S. Entry", "p2_23_i94_number", "23. Form I-94 Arrival-Departure Record Number (if any)", "text", False),
    ("2I. U.S. Entry", "p2_24_authorized_period", "24. Date Your Authorized Period of Stay in the United States Expired or Will Expire (mm/dd/yyyy or duration of status D/S)", "text", False),
    ("2I. U.S. Entry", "p2_25_passport_number", "25. Passport Number (most recent) (if any)", "text", False),
    ("2I. U.S. Entry", "p2_26_travel_doc_number", "26. Travel Document Number (if any)", "text", False),
    ("2I. U.S. Entry", "p2_27_passport_number_2", "27. Additional Passport or Travel Document Number", "text", False),
    ("2I. U.S. Entry", "p2_28_passport_number_3", "28. Additional Passport or Travel Document Number", "text", False),
    ("2I. U.S. Entry", "p2_29_country_issuance", "29. Country of Issuance for most recent Passport or Travel Document", "text", False),
    ("2I. U.S. Entry", "p2_30_expiration_date", "30. Expiration Date for most recent Passport or Travel Document (mm/dd/yyyy)", "date", False),

    # Your Current Immigration Status
    ("2J. Current Status", "p2_31_current_status", "31. Current Immigration Status or Lack of Status", "text", True),
    ("2J. Current Status", "p2_32_ever_in_proceedings", "32. Are you now or were you EVER in immigration proceedings?", "radio", True),
    ("2J. Current Status", "p2_33a_immigration_court", "33.a. Immigration Court (before an Immigration Judge)", "checkbox", False),
    ("2J. Current Status", "p2_33b_bia", "33.b. Board of Immigration Appeals (BIA)", "checkbox", False),
    ("2J. Current Status", "p2_33c_no_longer_doj", "33.c. I am no longer in Department of Justice (DOJ) or DHS immigration proceedings", "checkbox", False),
    ("2J. Current Status", "p2_34_doj_dhs_locations", "34. Locations Where Your DOJ and/or DHS Proceedings were Held (or are currently being held)", "text", False),
    ("2J. Current Status", "p2_35_federal_court_locations", "35. Locations Where Your Federal Court Proceedings Regarding Immigration Issues were Held", "text", False),
    ("2J. Current Status", "p2_36a_from", "36.a. Dates for Your Proceedings - From (mm/dd/yyyy)", "date", False),
    ("2J. Current Status", "p2_36b_to", "36.b. Dates for Your Proceedings - To (mm/dd/yyyy)", "date", False),
    ("2J. Current Status", "p2_36c_present", "36.c. Present", "checkbox", False),

    # =========================================================================
    # PART 3: BIOGRAPHIC INFORMATION (Pages 3-4)
    # =========================================================================
    ("3. Biographic", "p3_1_ethnicity", "1. Ethnicity", "radio", True),
    ("3. Biographic", "p3_2_race_white", "2. Race - White", "checkbox", False),
    ("3. Biographic", "p3_2_race_asian", "2. Race - Asian", "checkbox", False),
    ("3. Biographic", "p3_2_race_black", "2. Race - Black or African American", "checkbox", False),
    ("3. Biographic", "p3_2_race_native_american", "2. Race - American Indian or Alaska Native", "checkbox", False),
    ("3. Biographic", "p3_2_race_pacific", "2. Race - Native Hawaiian or Other Pacific Islander", "checkbox", False),
    ("3. Biographic", "p3_3_height_feet", "3. Height - Feet", "text", True),
    ("3. Biographic", "p3_3_height_inches", "3. Height - Inches", "text", True),
    ("3. Biographic", "p3_4_weight", "4. Weight - Pounds", "text", True),
    ("3. Biographic", "p3_5_eye_color", "5. Eye Color", "radio", True),
    ("3. Biographic", "p3_6_hair_color", "6. Hair Color", "radio", True),

    # =========================================================================
    # PART 4: INFORMATION ABOUT YOUR CURRENT SPOUSE (Page 4)
    # =========================================================================
    ("4. Current Spouse", "p4_1_uscis_account", "1. USCIS Online Account Number (if any and if known)", "text", False),
    ("4. Current Spouse", "p4_2_a_number", "2. A-Number (if any and if known)", "text", False),
    ("4. Current Spouse", "p4_3a_family_name", "3.a. Family Name (Last Name)", "text", False),
    ("4. Current Spouse", "p4_3b_given_name", "3.b. Given Name (First Name)", "text", False),
    ("4. Current Spouse", "p4_3c_middle_name", "3.c. Middle Name", "text", False),

    # Mailing Address of Spouse
    ("4. Spouse Mailing", "p4_4a_street", "4.a. Street Number and Name", "text", False),
    ("4. Spouse Mailing", "p4_4b_apt", "4.b. Apt. / Ste. / Flr.", "select", False),
    ("4. Spouse Mailing", "p4_4b_number", "4.b. Number", "text", False),
    ("4. Spouse Mailing", "p4_4c_city", "4.c. City or Town", "text", False),
    ("4. Spouse Mailing", "p4_4d_state", "4.d. State", "select", False),
    ("4. Spouse Mailing", "p4_4e_zip", "4.e. ZIP Code", "text", False),
    ("4. Spouse Mailing", "p4_4f_province", "4.f. Province", "text", False),
    ("4. Spouse Mailing", "p4_4g_postal_code", "4.g. Postal Code", "text", False),
    ("4. Spouse Mailing", "p4_4h_country", "4.h. Country", "text", False),

    # Other Information About Current Spouse
    ("4. Spouse Other Info", "p4_5_dob", "5. Your Spouse's Date of Birth (mm/dd/yyyy)", "date", False),
    ("4. Spouse Other Info", "p4_6_marriage_date", "6. Date of Marriage to Your Current Spouse (mm/dd/yyyy)", "date", False),
    ("4. Spouse Other Info", "p4_7_marriage_place", "7. Place of Marriage to Your Current Spouse", "text", False),
    ("4. Spouse Other Info", "p4_8a_city", "8.a. City or Town", "text", False),
    ("4. Spouse Other Info", "p4_8b_state", "8.b. State", "select", False),
    ("4. Spouse Other Info", "p4_8c_province", "8.c. Province (if any)", "text", False),
    ("4. Spouse Other Info", "p4_8d_country", "8.d. Country", "text", False),
    ("4. Spouse Other Info", "p4_9_ever_tps", "9. If you know, has your current spouse EVER had TPS?", "radio", False),
    ("4. Spouse Other Info", "p4_10a_tps_from", "10.a. If yes, TPS dates - From (mm/dd/yyyy)", "date", False),
    ("4. Spouse Other Info", "p4_10b_tps_to", "10.b. If yes, TPS dates - To (mm/dd/yyyy)", "date", False),
    ("4. Spouse Other Info", "p4_10c_tps_present", "10.c. Present", "checkbox", False),
    ("4. Spouse Other Info", "p4_10d_unknown_dates", "10.d. I do not know the dates", "checkbox", False),
    ("4. Spouse Other Info", "p4_11_tps_valid", "11. Is your spouse's TPS still valid? (if known)", "radio", False),

    # =========================================================================
    # PART 5: INFORMATION ABOUT YOUR FORMER SPOUSES (Page 5)
    # =========================================================================
    # First Marriage
    ("5. Former Spouse 1", "p5_1a_family_name", "First Marriage - 1.a. Family Name (Last Name)", "text", False),
    ("5. Former Spouse 1", "p5_1b_given_name", "First Marriage - 1.b. Given Name (First Name)", "text", False),
    ("5. Former Spouse 1", "p5_1c_middle_name", "First Marriage - 1.c. Middle Name", "text", False),
    ("5. Former Spouse 1", "p5_2_nationalities", "First Marriage - 2. Nationalities of Former Spouse", "text", False),
    ("5. Former Spouse 1", "p5_3_a_number", "First Marriage - 3. A-Number of Former Spouse (if any and if known)", "text", False),
    ("5. Former Spouse 1", "p5_4_dob", "First Marriage - 4. Date of Birth of Former Spouse (mm/dd/yyyy)", "date", False),
    ("5. Former Spouse 1", "p5_5_death_date", "First Marriage - 5. Date of Death if Former Spouse Deceased (mm/dd/yyyy)", "date", False),
    ("5. Former Spouse 1", "p5_6a_marriage_from", "First Marriage - 6.a. From (mm/dd/yyyy)", "date", False),
    ("5. Former Spouse 1", "p5_6b_marriage_to", "First Marriage - 6.b. To (mm/dd/yyyy)", "date", False),
    ("5. Former Spouse 1", "p5_7_how_ended", "First Marriage - 7. How Marriage Ended (divorce, widowed, annulled)", "text", False),
    ("5. Former Spouse 1", "p5_8_spouse_tps", "First Marriage - 8. Did or does this former spouse have TPS (if known)?", "radio", False),
    ("5. Former Spouse 1", "p5_9a_tps_from", "First Marriage - 9.a. TPS dates - From (mm/dd/yyyy)", "date", False),
    ("5. Former Spouse 1", "p5_9b_tps_to", "First Marriage - 9.b. TPS dates - To (mm/dd/yyyy)", "date", False),
    ("5. Former Spouse 1", "p5_9c_tps_present", "First Marriage - 9.c. Present", "checkbox", False),
    ("5. Former Spouse 1", "p5_9d_unknown_dates", "First Marriage - 9.d. I do not know the dates", "checkbox", False),
    ("5. Former Spouse 1", "p5_10_applying", "First Marriage - 10. Is this former spouse currently applying for or re-registering for TPS?", "radio", False),

    # Second Marriage
    ("5. Former Spouse 2", "p5_11a_family_name", "Second Marriage - 11.a. Family Name (Last Name)", "text", False),
    ("5. Former Spouse 2", "p5_11b_given_name", "Second Marriage - 11.b. Given Name (First Name)", "text", False),
    ("5. Former Spouse 2", "p5_11c_middle_name", "Second Marriage - 11.c. Middle Name", "text", False),
    ("5. Former Spouse 2", "p5_12_nationalities", "Second Marriage - 12. Nationalities of Former Spouse", "text", False),
    ("5. Former Spouse 2", "p5_13_a_number", "Second Marriage - 13. A-Number of Former Spouse (if any and if known)", "text", False),
    ("5. Former Spouse 2", "p5_14_dob", "Second Marriage - 14. Date of Birth of Former Spouse (mm/dd/yyyy)", "date", False),
    ("5. Former Spouse 2", "p5_15_death_date", "Second Marriage - 15. Date of Death if Former Spouse Deceased (mm/dd/yyyy)", "date", False),
    ("5. Former Spouse 2", "p5_16a_marriage_from", "Second Marriage - 16.a. From (mm/dd/yyyy)", "date", False),
    ("5. Former Spouse 2", "p5_16b_marriage_to", "Second Marriage - 16.b. To (mm/dd/yyyy)", "date", False),
    ("5. Former Spouse 2", "p5_17_how_ended", "Second Marriage - 17. How Marriage Ended (divorce, widowed, annulled)", "text", False),
    ("5. Former Spouse 2", "p5_18_spouse_tps", "Second Marriage - 18. Did or does this former spouse have TPS (if known)?", "radio", False),
    ("5. Former Spouse 2", "p5_19a_tps_from", "Second Marriage - 19.a. TPS dates - From (mm/dd/yyyy)", "date", False),
    ("5. Former Spouse 2", "p5_19b_tps_to", "Second Marriage - 19.b. TPS dates - To (mm/dd/yyyy)", "date", False),
    ("5. Former Spouse 2", "p5_19c_tps_present", "Second Marriage - 19.c. Present", "checkbox", False),
    ("5. Former Spouse 2", "p5_19d_unknown_dates", "Second Marriage - 19.d. I do not know the dates", "checkbox", False),
    ("5. Former Spouse 2", "p5_20_applying", "Second Marriage - 20. Is this former spouse currently applying for or re-registering for TPS?", "radio", False),

    # =========================================================================
    # PART 6: INFORMATION ABOUT YOUR CHILDREN (Page 6)
    # =========================================================================
    # Child 1
    ("6. Child 1", "p6_1a_family_name", "Child 1 - 1.a. Family Name (Last Name)", "text", False),
    ("6. Child 1", "p6_1b_given_name", "Child 1 - 1.b. Given Name (First Name)", "text", False),
    ("6. Child 1", "p6_1c_middle_name", "Child 1 - 1.c. Middle Name", "text", False),
    ("6. Child 1", "p6_2_uscis_account", "Child 1 - 2. USCIS Online Account Number (if any and if known)", "text", False),
    ("6. Child 1", "p6_3_a_number", "Child 1 - 3. Alien Registration Number (A-Number) (if any and if known)", "text", False),
    ("6. Child 1", "p6_4_dob", "Child 1 - 4. Date of Birth (mm/dd/yyyy)", "date", False),
    ("6. Child 1", "p6_5a_mailing_street", "Child 1 - 5.a. Mailing Address - Street Number and Name", "text", False),
    ("6. Child 1", "p6_5b_mailing_apt", "Child 1 - 5.b. Mailing Address - Apt./Ste./Flr.", "select", False),
    ("6. Child 1", "p6_5b_mailing_number", "Child 1 - 5.b. Mailing Address - Number", "text", False),
    ("6. Child 1", "p6_5c_mailing_city", "Child 1 - 5.c. Mailing Address - City or Town", "text", False),
    ("6. Child 1", "p6_5d_mailing_state", "Child 1 - 5.d. Mailing Address - State", "select", False),
    ("6. Child 1", "p6_5e_mailing_zip", "Child 1 - 5.e. Mailing Address - ZIP Code", "text", False),
    ("6. Child 1", "p6_5f_mailing_province", "Child 1 - 5.f. Mailing Address - Province", "text", False),
    ("6. Child 1", "p6_5g_mailing_postal", "Child 1 - 5.g. Mailing Address - Postal Code", "text", False),
    ("6. Child 1", "p6_5h_mailing_country", "Child 1 - 5.h. Mailing Address - Country", "text", False),
    ("6. Child 1", "p6_6a_tps_from", "Child 1 - 6.a. If this child has or had TPS, dates - From (mm/dd/yyyy)", "date", False),
    ("6. Child 1", "p6_6b_tps_to", "Child 1 - 6.b. If this child has or had TPS, dates - To (mm/dd/yyyy)", "date", False),
    ("6. Child 1", "p6_7_applying", "Child 1 - 7. Is this child currently applying for or re-registering for TPS (if known)?", "radio", False),

    # Child 2
    ("6. Child 2", "p6_8a_family_name", "Child 2 - 8.a. Family Name (Last Name)", "text", False),
    ("6. Child 2", "p6_8b_given_name", "Child 2 - 8.b. Given Name (First Name)", "text", False),
    ("6. Child 2", "p6_8c_middle_name", "Child 2 - 8.c. Middle Name", "text", False),
    ("6. Child 2", "p6_9_uscis_account", "Child 2 - 9. USCIS Online Account Number (if any and if known)", "text", False),
    ("6. Child 2", "p6_10_a_number", "Child 2 - 10. Alien Registration Number (A-Number) (if any and if known)", "text", False),
    ("6. Child 2", "p6_11_dob", "Child 2 - 11. Date of Birth (mm/dd/yyyy)", "date", False),
    ("6. Child 2", "p6_12a_mailing_street", "Child 2 - 12.a. Mailing Address - Street Number and Name", "text", False),
    ("6. Child 2", "p6_12b_mailing_apt", "Child 2 - 12.b. Mailing Address - Apt./Ste./Flr.", "select", False),
    ("6. Child 2", "p6_12b_mailing_number", "Child 2 - 12.b. Mailing Address - Number", "text", False),
    ("6. Child 2", "p6_12c_mailing_city", "Child 2 - 12.c. Mailing Address - City or Town", "text", False),
    ("6. Child 2", "p6_12d_mailing_state", "Child 2 - 12.d. Mailing Address - State", "select", False),
    ("6. Child 2", "p6_12e_mailing_zip", "Child 2 - 12.e. Mailing Address - ZIP Code", "text", False),
    ("6. Child 2", "p6_12f_mailing_province", "Child 2 - 12.f. Mailing Address - Province", "text", False),
    ("6. Child 2", "p6_12g_mailing_postal", "Child 2 - 12.g. Mailing Address - Postal Code", "text", False),
    ("6. Child 2", "p6_12h_mailing_country", "Child 2 - 12.h. Mailing Address - Country", "text", False),
    ("6. Child 2", "p6_13a_tps_from", "Child 2 - 13.a. If this child has or had TPS, dates - From (mm/dd/yyyy)", "date", False),
    ("6. Child 2", "p6_13b_tps_to", "Child 2 - 13.b. If this child has or had TPS, dates - To (mm/dd/yyyy)", "date", False),
    ("6. Child 2", "p6_14_applying", "Child 2 - 14. Is this child currently applying for or re-registering for TPS (if known)?", "radio", False),

    # =========================================================================
    # PART 7: ELIGIBILITY STANDARDS (Pages 6-10)
    # =========================================================================
    # Basis for Eligibility
    ("7A. Basis", "p7_1a_nationality", "1.a. I am a national of (or a person having no nationality who last habitually resided in the country of):", "text", True),
    ("7B. Entry Date", "p7_1b_entry_date", "1.b. I entered the United States on the following date, and have resided in the United States since that time (mm/dd/yyyy)", "date", True),
    ("7C. Travel", "p7_1c_ever_traveled", "1.c. Have you EVER traveled to and entered another country, other than the one listed in Item Number 1.a. before you last entered the United States?", "radio", False),
    ("7C. Travel", "p7_2_countries_traveled", "2. Name of All the Other Countries to Which You Traveled and Entered Prior to Entering the United States", "textarea", False),
    ("7C. Travel", "p7_3a_dates_from", "3.a. Dates That You Were in the Other Country or Countries - From (mm/dd/yyyy)", "date", False),
    ("7C. Travel", "p7_3b_dates_to", "3.b. Dates That You Were in the Other Country or Countries - To (mm/dd/yyyy)", "date", False),
    ("7C. Travel", "p7_4_immigration_status", "4. Your Immigration Status, if Any, in the Other Country", "text", False),
    ("7C. Travel", "p7_5_offered_status", "5. Have you EVER been offered any immigration status by another country that you did not accept?", "radio", False),
    ("7C. Travel", "p7_6_offered_details", "6. If you answered Yes to Item Number 5, describe the country or countries, the nature of the immigration status you were offered, and the dates when it was offered", "textarea", False),
    ("7C. Travel", "p7_7_chose_not_accept", "7. If you answered Yes to Item Number 5, describe why you chose not to accept the immigration status offered to you by the other country or countries", "textarea", False),

    # Criminal Offenses
    ("7D. Criminal", "p7_8a_felony_us", "8.a. Have you EVER been convicted of: Any felony committed in the United States?", "radio", False),
    ("7D. Criminal", "p7_8b_misdemeanor_us", "8.b. Any misdemeanor committed in the United States?", "radio", False),
    ("7D. Criminal", "p7_8c_serious_crime", "8.c. Any particularly serious crime committed either in or outside the United States?", "radio", False),
    ("7D. Criminal", "p7_9a_persecution", "9.a. Have you EVER ordered, incited, assisted, or otherwise participated in the persecution of any person on account of race, religion, nationality, membership in a particular social group, or political opinion?", "radio", False),
    ("7D. Criminal", "p7_9b_nonpolitical_crime", "9.b. Have you EVER committed serious nonpolitical crimes outside of the United States prior to your arrival in the United States?", "radio", False),
    ("7D. Criminal", "p7_9c_danger", "9.c. Have you EVER or are you NOW engaged in activities that could be reasonable grounds for concluding that you are a danger to the security of the United States?", "radio", False),
    ("7D. Criminal", "p7_10a_crime_political", "10.a. Have you EVER been convicted of or have you EVER committed acts which constitute the essential elements of: A crime (other than a purely political offense)?", "radio", False),
    ("7D. Criminal", "p7_10b_controlled_substance", "10.b. A violation of any law relating to a controlled substance as defined in section 102 of the Controlled Substances Act?", "radio", False),
    ("7D. Criminal", "p7_10c_conspiracy", "10.c. A conspiracy to violate any law relating to a controlled substance as defined in section 102 of the Controlled Substances Act?", "radio", False),
    ("7D. Criminal", "p7_11_two_crimes", "11. Have you EVER been convicted of two or more criminal offenses (other than purely political offenses) for which you received sentences to confinement that, when combined, total five years or more?", "radio", False),
    ("7D. Criminal", "p7_12a_trafficking_now", "12.a. Have you EVER trafficked in or are you NOW trafficking in any controlled substance?", "radio", False),
    ("7D. Criminal", "p7_12b_trafficking_assist", "12.b. Are you NOW or have you EVER knowingly assisted, abetted, conspired, or colluded with others in the unlawful trafficking of any controlled substance?", "radio", False),
    ("7D. Criminal", "p7_12c_spouse_trafficking", "12.c. Are you the spouse or child of an alien who unlawfully trafficked in any controlled substance?", "radio", False),
    ("7D. Criminal", "p7_12d_spouse_assisted", "12.d. Are you the spouse or child of an alien who assisted, abetted, conspired, or colluded with others in the unlawful trafficking of any controlled substance?", "radio", False),
    ("7D. Criminal", "p7_12e_benefit_trafficking", "12.e. Within the previous five years, have you EVER obtained any financial or other benefit from the unlawful activity of your spouse (including former spouses) or parents, and you knew, or reasonably should have known, that the financial or other bene...", "radio", False),
    ("7D. Criminal", "p7_13a_espionage", "13.a. Have you EVER engaged, or do you plan to engage, solely, principally, or incidentally, in any of the following: Any activity to violate any law of the United States relating to espionage or sabotage?", "radio", False),
    ("7D. Criminal", "p7_13b_export_law", "13.b. Any activity to violate or evade any law prohibiting the export from the United States of goods, technology, or sensitive information?", "radio", False),
    ("7D. Criminal", "p7_13c_unlawful_activity", "13.c. Any other unlawful activity in the United States?", "radio", False),
    ("7D. Criminal", "p7_13d_oppose_government", "13.d. Any activity in which a purpose is to oppose, control, or overthrow the Government of the United States by force, violence, or other unlawful means, including but not limited to participating in such activities, giving support to others involved ...", "radio", False),
    ("7D. Criminal", "p7_14a_terrorist_now", "14.a. Have you EVER or are you NOW engaged in terrorist activities?", "radio", False),
    ("7D. Criminal", "p7_14b_terrorist_plan", "14.b. Have you EVER or are you NOW engaged in or plan to engage in activities in the United States that would have potentially serious adverse foreign policy consequences for the United States?", "radio", False),
    ("7D. Criminal", "p7_14c_totalitarian_member", "14.c. Have you EVER been or are you NOW a member of the Communist or other totalitarian party, except when membership was involuntary?", "radio", False),
    ("7D. Criminal", "p7_14d_nazi_persecution", "14.d. Have you EVER participated in Nazi persecution or genocide?", "radio", False),
    ("7D. Criminal", "p7_15a_arrested", "15.a. Have you EVER, whether in the United States or any other country: Arrested, for breaking or violating any law or ordinance, excluding minor traffic violations?", "radio", False),
    ("7D. Criminal", "p7_15b_cited", "15.b. Cited, charged, or indicted, for breaking or violating any law or ordinance, excluding minor traffic violations?", "radio", False),
    ("7D. Criminal", "p7_15c_convicted", "15.c. Been convicted, fined, imprisoned, placed on probation, received a suspended sentence or deferral of adjudication for breaking or violating any law or ordinance, excluding minor traffic violations?", "radio", False),
    ("7D. Criminal", "p7_16_pardon", "16. Have you EVER been the beneficiary of a pardon, amnesty, rehabilitation decree, other act of clemency, or similar action?", "radio", False),
    ("7D. Criminal", "p7_17_serious_offense_immunity", "17. Have you EVER committed a serious criminal offense in the United States and asserted immunity from prosecution?", "radio", False),
    ("7D. Criminal", "p7_18a_prostitution_now", "18.a. Have you EVER, within the past 10 years, or are you NOW engaged in prostitution or procurement of prostitution?", "radio", False),
    ("7D. Criminal", "p7_18b_prostitution_procure", "18.b. Have you EVER, within the past 10 years (either directly or indirectly) procured or attempted to procure or import prostitutes or persons for the purpose of prostitution?", "radio", False),
    ("7D. Criminal", "p7_18c_prostitution_proceeds", "18.c. Have you EVER, within the past 10 years, received, in whole or in part, the proceeds of prostitution?", "radio", False),
    ("7D. Criminal", "p7_19_commercial_vice", "19. Have you EVER been or do you intend to be involved in any other commercial vice?", "radio", False),
    ("7D. Criminal", "p7_20a_removed_deported", "20.a. Have you EVER been ordered removed, and been deported from the United States?", "radio", False),
    ("7D. Criminal", "p7_20b_voluntary_departure", "20.b. Have you EVER voluntarily departed the United States under an order of removal?", "radio", False),
    ("7D. Criminal", "p7_20c_reentered_unlawfully", "20.c. If you answered Yes to either Item Number 20.a. or 20.b. above, have you re-entered the United States unlawfully at any time after you were deported or you voluntarily departed?", "radio", False),
    ("7D. Criminal", "p7_20d_dhs_prior_order", "20.d. If you answered Yes to Item Number 20.c. above, has DHS set your prior order of removal aside?", "radio", False),
    ("7D. Criminal", "p7_20e_failed_attend", "20.e. Have you EVER failed to attend or remain in attendance at any immigration proceedings to determine your admissibility or deportability?", "radio", False),
    ("7D. Criminal", "p7_21_fraud", "21. Have you EVER, by fraud or willfully misrepresenting a material fact, sought to obtain a visa or other documentation, admission to the United States, or any other immigration benefit?", "radio", False),
    ("7D. Criminal", "p7_22_assisted_violation", "22. Have you EVER assisted any other person to enter the United States in violation of the law?", "radio", False),
    ("7D. Criminal", "p7_23a_communicable_disease", "23.a. Do you NOW have a communicable disease of public health significance?", "radio", False),
    ("7D. Criminal", "p7_23b_physical_mental", "23.b. Do you NOW have or have you EVER had a physical or mental disorder and behavior (or a history of behavior that is likely to recur) associated with the disorder which has posed or may pose a threat to the property, safety, or welfare of yourself o...", "radio", False),
    ("7D. Criminal", "p7_23c_drug_abuser", "23.c. Are you NOW or have you EVER been a drug abuser or drug addict?", "radio", False),
    ("7D. Criminal", "p7_24_stowaway", "24. Have you EVER entered the United States as a stowaway?", "radio", False),
    ("7D. Criminal", "p7_25_false_docs_ins", "25. Did the former Immigration and Naturalization Service (INS) EVER impose, or has DHS EVER imposed, civil monetary penalties on you for producing or using false documentation to obtain an immigration benefit?", "radio", False),
    ("7D. Criminal", "p7_26_final_order_274c", "26. Are you NOW subject to a final order for violation of section 274C (producing and/or using false documentation to unlawfully satisfy a requirement of the Immigration and Nationality Act)?", "radio", False),
    ("7D. Criminal", "p7_27_polygamy", "27. Do you NOW practice polygamy?", "radio", False),
    ("7D. Criminal", "p7_28_guardian", "28. Are you NOW the guardian of, and are you accompanying, another individual who has been found to be inadmissible and who has been certified by a medical examiner to be helpless due to sickness, physical or mental disability, or infancy?", "radio", False),
    ("7D. Criminal", "p7_29_detained_citizenship", "29. Have you EVER detained, retained, or withheld the custody of a U.S. citizen child outside the United States, from a U.S. citizen granted custody?", "radio", False),
    ("7D. Criminal", "p7_30a_torture_genocide", "30.a. Have you EVER ordered, incited, called for, committed, assisted, helped with, or otherwise participated in any of the following: Acts involving torture or genocide?", "radio", False),
    ("7D. Criminal", "p7_30b_killing", "30.b. Killing any person?", "radio", False),
    ("7D. Criminal", "p7_30c_injuring", "30.c. Intentionally and severely injuring any person?", "radio", False),
    ("7D. Criminal", "p7_30d_sexual_contact", "30.d. Engaging in any kind of sexual contact or relations with any person who was being forced or threatened?", "radio", False),
    ("7D. Criminal", "p7_30e_religious_beliefs", "30.e. Limiting or denying any person's ability to exercise religious beliefs?", "radio", False),
    ("7D. Criminal", "p7_31a_military_unit", "31.a. Have you EVER: Served in, been a member of, assisted in, or participated in any military unit, paramilitary unit, police unit, self-defense unit, vigilante unit, rebel group, guerrilla group, militia, or insurgent organization?", "radio", False),
    ("7D. Criminal", "p7_31b_prison_detention", "31.b. Served or worked in any prison, jail, prison camp, detention facility, labor camp, or any other situation that involved detaining persons?", "radio", False),
    ("7D. Criminal", "p7_32_group_weapon", "32. Have you EVER been a member of, assisted in, or participated in any group, unit, or organization of any kind in which you or other persons used any type of weapon against any person or threatened to do so?", "radio", False),
    ("7D. Criminal", "p7_33_weapons_selling", "33. Have you EVER assisted with or participated in selling or providing weapons to any person who to your knowledge used them against another person, or in transporting weapons to any person who to your knowledge used them against another person?", "radio", False),
    ("7D. Criminal", "p7_34_military_training", "34. Have you EVER received any type of military, paramilitary, or weapons training?", "radio", False),
    ("7D. Criminal", "p7_35_voted_unlawfully", "35. Have you EVER unlawfully voted in a United States Federal, state, or local election?", "radio", False),
    ("7D. Criminal", "p7_36_claimed_citizen", "36. Have you EVER claimed to be a U.S. citizen (in writing or in any other way)?", "radio", False),
    ("7D. Criminal", "p7_37a_recruited_child", "37.a. Have you EVER recruited, enlisted, conscripted, or used any person under 15 years of age to serve in or help an armed force or group?", "radio", False),
    ("7D. Criminal", "p7_37b_child_combat", "37.b. Have you EVER used any person under 15 years of age to take part in hostilities or to help or provide services to people in combat?", "radio", False),
    ("7D. Criminal", "p7_38a_human_trafficking_committed", "38.a. Have you EVER committed or conspired to commit human trafficking offenses, as defined in the section 103 of the Victims of Trafficking and Violence Protection Act of 2000, in the United States or outside the United States?", "radio", False),
    ("7D. Criminal", "p7_38b_human_trafficking_aided", "38.b. Have you EVER knowingly aided, abetted, assisted, conspired, or colluded with a human trafficker?", "radio", False),
    ("7D. Criminal", "p7_38c_spouse_trafficker", "38.c. Are you NOW the spouse or child of, or are you yourself, an alien who knowingly aided, abetted, assisted, conspired, or colluded with a human trafficker?", "radio", False),
    ("7D. Criminal", "p7_38e_benefit_trafficking", "38.e. Within the previous five years, have you EVER obtained any financial or other benefit from the human trafficking activity of your spouse (including former spouses) or parents, and you knew, or reasonably should have known, that the financial or o...", "radio", False),
    ("7D. Criminal", "p7_39a_money_laundering_now", "39.a. Are you NOW or have you EVER engaged in money laundering as described in section 1956 or 1957 of Title 18, United States Code?", "radio", False),
    ("7D. Criminal", "p7_39b_money_laundering_aider", "39.b. Are you NOW or have you EVER been a knowing aider, abettor, assister, conspirator, or colluder with others in money laundering?", "radio", False),
    ("7D. Criminal", "p7_40_religious_freedom", "40. Have you EVER been responsible for or directly carried out particularly severe violations of religious freedom, as defined in section 3 of the International Religious Freedom Act of 1998 (22 U.S.C. section 6402) while serving as a foreign governmen...", "radio", False),
    ("7D. Criminal", "p7_41_frivolous_asylum", "41. Has an immigration judge or the Board of Immigration Appeals EVER determined that you filed a frivolous asylum application in the past?", "radio", False),

    # =========================================================================
    # PART 8: APPLICANT'S STATEMENT, CONTACT INFORMATION, CERTIFICATION, AND SIGNATURE (Pages 10-11)
    # =========================================================================
    ("8. Applicant Statement", "p8_1a_english_understood", "1.a. I can read and understand English, and I have read and understand every question and instruction on this application and my answer to every question", "checkbox", False),
    ("8. Applicant Statement", "p8_1b_interpreter", "1.b. The interpreter named in Part 9. read to me every question and instruction on this application and my answer to every question in [language], and I understood everything", "checkbox", False),
    ("8. Applicant Statement", "p8_2_preparer", "2. At my request, the preparer named in Part 10. prepared this application for me based only upon information I provided or authorized", "checkbox", False),

    # Applicant's Contact Information
    ("8. Contact", "p8_3_phone", "3. Applicant's Daytime Telephone Number", "phone", False),
    ("8. Contact", "p8_4_mobile", "4. Applicant's Mobile Telephone Number (if any)", "phone", False),
    ("8. Contact", "p8_5_email", "5. Applicant's Email Address (if any)", "text", False),

    # Applicant's Signature
    ("8. Signature", "p8_6a_signature_date", "6.a. Applicant's Signature", "text", True),
    ("8. Signature", "p8_6b_date", "6.b. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 9: INTERPRETER'S CONTACT INFORMATION, CERTIFICATION, AND SIGNATURE (Pages 11-12)
    # =========================================================================
    ("9. Interpreter", "p9_1a_family_name", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("9. Interpreter", "p9_1b_given_name", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("9. Interpreter", "p9_2_organization", "2. Interpreter's Business or Organization Name (if any)", "text", False),
    ("9. Interpreter", "p9_3a_street", "3.a. Interpreter's Mailing Address - Street Number and Name", "text", False),
    ("9. Interpreter", "p9_3b_apt", "3.b. Interpreter's Mailing Address - Apt./Ste./Flr.", "select", False),
    ("9. Interpreter", "p9_3b_number", "3.b. Interpreter's Mailing Address - Number", "text", False),
    ("9. Interpreter", "p9_3c_city", "3.c. Interpreter's Mailing Address - City or Town", "text", False),
    ("9. Interpreter", "p9_3d_state", "3.d. Interpreter's Mailing Address - State", "select", False),
    ("9. Interpreter", "p9_3e_zip", "3.e. Interpreter's Mailing Address - ZIP Code", "text", False),
    ("9. Interpreter", "p9_3f_province", "3.f. Interpreter's Mailing Address - Province", "text", False),
    ("9. Interpreter", "p9_3g_postal", "3.g. Interpreter's Mailing Address - Postal Code", "text", False),
    ("9. Interpreter", "p9_3h_country", "3.h. Interpreter's Mailing Address - Country", "text", False),
    ("9. Interpreter", "p9_4_phone", "4. Interpreter's Daytime Telephone Number", "phone", False),
    ("9. Interpreter", "p9_5_mobile", "5. Interpreter's Mobile Telephone Number (if any)", "phone", False),
    ("9. Interpreter", "p9_6_email", "6. Interpreter's Email Address (if any)", "text", False),
    ("9. Interpreter", "p9_7a_signature", "7.a. Interpreter's Signature", "text", False),
    ("9. Interpreter", "p9_7b_date", "7.b. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 10: CONTACT INFORMATION, DECLARATION, AND SIGNATURE OF THE PERSON PREPARING THIS APPLICATION (Page 12)
    # =========================================================================
    ("10. Preparer", "p10_1a_family_name", "1.a. Preparer's Family Name (Last Name)", "text", False),
    ("10. Preparer", "p10_1b_given_name", "1.b. Preparer's Given Name (First Name)", "text", False),
    ("10. Preparer", "p10_2_organization", "2. Preparer's Business or Organization Name (if any)", "text", False),
    ("10. Preparer", "p10_3a_street", "3.a. Preparer's Mailing Address - Street Number and Name", "text", False),
    ("10. Preparer", "p10_3b_apt", "3.b. Preparer's Mailing Address - Apt./Ste./Flr.", "select", False),
    ("10. Preparer", "p10_3b_number", "3.b. Preparer's Mailing Address - Number", "text", False),
    ("10. Preparer", "p10_3c_city", "3.c. Preparer's Mailing Address - City or Town", "text", False),
    ("10. Preparer", "p10_3d_state", "3.d. Preparer's Mailing Address - State", "select", False),
    ("10. Preparer", "p10_3e_zip", "3.e. Preparer's Mailing Address - ZIP Code", "text", False),
    ("10. Preparer", "p10_3f_province", "3.f. Preparer's Mailing Address - Province", "text", False),
    ("10. Preparer", "p10_3g_postal", "3.g. Preparer's Mailing Address - Postal Code", "text", False),
    ("10. Preparer", "p10_3h_country", "3.h. Preparer's Mailing Address - Country", "text", False),
    ("10. Preparer", "p10_4_phone", "4. Preparer's Daytime Telephone Number", "phone", False),
    ("10. Preparer", "p10_5_mobile", "5. Preparer's Mobile Telephone Number (if any)", "phone", False),
    ("10. Preparer", "p10_6_email", "6. Preparer's Email Address (if any)", "text", False),
    ("10. Preparer", "p10_7a_not_attorney", "7.a. I am not an attorney or accredited representative but have prepared this application on behalf of the applicant and with the applicant's consent", "checkbox", False),
    ("10. Preparer", "p10_7b_attorney_extends", "7.b. I am an attorney or accredited representative and my representation of the applicant in this case extends beyond the preparation of this application", "checkbox", False),
    ("10. Preparer", "p10_7b_attorney_not_extend", "7.b. I am an attorney or accredited representative and my representation does not extend beyond the preparation of this application", "checkbox", False),
    ("10. Preparer", "p10_8a_signature", "8.a. Preparer's Signature", "text", False),
    ("10. Preparer", "p10_8b_date", "8.b. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 11: ADDITIONAL INFORMATION (Page 13)
    # =========================================================================
    ("11. Additional Info 1", "p11_1a_family_name", "1.a. Family Name (Last Name)", "text", False),
    ("11. Additional Info 1", "p11_1b_given_name", "1.b. Given Name (First Name)", "text", False),
    ("11. Additional Info 1", "p11_1c_middle_name", "1.c. Middle Name", "text", False),
    ("11. Additional Info 1", "p11_2_a_number", "2. A-Number (if any)", "text", False),
    ("11. Additional Info 1", "p11_3a_page", "3.a. Page Number", "text", False),
    ("11. Additional Info 1", "p11_3b_part", "3.b. Part Number", "text", False),
    ("11. Additional Info 1", "p11_3c_item", "3.c. Item Number", "text", False),
    ("11. Additional Info 1", "p11_3d_additional", "3.d. Additional Information", "textarea", False),
    ("11. Additional Info 2", "p11_4a_page", "4.a. Page Number", "text", False),
    ("11. Additional Info 2", "p11_4b_part", "4.b. Part Number", "text", False),
    ("11. Additional Info 2", "p11_4c_item", "4.c. Item Number", "text", False),
    ("11. Additional Info 2", "p11_4d_additional", "4.d. Additional Information", "textarea", False),
    ("11. Additional Info 3", "p11_5a_page", "5.a. Page Number", "text", False),
    ("11. Additional Info 3", "p11_5b_part", "5.b. Part Number", "text", False),
    ("11. Additional Info 3", "p11_5c_item", "5.c. Item Number", "text", False),
    ("11. Additional Info 3", "p11_5d_additional", "5.d. Additional Information", "textarea", False),
    ("11. Additional Info 4", "p11_6a_page", "6.a. Page Number", "text", False),
    ("11. Additional Info 4", "p11_6b_part", "6.b. Part Number", "text", False),
    ("11. Additional Info 4", "p11_6c_item", "6.c. Item Number", "text", False),
    ("11. Additional Info 4", "p11_6d_additional", "6.d. Additional Information", "textarea", False),
    ("11. Additional Info 5", "p11_7a_page", "7.a. Page Number", "text", False),
    ("11. Additional Info 5", "p11_7b_part", "7.b. Part Number", "text", False),
    ("11. Additional Info 5", "p11_7c_item", "7.c. Item Number", "text", False),
    ("11. Additional Info 5", "p11_7d_additional", "7.d. Additional Information", "textarea", False),
]


def update_i821(template_id=None):
    """Insert or update I-821 fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-821%' AND name NOT LIKE '%OLD%' AND name NOT LIKE '%I-821D%' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('I-821 - Application for Temporary Protected Status (EXPANDED)', "
                    "'Complete I-821 with all official USCIS fields - Edition 01/20/25') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(I821_FIELDS):
            conn.execute(text(
                "INSERT INTO questionnaire_fields (template_id, section, field_name, label, field_type, is_required, \"order\") "
                "VALUES (:tid, :section, :field_name, :label, :field_type, :is_required, :order)"
            ), {
                "tid": template_id, "section": section, "field_name": field_name,
                "label": label, "field_type": field_type, "is_required": required, "order": i + 1
            })

        conn.commit()
        print(f"I-821 expanded: template_id={template_id}, fields={len(I821_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_i821()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(I821_FIELDS)}")

    sections = {}
    for section, _, _, _, _ in I821_FIELDS:
        sections[section] = sections.get(section, 0) + 1

    print("\nFields by section:")
    for section, count in sections.items():
        print(f"  {section}: {count}")
