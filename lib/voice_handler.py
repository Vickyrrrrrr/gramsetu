import os
import asyncio
import tempfile
import httpx
from dotenv import load_dotenv
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

def transcribe_audio(audio_path: str, language: str = "hi") -> str:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_transcribe(audio_path, language))
    except Exception as e:
        print(f"[Voice] ASR failed: {e}")
    return _mock(language)

async def _transcribe(audio_path: str, language: str) -> str:
    # Try Groq Whisper (best for Indian languages)
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
