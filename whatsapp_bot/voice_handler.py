"""
============================================
voice_handler.py -- Voice Note Processing
============================================
Downloads voice notes from Twilio and transcribes using:
  1. Groq whisper-large-v3 (primary -- best accuracy for Indian languages)
  2. NVIDIA parakeet-ctc-1.1b-asr (backup)
  3. Mock transcription (demo fallback)
"""

import os
import asyncio
import tempfile
import httpx
import requests
from dotenv import load_dotenv

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")


async def download_audio_async(media_url: str, twilio_sid: str, twilio_token: str) -> str:
    """Async download of a voice note from Twilio's media URL."""
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(media_url, auth=(twilio_sid, twilio_token))
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
                tmp.write(response.content)
                return tmp.name
    except Exception as e:
        print(f"[Voice] Failed to download audio: {e}")
        return None


def download_audio(media_url: str, twilio_sid: str, twilio_token: str) -> str:
    """Sync wrapper kept for legacy callers."""
    try:
        response = requests.get(media_url, auth=(twilio_sid, twilio_token), stream=True, timeout=20)
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            for chunk in response.iter_content(chunk_size=8192):
                tmp.write(chunk)
            return tmp.name
    except Exception as e:
        print(f"[Voice] Failed to download audio: {e}")
        return None


def transcribe_audio(audio_path: str, language: str = "hi") -> str:
    """
    Transcribe audio file to text.
    Priority: Groq Whisper -> NVIDIA Parakeet -> mock fallback.
    """
    # Run async ASR in a fresh event loop (called from sync context)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            from backend.llm_client import transcribe_audio_groq, transcribe_audio_nvidia

            # 1. Groq Whisper (best accuracy for Indian languages, free)
            result = loop.run_until_complete(transcribe_audio_groq(audio_path, language))
            if result:
                print(f"[Voice] Groq Whisper: {result[:80]}")
                return result

            # 2. NVIDIA parakeet (backup)
            result = loop.run_until_complete(transcribe_audio_nvidia(audio_path, language))
            if result:
                print(f"[Voice] NVIDIA ASR: {result[:80]}")
                return result
        finally:
            loop.close()
    except Exception as e:
        print(f"[Voice] ASR pipeline failed: {e}")

    return _mock_transcription(language)


def _mock_transcription(language: str) -> str:
    """Demo fallback -- realistic voice input sample."""
    mock_messages = {
        "hi": "नमस्ते, मुझे पैन कार्ड के लिए आवेदन करना है",
        "en": "Hello, I want to apply for PAN card",
        "ta": "வணக்கம், எனக்கு ரேஷன் கார்டு வேண்டும்",
        "te": "నమస్కారం, నాకు రేషన్ కార్డు కావాలి",
        "bn": "নমস্কার, আমার রেশন কার্ড দরকার",
    }
    transcription = mock_messages.get(language, mock_messages["hi"])
    print(f"[Voice] Mock transcription ({language}): {transcription}")
    return transcription


def cleanup_audio(audio_path: str):
    """Remove temporary audio file after processing."""
    try:
        if audio_path and os.path.exists(audio_path):
            os.unlink(audio_path)
    except Exception as e:
        print(f"[Voice] Failed to cleanup audio: {e}")
