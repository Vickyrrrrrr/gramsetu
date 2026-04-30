"""
============================================================
whatsapp.py — WhatsApp-to-Agent Bridge API
============================================================
Receives messages from the Baileys WhatsApp gateway,
routes them through the GramSetu agent pipeline,
and returns responses + media for WhatsApp delivery.

Endpoints:
  POST /api/whatsapp/message — Text message from WhatsApp → agent → response
  POST /api/whatsapp/voice   — Voice note → Sarvam STT → transcription
  POST /api/whatsapp/image   — Image → VLM analysis → response
  GET  /api/whatsapp/state   — Get session state for a phone number
  GET  /api/whatsapp/health  — Connection status
"""
import os
import json
import base64
import tempfile
import asyncio
from fastapi import APIRouter, Request, HTTPException, UploadFile, Form
from fastapi.responses import JSONResponse

from backend.agents.graph import process_message as v3_process_message
from backend.agents.schema import GraphStatus
from lib.language_utils import detect_language
from backend.llm_client import (
    transcribe_audio_sarvam, transcribe_audio_groq,
    chat_conversational,
)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

# ── WhatsApp Session Store ─────────────────────────────────
_wa_sessions: dict[str, dict] = {}  # phone → {session_id, last_active, language, form_type}


def _get_wa_session(phone: str) -> dict:
    if phone not in _wa_sessions:
        _wa_sessions[phone] = {
            "session_id": "",
            "last_active": 0,
            "language": "hi",
            "message_count": 0,
        }
    return _wa_sessions[phone]


# ════════════════════════════════════════════════════════════
# TEXT MESSAGE
# ════════════════════════════════════════════════════════════

@router.post("/message")
async def whatsapp_message(request: Request):
    """Process a WhatsApp text message through the GramSetu agent."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    text = (body.get("message") or "").strip()
    phone = body.get("phone") or body.get("user_id") or "whatsapp-user"
    lang = body.get("language") or detect_language(text) or "hi"

    if not text:
        return JSONResponse({"response": "कृपया अपना संदेश भेजें। / Please send your message.", "status": "error"})

    session = _get_wa_session(phone)
    session["last_active"] = __import__("time").time()
    session["message_count"] += 1
    session["language"] = lang

    # First-time greeting
    if session["message_count"] == 1 and text.lower() in ("hi", "hello", "start", "नमस्ते", "namaste", "help"):
        return JSONResponse({
            "response": (
                "🙏 *नमस्ते! मैं GramSetu हूँ — आपका AI फ़ॉर्म सहायक.*\n\n"
                "📋 मैं आपकी मदद कर सकता हूँ:\n"
                "• राशन कार्ड, पैन कार्ड, वोटर ID, पेंशन\n"
                "• आयुष्मान भारत, PM-किसान, जन धन खाता\n"
                "• जाति प्रमाण पत्र, जन्म प्रमाण पत्र\n"
                "• किसी भी सरकारी योजना की जानकारी\n\n"
                "📱 *बस आवेदन का नाम भेजें या बोलें — बाकी मैं करूँगा!*\n\n"
                "_मैं आपकी आवाज़ के नोट भी समझता हूँ। 🎙️_"
            ),
            "status": "active",
        })

    # Route through the full agent pipeline
    try:
        result = await v3_process_message(
            user_id=phone,
            user_phone=phone,
            message=text,
            message_type="text",
            language=lang,
            session_id=session.get("session_id"),
        )

        session["session_id"] = result.get("session_id", "")

        # Build WhatsApp-friendly response
        response_text = result.get("response", "")

        # Clean up formatting for WhatsApp (remove bold markers, simplify)
        response_text = _format_for_whatsapp(response_text)

        return JSONResponse({
            "response": response_text,
            "status": result.get("status", ""),
            "session_id": result.get("session_id", ""),
            "form_type": result.get("form_type", ""),
            "screenshot_b64": result.get("screenshot_b64", ""),
            "receipt_ready": result.get("receipt_ready", False),
            "reference_number": result.get("reference_number", ""),
            "identity_verified": result.get("identity_verified", False),
        })
    except Exception as e:
        print(f"[WhatsApp] Agent error: {e}")
        return JSONResponse({
            "response": "⚠️ सेवा अस्थायी रूप से अनुपलब्ध है। कृपया पुनः प्रयास करें।",
            "status": "error",
        })


# ════════════════════════════════════════════════════════════
# VOICE NOTE
# ════════════════════════════════════════════════════════════

@router.post("/voice")
async def whatsapp_voice(audio: UploadFile, phone: str = Form(""), language: str = Form("hi")):
    """Process a WhatsApp voice note through Sarvam STT."""
    suffix = ".ogg" if audio.filename and audio.filename.endswith(".ogg") else ".opus"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Sarvam PRIMARY → Groq FALLBACK
        text = await transcribe_audio_sarvam(tmp_path, language)
        if not text:
            text = await transcribe_audio_groq(tmp_path, language)

        if text:
            return JSONResponse({
                "text": text,
                "language": language,
                "source": "whatsapp-voice",
            })

        return JSONResponse({"text": "", "error": "STT failed"})
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


# ════════════════════════════════════════════════════════════
# IMAGE / DOCUMENT
# ════════════════════════════════════════════════════════════

@router.post("/image")
async def whatsapp_image(request: Request):
    """Process a WhatsApp image (document photo, form, ID) through VLM."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    image_b64 = body.get("image", "")
    phone = body.get("phone", "whatsapp-user")
    caption = body.get("caption", "")

    if not image_b64:
        return JSONResponse({"response": "No image received."})

    # Use NVIDIA VLM to analyze the image
    try:
        from backend.llm_client import chat_vision

        prompt = (
            "You are GramSetu, a government form assistant. "
            "Analyze this image sent by a user via WhatsApp. "
            "It could be: a document photo, an ID card, a form, a receipt, or a screenshot. "
            "Describe what you see and extract any useful text/information. "
            "If it's a government document, note which fields are visible. "
            "Be concise — respond in 2-3 lines maximum."
        )

        analysis = await chat_vision(image_b64, prompt, temperature=0.1, max_tokens=200)

        if analysis:
            return JSONResponse({
                "response": f"📸 *Image Analysis:*\n\n{analysis[:500]}",
                "extracted_text": analysis,
            })
    except Exception as e:
        print(f"[WhatsApp] Vision analysis failed: {e}")

    # Fallback: acknowledge receipt
    return JSONResponse({
        "response": (
            "📸 *Image received!*\n\n"
            "I can see you've sent a photo. If this is a document or form, "
            "please also type what you need in text — it helps me process faster.\n\n"
            "Meanwhile, tell me: would you like to fill a form or check a scheme?"
        ),
    })


# ════════════════════════════════════════════════════════════
# SESSION STATE
# ════════════════════════════════════════════════════════════

@router.get("/state")
async def whatsapp_state(phone: str = ""):
    """Get current session state for a WhatsApp user."""
    if phone not in _wa_sessions:
        return JSONResponse({"active": False, "message": "No active session"})

    session = _wa_sessions[phone]
    return JSONResponse({
        "active": True,
        "session_id": session["session_id"],
        "language": session["language"],
        "message_count": session["message_count"],
        "last_active": session["last_active"],
    })


# ════════════════════════════════════════════════════════════
# HEALTH
# ════════════════════════════════════════════════════════════

@router.get("/health")
async def whatsapp_health():
    return JSONResponse({
        "status": "ok",
        "active_sessions": len(_wa_sessions),
        "providers": {
            "chat": "Sarvam (sarvam-30b) → Groq (llama-3.3-70b)",
            "stt": "Sarvam (saaras:v3) → Groq (whisper-large-v3)",
            "tts": "Sarvam (bulbul:v3) → edge-tts",
            "vision": "NVIDIA (llama-3.2-11b) → Groq",
        },
    })


# ── HELPERS ─────────────────────────────────────────────────

def _format_for_whatsapp(text: str) -> str:
    """Clean up formatting for WhatsApp display."""
    import re

    # Keep WhatsApp markdown: *bold*, _italic_, ~strikethrough~
    # Remove HTML-style formatting
    text = re.sub(r'<[^>]+>', '', text)

    # Trim excessive whitespace but preserve paragraph breaks
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    # Limit to ~4000 chars (WhatsApp limit is 4096)
    if len(text) > 4000:
        text = text[:3900] + "\n\n...[message trimmed]"

    return text
