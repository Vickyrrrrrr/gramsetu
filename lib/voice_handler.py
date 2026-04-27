import os
import asyncio
import tempfile
import httpx
from dotenv import load_dotenv
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")

async def _sarvam_stt(audio_path: str, language: str) -> str:
    if not SARVAM_API_KEY or SARVAM_API_KEY in ("", "your_sarvam_key_here"):
        return ""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            with open(audio_path, "rb") as f:
                response = await client.post(
                    "https://api.sarvam.ai/speech-to-text",
                    headers={"api-subscription-key": SARVAM_API_KEY},
                    files={"file": f},
                    data={"model": "saaras:v3"},
                )
            if response.status_code == 200:
                return response.json().get("transcript", "")
    except Exception as e:
        print(f"[Voice] Sarvam STT failed: {e}")
    return ""

async def generate_voice(text: str, language: str = "hi-IN") -> bytes:
    """Generate audio from text using Sarvam Bulbul."""
    if not SARVAM_API_KEY or SARVAM_API_KEY in ("", "your_sarvam_key_here"):
        return b""
    
    # Map short codes to Sarvam language codes
    lang_map = {
        "hi": "hi-IN", "en": "en-IN", "mr": "mr-IN", "ta": "ta-IN",
        "te": "te-IN", "bn": "bn-IN", "gu": "gu-IN", "kn": "kn-IN"
    }
    sarvam_lang = lang_map.get(language[:2], "hi-IN")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.sarvam.ai/text-to-speech",
                headers={"api-subscription-key": SARVAM_API_KEY},
                json={
                    "text": text,
                    "model": "bulbul:v3",
                    "language_code": sarvam_lang,
                    "speaker": "priya",
                    "enable_preprocessing": True
                }
            )
            if response.status_code == 200:
                import base64
                audio_b64 = response.json().get("audio_content", "")
                return base64.b64decode(audio_b64)
            else:
                print(f"[Voice] Sarvam TTS failed with {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[Voice] Sarvam TTS exception: {e}")
    return b""

def transcribe_audio(audio_path: str, language: str = "hi") -> str:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_transcribe(audio_path, language))
    except Exception as e:
        print(f"[Voice] ASR failed: {e}")
    return _mock(language)

async def _transcribe(audio_path: str, language: str) -> str:
    # 1. Try Sarvam STT (India-native, very accurate for Hindi/Indic)
    text = await _sarvam_stt(audio_path, language)
    if text:
        return text

    # 2. Try Groq Whisper (best global open-source ASR)
    if GROQ_API_KEY and GROQ_API_KEY not in ("", "gsk_placeholder", "your_groq_key_here"):
        try:
            whisper_lang_map = {"hi": "hi", "en": "en", "mr": "mr", "ta": "ta", "te": "te", "bn": "bn", "gu": "gu", "kn": "kn", "ml": "ml", "pa": "pa", "ur": "ur"}
            wlang = whisper_lang_map.get(language, "hi")
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    files={"file": (os.path.basename(audio_path), audio_bytes, "audio/ogg")},
                    data={"model": "whisper-large-v3", "language": wlang, "response_format": "text"},
                )
            if response.status_code == 200:
                return response.text.strip()
        except Exception as e:
            print(f"[Voice] Groq Whisper failed: {e}")
    return _mock(language)

def _mock(language: str) -> str:
    return {"hi": "नमस्ते, मुझे राशन कार्ड के लिए आवेदन करना है", "en": "Hello, I want to apply for a ration card"}.get(language, "नमस्ते")
