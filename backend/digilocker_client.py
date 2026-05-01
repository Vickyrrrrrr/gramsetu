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


async def group_fields_by_topic(fields: list[str], form_type: str) -> list[dict]:
    """
    LLM groups 15-30 fields into 3-5 topic clusters for conversational collection.
    Returns: [{"topic": "Company Details", "fields": ["company_name", ...]}]
    """
    if len(fields) <= 6:
        return [{"topic": "All Details", "fields": fields}]

    try:
        from backend.llm_client import chat_intent
        prompt = (
            f"I have {len(fields)} fields for a '{form_type}' application: {', '.join(fields[:30])}. "
            "Group these fields into 3-5 logical topic clusters. "
            "Return ONLY JSON: [{\"topic\": \"short name\", \"fields\": [\"field1\", \"field2\"]}]."
        )
        result = await chat_intent(
            [{"role": "system", "content": "Group form fields into topics. Return ONLY valid JSON array."},
             {"role": "user", "content": prompt}], temperature=0.1, max_tokens=600
        )
        if result:
            m = re.search(r'\[.*\]', result, re.DOTALL)
            if m:
                groups = json.loads(m.group(0))
                if isinstance(groups, list) and len(groups) >= 2:
                    return groups
    except Exception as e:
        print(f"[DigiLocker] Grouping failed: {e}")

    # Fallback: auto-group by field name prefixes
    return _auto_group_fields(fields)


def _auto_group_fields(fields: list[str]) -> list[dict]:
    """Auto-group by field name prefixes if LLM grouping fails."""
    groups = {}
    topic_map = {
        "name": "Personal Details", "founder": "Founder & Background",
        "cofounder": "Founder & Background", "education": "Founder & Background",
        "background": "Founder & Background",
        "company": "Company Details", "description": "Company Details",
        "problem": "Company Details", "solving": "Company Details",
        "story": "Company Details", "founding": "Company Details",
        "product": "Product & Tech", "tech": "Product & Tech",
        "market": "Market & Traction", "revenue": "Market & Traction",
        "growth": "Market & Traction", "users": "Market & Traction",
        "competitor": "Market & Traction", "traction": "Market & Traction",
        "team": "Team", "hire": "Team",
        "financial": "Financial", "funding": "Financial",
        "objective": "Goals & Fit", "why": "Goals & Fit",
        "achievement": "Goals & Fit", "goal": "Goals & Fit",
    }
    for field in fields:
        matched = False
        for key, topic in topic_map.items():
            if key in field.lower():
                groups.setdefault(topic, []).append(field)
                matched = True
                break
        if not matched:
            groups.setdefault("Additional Details", []).append(field)

    return [{"topic": t, "fields": fs} for t, fs in groups.items()]


async def generate_group_question(
    topic: str, fields: list[str], form_type: str,
    collected_count: int, total_count: int,
) -> str:
    """
    LLM generates a natural paragraph-style question for a group of related fields.
    Example: "Tell me about your company — what's it called, what problem
              are you solving, how did you come up with the idea?"
    """
    if len(fields) <= 3:
        field_list = " and ".join(f.replace("_", " ").title() for f in fields)
        return f"Please share your *{field_list}*."

    try:
        from backend.llm_client import chat_intent
        prompt = (
            f"You are helping a user fill a '{form_type}' application. "
            f"You need to collect these fields about '{topic}': {', '.join(f.title().replace('_',' ') for f in fields)}. "
            f"So far {collected_count}/{total_count} fields collected. "
            f"Generate ONE warm, natural question (2-3 sentences) asking about ALL these fields at once. "
            f"Use examples, make it conversational. User will respond with a paragraph. "
            f"Be encouraging and specific. Do NOT list fields separately — weave them into a natural question."
        )
        result = await chat_intent(
            [{"role": "system", "content": "Generate natural, warm questions. 2-3 sentences. Be conversational."},
             {"role": "user", "content": prompt}], temperature=0.7, max_tokens=200
        )
        if result and len(result.strip()) > 10:
            return result.strip()
    except Exception as e:
        print(f"[DigiLocker] Question generation failed: {e}")

    # Fallback
    field_list = ", ".join(f.replace("_", " ").title() for f in fields[:8])
    return (
        f"Tell me about your *{topic}* — specifically: {field_list}. "
        f"Write freely, I'll extract the details."
    )
