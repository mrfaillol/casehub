#!/usr/bin/env python3
"""
Expand I-829 (Petition by Investor to Remove Conditions on Permanent Resident Status)
with ALL official USCIS fields.
Edition 12/23/22 - 11 pages, Parts 1-8.
EB-5 investors use this to remove conditions after 2 years of conditional residence.
"""
import json
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I829_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT YOU (Pages 1-3)
    # =========================================================================
    ("Part 1. Information About You", "p1_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("Part 1. Information About You", "p1_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("Part 1. Information About You", "p1_1c_middle_name", "1.c. Middle Name", "text", False),
    ("Part 1. Other Names Used", "p1_2a_family_name", "2.a. Other Family Names Used (if any)", "text", False),
    ("Part 1. Other Names Used", "p1_2b_given_name", "2.b. Other Given Names Used (if any)", "text", False),
    ("Part 1. Other Names Used", "p1_2c_middle_name", "2.c. Other Middle Names Used (if any)", "text", False),
    ("Part 1. Information About You", "p1_3_dob", "3. Date of Birth (mm/dd/yyyy)", "date", True),
    ("Part 1. Information About You", "p1_4_country_of_birth", "4. Country of Birth", "text", True),
    ("Part 1. Information About You", "p1_5_country_of_citizenship", "5. Country of Citizenship or Nationality", "text", True),
    ("Part 1. Information About You", "p1_6_gender_male", "6. Gender - Male", "radio", False),
    ("Part 1. Information About You", "p1_6_gender_female", "6. Gender - Female", "radio", False),
    ("Part 1. Information About You", "p1_7_a_number", "7. Alien Registration Number (A-Number)", "text", True),
    ("Part 1. Information About You", "p1_8_uscis_account", "8. USCIS Online Account Number (if any)", "text", False),
    ("Part 1. Information About You", "p1_9_ssn", "9. U.S. Social Security Number (if any)", "text", False),

    # Mailing Address
    ("Part 1. Mailing Address", "p1_10a_in_care_of", "10.a. In Care Of Name (if any)", "text", False),
    ("Part 1. Mailing Address", "p1_10b_street", "10.b. Street Number and Name", "text", True),
    ("Part 1. Mailing Address", "p1_10c_apt_type", "10.c. Apt./Ste./Flr.", "select", False),
    ("Part 1. Mailing Address", "p1_10c_apt_number", "10.c. Number", "text", False),
    ("Part 1. Mailing Address", "p1_10d_city", "10.d. City or Town", "text", True),
    ("Part 1. Mailing Address", "p1_10e_state", "10.e. State", "select", True),
    ("Part 1. Mailing Address", "p1_10f_zip", "10.f. ZIP Code", "text", True),

    # Physical Address
    ("Part 1. Physical Address", "p1_11a_street", "11.a. Street Number and Name (if different from mailing)", "text", False),
    ("Part 1. Physical Address", "p1_11b_apt_type", "11.b. Apt./Ste./Flr.", "select", False),
    ("Part 1. Physical Address", "p1_11b_apt_number", "11.b. Number", "text", False),
    ("Part 1. Physical Address", "p1_11c_city", "11.c. City or Town", "text", False),
    ("Part 1. Physical Address", "p1_11d_state", "11.d. State", "select", False),
    ("Part 1. Physical Address", "p1_11e_zip", "11.e. ZIP Code", "text", False),

    # Contact
    ("Part 1. Contact Information", "p1_12_daytime_phone", "12. Daytime Telephone Number", "phone", True),
    ("Part 1. Contact Information", "p1_13_mobile_phone", "13. Mobile Telephone Number (if any)", "phone", False),
    ("Part 1. Contact Information", "p1_14_email", "14. Email Address (if any)", "email", False),

    # Immigration Info
    ("Part 1. Immigration Information", "p1_15_conditional_date", "15. Date You Became a Conditional Permanent Resident (mm/dd/yyyy)", "date", True),
    ("Part 1. Immigration Information", "p1_16_i526_receipt", "16. Receipt Number of Your Approved I-526 Petition", "text", False),
    ("Part 1. Immigration Information", "p1_17_port_of_entry", "17. Port of Entry Where You Were Admitted as Conditional Resident", "text", False),
    ("Part 1. Immigration Information", "p1_18_class_of_admission", "18. Class of Admission as Conditional Resident", "text", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT YOUR INVESTMENT (Pages 3-5)
    # =========================================================================
    ("Part 2. Information About Your Investment", "p2_1_investment_type", "1. Type of Investment", "select", True),
    ("Part 2. Information About Your Investment", "p2_2_total_invested", "2. Total Amount of Capital Invested (USD)", "text", True),
    ("Part 2. Information About Your Investment", "p2_3_source_of_funds", "3. Source of Investment Funds", "textarea", True),
    ("Part 2. Information About Your Investment", "p2_4_investment_date", "4. Date of Initial Investment (mm/dd/yyyy)", "date", True),

    # Investment Entity
    ("Part 2. Investment Entity", "p2_5_entity_name", "5. Name of Commercial Enterprise", "text", True),
    ("Part 2. Investment Entity", "p2_6a_entity_street", "6.a. Street Number and Name", "text", True),
    ("Part 2. Investment Entity", "p2_6b_apt_type", "6.b. Ste./Flr.", "select", False),
    ("Part 2. Investment Entity", "p2_6b_apt_number", "6.b. Number", "text", False),
    ("Part 2. Investment Entity", "p2_6c_city", "6.c. City or Town", "text", True),
    ("Part 2. Investment Entity", "p2_6d_state", "6.d. State", "select", True),
    ("Part 2. Investment Entity", "p2_6e_zip", "6.e. ZIP Code", "text", True),
    ("Part 2. Investment Entity", "p2_7_entity_type", "7. Type of Business Entity", "text", False),
    ("Part 2. Investment Entity", "p2_8_ein", "8. Employer Identification Number (EIN)", "text", False),
    ("Part 2. Investment Entity", "p2_9_naics", "9. NAICS Code", "text", False),
    ("Part 2. Investment Entity", "p2_10_date_established", "10. Date Enterprise Was Established (mm/dd/yyyy)", "date", False),
    ("Part 2. Investment Entity", "p2_11_your_role", "11. Your Role in the Enterprise", "text", False),

    # Job Creation
    ("Part 2. Job Creation", "p2_12_jobs_required", "12. Number of Full-Time Jobs Required to Be Created", "number", True),
    ("Part 2. Job Creation", "p2_13_jobs_created_direct", "13. Number of Direct Full-Time Jobs Created to Date", "number", True),
    ("Part 2. Job Creation", "p2_14_jobs_created_indirect", "14. Number of Indirect Full-Time Jobs Created to Date (if applicable)", "number", False),
    ("Part 2. Job Creation", "p2_15_total_employees", "15. Current Total Number of Employees", "number", False),
    ("Part 2. Job Creation", "p2_16_employees_at_start", "16. Number of Employees When You Made Your Investment", "number", False),

    # TEA
    ("Part 2. Targeted Employment Area", "p2_17_tea_claimed", "17. Was the investment made in a Targeted Employment Area (TEA)?", "select", False),
    ("Part 2. Targeted Employment Area", "p2_18_tea_type", "18. Type of TEA", "select", False),
    ("Part 2. Targeted Employment Area", "p2_19_tea_designation", "19. TEA Designation Authority (state or federal)", "text", False),

    # Regional Center
    ("Part 2. Regional Center", "p2_20_regional_center", "20. Did you invest through an approved Regional Center?", "select", False),
    ("Part 2. Regional Center", "p2_21_rc_name", "21. Regional Center Name", "text", False),
    ("Part 2. Regional Center", "p2_22_rc_id", "22. Regional Center USCIS ID Number", "text", False),

    # Additional Investment Details
    ("Part 2. Additional Investment Details", "p2_23_sustained_investment", "23. Has your investment been sustained throughout the period of conditional residence?", "select", True),
    ("Part 2. Additional Investment Details", "p2_24_investment_at_risk", "24. Is your investment currently at risk for the purpose of generating a return?", "select", True),
    ("Part 2. Additional Investment Details", "p2_25_investment_changes", "25. Describe any changes to your investment since your conditional residence was granted", "textarea", False),
    ("Part 2. Additional Investment Details", "p2_26_business_tax_returns", "26. Have you filed all required tax returns for the commercial enterprise?", "select", True),

    # =========================================================================
    # PART 3: FAMILY MEMBERS (Pages 5-6)
    # =========================================================================
    ("Part 3. Information About Family Members", "p3_1_has_dependents", "1. Do you have any dependents (spouse or children) who were granted conditional residence based on your investment?", "select", True),

    # Spouse
    ("Part 3. Spouse Information", "p3_2a_spouse_family", "2.a. Spouse's Family Name (Last Name)", "text", False),
    ("Part 3. Spouse Information", "p3_2b_spouse_given", "2.b. Spouse's Given Name (First Name)", "text", False),
    ("Part 3. Spouse Information", "p3_2c_spouse_middle", "2.c. Spouse's Middle Name", "text", False),
    ("Part 3. Spouse Information", "p3_3_spouse_a_number", "3. Spouse's A-Number (if any)", "text", False),
    ("Part 3. Spouse Information", "p3_4_spouse_dob", "4. Spouse's Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 3. Spouse Information", "p3_5_spouse_country_of_birth", "5. Spouse's Country of Birth", "text", False),
    ("Part 3. Spouse Information", "p3_6_spouse_included", "6. Is your spouse included in this petition?", "select", False),

    # Child 1
    ("Part 3. Child 1", "p3_7a_child1_family", "7.a. Child 1 - Family Name", "text", False),
    ("Part 3. Child 1", "p3_7b_child1_given", "7.b. Child 1 - Given Name", "text", False),
    ("Part 3. Child 1", "p3_7c_child1_middle", "7.c. Child 1 - Middle Name", "text", False),
    ("Part 3. Child 1", "p3_8_child1_a_number", "8. Child 1 - A-Number (if any)", "text", False),
    ("Part 3. Child 1", "p3_9_child1_dob", "9. Child 1 - Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 3. Child 1", "p3_10_child1_country_of_birth", "10. Child 1 - Country of Birth", "text", False),
    ("Part 3. Child 1", "p3_11_child1_included", "11. Child 1 - Is this child included in this petition?", "select", False),

    # Child 2
    ("Part 3. Child 2", "p3_12a_child2_family", "12.a. Child 2 - Family Name", "text", False),
    ("Part 3. Child 2", "p3_12b_child2_given", "12.b. Child 2 - Given Name", "text", False),
    ("Part 3. Child 2", "p3_12c_child2_middle", "12.c. Child 2 - Middle Name", "text", False),
    ("Part 3. Child 2", "p3_13_child2_a_number", "13. Child 2 - A-Number (if any)", "text", False),
    ("Part 3. Child 2", "p3_14_child2_dob", "14. Child 2 - Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 3. Child 2", "p3_15_child2_country_of_birth", "15. Child 2 - Country of Birth", "text", False),
    ("Part 3. Child 2", "p3_16_child2_included", "16. Child 2 - Is this child included in this petition?", "select", False),

    # =========================================================================
    # PART 4: PETITIONER'S STATEMENT, CONTACT, DECLARATION, AND SIGNATURE (Pages 7-8)
    # =========================================================================
    ("Part 4. Petitioner's Statement, Contact, Declaration, and Signature", "p4_1_language_read", "1. I can read and understand English", "checkbox", False),
    ("Part 4. Petitioner's Statement, Contact, Declaration, and Signature", "p4_1b_interpreter_used", "1.b. The interpreter named in Part 5 read to me every question and instruction in a language I understand", "checkbox", False),
    ("Part 4. Petitioner's Statement, Contact, Declaration, and Signature", "p4_2_preparer_used", "2. At my request, the preparer named in Part 6 prepared this petition for me", "checkbox", False),
    ("Part 4. Petitioner's Statement, Contact, Declaration, and Signature", "p4_3a_daytime_phone", "3.a. Petitioner's Daytime Telephone Number", "phone", False),
    ("Part 4. Petitioner's Statement, Contact, Declaration, and Signature", "p4_3b_mobile_phone", "3.b. Petitioner's Mobile Telephone Number", "phone", False),
    ("Part 4. Petitioner's Statement, Contact, Declaration, and Signature", "p4_3c_email", "3.c. Petitioner's Email Address", "email", False),
    ("Part 4. Petitioner's Statement, Contact, Declaration, and Signature", "p4_4_signature", "4. Petitioner's Signature", "text", False),
    ("Part 4. Petitioner's Statement, Contact, Declaration, and Signature", "p4_5_signature_date", "5. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 5: INTERPRETER'S CONTACT INFORMATION (Pages 8-9)
    # =========================================================================
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_1a_family_name", "1.a. Interpreter's Family Name (Last Name)", "text", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_1b_given_name", "1.b. Interpreter's Given Name (First Name)", "text", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_2_business_name", "2. Interpreter's Business or Organization Name (if any)", "text", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_3a_street", "3.a. Street Number and Name", "text", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_3b_apt_number", "3.b. Number", "text", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_3c_city", "3.c. City or Town", "text", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_3d_state", "3.d. State", "select", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_3f_province", "3.f. Province (if applicable)", "text", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_3g_postal_code", "3.g. Postal Code (if applicable)", "text", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_3h_country", "3.h. Country", "text", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_4a_daytime_phone", "4.a. Interpreter's Daytime Telephone Number", "phone", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_4b_mobile_phone", "4.b. Interpreter's Mobile Telephone Number", "phone", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_4c_email", "4.c. Interpreter's Email Address", "email", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_5_language", "5. Language Interpreted", "text", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_6_signature", "6. Interpreter's Signature", "text", False),
    ("Part 5. Interpreter's Contact Information, Certification, and Signature", "p5_7_signature_date", "7. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 6: CONTACT INFORMATION, DECLARATION, AND SIGNATURE OF PREPARER (Pages 9-10)
    # =========================================================================
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_1a_family_name", "1.a. Preparer's Family Name (Last Name)", "text", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_1b_given_name", "1.b. Preparer's Given Name (First Name)", "text", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_2_business_name", "2. Preparer's Business or Organization Name (if any)", "text", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_3a_street", "3.a. Preparer's Street Number and Name", "text", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_3b_apt_type", "3.b. Apt./Ste./Flr.", "select", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_3b_apt_number", "3.b. Number", "text", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_3c_city", "3.c. City or Town", "text", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_3d_state", "3.d. State", "select", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_3e_zip", "3.e. ZIP Code", "text", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_3f_province", "3.f. Province (if applicable)", "text", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_3g_postal_code", "3.g. Postal Code (if applicable)", "text", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_3h_country", "3.h. Country", "text", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_4a_daytime_phone", "4.a. Preparer's Daytime Telephone Number", "phone", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_4b_mobile_phone", "4.b. Preparer's Mobile Telephone Number", "phone", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_4c_email", "4.c. Preparer's Email Address", "email", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_5_is_attorney", "5. Is the preparer an attorney or accredited representative?", "select", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_6_signature", "6. Preparer's Signature", "text", False),
    ("Part 6. Contact Information, Declaration, and Signature of Person Preparing this Petition", "p6_7_signature_date", "7. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 7: ADDITIONAL INFORMATION (Pages 10-11)
    # =========================================================================
    ("Part 7. Additional Information", "p7_1a_page_number", "1.a. Page Number", "text", False),
    ("Part 7. Additional Information", "p7_1b_part_number", "1.b. Part Number", "text", False),
    ("Part 7. Additional Information", "p7_1c_item_number", "1.c. Item Number", "text", False),
    ("Part 7. Additional Information", "p7_1d_additional_info", "1.d. Additional Information", "textarea", False),
    ("Part 7. Additional Information", "p7_2a_page_number", "2.a. Page Number", "text", False),
    ("Part 7. Additional Information", "p7_2b_part_number", "2.b. Part Number", "text", False),
    ("Part 7. Additional Information", "p7_2c_item_number", "2.c. Item Number", "text", False),
    ("Part 7. Additional Information", "p7_2d_additional_info", "2.d. Additional Information", "textarea", False),
]

OPTIONS_MAP = {
    "p1_10c_apt_type": ["Apt.", "Ste.", "Flr."],
    "p1_11b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p2_6b_apt_type": ["Ste.", "Flr."],
    "p5_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p6_3b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p2_1_investment_type": ["New Commercial Enterprise", "Existing Business (Restructured/Reorganized)", "Troubled Business"],
    "p2_17_tea_claimed": ["Yes", "No"],
    "p2_18_tea_type": ["High Unemployment Area", "Rural Area"],
    "p2_20_regional_center": ["Yes", "No"],
    "p2_23_sustained_investment": ["Yes", "No"],
    "p2_24_investment_at_risk": ["Yes", "No"],
    "p2_26_business_tax_returns": ["Yes", "No"],
    "p3_1_has_dependents": ["Yes", "No"],
    "p3_6_spouse_included": ["Yes", "No"],
    "p3_11_child1_included": ["Yes", "No"],
    "p3_16_child2_included": ["Yes", "No"],
    "p6_5_is_attorney": ["Yes", "No"],
}


def expand():
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-829%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
        ))
        row = result.fetchone()
        if not row:
            print("I-829 template not found!")
            return
        tid = row[0]
        print(f"Found I-829 template id={tid}")

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": tid})

        for i, (section, fname, label, ftype, req) in enumerate(I829_FIELDS, 1):
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
        print(f"Expanded I-829: {len(I829_FIELDS)} fields inserted for template {tid}")


if __name__ == "__main__":
    expand()
