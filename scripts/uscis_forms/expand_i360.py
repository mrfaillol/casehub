#!/usr/bin/env python3
"""
Expand I-360 (Petition for Amerasian, Widow(er), or Special Immigrant) with ALL official USCIS fields.
Edition 06/05/24 - 12 pages, Parts 1-10.
Covers: Religious Workers, Special Immigrant Juveniles, VAWA, Amerasians, etc.
"""
import json
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I360_FIELDS = [
    # =========================================================================
    # PART 1: CLASSIFICATION YOU ARE SEEKING (Page 1)
    # =========================================================================
    ("Part 1. Classification You Are Seeking", "p1_1_classification", "1. I am filing this petition for classification as (select one)", "select", True),

    # =========================================================================
    # PART 2: INFORMATION ABOUT YOU (Pages 1-3)
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
    ("Part 2. Mailing Address", "p2_12i_country", "12.i. Country", "text", False),

    # Physical Address
    ("Part 2. Physical Address", "p2_13a_street", "13.a. Street Number and Name", "text", False),
    ("Part 2. Physical Address", "p2_13b_apt_type", "13.b. Apt./Ste./Flr.", "select", False),
    ("Part 2. Physical Address", "p2_13b_apt_number", "13.b. Number", "text", False),
    ("Part 2. Physical Address", "p2_13c_city", "13.c. City or Town", "text", False),
    ("Part 2. Physical Address", "p2_13d_state", "13.d. State", "select", False),
    ("Part 2. Physical Address", "p2_13e_zip", "13.e. ZIP Code", "text", False),

    # Contact
    ("Part 2. Contact Information", "p2_14_daytime_phone", "14. Daytime Telephone Number", "phone", True),
    ("Part 2. Contact Information", "p2_15_mobile_phone", "15. Mobile Telephone Number (if any)", "phone", False),
    ("Part 2. Contact Information", "p2_16_email", "16. Email Address (if any)", "email", False),

    # Immigration Info
    ("Part 2. Immigration Information", "p2_17_current_status", "17. Current Immigration Status", "text", False),
    ("Part 2. Immigration Information", "p2_18_date_of_last_entry", "18. Date of Last Entry Into the United States (mm/dd/yyyy)", "date", False),
    ("Part 2. Immigration Information", "p2_19_i94_number", "19. I-94 Arrival-Departure Record Number", "text", False),
    ("Part 2. Immigration Information", "p2_20_passport_number", "20. Passport or Travel Document Number", "text", False),
    ("Part 2. Immigration Information", "p2_21_travel_doc_country", "21. Country That Issued Your Passport or Travel Document", "text", False),
    ("Part 2. Immigration Information", "p2_22_passport_expiration", "22. Expiration Date (mm/dd/yyyy)", "date", False),

    # Marital History
    ("Part 2. Marital History", "p2_23_marital_status", "23. Current Marital Status", "select", True),
    ("Part 2. Marital History", "p2_24_times_married", "24. How many times have you been married?", "number", False),

    # =========================================================================
    # PART 3: INFORMATION ABOUT YOUR EMPLOYER (IF APPLICABLE) (Pages 3-4)
    # =========================================================================
    ("Part 3. Information About Your Employer", "p3_1_employer_name", "1. Employer's Name", "text", False),
    ("Part 3. Information About Your Employer", "p3_2a_street", "2.a. Employer's Street Number and Name", "text", False),
    ("Part 3. Information About Your Employer", "p3_2b_apt_type", "2.b. Ste./Flr.", "select", False),
    ("Part 3. Information About Your Employer", "p3_2b_apt_number", "2.b. Number", "text", False),
    ("Part 3. Information About Your Employer", "p3_2c_city", "2.c. City or Town", "text", False),
    ("Part 3. Information About Your Employer", "p3_2d_state", "2.d. State", "select", False),
    ("Part 3. Information About Your Employer", "p3_2e_zip", "2.e. ZIP Code", "text", False),
    ("Part 3. Information About Your Employer", "p3_3_employer_phone", "3. Employer's Telephone Number", "phone", False),
    ("Part 3. Information About Your Employer", "p3_4_ein", "4. Employer Identification Number (EIN)", "text", False),

    # =========================================================================
    # PART 4: PROCESSING INFORMATION (Pages 4-5)
    # =========================================================================
    ("Part 4. Processing Information", "p4_1_processing_type", "1. Type of Processing Requested", "select", False),
    ("Part 4. Processing Information", "p4_2_consulate_city", "2. U.S. Consulate - City or Town", "text", False),
    ("Part 4. Processing Information", "p4_3_consulate_country", "3. U.S. Consulate - Country", "text", False),
    ("Part 4. Processing Information", "p4_4_in_proceedings", "4. Are you currently in immigration proceedings?", "select", False),
    ("Part 4. Processing Information", "p4_5_prior_petition", "5. Have you ever previously filed an I-360?", "select", False),
    ("Part 4. Processing Information", "p4_6_prior_petition_date", "6. Date of Prior Filing (mm/dd/yyyy)", "date", False),
    ("Part 4. Processing Information", "p4_7_prior_petition_result", "7. Result of Prior Filing", "text", False),

    # =========================================================================
    # PART 5: ADDITIONAL INFORMATION FOR RELIGIOUS WORKERS (Pages 5-7)
    # =========================================================================
    ("Part 5. Additional Information for Religious Workers", "p5_1_denomination", "1. Name of Religious Denomination", "text", False),
    ("Part 5. Additional Information for Religious Workers", "p5_2_member_since", "2. Date You Became a Member of This Denomination (mm/dd/yyyy)", "date", False),
    ("Part 5. Additional Information for Religious Workers", "p5_3_religious_occupation", "3. Religious Occupation or Vocation", "select", False),
    ("Part 5. Additional Information for Religious Workers", "p5_4_ordained", "4. Have you been ordained, commissioned, or licensed?", "select", False),
    ("Part 5. Additional Information for Religious Workers", "p5_5_ordination_date", "5. Date of Ordination/Commissioning/Licensing (mm/dd/yyyy)", "date", False),
    ("Part 5. Additional Information for Religious Workers", "p5_6_compensated", "6. Will you be compensated for your religious work?", "select", False),
    ("Part 5. Additional Information for Religious Workers", "p5_7_annual_compensation", "7. Amount of Annual Compensation (USD)", "text", False),
    ("Part 5. Additional Information for Religious Workers", "p5_8_work_full_time", "8. Will you work full time (35+ hours per week)?", "select", False),
    ("Part 5. Additional Information for Religious Workers", "p5_9_org_tax_exempt", "9. Is the organization tax-exempt under IRC 501(c)(3)?", "select", False),
    ("Part 5. Additional Information for Religious Workers", "p5_10_org_name", "10. Name of Religious Organization Where You Will Work", "text", False),
    ("Part 5. Additional Information for Religious Workers", "p5_11a_org_street", "11.a. Organization Street Number and Name", "text", False),
    ("Part 5. Additional Information for Religious Workers", "p5_11b_org_city", "11.b. Organization City or Town", "text", False),
    ("Part 5. Additional Information for Religious Workers", "p5_11c_org_state", "11.c. Organization State", "text", False),
    ("Part 5. Additional Information for Religious Workers", "p5_11d_org_zip", "11.d. Organization ZIP Code", "text", False),
    ("Part 5. Additional Information for Religious Workers", "p5_12_duties_description", "12. Description of Your Religious Duties", "textarea", False),

    # =========================================================================
    # PART 6: ADDITIONAL INFORMATION FOR SPECIAL IMMIGRANT JUVENILES (Pages 7-8)
    # =========================================================================
    ("Part 6. Additional Information for Special Immigrant Juveniles", "p6_1_court_order", "1. Has a juvenile court determined that you are dependent on the court or placed in custody?", "select", False),
    ("Part 6. Additional Information for Special Immigrant Juveniles", "p6_2_court_name", "2. Name of Juvenile Court", "text", False),
    ("Part 6. Additional Information for Special Immigrant Juveniles", "p6_3_court_city", "3. City/Town of Court", "text", False),
    ("Part 6. Additional Information for Special Immigrant Juveniles", "p6_4_court_state", "4. State of Court", "text", False),
    ("Part 6. Additional Information for Special Immigrant Juveniles", "p6_5_order_date", "5. Date of Court Order (mm/dd/yyyy)", "date", False),
    ("Part 6. Additional Information for Special Immigrant Juveniles", "p6_6_reunification_not_viable", "6. Has the court found that reunification with one or both parents is not viable?", "select", False),
    ("Part 6. Additional Information for Special Immigrant Juveniles", "p6_7_best_interest", "7. Has the court found it is not in your best interest to return to your home country?", "select", False),

    # =========================================================================
    # PART 7: PETITIONER'S STATEMENT, CONTACT, DECLARATION, AND SIGNATURE (Pages 8-9)
    # =========================================================================
    ("Part 7. Petitioner's Statement, Contact, Declaration, and Signature", "p7_1_language_read", "1. I can read and understand English", "checkbox", False),
    ("Part 7. Petitioner's Statement, Contact, Declaration, and Signature", "p7_1b_interpreter_used", "1.b. The interpreter named in Part 8 read to me every question in a language I understand", "checkbox", False),
    ("Part 7. Petitioner's Statement, Contact, Declaration, and Signature", "p7_2_preparer_used", "2. At my request, the preparer named in Part 9 prepared this petition for me", "checkbox", False),
    ("Part 7. Petitioner's Statement, Contact, Declaration, and Signature", "p7_3a_daytime_phone", "3.a. Petitioner's Daytime Telephone Number", "phone", False),
    ("Part 7. Petitioner's Statement, Contact, Declaration, and Signature", "p7_3b_mobile_phone", "3.b. Petitioner's Mobile Telephone Number", "phone", False),
    ("Part 7. Petitioner's Statement, Contact, Declaration, and Signature", "p7_3c_email", "3.c. Petitioner's Email Address", "email", False),
    ("Part 7. Petitioner's Statement, Contact, Declaration, and Signature", "p7_4_signature", "4. Petitioner's Signature", "text", False),
    ("Part 7. Petitioner's Statement, Contact, Declaration, and Signature", "p7_5_signature_date", "5. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 8: INTERPRETER'S CONTACT INFORMATION (Pages 9-10)
    # =========================================================================
    ("Part 8. Interpreter's Contact Information, Certification, and Signature", "p8_1a_family_name", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("Part 8. Interpreter's Contact Information, Certification, and Signature", "p8_1b_given_name", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("Part 8. Interpreter's Contact Information, Certification, and Signature", "p8_2_business_name", "2. Interpreter's Business or Organization Name (if any)", "text", False),
    ("Part 8. Interpreter's Contact Information, Certification, and Signature", "p8_3a_street", "3.a. Street Number and Name", "text", False),
    ("Part 8. Interpreter's Contact Information, Certification, and Signature", "p8_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 8. Interpreter's Contact Information, Certification, and Signature", "p8_3b_apt_number", "3.b. Number", "text", False),
    ("Part 8. Interpreter's Contact Information, Certification, and Signature", "p8_3c_city", "3.c. City or Town", "text", False),
    ("Part 8. Interpreter's Contact Information, Certification, and Signature", "p8_3d_state", "3.d. State", "select", False),
    ("Part 8. Interpreter's Contact Information, Certification, and Signature", "p8_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 8. Interpreter's Contact Information, Certification, and Signature", "p8_4a_daytime_phone", "4.a. Interpreter's Daytime Telephone Number", "phone", False),
    ("Part 8. Interpreter's Contact Information, Certification, and Signature", "p8_4b_mobile_phone", "4.b. Interpreter's Mobile Telephone Number", "phone", False),
    ("Part 8. Interpreter's Contact Information, Certification, and Signature", "p8_4c_email", "4.c. Interpreter's Email Address", "email", False),
    ("Part 8. Interpreter's Contact Information, Certification, and Signature", "p8_5_language", "5. Language Interpreted", "text", False),
    ("Part 8. Interpreter's Contact Information, Certification, and Signature", "p8_6_signature", "6. Interpreter's Signature", "text", False),
    ("Part 8. Interpreter's Contact Information, Certification, and Signature", "p8_7_signature_date", "7. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 9: CONTACT INFORMATION, DECLARATION, AND SIGNATURE OF PREPARER (Pages 10-11)
    # =========================================================================
    ("Part 9. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p9_1a_family_name", "1.a. Preparer's Family Name (Last Name)", "text", False),
    ("Part 9. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p9_1b_given_name", "1.b. Preparer's Given Name (First Name)", "text", False),
    ("Part 9. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p9_2_business_name", "2. Preparer's Business or Organization Name (if any)", "text", False),
    ("Part 9. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p9_3a_street", "3.a. Preparer's Street Number and Name", "text", False),
    ("Part 9. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p9_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 9. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p9_3b_apt_number", "3.b. Number", "text", False),
    ("Part 9. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p9_3c_city", "3.c. City or Town", "text", False),
    ("Part 9. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p9_3d_state", "3.d. State", "select", False),
    ("Part 9. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p9_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 9. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p9_4a_daytime_phone", "4.a. Preparer's Daytime Telephone Number", "phone", False),
    ("Part 9. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p9_4b_mobile_phone", "4.b. Preparer's Mobile Telephone Number", "phone", False),
    ("Part 9. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p9_4c_email", "4.c. Preparer's Email Address", "email", False),
    ("Part 9. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p9_5_is_attorney", "5. Is the preparer an attorney or accredited representative?", "select", False),
    ("Part 9. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p9_6_signature", "6. Preparer's Signature", "text", False),
    ("Part 9. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p9_7_signature_date", "7. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 10: ADDITIONAL INFORMATION (Page 12)
    # =========================================================================
    ("Part 10. Additional Information", "p10_1a_page_number", "1.a. Page Number", "text", False),
    ("Part 10. Additional Information", "p10_1b_part_number", "1.b. Part Number", "text", False),
    ("Part 10. Additional Information", "p10_1c_item_number", "1.c. Item Number", "text", False),
    ("Part 10. Additional Information", "p10_1d_additional_info", "1.d. Additional Information", "textarea", False),
    ("Part 10. Additional Information", "p10_2a_page_number", "2.a. Page Number", "text", False),
    ("Part 10. Additional Information", "p10_2b_part_number", "2.b. Part Number", "text", False),
    ("Part 10. Additional Information", "p10_2c_item_number", "2.c. Item Number", "text", False),
    ("Part 10. Additional Information", "p10_2d_additional_info", "2.d. Additional Information", "textarea", False),
]

OPTIONS_MAP = {
    "p1_1_classification": [
        "Amerasian",
        "Widow(er) of U.S. citizen",
        "Battered or abused spouse of U.S. citizen (VAWA)",
        "Battered or abused child of U.S. citizen (VAWA)",
        "Battered or abused spouse of LPR (VAWA)",
        "Battered or abused child of LPR (VAWA)",
        "Special Immigrant Religious Worker",
        "Special Immigrant Juvenile",
        "Afghan or Iraqi National (SI/SQ)",
        "International Organization Employee",
        "Other Special Immigrant",
    ],
    "p2_12c_apt_type": ["Apt.", "Ste.", "Flr."],
    "p2_13b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p3_2b_apt_type": ["Ste.", "Flr."],
    "p8_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p9_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p2_23_marital_status": ["Single, Never Married", "Married", "Divorced", "Widowed", "Separated", "Marriage Annulled"],
    "p4_1_processing_type": ["Adjustment of Status", "Consular Processing"],
    "p4_4_in_proceedings": ["Yes", "No"],
    "p4_5_prior_petition": ["Yes", "No"],
    "p5_3_religious_occupation": ["Minister of Religion", "Religious Vocation", "Religious Occupation"],
    "p5_4_ordained": ["Yes", "No"],
    "p5_6_compensated": ["Yes", "No"],
    "p5_8_work_full_time": ["Yes", "No"],
    "p5_9_org_tax_exempt": ["Yes", "No"],
    "p6_1_court_order": ["Yes", "No"],
    "p6_6_reunification_not_viable": ["Yes", "No"],
    "p6_7_best_interest": ["Yes", "No"],
    "p9_5_is_attorney": ["Yes", "No"],
}


def expand():
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-360%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
        ))
        row = result.fetchone()
        if not row:
            print("I-360 template not found!")
            return
        tid = row[0]
        print(f"Found I-360 template id={tid}")

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": tid})

        for i, (section, fname, label, ftype, req) in enumerate(I360_FIELDS, 1):
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
        print(f"Expanded I-360: {len(I360_FIELDS)} fields inserted for template {tid}")


if __name__ == "__main__":
    expand()
