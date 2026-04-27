import re

SCRIPT_RANGES = [
    (r'[\u0B80-\u0BFF]', 'ta'), (r'[\u0C00-\u0C7F]', 'te'), (r'[\u0980-\u09FF]', 'bn'),
    (r'[\u0A80-\u0AFF]', 'gu'), (r'[\u0C80-\u0CFF]', 'kn'), (r'[\u0D00-\u0D7F]', 'ml'),
    (r'[\u0A00-\u0A7F]', 'pa'), (r'[\u0600-\u06FF]', 'ur'), (r'[\u0900-\u097F]', 'hi'),
]

HINDI_KEYWORDS = {"namaste", "namaskar", "haan", "nahi", "ji", "kya", "mujhe", "chahiye", "yojana", "pension", "ration", "kisan", "pension", "bhai", "didi"}
MARATHI_KEYWORDS = {"namaskar", "aahe", "nahi", "mala", "pahije", "yojana"}
TAMIL_KEYWORDS = {"vanakkam", "enna", "enakku", "vendum", "pannunga"}
TELUGU_KEYWORDS = {"namaskaram", "ela", "naku", "kavali", "cheppandi"}
BENGALI_KEYWORDS = {"namaskar", "kemon", "achen", "chai", "bolun"}
KANNADA_KEYWORDS = {"namaskara", "hege", "idiya", "nanage", "beku"}

ROMANIZED_KEYWORD_MAP = [("ta", TAMIL_KEYWORDS), ("te", TELUGU_KEYWORDS), ("bn", BENGALI_KEYWORDS), ("kn", KANNADA_KEYWORDS), ("mr", MARATHI_KEYWORDS), ("hi", HINDI_KEYWORDS)]

def detect_language(text: str) -> str:
    for pattern, lang_code in SCRIPT_RANGES:
        if re.search(pattern, text):
            if lang_code == "hi":
                words = set(text.lower().split())
                if len(words.intersection(MARATHI_KEYWORDS)) >= 2:
                    return "mr"
            return lang_code
    words = set(text.lower().split())
    scores = {lc: len(words.intersection(kw)) for lc, kw in ROMANIZED_KEYWORD_MAP if words.intersection(kw)}
    return max(scores, key=scores.get) if scores else "en"

async def translate_to_language(text: str, target_lang: str) -> str:
    if target_lang in ("en", ""):
        return text
    try:
        from backend.llm_client import chat_translation
        result = await chat_translation(text, "en", target_lang)
        return result or text
    except Exception:
        return text
