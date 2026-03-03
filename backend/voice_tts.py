"""
============================================================
voice_tts.py — Text-to-Speech for WhatsApp Voice Replies
============================================================
Uses edge-tts (FREE, Microsoft Edge neural voices) 
to generate voice replies in 10+ Indian languages.

The bot SPEAKS the form summary aloud — critical for 
users who can't read well (300M+ people in rural India).

All voices are FREE — no API key required.
Full voice list: python -m edge_tts --list-voices | grep "IN"
"""

import os
import uuid
import asyncio
from typing import Optional

# edge-tts is free, no API key needed
import edge_tts

# ── Output directory ─────────────────────────────────────────
VOICE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "voice_cache"
)
os.makedirs(VOICE_DIR, exist_ok=True)

# ── Voice Config — 10+ Indian Languages, FREE via edge-tts ──
# Format: { "lang_code": ("female_voice", "male_voice") }
VOICES: dict[str, tuple[str, str]] = {
    "hi":  ("hi-IN-SwaraNeural",       "hi-IN-MadhurNeural"),       # Hindi
    "en":  ("en-IN-NeerjaNeural",      "en-IN-PrabhatNeural"),      # Indian English
    "bn":  ("bn-IN-TanishaaNeural",    "bn-IN-BashkarNeural"),      # Bengali
    "ta":  ("ta-IN-PallaviNeural",     "ta-IN-ValluvarNeural"),     # Tamil
    "te":  ("te-IN-ShrutiNeural",      "te-IN-MohanNeural"),        # Telugu
    "mr":  ("mr-IN-AarohiNeural",      "mr-IN-ManoharNeural"),      # Marathi
    "gu":  ("gu-IN-DhwaniNeural",      "gu-IN-NiranjanNeural"),     # Gujarati
    "kn":  ("kn-IN-SapnaNeural",       "kn-IN-GaganNeural"),        # Kannada
    "ml":  ("ml-IN-SobhanaNeural",     "ml-IN-MidhunNeural"),       # Malayalam
    "pa":  ("pa-IN-OjasNeural",        "pa-IN-VaaniNeural"),        # Punjabi
    "ur":  ("ur-IN-GulNeural",         "ur-IN-SalmanNeural"),       # Urdu
    # Fallback for Hinglish / unknown
    "hinglish": ("hi-IN-SwaraNeural",  "hi-IN-MadhurNeural"),
}

# Language code aliases (normalise inputs)
LANG_ALIASES: dict[str, str] = {
    "hindi": "hi", "english": "en", "bengali": "bn", "bangla": "bn",
    "tamil": "ta", "telugu": "te", "marathi": "mr", "gujarati": "gu",
    "kannada": "kn", "malayalam": "ml", "punjabi": "pa", "urdu": "ur",
    "odia": "hi",   # edge-tts has no Odia yet → fallback to Hindi
    "assamese": "hi",  # no Assamese voice yet
}


async def text_to_speech(
    text: str,
    language: str = "hi",
    voice_gender: str = "female",
) -> Optional[str]:
    """
    Convert text to speech using edge-tts (FREE, no API key).

    Args:
        text:         Text to speak
        language:     BCP-47 code or name: "hi", "en", "bn", "ta", "te",
                      "mr", "gu", "kn", "ml", "pa", "ur", or their full names
        voice_gender: "female" (default) or "male"

    Returns:
        Path to the generated .mp3 file, or None if failed
    """
    # Normalise language code
    lang = LANG_ALIASES.get(language.lower(), language.lower())
    voices_pair = VOICES.get(lang, VOICES["hi"])
    voice = voices_pair[1] if voice_gender == "male" else voices_pair[0]

    # Clean text for speech (remove emojis, markdown)
    clean_text = _clean_for_speech(text)

    if not clean_text:
        return None

    # Generate audio
    filename = f"tts_{uuid.uuid4().hex[:8]}.mp3"
    filepath = os.path.join(VOICE_DIR, filename)

    try:
        communicate = edge_tts.Communicate(clean_text, voice)
        await communicate.save(filepath)
        return filepath
    except Exception as e:
        print(f"[TTS] Error ({lang}/{voice}): {e}")
        # Retry with Hindi fallback
        if lang != "hi":
            try:
                communicate = edge_tts.Communicate(clean_text, VOICES["hi"][0])
                await communicate.save(filepath)
                return filepath
            except Exception:
                pass
        return None


async def generate_summary_voice(
    form_data: dict,
    language: str = "hi",
) -> Optional[str]:
    """
    Generate a spoken summary of the form data.
    Used after DigiLocker extraction — bot reads the summary aloud.
    """
    if language == "hi":
        lines = ["आपके फ़ॉर्म का सारांश इस प्रकार है। "]
        for field, value in form_data.items():
            if isinstance(value, dict):
                continue
            label = _field_label_hi(field)
            if label and value:
                lines.append(f"{label}: {value}. ")
        lines.append("अगर सब सही है तो YES भेजें।")
    else:
        lines = ["Here is your form summary. "]
        for field, value in form_data.items():
            if isinstance(value, dict):
                continue
            label = field.replace("_", " ").title()
            if value:
                lines.append(f"{label}: {value}. ")
        lines.append("If everything is correct, reply YES.")

    text = " ".join(lines)
    return await text_to_speech(text, language)


def _clean_for_speech(text: str) -> str:
    """Remove emojis, markdown, and special chars for cleaner TTS."""
    import re
    # Remove emojis
    text = re.sub(
        r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF'
        r'\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF'
        r'\U00002702-\U000027B0\U0001F900-\U0001F9FF'
        r'\U00002600-\U000026FF\U00002B50-\U00002B55'
        r'\U0000200D\U0000FE0F]+', '', text
    )
    # Remove markdown (bold, italic, links)
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'_+', ' ', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove bullet points
    text = re.sub(r'^[\s]*[•\-→👉✅❌🟢🟡🔴📋📊🔐🌐📝📍]\s*', '', text, flags=re.MULTILINE)
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _field_label_hi(field: str) -> str:
    """Get Hindi label for a field name."""
    labels = {
        "applicant_name": "आवेदक का नाम",
        "aadhaar_number": "आधार नंबर",
        "date_of_birth": "जन्म तिथि",
        "gender": "लिंग",
        "family_head_name": "परिवार के मुखिया",
        "family_members": "परिवार के सदस्य",
        "annual_income": "वार्षिक आय",
        "category": "श्रेणी",
        "mobile_number": "मोबाइल नंबर",
        "pension_type": "पेंशन प्रकार",
        "full_name": "पूरा नाम",
        "father_name": "पिता का नाम",
        "document_type": "दस्तावेज़ प्रकार",
    }
    return labels.get(field, "")


async def cleanup_old_audio(max_age_hours: int = 1):
    """Remove voice files older than max_age_hours."""
    import time
    now = time.time()
    max_age = max_age_hours * 3600

    if not os.path.exists(VOICE_DIR):
        return

    for f in os.listdir(VOICE_DIR):
        filepath = os.path.join(VOICE_DIR, f)
        if os.path.isfile(filepath):
            age = now - os.path.getmtime(filepath)
            if age > max_age:
                try:
                    os.remove(filepath)
                except OSError:
                    pass
