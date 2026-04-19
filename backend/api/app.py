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

Application assembly module for GramSetu. Imported by whatsapp_bot.main.
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
from backend.core import get_settings
from backend.core.cache import get_cache, close_cache
from backend.core.metrics import instrument_fastapi
from backend.api.state import settings
from backend.api.routes.health import router as health_router

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
load_dotenv()

from whatsapp_bot.voice_handler import transcribe_audio
from whatsapp_bot.language_utils import detect_language
from backend.storage import db
from backend.orchestrator.flow import process_message as v3_process_message
from backend.orchestrator.models import GraphStatus
from backend.integrations.security import api_limiter, sanitize_input, validate_otp_input
from backend.integrations.schemes import discover_schemes
from backend.integrations.voice import text_to_speech
from backend.services.session_store import (
    get_chat_session,
    save_chat_session,
    save_completed_session,
)

settings = get_settings()

# ---------------------------------------------------------------------------
# Session + impact tracking (in-memory; resets on server restart)
# ---------------------------------------------------------------------------



async def _store_session_state(session_key: str, payload: dict, ttl: int = 3600):
    try:
        await save_chat_session(session_key, payload, ttl=ttl)
    except Exception:
        pass

async def _get_session_state(session_key: str):
    try:
        return await get_chat_session(session_key)
    except Exception:
        return None

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

STATIC_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if settings.metrics_enabled:
    instrument_fastapi(app)

app.include_router(health_router)


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    db.init_db()
    cache = get_cache()
    try:
        await cache.ping()
        print("[Cache] Redis/in-memory cache ready")
        print("[Sessions] Chat sessions now use cache-backed persistence")
    except Exception as e:
        print(f"[Cache] cache unavailable: {e}")

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


@app.on_event("shutdown")
async def shutdown():
    await close_cache()

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
