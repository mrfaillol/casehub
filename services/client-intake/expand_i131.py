#!/usr/bin/env python3
"""
Expand I-131 (Application for Travel Documents, Parole Documents, and Arrival/Departure Records)
"""
import os
import json
from sqlalchemy import create_engine, text
from uscis_form_options import I131_OPTIONS_MAP

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/casehub")
engine = create_engine(DATABASE_URL)

I131_FIELDS = [
    # =========================================================================
    # PART 1: APPLICATION TYPE
    # =========================================================================
    ("1A. Travel Document Type", "p1_1a_reentry_permit", "1.a. I am a permanent/conditional resident applying for a Reentry Permit", "checkbox", False),
    ("1A. Travel Document Type", "p1_1b_refugee_travel", "1.b. I am a refugee/asylee applying for a Refugee Travel Document", "checkbox", False),
    ("1A. Travel Document Type", "p1_1c_tps_travel", "1.c. I have TPS and am applying for Travel Authorization", "checkbox", False),
    ("1A. Travel Document Type", "p1_1d_advance_parole", "1.d. I am applying for an Advance Parole Document", "checkbox", False),
    ("1A. Travel Document Type", "p1_1e_cnmi_resident", "1.e. I am a CNMI long-term resident applying for travel permission", "checkbox", False),
    ("1A. Travel Document Type", "p1_1f_initial_parole", "1.f. I am applying for an Initial Parole Document (outside U.S.)", "checkbox", False),
    ("1A. Travel Document Type", "p1_1g_parole_in_place", "1.g. I am applying for Parole in Place", "checkbox", False),
    ("1A. Travel Document Type", "p1_1h_reparole", "1.h. I am applying for Re-parole", "checkbox", False),
    ("1A. Travel Document Type", "p1_1i_arrival_departure", "1.i. I am applying for an Arrival/Departure Record", "checkbox", False),

    # =========================================================================
    # PART 2: INFORMATION ABOUT YOU
    # =========================================================================
    ("2A. Your Full Name", "p2_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("2A. Your Full Name", "p2_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("2A. Your Full Name", "p2_1c_middle_name", "1.c. Middle Name", "text", False),

    ("2B. Other Names", "p2_2_other_names", "2. Have you used other names since birth?", "radio", False),
    ("2B. Other Names", "p2_3a_other1_family", "3.a. Other Name 1 - Family Name", "text", False),
    ("2B. Other Names", "p2_3b_other1_given", "3.b. Other Name 1 - Given Name", "text", False),
    ("2B. Other Names", "p2_3c_other1_middle", "3.c. Other Name 1 - Middle Name", "text", False),

    ("2C. U.S. Physical Address", "p2_4a_street", "4.a. Street Number and Name", "text", True),
    ("2C. U.S. Physical Address", "p2_4b_apt_type", "4.b. Apt/Ste/Flr Type", "select", False),
    ("2C. U.S. Physical Address", "p2_4c_apt_number", "4.c. Apt/Ste/Flr Number", "text", False),
    ("2C. U.S. Physical Address", "p2_4d_city", "4.d. City or Town", "text", True),
    ("2C. U.S. Physical Address", "p2_4e_state", "4.e. State", "select", True),
    ("2C. U.S. Physical Address", "p2_4f_zip", "4.f. ZIP Code", "text", True),

    ("2D. Mailing Address", "p2_5_same_as_physical", "5. Is your mailing address the same as your physical address?", "radio", False),
    ("2D. Mailing Address", "p2_6a_mail_care_of", "6.a. Mailing Address - In Care Of Name", "text", False),
    ("2D. Mailing Address", "p2_6b_mail_street", "6.b. Mailing Address - Street", "text", False),
    ("2D. Mailing Address", "p2_6c_mail_apt", "6.c. Mailing Address - Apt/Ste/Flr", "text", False),
    ("2D. Mailing Address", "p2_6d_mail_city", "6.d. Mailing Address - City", "text", False),
    ("2D. Mailing Address", "p2_6e_mail_state", "6.e. Mailing Address - State", "select", False),
    ("2D. Mailing Address", "p2_6f_mail_zip", "6.f. Mailing Address - ZIP Code", "text", False),
    ("2D. Mailing Address", "p2_6g_mail_province", "6.g. Mailing Address - Province", "text", False),
    ("2D. Mailing Address", "p2_6h_mail_postal", "6.h. Mailing Address - Postal Code", "text", False),
    ("2D. Mailing Address", "p2_6i_mail_country", "6.i. Mailing Address - Country", "text", False),

    ("2E. Identification", "p2_7_a_number", "7. Alien Registration Number (A-Number)", "text", False),
    ("2E. Identification", "p2_8_uscis_account", "8. USCIS Online Account Number", "text", False),
    ("2E. Identification", "p2_9_ssn", "9. U.S. Social Security Number", "text", False),

    ("2F. Biographic Information", "p2_10_dob", "10. Date of Birth (mm/dd/yyyy)", "date", True),
    ("2F. Biographic Information", "p2_11_sex", "11. Sex", "select", True),
    ("2F. Biographic Information", "p2_12_city_birth", "12. City/Town of Birth", "text", True),
    ("2F. Biographic Information", "p2_13_state_birth", "13. State/Province of Birth", "text", False),
    ("2F. Biographic Information", "p2_14_country_birth", "14. Country of Birth", "text", True),
    ("2F. Biographic Information", "p2_15_citizenship", "15. Country of Citizenship or Nationality", "text", True),

    ("2G. Immigration Status", "p2_16_class_of_admission", "16. Class of Admission", "select", True),
    ("2G. Immigration Status", "p2_17_date_status_granted", "17. Date Status Was Granted", "date", False),
    ("2G. Immigration Status", "p2_18_i94_number", "18. Form I-94 Arrival-Departure Record Number", "text", False),

    # =========================================================================
    # PART 3: BIOGRAPHIC INFORMATION
    # =========================================================================
    ("3A. Physical Description", "p3_1_ethnicity", "1. Ethnicity (Hispanic/Latino or Not)", "select", False),
    ("3A. Physical Description", "p3_2_race", "2. Race", "select", False),
    ("3A. Physical Description", "p3_3_height_feet", "3.a. Height - Feet", "number", False),
    ("3A. Physical Description", "p3_4_height_inches", "3.b. Height - Inches", "number", False),
    ("3A. Physical Description", "p3_5_weight_lbs", "4. Weight (pounds)", "number", False),
    ("3A. Physical Description", "p3_6_eye_color", "5. Eye Color", "select", False),
    ("3A. Physical Description", "p3_7_hair_color", "6. Hair Color", "select", False),

    # =========================================================================
    # PART 4: PROCESSING INFORMATION
    # =========================================================================
    ("4A. Document Delivery", "p4_1_where_to_pick_up", "1. If approved, where do you want to pick up the document?", "select", False),
    ("4A. Document Delivery", "p4_2a_consulate_city", "2.a. U.S. Embassy/Consulate - City", "text", False),
    ("4A. Document Delivery", "p4_2b_consulate_country", "2.b. U.S. Embassy/Consulate - Country", "text", False),

    ("4B. Safe Alternate Address", "p4_3_safe_address", "3. Do you want notifications sent to a safe alternate address?", "radio", False),
    ("4B. Safe Alternate Address", "p4_4a_safe_street", "4.a. Safe Alternate Address - Street", "text", False),
    ("4B. Safe Alternate Address", "p4_4b_safe_apt", "4.b. Safe Alternate Address - Apt/Ste/Flr", "text", False),
    ("4B. Safe Alternate Address", "p4_4c_safe_city", "4.c. Safe Alternate Address - City", "text", False),
    ("4B. Safe Alternate Address", "p4_4d_safe_state", "4.d. Safe Alternate Address - State", "select", False),
    ("4B. Safe Alternate Address", "p4_4e_safe_zip", "4.e. Safe Alternate Address - ZIP Code", "text", False),

    # =========================================================================
    # PART 5: REENTRY PERMIT ONLY
    # =========================================================================
    ("5A. Time Outside U.S.", "p5_1_total_time_outside", "1. Since becoming a permanent resident, total time spent outside U.S.", "text", False),
    ("5A. Time Outside U.S.", "p5_2_trips_outside", "2. Since becoming a permanent resident, how many trips outside U.S.?", "number", False),
    ("5A. Time Outside U.S.", "p5_3_longest_trip", "3. Length of your longest trip outside the U.S.", "text", False),
    ("5B. Travel Plans", "p5_4_planned_trip_length", "4. How long do you plan to be outside the U.S.?", "text", False),
    ("5B. Travel Plans", "p5_5_why_reentry_permit", "5. Why do you need a Reentry Permit?", "textarea", False),

    # =========================================================================
    # PART 6: REFUGEE TRAVEL DOCUMENT ONLY
    # =========================================================================
    ("6A. Travel to Country of Persecution", "p6_1_plan_travel_persecution", "1. Do you plan to travel to the country from which you claimed persecution?", "radio", False),
    ("6B. Contact with Country", "p6_2_applied_passport", "2. Since being granted asylum/refugee status, have you applied for a passport?", "radio", False),
    ("6B. Contact with Country", "p6_3_received_passport", "3. Have you received a passport from that country?", "radio", False),
    ("6B. Contact with Country", "p6_4_acquired_nationality", "4. Have you acquired the nationality of any other country?", "radio", False),
    ("6B. Contact with Country", "p6_5_granted_residence", "5. Have you been granted permanent residence in any other country?", "radio", False),
    ("6B. Contact with Country", "p6_6_returned_persecution", "6. Since being granted status, have you returned to that country?", "radio", False),
    ("6B. Contact with Country", "p6_7_explain_yes", "7. If you answered 'Yes' to any above, explain:", "textarea", False),

    # =========================================================================
    # PART 7: PROPOSED TRAVEL INFORMATION
    # =========================================================================
    ("7A. Trip Details", "p7_1_purpose_of_trip", "1. Purpose of your trip (describe)", "textarea", True),
    ("7A. Trip Details", "p7_2a_country1", "2.a. Country 1 you intend to visit", "text", False),
    ("7A. Trip Details", "p7_2b_country2", "2.b. Country 2 you intend to visit", "text", False),
    ("7A. Trip Details", "p7_2c_country3", "2.c. Country 3 you intend to visit", "text", False),
    ("7A. Trip Details", "p7_3_departure_date", "3. Expected date of departure", "date", False),
    ("7A. Trip Details", "p7_4_return_date", "4. Expected date of return", "date", False),
    ("7A. Trip Details", "p7_5_trip_length", "5. Expected length of trip", "text", False),

    ("7B. Previous Advance Parole", "p7_6_prev_advance_parole", "6. Have you previously been issued an Advance Parole Document?", "radio", False),
    ("7B. Previous Advance Parole", "p7_7_prev_ap_date", "7. If Yes, date of previous Advance Parole", "date", False),
    ("7B. Previous Advance Parole", "p7_8_prev_ap_disposition", "8. Disposition of previous Advance Parole", "text", False),

    # =========================================================================
    # PART 8: PAROLE REQUEST (Initial Parole, Parole in Place, or Re-Parole)
    # =========================================================================
    ("8A. Basis for Parole", "p8_1_basis_parole", "1. Basis for requesting parole (explain)", "textarea", False),
    ("8A. Basis for Parole", "p8_2_humanitarian", "2. Requesting based on urgent humanitarian reasons", "checkbox", False),
    ("8A. Basis for Parole", "p8_3_public_benefit", "3. Requesting based on significant public benefit", "checkbox", False),
    ("8A. Basis for Parole", "p8_4_military_parole", "4. Requesting military parole in place", "checkbox", False),
    ("8A. Basis for Parole", "p8_5_explain_basis", "5. Explain your basis for parole:", "textarea", False),

    # =========================================================================
    # PART 9: EMPLOYMENT AUTHORIZATION (For Re-Parole)
    # =========================================================================
    ("9A. EAD Request", "p9_1_request_ead", "1. I am requesting an EAD upon approval of re-parole", "checkbox", False),
    ("9A. EAD Request", "p9_2_previous_ead", "2. Have you previously been issued an EAD?", "radio", False),
    ("9A. EAD Request", "p9_3_prev_ead_number", "3. Previous EAD Card Number", "text", False),
    ("9A. EAD Request", "p9_4_prev_ead_exp", "4. Previous EAD Expiration Date", "date", False),

    # =========================================================================
    # PART 10: APPLICANT'S STATEMENT, CONTACT, CERTIFICATION, AND SIGNATURE
    # =========================================================================
    ("10A. Applicant's Statement", "p10_1a_can_read", "1.a. I can read and understand English", "checkbox", False),
    ("10A. Applicant's Statement", "p10_1b_interpreter_read", "1.b. The interpreter named in Part 11 read to me", "checkbox", False),
    ("10A. Applicant's Statement", "p10_2_preparer_assisted", "2. At my request, the preparer named in Part 12 prepared this form", "checkbox", False),

    ("10B. Contact Information", "p10_3_daytime_phone", "3. Applicant's Daytime Telephone Number", "phone", True),
    ("10B. Contact Information", "p10_4_mobile_phone", "4. Applicant's Mobile Telephone Number", "phone", False),
    ("10B. Contact Information", "p10_5_email", "5. Applicant's Email Address", "email", False),

    ("10C. Certification", "p10_6_signature_date", "6. Date of Signature (mm/dd/yyyy)", "date", True),

    # =========================================================================
    # PART 11: INTERPRETER'S INFORMATION
    # =========================================================================
    ("11A. Interpreter's Name", "p11_1a_interp_family", "1.a. Interpreter's Family Name", "text", False),
    ("11A. Interpreter's Name", "p11_1b_interp_given", "1.b. Interpreter's Given Name", "text", False),
    ("11A. Interpreter's Name", "p11_2_interp_org", "2. Interpreter's Business or Organization", "text", False),
    ("11B. Interpreter's Address", "p11_3a_interp_street", "3.a. Interpreter's Street", "text", False),
    ("11B. Interpreter's Address", "p11_3b_interp_apt", "3.b. Interpreter's Apt/Ste/Flr", "text", False),
    ("11B. Interpreter's Address", "p11_3c_interp_city", "3.c. Interpreter's City", "text", False),
    ("11B. Interpreter's Address", "p11_3d_interp_state", "3.d. Interpreter's State", "select", False),
    ("11B. Interpreter's Address", "p11_3e_interp_zip", "3.e. Interpreter's ZIP Code", "text", False),
    ("11B. Interpreter's Address", "p11_3f_interp_country", "3.f. Interpreter's Country", "text", False),
    ("11C. Interpreter's Contact", "p11_4_interp_phone", "4. Interpreter's Phone", "phone", False),
    ("11C. Interpreter's Contact", "p11_5_interp_email", "5. Interpreter's Email", "email", False),
    ("11D. Interpreter's Certification", "p11_6_language", "6. Language Interpreted", "text", False),
    ("11D. Interpreter's Certification", "p11_7_interp_signature_date", "7. Interpreter's Signature Date", "date", False),

    # =========================================================================
    # PART 12: PREPARER'S INFORMATION
    # =========================================================================
    ("12A. Preparer's Statement", "p12_1a_prep_not_attorney", "1.a. I am NOT an attorney or accredited representative", "checkbox", False),
    ("12A. Preparer's Statement", "p12_1b_prep_is_attorney", "1.b. I AM an attorney or accredited representative", "checkbox", False),
    ("12B. Preparer's Name", "p12_2a_prep_family", "2.a. Preparer's Family Name", "text", False),
    ("12B. Preparer's Name", "p12_2b_prep_given", "2.b. Preparer's Given Name", "text", False),
    ("12B. Preparer's Name", "p12_3_prep_org", "3. Preparer's Business or Organization", "text", False),
    ("12C. Preparer's Address", "p12_4a_prep_street", "4.a. Preparer's Street", "text", False),
    ("12C. Preparer's Address", "p12_4b_prep_apt", "4.b. Preparer's Apt/Ste/Flr", "text", False),
    ("12C. Preparer's Address", "p12_4c_prep_city", "4.c. Preparer's City", "text", False),
    ("12C. Preparer's Address", "p12_4d_prep_state", "4.d. Preparer's State", "select", False),
    ("12C. Preparer's Address", "p12_4e_prep_zip", "4.e. Preparer's ZIP Code", "text", False),
    ("12C. Preparer's Address", "p12_4f_prep_country", "4.f. Preparer's Country", "text", False),
    ("12D. Preparer's Contact", "p12_5_prep_phone", "5. Preparer's Phone", "phone", False),
    ("12D. Preparer's Contact", "p12_6_prep_email", "6. Preparer's Email", "email", False),
    ("12E. Preparer's Certification", "p12_7_prep_extends", "7. Does representation extend beyond this case?", "radio", False),
    ("12E. Preparer's Certification", "p12_8_prep_signature_date", "8. Preparer's Signature Date", "date", False),

    # =========================================================================
    # PART 13: ADDITIONAL INFORMATION
    # =========================================================================
    ("13. Additional Information", "p13_1a_page", "1.a. Page Number", "text", False),
    ("13. Additional Information", "p13_1b_part", "1.b. Part Number", "text", False),
    ("13. Additional Information", "p13_1c_item", "1.c. Item Number", "text", False),
    ("13. Additional Information", "p13_1d_answer", "1.d. Additional Information", "textarea", False),
    ("13. Additional Information", "p13_2a_page", "2.a. Page Number", "text", False),
    ("13. Additional Information", "p13_2b_part", "2.b. Part Number", "text", False),
    ("13. Additional Information", "p13_2c_item", "2.c. Item Number", "text", False),
    ("13. Additional Information", "p13_2d_answer", "2.d. Additional Information", "textarea", False),
    ("13. Additional Information", "p13_3_additional", "3. Additional Information (continue)", "textarea", False),
]

def update_form(template_id: int, fields: list, form_name: str, options_map: dict):
    """Update a form with all fields including options for select/radio fields."""
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": template_id})
        for i, field in enumerate(fields):
            section, field_name, label, field_type, required = field
            # Get options from the options map if available
            options = options_map.get(field_name, None)
            options_json = json.dumps(options) if options else None

            conn.execute(text("""
                INSERT INTO questionnaire_fields
                (template_id, field_name, label, field_type, is_required, section, "order", options)
                VALUES (:tid, :fname, :label, :ftype, :req, :section, :ord, :options)
            """), {
                'tid': template_id,
                'fname': field_name,
                'label': label,
                'ftype': field_type,
                'req': required,
                'section': section,
                'ord': i + 1,
                'options': options_json
            })
        conn.commit()
        print(f"{form_name} updated: {len(fields)} fields with options")

if __name__ == "__main__":
    update_form(43, I131_FIELDS, "I-131", I131_OPTIONS_MAP)
