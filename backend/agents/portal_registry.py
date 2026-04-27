"""
============================================================
portal_registry.py — Government Portal Configurations
============================================================
Maps each form type to its portal URL, semantic field labels,
and portal-specific fill instructions.

Field labels are in Hindi + English so the VLM can match
them regardless of the portal's language.

Adding a new form? Add it here. The form_fill_agent will
automatically use the correct config.
"""

from typing import Optional

# ── Portal URLs per form type ────────────────────────────────
# DEMO MODE: Using local mock portals for reliability
PORTAL_URLS: dict[str, str] = {
    "ration_card":        "http://127.0.0.1:8000/mock/ration_card.html",
    "pension":            "http://127.0.0.1:8000/mock/pension.html",
    "ayushman_bharat":   "http://127.0.0.1:8000/mock/ayushman_bharat.html",
    "mnrega":             "http://127.0.0.1:8000/mock/ration_card.html", # Reuse ration for demo
    "pan_card":           "http://127.0.0.1:8000/mock/pan_card.html",
    "voter_id":           "http://127.0.0.1:8000/mock/pan_card.html",   # Reuse pan for demo
    "identity":           "http://127.0.0.1:8000/mock/pan_card.html",
    "caste_certificate": "http://127.0.0.1:8000/mock/ration_card.html",
    "birth_certificate": "http://127.0.0.1:8000/mock/ration_card.html",
    "pm_kisan":           "http://127.0.0.1:8000/mock/ration_card.html",
    "kisan_credit_card": "http://127.0.0.1:8000/mock/ration_card.html",
    "jan_dhan":           "http://127.0.0.1:8000/mock/pension.html",
}

# ── Portal Names ──────────────────────────────────────────
PORTAL_NAMES: dict[str, str] = {
    "ration_card":        "NFSA - National Food Security Portal",
    "pension":            "NSAP - National Social Assistance Programme",
    "ayushman_bharat":   "PM-JAY - Ayushman Bharat Health Insurance",
    "mnrega":             "NREGA - Mahatma Gandhi National Rural Employment",
    "pan_card":           "NSDL - PAN Card Services",
    "voter_id":           "ECI - Election Commission Voter Services",
    "identity":           "NSDL - Identity Services",
    "caste_certificate": "India Government Services - Caste Certificate",
    "birth_certificate": "CRS - Civil Registration System",
    "pm_kisan":           "PM-KISAN - Farmer Support Scheme",
    "kisan_credit_card": "KCC - Kisan Credit Card Portal",
    "jan_dhan":           "PMJDY - Jan Dhan Yojana",
}

# ── Semantic Field Mappings ────────────────────────────────
# Maps GramSetu field names → Portal label variants (Hindi + English)
# The VLM sees these labels on screen and maps them to our field names
FIELD_MAPPINGS: dict[str, dict[str, list[str]]] = {
    "ration_card": {
        "applicant_name": [
            "Applicant Name", "Full Name", "Name of Applicant", "Name",
            "आवेदक का नाम", "नाम", "पूरा नाम", "आवेदक का पूरा नाम",
        ],
        "aadhaar_number": [
            "Aadhaar Number", "Aadhaar ID", "UID", "Aadhar Number",
            "आधार संख्या", "आधार आईडी", "यूआईडी",
        ],
        "date_of_birth": [
            "Date of Birth", "DOB", "Birth Date", "जन्म तिथि", "जन्म की तारीख",
        ],
        "gender": [
            "Gender", "Sex", "Male Female", "लिंग", "Male", "Female",
        ],
        "family_head_name": [
            "Family Head Name", "Head of Family", "Head of Household",
            "परिवार के मुखिया", "परिवार का मुखिया", "परिवार अध्यक्ष",
        ],
        "family_members": [
            "Family Members", "Number of Family Members", "Total Members",
            "परिवार के सदस्य", "सदस्यों की संख्या",
        ],
        "annual_income": [
            "Annual Income", "Yearly Income", "Income",
            "वार्षिक आय", "सालाना आय", "आय",
        ],
        "category": [
            "Category", "Ration Card Type", "Card Category",
            "श्रेणी", "कार्ड की श्रेणी", "APL", "BPL", "AAY",
        ],
        "mobile_number": [
            "Mobile Number", "Phone Number", "Mobile", "Contact",
            "मोबाइल नंबर", "फ़ोन नंबर", "संपर्क",
        ],
        "house_number": [
            "House Number", "Door Number", "Flat Number",
            "मकान नंबर", "घर नंबर", "दरवाज़ा नंबर",
        ],
        "village": [
            "Village", "Town", "Ward", "Locality",
            "गाँव", "कस्बा", "वार्ड",
        ],
        "district": [
            "District", "जिला", "ज़िला",
        ],
        "state": [
            "State", "राज्य", "State Name",
        ],
        "pin_code": [
            "PIN Code", "Postal Code", "Pincode", "पिन कोड", "डाक कोड",
        ],
    },
    "pension": {
        "applicant_name": [
            "Applicant Name", "Full Name", "Beneficiary Name", "Pensioner Name",
            "आवेदक का नाम", "लाभार्थी का नाम", "पेंशनर का नाम",
        ],
        "aadhaar_number": [
            "Aadhaar Number", "UID", "आधार संख्या",
        ],
        "date_of_birth": [
            "Date of Birth", "DOB", "जन्म तिथि",
        ],
        "pension_type": [
            "Pension Type", "Type of Pension", "Scheme Type",
            "पेंशन का प्रकार", "योजना प्रकार", "Old Age", "Widow", "Disability",
        ],
        "gender": [
            "Gender", "Sex", "लिंग",
        ],
        "mobile_number": [
            "Mobile Number", "Phone", "मोबाइल नंबर",
        ],
        "account_number": [
            "Bank Account Number", "Account No", "Account Number",
            "बैंक खाता संख्या", "खाता नंबर",
        ],
        "ifsc_code": [
            "IFSC Code", "IFSC", "बैंक IFSC कोड",
        ],
        "bank_name": [
            "Bank Name", "Bank", "बैंक का नाम",
        ],
        "annual_income": [
            "Annual Income", "Income", "वार्षिक आय",
        ],
        "pin_code": [
            "PIN Code", "Pincode", "पिन कोड",
        ],
        "district": [
            "District", "जिला",
        ],
        "state": [
            "State", "राज्य",
        ],
    },
    "pan_card": {
        "full_name": [
            "Full Name", "Applicant Name", "Name as in Aadhaar",
            "पूरा नाम", "नाम",
        ],
        "date_of_birth": [
            "Date of Birth", "DOB", "जन्म तिथि",
        ],
        "father_name": [
            "Father Name", "Father's Name",
            "पिता का नाम",
        ],
        "aadhaar_number": [
            "Aadhaar Number", "UID", "आधार संख्या",
        ],
        "mobile_number": [
            "Mobile Number", "Phone", "मोबाइल नंबर",
        ],
        "email": [
            "Email", "Email Address", "ईमेल",
        ],
        "pin_code": [
            "PIN Code", "Pincode", "पिन कोड",
        ],
        "state": [
            "State", "राज्य",
        ],
    },
    "pm_kisan": {
        "applicant_name": [
            "Applicant Name", "Farmer Name", "Name", "किसान का नाम",
        ],
        "aadhaar_number": [
            "Aadhaar Number", "आधार संख्या",
        ],
        "date_of_birth": [
            "Date of Birth", "DOB", "जन्म तिथि",
        ],
        "mobile_number": [
            "Mobile Number", "Phone", "मोबाइल नंबर",
        ],
        "land_holding_acres": [
            "Land Holding", "Land in Acres", "Farm Size", "ज़मीन की माप",
        ],
        "bank_account_number": [
            "Account Number", "Bank Account", "खाता नंबर",
        ],
        "ifsc_code": [
            "IFSC Code", "IFSC", "आईएफएससी कोड",
        ],
        "state": [
            "State", "राज्य",
        ],
        "pin_code": [
            "PIN Code", "Pincode", "पिन कोड",
        ],
    },
}

# ── Select/Dropdown Options per form type ───────────────────
SELECT_OPTIONS: dict[str, dict[str, dict[str, str]]] = {
    "ration_card": {
        "category": {
            "APL": "apl", "BPL": "bpl", "AAY": "aay",
            "APLBPL": "apl",   # treat as BPL if in NFSA
        },
        "gender": {
            "male": "male", "Male": "male",
            "female": "female", "Female": "female",
            "other": "other", "Other": "other",
        },
    },
    "pension": {
        "pension_type": {
            "old_age": "old_age", "Old Age": "old_age",
            "widow": "widow", "Widow": "widow",
            "disability": "disability", "Disability": "disability",
        },
        "gender": {
            "male": "male", "Male": "male",
            "female": "female", "Female": "female",
            "other": "other", "Other": "other",
        },
    },
    "pan_card": {
        "gender": {
            "male": "male", "Male": "male",
            "female": "female", "Female": "female",
            "other": "other", "Other": "other",
        },
        "source_of_income": {
            "salary": "salary", "Business": "business",
            "No Income": "no_income", "Capital Gains": "capital_gains",
        },
    },
}

# ── Page Flow per form type ────────────────────────────────
# The order of form sections on the portal (for scroll navigation)
PAGE_SECTIONS: dict[str, list[str]] = {
    "ration_card": [
        "Personal Details", "Address Details", "Bank Details", "Declaration",
        "व्यक्तिगत विवरण", "पता विवरण", "बैंक विवरण",
    ],
    "pension": [
        "Beneficiary Details", "Bank Details", "Document Upload", "Declaration",
        "लाभार्थी विवरण", "बैंक विवरण",
    ],
    "pan_card": [
        "Personal Information", "Address", "Contact", "Declaration",
        "व्यक्तिगत जानकारी", "पता",
    ],
    "pm_kisan": [
        "Farmer Details", "Land Details", "Bank Details", "Declaration",
        "किसान विवरण", "ज़मीन विवरण", "बैंक विवरण",
    ],
}

# ── OTP page detection patterns ─────────────────────────────
OTP_KEYWORDS: dict[str, list[str]] = {
    "default": [
        "otp", "one-time password", "verification code", "code sent",
        "एक बार पासवर्ड", "सत्यापन कोड", "OTP भेजें",
        "enter otp", "verify otp", "कोड दर्ज करें",
    ],
}


def get_portal_info(form_type: str) -> dict:
    """Get full portal configuration for a form type."""
    return {
        "url": PORTAL_URLS.get(form_type, "https://services.india.gov.in/"),
        "name": PORTAL_NAMES.get(form_type, "Government Portal"),
        "field_mappings": FIELD_MAPPINGS.get(form_type, {}),
        "select_options": SELECT_OPTIONS.get(form_type, {}),
        "sections": PAGE_SECTIONS.get(form_type, []),
        "otp_keywords": OTP_KEYWORDS["default"],
    }


def get_field_labels(form_type: str, field_name: str) -> list[str]:
    """Get all label variants for a field (for VLM matching)."""
    mappings = FIELD_MAPPINGS.get(form_type, {})
    return mappings.get(field_name, [field_name.replace("_", " ").title()])


def match_field_by_label(
    visible_label: str,
    form_type: str,
    form_data_keys: list[str],
) -> tuple[Optional[str], float]:
    """
    Match a visible label on screen to a GramSetu field name.
    Returns (field_name, confidence).

    Uses fuzzy matching to handle Hindi/English label variations.
    """
    visible_lower = visible_label.lower().strip()

    # Check direct mappings first
    mappings = FIELD_MAPPINGS.get(form_type, {})
    for field_name, labels in mappings.items():
        if field_name not in form_data_keys:
            continue
        for label in labels:
            if label.lower() in visible_lower or visible_lower in label.lower():
                return field_name, 0.95

    # Fuzzy fallback: match by keyword
    for key in form_data_keys:
        key_lower = key.lower().replace("_", " ")
        if key_lower in visible_lower:
            return key, 0.7

    return None, 0.0