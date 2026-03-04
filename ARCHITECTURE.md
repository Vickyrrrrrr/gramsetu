# GramSetu — Full Architecture & Component Guide

> **Current state:** You're running the webapp with hardcoded/demo data.  
> This document explains every component you've built but aren't fully using yet, and exactly what each unlocks.

---

## The Two Modes: What You Have vs What's Built

```
RIGHT NOW (demo mode)
─────────────────────────────────────────────────────────────
User types in webapp  →  /api/chat  →  LangGraph v3 graph
                                              │
                                    DigiLocker: MOCK data
                                    Form fill: REAL Playwright
                                    LLM: keyword fallback only
                                    WhatsApp: not connected

FULL SYSTEM (when wired up)
─────────────────────────────────────────────────────────────
User speaks on WhatsApp  →  Twilio  →  /webhook  →  LangGraph
                                              │
                                    DigiLocker: REAL OAuth data
                                    Form fill: REAL Playwright
                                    LLM: NVIDIA NIM (Llama 3.1)
                                    MCP servers: all 4 running
```

---

## 1. LangGraph v3 Pipeline (`backend/agents/graph.py`)

**What it is:** The brain. A 5-node state machine that runs every user request through a structured, resumable pipeline.

**You ARE using this** — it runs whenever the webapp calls `/api/chat`.

### The 5 Nodes

| Node | What it does | Currently |
|------|-------------|-----------|
| **TRANSCRIBE** | Converts voice note → text via NVIDIA NeMo ASR | ✅ Active (text messages bypass it) |
| **DETECT_INTENT** | Classifies: ration card / PM-KISAN / pension / etc. | ✅ Active (keyword-based fallback) |
| **DIGILOCKER_FETCH** | Pulls Aadhaar, PAN, address from DigiLocker OAuth | ⚠️ Uses hardcoded demo data |
| **CONFIRM** | Shows data summary, waits for user YES/NO | ✅ Active |
| **FILL_FORM** | Playwright opens portal, fills every field, handles OTP | ✅ Active |

### The Key Power: OTP Suspend/Resume

LangGraph checkpoints state to SQLite. When the form needs an OTP:
1. Graph **suspends** mid-execution
2. User receives OTP on phone, replies
3. Graph **resumes from exact checkpoint** — portal is still open

This is why `data/checkpoints.db` exists. Without it, you'd lose the browser session on every message.

---

## 2. MCP Servers (`backend/mcp_servers/`)

**What they are:** 4 microservices that run as independent HTTP servers on ports 8100–8103. The LangGraph graph talks to them via the MCP (Model Context Protocol) — basically a standardized tool-calling interface.

### Why this architecture?

Instead of one giant script, each capability is isolated. You can restart/upgrade one server without touching the others. Think of them like specialist workers the LangGraph "manager" calls.

### WhatsApp MCP (Port 8100) — `whatsapp_mcp.py`

**Unlocks:** Real WhatsApp integration

Currently, your webapp manually calls Twilio via `main.py`. The WhatsApp MCP handles:
- Receiving Twilio webhooks (incoming WhatsApp messages)
- Sending replies back via Twilio API
- Detecting OTP messages (e.g., user replies "456321")
- Downloading and staging voice note audio files
- Twilio HMAC signature validation (security)

**Without it:** You can only test via the webapp — real WhatsApp users can't reach GramSetu.

**With it:** Any WhatsApp user in India can message your Twilio number and interact fully.

---

### Browser MCP (Port 8101) — `browser_mcp.py`

**Unlocks:** Advanced Playwright with VLM vision guidance

Currently, `graph.py` runs Playwright directly using CSS selectors (`[name="field_name"]`). The Browser MCP adds:
- **Vision LLM (VLM) navigation**: Takes a screenshot, asks NVIDIA's vision model "where is the date of birth field?" and clicks it — works even when portals change their HTML
- **Screenshot streaming**: Sends live Playwright frames to the webapp's WebSocket (the `/ws/browser/{session_id}` endpoint)
- Handles CAPTCHAs, page loading waits, and portal-specific quirks

**Without it:** Works for portals with predictable HTML. Breaks when portals change structure.

**With it:** Resilient to portal redesigns. VLM "reads" the page visually just like a human would.

---

### Audit MCP (Port 8102) — `audit_mcp.py`

**Unlocks:** The Streamlit dashboard becoming useful

Currently, the Streamlit dashboard (`dashboard/app.py`) mostly shows empty data. The Audit MCP:
- Logs every agent action with structured data: `{timestamp, user_id, node, latency_ms, confidence, pii_touched}`
- PII-redacts before storing (Aadhaar shown as `XXXX-XXXX-1234`)
- Writes to `data/audit.db` (separate from `checkpoints.db`)
- Powers `/api/audit-logs` endpoint that the dashboard polls

**Without it:** Dashboard shows no real metrics. You can't tell how many forms were filled, which fields fail, or latency per node.

**With it:** Real-time admin view — see every user session, every field filled, success/failure rates.

---

### DigiLocker MCP (Port 8103) — `digilocker_mcp.py`

**Unlocks:** Real Aadhaar/PAN data — the core of the autonomous flow

This is the most important one for going from demo → real.

Currently, `DIGILOCKER_FETCH` node in `graph.py` calls `_get_demo_data()` which returns hardcoded:
```python
{"name": "रामेश कुमार", "aadhaar": "XXXX-XXXX-1234", "dob": "15/08/1975", ...}
```

The DigiLocker MCP replaces this with real OAuth 2.0:
1. Generates OAuth login URL for the user (send via WhatsApp)
2. User logs into DigiLocker on their phone
3. MCP receives the auth code callback
4. Exchanges code → access token
5. Fetches Aadhaar eKYC XML → parses name, DOB, address, photo
6. Fetches PAN data, income certificates
7. Returns structured data to the graph → form fills with REAL data

**Without it:** Every form fills with demo data ("Ramesh Kumar"). Useless in production.

**With it:** Every form fills with the actual user's verified government data. This is what makes GramSetu truly zero-typing and impossible to get wrong.

---

## 3. `agent_core/` — The v2 Legacy System

**What it is:** The original agent before LangGraph was added. A simpler single-function pipeline.

```python
# main.py line 37:
from agent_core.agents import process_message as v2_process_message
```

**Where it's used:** `main.py` imports it as a fallback. If `USE_V3_GRAPH=false` in `.env`, it runs instead of the LangGraph graph.

### v2 vs v3 comparison

| | v2 (agent_core/) | v3 (backend/agents/graph.py) |
|---|---|---|
| Architecture | Single function | 5-node state machine |
| OTP resume | ❌ No | ✅ Yes (SQLite checkpoints) |
| DigiLocker | Hardcoded | Pluggable (MCP) |
| LLM | NVIDIA NIM | Keyword + NIM fallback |
| Voice | Basic handler | NeMo ASR node |
| Confidence scoring | ❌ | ✅ per field |

**Should you keep it?** Keep it as long as you want a fallback. Once v3 is stable (real DigiLocker + live WhatsApp), you can remove `agent_core/` and the fallback import.

---

## 4. `whatsapp_bot/main.py` — The FastAPI Server

You ARE using this — it's the server the webapp calls. But several endpoints are dormant:

| Endpoint | Status | What it does when live |
|----------|--------|------------------------|
| `POST /webhook` | ⚠️ Unused (no Twilio) | Real WhatsApp message intake |
| `POST /api/otp-resume` | ⚠️ Waiting | Resumes graph after user sends OTP |
| `GET /api/schemes` | ✅ Used | Returns eligible schemes list |
| `POST /api/chat` | ✅ Used | Webapp chat messages |
| `WS /ws/browser/{id}` | ✅ Connected | Live Playwright screenshots |
| `GET /api/screenshot/...` | ✅ Available | Static screenshot serving |
| `POST /api/voice` | ✅ Available | Audio → NeMo transcription |
| `GET /api/audit-logs` | ⚠️ Empty | Needs Audit MCP running |
| `GET /api/mcp-status` | ✅ Works | Probes all 4 MCP ports |

### ngrok Bypass Middleware (added)

Twilio's servers don't send a browser `User-Agent`, so ngrok's free-tier intercepts their webhook POSTs with a browser challenge HTML page. To fix this, `main.py` includes `NgrokBypassMiddleware` which adds `ngrok-skip-browser-warning: true` to all responses, telling ngrok's edge to pass requests through without the challenge.

Also configure ngrok with a named tunnel (`inspect: false`) in `ngrok.yml`:

```yaml
tunnels:
  gramsetu:
    proto: http
    addr: 8000
    inspect: false
```
Then start with: `ngrok start gramsetu`

---

## 5. `backend/llm_client.py` — The LLM Layer

Currently, intent detection mostly runs on keywords (for speed and reliability). The LLM client is built but underused.

### 4 Specialized Models (NVIDIA NIM)

| Purpose | Model | Currently |
|---------|-------|-----------|
| Intent detection | `meta/llama-3.1-8b-instruct` | ⚠️ Keyword fallback used |
| Conversational replies | `meta/llama-3.3-70b-instruct` | ✅ Used for scheme text |
| Field extraction | `meta/llama-3.1-8b-instruct` | ⚠️ Direct parse used |
| General reasoning | `nvidia/llama-3.1-nemotron-70b` | ⚠️ Rarely called |

**To enable:** Set `NVIDIA_API_KEY` in `.env`. Get a free key at [build.nvidia.com](https://build.nvidia.com).

Edge cases where LLM matters vs keywords:
- "Meri maa ko pension chahiye jo widow hai" → LLM detects `widow_pension`, keywords miss
- "PM ke kisan wala scheme" → LLM understands, keywords might not
- Multi-intent: "Ration card aur voter ID dono chahiye" → LLM handles gracefully

---

## 6. `backend/security.py` — PII Protection

Built but mostly dormant in demo mode.

What it does when active:
- **AES-256 encryption** of Aadhaar/PAN before writing to DB
- **Input sanitization** — strips script injection, validates phone formats
- **Rate limiting** — blocks >5 requests/minute from same number
- **Session cleanup** — wipes PII from memory after form submission

**Relevant for production**: Required for DPDP Act compliance (India's data protection law).

---

## 7. `dashboard/app.py` — Streamlit Admin Dashboard

**Access:** `http://localhost:8501` (when Streamlit is running)

Currently shows mostly empty/demo data. Full power requires Audit MCP running:

- **Live session map**: See every active user → current node in pipeline
- **Form fill success rate**: Which forms succeed, which fail, latency per node
- **PII audit log**: What data was touched, for whom, when (redacted)
- **Screenshot gallery**: Last Playwright screenshot per session
- **WebSocket viewer**: Live browser stream embedded in dashboard

---

## Activation Checklist (Demo → Real)

```
Step 1 — Enable real LLMs
  □ Get NVIDIA NIM API key from build.nvidia.com (free tier available)
  □ Add NVIDIA_API_KEY=nvapi-... to .env

Step 2 — Enable real DigiLocker
  □ Register at developers.digilocker.gov.in
  □ Add DIGILOCKER_CLIENT_ID, DIGILOCKER_CLIENT_SECRET to .env
  □ Change _get_demo_data() call in graph.py to hit DigiLocker MCP

Step 3 — Enable WhatsApp
  □ Get a Twilio account → WhatsApp sandbox or paid WABA number
  □ Add TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER to .env
  □ Run ngrok / deploy to get a public URL
  □ Set Twilio webhook → https://your-url.com/webhook

Step 4 — Run all MCP servers
  □ .\start_mcp.ps1  (starts all 4 on ports 8100-8103)
  □ Verify with GET /api/mcp-status

Step 5 — Full project start
  □ .\start.ps1 -All
```

Each step unlocks a new layer of the system. Steps 1–2 alone make the NLP and data-filling production-grade. Steps 3–4 open the WhatsApp channel.

---

*Read `SCALING.md` for database migration, Docker deployment, and cloud hosting after these are working.*

---

## WhatsApp Provider Options

If Twilio sandbox limits are blocking development (error 63038 = daily cap), here are alternatives:

| Provider | Cost | Daily Limit | Notes |
|---|---|---|---|
| **Twilio Sandbox** | Free | ~10 conversations | Easiest to start, resets every 24h |
| **Meta Cloud API** | Free | None | Official, recommended upgrade path |
| **360dialog** | ~€49/mo | None | India-focused production option |
| **whatsapp-web.js** | Free (unofficial) | None | Your own SIM, no business account needed, demo use only |

> Switching to **Meta Cloud API** requires only a new webhook endpoint that parses JSON (Meta format) instead of form-data (Twilio format). All backend graph logic stays identical.

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'whatsapp_bot'`
Always run from inside the `gramsetu/gramsetu/` subfolder, not the repo root:
```powershell
cd gramsetu\gramsetu
python -m whatsapp_bot.main
```

### Twilio error 63038 on outbound replies
Twilio sandbox has a daily unique-conversation limit. **Wait 24 hours** or switch to Meta Cloud API.

### WhatsApp messages received by Twilio but bot never replies
Check in order:
1. Is ngrok running? (`http://localhost:4040`)
2. Is the webhook URL in Twilio sandbox settings pointing to `https://<ngrok-url>/webhook`?
3. Is the backend running on port 8000? (`GET http://localhost:8000/api/health`)
4. Has your phone joined the sandbox? (Send `join <keyword>` to `+14155238886`)
