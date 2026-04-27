"""
DigiLocker client - demo data for form filling.
"""

def _get_demo_data(form_type: str) -> dict:
    """Return demo data simulating DigiLocker extraction."""
    aadhaar = {
        "aadhaar_number": "2834 1256 9087",
        "name": "राम कुमार शर्मा",
        "name_en": "Ram Kumar Sharma",
        "date_of_birth": "1985-03-15",
        "gender": "Male",
        "father_name": "श्री सुरेश कुमार शर्मा",
        "mobile_number": "9876543210",
        "address_line1": "ग्राम पंचायत सुभाषनगर",
        "address_line2": "ब्लॉक सदर",
        "district": "लखनऊ",
        "state": "उत्तर प्रदेश",
        "pincode": "226001",
    }
    bank = {
        "account_holder_name": "Ram Kumar Sharma",
        "account_number": "31850100073456",
        "ifsc_code": "SBIN0001234",
        "bank_name": "State Bank of India",
    }
    
    if form_type == "ration_card":
        data = {"applicant_name": aadhaar["name_en"], "aadhaar_number": aadhaar["aadhaar_number"].replace(" ", ""), "date_of_birth": aadhaar["date_of_birth"], "gender": aadhaar["gender"].lower(), "family_head_name": aadhaar["name_en"], "family_members": 4, "annual_income": 120000, "category": "BPL", "mobile_number": aadhaar["mobile_number"], "address": {"line1": aadhaar["address_line1"], "line2": aadhaar["address_line2"], "district": aadhaar["district"], "state": aadhaar["state"], "pincode": aadhaar["pincode"]}}
        conf = {"applicant_name": 0.98, "aadhaar_number": 0.99, "date_of_birth": 0.98, "gender": 0.98, "family_head_name": 0.90, "family_members": 0.90, "annual_income": 0.90, "category": 0.90, "mobile_number": 0.95, "address": 0.95}
    elif form_type == "pension":
        data = {"applicant_name": aadhaar["name_en"], "aadhaar_number": aadhaar["aadhaar_number"].replace(" ", ""), "date_of_birth": aadhaar["date_of_birth"], "pension_type": "old_age", "gender": aadhaar["gender"].lower(), "mobile_number": aadhaar["mobile_number"], "annual_income": 60000, "address": {"line1": aadhaar["address_line1"], "line2": aadhaar["address_line2"], "district": aadhaar["district"], "state": aadhaar["state"], "pincode": aadhaar["pincode"]}, "bank_account": bank}
        conf = {"applicant_name": 0.98, "aadhaar_number": 0.99, "date_of_birth": 0.98, "gender": 0.98, "mobile_number": 0.95, "address": 0.95, "pension_type": 0.90, "annual_income": 0.90, "bank_account": 0.90}
    else:
        data = {"full_name": aadhaar["name_en"], "aadhaar_number": aadhaar["aadhaar_number"].replace(" ", ""), "date_of_birth": aadhaar["date_of_birth"], "gender": aadhaar["gender"].lower(), "mobile_number": aadhaar["mobile_number"], "address": {"line1": aadhaar["address_line1"], "line2": aadhaar["address_line2"], "district": aadhaar["district"], "state": aadhaar["state"], "pincode": aadhaar["pincode"]}}
        conf = {"full_name": 0.98, "aadhaar_number": 0.99, "date_of_birth": 0.98, "gender": 0.98, "mobile_number": 0.95, "address": 0.95}
        if form_type in ("pm_kisan", "kisan_credit_card", "jan_dhan", "mnrega", "ayushman_bharat"):
            data["bank_account"] = bank
            conf["bank_account"] = 0.90
    
    return {"extracted_data": data, "confidence_scores": conf, "sources": {}, "missing_fields": [], "ready_to_submit": True}
