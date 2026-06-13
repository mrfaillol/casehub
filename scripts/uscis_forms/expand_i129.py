#!/usr/bin/env python3
"""
Expand I-129 (Petition for a Nonimmigrant Worker) with essential USCIS fields.
Edition 01/20/25 - Core petition (Parts 1-7) + H-1B/H-2/E-1/E-2 supplements.
This script focuses on the most commonly used fields for practical form completion.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I129_FIELDS = [
    # =========================================================================
    # USCIS USE ONLY - Receipt Section (Page 1 - top)
    # =========================================================================
    ("USCIS Receipt", "receipt_class", "Class", "text", False),
    ("USCIS Receipt", "receipt_num_workers", "No. of Workers", "text", False),
    ("USCIS Receipt", "receipt_job_code", "Job Code", "text", False),
    ("USCIS Receipt", "receipt_validity_from", "Validity Dates - From", "date", False),
    ("USCIS Receipt", "receipt_validity_to", "Validity Dates - To", "date", False),

    # =========================================================================
    # PART 1: PETITIONER INFORMATION (Page 1)
    # =========================================================================
    # Item 1: Individual Petitioner
    ("Part 1. Petitioner - Individual", "p1_1_family_name", "1. Individual - Family Name (Last Name)", "text", False),
    ("Part 1. Petitioner - Individual", "p1_1_given_name", "1. Individual - Given Name (First Name)", "text", False),
    ("Part 1. Petitioner - Individual", "p1_1_middle_name", "1. Individual - Middle Name", "text", False),

    # Item 2: Company/Organization
    ("Part 1. Petitioner - Company", "p1_2_company_name", "2. Company or Organization Name", "text", False),

    # Item 3: Mailing Address
    ("Part 1. Petitioner - Mailing Address", "p1_3_in_care_of", "3. Mailing Address - In Care Of Name", "text", False),
    ("Part 1. Petitioner - Mailing Address", "p1_3_street", "3. Mailing Address - Street Number and Name", "text", True),
    ("Part 1. Petitioner - Mailing Address", "p1_3_apt", "3. Mailing Address - Apt. Number", "text", False),
    ("Part 1. Petitioner - Mailing Address", "p1_3_ste", "3. Mailing Address - Ste.", "text", False),
    ("Part 1. Petitioner - Mailing Address", "p1_3_flr", "3. Mailing Address - Flr.", "text", False),
    ("Part 1. Petitioner - Mailing Address", "p1_3_city", "3. Mailing Address - City or Town", "text", True),
    ("Part 1. Petitioner - Mailing Address", "p1_3_state", "3. Mailing Address - State", "select", False),
    ("Part 1. Petitioner - Mailing Address", "p1_3_zip", "3. Mailing Address - ZIP Code", "text", True),
    ("Part 1. Petitioner - Mailing Address", "p1_3_province", "3. Mailing Address - Province", "text", False),
    ("Part 1. Petitioner - Mailing Address", "p1_3_postal_code", "3. Mailing Address - Postal Code", "text", False),
    ("Part 1. Petitioner - Mailing Address", "p1_3_country", "3. Mailing Address - Country", "text", False),

    # Item 4: Contact Information
    ("Part 1. Petitioner - Contact", "p1_4_daytime_phone", "4. Daytime Telephone Number", "phone", False),
    ("Part 1. Petitioner - Contact", "p1_4_mobile_phone", "4. Mobile Telephone Number", "phone", False),
    ("Part 1. Petitioner - Contact", "p1_4_email", "4. Email Address (if any)", "email", False),

    # Item 5-8: Other Information
    ("Part 1. Petitioner - Other Information", "p1_5_fein", "5. Federal Employer Identification Number (FEIN)", "text", False),
    ("Part 1. Petitioner - Other Information", "p1_6_nonprofit", "6. Are you a nonprofit organized as tax exempt?", "radio", False),
    ("Part 1. Petitioner - Other Information", "p1_7_irs_tax_number", "7. Individual IRS Tax Number", "text", False),
    ("Part 1. Petitioner - Other Information", "p1_8_ssn", "8. U.S. Social Security Number (if any)", "text", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT THIS PETITION (Page 2)
    # =========================================================================
    ("Part 2. Petition Information", "p2_1_classification", "1. Requested Nonimmigrant Classification (classification symbol)", "text", True),
    ("Part 2. Petition Information", "p2_2_basis_new", "2. Basis - a. New employment", "checkbox", False),
    ("Part 2. Petition Information", "p2_2_basis_continuation", "2. Basis - b. Continuation without change", "checkbox", False),
    ("Part 2. Petition Information", "p2_2_basis_change", "2. Basis - c. Change in previously approved employment", "checkbox", False),
    ("Part 2. Petition Information", "p2_2_basis_concurrent", "2. Basis - d. New concurrent employment", "checkbox", False),
    ("Part 2. Petition Information", "p2_2_basis_change_employer", "2. Basis - e. Change of employer", "checkbox", False),
    ("Part 2. Petition Information", "p2_2_basis_amended", "2. Basis - f. Amended petition", "checkbox", False),
    ("Part 2. Petition Information", "p2_3_prior_receipt", "3. Most recent petition/application receipt number for beneficiary", "text", False),

    # Item 4: Requested Action
    ("Part 2. Petition Information", "p2_4_action_notify", "4. Requested Action - a. Notify office in Part 4", "checkbox", False),
    ("Part 2. Petition Information", "p2_4_action_change_status", "4. Requested Action - b. Change/extend status", "checkbox", False),
    ("Part 2. Petition Information", "p2_4_action_extend_stay", "4. Requested Action - c. Extend stay", "checkbox", False),
    ("Part 2. Petition Information", "p2_4_action_amend", "4. Requested Action - d. Amend stay", "checkbox", False),
    ("Part 2. Petition Information", "p2_4_action_extend_trade", "4. Requested Action - e. Extend status (free trade)", "checkbox", False),
    ("Part 2. Petition Information", "p2_4_action_change_trade", "4. Requested Action - f. Change status (free trade)", "checkbox", False),

    ("Part 2. Petition Information", "p2_5_total_workers", "5. Total number of workers included in this petition", "text", False),

    # =========================================================================
    # PART 3: BENEFICIARY INFORMATION (Pages 2-3)
    # =========================================================================
    ("Part 3. Beneficiary Information", "p3_1_type_named", "1. Type - Named", "checkbox", False),
    ("Part 3. Beneficiary Information", "p3_1_type_unnamed", "1. Type - Unnamed (H-2A/H-2B only)", "checkbox", False),
    ("Part 3. Beneficiary Information", "p3_2_group_name", "2. Entertainment Group Name (if applicable)", "text", False),

    # Item 3: Name of Beneficiary
    ("Part 3. Beneficiary - Name", "p3_3_family_name", "3. Beneficiary - Family Name (Last Name)", "text", True),
    ("Part 3. Beneficiary - Name", "p3_3_given_name", "3. Beneficiary - Given Name (First Name)", "text", True),
    ("Part 3. Beneficiary - Name", "p3_3_middle_name", "3. Beneficiary - Middle Name", "text", False),

    # Item 4: Other Names
    ("Part 3. Beneficiary - Other Names", "p3_4_other_family_1", "4. Other Names - Family Name 1", "text", False),
    ("Part 3. Beneficiary - Other Names", "p3_4_other_given_1", "4. Other Names - Given Name 1", "text", False),
    ("Part 3. Beneficiary - Other Names", "p3_4_other_middle_1", "4. Other Names - Middle Name 1", "text", False),
    ("Part 3. Beneficiary - Other Names", "p3_4_other_family_2", "4. Other Names - Family Name 2", "text", False),
    ("Part 3. Beneficiary - Other Names", "p3_4_other_given_2", "4. Other Names - Given Name 2", "text", False),
    ("Part 3. Beneficiary - Other Names", "p3_4_other_middle_2", "4. Other Names - Middle Name 2", "text", False),

    # Item 5: Other Information
    ("Part 3. Beneficiary - Personal Info", "p3_5_dob", "5. Date of birth (mm/dd/yyyy)", "date", True),
    ("Part 3. Beneficiary - Personal Info", "p3_5_sex", "5. Sex", "radio", True),
    ("Part 3. Beneficiary - Personal Info", "p3_5_ssn", "5. U.S. Social Security Number (if any)", "text", False),
    ("Part 3. Beneficiary - Personal Info", "p3_5_a_number", "5. A-Number (Alien Registration Number)", "text", False),
    ("Part 3. Beneficiary - Personal Info", "p3_5_country_birth", "5. Country of Birth", "text", True),
    ("Part 3. Beneficiary - Personal Info", "p3_5_province_birth", "5. Province of Birth", "text", False),
    ("Part 3. Beneficiary - Personal Info", "p3_5_country_citizenship", "5. Country of Citizenship or Nationality", "text", True),

    # Item 6: If beneficiary in U.S.
    ("Part 3. Beneficiary - U.S. Status", "p3_6_last_arrival", "6. Date of Last Arrival (mm/dd/yyyy)", "date", False),
    ("Part 3. Beneficiary - U.S. Status", "p3_6_i94_number", "6. I-94 Arrival-Departure Record Number", "text", False),
    ("Part 3. Beneficiary - U.S. Status", "p3_6_passport_number", "6. Passport or Travel Document Number", "text", False),
    ("Part 3. Beneficiary - U.S. Status", "p3_6_passport_issued", "6. Date Passport Issued (mm/dd/yyyy)", "date", False),
    ("Part 3. Beneficiary - U.S. Status", "p3_6_passport_expires", "6. Date Passport Expires (mm/dd/yyyy)", "date", False),
    ("Part 3. Beneficiary - U.S. Status", "p3_6_passport_country", "6. Passport Country of Issuance", "text", False),
    ("Part 3. Beneficiary - U.S. Status", "p3_6_current_status", "6. Current Nonimmigrant Status", "text", False),
    ("Part 3. Beneficiary - U.S. Status", "p3_6_status_expires", "6. Date Status Expires (mm/dd/yyyy) or D/S", "text", False),
    ("Part 3. Beneficiary - U.S. Status", "p3_6_sevis", "6. SEVIS Number (if any)", "text", False),
    ("Part 3. Beneficiary - U.S. Status", "p3_6_ead", "6. Employment Authorization Document (EAD) Number (if any)", "text", False),

    # Item 7: Current U.S. Address
    ("Part 3. Beneficiary - U.S. Address", "p3_7_street", "7. Current U.S. Address - Street Number and Name", "text", False),
    ("Part 3. Beneficiary - U.S. Address", "p3_7_apt", "7. Current U.S. Address - Apt. Number", "text", False),
    ("Part 3. Beneficiary - U.S. Address", "p3_7_ste", "7. Current U.S. Address - Ste.", "text", False),
    ("Part 3. Beneficiary - U.S. Address", "p3_7_flr", "7. Current U.S. Address - Flr.", "text", False),
    ("Part 3. Beneficiary - U.S. Address", "p3_7_city", "7. Current U.S. Address - City or Town", "text", False),
    ("Part 3. Beneficiary - U.S. Address", "p3_7_state", "7. Current U.S. Address - State", "select", False),
    ("Part 3. Beneficiary - U.S. Address", "p3_7_zip", "7. Current U.S. Address - ZIP Code", "text", False),

    # =========================================================================
    # PART 4: PROCESSING INFORMATION (Pages 3-4)
    # =========================================================================
    # Item 1: Consular Processing
    ("Part 4. Processing Information", "p4_1_type_consulate", "1.a. Type of Office - Consulate", "checkbox", False),
    ("Part 4. Processing Information", "p4_1_type_preflight", "1.a. Type of Office - Pre-flight inspection", "checkbox", False),
    ("Part 4. Processing Information", "p4_1_type_poe", "1.a. Type of Office - Port of Entry", "checkbox", False),
    ("Part 4. Processing Information", "p4_1b_office_city", "1.b. Office Address (City)", "text", False),
    ("Part 4. Processing Information", "p4_1c_office_country", "1.c. U.S. State or Foreign Country", "text", False),

    # Item 4d: Beneficiary's Foreign Address
    ("Part 4. Beneficiary - Foreign Address", "p4_d_street", "d. Foreign Address - Street Number and Name", "text", False),
    ("Part 4. Beneficiary - Foreign Address", "p4_d_apt", "d. Foreign Address - Apt./Ste./Flr. Number", "text", False),
    ("Part 4. Beneficiary - Foreign Address", "p4_d_city", "d. Foreign Address - City or Town", "text", False),
    ("Part 4. Beneficiary - Foreign Address", "p4_d_state", "d. Foreign Address - State", "text", False),
    ("Part 4. Beneficiary - Foreign Address", "p4_d_province", "d. Foreign Address - Province", "text", False),
    ("Part 4. Beneficiary - Foreign Address", "p4_d_postal_code", "d. Foreign Address - Postal Code", "text", False),
    ("Part 4. Beneficiary - Foreign Address", "p4_d_country", "d. Foreign Address - Country", "text", False),

    # Items 2-11: Processing Questions
    ("Part 4. Processing Questions", "p4_2_valid_passport", "2. Does each person in this petition have a valid passport?", "radio", False),
    ("Part 4. Processing Questions", "p4_3_other_petitions", "3. Are you filing any other petitions with this one?", "radio", False),
    ("Part 4. Processing Questions", "p4_3_how_many", "3. If Yes, how many?", "text", False),
    ("Part 4. Processing Questions", "p4_4_i94_replacement", "4. Filing I-94 replacement applications with this petition?", "radio", False),
    ("Part 4. Processing Questions", "p4_4_how_many", "4. If Yes, how many?", "text", False),
    ("Part 4. Processing Questions", "p4_5_dependent_applications", "5. Filing dependent applications with this petition?", "radio", False),
    ("Part 4. Processing Questions", "p4_5_how_many", "5. If Yes, how many?", "text", False),
    ("Part 4. Processing Questions", "p4_6_removal_proceedings", "6. Is any beneficiary in removal proceedings?", "radio", False),
    ("Part 4. Processing Questions", "p4_7_prior_immigration_petition", "7. Have you ever filed an immigration petition for any beneficiary?", "radio", False),
    ("Part 4. Processing Questions", "p4_7_how_many", "7. If Yes, how many?", "text", False),
    ("Part 4. Processing Questions", "p4_8_new_petition", "8. Did you indicate you were filing a new petition in Part 2?", "radio", False),
    ("Part 4. Processing Questions", "p4_8a_classification_given", "8.a. Classification given within last 7 years?", "radio", False),
    ("Part 4. Processing Questions", "p4_8b_classification_denied", "8.b. Classification denied within last 7 years?", "radio", False),
    ("Part 4. Processing Questions", "p4_9_prior_nonimmigrant", "9. Previously filed nonimmigrant petition for beneficiary?", "radio", False),
    ("Part 4. Processing Questions", "p4_10_entertainment_group", "10. Entertainment group - beneficiary not with group 1+ year?", "radio", False),
    ("Part 4. Processing Questions", "p4_11a_j1_exchange", "11.a. Beneficiary been J-1 or J-2 dependent?", "radio", False),
    ("Part 4. Processing Questions", "p4_11b_j1_dates", "11.b. If Yes, provide dates and evidence", "textarea", False),

    # =========================================================================
    # PART 5: BASIC INFORMATION ABOUT PROPOSED EMPLOYMENT (Pages 5-6)
    # =========================================================================
    ("Part 5. Employment Information", "p5_1_job_title", "1. Job Title", "text", True),
    ("Part 5. Employment Information", "p5_2_lca_eta_case", "2. LCA or ETA Case Number", "text", False),

    # Item 3: Work Address 1
    ("Part 5. Work Address 1", "p5_3_addr1_street", "3. Address 1 - Street Number and Name", "text", False),
    ("Part 5. Work Address 1", "p5_3_addr1_apt", "3. Address 1 - Apt./Ste./Flr. Number", "text", False),
    ("Part 5. Work Address 1", "p5_3_addr1_city", "3. Address 1 - City or Town", "text", False),
    ("Part 5. Work Address 1", "p5_3_addr1_state", "3. Address 1 - State", "select", False),
    ("Part 5. Work Address 1", "p5_3_addr1_zip", "3. Address 1 - ZIP Code", "text", False),
    ("Part 5. Work Address 1", "p5_3_addr1_third_party", "3. Address 1 - Third-party location?", "radio", False),
    ("Part 5. Work Address 1", "p5_3_addr1_third_party_name", "3. Address 1 - Third-party organization name", "text", False),

    # Item 3: Work Address 2
    ("Part 5. Work Address 2", "p5_3_addr2_street", "3. Address 2 - Street Number and Name", "text", False),
    ("Part 5. Work Address 2", "p5_3_addr2_apt", "3. Address 2 - Apt./Ste./Flr. Number", "text", False),
    ("Part 5. Work Address 2", "p5_3_addr2_city", "3. Address 2 - City or Town", "text", False),
    ("Part 5. Work Address 2", "p5_3_addr2_state", "3. Address 2 - State", "select", False),
    ("Part 5. Work Address 2", "p5_3_addr2_zip", "3. Address 2 - ZIP Code", "text", False),
    ("Part 5. Work Address 2", "p5_3_addr2_third_party", "3. Address 2 - Third-party location?", "radio", False),
    ("Part 5. Work Address 2", "p5_3_addr2_third_party_name", "3. Address 2 - Third-party organization name", "text", False),

    # Items 4-11: Employment Details
    ("Part 5. Employment Details", "p5_4_itinerary_included", "4. Did you include an itinerary with the petition?", "radio", False),
    ("Part 5. Employment Details", "p5_5_work_offsite", "5. Will beneficiary work off-site at another location?", "radio", False),
    ("Part 5. Employment Details", "p5_6_work_cnmi", "6. Work exclusively in CNMI?", "radio", False),
    ("Part 5. Employment Details", "p5_7_full_time", "7. Is this a full-time position?", "radio", False),
    ("Part 5. Employment Details", "p5_8_hours_per_week", "8. If no, how many hours per week for the position?", "text", False),
    ("Part 5. Employment Details", "p5_9_wages", "9. Wages: $", "text", False),
    ("Part 5. Employment Details", "p5_9_wages_per", "9. Wages per (hour, week, month, year)", "text", False),
    ("Part 5. Employment Details", "p5_10_other_compensation", "10. Other Compensation (Explain)", "textarea", False),
    ("Part 5. Employment Details", "p5_11_employment_from", "11. Dates of intended employment - From (mm/dd/yyyy)", "date", False),
    ("Part 5. Employment Details", "p5_11_employment_to", "11. Dates of intended employment - To (mm/dd/yyyy)", "date", False),

    # Items 12-17: Company Information
    ("Part 5. Company Information", "p5_12_type_business", "12. Type of Business", "text", False),
    ("Part 5. Company Information", "p5_13_year_established", "13. Year Established", "text", False),
    ("Part 5. Company Information", "p5_14_current_employees", "14. Current Number of Employees in the United States", "text", False),
    ("Part 5. Company Information", "p5_15_small_employer", "15. Employ 25 or fewer full-time equivalent employees?", "radio", False),
    ("Part 5. Company Information", "p5_16_gross_income", "16. Gross Annual Income", "text", False),
    ("Part 5. Company Information", "p5_17_net_income", "17. Net Annual Income", "text", False),

    # =========================================================================
    # PART 6: CERTIFICATION - CONTROLLED TECHNOLOGY (Page 6)
    # =========================================================================
    ("Part 6. Technology Certification", "p6_1_no_license", "1. No license required from Commerce or State", "checkbox", False),
    ("Part 6. Technology Certification", "p6_2_license_required", "2. License required - will prevent access until authorized", "checkbox", False),

    # =========================================================================
    # PART 7: PETITIONER'S DECLARATION AND SIGNATURE (Pages 6-7)
    # =========================================================================
    ("Part 7. Petitioner Signature", "p7_1_signatory_family_name", "1. Authorized Signatory - Family Name (Last Name)", "text", True),
    ("Part 7. Petitioner Signature", "p7_1_signatory_given_name", "1. Authorized Signatory - Given Name (First Name)", "text", True),
    ("Part 7. Petitioner Signature", "p7_1_signatory_title", "1. Authorized Signatory - Title", "text", True),
    ("Part 7. Petitioner Signature", "p7_2_signature_date", "2. Signature Date (mm/dd/yyyy)", "date", True),
    ("Part 7. Petitioner Signature", "p7_3_daytime_phone", "3. Daytime Telephone Number", "phone", False),
    ("Part 7. Petitioner Signature", "p7_3_email", "3. Email Address (if any)", "email", False),

    # =========================================================================
    # PART 8: PREPARER'S DECLARATION AND SIGNATURE (Page 7)
    # =========================================================================
    ("Part 8. Preparer Information", "p8_1_preparer_family_name", "1. Preparer - Family Name (Last Name)", "text", False),
    ("Part 8. Preparer Information", "p8_1_preparer_given_name", "1. Preparer - Given Name (First Name)", "text", False),
    ("Part 8. Preparer Information", "p8_2_business_name", "2. Preparer's Business or Organization Name (if any)", "text", False),

    # Item 3: Preparer's Mailing Address
    ("Part 8. Preparer - Mailing Address", "p8_3_street", "3. Preparer - Street Number and Name", "text", False),
    ("Part 8. Preparer - Mailing Address", "p8_3_apt", "3. Preparer - Apt./Ste./Flr. Number", "text", False),
    ("Part 8. Preparer - Mailing Address", "p8_3_city", "3. Preparer - City or Town", "text", False),
    ("Part 8. Preparer - Mailing Address", "p8_3_state", "3. Preparer - State", "select", False),
    ("Part 8. Preparer - Mailing Address", "p8_3_zip", "3. Preparer - ZIP Code", "text", False),
    ("Part 8. Preparer - Mailing Address", "p8_3_province", "3. Preparer - Province", "text", False),
    ("Part 8. Preparer - Mailing Address", "p8_3_postal_code", "3. Preparer - Postal Code", "text", False),
    ("Part 8. Preparer - Mailing Address", "p8_3_country", "3. Preparer - Country", "text", False),

    # Item 4: Preparer's Contact
    ("Part 8. Preparer - Contact", "p8_4_daytime_phone", "4. Preparer - Daytime Telephone Number", "phone", False),
    ("Part 8. Preparer - Contact", "p8_4_fax", "4. Preparer - Fax Number", "text", False),
    ("Part 8. Preparer - Contact", "p8_4_email", "4. Preparer - Email Address (if any)", "email", False),

    ("Part 8. Preparer Signature", "p8_5_signature_date", "5. Preparer Signature Date (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 9: ADDITIONAL INFORMATION (Page 8)
    # =========================================================================
    ("Part 9. Additional Information", "p9_1_a_number", "1. A-Number", "text", False),
    ("Part 9. Additional Information", "p9_2_page_number", "2. Page Number", "text", False),
    ("Part 9. Additional Information", "p9_2_part_number", "2. Part Number", "text", False),
    ("Part 9. Additional Information", "p9_2_item_number", "2. Item Number", "text", False),
    ("Part 9. Additional Information", "p9_additional_text", "Additional Information", "textarea", False),

    # =========================================================================
    # E-1/E-2 SUPPLEMENT (Page 9-10)
    # =========================================================================
    ("E-1/E-2 Supplement", "e_1_petitioner_name", "Name of the Petitioner", "text", False),
    ("E-1/E-2 Supplement", "e_2_beneficiary_family_name", "Beneficiary - Family Name (Last Name)", "text", False),
    ("E-1/E-2 Supplement", "e_2_beneficiary_given_name", "Beneficiary - Given Name (First Name)", "text", False),
    ("E-1/E-2 Supplement", "e_2_beneficiary_middle_name", "Beneficiary - Middle Name", "text", False),
    ("E-1/E-2 Supplement", "e_3_class_e1_trader", "3. Classification - E-1 Treaty Trader", "checkbox", False),
    ("E-1/E-2 Supplement", "e_3_class_e2_investor", "3. Classification - E-2 Treaty Investor", "checkbox", False),
    ("E-1/E-2 Supplement", "e_3_class_e2_cnmi", "3. Classification - E-2 CNMI Investor", "checkbox", False),
    ("E-1/E-2 Supplement", "e_4_treaty_country", "4. Name of country signatory to treaty with United States", "text", False),
    ("E-1/E-2 Supplement", "e_5_seeking_advice", "5. Seeking advice from USCIS re: substantive changes?", "radio", False),

    # Section 1: Employer Outside U.S.
    ("E-1/E-2 Supp - Section 1", "e_s1_1_employer_name", "Section 1.1. Employer's Name", "text", False),
    ("E-1/E-2 Supp - Section 1", "e_s1_2_total_employees", "Section 1.2. Total Number of Employees", "text", False),
    ("E-1/E-2 Supp - Section 1", "e_s1_3_street", "Section 1.3. Employer's Address - Street", "text", False),
    ("E-1/E-2 Supp - Section 1", "e_s1_3_apt", "Section 1.3. Employer's Address - Apt./Ste./Flr.", "text", False),
    ("E-1/E-2 Supp - Section 1", "e_s1_3_city", "Section 1.3. Employer's Address - City", "text", False),
    ("E-1/E-2 Supp - Section 1", "e_s1_3_state", "Section 1.3. Employer's Address - State", "text", False),
    ("E-1/E-2 Supp - Section 1", "e_s1_3_zip", "Section 1.3. Employer's Address - ZIP Code", "text", False),
    ("E-1/E-2 Supp - Section 1", "e_s1_3_province", "Section 1.3. Employer's Address - Province", "text", False),
    ("E-1/E-2 Supp - Section 1", "e_s1_3_postal_code", "Section 1.3. Employer's Address - Postal Code", "text", False),
    ("E-1/E-2 Supp - Section 1", "e_s1_3_country", "Section 1.3. Employer's Address - Country", "text", False),
    ("E-1/E-2 Supp - Section 1", "e_s1_4_product_service", "Section 1.4. Principal Product, Merchandise or Service", "textarea", False),
    ("E-1/E-2 Supp - Section 1", "e_s1_5_employee_position", "Section 1.5. Employee's Position - Title, duties, years employed", "textarea", False),

    # Section 2: U.S. Employer Information
    ("E-1/E-2 Supp - Section 2", "e_s2_1_relation_parent", "Section 2.1. Relation - Parent", "checkbox", False),
    ("E-1/E-2 Supp - Section 2", "e_s2_1_relation_branch", "Section 2.1. Relation - Branch", "checkbox", False),
    ("E-1/E-2 Supp - Section 2", "e_s2_1_relation_subsidiary", "Section 2.1. Relation - Subsidiary", "checkbox", False),
    ("E-1/E-2 Supp - Section 2", "e_s2_1_relation_affiliate", "Section 2.1. Relation - Affiliate", "checkbox", False),
    ("E-1/E-2 Supp - Section 2", "e_s2_1_relation_joint", "Section 2.1. Relation - Joint Venture", "checkbox", False),
    ("E-1/E-2 Supp - Section 2", "e_s2_2a_place_incorporation", "Section 2.2.a. Place of Incorporation/Establishment in U.S.", "text", False),
    ("E-1/E-2 Supp - Section 2", "e_s2_2b_date_incorporation", "Section 2.2.b. Date of incorporation/establishment (mm/dd/yyyy)", "date", False),
    ("E-1/E-2 Supp - Section 2", "e_s2_3_ownership", "Section 2.3. Nationality of Ownership (table)", "textarea", False),
    ("E-1/E-2 Supp - Section 2", "e_s2_4_assets", "Section 2.4. Assets", "text", False),
    ("E-1/E-2 Supp - Section 2", "e_s2_5_net_worth", "Section 2.5. Net Worth", "text", False),
    ("E-1/E-2 Supp - Section 2", "e_s2_6_net_income", "Section 2.6. Net Annual Income", "text", False),
    ("E-1/E-2 Supp - Section 2", "e_s2_7a_exec_mgmt_treaty", "Section 2.7.a. Executive/managerial treaty nationals in E/L/H", "text", False),
    ("E-1/E-2 Supp - Section 2", "e_s2_7b_special_qual", "Section 2.7.b. Persons with special qualifications in E/L/H", "text", False),
    ("E-1/E-2 Supp - Section 2", "e_s2_7c_exec_mgmt_total", "Section 2.7.c. Total exec/managerial positions in U.S.", "text", False),
    ("E-1/E-2 Supp - Section 2", "e_s2_7d_special_qual_total", "Section 2.7.d. Total special qualification positions in U.S.", "text", False),
    ("E-1/E-2 Supp - Section 2", "e_s2_8_exec_special_qual", "Section 2.8. Explain exec/mgr or special qualifications", "textarea", False),

    # Section 3: E-1 Treaty Trader
    ("E-1/E-2 Supp - Section 3", "e_s3_1_gross_trade", "Section 3.1. Total Annual Gross Trade/Business of U.S. company", "text", False),
    ("E-1/E-2 Supp - Section 3", "e_s3_2_year_ending", "Section 3.2. For Year Ending (yyyy)", "text", False),
    ("E-1/E-2 Supp - Section 3", "e_s3_3_percent_trade", "Section 3.3. Percent of gross trade between U.S. and treaty country", "text", False),

    # Section 4: E-2 Treaty Investor
    ("E-1/E-2 Supp - Section 4", "e_s4_investment_cash", "Section 4. Total Investment - Cash", "text", False),
    ("E-1/E-2 Supp - Section 4", "e_s4_investment_equipment", "Section 4. Total Investment - Equipment", "text", False),
    ("E-1/E-2 Supp - Section 4", "e_s4_investment_other", "Section 4. Total Investment - Other", "text", False),
    ("E-1/E-2 Supp - Section 4", "e_s4_investment_inventory", "Section 4. Total Investment - Inventory", "text", False),
    ("E-1/E-2 Supp - Section 4", "e_s4_investment_premises", "Section 4. Total Investment - Premises", "text", False),
    ("E-1/E-2 Supp - Section 4", "e_s4_investment_total", "Section 4. Total Investment - Total", "text", False),

    # =========================================================================
    # H SUPPLEMENT (Pages 13-15)
    # =========================================================================
    ("H Supplement", "h_1_petitioner_name", "Name of the Petitioner", "text", False),
    ("H Supplement", "h_2a_beneficiary_name", "2.a. Name of the Beneficiary", "text", False),
    ("H Supplement", "h_2b_total_beneficiaries", "2.b. Total number of beneficiaries (if multiple)", "text", False),

    # Item 3: Prior Periods of Stay (table)
    ("H Supplement", "h_3_prior_stay_subject_1", "3. Prior Stay - Subject's Name 1", "text", False),
    ("H Supplement", "h_3_prior_stay_from_1", "3. Prior Stay - Period From 1 (mm/dd/yyyy)", "date", False),
    ("H Supplement", "h_3_prior_stay_to_1", "3. Prior Stay - Period To 1 (mm/dd/yyyy)", "date", False),
    ("H Supplement", "h_3_prior_stay_subject_2", "3. Prior Stay - Subject's Name 2", "text", False),
    ("H Supplement", "h_3_prior_stay_from_2", "3. Prior Stay - Period From 2 (mm/dd/yyyy)", "date", False),
    ("H Supplement", "h_3_prior_stay_to_2", "3. Prior Stay - Period To 2 (mm/dd/yyyy)", "date", False),

    # Item 4: Classification Sought
    ("H Supplement", "h_4_class_h1b_specialty", "4. Classification - a. H-1B Specialty Occupation", "checkbox", False),
    ("H Supplement", "h_4_class_h1b1_chile_sing", "4. Classification - b. H-1B1 Chile and Singapore", "checkbox", False),
    ("H Supplement", "h_4_class_h1b2_dod", "4. Classification - c. H-1B2 DOD cooperative R&D project", "checkbox", False),
    ("H Supplement", "h_4_class_h1b3_fashion", "4. Classification - d. H-1B3 Fashion model", "checkbox", False),
    ("H Supplement", "h_4_class_h2a_agricultural", "4. Classification - e. H-2A Agricultural worker", "checkbox", False),
    ("H Supplement", "h_4_class_h2b_nonagricultural", "4. Classification - f. H-2B Non-agricultural worker", "checkbox", False),
    ("H Supplement", "h_4_class_h3_trainee", "4. Classification - g. H-3 Trainee", "checkbox", False),
    ("H Supplement", "h_4_class_h3_special_ed", "4. Classification - h. H-3 Special education exchange visitor", "checkbox", False),

    # Item 5: H-1B Confirmation Number
    ("H Supplement", "h_5_confirmation_number", "5. H-1B Confirmation Number from Registration Notice", "text", False),

    # Item 6-8: Cap and Guam questions
    ("H Supplement", "h_6_guam_cnmi_cap", "6. Filing for beneficiary subject to Guam-CNMI cap exemption?", "radio", False),
    ("H Supplement", "h_7_change_employer_guam", "7. Change of employer - beneficiary previously Guam-CNMI exempt?", "radio", False),
    ("H Supplement", "h_8a_controlling_interest", "8.a. Beneficiary has controlling interest in petitioner?", "radio", False),
    ("H Supplement", "h_8b_controlling_explain", "8.b. If Yes, explanation", "textarea", False),

    # Section 1: H-1B Classification
    ("H Supp - Section 1", "h_s1_1_duties", "Section 1.1. Describe the proposed duties", "textarea", False),
    ("H Supp - Section 1", "h_s1_2_occupation_experience", "Section 1.2. Beneficiary's present occupation and prior work experience", "textarea", False),

    # Section 2: H-2A or H-2B Classification
    ("H Supp - Section 2", "h_s2_1_employment_seasonal", "Section 2.1. Employment is - a. Seasonal", "checkbox", False),
    ("H Supp - Section 2", "h_s2_1_employment_peakload", "Section 2.1. Employment is - b. Peak load", "checkbox", False),
    ("H Supp - Section 2", "h_s2_1_employment_intermittent", "Section 2.1. Employment is - c. Intermittent", "checkbox", False),
    ("H Supp - Section 2", "h_s2_1_employment_onetime", "Section 2.1. Employment is - d. One-time occurrence", "checkbox", False),
    ("H Supp - Section 2", "h_s2_2_need_unpredictable", "Section 2.2. Temporary need is - a. Unpredictable", "checkbox", False),
    ("H Supp - Section 2", "h_s2_2_need_periodic", "Section 2.2. Temporary need is - b. Periodic", "checkbox", False),
    ("H Supp - Section 2", "h_s2_2_need_recurrent", "Section 2.2. Temporary need is - c. Recurrent annually", "checkbox", False),
    ("H Supp - Section 2", "h_s2_3_temporary_need_explain", "Section 2.3. Explain temporary need for workers' services", "textarea", False),
    ("H Supp - Section 2", "h_s2_4_prior_admission", "Section 2.4. Named beneficiaries admitted in H-2A/H-2B previously?", "radio", False),
    ("H Supp - Section 2", "h_s2_5_restarting_3year", "Section 2.5. Requesting restarting of 3-year max period (60+ days absence)?", "radio", False),
    ("H Supp - Section 2", "h_s2_6_agent_facilitator", "Section 2.6. Using agent/facilitator to locate/recruit H-2 workers?", "radio", False),
    ("H Supp - Section 2", "h_s2_7_agent_list", "Section 2.7. If Yes, list all agents/entities (name and address)", "textarea", False),

    # =========================================================================
    # TRADE AGREEMENT SUPPLEMENT (Pages 11-12)
    # =========================================================================
    ("Trade Agreement Supplement", "ta_1_petitioner_name", "Name of the Petitioner", "text", False),
    ("Trade Agreement Supplement", "ta_2_beneficiary_name", "Name of the Beneficiary", "text", False),
    ("Trade Agreement Supplement", "ta_3_us_employer", "3. Employer - U.S. Employer", "checkbox", False),
    ("Trade Agreement Supplement", "ta_3_foreign_employer", "3. Employer - Foreign Employer", "checkbox", False),
    ("Trade Agreement Supplement", "ta_4_foreign_country", "4. If Foreign Employer, Name the Foreign Country", "text", False),

    # Section 1: Free Trade Status
    ("Trade Agr Supp - Section 1", "ta_s1_1a_canada_tn1", "Section 1.1.a. Free Trade, Canada (TN1)", "checkbox", False),
    ("Trade Agr Supp - Section 1", "ta_s1_1b_mexico_tn2", "Section 1.1.b. Free Trade, Mexico (TN2)", "checkbox", False),
    ("Trade Agr Supp - Section 1", "ta_s1_1c_chile_h1b1", "Section 1.1.c. Free Trade, Chile (H-1B1)", "checkbox", False),
    ("Trade Agr Supp - Section 1", "ta_s1_1d_singapore_h1b1", "Section 1.1.d. Free Trade, Singapore (H-1B1)", "checkbox", False),
    ("Trade Agr Supp - Section 1", "ta_s1_1e_other", "Section 1.1.e. Free Trade, Other", "checkbox", False),
    ("Trade Agr Supp - Section 1", "ta_s1_1f_sixth_consecutive", "Section 1.1.f. Sixth consecutive request for Chile/Singapore", "checkbox", False),

    # Section 2: Petitioner's Declaration
    ("Trade Agr Supp - Section 2", "ta_s2_1_petitioner_family_name", "Section 2.1. Name of Petitioner - Family Name", "text", False),
    ("Trade Agr Supp - Section 2", "ta_s2_1_petitioner_given_name", "Section 2.1. Name of Petitioner - Given Name", "text", False),
    ("Trade Agr Supp - Section 2", "ta_s2_2_signature_date", "Section 2.2. Signature Date (mm/dd/yyyy)", "date", False),
    ("Trade Agr Supp - Section 2", "ta_s2_3_daytime_phone", "Section 2.3. Daytime Telephone Number", "phone", False),
    ("Trade Agr Supp - Section 2", "ta_s2_3_mobile_phone", "Section 2.3. Mobile Telephone Number", "phone", False),
    ("Trade Agr Supp - Section 2", "ta_s2_3_email", "Section 2.3. Email Address (if any)", "email", False),

    # Section 3: Preparer's Declaration (if different from petitioner)
    ("Trade Agr Supp - Section 3", "ta_s3_1_preparer_family_name", "Section 3.1. Preparer - Family Name", "text", False),
    ("Trade Agr Supp - Section 3", "ta_s3_1_preparer_given_name", "Section 3.1. Preparer - Given Name", "text", False),
    ("Trade Agr Supp - Section 3", "ta_s3_2_business_name", "Section 3.2. Preparer's Business/Organization Name", "text", False),
    ("Trade Agr Supp - Section 3", "ta_s3_3_street", "Section 3.3. Preparer - Street Number and Name", "text", False),
    ("Trade Agr Supp - Section 3", "ta_s3_3_apt", "Section 3.3. Preparer - Apt./Ste./Flr.", "text", False),
    ("Trade Agr Supp - Section 3", "ta_s3_3_city", "Section 3.3. Preparer - City or Town", "text", False),
    ("Trade Agr Supp - Section 3", "ta_s3_3_state", "Section 3.3. Preparer - State", "select", False),
    ("Trade Agr Supp - Section 3", "ta_s3_3_zip", "Section 3.3. Preparer - ZIP Code", "text", False),
    ("Trade Agr Supp - Section 3", "ta_s3_3_province", "Section 3.3. Preparer - Province", "text", False),
    ("Trade Agr Supp - Section 3", "ta_s3_3_postal_code", "Section 3.3. Preparer - Postal Code", "text", False),
    ("Trade Agr Supp - Section 3", "ta_s3_3_country", "Section 3.3. Preparer - Country", "text", False),
    ("Trade Agr Supp - Section 3", "ta_s3_4_daytime_phone", "Section 3.4. Preparer - Daytime Telephone Number", "phone", False),
    ("Trade Agr Supp - Section 3", "ta_s3_4_fax", "Section 3.4. Preparer - Fax Number", "text", False),
    ("Trade Agr Supp - Section 3", "ta_s3_4_email", "Section 3.4. Preparer - Email Address", "email", False),
    ("Trade Agr Supp - Section 3", "ta_s3_5_signature_date", "Section 3.5. Preparer Signature Date (mm/dd/yyyy)", "date", False),
]


def update_i129(template_id=None):
    """Insert or update I-129 fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-129%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('I-129 - Petition for a Nonimmigrant Worker (EXPANDED)', "
                    "'Complete I-129 with essential fields - Edition 01/20/25 - Parts 1-7 + H/E supplements') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(I129_FIELDS):
            conn.execute(text(
                "INSERT INTO questionnaire_fields (template_id, section, field_name, label, field_type, is_required, \"order\") "
                "VALUES (:tid, :section, :field_name, :label, :field_type, :is_required, :order)"
            ), {
                "tid": template_id, "section": section, "field_name": field_name,
                "label": label, "field_type": field_type, "is_required": required, "order": i + 1
            })

        conn.commit()
        print(f"I-129 expanded: template_id={template_id}, fields={len(I129_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_i129()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(I129_FIELDS)}")

    sections = {}
    for section, _, _, _, _ in I129_FIELDS:
        sections[section] = sections.get(section, 0) + 1

    print("\nFields by section:")
    for section, count in sorted(sections.items()):
        print(f"  {section}: {count}")

    # Check for duplicates
    field_names = [field_name for _, field_name, _, _, _ in I129_FIELDS]
    duplicates = [name for name in field_names if field_names.count(name) > 1]
    if duplicates:
        print(f"\nWARNING: Duplicate field names found: {set(duplicates)}")
    else:
        print("\nNo duplicate field names detected.")
