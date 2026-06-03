"""
CaseHub - USCIS Forms Service
Library of USCIS forms with pre-population capabilities.
"""
import os
import json
from datetime import datetime
from typing import Dict, List, Optional
from io import BytesIO

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


# USCIS Form Definitions
# Forms with has_auto_fill=True have corresponding expand_*.py files for deep field mapping.
# The full catalog (300+) is browsable; 31 core forms have deep auto-fill support.
USCIS_FORMS = {
    # =========================================================================
    # I-Series (Immigration)
    # =========================================================================

    "I-9": {
        "name": "Employment Eligibility Verification",
        "category": "Employment-Based",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Verify identity and employment authorization of individuals hired for employment in the U.S.",
        "visa_types": ["All"],
        "pages": 3,
        "edition": "08/01/23",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-17": {
        "name": "Petition for Approval of School for Attendance by Nonimmigrant Student",
        "category": "Student",
        "fee": 1700,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Petition for a school to be approved to enroll F-1 or M-1 nonimmigrant students",
        "visa_types": ["F-1", "M-1"],
        "pages": 9,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-20": {
        "name": "Certificate of Eligibility for Nonimmigrant Student Status",
        "category": "Student",
        "fee": 350,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Certificate of Eligibility for F-1 student status",
        "visa_types": ["F-1"],
        "pages": 3,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-90": {
        "name": "Application to Replace Permanent Resident Card",
        "category": "Green Card",
        "fee": 455,
        "premium_fee": None,
        "processing_time": "6-12 months",
        "description": "Renew or replace a Permanent Resident Card (Green Card)",
        "visa_types": ["All"],
        "pages": 6,
        "edition": "04/01/24",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-94": {
        "name": "Arrival/Departure Record",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Record of arrival and departure from the U.S.",
        "visa_types": ["All"],
        "pages": 1,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-102": {
        "name": "Application for Replacement/Initial Nonimmigrant Arrival-Departure Document",
        "category": "Supporting",
        "fee": 445,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Replace a lost or stolen I-94 Arrival/Departure Record",
        "visa_types": ["All"],
        "pages": 4,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-129": {
        "name": "Petition for a Nonimmigrant Worker",
        "category": "Employment-Based",
        "fee": 460,
        "premium_fee": 2805,
        "processing_time": "2-6 months",
        "description": "Petition to bring a nonimmigrant worker to the U.S. temporarily",
        "visa_types": ["H-1B", "H-2A", "H-2B", "L-1A", "L-1B", "O-1", "P-1", "TN"],
        "pages": 36,
        "edition": "04/01/24",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-129CW": {
        "name": "Petition for a CNMI-Only Nonimmigrant Transitional Worker",
        "category": "Employment-Based",
        "fee": 460,
        "premium_fee": None,
        "processing_time": "3-6 months",
        "description": "Petition for transitional worker status in the Commonwealth of the Northern Mariana Islands",
        "visa_types": ["CW-1"],
        "pages": 15,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-129F": {
        "name": "Petition for Alien Fiance(e)",
        "category": "Family-Based",
        "fee": 535,
        "premium_fee": None,
        "processing_time": "6-12 months",
        "description": "Petition for K-1 fiance(e) or K-3 spouse nonimmigrant visa",
        "visa_types": ["K-1", "K-3"],
        "pages": 14,
        "edition": "04/01/24",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-129S": {
        "name": "Nonimmigrant Petition Based on Blanket L Petition",
        "category": "Employment-Based",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Supplement for individual L-1 beneficiaries under an approved blanket petition",
        "visa_types": ["L-1A", "L-1B"],
        "pages": 7,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-130": {
        "name": "Petition for Alien Relative",
        "category": "Family-Based",
        "fee": 625,
        "premium_fee": None,
        "processing_time": "12-24 months",
        "description": "Petition to establish relationship with foreign relative",
        "visa_types": ["IR-1", "IR-2", "F1", "F2A", "F2B", "F3", "F4"],
        "pages": 12,
        "edition": "04/01/24",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-130A": {
        "name": "Supplemental Information for Spouse Beneficiary",
        "category": "Family-Based",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Supplemental form for I-130 spouse petitions",
        "visa_types": ["IR-1", "CR-1"],
        "pages": 6,
        "edition": "04/01/24",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-131": {
        "name": "Application for Travel Document",
        "category": "Adjustment of Status",
        "fee": 630,
        "premium_fee": None,
        "processing_time": "3-6 months",
        "description": "Application for Advance Parole or Re-entry Permit",
        "visa_types": ["All"],
        "pages": 14,
        "edition": "01/20/25",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-131A": {
        "name": "Application for Travel Document (Carrier Documentation)",
        "category": "Adjustment of Status",
        "fee": 575,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Application for a travel document for a lawful permanent resident who is abroad without one",
        "visa_types": ["All"],
        "pages": 6,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-134": {
        "name": "Declaration of Financial Support",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Declaration of financial support for a nonimmigrant visitor",
        "visa_types": ["B-1", "B-2"],
        "pages": 6,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-134A": {
        "name": "Online Request to be a Supporter and Declaration of Financial Support",
        "category": "Humanitarian",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Financial support declaration for Uniting for Ukraine and other humanitarian parole processes",
        "visa_types": ["Humanitarian Parole"],
        "pages": 8,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-140": {
        "name": "Immigrant Petition for Alien Workers",
        "category": "Employment-Based",
        "fee": 700,
        "premium_fee": 2805,
        "processing_time": "6-12 months",
        "description": "Petition for permanent residence based on employment",
        "visa_types": ["EB-1A", "EB-1B", "EB-1C", "EB-2", "EB-2 NIW", "EB-3"],
        "pages": 10,
        "edition": "06/07/24",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-191": {
        "name": "Application for Relief Under Former Section 212(c) of the INA",
        "category": "Waivers",
        "fee": 930,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Application for discretionary relief from deportation under former INA 212(c)",
        "visa_types": ["All"],
        "pages": 5,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-192": {
        "name": "Application for Advance Permission to Enter as a Nonimmigrant",
        "category": "Waivers",
        "fee": 930,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Advance permission to enter the U.S. despite grounds of inadmissibility",
        "visa_types": ["All"],
        "pages": 5,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-193": {
        "name": "Application for Waiver of Passport and/or Visa",
        "category": "Waivers",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Application to waive the passport and/or visa documentary requirement",
        "visa_types": ["All"],
        "pages": 2,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-212": {
        "name": "Application for Permission to Reapply for Admission into the U.S.",
        "category": "Waivers",
        "fee": 930,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Permission to reapply for admission after deportation or removal",
        "visa_types": ["All"],
        "pages": 7,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-290B": {
        "name": "Notice of Appeal or Motion",
        "category": "Appeals",
        "fee": 715,
        "premium_fee": None,
        "processing_time": "6-12 months",
        "description": "Appeal an unfavorable decision or file a motion to reopen/reconsider",
        "visa_types": ["All"],
        "pages": 6,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-356": {
        "name": "Request for Cancellation of Public Charge Bond",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Request cancellation of a public charge bond",
        "visa_types": ["All"],
        "pages": 3,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-360": {
        "name": "Petition for Amerasian, Widow(er), or Special Immigrant",
        "category": "Special Immigrant",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "6-18 months",
        "description": "Petition for special immigrant categories including VAWA self-petitioners and religious workers",
        "visa_types": ["VAWA", "SIJ", "Religious Worker"],
        "pages": 14,
        "edition": "04/01/24",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-361": {
        "name": "Affidavit of Financial Support and Intent to Petition for Legal Custody for Public Law 97-359 Amerasian",
        "category": "Special Immigrant",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Financial support affidavit for Amerasian immigration",
        "visa_types": ["Amerasian"],
        "pages": 3,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-363": {
        "name": "Request to Enforce Affidavit of Financial Support and Intent to Petition",
        "category": "Special Immigrant",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Enforce a previously submitted affidavit of financial support for Amerasians",
        "visa_types": ["Amerasian"],
        "pages": 2,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-407": {
        "name": "Record of Abandonment of Lawful Permanent Resident Status",
        "category": "Green Card",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Voluntarily abandon lawful permanent resident status",
        "visa_types": ["All"],
        "pages": 1,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-485": {
        "name": "Application to Register Permanent Residence or Adjust Status",
        "category": "Adjustment of Status",
        "fee": 1225,
        "premium_fee": None,
        "processing_time": "12-36 months",
        "description": "Application to adjust status to permanent resident (Green Card)",
        "visa_types": ["All"],
        "pages": 24,
        "edition": "01/20/25",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-485J": {
        "name": "Confirmation of Bona Fide Job Offer or Request for Job Portability Under INA 204(j)",
        "category": "Adjustment of Status",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Supplement to I-485 confirming a bona fide job offer for employment-based adjustment",
        "visa_types": ["EB-1", "EB-2", "EB-3"],
        "pages": 3,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-508": {
        "name": "Request for Waiver of Certain Rights, Privileges, and Immunities",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Waiver of diplomatic or international organization immunities for permanent residence",
        "visa_types": ["All"],
        "pages": 2,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-508F": {
        "name": "Request for Waiver of Certain Rights, Privileges, and Immunities (French)",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "French-language version of I-508 waiver of diplomatic immunities",
        "visa_types": ["All"],
        "pages": 2,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-526": {
        "name": "Immigrant Petition by Standalone Investor",
        "category": "Investment",
        "fee": 3675,
        "premium_fee": None,
        "processing_time": "24-48 months",
        "description": "EB-5 Immigrant Investor Program petition",
        "visa_types": ["EB-5"],
        "pages": 14,
        "edition": "04/19/23",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-526E": {
        "name": "Immigrant Petition by Regional Center Investor",
        "category": "Investment",
        "fee": 3675,
        "premium_fee": None,
        "processing_time": "24-48 months",
        "description": "EB-5 petition through Regional Center",
        "visa_types": ["EB-5"],
        "pages": 10,
        "edition": "04/19/23",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-539": {
        "name": "Application to Extend/Change Nonimmigrant Status",
        "category": "Extensions",
        "fee": 370,
        "premium_fee": 1965,
        "processing_time": "3-12 months",
        "description": "Application to extend stay or change nonimmigrant status",
        "visa_types": ["B-1", "B-2", "F-1", "H-4", "L-2"],
        "pages": 11,
        "edition": "04/01/24",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-566": {
        "name": "Interagency Record of Request - A, G, or NATO Dependent Employment Authorization",
        "category": "Employment-Based",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Employment authorization for dependents of A, G, or NATO visa holders",
        "visa_types": ["A", "G", "NATO"],
        "pages": 2,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-589": {
        "name": "Application for Asylum and for Withholding of Removal",
        "category": "Humanitarian",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "6-24 months",
        "description": "Application for asylum and/or withholding of removal",
        "visa_types": ["Asylum"],
        "pages": 14,
        "edition": "04/01/24",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-590": {
        "name": "Registration for Classification as Refugee",
        "category": "Humanitarian",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Registration for refugee classification for overseas processing",
        "visa_types": ["Refugee"],
        "pages": 4,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-600": {
        "name": "Petition to Classify Orphan as an Immediate Relative",
        "category": "Family-Based",
        "fee": 775,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Petition to classify a foreign orphan as an immediate relative for adoption",
        "visa_types": ["IR-3", "IR-4"],
        "pages": 10,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-600A": {
        "name": "Application for Advance Processing of an Orphan Petition",
        "category": "Family-Based",
        "fee": 775,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Advance processing of an orphan petition before identifying a specific child",
        "visa_types": ["IR-3", "IR-4"],
        "pages": 7,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-601": {
        "name": "Application for Waiver of Grounds of Inadmissibility",
        "category": "Waivers",
        "fee": 930,
        "premium_fee": None,
        "processing_time": "6-24 months",
        "description": "Waiver of certain grounds of inadmissibility (e.g., fraud, unlawful presence)",
        "visa_types": ["All"],
        "pages": 10,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-601A": {
        "name": "Application for Provisional Unlawful Presence Waiver",
        "category": "Waivers",
        "fee": 630,
        "premium_fee": None,
        "processing_time": "6-18 months",
        "description": "Provisional waiver of unlawful presence for immediate relatives of U.S. citizens",
        "visa_types": ["All Family-Based"],
        "pages": 8,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-602": {
        "name": "Application by Refugee for Waiver of Inadmissibility Grounds",
        "category": "Humanitarian",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Waiver of inadmissibility grounds for refugees",
        "visa_types": ["Refugee"],
        "pages": 4,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-612": {
        "name": "Application for Waiver of the Foreign Residence Requirement",
        "category": "Waivers",
        "fee": 930,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Waiver of the two-year foreign residence requirement for J-1 exchange visitors",
        "visa_types": ["J-1"],
        "pages": 4,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-690": {
        "name": "Application for Waiver of Grounds of Inadmissibility Under Sections 245A or 210 of the INA",
        "category": "Waivers",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Waiver of inadmissibility for legalization or special agricultural worker applicants",
        "visa_types": ["All"],
        "pages": 4,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-693": {
        "name": "Report of Medical Examination and Vaccination Record",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Medical examination and vaccination record required for adjustment of status",
        "visa_types": ["All"],
        "pages": 8,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-694": {
        "name": "Notice of Appeal of Decision Under Sections 245A or 210 of the INA",
        "category": "Appeals",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Appeal of a decision regarding legalization or special agricultural worker applications",
        "visa_types": ["All"],
        "pages": 2,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-698": {
        "name": "Application to Adjust Status from Temporary to Permanent Resident",
        "category": "Adjustment of Status",
        "fee": 1670,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Adjust from temporary to permanent resident under legalization provisions",
        "visa_types": ["All"],
        "pages": 6,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-730": {
        "name": "Refugee/Asylee Relative Petition",
        "category": "Humanitarian",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Petition for a qualifying family member of a refugee or asylee to join them in the U.S.",
        "visa_types": ["Refugee", "Asylum"],
        "pages": 6,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-751": {
        "name": "Petition to Remove Conditions on Residence",
        "category": "Family-Based",
        "fee": 750,
        "premium_fee": None,
        "processing_time": "12-24 months",
        "description": "Remove conditions on permanent residence (conditional green card)",
        "visa_types": ["CR-1"],
        "pages": 10,
        "edition": "04/01/24",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-765": {
        "name": "Application for Employment Authorization",
        "category": "Employment-Based",
        "fee": 410,
        "premium_fee": None,
        "processing_time": "3-6 months",
        "description": "Application for Employment Authorization Document (EAD)",
        "visa_types": ["All"],
        "pages": 7,
        "edition": "08/21/25",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-765V": {
        "name": "Application for Employment Authorization for Abused Nonimmigrant Spouse",
        "category": "Humanitarian",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "EAD application for certain abused nonimmigrant spouses (V visa holders)",
        "visa_types": ["V"],
        "pages": 4,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-800": {
        "name": "Petition to Classify Convention Adoptee as an Immediate Relative",
        "category": "Family-Based",
        "fee": 775,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Petition to classify a Hague Convention adoptee as an immediate relative",
        "visa_types": ["IH-3", "IH-4"],
        "pages": 10,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-800A": {
        "name": "Application for Determination of Suitability to Adopt a Child from a Convention Country",
        "category": "Family-Based",
        "fee": 775,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Determine suitability to adopt a child from a Hague Convention country",
        "visa_types": ["IH-3", "IH-4"],
        "pages": 9,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-817": {
        "name": "Application for Family Unity Benefits",
        "category": "Family-Based",
        "fee": 600,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Application for voluntary departure or work authorization under Family Unity program",
        "visa_types": ["Family Unity"],
        "pages": 6,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-821": {
        "name": "Application for Temporary Protected Status",
        "category": "Humanitarian",
        "fee": 50,
        "premium_fee": None,
        "processing_time": "3-12 months",
        "description": "Application for Temporary Protected Status (TPS)",
        "visa_types": ["TPS"],
        "pages": 12,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-821D": {
        "name": "Consideration of Deferred Action for Childhood Arrivals",
        "category": "Humanitarian",
        "fee": 410,
        "premium_fee": None,
        "processing_time": "3-6 months",
        "description": "Request for Deferred Action for Childhood Arrivals (DACA)",
        "visa_types": ["DACA"],
        "pages": 7,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-824": {
        "name": "Application for Action on an Approved Application or Petition",
        "category": "Supporting",
        "fee": 465,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Request USCIS take action on a previously approved application or petition",
        "visa_types": ["All"],
        "pages": 4,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-829": {
        "name": "Petition by Investor to Remove Conditions on Permanent Resident Status",
        "category": "Investment",
        "fee": 3750,
        "premium_fee": None,
        "processing_time": "24-48 months",
        "description": "Remove conditions on EB-5 investor permanent residence",
        "visa_types": ["EB-5"],
        "pages": 8,
        "edition": "12/13/22",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-864": {
        "name": "Affidavit of Support Under Section 213A of the INA",
        "category": "Family-Based",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Affidavit of Support under Section 213A of the INA",
        "visa_types": ["All Family-Based"],
        "pages": 12,
        "edition": "10/17/24",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-864A": {
        "name": "Contract Between Sponsor and Household Member",
        "category": "Family-Based",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Contract between sponsor and household member for I-864 joint sponsorship",
        "visa_types": ["All Family-Based"],
        "pages": 4,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-864EZ": {
        "name": "Affidavit of Support Under Section 213A of the INA (EZ)",
        "category": "Family-Based",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Simplified Affidavit of Support for sponsors with only their own income",
        "visa_types": ["All Family-Based"],
        "pages": 5,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-864P": {
        "name": "HHS Poverty Guidelines for Affidavit of Support",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Current HHS poverty guidelines used with I-864 Affidavit of Support",
        "visa_types": ["All"],
        "pages": 1,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-864W": {
        "name": "Request for Exemption for Intending Immigrant's Affidavit of Support",
        "category": "Family-Based",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Request exemption from the Affidavit of Support requirement",
        "visa_types": ["All"],
        "pages": 2,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-907": {
        "name": "Request for Premium Processing Service",
        "category": "Supporting",
        "fee": 2805,
        "premium_fee": None,
        "processing_time": "15 business days",
        "description": "Request premium processing for eligible employment-based petitions",
        "visa_types": ["H-1B", "L-1", "O-1", "EB-1", "EB-2"],
        "pages": 4,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "I-914": {
        "name": "Application for T Nonimmigrant Status",
        "category": "Humanitarian",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Application for T visa for victims of human trafficking",
        "visa_types": ["T"],
        "pages": 18,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-918": {
        "name": "Petition for U Nonimmigrant Status",
        "category": "Humanitarian",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Petition for U visa for victims of certain crimes who assist law enforcement",
        "visa_types": ["U"],
        "pages": 15,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-924": {
        "name": "Application for Regional Center Designation Under the Immigrant Investor Program",
        "category": "Investment",
        "fee": 17795,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Designation as an EB-5 regional center",
        "visa_types": ["EB-5"],
        "pages": 14,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-924A": {
        "name": "Annual Certification of Regional Center",
        "category": "Investment",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Annual certification required of EB-5 regional centers",
        "visa_types": ["EB-5"],
        "pages": 4,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-929": {
        "name": "Petition for Qualifying Family Member of a U-1 Nonimmigrant",
        "category": "Humanitarian",
        "fee": 230,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Petition for family members of U visa holders",
        "visa_types": ["U"],
        "pages": 8,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-942": {
        "name": "Request for Reduced Fee",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Request a reduced filing fee based on household income",
        "visa_types": ["All"],
        "pages": 4,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-956": {
        "name": "Application for Regional Center Designation",
        "category": "Investment",
        "fee": 17795,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Application for initial EB-5 Regional Center designation under the RIA",
        "visa_types": ["EB-5"],
        "pages": 12,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-956F": {
        "name": "Application for Approval of an Investment in a Commercial Enterprise",
        "category": "Investment",
        "fee": 17795,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Approval of an investment offering by an EB-5 regional center",
        "visa_types": ["EB-5"],
        "pages": 10,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-956G": {
        "name": "Regional Center Annual Statement",
        "category": "Investment",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Annual statement required of EB-5 regional centers",
        "visa_types": ["EB-5"],
        "pages": 6,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-956H": {
        "name": "Bona Fides of Persons Involved with Regional Center Program",
        "category": "Investment",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Certification of bona fides for persons involved with EB-5 regional centers",
        "visa_types": ["EB-5"],
        "pages": 4,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "I-956K": {
        "name": "Registration for Direct and Third-Party Promoters",
        "category": "Investment",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Registration for promoters of EB-5 regional center offerings",
        "visa_types": ["EB-5"],
        "pages": 4,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },

    # =========================================================================
    # N-Series (Naturalization)
    # =========================================================================

    "N-4": {
        "name": "Monthly Report on Naturalization Papers",
        "category": "Naturalization",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Monthly report of naturalization papers issued by a court",
        "visa_types": ["Citizenship"],
        "pages": 1,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "N-300": {
        "name": "Application to File Declaration of Intention",
        "category": "Naturalization",
        "fee": 270,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "File a declaration of intention to become a U.S. citizen",
        "visa_types": ["Citizenship"],
        "pages": 3,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "N-336": {
        "name": "Request for a Hearing on a Decision in Naturalization Proceedings",
        "category": "Naturalization",
        "fee": 700,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Request a hearing before an immigration officer on a denied N-400",
        "visa_types": ["Citizenship"],
        "pages": 4,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "N-400": {
        "name": "Application for Naturalization",
        "category": "Naturalization",
        "fee": 760,
        "premium_fee": None,
        "processing_time": "8-14 months",
        "description": "Application to become a U.S. citizen",
        "visa_types": ["Citizenship"],
        "pages": 20,
        "edition": "04/01/24",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "N-426": {
        "name": "Request for Certification of Military or Naval Service",
        "category": "Naturalization",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Certification of military service for naturalization purposes",
        "visa_types": ["Citizenship"],
        "pages": 2,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "N-470": {
        "name": "Application to Preserve Residence for Naturalization Purposes",
        "category": "Naturalization",
        "fee": 355,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Preserve residence for naturalization while employed abroad",
        "visa_types": ["Citizenship"],
        "pages": 4,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "N-565": {
        "name": "Application for Replacement Naturalization/Citizenship Document",
        "category": "Naturalization",
        "fee": 555,
        "premium_fee": None,
        "processing_time": "6-12 months",
        "description": "Replace a lost, damaged, or incorrect naturalization or citizenship certificate",
        "visa_types": ["Citizenship"],
        "pages": 4,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "N-600": {
        "name": "Application for Certificate of Citizenship",
        "category": "Naturalization",
        "fee": 1170,
        "premium_fee": None,
        "processing_time": "6-18 months",
        "description": "Obtain a Certificate of Citizenship for persons who derived or acquired citizenship",
        "visa_types": ["Citizenship"],
        "pages": 12,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "N-600K": {
        "name": "Application for Citizenship and Issuance of Certificate Under Section 322",
        "category": "Naturalization",
        "fee": 1170,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Application for citizenship for a child of a U.S. citizen residing abroad",
        "visa_types": ["Citizenship"],
        "pages": 8,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "N-644": {
        "name": "Application for Posthumous Citizenship",
        "category": "Naturalization",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Application for posthumous citizenship for persons who died serving the U.S. military",
        "visa_types": ["Citizenship"],
        "pages": 3,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "N-648": {
        "name": "Medical Certification for Disability Exceptions",
        "category": "Naturalization",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Medical certification for disability exception to English and civics naturalization requirements",
        "visa_types": ["Citizenship"],
        "pages": 6,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },

    # =========================================================================
    # G-Series (General)
    # =========================================================================

    "G-28": {
        "name": "Notice of Entry of Appearance as Attorney or Accredited Representative",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Attorney or accredited representative enters appearance for a case",
        "visa_types": ["All"],
        "pages": 3,
        "edition": "04/01/24",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "G-28I": {
        "name": "Notice of Entry of Appearance as Attorney in Matters Outside the Geographical Confines of the United States",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Attorney appearance notice for matters processed outside the U.S.",
        "visa_types": ["All"],
        "pages": 3,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "G-325A": {
        "name": "Biographic Information",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Biographic information for immigration applications",
        "visa_types": ["All"],
        "pages": 1,
        "edition": "09/30/10",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "G-325B": {
        "name": "Biographic Information (for Deporting or Removing Agency)",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Biographic information used by enforcement agencies",
        "visa_types": ["All"],
        "pages": 1,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "G-325C": {
        "name": "Biographic Information (for Applicant in Naturalization Proceedings)",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Biographic information used in naturalization proceedings",
        "visa_types": ["Citizenship"],
        "pages": 1,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "G-325D": {
        "name": "Biographic Information (for Other Proceedings)",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Biographic information used in miscellaneous proceedings",
        "visa_types": ["All"],
        "pages": 1,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "G-639": {
        "name": "Freedom of Information/Privacy Act Request",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Request immigration records under FOIA or the Privacy Act",
        "visa_types": ["All"],
        "pages": 2,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },
    "G-845": {
        "name": "Verification Request",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Verification of immigration status for benefit-granting agencies",
        "visa_types": ["All"],
        "pages": 1,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "G-884": {
        "name": "Return of Original Documents",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Request return of original documents submitted with an application",
        "visa_types": ["All"],
        "pages": 1,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "G-1041": {
        "name": "Genealogy Index Search Request",
        "category": "Supporting",
        "fee": 65,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Request a search of USCIS historical genealogy records index",
        "visa_types": ["All"],
        "pages": 2,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "G-1041A": {
        "name": "Genealogy Records Request",
        "category": "Supporting",
        "fee": 65,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Request copies of USCIS historical genealogy records",
        "visa_types": ["All"],
        "pages": 2,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "G-1145": {
        "name": "E-Notification of Application/Petition Acceptance",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Request email/text notification when USCIS accepts your application",
        "visa_types": ["All"],
        "pages": 1,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "G-1256": {
        "name": "Authorization for Debit or Credit Card Transactions",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Authorize USCIS to charge filing fees to a debit or credit card",
        "visa_types": ["All"],
        "pages": 1,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },

    # =========================================================================
    # AR-Series
    # =========================================================================

    "AR-11": {
        "name": "Alien's Change of Address Card",
        "category": "Supporting",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Notify USCIS of a change of address within 10 days of moving",
        "visa_types": ["All"],
        "pages": 1,
        "edition": "N/A",
        "has_auto_fill": True,
        "field_count": 0,
    },

    # =========================================================================
    # EOIR-Series (Immigration Court)
    # =========================================================================

    "EOIR-26": {
        "name": "Notice of Appeal from a Decision of an Immigration Judge",
        "category": "Immigration Court",
        "fee": 110,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Appeal an immigration judge's decision to the Board of Immigration Appeals",
        "visa_types": ["All"],
        "pages": 3,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "EOIR-28": {
        "name": "Notice of Entry of Appearance as Attorney or Representative Before the Immigration Court",
        "category": "Immigration Court",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Attorney appearance notice for proceedings before an immigration judge",
        "visa_types": ["All"],
        "pages": 2,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "EOIR-29": {
        "name": "Notice of Appeal to the Board of Immigration Appeals from a Decision of a DHS Officer",
        "category": "Immigration Court",
        "fee": 110,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Appeal a DHS officer's decision to the Board of Immigration Appeals",
        "visa_types": ["All"],
        "pages": 3,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "EOIR-33": {
        "name": "Immigration Court Change of Address Form",
        "category": "Immigration Court",
        "fee": 0,
        "premium_fee": None,
        "processing_time": "N/A",
        "description": "Notify the immigration court of a change of address or contact information",
        "visa_types": ["All"],
        "pages": 1,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "EOIR-40": {
        "name": "Application for Suspension of Deportation",
        "category": "Immigration Court",
        "fee": 100,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Application for suspension of deportation under former INA provisions",
        "visa_types": ["All"],
        "pages": 6,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "EOIR-42A": {
        "name": "Application for Cancellation of Removal for Certain Permanent Residents",
        "category": "Immigration Court",
        "fee": 100,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Cancellation of removal for lawful permanent residents in removal proceedings",
        "visa_types": ["All"],
        "pages": 8,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
    "EOIR-42B": {
        "name": "Application for Cancellation of Removal and Adjustment of Status for Certain Nonpermanent Residents",
        "category": "Immigration Court",
        "fee": 100,
        "premium_fee": None,
        "processing_time": "Varies",
        "description": "Cancellation of removal for certain nonpermanent residents with qualifying relatives",
        "visa_types": ["All"],
        "pages": 9,
        "edition": "N/A",
        "has_auto_fill": False,
        "field_count": 0,
    },
}

# =============================================================================
# Form Categories - logical groupings for UI display
# =============================================================================
FORM_CATEGORIES = {
    "employment": {
        "name": "Employment-Based Immigration",
        "description": "H-1B, L-1, O-1, EB-1, EB-2, EB-3 petitions and work authorization",
        "icon": "fa-briefcase",
        "forms": ["I-129", "I-129S", "I-140", "I-765", "I-907", "I-526", "I-829"],
    },
    "family": {
        "name": "Family-Based Immigration",
        "description": "Spouse, parent, child petitions and affidavits of support",
        "icon": "fa-users",
        "forms": ["I-130", "I-130A", "I-485", "I-864", "I-864A", "I-864EZ",
                  "I-129F", "I-751", "I-360", "I-485J", "I-600", "I-800", "I-817"],
    },
    "naturalization": {
        "name": "Naturalization & Citizenship",
        "description": "Citizenship applications and certificate replacements",
        "icon": "fa-flag-usa",
        "forms": ["N-400", "N-336", "N-565", "N-600", "N-600K"],
    },
    "humanitarian": {
        "name": "Humanitarian & Protection",
        "description": "Asylum, TPS, DACA, VAWA, U-Visa, T-Visa",
        "icon": "fa-hand-holding-heart",
        "forms": ["I-589", "I-821", "I-821D", "I-914", "I-918", "I-929", "I-730"],
    },
    "travel": {
        "name": "Travel & Status Changes",
        "description": "Travel documents, extensions, status changes, green card renewal",
        "icon": "fa-plane-departure",
        "forms": ["I-131", "I-539", "I-90", "I-290B"],
    },
    "waivers": {
        "name": "Waivers",
        "description": "Inadmissibility waivers, unlawful presence waivers",
        "icon": "fa-shield-alt",
        "forms": ["I-601", "I-601A", "I-693"],
    },
    "general": {
        "name": "General & Administrative",
        "description": "Attorney appearance, FOIA, address changes, appeals",
        "icon": "fa-file-alt",
        "forms": ["G-28", "G-639", "AR-11"],
    },
}

# =============================================================================
# Form field mappings for pre-population from Client model
# Maps client_field -> expand_file_field_name for each form
# These map Client model fields to the expand_*.py field names (p{part}_{item}_{desc})
# =============================================================================
FORM_FIELD_MAPPINGS = {
    # -------------------------------------------------------------------------
    # G-28: Attorney appearance - maps to Part 3 (person being represented)
    # -------------------------------------------------------------------------
    "G-28": {
        "last_name": "p3_2a_family_name",
        "first_name": "p3_2b_given_name",
        "middle_name": "p3_2c_middle_name",
        "alien_number": "p3_3_a_number",
        "address": "p3_7a_street",
        "city": "p3_7c_city",
        "state": "p3_7d_state",
        "zip_code": "p3_7e_zip",
        "phone": "p3_8_phone",
        "email": "p3_10_email",
    },
    # -------------------------------------------------------------------------
    # I-90: Replace Green Card
    # -------------------------------------------------------------------------
    "I-90": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p1_5_dob",
        "country_of_origin": "p1_6_country_birth",
        "alien_number": "p1_7_a_number",
        "ssn": "p1_9_ssn",
        "address": "p1_10a_street",
        "city": "p1_10d_city",
        "state": "p1_10e_state",
        "zip_code": "p1_10f_zip",
        "phone": "p3_3_daytime_phone",
        "email": "p3_5_email",
    },
    # -------------------------------------------------------------------------
    # I-129: Nonimmigrant Worker Petition
    # -------------------------------------------------------------------------
    "I-129": {
        "last_name": "p2_1a_family_name",
        "first_name": "p2_1b_given_name",
        "middle_name": "p2_1c_middle_name",
        "date_of_birth": "p2_7_dob",
        "country_of_origin": "p2_8_country_birth",
        "alien_number": "p2_3_a_number",
        "ssn": "p2_5_ssn",
        "address": "p2_9a_street",
        "city": "p2_9c_city",
        "state": "p2_9d_state",
        "zip_code": "p2_9e_zip",
        "passport_number": "p2_11_passport_number",
        "phone": "p6_3_daytime_phone",
        "email": "p6_5_email",
    },
    # -------------------------------------------------------------------------
    # I-129F: Fiance(e) Petition
    # -------------------------------------------------------------------------
    "I-129F": {
        "last_name": "p2_1a_family_name",
        "first_name": "p2_1b_given_name",
        "middle_name": "p2_1c_middle_name",
        "date_of_birth": "p2_5_dob",
        "country_of_origin": "p2_7_country_birth",
        "alien_number": "p2_3_a_number",
        "ssn": "p2_4_ssn",
        "address": "p2_9a_street",
        "city": "p2_9d_city",
        "state": "p2_9e_state",
        "zip_code": "p2_9f_zip",
        "phone": "p7_3_daytime_phone",
        "email": "p7_5_email",
    },
    # -------------------------------------------------------------------------
    # I-130: Petition for Alien Relative - petitioner is the client
    # -------------------------------------------------------------------------
    "I-130": {
        "last_name": "p2_4a_family_name",
        "first_name": "p2_4b_given_name",
        "middle_name": "p2_4c_middle_name",
        "date_of_birth": "p2_10_dob",
        "country_of_origin": "p2_13_country_birth",
        "alien_number": "p2_1_a_number",
        "ssn": "p2_3_ssn",
        "address": "p2_7b_mail_street",
        "city": "p2_7e_mail_city",
        "state": "p2_7f_mail_state",
        "zip_code": "p2_7g_mail_zip",
        "phone": "p6_3_daytime_phone",
        "email": "p6_5_email",
    },
    # -------------------------------------------------------------------------
    # I-130A: Supplemental Information for Spouse
    # -------------------------------------------------------------------------
    "I-130A": {
        "last_name": "p1_3a_family_name",
        "first_name": "p1_3b_given_name",
        "middle_name": "p1_3c_middle_name",
        "alien_number": "p1_1_a_number",
        "address": "p1_4a_street",
        "city": "p1_4d_city",
        "state": "p1_4e_state",
        "zip_code": "p1_4f_zip",
        "phone": "p4_3_phone_day",
        "email": "p4_5_email",
    },
    # -------------------------------------------------------------------------
    # I-131: Travel Document
    # -------------------------------------------------------------------------
    "I-131": {
        "last_name": "p2_1a_family_name",
        "first_name": "p2_1b_given_name",
        "middle_name": "p2_1c_middle_name",
        "date_of_birth": "p2_10_dob",
        "country_of_origin": "p2_14_country_birth",
        "alien_number": "p2_7_a_number",
        "ssn": "p2_9_ssn",
        "address": "p2_4a_street",
        "city": "p2_4d_city",
        "state": "p2_4e_state",
        "zip_code": "p2_4f_zip",
        "phone": "p10_3_daytime_phone",
        "email": "p10_5_email",
    },
    # -------------------------------------------------------------------------
    # I-140: Immigrant Petition for Alien Workers
    # -------------------------------------------------------------------------
    "I-140": {
        "last_name": "p3_1a_family_name",
        "first_name": "p3_1b_given_name",
        "middle_name": "p3_1c_middle_name",
        "date_of_birth": "p3_10_dob",
        "country_of_origin": "p3_6_country_of_birth",
        "alien_number": "p3_8_a_number",
        "ssn": "p3_9_ssn",
        "address": "p3_2a_street",
        "city": "p3_2c_city",
        "state": "p3_2d_state",
        "zip_code": "p3_2e_zip",
        "passport_number": "p3_13_passport_number",
    },
    # -------------------------------------------------------------------------
    # I-290B: Notice of Appeal or Motion
    # -------------------------------------------------------------------------
    "I-290B": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "alien_number": "p1_2_a_number",
        "address": "p1_5a_street",
        "city": "p1_5d_city",
        "state": "p1_5e_state",
        "zip_code": "p1_5f_zip",
        "phone": "p4_3_daytime_phone",
        "email": "p4_5_email",
    },
    # -------------------------------------------------------------------------
    # I-360: Special Immigrant Petition
    # -------------------------------------------------------------------------
    "I-360": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p1_5_dob",
        "country_of_origin": "p1_7_country_birth",
        "alien_number": "p1_3_a_number",
        "ssn": "p1_4_ssn",
        "address": "p1_8a_street",
        "city": "p1_8d_city",
        "state": "p1_8e_state",
        "zip_code": "p1_8f_zip",
        "phone": "p5_3_daytime_phone",
        "email": "p5_5_email",
    },
    # -------------------------------------------------------------------------
    # I-485: Adjustment of Status
    # -------------------------------------------------------------------------
    "I-485": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p1_5_dob",
        "country_of_origin": "p1_8_country_birth",
        "alien_number": "p1_11_a_number",
        "ssn": "p1_13_ssn",
        "address": "p1_14b_street",
        "city": "p1_14e_city",
        "state": "p1_14f_state",
        "zip_code": "p1_14g_zip",
        "passport_number": "p1_17_passport_number",
        "phone": "p11_3_daytime_phone",
        "email": "p11_5_email",
    },
    # -------------------------------------------------------------------------
    # I-526: Immigrant Investor Petition
    # -------------------------------------------------------------------------
    "I-526": {
        "last_name": "p2_1a_family_name",
        "first_name": "p2_1b_given_name",
        "middle_name": "p2_1c_middle_name",
        "date_of_birth": "p2_4_dob",
        "country_of_origin": "p2_5_country_birth",
        "alien_number": "p2_2_a_number",
        "ssn": "p2_3_ssn",
        "address": "p2_7a_street",
        "city": "p2_7d_city",
        "state": "p2_7e_state",
        "zip_code": "p2_7f_zip",
        "phone": "p5_3_daytime_phone",
        "email": "p5_5_email",
    },
    # -------------------------------------------------------------------------
    # I-539: Change/Extend Nonimmigrant Status
    # -------------------------------------------------------------------------
    "I-539": {
        "last_name": "p2_1a_family_name",
        "first_name": "p2_1b_given_name",
        "middle_name": "p2_1c_middle_name",
        "date_of_birth": "p2_7_dob",
        "country_of_origin": "p2_9_country_birth",
        "alien_number": "p2_4_a_number",
        "ssn": "p2_6_ssn",
        "address": "p2_10a_street",
        "city": "p2_10d_city",
        "state": "p2_10e_state",
        "zip_code": "p2_10f_zip",
        "passport_number": "p2_12_passport_number",
        "phone": "p5_3_daytime_phone",
        "email": "p5_5_email",
    },
    # -------------------------------------------------------------------------
    # I-589: Asylum Application
    # -------------------------------------------------------------------------
    "I-589": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p1_3_dob",
        "country_of_origin": "p1_5_country_birth",
        "alien_number": "p1_2_a_number",
        "ssn": "p1_7_ssn",
        "address": "p1_8a_street",
        "city": "p1_8d_city",
        "state": "p1_8e_state",
        "zip_code": "p1_8f_zip",
        "passport_number": "p1_10_passport_number",
        "phone": "p1_12_phone",
        "email": "p1_13_email",
    },
    # -------------------------------------------------------------------------
    # I-601: Waiver of Inadmissibility
    # -------------------------------------------------------------------------
    "I-601": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p1_5_dob",
        "country_of_origin": "p1_6_country_birth",
        "alien_number": "p1_2_a_number",
        "address": "p1_7a_street",
        "city": "p1_7d_city",
        "state": "p1_7e_state",
        "zip_code": "p1_7f_zip",
        "phone": "p5_3_daytime_phone",
        "email": "p5_5_email",
    },
    # -------------------------------------------------------------------------
    # I-601A: Provisional Unlawful Presence Waiver
    # -------------------------------------------------------------------------
    "I-601A": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p1_5_dob",
        "country_of_origin": "p1_6_country_birth",
        "alien_number": "p1_2_a_number",
        "address": "p1_7a_street",
        "city": "p1_7d_city",
        "state": "p1_7e_state",
        "zip_code": "p1_7f_zip",
        "phone": "p4_3_daytime_phone",
        "email": "p4_5_email",
    },
    # -------------------------------------------------------------------------
    # I-693: Medical Examination
    # -------------------------------------------------------------------------
    "I-693": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p1_3_dob",
        "country_of_origin": "p1_4_country_birth",
        "alien_number": "p1_2_a_number",
        "address": "p1_5a_street",
        "city": "p1_5d_city",
        "state": "p1_5e_state",
        "zip_code": "p1_5f_zip",
        "phone": "p1_6_phone",
        "email": "p1_7_email",
    },
    # -------------------------------------------------------------------------
    # I-751: Remove Conditions on Residence
    # -------------------------------------------------------------------------
    "I-751": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p1_5_dob",
        "country_of_origin": "p1_6_country_birth",
        "alien_number": "p1_2_a_number",
        "ssn": "p1_4_ssn",
        "address": "p1_7a_street",
        "city": "p1_7d_city",
        "state": "p1_7e_state",
        "zip_code": "p1_7f_zip",
        "phone": "p4_3_daytime_phone",
        "email": "p4_5_email",
    },
    # -------------------------------------------------------------------------
    # I-765: Employment Authorization
    # -------------------------------------------------------------------------
    "I-765": {
        "last_name": "p2_1a_family_name",
        "first_name": "p2_1b_given_name",
        "middle_name": "p2_1c_middle_name",
        "date_of_birth": "p2_16_dob",
        "country_of_origin": "p2_20_country_birth",
        "alien_number": "p2_8_a_number",
        "ssn": "p2_23_ssn",
        "address": "p2_5b_street",
        "city": "p2_5e_city",
        "state": "p2_5f_state",
        "zip_code": "p2_5g_zip",
        "passport_number": "p2_11_passport_number",
        "phone": "p3_4_daytime_phone",
        "email": "p3_6_email",
    },
    # -------------------------------------------------------------------------
    # I-821: Temporary Protected Status
    # -------------------------------------------------------------------------
    "I-821": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p1_5_dob",
        "country_of_origin": "p1_6_country_birth",
        "alien_number": "p1_2_a_number",
        "ssn": "p1_4_ssn",
        "address": "p1_7a_street",
        "city": "p1_7d_city",
        "state": "p1_7e_state",
        "zip_code": "p1_7f_zip",
        "phone": "p5_3_daytime_phone",
        "email": "p5_5_email",
    },
    # -------------------------------------------------------------------------
    # I-821D: DACA
    # -------------------------------------------------------------------------
    "I-821D": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p1_5_dob",
        "country_of_origin": "p1_6_country_birth",
        "alien_number": "p1_2_a_number",
        "ssn": "p1_4_ssn",
        "address": "p1_7a_street",
        "city": "p1_7d_city",
        "state": "p1_7e_state",
        "zip_code": "p1_7f_zip",
        "phone": "p3_3_daytime_phone",
        "email": "p3_5_email",
    },
    # -------------------------------------------------------------------------
    # I-829: Remove Conditions (EB-5)
    # -------------------------------------------------------------------------
    "I-829": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p1_5_dob",
        "country_of_origin": "p1_6_country_birth",
        "alien_number": "p1_2_a_number",
        "ssn": "p1_4_ssn",
        "address": "p1_7a_street",
        "city": "p1_7d_city",
        "state": "p1_7e_state",
        "zip_code": "p1_7f_zip",
        "phone": "p4_3_daytime_phone",
        "email": "p4_5_email",
    },
    # -------------------------------------------------------------------------
    # I-864: Affidavit of Support - sponsor is client
    # -------------------------------------------------------------------------
    "I-864": {
        "last_name": "p4_1a_family_name",
        "first_name": "p4_1b_given_name",
        "middle_name": "p4_1c_middle_name",
        "date_of_birth": "p4_4_dob",
        "ssn": "p4_8_ssn",
        "alien_number": "p4_10_a_number",
        "address": "p4_2b_street",
        "city": "p4_2e_city",
        "state": "p4_2f_state",
        "zip_code": "p4_2g_zip",
        "phone": "p8_6_daytime_phone",
        "email": "p8_8_email",
    },
    # -------------------------------------------------------------------------
    # I-907: Premium Processing
    # -------------------------------------------------------------------------
    "I-907": {
        "last_name": "p1_3_family_name",
        "first_name": "p1_3_given_name",
        "middle_name": "p1_3_middle_name",
        "alien_number": "p1_1_a_number",
        "address": "p1_5_street",
        "city": "p1_5_city",
        "state": "p1_5_state",
        "zip_code": "p1_5_zip",
        "phone": "p3_3_phone_day",
        "email": "p3_6_email",
    },
    # -------------------------------------------------------------------------
    # N-336: Hearing Request on Naturalization
    # -------------------------------------------------------------------------
    "N-336": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p1_5_dob",
        "alien_number": "p1_2_a_number",
        "address": "p1_6a_street",
        "city": "p1_6d_city",
        "state": "p1_6e_state",
        "zip_code": "p1_6f_zip",
        "phone": "p3_3_daytime_phone",
        "email": "p3_5_email",
    },
    # -------------------------------------------------------------------------
    # N-400: Naturalization
    # -------------------------------------------------------------------------
    "N-400": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p2_1_dob",
        "country_of_origin": "p2_3_country_birth",
        "alien_number": "p1_4_a_number",
        "ssn": "p1_6_ssn",
        "address": "p1_7a_street",
        "city": "p1_7d_city",
        "state": "p1_7e_state",
        "zip_code": "p1_7f_zip",
        "phone": "p12_3_daytime_phone",
        "email": "p12_5_email",
    },
    # -------------------------------------------------------------------------
    # N-565: Replace Naturalization Document
    # -------------------------------------------------------------------------
    "N-565": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p1_5_dob",
        "country_of_origin": "p1_6_country_birth",
        "alien_number": "p1_2_a_number",
        "address": "p1_7a_street",
        "city": "p1_7d_city",
        "state": "p1_7e_state",
        "zip_code": "p1_7f_zip",
        "phone": "p4_3_daytime_phone",
        "email": "p4_5_email",
    },
    # -------------------------------------------------------------------------
    # N-600: Certificate of Citizenship
    # -------------------------------------------------------------------------
    "N-600": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p2_1_dob",
        "country_of_origin": "p2_3_country_birth",
        "alien_number": "p1_2_a_number",
        "ssn": "p1_4_ssn",
        "address": "p1_5a_street",
        "city": "p1_5d_city",
        "state": "p1_5e_state",
        "zip_code": "p1_5f_zip",
        "phone": "p7_3_daytime_phone",
        "email": "p7_5_email",
    },
    # -------------------------------------------------------------------------
    # N-600K: Citizenship Under Section 322
    # -------------------------------------------------------------------------
    "N-600K": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p1_5_dob",
        "country_of_origin": "p1_6_country_birth",
        "alien_number": "p1_2_a_number",
        "address": "p1_7a_street",
        "city": "p1_7d_city",
        "state": "p1_7e_state",
        "zip_code": "p1_7f_zip",
        "phone": "p5_3_daytime_phone",
        "email": "p5_5_email",
    },
    # -------------------------------------------------------------------------
    # G-639: FOIA Request
    # -------------------------------------------------------------------------
    "G-639": {
        "last_name": "p1_1a_family_name",
        "first_name": "p1_1b_given_name",
        "middle_name": "p1_1c_middle_name",
        "date_of_birth": "p1_4_dob",
        "country_of_origin": "p1_5_country_birth",
        "alien_number": "p1_2_a_number",
        "address": "p1_6a_street",
        "city": "p1_6d_city",
        "state": "p1_6e_state",
        "zip_code": "p1_6f_zip",
        "phone": "p1_7_phone",
        "email": "p1_8_email",
    },
    # -------------------------------------------------------------------------
    # AR-11: Change of Address
    # -------------------------------------------------------------------------
    "AR-11": {
        "last_name": "family_name",
        "first_name": "given_name",
        "middle_name": "middle_name",
        "date_of_birth": "date_of_birth",
        "alien_number": "a_number",
        "address": "present_street_number",
        "city": "present_city",
        "state": "present_state",
        "zip_code": "present_zip",
    },
}


class USCISFormsService:
    """Service for managing USCIS form library."""

    DATA_DIR = "data/uscis_forms"

    def __init__(self):
        os.makedirs(self.DATA_DIR, exist_ok=True)

    def get_all_forms(self) -> List[dict]:
        """Get all available USCIS forms."""
        forms = []
        for form_number, form_data in USCIS_FORMS.items():
            forms.append({
                "form_number": form_number,
                **form_data
            })
        return sorted(forms, key=lambda x: x["form_number"])

    def get_forms_by_category(self, category: str) -> List[dict]:
        """Get forms filtered by category."""
        return [
            {"form_number": num, **data}
            for num, data in USCIS_FORMS.items()
            if data.get("category") == category
        ]

    def get_forms_by_visa_type(self, visa_type: str) -> List[dict]:
        """Get forms relevant to a specific visa type."""
        result = []
        for form_number, form_data in USCIS_FORMS.items():
            visa_types = form_data.get("visa_types", [])
            if visa_type in visa_types or "All" in visa_types:
                result.append({"form_number": form_number, **form_data})
        return result

    def get_form(self, form_number: str) -> Optional[dict]:
        """Get details for a specific form."""
        form_data = USCIS_FORMS.get(form_number.upper())
        if form_data:
            return {"form_number": form_number.upper(), **form_data}
        return None

    def get_categories(self) -> List[str]:
        """Get list of all form categories."""
        categories = set()
        for form_data in USCIS_FORMS.values():
            categories.add(form_data.get("category", "Other"))
        return sorted(list(categories))

    def get_forms_grouped_by_category(self) -> List[dict]:
        """Get forms organized by FORM_CATEGORIES for the library UI.

        Returns a list of category dicts, each with a 'forms' list of form dicts.
        Forms not in any category are grouped under 'other'.
        """
        assigned = set()
        result = []

        for cat_key, cat_info in FORM_CATEGORIES.items():
            cat_forms = []
            for form_number in cat_info["forms"]:
                form_data = USCIS_FORMS.get(form_number)
                if form_data:
                    cat_forms.append({"form_number": form_number, **form_data})
                    assigned.add(form_number)
            result.append({
                "key": cat_key,
                "name": cat_info["name"],
                "description": cat_info["description"],
                "icon": cat_info["icon"],
                "forms": sorted(cat_forms, key=lambda x: x["form_number"]),
                "auto_fill_count": sum(1 for f in cat_forms if f.get("has_auto_fill")),
            })

        # Collect any forms not assigned to a category
        other_forms = []
        for form_number, form_data in USCIS_FORMS.items():
            if form_number not in assigned:
                other_forms.append({"form_number": form_number, **form_data})
        if other_forms:
            result.append({
                "key": "other",
                "name": "Other Forms",
                "description": "Additional USCIS forms",
                "icon": "fa-folder-open",
                "forms": sorted(other_forms, key=lambda x: x["form_number"]),
                "auto_fill_count": sum(1 for f in other_forms if f.get("has_auto_fill")),
            })

        return result

    def get_form_fields(self, form_number: str) -> dict:
        """Get field mappings for pre-population."""
        return FORM_FIELD_MAPPINGS.get(form_number.upper(), {})

    def pre_populate_form(self, form_number: str, client_data: dict, case_data: dict = None) -> dict:
        """Pre-populate form fields with client/case data.

        Uses FORM_FIELD_MAPPINGS which maps Client model field names to
        expand_*.py field names (p{part}_{item}_{desc} format).

        Args:
            form_number: USCIS form number
            client_data: Dictionary with client information (Client model fields)
            case_data: Optional dictionary with case information

        Returns:
            Dictionary with pre-populated field values
        """
        populated = {}
        form_fields = self.get_form_fields(form_number)

        # Direct mapping: client_data keys match FORM_FIELD_MAPPINGS keys
        # (last_name, first_name, middle_name, date_of_birth, etc.)
        for client_field, expand_field in form_fields.items():
            value = client_data.get(client_field)
            if value and str(value).strip():
                populated[expand_field] = str(value)

        return {
            "form_number": form_number.upper(),
            "form_name": USCIS_FORMS.get(form_number.upper(), {}).get("name", "Unknown"),
            "populated_fields": populated,
            "populated_count": len(populated),
            "total_mapped": len(form_fields),
            "populated_at": datetime.now().isoformat()
        }

    def generate_form_summary_pdf(self, form_number: str, populated_data: dict) -> Optional[bytes]:
        """Generate a PDF summary of pre-populated form data."""
        if not REPORTLAB_AVAILABLE:
            return None

        try:
            buffer = BytesIO()
            c = canvas.Canvas(buffer, pagesize=letter)
            width, height = letter

            # Header
            c.setFont("Helvetica-Bold", 18)
            c.drawString(1*inch, height - 1*inch, f"USCIS Form {form_number}")

            c.setFont("Helvetica", 12)
            c.drawString(1*inch, height - 1.3*inch, populated_data.get("form_name", ""))

            # Pre-populated fields
            c.setFont("Helvetica-Bold", 14)
            c.drawString(1*inch, height - 2*inch, "Pre-populated Fields:")

            c.setFont("Helvetica", 10)
            y_position = height - 2.4*inch

            for field_name, value in populated_data.get("populated_fields", {}).items():
                if y_position < 1*inch:
                    c.showPage()
                    y_position = height - 1*inch

                # Truncate long field names
                display_name = field_name[:60] + "..." if len(field_name) > 60 else field_name
                c.drawString(1*inch, y_position, f"{display_name}:")
                c.drawString(1*inch + 0.2*inch, y_position - 15, str(value) if value else "")
                y_position -= 40

            # Footer
            c.setFont("Helvetica", 8)
            c.drawString(1*inch, 0.5*inch, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            c.drawString(1*inch, 0.35*inch, "This is a summary only. Complete the official USCIS form.")

            c.save()
            return buffer.getvalue()

        except Exception as e:
            return None

    def search_forms(self, query: str) -> List[dict]:
        """Search forms by number, name, or description."""
        query_lower = query.lower()
        results = []

        for form_number, form_data in USCIS_FORMS.items():
            if (query_lower in form_number.lower() or
                query_lower in form_data.get("name", "").lower() or
                query_lower in form_data.get("description", "").lower() or
                query_lower in form_data.get("category", "").lower()):
                results.append({"form_number": form_number, **form_data})

        return results

    def calculate_total_fees(self, form_numbers: List[str], include_premium: bool = False) -> dict:
        """Calculate total filing fees for a list of forms."""
        total_base = 0
        total_premium = 0
        breakdown = []

        for form_number in form_numbers:
            form = USCIS_FORMS.get(form_number.upper())
            if form:
                base_fee = form.get("fee", 0)
                premium_fee = form.get("premium_fee", 0) if include_premium else 0

                total_base += base_fee
                total_premium += premium_fee if premium_fee else 0

                breakdown.append({
                    "form_number": form_number.upper(),
                    "base_fee": base_fee,
                    "premium_fee": premium_fee
                })

        return {
            "total_base_fees": total_base,
            "total_premium_fees": total_premium,
            "grand_total": total_base + total_premium,
            "breakdown": breakdown
        }


# SQL for USCIS forms tracking
CREATE_USCIS_FORMS_TABLE = """
CREATE TABLE IF NOT EXISTS uscis_form_submissions (
    id SERIAL PRIMARY KEY,
    case_id INTEGER REFERENCES cases(id),
    form_number VARCHAR(20) NOT NULL,
    status VARCHAR(50) DEFAULT 'draft',
    populated_data JSONB,
    submitted_at TIMESTAMP,
    receipt_number VARCHAR(50),
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_uscis_forms_case ON uscis_form_submissions(case_id);
CREATE INDEX IF NOT EXISTS idx_uscis_forms_number ON uscis_form_submissions(form_number);
CREATE INDEX IF NOT EXISTS idx_uscis_forms_status ON uscis_form_submissions(status);
"""


# Singleton instance
uscis_forms_service = USCISFormsService()
