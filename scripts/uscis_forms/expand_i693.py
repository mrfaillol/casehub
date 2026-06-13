#!/usr/bin/env python3
"""
Expand I-693 (Report of Medical Examination and Vaccination Record) with ALL official USCIS fields.
Edition 10/15/19 - 8 pages, Parts 1-5.
Note: Most of this form is completed by the civil surgeon, not the applicant.
We include ALL fields for completeness, but the civil surgeon sections are marked accordingly.
"""
import json
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

I693_FIELDS = [
    # =========================================================================
    # PART 1: INFORMATION ABOUT YOU (APPLICANT) (Page 1)
    # =========================================================================
    ("Part 1. Information About You", "p1_1a_family_name", "1.a. Family Name (Last Name)", "text", True),
    ("Part 1. Information About You", "p1_1b_given_name", "1.b. Given Name (First Name)", "text", True),
    ("Part 1. Information About You", "p1_1c_middle_name", "1.c. Middle Name", "text", False),
    ("Part 1. Information About You", "p1_2_dob", "2. Date of Birth (mm/dd/yyyy)", "date", True),
    ("Part 1. Information About You", "p1_3_gender_male", "3. Gender - Male", "radio", False),
    ("Part 1. Information About You", "p1_3_gender_female", "3. Gender - Female", "radio", False),
    ("Part 1. Information About You", "p1_4_a_number", "4. Alien Registration Number (A-Number) (if any)", "text", False),
    ("Part 1. Information About You", "p1_5_uscis_account", "5. USCIS Online Account Number (if any)", "text", False),

    # Mailing Address
    ("Part 1. Mailing Address", "p1_6a_street", "6.a. Street Number and Name", "text", True),
    ("Part 1. Mailing Address", "p1_6b_apt_type", "6.b. Apt./Ste./Flr.", "select", False),
    ("Part 1. Mailing Address", "p1_6b_apt_number", "6.b. Number", "text", False),
    ("Part 1. Mailing Address", "p1_6c_city", "6.c. City or Town", "text", True),
    ("Part 1. Mailing Address", "p1_6d_state", "6.d. State", "select", True),
    ("Part 1. Mailing Address", "p1_6e_zip", "6.e. ZIP Code", "text", True),

    # Application Type
    ("Part 1. Application Information", "p1_7_application_type", "7. Type of application for which this medical examination is being conducted", "select", True),

    # =========================================================================
    # PART 2: EXAMINATION FINDINGS (CIVIL SURGEON) (Pages 2-4)
    # =========================================================================
    ("Part 2. Examination Findings (Civil Surgeon)", "p2_1_exam_date", "1. Date of Examination (mm/dd/yyyy)", "date", False),
    ("Part 2. Examination Findings (Civil Surgeon)", "p2_2_height_feet", "2.a. Height - Feet", "number", False),
    ("Part 2. Examination Findings (Civil Surgeon)", "p2_2_height_inches", "2.b. Height - Inches", "number", False),
    ("Part 2. Examination Findings (Civil Surgeon)", "p2_3_weight", "3. Weight (in pounds)", "number", False),

    # Class A Conditions
    ("Part 2. Class A Conditions", "p2_4_tb_class_a", "4. Tuberculosis - Class A (infectious)?", "select", False),
    ("Part 2. Class A Conditions", "p2_5_tb_test_type", "5. Type of TB Test Administered", "select", False),
    ("Part 2. Class A Conditions", "p2_6_tb_test_result", "6. TB Test Result", "text", False),
    ("Part 2. Class A Conditions", "p2_7_chest_xray", "7. Chest X-Ray Result (if applicable)", "text", False),
    ("Part 2. Class A Conditions", "p2_8_syphilis", "8. Syphilis Test Result", "select", False),
    ("Part 2. Class A Conditions", "p2_9_gonorrhea", "9. Gonorrhea Test Result", "select", False),
    ("Part 2. Class A Conditions", "p2_10_hansen", "10. Hansen's Disease (Leprosy) - Infectious?", "select", False),
    ("Part 2. Class A Conditions", "p2_11_mental_disorder", "11. Physical or Mental Disorder with Associated Harmful Behavior?", "select", False),
    ("Part 2. Class A Conditions", "p2_12_substance_abuse", "12. Drug Abuse or Addiction?", "select", False),

    # Overall Finding
    ("Part 2. Overall Finding", "p2_13_class_a_found", "13. Applicant has a Class A condition?", "select", False),
    ("Part 2. Overall Finding", "p2_14_class_b_found", "14. Applicant has a Class B condition?", "select", False),
    ("Part 2. Overall Finding", "p2_15_class_b_description", "15. If Class B, describe the condition(s)", "textarea", False),

    # =========================================================================
    # PART 3: VACCINATION REQUIREMENTS (Pages 4-6)
    # =========================================================================
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_1_mumps", "1. Mumps - Vaccinated?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_2_measles", "2. Measles - Vaccinated?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_3_rubella", "3. Rubella - Vaccinated?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_4_polio", "4. Polio - Vaccinated?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_5_tetanus_diphtheria", "5. Tetanus and Diphtheria Toxoids - Vaccinated?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_6_pertussis", "6. Pertussis - Vaccinated?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_7_hib", "7. Haemophilus Influenzae Type B (Hib) - Vaccinated?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_8_hepatitis_a", "8. Hepatitis A - Vaccinated?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_9_hepatitis_b", "9. Hepatitis B - Vaccinated?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_10_meningococcal", "10. Meningococcal Disease - Vaccinated?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_11_varicella", "11. Varicella - Vaccinated?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_12_pneumococcal", "12. Pneumococcal Disease - Vaccinated?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_13_rotavirus", "13. Rotavirus - Vaccinated?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_14_influenza", "14. Influenza - Vaccinated?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_15_covid19", "15. COVID-19 - Vaccinated?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_16_blanket_waiver", "16. Blanket waiver requested for any vaccination?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_17_individual_waiver", "17. Individual waiver requested for any vaccination?", "select", False),
    ("Part 3. Vaccination Requirements (Civil Surgeon)", "p3_18_waiver_reason", "18. If waiver requested, specify reason and vaccine", "textarea", False),

    # =========================================================================
    # PART 4: APPLICANT CERTIFICATION (Page 7)
    # =========================================================================
    ("Part 4. Applicant Certification", "p4_1_understood_exam", "1. I certify that I understood the purpose of the medical examination", "checkbox", False),
    ("Part 4. Applicant Certification", "p4_2_truthful_responses", "2. I certify that my responses were truthful and complete", "checkbox", False),
    ("Part 4. Applicant Certification", "p4_3_signature", "3. Applicant's Signature", "text", False),
    ("Part 4. Applicant Certification", "p4_4_signature_date", "4. Date of Signature (mm/dd/yyyy)", "date", False),

    # =========================================================================
    # PART 5: CIVIL SURGEON CERTIFICATION (Pages 7-8)
    # =========================================================================
    ("Part 5. Civil Surgeon Certification", "p5_1a_surgeon_family_name", "1.a. Civil Surgeon's Family Name (Last Name)", "text", False),
    ("Part 5. Civil Surgeon Certification", "p5_1b_surgeon_given_name", "1.b. Civil Surgeon's Given Name (First Name)", "text", False),
    ("Part 5. Civil Surgeon Certification", "p5_2_surgeon_address", "2. Civil Surgeon's Office Address", "text", False),
    ("Part 5. Civil Surgeon Certification", "p5_3_surgeon_city", "3. City or Town", "text", False),
    ("Part 5. Civil Surgeon Certification", "p5_4_surgeon_state", "4. State", "text", False),
    ("Part 5. Civil Surgeon Certification", "p5_5_surgeon_zip", "5. ZIP Code", "text", False),
    ("Part 5. Civil Surgeon Certification", "p5_6_surgeon_phone", "6. Telephone Number", "phone", False),
    ("Part 5. Civil Surgeon Certification", "p5_7_surgeon_email", "7. Email Address", "email", False),
    ("Part 5. Civil Surgeon Certification", "p5_8_surgeon_uscis_id", "8. USCIS Designation Number", "text", False),
    ("Part 5. Civil Surgeon Certification", "p5_9_surgeon_signature", "9. Civil Surgeon's Signature", "text", False),
    ("Part 5. Civil Surgeon Certification", "p5_10_surgeon_signature_date", "10. Date of Signature (mm/dd/yyyy)", "date", False),
]

OPTIONS_MAP = {
    "p1_6b_apt_type": ["Apt.", "Ste.", "Flr."],
    "p1_7_application_type": [
        "I-485 - Adjustment of Status",
        "I-601 - Waiver of Inadmissibility",
        "I-602 - Waiver as HRIFA Applicant",
        "Other",
    ],
    "p2_4_tb_class_a": ["Yes", "No"],
    "p2_5_tb_test_type": ["TST (Tuberculin Skin Test)", "IGRA (Blood Test)", "Chest X-Ray"],
    "p2_8_syphilis": ["Reactive", "Non-Reactive", "Not Tested"],
    "p2_9_gonorrhea": ["Positive", "Negative", "Not Tested"],
    "p2_10_hansen": ["Yes", "No"],
    "p2_11_mental_disorder": ["Yes", "No"],
    "p2_12_substance_abuse": ["Yes", "No"],
    "p2_13_class_a_found": ["Yes", "No"],
    "p2_14_class_b_found": ["Yes", "No"],
    "p3_1_mumps": ["Yes", "No", "Not Age-Appropriate"],
    "p3_2_measles": ["Yes", "No", "Not Age-Appropriate"],
    "p3_3_rubella": ["Yes", "No", "Not Age-Appropriate"],
    "p3_4_polio": ["Yes", "No", "Not Age-Appropriate"],
    "p3_5_tetanus_diphtheria": ["Yes", "No", "Not Age-Appropriate"],
    "p3_6_pertussis": ["Yes", "No", "Not Age-Appropriate"],
    "p3_7_hib": ["Yes", "No", "Not Age-Appropriate"],
    "p3_8_hepatitis_a": ["Yes", "No", "Not Age-Appropriate"],
    "p3_9_hepatitis_b": ["Yes", "No", "Not Age-Appropriate"],
    "p3_10_meningococcal": ["Yes", "No", "Not Age-Appropriate"],
    "p3_11_varicella": ["Yes", "No", "Not Age-Appropriate"],
    "p3_12_pneumococcal": ["Yes", "No", "Not Age-Appropriate"],
    "p3_13_rotavirus": ["Yes", "No", "Not Age-Appropriate"],
    "p3_14_influenza": ["Yes", "No", "Not Age-Appropriate"],
    "p3_15_covid19": ["Yes", "No", "Not Age-Appropriate"],
    "p3_16_blanket_waiver": ["Yes", "No"],
    "p3_17_individual_waiver": ["Yes", "No"],
}


def expand():
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT id FROM questionnaire_templates WHERE name LIKE '%I-693%' AND name NOT LIKE '%OLD%' ORDER BY id DESC LIMIT 1"
        ))
        row = result.fetchone()
        if not row:
            print("I-693 template not found!")
            return
        tid = row[0]
        print(f"Found I-693 template id={tid}")

        conn.execute(text("DELETE FROM questionnaire_fields WHERE template_id = :tid"), {"tid": tid})

        for i, (section, fname, label, ftype, req) in enumerate(I693_FIELDS, 1):
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
        print(f"Expanded I-693: {len(I693_FIELDS)} fields inserted for template {tid}")


if __name__ == "__main__":
    expand()
