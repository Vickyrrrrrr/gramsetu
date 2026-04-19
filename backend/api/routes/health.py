from backend.storage import db
from backend.api.app import _user_sessions, _impact
from fastapi.responses import JSONResponse
from fastapi import APIRouter, Request

from backend.core.cache import get_cache
from backend.api.state import settings, _impact

router = APIRouter(tags=["health"])

@router.get("/live")
async def live():
    return {"status": "alive"}

@router.get("/ready")
async def ready():
    cache_ok = False
    try:
        cache_ok = await get_cache().ping()
    except Exception:
        cache_ok = False
    return {
        "status": "ready" if cache_ok else "degraded",
        "cache": cache_ok,
        "db": True,
        "metrics": settings.metrics_enabled,
    }

@router.get("/api/health")
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

@router.get("/api/impact")
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
@router.get("/api/logs")
async def get_logs(limit: int = 100):
    return JSONResponse(db.get_audit_logs(limit))

@router.get("/api/conversations")
async def get_conversations(limit: int = 50):
    return JSONResponse(db.get_recent_conversations(limit))

@router.get("/api/submissions")
async def get_submissions():
    return JSONResponse(db.get_all_submissions())

@router.get("/api/submissions/pending")
async def get_pending():
    return JSONResponse(db.get_pending_submissions())

@router.get("/api/stats")
async def get_stats():
    stats = db.get_stats()
    stats["active_sessions"] = len(_user_sessions)
    return JSONResponse(stats)

@router.post("/api/confirm/{submission_id}")
async def confirm_submission(submission_id: int, request: Request):
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    db.confirm_submission(submission_id, body.get("notes", ""))
    return JSONResponse({"success": True})

@router.post("/api/reject/{submission_id}")
async def reject_submission(submission_id: int, request: Request):
    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    db.reject_submission(submission_id, body.get("notes", ""))
    return JSONResponse({"success": True})


# ---------------------------------------------------------------------------
# GRAPH STATE (debug)
# ---------------------------------------------------------------------------
@router.get("/api/graph/state/{user_id}")
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

@router.get("/api/mcp-status")
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
@router.get("/api/receipt/{session_id}")
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
@router.get("/api/screenshot/{form_type}/{session_id}")
async def get_screenshot(form_type: str, session_id: str):
    fp = os.path.join(STATIC_DIR, "data", "screenshots", f"{form_type}_{session_id}.png")
    if os.path.exists(fp):
        return FileResponse(fp, media_type="image/png")
    raise HTTPException(status_code=404, detail="Screenshot not found")


# ---------------------------------------------------------------------------
# AUDIT LOGS (admin-gated)
# ---------------------------------------------------------------------------
@router.get("/api/audit-logs")
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
@router.get("/presentation")
async def presentation_slides():
    """Serve the slides HTML for the demo."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Slides not found</h1>")

@router.get("/")
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
@router.websocket("/ws/browser/{session_id}")
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
