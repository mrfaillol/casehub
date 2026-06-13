#!/usr/bin/env python3
"""
Expand N-600K (Application for Citizenship and Issuance of Certificate Under Section 322)
with ALL official USCIS fields.
Edition 02/04/19 - 10 pages, Parts 1-8.
Used by children of U.S. citizens who regularly reside outside the United States.
"""
import json
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

N600K_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT THE CHILD (Pages 1-2)
    # =========================================================================
    ("Part 1. Information About the Child", "p1_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("Part 1. Information About the Child", "p1_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("Part 1. Information About the Child", "p1_1c_middle_name", "1.c. Middle Name", "text", False),
    ("Part 1. Other Names Used", "p1_2a_family_name", "2.a. Other Family Names Used (if any)", "text", False),
    ("Part 1. Other Names Used", "p1_2b_given_name", "2.b. Other Given Names Used (if any)", "text", False),
    ("Part 1. Other Names Used", "p1_2c_middle_name", "2.c. Other Middle Names Used (if any)", "text", False),
    ("Part 1. Information About the Child", "p1_3_dob", "3. Date of Birth (mm/dd/yyyy)", "date", True),
    ("Part 1. Information About the Child", "p1_4_gender_male", "4. Gender - Male", "radio", False),
    ("Part 1. Information About the Child", "p1_4_gender_female", "4. Gender - Female", "radio", False),
    ("Part 1. Information About the Child", "p1_5_city_of_birth", "5. City/Town/Village of Birth", "text", True),
    ("Part 1. Information About the Child", "p1_6_state_of_birth", "6. State/Province of Birth", "text", False),
    ("Part 1. Information About the Child", "p1_7_country_of_birth", "7. Country of Birth", "text", True),
    ("Part 1. Information About the Child", "p1_8_country_of_citizenship", "8. Country of Citizenship or Nationality", "text", True),
    ("Part 1. Information About the Child", "p1_9_a_number", "9. Alien Registration Number (A-Number) (if any)", "text", False),
    ("Part 1. Information About the Child", "p1_10_uscis_account", "10. USCIS Online Account Number (if any)", "text", False),
    ("Part 1. Information About the Child", "p1_11_ssn", "11. U.S. Social Security Number (if any)", "text", False),
    ("Part 1. Information About the Child", "p1_12_is_lpr", "12. Is the child a lawful permanent resident?", "select", False),
    ("Part 1. Information About the Child", "p1_13_lpr_date", "13. Date Child Became an LPR (mm/dd/yyyy)", "date", False),

    # Child's Address
    ("Part 1. Child's Address Abroad", "p1_14a_street", "14.a. Street Number and Name", "text", True),
    ("Part 1. Child's Address Abroad", "p1_14b_apt_type", "14.b. Apt./Ste./Flr.", "select", False),
    ("Part 1. Child's Address Abroad", "p1_14b_apt_number", "14.b. Number", "text", False),
    ("Part 1. Child's Address Abroad", "p1_14c_city", "14.c. City or Town", "text", True),
    ("Part 1. Child's Address Abroad", "p1_14d_province", "14.d. Province", "text", False),
    ("Part 1. Child's Address Abroad", "p1_14e_postal_code", "14.e. Postal Code", "text", False),
    ("Part 1. Child's Address Abroad", "p1_14f_country", "14.f. Country", "text", True),

    # Contact
    ("Part 1. Contact Information", "p1_15_daytime_phone", "15. Daytime Telephone Number", "phone", False),
    ("Part 1. Contact Information", "p1_16_mobile_phone", "16. Mobile Telephone Number", "phone", False),
    ("Part 1. Contact Information", "p1_17_email", "17. Email Address (if any)", "email", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT THE U.S. CITIZEN PARENT (Pages 2-4)
    # =========================================================================
    ("Part 2. Information About the U.S. Citizen Parent", "p2_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("Part 2. Information About the U.S. Citizen Parent", "p2_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("Part 2. Information About the U.S. Citizen Parent", "p2_1c_middle_name", "1.c. Middle Name", "text", False),
    ("Part 2. Information About the U.S. Citizen Parent", "p2_2_dob", "2. Date of Birth (mm/dd/yyyy)", "date", True),
    ("Part 2. Information About the U.S. Citizen Parent", "p2_3_gender_male", "3. Gender - Male", "radio", False),
    ("Part 2. Information About the U.S. Citizen Parent", "p2_3_gender_female", "3. Gender - Female", "radio", False),
    ("Part 2. Information About the U.S. Citizen Parent", "p2_4_city_of_birth", "4. City/Town/Village of Birth", "text", True),
    ("Part 2. Information About the U.S. Citizen Parent", "p2_5_state_of_birth", "5. State/Province of Birth", "text", False),
    ("Part 2. Information About the U.S. Citizen Parent", "p2_6_country_of_birth", "6. Country of Birth", "text", True),
    ("Part 2. Information About the U.S. Citizen Parent", "p2_7_citizenship_how", "7. How did this parent become a U.S. citizen?", "select", True),
    ("Part 2. Information About the U.S. Citizen Parent", "p2_8_ssn", "8. U.S. Social Security Number", "text", False),
    ("Part 2. Information About the U.S. Citizen Parent", "p2_9_is_biological", "9. Relationship to the child", "select", True),

    # Parent's Address
    ("Part 2. Parent's Address", "p2_10a_street", "10.a. Street Number and Name", "text", True),
    ("Part 2. Parent's Address", "p2_10b_apt_type", "10.b. Apt./Ste./Flr.", "select", False),
    ("Part 2. Parent's Address", "p2_10b_apt_number", "10.b. Number", "text", False),
    ("Part 2. Parent's Address", "p2_10c_city", "10.c. City or Town", "text", True),
    ("Part 2. Parent's Address", "p2_10d_state_or_province", "10.d. State/Province", "text", False),
    ("Part 2. Parent's Address", "p2_10e_zip_or_postal", "10.e. ZIP/Postal Code", "text", False),
    ("Part 2. Parent's Address", "p2_10f_country", "10.f. Country", "text", True),

    # Parent's Marital Info
    ("Part 2. Parent's Marital History", "p2_11_times_married", "11. How many times has this parent been married?", "number", False),
    ("Part 2. Parent's Marital History", "p2_12_marriage_to_other_parent_date", "12. Date of Marriage to Child's Other Parent (mm/dd/yyyy)", "date", False),
    ("Part 2. Parent's Marital History", "p2_13_still_married", "13. Are parents still married?", "select", False),

    # Contact
    ("Part 2. Parent's Contact", "p2_14_daytime_phone", "14. Daytime Telephone Number", "phone", False),
    ("Part 2. Parent's Contact", "p2_15_mobile_phone", "15. Mobile Telephone Number", "phone", False),
    ("Part 2. Parent's Contact", "p2_16_email", "16. Email Address", "email", False),

    # =========================================================================
    # PART 3: INFORMATION ABOUT THE U.S. CITIZEN GRANDPARENT (Pages 4-5)
    # =========================================================================
    ("Part 3. Information About the U.S. Citizen Grandparent", "p3_1a_family_name", "1.a. Grandparent's Family Name (Last Name)", "text", False),
    ("Part 3. Information About the U.S. Citizen Grandparent", "p3_1b_given_name", "1.b. Grandparent's Given Name (First Name)", "text", False),
    ("Part 3. Information About the U.S. Citizen Grandparent", "p3_1c_middle_name", "1.c. Grandparent's Middle Name", "text", False),
    ("Part 3. Information About the U.S. Citizen Grandparent", "p3_2_dob", "2. Grandparent's Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 3. Information About the U.S. Citizen Grandparent", "p3_3_gender_male", "3. Gender - Male", "radio", False),
    ("Part 3. Information About the U.S. Citizen Grandparent", "p3_3_gender_female", "3. Gender - Female", "radio", False),
    ("Part 3. Information About the U.S. Citizen Grandparent", "p3_4_city_of_birth", "4. City/Town/Village of Birth", "text", False),
    ("Part 3. Information About the U.S. Citizen Grandparent", "p3_5_state_of_birth", "5. State/Province of Birth", "text", False),
    ("Part 3. Information About the U.S. Citizen Grandparent", "p3_6_country_of_birth", "6. Country of Birth", "text", False),
    ("Part 3. Information About the U.S. Citizen Grandparent", "p3_7_citizenship_how", "7. How did this grandparent become a U.S. citizen?", "select", False),
    ("Part 3. Information About the U.S. Citizen Grandparent", "p3_8_is_deceased", "8. Is this grandparent deceased?", "select", False),
    ("Part 3. Information About the U.S. Citizen Grandparent", "p3_9_relationship", "9. Grandparent's Relationship to the U.S. Citizen Parent", "select", False),

    # =========================================================================
    # PART 4: PHYSICAL PRESENCE INFORMATION (Pages 5-6)
    # =========================================================================
    ("Part 4. Physical Presence Information", "p4_1_parent_physical_presence", "1. Has the U.S. citizen parent been physically present in the U.S. for at least 5 years (2 after age 14)?", "select", True),
    ("Part 4. Physical Presence Information", "p4_2_grandparent_presence", "2. If parent cannot meet presence requirement, has the U.S. citizen grandparent been physically present for 5 years (2 after age 14)?", "select", False),

    # Residence periods - Parent
    ("Part 4. Parent Residence Periods", "p4_3a_parent_res1_from", "3.a. Parent Residence Period 1 - From (mm/dd/yyyy)", "date", False),
    ("Part 4. Parent Residence Periods", "p4_3a_parent_res1_to", "3.a. Parent Residence Period 1 - To (mm/dd/yyyy)", "date", False),
    ("Part 4. Parent Residence Periods", "p4_3b_parent_res2_from", "3.b. Parent Residence Period 2 - From (mm/dd/yyyy)", "date", False),
    ("Part 4. Parent Residence Periods", "p4_3b_parent_res2_to", "3.b. Parent Residence Period 2 - To (mm/dd/yyyy)", "date", False),
    ("Part 4. Parent Residence Periods", "p4_3c_parent_res3_from", "3.c. Parent Residence Period 3 - From (mm/dd/yyyy)", "date", False),
    ("Part 4. Parent Residence Periods", "p4_3c_parent_res3_to", "3.c. Parent Residence Period 3 - To (mm/dd/yyyy)", "date", False),

    # Residence periods - Grandparent
    ("Part 4. Grandparent Residence Periods", "p4_4a_gp_res1_from", "4.a. Grandparent Residence Period 1 - From (mm/dd/yyyy)", "date", False),
    ("Part 4. Grandparent Residence Periods", "p4_4a_gp_res1_to", "4.a. Grandparent Residence Period 1 - To (mm/dd/yyyy)", "date", False),
    ("Part 4. Grandparent Residence Periods", "p4_4b_gp_res2_from", "4.b. Grandparent Residence Period 2 - From (mm/dd/yyyy)", "date", False),
    ("Part 4. Grandparent Residence Periods", "p4_4b_gp_res2_to", "4.b. Grandparent Residence Period 2 - To (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 5: APPLICANT'S/PARENT'S STATEMENT, CONTACT, AND SIGNATURE (Pages 6-7)
    # =========================================================================
    ("Part 5. Applicant's/Parent's Statement, Contact, Declaration, and Signature", "p5_1_language_read", "1. I can read and understand English", "checkbox", False),
    ("Part 5. Applicant's/Parent's Statement, Contact, Declaration, and Signature", "p5_1b_interpreter_used", "1.b. The interpreter named in Part 6 read to me every question in a language I understand", "checkbox", False),
    ("Part 5. Applicant's/Parent's Statement, Contact, Declaration, and Signature", "p5_2_preparer_used", "2. At my request, the preparer named in Part 7 prepared this application for me", "checkbox", False),
    ("Part 5. Applicant's/Parent's Statement, Contact, Declaration, and Signature", "p5_3a_daytime_phone", "3.a. Daytime Telephone Number", "phone", False),
    ("Part 5. Applicant's/Parent's Statement, Contact, Declaration, and Signature", "p5_3b_mobile_phone", "3.b. Mobile Telephone Number", "phone", False),
    ("Part 5. Applicant's/Parent's Statement, Contact, Declaration, and Signature", "p5_3c_email", "3.c. Email Address", "email", False),
    ("Part 5. Applicant's/Parent's Statement, Contact, Declaration, and Signature", "p5_4_signature", "4. Signature", "text", False),
    ("Part 5. Applicant's/Parent's Statement, Contact, Declaration, and Signature", "p5_5_signature_date", "5. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 6: INTERPRETER'S CONTACT INFORMATION (Pages 7-8)
    # =========================================================================
    ("Part 6. Interpreter's Contact Information, Certification, and Signature", "p6_1a_family_name", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("Part 6. Interpreter's Contact Information, Certification, and Signature", "p6_1b_given_name", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("Part 6. Interpreter's Contact Information, Certification, and Signature", "p6_2_business_name", "2. Interpreter's Business or Organization Name (if any)", "text", False),
    ("Part 6. Interpreter's Contact Information, Certification, and Signature", "p6_3a_street", "3.a. Street Number and Name", "text", False),
    ("Part 6. Interpreter's Contact Information, Certification, and Signature", "p6_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 6. Interpreter's Contact Information, Certification, and Signature", "p6_3b_apt_number", "3.b. Number", "text", False),
    ("Part 6. Interpreter's Contact Information, Certification, and Signature", "p6_3c_city", "3.c. City or Town", "text", False),
    ("Part 6. Interpreter's Contact Information, Certification, and Signature", "p6_3d_state", "3.d. State", "select", False),
    ("Part 6. Interpreter's Contact Information, Certification, and Signature", "p6_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 6. Interpreter's Contact Information, Certification, and Signature", "p6_4a_daytime_phone", "4.a. Interpreter's Daytime Telephone Number", "phone", False),
    ("Part 6. Interpreter's Contact Information, Certification, and Signature", "p6_4b_mobile_phone", "4.b. Interpreter's Mobile Telephone Number", "phone", False),
    ("Part 6. Interpreter's Contact Information, Certification, and Signature", "p6_4c_email", "4.c. Interpreter's Email Address", "email", False),
    ("Part 6. Interpreter's Contact Information, Certification, and Signature", "p6_5_language", "5. Language Interpreted", "text", False),
    ("Part 6. Interpreter's Contact Information, Certification, and Signature", "p6_6_signature", "6. Interpreter's Signature", "text", False),
    ("Part 6. Interpreter's Contact Information, Certification, and Signature", "p6_7_signature_date", "7. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 7: CONTACT INFORMATION, DECLARATION, AND SIGNATURE OF PREPARER (Pages 8-9)
    # =========================================================================
    ("Part 7. Contact Information, Declaration, and Signature of Person Preparing this Application", "p7_1a_family_name", "1.a. Preparer's Family Name (Last Name)", "text", False),
    ("Part 7. Contact Information, Declaration, and Signature of Person Preparing this Application", "p7_1b_given_name", "1.b. Preparer's Given Name (First Name)", "text", False),
    ("Part 7. Contact Information, Declaration, and Signature of Person Preparing this Application", "p7_2_business_name", "2. Preparer's Business or Organization Name (if any)", "text", False),
    ("Part 7. Contact Information, Declaration, and Signature of Person Preparing this Application", "p7_3a_street", "3.a. Preparer's Street Number and Name", "text", False),
    ("Part 7. Contact Information, Declaration, and Signature of Person Preparing this Application", "p7_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 7. Contact Information, Declaration, and Signature of Person Preparing this Application", "p7_3b_apt_number", "3.b. Number", "text", False),
    ("Part 7. Contact Information, Declaration, and Signature of Person Preparing this Application", "p7_3c_city", "3.c. City or Town", "text", False),
    ("Part 7. Contact Information, Declaration, and Signature of Person Preparing this Application", "p7_3d_state", "3.d. State", "select", False),
    ("Part 7. Contact Information, Declaration, and Signature of Person Preparing this Application", "p7_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 7. Contact Information, Declaration, and Signature of Person Preparing this Application", "p7_4a_daytime_phone", "4.a. Preparer's Daytime Telephone Number", "phone", False),
    ("Part 7. Contact Information, Declaration, and Signature of Person Preparing this Application", "p7_4b_mobile_phone", "4.b. Preparer's Mobile Telephone Number", "phone", False),
    ("Part 7. Contact Information, Declaration, and Signature of Person Preparing this Application", "p7_4c_email", "4.c. Preparer's Email Address", "email", False),
    ("Part 7. Contact Information, Declaration, and Signature of Person Preparing this Application", "p7_5_is_attorney", "5. Is the preparer an attorney or accredited representative?", "select", False),
    ("Part 7. Contact Information, Declaration, and Signature of Person Preparing this Application", "p7_6_signature", "6. Preparer's Signature", "text", False),
    ("Part 7. Contact Information, Declaration, and Signature of Person Preparing this Application", "p7_7_signature_date", "7. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 8: ADDITIONAL INFORMATION (Page 10)
    # =========================================================================
    ("Part 8. Additional Information", "p8_1a_page_number", "1.a. Page Number", "text", False),
    ("Part 8. Additional Information", "p8_1b_part_number", "1.b. Part Number", "text", False),
    ("Part 8. Additional Information", "p8_1c_item_number", "1.c. Item Number", "text", False),
    ("Part 8. Additional Information", "p8_1d_additional_info", "1.d. Additional Information", "textarea", False),
    ("Part 8. Additional Information", "p8_2a_page_number", "2.a. Page Number", "text", False),
    ("Part 8. Additional Information", "p8_2b_part_number", "2.b. Part Number", "text", False),
    ("Part 8. Additional Information", "p8_2c_item_number", "2.c. Item Number", "text", False),
    ("Part 8. Additional Information", "p8_2d_additional_info", "2.d. Additional Information", "textarea", False),
]

OPTIONS_MAP = {
    "p1_12_is_lpr": ["Yes", "No"],
    "p1_14b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p2_10b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p6_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p7_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p2_7_citizenship_how": ["Birth in the U.S.", "Naturalization", "Birth abroad to U.S. citizen parent(s)", "Other"],
    "p2_9_is_biological": ["Biological Parent", "Adoptive Parent", "Step-Parent"],
    "p2_13_still_married": ["Yes", "No"],
    "p3_7_citizenship_how": ["Birth in the U.S.", "Naturalization", "Birth abroad to U.S. citizen parent(s)", "Other"],
    "p3_8_is_deceased": ["Yes", "No"],
    "p3_9_relationship": ["Father", "Mother"],
    "p4_1_parent_physical_presence": ["Yes", "No"],
    "p4_2_grandparent_presence": ["Yes", "No"],
    "p7_5_is_attorney": ["Yes", "No"],
}


def expand():
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT id FROM questionnaire_templates WHERE name LIKE '%N-600K%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
        ))
        row = result.fetchone()
        if not row:
            print("N-600K template not found!")
            return
        tid = row[0]
        print(f"Found N-600K template id={tid}")

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": tid})

        for i, (section, fname, label, ftype, req) in enumerate(N600K_FIELDS, 1):
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
        print(f"Expanded N-600K: {len(N600K_FIELDS)} fields inserted for template {tid}")


if __name__ == "__main__":
    expand()
