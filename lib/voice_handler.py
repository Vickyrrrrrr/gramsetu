"""
============================================================
voice_handler.py — Voice Processing Pipeline (v4)
============================================================
Model Assignments:
  STT (Speech-to-Text):
    1. Sarvam Saaras v3 (PRIMARY — best for Indian languages)
    2. Groq Whisper v3    (FALLBACK — 99 languages, free)
    3. NVIDIA Parakeet    (BACKUP — free tier)

  TTS (Text-to-Speech):
    1. Sarvam Bulbul v3   (PRIMARY — 11 Indian languages)
    2. edge-tts           (FALLBACK — free, offline)
    3. Silent             (LAST RESORT — empty bytes)

NO mock/demo data. Real API calls only.
"""
import os
import asyncio
import tempfile
import base64
import httpx
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")

# ── Language code mapping ──────────────────────────────────
SARVAM_LANG_MAP = {
    "hi": "hi-IN", "en": "en-IN", "mr": "mr-IN", "ta": "ta-IN",
    "te": "te-IN", "bn": "bn-IN", "gu": "gu-IN", "kn": "kn-IN",
    "ml": "ml-IN", "pa": "pa-IN", "ur": "ur-IN",
}

GROQ_WHISPER_LANG = {
    "hi": "hi", "en": "en", "mr": "mr", "ta": "ta", "te": "te",
    "bn": "bn", "gu": "gu", "kn": "kn", "ml": "ml", "pa": "pa", "ur": "ur",
}

EDGE_TTS_VOICES = {
    "hi": "hi-IN-SwaraNeural",
    "en": "en-IN-NeerjaNeural",
    "mr": "mr-IN-AarohiNeural",
    "ta": "ta-IN-PallaviNeural",
    "te": "te-IN-ShrutiNeural",
    "bn": "bn-IN-TanishaaNeural",
    "gu": "gu-IN-DhwaniNeural",
    "kn": "kn-IN-SapnaNeural",
    "ml": "ml-IN-SobhanaNeural",
    "pa": "pa-IN-OjasNeural",
    "ur": "ur-IN-GulNeural",
}


# ════════════════════════════════════════════════════════════
# STT (Speech-to-Text)
# ════════════════════════════════════════════════════════════

def transcribe_audio(audio_path: str, language: str = "hi") -> str:
    """Synchronous wrapper — use from non-async contexts."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_transcribe(audio_path, language))
    except Exception as e:
        print(f"[Voice] STT pipeline failed: {e}")
    return ""


async def _transcribe(audio_path: str, language: str) -> str:
    """Cascade: Sarvam → Groq → empty string."""
    text = await _sarvam_stt(audio_path, language)
    if text:
        print(f"[Voice] Sarvam STT → {text[:60]}...")
        return text
    text = await _groq_whisper_stt(audio_path, language)
    if text:
        print(f"[Voice] Groq Whisper → {text[:60]}...")
        return text
    return ""


async def _sarvam_stt(audio_path: str, language: str) -> str:
    """Sarvam Saaras v3 — best for Indian languages."""
    if not SARVAM_API_KEY or SARVAM_API_KEY in ("", "your_sarvam_key_here"):
        return ""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(audio_path, "rb") as f:
                response = await client.post(
                    "https://api.sarvam.ai/speech-to-text",
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
            print(f"[Voice] Sarvam STT HTTP {response.status_code}")
    except Exception as e:
        print(f"[Voice] Sarvam STT error: {type(e).__name__}")
    return ""


async def _groq_whisper_stt(audio_path: str, language: str) -> str:
    """Groq Whisper v3 — 99 languages, excellent accuracy."""
    if not GROQ_API_KEY or GROQ_API_KEY in ("", "gsk_placeholder", "your_groq_key_here"):
        return ""
    wlang = GROQ_WHISPER_LANG.get(language[:2], language[:2])
    try:
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                files={"file": (os.path.basename(audio_path), audio_bytes, "audio/wav")},
                data={
                    "model": "whisper-large-v3",
                    "language": wlang,
                    "response_format": "text",
                    "temperature": "0",
                },
            )
        if response.status_code == 200:
            return response.text.strip()
        print(f"[Voice] Groq Whisper HTTP {response.status_code}")
    except Exception as e:
        print(f"[Voice] Groq Whisper error: {type(e).__name__}")
    return ""


async def _nvidia_parakeet_stt(audio_path: str, language: str) -> str:
    """NVIDIA Parakeet — DEPRECATED (endpoint removed by NVIDIA)."""
    return ""


# ════════════════════════════════════════════════════════════
# TTS (Text-to-Speech)
# ════════════════════════════════════════════════════════════

async def generate_voice(text: str, language: str = "hi") -> Optional[bytes]:
    """
    Generate audio from text.
    Cascade: Sarvam Bulbul (PRIMARY) → edge-tts (FALLBACK) → None.
    """
    if not text or not text.strip():
        return None

    lang = language[:2] if language else "hi"

    # 1. Sarvam Bulbul v3 (PRIMARY — best Indian voices)
    audio = await _sarvam_tts(text, lang)
    if audio:
        print(f"[Voice] Sarvam TTS → {len(audio)} bytes")
        return audio

    # 2. edge-tts (FALLBACK — free, offline)
    audio = await _edge_tts(text, lang)
    if audio:
        print(f"[Voice] edge-tts → {len(audio)} bytes")
        return audio

    print("[Voice] TTS: all providers failed")
    return None


async def _sarvam_tts(text: str, language: str) -> Optional[bytes]:
    """Sarvam Bulbul v3 — 11 Indian languages, natural voices."""
    if not SARVAM_API_KEY or SARVAM_API_KEY in ("", "your_sarvam_key_here"):
        return None

    sarvam_lang = SARVAM_LANG_MAP.get(language, "hi-IN")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={
                    "api-subscription-key": SARVAM_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model": "bulbul:v3",
                    "language_code": sarvam_lang,
                    "speaker": "priya",
                    "enable_preprocessing": True,
                },
            )
            if response.status_code == 200:
                data = response.json()
                audio_b64 = data.get("audio_content", "") or (
                    data.get("audios", [""])[0]
                )
                if audio_b64:
                    return base64.b64decode(audio_b64)
            else:
                print(f"[Voice] Sarvam TTS HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"[Voice] Sarvam TTS error: {type(e).__name__}")
    return None


async def _edge_tts(text: str, language: str) -> Optional[bytes]:
    """Microsoft edge-tts — free, no API key needed, 11 Indian voices."""
    try:
        from edge_tts import Communicate

        voice = EDGE_TTS_VOICES.get(language, "hi-IN-SwaraNeural")
        communicate = Communicate(text, voice)

        # Collect audio chunks
        chunks = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])

        if chunks:
            return b"".join(chunks)
    except ImportError:
        print("[Voice] edge-tts not installed. Run: pip install edge-tts")
    except Exception as e:
        print(f"[Voice] edge-tts error: {type(e).__name__}: {e}")
    return None
