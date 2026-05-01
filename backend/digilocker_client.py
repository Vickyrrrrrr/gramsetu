"""
DigiLocker client — LLM-driven data extraction.

No hardcoded demo data. Uses the LLM to extract form fields
from user-provided context OR calls the DigiLocker MCP tool
for registered user data.
"""

import json
import re


def _get_demo_data(form_type: str) -> dict:
    """
    Returns empty template — no hardcoded data.
    The agent collects user data conversationally or from the DigiLocker MCP.
    """
    return {
        "extracted_data": {},
        "confidence_scores": {},
        "sources": {},
        "missing_fields": [
            "applicant_name", "aadhaar_number", "date_of_birth", "gender",
            "mobile_number", "address"
        ],
        "ready_to_submit": False,
        "message": (
            "No pre-loaded data. Collect user information through conversation "
            "or the DigiLocker MCP tool before form filling."
        ),
    }


def _get_form_template(form_type: str) -> list[str]:
    """
    Returns empty list — fields are now determined dynamically by the LLM.
    No more hardcoded field templates for any form type.
    """
    return []


async def infer_form_fields(form_type: str, lang: str = "hi") -> list[str]:
    """
    Use LLM to dynamically determine what fields a form needs.
    Works for ANY form type — government, private, startup, academic.
    """
    try:
        from backend.llm_client import chat_intent
        prompt = (
            f"List ALL the fields required for a '{form_type}' application. "
            "Return ONLY a JSON array of field names using snake_case. "
            "Include personal details, address, bank details, and any form-specific fields. "
            "Example: ['applicant_name', 'aadhaar_number', 'date_of_birth', 'gender', 'mobile_number', 'address']"
        )
        messages = [
            {"role": "system", "content": "You are a form schema expert. Return ONLY valid JSON arrays. Consider ALL form types — government, private, academic, startup, visa, application."},
            {"role": "user", "content": prompt},
        ]
        raw = await chat_intent(messages, temperature=0.1, max_tokens=512)
        if raw:
            import re
            import json
            m = re.search(r'\[.*\]', raw, re.DOTALL)
            if m:
                fields = json.loads(m.group(0))
                if isinstance(fields, list) and len(fields) > 0:
                    return fields
    except Exception as e:
        print(f"[DigiLocker] Field inference failed: {e}")

    # Common fallback fields for any form
    return [
        "applicant_name", "aadhaar_number", "date_of_birth", "gender",
        "mobile_number", "address"
    ]


async def extract_with_llm(user_context: str, form_type: str) -> dict:
    """
    Use the LLM to extract structured form data from free-text user input.

    Args:
        user_context: Free-text from the user describing their information
        form_type: The form being filled

    Returns:
        Dict with extracted_data, confidence_scores, missing_fields
    """
    required_fields = _get_form_template(form_type)

    if not user_context or not user_context.strip():
        return {
            "extracted_data": {},
            "confidence_scores": {},
            "missing_fields": required_fields,
        }

    try:
        from backend.llm_client import chat_intent

        system = f"""Extract form data from user input. Form type: {form_type}

Required fields: {', '.join(required_fields)}

Return ONLY valid JSON with:
- extracted_data: {{field: value}} for every field you can find
- confidence_scores: {{field: 0.0-1.0}} confidence per field
- missing_fields: [list of required fields NOT found]

Be thorough — extract names, numbers, dates, addresses from any format."""

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_context},
        ]

        raw = await chat_intent(messages, temperature=0.1, max_tokens=1024)
        if raw:
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            if m:
                parsed = json.loads(m.group(0))
                return {
                    "extracted_data": parsed.get("extracted_data", {}),
                    "confidence_scores": parsed.get("confidence_scores", {}),
                    "missing_fields": parsed.get("missing_fields", required_fields),
                    "sources": {},
                }
    except Exception as e:
        print(f"[DigiLocker] LLM extraction failed: {e}")

    # Fallback: manual regex extraction
    return _manual_extract(user_context, required_fields)


def _manual_extract(text: str, required_fields: list[str]) -> dict:
    """Manual regex-based extraction as fallback."""
    data = {}
    conf = {}

    # Aadhaar
    m = re.search(r'\b([2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4})\b', text)
    if m:
        data["aadhaar_number"] = re.sub(r'[\s-]', '', m.group(1))
        conf["aadhaar_number"] = 0.9

    # Mobile
    m = re.search(r'\b([6-9]\d{9})\b', text)
    if m:
        data["mobile_number"] = m.group(1)
        conf["mobile_number"] = 0.9

    # Email
    m = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
    if m:
        data["email"] = m.group(0)
        conf["email"] = 0.7

    # PIN code
    m = re.search(r'\b([1-9]\d{5})\b', text)
    if m:
        data["pincode"] = m.group(1)
        conf["pincode"] = 0.7

    # IFSC
    m = re.search(r'\b([A-Z]{4}0[A-Z0-9]{6})\b', text, re.I)
    if m:
        data["ifsc_code"] = m.group(1).upper()
        conf["ifsc_code"] = 0.8

    # Address / city — extract text after "lucknow", "address:", "city:", comma-separated locations
    # Simple: take any non-numeric, non-email text after common separators
    parts = re.split(r'[,;|]', text)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Skip if it's a number, email, or already extracted
        if re.match(r'^[\d\s\-+.@]+$', part):
            continue
        if "@" in part:
            continue
        # This looks like an address/city/name
        if len(part) >= 2 and len(part) < 100:
            key = "address" if "address" in required_fields else (
                "applicant_name" if "applicant_name" in required_fields else "full_name"
            )
            if key not in data or conf.get(key, 0) < 0.5:
                data[key] = part
                conf[key] = 0.4

    missing = [f for f in required_fields if f not in data]

    return {
        "extracted_data": data,
        "confidence_scores": conf,
        "missing_fields": missing,
        "sources": {},
    }
