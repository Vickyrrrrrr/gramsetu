"""
voice_tts.py - Text-to-Speech facade for GramSetu.
Provides TTS functionality using Sarvam API (primary) with fallback options.
"""

import os
import httpx
from typing import Optional

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
SARVAM_URL = "https://api.sarvam.ai"

def _sarvam_ok() -> bool:
    return bool(SARVAM_API_KEY and SARVAM_API_KEY not in ("", "your_sarvam_key_here"))

async def text_to_speech(text: str, language_code: str = "hi-IN") -> Optional[bytes]:
    """
    Convert text to speech using Sarvam TTS API.
    Supports Indian languages: hi-IN, bn-IN, ta-IN, te-IN, mr-IN, etc.
    
    Returns audio bytes (mp3) or None if failed.
    """
    if not _sarvam_ok():
        return None
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{SARVAM_URL}/text-to-speech",
                headers={"Authorization": f"Bearer {SARVAM_API_KEY}"},
                json={
                    "inputs": [text],
                    "target_language_code": language_code,
                    "speaker": "female",
                    "pitch": 0,
                    "pace": 1.0,
                    "loudness": 1.0,
                    "enable_preprocessing": True,
                    "model": "bulbul:v1"
                }
            )
            if response.status_code == 200:
                return response.content
    except Exception as e:
        print(f"[TTS] Sarvam failed: {e}")
    return None

async def generate_speech(text: str, language: str = "hi") -> Optional[bytes]:
    """Wrapper function for generating speech from text."""
    lang_map = {
        "hi": "hi-IN", "en": "en-IN", "bn": "bn-IN", "ta": "ta-IN",
        "te": "te-IN", "mr": "mr-IN", "gu": "gu-IN", "kn": "kn-IN",
        "ml": "ml-IN", "pa": "pa-IN", "ur": "ur-IN"
    }
    lang_code = lang_map.get(language, "hi-IN")
    return await text_to_speech(text, lang_code)
