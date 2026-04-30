"""
DigiLocker MCP Server — Secure document and data fetching.

Exposes tools:
  - fetch_user_data: Retrieve user's identity data from DigiLocker
  - extract_form_data: Use LLM to extract form fields from user context
  - list_available_documents: List documents available in DigiLocker
  - fetch_document: Fetch a specific document by type

This MCP server connects to the LLM for intelligent data extraction
instead of using hardcoded demo data.
"""

import os
import json
from typing import Optional
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("GramSetu DigiLocker Server")

# ── In-memory user data store (production: real DigiLocker API) ─
# Users can register their data through the web app vault or chat
_USER_DATA_STORE: dict[str, dict] = {}


@mcp.tool()
def register_user_data(user_id: str, data: dict) -> dict:
    """
    Register user's identity data in the secure store.
    Data is keyed by user_id and encrypted in production.

    Args:
        user_id: Unique identifier for the user
        data: Dict of user data (name, aadhaar, address, bank, etc.)
    """
    _USER_DATA_STORE[user_id] = data
    return {"registered": True, "fields_stored": len(data)}


@mcp.tool()
def fetch_user_data(user_id: str) -> dict:
    """
    Fetch user's stored identity data.
    Returns all available fields for the user.

    Args:
        user_id: The user's unique identifier
    """
    data = _USER_DATA_STORE.get(user_id, {})
    if not data:
        return {
            "found": False,
            "extracted_data": {},
            "message": "No data found. User needs to register their information first."
        }

    # Redact Aadhaar in response
    safe_data = dict(data)
    for key in list(safe_data.keys()):
        if "aadhaar" in key.lower() and isinstance(safe_data[key], str):
            clean = safe_data[key].replace(" ", "").replace("-", "")
            if len(clean) >= 4:
                safe_data[key] = f"XXXX-XXXX-{clean[-4:]}"

    return {
        "found": True,
        "extracted_data": data,
        "safe_data": safe_data,
        "fields_count": len(data),
    }


@mcp.tool()
def list_available_documents(user_id: str) -> dict:
    """
    List all document types available for this user.
    """
    data = _USER_DATA_STORE.get(user_id, {})
    if not data:
        return {"documents": [], "count": 0}

    doc_types = []
    if any(k for k in data if "aadhaar" in k.lower()):
        doc_types.append("aadhaar_card")
    if any(k for k in data if "pan" in k.lower()):
        doc_types.append("pan_card")
    if any(k for k in data if "voter" in k.lower()):
        doc_types.append("voter_id")
    if any(k for k in data if "bank" in k.lower() or "account" in k.lower()):
        doc_types.append("bank_details")
    if any(k for k in data if "address" in k.lower() or "pincode" in k.lower()):
        doc_types.append("address_proof")
    if any(k for k in data if "name" in k.lower()):
        doc_types.append("identity_proof")

    return {"documents": doc_types, "count": len(doc_types)}


@mcp.tool()
def fetch_document(user_id: str, document_type: str) -> dict:
    """
    Fetch a specific document type for the user.

    Args:
        user_id: User identifier
        document_type: e.g. 'aadhaar_card', 'pan_card', 'bank_details'
    """
    data = _USER_DATA_STORE.get(user_id, {})
    if not data:
        return {"found": False, "document": {}, "message": "No user data found"}

    doc_map = {
        "aadhaar_card": ["aadhaar_number", "aadhaar", "uid"],
        "pan_card": ["pan_number", "pan", "pan_card"],
        "bank_details": ["account_number", "ifsc_code", "bank_name", "account_holder_name"],
        "address_proof": ["address", "pincode", "district", "state", "pin_code"],
        "identity_proof": ["name", "full_name", "applicant_name", "date_of_birth", "dob", "gender"],
    }

    keys = doc_map.get(document_type, [])
    result = {}
    for key in keys:
        if key in data:
            result[key] = data[key]
        elif any(k for k in data if key.lower() in k.lower()):
            match = next(k for k in data if key.lower() in k.lower())
            result[match] = data[match]

    return {"found": bool(result), "document_type": document_type, "data": result}


@mcp.tool()
async def extract_form_data(form_type: str, user_context: str) -> dict:
    """
    Use LLM to intelligently extract form fields from user-provided context.
    This is the core function that replaces hardcoded demo data.

    Args:
        form_type: The type of form to fill (e.g. 'ration_card', 'generic')
        user_context: Free-text user information (name, address, etc.)
                      Can be collected conversationally.

    Returns:
        Dict with extracted_data, confidence_scores, and missing_fields
    """
    try:
        from backend.llm_client import chat_intent
    except ImportError:
        return _fallback_extract(form_type, user_context)

    system_prompt = f"""You are a form data extraction AI. Extract structured fields from the user's text.

Form type: {form_type}

Extract ALL available fields from the user's text. For each field, assign a confidence score (0.0-1.0).

Return ONLY valid JSON with these keys:
- extracted_data: dict of field_name -> value
- confidence_scores: dict of field_name -> confidence (0.0-1.0)
- missing_fields: list of fields that are needed but not found

Common fields to look for:
- name/full_name/applicant_name
- aadhaar_number
- date_of_birth (YYYY-MM-DD)
- gender (male/female/other)
- mobile_number
- address (line1, line2, district, state, pincode)
- father_name, mother_name
- annual_income
- bank_account (account_number, ifsc_code, bank_name)
- family_members, category"""

    user_text = user_context or ""
    if not user_text.strip():
        return {
            "extracted_data": {},
            "confidence_scores": {},
            "missing_fields": ["name", "aadhaar_number", "mobile_number", "date_of_birth", "address"],
            "message": "No user context provided. Please provide your details."
        }

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Extract form fields from this user information:\n\n{user_text}"},
    ]

    try:
        raw = await chat_intent(messages, temperature=0.1, max_tokens=1024)
        if raw:
            import re as _re
            m = _re.search(r'\{.*\}', raw, _re.DOTALL)
            if m:
                parsed = json.loads(m.group(0))
                return {
                    "extracted_data": parsed.get("extracted_data", {}),
                    "confidence_scores": parsed.get("confidence_scores", {}),
                    "missing_fields": parsed.get("missing_fields", []),
                }
    except Exception as e:
        pass

    return _fallback_extract(form_type, user_text)


def _fallback_extract(form_type: str, user_text: str) -> dict:
    """Manual extraction fallback when LLM is unavailable."""
    data = {}
    conf = {}
    text = user_text or ""

    import re as _re

    # Aadhaar
    aadhaar_match = _re.search(r'\b([2-9]\d{2}[\s-]?\d{4}[\s-]?\d{4})\b', text)
    if aadhaar_match:
        data["aadhaar_number"] = _re.sub(r'[\s-]', '', aadhaar_match.group(1))
        conf["aadhaar_number"] = 0.9

    # Mobile
    mobile_match = _re.search(r'\b([6-9]\d{9})\b', text)
    if mobile_match:
        data["mobile_number"] = mobile_match.group(1)
        conf["mobile_number"] = 0.9

    # Date
    dob_match = _re.search(r'(\d{2,4}[/-]\d{1,2}[/-]\d{2,4})', text)
    if dob_match:
        data["date_of_birth"] = dob_match.group(1)
        conf["date_of_birth"] = 0.7

    # Name — take first capitalized words
    name_match = _re.search(r'(?:name is|i am|name:?)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', text, _re.I)
    if name_match:
        data["name"] = name_match.group(1)
        conf["name"] = 0.6

    missing = [f for f in ["name", "aadhaar_number", "mobile_number", "date_of_birth"] if f not in data]

    return {
        "extracted_data": data,
        "confidence_scores": conf,
        "missing_fields": missing,
    }
