"""
============================================
nims_client.py — NVIDIA NIM API Client
============================================
Calls NVIDIA's free LLM API (Llama 3.1 70B Instruct).
Uses the OpenAI-compatible endpoint format.

FREE TIER: https://build.nvidia.com → Get API Key
Base URL: https://integrate.api.nvidia.com/v1
"""

import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# ---- Configuration ----
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")

# Create the OpenAI-compatible client pointed at NVIDIA
client = None
if NVIDIA_API_KEY and NVIDIA_API_KEY != "nvapi-your-key-here":
    client = OpenAI(
        base_url=NVIDIA_BASE_URL,
        api_key=NVIDIA_API_KEY,
    )


def is_nim_available() -> bool:
    """Check if NVIDIA NIM API is configured and available."""
    return client is not None


def chat_completion(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = 1024,
    system_prompt: str = None,
) -> str:
    """
    Send a chat completion request to NVIDIA NIM (Llama 3.1 70B).
    
    Args:
        messages: List of chat messages [{"role": "user", "content": "..."}]
        temperature: Creativity level (0 = deterministic, 1 = creative)
        max_tokens: Max response length
        system_prompt: Optional system instruction
    
    Returns:
        The model's text response, or a fallback if NIM is unavailable.
    """
    if not is_nim_available():
        return _fallback_response(messages)
    
    # Prepend system prompt if provided
    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)
    
    try:
        response = client.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[NIM] ❌ API Error: {e}")
        return _fallback_response(messages)


def detect_intent(user_message: str) -> dict:
    """
    Use NIM to detect user's intent from their message.
    
    Returns:
        {"intent": "apply_form" | "check_status" | "greeting" | "help" | "unknown",
         "form_type": "pan_card" | "pm_kisan" | null,
         "language": "hi" | "en"}
    """
    system = """You are an intent classifier for a government form-filling assistant in India.
Classify the user's message into one of these intents:
- "greeting": User is saying hello/namaste
- "apply_form": User wants to apply for a government scheme or fill a form
- "check_status": User wants to check application status
- "provide_info": User is providing personal information (name, Aadhaar, etc.)
- "help": User needs help or has a question
- "confirm": User is confirming/saying yes
- "deny": User is saying no/rejecting
- "unknown": Can't determine intent

Also detect:
- form_type: "pan_card", "pm_kisan", "aadhaar", or null
- language: "hi" (Hindi) or "en" (English)

Respond ONLY with valid JSON, no other text:
{"intent": "...", "form_type": "...", "language": "..."}"""

    response = chat_completion(
        messages=[{"role": "user", "content": user_message}],
        system_prompt=system,
        temperature=0.1,
        max_tokens=100,
    )
    
    try:
        # Try to parse JSON from response
        # Handle cases where model wraps JSON in markdown code blocks
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean
            clean = clean.rsplit("```", 1)[0] if "```" in clean else clean
            clean = clean.strip()
        return json.loads(clean)
    except (json.JSONDecodeError, Exception):
        # Fallback: simple keyword detection
        return _fallback_intent(user_message)


def extract_entities(user_message: str, form_type: str, existing_data: dict = None) -> dict:
    """
    Use NIM to extract entities (name, Aadhaar, DOB, etc.) from user message.
    
    Returns:
        {"field_name": {"value": "...", "confidence": 0.0-1.0}, ...}
    """
    existing_str = json.dumps(existing_data or {}, indent=2)
    
    system = f"""You are an entity extractor for Indian government forms.
The user is filling a "{form_type}" form.
Already collected data: {existing_str}

Extract any new information from the user's message. For each field found, assign a confidence score (0.0 to 1.0).

Fields to look for:
- full_name: Person's full name
- father_name: Father's name  
- date_of_birth: DOB in DD/MM/YYYY format
- aadhaar_number: 12-digit Aadhaar number
- pan_number: 10-character PAN (e.g., ABCDE1234F)
- mobile_number: 10-digit phone number
- email: Email address
- address: Full address
- pincode: 6-digit PIN code
- state: Indian state name
- district: District name
- annual_income: Yearly income
- bank_account: Bank account number
- ifsc_code: Bank IFSC code
- land_acres: Land area in acres

Respond ONLY with valid JSON:
{{"field_name": {{"value": "extracted_value", "confidence": 0.95}}, ...}}
If no new information found, respond: {{}}"""

    response = chat_completion(
        messages=[{"role": "user", "content": user_message}],
        system_prompt=system,
        temperature=0.1,
        max_tokens=500,
    )

    try:
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean
            clean = clean.rsplit("```", 1)[0] if "```" in clean else clean
            clean = clean.strip()
        return json.loads(clean)
    except (json.JSONDecodeError, Exception):
        return {}


def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """
    Translate text between Hindi and English using NIM.
    
    Args:
        text: Text to translate
        source_lang: Source language code ("hi" or "en")
        target_lang: Target language code ("hi" or "en")
    """
    if source_lang == target_lang:
        return text
    
    lang_names = {"hi": "Hindi", "en": "English"}
    system = f"Translate the following {lang_names.get(source_lang, source_lang)} text to {lang_names.get(target_lang, target_lang)}. Respond with ONLY the translation, nothing else."
    
    response = chat_completion(
        messages=[{"role": "user", "content": text}],
        system_prompt=system,
        temperature=0.2,
        max_tokens=500,
    )
    return response


def generate_response(user_message: str, context: str, language: str = "hi") -> str:
    """
    Generate a natural conversational response in the user's language.
    
    Args:
        user_message: What the user said
        context: Current conversation context/state
        language: Response language ("hi" or "en")
    """
    lang = "Hindi" if language == "hi" else "English"
    system = f"""You are GramSetu (ग्रामसेतु), a friendly government form-filling assistant for rural Indians.
You speak {lang}. Be warm, simple, and use respectful language.
You help people fill government forms like PAN Card, PM-KISAN, Aadhaar, etc.

Current context: {context}

Rules:
- Keep responses SHORT (2-3 sentences max)
- Use emojis for friendliness
- If asking for information, ask for ONE field at a time
- Use simple {lang} that rural users can understand"""

    response = chat_completion(
        messages=[{"role": "user", "content": user_message}],
        system_prompt=system,
        temperature=0.5,
        max_tokens=300,
    )
    return response


# ---- Fallback Functions (when NIM is not available) ----

def _fallback_response(messages: list) -> str:
    """Fallback when NIM API is not configured — uses keyword matching."""
    if not messages:
        return "Welcome to GramSetu! How can I help you?"
    last_msg = messages[-1].get("content", "").lower()
    
    # Simple keyword-based response
    if any(w in last_msg for w in ["namaste", "namaskar", "hello", "hi"]):
        return '{"intent": "greeting", "form_type": null, "language": "hi"}'
    elif any(w in last_msg for w in ["pan", "पैन"]):
        return '{"intent": "apply_form", "form_type": "pan_card", "language": "hi"}'
    elif any(w in last_msg for w in ["kisan", "किसान", "pm-kisan"]):
        return '{"intent": "apply_form", "form_type": "pm_kisan", "language": "hi"}'
    elif any(w in last_msg for w in ["status", "स्थिति", "check"]):
        return '{"intent": "check_status", "form_type": null, "language": "hi"}'
    elif any(w in last_msg for w in ["haan", "yes", "ha", "ji", "हाँ"]):
        return '{"intent": "confirm", "form_type": null, "language": "hi"}'
    elif any(w in last_msg for w in ["nahi", "no", "naa", "नहीं"]):
        return '{"intent": "deny", "form_type": null, "language": "hi"}'
    return '{"intent": "provide_info", "form_type": null, "language": "hi"}'


def _fallback_intent(user_message: str) -> dict:
    """Fallback intent detection using simple keyword matching."""
    msg = user_message.lower().strip()
    
    if any(w in msg for w in ["namaste", "namaskar", "hello", "hi", "नमस्ते"]):
        lang = "hi" if any(c >= '\u0900' and c <= '\u097F' for c in msg) else "en"
        return {"intent": "greeting", "form_type": None, "language": lang}
    elif any(w in msg for w in ["pan", "पैन"]):
        return {"intent": "apply_form", "form_type": "pan_card", "language": "hi"}
    elif any(w in msg for w in ["kisan", "किसान", "pm-kisan", "pm kisan"]):
        return {"intent": "apply_form", "form_type": "pm_kisan", "language": "hi"}
    elif any(w in msg for w in ["status", "स्थिति", "track"]):
        return {"intent": "check_status", "form_type": None, "language": "en"}
    elif any(w in msg for w in ["help", "madad", "मदद", "sahayata"]):
        return {"intent": "help", "form_type": None, "language": "hi"}
    elif any(w in msg for w in ["haan", "yes", "ha", "ji", "हाँ", "ok"]):
        return {"intent": "confirm", "form_type": None, "language": "hi"}
    elif any(w in msg for w in ["nahi", "no", "naa", "नहीं"]):
        return {"intent": "deny", "form_type": None, "language": "hi"}
    
    # Check for Devanagari script
    has_hindi = any(c >= '\u0900' and c <= '\u097F' for c in msg)
    return {"intent": "provide_info", "form_type": None, "language": "hi" if has_hindi else "en"}
