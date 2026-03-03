"""
============================================
voice_handler.py — Voice Note Processing
============================================
Downloads voice notes from Twilio and transcribes using
NVIDIA NeMo ASR or fallback speech recognition.

For hackathon: Falls back to a mock transcription if ASR
API is unavailable (keeps the demo working).
"""

import os
import tempfile
import asyncio
import httpx
import requests
from dotenv import load_dotenv

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")


async def download_audio_async(media_url: str, twilio_sid: str, twilio_token: str) -> str:
    """
    Async version — download a voice note from Twilio's media URL
    without blocking the event loop.
    """
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                media_url,
                auth=(twilio_sid, twilio_token),
            )
            response.raise_for_status()
            suffix = ".ogg"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(response.content)
                return tmp.name
    except Exception as e:
        print(f"[Voice] ❌ Failed to download audio: {e}")
        return None


def download_audio(media_url: str, twilio_sid: str, twilio_token: str) -> str:
    """
    Sync wrapper kept for legacy callers.
    Prefer download_audio_async inside async contexts.
    """
    try:
        response = requests.get(
            media_url,
            auth=(twilio_sid, twilio_token),
            stream=True,
            timeout=20,
        )
        response.raise_for_status()
        suffix = ".ogg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            for chunk in response.iter_content(chunk_size=8192):
                tmp.write(chunk)
            return tmp.name
    except Exception as e:
        print(f"[Voice] ❌ Failed to download audio: {e}")
        return None


def transcribe_audio(audio_path: str, language: str = "hi") -> str:
    """
    Transcribe audio file to text using NVIDIA NeMo ASR.
    
    Falls back to a mock transcription for hackathon demo
    if the ASR API is not available.
    
    Args:
        audio_path: Path to the audio file
        language: Expected language ("hi" for Hindi, "en" for English)
    
    Returns:
        Transcribed text string
    """
    # Try NVIDIA NeMo ASR
    if NVIDIA_API_KEY and NVIDIA_API_KEY != "nvapi-your-key-here":
        try:
            return _nvidia_asr(audio_path, language)
        except Exception as e:
            print(f"[Voice] ⚠️ NVIDIA ASR failed, using fallback: {e}")
    
    # Fallback: mock transcription for demo
    return _mock_transcription(language)


def _nvidia_asr(audio_path: str, language: str) -> str:
    """
    Call NVIDIA NeMo ASR API for speech-to-text.
    
    Note: This uses the NVIDIA API endpoint for ASR.
    If the specific ASR model isn't available on free tier,
    the fallback will handle it.
    """
    try:
        url = "https://integrate.api.nvidia.com/v1/audio/transcriptions"
        
        with open(audio_path, "rb") as audio_file:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {NVIDIA_API_KEY}",
                },
                files={"file": audio_file},
                data={
                    "model": "nvidia/parakeet-ctc-1.1b-asr",
                    "language": language,
                },
            )
            response.raise_for_status()
            result = response.json()
            return result.get("text", "")
    except Exception as e:
        print(f"[Voice] ❌ NVIDIA ASR API error: {e}")
        raise


def _mock_transcription(language: str) -> str:
    """
    Mock transcription for hackathon demo.
    Returns a realistic sample message as if it was voice input.
    """
    mock_messages = {
        "hi": "नमस्ते, मुझे पैन कार्ड के लिए आवेदन करना है",
        "en": "Hello, I want to apply for PAN card",
    }
    transcription = mock_messages.get(language, mock_messages["hi"])
    print(f"[Voice] 🎤 Mock transcription ({language}): {transcription}")
    return transcription


def cleanup_audio(audio_path: str):
    """Remove temporary audio file after processing."""
    try:
        if audio_path and os.path.exists(audio_path):
            os.unlink(audio_path)
    except Exception as e:
        print(f"[Voice] ⚠️ Failed to cleanup audio: {e}")
