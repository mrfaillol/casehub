#!/usr/bin/env python3
"""
Seed EB-1A Extraordinary Ability questionnaire templates with all required fields.
Creates 4 comprehensive templates for EB-1A visa evidence collection:
- Template 101: Personal Information & Eligibility (40 fields)
- Template 102: Evidence Checklist & Metadata (50 fields)
- Template 103: Criteria Deep-Dive (60 fields)
- Template 104: Supporting Statement Data (25 fields)

Based on 8 CFR 204.5(h)(3) - 10 EB-1A criteria.
"""
from sqlalchemy import create_engine, text

from config import settings
engine = create_engine(settings.DATABASE_URL)

# =======================================================================================
# TEMPLATE 101: EB-1A PERSONAL INFORMATION & ELIGIBILITY (40 fields)
# =======================================================================================
TEMPLATE_101_FIELDS = [
    # Section 1: Personal Information (10 fields)
    ("1. Personal Information", "full_name", "Full Legal Name", "text", True),
    ("1. Personal Information", "date_of_birth", "Date of Birth", "date", True),
    ("1. Personal Information", "country_of_birth", "Country of Birth", "text", True),
    ("1. Personal Information", "country_of_citizenship", "Country of Citizenship", "text", True),
    ("1. Personal Information", "alien_number", "A-Number (if any)", "text", False),
    ("1. Personal Information", "email_address", "Email Address", "email", True),
    ("1. Personal Information", "phone_number", "Phone Number", "phone", True),
    ("1. Personal Information", "current_address", "Current U.S. Address", "textarea", True),
    ("1. Personal Information", "foreign_address", "Foreign Address (if any)", "textarea", False),
    ("1. Personal Information", "marital_status", "Marital Status", "select", False),

    # Section 2: Current Immigration Status (8 fields)
    ("2. Immigration Status", "current_visa_type", "Current Visa Type", "text", True),
    ("2. Immigration Status", "visa_expiration_date", "Visa Expiration Date", "date", False),
    ("2. Immigration Status", "i94_number", "I-94 Number", "text", False),
    ("2. Immigration Status", "i94_expiration_date", "I-94 Expiration Date", "date", False),
    ("2. Immigration Status", "passport_number", "Passport Number", "text", True),
    ("2. Immigration Status", "passport_expiration_date", "Passport Expiration Date", "date", True),
    ("2. Immigration Status", "date_of_entry_usa", "Date of Entry to U.S.", "date", True),
    ("2. Immigration Status", "port_of_entry", "Port of Entry", "text", False),

    # Section 3: Education (8 fields)
    ("3. Education", "highest_degree", "Highest Degree Earned", "select", True),
    ("3. Education", "degree_institution", "Institution Name", "text", True),
    ("3. Education", "degree_country", "Country of Institution", "text", True),
    ("3. Education", "degree_year", "Year of Completion", "text", True),
    ("3. Education", "field_of_study", "Field of Study", "text", True),
    ("3. Education", "degree_certified_usa", "Is degree certified/evaluated for U.S. equivalency?", "radio", False),
    ("3. Education", "additional_degrees", "Additional Degrees/Certifications", "textarea", False),
    ("3. Education", "academic_distinctions", "Academic Honors/Distinctions", "textarea", False),

    # Section 4: Current Employment (7 fields)
    ("4. Current Employment", "current_employer", "Current Employer Name", "text", True),
    ("4. Current Employment", "job_title", "Job Title", "text", True),
    ("4. Current Employment", "employment_start_date", "Employment Start Date", "date", True),
    ("4. Current Employment", "annual_salary", "Annual Salary (USD)", "number", False),
    ("4. Current Employment", "job_description", "Brief Job Description", "textarea", True),
    ("4. Current Employment", "employer_distinguished", "Is your employer a distinguished organization?", "radio", False),
    ("4. Current Employment", "h1b_or_other_status", "Are you currently on H-1B or other work visa?", "radio", False),

    # Section 5: EB-1A Eligibility Criteria (7 fields)
    ("5. Eligibility Criteria", "criteria_header", "Check ALL criteria you meet (need at least 3 of 10):", "section", False),
    ("5. Eligibility Criteria", "criteria_awards", "1. National/International Awards", "checkbox", False),
    ("5. Eligibility Criteria", "criteria_memberships", "2. Exclusive Memberships", "checkbox", False),
    ("5. Eligibility Criteria", "criteria_published_material", "3. Published Material About You", "checkbox", False),
    ("5. Eligibility Criteria", "criteria_judging", "4. Judging Work of Others", "checkbox", False),
    ("5. Eligibility Criteria", "criteria_original_contributions", "5. Original Contributions of Major Significance", "checkbox", False),
    ("5. Eligibility Criteria", "criteria_scholarly_articles", "6. Scholarly Articles", "checkbox", False),
]

# =======================================================================================
# TEMPLATE 102: EB-1A EVIDENCE CHECKLIST & METADATA (50 fields)
# =======================================================================================
TEMPLATE_102_FIELDS = [
    # Section 1: Required Documents (10 fields)
    ("1. Required Documents", "passport_uploaded", "Passport (bio page scan)", "checkbox", True),
    ("1. Required Documents", "i94_uploaded", "I-94 Arrival/Departure Record", "checkbox", True),
    ("1. Required Documents", "current_visa_uploaded", "Current Visa (if applicable)", "checkbox", False),
    ("1. Required Documents", "diploma_uploaded", "Highest Degree Diploma", "checkbox", True),
    ("1. Required Documents", "transcripts_uploaded", "Academic Transcripts", "checkbox", True),
    ("1. Required Documents", "employment_letter_uploaded", "Current Employment Verification Letter", "checkbox", True),
    ("1. Required Documents", "i140_form_uploaded", "Form I-140 (Petition)", "checkbox", True),
    ("1. Required Documents", "g1145_form_uploaded", "Form G-1145 (e-Notification)", "checkbox", True),
    ("1. Required Documents", "cv_resume_uploaded", "Current CV/Resume", "checkbox", True),
    ("1. Required Documents", "birth_certificate_uploaded", "Birth Certificate", "checkbox", False),

    # Section 2: Letters of Recommendation - Recommender 1 (6 fields)
    ("2. Recommender 1", "rec1_name", "Recommender 1 - Full Name", "text", True),
    ("2. Recommender 1", "rec1_title", "Recommender 1 - Professional Title", "text", True),
    ("2. Recommender 1", "rec1_organization", "Recommender 1 - Organization/Institution", "text", True),
    ("2. Recommender 1", "rec1_email", "Recommender 1 - Email Address", "email", True),
    ("2. Recommender 1", "rec1_relationship", "Recommender 1 - Relationship to You", "text", True),
    ("2. Recommender 1", "rec1_letter_status", "Recommender 1 - Letter Status", "select", True),

    # Section 3: Letters of Recommendation - Recommender 2 (6 fields)
    ("3. Recommender 2", "rec2_name", "Recommender 2 - Full Name", "text", True),
    ("3. Recommender 2", "rec2_title", "Recommender 2 - Professional Title", "text", True),
    ("3. Recommender 2", "rec2_organization", "Recommender 2 - Organization/Institution", "text", True),
    ("3. Recommender 2", "rec2_email", "Recommender 2 - Email Address", "email", True),
    ("3. Recommender 2", "rec2_relationship", "Recommender 2 - Relationship to You", "text", True),
    ("3. Recommender 2", "rec2_letter_status", "Recommender 2 - Letter Status", "select", True),

    # Section 4: Letters of Recommendation - Recommender 3 (6 fields)
    ("4. Recommender 3", "rec3_name", "Recommender 3 - Full Name", "text", False),
    ("4. Recommender 3", "rec3_title", "Recommender 3 - Professional Title", "text", False),
    ("4. Recommender 3", "rec3_organization", "Recommender 3 - Organization/Institution", "text", False),
    ("4. Recommender 3", "rec3_email", "Recommender 3 - Email Address", "email", False),
    ("4. Recommender 3", "rec3_relationship", "Recommender 3 - Relationship to You", "text", False),
    ("4. Recommender 3", "rec3_letter_status", "Recommender 3 - Letter Status", "select", False),

    # Section 5: Letters of Recommendation - Recommender 4 (6 fields)
    ("5. Recommender 4", "rec4_name", "Recommender 4 - Full Name", "text", False),
    ("5. Recommender 4", "rec4_title", "Recommender 4 - Professional Title", "text", False),
    ("5. Recommender 4", "rec4_organization", "Recommender 4 - Organization/Institution", "text", False),
    ("5. Recommender 4", "rec4_email", "Recommender 4 - Email Address", "email", False),
    ("5. Recommender 4", "rec4_relationship", "Recommender 4 - Relationship to You", "text", False),
    ("5. Recommender 4", "rec4_letter_status", "Recommender 4 - Letter Status", "select", False),

    # Section 6: Letters of Recommendation - Recommender 5 (6 fields)
    ("6. Recommender 5", "rec5_name", "Recommender 5 - Full Name", "text", False),
    ("6. Recommender 5", "rec5_title", "Recommender 5 - Professional Title", "text", False),
    ("6. Recommender 5", "rec5_organization", "Recommender 5 - Organization/Institution", "text", False),
    ("6. Recommender 5", "rec5_email", "Recommender 5 - Email Address", "email", False),
    ("6. Recommender 5", "rec5_relationship", "Recommender 5 - Relationship to You", "text", False),
    ("6. Recommender 5", "rec5_letter_status", "Recommender 5 - Letter Status", "select", False),

    # Section 7: Letters of Recommendation - Recommender 6 (6 fields)
    ("7. Recommender 6", "rec6_name", "Recommender 6 - Full Name", "text", False),
    ("7. Recommender 6", "rec6_title", "Recommender 6 - Professional Title", "text", False),
    ("7. Recommender 6", "rec6_organization", "Recommender 6 - Organization/Institution", "text", False),
    ("7. Recommender 6", "rec6_email", "Recommender 6 - Email Address", "email", False),
    ("7. Recommender 6", "rec6_relationship", "Recommender 6 - Relationship to You", "text", False),
    ("7. Recommender 6", "rec6_letter_status", "Recommender 6 - Letter Status", "select", False),

    # Section 8: Evidence Inventory (4 fields)
    ("8. Evidence Inventory", "total_awards_count", "Total Number of Awards/Prizes", "number", True),
    ("8. Evidence Inventory", "total_memberships_count", "Total Number of Exclusive Memberships", "number", True),
    ("8. Evidence Inventory", "total_publications_count", "Total Number of Publications/Articles", "number", True),
    ("8. Evidence Inventory", "total_judging_invitations_count", "Total Number of Judging/Reviewing Invitations", "number", True),
]

# =======================================================================================
# TEMPLATE 103: EB-1A CRITERIA DEEP-DIVE (60 fields)
# This template is repeatable - client fills once per claimed criterion
# =======================================================================================
TEMPLATE_103_FIELDS = [
    # Awards (7 fields)
    ("Awards", "award_name", "Name of Award/Prize", "text", False),
    ("Awards", "award_date", "Date Received", "date", False),
    ("Awards", "award_organization", "Awarding Organization", "text", False),
    ("Awards", "award_scope", "National or International?", "select", False),
    ("Awards", "award_selection_criteria", "Selection Criteria", "textarea", False),
    ("Awards", "award_significance", "Significance in Your Field", "textarea", False),
    ("Awards", "award_proof_documents", "Supporting Documents Uploaded", "textarea", False),

    # Memberships (7 fields)
    ("Memberships", "membership_organization", "Organization Name", "text", False),
    ("Membership", "membership_requirements", "Membership Requirements", "textarea", False),
    ("Memberships", "membership_selection_process", "Selection/Admission Process", "textarea", False),
    ("Memberships", "membership_leadership_role", "Leadership Role (if any)", "text", False),
    ("Memberships", "membership_start_date", "Membership Start Date", "date", False),
    ("Memberships", "membership_end_date", "Membership End Date (if applicable)", "date", False),
    ("Memberships", "membership_proof_documents", "Supporting Documents Uploaded", "textarea", False),

    # Published Material About You (9 fields)
    ("Published Material", "pubmat_title", "Title of Article/Feature", "text", False),
    ("Published Material", "pubmat_publication_name", "Publication Name", "text", False),
    ("Published Material", "pubmat_date", "Publication Date", "date", False),
    ("Published Material", "pubmat_circulation_reach", "Circulation/Reach", "text", False),
    ("Published Material", "pubmat_online_url", "Online URL (if available)", "text", False),
    ("Published Material", "pubmat_about_your_work", "What aspect of your work was covered?", "textarea", False),
    ("Published Material", "pubmat_quotes", "Were you quoted? (paste quotes)", "textarea", False),
    ("Published Material", "pubmat_significance", "Significance of this coverage", "textarea", False),
    ("Published Material", "pubmat_proof_documents", "Supporting Documents Uploaded", "textarea", False),

    # Judging/Reviewing (7 fields)
    ("Judging", "judging_event_name", "Event/Publication/Grant Name", "text", False),
    ("Judging", "judging_role", "Your Role (reviewer, panelist, judge, editor)", "text", False),
    ("Judging", "judging_start_date", "Start Date", "date", False),
    ("Judging", "judging_end_date", "End Date (if applicable)", "date", False),
    ("Judging", "judging_scope", "Scope (national, international, peer-reviewed)", "textarea", False),
    ("Judging", "judging_how_selected", "How were you selected for this role?", "textarea", False),
    ("Judging", "judging_proof_documents", "Supporting Documents Uploaded", "textarea", False),

    # Original Contributions (8 fields)
    ("Original Contributions", "contrib_type", "Type of Contribution (research, innovation, methodology, etc.)", "text", False),
    ("Original Contributions", "contrib_description", "Detailed Description", "textarea", False),
    ("Original Contributions", "contrib_adoption", "Who has adopted/used your contribution?", "textarea", False),
    ("Original Contributions", "contrib_citations", "Number of Citations (if research)", "number", False),
    ("Original Contributions", "contrib_patents", "Patents Granted/Pending (if any)", "text", False),
    ("Original Contributions", "contrib_industry_impact", "Industry/Field Impact", "textarea", False),
    ("Original Contributions", "contrib_expert_letters", "Expert Testimonial Letters Uploaded", "textarea", False),
    ("Original Contributions", "contrib_proof_documents", "Supporting Documents Uploaded", "textarea", False),

    # Scholarly Articles (9 fields)
    ("Scholarly Articles", "article_title", "Article Title", "text", False),
    ("Scholarly Articles", "article_journal_name", "Journal/Conference Name", "text", False),
    ("Scholarly Articles", "article_publication_date", "Publication Date", "date", False),
    ("Scholarly Articles", "article_doi", "DOI or URL", "text", False),
    ("Scholarly Articles", "article_coauthors", "Co-Authors (if any)", "text", False),
    ("Scholarly Articles", "article_citations", "Number of Citations", "number", False),
    ("Scholarly Articles", "article_journal_impact_factor", "Journal Impact Factor", "text", False),
    ("Scholarly Articles", "article_your_h_index", "Your H-Index (if applicable)", "text", False),
    ("Scholarly Articles", "article_proof_documents", "Supporting Documents Uploaded", "textarea", False),

    # Leading/Critical Role (7 fields)
    ("Leading Role", "leading_role_title", "Position/Title", "text", False),
    ("Leading Role", "leading_role_organization", "Organization Name", "text", False),
    ("Leading Role", "leading_role_responsibilities", "Key Responsibilities", "textarea", False),
    ("Leading Role", "leading_role_achievements", "Key Achievements in This Role", "textarea", False),
    ("Leading Role", "leading_role_team_size", "Team Size (if applicable)", "number", False),
    ("Leading Role", "leading_role_start_date", "Start Date", "date", False),
    ("Leading Role", "leading_role_end_date", "End Date (if applicable)", "date", False),

    # High Salary (6 fields)
    ("High Salary", "salary_current_amount", "Current Annual Salary (USD)", "number", False),
    ("High Salary", "salary_industry_data", "Industry Average Salary (source: BLS, Glassdoor, etc.)", "text", False),
    ("High Salary", "salary_percentile", "Your Salary Percentile in Your Field", "text", False),
    ("High Salary", "salary_bonuses_stock", "Bonuses/Stock Options (if any)", "text", False),
    ("High Salary", "salary_comparison_evidence", "Salary Comparison Evidence Uploaded", "textarea", False),
    ("High Salary", "salary_proof_documents", "Supporting Documents Uploaded", "textarea", False),
]

# =======================================================================================
# TEMPLATE 104: EB-1A SUPPORTING STATEMENT DATA (25 fields)
# Narrative content for the petition letter
# =======================================================================================
TEMPLATE_104_FIELDS = [
    # Section 1: Field of Expertise (5 fields)
    ("1. Field of Expertise", "field_description", "Describe your field of expertise in detail", "textarea", True),
    ("1. Field of Expertise", "field_us_relevance", "Why is your field relevant to the United States?", "textarea", True),
    ("1. Field of Expertise", "field_challenges", "What are the major challenges in your field?", "textarea", False),
    ("1. Field of Expertise", "field_growth_trends", "What are the growth trends in your field?", "textarea", False),
    ("1. Field of Expertise", "field_barriers_entry", "What are the barriers to entry in your field?", "textarea", False),

    # Section 2: Professional Journey (6 fields)
    ("2. Professional Journey", "journey_key_milestones", "Describe 3-5 key milestones in your career", "textarea", True),
    ("2. Professional Journey", "journey_breakthroughs", "What breakthroughs/innovations have you achieved?", "textarea", True),
    ("2. Professional Journey", "journey_recognition", "How has your work been recognized by peers/industry?", "textarea", True),
    ("2. Professional Journey", "journey_setbacks", "Have you overcome significant setbacks? (optional)", "textarea", False),
    ("2. Professional Journey", "journey_evolution", "How has your expertise evolved over time?", "textarea", False),
    ("2. Professional Journey", "journey_unique_path", "What makes your career path unique?", "textarea", False),

    # Section 3: Impact of Your Work (5 fields)
    ("3. Impact", "impact_field", "How has your work impacted your field?", "textarea", True),
    ("3. Impact", "impact_applications", "Real-world applications of your work", "textarea", True),
    ("3. Impact", "impact_beneficiaries", "Who has benefited from your work?", "textarea", True),
    ("3. Impact", "impact_scale", "What is the scale of your impact? (national, international)", "textarea", False),
    ("3. Impact", "impact_testimonials", "Key quotes from experts about your work", "textarea", False),

    # Section 4: Future Plans in the U.S. (5 fields)
    ("4. Future Plans", "future_us_work", "What will you work on in the United States?", "textarea", True),
    ("4. Future Plans", "future_projects", "Describe specific projects/initiatives you plan to undertake", "textarea", True),
    ("4. Future Plans", "future_timeline", "What is your 3-5 year plan?", "textarea", False),
    ("4. Future Plans", "future_collaborations", "Potential collaborations with U.S. institutions/companies", "textarea", False),
    ("4. Future Plans", "future_expected_outcomes", "Expected outcomes/impact of your U.S. work", "textarea", False),

    # Section 5: Synthesis (4 fields)
    ("5. Synthesis", "synthesis_criteria_met", "Summarize how you meet the EB-1A criteria", "textarea", True),
    ("5. Synthesis", "synthesis_distinction", "What distinguishes you from others in your field?", "textarea", True),
    ("5. Synthesis", "synthesis_unique_value", "What unique value will you bring to the U.S.?", "textarea", True),
    ("5. Synthesis", "synthesis_final_statement", "Closing statement (why you qualify for EB-1A)", "textarea", False),
]


def create_template(name, description, category, fields):
    """
    Insert template and fields into database.
    Idempotent - can run multiple times safely.
    """
    with engine.connect() as conn:
        # Check if template exists
        result = conn.execute(
            text("SELECT id FROM questionnaire_templates WHERE name = :name"),
            {"name": name}
        )
        row = result.fetchone()

        if row:
            template_id = row[0]
            print(f"  Found existing template '{name}': ID {template_id}")
            # Delete old fields for idempotency
            conn.execute(
                text("DELETE FROM questionnaire_fields WHERE template_id = :tid"),
                {"tid": template_id}
            )
            print(f"  Deleted old fields for template {template_id}")
        else:
            # Create new template
            result = conn.execute(text("""
                INSERT INTO questionnaire_templates
                (name, description, category, target_type, is_active, is_required)
                VALUES (:name, :desc, :cat, 'case', true, true)
                RETURNING id
            """), {"name": name, "desc": description, "cat": category})
            template_id = result.fetchone()[0]
            print(f"  Created new template '{name}': ID {template_id}")

        # Insert all fields
        for i, (section, field_name, label, field_type, required) in enumerate(fields):
            conn.execute(text("""
                INSERT INTO questionnaire_fields
                (template_id, field_name, label, field_type, is_required, section, "order")
                VALUES (:tid, :fname, :label, :ftype, :req, :section, :ord)
            """), {
                'tid': template_id,
                'fname': field_name,
                'label': label,
                'ftype': field_type,
                'req': required,
                'section': section,
                'ord': i + 1
            })

        conn.commit()
        print(f"  ✅ Inserted {len(fields)} fields into template {template_id}\n")
        return template_id


if __name__ == "__main__":
    print("=" * 80)
    print("EB-1A QUESTIONNAIRE TEMPLATES - SEEDING SCRIPT")
    print("=" * 80)
    print()

    # Create all 4 templates
    print("Creating Template 101: EB-1A Personal Information & Eligibility")
    t101 = create_template(
        "EB-1A Personal Information & Eligibility",
        "Personal details, immigration status, education, employment, and EB-1A criteria eligibility checklist",
        "EB-1A Extraordinary Ability",
        TEMPLATE_101_FIELDS
    )

    print("Creating Template 102: EB-1A Evidence Checklist & Metadata")
    t102 = create_template(
        "EB-1A Evidence Checklist & Metadata",
        "Required documents checklist, letters of recommendation tracking, and evidence inventory counts",
        "EB-1A Extraordinary Ability",
        TEMPLATE_102_FIELDS
    )

    print("Creating Template 103: EB-1A Criteria Deep-Dive")
    t103 = create_template(
        "EB-1A Criteria Deep-Dive",
        "Detailed evidence for each claimed EB-1A criterion (awards, memberships, publications, judging, contributions, etc.)",
        "EB-1A Extraordinary Ability",
        TEMPLATE_103_FIELDS
    )

    print("Creating Template 104: EB-1A Supporting Statement Data")
    t104 = create_template(
        "EB-1A Supporting Statement Data",
        "Narrative content for petition letter: field expertise, professional journey, impact, future plans, and synthesis",
        "EB-1A Extraordinary Ability",
        TEMPLATE_104_FIELDS
    )

    print("=" * 80)
    print("✅ SEEDING COMPLETE!")
    print("=" * 80)
    print(f"Template 101 (Personal Info & Eligibility): ID {t101} - {len(TEMPLATE_101_FIELDS)} fields")
    print(f"Template 102 (Evidence Checklist): ID {t102} - {len(TEMPLATE_102_FIELDS)} fields")
    print(f"Template 103 (Criteria Deep-Dive): ID {t103} - {len(TEMPLATE_103_FIELDS)} fields")
    print(f"Template 104 (Supporting Statement): ID {t104} - {len(TEMPLATE_104_FIELDS)} fields")
    print(f"\nTotal: {len(TEMPLATE_101_FIELDS) + len(TEMPLATE_102_FIELDS) + len(TEMPLATE_103_FIELDS) + len(TEMPLATE_104_FIELDS)} fields across 4 templates")
    print()
