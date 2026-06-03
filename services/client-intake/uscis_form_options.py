#!/usr/bin/env python3
"""
USCIS Form Standard Options
All dropdown and radio options for USCIS forms following OFFICIAL USCIS standards.
Source: https://www.uscis.gov/sites/default/files/document/forms/i-130.pdf
        https://www.uscis.gov/sites/default/files/document/forms/i-130instr.pdf
"""
import json

# ============================================================================
# RELATIONSHIP OPTIONS (I-130 Part 1, Question 1)
# Official USCIS: "I am filing this petition for my:"
# ============================================================================
RELATIONSHIP_OPTIONS = [
    {"value": "Spouse", "label": "Spouse"},
    {"value": "Parent", "label": "Parent"},
    {"value": "Brother/Sister", "label": "Brother/Sister"},
    {"value": "Child", "label": "Child"}
]

# ============================================================================
# YES/NO OPTIONS (for all radio fields)
# ============================================================================
YES_NO_OPTIONS = [
    {"value": "Yes", "label": "Yes"},
    {"value": "No", "label": "No"}
]

# ============================================================================
# SEX OPTIONS (Official USCIS)
# ============================================================================
SEX_OPTIONS = [
    {"value": "Male", "label": "Male"},
    {"value": "Female", "label": "Female"}
]

# ============================================================================
# MARITAL STATUS OPTIONS (Official USCIS - Part 2H, Question 22)
# Source: USCIS I-130 Form
# ============================================================================
MARITAL_STATUS_OPTIONS = [
    {"value": "Single", "label": "Single, Never Married"},
    {"value": "Married", "label": "Married"},
    {"value": "Divorced", "label": "Divorced"},
    {"value": "Widowed", "label": "Widowed"},
    {"value": "Separated", "label": "Separated"},
    {"value": "Annulled", "label": "Marriage Annulled"}
]

# ============================================================================
# ETHNICITY OPTIONS (Official USCIS - Part 3A, Question 1)
# Source: USCIS I-130 Instructions - "Are you Hispanic or Latino?"
# ============================================================================
ETHNICITY_OPTIONS = [
    {"value": "Hispanic", "label": "Hispanic or Latino"},
    {"value": "Not_Hispanic", "label": "Not Hispanic or Latino"}
]

# ============================================================================
# RACE OPTIONS (Official USCIS - Part 3B)
# NOTE: These are checkboxes (can select multiple), not a select dropdown
# Source: USCIS I-130 Form Part 3B
# ============================================================================
RACE_OPTIONS = [
    {"value": "White", "label": "White"},
    {"value": "Asian", "label": "Asian"},
    {"value": "Black", "label": "Black or African American"},
    {"value": "American_Indian", "label": "American Indian or Alaska Native"},
    {"value": "Pacific_Islander", "label": "Native Hawaiian or Other Pacific Islander"}
]

# ============================================================================
# EYE COLOR OPTIONS (Official USCIS - Part 3C, Question 5)
# Source: USCIS I-130 Form "Select the box that best describes the color of your eyes"
# ============================================================================
EYE_COLOR_OPTIONS = [
    {"value": "Black", "label": "Black"},
    {"value": "Blue", "label": "Blue"},
    {"value": "Brown", "label": "Brown"},
    {"value": "Gray", "label": "Gray"},
    {"value": "Green", "label": "Green"},
    {"value": "Hazel", "label": "Hazel"},
    {"value": "Maroon", "label": "Maroon"},
    {"value": "Pink", "label": "Pink"},
    {"value": "Unknown", "label": "Unknown/Other"}
]

# ============================================================================
# HAIR COLOR OPTIONS (Official USCIS - Part 3C, Question 6)
# Source: USCIS I-130 Form "Select the box that best describes the color of your hair"
# ============================================================================
HAIR_COLOR_OPTIONS = [
    {"value": "Bald", "label": "Bald (No hair)"},
    {"value": "Black", "label": "Black"},
    {"value": "Blond", "label": "Blond"},
    {"value": "Brown", "label": "Brown"},
    {"value": "Gray", "label": "Gray"},
    {"value": "Red", "label": "Red"},
    {"value": "Sandy", "label": "Sandy"},
    {"value": "White", "label": "White"},
    {"value": "Unknown", "label": "Unknown/Other"}
]

# ============================================================================
# APT/STE/FLR TYPE OPTIONS (Official USCIS)
# ============================================================================
APT_TYPE_OPTIONS = [
    {"value": "Apt", "label": "Apt."},
    {"value": "Ste", "label": "Ste."},
    {"value": "Flr", "label": "Flr."}
]

# ============================================================================
# HOW CITIZENSHIP WAS ACQUIRED (Official USCIS - Part 2G, Question 16)
# "If you are a U.S. citizen, how did you become a U.S. citizen?"
# ============================================================================
CITIZENSHIP_HOW_OPTIONS = [
    {"value": "Birth_US", "label": "Birth in the United States"},
    {"value": "Birth_Abroad", "label": "Birth abroad to U.S. citizen parent(s)"},
    {"value": "Naturalization", "label": "Naturalization"},
    {"value": "Parents_Naturalization", "label": "Parents' naturalization (before age 18)"},
    {"value": "Other", "label": "Other (explain in Additional Information)"}
]

# ============================================================================
# PRIOR PETITION RESULT (Part 5A, Question 6)
# ============================================================================
PETITION_RESULT_OPTIONS = [
    {"value": "Approved", "label": "Approved"},
    {"value": "Denied", "label": "Denied"},
    {"value": "Withdrawn", "label": "Withdrawn"}
]

# ============================================================================
# CLASS OF ADMISSION (for LPR - Part 2G, Question 20)
# Common visa categories
# ============================================================================
CLASS_OF_ADMISSION_OPTIONS = [
    {"value": "IR1", "label": "IR1 - Spouse of U.S. Citizen"},
    {"value": "IR2", "label": "IR2 - Child of U.S. Citizen"},
    {"value": "IR5", "label": "IR5 - Parent of U.S. Citizen"},
    {"value": "CR1", "label": "CR1 - Conditional Resident Spouse"},
    {"value": "F1", "label": "F1 - Unmarried Adult Child of U.S. Citizen"},
    {"value": "F2A", "label": "F2A - Spouse/Child of LPR"},
    {"value": "F2B", "label": "F2B - Unmarried Adult Child of LPR"},
    {"value": "F3", "label": "F3 - Married Adult Child of U.S. Citizen"},
    {"value": "F4", "label": "F4 - Sibling of Adult U.S. Citizen"},
    {"value": "EB1", "label": "EB-1 - Priority Worker"},
    {"value": "EB2", "label": "EB-2 - Advanced Degree/Exceptional Ability"},
    {"value": "EB3", "label": "EB-3 - Skilled/Professional Worker"},
    {"value": "EB4", "label": "EB-4 - Special Immigrant"},
    {"value": "EB5", "label": "EB-5 - Investor"},
    {"value": "DV", "label": "DV - Diversity Visa"},
    {"value": "Asylee", "label": "Asylee"},
    {"value": "Refugee", "label": "Refugee"},
    {"value": "K1", "label": "K-1 Fiancé(e)"},
    {"value": "Other", "label": "Other"}
]

# ============================================================================
# US STATES AND TERRITORIES (Official USCIS)
# ============================================================================
US_STATES_OPTIONS = [
    {"value": "AL", "label": "Alabama"},
    {"value": "AK", "label": "Alaska"},
    {"value": "AZ", "label": "Arizona"},
    {"value": "AR", "label": "Arkansas"},
    {"value": "CA", "label": "California"},
    {"value": "CO", "label": "Colorado"},
    {"value": "CT", "label": "Connecticut"},
    {"value": "DE", "label": "Delaware"},
    {"value": "DC", "label": "District of Columbia"},
    {"value": "FL", "label": "Florida"},
    {"value": "GA", "label": "Georgia"},
    {"value": "HI", "label": "Hawaii"},
    {"value": "ID", "label": "Idaho"},
    {"value": "IL", "label": "Illinois"},
    {"value": "IN", "label": "Indiana"},
    {"value": "IA", "label": "Iowa"},
    {"value": "KS", "label": "Kansas"},
    {"value": "KY", "label": "Kentucky"},
    {"value": "LA", "label": "Louisiana"},
    {"value": "ME", "label": "Maine"},
    {"value": "MD", "label": "Maryland"},
    {"value": "MA", "label": "Massachusetts"},
    {"value": "MI", "label": "Michigan"},
    {"value": "MN", "label": "Minnesota"},
    {"value": "MS", "label": "Mississippi"},
    {"value": "MO", "label": "Missouri"},
    {"value": "MT", "label": "Montana"},
    {"value": "NE", "label": "Nebraska"},
    {"value": "NV", "label": "Nevada"},
    {"value": "NH", "label": "New Hampshire"},
    {"value": "NJ", "label": "New Jersey"},
    {"value": "NM", "label": "New Mexico"},
    {"value": "NY", "label": "New York"},
    {"value": "NC", "label": "North Carolina"},
    {"value": "ND", "label": "North Dakota"},
    {"value": "OH", "label": "Ohio"},
    {"value": "OK", "label": "Oklahoma"},
    {"value": "OR", "label": "Oregon"},
    {"value": "PA", "label": "Pennsylvania"},
    {"value": "RI", "label": "Rhode Island"},
    {"value": "SC", "label": "South Carolina"},
    {"value": "SD", "label": "South Dakota"},
    {"value": "TN", "label": "Tennessee"},
    {"value": "TX", "label": "Texas"},
    {"value": "UT", "label": "Utah"},
    {"value": "VT", "label": "Vermont"},
    {"value": "VA", "label": "Virginia"},
    {"value": "WA", "label": "Washington"},
    {"value": "WV", "label": "West Virginia"},
    {"value": "WI", "label": "Wisconsin"},
    {"value": "WY", "label": "Wyoming"},
    # US Territories
    {"value": "AS", "label": "American Samoa"},
    {"value": "GU", "label": "Guam"},
    {"value": "MP", "label": "Northern Mariana Islands"},
    {"value": "PR", "label": "Puerto Rico"},
    {"value": "VI", "label": "U.S. Virgin Islands"},
    # Armed Forces
    {"value": "AA", "label": "Armed Forces Americas"},
    {"value": "AE", "label": "Armed Forces Europe/Africa/Middle East"},
    {"value": "AP", "label": "Armed Forces Pacific"}
]

# ============================================================================
# I-130 FIELD TO OPTIONS MAPPING
# Maps each select/radio field to its correct options
# ============================================================================
I130_OPTIONS_MAP = {
    # Part 1 - Relationship
    "p1_1_filing_for": RELATIONSHIP_OPTIONS,
    "p1_3_sibling_adoption": YES_NO_OPTIONS,
    "p1_4_lpr_adoption": YES_NO_OPTIONS,
    "p1_5_step_relationship": YES_NO_OPTIONS,

    # Part 2 - Petitioner Information
    "p2_7c_mail_apt_type": APT_TYPE_OPTIONS,
    "p2_7f_mail_state": US_STATES_OPTIONS,
    "p2_8_same_as_mailing": YES_NO_OPTIONS,
    "p2_9b_phys_apt_type": APT_TYPE_OPTIONS,
    "p2_9e_phys_state": US_STATES_OPTIONS,
    "p2_16_citizenship_how": CITIZENSHIP_HOW_OPTIONS,
    "p2_20_class_admission": CLASS_OF_ADMISSION_OPTIONS,
    "p2_22_marital_status": MARITAL_STATUS_OPTIONS,
    "p2_25d_emp_state": US_STATES_OPTIONS,

    # Part 3 - Biographic Information
    "p3_1_ethnicity": ETHNICITY_OPTIONS,
    "p3_5_eye_color": EYE_COLOR_OPTIONS,
    "p3_6_hair_color": HAIR_COLOR_OPTIONS,

    # Part 4 - Beneficiary Information
    "p4_7b_apt_type": APT_TYPE_OPTIONS,
    "p4_13_sex": SEX_OPTIONS,
    "p4_14_marital_status": MARITAL_STATUS_OPTIONS,
    "p4_16_in_us": YES_NO_OPTIONS,
    "p4_19_last_entry_state": US_STATES_OPTIONS,
    "p4_29_father_sex": SEX_OPTIONS,
    "p4_36_mother_sex": SEX_OPTIONS,

    # Part 5 - Other Information
    "p5_1_prior_petition": YES_NO_OPTIONS,
    "p5_6_prior_result": PETITION_RESULT_OPTIONS,
    "p5_7_beneficiary_proceedings": YES_NO_OPTIONS,
    "p5_8_beneficiary_removed": YES_NO_OPTIONS,
    "p5_9_beneficiary_ina212": YES_NO_OPTIONS,

    # Part 7 - Interpreter
    "p7_3d_interp_state": US_STATES_OPTIONS,

    # Part 8 - Preparer
    "p8_4d_prep_state": US_STATES_OPTIONS,
    "p8_8_prep_extends": YES_NO_OPTIONS,
}

# ============================================================================
# I-485 SPECIFIC OPTIONS
# ============================================================================

# Application Type (I-485)
I485_APPLICATION_TYPE_OPTIONS = [
    {"value": "Family", "label": "Family-Sponsored Immigrant"},
    {"value": "Employment", "label": "Employment-Based Immigrant"},
    {"value": "Diversity", "label": "Diversity Immigrant (DV Lottery)"},
    {"value": "Special", "label": "Special Immigrant"},
    {"value": "Asylee", "label": "Asylee or Refugee"},
    {"value": "VAWA", "label": "VAWA Self-Petitioner"},
    {"value": "Other", "label": "Other"}
]

# ============================================================================
# I-765 SPECIFIC OPTIONS
# ============================================================================

# Eligibility Category (I-765) - Most common categories
I765_ELIGIBILITY_OPTIONS = [
    {"value": "(a)(3)", "label": "(a)(3) - Refugee"},
    {"value": "(a)(4)", "label": "(a)(4) - Paroled as Refugee"},
    {"value": "(a)(5)", "label": "(a)(5) - Asylee"},
    {"value": "(a)(7)", "label": "(a)(7) - N-8 or N-9 Nonimmigrant"},
    {"value": "(a)(10)", "label": "(a)(10) - Withholding of Deportation Granted"},
    {"value": "(c)(9)", "label": "(c)(9) - Adjustment Applicant (filed I-485)"},
    {"value": "(c)(10)", "label": "(c)(10) - Adjustment Applicant (I-485 pending 180+ days)"},
    {"value": "(c)(14)", "label": "(c)(14) - Deferred Action (DACA)"},
    {"value": "(c)(26)", "label": "(c)(26) - H-4 Dependent Spouse"},
    {"value": "(c)(33)", "label": "(c)(33) - Compelling Circumstances EAD"},
    {"value": "(c)(35)", "label": "(c)(35) - Principal Beneficiary of Approved I-140"},
    {"value": "(c)(36)", "label": "(c)(36) - Spouse/Child of (c)(35) Principal"},
    {"value": "Other", "label": "Other (see I-765 instructions)"}
]

# ============================================================================
# I-131 SPECIFIC OPTIONS
# ============================================================================

# Application Type (I-131)
I131_APPLICATION_TYPE_OPTIONS = [
    {"value": "Reentry_Permit", "label": "Reentry Permit"},
    {"value": "Refugee_Travel", "label": "Refugee Travel Document"},
    {"value": "Advance_Parole", "label": "Advance Parole Document"},
    {"value": "TPS_Travel", "label": "TPS Travel Authorization"}
]

# ============================================================================
# I-864 SPECIFIC OPTIONS
# ============================================================================

# Sponsor Type (I-864)
I864_SPONSOR_TYPE_OPTIONS = [
    {"value": "Petitioner", "label": "I am the petitioner who filed or will file Form I-130"},
    {"value": "Joint_Sponsor", "label": "I am a joint sponsor"},
    {"value": "Substitute_Sponsor", "label": "I am a substitute sponsor"},
    {"value": "Household_Member", "label": "I am only using my income to meet requirements as a household member"}
]

# ============================================================================
# HELPER FUNCTION - Get options for any field
# ============================================================================
# ============================================================================
# ADDITIONAL OPTIONS FOR I-485
# ============================================================================

# Relationship to Principal Applicant (I-485 Part 2D)
RELATIONSHIP_TO_PRINCIPAL_OPTIONS = [
    {"value": "Spouse", "label": "Spouse of Principal"},
    {"value": "Child", "label": "Child of Principal"},
    {"value": "NA", "label": "Not Applicable (I am the principal)"}
]

# Pickup location for travel documents (I-131)
PICKUP_LOCATION_OPTIONS = [
    {"value": "USCIS", "label": "USCIS Office"},
    {"value": "Embassy", "label": "U.S. Embassy or Consulate Abroad"}
]

# ============================================================================
# I-485 FIELD TO OPTIONS MAPPING
# ============================================================================
I485_OPTIONS_MAP = {
    # Part 1 - Personal Information
    "p1_6_sex": SEX_OPTIONS,
    "p1_14c_apt_type": APT_TYPE_OPTIONS,
    "p1_14f_state": US_STATES_OPTIONS,
    "p1_15_safe_address": YES_NO_OPTIONS,
    "p1_16c_safe_apt_type": APT_TYPE_OPTIONS,
    "p1_16f_safe_state": US_STATES_OPTIONS,
    "p1_22b_arrival_state": US_STATES_OPTIONS,

    # Part 2 - Application Type
    "p2_1_eoir_proceeding": YES_NO_OPTIONS,
    "p2_6_principal_applicant": YES_NO_OPTIONS,
    "p2_10_relationship": RELATIONSHIP_TO_PRINCIPAL_OPTIONS,

    # Part 3 - I-864 Exemption
    "p3_1_claiming_exemption": YES_NO_OPTIONS,
    "p3_8_applied_immigrant_visa": YES_NO_OPTIONS,
    "p3_11_visa_approved": YES_NO_OPTIONS,
    "p3_12_visa_refused": YES_NO_OPTIONS,
    "p3_13_visa_withdrawn": YES_NO_OPTIONS,

    # Part 4 - Addresses
    "p4_1b_apt_type": APT_TYPE_OPTIONS,
    "p4_1e_state": US_STATES_OPTIONS,
    "p4_4d_prev1_state": US_STATES_OPTIONS,
    "p4_7d_prev2_state": US_STATES_OPTIONS,
    "p4_14d_emp_state": US_STATES_OPTIONS,
    "p4_19c_prev_emp1_state": US_STATES_OPTIONS,

    # Part 5 - Parents
    "p5_3_parent1_sex": SEX_OPTIONS,
    "p5_10_parent2_sex": SEX_OPTIONS,

    # Part 6 - Marital History
    "p6_1_marital_status": MARITAL_STATUS_OPTIONS,
    "p6_9b_marriage_state": US_STATES_OPTIONS,
    "p6_10_spouse_in_us": YES_NO_OPTIONS,
    "p6_11_spouse_applying_together": YES_NO_OPTIONS,

    # Part 7 - Children
    "p7_6_child1_in_us": YES_NO_OPTIONS,
    "p7_7_child1_applying": YES_NO_OPTIONS,
    "p7_12_child2_in_us": YES_NO_OPTIONS,
    "p7_13_child2_applying": YES_NO_OPTIONS,
    "p7_17_child3_in_us": YES_NO_OPTIONS,

    # Part 8 - Biographic Information
    "p8_1_ethnicity": ETHNICITY_OPTIONS,
    "p8_5_eye_color": EYE_COLOR_OPTIONS,
    "p8_6_hair_color": HAIR_COLOR_OPTIONS,

    # Part 9 - Eligibility and Inadmissibility (ALL YES/NO)
    "p9_1_member_org": YES_NO_OPTIONS,
    "p9_4_communist_totalitarian": YES_NO_OPTIONS,
    "p9_5_nazi_government": YES_NO_OPTIONS,
    "p9_6_military_service": YES_NO_OPTIONS,
    "p9_8_weapons_training": YES_NO_OPTIONS,
    "p9_10_worked_unauthorized": YES_NO_OPTIONS,
    "p9_11_violated_status": YES_NO_OPTIONS,
    "p9_12_immigration_fraud": YES_NO_OPTIONS,
    "p9_13_falsely_claimed_citizen": YES_NO_OPTIONS,
    "p9_14_stowaway": YES_NO_OPTIONS,
    "p9_15_alien_smuggling": YES_NO_OPTIONS,
    "p9_16_document_fraud": YES_NO_OPTIONS,
    "p9_17_removed_deported": YES_NO_OPTIONS,
    "p9_18_ordered_removed": YES_NO_OPTIONS,
    "p9_19_voluntary_departure": YES_NO_OPTIONS,
    "p9_20_denied_visa": YES_NO_OPTIONS,
    "p9_21_denied_admission": YES_NO_OPTIONS,
    "p9_22_denied_i485": YES_NO_OPTIONS,
    "p9_23_in_proceedings": YES_NO_OPTIONS,
    "p9_24_final_order": YES_NO_OPTIONS,
    "p9_25_arrested": YES_NO_OPTIONS,
    "p9_26_not_charged": YES_NO_OPTIONS,
    "p9_28_convicted": YES_NO_OPTIONS,
    "p9_29_admitted_crime": YES_NO_OPTIONS,
    "p9_30_crime_moral_turpitude": YES_NO_OPTIONS,
    "p9_31_controlled_substance": YES_NO_OPTIONS,
    "p9_32_drug_trafficker": YES_NO_OPTIONS,
    "p9_33_drug_abuser": YES_NO_OPTIONS,
    "p9_34_multiple_convictions": YES_NO_OPTIONS,
    "p9_35_prostitution": YES_NO_OPTIONS,
    "p9_36_commercialized_vice": YES_NO_OPTIONS,
    "p9_37_human_trafficking": YES_NO_OPTIONS,
    "p9_38_money_laundering": YES_NO_OPTIONS,
    "p9_39_domestic_violence": YES_NO_OPTIONS,
    "p9_40_restraining_order": YES_NO_OPTIONS,
    "p9_41_juvenile_court": YES_NO_OPTIONS,
    "p9_42_espionage": YES_NO_OPTIONS,
    "p9_43_sabotage": YES_NO_OPTIONS,
    "p9_44_overthrow_govt": YES_NO_OPTIONS,
    "p9_45_terrorist_activity": YES_NO_OPTIONS,
    "p9_46_terrorist_member": YES_NO_OPTIONS,
    "p9_47_terrorist_support": YES_NO_OPTIONS,
    "p9_48_terrorist_training": YES_NO_OPTIONS,
    "p9_49_genocide": YES_NO_OPTIONS,
    "p9_50_torture": YES_NO_OPTIONS,
    "p9_51_extrajudicial_killing": YES_NO_OPTIONS,
    "p9_52_severe_violations": YES_NO_OPTIONS,
    "p9_53_persecution": YES_NO_OPTIONS,
    "p9_54_nazi_persecution": YES_NO_OPTIONS,
    "p9_55_child_soldiers": YES_NO_OPTIONS,
    "p9_56_public_benefits": YES_NO_OPTIONS,
    "p9_57_received_benefits": YES_NO_OPTIONS,
    "p9_59_communicable_disease": YES_NO_OPTIONS,
    "p9_60_physical_mental_disorder": YES_NO_OPTIONS,
    "p9_61_drug_abuser": YES_NO_OPTIONS,
    "p9_62_voted_illegally": YES_NO_OPTIONS,
    "p9_63_renounced_citizenship": YES_NO_OPTIONS,
    "p9_64_unlawful_180_days": YES_NO_OPTIONS,
    "p9_65_unlawful_1_year": YES_NO_OPTIONS,
    "p9_66_reenter_after_removal": YES_NO_OPTIONS,
    "p9_67_polygamy": YES_NO_OPTIONS,
    "p9_68_guardian_custody": YES_NO_OPTIONS,
    "p9_69_unlawful_voters": YES_NO_OPTIONS,
    "p9_70_export_violations": YES_NO_OPTIONS,
    "p9_71_other_unlawful": YES_NO_OPTIONS,
    "p9_72_male_18_26": YES_NO_OPTIONS,
    "p9_73_registered_selective": YES_NO_OPTIONS,

    # Part 10 - Accommodations
    "p10_1_requesting": YES_NO_OPTIONS,

    # Part 12 - Interpreter
    "p12_3d_interp_state": US_STATES_OPTIONS,

    # Part 13 - Preparer
    "p13_4d_prep_state": US_STATES_OPTIONS,
    "p13_8_prep_extends": YES_NO_OPTIONS,
}

# ============================================================================
# I-864 FIELD TO OPTIONS MAPPING
# ============================================================================
I864_OPTIONS_MAP = {
    # Part 2 - Principal Immigrant
    "p2_2c_apt_type": APT_TYPE_OPTIONS,
    "p2_2f_state": US_STATES_OPTIONS,

    # Part 4 - Sponsor
    "p4_2c_apt_type": APT_TYPE_OPTIONS,
    "p4_2f_state": US_STATES_OPTIONS,
    "p4_12_active_duty": YES_NO_OPTIONS,

    # Part 6 - Income
    "p6_11_filed_taxes": YES_NO_OPTIONS,

    # Part 9 - Interpreter
    "p9_3d_interp_state": US_STATES_OPTIONS,

    # Part 10 - Preparer
    "p10_4d_prep_state": US_STATES_OPTIONS,
    "p10_8_prep_extends": YES_NO_OPTIONS,
}

# ============================================================================
# I-765 FIELD TO OPTIONS MAPPING
# ============================================================================
I765_OPTIONS_MAP = {
    # Part 1 - Reason
    "p1_2_previously_filed": YES_NO_OPTIONS,

    # Part 2 - Applicant Info
    "p2_2_other_names_used": YES_NO_OPTIONS,
    "p2_5c_apt_type": APT_TYPE_OPTIONS,
    "p2_5f_state": US_STATES_OPTIONS,
    "p2_6_safe_address": YES_NO_OPTIONS,
    "p2_7b_phys_apt_type": APT_TYPE_OPTIONS,
    "p2_7e_phys_state": US_STATES_OPTIONS,
    "p2_17_sex": SEX_OPTIONS,
    "p2_22_ssn_issued": YES_NO_OPTIONS,
    "p2_24_want_ssn": YES_NO_OPTIONS,
    "p2_35_stem_opt": YES_NO_OPTIONS,
    "p2_33_eligibility_category": I765_ELIGIBILITY_OPTIONS,
    "p2_44_marital_status": MARITAL_STATUS_OPTIONS,

    # Part 4 - Interpreter
    "p4_3d_interp_state": US_STATES_OPTIONS,

    # Part 5 - Preparer
    "p5_4d_prep_state": US_STATES_OPTIONS,
    "p5_8_prep_extends": YES_NO_OPTIONS,
}

# ============================================================================
# I-131 FIELD TO OPTIONS MAPPING
# ============================================================================
I131_OPTIONS_MAP = {
    # Part 2 - Personal Info
    "p2_2_other_names": YES_NO_OPTIONS,
    "p2_4b_apt_type": APT_TYPE_OPTIONS,
    "p2_4e_state": US_STATES_OPTIONS,
    "p2_5_same_as_physical": YES_NO_OPTIONS,
    "p2_6e_mail_state": US_STATES_OPTIONS,
    "p2_11_sex": SEX_OPTIONS,
    "p2_16_class_of_admission": CLASS_OF_ADMISSION_OPTIONS,

    # Part 3 - Biographic
    "p3_1_ethnicity": ETHNICITY_OPTIONS,
    "p3_2_race": RACE_OPTIONS,
    "p3_6_eye_color": EYE_COLOR_OPTIONS,
    "p3_7_hair_color": HAIR_COLOR_OPTIONS,

    # Part 4 - Processing
    "p4_1_where_to_pick_up": PICKUP_LOCATION_OPTIONS,
    "p4_3_safe_address": YES_NO_OPTIONS,
    "p4_4d_safe_state": US_STATES_OPTIONS,

    # Part 6 - Refugee Travel
    "p6_1_plan_travel_persecution": YES_NO_OPTIONS,
    "p6_2_applied_passport": YES_NO_OPTIONS,
    "p6_3_received_passport": YES_NO_OPTIONS,
    "p6_4_acquired_nationality": YES_NO_OPTIONS,
    "p6_5_granted_residence": YES_NO_OPTIONS,
    "p6_6_returned_persecution": YES_NO_OPTIONS,

    # Part 7 - Travel
    "p7_6_prev_advance_parole": YES_NO_OPTIONS,

    # Part 9 - EAD Request
    "p9_2_previous_ead": YES_NO_OPTIONS,

    # Part 11 - Interpreter
    "p11_3d_interp_state": US_STATES_OPTIONS,

    # Part 12 - Preparer
    "p12_4d_prep_state": US_STATES_OPTIONS,
    "p12_7_prep_extends": YES_NO_OPTIONS,
}
