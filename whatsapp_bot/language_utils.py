"""
============================================
language_utils.py -- Language Detection & Translation
============================================
Detects 10+ Indian languages from text using Unicode script ranges
and language-specific romanized keyword sets.
Supports dynamic translation via Groq (primary) or NVIDIA NIM.

Language codes returned:
  hi  -- Hindi / Hinglish (Devanagari)
  mr  -- Marathi          (Devanagari -- detected by keywords)
  ta  -- Tamil            (Tamil script U+0B80-U+0BFF)
  te  -- Telugu           (Telugu script U+0C00-U+0C7F)
  bn  -- Bengali          (Bengali script U+0980-U+09FF)
  gu  -- Gujarati         (Gujarati script U+0A80-U+0AFF)
  kn  -- Kannada          (Kannada script U+0C80-U+0CFF)
  ml  -- Malayalam        (Malayalam script U+0D00-U+0D7F)
  pa  -- Punjabi/Gurmukhi (Gurmukhi script U+0A00-U+0A7F)
  ur  -- Urdu             (Arabic-Perso script U+0600-U+06FF)
  en  -- English (default fallback)
"""

import re

# -----------------------------------------------------------
# Unicode Script Ranges → Language Code
# -----------------------------------------------------------
SCRIPT_RANGES = [
    (r'[\u0B80-\u0BFF]', 'ta'),   # Tamil
    (r'[\u0C00-\u0C7F]', 'te'),   # Telugu
    (r'[\u0980-\u09FF]', 'bn'),   # Bengali / Assamese
    (r'[\u0A80-\u0AFF]', 'gu'),   # Gujarati
    (r'[\u0C80-\u0CFF]', 'kn'),   # Kannada
    (r'[\u0D00-\u0D7F]', 'ml'),   # Malayalam
    (r'[\u0A00-\u0A7F]', 'pa'),   # Gurmukhi (Punjabi)
    (r'[\u0600-\u06FF]', 'ur'),   # Arabic/Urdu/Perso
    (r'[\u0900-\u097F]', 'hi'),   # Devanagari (Hindi/Marathi/others)
]

# -----------------------------------------------------------
# Romanized keyword sets per language
# -----------------------------------------------------------
# Hindi / Hinglish
HINDI_KEYWORDS = {
    "namaste", "namaskar", "haan", "nahi", "ji", "kya", "kaise", "kab",
    "mujhe", "chahiye", "batao", "karein", "karo", "madad", "sahayata",
    "yojana", "avedan", "sthiti", "dastavez", "kisan", "sarkar",
    "gaon", "gaanv", "zila", "rajya", "zameen", "bhoomi", "paisa",
    "naam", "pata", "khata", "aay", "shukriya", "dhanyavaad",
    "mera", "meri", "aapka", "aapki", "form", "bharein", "loan",
    "ration", "pension", "bhai", "didi", "chacha", "chachu",
    "rupaye", "pani", "bijli", "khana", "ghar", "makaan",
}

# Marathi romanized keywords (shares Devanagari with Hindi — detected by keywords)
MARATHI_KEYWORDS = {
    "namaskar", "aahe", "ahe", "nahi", "kay", "kasa", "kiti",
    "mala", "pahije", "sangaa", "kara", "maddat", "yojana",
    "shetkari", "sarkar", "gaon", "jilha", "rajya", "zamin",
    "rup", "nav", "patta", "khate", "dhanyavad", "bhet",
    "amchi", "tumchi", "pora", "didi", "aaji", "aajoba",
}

# Tamil romanized keywords
TAMIL_KEYWORDS = {
    "vanakkam", "enna", "eppadi", "engee", "enakku", "vendum",
    "sollunga", "pannunga", "udavi", "thittam", "manuthar",
    "vivasayi", "arasaangam", "oor", "maavattam", "naadu",
    "mann", "neer", "saappadu", "veedu", "idam",
}

# Telugu romanized keywords
TELUGU_KEYWORDS = {
    "namaskaram", "ela", "ela unnaru", "emiti", "naku", "kavali",
    "cheppandi", "cheyyandi", "sahayam", "pata", "rythu",
    "prajalu", "graama", "zilla", "rashtram", "bhumi",
    "niru", "tindi", "illu", "stalam",
}

# Bengali romanized keywords
BENGALI_KEYWORDS = {
    "namaskar", "kemon", "achen", "kothay", "amar", "chai",
    "bolun", "korun", "sahajya", "prakalpa", "chasi",
    "sarkar", "gram", "jela", "rajya", "jomi",
    "jal", "khabar", "bari", "jaiga",
}

# Kannada romanized keywords
KANNADA_KEYWORDS = {
    "namaskara", "hege", "idiya", "yellide", "nanage", "beku",
    "heli", "madi", "sahaya", "yojane", "raita",
    "sarkara", "hooru", "jille", "rajya", "bhumi",
    "niru", "oota", "mane", "jagah",
}

# -----------------------------------------------------------
# Human-readable language names
# -----------------------------------------------------------
LANG_NAMES = {
    "hi": "Hindi",
    "mr": "Marathi",
    "ta": "Tamil",
    "te": "Telugu",
    "bn": "Bengali",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "ur": "Urdu",
    "en": "English",
}

# Romanized keyword → language mapping (checked after script detection)
ROMANIZED_KEYWORD_MAP = [
    ("ta", TAMIL_KEYWORDS),
    ("te", TELUGU_KEYWORDS),
    ("bn", BENGALI_KEYWORDS),
    ("kn", KANNADA_KEYWORDS),
    ("mr", MARATHI_KEYWORDS),
    ("hi", HINDI_KEYWORDS),
]


def detect_language(text: str) -> str:
    """
    Detect the language of ``text``.

    Priority order:
      1. Unicode script ranges  — most reliable for native-script input
      2. Romanized keyword sets — for Romanized Indian text ("vanakkam", "namaste")
      3. Default: "en"

    Returns one of: hi, mr, ta, te, bn, gu, kn, ml, pa, ur, en
    """
    # 1. Script-level detection (fast, reliable)
    for pattern, lang_code in SCRIPT_RANGES:
        if re.search(pattern, text):
            # Devanagari can be Hindi OR Marathi — disambiguate by keywords
            if lang_code == "hi":
                words = set(text.lower().split())
                if len(words.intersection(MARATHI_KEYWORDS)) >= 2:
                    return "mr"
            return lang_code

    # 2. Romanized keyword detection
    words = set(text.lower().split())
    scores = {}
    for lang_code, kw_set in ROMANIZED_KEYWORD_MAP:
        matches = len(words.intersection(kw_set))
        if matches > 0:
            scores[lang_code] = matches

    if scores:
        return max(scores, key=scores.get)

    return "en"


def get_language_name(lang_code: str) -> str:
    """Return the human-readable name for a language code."""
    return LANG_NAMES.get(lang_code, "English")


def translate_to_english(text: str, source_lang: str = None) -> str:
    """
    Translate any Indian-language text to English for LLM processing.
    Sync wrapper -- runs async translation in a new event loop.
    """
    if source_lang is None:
        source_lang = detect_language(text)
    if source_lang == "en":
        return text

    try:
        import asyncio
        from backend.llm_client import chat_translation
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(chat_translation(text, source_lang, "en"))
        loop.close()
        return result or text
    except Exception as e:
        print(f"[LangUtils] translate_to_english failed: {e}")
        return _simple_translate_to_english(text)


async def translate_to_language(text: str, target_lang: str) -> str:
    """
    Translate text to target_lang using Groq 70B (primary).
    Falls back to original text on failure.

    Args:
        text: Source text (English or Hindi template message)
        target_lang: BCP-47 language code (e.g. "ta", "te", "bn")

    Returns:
        Translated message in the target language, or original on failure.
    """
    if target_lang in ("en", ""):
        return text

    try:
        from backend.llm_client import chat_translation
        source_lang = "en" if not any(
            re.search(p, text) for p, _ in SCRIPT_RANGES
        ) else detect_language(text)
        result = await chat_translation(text, source_lang, target_lang)
        return result or text
    except Exception as e:
        print(f"[LangUtils] Translation to {target_lang} failed: {e}")
        return text


def translate_to_hindi(text: str) -> str:
    """Translate English text to Hindi (sync)."""
    try:
        import asyncio
        from backend.llm_client import chat_translation
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(chat_translation(text, "en", "hi"))
        loop.close()
        return result or text
    except Exception as e:
        print(f"[LangUtils] translate_to_hindi failed: {e}")
        return text


def _simple_translate_to_english(text: str) -> str:
    """Fallback translation using simple keyword replacement."""
    translations = {
        "नमस्ते": "hello", "मदद": "help", "आवेदन": "application",
        "फ़ॉर्म": "form", "भरना": "fill", "पैन": "PAN",
        "कार्ड": "card", "किसान": "farmer", "योजना": "scheme",
        "स्थिति": "status", "जाँच": "check", "हाँ": "yes",
        "नहीं": "no", "धन्यवाद": "thank you",
    }
    result = text
    for hindi, english in translations.items():
        result = result.replace(hindi, english)
    return result


def get_response_language(user_id: str, detected_lang: str) -> str:
    """
    Determine what language to respond in.
    Always respond in the same language the user used.
    """
    return detected_lang
