#!/usr/bin/env python3
"""
Expand I-140 (Immigrant Petition for Alien Workers) with ALL official USCIS fields.
Edition 06/07/24 - 8 pages, Parts 1-11.
Covers: EB-1A, EB-1B, EB-1C, EB-2, EB-2 NIW, EB-3.
"""
import json
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I140_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT THE PERSON OR ORGANIZATION FILING THIS PETITION
    # (Page 1) - Petitioner/Employer Information
    # =========================================================================
    # Individual Petitioner Name (for self-petition like EB-1A, EB-2 NIW)
    ("Part 1. Petitioner Information", "p1_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("Part 1. Petitioner Information", "p1_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("Part 1. Petitioner Information", "p1_1c_middle_name", "1.c. Middle Name", "text", False),

    # Company/Organization Name
    ("Part 1. Petitioner Information", "p1_2_company_name", "2. Company or Organization Name", "text", False),

    # Federal EIN
    ("Part 1. Petitioner Information", "p1_3_ein", "3. IRS Employer Identification Number (EIN) (if any)", "text", False),

    # SSN
    ("Part 1. Petitioner Information", "p1_4_ssn", "4. U.S. Social Security Number (if any)", "text", False),

    # Nonprofit question
    ("Part 1. Petitioner Information", "p1_5_nonprofit", "5. Is the organization a nonprofit or governmental research organization?", "radio", True),

    # Employee count question
    ("Part 1. Petitioner Information", "p1_6_25_or_fewer_employees", "6. Does the organization currently employ a total of 25 or fewer full-time equivalent employees in the United States, including all affiliates and subsidiaries?", "radio", True),

    # USCIS Online Account Number
    ("Part 1. Petitioner Information", "p1_7_uscis_account", "7. USCIS Online Account Number (if any)", "text", False),

    # Mailing Address
    ("Part 1. Mailing Address", "p1_8a_street", "8.a. Street Number and Name", "text", True),
    ("Part 1. Mailing Address", "p1_8b_apt_type", "8.b. Apt./Ste./Flr.", "select", False),
    ("Part 1. Mailing Address", "p1_8b_apt_number", "8.b. Number", "text", False),
    ("Part 1. Mailing Address", "p1_8c_city", "8.c. City or Town", "text", True),
    ("Part 1. Mailing Address", "p1_8d_state", "8.d. State", "select", True),
    ("Part 1. Mailing Address", "p1_8e_zip", "8.e. ZIP Code", "text", True),
    ("Part 1. Mailing Address", "p1_8f_province", "8.f. Province (foreign address only)", "text", False),
    ("Part 1. Mailing Address", "p1_8g_postal_code", "8.g. Postal Code (foreign address only)", "text", False),
    ("Part 1. Mailing Address", "p1_8h_country", "8.h. Country (foreign address only)", "text", False),

    # =========================================================================
    # PART 2: PETITION TYPE (Pages 1-2)
    # =========================================================================
    # Classification
    ("Part 2. Petition Type", "p2_1a_eb1a_extraordinary", "1.a. An alien of extraordinary ability (EB-1A)", "checkbox", False),
    ("Part 2. Petition Type", "p2_1b_eb1b_professor", "1.b. An outstanding professor or researcher (EB-1B)", "checkbox", False),
    ("Part 2. Petition Type", "p2_1c_eb1c_multinational", "1.c. A multinational executive or manager (EB-1C)", "checkbox", False),
    ("Part 2. Petition Type", "p2_1d_eb2_advanced", "1.d. A member of the professions holding an advanced degree or an alien of exceptional ability (NOT seeking a National Interest Waiver) (EB-2)", "checkbox", False),
    ("Part 2. Petition Type", "p2_1e_eb3_professional", "1.e. A professional (at minimum a U.S. baccalaureate degree or a foreign equivalent degree) (EB-3)", "checkbox", False),
    ("Part 2. Petition Type", "p2_1f_eb3_skilled", "1.f. A skilled worker (requiring at least 2 years of training or experience) (EB-3)", "checkbox", False),
    ("Part 2. Petition Type", "p2_1g_eb3_other", "1.g. Any other worker (requiring less than 2 years of training or experience) (EB-3)", "checkbox", False),
    ("Part 2. Petition Type", "p2_1h_eb2_niw", "1.h. A member of the professions holding an advanced degree or an alien of exceptional ability seeking a National Interest Waiver (EB-2 NIW)", "checkbox", False),

    # Filing Purpose
    ("Part 2. Filing Purpose", "p2_2a_amend", "2.a. To amend a previously filed petition. Receipt Number:", "text", False),
    ("Part 2. Filing Purpose", "p2_2b_new", "2.b. For a new petition", "checkbox", False),
    ("Part 2. Filing Purpose", "p2_2c_schedule_a", "2.c. For the Schedule A, Group I or II designation", "checkbox", False),

    # =========================================================================
    # PART 3: INFORMATION ABOUT THE PERSON YOU ARE FILING FOR (BENEFICIARY)
    # (Pages 2-3)
    # =========================================================================
    # Beneficiary Name
    ("Part 3. Beneficiary Information", "p3_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("Part 3. Beneficiary Information", "p3_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("Part 3. Beneficiary Information", "p3_1c_middle_name", "1.c. Middle Name", "text", False),

    # Beneficiary U.S. Mailing Address
    ("Part 3. Beneficiary Address", "p3_2a_street", "2.a. Street Number and Name", "text", True),
    ("Part 3. Beneficiary Address", "p3_2b_apt_type", "2.b. Apt./Ste./Flr.", "select", False),
    ("Part 3. Beneficiary Address", "p3_2b_apt_number", "2.b. Number", "text", False),
    ("Part 3. Beneficiary Address", "p3_2c_city", "2.c. City or Town", "text", True),
    ("Part 3. Beneficiary Address", "p3_2d_state", "2.d. State", "select", False),
    ("Part 3. Beneficiary Address", "p3_2e_zip", "2.e. ZIP Code", "text", False),
    ("Part 3. Beneficiary Address", "p3_2f_province", "2.f. Province (foreign address only)", "text", False),
    ("Part 3. Beneficiary Address", "p3_2g_postal_code", "2.g. Postal Code (foreign address only)", "text", False),
    ("Part 3. Beneficiary Address", "p3_2h_country", "2.h. Country", "text", False),

    # Beneficiary Other Info
    ("Part 3. Beneficiary Details", "p3_3_date_last_arrival", "3. Date of Last Arrival in the U.S. (mm/dd/yyyy)", "date", False),
    ("Part 3. Beneficiary Details", "p3_4_i94_number", "4. I-94 Arrival-Departure Record Number", "text", False),
    ("Part 3. Beneficiary Details", "p3_5a_current_status", "5.a. Current Nonimmigrant Status or Category", "text", False),
    ("Part 3. Beneficiary Details", "p3_5b_status_expires", "5.b. Date Status Expires or D/S (mm/dd/yyyy)", "text", False),
    ("Part 3. Beneficiary Details", "p3_6_country_of_birth", "6. Country of Birth", "text", True),
    ("Part 3. Beneficiary Details", "p3_7_country_citizenship", "7. Country of Citizenship or Nationality", "text", True),
    ("Part 3. Beneficiary Details", "p3_8_a_number", "8. Alien Registration Number (A-Number) (if any)", "text", False),
    ("Part 3. Beneficiary Details", "p3_9_ssn", "9. U.S. Social Security Number (if any)", "text", False),
    ("Part 3. Beneficiary Details", "p3_10_dob", "10. Date of Birth (mm/dd/yyyy)", "date", True),
    ("Part 3. Beneficiary Details", "p3_11_gender", "11. Gender", "radio", True),
    ("Part 3. Beneficiary Details", "p3_12_uscis_account", "12. USCIS Online Account Number (if any)", "text", False),

    # Passport Info
    ("Part 3. Passport Information", "p3_13_passport_number", "13. Passport Number", "text", False),
    ("Part 3. Passport Information", "p3_14_travel_doc_number", "14. Travel Document Number (if any)", "text", False),
    ("Part 3. Passport Information", "p3_15_country_issuance", "15. Country of Issuance for Passport or Travel Document", "text", False),
    ("Part 3. Passport Information", "p3_16_expiration_date", "16. Expiration Date for Passport or Travel Document (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 4: PROCESSING INFORMATION (Pages 3-4)
    # =========================================================================
    ("Part 4. Processing Information", "p4_1a_consular_processing", "1.a. Alien will apply for a visa abroad at a U.S. Embassy or U.S. Consulate at:", "checkbox", False),
    ("Part 4. Processing Information", "p4_1b_consulate_city", "1.b. City or Town", "text", False),
    ("Part 4. Processing Information", "p4_1c_consulate_country", "1.c. Country", "text", False),

    ("Part 4. Processing Information", "p4_2a_adjustment_of_status", "2.a. Alien is in the United States and will apply for adjustment of status to that of lawful permanent resident", "checkbox", False),
    ("Part 4. Processing Information", "p4_2b_country_of_residence", "2.b. Country of current residence or, if now in the U.S., country of last permanent residence abroad", "text", False),

    # Foreign Address (if U.S. address given in Part 3)
    ("Part 4. Foreign Address", "p4_3a_foreign_street", "3.a. Foreign Address - Street Number and Name", "text", False),
    ("Part 4. Foreign Address", "p4_3b_foreign_city", "3.b. Foreign Address - City or Town", "text", False),
    ("Part 4. Foreign Address", "p4_3c_foreign_province", "3.c. Foreign Address - Province", "text", False),
    ("Part 4. Foreign Address", "p4_3d_foreign_postal", "3.d. Foreign Address - Postal Code", "text", False),
    ("Part 4. Foreign Address", "p4_3e_foreign_country", "3.e. Foreign Address - Country", "text", False),

    # Native Alphabet
    ("Part 4. Native Alphabet", "p4_4a_native_family_name", "4.a. Beneficiary's Name in Native Alphabet - Family Name", "text", False),
    ("Part 4. Native Alphabet", "p4_4b_native_given_name", "4.b. Beneficiary's Name in Native Alphabet - Given Name", "text", False),
    ("Part 4. Native Alphabet", "p4_4c_native_middle_name", "4.c. Beneficiary's Name in Native Alphabet - Middle Name", "text", False),

    # Native Alphabet Address
    ("Part 4. Native Alphabet Address", "p4_5a_native_street", "5.a. Foreign Address in Native Alphabet - Street Number and Name", "text", False),
    ("Part 4. Native Alphabet Address", "p4_5b_native_city", "5.b. Foreign Address in Native Alphabet - City or Town", "text", False),
    ("Part 4. Native Alphabet Address", "p4_5c_native_province", "5.c. Foreign Address in Native Alphabet - Province", "text", False),
    ("Part 4. Native Alphabet Address", "p4_5d_native_postal", "5.d. Foreign Address in Native Alphabet - Postal Code", "text", False),
    ("Part 4. Native Alphabet Address", "p4_5e_native_country", "5.e. Foreign Address in Native Alphabet - Country", "text", False),

    # Additional Questions
    ("Part 4. Additional Questions", "p4_6a_other_petitions", "6.a. Are you filing any other petitions or applications with this Form I-140?", "radio", True),
    ("Part 4. Additional Questions", "p4_6b_removal_proceedings", "6.b. Is the person you are filing for in removal proceedings?", "radio", True),
    ("Part 4. Additional Questions", "p4_7_prior_immigrant_visa", "7. Has any immigrant visa petition ever been filed by or on behalf of this person?", "radio", True),
    ("Part 4. Additional Questions", "p4_8_labor_cert_filed", "8. Has a labor certification application ever been filed for this person?", "radio", False),
    ("Part 4. Additional Questions", "p4_9_prior_i140", "9. Has an immigrant petition (I-140) ever previously been filed for this person?", "radio", False),
    ("Part 4. Additional Questions", "p4_10_duplicate_labor_cert", "10. Are you requesting USCIS to obtain a duplicate of a labor certification for this person from the Department of Labor?", "radio", False),
    ("Part 4. Additional Questions", "p4_11_explanation", "11. If you answered 'Yes' to any question above, explain (include case numbers, dates, offices). Provide details on Part 11 if needed.", "textarea", False),

    # =========================================================================
    # PART 5: ADDITIONAL INFORMATION ABOUT THE PETITIONER (Pages 4)
    # =========================================================================
    ("Part 5. Additional Petitioner Info", "p5_1a_employer", "1.a. Type of petitioner: Employer", "checkbox", False),
    ("Part 5. Additional Petitioner Info", "p5_1b_self", "1.b. Type of petitioner: Self", "checkbox", False),
    ("Part 5. Additional Petitioner Info", "p5_1c_other", "1.c. Type of petitioner: Other (explain in Item Number 2.)", "checkbox", False),
    ("Part 5. Additional Petitioner Info", "p5_2_other_explain", "2. If you selected 'Other', explain:", "text", False),
    ("Part 5. Additional Petitioner Info", "p5_3_num_employees", "3. Current Number of U.S. Employees", "number", False),
    ("Part 5. Additional Petitioner Info", "p5_4_year_established", "4. Year Established", "text", False),
    ("Part 5. Additional Petitioner Info", "p5_5_gross_annual_income", "5. Gross Annual Income", "text", False),
    ("Part 5. Additional Petitioner Info", "p5_6_net_annual_income", "6. Net Annual Income", "text", False),
    ("Part 5. Additional Petitioner Info", "p5_7_naics_code", "7. NAICS Code", "text", False),
    ("Part 5. Additional Petitioner Info", "p5_8_dol_case_number", "8. DOL Labor Certification Case Number", "text", False),
    ("Part 5. Additional Petitioner Info", "p5_9_dol_filing_date", "9. DOL Filing Date (mm/dd/yyyy)", "date", False),
    ("Part 5. Additional Petitioner Info", "p5_10_dol_expiration", "10. DOL Expiration Date (mm/dd/yyyy)", "date", False),
    ("Part 5. Additional Petitioner Info", "p5_11_occupation", "11. Occupation (if individual is filing for self)", "text", False),
    ("Part 5. Additional Petitioner Info", "p5_12_annual_income", "12. Annual Income (if individual is filing for self)", "text", False),

    # =========================================================================
    # PART 6: BASIC INFORMATION ABOUT THE PROPOSED EMPLOYMENT (Page 4-5)
    # =========================================================================
    ("Part 6. Proposed Employment", "p6_1_job_title", "1. Job Title", "text", True),
    ("Part 6. Proposed Employment", "p6_2_soc_code", "2. SOC (Standard Occupational Classification) Code", "text", False),
    ("Part 6. Proposed Employment", "p6_3_job_description", "3. Nontechnical Description of Job", "textarea", True),
    ("Part 6. Proposed Employment", "p6_4_full_time", "4. Is this a full-time position?", "radio", True),
    ("Part 6. Proposed Employment", "p6_5_hours_per_week", "5. If the answer to Item Number 4. is 'No,' how many hours per week for the position?", "number", False),
    ("Part 6. Proposed Employment", "p6_6_permanent", "6. Is this a permanent position?", "radio", True),
    ("Part 6. Proposed Employment", "p6_7_new_position", "7. Is this a new position?", "radio", True),
    ("Part 6. Proposed Employment", "p6_8_wages", "8. Wages Per (enter amount)", "text", True),
    ("Part 6. Proposed Employment", "p6_8_wage_period", "8. Per (select one: Hour, Week, Biweekly, Month, Year)", "select", True),

    # Worksite Address
    ("Part 6. Worksite Address", "p6_9a_street", "9.a. Street Number and Name", "text", True),
    ("Part 6. Worksite Address", "p6_9b_apt_type", "9.b. Apt./Ste./Flr.", "select", False),
    ("Part 6. Worksite Address", "p6_9b_apt_number", "9.b. Number", "text", False),
    ("Part 6. Worksite Address", "p6_9c_city", "9.c. City or Town", "text", True),
    ("Part 6. Worksite Address", "p6_9d_state", "9.d. State", "select", True),
    ("Part 6. Worksite Address", "p6_9e_zip", "9.e. ZIP Code", "text", True),
    ("Part 6. Worksite Address", "p6_9f_county", "9.f. County", "text", False),

    # =========================================================================
    # PART 7: INFORMATION ABOUT SPOUSE AND ALL CHILDREN (Pages 5)
    # (Repeating block for up to 5 family members)
    # =========================================================================
    # Family Member 1
    ("Part 7. Family Members", "p7_1_name_1", "1. Full Name of Spouse or Child", "text", False),
    ("Part 7. Family Members", "p7_2_relationship_1", "2. Relationship", "select", False),
    ("Part 7. Family Members", "p7_3_dob_1", "3. Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 7. Family Members", "p7_4_country_birth_1", "4. Country of Birth", "text", False),
    ("Part 7. Family Members", "p7_5_country_citizenship_1", "5. Country of Citizenship", "text", False),
    ("Part 7. Family Members", "p7_6_applying_adjustment_1", "6. Applying for Adjustment of Status?", "radio", False),
    ("Part 7. Family Members", "p7_7_applying_visa_1", "7. Applying for a Visa Abroad?", "radio", False),

    # Family Member 2
    ("Part 7. Family Members", "p7_1_name_2", "1. Full Name of Spouse or Child (2nd family member)", "text", False),
    ("Part 7. Family Members", "p7_2_relationship_2", "2. Relationship (2nd family member)", "select", False),
    ("Part 7. Family Members", "p7_3_dob_2", "3. Date of Birth (2nd family member)", "date", False),
    ("Part 7. Family Members", "p7_4_country_birth_2", "4. Country of Birth (2nd family member)", "text", False),
    ("Part 7. Family Members", "p7_5_country_citizenship_2", "5. Country of Citizenship (2nd family member)", "text", False),
    ("Part 7. Family Members", "p7_6_applying_adjustment_2", "6. Applying for Adjustment of Status? (2nd family member)", "radio", False),
    ("Part 7. Family Members", "p7_7_applying_visa_2", "7. Applying for a Visa Abroad? (2nd family member)", "radio", False),

    # Family Member 3
    ("Part 7. Family Members", "p7_1_name_3", "1. Full Name of Spouse or Child (3rd family member)", "text", False),
    ("Part 7. Family Members", "p7_2_relationship_3", "2. Relationship (3rd family member)", "select", False),
    ("Part 7. Family Members", "p7_3_dob_3", "3. Date of Birth (3rd family member)", "date", False),
    ("Part 7. Family Members", "p7_4_country_birth_3", "4. Country of Birth (3rd family member)", "text", False),
    ("Part 7. Family Members", "p7_5_country_citizenship_3", "5. Country of Citizenship (3rd family member)", "text", False),
    ("Part 7. Family Members", "p7_6_applying_adjustment_3", "6. Applying for Adjustment of Status? (3rd family member)", "radio", False),
    ("Part 7. Family Members", "p7_7_applying_visa_3", "7. Applying for a Visa Abroad? (3rd family member)", "radio", False),

    # Family Member 4
    ("Part 7. Family Members", "p7_1_name_4", "1. Full Name of Spouse or Child (4th family member)", "text", False),
    ("Part 7. Family Members", "p7_2_relationship_4", "2. Relationship (4th family member)", "select", False),
    ("Part 7. Family Members", "p7_3_dob_4", "3. Date of Birth (4th family member)", "date", False),
    ("Part 7. Family Members", "p7_4_country_birth_4", "4. Country of Birth (4th family member)", "text", False),
    ("Part 7. Family Members", "p7_5_country_citizenship_4", "5. Country of Citizenship (4th family member)", "text", False),
    ("Part 7. Family Members", "p7_6_applying_adjustment_4", "6. Applying for Adjustment of Status? (4th family member)", "radio", False),
    ("Part 7. Family Members", "p7_7_applying_visa_4", "7. Applying for a Visa Abroad? (4th family member)", "radio", False),

    # Family Member 5
    ("Part 7. Family Members", "p7_1_name_5", "1. Full Name of Spouse or Child (5th family member)", "text", False),
    ("Part 7. Family Members", "p7_2_relationship_5", "2. Relationship (5th family member)", "select", False),
    ("Part 7. Family Members", "p7_3_dob_5", "3. Date of Birth (5th family member)", "date", False),
    ("Part 7. Family Members", "p7_4_country_birth_5", "4. Country of Birth (5th family member)", "text", False),
    ("Part 7. Family Members", "p7_5_country_citizenship_5", "5. Country of Citizenship (5th family member)", "text", False),
    ("Part 7. Family Members", "p7_6_applying_adjustment_5", "6. Applying for Adjustment of Status? (5th family member)", "radio", False),
    ("Part 7. Family Members", "p7_7_applying_visa_5", "7. Applying for a Visa Abroad? (5th family member)", "radio", False),

    # =========================================================================
    # PART 8: CONTACT INFORMATION, CERTIFICATION, AND SIGNATURE OF PETITIONER
    # (Pages 5-6)
    # =========================================================================
    ("Part 8. Petitioner Statement", "p8_1a_read_english", "1.a. I can read and understand English, and I have read and understand every question and instruction on this petition and my answer to every question", "checkbox", False),
    ("Part 8. Petitioner Statement", "p8_1b_interpreter", "1.b. The interpreter named in Part 9. read to me every question and instruction on this petition and my answer to every question in a language in which I am fluent", "checkbox", False),
    ("Part 8. Petitioner Statement", "p8_2_preparer", "2. At my request, the preparer named in Part 10., prepared this petition for me based only upon information I provided or authorized", "checkbox", False),

    # Contact Info
    ("Part 8. Petitioner Contact", "p8_3a_family_name", "3.a. Petitioner's or Authorized Signatory's Family Name (Last Name)", "text", True),
    ("Part 8. Petitioner Contact", "p8_3b_given_name", "3.b. Petitioner's or Authorized Signatory's Given Name (First Name)", "text", True),
    ("Part 8. Petitioner Contact", "p8_4_title", "4. Title of Authorized Signatory of Petitioning Organization (if applicable)", "text", False),
    ("Part 8. Petitioner Contact", "p8_5_phone", "5. Petitioner's Daytime Telephone Number", "phone", False),
    ("Part 8. Petitioner Contact", "p8_6_mobile", "6. Petitioner's Mobile Telephone Number (if any)", "phone", False),
    ("Part 8. Petitioner Contact", "p8_7_email", "7. Petitioner's Email Address (if any)", "email", False),

    # Signature
    ("Part 8. Petitioner Signature", "p8_8a_signature", "8.a. Petitioner's or Authorized Signatory's Signature", "text", True),
    ("Part 8. Petitioner Signature", "p8_8b_date", "8.b. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 9: INTERPRETER'S CONTACT INFORMATION, CERTIFICATION, AND SIGNATURE
    # (Pages 6-7)
    # =========================================================================
    ("Part 9. Interpreter Info", "interpreter_1a_family_name", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("Part 9. Interpreter Info", "interpreter_1b_given_name", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("Part 9. Interpreter Info", "interpreter_2_business", "2. Interpreter's Business or Organization Name (if any)", "text", False),

    # Interpreter Address
    ("Part 9. Interpreter Address", "interpreter_3a_street", "3.a. Interpreter's Mailing Address - Street Number and Name", "text", False),
    ("Part 9. Interpreter Address", "interpreter_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 9. Interpreter Address", "interpreter_3b_apt_number", "3.b. Number", "text", False),
    ("Part 9. Interpreter Address", "interpreter_3c_city", "3.c. City or Town", "text", False),
    ("Part 9. Interpreter Address", "interpreter_3d_state", "3.d. State", "select", False),
    ("Part 9. Interpreter Address", "interpreter_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 9. Interpreter Address", "interpreter_3f_province", "3.f. Province (foreign address only)", "text", False),
    ("Part 9. Interpreter Address", "interpreter_3g_postal", "3.g. Postal Code (foreign address only)", "text", False),
    ("Part 9. Interpreter Address", "interpreter_3h_country", "3.h. Country (foreign address only)", "text", False),

    # Interpreter Contact
    ("Part 9. Interpreter Contact", "interpreter_4_phone", "4. Interpreter's Daytime Telephone Number", "phone", False),
    ("Part 9. Interpreter Contact", "interpreter_5_mobile", "5. Interpreter's Mobile Telephone Number (if any)", "phone", False),
    ("Part 9. Interpreter Contact", "interpreter_6a_email", "6.a. Interpreter's Email Address (if any)", "email", False),
    ("Part 9. Interpreter Contact", "interpreter_6b_language", "6.b. Language Interpreted", "text", False),

    # Interpreter Signature
    ("Part 9. Interpreter Signature", "interpreter_7a_signature", "7.a. Interpreter's Signature", "text", False),
    ("Part 9. Interpreter Signature", "interpreter_7b_date", "7.b. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 10: PREPARER'S CONTACT INFORMATION, CERTIFICATION, AND SIGNATURE
    # (Pages 7-8)
    # =========================================================================
    ("Part 10. Preparer Info", "preparer_1a_family_name", "1.a. Preparer's Family Name (Last Name)", "text", False),
    ("Part 10. Preparer Info", "preparer_1b_given_name", "1.b. Preparer's Given Name (First Name)", "text", False),
    ("Part 10. Preparer Info", "preparer_2_business", "2. Preparer's Business or Organization Name (if any)", "text", False),

    # Preparer Address
    ("Part 10. Preparer Address", "preparer_3a_street", "3.a. Preparer's Mailing Address - Street Number and Name", "text", False),
    ("Part 10. Preparer Address", "preparer_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 10. Preparer Address", "preparer_3b_apt_number", "3.b. Number", "text", False),
    ("Part 10. Preparer Address", "preparer_3c_city", "3.c. City or Town", "text", False),
    ("Part 10. Preparer Address", "preparer_3d_state", "3.d. State", "select", False),
    ("Part 10. Preparer Address", "preparer_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 10. Preparer Address", "preparer_3f_province", "3.f. Province (foreign address only)", "text", False),
    ("Part 10. Preparer Address", "preparer_3g_postal", "3.g. Postal Code (foreign address only)", "text", False),
    ("Part 10. Preparer Address", "preparer_3h_country", "3.h. Country (foreign address only)", "text", False),

    # Preparer Contact
    ("Part 10. Preparer Contact", "preparer_4_phone", "4. Preparer's Daytime Telephone Number", "phone", False),
    ("Part 10. Preparer Contact", "preparer_5_fax", "5. Preparer's Fax Number (if any)", "text", False),
    ("Part 10. Preparer Contact", "preparer_6_email", "6. Preparer's Email Address (if any)", "email", False),

    # Preparer Statement
    ("Part 10. Preparer Statement", "preparer_7a_not_attorney", "7.a. I am not an attorney or accredited representative but have prepared this petition on behalf of the petitioner and with the petitioner's consent", "checkbox", False),
    ("Part 10. Preparer Statement", "preparer_7b_is_attorney", "7.b. I am an attorney or accredited representative and my representation of the petitioner in this case extends/does not extend beyond the preparation of this petition", "checkbox", False),
    ("Part 10. Preparer Statement", "preparer_7b_extends", "7.b. Extends beyond preparation", "checkbox", False),
    ("Part 10. Preparer Statement", "preparer_7b_not_extends", "7.b. Does NOT extend beyond preparation", "checkbox", False),

    # Preparer Signature
    ("Part 10. Preparer Signature", "preparer_8a_signature", "8.a. Preparer's Signature", "text", False),
    ("Part 10. Preparer Signature", "preparer_8b_date", "8.b. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 11: ADDITIONAL INFORMATION (Page 8)
    # =========================================================================
    ("Part 11. Additional Information", "p11_1a_family_name", "1.a. Family Name (Last Name)", "text", False),
    ("Part 11. Additional Information", "p11_1b_given_name", "1.b. Given Name (First Name)", "text", False),
    ("Part 11. Additional Information", "p11_1c_middle_name", "1.c. Middle Name", "text", False),
    ("Part 11. Additional Information", "p11_2_a_number", "2. A-Number (if any)", "text", False),

    # Additional Info Block 1
    ("Part 11. Additional Information", "p11_3a_page_1", "3.a. Page Number", "text", False),
    ("Part 11. Additional Information", "p11_3b_part_1", "3.b. Part Number", "text", False),
    ("Part 11. Additional Information", "p11_3c_item_1", "3.c. Item Number", "text", False),
    ("Part 11. Additional Information", "p11_3d_info_1", "3.d. Additional Information", "textarea", False),

    # Additional Info Block 2
    ("Part 11. Additional Information", "p11_4a_page_2", "4.a. Page Number", "text", False),
    ("Part 11. Additional Information", "p11_4b_part_2", "4.b. Part Number", "text", False),
    ("Part 11. Additional Information", "p11_4c_item_2", "4.c. Item Number", "text", False),
    ("Part 11. Additional Information", "p11_4d_info_2", "4.d. Additional Information", "textarea", False),

    # Additional Info Block 3
    ("Part 11. Additional Information", "p11_5a_page_3", "5.a. Page Number", "text", False),
    ("Part 11. Additional Information", "p11_5b_part_3", "5.b. Part Number", "text", False),
    ("Part 11. Additional Information", "p11_5c_item_3", "5.c. Item Number", "text", False),
    ("Part 11. Additional Information", "p11_5d_info_3", "5.d. Additional Information", "textarea", False),

    # Additional Info Block 4
    ("Part 11. Additional Information", "p11_6a_page_4", "6.a. Page Number", "text", False),
    ("Part 11. Additional Information", "p11_6b_part_4", "6.b. Part Number", "text", False),
    ("Part 11. Additional Information", "p11_6c_item_4", "6.c. Item Number", "text", False),
    ("Part 11. Additional Information", "p11_6d_info_4", "6.d. Additional Information", "textarea", False),
]

# Options for select/radio fields
OPTIONS_MAP = {
    "p1_5_nonprofit": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p1_6_25_or_fewer_employees": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p1_8b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p1_8d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","PR","VI","GU","AS","MP"],
    "p3_2b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p3_2d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","PR","VI","GU","AS","MP"],
    "p3_11_gender": [{"value": "Male", "label": "Male"}, {"value": "Female", "label": "Female"}],
    "p4_6a_other_petitions": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p4_6b_removal_proceedings": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p4_7_prior_immigrant_visa": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p4_8_labor_cert_filed": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p4_9_prior_i140": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p4_10_duplicate_labor_cert": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p6_4_full_time": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p6_6_permanent": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p6_7_new_position": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p6_8_wage_period": ["Hour", "Week", "Biweekly", "Month", "Year"],
    "p6_9b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p6_9d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","PR","VI","GU","AS","MP"],
    "p7_2_relationship_1": [{"value": "Spouse", "label": "Spouse"}, {"value": "Son", "label": "Son"}, {"value": "Daughter", "label": "Daughter"}],
    "p7_6_applying_adjustment_1": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p7_7_applying_visa_1": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p7_2_relationship_2": [{"value": "Spouse", "label": "Spouse"}, {"value": "Son", "label": "Son"}, {"value": "Daughter", "label": "Daughter"}],
    "p7_6_applying_adjustment_2": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p7_7_applying_visa_2": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p7_2_relationship_3": [{"value": "Spouse", "label": "Spouse"}, {"value": "Son", "label": "Son"}, {"value": "Daughter", "label": "Daughter"}],
    "p7_6_applying_adjustment_3": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p7_7_applying_visa_3": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p7_2_relationship_4": [{"value": "Spouse", "label": "Spouse"}, {"value": "Son", "label": "Son"}, {"value": "Daughter", "label": "Daughter"}],
    "p7_6_applying_adjustment_4": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p7_7_applying_visa_4": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p7_2_relationship_5": [{"value": "Spouse", "label": "Spouse"}, {"value": "Son", "label": "Son"}, {"value": "Daughter", "label": "Daughter"}],
    "p7_6_applying_adjustment_5": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "p7_7_applying_visa_5": [{"value": "Yes", "label": "Yes"}, {"value": "No", "label": "No"}],
    "interpreter_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "interpreter_3d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","PR","VI","GU","AS","MP"],
    "preparer_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "preparer_3d_state": ["AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","PR","VI","GU","AS","MP"],
}


def update_i140(template_id=None):
    """Insert or update I-140 fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-140%' "
                "AND name NOT LIKE '%specific%' AND name NOT LIKE '%OLD%' "
                "ORDER BY id ASC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('I-140 - Immigrant Petition for Alien Workers (EXPANDED)', "
                    "'Complete I-140 with all official USCIS fields - Edition 06/07/24') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(I140_FIELDS):
            options = OPTIONS_MAP.get(field_name)
            conn.execute(text(
                "INSERT INTO questionnaire_fields (template_id, section, field_name, label, field_type, is_required, \"order\", options) "
                "VALUES (:tid, :section, :field_name, :label, :field_type, :is_required, :order, :options)"
            ), {
                "tid": template_id, "section": section, "field_name": field_name,
                "label": label, "field_type": field_type, "is_required": required, "order": i + 1,
                "options": json.dumps(options) if options else None
            })

        conn.commit()
        print(f"I-140 expanded: template_id={template_id}, fields={len(I140_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_i140()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(I140_FIELDS)}")

    sections = {}
    for section, _, _, _, _ in I140_FIELDS:
        sections[section] = sections.get(section, 0) + 1

    print("\nFields by section:")
    for section, count in sections.items():
        print(f"  {section}: {count}")

    # Check for duplicates
    field_names = [field_name for _, field_name, _, _, _ in I140_FIELDS]
    duplicates = [name for name in field_names if field_names.count(name) > 1]
    if duplicates:
        print(f"\nWARNING: Duplicate field names found: {set(duplicates)}")
    else:
        print("\nNo duplicate field names found.")
