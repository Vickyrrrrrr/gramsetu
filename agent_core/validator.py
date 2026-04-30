"""
============================================
validator.py — Rule-Based Form Validation
============================================
Checks Aadhaar checksum, PAN format, PINCODE, phone number, etc.
No API calls needed — pure Python validation.
"""

import re


def validate_aadhaar(number: str) -> dict:
    """
    Validate Aadhaar number using Verhoeff algorithm checksum.
    Aadhaar is a 12-digit number issued by UIDAI.
    
    Returns:
        {"valid": True/False, "error": "error message if invalid"}
    """
    # Remove spaces and hyphens
    clean = re.sub(r"[\s\-]", "", str(number))
    
    if not clean.isdigit():
        return {"valid": False, "error": "Aadhaar must contain only digits"}
    
    if len(clean) != 12:
        return {"valid": False, "error": f"Aadhaar must be 12 digits (got {len(clean)})"}
    
    if clean[0] == "0" or clean[0] == "1":
        return {"valid": False, "error": "Aadhaar cannot start with 0 or 1"}
    
    # Verhoeff checksum tables
    d_table = [
        [0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],
        [2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],
        [4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],
        [6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],
        [8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]
    ]
    p_table = [
        [0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],
        [5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],
        [9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],
        [2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]
    ]
    
    c = 0
    digits = [int(x) for x in reversed(clean)]
    for i, digit in enumerate(digits):
        c = d_table[c][p_table[i % 8][digit]]
    
    if c != 0:
        return {"valid": False, "error": "Aadhaar checksum invalid"}
    
    return {"valid": True, "error": None}


def validate_pan(pan: str) -> dict:
    """
    Validate PAN (Permanent Account Number) format.
    PAN format: ABCDE1234F (5 letters, 4 digits, 1 letter)
    """
    clean = str(pan).upper().strip()
    
    if len(clean) != 10:
        return {"valid": False, "error": f"PAN must be 10 characters (got {len(clean)})"}
    
    pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]$'
    if not re.match(pattern, clean):
        return {"valid": False, "error": "PAN format: 5 letters + 4 digits + 1 letter (e.g., ABCDE1234F)"}
    
    # 4th character indicates holder type
    valid_4th = "ABCFGHLJPT"
    if clean[3] not in valid_4th:
        return {"valid": False, "error": f"4th character '{clean[3]}' is not a valid PAN category"}
    
    return {"valid": True, "error": None}


def validate_pincode(pincode: str) -> dict:
    """
    Validate Indian PIN code (6 digits, first digit 1-9).
    """
    clean = re.sub(r"\s", "", str(pincode))
    
    if not clean.isdigit() or len(clean) != 6:
        return {"valid": False, "error": "PIN code must be 6 digits"}
    
    if clean[0] == "0":
        return {"valid": False, "error": "PIN code cannot start with 0"}
    
    return {"valid": True, "error": None}


def validate_phone(phone: str) -> dict:
    """
    Validate Indian mobile number (10 digits starting with 6-9).
    """
    clean = re.sub(r"[\s\-\+]", "", str(phone))
    
    # Remove country code
    if clean.startswith("91") and len(clean) == 12:
        clean = clean[2:]
    
    if not clean.isdigit() or len(clean) != 10:
        return {"valid": False, "error": "Phone must be 10 digits"}
    
    if clean[0] not in "6789":
        return {"valid": False, "error": "Indian mobile numbers start with 6, 7, 8, or 9"}
    
    return {"valid": True, "error": None}


def validate_dob(dob: str) -> dict:
    """
    Validate date of birth (DD/MM/YYYY format, reasonable age).
    """
    import datetime
    
    patterns = [
        (r"(\d{2})[/\-](\d{2})[/\-](\d{4})", "%d/%m/%Y"),
        (r"(\d{4})[/\-](\d{2})[/\-](\d{2})", "%Y/%m/%d"),
    ]
    
    clean = str(dob).strip()
    
    for pattern, fmt in patterns:
        match = re.match(pattern, clean)
        if match:
            try:
                date_str = clean.replace("-", "/")
                parsed = datetime.datetime.strptime(date_str, fmt)
                age = (datetime.datetime.now() - parsed).days // 365
                
                if age < 0:
                    return {"valid": False, "error": "Date of birth cannot be in the future"}
                if age > 150:
                    return {"valid": False, "error": "Invalid date of birth"}
                if age < 18:
                    return {"valid": False, "error": "Applicant must be at least 18 years old"}
                
                return {"valid": True, "error": None, "formatted": parsed.strftime("%d/%m/%Y")}
            except ValueError:
                return {"valid": False, "error": "Invalid date format"}
    
    return {"valid": False, "error": "Date format should be DD/MM/YYYY"}


def validate_ifsc(ifsc: str) -> dict:
    """
    Validate IFSC (Indian Financial System Code).
    Format: 4 letters + 0 + 6 alphanumeric characters
    """
    clean = str(ifsc).upper().strip()
    
    if len(clean) != 11:
        return {"valid": False, "error": "IFSC must be 11 characters"}
    
    pattern = r'^[A-Z]{4}0[A-Z0-9]{6}$'
    if not re.match(pattern, clean):
        return {"valid": False, "error": "IFSC format: 4 letters + 0 + 6 alphanumeric (e.g., SBIN0001234)"}
    
    return {"valid": True, "error": None}


def validate_name(name: str) -> dict:
    """Validate that a name is reasonable."""
    clean = str(name).strip()
    
    if len(clean) < 2:
        return {"valid": False, "error": "Name is too short"}
    
    if len(clean) > 100:
        return {"valid": False, "error": "Name is too long"}
    
    # Allow letters, spaces, periods (for initials)
    if not re.match(r'^[\w\s\.\u0900-\u097F]+$', clean):
        return {"valid": False, "error": "Name contains invalid characters"}
    
    return {"valid": True, "error": None}


def validate_field(field_name: str, value: str) -> dict:
    """
    Master validator: validate any field by name.
    
    Returns:
        {"valid": True/False, "error": "...", "confidence_boost": 0.0-0.1}
    """
    validators = {
        "aadhaar_number": validate_aadhaar,
        "pan_number": validate_pan,
        "pincode": validate_pincode,
        "mobile_number": validate_phone,
        "phone": validate_phone,
        "date_of_birth": validate_dob,
        "ifsc_code": validate_ifsc,
        "full_name": validate_name,
        "father_name": validate_name,
    }
    
    validator = validators.get(field_name)
    if validator:
        result = validator(str(value))
        # Add confidence boost for validated fields
        result["confidence_boost"] = 0.1 if result["valid"] else -0.2
        return result
    
    # No specific validator — basic non-empty check
    if value and str(value).strip():
        return {"valid": True, "error": None, "confidence_boost": 0.0}
    return {"valid": False, "error": f"{field_name} cannot be empty", "confidence_boost": -0.1}


from datetime import datetime


def normalize_field_value(field_name: str, value):
    """Normalize user/LLM extracted values before validation."""
    if value is None:
        return value
    if isinstance(value, str):
        value = value.strip()
        value = re.sub(r"\s+", " ", value)
    if field_name in {"aadhaar_number", "mobile", "phone", "pincode"} and value is not None:
        return re.sub(r"[^0-9]", "", str(value))
    if field_name in {"pan_number", "pan"} and value is not None:
        return str(value).strip().upper().replace(" ", "")
    if field_name in {"email"} and value is not None:
        return str(value).strip().lower()
    return value


def validate_cross_field_consistency(form_type: str, data: dict) -> dict:
    """Deterministic checks across fields so AI cannot submit contradictory data."""
    errors = []
    name = str(data.get("applicant_name") or data.get("full_name") or "").strip()
    guardian = str(data.get("father_name") or data.get("guardian_name") or "").strip()
    mobile = str(data.get("mobile") or data.get("phone") or "").strip()
    pincode = str(data.get("pincode") or "").strip()
    dob = str(data.get("date_of_birth") or data.get("dob") or "").strip()

    if name and guardian and name.lower() == guardian.lower():
        errors.append("Applicant name and father/guardian name cannot be identical")
    if mobile and len(mobile) == 10 and mobile[0] not in '6789':
        errors.append("Indian mobile number must start with 6, 7, 8, or 9")
    if pincode and len(pincode) == 6 and pincode[0] == '0':
        errors.append("PIN code cannot start with 0")
    if dob:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                parsed = datetime.strptime(dob, fmt)
                if parsed.year < 1900 or parsed > datetime.now():
                    errors.append("Date of birth is out of allowed range")
                break
            except Exception:
                continue
    return {"valid": len(errors) == 0, "errors": errors}


def final_submission_gate(form_type: str, data: dict, required_fields: list | None = None) -> dict:
    """Hard stop before browser automation starts."""
    normalized = {}
    for k, v in (data or {}).items():
        normalized[k] = normalize_field_value(k, v)

    field_errors = {}
    for key, value in normalized.items():
        result = validate_field(key, value)
        if isinstance(result, dict) and not result.get("valid", True):
            field_errors[key] = result.get("error", "Invalid value")

    missing = []
    for field in (required_fields or []):
        if normalized.get(field) in (None, "", []):
            missing.append(field)

    consistency = validate_cross_field_consistency(form_type, normalized)
    return {
        "valid": not field_errors and not missing and consistency.get("valid", False),
        "normalized": normalized,
        "missing": missing,
        "field_errors": field_errors,
        "consistency_errors": consistency.get("errors", []),
    }
