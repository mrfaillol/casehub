#!/usr/bin/env python3
"""
Expand I-751 (Petition to Remove Conditions on Residence) with ALL official USCIS fields.
Edition 04/25/23 - 10 pages, Parts 1-9.
"""
import json
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I751_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT YOU (Pages 1-2)
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
    ("Part 1. Information About You", "p1_9_a_number", "9. Alien Registration Number (A-Number)", "text", True),
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

    # Physical Address (if different)
    ("Part 1. Physical Address", "p1_13a_street", "13.a. Street Number and Name (if different from mailing address)", "text", False),
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
    # PART 2: INFORMATION ABOUT CONDITIONAL RESIDENCE (Pages 2-3)
    # =========================================================================
    ("Part 2. Information About Your Conditional Residence", "p2_1_basis", "1. My conditional residence was based on my marriage to a U.S. citizen or lawful permanent resident", "select", True),
    ("Part 2. Information About Your Conditional Residence", "p2_2_filing_type", "2. I am filing this petition (joint filing / waiver)", "select", True),
    ("Part 2. Information About Your Conditional Residence", "p2_3_conditional_card_date", "3. Date You Became a Conditional Permanent Resident (mm/dd/yyyy)", "date", True),
    ("Part 2. Information About Your Conditional Residence", "p2_4_conditional_card_city", "4. City/Town Where You Obtained Conditional Residence", "text", False),
    ("Part 2. Information About Your Conditional Residence", "p2_5_conditional_card_state", "5. State Where You Obtained Conditional Residence", "text", False),
    ("Part 2. Information About Your Conditional Residence", "p2_6_marriage_date", "6. Date of Marriage to Conditional Residence Sponsor (mm/dd/yyyy)", "date", True),
    ("Part 2. Information About Your Conditional Residence", "p2_7_marriage_city", "7. City/Town Where Marriage Took Place", "text", False),
    ("Part 2. Information About Your Conditional Residence", "p2_8_marriage_state", "8. State/Province Where Marriage Took Place", "text", False),
    ("Part 2. Information About Your Conditional Residence", "p2_9_marriage_country", "9. Country Where Marriage Took Place", "text", False),
    ("Part 2. Information About Your Conditional Residence", "p2_10_currently_married", "10. Are you still married to the person through whom you gained conditional residence?", "select", True),
    ("Part 2. Information About Your Conditional Residence", "p2_11_living_together", "11. Are you currently living with your spouse?", "select", False),
    ("Part 2. Information About Your Conditional Residence", "p2_12_separated_date", "12. If you are separated, date of separation (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 3: INFORMATION ABOUT YOUR SPOUSE (Pages 3-4)
    # =========================================================================
    ("Part 3. Information About Your Spouse", "p3_1a_family_name", "1.a. Spouse's Family Name (Last Name)", "text", True),
    ("Part 3. Information About Your Spouse", "p3_1b_given_name", "1.b. Spouse's Given Name (First Name)", "text", True),
    ("Part 3. Information About Your Spouse", "p3_1c_middle_name", "1.c. Spouse's Middle Name", "text", False),
    ("Part 3. Information About Your Spouse", "p3_2_a_number", "2. Spouse's Alien Registration Number (A-Number) (if any)", "text", False),
    ("Part 3. Information About Your Spouse", "p3_3_uscis_account", "3. Spouse's USCIS Online Account Number (if any)", "text", False),
    ("Part 3. Information About Your Spouse", "p3_4_dob", "4. Spouse's Date of Birth (mm/dd/yyyy)", "date", True),
    ("Part 3. Information About Your Spouse", "p3_5_ssn", "5. Spouse's U.S. Social Security Number (if any)", "text", False),
    ("Part 3. Information About Your Spouse", "p3_6_country_of_birth", "6. Spouse's Country of Birth", "text", False),
    ("Part 3. Information About Your Spouse", "p3_7_country_of_citizenship", "7. Spouse's Country of Citizenship or Nationality", "text", False),
    ("Part 3. Information About Your Spouse", "p3_8_immigration_status", "8. Spouse's Current Immigration Status", "text", False),

    # Spouse Address
    ("Part 3. Spouse's Address", "p3_9a_street", "9.a. Spouse's Street Number and Name", "text", False),
    ("Part 3. Spouse's Address", "p3_9b_apt_type", "9.b. Apt./Ste./Flr.", "select", False),
    ("Part 3. Spouse's Address", "p3_9b_apt_number", "9.b. Number", "text", False),
    ("Part 3. Spouse's Address", "p3_9c_city", "9.c. City or Town", "text", False),
    ("Part 3. Spouse's Address", "p3_9d_state", "9.d. State", "select", False),
    ("Part 3. Spouse's Address", "p3_9e_zip", "9.e. ZIP Code", "text", False),
    ("Part 3. Spouse's Address", "p3_9f_province", "9.f. Province (if applicable)", "text", False),
    ("Part 3. Spouse's Address", "p3_9g_postal_code", "9.g. Postal Code (if applicable)", "text", False),
    ("Part 3. Spouse's Address", "p3_9h_country", "9.h. Country (if outside U.S.)", "text", False),

    # Spouse Employment
    ("Part 3. Spouse's Employment", "p3_10_employer_name", "10. Spouse's Employer or Company Name (if any)", "text", False),
    ("Part 3. Spouse's Employment", "p3_11a_employer_street", "11.a. Spouse's Employer Street Number and Name", "text", False),
    ("Part 3. Spouse's Employment", "p3_11b_employer_city", "11.b. Spouse's Employer City or Town", "text", False),
    ("Part 3. Spouse's Employment", "p3_11c_employer_state", "11.c. Spouse's Employer State", "text", False),
    ("Part 3. Spouse's Employment", "p3_11d_employer_zip", "11.d. Spouse's Employer ZIP Code", "text", False),

    # =========================================================================
    # PART 4: INFORMATION ABOUT YOUR CHILDREN (Pages 4-5)
    # =========================================================================
    ("Part 4. Information About Your Children", "p4_1_has_children", "1. Do you have any children?", "select", True),

    # Child 1
    ("Part 4. Child 1", "p4_2a_child1_family", "2.a. Child 1 - Family Name", "text", False),
    ("Part 4. Child 1", "p4_2b_child1_given", "2.b. Child 1 - Given Name", "text", False),
    ("Part 4. Child 1", "p4_2c_child1_middle", "2.c. Child 1 - Middle Name", "text", False),
    ("Part 4. Child 1", "p4_3_child1_a_number", "3. Child 1 - A-Number (if any)", "text", False),
    ("Part 4. Child 1", "p4_4_child1_dob", "4. Child 1 - Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 4. Child 1", "p4_5_child1_country_of_birth", "5. Child 1 - Country of Birth", "text", False),
    ("Part 4. Child 1", "p4_6_child1_included", "6. Child 1 - Is this child included in this petition?", "select", False),

    # Child 2
    ("Part 4. Child 2", "p4_7a_child2_family", "7.a. Child 2 - Family Name", "text", False),
    ("Part 4. Child 2", "p4_7b_child2_given", "7.b. Child 2 - Given Name", "text", False),
    ("Part 4. Child 2", "p4_7c_child2_middle", "7.c. Child 2 - Middle Name", "text", False),
    ("Part 4. Child 2", "p4_8_child2_a_number", "8. Child 2 - A-Number (if any)", "text", False),
    ("Part 4. Child 2", "p4_9_child2_dob", "9. Child 2 - Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 4. Child 2", "p4_10_child2_country_of_birth", "10. Child 2 - Country of Birth", "text", False),
    ("Part 4. Child 2", "p4_11_child2_included", "11. Child 2 - Is this child included in this petition?", "select", False),

    # Child 3
    ("Part 4. Child 3", "p4_12a_child3_family", "12.a. Child 3 - Family Name", "text", False),
    ("Part 4. Child 3", "p4_12b_child3_given", "12.b. Child 3 - Given Name", "text", False),
    ("Part 4. Child 3", "p4_12c_child3_middle", "12.c. Child 3 - Middle Name", "text", False),
    ("Part 4. Child 3", "p4_13_child3_a_number", "13. Child 3 - A-Number (if any)", "text", False),
    ("Part 4. Child 3", "p4_14_child3_dob", "14. Child 3 - Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 4. Child 3", "p4_15_child3_country_of_birth", "15. Child 3 - Country of Birth", "text", False),
    ("Part 4. Child 3", "p4_16_child3_included", "16. Child 3 - Is this child included in this petition?", "select", False),

    # =========================================================================
    # PART 5: WAIVER OF JOINT FILING REQUIREMENT (Pages 5-6)
    # =========================================================================
    ("Part 5. Waiver of Joint Filing Requirement", "p5_1_waiver_basis", "1. Basis for waiver of the joint filing requirement", "select", False),
    ("Part 5. Waiver of Joint Filing Requirement", "p5_1a_terminated_death", "1.a. Spouse is deceased", "checkbox", False),
    ("Part 5. Waiver of Joint Filing Requirement", "p5_1b_terminated_divorce", "1.b. Good-faith marriage terminated through divorce/annulment", "checkbox", False),
    ("Part 5. Waiver of Joint Filing Requirement", "p5_1c_battery_cruelty", "1.c. Subject to battery or extreme cruelty by U.S. citizen/LPR spouse", "checkbox", False),
    ("Part 5. Waiver of Joint Filing Requirement", "p5_1d_extreme_hardship", "1.d. Removal would result in extreme hardship", "checkbox", False),

    # If spouse deceased
    ("Part 5. Spouse Deceased Info", "p5_2_spouse_death_date", "2. Date of Spouse's Death (mm/dd/yyyy)", "date", False),
    ("Part 5. Spouse Deceased Info", "p5_3_spouse_death_city", "3. City/Town Where Spouse Died", "text", False),
    ("Part 5. Spouse Deceased Info", "p5_4_spouse_death_state", "4. State/Province Where Spouse Died", "text", False),
    ("Part 5. Spouse Deceased Info", "p5_5_spouse_death_country", "5. Country Where Spouse Died", "text", False),

    # If divorce/annulment
    ("Part 5. Divorce/Annulment Info", "p5_6_divorce_date", "6. Date of Divorce/Annulment (mm/dd/yyyy)", "date", False),
    ("Part 5. Divorce/Annulment Info", "p5_7_divorce_city", "7. City/Town Where Divorce Was Granted", "text", False),
    ("Part 5. Divorce/Annulment Info", "p5_8_divorce_state", "8. State/Province Where Divorce Was Granted", "text", False),
    ("Part 5. Divorce/Annulment Info", "p5_9_divorce_country", "9. Country Where Divorce Was Granted", "text", False),

    # Good faith marriage evidence
    ("Part 5. Good Faith Marriage", "p5_10_good_faith_explain", "10. Explain how your marriage was entered into in good faith", "textarea", False),

    # Battery / extreme cruelty
    ("Part 5. Battery/Cruelty", "p5_11_battery_explain", "11. Describe the battery or extreme cruelty", "textarea", False),

    # =========================================================================
    # PART 6: APPLICANT'S STATEMENT, CONTACT, DECLARATION, AND SIGNATURE (Pages 6-7)
    # =========================================================================
    ("Part 6. Applicant's Statement, Contact, Declaration, and Signature", "p6_1_language_read", "1. I can read and understand English", "checkbox", False),
    ("Part 6. Applicant's Statement, Contact, Declaration, and Signature", "p6_1b_interpreter_used", "1.b. The interpreter named in Part 7 read to me every question and instruction in a language I understand", "checkbox", False),
    ("Part 6. Applicant's Statement, Contact, Declaration, and Signature", "p6_2_preparer_used", "2. At my request, the preparer named in Part 8 prepared this petition for me", "checkbox", False),
    ("Part 6. Applicant's Statement, Contact, Declaration, and Signature", "p6_3a_daytime_phone", "3.a. Applicant's Daytime Telephone Number", "phone", False),
    ("Part 6. Applicant's Statement, Contact, Declaration, and Signature", "p6_3b_mobile_phone", "3.b. Applicant's Mobile Telephone Number", "phone", False),
    ("Part 6. Applicant's Statement, Contact, Declaration, and Signature", "p6_3c_email", "3.c. Applicant's Email Address", "email", False),
    ("Part 6. Applicant's Statement, Contact, Declaration, and Signature", "p6_4_signature", "4. Applicant's Signature", "text", False),
    ("Part 6. Applicant's Statement, Contact, Declaration, and Signature", "p6_5_signature_date", "5. Date of Signature (mm/dd/yyyy)", "date", False),

    # Spouse's signature (for joint filing)
    ("Part 6. Spouse's Signature", "p6_6_spouse_signature", "6. Spouse's Signature (if joint filing)", "text", False),
    ("Part 6. Spouse's Signature", "p6_7_spouse_signature_date", "7. Spouse's Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 7: INTERPRETER'S CONTACT INFORMATION (Pages 7-8)
    # =========================================================================
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_1a_family_name", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_1b_given_name", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_2_business_name", "2. Interpreter's Business or Organization Name (if any)", "text", False),
    ("Part 7. Interpreter's Contact Information, Certification, and Signature", "p7_3a_street", "3.a. Street Number and Name", "text", False),
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
    # PART 8: CONTACT INFORMATION, DECLARATION, AND SIGNATURE OF PREPARER (Pages 8-9)
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
    # PART 9: ADDITIONAL INFORMATION (Page 10)
    # =========================================================================
    ("Part 9. Additional Information", "p9_1a_page_number", "1.a. Page Number", "text", False),
    ("Part 9. Additional Information", "p9_1b_part_number", "1.b. Part Number", "text", False),
    ("Part 9. Additional Information", "p9_1c_item_number", "1.c. Item Number", "text", False),
    ("Part 9. Additional Information", "p9_1d_additional_info", "1.d. Additional Information", "textarea", False),
    ("Part 9. Additional Information", "p9_2a_page_number", "2.a. Page Number", "text", False),
    ("Part 9. Additional Information", "p9_2b_part_number", "2.b. Part Number", "text", False),
    ("Part 9. Additional Information", "p9_2c_item_number", "2.c. Item Number", "text", False),
    ("Part 9. Additional Information", "p9_2d_additional_info", "2.d. Additional Information", "textarea", False),
]

OPTIONS_MAP = {
    "p1_12c_apt_type": ["Apt.", "Ste.", "Flr."],
    "p1_13b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p3_9b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p7_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p8_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p2_1_basis": ["Marriage to U.S. Citizen", "Marriage to Lawful Permanent Resident"],
    "p2_2_filing_type": ["Joint Filing (with spouse)", "Waiver - Spouse is Deceased", "Waiver - Good-faith Marriage Terminated", "Waiver - Battery or Extreme Cruelty", "Waiver - Extreme Hardship"],
    "p2_10_currently_married": ["Yes", "No"],
    "p2_11_living_together": ["Yes", "No"],
    "p4_1_has_children": ["Yes", "No"],
    "p4_6_child1_included": ["Yes", "No"],
    "p4_11_child2_included": ["Yes", "No"],
    "p4_16_child3_included": ["Yes", "No"],
    "p8_5_is_attorney": ["Yes", "No"],
}


def expand():
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-751%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
        ))
        row = result.fetchone()
        if not row:
            print("I-751 template not found!")
            return
        tid = row[0]
        print(f"Found I-751 template id={tid}")

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": tid})

        for i, (section, fname, label, ftype, req) in enumerate(I751_FIELDS, 1):
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
        print(f"Expanded I-751: {len(I751_FIELDS)} fields inserted for template {tid}")


if __name__ == "__main__":
    expand()
