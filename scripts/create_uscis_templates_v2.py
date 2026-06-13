#!/usr/bin/env python3
"""
Create USCIS Form Templates with CORRECT descriptive labels
Based on official USCIS form structures
"""

import os
import sys
import psycopg2
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set. Export it or create .env")
    sys.exit(1)

# ============================================================================
# FORM I-130 - Petition for Alien Relative (12 pages)
# ============================================================================
I130_FIELDS = [
    # PART 1: Relationship
    {"section": "Part 1. Relationship", "label": "I am filing this petition for my:", "field_name": "p1_relationship_type", "field_type": "radio", "options": ["Spouse", "Parent", "Brother/Sister", "Child"], "required": True, "order": 1},
    {"section": "Part 1. Relationship", "label": "If filing for a child, the child relationship is:", "field_name": "p1_child_relationship", "field_type": "radio", "options": ["Legitimate child born in wedlock", "Stepchild", "Legally adopted child", "Child born out of wedlock"], "required": False, "order": 2},
    {"section": "Part 1. Relationship", "label": "If filing for a brother/sister, are you related by adoption?", "field_name": "p1_sibling_adoption", "field_type": "radio", "options": ["Yes", "No"], "required": False, "order": 3},
    {"section": "Part 1. Relationship", "label": "Did you gain permanent residence through adoption?", "field_name": "p1_pr_through_adoption", "field_type": "radio", "options": ["Yes", "No"], "required": False, "order": 4},

    # PART 2: Information About You (Petitioner)
    {"section": "Part 2. Information About You (Petitioner)", "label": "Alien Registration Number (A-Number)", "field_name": "p2_a_number", "field_type": "text", "options": [], "required": False, "order": 10, "help_text": "If any"},
    {"section": "Part 2. Information About You (Petitioner)", "label": "USCIS Online Account Number", "field_name": "p2_uscis_account", "field_type": "text", "options": [], "required": False, "order": 11},
    {"section": "Part 2. Information About You (Petitioner)", "label": "U.S. Social Security Number", "field_name": "p2_ssn", "field_type": "text", "options": [], "required": False, "order": 12},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Family Name (Last Name)", "field_name": "p2_last_name", "field_type": "text", "options": [], "required": True, "order": 13},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Given Name (First Name)", "field_name": "p2_first_name", "field_type": "text", "options": [], "required": True, "order": 14},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Middle Name", "field_name": "p2_middle_name", "field_type": "text", "options": [], "required": False, "order": 15},

    # Mailing Address
    {"section": "Part 2. Information About You (Petitioner)", "label": "Street Number and Name", "field_name": "p2_mail_street", "field_type": "text", "options": [], "required": True, "order": 20},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Apt/Ste/Flr", "field_name": "p2_mail_apt_type", "field_type": "select", "options": ["Apt", "Ste", "Flr"], "required": False, "order": 21},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Apt/Ste/Flr Number", "field_name": "p2_mail_apt_number", "field_type": "text", "options": [], "required": False, "order": 22},
    {"section": "Part 2. Information About You (Petitioner)", "label": "City or Town", "field_name": "p2_mail_city", "field_type": "text", "options": [], "required": True, "order": 23},
    {"section": "Part 2. Information About You (Petitioner)", "label": "State", "field_name": "p2_mail_state", "field_type": "select", "options": ["AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC","PR","VI","GU","AS","MP"], "required": True, "order": 24},
    {"section": "Part 2. Information About You (Petitioner)", "label": "ZIP Code", "field_name": "p2_mail_zip", "field_type": "text", "options": [], "required": True, "order": 25},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Province (if foreign address)", "field_name": "p2_mail_province", "field_type": "text", "options": [], "required": False, "order": 26},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Postal Code (if foreign address)", "field_name": "p2_mail_postal", "field_type": "text", "options": [], "required": False, "order": 27},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Country", "field_name": "p2_mail_country", "field_type": "text", "options": [], "required": True, "order": 28},

    # Physical Address
    {"section": "Part 2. Information About You (Petitioner)", "label": "Is your physical address the same as your mailing address?", "field_name": "p2_same_address", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 30},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Physical Address - Street Number and Name", "field_name": "p2_phys_street", "field_type": "text", "options": [], "required": False, "order": 31},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Physical Address - Apt/Ste/Flr", "field_name": "p2_phys_apt_type", "field_type": "select", "options": ["Apt", "Ste", "Flr"], "required": False, "order": 32},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Physical Address - Apt/Ste/Flr Number", "field_name": "p2_phys_apt_number", "field_type": "text", "options": [], "required": False, "order": 33},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Physical Address - City or Town", "field_name": "p2_phys_city", "field_type": "text", "options": [], "required": False, "order": 34},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Physical Address - State", "field_name": "p2_phys_state", "field_type": "select", "options": ["AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC","PR","VI","GU","AS","MP"], "required": False, "order": 35},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Physical Address - ZIP Code", "field_name": "p2_phys_zip", "field_type": "text", "options": [], "required": False, "order": 36},

    # Other Info
    {"section": "Part 2. Information About You (Petitioner)", "label": "Date of Birth", "field_name": "p2_dob", "field_type": "date", "options": [], "required": True, "order": 40},
    {"section": "Part 2. Information About You (Petitioner)", "label": "City/Town of Birth", "field_name": "p2_birth_city", "field_type": "text", "options": [], "required": True, "order": 41},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Country of Birth", "field_name": "p2_birth_country", "field_type": "text", "options": [], "required": True, "order": 42},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Country of Citizenship or Nationality", "field_name": "p2_citizenship", "field_type": "text", "options": [], "required": True, "order": 43},
    {"section": "Part 2. Information About You (Petitioner)", "label": "I am a:", "field_name": "p2_status", "field_type": "radio", "options": ["U.S. Citizen", "U.S. Lawful Permanent Resident"], "required": True, "order": 44},

    # Marriage Info
    {"section": "Part 2. Information About You (Petitioner)", "label": "Current Marital Status", "field_name": "p2_marital_status", "field_type": "radio", "options": ["Single, Never Married", "Married", "Divorced", "Widowed", "Marriage Annulled", "Legally Separated"], "required": True, "order": 50},
    {"section": "Part 2. Information About You (Petitioner)", "label": "How many times have you been married?", "field_name": "p2_times_married", "field_type": "number", "options": [], "required": True, "order": 51},

    # Employment
    {"section": "Part 2. Information About You (Petitioner)", "label": "Current Employer or Company Name", "field_name": "p2_employer", "field_type": "text", "options": [], "required": False, "order": 55},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Employer Street Address", "field_name": "p2_employer_street", "field_type": "text", "options": [], "required": False, "order": 56},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Employer City", "field_name": "p2_employer_city", "field_type": "text", "options": [], "required": False, "order": 57},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Employer State", "field_name": "p2_employer_state", "field_type": "select", "options": ["AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC"], "required": False, "order": 58},
    {"section": "Part 2. Information About You (Petitioner)", "label": "Employer ZIP Code", "field_name": "p2_employer_zip", "field_type": "text", "options": [], "required": False, "order": 59},

    # PART 3: Biographic Information (Petitioner)
    {"section": "Part 3. Biographic Information", "label": "Ethnicity", "field_name": "p3_ethnicity", "field_type": "radio", "options": ["Hispanic or Latino", "Not Hispanic or Latino"], "required": True, "order": 60},
    {"section": "Part 3. Biographic Information", "label": "Race (select all that apply)", "field_name": "p3_race", "field_type": "checkbox", "options": ["White", "Asian", "Black or African American", "American Indian or Alaska Native", "Native Hawaiian or Other Pacific Islander"], "required": True, "order": 61},
    {"section": "Part 3. Biographic Information", "label": "Height (Feet)", "field_name": "p3_height_feet", "field_type": "select", "options": ["3","4","5","6","7"], "required": True, "order": 62},
    {"section": "Part 3. Biographic Information", "label": "Height (Inches)", "field_name": "p3_height_inches", "field_type": "select", "options": ["0","1","2","3","4","5","6","7","8","9","10","11"], "required": True, "order": 63},
    {"section": "Part 3. Biographic Information", "label": "Weight (Pounds)", "field_name": "p3_weight", "field_type": "number", "options": [], "required": True, "order": 64},
    {"section": "Part 3. Biographic Information", "label": "Eye Color", "field_name": "p3_eye_color", "field_type": "select", "options": ["Black", "Blue", "Brown", "Gray", "Green", "Hazel", "Maroon", "Pink", "Unknown/Other"], "required": True, "order": 65},
    {"section": "Part 3. Biographic Information", "label": "Hair Color", "field_name": "p3_hair_color", "field_type": "select", "options": ["Bald (No Hair)", "Black", "Blond", "Brown", "Gray", "Red", "Sandy", "White", "Unknown/Other"], "required": True, "order": 66},

    # PART 4: Information About Beneficiary
    {"section": "Part 4. Information About Beneficiary", "label": "Alien Registration Number (A-Number)", "field_name": "p4_a_number", "field_type": "text", "options": [], "required": False, "order": 70},
    {"section": "Part 4. Information About Beneficiary", "label": "USCIS Online Account Number", "field_name": "p4_uscis_account", "field_type": "text", "options": [], "required": False, "order": 71},
    {"section": "Part 4. Information About Beneficiary", "label": "U.S. Social Security Number", "field_name": "p4_ssn", "field_type": "text", "options": [], "required": False, "order": 72},
    {"section": "Part 4. Information About Beneficiary", "label": "Family Name (Last Name)", "field_name": "p4_last_name", "field_type": "text", "options": [], "required": True, "order": 73},
    {"section": "Part 4. Information About Beneficiary", "label": "Given Name (First Name)", "field_name": "p4_first_name", "field_type": "text", "options": [], "required": True, "order": 74},
    {"section": "Part 4. Information About Beneficiary", "label": "Middle Name", "field_name": "p4_middle_name", "field_type": "text", "options": [], "required": False, "order": 75},

    # Beneficiary Other Names
    {"section": "Part 4. Information About Beneficiary", "label": "Other Names Used - Family Name", "field_name": "p4_other_last_name", "field_type": "text", "options": [], "required": False, "order": 76},
    {"section": "Part 4. Information About Beneficiary", "label": "Other Names Used - Given Name", "field_name": "p4_other_first_name", "field_type": "text", "options": [], "required": False, "order": 77},
    {"section": "Part 4. Information About Beneficiary", "label": "Other Names Used - Middle Name", "field_name": "p4_other_middle_name", "field_type": "text", "options": [], "required": False, "order": 78},

    # Beneficiary Address
    {"section": "Part 4. Information About Beneficiary", "label": "Current Address - Street Number and Name", "field_name": "p4_street", "field_type": "text", "options": [], "required": True, "order": 80},
    {"section": "Part 4. Information About Beneficiary", "label": "Current Address - City or Town", "field_name": "p4_city", "field_type": "text", "options": [], "required": True, "order": 81},
    {"section": "Part 4. Information About Beneficiary", "label": "Current Address - State/Province", "field_name": "p4_state", "field_type": "text", "options": [], "required": False, "order": 82},
    {"section": "Part 4. Information About Beneficiary", "label": "Current Address - Country", "field_name": "p4_country", "field_type": "text", "options": [], "required": True, "order": 83},
    {"section": "Part 4. Information About Beneficiary", "label": "Current Address - Postal Code", "field_name": "p4_postal", "field_type": "text", "options": [], "required": False, "order": 84},

    # Beneficiary Other Info
    {"section": "Part 4. Information About Beneficiary", "label": "Date of Birth", "field_name": "p4_dob", "field_type": "date", "options": [], "required": True, "order": 90},
    {"section": "Part 4. Information About Beneficiary", "label": "City/Town of Birth", "field_name": "p4_birth_city", "field_type": "text", "options": [], "required": True, "order": 91},
    {"section": "Part 4. Information About Beneficiary", "label": "Country of Birth", "field_name": "p4_birth_country", "field_type": "text", "options": [], "required": True, "order": 92},
    {"section": "Part 4. Information About Beneficiary", "label": "Country of Citizenship or Nationality", "field_name": "p4_citizenship", "field_type": "text", "options": [], "required": True, "order": 93},
    {"section": "Part 4. Information About Beneficiary", "label": "Sex", "field_name": "p4_sex", "field_type": "radio", "options": ["Male", "Female"], "required": True, "order": 94},

    # Beneficiary Marriage
    {"section": "Part 4. Information About Beneficiary", "label": "Current Marital Status", "field_name": "p4_marital_status", "field_type": "radio", "options": ["Single, Never Married", "Married", "Divorced", "Widowed", "Marriage Annulled", "Legally Separated"], "required": True, "order": 100},
    {"section": "Part 4. Information About Beneficiary", "label": "How many times has the beneficiary been married?", "field_name": "p4_times_married", "field_type": "number", "options": [], "required": True, "order": 101},

    # Beneficiary Immigration Info
    {"section": "Part 4. Information About Beneficiary", "label": "Is the beneficiary currently in the United States?", "field_name": "p4_in_us", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 110},
    {"section": "Part 4. Information About Beneficiary", "label": "Date of Last Entry (if in U.S.)", "field_name": "p4_last_entry_date", "field_type": "date", "options": [], "required": False, "order": 111},
    {"section": "Part 4. Information About Beneficiary", "label": "Place of Last Entry - City and State", "field_name": "p4_last_entry_place", "field_type": "text", "options": [], "required": False, "order": 112},
    {"section": "Part 4. Information About Beneficiary", "label": "I-94 Arrival-Departure Record Number", "field_name": "p4_i94_number", "field_type": "text", "options": [], "required": False, "order": 113},
    {"section": "Part 4. Information About Beneficiary", "label": "Current Immigration Status", "field_name": "p4_immigration_status", "field_type": "text", "options": [], "required": False, "order": 114, "help_text": "e.g., B-2, F-1, H-1B, etc."},
    {"section": "Part 4. Information About Beneficiary", "label": "Status Expiration Date", "field_name": "p4_status_expires", "field_type": "date", "options": [], "required": False, "order": 115},
    {"section": "Part 4. Information About Beneficiary", "label": "Passport Number", "field_name": "p4_passport_number", "field_type": "text", "options": [], "required": False, "order": 116},
    {"section": "Part 4. Information About Beneficiary", "label": "Travel Document Number", "field_name": "p4_travel_doc_number", "field_type": "text", "options": [], "required": False, "order": 117},
    {"section": "Part 4. Information About Beneficiary", "label": "Country of Issuance for Passport/Travel Document", "field_name": "p4_passport_country", "field_type": "text", "options": [], "required": False, "order": 118},
    {"section": "Part 4. Information About Beneficiary", "label": "Passport/Travel Document Expiration Date", "field_name": "p4_passport_expires", "field_type": "date", "options": [], "required": False, "order": 119},

    # Beneficiary's Parents
    {"section": "Part 4. Information About Beneficiary", "label": "Beneficiary's Father - Family Name", "field_name": "p4_father_last_name", "field_type": "text", "options": [], "required": True, "order": 125},
    {"section": "Part 4. Information About Beneficiary", "label": "Beneficiary's Father - Given Name", "field_name": "p4_father_first_name", "field_type": "text", "options": [], "required": True, "order": 126},
    {"section": "Part 4. Information About Beneficiary", "label": "Beneficiary's Father - Date of Birth", "field_name": "p4_father_dob", "field_type": "date", "options": [], "required": False, "order": 127},
    {"section": "Part 4. Information About Beneficiary", "label": "Beneficiary's Father - Country of Birth", "field_name": "p4_father_birth_country", "field_type": "text", "options": [], "required": False, "order": 128},
    {"section": "Part 4. Information About Beneficiary", "label": "Beneficiary's Father - City/Town of Residence", "field_name": "p4_father_city", "field_type": "text", "options": [], "required": False, "order": 129},
    {"section": "Part 4. Information About Beneficiary", "label": "Beneficiary's Mother - Family Name", "field_name": "p4_mother_last_name", "field_type": "text", "options": [], "required": True, "order": 130},
    {"section": "Part 4. Information About Beneficiary", "label": "Beneficiary's Mother - Given Name", "field_name": "p4_mother_first_name", "field_type": "text", "options": [], "required": True, "order": 131},
    {"section": "Part 4. Information About Beneficiary", "label": "Beneficiary's Mother - Date of Birth", "field_name": "p4_mother_dob", "field_type": "date", "options": [], "required": False, "order": 132},
    {"section": "Part 4. Information About Beneficiary", "label": "Beneficiary's Mother - Country of Birth", "field_name": "p4_mother_birth_country", "field_type": "text", "options": [], "required": False, "order": 133},
    {"section": "Part 4. Information About Beneficiary", "label": "Beneficiary's Mother - City/Town of Residence", "field_name": "p4_mother_city", "field_type": "text", "options": [], "required": False, "order": 134},

    # PART 5: Other Information
    {"section": "Part 5. Other Information", "label": "Has anyone else ever filed a petition for the beneficiary?", "field_name": "p5_prior_petition", "field_type": "radio", "options": ["Yes", "No", "Unknown"], "required": True, "order": 140},

    # PART 6: Petitioner's Statement
    {"section": "Part 6. Petitioner's Statement", "label": "Can you read and understand English?", "field_name": "p6_read_english", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 150},
    {"section": "Part 6. Petitioner's Statement", "label": "Language used by interpreter", "field_name": "p6_interpreter_language", "field_type": "text", "options": [], "required": False, "order": 151},
    {"section": "Part 6. Petitioner's Statement", "label": "Petitioner's Daytime Telephone Number", "field_name": "p6_phone", "field_type": "phone", "options": [], "required": True, "order": 152},
    {"section": "Part 6. Petitioner's Statement", "label": "Petitioner's Mobile Telephone Number", "field_name": "p6_mobile", "field_type": "phone", "options": [], "required": False, "order": 153},
    {"section": "Part 6. Petitioner's Statement", "label": "Petitioner's Email Address", "field_name": "p6_email", "field_type": "email", "options": [], "required": False, "order": 154},
]

# ============================================================================
# FORM I-130A - Supplemental Information for Spouse Beneficiary
# ============================================================================
I130A_FIELDS = [
    # PART 1: Information About Spouse Beneficiary
    {"section": "Part 1. Information About Spouse Beneficiary", "label": "Alien Registration Number (A-Number)", "field_name": "p1_a_number", "field_type": "text", "options": [], "required": False, "order": 1},
    {"section": "Part 1. Information About Spouse Beneficiary", "label": "Family Name (Last Name)", "field_name": "p1_last_name", "field_type": "text", "options": [], "required": True, "order": 2},
    {"section": "Part 1. Information About Spouse Beneficiary", "label": "Given Name (First Name)", "field_name": "p1_first_name", "field_type": "text", "options": [], "required": True, "order": 3},
    {"section": "Part 1. Information About Spouse Beneficiary", "label": "Middle Name", "field_name": "p1_middle_name", "field_type": "text", "options": [], "required": False, "order": 4},

    # Address History (Last 5 years) - Address 1
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 1 - Street Number and Name", "field_name": "p1_addr1_street", "field_type": "text", "options": [], "required": True, "order": 10},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 1 - Apt/Ste/Flr", "field_name": "p1_addr1_apt_type", "field_type": "select", "options": ["Apt", "Ste", "Flr"], "required": False, "order": 11},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 1 - Apt/Ste/Flr Number", "field_name": "p1_addr1_apt_number", "field_type": "text", "options": [], "required": False, "order": 12},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 1 - City or Town", "field_name": "p1_addr1_city", "field_type": "text", "options": [], "required": True, "order": 13},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 1 - State/Province", "field_name": "p1_addr1_state", "field_type": "text", "options": [], "required": False, "order": 14},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 1 - ZIP/Postal Code", "field_name": "p1_addr1_zip", "field_type": "text", "options": [], "required": False, "order": 15},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 1 - Country", "field_name": "p1_addr1_country", "field_type": "text", "options": [], "required": True, "order": 16},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 1 - Date From", "field_name": "p1_addr1_from", "field_type": "date", "options": [], "required": True, "order": 17},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 1 - Date To", "field_name": "p1_addr1_to", "field_type": "date", "options": [], "required": False, "order": 18, "help_text": "Leave blank if current address"},

    # Address 2
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 2 - Street Number and Name", "field_name": "p1_addr2_street", "field_type": "text", "options": [], "required": False, "order": 20},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 2 - City or Town", "field_name": "p1_addr2_city", "field_type": "text", "options": [], "required": False, "order": 21},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 2 - State/Province", "field_name": "p1_addr2_state", "field_type": "text", "options": [], "required": False, "order": 22},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 2 - Country", "field_name": "p1_addr2_country", "field_type": "text", "options": [], "required": False, "order": 23},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 2 - Date From", "field_name": "p1_addr2_from", "field_type": "date", "options": [], "required": False, "order": 24},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 2 - Date To", "field_name": "p1_addr2_to", "field_type": "date", "options": [], "required": False, "order": 25},

    # Address 3
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 3 - Street Number and Name", "field_name": "p1_addr3_street", "field_type": "text", "options": [], "required": False, "order": 30},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 3 - City or Town", "field_name": "p1_addr3_city", "field_type": "text", "options": [], "required": False, "order": 31},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 3 - State/Province", "field_name": "p1_addr3_state", "field_type": "text", "options": [], "required": False, "order": 32},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 3 - Country", "field_name": "p1_addr3_country", "field_type": "text", "options": [], "required": False, "order": 33},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 3 - Date From", "field_name": "p1_addr3_from", "field_type": "date", "options": [], "required": False, "order": 34},
    {"section": "Part 1. Address History (Last 5 Years)", "label": "Address 3 - Date To", "field_name": "p1_addr3_to", "field_type": "date", "options": [], "required": False, "order": 35},

    # PART 2: Employment History
    {"section": "Part 2. Employment History (Last 5 Years)", "label": "Employer 1 - Name", "field_name": "p2_emp1_name", "field_type": "text", "options": [], "required": False, "order": 40},
    {"section": "Part 2. Employment History (Last 5 Years)", "label": "Employer 1 - Street Address", "field_name": "p2_emp1_street", "field_type": "text", "options": [], "required": False, "order": 41},
    {"section": "Part 2. Employment History (Last 5 Years)", "label": "Employer 1 - City", "field_name": "p2_emp1_city", "field_type": "text", "options": [], "required": False, "order": 42},
    {"section": "Part 2. Employment History (Last 5 Years)", "label": "Employer 1 - State/Province", "field_name": "p2_emp1_state", "field_type": "text", "options": [], "required": False, "order": 43},
    {"section": "Part 2. Employment History (Last 5 Years)", "label": "Employer 1 - Country", "field_name": "p2_emp1_country", "field_type": "text", "options": [], "required": False, "order": 44},
    {"section": "Part 2. Employment History (Last 5 Years)", "label": "Employer 1 - Occupation", "field_name": "p2_emp1_occupation", "field_type": "text", "options": [], "required": False, "order": 45},
    {"section": "Part 2. Employment History (Last 5 Years)", "label": "Employer 1 - Date From", "field_name": "p2_emp1_from", "field_type": "date", "options": [], "required": False, "order": 46},
    {"section": "Part 2. Employment History (Last 5 Years)", "label": "Employer 1 - Date To", "field_name": "p2_emp1_to", "field_type": "date", "options": [], "required": False, "order": 47, "help_text": "Leave blank if current employer"},

    {"section": "Part 2. Employment History (Last 5 Years)", "label": "Employer 2 - Name", "field_name": "p2_emp2_name", "field_type": "text", "options": [], "required": False, "order": 50},
    {"section": "Part 2. Employment History (Last 5 Years)", "label": "Employer 2 - City", "field_name": "p2_emp2_city", "field_type": "text", "options": [], "required": False, "order": 51},
    {"section": "Part 2. Employment History (Last 5 Years)", "label": "Employer 2 - Country", "field_name": "p2_emp2_country", "field_type": "text", "options": [], "required": False, "order": 52},
    {"section": "Part 2. Employment History (Last 5 Years)", "label": "Employer 2 - Occupation", "field_name": "p2_emp2_occupation", "field_type": "text", "options": [], "required": False, "order": 53},
    {"section": "Part 2. Employment History (Last 5 Years)", "label": "Employer 2 - Date From", "field_name": "p2_emp2_from", "field_type": "date", "options": [], "required": False, "order": 54},
    {"section": "Part 2. Employment History (Last 5 Years)", "label": "Employer 2 - Date To", "field_name": "p2_emp2_to", "field_type": "date", "options": [], "required": False, "order": 55},

    # PART 3: Information About Parents
    {"section": "Part 3. Information About Your Parents", "label": "Father's Family Name (Last Name)", "field_name": "p3_father_last_name", "field_type": "text", "options": [], "required": True, "order": 60},
    {"section": "Part 3. Information About Your Parents", "label": "Father's Given Name (First Name)", "field_name": "p3_father_first_name", "field_type": "text", "options": [], "required": True, "order": 61},
    {"section": "Part 3. Information About Your Parents", "label": "Father's Middle Name", "field_name": "p3_father_middle_name", "field_type": "text", "options": [], "required": False, "order": 62},
    {"section": "Part 3. Information About Your Parents", "label": "Father's Date of Birth", "field_name": "p3_father_dob", "field_type": "date", "options": [], "required": False, "order": 63},
    {"section": "Part 3. Information About Your Parents", "label": "Father's Sex", "field_name": "p3_father_sex", "field_type": "radio", "options": ["Male", "Female"], "required": False, "order": 64},
    {"section": "Part 3. Information About Your Parents", "label": "Father's Country of Birth", "field_name": "p3_father_birth_country", "field_type": "text", "options": [], "required": False, "order": 65},
    {"section": "Part 3. Information About Your Parents", "label": "Father's City of Residence", "field_name": "p3_father_city", "field_type": "text", "options": [], "required": False, "order": 66},
    {"section": "Part 3. Information About Your Parents", "label": "Father's Country of Residence", "field_name": "p3_father_country", "field_type": "text", "options": [], "required": False, "order": 67},

    {"section": "Part 3. Information About Your Parents", "label": "Mother's Family Name (Last Name)", "field_name": "p3_mother_last_name", "field_type": "text", "options": [], "required": True, "order": 70},
    {"section": "Part 3. Information About Your Parents", "label": "Mother's Given Name (First Name)", "field_name": "p3_mother_first_name", "field_type": "text", "options": [], "required": True, "order": 71},
    {"section": "Part 3. Information About Your Parents", "label": "Mother's Maiden Name", "field_name": "p3_mother_maiden_name", "field_type": "text", "options": [], "required": False, "order": 72},
    {"section": "Part 3. Information About Your Parents", "label": "Mother's Date of Birth", "field_name": "p3_mother_dob", "field_type": "date", "options": [], "required": False, "order": 73},
    {"section": "Part 3. Information About Your Parents", "label": "Mother's Sex", "field_name": "p3_mother_sex", "field_type": "radio", "options": ["Male", "Female"], "required": False, "order": 74},
    {"section": "Part 3. Information About Your Parents", "label": "Mother's Country of Birth", "field_name": "p3_mother_birth_country", "field_type": "text", "options": [], "required": False, "order": 75},
    {"section": "Part 3. Information About Your Parents", "label": "Mother's City of Residence", "field_name": "p3_mother_city", "field_type": "text", "options": [], "required": False, "order": 76},
    {"section": "Part 3. Information About Your Parents", "label": "Mother's Country of Residence", "field_name": "p3_mother_country", "field_type": "text", "options": [], "required": False, "order": 77},

    # PART 4: Beneficiary's Statement
    {"section": "Part 4. Beneficiary's Statement", "label": "Can you read and understand English?", "field_name": "p4_read_english", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 80},
    {"section": "Part 4. Beneficiary's Statement", "label": "Language used by interpreter", "field_name": "p4_interpreter_language", "field_type": "text", "options": [], "required": False, "order": 81},
    {"section": "Part 4. Beneficiary's Statement", "label": "Daytime Telephone Number", "field_name": "p4_phone", "field_type": "phone", "options": [], "required": False, "order": 82},
    {"section": "Part 4. Beneficiary's Statement", "label": "Mobile Telephone Number", "field_name": "p4_mobile", "field_type": "phone", "options": [], "required": False, "order": 83},
    {"section": "Part 4. Beneficiary's Statement", "label": "Email Address", "field_name": "p4_email", "field_type": "email", "options": [], "required": False, "order": 84},
]

# ============================================================================
# FORM I-485 - Application to Register Permanent Residence
# ============================================================================
I485_FIELDS = [
    # PART 1: Information About You
    {"section": "Part 1. Information About You", "label": "Alien Registration Number (A-Number)", "field_name": "p1_a_number", "field_type": "text", "options": [], "required": False, "order": 1},
    {"section": "Part 1. Information About You", "label": "USCIS Online Account Number", "field_name": "p1_uscis_account", "field_type": "text", "options": [], "required": False, "order": 2},
    {"section": "Part 1. Information About You", "label": "U.S. Social Security Number", "field_name": "p1_ssn", "field_type": "text", "options": [], "required": False, "order": 3},
    {"section": "Part 1. Information About You", "label": "Family Name (Last Name)", "field_name": "p1_last_name", "field_type": "text", "options": [], "required": True, "order": 4},
    {"section": "Part 1. Information About You", "label": "Given Name (First Name)", "field_name": "p1_first_name", "field_type": "text", "options": [], "required": True, "order": 5},
    {"section": "Part 1. Information About You", "label": "Middle Name", "field_name": "p1_middle_name", "field_type": "text", "options": [], "required": False, "order": 6},

    # Other Names
    {"section": "Part 1. Information About You", "label": "Other Names Used - Family Name", "field_name": "p1_other_last_name", "field_type": "text", "options": [], "required": False, "order": 7},
    {"section": "Part 1. Information About You", "label": "Other Names Used - Given Name", "field_name": "p1_other_first_name", "field_type": "text", "options": [], "required": False, "order": 8},
    {"section": "Part 1. Information About You", "label": "Other Names Used - Middle Name", "field_name": "p1_other_middle_name", "field_type": "text", "options": [], "required": False, "order": 9},

    # Mailing Address
    {"section": "Part 1. Information About You", "label": "Mailing Address - Street Number and Name", "field_name": "p1_mail_street", "field_type": "text", "options": [], "required": True, "order": 15},
    {"section": "Part 1. Information About You", "label": "Mailing Address - Apt/Ste/Flr", "field_name": "p1_mail_apt_type", "field_type": "select", "options": ["Apt", "Ste", "Flr"], "required": False, "order": 16},
    {"section": "Part 1. Information About You", "label": "Mailing Address - Apt/Ste/Flr Number", "field_name": "p1_mail_apt_number", "field_type": "text", "options": [], "required": False, "order": 17},
    {"section": "Part 1. Information About You", "label": "Mailing Address - City or Town", "field_name": "p1_mail_city", "field_type": "text", "options": [], "required": True, "order": 18},
    {"section": "Part 1. Information About You", "label": "Mailing Address - State", "field_name": "p1_mail_state", "field_type": "select", "options": ["AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC","PR","VI","GU","AS","MP"], "required": True, "order": 19},
    {"section": "Part 1. Information About You", "label": "Mailing Address - ZIP Code", "field_name": "p1_mail_zip", "field_type": "text", "options": [], "required": True, "order": 20},

    # Personal Info
    {"section": "Part 1. Information About You", "label": "Date of Birth", "field_name": "p1_dob", "field_type": "date", "options": [], "required": True, "order": 30},
    {"section": "Part 1. Information About You", "label": "City/Town of Birth", "field_name": "p1_birth_city", "field_type": "text", "options": [], "required": True, "order": 31},
    {"section": "Part 1. Information About You", "label": "Country of Birth", "field_name": "p1_birth_country", "field_type": "text", "options": [], "required": True, "order": 32},
    {"section": "Part 1. Information About You", "label": "Country of Citizenship or Nationality", "field_name": "p1_citizenship", "field_type": "text", "options": [], "required": True, "order": 33},
    {"section": "Part 1. Information About You", "label": "Sex", "field_name": "p1_sex", "field_type": "radio", "options": ["Male", "Female"], "required": True, "order": 34},

    # PART 2: Application Type
    {"section": "Part 2. Application Type", "label": "I am applying based on:", "field_name": "p2_application_basis", "field_type": "radio", "options": [
        "An immigrant petition filed by my spouse/parent/child (I-130)",
        "An immigrant petition filed by an employer (I-140)",
        "Diversity Visa Lottery",
        "Special Immigrant status",
        "Adjustment under Cuban Adjustment Act",
        "Registry (continuous residence since before January 1, 1972)",
        "Other"
    ], "required": True, "order": 40},
    {"section": "Part 2. Application Type", "label": "If other, explain:", "field_name": "p2_other_explanation", "field_type": "textarea", "options": [], "required": False, "order": 41},

    # PART 3: Additional Information About You
    {"section": "Part 3. Additional Information About You", "label": "Have you EVER been in immigration proceedings?", "field_name": "p3_immigration_proceedings", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 50},
    {"section": "Part 3. Additional Information About You", "label": "If yes, what type of proceedings?", "field_name": "p3_proceedings_type", "field_type": "checkbox", "options": ["Exclusion", "Deportation", "Removal", "Rescission"], "required": False, "order": 51},
    {"section": "Part 3. Additional Information About You", "label": "Where were the proceedings held? (City and State)", "field_name": "p3_proceedings_location", "field_type": "text", "options": [], "required": False, "order": 52},
    {"section": "Part 3. Additional Information About You", "label": "Date proceedings began", "field_name": "p3_proceedings_date", "field_type": "date", "options": [], "required": False, "order": 53},

    # Last Entry
    {"section": "Part 3. Additional Information About You", "label": "Date of Last Arrival in the U.S.", "field_name": "p3_last_arrival_date", "field_type": "date", "options": [], "required": True, "order": 60},
    {"section": "Part 3. Additional Information About You", "label": "Place of Last Arrival (City and State)", "field_name": "p3_last_arrival_place", "field_type": "text", "options": [], "required": True, "order": 61},
    {"section": "Part 3. Additional Information About You", "label": "I-94 Arrival-Departure Record Number", "field_name": "p3_i94_number", "field_type": "text", "options": [], "required": False, "order": 62},
    {"section": "Part 3. Additional Information About You", "label": "Status at Last Arrival", "field_name": "p3_arrival_status", "field_type": "text", "options": [], "required": True, "order": 63, "help_text": "e.g., B-2, F-1, K-1"},
    {"section": "Part 3. Additional Information About You", "label": "Current Immigration Status", "field_name": "p3_current_status", "field_type": "text", "options": [], "required": True, "order": 64},
    {"section": "Part 3. Additional Information About You", "label": "Status Expiration Date", "field_name": "p3_status_expires", "field_type": "date", "options": [], "required": False, "order": 65},

    # Passport
    {"section": "Part 3. Additional Information About You", "label": "Passport Number", "field_name": "p3_passport_number", "field_type": "text", "options": [], "required": False, "order": 70},
    {"section": "Part 3. Additional Information About You", "label": "Travel Document Number", "field_name": "p3_travel_doc_number", "field_type": "text", "options": [], "required": False, "order": 71},
    {"section": "Part 3. Additional Information About You", "label": "Country of Issuance", "field_name": "p3_passport_country", "field_type": "text", "options": [], "required": False, "order": 72},
    {"section": "Part 3. Additional Information About You", "label": "Expiration Date", "field_name": "p3_passport_expires", "field_type": "date", "options": [], "required": False, "order": 73},

    # PART 4: Information About Your Parents
    {"section": "Part 4. Information About Your Parents", "label": "Parent 1 - Family Name (Last Name)", "field_name": "p4_parent1_last_name", "field_type": "text", "options": [], "required": True, "order": 80},
    {"section": "Part 4. Information About Your Parents", "label": "Parent 1 - Given Name (First Name)", "field_name": "p4_parent1_first_name", "field_type": "text", "options": [], "required": True, "order": 81},
    {"section": "Part 4. Information About Your Parents", "label": "Parent 1 - Date of Birth", "field_name": "p4_parent1_dob", "field_type": "date", "options": [], "required": False, "order": 82},
    {"section": "Part 4. Information About Your Parents", "label": "Parent 1 - Sex", "field_name": "p4_parent1_sex", "field_type": "radio", "options": ["Male", "Female"], "required": False, "order": 83},
    {"section": "Part 4. Information About Your Parents", "label": "Parent 1 - Country of Birth", "field_name": "p4_parent1_birth_country", "field_type": "text", "options": [], "required": False, "order": 84},
    {"section": "Part 4. Information About Your Parents", "label": "Parent 1 - City of Residence", "field_name": "p4_parent1_city", "field_type": "text", "options": [], "required": False, "order": 85},

    {"section": "Part 4. Information About Your Parents", "label": "Parent 2 - Family Name (Last Name)", "field_name": "p4_parent2_last_name", "field_type": "text", "options": [], "required": True, "order": 90},
    {"section": "Part 4. Information About Your Parents", "label": "Parent 2 - Given Name (First Name)", "field_name": "p4_parent2_first_name", "field_type": "text", "options": [], "required": True, "order": 91},
    {"section": "Part 4. Information About Your Parents", "label": "Parent 2 - Maiden Name", "field_name": "p4_parent2_maiden_name", "field_type": "text", "options": [], "required": False, "order": 92},
    {"section": "Part 4. Information About Your Parents", "label": "Parent 2 - Date of Birth", "field_name": "p4_parent2_dob", "field_type": "date", "options": [], "required": False, "order": 93},
    {"section": "Part 4. Information About Your Parents", "label": "Parent 2 - Sex", "field_name": "p4_parent2_sex", "field_type": "radio", "options": ["Male", "Female"], "required": False, "order": 94},
    {"section": "Part 4. Information About Your Parents", "label": "Parent 2 - Country of Birth", "field_name": "p4_parent2_birth_country", "field_type": "text", "options": [], "required": False, "order": 95},
    {"section": "Part 4. Information About Your Parents", "label": "Parent 2 - City of Residence", "field_name": "p4_parent2_city", "field_type": "text", "options": [], "required": False, "order": 96},

    # PART 5: Marital History
    {"section": "Part 5. Information About Your Marital History", "label": "Current Marital Status", "field_name": "p5_marital_status", "field_type": "radio", "options": ["Single, Never Married", "Married", "Divorced", "Widowed", "Marriage Annulled", "Legally Separated"], "required": True, "order": 100},
    {"section": "Part 5. Information About Your Marital History", "label": "How many times have you been married?", "field_name": "p5_times_married", "field_type": "number", "options": [], "required": True, "order": 101},

    # Current Spouse
    {"section": "Part 5. Information About Your Marital History", "label": "Current Spouse - Family Name", "field_name": "p5_spouse_last_name", "field_type": "text", "options": [], "required": False, "order": 105},
    {"section": "Part 5. Information About Your Marital History", "label": "Current Spouse - Given Name", "field_name": "p5_spouse_first_name", "field_type": "text", "options": [], "required": False, "order": 106},
    {"section": "Part 5. Information About Your Marital History", "label": "Current Spouse - Middle Name", "field_name": "p5_spouse_middle_name", "field_type": "text", "options": [], "required": False, "order": 107},
    {"section": "Part 5. Information About Your Marital History", "label": "Current Spouse - A-Number", "field_name": "p5_spouse_a_number", "field_type": "text", "options": [], "required": False, "order": 108},
    {"section": "Part 5. Information About Your Marital History", "label": "Current Spouse - Date of Birth", "field_name": "p5_spouse_dob", "field_type": "date", "options": [], "required": False, "order": 109},
    {"section": "Part 5. Information About Your Marital History", "label": "Date of Marriage", "field_name": "p5_marriage_date", "field_type": "date", "options": [], "required": False, "order": 110},
    {"section": "Part 5. Information About Your Marital History", "label": "Place of Marriage (City and Country)", "field_name": "p5_marriage_place", "field_type": "text", "options": [], "required": False, "order": 111},
    {"section": "Part 5. Information About Your Marital History", "label": "Is your spouse applying with you?", "field_name": "p5_spouse_applying", "field_type": "radio", "options": ["Yes", "No"], "required": False, "order": 112},

    # PART 6: Information About Your Children
    {"section": "Part 6. Information About Your Children", "label": "Do you have any children?", "field_name": "p6_has_children", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 120},
    {"section": "Part 6. Information About Your Children", "label": "Total number of children", "field_name": "p6_num_children", "field_type": "number", "options": [], "required": False, "order": 121},

    # Child 1
    {"section": "Part 6. Information About Your Children", "label": "Child 1 - Family Name", "field_name": "p6_child1_last_name", "field_type": "text", "options": [], "required": False, "order": 125},
    {"section": "Part 6. Information About Your Children", "label": "Child 1 - Given Name", "field_name": "p6_child1_first_name", "field_type": "text", "options": [], "required": False, "order": 126},
    {"section": "Part 6. Information About Your Children", "label": "Child 1 - A-Number", "field_name": "p6_child1_a_number", "field_type": "text", "options": [], "required": False, "order": 127},
    {"section": "Part 6. Information About Your Children", "label": "Child 1 - Date of Birth", "field_name": "p6_child1_dob", "field_type": "date", "options": [], "required": False, "order": 128},
    {"section": "Part 6. Information About Your Children", "label": "Child 1 - Country of Birth", "field_name": "p6_child1_birth_country", "field_type": "text", "options": [], "required": False, "order": 129},
    {"section": "Part 6. Information About Your Children", "label": "Is Child 1 applying with you?", "field_name": "p6_child1_applying", "field_type": "radio", "options": ["Yes", "No"], "required": False, "order": 130},

    # Child 2
    {"section": "Part 6. Information About Your Children", "label": "Child 2 - Family Name", "field_name": "p6_child2_last_name", "field_type": "text", "options": [], "required": False, "order": 135},
    {"section": "Part 6. Information About Your Children", "label": "Child 2 - Given Name", "field_name": "p6_child2_first_name", "field_type": "text", "options": [], "required": False, "order": 136},
    {"section": "Part 6. Information About Your Children", "label": "Child 2 - A-Number", "field_name": "p6_child2_a_number", "field_type": "text", "options": [], "required": False, "order": 137},
    {"section": "Part 6. Information About Your Children", "label": "Child 2 - Date of Birth", "field_name": "p6_child2_dob", "field_type": "date", "options": [], "required": False, "order": 138},
    {"section": "Part 6. Information About Your Children", "label": "Child 2 - Country of Birth", "field_name": "p6_child2_birth_country", "field_type": "text", "options": [], "required": False, "order": 139},
    {"section": "Part 6. Information About Your Children", "label": "Is Child 2 applying with you?", "field_name": "p6_child2_applying", "field_type": "radio", "options": ["Yes", "No"], "required": False, "order": 140},

    # PART 7: Biographic Information
    {"section": "Part 7. Biographic Information", "label": "Ethnicity", "field_name": "p7_ethnicity", "field_type": "radio", "options": ["Hispanic or Latino", "Not Hispanic or Latino"], "required": True, "order": 150},
    {"section": "Part 7. Biographic Information", "label": "Race (select all that apply)", "field_name": "p7_race", "field_type": "checkbox", "options": ["White", "Asian", "Black or African American", "American Indian or Alaska Native", "Native Hawaiian or Other Pacific Islander"], "required": True, "order": 151},
    {"section": "Part 7. Biographic Information", "label": "Height (Feet)", "field_name": "p7_height_feet", "field_type": "select", "options": ["3","4","5","6","7"], "required": True, "order": 152},
    {"section": "Part 7. Biographic Information", "label": "Height (Inches)", "field_name": "p7_height_inches", "field_type": "select", "options": ["0","1","2","3","4","5","6","7","8","9","10","11"], "required": True, "order": 153},
    {"section": "Part 7. Biographic Information", "label": "Weight (Pounds)", "field_name": "p7_weight", "field_type": "number", "options": [], "required": True, "order": 154},
    {"section": "Part 7. Biographic Information", "label": "Eye Color", "field_name": "p7_eye_color", "field_type": "select", "options": ["Black", "Blue", "Brown", "Gray", "Green", "Hazel", "Maroon", "Pink", "Unknown/Other"], "required": True, "order": 155},
    {"section": "Part 7. Biographic Information", "label": "Hair Color", "field_name": "p7_hair_color", "field_type": "select", "options": ["Bald (No Hair)", "Black", "Blond", "Brown", "Gray", "Red", "Sandy", "White", "Unknown/Other"], "required": True, "order": 156},

    # PART 8: General Eligibility and Inadmissibility Grounds (KEY QUESTIONS)
    {"section": "Part 8. General Eligibility Questions", "label": "Have you EVER been arrested, cited, charged, or detained for any reason by any law enforcement official?", "field_name": "p8_arrested", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 160},
    {"section": "Part 8. General Eligibility Questions", "label": "Have you EVER been convicted of a crime in the U.S. or any other country?", "field_name": "p8_convicted", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 161},
    {"section": "Part 8. General Eligibility Questions", "label": "Have you EVER been a member of or affiliated with the Communist Party?", "field_name": "p8_communist", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 162},
    {"section": "Part 8. General Eligibility Questions", "label": "Have you EVER been a member of or affiliated with a terrorist organization?", "field_name": "p8_terrorist", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 163},
    {"section": "Part 8. General Eligibility Questions", "label": "Have you EVER engaged in, ordered, or assisted in persecution of any person?", "field_name": "p8_persecution", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 164},
    {"section": "Part 8. General Eligibility Questions", "label": "Have you EVER participated in genocide, torture, or killing?", "field_name": "p8_genocide", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 165},
    {"section": "Part 8. General Eligibility Questions", "label": "Have you EVER been removed, excluded, or deported from the U.S.?", "field_name": "p8_removed", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 166},
    {"section": "Part 8. General Eligibility Questions", "label": "Have you EVER illegally entered or attempted to enter the U.S.?", "field_name": "p8_illegal_entry", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 167},
    {"section": "Part 8. General Eligibility Questions", "label": "Have you EVER been a J-1 or J-2 exchange visitor subject to the 2-year foreign residence requirement?", "field_name": "p8_j_visa", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 168},
    {"section": "Part 8. General Eligibility Questions", "label": "Are you currently in lawful nonimmigrant status?", "field_name": "p8_lawful_status", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 169},
    {"section": "Part 8. General Eligibility Questions", "label": "Since becoming a nonimmigrant, have you worked without authorization?", "field_name": "p8_unauthorized_work", "field_type": "radio", "options": ["Yes", "No", "N/A"], "required": True, "order": 170},
    {"section": "Part 8. General Eligibility Questions", "label": "Have you EVER voted in violation of any federal, state, or local law?", "field_name": "p8_voted", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 171},

    # PART 10: Applicant's Statement
    {"section": "Part 10. Applicant's Statement", "label": "Can you read and understand English?", "field_name": "p10_read_english", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 180},
    {"section": "Part 10. Applicant's Statement", "label": "Language used by interpreter", "field_name": "p10_interpreter_language", "field_type": "text", "options": [], "required": False, "order": 181},
    {"section": "Part 10. Applicant's Statement", "label": "Daytime Telephone Number", "field_name": "p10_phone", "field_type": "phone", "options": [], "required": True, "order": 182},
    {"section": "Part 10. Applicant's Statement", "label": "Mobile Telephone Number", "field_name": "p10_mobile", "field_type": "phone", "options": [], "required": False, "order": 183},
    {"section": "Part 10. Applicant's Statement", "label": "Email Address", "field_name": "p10_email", "field_type": "email", "options": [], "required": False, "order": 184},
]

# ============================================================================
# FORM I-864 - Affidavit of Support
# ============================================================================
I864_FIELDS = [
    # PART 1: Basis for Filing
    {"section": "Part 1. Basis for Filing", "label": "I am the petitioner who filed or is filing the I-130", "field_name": "p1_basis_petitioner", "field_type": "checkbox", "options": [], "required": False, "order": 1},
    {"section": "Part 1. Basis for Filing", "label": "I am the first joint sponsor", "field_name": "p1_basis_joint_sponsor_1", "field_type": "checkbox", "options": [], "required": False, "order": 2},
    {"section": "Part 1. Basis for Filing", "label": "I am the second joint sponsor", "field_name": "p1_basis_joint_sponsor_2", "field_type": "checkbox", "options": [], "required": False, "order": 3},
    {"section": "Part 1. Basis for Filing", "label": "I am a household member", "field_name": "p1_basis_household_member", "field_type": "checkbox", "options": [], "required": False, "order": 4},

    # PART 2: Information About Principal Immigrant
    {"section": "Part 2. Information About Principal Immigrant", "label": "Family Name (Last Name)", "field_name": "p2_immigrant_last_name", "field_type": "text", "options": [], "required": True, "order": 10},
    {"section": "Part 2. Information About Principal Immigrant", "label": "Given Name (First Name)", "field_name": "p2_immigrant_first_name", "field_type": "text", "options": [], "required": True, "order": 11},
    {"section": "Part 2. Information About Principal Immigrant", "label": "Middle Name", "field_name": "p2_immigrant_middle_name", "field_type": "text", "options": [], "required": False, "order": 12},
    {"section": "Part 2. Information About Principal Immigrant", "label": "Alien Registration Number (A-Number)", "field_name": "p2_immigrant_a_number", "field_type": "text", "options": [], "required": False, "order": 13},
    {"section": "Part 2. Information About Principal Immigrant", "label": "Date of Birth", "field_name": "p2_immigrant_dob", "field_type": "date", "options": [], "required": True, "order": 14},
    {"section": "Part 2. Information About Principal Immigrant", "label": "Relationship to Sponsor", "field_name": "p2_immigrant_relationship", "field_type": "radio", "options": ["Spouse", "Parent", "Child", "Brother/Sister", "Other"], "required": True, "order": 15},

    # PART 3: Information About Immigrants You Are Sponsoring
    {"section": "Part 3. Immigrants You Are Sponsoring", "label": "List all other immigrants in same case (Full Name)", "field_name": "p3_other_immigrants", "field_type": "textarea", "options": [], "required": False, "order": 20, "help_text": "List each immigrant's full name and relationship, one per line"},

    # PART 4: Information About Sponsor
    {"section": "Part 4. Information About Sponsor", "label": "Family Name (Last Name)", "field_name": "p4_sponsor_last_name", "field_type": "text", "options": [], "required": True, "order": 30},
    {"section": "Part 4. Information About Sponsor", "label": "Given Name (First Name)", "field_name": "p4_sponsor_first_name", "field_type": "text", "options": [], "required": True, "order": 31},
    {"section": "Part 4. Information About Sponsor", "label": "Middle Name", "field_name": "p4_sponsor_middle_name", "field_type": "text", "options": [], "required": False, "order": 32},
    {"section": "Part 4. Information About Sponsor", "label": "Mailing Address - Street Number and Name", "field_name": "p4_sponsor_street", "field_type": "text", "options": [], "required": True, "order": 33},
    {"section": "Part 4. Information About Sponsor", "label": "Mailing Address - City", "field_name": "p4_sponsor_city", "field_type": "text", "options": [], "required": True, "order": 34},
    {"section": "Part 4. Information About Sponsor", "label": "Mailing Address - State", "field_name": "p4_sponsor_state", "field_type": "select", "options": ["AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC"], "required": True, "order": 35},
    {"section": "Part 4. Information About Sponsor", "label": "Mailing Address - ZIP Code", "field_name": "p4_sponsor_zip", "field_type": "text", "options": [], "required": True, "order": 36},
    {"section": "Part 4. Information About Sponsor", "label": "Telephone Number", "field_name": "p4_sponsor_phone", "field_type": "phone", "options": [], "required": True, "order": 37},
    {"section": "Part 4. Information About Sponsor", "label": "Email Address", "field_name": "p4_sponsor_email", "field_type": "email", "options": [], "required": False, "order": 38},
    {"section": "Part 4. Information About Sponsor", "label": "Date of Birth", "field_name": "p4_sponsor_dob", "field_type": "date", "options": [], "required": True, "order": 39},
    {"section": "Part 4. Information About Sponsor", "label": "Place of Birth (City and Country)", "field_name": "p4_sponsor_birth_place", "field_type": "text", "options": [], "required": True, "order": 40},
    {"section": "Part 4. Information About Sponsor", "label": "U.S. Social Security Number", "field_name": "p4_sponsor_ssn", "field_type": "text", "options": [], "required": True, "order": 41},
    {"section": "Part 4. Information About Sponsor", "label": "I am a:", "field_name": "p4_sponsor_status", "field_type": "radio", "options": ["U.S. Citizen", "U.S. National", "U.S. Lawful Permanent Resident"], "required": True, "order": 42},

    # PART 5: Sponsor's Household Size
    {"section": "Part 5. Sponsor's Household Size", "label": "Number of persons in your household (including yourself)", "field_name": "p5_household_total", "field_type": "number", "options": [], "required": True, "order": 50},
    {"section": "Part 5. Sponsor's Household Size", "label": "Number of immigrants you are sponsoring in this affidavit", "field_name": "p5_sponsored_count", "field_type": "number", "options": [], "required": True, "order": 51},
    {"section": "Part 5. Sponsor's Household Size", "label": "Number of dependents (children under 21)", "field_name": "p5_dependents", "field_type": "number", "options": [], "required": True, "order": 52},
    {"section": "Part 5. Sponsor's Household Size", "label": "Number of other persons you're obligated to support", "field_name": "p5_other_dependents", "field_type": "number", "options": [], "required": True, "order": 53},
    {"section": "Part 5. Sponsor's Household Size", "label": "Total household size for this sponsorship", "field_name": "p5_total_household_size", "field_type": "number", "options": [], "required": True, "order": 54},

    # PART 6: Sponsor's Employment and Income
    {"section": "Part 6. Sponsor's Employment and Income", "label": "I am currently:", "field_name": "p6_employment_status", "field_type": "radio", "options": ["Employed as an employee", "Self-employed", "Retired", "Unemployed"], "required": True, "order": 60},
    {"section": "Part 6. Sponsor's Employment and Income", "label": "Employer Name (or self-employed business name)", "field_name": "p6_employer_name", "field_type": "text", "options": [], "required": False, "order": 61},
    {"section": "Part 6. Sponsor's Employment and Income", "label": "Employer Address", "field_name": "p6_employer_address", "field_type": "text", "options": [], "required": False, "order": 62},
    {"section": "Part 6. Sponsor's Employment and Income", "label": "Occupation", "field_name": "p6_occupation", "field_type": "text", "options": [], "required": False, "order": 63},
    {"section": "Part 6. Sponsor's Employment and Income", "label": "Date employment began", "field_name": "p6_employment_date", "field_type": "date", "options": [], "required": False, "order": 64},
    {"section": "Part 6. Sponsor's Employment and Income", "label": "My current individual annual income is:", "field_name": "p6_annual_income", "field_type": "number", "options": [], "required": True, "order": 65, "help_text": "Enter amount in US dollars"},
    {"section": "Part 6. Sponsor's Employment and Income", "label": "My total household income (including household members)", "field_name": "p6_household_income", "field_type": "number", "options": [], "required": False, "order": 66},
    {"section": "Part 6. Sponsor's Employment and Income", "label": "Federal income tax return information - I filed a federal tax return for the most recent tax year", "field_name": "p6_filed_taxes", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 67},
    {"section": "Part 6. Sponsor's Employment and Income", "label": "Tax year", "field_name": "p6_tax_year", "field_type": "text", "options": [], "required": False, "order": 68},
    {"section": "Part 6. Sponsor's Employment and Income", "label": "Total income shown on tax return", "field_name": "p6_tax_income", "field_type": "number", "options": [], "required": False, "order": 69},

    # PART 7: Assets
    {"section": "Part 7. Use of Assets to Supplement Income", "label": "Do you have assets to supplement income?", "field_name": "p7_has_assets", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 70},
    {"section": "Part 7. Use of Assets to Supplement Income", "label": "Total value of cash/savings", "field_name": "p7_cash_value", "field_type": "number", "options": [], "required": False, "order": 71},
    {"section": "Part 7. Use of Assets to Supplement Income", "label": "Total value of stocks/bonds", "field_name": "p7_stocks_value", "field_type": "number", "options": [], "required": False, "order": 72},
    {"section": "Part 7. Use of Assets to Supplement Income", "label": "Total value of real estate", "field_name": "p7_real_estate_value", "field_type": "number", "options": [], "required": False, "order": 73},
    {"section": "Part 7. Use of Assets to Supplement Income", "label": "Total value of other assets", "field_name": "p7_other_assets_value", "field_type": "number", "options": [], "required": False, "order": 74},
    {"section": "Part 7. Use of Assets to Supplement Income", "label": "Total value of all assets", "field_name": "p7_total_assets", "field_type": "number", "options": [], "required": False, "order": 75},

    # PART 8: Sponsor's Contract
    {"section": "Part 8. Sponsor's Contract", "label": "I understand my obligations as a sponsor", "field_name": "p8_understand_obligations", "field_type": "checkbox", "options": [], "required": True, "order": 80},
    {"section": "Part 8. Sponsor's Contract", "label": "Daytime Telephone Number", "field_name": "p8_phone", "field_type": "phone", "options": [], "required": True, "order": 81},
    {"section": "Part 8. Sponsor's Contract", "label": "Mobile Telephone Number", "field_name": "p8_mobile", "field_type": "phone", "options": [], "required": False, "order": 82},
    {"section": "Part 8. Sponsor's Contract", "label": "Email Address", "field_name": "p8_email", "field_type": "email", "options": [], "required": False, "order": 83},
]

# ============================================================================
# FORM I-765 - Application for Employment Authorization
# ============================================================================
I765_FIELDS = [
    # PART 1: Reason for Applying
    {"section": "Part 1. Reason for Applying", "label": "I am applying for:", "field_name": "p1_reason", "field_type": "radio", "options": ["Initial permission to accept employment", "Replacement of lost, stolen, or damaged EAD", "Renewal of my permission to accept employment"], "required": True, "order": 1},

    # PART 2: Information About You
    {"section": "Part 2. Information About You", "label": "Alien Registration Number (A-Number)", "field_name": "p2_a_number", "field_type": "text", "options": [], "required": False, "order": 10},
    {"section": "Part 2. Information About You", "label": "USCIS Online Account Number", "field_name": "p2_uscis_account", "field_type": "text", "options": [], "required": False, "order": 11},
    {"section": "Part 2. Information About You", "label": "Family Name (Last Name)", "field_name": "p2_last_name", "field_type": "text", "options": [], "required": True, "order": 12},
    {"section": "Part 2. Information About You", "label": "Given Name (First Name)", "field_name": "p2_first_name", "field_type": "text", "options": [], "required": True, "order": 13},
    {"section": "Part 2. Information About You", "label": "Middle Name", "field_name": "p2_middle_name", "field_type": "text", "options": [], "required": False, "order": 14},

    # Other Names
    {"section": "Part 2. Information About You", "label": "Other Names Used - Family Name", "field_name": "p2_other_last_name", "field_type": "text", "options": [], "required": False, "order": 15},
    {"section": "Part 2. Information About You", "label": "Other Names Used - Given Name", "field_name": "p2_other_first_name", "field_type": "text", "options": [], "required": False, "order": 16},

    # Address
    {"section": "Part 2. Information About You", "label": "U.S. Mailing Address - Street Number and Name", "field_name": "p2_street", "field_type": "text", "options": [], "required": True, "order": 20},
    {"section": "Part 2. Information About You", "label": "Apt/Ste/Flr", "field_name": "p2_apt_type", "field_type": "select", "options": ["Apt", "Ste", "Flr"], "required": False, "order": 21},
    {"section": "Part 2. Information About You", "label": "Apt/Ste/Flr Number", "field_name": "p2_apt_number", "field_type": "text", "options": [], "required": False, "order": 22},
    {"section": "Part 2. Information About You", "label": "City or Town", "field_name": "p2_city", "field_type": "text", "options": [], "required": True, "order": 23},
    {"section": "Part 2. Information About You", "label": "State", "field_name": "p2_state", "field_type": "select", "options": ["AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC","PR","VI","GU","AS","MP"], "required": True, "order": 24},
    {"section": "Part 2. Information About You", "label": "ZIP Code", "field_name": "p2_zip", "field_type": "text", "options": [], "required": True, "order": 25},

    # Personal Info
    {"section": "Part 2. Information About You", "label": "Date of Birth", "field_name": "p2_dob", "field_type": "date", "options": [], "required": True, "order": 30},
    {"section": "Part 2. Information About You", "label": "Country of Birth", "field_name": "p2_birth_country", "field_type": "text", "options": [], "required": True, "order": 31},
    {"section": "Part 2. Information About You", "label": "Country of Citizenship or Nationality", "field_name": "p2_citizenship", "field_type": "text", "options": [], "required": True, "order": 32},
    {"section": "Part 2. Information About You", "label": "U.S. Social Security Number", "field_name": "p2_ssn", "field_type": "text", "options": [], "required": False, "order": 33},
    {"section": "Part 2. Information About You", "label": "Sex", "field_name": "p2_sex", "field_type": "radio", "options": ["Male", "Female"], "required": True, "order": 34},
    {"section": "Part 2. Information About You", "label": "Marital Status", "field_name": "p2_marital_status", "field_type": "radio", "options": ["Single", "Married", "Divorced", "Widowed"], "required": True, "order": 35},

    # Immigration Info
    {"section": "Part 2. Information About You", "label": "Date of Last Arrival into the U.S.", "field_name": "p2_last_arrival_date", "field_type": "date", "options": [], "required": True, "order": 40},
    {"section": "Part 2. Information About You", "label": "Place of Last Arrival", "field_name": "p2_last_arrival_place", "field_type": "text", "options": [], "required": True, "order": 41},
    {"section": "Part 2. Information About You", "label": "I-94 Arrival-Departure Record Number", "field_name": "p2_i94_number", "field_type": "text", "options": [], "required": False, "order": 42},
    {"section": "Part 2. Information About You", "label": "Current Immigration Status", "field_name": "p2_current_status", "field_type": "text", "options": [], "required": True, "order": 43, "help_text": "e.g., B-2, F-1, pending I-485"},
    {"section": "Part 2. Information About You", "label": "EAD Eligibility Category", "field_name": "p2_eligibility_category", "field_type": "text", "options": [], "required": True, "order": 44, "help_text": "e.g., (c)(9) for pending I-485"},
    {"section": "Part 2. Information About You", "label": "SEVIS Number (if applicable)", "field_name": "p2_sevis", "field_type": "text", "options": [], "required": False, "order": 45},

    # PART 3: Applicant's Statement
    {"section": "Part 3. Applicant's Statement", "label": "Can you read and understand English?", "field_name": "p3_read_english", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 50},
    {"section": "Part 3. Applicant's Statement", "label": "Language used by interpreter", "field_name": "p3_interpreter_language", "field_type": "text", "options": [], "required": False, "order": 51},
    {"section": "Part 3. Applicant's Statement", "label": "Daytime Telephone Number", "field_name": "p3_phone", "field_type": "phone", "options": [], "required": True, "order": 52},
    {"section": "Part 3. Applicant's Statement", "label": "Mobile Telephone Number", "field_name": "p3_mobile", "field_type": "phone", "options": [], "required": False, "order": 53},
    {"section": "Part 3. Applicant's Statement", "label": "Email Address", "field_name": "p3_email", "field_type": "email", "options": [], "required": False, "order": 54},
]

# ============================================================================
# FORM I-131 - Application for Travel Document
# ============================================================================
I131_FIELDS = [
    # PART 1: Application Type
    {"section": "Part 1. Application Type", "label": "I am applying for:", "field_name": "p1_application_type", "field_type": "radio", "options": ["Reentry Permit", "Refugee Travel Document", "Advance Parole Document", "Parole into the United States"], "required": True, "order": 1},

    # PART 2: Information About You
    {"section": "Part 2. Information About You", "label": "Alien Registration Number (A-Number)", "field_name": "p2_a_number", "field_type": "text", "options": [], "required": False, "order": 10},
    {"section": "Part 2. Information About You", "label": "USCIS Online Account Number", "field_name": "p2_uscis_account", "field_type": "text", "options": [], "required": False, "order": 11},
    {"section": "Part 2. Information About You", "label": "Family Name (Last Name)", "field_name": "p2_last_name", "field_type": "text", "options": [], "required": True, "order": 12},
    {"section": "Part 2. Information About You", "label": "Given Name (First Name)", "field_name": "p2_first_name", "field_type": "text", "options": [], "required": True, "order": 13},
    {"section": "Part 2. Information About You", "label": "Middle Name", "field_name": "p2_middle_name", "field_type": "text", "options": [], "required": False, "order": 14},

    # Address
    {"section": "Part 2. Information About You", "label": "U.S. Mailing Address - Street Number and Name", "field_name": "p2_street", "field_type": "text", "options": [], "required": True, "order": 20},
    {"section": "Part 2. Information About You", "label": "Apt/Ste/Flr", "field_name": "p2_apt_type", "field_type": "select", "options": ["Apt", "Ste", "Flr"], "required": False, "order": 21},
    {"section": "Part 2. Information About You", "label": "Apt/Ste/Flr Number", "field_name": "p2_apt_number", "field_type": "text", "options": [], "required": False, "order": 22},
    {"section": "Part 2. Information About You", "label": "City or Town", "field_name": "p2_city", "field_type": "text", "options": [], "required": True, "order": 23},
    {"section": "Part 2. Information About You", "label": "State", "field_name": "p2_state", "field_type": "select", "options": ["AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC","PR","VI","GU","AS","MP"], "required": True, "order": 24},
    {"section": "Part 2. Information About You", "label": "ZIP Code", "field_name": "p2_zip", "field_type": "text", "options": [], "required": True, "order": 25},

    # Personal Info
    {"section": "Part 2. Information About You", "label": "Date of Birth", "field_name": "p2_dob", "field_type": "date", "options": [], "required": True, "order": 30},
    {"section": "Part 2. Information About You", "label": "Country of Birth", "field_name": "p2_birth_country", "field_type": "text", "options": [], "required": True, "order": 31},
    {"section": "Part 2. Information About You", "label": "Country of Citizenship or Nationality", "field_name": "p2_citizenship", "field_type": "text", "options": [], "required": True, "order": 32},
    {"section": "Part 2. Information About You", "label": "Sex", "field_name": "p2_sex", "field_type": "radio", "options": ["Male", "Female"], "required": True, "order": 33},
    {"section": "Part 2. Information About You", "label": "Class of Admission", "field_name": "p2_class_admission", "field_type": "text", "options": [], "required": True, "order": 34, "help_text": "e.g., LPR, Asylee, Refugee, pending I-485"},
    {"section": "Part 2. Information About You", "label": "Date of Admission", "field_name": "p2_admission_date", "field_type": "date", "options": [], "required": False, "order": 35},

    # PART 3: Biographic Information
    {"section": "Part 3. Biographic Information", "label": "Ethnicity", "field_name": "p3_ethnicity", "field_type": "radio", "options": ["Hispanic or Latino", "Not Hispanic or Latino"], "required": True, "order": 40},
    {"section": "Part 3. Biographic Information", "label": "Race (select all that apply)", "field_name": "p3_race", "field_type": "checkbox", "options": ["White", "Asian", "Black or African American", "American Indian or Alaska Native", "Native Hawaiian or Other Pacific Islander"], "required": True, "order": 41},
    {"section": "Part 3. Biographic Information", "label": "Height (Feet)", "field_name": "p3_height_feet", "field_type": "select", "options": ["3","4","5","6","7"], "required": True, "order": 42},
    {"section": "Part 3. Biographic Information", "label": "Height (Inches)", "field_name": "p3_height_inches", "field_type": "select", "options": ["0","1","2","3","4","5","6","7","8","9","10","11"], "required": True, "order": 43},
    {"section": "Part 3. Biographic Information", "label": "Weight (Pounds)", "field_name": "p3_weight", "field_type": "number", "options": [], "required": True, "order": 44},
    {"section": "Part 3. Biographic Information", "label": "Eye Color", "field_name": "p3_eye_color", "field_type": "select", "options": ["Black", "Blue", "Brown", "Gray", "Green", "Hazel", "Maroon", "Pink", "Unknown/Other"], "required": True, "order": 45},
    {"section": "Part 3. Biographic Information", "label": "Hair Color", "field_name": "p3_hair_color", "field_type": "select", "options": ["Bald (No Hair)", "Black", "Blond", "Brown", "Gray", "Red", "Sandy", "White", "Unknown/Other"], "required": True, "order": 46},

    # PART 7: Information About Proposed Travel (for Advance Parole)
    {"section": "Part 7. Information About Proposed Travel", "label": "Purpose of Trip", "field_name": "p7_purpose", "field_type": "textarea", "options": [], "required": True, "order": 50, "help_text": "Explain the purpose of your proposed travel"},
    {"section": "Part 7. Information About Proposed Travel", "label": "Countries to be Visited", "field_name": "p7_countries", "field_type": "text", "options": [], "required": True, "order": 51},
    {"section": "Part 7. Information About Proposed Travel", "label": "Intended Departure Date", "field_name": "p7_departure_date", "field_type": "date", "options": [], "required": True, "order": 52},
    {"section": "Part 7. Information About Proposed Travel", "label": "Expected Length of Trip", "field_name": "p7_trip_length", "field_type": "text", "options": [], "required": True, "order": 53, "help_text": "e.g., 2 weeks, 1 month"},
    {"section": "Part 7. Information About Proposed Travel", "label": "Number of Trips", "field_name": "p7_num_trips", "field_type": "radio", "options": ["One trip", "More than one trip"], "required": True, "order": 54},

    # PART 10: Applicant's Statement
    {"section": "Part 10. Applicant's Statement", "label": "Can you read and understand English?", "field_name": "p10_read_english", "field_type": "radio", "options": ["Yes", "No"], "required": True, "order": 60},
    {"section": "Part 10. Applicant's Statement", "label": "Language used by interpreter", "field_name": "p10_interpreter_language", "field_type": "text", "options": [], "required": False, "order": 61},
    {"section": "Part 10. Applicant's Statement", "label": "Daytime Telephone Number", "field_name": "p10_phone", "field_type": "phone", "options": [], "required": True, "order": 62},
    {"section": "Part 10. Applicant's Statement", "label": "Mobile Telephone Number", "field_name": "p10_mobile", "field_type": "phone", "options": [], "required": False, "order": 63},
    {"section": "Part 10. Applicant's Statement", "label": "Email Address", "field_name": "p10_email", "field_type": "email", "options": [], "required": False, "order": 64},
]


def create_template(cursor, name, description, category, fields, is_required=False):
    """Create a questionnaire template with fields"""
    import json

    # Create template
    cursor.execute("""
        INSERT INTO questionnaire_templates (name, description, category, target_type, is_active, is_required, created_at, updated_at)
        VALUES (%s, %s, %s, 'case', true, %s, NOW(), NOW())
        RETURNING id
    """, (name, description, category, is_required))

    template_id = cursor.fetchone()[0]
    print(f"Created template: {name} (ID: {template_id}) with {len(fields)} fields")

    # Create fields
    for field in fields:
        options_json = json.dumps(field.get("options", []))
        help_text = field.get("help_text", "")

        cursor.execute("""
            INSERT INTO questionnaire_fields
            (template_id, section, label, field_name, field_type, options, is_required, "order", description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            template_id,
            field["section"],
            field["label"],
            field["field_name"],
            field["field_type"],
            options_json,
            field["required"],
            field["order"],
            help_text
        ))

    return template_id


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    try:
        # Create all templates
        templates = [
            ("Form I-130 - Petition for Alien Relative",
             "Use this form to petition for an alien relative to become a lawful permanent resident.",
             "USCIS Family-Based", I130_FIELDS, True),

            ("Form I-130A - Supplemental Information for Spouse Beneficiary",
             "Supplemental form for spouse beneficiaries providing additional information.",
             "USCIS Family-Based", I130A_FIELDS, True),

            ("Form I-485 - Application to Register Permanent Residence",
             "Use this form to apply for lawful permanent resident status (Green Card).",
             "USCIS Adjustment of Status", I485_FIELDS, True),

            ("Form I-864 - Affidavit of Support",
             "Affidavit of Support required for most family-based immigrants.",
             "USCIS Family-Based", I864_FIELDS, True),

            ("Form I-765 - Application for Employment Authorization",
             "Application for Employment Authorization Document (EAD/Work Permit).",
             "USCIS Employment", I765_FIELDS, False),

            ("Form I-131 - Application for Travel Document",
             "Application for Advance Parole or Re-entry Permit.",
             "USCIS Travel", I131_FIELDS, False),
        ]

        template_ids = []
        for name, desc, category, fields, is_required in templates:
            template_id = create_template(cursor, name, desc, category, fields, is_required)
            template_ids.append(template_id)

        conn.commit()
        print(f"\nSuccessfully created {len(templates)} templates")
        print(f"Template IDs: {template_ids}")

        # Count total fields
        cursor.execute("SELECT COUNT(*) FROM questionnaire_fields WHERE template_id IN %s", (tuple(template_ids),))
        total_fields = cursor.fetchone()[0]
        print(f"Total fields created: {total_fields}")

    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
