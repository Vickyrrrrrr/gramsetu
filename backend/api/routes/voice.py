import asyncio
import tempfile
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from whatsapp_bot.voice_handler import transcribe_audio
from whatsapp_bot.language_utils import detect_language
from backend.integrations.voice import text_to_speech
from backend.api.state import _impact

router = APIRouter(tags=["voice"])


