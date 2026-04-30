"""
============================================================
llm_client.py — Multi-Provider LLM Client (Production v4)
============================================================
Provider Strategy (CORRECT MODEL FOR EACH TASK):

  TEXT / CHAT / INTENT / FORM-FILL
      → Sarvam (PRIMARY — purpose-built for Indian languages)
      → Groq (FALLBACK — llama-3.3-70b, fast & free)
      → NVIDIA NIM (BACKUP — meta/llama-3.1-8b-instruct)

  VISION (form screenshots, portal page analysis)
      → NVIDIA NIM (PRIMARY — llama-3.2-11b-vision-instruct)
      → Groq Vision (FALLBACK — llama-3.2-11b-vision-preview)

  ASR / STT (voice-to-text)
      → Sarvam Saaras v3 (PRIMARY — best for Hindi + 10 languages)
      → Groq Whisper v3 (FALLBACK — 99 languages)
      → NVIDIA Parakeet (BACKUP)

  REALTIME STT (live microphone)
      → Sarvam WebSocket saaras:v3 (PRIMARY — sub-500ms latency)

  TTS (text-to-speech)
      → Sarvam Bulbul v3 (PRIMARY — 11 Indian voices)
      → edge-tts (FALLBACK — Microsoft neural voices, free)

  TRANSLATION (Hindi ↔ regional languages)
      → Sarvam Translate (PRIMARY — specialized Indic API)
      → Groq (FALLBACK — llama-3.3-70b)

Sarvam Models:
  CHAT        sarvam-m / sarvam-30b / sarvam-105b
  STT         saaras:v3
  TTS         bulbul:v3
"""

import os
import re
import json
from typing import Optional
import asyncio
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
    """Check if Sarvam API key is configured and valid."""
    return bool(SARVAM_API_KEY and SARVAM_API_KEY not in ("", "your_sarvam_key_here"))

async def _sarvam_call(messages: list, temperature: float, max_tokens: int) -> str:
    if not _sarvam_ok():
        return ""
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    f"{SARVAM_URL}/v1/chat/completions",
                    headers={
                        "api-subscription-key": SARVAM_API_KEY,
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": SARVAM_CHAT_MODEL,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
            if response.status_code == 429:
                await asyncio.sleep((attempt + 1) * 2)
                continue
            if response.status_code != 200:
                print(f"[LLM] Sarvam {response.status_code}: {response.text[:200]}")
                return ""
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt == 2:
                print(f"[LLM] Sarvam error: {type(e).__name__}")
                return ""
            await asyncio.sleep(1)
    return ""

# -- Sarvam Models (Indian languages optimized) ------------
SARVAM_CHAT_MODEL = os.getenv("SARVAM_CHAT_MODEL", "sarvam-30b")
# sarvam-m (fast, think-tags), sarvam-30b (balanced, clean), sarvam-105b (best)


# -- Groq Models ----------------------------------------------

GROQ_MODEL_FAST   = os.getenv("GROQ_MODEL_FAST",   "llama-3.1-8b-instant")
GROQ_MODEL_MAIN   = os.getenv("GROQ_MODEL_MAIN",   "llama-3.3-70b-versatile")
GROQ_MODEL_VISION = os.getenv("GROQ_MODEL_VISION", "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_WHISPER      = "whisper-large-v3"

# -- NVIDIA NIM Models (free tier) ----------------------------
NIM_MODEL_VISION  = os.getenv("NIM_MODEL_VISION",  "meta/llama-3.2-11b-vision-instruct")
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
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    base_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
            if response.status_code == 429:
                wait = (attempt + 1) * 2
                print(f"[LLM] Rate limit (429). Retrying in {wait}s...")
                await asyncio.sleep(wait)
                continue
            if response.status_code != 200:
                print(f"[LLM] Error {response.status_code} at {base_url} (Model: {model}): {response.text}")
                return ""
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt == 2:
                print(f"[LLM] Final attempt failed: {e}")
                return ""
            await asyncio.sleep(1)
    return ""


async def _groq_call(model: str, messages: list, temperature: float, max_tokens: int) -> str:
    if not _groq_ok():
        return ""
    return await _openai_compat(f"{GROQ_URL}/chat/completions", GROQ_API_KEY, model, messages, temperature, max_tokens)


async def _nim_call(model: str, messages: list, temperature: float, max_tokens: int) -> str:
    if not _nim_ok():
        return ""
    return await _openai_compat(f"{NVIDIA_URL}/chat/completions", NVIDIA_API_KEY, model, messages, temperature, max_tokens)


# -- Public LLM Functions -------------------------------------

async def chat_intent(messages: list, temperature: float = 0.1, max_tokens: int = 256) -> str:
    """Fast intent classification — Sarvam (PRIMARY, India-optimized) → Groq → NVIDIA."""
    result = await _sarvam_call(messages, temperature, max_tokens)
    if result:
        return result
    result = await _groq_call(GROQ_MODEL_FAST, messages, temperature, max_tokens)
    if result:
        return result
    return await _nim_call(NIM_MODEL_GENERAL, messages, temperature, max_tokens)


async def chat_conversational(messages: list, temperature: float = 0.6, max_tokens: int = 768) -> str:
    """Warm multilingual conversation — Sarvam (PRIMARY, best for Hindi/Indic) → Groq → NVIDIA."""
    result = await _sarvam_call(messages, temperature, max_tokens)
    if result:
        return result
    result = await _groq_call(GROQ_MODEL_MAIN, messages, temperature, max_tokens)
    if result:
        return result
    return await _nim_call(NIM_MODEL_GENERAL, messages, temperature, max_tokens)


async def chat_extraction(messages: list, temperature: float = 0.1, max_tokens: int = 512) -> str:
    """Structured data extraction — Sarvam (PRIMARY, understands Hindi forms) → Groq → NVIDIA."""
    result = await _sarvam_call(messages, temperature, max_tokens)
    if result:
        return result
    result = await _groq_call(GROQ_MODEL_MAIN, messages, temperature, max_tokens)
    if result:
        return result
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
    messages: list, temperature: float = 0.3, max_tokens: int = 1024,
    use_web_search: bool = False,
) -> str:
    """General-purpose chat — Sarvam (PRIMARY, India-optimized) → Groq → NVIDIA."""
    result = await _sarvam_call(messages, temperature, max_tokens)
    if result:
        return result
    result = await _groq_call(GROQ_MODEL_MAIN, messages, temperature, max_tokens)
    if result:
        return result
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
    result = await _groq_call(GROQ_MODEL_FAST, messages, 0.0, 32)
    if result:
        return result.strip().lower()
    result = await _nim_call(NIM_MODEL_GENERAL, messages, 0.0, 32)
    if result:
        return result.strip().lower()
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
    Transcribe audio using Sarvam Saaras (PRIMARY — Best for Indian languages).
    Uses saaras:v3 — optimized for Hindi, Tamil, Telugu, Bengali + 8 more languages.
    """
    if not _sarvam_ok():
        return ""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(audio_path, "rb") as f:
                response = await client.post(
                    f"{SARVAM_URL}/speech-to-text",
                    headers={
                        "api-subscription-key": SARVAM_API_KEY,
                        "Accept": "application/json",
                    },
                    files={"file": (os.path.basename(audio_path), f, "audio/wav")},
                    data={
                        "model": "saaras:v3",
                        "language_code": language,
                        "with_timestamps": "false",
                    },
                )
            if response.status_code == 200:
                data = response.json()
                return data.get("transcript", "") or data.get("text", "")
            print(f"[ASR] Sarvam HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"[ASR] Sarvam failed: {type(e).__name__}: {e}")
    return ""


async def transcribe_audio_groq(audio_path: str, language: str = "hi") -> str:
    """
    Transcribe audio using Groq Whisper (FALLBACK — whisper-large-v3).
    Best free ASR backup — supports Hindi, Tamil, Telugu + 90+ languages.
    """
    if not _groq_ok():
        return ""
    whisper_lang_map = {
        "hi": "hi", "en": "en", "mr": "mr", "ta": "ta", "te": "te",
        "bn": "bn", "gu": "gu", "kn": "kn", "ml": "ml", "pa": "pa", "ur": "ur",
    }
    whisper_lang = whisper_lang_map.get(language[:2], language[:2])
    try:
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{GROQ_URL}/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={"file": (os.path.basename(audio_path), audio_bytes, "audio/wav")},
                data={
                    "model": GROQ_WHISPER,
                    "language": whisper_lang,
                    "response_format": "text",
                    "temperature": "0",
                },
            )
        if response.status_code == 200:
            return response.text.strip()
        print(f"[ASR] Groq Whisper HTTP {response.status_code}: {response.text[:200]}")
        return ""
    except Exception as e:
        print(f"[ASR] Groq Whisper failed: {type(e).__name__}: {e}")
        return ""


async def transcribe_audio_nvidia(audio_path: str, language: str = "hi") -> str:
    """NVIDIA Parakeet ASR — DEPRECATED (endpoint no longer available). Returns empty."""
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
