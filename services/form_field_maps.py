"""
USCIS Form Field Maps - Semantic Mappings
Maps our intake field names (p{part}_{item}_{description}) to PDF AcroForm field names.

CRITICAL: Our expand scripts reorganized field order for better client UX.
Item numbers in our fields do NOT match the USCIS form visible item numbers.
All mappings here are done by SEMANTIC MEANING, not by item number.

All PDF field names are FLAT (e.g. "Pt2Line8_DateofBirth[0]")
NOT hierarchical (e.g. "form1[0].#subform[0].Pt2Line8_DateofBirth[0]")

Generated: 2026-03-05 via manual semantic analysis of expand scripts + PDF AcroForm extraction.
"""

# =============================================================================
# G-28: Notice of Entry of Appearance as Attorney or Accredited Representative
# Template ID: 52 | PDF fields: 110 | Our fields: 136
# =============================================================================
G28_FIELD_MAP = {
    # Part 1: Attorney/Representative Information
    "p1_2a_family_name": "Pt1Line2a_FamilyName[0]",
    "p1_2b_given_name": "Pt1Line2b_GivenName[0]",
    "p1_2c_middle_name": "Pt1Line2c_MiddleName[0]",
    "p1_3a_attorney_bar_number": "Pt2Line1b_BarNumber[0]",
    "p1_3b_uscis_account": "Pt1Line1_USCISOnlineAcctNumber[0]",
    "p1_4_firm_name": "Pt2Line1d_NameofFirmOrOrganization[0]",
    "p1_1a_state_bar": "Pt2Line1a_LicensingAuthority[0]",
    "p1_1b_organization": "Line2b_NameofOrganization[0]",
    # Attorney Mailing Address (our Item 5 = PDF Line3)
    "p1_5a_street": "Line3a_StreetNumber[0]",
    "p1_5b_apt_number": "Line3b_AptSteFlrNumber[0]",
    "p1_5c_city": "Line3c_CityOrTown[0]",
    "p1_5d_state": "Line3d_State[0]",
    "p1_5e_zip": "Line3e_ZipCode[0]",
    "p1_5f_province": "Line3f_Province[0]",
    "p1_5g_postal_code": "Line3g_PostalCode[0]",
    "p1_5h_country": "Line3h_Country[0]",
    # Attorney Contact (our Items 6-9)
    "p1_6_phone": "Line9_DaytimeTelephoneNumber[0]",
    "p1_7_mobile": "Line10_MobileTelephoneNumber[0]",
    "p1_8_email": "Line11_EMail[0]",
    "p1_9_fax": "Pt1ItemNumber7_FaxNumber[0]",

    # Part 3: Person Being Represented
    "p3_2a_family_name": "Pt3Line5a_FamilyName[0]",
    "p3_2b_given_name": "Pt3Line5b_GivenName[0]",
    "p3_2c_middle_name": "Pt3Line5c_MiddleName[0]",
    "p3_3_a_number": "Pt3Line9_ANumber[0]",
    "p3_4_uscis_account": "Pt3Line8_USCISOnlineAcctNumber[0]",
    "p3_5_receipt_number": "Pt3Line4_ReceiptNumber[0]",
    "p3_6_form_number": "Line1b_ListFormNumber[0]",
    # Person's Address (our Item 7 = PDF Line12)
    "p3_7a_street": "Line12a_StreetNumberName[0]",
    "p3_7b_apt_number": "Line12b_AptSteFlrNumber[0]",
    "p3_7c_city": "Line12c_CityOrTown[0]",
    "p3_7d_state": "Line12d_State[0]",
    "p3_7e_zip": "Line12e_ZipCode[0]",
    "p3_7f_province": "Line12f_Province[0]",
    "p3_7g_postal_code": "Line12g_PostalCode[0]",
    "p3_7h_country": "Line12h_Country[0]",
    # Person's Contact (our Items 8-10 = PDF Lines 4,7,6)
    "p3_8_phone": "Line4_DaytimeTelephoneNumber[0]",
    "p3_9_mobile": "Line7_MobileTelephoneNumber[0]",
    "p3_10_email": "Line6_EMail[0]",

    # Part 6: Additional Information (PDF uses Pt9 prefix)
    "p6_1a_family_name": "Pt3Line5a_FamilyName[1]",
    "p6_1b_given_name": "Pt3Line5b_GivenName[1]",
    "p6_1c_middle_name": "Pt3Line5c_MiddleName[1]",
    "p6_3a_page_number_1": "Pt9Line3a_PageNumber[0]",
    "p6_3b_part_number_1": "Pt9Line3b_PartNumber[0]",
    "p6_3c_item_number_1": "Pt9Line3c_ItemNumber[0]",
    "p6_3d_additional_info_1": "Pt9Line3d_AdditionalInfo[0]",
    "p6_4a_page_number_2": "Pt9Line4a_PageNumber[0]",
    "p6_4b_part_number_2": "Pt9Line4b_PartNumber[0]",
    "p6_4c_item_number_2": "Pt9Line4c_ItemNumber[0]",
    "p6_4d_additional_info_2": "Pt9Line4d_AdditionalInfo[0]",
    "p6_5a_page_number_3": "Pt9Line5a_PageNumber[0]",
    "p6_5b_part_number_3": "Pt9Line5b_PartNumber[0]",
    "p6_5c_item_number_3": "Pt9Line5c_ItemNumber[0]",
    "p6_5d_additional_info_3": "Pt9Line5d_AdditionalInfo[0]",
}


# =============================================================================
# I-130: Petition for Alien Relative
# Template ID: 38 | PDF fields: 470 | Our fields: 248
# CRITICAL: Our item numbers differ from USCIS visible items!
# Example: our p2_3_ssn (Item 3) = form's Item 11 (Pt2Line11_SSN)
# =============================================================================
I130_FIELD_MAP = {
    # Part 2: Petitioner Information
    # IDs (our Items 1-3)
    "p2_1_a_number": "Pt2Line1_AlienNumber[0]",
    "p2_2_uscis_account": "Pt2Line2_USCISOnlineActNumber[0]",
    "p2_3_ssn": "Pt2Line11_SSN[0]",  # our Item 3 = form Item 11!
    # Name (our Items 4-5)
    "p2_4a_family_name": "Pt2Line4a_FamilyName[0]",
    "p2_4b_given_name": "Pt2Line4b_GivenName[0]",
    "p2_4c_middle_name": "Pt2Line4c_MiddleName[0]",
    "p2_5a_other1_family": "Pt2Line5a_FamilyName[0]",
    "p2_5b_other1_given": "Pt2Line5b_GivenName[0]",
    "p2_5c_other1_middle": "Pt2Line5c_MiddleName[0]",
    # Mailing Address (our Item 7 = form Item 10)
    "p2_7a_mail_care_of": "Pt2Line10_InCareofName[0]",
    "p2_7b_mail_street": "Pt2Line10_StreetNumberName[0]",
    "p2_7d_mail_apt_number": "Pt2Line10_AptSteFlrNumber[0]",
    "p2_7e_mail_city": "Pt2Line10_CityOrTown[0]",
    "p2_7f_mail_state": "Pt2Line10_State[0]",
    "p2_7g_mail_zip": "Pt2Line10_ZipCode[0]",
    "p2_7h_mail_province": "Pt2Line10_Province[0]",
    "p2_7i_mail_postal": "Pt2Line10_PostalCode[0]",
    "p2_7j_mail_country": "Pt2Line10_Country[0]",
    # Physical Address (our Item 9 = form Item 12)
    "p2_9a_phys_street": "Pt2Line12_StreetNumberName[0]",
    "p2_9c_phys_apt_number": "Pt2Line12_AptSteFlrNumber[0]",
    "p2_9d_phys_city": "Pt2Line12_CityOrTown[0]",
    "p2_9e_phys_state": "Pt2Line12_State[0]",
    "p2_9f_phys_zip": "Pt2Line12_ZipCode[0]",
    "p2_9g_phys_province": "Pt2Line12_Province[0]",
    "p2_9h_phys_country": "Pt2Line12_Country[0]",
    # Personal Info (our Items 10-14, form Items 8,6,7,9)
    "p2_10_dob": "Pt2Line8_DateofBirth[0]",  # our Item 10 = form Item 8
    "p2_11_city_birth": "Pt2Line6_CityTownOfBirth[0]",  # our Item 11 = form Item 6
    "p2_13_country_birth": "Pt2Line7_CountryofBirth[0]",  # our Item 13 = form Item 7
    # Marital Info
    "p2_23_times_married": "Pt2Line16_NumberofMarriages[0]",
    # Employment
    "p2_24_employer_name": "Pt2Line40_EmployerOrCompName[0]",
    "p2_25a_emp_street": "Pt2Line41_StreetNumberName[0]",
    "p2_25b_emp_apt": "Pt2Line41_AptSteFlrNumber[0]",
    "p2_25c_emp_city": "Pt2Line41_CityOrTown[0]",
    "p2_25d_emp_state": "Pt2Line41_State[0]",
    "p2_25e_emp_zip": "Pt2Line41_ZipCode[0]",
    "p2_25f_emp_province": "Pt2Line41_Province[0]",
    "p2_25g_emp_country": "Pt2Line41_Country[0]",
    # Immigration Status
    "p2_17_certificate_number": "Pt2Line37a_CertificateNumber[0]",
    "p2_18_certificate_place": "Pt2Line37b_PlaceOfIssuance[0]",
    "p2_19_certificate_date": "Pt2Line37c_DateOfIssuance[0]",
    "p2_20_class_admission": "Pt2Line40a_ClassOfAdmission[0]",
    "p2_21_lpr_date": "Pt2Line40b_DateOfAdmission[0]",

    # Part 3: Biographic Information (Petitioner)
    "p3_3a_height_feet": "Pt3Line3_HeightFeet[0]",
    "p3_3b_height_inches": "Pt3Line3_HeightInches[0]",

    # Part 4: Beneficiary Information
    "p4_1_a_number": "Pt4Line1_AlienNumber[0]",
    "p4_2_uscis_account": "Pt4Line2_USCISOnlineActNumber[0]",
    "p4_3_ssn": "Pt4Line3_SSN[0]",
    "p4_4a_family_name": "Pt4Line4a_FamilyName[0]",
    "p4_4b_given_name": "Pt4Line4b_GivenName[0]",
    "p4_4c_middle_name": "Pt4Line4c_MiddleName[0]",
    "p4_5a_other1_family": "P4Line5a_FamilyName[0]",  # NOTE: P4 not Pt4!
    "p4_5b_other1_given": "Pt4Line5b_GivenName[0]",
    "p4_5c_other1_middle": "Pt4Line5c_MiddleName[0]",
    "p4_6a_other2_family": "Pt4Line6a_FamilyName[0]",
    "p4_6b_other2_given": "Pt4Line6b_GivenName[0]",
    # Address (our Item 7 = form Item 11)
    "p4_7a_street": "Pt4Line11_StreetNumberName[0]",
    "p4_7c_apt_number": "Pt4Line11_AptSteFlrNumber[0]",
    "p4_7d_city": "Pt4Line11_CityOrTown[0]",
    "p4_7e_state": "Pt4Line11_State[0]",
    "p4_7f_postal": "Pt4Line11_PostalCode[0]",
    "p4_7g_country": "Pt4Line11_Country[0]",
    # Personal Info (our Items 8-13, form Items 9,7,8)
    "p4_8_dob": "Pt4Line9_DateOfBirth[0]",  # our Item 8 = form Item 9
    "p4_9_city_birth": "Pt4Line7_CityTownOfBirth[0]",  # our Item 9 = form Item 7
    "p4_11_country_birth": "Pt4Line8_CountryOfBirth[0]",  # our Item 11 = form Item 8
    # Marital
    "p4_15_times_married": "Pt4Line17_NumberofMarriages[0]",
    # Travel Documents
    "p4_23_passport_number": "Pt4Line22_PassportNumber[0]",
    "p4_24_travel_doc_number": "Pt4Line23_TravelDocNumber[0]",
    "p4_25_passport_country": "Pt4Line24_CountryOfIssuance[0]",
    "p4_26_passport_exp": "Pt4Line25_ExpDate[0]",
    # Father
    "p4_27a_father_family": "Pt4Line30a_FamilyName[0]",
    "p4_27b_father_given": "Pt4Line30b_GivenName[0]",
    "p4_27c_father_middle": "Pt4Line30c_MiddleName[0]",
    "p4_28_father_dob": "Pt4Line32_DateOfBirth[0]",
    # Mother
    "p4_33a_mother_family": "Pt4Line38a_FamilyName[0]",
    "p4_33b_mother_given": "Pt4Line38b_GivenName[0]",
    "p4_33c_mother_middle": "Pt4Line38c_MiddleName[0]",

    # Part 5: Prior Petitions
    "p5_2_prior_family": "Pt5Line2a_FamilyName[0]",
    "p5_3_prior_given": "Pt5Line2b_GivenName[0]",
    "p5_5_prior_date": "Pt5Line4_DateFiled[0]",
    "p5_6_prior_result": "Pt5Line5_Result[0]",

    # Part 6: Petitioner's Statement & Contact
    "p6_3_daytime_phone": "Pt6Line3_DaytimePhoneNumber[0]",
    "p6_4_mobile_phone": "Pt6Line4_MobileNumber[0]",
    "p6_5_email": "Pt6Line5_Email[0]",

    # Part 7: Interpreter
    "p7_1a_interp_family": "Pt7Line1a_InterpreterFamilyName[0]",
    "p7_1b_interp_given": "Pt7Line1b_InterpreterGivenName[0]",
    "p7_2_interp_org": "Pt7Line2_InterpreterBusinessorOrg[0]",
    "p7_3a_interp_street": "Pt7Line3_StreetNumberName[0]",
    "p7_3b_interp_apt": "Pt7Line3_AptSteFlrNumber[0]",
    "p7_3c_interp_city": "Pt7Line3_CityOrTown[0]",
    "p7_3d_interp_state": "Pt7Line3_State[0]",
    "p7_3e_interp_zip": "Pt7Line3_ZipCode[0]",
    "p7_3f_interp_country": "Pt7Line3_Country[0]",
    "p7_4_interp_phone": "Pt7Line4_InterpreterDaytimeTelephone[0]",
    "p7_6_interp_email": "Pt7Line5_Email[0]",
    "p7_7_language": "Pt7_NameofLanguage[0]",

    # Part 8: Preparer
    "p8_2a_prep_family": "Pt8Line1a_PreparerFamilyName[0]",
    "p8_2b_prep_given": "Pt8Line1b_PreparerGivenName[0]",
    "p8_3_prep_org": "Pt8Line2_BusinessName[0]",
    "p8_4a_prep_street": "Pt8Line3_StreetNumberName[0]",
    "p8_4b_prep_apt": "Pt8Line3_AptSteFlrNumber[0]",
    "p8_4c_prep_city": "Pt8Line3_CityOrTown[0]",
    "p8_4d_prep_state": "Pt8Line3_State[0]",
    "p8_4e_prep_zip": "Pt8Line3_ZipCode[0]",
    "p8_4f_prep_country": "Pt8Line3_Country[0]",
    "p8_5_prep_phone": "Pt8Line4_DaytimePhoneNumber[0]",
    "p8_7_prep_email": "Pt8Line6_Email[0]",

    # Part 9: Additional Information
    "p9_1a_page": "Pt9Line3a_PageNumber[0]",
    "p9_1b_part": "Pt9Line3b_PartNumber[0]",
    "p9_1c_item": "Pt9Line3c_ItemNumber[0]",
    "p9_1d_info": "Pt9Line3d_AdditionalInfo[0]",
    "p9_2a_page": "Pt9Line4a_PageNumber[0]",
    "p9_2b_part": "Pt9Line4b_PartNumber[0]",
    "p9_2c_item": "Pt9Line4c_ItemNumber[0]",
    "p9_2d_info": "Pt9Line4d_AdditionalInfo[0]",
}


# =============================================================================
# I-765: Application for Employment Authorization
# Template ID: 42 | PDF fields: 169 | Our fields: 177
# =============================================================================
I765_FIELD_MAP = {
    # Part 2: Information About You
    "p2_1a_family_name": "Line1a_FamilyName[0]",
    "p2_1b_given_name": "Line1b_GivenName[0]",
    "p2_1c_middle_name": "Line1c_MiddleName[0]",
    # Other Names
    "p2_3a_other1_family": "Line2a_FamilyName[0]",
    "p2_3b_other1_given": "Line2b_GivenName[0]",
    "p2_3c_other1_middle": "Line2c_MiddleName[0]",
    "p2_4a_other2_family": "Line3a_FamilyName[0]",
    "p2_4b_other2_given": "Line3b_GivenName[0]",
    "p2_4c_other2_middle": "Line3c_MiddleName[0]",
    # Mailing Address
    "p2_5a_care_of": "Line4a_InCareofName[0]",
    "p2_5b_street": "Line4b_StreetNumberName[0]",
    "p2_5d_apt_number": "Pt2Line5_AptSteFlrNumber[0]",
    "p2_5e_city": "Pt2Line5_CityOrTown[0]",
    "p2_5f_state": "Pt2Line5_State[0]",
    "p2_5g_zip": "Pt2Line5_ZipCode[0]",
    # Physical Address
    "p2_7a_phys_street": "Pt2Line7_StreetNumberName[0]",
    "p2_7c_phys_apt_number": "Pt2Line7_AptSteFlrNumber[0]",
    "p2_7d_phys_city": "Pt2Line7_CityOrTown[0]",
    "p2_7e_phys_state": "Pt2Line7_State[0]",
    "p2_7f_phys_zip": "Pt2Line7_ZipCode[0]",
    # IDs
    "p2_8_a_number": "Line7_AlienNumber[0]",
    "p2_9_uscis_account": "Line8_ElisAccountNumber[0]",
    "p2_10_i94_number": "Line20a_I94Number[0]",
    "p2_11_passport_number": "Line20b_Passport[0]",
    "p2_12_travel_doc_number": "Line20c_TravelDoc[0]",
    "p2_13_passport_country": "Line20d_CountryOfIssuance[0]",
    "p2_14_passport_exp": "Line20e_ExpDate[0]",
    "p2_15_sevis_number": "Line26_SEVISnumber[0]",
    # Biographic
    "p2_16_dob": "Line19_DOB[0]",
    "p2_18_city_birth": "Line18a_CityTownOfBirth[0]",
    "p2_19_state_birth": "Line18b_CityTownOfBirth[0]",
    "p2_20_country_birth": "Line18c_CountryOfBirth[0]",
    "p2_21_citizenship": "Line17a_CountryOfBirth[0]",
    # SSN
    "p2_23_ssn": "Line12b_SSN[0]",
    # Immigration
    "p2_28_date_last_entry": "Line21_DateOfLastEntry[0]",
    "p2_29_place_last_entry": "place_entry[0]",
    "p2_30_status_at_entry": "Line23_StatusLastEntry[0]",
    "p2_31_current_status": "Line24_CurrentStatus[0]",
    "p2_33_eligibility_category": "section_1[0]",

    # Part 3: Contact
    "p3_4_daytime_phone": "Pt3Line3_DaytimePhoneNumber1[0]",
    "p3_5_mobile_phone": "Pt3Line4_MobileNumber1[0]",
    "p3_6_email": "Pt3Line5_Email[0]",

    # Part 4: Interpreter
    "p4_1a_interp_family": "Pt4Line1a_InterpreterFamilyName[0]",
    "p4_1b_interp_given": "Pt4Line1b_InterpreterGivenName[0]",
    "p4_2_interp_org": "Pt4Line2_InterpreterBusinessorOrg[0]",
    "p4_4_interp_phone": "Pt4Line4_InterpreterDaytimeTelephone[0]",
    "p4_5_interp_mobile": "Pt4Line5_MobileNumber[0]",
    "p4_6_interp_email": "Pt4Line6_Email[0]",
    "p4_7_language": "Part4_NameofLanguage[0]",

    # Part 5: Preparer
    "p5_2a_prep_family": "Pt5Line1a_PreparerFamilyName[0]",
    "p5_2b_prep_given": "Pt5Line1b_PreparerGivenName[0]",
    "p5_3_prep_org": "Pt5Line2_BusinessName[0]",
    "p5_4a_prep_street": "Pt5Line3a_StreetNumberName[0]",
    "p5_4b_prep_apt": "Pt5Line3b_AptSteFlrNumber[0]",
    "p5_4c_prep_city": "Pt5Line3c_CityOrTown[0]",
    "p5_4d_prep_state": "Pt5Line3d_State[0]",
    "p5_4e_prep_zip": "Pt5Line3e_ZipCode[0]",
    "p5_4f_prep_province": "Pt5Line3f_Province[0]",
    "p5_4g_prep_postal": "Pt5Line3g_PostalCode[0]",
    "p5_4h_prep_country": "Pt5Line3h_Country[0]",
    "p5_5_prep_phone": "Pt5Line4_DaytimePhoneNumber1[0]",
    "p5_7_prep_email": "Pt5Line6_Email[0]",

    # Part 6: Additional Info
    "p6_1a_page": "Pt6Line3a_PageNumber[0]",
    "p6_1b_part": "Pt6Line3b_PartNumber[0]",
    "p6_1c_item": "Pt6Line3c_ItemNumber[0]",
}


# =============================================================================
# I-140: Immigrant Petition for Alien Workers
# Template ID: 19 | PDF fields: 279 | Our fields: 351
# Used for: EB-1A, EB-1B, EB-1C, EB-2, EB-2 NIW, EB-3
# =============================================================================
I140_FIELD_MAP = {
    # Part 1: Petitioner Information
    "p1_1a_family_name": "Pt1Line1a_FamilyName[0]",
    "p1_1b_given_name": "Pt1Line1b_GivenName[0]",
    "p1_1c_middle_name": "Pt1Line1c_MiddleName[0]",
    "p1_2_company_name": "Line2_CompanyName[0]",
    "p1_3_ein": "Pt1Line3_TaxNumber[0]",
    "p1_4_ssn": "Line7_SSN[0]",
    "p1_7_uscis_account": "Pt1Line8_USCISOnlineActNumber[0]",
    # Petitioner Mailing Address (our Item 8 = PDF Line6)
    "p1_8a_street": "Line6b_StreetNumberName[0]",
    "p1_8b_apt_number": "Line6c_AptSteFlrNumber[0]",
    "p1_8c_city": "Line6d_CityOrTown[0]",
    "p1_8d_state": "Line6e_State[0]",
    "p1_8e_zip": "Line6f_ZipCode[0]",
    "p1_8f_province": "Line6h_Province[0]",
    "p1_8g_postal_code": "Line6g_PostalCode[0]",
    "p1_8h_country": "Line6i_Country[0]",

    # Part 3: Beneficiary Information
    "p3_1a_family_name": "Pt3Line1a_FamilyName[0]",
    "p3_1b_given_name": "Pt3Line1b_GivenName[0]",
    "p3_1c_middle_name": "Pt3Line1c_MiddleName[0]",
    # Beneficiary Address
    "p3_2a_street": "Line2a_StreetNumberName[0]",
    "p3_2c_city": "Line2c_CityOrTown[0]",
    "p3_2d_state": "Line2e_State[0]",
    "p3_2e_zip": "Line2f_ZipCode[0]",
    "p3_2f_province": "Line2e_Province[0]",
    "p3_2g_postal_code": "Line2d_PostalCode[0]",
    "p3_2h_country": "Line2f_Country[0]",
    # Beneficiary Details
    "p3_3_date_last_arrival": "Line13_DateOArrival[0]",
    "p3_4_i94_number": "Line14a_ArrivalDeparture[0]",
    "p3_5a_current_status": "Line15_CurrentNon[0]",
    "p3_8_a_number": "Pt3Line8_AlienNumber[0]",
    "p3_9_ssn": "Line12_SSN[0]",
    "p3_10_dob": "Line5_DateOfBirth[0]",
    # Passport
    "p3_13_passport_number": "Line14b_Passport[0]",
    "p3_14_travel_doc_number": "Line14c_TravelDoc[0]",
    "p3_15_country_issuance": "Line14d_CountryOfIssuance[0]",
    "p3_16_expiration_date": "Line14e_ExpDate[0]",

    # Part 5: Additional Petitioner Info
    "p5_3_num_employees": "Line2c_NumberofEmployees[0]",
    "p5_5_gross_annual_income": "Line2d_GrossAnnualIncome[0]",
    "p5_6_net_annual_income": "Line2e_NetAnnualIncome[0]",
    "p5_7_naics_code": "Line2f_NAICSCode[0]",
    "p5_8_dol_case_number": "Line2g_LaborCertification[0]",
    "p5_10_dol_expiration": "Line2i_LaborCertificationDate[0]",
    "p5_11_occupation": "Line3a_Occupation[0]",
    "p5_12_annual_income": "Line3b_AnnualIncome[0]",

    # Part 6: Proposed Employment
    "p6_1_job_title": "Line1_JobTitle[0]",
    "p6_2_soc_code": "Line2_SOCCode1[0]",
    "p6_3_job_description": "Line3_JobDescription[0]",
    "p6_8_wages": "Line8_Wages[0]",
    "p6_8_wage_period": "Line8_Per[0]",
    "p6_9a_street": "Line9a_StreetNumberName[0]",
    "p6_9b_apt_number": "Line9b_AptSteFlrNumber[0]",
    "p6_9c_city": "Line9c_CityOrTown[0]",
    "p6_9d_state": "Line9d_State[0]",
    "p6_9e_zip": "Line9e_ZipCode[0]",

    # Part 8: Petitioner Contact (PDF uses Part7_Item prefix)
    "p8_3a_family_name": "Part7_Item3a_FamilyName[0]",
    "p8_3b_given_name": "Part7_Item3b_GivenName[0]",
    "p8_4_title": "Part7_Item4_Title[0]",
    "p8_5_phone": "Part7_Item5_DayPhone[0]",
    "p8_6_mobile": "Part7_Item6_MobilePhone[0]",
    "p8_7_email": "Part7_Item7_Email[0]",

    # Part 9: Interpreter (PDF uses Part8_Item prefix)
    "interpreter_1a_family_name": "Part8_Item1a_FamilyName[0]",
    "interpreter_1b_given_name": "Part8_Item1b_GivenName[0]",
    "interpreter_2_business": "Part8_Item2_OrgName[0]",
    "interpreter_4_phone": "Part8_Item4_DayPhone[0]",
    "interpreter_5_mobile": "Part8_Item5_MobilePhone[0]",
    "interpreter_6a_email": "Part8_Item6_Email[0]",
    "interpreter_6b_language": "Part8_Item6_Language[0]",

    # Part 10: Preparer (PDF uses Part10_Item prefix)
    "preparer_1a_family_name": "Part10_Item1_FamilyName[0]",
    "preparer_1b_given_name": "Part10_Item1_GivenName[0]",
    "preparer_2_business": "Part10_Item2_OrgName[0]",
    "preparer_4_phone": "Part10_Item3_DayPhone[0]",
    "preparer_6_email": "Part10_Item5_Email[0]",

    # Part 11: Additional Info (PDF uses Pt9 prefix)
    "p11_3a_page_1": "Pt9Line3a_PageNumber[0]",
    "p11_3b_part_1": "Pt9Line3b_PartNumber[0]",
    "p11_3c_item_1": "Pt9Line3c_ItemNumber[0]",
    "p11_3d_info_1": "Pt9Line3d_AdditionalInfo[0]",
    "p11_4a_page_2": "Pt9Line4a_PageNumber[0]",
    "p11_4b_part_2": "Pt9Line4b_PartNumber[0]",
    "p11_4c_item_2": "Pt9Line4c_ItemNumber[0]",
    "p11_4d_info_2": "Pt9Line4d_AdditionalInfo[0]",
}


# =============================================================================
# Stub maps for forms to be completed later
# =============================================================================
# =============================================================================
# I-907: Request for Premium Processing Service
# Template ID: 13 | Edition 04/01/24 | 7 pages, Parts 1-6
# =============================================================================
I907_FIELD_MAP = {
    # Header - Attorney/Representative Info
    "header_g28_checkbox": "FormG28Attach[0]",
    "header_attorney_bar_number": "AttyStateBarNumber[0]",
    "header_attorney_uscis_account": "USCISOnlineAcctNumber[0]",

    # Part 1: Person Filing - IDs & Name
    "p1_1_a_number": "Pt1Line1_AlienRegistrationNumber[0]",
    "p1_2_uscis_account": "Pt1Line2_USCISOnlineActNumber[0]",
    "p1_3_family_name": "Pt1Line3_FamilyName[0]",
    "p1_3_given_name": "Pt1Line3_GivenName[0]",
    "p1_3_middle_name": "Pt1Line3_MiddleName[0]",
    "p1_4_company_org": "Part1_Line4_CompanyorOrganizationName[0]",

    # Part 1: Mailing Address (Item 5)
    "p1_5_in_care_of": "Part1_Line5_MailingAddress_InCareofName[0]",
    "p1_5_street": "Part1_Line5_MailingAddress_StreetNumberName[0]",
    "p1_5_apt_number": "Part1_Line5_MailingAddress_AptSteFlrNumber[0]",
    "p1_5_city": "Part1_Line5_MailingAddress_CityTown[0]",
    "p1_5_state": "Part1_Line5_MailingAddress_State[0]",
    "p1_5_zip": "Part1_Line5_MailingAddress_ZipCode[0]",
    "p1_5_province": "Part1_Line5_MailingAddress_Province[0]",
    "p1_5_postal_code": "Part1_Line5_MailingAddress_PostalCode[0]",
    "p1_5_country": "Part1_Line5_MailingAddress_Country[0]",

    # Part 1: Physical Address (Item 7)
    "p1_7_street": "Part1_Line7_PhysicalAddress_StreetNumberName[0]",
    "p1_7_apt_number": "Part1_Line7_PhysicalAddress_AptSteFlrNumber[0]",
    "p1_7_city": "Part1_Line7_PhysicalAddress_CityTown[0]",
    "p1_7_state": "Part1_Line7_PhysicalAddress_State[0]",
    "p1_7_zip": "Part1_Line7_PhysicalAddress_ZipCode[0]",
    "p1_7_province": "Part1_Line7_PhysicalAddress_Province[0]",
    "p1_7_postal_code": "Part1_Line7_PhysicalAddress_PostalCode[0]",
    "p1_7_country": "Part1_Line7_PhysicalAddress_Country[0]",

    # Part 1: Request Type (Item 8) - checkboxes
    "p1_8_petitioner": "Part1_Line8_CheckBox[0]",
    "p1_8_attorney_petitioner": "Part1_Line8_CheckBox[1]",
    "p1_8_applicant": "Part1_Line8_CheckBox[2]",
    "p1_8_attorney_applicant": "Part1_Line8_CheckBox[3]",

    # Part 2: Request Info
    "p2_1_form_number": "P2_Line1_FormNumberof[0]",
    "p2_2_receipt_number": "P2_Line2_ReceiptNumberof[0]",
    "p2_3_classification": "P2_Line2_ClassorEligRequested[0]",

    # Part 2: Petitioner/Applicant in Related Case (Item 4)
    "p2_4_family_name": "Part2_Line4_PetitionerApplicantFamilyName[0]",
    "p2_4_given_name": "Part2_Line4_PetitionerApplicantGivenName[0]",
    "p2_4_middle_name": "Part2_Line4_PetitionerApplicantMiddleName[0]",

    # Part 2: Beneficiary in Related Case (Item 5)
    "p2_5_family_name": "Line_FamilyName[0]",
    "p2_5_given_name": "Line_GivenName[0]",
    "p2_5_middle_name": "Line_MiddleName[0]",

    # Part 2: Point of Contact for Company (Item 6)
    "p2_6_family_name": "Part1_Line8_NameOfCompanyPOC_FamilyName[0]",
    "p2_6_given_name": "Part1_Line8_NameOfCompanyPOC_GivenName[0]",
    "p2_6_middle_name": "Part1_Line8_NameOfCompanyPOC_MiddleName[0]",
    "p2_6_position_title": "Part1_Line8_NameOfCompanyPOC_TitleofPOC[0]",

    # Part 2: Company EIN (Item 7)
    "p2_7_ein": "Part1_Line9_CompanyIRSTaxNumber[0]",

    # Part 2: Address of Company/Petitioner/Applicant (Item 8)
    "p2_8_street": "Part1_Line7_OtherInformationAboutCompanyOrg_StreetNumberName[0]",
    "p2_8_apt_number": "Part1_Line7_OtherInformationAboutCompanyOrg_AptSteFlrNumber[0]",
    "p2_8_city": "Part1_Line7_OtherInformationAboutCompanyOrg_CityTown[0]",
    "p2_8_state": "Part1_Line7_OtherInformationAboutCompanyOrg_State[0]",
    "p2_8_zip": "Part1_Line7_OtherInformationAboutCompanyOrg_ZipCode[0]",
    "p2_8_province": "Part1_Line7_OtherInformationAboutCompanyOrg_Province[0]",
    "p2_8_postal_code": "Part1_Line7_OtherInformationAboutCompanyOrg_PostalCode[0]",
    "p2_8_country": "Part1_Line7_OtherInformationAboutCompanyOrg_Country[0]",

    # Part 3: Requestor's Statement
    "p3_1b_language": "P3_Line1_B_Language[0]",

    # Part 3: Requestor's Contact Info
    "p3_3_phone_day": "P3_Line4_DaytimeTelePhoneNumber[0]",
    "p3_4_phone_mobile": "P3_Line5_MobileTelePhoneNumber[0]",
    "p3_5_fax": "P3_Line5_MobileTelePhoneNumber[1]",  # fax uses [1] index
    "p3_6_email": "P3_Line6_Email[0]",

    # Part 4: Interpreter Name & Org
    "p4_1_family_name": "P4_Line1_InterpreterFamilyName[0]",
    "p4_1_given_name": "P4_Line1_InterpreterGivenName[0]",
    "p4_2_business_org": "P4_Line2_NameofBusinessorOrgName[0]",

    # Part 4: Interpreter Address (Item 3)
    "p4_3_street": "P4_Line3_StreetNumberName[0]",
    "p4_3_apt_number": "P4_Line3_AptSteFlrNumber[0]",
    "p4_3_city": "P4_Line3_CityTown[0]",
    "p4_3_state": "P4_Line3_State[0]",
    "p4_3_zip": "P4_Line3_ZipCode[0]",
    "p4_3_province": "P4_Line3_Province[0]",
    "p4_3_postal_code": "P4_Line3_PostalCode[0]",
    "p4_3_country": "P4_Line3_Country[0]",

    # Part 4: Interpreter Contact
    "p4_4_phone_day": "P4_Line4_DaytimeTelePhoneNumber[0]",
    "p4_5_phone_mobile": "P4_Line4_DaytimeTelePhoneNumber[1]",  # mobile uses [1] index
    "p4_6_email": "P4_Line5_Email[0]",
    "p4_cert_language": "P4_Line6_Language[0]",

    # Part 5: Preparer Name & Org
    "p5_1_family_name": "P5_Line1_PreparerFamilyName[0]",
    "p5_1_given_name": "P5_Line1_PreparerGivenName[0]",
    "p5_2_business_org": "P5_Line2_NameofBusinessorOrgName[0]",

    # Part 5: Preparer Address (Item 3)
    "p5_3_street": "P5_Line3_StreetNumberName[0]",
    "p5_3_apt_number": "P5_Line3_AptSteFlrNumber[0]",
    "p5_3_city": "P5_Line3_CityTown[0]",
    "p5_3_state": "P5_Line3_State[0]",
    "p5_3_zip": "P5_Line3_ZipCode[0]",
    "p5_3_province": "P5_Line3_Province[0]",
    "p5_3_postal_code": "P5_Line3_PostalCode[0]",
    "p5_3_country": "P5_Line3_Country[0]",

    # Part 5: Preparer Contact
    "p5_4_phone_day": "P5_Line4_DaytimeTelePhoneNumber[0]",
    "p5_5_phone_mobile": "P5_Line5_FaxNumber[0]",  # PDF field labeled fax but maps to mobile
    "p5_6_email": "P5_Line6_EmailAddress[0]",

    # Part 5: Preparer Statement - checkboxes
    "p5_7a_not_attorney": "P5_Line7a_Checkbox[0]",
    "p5_7b_attorney_extends": "P5_Line7b_extends[0]",
    "p5_7b_attorney_not_extend": "P5_Line7b_notextends[0]",

    # Part 6: Additional Info - Person's Name & A-Number
    "p6_1_family_name": "Pt1Line3_FamilyName[1]",  # page 7 repeat fields
    "p6_1_given_name": "Pt1Line3_GivenName[1]",
    "p6_1_middle_name": "Pt1Line3_MiddleName[1]",
    "p6_2_a_number": "Pt1Line1_AlienRegistrationNumber[1]",

    # Part 6: Additional Info - Row 1
    "p6_3a_page_number": "Pt9Line3a_PageNumber[0]",
    "p6_3b_part_number": "Pt9Line3b_PartNumber[0]",
    "p6_3c_item_number": "Pt9Line3c_ItemNumber[0]",
    "p6_3d_additional_info": "Pt9Line3d_AdditionalInfo[0]",

    # Part 6: Additional Info - Row 2
    "p6_4a_page_number": "Pt9Line4a_PageNumber[0]",
    "p6_4b_part_number": "Pt9Line4b_PartNumber[0]",
    "p6_4c_item_number": "Pt9Line4c_ItemNumber[0]",
    "p6_4d_additional_info": "Pt9Line4d_AdditionalInfo[0]",
}
# =============================================================================
# I-485: Application to Register Permanent Residence or Adjust Status
# Template ID: 40 | PDF fields: 736 | Our fields: 513
# CRITICAL: Our item numbers differ HEAVILY from USCIS visible items.
# Part 9 has 80+ eligibility questions (Yes/No radios) - not mapped here
# because they require special checkbox/radio handling, not text fill.
# =============================================================================
I485_FIELD_MAP = {
    # Part 1: Applicant Information - Name
    "p1_1a_family_name": "Pt1Line1_FamilyName[0]",
    "p1_1b_given_name": "Pt1Line1_GivenName[0]",
    "p1_1c_middle_name": "Pt1Line1_MiddleName[0]",

    # Part 1: Other Names Used
    "p1_2a_other1_family": "Pt1Line2_FamilyName[0]",
    "p1_2b_other1_given": "Pt1Line2_GivenName[0]",
    "p1_2c_other1_middle": "Pt1Line2_MiddleName[0]",
    "p1_3a_other2_family": "Pt1Line2a_FamilyName[0]",
    "p1_3b_other2_given": "Pt1Line2a_GivenName[0]",
    "p1_3c_other2_middle": "Pt1Line2a_MiddleName[0]",

    # Part 1: Personal Information
    "p1_5_dob": "Pt1Line3_DOB[0]",
    "p1_7_city_birth": "Pt1Line7_CityTownOfBirth[0]",
    "p1_8_country_birth": "Pt1Line7_CountryOfBirth[0]",
    "p1_9_citizenship": "Pt1Line8_CountryofCitizenshipNationality[0]",

    # Part 1: IDs
    "p1_11_a_number": "Pt1Line4_AlienNumber[0]",
    "p1_12_uscis_account": "Pt1Line9_USCISAccountNumber[0]",
    "p1_13_ssn": "Pt1Line19_SSN[0]",

    # Part 1: U.S. Mailing Address (our Item 14 = form Item 18)
    "p1_14a_care_of": "Part1_Item18_InCareOfName[0]",
    "p1_14b_street": "Pt1Line18_StreetNumberName[0]",
    "p1_14d_apt_number": "Pt1Line18US_AptSteFlrNumber[0]",
    "p1_14e_city": "Pt1Line18_CityOrTown[0]",
    "p1_14f_state": "Pt1Line18_State[0]",
    "p1_14g_zip": "Pt1Line18_ZipCode[0]",

    # Part 1: Travel Documents
    "p1_17_passport_number": "Pt1Line10_PassportNum[0]",
    "p1_19_passport_exp": "Pt1Line10_ExpDate[0]",
    "p1_20_passport_country": "Pt1Line10_Passport[0]",
    "p1_21_nonimmigrant_visa": "Pt1Line10_VisaNum[0]",

    # Part 1: Last Arrival Information
    "p1_22a_arrival_city": "Pt1Line10_CityTown[0]",
    "p1_22b_arrival_state": "Pt1Line10_State[0]",
    "p1_23_arrival_date": "Pt1Line10_DateofArrival[0]",

    # Part 1: Current Immigration Status
    "p1_25_i94_number": "P1Line12_I94[0]",
    "p1_26_status_expires": "Pt1Line15_Date[0]",
    "p1_27_status_on_i94": "Pt1Line12_Status[0]",
    "p1_28_current_status": "Pt1Line14_Status[0]",
    "p1_29a_name_i94_family": "P1Line12_FamilyName[0]",
    "p1_29b_name_i94_given": "P1Line13_GivenName[0]",

    # Part 2: Filing Category - Approved Petition
    "p2_4_petition_receipt": "Pt2Line2_Receipt[0]",
    "p2_5_priority_date": "Pt2Line2_Date[0]",
    "p2_7a_principal_family": "Pt2Line2_FamilyName[0]",
    "p2_7b_principal_given": "Pt2Line2_GivenName[0]",
    "p2_7c_principal_middle": "Pt2Line2_MiddleName[0]",
    "p2_8_principal_a_number": "Pt2Line2_AlienNumber[0]",
    "p2_9_principal_dob": "Pt1Line2_DOB[0]",

    # Part 4: Current Physical Address (PDF uses Pt1Line18_Current* prefix)
    "p4_1a_street": "Pt1Line18_CurrentStreetNumberName[0]",
    "p4_1c_apt_number": "Pt1Line18_CurrentAptSteFlrNumber[0]",
    "p4_1d_city": "Pt1Line18_CurrentCityOrTown[0]",
    "p4_1e_state": "Pt1Line18_CurrentState[0]",
    "p4_1f_zip": "Pt1Line18_CurrentZipCode[0]",

    # Part 4: Previous Address 1 (PDF uses Pt1Line18_Prior* prefix)
    "p4_4a_prev1_street": "Pt1Line18_PriorStreetName[0]",
    "p4_4b_prev1_apt": "Pt1Line18_PriorAddress_Number[0]",
    "p4_4c_prev1_city": "Pt1Line18_PriorCity[0]",
    "p4_4d_prev1_state": "Pt1Line18_PriorState[0]",
    "p4_4e_prev1_zip": "Pt1Line18_PriorZipCode[0]",
    "p4_4f_prev1_province": "Pt1Line18_PriorProvince[0]",
    "p4_4g_prev1_country": "Pt1Line18_PriorCountry[0]",
    "p4_5_prev1_from": "Pt1Line18_PriorDateFrom[0]",
    "p4_6_prev1_to": "Pt1Line18PriorDateTo[0]",

    # Part 4: Previous Address 2 (PDF uses Pt1Line18_Recent* prefix)
    "p4_7a_prev2_street": "Pt1Line18_RecentStreetName[0]",
    "p4_7b_prev2_apt": "Pt1Line18_RecentNumber[0]",
    "p4_7c_prev2_city": "Pt1Line18_RecentCity[0]",
    "p4_7d_prev2_state": "Pt1Line18_RecentState[0]",
    "p4_8_prev2_from": "Pt1Line18_RecentDateFrom[0]",
    "p4_9_prev2_to": "Pt1Line18_RecentDateTo[0]",

    # Part 4: Current Employment (PDF uses Pt4Line7/P4Line7 prefix)
    "p4_13_employer_name": "Pt4Line7_EmployerName[0]",
    "p4_14a_emp_street": "Part4Line7_StreetName[0]",
    "p4_14b_emp_apt": "P4Line7_Number[0]",
    "p4_14c_emp_city": "P4Line7_City[0]",
    "p4_14d_emp_state": "P4Line7_State[0]",
    "p4_14e_emp_zip": "P4Line7_ZipCode[0]",
    "p4_14f_emp_province": "P4Line7_Province[0]",
    "p4_14g_emp_country": "P4Line7_Country[0]",
    "p4_15_occupation": "Pt4Line8_Occupation[0]",
    "p4_16_emp_from": "Pt4Line7_DateFrom[0]",
    "p4_17_emp_to": "Pt4Line7_DateTo[0]",

    # Part 4: Previous Employment 1 (PDF uses Pt4Line8/P4Line8 prefix)
    "p4_18_prev_emp1_name": "Pt4Line8_EmployerName[0]",
    "p4_19a_prev_emp1_street": "P4Line8_StreetName[0]",
    "p4_19b_prev_emp1_city": "P4Line8_City[0]",
    "p4_19c_prev_emp1_state": "P4Line8_State[0]",
    "p4_21_prev_emp1_from": "Pt4Line8_DateFrom[0]",
    "p4_22_prev_emp1_to": "Pt4Line8_DateTo[0]",

    # Part 5: Parents - Parent 1
    "p5_1a_parent1_family": "Pt5Line1_FamilyName[0]",
    "p5_1b_parent1_given": "Pt5Line1_GivenName[0]",
    "p5_1c_parent1_middle": "Pt5Line1_MiddleName[0]",
    "p5_2_parent1_dob": "Pt5Line3_DateofBirth[0]",
    "p5_4_parent1_city_birth": "Pt5Line5_CityTownOfBirth[0]",

    # Part 5: Parents - Parent 2
    "p5_8a_parent2_family": "Pt5Line6_FamilyName[0]",
    "p5_8b_parent2_given": "Pt5Line6_GivenName[0]",
    "p5_8c_parent2_middle": "Pt5Line6_MiddleName[0]",
    "p5_9_parent2_dob": "Pt5Line8_DateofBirth[0]",
    "p5_11_parent2_city_birth": "Pt5Line10_CityTownOfBirth[0]",

    # Part 6: Marital History
    "p6_2_times_married": "Pt6Line3_TimesMarried[0]",
    "p6_3a_spouse_family": "Pt6Line4_FamilyName[0]",
    "p6_3b_spouse_given": "Pt6Line4_GivenName[0]",
    "p6_3c_spouse_middle": "Pt6Line4_MiddleName[0]",
    "p6_4_spouse_a_number": "Pt6Line5_AlienNumber[0]",
    "p6_5_spouse_dob": "Pt5Line8_DateofBirth[1]",  # reuses Pt5 prefix with [1]
    "p6_6_spouse_country_birth": "Pt6Line7_Country[0]",

    # Part 6: Prior Spouse
    "p6_12a_prior1_family": "Pt6Line12_FamilyName[0]",
    "p6_12b_prior1_given": "Pt6Line12_GivenName[0]",

    # Part 7: Children
    "p7_1_total_children": "Pt6Line1_TotalChildren[0]",
    "p7_2a_child1_family": "Pt7Line2_FamilyName[0]",
    "p7_2b_child1_given": "Pt7Line2_GivenName[0]",
    "p7_2c_child1_middle": "Pt7Line2_MiddleName[0]",
    "p7_3_child1_a_number": "Pt7Line2_AlienNumber[0]",
    "p7_4_child1_dob": "Pt7Line2_DateofBirth[0]",
    "p7_5_child1_country_birth": "Pt7Line2_Country[0]",

    "p7_8a_child2_family": "Pt7Line3_FamilyName[0]",
    "p7_8b_child2_given": "Pt7Line3_GivenName[0]",
    "p7_9_child2_a_number": "Pt7Line3_AlienNumber[0]",
    "p7_10_child2_dob": "Pt7Line3_DateofBirth[0]",
    "p7_11_child2_country": "Pt7Line3_Country[0]",

    # Part 8: Biographic (PDF uses Pt7 prefix confusingly)
    "p8_3a_height_feet": "Pt7Line3_HeightFeet[0]",
    "p8_3b_height_inches": "Pt7Line3_HeightInches[0]",

    # Part 11: Contact (PDF uses Pt3 prefix for contact!)
    "p11_3_daytime_phone": "Pt3Line3_DaytimePhoneNumber1[0]",
    "p11_4_mobile_phone": "Pt3Line4_MobileNumber1[0]",
    "p11_5_email": "Pt3Line5_Email[0]",

    # Part 12: Interpreter (PDF uses Pt11/P3 prefix mix)
    "p12_1a_interp_family": "Pt11Line1a_FamilyName[0]",
    "p12_1b_interp_given": "Pt11Line1b_GivenName[0]",
    "p12_2_interp_org": "Pt11Line2_OrgName[0]",
    "p12_4_interp_phone": "P3_Line4_DaytimeTelePhoneNumber[0]",
    "p12_5_interp_mobile": "P3_Line5_MobileTelePhoneNumber[0]",
    "p12_6_interp_email": "P3_Line6_Email[0]",
    "p12_7_language": "Part11_NameofLanguage[0]",

    # Part 13: Preparer (PDF uses Pt12 prefix)
    "p13_2a_prep_family": "Pt12Line1_PreparerFamilyName[0]",
    "p13_2b_prep_given": "Pt12Line1a_PreparerGivenName[0]",
    "p13_3_prep_org": "Pt12Line2_BusinessName[0]",
    "p13_5_prep_phone": "Pt12Line3_PreparerDaytimePhoneNumber1[0]",
    "p13_6_prep_mobile": "Pt12Line4_PreparerMobileNumber[0]",
    "p13_7_prep_email": "Pt12Line5_PreparerEmail[0]",

    # Part 14: Additional Information (PDF uses Pt9/P14 prefix)
    "p14_1a_page": "Pt9Line3a_PageNumber[0]",
    "p14_1b_part": "Pt9Line3b_PartNumber[0]",
    "p14_1c_item": "Pt9Line3c_ItemNumber[0]",
    "p14_1d_info": "P14_Line2_AdditionalInfo[0]",
    "p14_2a_page": "Pt9Line3a_PageNumber[1]",
    "p14_2b_part": "Pt9Line3b_PartNumber[1]",
    "p14_2c_item": "Pt9Line3c_ItemNumber[1]",
    "p14_2d_info": "P14_Line3_AdditionalInfo[0]",
}

# =============================================================================
# I-131: Application for Travel Documents, Parole Documents, and
#         Arrival/Departure Records
# Template ID: 43 | PDF fields: 325 | Our fields: 208
# =============================================================================
I131_FIELD_MAP = {
    # Part 2: Applicant Name
    "p2_1a_family_name": "Part2_Line1_FamilyName[0]",
    "p2_1b_given_name": "Part2_Line1_GivenName[0]",
    "p2_1c_middle_name": "Part2_Line1_MiddleName[0]",

    # Part 2: Other Names
    "p2_3a_other1_family": "Part2_Line2_FamilyName1[0]",
    "p2_3b_other1_given": "Part2_Line2_GivenName1[0]",
    "p2_3c_other1_middle": "Part2_Line2_MiddleName1[0]",

    # Part 2: Physical Address (PDF Line4 = physical)
    "p2_4a_street": "Part2_Line4_StreetNumberName[0]",
    "p2_4c_apt_number": "Part2_Line4_AptSteFlrNumber[0]",
    "p2_4d_city": "Part2_Line4_CityTown[0]",
    "p2_4e_state": "Part2_Line4_State[0]",
    "p2_4f_zip": "Part2_Line4_ZipCode[0]",

    # Part 2: Mailing Address (PDF Line3 = mailing)
    "p2_6a_mail_care_of": "Part2_Line3_InCareofName[0]",
    "p2_6b_mail_street": "Part2_Line3_StreetNumberName[0]",
    "p2_6c_mail_apt": "Part2_Line3_AptSteFlrNumber[0]",
    "p2_6d_mail_city": "Part2_Line3_CityTown[0]",
    "p2_6e_mail_state": "Part2_Line3_State[0]",
    "p2_6f_mail_zip": "Part2_Line3_ZipCode[0]",
    "p2_6g_mail_province": "Part2_Line3_Province[0]",
    "p2_6h_mail_postal": "Part2_Line3_PostalCode[0]",
    "p2_6i_mail_country": "Part2_Line3_Country[0]",

    # Part 2: IDs
    "p2_7_a_number": "Part2_Line5_AlienNumber[0]",
    "p2_8_uscis_account": "Part2_Line11_USCISOnlineAcctNumber[0]",
    "p2_9_ssn": "Part2_Line10_SSN[0]",

    # Part 2: Biographic
    "p2_10_dob": "Part2_Line9_DateOfBirth[0]",
    "p2_14_country_birth": "Part2_Line6_CountryOfBirth[0]",
    "p2_15_citizenship": "Part2_Line7_CountryOfCitizenshiporNationality[0]",

    # Part 2: Immigration Status
    "p2_16_class_of_admission": "Part2_Line12_ClassofAdmission[0]",
    "p2_18_i94_number": "Part2_Line13_I94RecordNo[0]",

    # Part 3: Biographic - Physical Description
    "p3_3_height_feet": "P3_Line3_HeightFeet[0]",
    "p3_4_height_inches": "P3_Line3_HeightInches[0]",

    # Part 7: Proposed Travel Info
    "p7_1_purpose_of_trip": "P7_Line2_Purpose[0]",
    "p7_2a_country1": "P7_Line3_ListCountries[0]",
    "p7_3_departure_date": "P7_Line1_DateOfDeparture[0]",
    "p7_5_trip_length": "P7_Line5_ExpectedLengthTrip[0]",

    # Part 10: Contact Information
    "p10_3_daytime_phone": "Part10_Line1_DayPhone[0]",
    "p10_4_mobile_phone": "Part10_Line2_MobilePhone[0]",
    "p10_5_email": "Part10_Line3_Email[0]",

    # Part 11: Interpreter
    "p11_1a_interp_family": "Part11_Line1_InterpreterFamilyName[0]",
    "p11_1b_interp_given": "Part11_Line1_InterpreterGivenName[0]",
    "p11_2_interp_org": "Part11_Line2_NameofBusinessorOrgName[0]",
    "p11_4_interp_phone": "Part11_Line3_DayPhone[0]",
    "p11_5_interp_email": "Part11_Line5_Email[0]",
    "p11_6_language": "P11_Language[0]",

    # Part 12: Preparer
    "p12_2a_prep_family": "Part12_Line1_FamilyName[0]",
    "p12_2b_prep_given": "Part12_Line1_GivenName[0]",
    "p12_3_prep_org": "Part12_Line2_NameofBusinessorOrgName[0]",
    "p12_5_prep_phone": "Part12_Line3_DayPhone[0]",
    "p12_6_prep_email": "Part12_Line5_Email[0]",

    # Part 13: Additional Info
    "p13_1a_page": "Part13_Line3_PageNumber[0]",
    "p13_1b_part": "Part13_Line3_PartNumber[0]",
    "p13_1c_item": "Part13_Line3_ItemNumber[0]",
    "p13_1d_answer": "Part13_Line3_AdditionalInfo[0]",
    "p13_2a_page": "Part13_Line4_PageNumber[0]",
    "p13_2b_part": "Part13_Line4_PartNumber[0]",
    "p13_2c_item": "Part13_Line4_ItemNumber[0]",
    "p13_2d_answer": "Part13_Line4_AdditionalInfo[0]",
}

# =============================================================================
# I-864: Affidavit of Support Under Section 213A of the INA
# Template ID: 41 | PDF fields: 207 | Our fields: 260
# QUIRKS: Email uses P7 prefix in Part 8! Interpreter org uses P8 prefix!
# =============================================================================
I864_FIELD_MAP = {
    # Header
    "header_g28_checkbox": "G28-CheckBox1[0]",

    # Part 2: Principal Immigrant Info
    "p2_1a_family_name": "P2_Line1a_FamilyName[0]",
    "p2_1b_given_name": "P2_Line1b_GivenName[0]",
    "p2_1c_middle_name": "P2_Line1c_MiddleName[0]",
    "p2_2a_care_of": "P2_Line2_InCareOf[0]",
    "p2_2b_street": "P2_Line2_StreetNumberName[0]",
    "p2_2d_apt_number": "P2_Line2_AptSteFlrNumber[0]",
    "p2_2e_city": "P2_Line2_CityOrTown[0]",
    "p2_2f_state": "P2_Line2_State[0]",
    "p2_2g_zip": "P2_Line2_ZipCode[0]",
    "p2_2h_province": "P2_Line2_Province[0]",
    "p2_2i_postal": "P2_Line2_PostalCode[0]",
    "p2_2j_country": "P2_Line2_Country[0]",
    "p2_3_dob": "P2_Line4_DateOfBirth[0]",
    "p2_4_a_number": "P2_Line5_AlienNumber[0]",
    "p2_5_uscis_account": "Pt2_Line6_USCISOnlineAcctNumber[0]",

    # Part 3: Family Members Being Sponsored
    # Family Member 1
    "p3_3a_fm1_family_name": "P3_Line3a_FamilyName[0]",
    "p3_3b_fm1_given_name": "P3_Line3b_GivenName[0]",
    "p3_3c_fm1_middle_name": "P3_Line3c_MiddleName[0]",
    "p3_4_fm1_relationship": "P3_Line4_Relationship[0]",
    "p3_5_fm1_dob": "P3_Line_DateOfBirth[0]",
    "p3_6_fm1_a_number": "P2_Line5_AlienNumber[1]",  # reuses P2 prefix!

    # Family Member 2
    "p3_7a_fm2_family_name": "P3_Line8a_FamilyName[0]",
    "p3_7b_fm2_given_name": "P3_Line8b_GivenName[0]",
    "p3_7c_fm2_middle_name": "P3_Line8c_MiddleName[0]",
    "p3_8_fm2_relationship": "P3_Line9_Relationship[0]",
    "p3_9_fm2_dob": "P3_Line10_DateOfBirth[0]",
    "p3_10_fm2_a_number": "P3_Line11_AlienNumber[0]",

    # Family Member 3
    "p3_11a_fm3_family_name": "P3_Line13a_FamilyName[0]",
    "p3_11b_fm3_given_name": "P3_Line13b_GivenName[0]",
    "p3_11c_fm3_middle_name": "P3_Line13c_MiddleName[0]",
    "p3_12_fm3_relationship": "P3_Line14_Relationship[0]",
    "p3_13_fm3_dob": "P3_Line15_DateOfBirth[0]",
    "p3_14_fm3_a_number": "P2_Line5_AlienNumber[2]",  # reuses P2 prefix!

    # Family Member 4
    "p3_15a_fm4_family_name": "P3_Line18a_FamilyName[0]",
    "p3_15b_fm4_given_name": "P3_Line18b_GivenName[0]",
    "p3_15c_fm4_middle_name": "P3_Line18c_MiddleName[0]",
    "p3_16_fm4_relationship": "P3_Line19_Relationship[0]",
    "p3_17_fm4_dob": "P3_Line20_DateOfBirth[0]",
    "p3_18_fm4_a_number": "P3_Line21_AlienNumber[0]",

    # Part 3: Total
    "p3_23_total_immigrants": "P3_Line28_TotalNumberofImmigrants[0]",

    # Part 4: Sponsor Information
    "p4_1a_family_name": "P4_Line1a_FamilyName[0]",
    "p4_1b_given_name": "P4_Line1b_GivenName[0]",
    "p4_1c_middle_name": "P4_Line1c_MiddleName[0]",
    "p4_2a_care_of": "P4_Line2a_InCareOf[0]",
    "p4_2b_street": "P4_Line2b_StreetNumberName[0]",
    "p4_2d_apt_number": "P4_Line2d_AptSteFlrNumber[0]",
    "p4_2e_city": "P4_Line2e_CityOrTown[0]",
    "p4_2f_state": "P4_Line2f_State[0]",
    "p4_2g_zip": "P4_Line2g_ZipCode[0]",
    "p4_3_country_domicile": "P4_Line5_CountryOfDomicile[0]",
    "p4_4_dob": "P4_Line6_DateOfBirth[0]",
    "p4_5_city_birth": "P4_Line7_CityofBirth[0]",
    "p4_8_ssn": "P4_Line10_SocialSecurityNumber[0]",
    "p4_10_a_number": "P4_Line12_AlienNumber[0]",
    "p4_11_uscis_account": "P4_Line13_AcctIdentifier[0]",

    # Part 5: Household Size
    "p5_1_yourself": "P5_Line2_Yourself[0]",
    "p5_2_spouse": "P5_Line3_Married[0]",
    "p5_3_dependents": "P5_Line4_DependentChildren[0]",
    "p5_4_other_dependents": "P5_Line5_OtherDependents[0]",
    "p5_5_sponsored_immigrants": "P5_Line6_Sponsors[0]",
    "p5_6_previous_sponsored": "P5_Line7_SameResidence[0]",

    # Part 6: Employment & Income
    "p6_1a_employer_name": "P6_Line1a_NameofEmployer[0]",
    "p6_2_self_employed": "P6_Line4a_SelfEmployedAs[0]",
    "p6_3_retired": "P6_Line5a_DateRetired[0]",
    "p6_4_unemployed": "P6_Line6a_DateofUnemployment[0]",
    "p6_5_current_annual_income": "P6_Line2_TotalIncome[0]",

    # Part 6: Household Members Income
    "p6_7a_person1_name": "P6_Line3_Name[0]",
    "p6_7b_person1_relationship": "P6_Line4_Relationship[0]",
    "p6_7c_person1_income": "P6_Line5_CurrentIncome[0]",
    "p6_8a_person2_name": "P6_Line6_Name[0]",
    "p6_8b_person2_relationship": "P6_Line7_Relationship[0]",
    "p6_8c_person2_income": "P6_Line8_CurrentIncome[0]",
    "p6_9a_person3_name": "P6_Line9_Name[0]",
    "p6_9b_person3_relationship": "P6_Line10_Relationship[0]",
    "p6_9c_person3_income": "P6_Line11_CurrentIncome[0]",
    "p6_10_total_household_income": "P6_Line15_TotalHouseholdIncome[0]",

    # Part 6: Tax Returns
    "p6_12_tax_year1": "P6_Line19a_TaxYear[0]",
    "p6_13_tax_year1_income": "P6_Line19a_TotalIncome[0]",
    "p6_14_tax_year2": "P6_Line19b_TaxYear[0]",
    "p6_15_tax_year2_income": "P6_Line19b_TotalIncome[0]",
    "p6_16_tax_year3": "P6_Line19c_TaxYear[0]",
    "p6_17_tax_year3_income": "P6_Line19c_TotalIncome[0]",

    # Part 7: Assets - Sponsor's
    "p7_2_savings": "P7_Line1_BalanceofAccounts[0]",
    "p7_4_real_estate": "P7_Line2_RealEstate[0]",
    "p7_3_stocks_bonds": "P7_Line3_StocksBonds[0]",
    "p7_6_total_sponsor_assets": "P7_Line4_Total[0]",

    # Part 7: Assets - Immigrant's
    "p7_7_immigrant_savings": "P7_Line6_BalanceofAccounts[0]",
    "p7_9_immigrant_real_estate": "P7_Line7_RealEstate[0]",
    "p7_8_immigrant_stocks": "P7_Line8_StocksBonds[0]",
    "p7_11_total_immigrant_assets": "P7_Line9_Total[0]",
    "p7_12_total_all_assets": "P7_Line10_TotalValueAssets[0]",

    # Part 8: Contact (QUIRK: email uses P7 prefix!)
    "p8_6_daytime_phone": "P8_Line3_DaytimeTelephoneNumber[0]",
    "p8_7_mobile_phone": "P8_Line4_MobileTelephoneNumber[0]",
    "p8_8_email": "P7Line7_EmailAddress[0]",  # QUIRK: P7 prefix in Part 8

    # Part 9: Interpreter (QUIRK: org uses P8 prefix!)
    "p9_1a_interp_family": "P9_Line1a_InterpretersFamilyName[0]",
    "p9_1b_interp_given": "P9_Line1b_InterpretersGivenName[0]",
    "p9_2_interp_org": "P8Line2_InterpretersBusinessName[0]",  # QUIRK: P8 prefix
    "p9_4_interp_phone": "P9_Line4_InterpretersDaytimePhoneNumber[0]",
    "p9_5_interp_mobile": "P9_Line4_InterpretersDaytimePhoneNumber[1]",  # [1] index
    "p9_6_interp_email": "P9_Line5_InterpretersEmailAddress[0]",
    "p9_7_language": "P9_Language[0]",

    # Part 10: Preparer
    "p10_2a_prep_family": "P10_Line1a_PreparersFamilyName[0]",
    "p10_2b_prep_given": "P10_Line1b_PreparersGivenName[0]",
    "p10_3_prep_org": "P10_Line2_PreparersBusinessName[0]",
    "p10_5_prep_phone": "P10_Line4_PreparersDaytimePhoneNumber[0]",
    "p10_7_prep_email": "P10_Line6_PreparersEmailAddress[0]",

    # Part 11: Additional Info
    "p11_1a_page": "P11_Line3a_PageNumber[0]",
    "p11_1b_part": "P11_Line3b_PartNumber[0]",
    "p11_1c_item": "P11_Line3c_ItemNumber[0]",
    "p11_1d_answer": "P11_Line3d_AdditionalInfo[0]",
    "p11_2a_page": "P11_Line4a_PageNumber[0]",
    "p11_2b_part": "P11_Line4b_PartNumber[0]",
    "p11_2c_item": "P11_Line4c_ItemNumber[0]",
    "p11_2d_answer": "P11_Line4d_AdditionalInfo[0]",
}
# =============================================================================
# I-130A: Supplemental Information for Spouse Beneficiary
# Used with I-130 for spouse petitions
# Parts 1-7: Beneficiary info, employment, statement, interpreter, preparer, additional info
# =============================================================================
I130A_FIELD_MAP = {
    # Header - Attorney Info
    "header_g28_checkbox": "CheckBox1[0]",
    "header_attorney_bar_number": "AttorneyStateBarNumber[0]",
    "header_volag_number": "VolagNumber[0]",
    "header_uscis_account": "Pt2Line3_USCISELISActNumber[0]",

    # Part 1: Beneficiary Information
    # A-Number
    "p1_1_a_number": "Pt1Line1_AlienNumber[0]",

    # Beneficiary Name (Item 3)
    "p1_3a_family_name": "Pt1Line3a_FamilyName[0]",
    "p1_3b_given_name": "Pt1Line3b_GivenName[0]",
    "p1_3c_middle_name": "Pt1Line3c_MiddleName[0]",

    # Last Address Outside the US (Item 4) - address abroad
    "p1_4a_street": "Pt1Line4a_StreetNumberName[0]",
    "p1_4b_apt_number": "Pt1Line4b_AptSteFlrNumber[0]",
    "p1_4c_city": "Pt1Line4c_CityOrTown[0]",
    "p1_4d_state": "Pt1Line4d_State[0]",
    "p1_4e_zip": "Pt1Line4e_ZipCode[0]",
    "p1_4f_province": "Pt1Line4f_Province[0]",
    "p1_4g_postal_code": "Pt1Line4g_PostalCode[0]",
    "p1_4h_country": "Pt1Line4h_Country[0]",
    "p1_5a_date_from": "Pt1Line5a_DateFrom[0]",
    "p1_5b_date_to": "Pt1Line5b_DateTo[0]",

    # Address Abroad 2 (Item 6)
    "p1_6a_street": "Pt1Line6a_StreetNumberName[0]",
    "p1_6b_apt_number": "Pt1Line6b_AptSteFlrNumber[0]",
    "p1_6c_city": "Pt1Line6c_CityOrTown[0]",
    "p1_6d_state": "Pt1Line6d_State[0]",
    "p1_6e_zip": "Pt1Line6e_ZipCode[0]",
    "p1_6f_province": "Pt1Line6f_Province[0]",
    "p1_6g_postal_code": "Pt1Line6g_PostalCode[0]",
    "p1_6h_country": "Pt1Line6h_Country[0]",
    "p1_7a_date_from": "Pt1Line7a_DateFrom[0]",
    "p1_7b_date_to": "Pt1Line7b_DateTo[0]",

    # Address Abroad 3 (Item 8) - no state/zip (foreign only)
    "p1_8a_street": "Pt1Line8a_StreetNumberName[0]",
    "p1_8b_apt_number": "Pt1Line8b_AptSteFlrNumber[0]",
    "p1_8c_city": "Pt1Line8c_CityOrTown[0]",
    "p1_8d_province": "Pt1Line8d_Province[0]",
    "p1_8e_postal_code": "Pt1Line8e_PostalCode[0]",
    "p1_8f_country": "Pt1Line8f_Country[0]",
    "p1_9a_date_from": "Pt1Line9a_DateFrom[0]",
    "p1_9b_date_to": "Pt1Line9b_DateTo[0]",

    # Beneficiary's Last Spouse (Item 10)
    "p1_10_family_name": "Pt1Line10_FamilyName[0]",
    "p1_10_given_name": "Pt1Line10_GivenName[0]",
    "p1_10_middle_name": "Pt1Line10_MiddleName[0]",
    "p1_11_dob": "Pt1Line11_DateofBirth[0]",
    "p1_12_city_birth": "Pt1Line12CityTownOfBirth[0]",
    "p1_13_country_birth": "Pt1Line13_CountryofBirth[0]",
    "p1_14_nationality": "Pt1Line14_CountryofBirth[0]",
    "p1_15_country_residence": "Pt1Line15_CountryofResidence[0]",

    # Beneficiary's Last Spouse - Gender (radio/checkbox)
    "p1_12_male": "Pt1Line12_Male[0]",
    "p1_12_female": "Pt1Line12_Female[0]",

    # Beneficiary's Father (Item 16)
    "p1_16_family_name": "Pt1Line16_FamilyName[0]",
    "p1_16_given_name": "Pt1Line16_GivenName[0]",
    "p1_16_middle_name": "Pt1Line16_MiddleName[0]",
    "p1_17_father_dob": "Pt1Line17_DateofBirth[0]",
    "p1_18_father_city_birth": "Pt1Line18_CityTownOfBirth[0]",
    "p1_19_father_country_birth": "Pt1Line19_CountryofBirth[0]",
    "p1_20_father_city_residence": "Pt1Line20_CityTownVillageofRes[0]",
    "p1_21_father_country_residence": "Pt1Line21_CountryofResidence[0]",

    # Father's Gender (radio/checkbox)
    "p1_19_father_male": "Pt1Line19_Male[0]",
    "p1_19_father_female": "Pt1Line19_Female[0]",

    # Part 2: Beneficiary's Employment History - Employer 1
    "p2_1_employer_name": "Pt2Line1_EmployerOrCompName[0]",
    "p2_2a_street": "Pt2Line2a_StreetNumberName[0]",
    "p2_3_occupation": "Pt2Line3_Occupation[0]",
    "p2_4a_date_from": "Pt2Line4a_DateFrom[0]",
    "p2_4b_date_to": "Pt2Line4b_DateTo[0]",

    # Part 2: Employer 2
    "p2_5_employer_name": "Pt2Line5_EmployerOrCompName[0]",
    "p2_6a_street": "Pt2Line6_StreetNumberName[0]",
    "p2_7_occupation": "Pt2Line7_Occupation[0]",
    "p2_8a_date_from": "Pt2Line8a_DateFrom[0]",
    "p2_8b_date_to": "Pt2Line8b_DateTo[0]",

    # Part 3: Additional Employment
    "p3_1_employer_name": "Pt3Line1_EmployerOrCompName[0]",
    "p3_2a_street": "Pt3Line2a_StreetNumberName[0]",
    "p3_3_occupation": "Pt3Line3_Occupation[0]",
    "p3_4a_date_from": "Pt3Line4a_DateFrom[0]",
    "p3_4b_date_to": "Pt3Line4b_DateTo[0]",

    # Part 4: Beneficiary's Statement & Contact
    "p4_1b_language": "Pt4Line1b_Language[0]",
    "p4_3_phone_day": "Pt4Line3_DaytimePhoneNumber1[0]",
    "p4_4_phone_mobile": "Pt4Line4_MobileNumber1[0]",
    "p4_5_email": "Pt4Line5_Email[0]",

    # Part 4: Statement checkboxes
    "p4_1_english": "Pt4Line1Checkbox[0]",
    "p4_1_interpreter": "Pt4Line1Checkbox[1]",
    "p4_2_preparer": "Pt4_Checkbox[0]",
}


# =============================================================================
# Master registry: form name -> field map dict
# =============================================================================
FORM_FIELD_MAPS = {
    "G-28": G28_FIELD_MAP,
    "I-130": I130_FIELD_MAP,
    "I-765": I765_FIELD_MAP,
    "I-140": I140_FIELD_MAP,
    "I-907": I907_FIELD_MAP,
    "I-485": I485_FIELD_MAP,
    "I-131": I131_FIELD_MAP,
    "I-864": I864_FIELD_MAP,
    "I-130A": I130A_FIELD_MAP,
}

# Template ID -> form name mapping
TEMPLATE_TO_FORM = {
    52: "G-28",
    38: "I-130",
    42: "I-765",
    19: "I-140",
    13: "I-907",
    40: "I-485",
    43: "I-131",
    41: "I-864",
}
