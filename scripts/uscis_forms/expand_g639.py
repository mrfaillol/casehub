#!/usr/bin/env python3
"""
Expand G-639 (Freedom of Information/Privacy Act Request) with ALL official USCIS fields.
Edition 12/12/24 - 11 pages, Parts 1-5.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

G639_FIELDS = [
    # =========================================================================
    # PART 1: SPECIFY THE NATURE OF YOUR REQUEST (Pages 3-4)
    # =========================================================================
    # 1. Select Type of Request
    ("Part 1. Type of Request", "p1_1_type_a", "A. Information from your own immigration record", "checkbox", False),
    ("Part 1. Type of Request", "p1_1_type_b", "B. Information from another person's immigration record", "checkbox", False),
    ("Part 1. Type of Request", "p1_1_type_c", "C. USCIS business, operational, or policy records", "checkbox", False),
    ("Part 1. Type of Request", "p1_1_type_d", "D. An amendment or correction of your record under the Privacy Act", "checkbox", False),
    ("Part 1. Type of Request", "p1_1_type_e", "E. An amendment or correction of another person's immigration record on their behalf under the Privacy Act", "checkbox", False),
    ("Part 1. Type of Request", "p1_1_type_f", "F. Other records in USCIS custody", "checkbox", False),
    ("Part 1. Type of Request", "p1_1_type_f_explain", "F. Other records - Explain", "textarea", False),

    # 2. Request Specific Documents (Checkboxes)
    ("Part 1. Specific Documents", "p1_2_apprehensions", "Apprehensions, and Date of Apprehension (mm/dd/yyyy)", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_apprehensions_date", "Apprehensions - Date (mm/dd/yyyy)", "date", False),
    ("Part 1. Specific Documents", "p1_2_birth_cert", "Birth certificate", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_form_i94", "Form I-94, with Date of Entry (mm/dd/yyyy)", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_form_i94_date", "Form I-94 - Date of Entry (mm/dd/yyyy)", "date", False),
    ("Part 1. Specific Documents", "p1_2_passport", "Passport", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_other_arrival", "Other Arrival/Departure documents into the U.S., with Date of Entry (mm/dd/yyyy)", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_other_arrival_date", "Other Arrival/Departure - Date of Entry (mm/dd/yyyy)", "date", False),
    ("Part 1. Specific Documents", "p1_2_i129", "I-129, Petition for a Nonimmigrant Worker", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_i90", "I-90, Application to Replace Permanent Resident Card (Green Card)", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_i130", "I-130, Petition for Alien Relative", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_i140", "I-140, Immigrant Petition for Alien Workers", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_i485", "I-485, Application to Register Permanent Residence or Adjust Status", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_i751", "I-751, Petition to Remove Conditions on Residence", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_n400", "N-400, Application for Naturalization", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_labor_cert", "Labor certification issued by the U.S. Department of Labor", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_naturalization_cert", "Naturalization certificate", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_lpr_proof", "Proof of Lawful Permanent Resident (LPR) status", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_removal_record", "Record of removal from the U.S., with Date of Removal (mm/dd/yyyy)", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_removal_date", "Record of removal - Date of Removal (mm/dd/yyyy)", "date", False),
    ("Part 1. Specific Documents", "p1_2_other", "Other (Explain)", "checkbox", False),
    ("Part 1. Specific Documents", "p1_2_other_explain", "Other - Explanation", "textarea", False),

    # 3. Qualifications for Expedited Processing (Checkboxes)
    ("Part 1. Expedited Processing", "p1_3_imminent_threat", "Circumstances in which the lack of expedited processing could reasonably be expected to pose an imminent threat to the life or physical safety of an individual", "checkbox", False),
    ("Part 1. Expedited Processing", "p1_3_urgency_public", "An urgency to inform the public about an actual or alleged Federal government activity, if made by a person primarily engaged in disseminating information", "checkbox", False),
    ("Part 1. Expedited Processing", "p1_3_due_process", "The loss of substantial due process rights", "checkbox", False),
    ("Part 1. Expedited Processing", "p1_3_media_interest", "A matter of widespread and exceptional media interest in which there are possible questions about the government's integrity which affect public confidence", "checkbox", False),

    # 4. Statement Requesting Expedited Processing
    ("Part 1. Expedited Statement", "p1_4_statement", "Statement Requesting Expedited Processing (detailed explanation)", "textarea", False),

    # 5. Information Pertaining to an Upcoming Immigration Court Proceeding
    ("Part 1. Court Proceeding", "p1_5_court_proceeding", "The subject of record has a date scheduled for an immigration court proceeding", "checkbox", False),

    # =========================================================================
    # PART 2: PROVIDE INFORMATION TO IDENTIFY THE SUBJECT OF RECORD (Pages 4-6)
    # =========================================================================
    # Subject of Record's Identifying Information
    ("Part 2. Subject Identification", "p2_1_a_number_1", "1. Alien Registration Number (A-Number) 1", "text", False),
    ("Part 2. Subject Identification", "p2_1_a_number_2", "1. Alien Registration Number (A-Number) 2", "text", False),
    ("Part 2. Subject Identification", "p2_1_a_number_3", "1. Alien Registration Number (A-Number) 3", "text", False),
    ("Part 2. Subject Identification", "p2_2_dob", "2. Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 2. Subject Identification", "p2_3_country_birth", "3. Country of Birth", "text", False),

    # 4. Receipt Number (3 fields)
    ("Part 2. Receipt Number", "p2_4a_receipt", "4.A. Receipt Number", "text", False),
    ("Part 2. Receipt Number", "p2_4b_receipt", "4.B. Receipt Number", "text", False),
    ("Part 2. Receipt Number", "p2_4c_receipt", "4.C. Receipt Number", "text", False),

    # 5. Subject of Record's Name
    ("Part 2. Subject Name", "p2_5_family_name", "5. Family Name (Last Name)", "text", True),
    ("Part 2. Subject Name", "p2_5_given_name", "5. Given Name (First Name)", "text", True),
    ("Part 2. Subject Name", "p2_5_middle_name", "5. Middle Name (if applicable)", "text", False),

    # 6. Additional Names Used (3 sets)
    ("Part 2. Additional Name 1", "p2_6a_family_name", "6.A. Additional Name 1 - Family Name (Last Name)", "text", False),
    ("Part 2. Additional Name 1", "p2_6a_given_name", "6.A. Additional Name 1 - Given Name (First Name)", "text", False),
    ("Part 2. Additional Name 1", "p2_6a_middle_name", "6.A. Additional Name 1 - Middle Name (if applicable)", "text", False),
    ("Part 2. Additional Name 2", "p2_6b_family_name", "6.B. Additional Name 2 - Family Name (Last Name)", "text", False),
    ("Part 2. Additional Name 2", "p2_6b_given_name", "6.B. Additional Name 2 - Given Name (First Name)", "text", False),
    ("Part 2. Additional Name 2", "p2_6b_middle_name", "6.B. Additional Name 2 - Middle Name (if applicable)", "text", False),
    ("Part 2. Additional Name 3", "p2_6c_family_name", "6.C. Additional Name 3 - Family Name (Last Name)", "text", False),
    ("Part 2. Additional Name 3", "p2_6c_given_name", "6.C. Additional Name 3 - Given Name (First Name)", "text", False),
    ("Part 2. Additional Name 3", "p2_6c_middle_name", "6.C. Additional Name 3 - Middle Name (if applicable)", "text", False),

    # 7. Name Used Upon Entry to the United States
    ("Part 2. Entry Name", "p2_7_entry_family_name", "7. Name Used Upon Entry - Family Name (Last Name)", "text", False),
    ("Part 2. Entry Name", "p2_7_entry_given_name", "7. Name Used Upon Entry - Given Name (First Name)", "text", False),
    ("Part 2. Entry Name", "p2_7_entry_middle_name", "7. Name Used Upon Entry - Middle Name (if applicable)", "text", False),

    # 8. Subject of Record's Mailing Address and Contact Information
    ("Part 2. Mailing Address", "p2_8_street", "8. Street Number and Name", "text", False),
    ("Part 2. Mailing Address", "p2_8_apt", "8. Apt", "checkbox", False),
    ("Part 2. Mailing Address", "p2_8_ste", "8. Ste", "checkbox", False),
    ("Part 2. Mailing Address", "p2_8_flr", "8. Flr", "checkbox", False),
    ("Part 2. Mailing Address", "p2_8_number", "8. Number", "text", False),
    ("Part 2. Mailing Address", "p2_8_city", "8. City or Town", "text", False),
    ("Part 2. Mailing Address", "p2_8_state", "8. State", "select", False),
    ("Part 2. Mailing Address", "p2_8_zip", "8. ZIP Code (USPS ZIP Code Lookup)", "text", False),
    ("Part 2. Mailing Address", "p2_8_province", "8. Province", "text", False),
    ("Part 2. Mailing Address", "p2_8_postal_code", "8. Postal Code", "text", False),
    ("Part 2. Mailing Address", "p2_8_country", "8. Country", "text", False),
    ("Part 2. Mailing Address", "p2_8_phone", "8. Telephone Number", "phone", False),
    ("Part 2. Mailing Address", "p2_8_email", "8. Email Address", "email", False),

    # 9. Subject of Record's Father
    ("Part 2. Father", "p2_9_father_family_name", "9. Father - Family Name (Last Name)", "text", False),
    ("Part 2. Father", "p2_9_father_given_name", "9. Father - Given Name (First Name)", "text", False),
    ("Part 2. Father", "p2_9_father_middle_name", "9. Father - Middle Name (if applicable)", "text", False),
    ("Part 2. Father", "p2_9_father_unknown", "9. Father's Name is unknown", "checkbox", False),

    # 10. Subject of Record's Mother
    ("Part 2. Mother", "p2_10_mother_family_name", "10. Mother - Family Name (Last Name)", "text", False),
    ("Part 2. Mother", "p2_10_mother_maiden_name", "10. Mother - Maiden Name, or previous last names", "text", False),
    ("Part 2. Mother", "p2_10_mother_given_name", "10. Mother - Given Name (First Name)", "text", False),
    ("Part 2. Mother", "p2_10_mother_middle_name", "10. Mother - Middle Name (if applicable)", "text", False),
    ("Part 2. Mother", "p2_10_mother_unknown", "10. Mother's Name is unknown", "checkbox", False),

    # 11. Additional Family Members that May Appear on Requested Records (3 sets)
    ("Part 2. Family Member 1", "p2_11a_family_name", "11.A. Name 1 - Family Name (Last Name)", "text", False),
    ("Part 2. Family Member 1", "p2_11a_given_name", "11.A. Name 1 - Given Name (First Name)", "text", False),
    ("Part 2. Family Member 1", "p2_11a_middle_name", "11.A. Name 1 - Middle Name (if applicable)", "text", False),
    ("Part 2. Family Member 1", "p2_11a_relationship", "11.A. Name 1 - Relationship", "text", False),
    ("Part 2. Family Member 2", "p2_11b_family_name", "11.B. Name 2 - Family Name (Last Name)", "text", False),
    ("Part 2. Family Member 2", "p2_11b_given_name", "11.B. Name 2 - Given Name (First Name)", "text", False),
    ("Part 2. Family Member 2", "p2_11b_middle_name", "11.B. Name 2 - Middle Name (if applicable)", "text", False),
    ("Part 2. Family Member 2", "p2_11b_relationship", "11.B. Name 2 - Relationship", "text", False),
    ("Part 2. Family Member 3", "p2_11c_family_name", "11.C. Name 3 - Family Name (Last Name)", "text", False),
    ("Part 2. Family Member 3", "p2_11c_given_name", "11.C. Name 3 - Given Name (First Name)", "text", False),
    ("Part 2. Family Member 3", "p2_11c_middle_name", "11.C. Name 3 - Middle Name (if applicable)", "text", False),
    ("Part 2. Family Member 3", "p2_11c_relationship", "11.C. Name 3 - Relationship", "text", False),

    # 12. Avoiding Redaction of Records Mentioning Additional Persons
    ("Part 2. Redaction Avoidance", "p2_12_consent_notarized", "12. Consent for release (notarized document or signed under penalty of perjury)", "checkbox", False),
    ("Part 2. Redaction Avoidance", "p2_12_proof_deceased", "12. Proof of death (death certificate, obituary, photograph, Social Security Death Index, or probate documents)", "checkbox", False),

    # =========================================================================
    # PART 3: CERTIFICATION OF REQUEST AND CONSENT (Page 7)
    # =========================================================================
    # Requestor Consent to Pay Potential Fees
    ("Part 3. Requestor Consent", "p3_consent_fees", "I, the requestor, consent to pay all costs incurred for search, duplication, and review of documents up to $25", "checkbox", False),

    # Requestor Certification
    ("Part 3. Requestor Signature", "p3_1_signature_date", "1. Signature of Requestor - Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 4: THIRD-PARTY REQUESTOR (Pages 7-9)
    # =========================================================================
    # 1. Third-Party Requestor Identifying Information
    ("Part 4. Third-Party Info", "p4_1_family_name", "1. Third-Party Requestor - Family Name (Last Name)", "text", False),
    ("Part 4. Third-Party Info", "p4_1_given_name", "1. Third-Party Requestor - Given Name (First Name)", "text", False),
    ("Part 4. Third-Party Info", "p4_1_middle_name", "1. Third-Party Requestor - Middle Name (if applicable)", "text", False),

    # 2. Third-Party Requestor Mailing Address and Contact Information
    ("Part 4. Third-Party Address", "p4_2_in_care_of", "2. In Care Of Name (if any)", "text", False),
    ("Part 4. Third-Party Address", "p4_2_street", "2. Street Number and Name", "text", False),
    ("Part 4. Third-Party Address", "p4_2_apt", "2. Apt", "checkbox", False),
    ("Part 4. Third-Party Address", "p4_2_ste", "2. Ste", "checkbox", False),
    ("Part 4. Third-Party Address", "p4_2_flr", "2. Flr", "checkbox", False),
    ("Part 4. Third-Party Address", "p4_2_number", "2. Number", "text", False),
    ("Part 4. Third-Party Address", "p4_2_city", "2. City or Town", "text", False),
    ("Part 4. Third-Party Address", "p4_2_state", "2. State", "select", False),
    ("Part 4. Third-Party Address", "p4_2_zip", "2. ZIP Code (USPS ZIP Code Lookup)", "text", False),
    ("Part 4. Third-Party Address", "p4_2_province", "2. Province", "text", False),
    ("Part 4. Third-Party Address", "p4_2_postal_code", "2. Postal Code", "text", False),
    ("Part 4. Third-Party Address", "p4_2_country", "2. Country", "text", False),
    ("Part 4. Third-Party Address", "p4_2_phone", "2. Telephone Number", "phone", False),
    ("Part 4. Third-Party Address", "p4_2_email", "2. Email Address", "email", False),

    # 3. Third-Party Requestor's Relationship to the Subject of Record
    ("Part 4. Relationship", "p4_3a_attorney", "3.A. I am an attorney or accredited representative, acting on behalf of the subject of record", "checkbox", False),
    ("Part 4. Relationship", "p4_3b_deceased", "3.B. I am requesting information about someone who is deceased", "checkbox", False),
    ("Part 4. Relationship", "p4_3c_guardian", "3.C. I am requesting information on behalf of my child or a minor for whom I am a legal guardian", "checkbox", False),
    ("Part 4. Relationship", "p4_3d_other", "3.D. Other (Explain)", "checkbox", False),
    ("Part 4. Relationship", "p4_3d_other_explain", "3.D. Other - Explanation", "textarea", False),
    ("Part 4. Relationship", "p4_3e_media", "3.E. I am requesting as a member of the media", "checkbox", False),
    ("Part 4. Relationship", "p4_3f_other_no_relationship", "3.F. Other (Explain) - no relationship", "checkbox", False),
    ("Part 4. Relationship", "p4_3f_other_explain", "3.F. Other - Explanation", "textarea", False),

    # 4. If Item C selected - Parent/Guardian Information
    ("Part 4. Parent/Guardian", "p4_4a_guardian_family_name", "4.A. Parent/Guardian's Legal Name - Family Name (Last Name)", "text", False),
    ("Part 4. Parent/Guardian", "p4_4a_guardian_given_name", "4.A. Parent/Guardian's Legal Name - Given Name (First Name)", "text", False),
    ("Part 4. Parent/Guardian", "p4_4a_guardian_middle_name", "4.A. Parent/Guardian's Legal Name - Middle Name (if applicable)", "text", False),
    ("Part 4. Parent/Guardian", "p4_4b_guardian_dob", "4.B. Parent/Guardian's Date of Birth (mm/dd/yyyy)", "date", False),
    ("Part 4. Parent/Guardian", "p4_4c_guardian_country_birth", "4.C. Parent/Guardian's Country of Birth", "text", False),

    # Consent by Subject of Record (Option 1: Declaration Under Penalty of Perjury)
    ("Part 4. Consent Declaration", "p4_opt1_consent_declaration", "Option 1: I, the subject of record, consent to USCIS releasing my records to a third-party requestor", "checkbox", False),
    ("Part 4. Consent Declaration", "p4_5_subject_signature_date", "5. Signature of Subject of Record - Date of Signature (mm/dd/yyyy)", "date", False),

    # Option 2: Notarized Affidavit of Identity
    ("Part 4. Notarized Consent", "p4_6_subject_signature_date_notary", "6. Signature of Subject of Record (for notary) - Date of Signature (mm/dd/yyyy)", "date", False),
    ("Part 4. Notarized Consent", "p4_7_subject_signature_date_notary2", "7. Date of Signature (mm/dd/yyyy)", "date", False),
    ("Part 4. Notarized Consent", "p4_8_subscribed_sworn", "8. Subscribed and Sworn to Before Me on (mm/dd/yyyy)", "date", False),
    ("Part 4. Notarized Consent", "p4_9_notary_signature", "9. Signature of Notary", "text", False),
    ("Part 4. Notarized Consent", "p4_10_notary_phone", "10. Notary's Telephone Number", "phone", False),
    ("Part 4. Notarized Consent", "p4_11_commission_expires", "11. My Commission Expires on (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 5: ADDITIONAL INFORMATION (Page 10)
    # =========================================================================
    # Additional Information Fields (7 repeatable sections)
    ("Part 5. Additional Info 1", "p5_1_subject_family_name", "1. Subject of Record's Family Name (Last Name)", "text", False),
    ("Part 5. Additional Info 1", "p5_1_subject_given_name", "1. Subject of Record's Given Name (First Name)", "text", False),
    ("Part 5. Additional Info 1", "p5_1_subject_middle_name", "1. Subject of Record's Middle Name", "text", False),
    ("Part 5. Additional Info 1", "p5_2_subject_a_number", "2. Subject of Record's A-Number (if any)", "text", False),
    ("Part 5. Additional Info 1", "p5_3a_page_number", "3.A. Page Number", "text", False),
    ("Part 5. Additional Info 1", "p5_3b_part_number", "3.B. Part Number", "text", False),
    ("Part 5. Additional Info 1", "p5_3c_item_number", "3.C. Item Number", "text", False),
    ("Part 5. Additional Info 1", "p5_3d_additional_info", "3.D. Additional Information", "textarea", False),

    ("Part 5. Additional Info 2", "p5_4a_page_number", "4.A. Page Number", "text", False),
    ("Part 5. Additional Info 2", "p5_4b_part_number", "4.B. Part Number", "text", False),
    ("Part 5. Additional Info 2", "p5_4c_item_number", "4.C. Item Number", "text", False),
    ("Part 5. Additional Info 2", "p5_4d_additional_info", "4.D. Additional Information", "textarea", False),

    ("Part 5. Additional Info 3", "p5_5a_page_number", "5.A. Page Number", "text", False),
    ("Part 5. Additional Info 3", "p5_5b_part_number", "5.B. Part Number", "text", False),
    ("Part 5. Additional Info 3", "p5_5c_item_number", "5.C. Item Number", "text", False),
    ("Part 5. Additional Info 3", "p5_5d_additional_info", "5.D. Additional Information", "textarea", False),

    ("Part 5. Additional Info 4", "p5_6a_page_number", "6.A. Page Number", "text", False),
    ("Part 5. Additional Info 4", "p5_6b_part_number", "6.B. Part Number", "text", False),
    ("Part 5. Additional Info 4", "p5_6c_item_number", "6.C. Item Number", "text", False),
    ("Part 5. Additional Info 4", "p5_6d_additional_info", "6.D. Additional Information", "textarea", False),

    ("Part 5. Additional Info 5", "p5_7a_page_number", "7.A. Page Number", "text", False),
    ("Part 5. Additional Info 5", "p5_7b_part_number", "7.B. Part Number", "text", False),
    ("Part 5. Additional Info 5", "p5_7c_item_number", "7.C. Item Number", "text", False),
    ("Part 5. Additional Info 5", "p5_7d_additional_info", "7.D. Additional Information", "textarea", False),
]


def update_g639(template_id=None):
    """Insert or update G-639 fields in the database."""
    with engine.connect() as conn:
        if template_id is None:
            result = conn.execute(text(
                "SELECT id FROM questionnaire_templates WHERE name LIKE '%G-639%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
            ))
            row = result.fetchone()
            if row:
                template_id = row[0]
            else:
                result = conn.execute(text(
                    "INSERT INTO questionnaire_templates (name, description) "
                    "VALUES ('G-639 - Freedom of Information/Privacy Act Request (EXPANDED)', "
                    "'Complete G-639 with all official USCIS fields - Edition 12/12/24') RETURNING id"
                ))
                template_id = result.fetchone()[0]

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})

        for i, (section, field_name, label, field_type, required) in enumerate(G639_FIELDS):
            conn.execute(text(
                "INSERT INTO questionnaire_fields (template_id, section, field_name, label, field_type, is_required, \"order\") "
                "VALUES (:tid, :section, :field_name, :label, :field_type, :is_required, :order)"
            ), {
                "tid": template_id, "section": section, "field_name": field_name,
                "label": label, "field_type": field_type, "is_required": required, "order": i + 1
            })

        conn.commit()
        print(f"G-639 expanded: template_id={template_id}, fields={len(G639_FIELDS)}")
    return template_id


if __name__ == "__main__":
    tid = update_g639()
    print(f"\nDone! Template ID: {tid}")
    print(f"Total fields: {len(G639_FIELDS)}")

    sections = {}
    for section, _, _, _, _ in G639_FIELDS:
        sections[section] = sections.get(section, 0) + 1

    print("\nFields by section:")
    for section, count in sorted(sections.items()):
        print(f"  {section}: {count}")

    # Validation: Check for duplicate field names
    field_names = [field_name for _, field_name, _, _, _ in G639_FIELDS]
    duplicates = [name for name in field_names if field_names.count(name) > 1]
    if duplicates:
        print(f"\nWARNING: Duplicate field names found: {set(duplicates)}")
    else:
        print("\nValidation: No duplicate field names found.")
