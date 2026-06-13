#!/usr/bin/env python3
"""
Expand I-539 (Application to Extend/Change Nonimmigrant Status) with ALL official USCIS fields.
Edition 08/28/24 - 7 pages, Parts 1-8.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I539_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT YOU (Pages 1-2)
    # =========================================================================
    # Your Full Legal Name
    ("1. Your Full Legal Name", "p1_1_family_name", "Family Name (Last Name)", "text", True),
    ("1. Your Full Legal Name", "p1_1_given_name", "Given Name (First Name)", "text", True),
    ("1. Your Full Legal Name", "p1_1_middle_name", "Middle Name (if applicable)", "text", False),

    # Identification Numbers
    ("1. Identification", "p1_2_a_number", "2. Alien Registration Number (A-Number) (if any)", "text", False),
    ("1. Identification", "p1_3_uscis_account", "3. USCIS Online Account Number (if any)", "text", False),

    # U.S. Mailing Address
    ("1. U.S. Mailing Address", "p1_4_in_care_of", "4. In Care Of Name (if any)", "text", False),
    ("1. U.S. Mailing Address", "p1_4_street", "4. Street Number and Name", "text", True),
    ("1. U.S. Mailing Address", "p1_4_apt", "4. Apt./Ste./Flr.", "select", False),
    ("1. U.S. Mailing Address", "p1_4_number", "4. Number", "text", False),
    ("1. U.S. Mailing Address", "p1_4_city", "4. City or Town", "text", True),
    ("1. U.S. Mailing Address", "p1_4_state", "4. State", "select", True),
    ("1. U.S. Mailing Address", "p1_4_zip", "4. ZIP Code", "text", True),

    # Physical Address
    ("1. Physical Address", "p1_5_same_as_mailing", "5. Is your mailing address the same as your physical address?", "radio", True),
    ("1. Physical Address", "p1_6_street", "6. Your Current Physical Address - Street Number and Name", "text", False),
    ("1. Physical Address", "p1_6_apt", "6. Your Current Physical Address - Apt./Ste./Flr.", "select", False),
    ("1. Physical Address", "p1_6_number", "6. Your Current Physical Address - Number", "text", False),
    ("1. Physical Address", "p1_6_city", "6. Your Current Physical Address - City or Town", "text", False),
    ("1. Physical Address", "p1_6_state", "6. Your Current Physical Address - State", "select", False),
    ("1. Physical Address", "p1_6_zip", "6. Your Current Physical Address - ZIP Code", "text", False),

    # Other Information About You
    ("1. Other Information", "p1_7_country_birth", "7. Country of Birth", "text", True),
    ("1. Other Information", "p1_8_country_citizenship", "8. Country of Citizenship or Nationality", "text", True),
    ("1. Other Information", "p1_9_dob", "9. Date of Birth (mm/dd/yyyy)", "date", True),
    ("1. Other Information", "p1_10_ssn", "10. U.S. Social Security Number (if any)", "text", False),

    # Most Recent Entry Information
    ("1. Most Recent Entry", "p1_11_date_last_arrival", "11. Date of Last Arrival Into the United States (mm/dd/yyyy)", "date", True),
    ("1. Most Recent Entry", "p1_11_i94_number", "11. Form I-94 Arrival-Departure Record Number", "text", False),
    ("1. Most Recent Entry", "p1_11_passport_number", "11. Passport Number (if any)", "text", False),
    ("1. Most Recent Entry", "p1_11_travel_doc_number", "11. Travel Document Number (if any)", "text", False),
    ("1. Most Recent Entry", "p1_11_country_issuance", "11. Country of Passport or Travel Document Issuance", "text", False),
    ("1. Most Recent Entry", "p1_11_passport_expiration", "11. Passport or Travel Document Expiration Date (mm/dd/yyyy)", "date", False),

    # Current Status
    ("1. Current Status", "p1_12_current_status", "12. Current Nonimmigrant Status (for example, F-1 student, H-4 dependent, etc.)", "text", True),
    ("1. Current Status", "p1_12_status_expires", "12. Date Status Expires (mm/dd/yyyy)", "date", False),
    ("1. Current Status", "p1_12_duration_status", "12. Select this box if you were granted Duration of Status (D/S)", "checkbox", False),

    # =========================================================================
    # PART 2: APPLICATION TYPE (Page 2)
    # =========================================================================
    ("2. Application Type", "p2_1_reinstatement", "1. Reinstatement to student status", "checkbox", False),
    ("2. Application Type", "p2_1_extension", "1. An extension of stay in my current status", "checkbox", False),
    ("2. Application Type", "p2_1_change_status", "1. A change of status", "checkbox", False),

    # Change of Status Details
    ("2. Change Details", "p2_2_change_to", "2. I am requesting to change my status or employer/information medium to:", "text", False),
    ("2. Change Details", "p2_2_effective_date", "2. I am requesting the change to be effective medium to: (mm/dd/yyyy)", "date", False),

    # Number of People
    ("2. Number of People", "p2_3_only_applicant", "3. I am the only applicant", "checkbox", False),
    ("2. Number of People", "p2_3_with_family", "3. I am filing this application for myself and members of my family", "checkbox", False),
    ("2. Number of People", "p2_4_total_people", "4. The total number of people (including me) in the application is:", "text", False),

    # School Information
    ("2. School Information", "p2_5_school_name", "5. The name of the school you will attend (if applicable) as an Academic Student, Vocational Student, or Exchange Visitor", "text", False),
    ("2. School Information", "p2_6_sevis_id", "6. Your Student and Exchange Visitor Information System (SEVIS) ID Number, if applicable", "text", False),

    # =========================================================================
    # PART 3: PROCESSING INFORMATION (Pages 2-3)
    # =========================================================================
    ("3. Processing", "p3_1_extend_until", "1. I/We request that my/our current or requested status be extended until (mm/dd/yyyy):", "date", True),
    ("3. Processing", "p3_2_based_on_family", "2. Is this application based on an extension or change of status already granted to your spouse, child, or parent?", "radio", True),
    ("3. Processing", "p3_3_based_on_petition", "3. Is this application based on a separate petition or application to provide your spouse, child, or parent an extension or change of status?", "radio", False),
    ("3. Processing", "p3_3_filed_with_i539", "3. Yes, filed with this Form I-539", "checkbox", False),
    ("3. Processing", "p3_3_no", "3. No", "checkbox", False),
    ("3. Processing", "p3_3_filed_previously", "3. Yes, filed previously and pending with U.S. Citizenship and Immigration Services (USCIS)", "checkbox", False),

    # Related Petition Information
    ("3. Related Petition", "p3_4_form_i539", "4. Form I-539, Application to Extend/Change Nonimmigrant Status", "checkbox", False),
    ("3. Related Petition", "p3_4_form_i129", "4. Form I-129, Petition for a Nonimmigrant Worker", "checkbox", False),
    ("3. Related Petition", "p3_5_receipt_number", "5. If you answered Yes to Item Number 2. or 3., provide the USCIS Receipt Number", "text", False),
    ("3. Related Petition", "p3_6_beneficiary_first_name", "6. First and Last Name of Beneficiary or Applicant - First Name", "text", False),
    ("3. Related Petition", "p3_6_beneficiary_last_name", "6. First and Last Name of Beneficiary or Applicant - Last Name", "text", False),
    ("3. Related Petition", "p3_7_date_filed", "7. Date Filed (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 4: ADDITIONAL INFORMATION ABOUT THE PRINCIPAL APPLICANT (Pages 3-4)
    # =========================================================================
    # Current Passport Information
    ("4. Current Passport", "p4_1_passport_number", "1. Passport Number", "text", False),
    ("4. Current Passport", "p4_1_country_issuance", "1. Country of Passport Issuance", "text", False),
    ("4. Current Passport", "p4_1_expiration_date", "1. Passport Expiration Date (mm/dd/yyyy)", "date", False),

    # Physical Address Abroad
    ("4. Address Abroad", "p4_2_street", "2. Physical Address Abroad - Street Number and Name", "text", False),
    ("4. Address Abroad", "p4_2_apt", "2. Physical Address Abroad - Apt./Ste./Flr.", "select", False),
    ("4. Address Abroad", "p4_2_number", "2. Physical Address Abroad - Number", "text", False),
    ("4. Address Abroad", "p4_2_city", "2. Physical Address Abroad - City or Town", "text", False),
    ("4. Address Abroad", "p4_2_province", "2. Physical Address Abroad - Province", "text", False),
    ("4. Address Abroad", "p4_2_postal_code", "2. Physical Address Abroad - Postal Code", "text", False),
    ("4. Address Abroad", "p4_2_country", "2. Physical Address Abroad - Country", "text", False),

    # Immigration History Questions
    ("4. Immigration History", "p4_3_immigrant_visa_applicant", "3. Are you an applicant for an immigrant visa?", "radio", True),
    ("4. Immigration History", "p4_4_immigrant_petition_filed", "4. Has an immigrant petition EVER been filed for you?", "radio", True),
    ("4. Immigration History", "p4_5_i485_filed", "5. Have you EVER filed Form I-485, Application to Register Permanent Residence or Adjust Status?", "radio", True),
    ("4. Immigration History", "p4_6_arrested_convicted", "6. Have you been arrested or convicted of any criminal offense since last entering the United States?", "radio", True),

    # Criminal and Security Questions
    ("4. Security Questions", "p4_7a_torture_genocide", "7.a. Have you EVER ordered, incited, called for, committed, assisted, helped with, or otherwise participated in: Acts involving torture or genocide?", "radio", True),
    ("4. Security Questions", "p4_7b_killing", "7.b. Killing any person?", "radio", True),
    ("4. Security Questions", "p4_7c_injuring", "7.c. Intentionally and severely injuring any person?", "radio", True),
    ("4. Security Questions", "p4_7d_sexual_contact", "7.d. Engaging in any kind of sexual contact or relations with any person who did not consent or was unable to consent, or was being forced or threatened?", "radio", True),
    ("4. Security Questions", "p4_7e_religious_beliefs", "7.e. Limiting or denying any person's ability to exercise religious beliefs?", "radio", True),

    # Military and Weapons Questions
    ("4. Military Questions", "p4_8a_military_service", "8.a. Have you EVER: Served in, been a member of, assisted, or participated in any military unit, paramilitary unit, police unit, self-defense unit, vigilante unit, rebel group, guerrilla group, militia, insurgent organization, or any other armed group?", "radio", True),
    ("4. Military Questions", "p4_8b_prison_work", "8.b. Worked, volunteered, or otherwise served in any prison, jail, prison camp, detention facility, labor camp, or any other situation that involved detaining persons?", "radio", True),
    ("4. Military Questions", "p4_9_weapons_group", "9. Have you EVER been a member of, assisted, or participated in any group, unit, or organization of any kind in which you or other persons used or threatened to use any type of weapon against any person or threatened to do so?", "radio", True),
    ("4. Military Questions", "p4_10_weapons_transport", "10. Have you EVER sold, provided, or transported weapons, or assisted any person in selling, providing, or transporting weapons, which, you knew or believed would be used against another person?", "radio", True),
    ("4. Military Questions", "p4_11_weapons_training", "11. Have you EVER received any weapons training, paramilitary training, or other military-type training?", "radio", True),

    # Status Violation and Proceedings
    ("4. Status and Proceedings", "p4_12_violated_status", "12. Have you EVER violated the terms of the nonimmigrant status you now hold?", "radio", True),
    ("4. Status and Proceedings", "p4_13_removal_proceedings", "13. Are you now in removal proceedings?", "radio", True),

    # Employment Questions
    ("4. Employment", "p4_14_employed_in_us", "14. Have you EVER been employed in the United States since last admitted or granted an extension or change of status?", "radio", True),

    # J-1/J-2 Status
    ("4. J Status", "p4_15_j1_j2_status", "15. Are you currently or have you EVER been a J-1 exchange visitor or a J-2 dependent of a J-1 exchange visitor?", "radio", True),

    # =========================================================================
    # PART 5: APPLICANT'S CONTACT INFORMATION, CERTIFICATION, AND SIGNATURE (Page 5)
    # =========================================================================
    # Contact Information
    ("5. Contact Information", "p5_1_daytime_phone", "1. Applicant's Daytime Telephone Number", "phone", False),
    ("5. Contact Information", "p5_2_mobile_phone", "2. Applicant's Mobile Telephone Number (if any)", "phone", False),
    ("5. Contact Information", "p5_3_email", "3. Applicant's Email Address (if any)", "text", False),

    # Signature
    ("5. Signature", "p5_4_signature", "4. Applicant's Signature", "text", True),
    ("5. Signature", "p5_4_signature_date", "4. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 6: INTERPRETER'S CONTACT INFORMATION, CERTIFICATION, AND SIGNATURE (Page 5)
    # =========================================================================
    # Interpreter's Full Name
    ("6. Interpreter Name", "p6_1_family_name", "1. Interpreter's Family Name (Last Name)", "text", False),
    ("6. Interpreter Name", "p6_1_given_name", "1. Interpreter's Given Name (First Name)", "text", False),
    ("6. Interpreter Name", "p6_2_organization", "2. Interpreter's Business or Organization Name", "text", False),

    # Interpreter's Contact Information
    ("6. Interpreter Contact", "p6_3_daytime_phone", "3. Interpreter's Daytime Telephone Number", "phone", False),
    ("6. Interpreter Contact", "p6_4_mobile_phone", "4. Interpreter's Mobile Telephone Number (if any)", "phone", False),
    ("6. Interpreter Contact", "p6_5_email", "5. Interpreter's Email Address (if any)", "text", False),

    # Interpreter's Certification
    ("6. Interpreter Cert", "p6_language", "Language interpreted", "text", False),
    ("6. Interpreter Cert", "p6_6_signature", "6. Interpreter's Signature", "text", False),
    ("6. Interpreter Cert", "p6_6_signature_date", "6. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 7: CONTACT INFORMATION, DECLARATION, AND SIGNATURE OF THE PERSON PREPARING THIS APPLICATION (Page 6)
    # =========================================================================
    # Preparer's Full Name
    ("7. Preparer Name", "p7_1_family_name", "1. Preparer's Family Name (Last Name)", "text", False),
    ("7. Preparer Name", "p7_1_given_name", "1. Preparer's Given Name (First Name)", "text", False),
    ("7. Preparer Name", "p7_2_organization", "2. Preparer's Business or Organization Name", "text", False),

    # Preparer's Contact Information
    ("7. Preparer Contact", "p7_3_daytime_phone", "3. Preparer's Daytime Telephone Number", "phone", False),
    ("7. Preparer Contact", "p7_4_mobile_phone", "4. Preparer's Mobile Telephone Number (if any)", "phone", False),
    ("7. Preparer Contact", "p7_5_email", "5. Preparer's Email Address (if any)", "text", False),

    # Preparer's Signature
    ("7. Preparer Signature", "p7_6_signature", "6. Preparer's Signature", "text", False),
    ("7. Preparer Signature", "p7_6_signature_date", "6. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 8: ADDITIONAL INFORMATION (Page 7)
    # =========================================================================
    ("8. Additional Info 1", "p8_1_family_name", "1. Family Name (Last Name)", "text", False),
    ("8. Additional Info 1", "p8_1_given_name", "1. Given Name (First Name)", "text", False),
    ("8. Additional Info 1", "p8_1_middle_name", "1. Middle Name (if applicable)", "text", False),
    ("8. Additional Info 1", "p8_2_a_number", "2. A-Number", "text", False),
    ("8. Additional Info 1", "p8_3_page", "3. Page Number", "text", False),
    ("8. Additional Info 1", "p8_3_part", "3. Part Number", "text", False),
    ("8. Additional Info 1", "p8_3_item", "3. Item Number", "text", False),
    ("8. Additional Info 1", "p8_3_additional", "3. Additional Information", "textarea", False),

    ("8. Additional Info 2", "p8_4_page", "4. Page Number", "text", False),
    ("8. Additional Info 2", "p8_4_part", "4. Part Number", "text", False),
    ("8. Additional Info 2", "p8_4_item", "4. Item Number", "text", False),
    ("8. Additional Info 2", "p8_4_additional", "4. Additional Information", "textarea", False),

    ("8. Additional Info 3", "p8_5_page", "5. Page Number", "text", False),
    ("8. Additional Info 3", "p8_5_part", "5. Part Number", "text", False),
    ("8. Additional Info 3", "p8_5_item", "5. Item Number", "text", False),
    ("8. Additional Info 3", "p8_5_additional", "5. Additional Information", "textarea", False),

    ("8. Additional Info 4", "p8_6_page", "6. Page Number", "text", False),
    ("8. Additional Info 4", "p8_6_part", "6. Part Number", "text", False),
    ("8. Additional Info 4", "p8_6_item", "6. Item Number", "text", False),
    ("8. Additional Info 4", "p8_6_additional", "6. Additional Information", "textarea", False),

    # =========================================================================
    # ATTORNEY/REPRESENTATIVE SECTION (Page 1 header)
    # =========================================================================
    ("Attorney/Representative", "g28_attached", "Select this box if Form G-28 is attached", "checkbox", False),
    ("Attorney/Representative", "attorney_bar_number", "Attorney State Bar Number (if applicable)", "text", False),
    ("Attorney/Representative", "attorney_uscis_account", "Attorney or Accredited Representative USCIS Online Account Number (if any)", "text", False),
]


def update_i539(template_id=None):
    """Insert or update I-539 fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-539%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('I-539 - Application to Extend/Change Nonimmigrant Status (EXPANDED)', "
                    "'Complete I-539 with all official USCIS fields - Edition 08/28/24') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(I539_FIELDS):
            conn.execute(text(
                "INSERT INTO questionnaire_fields (template_id, section, field_name, label, field_type, is_required, \"order\") "
                "VALUES (:tid, :section, :field_name, :label, :field_type, :is_required, :order)"
            ), {
                "tid": template_id, "section": section, "field_name": field_name,
                "label": label, "field_type": field_type, "is_required": required, "order": i + 1
            })

        conn.commit()
        print(f"I-539 expanded: template_id={template_id}, fields={len(I539_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_i539()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(I539_FIELDS)}")

    sections = {}
    for section, _, _, _, _ in I539_FIELDS:
        sections[section] = sections.get(section, 0) + 1

    print("\nFields by section:")
    for section, count in sections.items():
        print(f"  {section}: {count}")

    # Check for duplicate field names
    field_names = [field_name for _, field_name, _, _, _ in I539_FIELDS]
    duplicates = [name for name in field_names if field_names.count(name) > 1]
    if duplicates:
        print(f"\nWARNING: Duplicate field names found: {set(duplicates)}")
    else:
        print("\nNo duplicate field names found.")
