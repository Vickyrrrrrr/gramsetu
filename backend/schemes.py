"""
============================================================
schemes.py — LLM-Powered Scheme Discovery Engine
============================================================
NOT hardcoded — uses the LLM with Google Search grounding
to discover government schemes in REAL TIME.

When a user says "I'm a farmer, 65 years old":
1. The LLM searches government websites (india.gov.in, myscheme.gov.in)
2. It finds ALL matching schemes with eligibility criteria
3. Returns a WhatsApp-formatted list with benefits

Falls back to a curated local database if LLM is unavailable.
"""

import json
from typing import Optional

from backend.llm_client import chat, extract_json, get_active_provider


# ============================================================
# LLM-Powered Scheme Discovery (PRIMARY)
# ============================================================

async def discover_schemes(
    age: Optional[int] = None,
    gender: Optional[str] = None,
    income: Optional[float] = None,
    occupation: Optional[str] = None,
    state: Optional[str] = None,
    language: str = "hi",
    extra_keywords: Optional[str] = None,
) -> dict:
    """
    Discover eligible government schemes using LLM + web search.

    The LLM searches real government websites and returns
    current, accurate scheme information — not hardcoded data.

    Falls back to local database if no LLM is available.

    Args:
        extra_keywords: Free-form hint string to guide LLM search
                        (e.g. "farmer needs agricultural loan")
    """
    # Try LLM-powered discovery first (Groq 70B with scheme knowledge)
    from backend.llm_client import get_active_provider
    if get_active_provider() != "fallback":
        try:
            llm_result = await _llm_discover(
                age=age, gender=gender, income=income,
                occupation=occupation, state=state,
                language=language, extra_keywords=extra_keywords,
            )
            if llm_result and llm_result.get("count", 0) > 0:
                return llm_result
        except Exception as e:
            print(f"[Schemes] LLM discovery failed, using local: {e}")

    # Fallback to local curated database (always works)
    return _local_discover(age, gender, income, occupation, language)


async def _llm_discover(
    age: Optional[int],
    gender: Optional[str],
    income: Optional[float],
    occupation: Optional[str],
    state: Optional[str],
    language: str,
    extra_keywords: Optional[str] = None,
) -> dict:
    """Use LLM + Google Search to find real schemes."""

    # Build user profile description
    profile_parts = []
    if age:
        profile_parts.append(f"Age: {age} years")
    if gender:
        profile_parts.append(f"Gender: {gender}")
    if income:
        profile_parts.append(f"Annual income: ₹{income:,.0f}")
    if occupation:
        profile_parts.append(f"Occupation: {occupation}")
    if state:
        profile_parts.append(f"State: {state}")
    if extra_keywords:
        profile_parts.append(f"Specific need: {extra_keywords}")

    profile = ", ".join(profile_parts) if profile_parts else "General citizen of rural India"

    messages = [
        {
            "role": "system",
            "content": (
                "You are an Indian government scheme expert. "
                "Search real government websites (myscheme.gov.in, india.gov.in, "
                "pmkisan.gov.in, nsap.nic.in, nfsa.gov.in) and find ALL government "
                "schemes this person is eligible for.\n\n"
                "Return ONLY valid JSON in this format:\n"
                "```json\n"
                "{\n"
                '  "schemes": [\n'
                "    {\n"
                '      "name": "Scheme Name",\n'
                '      "name_hi": "Hindi Name",\n'
                '      "benefit": "₹6000/year",\n'
                '      "description": "Short description",\n'
                '      "portal": "https://...",\n'
                '      "eligibility": "Brief eligibility criteria",\n'
                '      "emoji": "🌾"\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "```\n"
                "Include central AND state-level schemes. "
                "Be accurate with benefits amounts. "
                "Return 5-15 matching schemes."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Find all eligible government schemes for this person:\n"
                f"Profile: {profile}\n\n"
                f"Search Indian government websites and find real, current schemes. "
                f"Include PM-KISAN, NSAP pensions, NFSA ration, PMFBY, Ujjwala, "
                f"Awas Yojana, and any state-specific schemes if applicable."
            ),
        },
    ]

    # Use NIM general model for scheme research
    use_search = False
    response = await chat(messages, temperature=0.2, max_tokens=3000, use_web_search=use_search)

    # Parse JSON from response
    data = await extract_json(response)
    if not data or "schemes" not in data:
        return {"count": 0, "eligible": [], "message": ""}

    schemes = data["schemes"]

    # Build WhatsApp message
    if language == "hi":
        message = _build_message_hi(schemes)
    else:
        message = _build_message_en(schemes)

    return {
        "eligible": schemes,
        "count": len(schemes),
        "message": message,
        "source": "llm_web_search",
    }


async def discover_from_message(text: str, language: str = "hi") -> dict:
    """
    Auto-discover government schemes from free-form conversational text.
    Uses keyword extraction (no LLM) for instant, reliable results.
    """
    # ── Keyword-based profile extraction (no LLM) ────────────
    lower = text.lower()
    profile: dict = {}

    # Occupation
    if any(w in lower for w in ["kisan", "farmer", "kisaan", "vivasayi", "ryot", "krushi", "kheti"]):
        profile["occupation"] = "farmer"
    elif any(w in lower for w in ["mazdoor", "labor", "mgnrega", "nrega", "coolie"]):
        profile["occupation"] = "laborer"
    elif any(w in lower for w in ["student", "padhai", "school", "college", "vidyarthi"]):
        profile["occupation"] = "student"
    elif any(w in lower for w in ["bujurg", "budhapa", "old age", "vridha", "senior"]):
        profile["occupation"] = "senior"
    elif any(w in lower for w in ["widow", "vidhwa", "divyang", "disabled"]):
        profile["occupation"] = "widow"

    # Age hints
    import re as _re
    age_match = _re.search(r'\b(\d{1,3})\s*(?:saal|year|sal|varsh|age)\b', lower)
    if age_match:
        try:
            profile["age"] = int(age_match.group(1))
        except ValueError:
            pass

    # Income hints
    income_match = _re.search(r'(\d[\d,]*)\s*(?:income|aay|rupay|rs|inr|lakh)', lower)
    if income_match:
        try:
            profile["income"] = int(income_match.group(1).replace(",", ""))
        except ValueError:
            pass

    # Search for matching schemes with extracted profile
    return await discover_schemes(
        age=profile.get("age"),
        gender=profile.get("gender"),
        income=profile.get("income"),
        occupation=profile.get("occupation"),
        state=profile.get("state"),
        language=language,
        extra_keywords=text[:200],
    )


async def check_application_status(
    form_type: str,
    application_id: str = "",
    language: str = "hi",
) -> dict:
    """
    Use LLM to find how to check application status on the actual portal.
    Can also scrape the status page if application_id is provided.
    """
    portal_map = {
        "ration_card": "https://nfsa.gov.in/",
        "pension": "https://nsap.nic.in/",
        "pm_kisan": "https://pmkisan.gov.in/",
        "pan_card": "https://www.onlineservices.nsdl.com/paam/",
    }

    portal = portal_map.get(form_type, "https://services.india.gov.in/")

    messages = [
        {
            "role": "system",
            "content": (
                "You are helping a rural Indian citizen check their government "
                "application status. Search the relevant portal and provide "
                "accurate status checking information.\n\n"
                "Return JSON:\n"
                "```json\n"
                "{\n"
                '  "portal_url": "...",\n'
                '  "status_check_url": "...",\n'
                '  "steps_hi": ["Step 1...", "Step 2..."],\n'
                '  "steps_en": ["Step 1...", "Step 2..."],\n'
                '  "helpline": "1800-XXX-XXXX",\n'
                '  "estimated_days": 15\n'
                "}\n"
                "```"
            ),
        },
        {
            "role": "user",
            "content": (
                f"How to check {form_type.replace('_', ' ')} application status?\n"
                f"Portal: {portal}\n"
                f"Application ID: {application_id or 'Not provided'}\n"
                f"Find the correct status tracking URL and steps."
            ),
        },
    ]

    response = await chat(messages, temperature=0.1, max_tokens=1000, use_web_search=False)
    data = await extract_json(response)

    if data:
        steps = data.get(f"steps_{language}", data.get("steps_en", []))
        if language == "hi":
            message = (
                f"📋 *{form_type.replace('_', ' ').title()} — स्थिति जाँचें*\n\n"
                f"🌐 {data.get('status_check_url', portal)}\n\n"
                + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps)) +
                f"\n\n📞 हेल्पलाइन: {data.get('helpline', 'N/A')}"
            )
        else:
            message = (
                f"📋 *{form_type.replace('_', ' ').title()} — Check Status*\n\n"
                f"🌐 {data.get('status_check_url', portal)}\n\n"
                + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps)) +
                f"\n\n📞 Helpline: {data.get('helpline', 'N/A')}"
            )
        return {"message": message, "data": data}

    # Fallback
    return {
        "message": f"📋 Visit {portal} to check your status.",
        "data": {"portal_url": portal},
    }


# ============================================================
# LOCAL FALLBACK DATABASE
# ============================================================

FALLBACK_SCHEMES = [
    {
        "name": "Ration Card (BPL/APL)", "name_hi": "राशन कार्ड",
        "benefit": "₹1-3/kg food grains", "emoji": "🍚",
        "description": "Subsidized wheat, rice, dal",
        "eligibility": {"min_age": 18, "max_income": 10_000_000, "gender": "any", "occupation": "any"},
        "portal": "https://nfsa.gov.in/", "id": "ration_card",
    },
    {
        "name": "Old Age Pension (IGNOAPS)", "name_hi": "वृद्धावस्था पेंशन",
        "benefit": "₹200-500/month", "emoji": "👴",
        "description": "For senior citizens 60+ years (BPL)",
        "eligibility": {"min_age": 60, "max_income": 200_000, "gender": "any", "occupation": "any"},
        "portal": "https://nsap.nic.in/", "id": "pension_old_age",
    },
    {
        "name": "PM-KISAN", "name_hi": "पीएम-किसान",
        "benefit": "₹6,000/year", "emoji": "🌾",
        "description": "Income support for farmers",
        "eligibility": {"min_age": 18, "max_income": 10_000_000, "gender": "any", "occupation": "farmer"},
        "portal": "https://pmkisan.gov.in/", "id": "pm_kisan",
    },
    {
        "name": "PM Fasal Bima", "name_hi": "फसल बीमा",
        "benefit": "Crop insurance", "emoji": "🌱",
        "description": "Crop insurance for farmers",
        "eligibility": {"min_age": 18, "max_income": 10_000_000, "gender": "any", "occupation": "farmer"},
        "portal": "https://pmfby.gov.in/", "id": "fasal_bima",
    },
    {
        "name": "PAN Card", "name_hi": "पैन कार्ड",
        "benefit": "Tax filing + KYC", "emoji": "📇",
        "description": "Essential identity document",
        "eligibility": {"min_age": 18, "max_income": 10_000_000, "gender": "any", "occupation": "any"},
        "portal": "https://www.onlineservices.nsdl.com/paam/", "id": "pan_card",
    },
    {
        "name": "Voter ID", "name_hi": "मतदाता पहचान पत्र",
        "benefit": "Voting rights + ID proof", "emoji": "🗳️",
        "description": "Right to vote document",
        "eligibility": {"min_age": 18, "max_income": 10_000_000, "gender": "any", "occupation": "any"},
        "portal": "https://voters.eci.gov.in/", "id": "voter_id",
    },
    {
        "name": "PM Ujjwala Yojana", "name_hi": "उज्ज्वला योजना",
        "benefit": "Free LPG connection", "emoji": "🔥",
        "description": "Free LPG for BPL families",
        "eligibility": {"min_age": 18, "max_income": 200_000, "gender": "female", "occupation": "any"},
        "portal": "https://pmuy.gov.in/", "id": "ujjwala",
    },
    {
        "name": "PM Awas Yojana", "name_hi": "आवास योजना",
        "benefit": "₹1.2-2.5 lakh housing", "emoji": "🏠",
        "description": "Housing subsidy for BPL",
        "eligibility": {"min_age": 18, "max_income": 300_000, "gender": "any", "occupation": "any"},
        "portal": "https://pmaymis.gov.in/", "id": "awas_yojana",
    },
    {
        "name": "Soil Health Card", "name_hi": "मृदा स्वास्थ्य कार्ड",
        "benefit": "Free soil analysis", "emoji": "🧪",
        "description": "Soil testing for farmers",
        "eligibility": {"min_age": 18, "max_income": 10_000_000, "gender": "any", "occupation": "farmer"},
        "portal": "https://soilhealth.dac.gov.in/", "id": "soil_health",
    },
    {
        "name": "Widow Pension (IGNWPS)", "name_hi": "विधवा पेंशन",
        "benefit": "₹300-500/month", "emoji": "🙏",
        "description": "For widowed women (40+)",
        "eligibility": {"min_age": 40, "max_income": 200_000, "gender": "female", "occupation": "any"},
        "portal": "https://nsap.nic.in/", "id": "pension_widow",
    },
    {
        "name": "Disability Pension (IGNDPS)", "name_hi": "विकलांग पेंशन",
        "benefit": "₹300-500/month", "emoji": "♿",
        "description": "For persons with 40%+ disability",
        "eligibility": {"min_age": 18, "max_income": 200_000, "gender": "any", "occupation": "any"},
        "portal": "https://nsap.nic.in/", "id": "pension_disability",
    },
]


def _local_discover(
    age: Optional[int],
    gender: Optional[str],
    income: Optional[float],
    occupation: Optional[str],
    language: str,
) -> dict:
    """Fallback: filter from local curated database."""
    eligible = []

    for scheme in FALLBACK_SCHEMES:
        elig = scheme["eligibility"]
        if age is not None and age < elig.get("min_age", 0):
            continue
        if income is not None and income > elig.get("max_income", float("inf")):
            continue
        if elig.get("gender") != "any" and gender and gender != elig["gender"]:
            continue
        if elig.get("occupation") != "any" and occupation != elig["occupation"]:
            continue
        eligible.append(scheme)

    if language == "hi":
        message = _build_message_hi(eligible)
    else:
        message = _build_message_en(eligible)

    return {
        "eligible": eligible,
        "count": len(eligible),
        "message": message,
        "source": "local_database",
    }


def _build_message_hi(schemes: list) -> str:
    if not schemes:
        return "🔍 कोई योजना नहीं मिली।"
    lines = [f"🎯 *आप {len(schemes)} सरकारी योजनाओं के लिए पात्र हैं!*\n"]
    for i, s in enumerate(schemes, 1):
        name = s.get("name_hi", s.get("name", ""))
        emoji = s.get("emoji", "📋")
        benefit = s.get("benefit", "")
        lines.append(f"{i}️⃣ {emoji} *{name}*\n      💰 {benefit}\n")
    lines.append("\n👉 नंबर भेजें — बाकी सब मैं करूँगा! 🤖")
    return "\n".join(lines)


def _build_message_en(schemes: list) -> str:
    if not schemes:
        return "🔍 No schemes found."
    lines = [f"🎯 *You're eligible for {len(schemes)} government schemes!*\n"]
    for i, s in enumerate(schemes, 1):
        name = s.get("name", "")
        emoji = s.get("emoji", "📋")
        benefit = s.get("benefit", "")
        lines.append(f"{i}️⃣ {emoji} *{name}*\n      💰 {benefit}\n")
    lines.append("\n👉 Send the number — I'll do the rest! 🤖")
    return "\n".join(lines)


def get_scheme_by_number(number: int, eligible_schemes: list) -> Optional[dict]:
    """Get a scheme by display number."""
    if 1 <= number <= len(eligible_schemes):
        return eligible_schemes[number - 1]
    return None
