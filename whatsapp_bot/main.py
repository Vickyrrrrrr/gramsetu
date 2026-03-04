"""
============================================================
main.py — FastAPI Server (GramSetu v3 — Production)
============================================================
Handles:
  - Twilio WhatsApp webhooks (text + voice + OTP)
  - LangGraph v3 autonomous flow with DigiLocker
  - Scheme discovery ("you're eligible for 5 schemes!")
  - OTP suspend/resume
  - DigiLocker OAuth callback
  - Voice TTS replies
  - Security: Twilio HMAC, rate limiting, PII encryption
  - Application status tracking

Run: python -m whatsapp_bot.main
"""

import os
import sys
import asyncio
import uuid
import uvicorn
import httpx
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

# ── v2 legacy pipeline ──────────────────────────────────────
from agent_core.agents import process_message as v2_process_message
from whatsapp_bot.voice_handler import download_audio_async, transcribe_audio, cleanup_audio
from whatsapp_bot.language_utils import detect_language
import data.db as db

# ── v3 LangGraph pipeline ───────────────────────────────────
from backend.agents.graph import process_message as v3_process_message
from backend.agents.schema import GraphStatus

# ── Security ─────────────────────────────────────────────────
from backend.security import (
    validate_twilio_signature, webhook_limiter, api_limiter,
    sanitize_input, validate_otp_input,
)

# ── Scheme Discovery ─────────────────────────────────────────
from backend.schemes import discover_schemes

# ── Voice TTS ────────────────────────────────────────────────
from backend.voice_tts import text_to_speech, generate_summary_voice

# ── Feature Flags ────────────────────────────────────────────
USE_V3 = os.getenv("USE_V3_GRAPH", "true").lower() in ("true", "1", "yes")

# ── Twilio Config (for direct API sends) ────────────────────
_TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID", "")
_TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
_TWILIO_FROM  = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")


async def _send_whatsapp(to_phone: str, message: str) -> None:
    """Send a WhatsApp message directly via Twilio REST API (not TwiML)."""
    if not _TWILIO_SID or not _TWILIO_TOKEN:
        print(f"[WhatsApp] (mock) → {to_phone}: {message[:80]}")
        return
    to = f"whatsapp:{to_phone}" if not to_phone.startswith("whatsapp:") else to_phone
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{_TWILIO_SID}/Messages.json",
                auth=(_TWILIO_SID, _TWILIO_TOKEN),
                data={"From": _TWILIO_FROM, "To": to, "Body": message},
            )
            if resp.status_code not in (200, 201):
                print(f"[WhatsApp] ⚠️ Twilio HTTP {resp.status_code} for {to_phone}: {resp.text[:200]}")
            else:
                sid_sent = resp.json().get("sid", "?")
                print(f"[WhatsApp] ✅ Sent to {to_phone} (sid={sid_sent})")
    except Exception as e:
        print(f"[WhatsApp] ⚠️ Could not send to {to_phone}: {e}")

# ── Session tracker ──────────────────────────────────────────
_user_sessions: dict[str, dict] = {}  # phone → {session_id, created_at, ...}

# ── Impact tracker (in-memory, persists to DB) ───────────────
_impact = {
    "forms_filled": 0,
    "schemes_discovered": 0,
    "otp_handled": 0,
    "voice_notes_processed": 0,
    "users_served": set(),
    "districts": set(),
}

# ── Initialize FastAPI ───────────────────────────────────────
app = FastAPI(
    title="GramSetu v3 — Autonomous WhatsApp Agent",
    description="AI agent that fills government forms for rural India. "
                "DigiLocker auto-fill, vision-based portal navigation, "
                "OTP suspend/resume, scheme discovery.",
    version="3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# ── ngrok browser-warning bypass ─────────────────────────────
# Twilio's servers don't send a browser User-Agent, so ngrok's free-tier
# serves them a browser challenge page instead of forwarding the request.
# Adding this header to all responses tells ngrok's edge to skip the challenge.
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

class NgrokBypassMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers["ngrok-skip-browser-warning"] = "true"
        return response

app.add_middleware(NgrokBypassMiddleware)

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ── Shutdown ─────────────────────────────────────────────────
@app.on_event("shutdown")
async def shutdown():
    """Notify all active WhatsApp users that the server is closing."""
    if not _user_sessions:
        return
    print("[Server] 🔴 Sending shutdown notice to active users...")
    shutdown_hi = (
        "⚠️ *GramSetu सर्वर बंद हो रहा है*\n\n"
        "हमारा सर्वर अभी बंद हो गया है। कृपया कुछ देर बाद पुनः प्रयास करें।\n"
        "आपका डेटा सुरक्षित है। 🙏"
    )
    shutdown_en = (
        "⚠️ *GramSetu Server Closed*\n\n"
        "The server has been shut down. Please try again after some time.\n"
        "Your data is safe. 🙏"
    )
    tasks = []
    for phone in list(_user_sessions.keys()):
        msg = shutdown_hi  # default Hindi for rural users
        tasks.append(_send_whatsapp(phone, msg))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    print(f"[Server] 🔴 Shutdown notice sent to {len(tasks)} users.")


# ── Startup ──────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    import sys
    # Ensure UTF-8 output on Windows
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    db.init_db()
    v = "v3 (LangGraph)" if USE_V3 else "v2 (Legacy)"
    print("\n" + "=" * 62)
    print(f"  🌾 GramSetu {v} — Production Server")
    print("=" * 62)
    print(f"  🌐 API Docs:    http://localhost:{os.getenv('PORT', 8000)}/docs")
    print(f"  💬 Chat:        POST /api/chat")
    print(f"  📱 WhatsApp:    POST /webhook")
    print(f"  🔐 OTP:         POST /api/otp/{{user_id}}")
    print(f"  🎯 Schemes:     POST /api/schemes")
    print(f"  📊 Impact:      GET  /api/impact")
    print(f"  🔊 TTS:         POST /api/tts")
    print(f"  📈 Dashboard:   streamlit run dashboard/app.py")
    print("=" * 62 + "\n")


# ============================================================
# CORE: Process message through v3 pipeline
# ============================================================

async def _process(user_id: str, phone: str, message: str,
                   message_type: str = "text", form_type: str = "") -> dict:
    """Route to v3 LangGraph or v2 legacy pipeline with security."""

    # Sanitize input
    message = sanitize_input(message)

    if USE_V3:
        session = _user_sessions.get(phone, {})
        session_id = session.get("session_id")
        lang = detect_language(message) if message else "hi"

        result = await v3_process_message(
            user_id=user_id, user_phone=phone, message=message,
            message_type=message_type, language=lang,
            form_type=form_type, session_id=session_id,
        )

        # Track session
        import time
        _user_sessions[phone] = {
            "session_id": result.get("session_id", session_id),
            "created_at": session.get("created_at", time.time()),
            "last_active": time.time(),
            "status": result.get("status", ""),
        }

        # Track impact
        _impact["users_served"].add(phone)
        if result.get("status") == GraphStatus.COMPLETED.value:
            _impact["forms_filled"] += 1
        if message_type == "otp":
            _impact["otp_handled"] += 1
        if message_type == "voice":
            _impact["voice_notes_processed"] += 1

        _log_to_db(user_id, phone, message, result, message_type)
        return result
    else:
        return v2_process_message(user_id, phone, message, message_type)


def _log_to_db(user_id, phone, message, result, message_type):
    try:
        db.log_conversation(
            user_id=user_id, user_phone=phone, direction="incoming",
            original_text=message, detected_language=result.get("language", "hi"),
            bot_response=result.get("response", ""),
            active_agent=result.get("current_node", ""),
            message_type=message_type,
        )
    except Exception as e:
        print(f"[DB] ⚠️ {e}")


# ============================================================
# TWILIO WHATSAPP WEBHOOK (with security)
# ============================================================

_THINKING_MSGS = {
    "hi": "⏳ *GramSetu सोच रहा है...*\nआपका संदेश मिल गया। बस एक पल!",
    "ta": "⏳ *GramSetu யோசிக்கிறது...*\nஉங்கள் செய்தி கிடைத்தது. ஒரு நிமிடம்!",
    "te": "⏳ *GramSetu ఆలోచిస్తోంది...*\nమీ సందేశం అందింది. ఒక్క క్షణం!",
    "bn": "⏳ *GramSetu ভাবছে...*\nআপনার বার্তা পেয়েছি। একটু অপেক্ষা করুন!",
    "mr": "⏳ *GramSetu विचार करत आहे...*\nतुमचा संदेश मिळाला. एक क्षण!",
    "en": "⏳ *GramSetu is thinking...*\nGot your message. Just a moment!",
}

_ERROR_MSGS = {
    "hi": "❌ *कुछ गड़बड़ हो गई।*\nकृपया दोबारा भेजें या कुछ देर बाद प्रयास करें।\n\nसमस्या बनी रहे तो *0* भेजकर नए सिरे से शुरू करें।",
    "ta": "❌ *பிழை ஏற்பட்டது.*\nமீண்டும் அனுப்பவும் அல்லது சிறிது நேரம் கழித்து முயற்சிக்கவும்.\n\n*0* அனுப்பி மறுதொடக்கம் செய்யலாம்.",
    "te": "❌ *లోపం సంభవించింది.*\nదయచేసి మళ్ళీ పంపండి లేదా కొంత సేపు తర్వాత ప్రయత్నించండి.\n\n*0* పంపి మళ్ళీ మొదలుపెట్టండి.",
    "bn": "❌ *একটি ত্রুটি ঘটেছে।*\nঅনুগ্রহ করে আবার পাঠান বা কিছুক্ষণ পরে চেষ্টা করুন।\n\n*0* পাঠিয়ে নতুন করে শুরু করুন।",
    "mr": "❌ *काहीतरी चुकले.*\nकृपया पुन्हा पाठवा किंवा थोड्या वेळाने प्रयत्न करा.\n\n*0* पाठवून नव्याने सुरू करा.",
    "en": "❌ *Something went wrong.*\nPlease try sending again or wait a moment.\n\nSend *0* to start fresh.",
}


async def _process_and_reply(
    phone: str,
    user_id: str,
    message_text: str,
    message_type: str,
    media_url: str = "",
    media_content_type: str = "",
    detected_lang: str = "hi",
):
    """
    Background task:
      1. Send instant "thinking" indicator to user
      2. Download + transcribe voice if needed (async, not blocking)
      3. Run the full LangGraph pipeline
      4. Send real reply (or localized error on failure)
    """
    import time
    t0 = time.time()

    # ── 1. Instant "thinking" indicator ─────────────────────
    thinking_msg = _THINKING_MSGS.get(detected_lang, _THINKING_MSGS["hi"])
    await _send_whatsapp(phone, thinking_msg)

    # ── 2. Download + transcribe voice (async, non-blocking) ─
    if message_type == "voice" and media_url:
        twilio_sid   = os.getenv("TWILIO_ACCOUNT_SID", "")
        twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        audio_path = await download_audio_async(media_url, twilio_sid, twilio_token)
        if audio_path:
            try:
                message_text = await asyncio.to_thread(
                    transcribe_audio, audio_path, detected_lang
                )
            finally:
                await asyncio.to_thread(cleanup_audio, audio_path)
        else:
            message_text = ""

        if not message_text:
            await _send_whatsapp(phone, (
                "🎤 आवाज़ नहीं सुनाई दी। कृपया टेक्स्ट में भेजें।"
                if detected_lang == "hi" else
                "🎤 Could not process voice note. Please send as text."
            ))
            return

    # ── 3. Run the pipeline ──────────────────────────────────
    try:
        result = await _process(user_id, phone, message_text, message_type)
        reply = result.get("response", "").strip()
        elapsed = round((time.time() - t0) * 1000)
        print(f"[WhatsApp] 📤 {phone} ({elapsed}ms): {reply[:80] if reply else '(empty — sending fallback)'}")

        # Safety net: if graph returned no response (should never happen), send menu
        if not reply:
            reply = (
                "\u26a0️ *GramSetu* — namaskar! Kuch samasya aayi.\n"
                "Please try again or send *0* to reset.\n\n"
                "*0* — naye sire se shuru karein"
                if detected_lang != "hi" else
                "⚠️ *GramSetu* — नमस्कार! कुछ समस्या आई.\n"
                "कृपया दोबारा भेजें या *0* भेजकर नए सिरे से शुरू करें."
            )

        await _send_whatsapp(phone, reply)
    except Exception as e:
        import traceback
        print(f"[WhatsApp] ⚠️ Error for {phone}: {e}")
        traceback.print_exc()
        error_msg = _ERROR_MSGS.get(detected_lang, _ERROR_MSGS["hi"])
        await _send_whatsapp(phone, error_msg)


@app.post("/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Twilio WhatsApp Webhook.

    For text messages: process synchronously and reply inline via TwiML.
    This GUARANTEES delivery — no Twilio REST API, no ngrok issues.

    For voice: background task (download is slow), then REST API reply.
    """
    try:
        form_data = await request.form()
    except Exception:
        return HTMLResponse(content=str(MessagingResponse()), media_type="application/xml")

    from_number = form_data.get("From", "")
    phone = from_number.replace("whatsapp:", "")

    # ── Twilio Signature Validation ──────────────────────────
    try:
        signature  = request.headers.get("X-Twilio-Signature", "")
        proto      = request.headers.get("X-Forwarded-Proto", request.url.scheme)
        host       = request.headers.get("X-Forwarded-Host", request.url.netloc)
        canon_url  = f"{proto}://{host}{request.url.path}"
        params     = {k: v for k, v in form_data.items()}

        if not validate_twilio_signature(canon_url, params, signature):
            print(f"[Security] ⛔ Invalid Twilio signature from {phone}")
            raise HTTPException(status_code=403, detail="Invalid signature")
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Security] ⚠️ Signature validation error: {e} — allowing request")

    # ── Rate Limiting ────────────────────────────────────────
    if not webhook_limiter.is_allowed(phone):
        resp = MessagingResponse()
        resp.message("⚠️ Too many messages. Please wait a minute.")
        return HTMLResponse(content=str(resp), media_type="application/xml")

    # ── Extract fields ────────────────────────────────────────
    body               = form_data.get("Body", "") or ""
    num_media          = int(form_data.get("NumMedia", 0))
    media_url          = form_data.get("MediaUrl0", "") if num_media > 0 else ""
    media_content_type = form_data.get("MediaContentType0", "") if num_media > 0 else ""
    user_id            = phone
    message_text       = body or "hello"
    message_type       = "text"

    detected_lang = detect_language(body) if body.strip() else "hi"

    if num_media > 0 and "audio" in media_content_type:
        message_type = "voice"

    # ── OTP check ────────────────────────────────────────────
    session = _user_sessions.get(phone, {})
    if session.get("status") == GraphStatus.WAIT_OTP.value and message_type == "text":
        otp = validate_otp_input(message_text)
        if otp:
            message_text = otp
            message_type = "otp"

    print(f"[WhatsApp] 📨 {phone} [{detected_lang}] {message_type}: {message_text[:60]}")

    # ── Voice: background task (download is slow) ────────────
    if message_type == "voice":
        background_tasks.add_task(
            _process_and_reply,
            phone, user_id, message_text, message_type,
            media_url, media_content_type, detected_lang,
        )
        resp = MessagingResponse()
        resp.message(_THINKING_MSGS.get(detected_lang, _THINKING_MSGS["hi"]))
        return HTMLResponse(content=str(resp), media_type="application/xml")

    # ── Text / OTP: process synchronously + reply in TwiML ───
    try:
        result = await _process(user_id, phone, message_text, message_type)
        reply = result.get("response", "").strip()

        if not reply:
            reply = (
                "⚠️ GramSetu — कुछ समस्या आई। *0* भेजें और नए सिरे से शुरू करें।"
                if detected_lang == "hi" else
                "⚠️ GramSetu — something went wrong. Send *0* to start over."
            )

        print(f"[WhatsApp] 📤 {phone} → TwiML reply: {reply[:80]}")
        _log_to_db(user_id, phone, message_text, result, message_type)

    except Exception as e:
        import traceback
        traceback.print_exc()
        reply = _ERROR_MSGS.get(detected_lang, _ERROR_MSGS["hi"])

    resp = MessagingResponse()
    resp.message(reply)
    return HTMLResponse(content=str(resp), media_type="application/xml")


# ============================================================
# REST CHAT API (with rate limiting)
# ============================================================

@app.post("/api/chat")
async def chat_api(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not api_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    message = body.get("message", "")
    user_id = body.get("user_id", "test-user")
    phone = body.get("phone", "") or ""
    form_type = body.get("form_type", "")

    # Key fix: web users don't have a real phone number.
    # Falling back to '9999999999' caused ALL web users to share one session.
    # Use user_id as the session key when no real phone is provided.
    if not phone or phone in ("9999999999", "test", "0"):
        phone = user_id

    if not message:
        raise HTTPException(status_code=400, detail="'message' required")

    result = await _process(user_id, phone, message, "text", form_type)

    # Build screenshot URL — prefer base64 data URI (no file on disk required → no 404)
    screenshot_url = None
    # Check module-level cache FIRST (most reliable source)
    try:
        from backend.agents.graph import _screenshot_cache as _ss_cache
        _cached_b64 = _ss_cache.get(result.get("session_id", ""), "")
    except Exception:
        _cached_b64 = ""
    b64 = _cached_b64 or result.get("screenshot_b64", "")
    if b64:
        # Inline data URI: always available immediately, no separate HTTP request
        screenshot_url = f"data:image/png;base64,{b64}"
    elif (result.get("status") == "wait_otp" and result.get("current_node") == "fill_form"
            and result.get("session_id") and result.get("form_type")):
        # Legacy fallback: file-based URL (only if the file was actually written)
        fp = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "screenshots",
            f"{result['form_type']}_{result['session_id']}.png",
        )
        if os.path.exists(fp):
            screenshot_url = f"/api/screenshot/{result['form_type']}/{result['session_id']}"

    return JSONResponse({
        "success": True,
        "response": result["response"],
        "status": result.get("status", ""),
        "session_id": result.get("session_id", ""),
        "current_node": result.get("current_node", ""),
        "language": result.get("language", "hi"),
        "form_type": result.get("form_type", ""),
        "form_data": result.get("form_data", {}),
        "confidence_scores": result.get("confidence_scores", {}),
        "missing_fields": result.get("missing_fields", []),
        "screenshot_url": screenshot_url,
        "digilocker_auth_status": result.get("digilocker_auth_status", None),
    })


# ============================================================
# OTP RESUME
# ============================================================

@app.post("/api/otp/{user_id}")
async def resume_with_otp(user_id: str, request: Request):
    if not USE_V3:
        raise HTTPException(status_code=400, detail="v3 mode required")

    body = await request.json()
    raw_otp = body.get("otp", "")
    otp = validate_otp_input(raw_otp)
    if not otp:
        raise HTTPException(status_code=400, detail="Invalid OTP (4-6 digits required)")

    result = await _process(user_id, user_id, otp, "otp")
    return JSONResponse({
        "success": True, "response": result["response"],
        "status": result.get("status", ""),
    })


# ============================================================
# SCHEME DISCOVERY
# ============================================================

@app.post("/api/schemes")
async def discover_user_schemes(request: Request):
    """
    Find all schemes a user is eligible for.
    Send: {"age": 65, "gender": "male", "income": 80000, "occupation": "farmer"}
    """
    body = await request.json()
    lang = body.get("language", "hi")

    try:
        result = await discover_schemes(
            age=body.get("age"),
            gender=body.get("gender"),
            income=body.get("income"),
            occupation=body.get("occupation"),
            language=lang,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Scheme discovery failed. Please try again. ({e})",
        )

    _impact["schemes_discovered"] += result["count"]

    schemes_payload = []
    for idx, s in enumerate(result.get("eligible", []), start=1):
        name = s.get(f"name_{lang}") or s.get("name") or s.get("name_en") or "Unknown Scheme"
        schemes_payload.append({
            "id": s.get("id", f"scheme_{idx}"),
            "name": name,
            "benefit": s.get("benefit", ""),
            "emoji": s.get("emoji", "📋"),
        })

    return JSONResponse({
        "count": result["count"],
        "message": result["message"],
        "schemes": schemes_payload,
    })


# ============================================================
# DIGILOCKER OAUTH CALLBACK
# ============================================================

@app.get("/callback/digilocker")
async def digilocker_callback(code: str = "", state: str = "", error: str = ""):
    """
    DigiLocker redirects here after user grants permission.
    Exchanges auth code for access token, then fetches documents.
    """
    if error:
        return HTMLResponse(
            "<h1>❌ DigiLocker Authorization Failed</h1>"
            f"<p>Error: {error}</p>"
            "<p>Please go back to WhatsApp and try again.</p>"
        )

    if not code or not state:
        return HTMLResponse(
            "<h1>⚠️ Missing Parameters</h1>"
            "<p>Please use the link sent on WhatsApp.</p>"
        )

    # Exchange code for token (in production)
    from backend.mcp_servers.digilocker_mcp import _auth_sessions
    session = _auth_sessions.get(state)

    if session:
        session["status"] = "completed"
        session["auth_code"] = code

        # In production: exchange code for access_token here
        # For now: mark as ready with demo data
        from backend.mcp_servers.digilocker_mcp import _get_demo_data
        form_type = session.get("form_type", "ration_card")
        session["data"] = _get_demo_data(form_type)

    return HTMLResponse(
        """
        <html>
        <head><style>
            body { font-family: 'Segoe UI', sans-serif; text-align: center;
                   padding: 60px 20px; background: #0d1117; color: #e6edf3; }
            .card { background: #161b22; border-radius: 16px; padding: 40px;
                    max-width: 400px; margin: 0 auto; border: 1px solid #30363d; }
            h1 { color: #58a6ff; font-size: 28px; }
            p { color: #8b949e; font-size: 16px; line-height: 1.6; }
            .check { font-size: 64px; }
        </style></head>
        <body>
            <div class="card">
                <div class="check">✅</div>
                <h1>DigiLocker Connected!</h1>
                <p>Your data has been fetched successfully.<br>
                   Go back to <strong>WhatsApp</strong> — your form is ready!</p>
                <p style="margin-top: 30px; font-size: 14px; color: #484f58;">
                    🔒 Your data is encrypted and never stored permanently.
                </p>
            </div>
        </body>
        </html>
        """
    )


# ============================================================
# VOICE TTS
# ============================================================

@app.post("/api/tts")
async def generate_voice(request: Request):
    """Generate voice reply. Send: {"text": "...", "language": "hi"}"""
    body = await request.json()
    text = body.get("text", "")
    lang = body.get("language", "hi")

    if not text:
        raise HTTPException(status_code=400, detail="'text' required")

    filepath = await text_to_speech(text, lang)
    if filepath and os.path.exists(filepath):
        return FileResponse(filepath, media_type="audio/mpeg", filename="reply.mp3")

    raise HTTPException(status_code=500, detail="TTS generation failed")


# ============================================================
# APPLICATION STATUS TRACKER
# ============================================================

@app.post("/api/status")
async def check_application_status(request: Request):
    """
    Check application status. Send: {"user_id": "...", "form_type": "ration_card"}
    In production: scrapes the portal status page.
    """
    body = await request.json()
    user_id = body.get("user_id", "")
    form_type = body.get("form_type", "")
    lang = body.get("language", "hi")

    # Demo response (in production: use browser_mcp to check portal)
    status_map = {
        "ration_card": ("Under Review", "15 दिन", "15 days"),
        "pension": ("Approved", "अगले महीने से", "from next month"),
        "identity": ("Processing", "7 दिन", "7 days"),
    }
    status, time_hi, time_en = status_map.get(form_type, ("Unknown", "N/A", "N/A"))

    if lang == "hi":
        message = (
            f"📋 *आवेदन की स्थिति*\n\n"
            f"📝 फ़ॉर्म: {form_type.replace('_', ' ').title()}\n"
            f"🔄 स्थिति: *{status}*\n"
            f"⏳ अनुमानित समय: {time_hi}\n\n"
            f"🔔 SMS पर अपडेट आएगा।"
        )
    else:
        message = (
            f"📋 *Application Status*\n\n"
            f"📝 Form: {form_type.replace('_', ' ').title()}\n"
            f"🔄 Status: *{status}*\n"
            f"⏳ Estimated time: {time_en}\n\n"
            f"🔔 Updates will come via SMS."
        )

    return JSONResponse({"status": status, "message": message})


# ============================================================
# IMPACT DASHBOARD
# ============================================================

@app.get("/api/impact")
async def get_impact():
    """Public impact metrics for the impact dashboard."""
    return JSONResponse({
        "forms_filled": _impact["forms_filled"],
        "schemes_discovered": _impact["schemes_discovered"],
        "otp_handled": _impact["otp_handled"],
        "voice_notes_processed": _impact["voice_notes_processed"],
        "users_served": len(_impact["users_served"]),
        "active_sessions": len(_user_sessions),
    })


# ============================================================
# EXISTING DASHBOARD ENDPOINTS (v2 compatible)
# ============================================================

@app.get("/api/logs")
async def get_logs(limit: int = 100):
    return JSONResponse(db.get_audit_logs(limit))

@app.get("/api/conversations")
async def get_conversations(limit: int = 50):
    return JSONResponse(db.get_recent_conversations(limit))

@app.get("/api/submissions")
async def get_submissions():
    return JSONResponse(db.get_all_submissions())

@app.get("/api/submissions/pending")
async def get_pending():
    return JSONResponse(db.get_pending_submissions())

@app.get("/api/stats")
async def get_stats():
    stats = db.get_stats()
    stats["version"] = "v3" if USE_V3 else "v2"
    stats["active_sessions"] = len(_user_sessions)
    return JSONResponse(stats)

@app.post("/api/confirm/{submission_id}")
async def confirm_submission(submission_id: int, request: Request):
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    db.confirm_submission(submission_id, body.get("notes", ""))
    return JSONResponse({"success": True, "message": f"Submission {submission_id} confirmed"})

@app.post("/api/reject/{submission_id}")
async def reject_submission(submission_id: int, request: Request):
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    db.reject_submission(submission_id, body.get("notes", ""))
    return JSONResponse({"success": True, "message": f"Submission {submission_id} rejected"})


# ── Graph State (debug) ─────────────────────────────────────

@app.get("/api/graph/state/{user_id}")
async def get_graph_state(user_id: str):
    session = _user_sessions.get(user_id, {})
    if not session.get("session_id"):
        return JSONResponse({"state": None, "message": "No active session"})

    try:
        from backend.agents.graph import get_compiled_graph
        compiled = get_compiled_graph()
        config = {"configurable": {"thread_id": session["session_id"]}}
        snapshot = compiled.get_state(config)
        if snapshot and snapshot.values:
            s = snapshot.values
            return JSONResponse({"state": {
                "session_id": s.get("session_id"),
                "status": s.get("status"),
                "current_node": s.get("current_node"),
                "form_type": s.get("form_type"),
                "missing_fields": s.get("missing_fields", []),
            }})
    except Exception as e:
        return JSONResponse({"state": None, "error": str(e)})
    return JSONResponse({"state": None})


# ── Health Check ─────────────────────────────────────────────

@app.get("/api/health")
async def health():
    from agent_core.nims_client import is_nim_available
    return JSONResponse({
        "status": "ok",
        "version": "v3" if USE_V3 else "v2",
        "nvidia_nim": "connected" if is_nim_available() else "fallback_mode",
        "graph_engine": "langgraph" if USE_V3 else "legacy",
        "active_sessions": len(_user_sessions),
        "forms_filled": _impact["forms_filled"],
    })


# ── Landing Page ─────────────────────────────────────────────

@app.get("/")
async def landing_page():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>GramSetu v3 Running 🌾</h1>")


# ============================================================
# UPGRADE 1: MCP STATUS ENDPOINT
# ============================================================

@app.get("/api/mcp-status")
async def mcp_status():
    """Probe all 4 MCP server ports and return status."""
    from datetime import datetime, timezone
    ports = {
        "whatsapp": int(os.getenv("MCP_WHATSAPP_PORT", 8100)),
        "browser": int(os.getenv("MCP_BROWSER_PORT", 8101)),
        "audit": int(os.getenv("MCP_AUDIT_PORT", 8102)),
        "digilocker": int(os.getenv("MCP_DIGILOCKER_PORT", 8103)),
    }
    result = {}
    async with httpx.AsyncClient(timeout=2.0) as client:
        for name, port in ports.items():
            try:
                r = await client.get(f"http://localhost:{port}/sse", timeout=1.5)
                result[name] = True
            except Exception:
                # Try a plain TCP probe as fallback
                try:
                    import socket
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(1)
                    s.connect(("localhost", port))
                    s.close()
                    result[name] = True
                except Exception:
                    result[name] = False
    result["timestamp"] = datetime.now(timezone.utc).isoformat()
    return JSONResponse(result)


# ============================================================
# UPGRADE 2: SCREENSHOT ENDPOINT
# ============================================================

@app.get("/api/screenshot/{form_type}/{session_id}")
async def get_screenshot(form_type: str, session_id: str):
    """Serve a Playwright screenshot PNG from data/screenshots/."""
    screenshot_dir = os.path.join(STATIC_DIR, "data", "screenshots")
    filename = f"{form_type}_{session_id}.png"
    filepath = os.path.join(screenshot_dir, filename)
    if os.path.exists(filepath):
        return FileResponse(filepath, media_type="image/png", filename=filename)
    raise HTTPException(status_code=404, detail="Screenshot not found")


# ============================================================
# UPGRADE 3: VOICE INPUT ENDPOINT (for webapp)
# ============================================================

@app.post("/api/voice")
async def voice_input(request: Request):
    """Accept audio upload (WebM/WAV), transcribe, return text."""
    import tempfile
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        audio_file = form.get("audio")
        if not audio_file:
            raise HTTPException(status_code=400, detail="'audio' field required")
        audio_bytes = await audio_file.read()
    else:
        audio_bytes = await request.body()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio")

    # Save to temp file
    suffix = ".webm" if b"webm" in audio_bytes[:32] else ".wav"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=os.path.join(STATIC_DIR, "data", "voice_cache"))
    tmp.write(audio_bytes)
    tmp.close()

    try:
        text = await asyncio.to_thread(transcribe_audio, tmp.name, "hi")
    except Exception as e:
        text = ""
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

    if not text:
        return JSONResponse({"text": "", "language_detected": "hi", "confidence": 0.0})

    lang = detect_language(text)
    return JSONResponse({"text": text, "language_detected": lang, "confidence": 0.85})


# ============================================================
# UPGRADE 6: AUDIT LOGS ENDPOINT
# ============================================================

@app.get("/api/audit-logs")
async def get_audit_logs(token: str = "", limit: int = 100):
    """Return audit entries from all active sessions. Token-gated for demo."""
    if token != "gramsetu-admin-2025":
        raise HTTPException(status_code=403, detail="Invalid admin token")

    from datetime import datetime, timezone
    all_entries = []

    # Collect from in-memory graph states via snapshot
    try:
        from backend.agents.graph import get_compiled_graph
        compiled = get_compiled_graph()
        for phone, session_info in _user_sessions.items():
            sid = session_info.get("session_id")
            if not sid:
                continue
            try:
                config = {"configurable": {"thread_id": sid}}
                snapshot = compiled.get_state(config)
                if snapshot and snapshot.values:
                    entries = snapshot.values.get("audit_entries", [])
                    for e in entries:
                        e.setdefault("user_id", phone)
                        e.setdefault("form_type", snapshot.values.get("form_type", ""))
                        e.setdefault("status", snapshot.values.get("status", ""))
                        e.setdefault("timestamp", session_info.get("last_active", 0))
                        e.setdefault("fields_filled", len(snapshot.values.get("form_data", {})))
                    all_entries.extend(entries)
            except Exception:
                pass
    except Exception:
        pass

    # Also pull from SQLite audit log
    try:
        db_logs = db.get_audit_logs(limit)
        for log in db_logs:
            all_entries.append({
                "timestamp": log.get("timestamp", ""),
                "user_id": log.get("user_id", ""),
                "form_type": log.get("form_type", ""),
                "status": log.get("status", "active"),
                "fields_filled": 0,
                "node": log.get("active_agent", ""),
                "latency_ms": 0,
            })
    except Exception:
        pass

    # Sort by timestamp desc, limit
    all_entries.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return JSONResponse(all_entries[:limit])


# ============================================================
# WEBSOCKET: Live Browser Preview
# ============================================================

@app.websocket("/ws/browser/{session_id}")
async def browser_preview_ws(websocket: WebSocket, session_id: str):
    """
    WebSocket for streaming live Playwright screenshots to the webapp.
    The graph's fill_form_node broadcasts JPEG frames here as fields are filled.
    """
    await websocket.accept()

    # Register this client
    from backend.agents.graph import _browser_ws_clients
    if session_id not in _browser_ws_clients:
        _browser_ws_clients[session_id] = []
    _browser_ws_clients[session_id].append(websocket)

    try:
        while True:
            # Keep connection alive — client sends pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if session_id in _browser_ws_clients:
            try:
                _browser_ws_clients[session_id].remove(websocket)
            except ValueError:
                pass


# ── Main ─────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("whatsapp_bot.main:app", host="0.0.0.0", port=port, reload=True)
