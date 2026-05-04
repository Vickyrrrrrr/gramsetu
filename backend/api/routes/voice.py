import os
import tempfile
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.param_functions import File

from backend.llm_client import transcribe_audio_sarvam, transcribe_audio_groq

router = APIRouter(tags=["voice"])


@router.post("/")
async def voice_transcribe(audio: UploadFile = File(...)):
    """Transcribe uploaded audio and return text."""
    print(f"[DEBUG] Received file: {audio.filename}, content_type: {audio.content_type}")
    if not audio.content_type or not (audio.content_type.startswith("audio/") or audio.content_type.startswith("video/") or audio.content_type == "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Invalid audio file")

    suffix = os.path.splitext(audio.filename or "recording.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await audio.read())
        tmp_path = tmp.name

    try:
        text = await transcribe_audio_sarvam(tmp_path)
        if not text:
            text = await transcribe_audio_groq(tmp_path)
        if not text:
            raise HTTPException(status_code=500, detail="Transcription failed")
        return JSONResponse({"text": text})
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
