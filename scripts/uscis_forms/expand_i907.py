#!/usr/bin/env python3
"""
Expand I-907 (Request for Premium Processing Service) with ALL official USCIS fields.
Edition 04/01/24 - 7 pages, Parts 1-6.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I907_FIELDS = [
    # =========================================================================
    # HEADER - Attorney/Representative Information (Page 1 top)
    # =========================================================================
    ("Header - Attorney Info", "header_g28_checkbox", "Select this box if Form G-28 or Form G-28I is attached", "checkbox", False),
    ("Header - Attorney Info", "header_attorney_bar_number", "Attorney State Bar Number (if applicable)", "text", False),
    ("Header - Attorney Info", "header_attorney_uscis_account", "Attorney or Accredited Representative USCIS Online Account Number (if any)", "text", False),

    # =========================================================================
    # PART 1: INFORMATION ABOUT THE PERSON FILING THIS REQUEST (Pages 1-2)
    # =========================================================================
    ("1. Person Filing", "p1_1_a_number", "1. Alien Registration Number (A-Number) (if any)", "text", False),
    ("1. Person Filing", "p1_2_uscis_account", "2. USCIS Online Account Number (if any)", "text", False),
    ("1. Person Filing", "p1_3_family_name", "3. Family Name (Last Name)", "text", True),
    ("1. Person Filing", "p1_3_given_name", "3. Given Name (First Name)", "text", True),
    ("1. Person Filing", "p1_3_middle_name", "3. Middle Name", "text", False),
    ("1. Person Filing", "p1_4_company_org", "4. Company or Organization Named in the Related Case (If filed on behalf of a company or organization)", "text", False),

    # Mailing Address
    ("1. Mailing Address", "p1_5_in_care_of", "5. Mailing Address - In Care Of Name", "text", False),
    ("1. Mailing Address", "p1_5_street", "5. Mailing Address - Street Number and Name", "text", True),
    ("1. Mailing Address", "p1_5_apt_type", "5. Mailing Address - Apt./Ste./Flr.", "select", False),
    ("1. Mailing Address", "p1_5_apt_number", "5. Mailing Address - Number", "text", False),
    ("1. Mailing Address", "p1_5_city", "5. Mailing Address - City or Town", "text", True),
    ("1. Mailing Address", "p1_5_state", "5. Mailing Address - State", "select", False),
    ("1. Mailing Address", "p1_5_zip", "5. Mailing Address - ZIP Code", "text", False),
    ("1. Mailing Address", "p1_5_province", "5. Mailing Address - Province", "text", False),
    ("1. Mailing Address", "p1_5_postal_code", "5. Mailing Address - Postal Code", "text", False),
    ("1. Mailing Address", "p1_5_country", "5. Mailing Address - Country", "text", False),
    ("1. Mailing Address", "p1_6_same_physical", "6. Is your current mailing address the same as your physical address?", "radio", True),

    # Physical Address
    ("1. Physical Address", "p1_7_street", "7. Physical Address - Street Number and Name", "text", False),
    ("1. Physical Address", "p1_7_apt_type", "7. Physical Address - Apt./Ste./Flr.", "select", False),
    ("1. Physical Address", "p1_7_apt_number", "7. Physical Address - Number", "text", False),
    ("1. Physical Address", "p1_7_city", "7. Physical Address - City or Town", "text", False),
    ("1. Physical Address", "p1_7_state", "7. Physical Address - State", "select", False),
    ("1. Physical Address", "p1_7_zip", "7. Physical Address - ZIP Code", "text", False),
    ("1. Physical Address", "p1_7_province", "7. Physical Address - Province", "text", False),
    ("1. Physical Address", "p1_7_postal_code", "7. Physical Address - Postal Code", "text", False),
    ("1. Physical Address", "p1_7_country", "7. Physical Address - Country", "text", False),

    # Request Type
    ("1. Request Type", "p1_8_petitioner", "8. I am the petitioner who is filing or has filed a petition eligible for Premium Processing Service", "checkbox", False),
    ("1. Request Type", "p1_8_attorney_petitioner", "8. I am the attorney or accredited representative for the petitioner (Complete and submit Form G-28 or G-28I, if not already submitted)", "checkbox", False),
    ("1. Request Type", "p1_8_applicant", "8. I am the applicant who is filing or has filed an application eligible for Premium Processing Service", "checkbox", False),
    ("1. Request Type", "p1_8_attorney_applicant", "8. I am the attorney or accredited representative for the applicant (Complete and submit Form G-28 or G-28I, if not already submitted)", "checkbox", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT THE REQUEST (Pages 2-3)
    # =========================================================================
    ("2. Request Info", "p2_1_form_number", "1. Form Number of Related Petition or Application", "text", True),
    ("2. Request Info", "p2_2_receipt_number", "2. Receipt Number of Related Petition or Application", "text", False),
    ("2. Request Info", "p2_3_classification", "3. Classification or Eligibility Requested", "text", True),

    # Petitioner or Applicant in the Related Case
    ("2. Petitioner/Applicant", "p2_4_family_name", "4. Petitioner or Applicant in the Related Case - Family Name (Last Name)", "text", True),
    ("2. Petitioner/Applicant", "p2_4_given_name", "4. Petitioner or Applicant in the Related Case - Given Name (First Name)", "text", True),
    ("2. Petitioner/Applicant", "p2_4_middle_name", "4. Petitioner or Applicant in the Related Case - Middle Name", "text", False),

    # Beneficiary in the Related Case
    ("2. Beneficiary", "p2_5_family_name", "5. Beneficiary in the Related Case - Family Name (Last Name)", "text", False),
    ("2. Beneficiary", "p2_5_given_name", "5. Beneficiary in the Related Case - Given Name (First Name)", "text", False),
    ("2. Beneficiary", "p2_5_middle_name", "5. Beneficiary in the Related Case - Middle Name", "text", False),

    # Point of Contact for Company/Organization
    ("2. Point of Contact", "p2_6_family_name", "6. Name of Point of Contact for the Company or Organization - Family Name (Last Name)", "text", False),
    ("2. Point of Contact", "p2_6_given_name", "6. Name of Point of Contact for the Company or Organization - Given Name (First Name)", "text", False),
    ("2. Point of Contact", "p2_6_middle_name", "6. Name of Point of Contact for the Company or Organization - Middle Name", "text", False),
    ("2. Point of Contact", "p2_6_position_title", "6. Position Title", "text", False),

    # Company/Organization Information
    ("2. Company/Organization", "p2_7_ein", "7. Company or Organization IRS Employer Identification Number (EIN) (if any)", "text", False),

    # Address of Petitioner/Applicant/Company/Organization
    ("2. Address", "p2_8_street", "8. Address of Petitioner, Applicant, Company, or Organization Named in Related Case - Street Number and Name", "text", False),
    ("2. Address", "p2_8_apt_type", "8. Address - Apt./Ste./Flr.", "select", False),
    ("2. Address", "p2_8_apt_number", "8. Address - Number", "text", False),
    ("2. Address", "p2_8_city", "8. Address - City or Town", "text", False),
    ("2. Address", "p2_8_state", "8. Address - State", "select", False),
    ("2. Address", "p2_8_zip", "8. Address - ZIP Code", "text", False),
    ("2. Address", "p2_8_province", "8. Address - Province", "text", False),
    ("2. Address", "p2_8_postal_code", "8. Address - Postal Code", "text", False),
    ("2. Address", "p2_8_country", "8. Address - Country", "text", False),

    # =========================================================================
    # PART 3: REQUESTOR'S STATEMENT, CONTACT INFORMATION, DECLARATION, CERTIFICATION, AND SIGNATURE (Pages 3-4)
    # =========================================================================
    # Requestor's Statement
    ("3. Requestor Statement", "p3_1a_english", "1.A. I can read and understand English, and I have read and understand every question and instruction on this request and my answer to every question", "checkbox", False),
    ("3. Requestor Statement", "p3_1b_interpreter", "1.B. The interpreter named in Part 4. read to me every question and instruction on this request and my answer to every question in [language], and I understood everything", "checkbox", False),
    ("3. Requestor Statement", "p3_1b_language", "1.B. Language", "text", False),
    ("3. Requestor Statement", "p3_2_preparer", "2. At my request, the preparer named in Part 5. prepared this request for me based only upon information I provided or authorized", "checkbox", False),

    # Requestor's Contact Information
    ("3. Requestor Contact", "p3_3_phone_day", "3. Requestor's Daytime Telephone Number", "phone", False),
    ("3. Requestor Contact", "p3_4_phone_mobile", "4. Requestor's Mobile Telephone Number (if any)", "phone", False),
    ("3. Requestor Contact", "p3_5_fax", "5. Requestor's Fax Number (if any)", "text", False),
    ("3. Requestor Contact", "p3_6_email", "6. Requestor's Email Address (if any)", "text", False),

    # Requestor's Signature
    ("3. Requestor Signature", "p3_7_signature", "7. Requestor's Signature", "text", True),
    ("3. Requestor Signature", "p3_7_date", "7. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 4: INTERPRETER'S CONTACT INFORMATION, CERTIFICATION, AND SIGNATURE (Page 4)
    # =========================================================================
    # Interpreter's Full Name
    ("4. Interpreter Name", "p4_1_family_name", "1. Interpreter's Family Name (Last Name)", "text", False),
    ("4. Interpreter Name", "p4_1_given_name", "1. Interpreter's Given Name (First Name)", "text", False),
    ("4. Interpreter Name", "p4_2_business_org", "2. Interpreter's Business or Organization Name (if any)", "text", False),

    # Interpreter's Mailing Address
    ("4. Interpreter Address", "p4_3_street", "3. Interpreter's Mailing Address - Street Number and Name", "text", False),
    ("4. Interpreter Address", "p4_3_apt_type", "3. Interpreter's Mailing Address - Apt./Ste./Flr.", "select", False),
    ("4. Interpreter Address", "p4_3_apt_number", "3. Interpreter's Mailing Address - Number", "text", False),
    ("4. Interpreter Address", "p4_3_city", "3. Interpreter's Mailing Address - City or Town", "text", False),
    ("4. Interpreter Address", "p4_3_state", "3. Interpreter's Mailing Address - State", "select", False),
    ("4. Interpreter Address", "p4_3_zip", "3. Interpreter's Mailing Address - ZIP Code", "text", False),
    ("4. Interpreter Address", "p4_3_province", "3. Interpreter's Mailing Address - Province", "text", False),
    ("4. Interpreter Address", "p4_3_postal_code", "3. Interpreter's Mailing Address - Postal Code", "text", False),
    ("4. Interpreter Address", "p4_3_country", "3. Interpreter's Mailing Address - Country", "text", False),

    # Interpreter's Contact Information
    ("4. Interpreter Contact", "p4_4_phone_day", "4. Interpreter's Daytime Telephone Number", "phone", False),
    ("4. Interpreter Contact", "p4_5_phone_mobile", "5. Interpreter's Mobile Telephone Number (if any)", "phone", False),
    ("4. Interpreter Contact", "p4_6_email", "6. Interpreter's Email Address (if any)", "text", False),

    # Interpreter's Certification
    ("4. Interpreter Certification", "p4_cert_language", "I am fluent in English and [language]", "text", False),

    # Interpreter's Signature
    ("4. Interpreter Signature", "p4_7_signature", "7. Interpreter's Signature", "text", False),
    ("4. Interpreter Signature", "p4_7_date", "7. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 5: CONTACT INFORMATION, DECLARATION, AND SIGNATURE OF THE PERSON PREPARING THIS REQUEST, IF OTHER THAN THE REQUESTOR (Pages 5-6)
    # =========================================================================
    # Preparer's Full Name
    ("5. Preparer Name", "p5_1_family_name", "1. Preparer's Family Name (Last Name)", "text", False),
    ("5. Preparer Name", "p5_1_given_name", "1. Preparer's Given Name (First Name)", "text", False),
    ("5. Preparer Name", "p5_2_business_org", "2. Preparer's Business or Organization Name (if any)", "text", False),

    # Preparer's Mailing Address
    ("5. Preparer Address", "p5_3_street", "3. Preparer's Mailing Address - Street Number and Name", "text", False),
    ("5. Preparer Address", "p5_3_apt_type", "3. Preparer's Mailing Address - Apt./Ste./Flr.", "select", False),
    ("5. Preparer Address", "p5_3_apt_number", "3. Preparer's Mailing Address - Number", "text", False),
    ("5. Preparer Address", "p5_3_city", "3. Preparer's Mailing Address - City or Town", "text", False),
    ("5. Preparer Address", "p5_3_state", "3. Preparer's Mailing Address - State", "select", False),
    ("5. Preparer Address", "p5_3_zip", "3. Preparer's Mailing Address - ZIP Code", "text", False),
    ("5. Preparer Address", "p5_3_province", "3. Preparer's Mailing Address - Province", "text", False),
    ("5. Preparer Address", "p5_3_postal_code", "3. Preparer's Mailing Address - Postal Code", "text", False),
    ("5. Preparer Address", "p5_3_country", "3. Preparer's Mailing Address - Country", "text", False),

    # Preparer's Contact Information
    ("5. Preparer Contact", "p5_4_phone_day", "4. Preparer's Daytime Telephone Number", "phone", False),
    ("5. Preparer Contact", "p5_5_phone_mobile", "5. Preparer's Mobile Telephone Number (if any)", "phone", False),
    ("5. Preparer Contact", "p5_6_email", "6. Preparer's Email Address (if any)", "text", False),

    # Preparer's Statement
    ("5. Preparer Statement", "p5_7a_not_attorney", "7.A. I am not an attorney or accredited representative but have prepared this request on behalf of the requestor with the requestor's consent", "checkbox", False),
    ("5. Preparer Statement", "p5_7b_attorney_extends", "7.B. I am an attorney or accredited representative and my representation of the requestor in this case extends", "checkbox", False),
    ("5. Preparer Statement", "p5_7b_attorney_not_extend", "7.B. I am an attorney or accredited representative and my representation does not extend beyond the preparation of this request", "checkbox", False),

    # Preparer's Signature
    ("5. Preparer Signature", "p5_8_signature", "8. Preparer's Signature", "text", False),
    ("5. Preparer Signature", "p5_8_date", "8. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 6: ADDITIONAL INFORMATION (Page 7)
    # =========================================================================
    # Additional Information Section 1
    ("6. Additional Info 1", "p6_1_family_name", "1. Family Name (Last Name)", "text", False),
    ("6. Additional Info 1", "p6_1_given_name", "1. Given Name (First Name)", "text", False),
    ("6. Additional Info 1", "p6_1_middle_name", "1. Middle Name", "text", False),
    ("6. Additional Info 1", "p6_2_a_number", "2. A-Number (if any)", "text", False),
    ("6. Additional Info 1", "p6_3a_page_number", "3.A. Page Number", "text", False),
    ("6. Additional Info 1", "p6_3b_part_number", "3.B. Part Number", "text", False),
    ("6. Additional Info 1", "p6_3c_item_number", "3.C. Item Number", "text", False),
    ("6. Additional Info 1", "p6_3d_additional_info", "3.D. Additional Information", "textarea", False),

    # Additional Information Section 2
    ("6. Additional Info 2", "p6_4a_page_number", "4.A. Page Number", "text", False),
    ("6. Additional Info 2", "p6_4b_part_number", "4.B. Part Number", "text", False),
    ("6. Additional Info 2", "p6_4c_item_number", "4.C. Item Number", "text", False),
    ("6. Additional Info 2", "p6_4d_additional_info", "4.D. Additional Information", "textarea", False),

    # Additional Information Section 3
    ("6. Additional Info 3", "p6_5a_page_number", "5.A. Page Number", "text", False),
    ("6. Additional Info 3", "p6_5b_part_number", "5.B. Part Number", "text", False),
    ("6. Additional Info 3", "p6_5c_item_number", "5.C. Item Number", "text", False),
    ("6. Additional Info 3", "p6_5d_additional_info", "5.D. Additional Information", "textarea", False),
]


def update_i907(template_id=None):
    """Insert or update I-907 fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-907%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('I-907 - Request for Premium Processing Service (EXPANDED)', "
                    "'Complete I-907 with all official USCIS fields - Edition 04/01/24') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(I907_FIELDS):
            conn.execute(text(
                "INSERT INTO questionnaire_fields (template_id, section, field_name, label, field_type, is_required, \"order\") "
                "VALUES (:tid, :section, :field_name, :label, :field_type, :is_required, :order)"
            ), {
                "tid": template_id, "section": section, "field_name": field_name,
                "label": label, "field_type": field_type, "is_required": required, "order": i + 1
            })

        conn.commit()
        print(f"I-907 expanded: template_id={template_id}, fields={len(I907_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_i907()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(I907_FIELDS)}")

    sections = {}
    for section, _, _, _, _ in I907_FIELDS:
        sections[section] = sections.get(section, 0) + 1

    print("\nFields by section:")
    for section, count in sections.items():
        print(f"  {section}: {count}")

    # Check for duplicates
    field_names = [field_name for _, field_name, _, _, _ in I907_FIELDS]
    duplicates = [name for name in field_names if field_names.count(name) > 1]
    if duplicates:
        print(f"\nWARNING: Duplicate field names found: {set(duplicates)}")
    else:
        print("\nNo duplicate field names found.")
