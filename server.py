import os
import sys
import time
import uuid
import asyncio
import tempfile
from typing import TypedDict

import uvicorn
from fastapi import FastAPI, Request, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend import database as db
from backend.agents.graph import process_message as v3_process_message
from backend.agents.schema import GraphStatus
from backend.security import api_limiter, sanitize_input, validate_otp_input
from backend.schemes import discover_schemes
from lib.language_utils import detect_language
from lib.voice_handler import transcribe_audio
from backend.api.routes.whatsapp import router as whatsapp_router

_user_sessions: dict[str, dict] = {}
_completed_forms: dict[str, dict] = {}

class ImpactStats(TypedDict):
    forms_filled: int
    schemes_discovered: int
    users_served: set[str]

_impact: ImpactStats = {
    "forms_filled": 0,
    "schemes_discovered": 0,
    "users_served": set(),
}

app = FastAPI(title="GramSetu API", version="1.0")
# ── CORS: restrict to known origins (not wildcard) ──────
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,https://gramsetu.vercel.app").split(",")
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET","POST"], allow_headers=["*"])

STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
# Specific mount for mock portals (DEMO MODE)
app.mount("/mock", StaticFiles(directory=os.path.join(STATIC_DIR, "backend", "static", "mock_portals")), name="mock")
app.include_router(whatsapp_router)

# ── Startup ─────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        db.init_db()
    except RuntimeError:
        print("[DB] Supabase not configured - skipping database (prototype mode)")
    except Exception as e:
        print(f"[DB] Database warning: {e}")
    from backend.llm_client import _groq_ok, _nim_ok, _sarvam_ok, GROQ_MODEL_MAIN
    print(f"\nGramSetu API | Chat: {'OK Sarvam' if _sarvam_ok() else 'NO KEY'} | Groq: {'OK' if _groq_ok() else 'NO KEY'} "
          f"| NVIDIA: {'OK' if _nim_ok() else 'NO KEY'} | Sarvam STT/TTS: {'OK' if _sarvam_ok() else 'NO KEY'}")
    print(f"Chat/Intent: Groq {GROQ_MODEL_MAIN} | Vision: NVIDIA | STT/TTS: Sarvam")
    print(f"API Docs: http://localhost:{os.getenv('PORT','8000')}/docs\n")

# ── Core processor ───────────────────────────────────────
async def _process(user_id: str, phone: str, message: str, message_type: str = "text") -> dict:
    message = sanitize_input(message)
    session = _user_sessions.get(phone, {})
    session_id = session.get("session_id")
    lang = detect_language(message) if message else "hi"
    result = await v3_process_message(user_id=user_id, user_phone=phone, message=message, message_type=message_type, language=lang, session_id=session_id)
    result_session_id = result.get("session_id", "")
    if session_id and result_session_id and session_id != result_session_id:
        print(f"[Session] Resumed session {session_id[:8]}...")
    elif result_session_id and not session_id:
        print(f"[Session] New session {result_session_id[:8]}...")
    _user_sessions[phone] = {"session_id": result_session_id, "created_at": session.get("created_at", time.time()), "last_active": time.time()}
    _impact["users_served"].add(phone)
    if result.get("status") == GraphStatus.COMPLETED.value:
        _impact["forms_filled"] += 1
        sid = result.get("session_id", session.get("session_id", ""))
        if sid and result.get("form_data"):
            _completed_forms[sid] = {"form_type": result.get("form_type", ""), "form_data": result.get("form_data", {}), "reference_number": result.get("reference_number", ""), "timestamp": __import__("datetime").datetime.now().isoformat()}
    try:
        db.log_conversation(user_id=user_id, user_phone=phone, direction="incoming", original_text=message, detected_language=result.get("language", "hi"), bot_response=result.get("response", ""), active_agent=result.get("current_node", ""), message_type=message_type)
    except RuntimeError:
        pass  # Supabase not configured
    except Exception as e:
        print(f"[DB] {e}")
    return result

# ── Chat ────────────────────────────────────────────────
@app.post("/api/chat")
async def chat_api(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not api_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    message = body.get("message", "")
    user_id = body.get("user_id", "web-user")
    phone = body.get("phone", "") or ""
    if not phone or phone in ("9999999999", "test", "0"):
        phone = user_id
    if not message:
        raise HTTPException(status_code=400, detail="'message' is required")
    result = await _process(user_id, phone, message, "text")
    screenshot_url = f"data:image/png;base64,{result.get('screenshot_b64', '')}" if result.get("screenshot_b64") else None
    return JSONResponse({"success": True, "response": result["response"], "status": result.get("status", ""), "session_id": result.get("session_id", ""), "language": result.get("language", "hi"), "form_type": result.get("form_type", ""), "form_data": result.get("form_data", {}), "confidence_scores": result.get("confidence_scores", {}), "screenshot_url": screenshot_url, "digilocker_auth_status": result.get("digilocker_auth_status"), "receipt_url": f"/api/receipt/{result['session_id']}" if result.get("receipt_ready") and result.get("session_id") else None})

# ── Browser Control ───────────────────────────────────────
@app.post("/api/browser/stop")
async def stop_browser(request: Request):
    body = await request.json()
    phone = body.get("phone", "")
    session_id = body.get("session_id", "")
    
    if not session_id and phone:
        session = _user_sessions.get(phone, {})
        session_id = session.get("session_id")
    
    if session_id:
        from backend.agents.form_fill_agent import _cancel_signals
        _cancel_signals[session_id] = True
        return {"status": "stopping", "session_id": session_id}
    return JSONResponse(status_code=404, content={"error": "Session not found"})

# ── Voice API ───────────────────────────────────
@app.post("/api/voice")
async def voice_input(request: Request):
    # File size limit: 5MB for voice uploads
    content_length = request.headers.get("content-length", "0")
    if int(content_length) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio file too large (max 5MB)")
    
    client_ip = request.client.host if request.client else "unknown"
    if not api_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")
    content_type = request.headers.get("content-type", "")
    lang = "hi"
    if "multipart/form-data" in content_type:
        form = await request.form()
        audio_file = form.get("audio")
        if not isinstance(audio_file, UploadFile):
            raise HTTPException(status_code=400, detail="'audio' field required")
        audio_bytes = await audio_file.read()
        lang = form.get("language", "hi")
    else:
        audio_bytes = await request.body()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio")
    
    voice_cache_dir = os.path.join(STATIC_DIR, "data", "voice_cache")
    os.makedirs(voice_cache_dir, exist_ok=True)
    suffix = ".webm" if b"webm" in audio_bytes[:32] else ".wav"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=voice_cache_dir)
    tmp.write(audio_bytes)
    tmp.close()
    
    try:
        from backend.llm_client import transcribe_audio_sarvam, transcribe_audio_groq
        text = await transcribe_audio_sarvam(tmp.name, lang)
        if not text:
            text = await transcribe_audio_groq(tmp.name, lang)
    except Exception as e:
        print(f"[Voice] Transcription error: {e}")
        text = ""
    finally:
        try: os.unlink(tmp.name)
        except Exception: pass
    
    if not text:
        return JSONResponse({"text": "", "language_detected": lang, "confidence": 0.0})
    return JSONResponse({"text": text, "language_detected": detect_language(text), "confidence": 0.85})


# ── Realtime Voice API (WebSocket) ─────────────────
@app.websocket("/api/voice/realtime")
async def websocket_realtime_voice(websocket: WebSocket):
    """Realtime STT via Sarvam WebSocket API."""
    await websocket.accept()
    
    import os
    SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
    
    if not SARVAM_API_KEY or SARVAM_API_KEY == "your_sarvam_key_here":
        await websocket.send_json({"type": "error", "message": "Sarvam API key not configured"})
        await websocket.close()
        return
    
    try:
        import websockets
        import json
        
        sarvam_ws = await websockets.connect(
            "wss://api.sarvam.ai/speech-to-text-realtime",
            extra_headers={"api-subscription-key": SARVAM_API_KEY}
        )
        
        # Handle start message
        start_msg = await websocket.receive_json()
        language = start_msg.get("language", "hi")
        
        # Send config to Sarvam
        await sarvam_ws.send(json.dumps({
            "type": "config",
            "language_code": f"{language}-IN",
            "model": "saaras:v3",
            "audio_format": "pcm",
            "sample_rate": 16000
        }))
        
        async def receive_from_client():
            try:
                while True:
                    try:
                        data = await asyncio.wait_for(websocket.receive(), timeout=0.1)
                        if "bytes" in data and data["bytes"]:
                            await sarvam_ws.send(data["bytes"])
                        elif "text" in data:
                            msg = json.loads(data["text"])
                            if msg.get("type") == "stop":
                                break
                    except asyncio.TimeoutError:
                        continue
            except Exception:
                pass
            finally:
                await sarvam_ws.close()
        
        async def receive_from_sarvam():
            try:
                async for message in sarvam_ws:
                    if isinstance(message, str):
                        data = json.loads(message)
                        await websocket.send_json({
                            "type": "transcript",
                            "text": data.get("transcript", ""),
                            "is_final": data.get("is_final", False)
                        })
            except Exception as e:
                print(f"[Realtime STT] Sarvam error: {e}")
        
        await asyncio.gather(receive_from_client(), receive_from_sarvam(), return_exceptions=True)
        
    except Exception as e:
        print(f"[Realtime STT] Error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass

# ── Voice Output (TTS) ──────────────────────────────────
@app.post("/api/tts")
async def voice_output(request: Request):
    body = await request.json()
    text = body.get("text", "")
    lang = body.get("language", "hi")
    if not text:
        raise HTTPException(status_code=400, detail="Text required")
    
    from lib.voice_handler import generate_voice
    audio_bytes = await generate_voice(text, lang)
    if not audio_bytes:
        raise HTTPException(status_code=500, detail="TTS generation failed — all providers unavailable")
    
    from fastapi.responses import Response
    return Response(content=audio_bytes, media_type="audio/wav")

# ── Schemes ─────────────────────────────────────────────
@app.post("/api/schemes")
async def discover_user_schemes(request: Request):
    body = await request.json()
    lang = body.get("language", "hi")
    try:
        result = await discover_schemes(age=body.get("age"), gender=body.get("gender"), income=body.get("income"), occupation=body.get("occupation"), language=lang)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scheme discovery failed: {e}")
    _impact["schemes_discovered"] += result["count"]
    schemes = [{"id": s.get("id", f"scheme_{idx}"), "name": s.get(f"name_{lang}") or s.get("name") or s.get("name_en") or "Unknown Scheme", "benefit": s.get("benefit", ""), "emoji": s.get("emoji", "📋")} for idx, s in enumerate(result.get("eligible", []), start=1)]
    return JSONResponse({"count": result["count"], "message": result["message"], "schemes": schemes})

# ── OTP Resume ────────────────────────────────────────────
@app.post("/api/otp/{user_id}")
async def resume_with_otp(user_id: str, request: Request):
    body = await request.json()
    otp = validate_otp_input(body.get("otp", ""))
    if not otp:
        raise HTTPException(status_code=400, detail="Invalid OTP (4-6 digits required)")
    result = await _process(user_id, user_id, otp, "otp")
    return JSONResponse({"success": True, "response": result["response"], "status": result.get("status", "")})

# ── Impact ───────────────────────────────────────────────
@app.get("/api/impact")
async def get_impact():
    return JSONResponse({"forms_filled": _impact["forms_filled"], "schemes_discovered": _impact["schemes_discovered"], "users_served": len(_impact["users_served"]), "active_sessions": len(_user_sessions)})

# ── DB Admin ─────────────────────────────────────────────
@app.get("/api/stats")
async def get_stats():
    stats = db.get_stats()
    stats["active_sessions"] = len(_user_sessions)
    return JSONResponse(stats)

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

@app.post("/api/confirm/{submission_id}")
async def confirm_submission(submission_id: int, request: Request):
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    db.confirm_submission(submission_id, body.get("notes", ""))
    return JSONResponse({"success": True})

@app.post("/api/reject/{submission_id}")
async def reject_submission(submission_id: int, request: Request):
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    db.reject_submission(submission_id, body.get("notes", ""))
    return JSONResponse({"success": True})

# ── Health ────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    from backend.llm_client import _groq_ok, _nim_ok
    return JSONResponse({"status": "ok", "groq": "configured" if _groq_ok() else "missing_key", "nvidia": "configured" if _nim_ok() else "missing_key"})

@app.get("/api/mcp-status")
async def mcp_status():
    from backend.llm_client import _groq_ok, _nim_ok
    import httpx
    import asyncio

    async def check_port(port: int) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as c:
                r = await c.get(f"http://127.0.0.1:{port}/health")
                return r.status_code == 200
        except Exception:
            return False

    browser_ok = await check_port(8101)
    audit_ok = await check_port(8102)
    digilocker_ok = await check_port(8103)
    whatsapp_ok = await check_port(8104)

    return JSONResponse({
        "groq": "configured" if _groq_ok() else "missing_key",
        "nvidia": "configured" if _nim_ok() else "missing_key",
        "browser": browser_ok,
        "audit": audit_ok,
        "digilocker": digilocker_ok,
        "whatsapp": whatsapp_ok,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    })

# ── Receipt ──────────────────────────────────────────────
@app.get("/api/receipt/{session_id}")
async def get_receipt(session_id: str):
    data = _completed_forms.get(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Receipt not found")
    form_type = data.get("form_type", "").replace("_", " ").title()
    form_data = data.get("form_data", {})
    ref = data.get("reference_number", "N/A")
    from datetime import datetime as _dt
    ts = _dt.now().strftime("%d %b %Y, %I:%M %p")
    rows = [(k.replace("_", " ").title(), str(v)) for k, v in form_data.items() if v and not isinstance(v, dict)]
    rows_html = "\n".join(f"<tr><td>{lbl}</td><td>{val}</td></tr>" for lbl, val in rows)
    html = f"<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'><title>GramSetu Receipt</title><style>body{{font-family:'Segoe UI',Arial,sans-serif;background:#f5f5f5;padding:30px}}table{{width:100%;border-collapse:collapse}}td{{padding:9px 12px;font-size:13.5px;border-bottom:1px solid #eee}}td:first-child{{font-weight:600;color:#555;width:42%}}</style></head><body><h1>GramSetu Receipt — {form_type}</h1><p>Ref: {ref} | {ts}</p><table>{rows_html}</table></body></html>"
    return HTMLResponse(content=html)

# ── Landing ──────────────────────────────────────────────
@app.get("/")
async def landing():
    return HTMLResponse("<html><body style='font-family:system-ui;background:#F7F6F3;display:flex;align-items:center;justify-content:center;height:100vh'><div style='text-align:center'><h1 style='font-style:italic'>GramSetu API</h1><p>API is running. Open <a href='/docs'>API Docs</a>.</p></div></body></html>")

# ── WebSocket: Live browser preview ──────────────────────
@app.websocket("/ws/browser/{session_id}")
async def browser_preview_ws(websocket: WebSocket, session_id: str):
    from backend.agents.graph import _browser_ws_clients
    await websocket.accept()
    _browser_ws_clients.setdefault(session_id, []).append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type":"pong"}')
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        try:
            _browser_ws_clients.get(session_id, []).remove(websocket)
        except ValueError:
            pass

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)