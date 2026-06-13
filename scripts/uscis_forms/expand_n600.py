#!/usr/bin/env python3
"""
Expand N-600 (Application for Certificate of Citizenship) with ALL official USCIS fields.
Edition 02/04/19 - 11 pages, Parts 1-11.
Used by persons who acquired or derived U.S. citizenship through their parents.
"""
import json
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

N600_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT YOUR ELIGIBILITY (Page 1)
    # =========================================================================
    ("Part 1. Information About Your Eligibility", "p1_1_basis", "1. I am claiming U.S. citizenship through (select one)", "select", True),
    ("Part 1. Information About Your Eligibility", "p1_2_born_in_us", "2. Were you born in the United States?", "select", True),
    ("Part 1. Information About Your Eligibility", "p1_3_born_abroad", "3. Were you born abroad to at least one U.S. citizen parent?", "select", False),
    ("Part 1. Information About Your Eligibility", "p1_4_adopted", "4. Were you adopted by a U.S. citizen parent?", "select", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT YOU (THE APPLICANT) (Pages 1-3)
    # =========================================================================
    ("Part 2. Information About You", "p2_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("Part 2. Information About You", "p2_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("Part 2. Information About You", "p2_1c_middle_name", "1.c. Middle Name", "text", False),
    ("Part 2. Other Names Used", "p2_2a_family_name", "2.a. Other Family Names Used (if any)", "text", False),
    ("Part 2. Other Names Used", "p2_2b_given_name", "2.b. Other Given Names Used (if any)", "text", False),
    ("Part 2. Other Names Used", "p2_2c_middle_name", "2.c. Other Middle Names Used (if any)", "text", False),
    ("Part 2. Information About You", "p2_3_dob", "3. Date of Birth (mm/dd/yyyy)", "date", True),
    ("Part 2. Information About You", "p2_4_gender_male", "4. Gender - Male", "radio", False),
    ("Part 2. Information About You", "p2_4_gender_female", "4. Gender - Female", "radio", False),
    ("Part 2. Information About You", "p2_5_city_of_birth", "5. City/Town/Village of Birth", "text", True),
    ("Part 2. Information About You", "p2_6_state_of_birth", "6. State/Province of Birth", "text", False),
    ("Part 2. Information About You", "p2_7_country_of_birth", "7. Country of Birth", "text", True),
    ("Part 2. Information About You", "p2_8_country_of_citizenship", "8. Country of Citizenship or Nationality", "text", True),
    ("Part 2. Information About You", "p2_9_a_number", "9. Alien Registration Number (A-Number) (if any)", "text", False),
    ("Part 2. Information About You", "p2_10_uscis_account", "10. USCIS Online Account Number (if any)", "text", False),
    ("Part 2. Information About You", "p2_11_ssn", "11. U.S. Social Security Number (if any)", "text", False),

    # Mailing Address
    ("Part 2. Mailing Address", "p2_12a_in_care_of", "12.a. In Care Of Name (if any)", "text", False),
    ("Part 2. Mailing Address", "p2_12b_street", "12.b. Street Number and Name", "text", True),
    ("Part 2. Mailing Address", "p2_12c_apt_type", "12.c. Apt./Ste./Flr.", "select", False),
    ("Part 2. Mailing Address", "p2_12c_apt_number", "12.c. Number", "text", False),
    ("Part 2. Mailing Address", "p2_12d_city", "12.d. City or Town", "text", True),
    ("Part 2. Mailing Address", "p2_12e_state", "12.e. State", "select", True),
    ("Part 2. Mailing Address", "p2_12f_zip", "12.f. ZIP Code", "text", True),
    ("Part 2. Mailing Address", "p2_12g_province", "12.g. Province (if applicable)", "text", False),
    ("Part 2. Mailing Address", "p2_12h_postal_code", "12.h. Postal Code (if applicable)", "text", False),
    ("Part 2. Mailing Address", "p2_12i_country", "12.i. Country (if outside U.S.)", "text", False),

    # Physical Address
    ("Part 2. Physical Address", "p2_13a_street", "13.a. Street Number and Name (if different from mailing)", "text", False),
    ("Part 2. Physical Address", "p2_13b_apt_type", "13.b. Apt./Ste./Flr.", "select", False),
    ("Part 2. Physical Address", "p2_13b_apt_number", "13.b. Number", "text", False),
    ("Part 2. Physical Address", "p2_13c_city", "13.c. City or Town", "text", False),
    ("Part 2. Physical Address", "p2_13d_state", "13.d. State", "select", False),
    ("Part 2. Physical Address", "p2_13e_zip", "13.e. ZIP Code", "text", False),

    # Contact
    ("Part 2. Contact Information", "p2_14_daytime_phone", "14. Daytime Telephone Number", "phone", True),
    ("Part 2. Contact Information", "p2_15_mobile_phone", "15. Mobile Telephone Number (if any)", "phone", False),
    ("Part 2. Contact Information", "p2_16_email", "16. Email Address (if any)", "email", False),

    # Immigration History
    ("Part 2. Immigration History", "p2_17_lpr", "17. Are you a lawful permanent resident (LPR)?", "select", False),
    ("Part 2. Immigration History", "p2_18_lpr_date", "18. Date You Became an LPR (mm/dd/yyyy)", "date", False),
    ("Part 2. Immigration History", "p2_19_certificate_issued", "19. Has a Certificate of Citizenship ever been issued in your name?", "select", False),
    ("Part 2. Immigration History", "p2_20_certificate_number", "20. Certificate Number (if any)", "text", False),
    ("Part 2. Immigration History", "p2_21_passport_issued", "21. Has a U.S. passport ever been issued in your name?", "select", False),
    ("Part 2. Immigration History", "p2_22_passport_number", "22. Passport Number (if any)", "text", False),

    # =========================================================================
    # PART 3: BIOGRAPHIC INFORMATION (Page 3)
    # =========================================================================
    ("Part 3. Biographic Information", "p3_1_ethnicity", "1. Ethnicity (select one)", "select", True),
    ("Part 3. Biographic Information", "p3_2_race", "2. Race (select all that apply)", "text", True),
    ("Part 3. Biographic Information", "p3_3_height_feet", "3.a. Height - Feet", "number", True),
    ("Part 3. Biographic Information", "p3_3_height_inches", "3.b. Height - Inches", "number", True),
    ("Part 3. Biographic Information", "p3_4_weight", "4. Weight (in pounds)", "number", True),
    ("Part 3. Biographic Information", "p3_5_eye_color", "5. Eye Color", "select", True),
    ("Part 3. Biographic Information", "p3_6_hair_color", "6. Hair Color", "select", True),

    # =========================================================================
    # PART 4: INFORMATION ABOUT U.S. CITIZEN FATHER OR MOTHER (Pages 3-5)
    # =========================================================================
    ("Part 4. Information About U.S. Citizen Father or Mother", "p4_1_relationship", "1. Relationship to You", "select", True),
    ("Part 4. Information About U.S. Citizen Father or Mother", "p4_2a_current_family_name", "2.a. Current Legal Family Name", "text", True),
    ("Part 4. Information About U.S. Citizen Father or Mother", "p4_2b_current_given_name", "2.b. Current Legal Given Name", "text", True),
    ("Part 4. Information About U.S. Citizen Father or Mother", "p4_2c_current_middle_name", "2.c. Current Legal Middle Name", "text", False),
    ("Part 4. Information About U.S. Citizen Father or Mother", "p4_3a_name_at_birth_family", "3.a. Name at Birth - Family Name", "text", False),
    ("Part 4. Information About U.S. Citizen Father or Mother", "p4_3b_name_at_birth_given", "3.b. Name at Birth - Given Name", "text", False),
    ("Part 4. Information About U.S. Citizen Father or Mother", "p4_3c_name_at_birth_middle", "3.c. Name at Birth - Middle Name", "text", False),
    ("Part 4. Information About U.S. Citizen Father or Mother", "p4_4_dob", "4. Date of Birth (mm/dd/yyyy)", "date", True),
    ("Part 4. Information About U.S. Citizen Father or Mother", "p4_5_gender_male", "5. Gender - Male", "radio", False),
    ("Part 4. Information About U.S. Citizen Father or Mother", "p4_5_gender_female", "5. Gender - Female", "radio", False),
    ("Part 4. Information About U.S. Citizen Father or Mother", "p4_6_city_of_birth", "6. City/Town/Village of Birth", "text", True),
    ("Part 4. Information About U.S. Citizen Father or Mother", "p4_7_state_of_birth", "7. State/Province of Birth", "text", False),
    ("Part 4. Information About U.S. Citizen Father or Mother", "p4_8_country_of_birth", "8. Country of Birth", "text", True),
    ("Part 4. Information About U.S. Citizen Father or Mother", "p4_9_citizenship_how", "9. How did this parent become a U.S. citizen?", "select", True),
    ("Part 4. Information About U.S. Citizen Father or Mother", "p4_10_is_deceased", "10. Is this parent deceased?", "select", False),

    # Parent's Addresses (U.S. residences)
    ("Part 4. Parent's U.S. Address", "p4_11a_street", "11.a. Current Street Number and Name", "text", False),
    ("Part 4. Parent's U.S. Address", "p4_11b_apt_type", "11.b. Apt./Ste./Flr.", "select", False),
    ("Part 4. Parent's U.S. Address", "p4_11b_apt_number", "11.b. Number", "text", False),
    ("Part 4. Parent's U.S. Address", "p4_11c_city", "11.c. City or Town", "text", False),
    ("Part 4. Parent's U.S. Address", "p4_11d_state", "11.d. State", "select", False),
    ("Part 4. Parent's U.S. Address", "p4_11e_zip", "11.e. ZIP Code", "text", False),

    # Parent's Marriage Info
    ("Part 4. Parent's Marital History", "p4_12_times_married", "12. How many times has this parent been married?", "number", False),
    ("Part 4. Parent's Marital History", "p4_13_marriage_date_to_other_parent", "13. Date of Marriage to Your Other Parent (mm/dd/yyyy)", "date", False),
    ("Part 4. Parent's Marital History", "p4_14_marriage_city", "14. City/Town Where Marriage Took Place", "text", False),
    ("Part 4. Parent's Marital History", "p4_15_marriage_state", "15. State/Province Where Marriage Took Place", "text", False),
    ("Part 4. Parent's Marital History", "p4_16_marriage_country", "16. Country Where Marriage Took Place", "text", False),
    ("Part 4. Parent's Marital History", "p4_17_still_married", "17. Are your parents still married?", "select", False),
    ("Part 4. Parent's Marital History", "p4_18_marriage_end_date", "18. If not, Date Marriage Ended (mm/dd/yyyy)", "date", False),
    ("Part 4. Parent's Marital History", "p4_19_marriage_end_reason", "19. How Marriage Ended", "select", False),

    # Parent's Physical Presence
    ("Part 4. Physical Presence", "p4_20_parent_physically_present", "20. Was this parent physically present in the U.S. or territories before your birth?", "select", False),
    ("Part 4. Physical Presence", "p4_21_residence_period_from", "21.a. Period of Residence - From (mm/dd/yyyy)", "date", False),
    ("Part 4. Physical Presence", "p4_21_residence_period_to", "21.b. Period of Residence - To (mm/dd/yyyy)", "date", False),
    ("Part 4. Physical Presence", "p4_22_residence_period2_from", "22.a. Period of Residence 2 - From (mm/dd/yyyy)", "date", False),
    ("Part 4. Physical Presence", "p4_22_residence_period2_to", "22.b. Period of Residence 2 - To (mm/dd/yyyy)", "date", False),
    ("Part 4. Physical Presence", "p4_23_residence_period3_from", "23.a. Period of Residence 3 - From (mm/dd/yyyy)", "date", False),
    ("Part 4. Physical Presence", "p4_23_residence_period3_to", "23.b. Period of Residence 3 - To (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 5: INFORMATION ABOUT YOUR U.S. CITIZEN FATHER (IF APPLICABLE) (Pages 5-6)
    # =========================================================================
    ("Part 5. Information About Your U.S. Citizen Father", "p5_1_is_biological", "1. Is this person your biological father?", "select", False),
    ("Part 5. Information About Your U.S. Citizen Father", "p5_2_paternity_established", "2. Was paternity established by legitimation, acknowledgment, or court order?", "select", False),
    ("Part 5. Information About Your U.S. Citizen Father", "p5_3_paternity_date", "3. Date Paternity Was Established (mm/dd/yyyy)", "date", False),
    ("Part 5. Information About Your U.S. Citizen Father", "p5_4a_father_family_name", "4.a. Father's Family Name", "text", False),
    ("Part 5. Information About Your U.S. Citizen Father", "p5_4b_father_given_name", "4.b. Father's Given Name", "text", False),
    ("Part 5. Information About Your U.S. Citizen Father", "p5_4c_father_middle_name", "4.c. Father's Middle Name", "text", False),
    ("Part 5. Information About Your U.S. Citizen Father", "p5_5_father_dob", "5. Father's Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 5. Information About Your U.S. Citizen Father", "p5_6_father_country_of_birth", "6. Father's Country of Birth", "text", False),

    # =========================================================================
    # PART 6: INFORMATION ABOUT YOUR U.S. CITIZEN MOTHER (IF APPLICABLE) (Pages 6-7)
    # =========================================================================
    ("Part 6. Information About Your U.S. Citizen Mother", "p6_1_is_biological", "1. Is this person your biological mother?", "select", False),
    ("Part 6. Information About Your U.S. Citizen Mother", "p6_2a_mother_family_name", "2.a. Mother's Family Name", "text", False),
    ("Part 6. Information About Your U.S. Citizen Mother", "p6_2b_mother_given_name", "2.b. Mother's Given Name", "text", False),
    ("Part 6. Information About Your U.S. Citizen Mother", "p6_2c_mother_middle_name", "2.c. Mother's Middle Name", "text", False),
    ("Part 6. Information About Your U.S. Citizen Mother", "p6_3_mother_maiden_name", "3. Mother's Name at Birth (Maiden Name)", "text", False),
    ("Part 6. Information About Your U.S. Citizen Mother", "p6_4_mother_dob", "4. Mother's Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 6. Information About Your U.S. Citizen Mother", "p6_5_mother_country_of_birth", "5. Mother's Country of Birth", "text", False),

    # =========================================================================
    # PART 7: INFORMATION ABOUT MILITARY SERVICE (Page 7)
    # =========================================================================
    ("Part 7. Information About Military Service of U.S. Citizen Parent", "p7_1_served_military", "1. Did your U.S. citizen parent serve in the U.S. Armed Forces?", "select", False),
    ("Part 7. Information About Military Service of U.S. Citizen Parent", "p7_2_branch", "2. Branch of Service", "text", False),
    ("Part 7. Information About Military Service of U.S. Citizen Parent", "p7_3_service_from", "3. Date of Service - From (mm/dd/yyyy)", "date", False),
    ("Part 7. Information About Military Service of U.S. Citizen Parent", "p7_4_service_to", "4. Date of Service - To (mm/dd/yyyy)", "date", False),
    ("Part 7. Information About Military Service of U.S. Citizen Parent", "p7_5_honorable_discharge", "5. Was the discharge honorable?", "select", False),

    # =========================================================================
    # PART 8: APPLICANT'S STATEMENT, CONTACT, DECLARATION, AND SIGNATURE (Pages 7-8)
    # =========================================================================
    ("Part 8. Applicant's Statement, Contact, Declaration, and Signature", "p8_1_language_read", "1. I can read and understand English", "checkbox", False),
    ("Part 8. Applicant's Statement, Contact, Declaration, and Signature", "p8_1b_interpreter_used", "1.b. The interpreter named in Part 9 read to me every question in a language I understand", "checkbox", False),
    ("Part 8. Applicant's Statement, Contact, Declaration, and Signature", "p8_2_preparer_used", "2. At my request, the preparer named in Part 10 prepared this application for me", "checkbox", False),
    ("Part 8. Applicant's Statement, Contact, Declaration, and Signature", "p8_3a_daytime_phone", "3.a. Applicant's Daytime Telephone Number", "phone", False),
    ("Part 8. Applicant's Statement, Contact, Declaration, and Signature", "p8_3b_mobile_phone", "3.b. Applicant's Mobile Telephone Number", "phone", False),
    ("Part 8. Applicant's Statement, Contact, Declaration, and Signature", "p8_3c_email", "3.c. Applicant's Email Address", "email", False),
    ("Part 8. Applicant's Statement, Contact, Declaration, and Signature", "p8_4_signature", "4. Applicant's Signature", "text", False),
    ("Part 8. Applicant's Statement, Contact, Declaration, and Signature", "p8_5_signature_date", "5. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 9: INTERPRETER'S CONTACT INFORMATION (Pages 8-9)
    # =========================================================================
    ("Part 9. Interpreter's Contact Information, Certification, and Signature", "p9_1a_family_name", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("Part 9. Interpreter's Contact Information, Certification, and Signature", "p9_1b_given_name", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("Part 9. Interpreter's Contact Information, Certification, and Signature", "p9_2_business_name", "2. Interpreter's Business or Organization Name (if any)", "text", False),
    ("Part 9. Interpreter's Contact Information, Certification, and Signature", "p9_3a_street", "3.a. Street Number and Name", "text", False),
    ("Part 9. Interpreter's Contact Information, Certification, and Signature", "p9_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 9. Interpreter's Contact Information, Certification, and Signature", "p9_3b_apt_number", "3.b. Number", "text", False),
    ("Part 9. Interpreter's Contact Information, Certification, and Signature", "p9_3c_city", "3.c. City or Town", "text", False),
    ("Part 9. Interpreter's Contact Information, Certification, and Signature", "p9_3d_state", "3.d. State", "select", False),
    ("Part 9. Interpreter's Contact Information, Certification, and Signature", "p9_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 9. Interpreter's Contact Information, Certification, and Signature", "p9_4a_daytime_phone", "4.a. Interpreter's Daytime Telephone Number", "phone", False),
    ("Part 9. Interpreter's Contact Information, Certification, and Signature", "p9_4b_mobile_phone", "4.b. Interpreter's Mobile Telephone Number", "phone", False),
    ("Part 9. Interpreter's Contact Information, Certification, and Signature", "p9_4c_email", "4.c. Interpreter's Email Address", "email", False),
    ("Part 9. Interpreter's Contact Information, Certification, and Signature", "p9_5_language", "5. Language Interpreted", "text", False),
    ("Part 9. Interpreter's Contact Information, Certification, and Signature", "p9_6_signature", "6. Interpreter's Signature", "text", False),
    ("Part 9. Interpreter's Contact Information, Certification, and Signature", "p9_7_signature_date", "7. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 10: CONTACT INFORMATION, DECLARATION, AND SIGNATURE OF PREPARER (Pages 9-10)
    # =========================================================================
    ("Part 10. Contact Information, Declaration, and Signature of Person Preparing this Application", "p10_1a_family_name", "1.a. Preparer's Family Name (Last Name)", "text", False),
    ("Part 10. Contact Information, Declaration, and Signature of Person Preparing this Application", "p10_1b_given_name", "1.b. Preparer's Given Name (First Name)", "text", False),
    ("Part 10. Contact Information, Declaration, and Signature of Person Preparing this Application", "p10_2_business_name", "2. Preparer's Business or Organization Name (if any)", "text", False),
    ("Part 10. Contact Information, Declaration, and Signature of Person Preparing this Application", "p10_3a_street", "3.a. Preparer's Street Number and Name", "text", False),
    ("Part 10. Contact Information, Declaration, and Signature of Person Preparing this Application", "p10_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 10. Contact Information, Declaration, and Signature of Person Preparing this Application", "p10_3b_apt_number", "3.b. Number", "text", False),
    ("Part 10. Contact Information, Declaration, and Signature of Person Preparing this Application", "p10_3c_city", "3.c. City or Town", "text", False),
    ("Part 10. Contact Information, Declaration, and Signature of Person Preparing this Application", "p10_3d_state", "3.d. State", "select", False),
    ("Part 10. Contact Information, Declaration, and Signature of Person Preparing this Application", "p10_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 10. Contact Information, Declaration, and Signature of Person Preparing this Application", "p10_4a_daytime_phone", "4.a. Preparer's Daytime Telephone Number", "phone", False),
    ("Part 10. Contact Information, Declaration, and Signature of Person Preparing this Application", "p10_4b_mobile_phone", "4.b. Preparer's Mobile Telephone Number", "phone", False),
    ("Part 10. Contact Information, Declaration, and Signature of Person Preparing this Application", "p10_4c_email", "4.c. Preparer's Email Address", "email", False),
    ("Part 10. Contact Information, Declaration, and Signature of Person Preparing this Application", "p10_5_is_attorney", "5. Is the preparer an attorney or accredited representative?", "select", False),
    ("Part 10. Contact Information, Declaration, and Signature of Person Preparing this Application", "p10_6_signature", "6. Preparer's Signature", "text", False),
    ("Part 10. Contact Information, Declaration, and Signature of Person Preparing this Application", "p10_7_signature_date", "7. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 11: ADDITIONAL INFORMATION (Page 11)
    # =========================================================================
    ("Part 11. Additional Information", "p11_1a_page_number", "1.a. Page Number", "text", False),
    ("Part 11. Additional Information", "p11_1b_part_number", "1.b. Part Number", "text", False),
    ("Part 11. Additional Information", "p11_1c_item_number", "1.c. Item Number", "text", False),
    ("Part 11. Additional Information", "p11_1d_additional_info", "1.d. Additional Information", "textarea", False),
    ("Part 11. Additional Information", "p11_2a_page_number", "2.a. Page Number", "text", False),
    ("Part 11. Additional Information", "p11_2b_part_number", "2.b. Part Number", "text", False),
    ("Part 11. Additional Information", "p11_2c_item_number", "2.c. Item Number", "text", False),
    ("Part 11. Additional Information", "p11_2d_additional_info", "2.d. Additional Information", "textarea", False),
]

OPTIONS_MAP = {
    "p1_1_basis": ["Birth abroad to U.S. citizen parent(s)", "Derived citizenship through naturalization of parent(s)", "Adopted by U.S. citizen parent(s)"],
    "p1_2_born_in_us": ["Yes", "No"],
    "p1_3_born_abroad": ["Yes", "No"],
    "p1_4_adopted": ["Yes", "No"],
    "p2_12c_apt_type": ["Apt.", "Ste.", "Flr."],
    "p2_13b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p4_11b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p9_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p10_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p2_17_lpr": ["Yes", "No"],
    "p2_19_certificate_issued": ["Yes", "No"],
    "p2_21_passport_issued": ["Yes", "No"],
    "p3_1_ethnicity": ["Hispanic or Latino", "Not Hispanic or Latino"],
    "p3_5_eye_color": ["Black", "Blue", "Brown", "Gray", "Green", "Hazel", "Maroon", "Pink", "Unknown/Other"],
    "p3_6_hair_color": ["Bald", "Black", "Blond", "Brown", "Gray", "Red", "Sandy", "White", "Unknown/Other"],
    "p4_1_relationship": ["Father", "Mother", "Adoptive Father", "Adoptive Mother"],
    "p4_9_citizenship_how": ["Birth in the U.S.", "Birth abroad to U.S. citizen parent(s)", "Naturalization", "Other"],
    "p4_10_is_deceased": ["Yes", "No"],
    "p4_17_still_married": ["Yes", "No"],
    "p4_19_marriage_end_reason": ["Divorce", "Death", "Annulment", "Other"],
    "p4_20_parent_physically_present": ["Yes", "No"],
    "p5_1_is_biological": ["Yes", "No"],
    "p5_2_paternity_established": ["Yes", "No"],
    "p6_1_is_biological": ["Yes", "No"],
    "p7_1_served_military": ["Yes", "No"],
    "p7_5_honorable_discharge": ["Yes", "No"],
    "p10_5_is_attorney": ["Yes", "No"],
}


def expand():
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT id FROM questionnaire_templates WHERE name LIKE '%N-600 -%' AND name NOT LIKE '%N-600K%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
        ))
        row = result.fetchone()
        if not row:
            print("N-600 template not found!")
            return
        tid = row[0]
        print(f"Found N-600 template id={tid}")

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": tid})

        for i, (section, fname, label, ftype, req) in enumerate(N600_FIELDS, 1):
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
        print(f"Expanded N-600: {len(N600_FIELDS)} fields inserted for template {tid}")


if __name__ == "__main__":
    expand()
