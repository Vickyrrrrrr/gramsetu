"""
============================================================
llm_client.py — Multi-Provider LLM Client (Production)
============================================================
Provider Strategy:
  TEXT / CHAT / INTENT / TRANSLATION
      -> Groq (primary -- generous free tier, very fast ~100-300ms)
      -> NVIDIA NIM (fallback)

  VISION (form screenshots, PDF pages)
      -> NVIDIA llama-3.2-11b-vision-instruct (free tier)
      -> Groq llama-3.2-11b-vision-preview (fallback)

  ASR  (voice messages)
      -> Groq whisper-large-v3 (best accuracy for Indian languages)
      -> NVIDIA parakeet-ctc-1.1b-asr (fallback)

Groq Models:
  INTENT      llama-3.1-8b-instant       ~50ms fast JSON
  CHAT/TRANS  llama-3.3-70b-versatile    best free multilingual 70B
  ASR         whisper-large-v3           99 languages incl. Hindi

NVIDIA NIM Free Models:
  VISION      nvidia/llama-3.2-11b-vision-instruct
  ASR-BACKUP  nvidia/parakeet-ctc-1.1b-asr
  TEXT-BACKUP meta/llama-3.1-8b-instruct
"""

import os
import re
import json
from typing import Optional
import httpx
from dotenv import load_dotenv

load_dotenv()

# -- API Keys -------------------------------------------------
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")

# -- Base URLs ------------------------------------------------
GROQ_URL   = "https://api.groq.com/openai/v1"
NVIDIA_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
SARVAM_URL = "https://api.sarvam.ai"

def _sarvam_ok() -> bool:
    return bool(SARVAM_API_KEY and SARVAM_API_KEY not in ("", "your_sarvam_key_here"))

async def _sarvam_call(messages: list, temperature: float, max_tokens: int) -> str:
    if not _sarvam_ok():
        return ""
    # Sarvam uses OpenAI-compatible chat endpoint
    return await _openai_compat(f"{SARVAM_URL}", SARVAM_API_KEY, "sarvam-1", messages, temperature, max_tokens)

# -- Groq Models ----------------------------------------------
GROQ_MODEL_FAST   = os.getenv("GROQ_MODEL_FAST",   "llama-3.1-8b-instant")
GROQ_MODEL_MAIN   = os.getenv("GROQ_MODEL_MAIN",   "llama-3.3-70b-versatile")
GROQ_MODEL_VISION = os.getenv("GROQ_MODEL_VISION", "llama-3.2-11b-vision-preview")
GROQ_WHISPER      = "whisper-large-v3"

# -- NVIDIA NIM Models (free tier) ----------------------------
NIM_MODEL_VISION  = os.getenv("NIM_MODEL_VISION",  "nvidia/llama-3.2-11b-vision-instruct")
NIM_MODEL_GENERAL = os.getenv("NIM_MODEL_GENERAL", "meta/llama-3.1-8b-instruct")

# Legacy aliases kept for external imports
NVIDIA_MODEL             = NIM_MODEL_GENERAL
GROQ_MODEL               = GROQ_MODEL_MAIN
NIM_MODEL_INTENT         = NIM_MODEL_GENERAL
NIM_MODEL_CONVERSATIONAL = NIM_MODEL_GENERAL
NIM_MODEL_EXTRACTION     = NIM_MODEL_GENERAL


def _groq_ok() -> bool:
    return bool(GROQ_API_KEY and GROQ_API_KEY not in ("", "your_groq_key_here", "gsk_placeholder"))


def _nim_ok() -> bool:
    return bool(NVIDIA_API_KEY and NVIDIA_API_KEY not in ("", "nvapi-your-key-here"))


def get_active_provider() -> str:
    if _groq_ok():
        return "groq"
    if _nim_ok():
        return "nvidia"
    return "fallback"


# -- Core HTTP call (OpenAI-compatible) -----------------------
async def _openai_compat(
    base_url: str,
    api_key: str,
    model: str,
    messages: list,
    temperature: float,
    max_tokens: int,
) -> str:
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
            )
            if response.status_code != 200:
                print(f"[LLM] {model} HTTP {response.status_code}: {response.text[:300]}")
                return ""
            content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                print(f"[LLM] {model} returned empty content")
            return content
    except Exception as e:
        print(f"[LLM] {model} failed: {type(e).__name__}: {e}")
    return ""


async def _groq_call(model: str, messages: list, temperature: float, max_tokens: int) -> str:
    if not _groq_ok():
        return ""
    return await _openai_compat(GROQ_URL, GROQ_API_KEY, model, messages, temperature, max_tokens)


async def _nim_call(model: str, messages: list, temperature: float, max_tokens: int) -> str:
    if not _nim_ok():
        return ""
    return await _openai_compat(NVIDIA_URL, NVIDIA_API_KEY, model, messages, temperature, max_tokens)


# -- Public LLM Functions -------------------------------------

async def chat_intent(messages: list, temperature: float = 0.1, max_tokens: int = 256) -> str:
    """Fast intent classification -- Sarvam/Groq llama-3.1-8b-instant."""
    result = await _sarvam_call(messages, temperature, max_tokens)
    if result: return result
    result = await _groq_call(GROQ_MODEL_FAST, messages, temperature, max_tokens)
    if result: return result
    return await _nim_call(NIM_MODEL_GENERAL, messages, temperature, max_tokens)


async def chat_conversational(messages: list, temperature: float = 0.6, max_tokens: int = 768) -> str:
    """Warm multilingual conversation -- Sarvam primary."""
    result = await _sarvam_call(messages, temperature, max_tokens)
    if result: return result
    result = await _groq_call(GROQ_MODEL_MAIN, messages, temperature, max_tokens)
    if result: return result
    return await _nim_call(NIM_MODEL_GENERAL, messages, temperature, max_tokens)


async def chat_extraction(messages: list, temperature: float = 0.1, max_tokens: int = 512) -> str:
    """Structured extraction -- Sarvam/Groq 70B."""
    result = await _sarvam_call(messages, temperature, max_tokens)
    if result: return result
    result = await _groq_call(GROQ_MODEL_MAIN, messages, temperature, max_tokens)
    if result: return result
    return await _nim_call(NIM_MODEL_GENERAL, messages, temperature, max_tokens)


async def chat_translation(text: str, source_lang: str, target_lang: str) -> str:
    """
    Translate text using Sarvam's specialized translation API.
    Supports: hi, en, mr, ta, te, bn, gu, kn, ml, pa, ur
    """
    if source_lang == target_lang:
        return text

    # 1. Try Sarvam specialized translation
    if _sarvam_ok():
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{SARVAM_URL}/translate",
                    headers={"Authorization": f"Bearer {SARVAM_API_KEY}"},
                    json={
                        "input": text,
                        "source_language_code": f"{source_lang}-IN" if source_lang != "en" else "en-IN",
                        "target_language_code": f"{target_lang}-IN" if target_lang != "en" else "en-IN",
                        "speaker_gender": "Female",
                        "mode": "formal"
                    }
                )
                if response.status_code == 200:
                    return response.json().get("translated_text", text)
        except Exception as e:
            print(f"[Translation] Sarvam failed: {e}")

    # 2. Fallback to LLM-based translation (Groq/NVIDIA)
    lang_names = {
        "hi": "Hindi", "en": "English", "mr": "Marathi", "ta": "Tamil",
        "te": "Telugu", "bn": "Bengali", "gu": "Gujarati", "kn": "Kannada",
        "ml": "Malayalam", "pa": "Punjabi", "ur": "Urdu",
    }
    src_name = lang_names.get(source_lang, source_lang)
    tgt_name = lang_names.get(target_lang, target_lang)
    messages = [
        {
            "role": "system",
            "content": (
                f"Translate the following text from {src_name} to {tgt_name}. "
                "Keep all emojis, numbers, government scheme names, and URLs exactly as-is. "
                "Return ONLY the translation -- no explanation, no prefix, no quotes."
            ),
        },
        {"role": "user", "content": text},
    ]
    result = await _groq_call(GROQ_MODEL_MAIN, messages, 0.1, 2000)
    if result:
        return result.strip()
    result = await _nim_call(NIM_MODEL_GENERAL, messages, 0.1, 2000)
    return result.strip() if result else text


async def chat(
    messages: list,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    use_web_search: bool = False,
) -> str:
    """General-purpose chat -- Sarvam primary, then Groq/NVIDIA."""
    result = await _sarvam_call(messages, temperature, max_tokens)
    if result: return result
    result = await _groq_call(GROQ_MODEL_MAIN, messages, temperature, max_tokens)
    if result: return result
    return await _nim_call(NIM_MODEL_GENERAL, messages, temperature, max_tokens)


async def detect_intent(text: str) -> str:
    """
    Detect user intent from a message.
    Returns a short label e.g. 'ration_card', 'pension', 'greeting', 'query', 'complaint'.
    Falls back to keyword matching when no LLM key is configured.
    """
    if not _groq_ok() and not _nim_ok():
        return _intent_keyword_fallback(text)

    messages = [
        {
            "role": "system",
            "content": (
                "You are an intent classifier for a rural Indian government services chatbot. "
                "Classify the user message into exactly ONE intent label from this list: "
                "greeting, ration_card, pension, pm_kisan, health_scheme, identity, "
                "form_fill, query, complaint, eligibility_check, status_check, other. "
                "Reply with ONLY the label — no explanation, no punctuation."
            ),
        },
        {"role": "user", "content": text},
    ]
    result = await _sarvam_call(messages, 0.0, 32)
    if result: return result.strip().lower()
    result = await _groq_call(GROQ_MODEL_FAST, messages, 0.0, 32)
    if result: return result.strip().lower()
    result = await _nim_call(NIM_MODEL_GENERAL, messages, 0.0, 32)
    if result: return result.strip().lower()
    return _intent_keyword_fallback(text)


def _intent_keyword_fallback(text: str) -> str:
    """Keyword-based intent detection when no LLM API key is set."""
    lower = text.lower()
    if any(w in lower for w in ["hello", "hi", "namaste", "namaskar"]):
        return "greeting"
    if any(w in lower for w in ["ration", "rashan", "bpl", "antyodaya"]):
        return "ration_card"
    if any(w in lower for w in ["pension", "old age", "vridha"]):
        return "pension"
    if any(w in lower for w in ["kisan", "farmer", "krishi"]):
        return "pm_kisan"
    if any(w in lower for w in ["pan", "voter", "aadhaar", "aadhar"]):
        return "identity"
    if any(w in lower for w in ["health", "ayushman", "hospital"]):
        return "health_scheme"
    if any(w in lower for w in ["status", "track", "application"]):
        return "status_check"
    if any(w in lower for w in ["eligible", "qualify", "laabh"]):
        return "eligibility_check"
    if any(w in lower for w in ["complaint", "problem", "issue", "shikayat"]):
        return "complaint"
    return "query"


async def chat_vision(
    image_b64: str,
    prompt: str,
    temperature: float = 0.1,
    max_tokens: int = 512,
) -> str:
    """
    Vision model for analyzing form screenshots and PDF pages.
    NVIDIA llama-3.2-11b-vision-instruct (free tier) first,
    then Groq vision fallback.
    """
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            ],
        }
    ]
    if _nim_ok():
        result = await _nim_call(NIM_MODEL_VISION, messages, temperature, max_tokens)
        if result:
            return result
    if _groq_ok():
        result = await _groq_call(GROQ_MODEL_VISION, messages, temperature, max_tokens)
        if result:
            return result
    return ""


async def transcribe_audio_sarvam(audio_path: str, language: str = "hi") -> str:
    """
    Transcribe audio using Sarvam Saaras (Best for Indian languages).
    """
    if not _sarvam_ok():
        return ""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(audio_path, "rb") as f:
                response = await client.post(
                    f"{SARVAM_URL}/speech-to-text-translate",
                    headers={"Authorization": f"Bearer {SARVAM_API_KEY}"},
                    files={"file": f},
                    data={"model": "saaras-v1", "language_code": language},
                )
            if response.status_code == 200:
                return response.json().get("transcript", "")
    except Exception as e:
        print(f"[ASR] Sarvam failed: {e}")
    return ""


async def transcribe_audio_groq(audio_path: str, language: str = "hi") -> str:
    """
    Transcribe audio using Groq Whisper (whisper-large-v3).
    Best free ASR -- supports Hindi, Tamil, Telugu, Bengali, Gujarati,
    Kannada, Malayalam, Punjabi, Urdu, Marathi and 90+ other languages.
    """
    if not _groq_ok():
        return ""
    whisper_lang_map = {
        "hi": "hi", "en": "en", "mr": "mr", "ta": "ta", "te": "te",
        "bn": "bn", "gu": "gu", "kn": "kn", "ml": "ml", "pa": "pa", "ur": "ur",
    }
    whisper_lang = whisper_lang_map.get(language, "hi")
    try:
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{GROQ_URL}/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={"file": (os.path.basename(audio_path), audio_bytes, "audio/ogg")},
                data={"model": GROQ_WHISPER, "language": whisper_lang, "response_format": "text"},
            )
        if response.status_code == 200:
            return response.text.strip()
        print(f"[ASR] Groq Whisper HTTP {response.status_code}: {response.text[:200]}")
        return ""
    except Exception as e:
        print(f"[ASR] Groq Whisper failed: {type(e).__name__}: {e}")
        return ""


async def transcribe_audio_nvidia(audio_path: str, language: str = "hi") -> str:
    """Transcribe audio using NVIDIA parakeet-ctc-1.1b ASR (backup)."""
    if not _nim_ok():
        return ""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(audio_path, "rb") as f:
                response = await client.post(
                    f"{NVIDIA_URL}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
                    files={"file": f},
                    data={"model": "nvidia/parakeet-ctc-1.1b-asr", "language": language},
                )
        if response.status_code == 200:
            return response.json().get("text", "")
        return ""
    except Exception:
        return ""


async def extract_json(response: str) -> Optional[dict]:
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r'\{.*\}', response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _fallback(messages: list) -> str:
    """Keyword-based fallback when no LLM is available."""
    last = messages[-1].get("content", "") if messages else ""
    lower = last.lower()
    if any(w in lower for w in ["ration", "rashan", "bpl"]):
        return '{"intent": "ration_card", "confidence": 0.9}'
    elif any(w in lower for w in ["pension"]):
        return '{"intent": "pension", "confidence": 0.9}'
    elif any(w in lower for w in ["pan", "voter"]):
        return '{"intent": "identity", "confidence": 0.9}'
    elif any(w in lower for w in ["kisan", "farmer"]):
        return '{"intent": "pm_kisan", "confidence": 0.9}'
    elif "scheme" in lower or "eligible" in lower:
        return (
            "Based on your profile, you may be eligible for: "
            "Ration Card (BPL), PM-KISAN, Old Age Pension. "
            "Please provide your age, occupation, and income for accurate results."
        )
    return "I understand your request. Please provide more details so I can help you."
