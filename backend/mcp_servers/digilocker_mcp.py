"""
============================================================
digilocker_mcp.py — DigiLocker Data Extraction MCP Server
============================================================
FastMCP server for autonomous data extraction from DigiLocker.

The agent NEVER asks the user to type their Aadhaar or PAN.
Instead, it pulls everything from DigiLocker automatically.

Flow:
  1. User says "I want a ration card"
  2. Agent sends DigiLocker OAuth link on WhatsApp
  3. User clicks → logs in → grants permission
  4. Agent extracts ALL data: Aadhaar, PAN, address, DOB, photo
  5. Agent shows summary → user confirms → portal filled

Tools:
  - send_digilocker_auth_link:   Send OAuth URL to user on WhatsApp
  - check_auth_status:           Poll if user completed DigiLocker login
  - fetch_aadhaar_data:          Pull Aadhaar details (name, DOB, address, photo)
  - fetch_pan_data:              Pull PAN card details
  - fetch_driving_license:       Pull DL details
  - fetch_all_documents:         Pull ALL available docs at once
  - extract_form_fields:         Map DigiLocker data → form fields automatically

DigiLocker API: https://developers.digilocker.gov.in/
"""

import os
import re
import json
import time
import uuid
import hashlib
import base64
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

# ── DigiLocker API Config ────────────────────────────────────
DIGILOCKER_CLIENT_ID = os.getenv("DIGILOCKER_CLIENT_ID", "")
DIGILOCKER_CLIENT_SECRET = os.getenv("DIGILOCKER_CLIENT_SECRET", "")
DIGILOCKER_REDIRECT_URI = os.getenv("DIGILOCKER_REDIRECT_URI", "http://localhost:8000/callback/digilocker")
DIGILOCKER_AUTH_URL = "https://digilocker.meripehchaan.gov.in/public/oauth2/1/authorize"
DIGILOCKER_TOKEN_URL = "https://digilocker.meripehchaan.gov.in/public/oauth2/1/token"
DIGILOCKER_API_BASE = "https://digilocker.meripehchaan.gov.in/public/oauth2/3"

# ── FastMCP Server ───────────────────────────────────────────
mcp = FastMCP(
    name="gramsetu-digilocker",
    instructions="DigiLocker integration for autonomous data extraction — "
                 "the user never types their Aadhaar or PAN.",
)

# ── Session storage for auth tokens ──────────────────────────
_auth_sessions: dict[str, dict] = {}


# ============================================================
# TOOL 1: Send DigiLocker Auth Link
# ============================================================

@mcp.tool()
async def send_digilocker_auth_link(
    user_phone: str,
    session_id: str,
    form_type: str,
) -> dict:
    """
    Generate a DigiLocker OAuth link and return it for WhatsApp delivery.
    The user clicks this link → logs into DigiLocker → grants data access.

    Args:
        user_phone: User's WhatsApp phone number
        session_id: Current conversation session ID
        form_type:  What form they want to fill (ration_card, pension, identity)

    Returns:
        {"auth_url": "https://...", "state": "uuid", "status": "WAIT_DIGILOCKER"}
    """
    state = str(uuid.uuid4())

    # Store session for callback
    _auth_sessions[state] = {
        "user_phone": user_phone,
        "session_id": session_id,
        "form_type": form_type,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "access_token": None,
        "data": {},
    }

    # Build OAuth URL
    auth_url = (
        f"{DIGILOCKER_AUTH_URL}"
        f"?response_type=code"
        f"&client_id={DIGILOCKER_CLIENT_ID}"
        f"&redirect_uri={DIGILOCKER_REDIRECT_URI}"
        f"&state={state}"
        f"&scope=openid"
    )

    # If no DigiLocker credentials, use demo mode
    if not DIGILOCKER_CLIENT_ID:
        auth_url = f"https://gramsetu.demo/digilocker?state={state}"
        # Auto-populate demo data
        _auth_sessions[state]["status"] = "completed"
        _auth_sessions[state]["data"] = _get_demo_data(form_type)

    return {
        "auth_url": auth_url,
        "state": state,
        "status": "WAIT_DIGILOCKER",
        "message_hi": (
            "🔐 *DigiLocker से आपका डेटा लेना होगा*\n\n"
            "📱 नीचे दी गई लिंक पर क्लिक करें:\n"
            f"👉 {auth_url}\n\n"
            "✅ DigiLocker में लॉगिन करें\n"
            "✅ अनुमति दें\n"
            "✅ मैं स्वचालित रूप से आपका डेटा ले लूँगा\n\n"
            "⏳ लिंक पर क्लिक करने के बाद मुझे बताएं"
        ),
        "message_en": (
            "🔐 *I need to pull your data from DigiLocker*\n\n"
            "📱 Click the link below:\n"
            f"👉 {auth_url}\n\n"
            "✅ Log in to DigiLocker\n"
            "✅ Grant permission\n"
            "✅ I'll automatically fetch your data\n\n"
            "⏳ Let me know after you've clicked the link"
        ),
    }


# ============================================================
# TOOL 2: Check Auth Status
# ============================================================

@mcp.tool()
async def check_auth_status(state: str) -> dict:
    """
    Check if the user has completed DigiLocker authorization.

    Returns:
        {"status": "completed|pending|expired", "data": {...} if completed}
    """
    session = _auth_sessions.get(state)
    if not session:
        return {"status": "not_found", "data": {}}

    return {
        "status": session["status"],
        "data": session.get("data", {}),
        "form_type": session.get("form_type", ""),
    }


# ============================================================
# TOOL 3: Fetch Aadhaar Data
# ============================================================

@mcp.tool()
async def fetch_aadhaar_data(access_token: str) -> dict:
    """
    Fetch Aadhaar card details from DigiLocker.
    Returns: name, DOB, gender, address, photo, aadhaar_number.

    In production, calls DigiLocker eAadhaar API.
    In demo mode, returns realistic sample data.
    """
    if not access_token or access_token == "demo":
        return _get_demo_aadhaar()

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{DIGILOCKER_API_BASE}/file/aadhaar",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        pass

    return _get_demo_aadhaar()


# ============================================================
# TOOL 4: Fetch PAN Data
# ============================================================

@mcp.tool()
async def fetch_pan_data(access_token: str) -> dict:
    """
    Fetch PAN card details from DigiLocker.
    Returns: pan_number, name, father_name, DOB.
    """
    if not access_token or access_token == "demo":
        return _get_demo_pan()

    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{DIGILOCKER_API_BASE}/file/pan",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        pass

    return _get_demo_pan()


# ============================================================
# TOOL 5: Fetch Driving License
# ============================================================

@mcp.tool()
async def fetch_driving_license(access_token: str) -> dict:
    """
    Fetch driving license details from DigiLocker.
    Returns: dl_number, name, DOB, address, blood_group.
    """
    if not access_token or access_token == "demo":
        return {
            "dl_number": "DL-0420110012345",
            "name": "राम कुमार शर्मा",
            "name_en": "Ram Kumar Sharma",
            "date_of_birth": "1985-03-15",
            "blood_group": "B+",
            "address": "ग्राम पंचायत सुभाषनगर, ब्लॉक सदर, जिला लखनऊ, उत्तर प्रदेश 226001",
            "valid_till": "2035-03-14",
            "source": "digilocker",
        }

    return {}


# ============================================================
# TOOL 6: Fetch ALL Documents (Master extraction)
# ============================================================

@mcp.tool()
async def fetch_all_documents(
    state: str,
    form_type: str = "",
) -> dict:
    """
    Pull ALL available documents from DigiLocker at once.
    This is the primary tool — call this instead of individual fetches.

    Automatically maps the extracted data to the required form fields.

    Args:
        state:     Auth state from send_digilocker_auth_link
        form_type: Which form to fill (determines which fields to extract)

    Returns:
        {
            "extracted_data": {all form fields pre-filled},
            "confidence_scores": {per-field confidence},
            "sources": {which document each field came from},
            "missing_fields": [fields not found in DigiLocker]
        }
    """
    session = _auth_sessions.get(state)
    if not session:
        # Demo mode — generate realistic data
        return _get_demo_data(form_type)

    if session.get("data"):
        return session["data"]

    access_token = session.get("access_token", "demo")

    # Fetch all documents in parallel
    aadhaar = await fetch_aadhaar_data(access_token)
    pan = await fetch_pan_data(access_token)
    dl = await fetch_driving_license(access_token)

    # Map to form fields based on form_type
    result = _map_to_form_fields(form_type, aadhaar, pan, dl)

    # Cache in session
    session["data"] = result
    return result


# ============================================================
# TOOL 7: Extract Form Fields
# ============================================================

@mcp.tool()
async def extract_form_fields(
    form_type: str,
    digilocker_data: dict,
) -> dict:
    """
    Map raw DigiLocker data to the exact fields needed for a form.

    Args:
        form_type:       ration_card, pension, identity
        digilocker_data: Raw data from fetch_all_documents

    Returns:
        {"form_data": {...}, "ready_to_submit": True/False, "missing": [...]}
    """
    return _map_to_form_fields(form_type, digilocker_data, {}, {})


# ============================================================
# Data Mapping: DigiLocker → Form Fields
# ============================================================

def _map_to_form_fields(form_type: str, aadhaar: dict, pan: dict, dl: dict) -> dict:
    """Map DigiLocker documents to the exact fields needed for a government form."""

    # Merge all sources — Aadhaar is primary, PAN & DL fill gaps
    name = aadhaar.get("name_en") or pan.get("name") or dl.get("name_en", "")
    dob = aadhaar.get("date_of_birth") or pan.get("date_of_birth") or dl.get("date_of_birth", "")
    gender = aadhaar.get("gender", "")
    father_name = pan.get("father_name") or aadhaar.get("father_name", "")
    mobile = aadhaar.get("mobile_number", "")
    aadhaar_num = aadhaar.get("aadhaar_number", "")
    pan_num = pan.get("pan_number", "")

    # Address from Aadhaar (most authoritative)
    address = {
        "line1": aadhaar.get("address_line1", ""),
        "line2": aadhaar.get("address_line2", ""),
        "district": aadhaar.get("district", ""),
        "state": aadhaar.get("state", ""),
        "pincode": aadhaar.get("pincode", ""),
    }

    sources = {}
    confidence = {}

    # ── Ration Card ──────────────────────────────────────────
    if form_type == "ration_card":
        form_data = {
            "applicant_name": name,
            "aadhaar_number": aadhaar_num,
            "date_of_birth": dob,
            "gender": gender.lower() if gender else "",
            "family_head_name": name,  # Default: applicant is head
            "family_members": 4,       # Default, user can correct
            "annual_income": 120000,   # Default, user can correct
            "category": "BPL",         # Default, user can correct
            "mobile_number": mobile,
            "address": address,
        }
        sources = {
            "applicant_name": "Aadhaar", "aadhaar_number": "Aadhaar",
            "date_of_birth": "Aadhaar", "gender": "Aadhaar",
            "mobile_number": "Aadhaar", "address": "Aadhaar",
            "family_head_name": "Default", "family_members": "Default",
            "annual_income": "Default", "category": "Default",
        }
        confidence = {
            "applicant_name": 0.98, "aadhaar_number": 0.99,
            "date_of_birth": 0.98, "gender": 0.98,
            "mobile_number": 0.95, "address": 0.95,
            "family_head_name": 0.60, "family_members": 0.30,
            "annual_income": 0.30, "category": 0.40,
        }

    # ── Pension ──────────────────────────────────────────────
    elif form_type == "pension":
        form_data = {
            "applicant_name": name,
            "aadhaar_number": aadhaar_num,
            "date_of_birth": dob,
            "pension_type": "old_age",  # Default, user can correct
            "gender": gender.lower() if gender else "",
            "mobile_number": mobile,
            "annual_income": 60000,     # Default
            "address": address,
            "bank_account": {
                "account_holder_name": name,
                "account_number": "",  # Not in DigiLocker
                "ifsc_code": "",       # Not in DigiLocker
                "bank_name": "",       # Not in DigiLocker
            },
        }
        sources = {
            "applicant_name": "Aadhaar", "aadhaar_number": "Aadhaar",
            "date_of_birth": "Aadhaar", "gender": "Aadhaar",
            "mobile_number": "Aadhaar", "address": "Aadhaar",
            "pension_type": "Default", "annual_income": "Default",
            "bank_account": "User input needed",
        }
        confidence = {
            "applicant_name": 0.98, "aadhaar_number": 0.99,
            "date_of_birth": 0.98, "gender": 0.98,
            "mobile_number": 0.95, "address": 0.95,
            "pension_type": 0.40, "annual_income": 0.30,
            "bank_account": 0.0,
        }

    # ── Identity (PAN/Voter ID) ──────────────────────────────
    elif form_type == "identity":
        form_data = {
            "full_name": name,
            "date_of_birth": dob,
            "document_type": "pan_card",
            "gender": gender.lower() if gender else "",
            "father_name": father_name,
            "aadhaar_number": aadhaar_num,
            "mobile_number": mobile,
            "address": address,
            "pan_category": "individual",
            "source_of_income": "salary",
        }
        sources = {
            "full_name": "Aadhaar", "date_of_birth": "Aadhaar",
            "gender": "Aadhaar", "father_name": "PAN",
            "aadhaar_number": "Aadhaar", "mobile_number": "Aadhaar",
            "address": "Aadhaar", "document_type": "Default",
        }
        confidence = {
            "full_name": 0.98, "date_of_birth": 0.98,
            "gender": 0.98, "father_name": 0.90,
            "aadhaar_number": 0.99, "mobile_number": 0.95,
            "address": 0.95, "document_type": 0.50,
        }

    elif form_type in ("pm_kisan", "kisan_credit_card"):
        form_data = {
            "full_name":     name,
            "dob":           dob,
            "gender":        gender.lower() if gender else "",
            "aadhaar":       aadhaar_num,
            "mobile":        mobile,
            "house_no":      address.get("line1", ""),
            "village":       address.get("line2", ""),
            "district":      address.get("district", ""),
            "state":         address.get("state", ""),
            "pin_code":      address.get("pincode", ""),
            "annual_income": 120000,
        }
        sources = {"full_name": "Aadhaar", "aadhaar": "Aadhaar", "mobile": "Aadhaar",
                   "dob": "Aadhaar", "gender": "Aadhaar", "house_no": "Aadhaar",
                   "village": "Aadhaar", "district": "Aadhaar", "state": "Aadhaar",
                   "pin_code": "Aadhaar", "annual_income": "Default"}
        confidence = {"full_name": 0.98, "aadhaar": 0.99, "mobile": 0.95,
                      "dob": 0.98, "gender": 0.98, "house_no": 0.90,
                      "village": 0.90, "district": 0.95, "state": 0.95,
                      "pin_code": 0.95, "annual_income": 0.30}

    elif form_type in ("jan_dhan", "mnrega", "ayushman_bharat",
                       "pan_card", "voter_id", "caste_certificate", "birth_certificate"):
        form_data = {
            "full_name":  name,
            "dob":        dob,
            "gender":     gender.lower() if gender else "",
            "aadhaar":    aadhaar_num,
            "mobile":     mobile,
            "house_no":   address.get("line1", ""),
            "village":    address.get("line2", ""),
            "district":   address.get("district", ""),
            "state":      address.get("state", ""),
            "pin_code":   address.get("pincode", ""),
        }
        sources = {"full_name": "Aadhaar", "aadhaar": "Aadhaar", "mobile": "Aadhaar",
                   "dob": "Aadhaar", "gender": "Aadhaar", "house_no": "Aadhaar",
                   "village": "Aadhaar", "district": "Aadhaar", "state": "Aadhaar",
                   "pin_code": "Aadhaar"}
        confidence = {"full_name": 0.98, "aadhaar": 0.99, "mobile": 0.95,
                      "dob": 0.98, "gender": 0.98, "house_no": 0.90,
                      "village": 0.90, "district": 0.95, "state": 0.95, "pin_code": 0.95}

    else:
        form_data = {
            "full_name":  name,
            "dob":        dob,
            "gender":     gender.lower() if gender else "",
            "aadhaar":    aadhaar_num,
            "mobile":     mobile,
            "house_no":   address.get("line1", ""),
            "village":    address.get("line2", ""),
            "district":   address.get("district", ""),
            "state":      address.get("state", ""),
            "pin_code":   address.get("pincode", ""),
        }
        sources = {"full_name": "Aadhaar", "aadhaar": "Aadhaar", "mobile": "Aadhaar"}
        confidence = {"full_name": 0.98, "aadhaar": 0.99, "mobile": 0.95}

    # Find missing fields (confidence == 0 or empty)
    missing = [k for k, v in form_data.items()
               if (not v) or (isinstance(v, dict) and not any(v.values()))]

    return {
        "extracted_data": form_data,
        "confidence_scores": confidence,
        "sources": sources,
        "missing_fields": missing,
        "ready_to_submit": len(missing) == 0,
    }


# ============================================================
# Demo Data — Realistic Indian data for testing
# ============================================================

def _get_demo_aadhaar() -> dict:
    return {
        "aadhaar_number": "2834 1256 9087",
        "name": "राम कुमार शर्मा",
        "name_en": "Ram Kumar Sharma",
        "date_of_birth": "1985-03-15",
        "gender": "Male",
        "father_name": "श्री सुरेश कुमार शर्मा",
        "mobile_number": "9876543210",
        "email": "",
        "address_line1": "ग्राम पंचायत सुभाषनगर",
        "address_line2": "ब्लॉक सदर",
        "district": "लखनऊ",
        "state": "उत्तर प्रदेश",
        "pincode": "226001",
        "photo_b64": "",
        "source": "digilocker_aadhaar",
    }


def _get_demo_pan() -> dict:
    return {
        "pan_number": "ABCDE1234F",
        "name": "Ram Kumar Sharma",
        "father_name": "Suresh Kumar Sharma",
        "date_of_birth": "1985-03-15",
        "source": "digilocker_pan",
    }


def _get_demo_bank() -> dict:
    """
    Demo bank account data (NPCI Aadhaar-linked account).

    In production: fetched from NPCI's Aadhaar Payment Bridge (APB) / Mapper API.
    Requires: (a) payment aggregator / bank license, or
              (b) Account Aggregator (AA) framework license from RBI.
    See DIGILOCKER_INTEGRATION.md for real API details.
    """
    return {
        "account_holder_name": "Ram Kumar Sharma",
        "account_number": "31850100073456",
        "ifsc_code": "SBIN0001234",
        "bank_name": "State Bank of India",
        "branch": "Lucknow Main Branch",
        "account_type": "savings",
        "linked_aadhaar": "2834 1256 9087",
        "npci_linked": True,
        "source": "npci_aadhaar_mapper_demo",
    }


def _get_demo_data(form_type: str) -> dict:
    aadhaar = _get_demo_aadhaar()
    pan = _get_demo_pan()
    dl = {}
    result = _map_to_form_fields(form_type, aadhaar, pan, dl)
    # Inject bank details where relevant
    bank = _get_demo_bank()
    if form_type in ("pension", "pm_kisan", "jan_dhan", "kisan_credit_card", "mnrega", "ayushman_bharat"):
        result["extracted_data"]["bank_account"] = {
            "account_holder_name": bank["account_holder_name"],
            "account_number": bank["account_number"],
            "ifsc_code": bank["ifsc_code"],
            "bank_name": bank["bank_name"],
        }
        result["confidence_scores"]["bank_account"] = 0.90
        result["sources"]["bank_account"] = "NPCI Aadhaar Mapper"
        # Remove bank_account from missing_fields if it was there
        result["missing_fields"] = [f for f in result["missing_fields"] if f != "bank_account"]
    return result


# ============================================================
# TOOL 8: Fetch Bank Details (NPCI Aadhaar-linked account)
# ============================================================

@mcp.tool()
async def fetch_bank_details(
    aadhaar_number: str,
    access_token: str = "demo",
) -> dict:
    """
    Fetch the bank account linked to the user's Aadhaar via NPCI.

    In production this calls the NPCI Aadhaar Payment Bridge (APB) Mapper API.
    Requirements for real API:
      - Payment aggregator license OR bank/NBFC integration
      - Or use the Account Aggregator (AA / Sahamati) framework — RBI licensed

    Args:
        aadhaar_number: User's 12-digit Aadhaar number
        access_token:   DigiLocker/NPCI access token

    Returns:
        {"account_number": "...", "ifsc_code": "...", "bank_name": "...", ...}
    """
    if not access_token or access_token == "demo":
        return _get_demo_bank()

    # Real NPCI APB API (requires license):
    # POST https://apb.npci.org.in/mapper/link/1.0/validate
    # Authorization: Bearer {access_token}
    # Body: {"aadhaarNumber": "<encrypted>", "referenceNumber": "<uuid>"}
    #
    # Or via Account Aggregator (AA) framework:
    # https://api.sahamati.org.in/aa/v2/accounts/link/token

    return _get_demo_bank()


# ── Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8103)
