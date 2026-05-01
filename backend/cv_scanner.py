"""
============================================================
cv_scanner.py — Resume/CV Upload → VLM Extraction → Vault
============================================================
User uploads resume once → GramSetu extracts everything via VLM
→ stored encrypted in Supabase → auto-fills ANY future form.

Works with: PDFs, images (JPG/PNG), WhatsApp document shares.
VLM: NVIDIA llama-3.2-11b-vision-instruct (free tier).
"""
import json
import re
from backend.persistent_state import set_state, get_state


async def scan_and_store_resume(user_id: str, document_b64: str, document_type: str = "pdf") -> dict:
    """
    Extract ALL personal information from a resume/CV via NVIDIA VLM.
    Stores result in Supabase; returns extracted data for immediate use.
    """
    try:
        from backend.llm_client import chat_vision
    except ImportError:
        return {"error": "VLM not available", "fields_extracted": 0}

    prompt = """You are a resume/CV parser. Extract ALL personal information from this document.

Return ONLY valid JSON with these keys. Use snake_case. Leave empty for missing fields.
Include fields that exist on the document — do NOT invent data.

{
  "personal": {
    "full_name": "",
    "email": "",
    "phone": "",
    "date_of_birth": "",
    "gender": "",
    "nationality": "",
    "languages": [],
    "linkedin_url": "",
    "github_url": "",
    "portfolio_url": "",
    "current_location": "",
    "willing_to_relocate": false
  },
  "education": [
    {"degree": "", "institution": "", "year": "", "gpa": "", "major": ""}
  ],
  "experience": [
    {"company": "", "role": "", "start_date": "", "end_date": "", "description": "", "achievements": ""}
  ],
  "skills": [],
  "projects": [
    {"name": "", "description": "", "technologies": [], "url": ""}
  ],
  "achievements": [],
  "certifications": [],
  "summary": "",
  "document_type": "resume"
}"""

    try:
        vlm_raw = await chat_vision(document_b64, prompt, temperature=0.0, max_tokens=2048)
        if not vlm_raw:
            return _fallback_scan(document_b64)

        m = re.search(r'\{.*\}', vlm_raw, re.DOTALL)
        if not m:
            return _fallback_scan(document_b64)

        parsed = json.loads(m.group(0))

        # Store in Supabase
        set_state("cv_data", user_id, {
            "personal": parsed.get("personal", {}),
            "education": parsed.get("education", []),
            "experience": parsed.get("experience", []),
            "skills": parsed.get("skills", []),
            "projects": parsed.get("projects", []),
            "achievements": parsed.get("achievements", []),
            "certifications": parsed.get("certifications", []),
            "summary": parsed.get("summary", ""),
            "last_scanned": __import__("time").time(),
        })

        # Extract key fields for form auto-filling
        personal = parsed.get("personal", {})
        fields_count = sum(
            1 for v in personal.values() if v
        ) + len(parsed.get("education", [])) + len(parsed.get("skills", []))

        return {
            "extracted": True,
            "fields_extracted": fields_count,
            "name": personal.get("full_name", ""),
            "email": personal.get("email", ""),
            "phone": personal.get("phone", ""),
            "skills_count": len(parsed.get("skills", [])),
            "experience_years": len(parsed.get("experience", [])),
            "message": f"Resume scanned — {fields_count} fields extracted and stored.",
        }

    except Exception as e:
        print(f"[CV Scanner] Extraction failed: {e}")
        return {"error": str(e), "fields_extracted": 0}


def _fallback_scan(document_b64: str) -> dict:
    """Fallback if VLM fails — return basic response."""
    return {
        "extracted": False,
        "fields_extracted": 0,
        "message": "Could not read the resume. Please try uploading a clearer copy or type your details.",
    }


def get_cv_data(user_id: str) -> dict:
    """Retrieve stored CV/resume data for auto-filling forms."""
    data = get_state("cv_data", user_id)
    if not data:
        return {"found": False, "message": "No resume data stored. Upload your resume first."}

    return {
        "found": True,
        "personal": data.get("personal", {}),
        "education": data.get("education", []),
        "experience": data.get("experience", []),
        "skills": data.get("skills", []),
        "summary": data.get("summary", ""),
        "last_scanned": data.get("last_scanned", 0),
    }


def map_cv_to_form_fields(cv_data: dict, required_fields: list[str]) -> dict:
    """
    Map stored CV data to ANY form's required fields.
    Uses fuzzy matching to fill as many fields as possible.

    Example:
      form needs ["founder_name", "email", "linkedin_url"]
      CV has: {full_name: "Vicky", email: "v@email.com", linkedin_url: "..."}
      Returns: {founder_name: "Vicky", email: "v@email.com", linkedin_url: "..."}
    """
    if not cv_data.get("found"):
        return {}

    personal = cv_data.get("personal", {})
    result = {}

    # Direct mappings
    field_aliases = {
        # Name variants
        "full_name": ["full_name", "name", "applicant_name", "founder_name", "first_name", "last_name", "student_name"],
        "email": ["email", "email_address", "contact_email", "founder_email"],
        "phone": ["phone", "mobile", "mobile_number", "contact_number", "phone_number"],
        "date_of_birth": ["date_of_birth", "dob", "birth_date"],
        "gender": ["gender", "sex"],
        "current_location": ["current_location", "location", "city", "address", "current_city"],
        "linkedin_url": ["linkedin_url", "linkedin", "linkedin_profile"],
        "github_url": ["github_url", "github", "github_profile"],
        "portfolio_url": ["portfolio_url", "portfolio", "personal_website", "website"],
        "languages": ["languages", "language", "known_languages"],
        "nationality": ["nationality"],
    }

    for cv_field, aliases in field_aliases.items():
        value = personal.get(cv_field)
        if value:
            for required in required_fields:
                if required in aliases:
                    result[required] = value
                    break

    # Skills → comma-separated string
    skills = cv_data.get("skills", [])
    if skills and any("skill" in f.lower() or "tech" in f.lower() or "technology" in f.lower() for f in required_fields):
        for req in required_fields:
            if "skill" in req.lower() or "tech" in req.lower() or "stack" in req.lower():
                result[req] = ", ".join(skills[:15])

    # Education
    education = cv_data.get("education", [])
    if education:
        first_edu = education[0]
        for req in required_fields:
            if "education" in req.lower() or "degree" in req.lower():
                result[req] = f"{first_edu.get('degree', '')} from {first_edu.get('institution', '')} ({first_edu.get('year', '')})"
            if "university" in req.lower() or "college" in req.lower() or "institution" in req.lower():
                result[req] = first_edu.get("institution", "")

    # Experience → years + latest company
    experience = cv_data.get("experience", [])
    if experience:
        latest = experience[0]
        for req in required_fields:
            if "previous_startups" in req.lower() or "past_experience" in req.lower():
                result[req] = f"{len(experience)} roles including {latest.get('role', '')} at {latest.get('company', '')}"
            if "current_role" in req.lower() or "job" in req.lower() or "occupation" in req.lower():
                result[req] = latest.get("role", "")
            if "company" in req.lower() or "employer" in req.lower():
                result[req] = latest.get("company", "")

    # Summary → description/story/objective
    summary = cv_data.get("summary", "")
    if summary:
        for req in required_fields:
            if any(w in req.lower() for w in ["description", "story", "objective", "about", "background", "summary"]):
                if req not in result:
                    result[req] = summary[:500]

    return result
