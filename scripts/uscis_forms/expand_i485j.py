#!/usr/bin/env python3
"""
Expand I-485J (Confirmation of Bona Fide Job Offer or Request for Job Portability
Under INA Section 204(j)). Supplement to I-485 for employment-based adjustment.
3 pages, Parts 1-5.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I485J_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT THE APPLICANT
    # =========================================================================
    ("1A. Applicant Name", "p1_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("1A. Applicant Name", "p1_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("1A. Applicant Name", "p1_1c_middle_name", "1.c. Middle Name", "text", False),
    ("1A. Applicant IDs", "p1_2_a_number", "2. Alien Registration Number (A-Number)", "text", False),
    ("1A. Applicant IDs", "p1_3_uscis_account", "3. USCIS Online Account Number (if any)", "text", False),
    ("1A. Applicant IDs", "p1_4_dob", "4. Date of Birth (mm/dd/yyyy)", "date", True),
    ("1A. Applicant IDs", "p1_5_country_birth", "5. Country of Birth", "text", True),
    ("1A. Applicant IDs", "p1_6_country_citizenship", "6. Country of Citizenship or Nationality", "text", True),

    # Mailing Address
    ("1B. Mailing Address", "p1_7a_street", "7.a. Street Number and Name", "text", True),
    ("1B. Mailing Address", "p1_7b_apt_type", "7.b. Apt/Ste/Flr Type", "select", False),
    ("1B. Mailing Address", "p1_7c_apt_number", "7.c. Apt/Ste/Flr Number", "text", False),
    ("1B. Mailing Address", "p1_7d_city", "7.d. City or Town", "text", True),
    ("1B. Mailing Address", "p1_7e_state", "7.e. State", "select", True),
    ("1B. Mailing Address", "p1_7f_zip", "7.f. ZIP Code", "text", True),

    # Contact
    ("1C. Contact", "p1_8_phone", "8. Daytime Telephone Number", "phone", False),
    ("1C. Contact", "p1_9_email", "9. Email Address (if any)", "email", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT THE I-485 APPLICATION
    # =========================================================================
    ("2A. I-485 Info", "p2_1_i485_receipt", "1. I-485 Receipt Number", "text", True),
    ("2A. I-485 Info", "p2_2_i485_filing_date", "2. Date I-485 Filed (mm/dd/yyyy)", "date", True),
    ("2A. I-485 Info", "p2_3_i140_receipt", "3. I-140 Receipt Number", "text", True),
    ("2A. I-485 Info", "p2_4_i140_approval_date", "4. I-140 Approval Date (mm/dd/yyyy)", "date", False),
    ("2A. I-485 Info", "p2_5_priority_date", "5. Priority Date (mm/dd/yyyy)", "date", True),
    ("2A. I-485 Info", "p2_6_preference_category", "6. Employment-Based Preference Category", "select", True),
    ("2A. I-485 Info", "p2_7_labor_cert_number", "7. DOL Labor Certification/ETA Case Number (if applicable)", "text", False),

    # =========================================================================
    # PART 3: INFORMATION ABOUT THE JOB OFFER
    # =========================================================================
    ("3A. Current Employer", "p3_1_employer_name", "1. Employer/Company Name", "text", True),
    ("3A. Current Employer", "p3_2_ein", "2. IRS Employer Identification Number (EIN)", "text", False),
    ("3A. Current Employer", "p3_3a_emp_street", "3.a. Employer Street Number and Name", "text", True),
    ("3A. Current Employer", "p3_3b_emp_apt", "3.b. Apt/Ste/Flr Number", "text", False),
    ("3A. Current Employer", "p3_3c_emp_city", "3.c. City or Town", "text", True),
    ("3A. Current Employer", "p3_3d_emp_state", "3.d. State", "select", True),
    ("3A. Current Employer", "p3_3e_emp_zip", "3.e. ZIP Code", "text", True),

    ("3B. Job Details", "p3_4_job_title", "4. Job Title", "text", True),
    ("3B. Job Details", "p3_5_soc_code", "5. SOC Code (Standard Occupational Classification)", "text", False),
    ("3B. Job Details", "p3_6_job_description", "6. Job Description", "textarea", True),
    ("3B. Job Details", "p3_7_full_time", "7. Is this a full-time position?", "radio", True),
    ("3B. Job Details", "p3_8_permanent", "8. Is this a permanent position?", "radio", True),
    ("3B. Job Details", "p3_9_wages", "9. Offered Wage ($)", "text", True),
    ("3B. Job Details", "p3_9_wage_period", "9. Per (Hour/Week/Month/Year)", "select", True),

    ("3C. Portability", "p3_10_same_employer", "10. Is this the same employer from the I-140?", "radio", True),
    ("3C. Portability", "p3_11_same_occupation", "11. Is this the same or similar occupational classification?", "radio", True),
    ("3C. Portability", "p3_12_portability_explain", "12. If requesting portability, explain how new job is same or similar", "textarea", False),

    # Worksite
    ("3D. Worksite", "p3_13a_worksite_street", "13.a. Principal Worksite - Street Number and Name", "text", False),
    ("3D. Worksite", "p3_13b_worksite_city", "13.b. City or Town", "text", False),
    ("3D. Worksite", "p3_13c_worksite_state", "13.c. State", "select", False),
    ("3D. Worksite", "p3_13d_worksite_zip", "13.d. ZIP Code", "text", False),

    # =========================================================================
    # PART 4: EMPLOYER'S CERTIFICATION
    # =========================================================================
    ("4. Employer Certification", "p4_1_certify_bona_fide", "1. I certify this is a bona fide job offer", "checkbox", True),
    ("4. Employer Certification", "p4_2_certify_ability_pay", "2. I certify the employer has ability to pay the offered wage", "checkbox", True),
    ("4. Employer Certification", "p4_3a_auth_family", "3.a. Authorized Representative - Family Name", "text", True),
    ("4. Employer Certification", "p4_3b_auth_given", "3.b. Authorized Representative - Given Name", "text", True),
    ("4. Employer Certification", "p4_4_auth_title", "4. Title of Authorized Representative", "text", True),
    ("4. Employer Certification", "p4_5_auth_phone", "5. Daytime Telephone Number", "phone", True),
    ("4. Employer Certification", "p4_6_auth_email", "6. Email Address", "email", False),
    ("4. Employer Certification", "p4_signature_date", "Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 5: ADDITIONAL INFORMATION
    # =========================================================================
    ("5. Additional Information", "p5_1a_page_1", "1.a. Page Number", "text", False),
    ("5. Additional Information", "p5_1b_part_1", "1.b. Part Number", "text", False),
    ("5. Additional Information", "p5_1c_item_1", "1.c. Item Number", "text", False),
    ("5. Additional Information", "p5_1d_info_1", "1.d. Additional Information", "textarea", False),
    ("5. Additional Information", "p5_2a_page_2", "2.a. Page Number", "text", False),
    ("5. Additional Information", "p5_2b_part_2", "2.b. Part Number", "text", False),
    ("5. Additional Information", "p5_2c_item_2", "2.c. Item Number", "text", False),
    ("5. Additional Information", "p5_2d_info_2", "2.d. Additional Information", "textarea", False),
]

# Total: 65+ fields

if __name__ == "__main__":
    print(f"I-485J fields defined: {len(I485J_FIELDS)}")
