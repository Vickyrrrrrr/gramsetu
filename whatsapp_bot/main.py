"""
============================================================
main.py -- GramSetu Web API Server (v3)
============================================================
REST API server for the GramSetu web app.

Endpoints:
  POST /api/chat             -- Chat with the AI agent
  POST /api/voice            -- Upload audio, get transcription
  POST /api/otp/{user_id}    -- Resume a form fill after OTP
  POST /api/schemes          -- Discover eligible schemes
  POST /api/tts              -- Generate TTS audio
  POST /api/status           -- Check application status
  GET  /api/impact           -- Public impact metrics
  GET  /api/health           -- Service health check
  GET  /api/mcp-status       -- MCP + LLM provider status
  GET  /callback/digilocker  -- DigiLocker OAuth callback

Run: python -m whatsapp_bot.main   OR   start.ps1
"""

import os
import sys
import asyncio
import tempfile
from typing import TypedDict

import uvicorn
from fastapi import FastAPI, Request, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from whatsapp_bot.voice_handler import transcribe_audio
from whatsapp_bot.language_utils import detect_language
from backend import database as db

from backend.agents.graph import process_message as v3_process_message
from backend.agents.schema import GraphStatus
from backend.security import api_limiter, sanitize_input, validate_otp_input
from backend.schemes import discover_schemes
from backend.voice_tts import text_to_speech

# ---------------------------------------------------------------------------
# Session + impact tracking (in-memory; resets on server restart)
# ---------------------------------------------------------------------------
_user_sessions: dict[str, dict] = {}   # session_key -> {session_id, status, ...}
_completed_forms: dict[str, dict] = {} # session_id -> {form_type, form_data, ref, timestamp}

class ImpactStats(TypedDict):
    forms_filled: int
    schemes_discovered: int
    otp_handled: int
    voice_notes_processed: int
    users_served: set[str]


_impact: ImpactStats = {
    "forms_filled": 0,
    "schemes_discovered": 0,
    "otp_handled": 0,
    "voice_notes_processed": 0,
    "users_served": set(),
}

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="GramSetu v3 -- AI Government Forms Assistant",
    description=(
        "AI agent that fills Indian government forms via web chat. "
        "Supports text, voice, OTP handling, DigiLocker auto-fill, "
        "scheme discovery, and 11 Indian languages."
    ),
    version="3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

STATIC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    db.init_db()

    from backend.llm_client import _groq_ok, _nim_ok, GROQ_MODEL_MAIN
    groq_status   = "OK Groq"   if _groq_ok() else "NO KEY Groq"
    nvidia_status = "OK NVIDIA" if _nim_ok()  else "NO KEY NVIDIA"
    port = os.getenv("PORT", "8000")

    print("\n" + "=" * 60)
    print("  GramSetu v3 -- Web API Server")
    print("=" * 60)
    print(f"  LLM:        {groq_status} ({GROQ_MODEL_MAIN})")
    print(f"  Vision/ASR: {nvidia_status}")
    print(f"  ASR:        Groq whisper-large-v3 -> NVIDIA parakeet")
    print(f"  TTS:        edge-tts (11 Indian languages, free)")
    print(f"  DigiLocker: Mock (see DIGILOCKER_INTEGRATION.md for real API)")
    print(f"  Gov Portal: Mock (Playwright)")
    print("-" * 60)
    print(f"  API Docs:   http://localhost:{port}/docs")
    print(f"  Chat:       POST /api/chat")
    print(f"  Voice:      POST /api/voice")
    print(f"  OTP:        POST /api/otp/{{user_id}}")
    print(f"  Schemes:    POST /api/schemes")
    print(f"  Impact:     GET  /api/impact")
    print("=" * 60 + "\n")

    _start_mcp_servers()


def _start_mcp_servers():
    """Start all 4 MCP tool servers as background daemon threads."""
    import threading

    mcp_configs = [
        ("WhatsApp",   "backend.mcp_servers.whatsapp_mcp",   int(os.getenv("MCP_WHATSAPP_PORT",   "8100"))),
        ("Audit",      "backend.mcp_servers.audit_mcp",      int(os.getenv("MCP_AUDIT_PORT",      "8102"))),
        ("Browser",    "backend.mcp_servers.browser_mcp",    int(os.getenv("MCP_BROWSER_PORT",    "8101"))),
        ("DigiLocker", "backend.mcp_servers.digilocker_mcp", int(os.getenv("MCP_DIGILOCKER_PORT", "8103"))),
    ]

    def _run_mcp(name: str, module: str, port: int):
        try:
            import importlib
            mod = importlib.import_module(module)
            mcp_server = getattr(mod, "mcp", None)
            if mcp_server and hasattr(mcp_server, "run"):
                print(f"[MCP] {name} starting on :{port}")
                mcp_server.run(transport="streamable-http", host="127.0.0.1", port=port)
        except Exception as e:
            print(f"[MCP] {name} failed: {e}")

    for name, module, port in mcp_configs:
        threading.Thread(target=_run_mcp, args=(name, module, port), daemon=True).start()

    print("[MCP] 4 servers: WhatsApp :8100 | Browser :8101 | Audit :8102 | DigiLocker :8103")


# ---------------------------------------------------------------------------
# Core: run a message through the v3 LangGraph pipeline
# ---------------------------------------------------------------------------
async def _process(
    user_id: str, phone: str, message: str,
    message_type: str = "text", form_type: str = "",
) -> dict:
    import time

    message = sanitize_input(message)
    session = _user_sessions.get(phone, {})
    lang = detect_language(message) if message else "hi"

    result = await v3_process_message(
        user_id=user_id, user_phone=phone, message=message,
        message_type=message_type, language=lang,
        form_type=form_type, session_id=session.get("session_id"),
    )

    _user_sessions[phone] = {
        "session_id": result.get("session_id", session.get("session_id")),
        "created_at": session.get("created_at", time.time()),
        "last_active": time.time(),
        "status": result.get("status", ""),
    }

    _impact["users_served"].add(phone)
    if result.get("status") == GraphStatus.COMPLETED.value:
        _impact["forms_filled"] += 1
        # Store completed form for receipt generation
        sid = result.get("session_id", session.get("session_id", ""))
        if sid and result.get("form_data"):
            _completed_forms[sid] = {
                "form_type":       result.get("form_type", ""),
                "form_data":       result.get("form_data", {}),
                "reference_number": result.get("reference_number", ""),
                "timestamp":       __import__("datetime").datetime.now().isoformat(),
                "user_id":         user_id,
            }
    if message_type == "otp":
        _impact["otp_handled"] += 1
    if message_type == "voice":
        _impact["voice_notes_processed"] += 1

    _log_to_db(user_id, phone, message, result, message_type)
    return result


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
        print(f"[DB] {e}")


# ---------------------------------------------------------------------------
# CHAT -- main entry point for the web app
# ---------------------------------------------------------------------------
@app.post("/api/chat")
async def chat_api(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not api_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    message   = body.get("message", "")
    user_id   = body.get("user_id", "web-user")
    phone     = body.get("phone", "") or ""
    form_type = body.get("form_type", "")

    # Web users don't have a real phone — use user_id as the session key
    if not phone or phone in ("9999999999", "test", "0"):
        phone = user_id

    if not message:
        raise HTTPException(status_code=400, detail="'message' is required")

    result = await _process(user_id, phone, message, "text", form_type)

    # Build screenshot URL — _format_result already pops from cache into result
    screenshot_url = None
    b64 = result.get("screenshot_b64", "")
    if b64:
        screenshot_url = f"data:image/png;base64,{b64}"

    return JSONResponse({
        "success":               True,
        "response":              result["response"],
        "status":                result.get("status", ""),
        "session_id":            result.get("session_id", ""),
        "current_node":          result.get("current_node", ""),
        "language":              result.get("language", "hi"),
        "form_type":             result.get("form_type", ""),
        "form_data":             result.get("form_data", {}),
        "confidence_scores":     result.get("confidence_scores", {}),
        "missing_fields":        result.get("missing_fields", []),
        "screenshot_url":        screenshot_url,
        "digilocker_auth_status": result.get("digilocker_auth_status"),
        "receipt_url": (
            f"/api/receipt/{result['session_id']}"
            if result.get("receipt_ready") and result.get("session_id")
            else None
        ),
    })


# ---------------------------------------------------------------------------
# OTP RESUME
# ---------------------------------------------------------------------------
@app.post("/api/otp/{user_id}")
async def resume_with_otp(user_id: str, request: Request):
    """Resume a form fill that was paused waiting for an OTP."""
    body = await request.json()
    otp = validate_otp_input(body.get("otp", ""))
    if not otp:
        raise HTTPException(status_code=400, detail="Invalid OTP (4-6 digits required)")
    result = await _process(user_id, user_id, otp, "otp")
    return JSONResponse({"success": True, "response": result["response"], "status": result.get("status", "")})


# ---------------------------------------------------------------------------
# VOICE INPUT
# ---------------------------------------------------------------------------
@app.post("/api/voice")
async def voice_input(request: Request):
    """Upload a WebM/WAV audio file, get back the transcribed text."""
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        audio_file = form.get("audio")
        if not isinstance(audio_file, UploadFile):
            raise HTTPException(status_code=400, detail="'audio' field required")
        audio_bytes = await audio_file.read()
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
        text = await asyncio.to_thread(transcribe_audio, tmp.name, "hi")
    except Exception:
        text = ""
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass

    if not text:
        return JSONResponse({"text": "", "language_detected": "hi", "confidence": 0.0})
    return JSONResponse({"text": text, "language_detected": detect_language(text), "confidence": 0.85})


# ---------------------------------------------------------------------------
# SCHEME DISCOVERY
# ---------------------------------------------------------------------------
@app.post("/api/schemes")
async def discover_user_schemes(request: Request):
    """Find all schemes a user is eligible for.
    Body: {"age": 65, "gender": "male", "income": 80000, "occupation": "farmer", "language": "hi"}
    """
    body = await request.json()
    lang = body.get("language", "hi")
    try:
        result = await discover_schemes(
            age=body.get("age"), gender=body.get("gender"),
            income=body.get("income"), occupation=body.get("occupation"),
            language=lang,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scheme discovery failed: {e}")

    _impact["schemes_discovered"] += result["count"]
    schemes = []
    for idx, s in enumerate(result.get("eligible", []), start=1):
        name = s.get(f"name_{lang}") or s.get("name") or s.get("name_en") or "Unknown Scheme"
        schemes.append({"id": s.get("id", f"scheme_{idx}"), "name": name,
                        "benefit": s.get("benefit", ""), "emoji": s.get("emoji", "📋")})
    return JSONResponse({"count": result["count"], "message": result["message"], "schemes": schemes})


# ---------------------------------------------------------------------------
# DIGILOCKER OAUTH CALLBACK
# ---------------------------------------------------------------------------
@app.get("/callback/digilocker")
async def digilocker_callback(code: str = "", state: str = "", error: str = ""):
    """DigiLocker redirects here after the user grants document access."""
    if error:
        return HTMLResponse(f"<h1>DigiLocker Authorization Failed</h1><p>Error: {error}</p>")
    if not code or not state:
        return HTMLResponse("<h1>Missing Parameters</h1>")

    from backend.mcp_servers.digilocker_mcp import _auth_sessions, _get_demo_data
    session = _auth_sessions.get(state)
    if session:
        session["status"]    = "completed"
        session["auth_code"] = code
        session["data"]      = _get_demo_data(session.get("form_type", "ration_card"))
        # TODO (real API): exchange `code` for access_token here
        # See DIGILOCKER_INTEGRATION.md for the full OAuth flow

    return HTMLResponse("""<html><head><style>
        body{font-family:'Segoe UI',sans-serif;text-align:center;padding:60px 20px;background:#0d1117;color:#e6edf3}
        .card{background:#161b22;border-radius:16px;padding:40px;max-width:400px;margin:0 auto;border:1px solid #30363d}
        h1{color:#58a6ff} p{color:#8b949e;line-height:1.6}
    </style></head><body><div class="card">
        <div style="font-size:64px">OK</div>
        <h1>DigiLocker Connected!</h1>
        <p>Your documents have been fetched. Go back to the app -- your form is ready!</p>
        <p style="font-size:14px;color:#484f58;margin-top:24px">Your data is encrypted and never stored permanently.</p>
    </div></body></html>""")


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------
@app.post("/api/tts")
async def generate_voice(request: Request):
    """Generate TTS audio. Body: {"text": "...", "language": "hi"}"""
    body = await request.json()
    text = body.get("text", "")
    lang = body.get("language", "hi")
    if not text:
        raise HTTPException(status_code=400, detail="'text' is required")
    filepath = await text_to_speech(text, lang)
    if filepath and os.path.exists(filepath):
        return FileResponse(filepath, media_type="audio/mpeg", filename="reply.mp3")
    raise HTTPException(status_code=500, detail="TTS generation failed")


# ---------------------------------------------------------------------------
# APPLICATION STATUS (demo -- in production use browser_mcp to scrape portal)
# ---------------------------------------------------------------------------
@app.post("/api/status")
async def check_application_status(request: Request):
    body = await request.json()
    form_type = body.get("form_type", "")
    lang = body.get("language", "hi")
    status_map = {
        "ration_card": ("Under Review", "15 din", "15 days"),
        "pension":     ("Approved",     "agle mahine se", "from next month"),
        "identity":    ("Processing",   "7 din", "7 days"),
    }
    status, time_hi, time_en = status_map.get(form_type, ("Unknown", "N/A", "N/A"))
    if lang == "hi":
        msg = f"Aawedan ki sthiti\n\nForm: {form_type}\nSthiti: {status}\nSamay: {time_hi}"
    else:
        msg = f"Application Status\n\nForm: {form_type}\nStatus: {status}\nTime: {time_en}"
    return JSONResponse({"status": status, "message": msg})


# ---------------------------------------------------------------------------
# IMPACT METRICS
# ---------------------------------------------------------------------------
@app.get("/api/impact")
async def get_impact():
    return JSONResponse({
        "forms_filled":          _impact["forms_filled"],
        "schemes_discovered":    _impact["schemes_discovered"],
        "otp_handled":           _impact["otp_handled"],
        "voice_notes_processed": _impact["voice_notes_processed"],
        "users_served":          len(_impact["users_served"]),
        "active_sessions":       len(_user_sessions),
    })


# ---------------------------------------------------------------------------
# DB / ADMIN ENDPOINTS
# ---------------------------------------------------------------------------
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
    stats["active_sessions"] = len(_user_sessions)
    return JSONResponse(stats)

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


# ---------------------------------------------------------------------------
# GRAPH STATE (debug)
# ---------------------------------------------------------------------------
@app.get("/api/graph/state/{user_id}")
async def get_graph_state(user_id: str):
    session = _user_sessions.get(user_id, {})
    if not session.get("session_id"):
        return JSONResponse({"state": None, "message": "No active session"})
    try:
        from backend.agents.graph import get_compiled_graph
        snapshot = get_compiled_graph().get_state({"configurable": {"thread_id": session["session_id"]}})
        if snapshot and snapshot.values:
            s = snapshot.values
            return JSONResponse({"state": {
                "session_id":    s.get("session_id"),
                "status":        s.get("status"),
                "current_node":  s.get("current_node"),
                "form_type":     s.get("form_type"),
                "missing_fields": s.get("missing_fields", []),
            }})
    except Exception as e:
        return JSONResponse({"state": None, "error": str(e)})
    return JSONResponse({"state": None})


# ---------------------------------------------------------------------------
# HEALTH
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    from backend.llm_client import _groq_ok, _nim_ok
    return JSONResponse({
        "status":          "ok",
        "version":         "v3",
        "groq":            "configured" if _groq_ok() else "missing_key",
        "nvidia":          "configured" if _nim_ok()  else "missing_key",
        "graph_engine":    "langgraph",
        "active_sessions": len(_user_sessions),
        "forms_filled":    _impact["forms_filled"],
    })


# ---------------------------------------------------------------------------
# MCP STATUS
# ---------------------------------------------------------------------------
@app.get("/api/mcp-status")
async def mcp_status():
    import socket
    from datetime import datetime, timezone
    from backend.llm_client import _groq_ok, _nim_ok
    ports = {
        "whatsapp":   int(os.getenv("MCP_WHATSAPP_PORT",   "8100")),
        "browser":    int(os.getenv("MCP_BROWSER_PORT",    "8101")),
        "audit":      int(os.getenv("MCP_AUDIT_PORT",      "8102")),
        "digilocker": int(os.getenv("MCP_DIGILOCKER_PORT", "8103")),
    }
    result = {}
    for name, port in ports.items():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect(("localhost", port))
            s.close()
            result[f"mcp_{name}"] = "online"
        except Exception:
            result[f"mcp_{name}"] = "offline"
    result.update({
        "groq":       "configured" if _groq_ok() else "missing_key",
        "nvidia":     "configured" if _nim_ok()  else "missing_key",
        "digilocker": "mock",
        "gov_portal": "mock",
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    })
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# RECEIPT — HTML download after form submission
# ---------------------------------------------------------------------------
@app.get("/api/receipt/{session_id}")
async def get_receipt(session_id: str):
    """
    Return a printable HTML receipt for a submitted form.
    The user can open this in a browser and Ctrl+P to save as PDF.
    """
    data = _completed_forms.get(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Receipt not found. It may have expired (server restart clears receipts).")

    form_type   = data.get("form_type", "").replace("_", " ").title()
    form_data   = data.get("form_data", {})
    ref         = data.get("reference_number", "N/A")
    timestamp   = data.get("timestamp", "")
    from datetime import datetime as _dt
    try:
        ts = _dt.fromisoformat(timestamp).strftime("%d %b %Y, %I:%M %p")
    except Exception:
        ts = timestamp

    def _flatten(d: dict, prefix: str = "") -> list[tuple[str, str]]:
        rows = []
        for k, v in d.items():
            label = (prefix + k).replace("_", " ").title()
            if isinstance(v, dict):
                rows.extend(_flatten(v, prefix=k + " "))
            elif v:
                # Redact Aadhaar
                val = str(v)
                if "aadhaar" in k.lower() and len(val.replace(" ", "").replace("-", "")) >= 4:
                    clean = val.replace(" ", "").replace("-", "")
                    val = f"XXXX-XXXX-{clean[-4:]}"
                rows.append((label, val))
        return rows

    rows = _flatten(form_data)
    rows_html = "\n".join(
        f"<tr><td>{lbl}</td><td>{val}</td></tr>"
        for lbl, val in rows
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>GramSetu Receipt — {form_type}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f5f5f5; padding: 30px 20px; color: #1a1a1a; }}
  .page {{ max-width: 700px; margin: 0 auto; background: white; border-radius: 12px;
           box-shadow: 0 4px 24px rgba(0,0,0,.08); overflow: hidden; }}
  .header {{ background: #0C0C0C; color: white; padding: 28px 32px; }}
  .header h1 {{ font-size: 22px; font-weight: 700; letter-spacing: -.3px; }}
  .header p {{ font-size: 13px; color: #aaa; margin-top: 4px; }}
  .badge {{ display: inline-block; background: #22c55e; color: white; font-size: 11px;
            font-weight: 700; padding: 3px 10px; border-radius: 99px; margin-top: 10px; letter-spacing: .4px; }}
  .meta {{ padding: 20px 32px; border-bottom: 1px solid #eee; display: flex; gap: 32px; flex-wrap: wrap; }}
  .meta-item {{ flex: 1; min-width: 180px; }}
  .meta-item .label {{ font-size: 11px; color: #888; font-weight: 600; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; }}
  .meta-item .value {{ font-size: 15px; font-weight: 600; color: #0C0C0C; }}
  .data-section {{ padding: 24px 32px; }}
  .data-section h2 {{ font-size: 14px; font-weight: 700; color: #888; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 14px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  tr:nth-child(even) td {{ background: #f9f9f9; }}
  td {{ padding: 9px 12px; font-size: 13.5px; border-bottom: 1px solid #eee; vertical-align: top; }}
  td:first-child {{ font-weight: 600; color: #555; width: 42%; white-space: nowrap; }}
  td:last-child {{ color: #111; }}
  .footer {{ padding: 20px 32px; border-top: 1px solid #eee; font-size: 12px; color: #999; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }}
  .print-btn {{ display: inline-block; background: #0C0C0C; color: white; padding: 10px 22px; border-radius: 8px;
                font-size: 13px; font-weight: 600; cursor: pointer; border: none; }}
  @media print {{
    body {{ background: white; padding: 0; }}
    .page {{ box-shadow: none; border-radius: 0; }}
    .print-btn {{ display: none !important; }}
  }}
</style>
</head>
<body>
<div class="page">
  <div class="header">
    <h1>GramSetu</h1>
    <p>AI Government Forms Assistant — Official Receipt</p>
    <span class="badge">SUBMITTED</span>
  </div>
  <div class="meta">
    <div class="meta-item">
      <div class="label">Form Type</div>
      <div class="value">{form_type}</div>
    </div>
    <div class="meta-item">
      <div class="label">Reference Number</div>
      <div class="value">{ref}</div>
    </div>
    <div class="meta-item">
      <div class="label">Submitted On</div>
      <div class="value">{ts}</div>
    </div>
    <div class="meta-item">
      <div class="label">Data Source</div>
      <div class="value">DigiLocker + NPCI</div>
    </div>
  </div>
  <div class="data-section">
    <h2>Form Details</h2>
    <table>
      {rows_html}
    </table>
  </div>
  <div class="footer">
    <span>Generated by GramSetu &bull; Data filled from DigiLocker &bull; {ts}</span>
    <button class="print-btn" onclick="window.print()">Save as PDF</button>
  </div>
</div>
</body>
</html>"""

    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# SCREENSHOT
# ---------------------------------------------------------------------------
@app.get("/api/screenshot/{form_type}/{session_id}")
async def get_screenshot(form_type: str, session_id: str):
    fp = os.path.join(STATIC_DIR, "data", "screenshots", f"{form_type}_{session_id}.png")
    if os.path.exists(fp):
        return FileResponse(fp, media_type="image/png")
    raise HTTPException(status_code=404, detail="Screenshot not found")


# ---------------------------------------------------------------------------
# AUDIT LOGS (admin-gated)
# ---------------------------------------------------------------------------
@app.get("/api/audit-logs")
async def get_audit_logs(token: str = "", limit: int = 100):
    if token != "gramsetu-admin-2025":
        raise HTTPException(status_code=403, detail="Invalid admin token")
    all_entries = []
    try:
        from backend.agents.graph import get_compiled_graph
        compiled = get_compiled_graph()
        for phone, info in _user_sessions.items():
            sid = info.get("session_id")
            if not sid:
                continue
            try:
                snapshot = compiled.get_state({"configurable": {"thread_id": sid}})
                if snapshot and snapshot.values:
                    for e in snapshot.values.get("audit_entries", []):
                        e.setdefault("user_id", phone)
                        e.setdefault("form_type", snapshot.values.get("form_type", ""))
                        e.setdefault("status", snapshot.values.get("status", ""))
                    all_entries.extend(snapshot.values.get("audit_entries", []))
            except Exception:
                pass
    except Exception:
        pass
    for log in db.get_audit_logs(limit):
        all_entries.append({
            "timestamp": log.get("timestamp", ""),
            "user_id":   log.get("user_id", ""),
            "form_type": log.get("form_type", ""),
            "status":    log.get("status", "active"),
            "node":      log.get("active_agent", ""),
        })
    all_entries.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return JSONResponse(all_entries[:limit])


# ---------------------------------------------------------------------------
# LANDING PAGE
# ---------------------------------------------------------------------------
@app.get("/presentation")
async def presentation_slides():
    """Serve the slides HTML for the demo."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Slides not found</h1>")

@app.get("/")
async def landing_page():
    """Professional API landing page."""
    return HTMLResponse("""
    <html><head><style>
        body { font-family: 'Inter', system-ui, sans-serif; background: #F7F6F3; color: #0C0C0C; display: flex; align-items: center; justify-content: center; height: 100vh; text-align: center; }
        .card { background: white; border: 1px solid #E5E5E0; border-radius: 16px; padding: 40px; box-shadow: 0 4px 24px rgba(0,0,0,0.05); }
        h1 { font-style: italic; font-family: 'Instrument Serif', serif; font-size: 32px; margin-bottom: 10px; }
        p { color: #6B6B6B; margin-bottom: 24px; }
        a { background: #0C0C0C; color: #F7F6F3; text-decoration: none; padding: 10px 20px; border-radius: 99px; font-weight: 500; display: inline-block; margin: 10px; transition: opacity 0.2s; }
        a:hover { opacity: 0.8; }
    </style></head><body>
        <div class="card">
            <h1>GramSetu Backend 🌾</h1>
            <p>The AI Government Forms Engine is active and healthy.</p>
            <a href="/docs">📜 API Documentation</a>
            <a href="/presentation">📽️ View Presentation</a>
        </div>
    </body></html>
    """)


# ---------------------------------------------------------------------------
# WEBSOCKET: Live browser preview during form filling
# ---------------------------------------------------------------------------
@app.websocket("/ws/browser/{session_id}")
async def browser_preview_ws(websocket: WebSocket, session_id: str):
    """Stream Playwright screenshots to the webapp as fields are filled."""
    await websocket.accept()
    from backend.agents.graph import _browser_ws_clients
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("whatsapp_bot.main:app", host="0.0.0.0",
                port=int(os.getenv("PORT", "8000")), reload=True)
