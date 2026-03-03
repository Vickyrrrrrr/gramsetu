# GramSetu — Server & Startup Guide

> Complete guide to every server in GramSetu, what it does, how to start it, and how they connect.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        GramSetu v3 System                            │
│                                                                      │
│  ┌────────────────┐    ┌──────────────────────────────────────────┐  │
│  │  Next.js Web   │───▶│  FastAPI Backend (Port 8000)             │  │
│  │  (Port 3000)   │    │  ├── /api/chat        (LangGraph)       │  │
│  └────────────────┘    │  ├── /api/schemes     (Discovery)       │  │
│                        │  ├── /api/health      (Status)          │  │
│  ┌────────────────┐    │  ├── /api/tts         (Voice)           │  │
│  │  WhatsApp Bot  │───▶│  ├── /webhook         (Twilio)          │  │
│  │  (Twilio)      │    │  └── /static/*        (Mock Portal)     │  │
│  └────────────────┘    └──────────┬───────────────────────────────┘  │
│                                   │                                  │
│               ┌───────────────────┼───────────────────┐              │
│               ▼                   ▼                   ▼              │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐     │
│  │ WhatsApp MCP     │ │ Browser MCP      │ │ Audit MCP        │     │
│  │ Port 8100        │ │ Port 8101        │ │ Port 8102        │     │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘     │
│                                                                      │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐     │
│  │ DigiLocker MCP   │ │ Streamlit Dash   │ │ ngrok Tunnel     │     │
│  │ Port 8103        │ │ Port 8501        │ │ Port 4040 (admin)│     │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Quick Start (Recommended)

### Option A — One Command (Everything)
```powershell
cd gramsetu
.\start.ps1 -All
```
This starts **all** servers: MCP servers, ngrok tunnel, Next.js webapp, Streamlit dashboard, and the FastAPI backend.

### Option B — Selective Start
```powershell
# Development (hot-reload ON)
.\start.ps1

# Production demo (hot-reload OFF, stable)
.\start.ps1 -Prod

# Production + WhatsApp tunnel + webapp
.\start.ps1 -Prod -Ngrok -Webapp

# Just MCP servers in the background
.\start_mcp.ps1
```

### Option C — Start Each Server Manually
See the per-server sections below.

---

## Server Reference

### 1. FastAPI Backend — Port 8000

| Item | Detail |
|------|--------|
| **File** | `whatsapp_bot/main.py` |
| **Role** | Central API server — routes all requests, runs LangGraph pipeline, serves static files |
| **Start** | `.\start.ps1` (runs as foreground process) |
| **Manual Start** | `.venv\Scripts\python.exe -m uvicorn whatsapp_bot.main:app --host 0.0.0.0 --port 8000 --workers 1` |

**What it does:**
- Receives WhatsApp messages from Twilio via `/webhook`
- Runs the 5-node LangGraph autonomous pipeline (detect intent → DigiLocker fetch → confirm → fill form → OTP)
- Serves the web chat API at `/api/chat` for the Next.js frontend
- Discovers government schemes at `/api/schemes`
- Handles text-to-speech at `/api/tts`
- Serves static files (including the mock portal) at `/static/*`
- Tracks sessions, impact metrics, and form submissions

**API Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/webhook` | Twilio WhatsApp incoming messages |
| `POST` | `/api/chat` | Web chat — send `{message, user_id, phone, form_type?}` |
| `POST` | `/api/otp/{user_id}` | Submit OTP for a paused session |
| `POST` | `/api/schemes` | Discover matching government schemes |
| `GET` | `/callback/digilocker` | DigiLocker OAuth redirect |
| `POST` | `/api/tts` | Text-to-speech audio generation |
| `POST` | `/api/status` | Update application status |
| `GET` | `/api/impact` | Public impact metrics |
| `GET` | `/api/logs` | Recent log entries |
| `GET` | `/api/conversations` | List WhatsApp conversations |
| `GET` | `/api/submissions` | All form submissions |
| `GET` | `/api/submissions/pending` | Pending submissions |
| `GET` | `/api/stats` | Aggregated statistics |
| `POST` | `/api/confirm/{id}` | Confirm a submission |
| `POST` | `/api/reject/{id}` | Reject a submission |
| `GET` | `/api/graph/state/{user_id}` | LangGraph state for a user |
| `GET` | `/api/health` | Health check + system status |
| `GET` | `/` | Serves `index.html` landing page |

**Test it:**
```powershell
Invoke-WebRequest http://localhost:8000/api/health -UseBasicParsing | Select-Object -ExpandProperty Content
# → {"status":"ok","version":"v3","nvidia_nim":"connected","graph_engine":"langgraph","active_sessions":0,"forms_filled":0}
```

---

### 2. Next.js Web App — Port 3000

| Item | Detail |
|------|--------|
| **Directory** | `webapp/` |
| **Role** | Modern web interface for users to chat with GramSetu (alternative to WhatsApp) |
| **Start** | `.\start.ps1 -Webapp` |
| **Manual Start** | `cd webapp; npm install; npm run dev` |

**What it does:**
- Landing page at `/` with editorial design (scheme overview, language support, 3-step guide)
- AI chat interface at `/app` — open-ended conversation with the LangGraph agent
- Proxies all `/api/*` requests to the FastAPI backend (via `next.config.js` rewrites)
- Quick-action chips for common tasks (ration card, pension, Ayushman Bharat, etc.)
- Mobile-first responsive design with Tailwind CSS + framer-motion animations

**Tech Stack:** Next.js 14, TypeScript, Tailwind CSS, framer-motion, lucide-react

**Test it:**
```powershell
Invoke-WebRequest http://localhost:3000 -UseBasicParsing | Select-Object StatusCode
# → 200
```

---

### 3. WhatsApp MCP Server — Port 8100

| Item | Detail |
|------|--------|
| **File** | `backend/mcp_servers/whatsapp_mcp.py` |
| **Role** | Exposes WhatsApp communication tools to the LangGraph agent via MCP protocol |
| **Start** | `.\start_mcp.ps1` or `.\start.ps1 -MCP` |
| **Manual Start** | `.venv\Scripts\python.exe -m backend.mcp_servers.whatsapp_mcp` |
| **SSE Endpoint** | `http://localhost:8100/sse` |

**Tools exposed:**
| Tool | Purpose |
|------|---------|
| `send_text_message` | Send a text reply to a user on WhatsApp via Twilio |
| `send_streaming_reply` | Stream a long response in chunks |
| `download_media` | Download voice notes / images from Twilio media URLs |
| `request_otp` | Ask the user for OTP and signal `WAIT_OTP` to the graph |
| `detect_language` | Detect Hindi / English / Hinglish from text |

---

### 4. Browser MCP Server — Port 8101

| Item | Detail |
|------|--------|
| **File** | `backend/mcp_servers/browser_mcp.py` |
| **Role** | Playwright-based browser automation with Vision-Language Model (VLM) navigation |
| **Start** | `.\start_mcp.ps1` or `.\start.ps1 -MCP` |
| **Manual Start** | `.venv\Scripts\python.exe -m backend.mcp_servers.browser_mcp` |
| **SSE Endpoint** | `http://localhost:8101/sse` |

**Tools exposed:**
| Tool | Purpose |
|------|---------|
| `launch_browser` | Start a Chromium session (headless or visible) |
| `navigate_to_url` | Go to a government portal URL |
| `vision_find_element` | Use VLM to locate a form field by visual label (no CSS selectors) |
| `vision_click` | Click at coordinates found by the VLM |
| `vision_type` | Type text at coordinates found by the VLM |
| `take_screenshot` | Capture current page for VLM analysis |
| `detect_otp_page` | Check if the portal is requesting OTP |
| `submit_otp` | Enter OTP into the portal |
| `close_browser` | Clean up browser resources |

**Dependency:** Requires Playwright + Chromium installed:
```powershell
.venv\Scripts\pip.exe install playwright==1.49.0
.venv\Scripts\python.exe -m playwright install chromium
```

---

### 5. Audit MCP Server — Port 8102

| Item | Detail |
|------|--------|
| **File** | `backend/mcp_servers/audit_mcp.py` |
| **Role** | Real-time audit logging and observability — tracks every agent decision with confidence scores |
| **Start** | `.\start_mcp.ps1` or `.\start.ps1 -MCP` |
| **Manual Start** | `.venv\Scripts\python.exe -m backend.mcp_servers.audit_mcp` |
| **SSE Endpoint** | `http://localhost:8102/sse` |
| **Database** | `data/audit.db` (SQLite, async) |

**Tools exposed:**
| Tool | Purpose |
|------|---------|
| `log_reasoning` | Log an agent decision with confidence score |
| `log_pii_access` | Record when Personal Identifiable Information is accessed |
| `get_audit_trail` | Retrieve the full audit trail for a session |
| `get_agent_metrics` | Dashboard metrics (latency, confidence distribution, etc.) |
| `redact_pii` | Mask PII fields for safe display (Aadhaar → XXXX-XXXX-1234) |

---

### 6. DigiLocker MCP Server — Port 8103

| Item | Detail |
|------|--------|
| **File** | `backend/mcp_servers/digilocker_mcp.py` |
| **Role** | Autonomous data extraction from DigiLocker — pulls all user documents without manual entry |
| **Start** | `.\start_mcp.ps1` or `.\start.ps1 -MCP` |
| **Manual Start** | `.venv\Scripts\python.exe -m backend.mcp_servers.digilocker_mcp` |
| **SSE Endpoint** | `http://localhost:8103/sse` |

**Tools exposed:**
| Tool | Purpose |
|------|---------|
| `send_digilocker_auth_link` | Send DigiLocker OAuth URL to user on WhatsApp |
| `check_auth_status` | Poll whether the user completed DigiLocker login |
| `fetch_aadhaar_data` | Pull Aadhaar details (name, DOB, address, photo) |
| `fetch_pan_data` | Pull PAN card details |
| `fetch_driving_license` | Pull Driving License details |
| `fetch_all_documents` | Pull ALL available documents at once |
| `extract_form_fields` | Map DigiLocker data → government form fields automatically |

---

### 7. Streamlit Dashboard — Port 8501 (Optional)

| Item | Detail |
|------|--------|
| **File** | `dashboard/app.py` |
| **Role** | Live admin dashboard showing audit trail, agent reasoning, and form-fill progress |
| **Start** | `.\start.ps1 -Dashboard` |
| **Manual Start** | `.venv\Scripts\streamlit.exe run dashboard\app.py --server.port 8501` |

---

### 8. ngrok Tunnel (Optional)

| Item | Detail |
|------|--------|
| **Role** | Exposes `localhost:8000` to the internet so Twilio can send WhatsApp webhooks |
| **Start** | `.\start.ps1 -Ngrok` |
| **Manual Start** | `ngrok http 8000` |
| **Admin UI** | `http://localhost:4040` |

After ngrok starts, copy the HTTPS URL and set it as your Twilio webhook:
```
Twilio Console → Messaging → Sandbox → WHEN A MESSAGE COMES IN → https://xxxx.ngrok-free.app/webhook
```

---

### 9. Mock Government Portal (Static)

| Item | Detail |
|------|--------|
| **File** | `public/mock_portal.html` |
| **URL** | `http://localhost:8000/static/public/mock_portal.html` |
| **Role** | Realistic fake government portal for demo — Playwright fills this form visibly |

**What it does:**
- Simulates a National Government Services Portal (ministry header, sidebar, form fields)
- Accepts URL params to pre-fill fields: `?form_type=ration_card&full_name=Ram+Kumar&...`
- Has declaration checkbox, "Send OTP" button, and success overlay
- All `<input name="...">` attributes match DigiLocker field names for Playwright auto-fill
- Supports 11 form types: Ration Card, Pension, Ayushman Bharat, PM-KISAN, PAN Card, Voter ID, etc.

---

## Port Reference Table

| Port | Server | Protocol | Required? |
|------|--------|----------|-----------|
| **8000** | FastAPI Backend | HTTP/REST | **Yes** — core server |
| **3000** | Next.js Webapp | HTTP | Optional — web UI |
| **8100** | WhatsApp MCP | SSE (MCP) | Optional — WhatsApp tools |
| **8101** | Browser MCP | SSE (MCP) | Optional — Playwright VLM |
| **8102** | Audit MCP | SSE (MCP) | Optional — logging |
| **8103** | DigiLocker MCP | SSE (MCP) | Optional — document extraction |
| **8501** | Streamlit Dashboard | HTTP | Optional — admin panel |
| **4040** | ngrok Admin | HTTP | Optional — tunnel UI |

---

## Startup Order

For a **full demo**, start in this order:

```
1. MCP Servers (8100–8103)     ← background, takes ~2 seconds
2. FastAPI Backend (8000)      ← foreground, blocks terminal
3. Next.js Webapp (3000)       ← separate terminal
4. ngrok (optional)            ← only if showing WhatsApp
```

The `.\start.ps1 -All` script does this automatically.

---

## Stopping Servers

```powershell
# Stop MCP servers (background jobs)
.\start_mcp.ps1 -Stop

# Stop FastAPI backend
# Press Ctrl+C in the terminal running start.ps1

# Stop Next.js
# Press Ctrl+C in the webapp terminal

# Kill everything (nuclear option)
Stop-Process -Name "python" -ErrorAction SilentlyContinue
Stop-Process -Name "node" -ErrorAction SilentlyContinue
Stop-Process -Name "ngrok" -ErrorAction SilentlyContinue
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your keys:

```powershell
Copy-Item .env.example .env
```

| Variable | Purpose | Where to get it |
|----------|---------|-----------------|
| `GEMINI_API_KEY` | LLM inference (Gemini 2.0 Flash) | [Google AI Studio](https://aistudio.google.com/apikey) |
| `NVIDIA_API_KEY` | NVIDIA NIM (Llama 3.1 + VLM) | [build.nvidia.com](https://build.nvidia.com) |
| `GROQ_API_KEY` | Fast inference fallback | [console.groq.com](https://console.groq.com) |
| `TWILIO_ACCOUNT_SID` | WhatsApp integration | [twilio.com](https://www.twilio.com/try-twilio) |
| `TWILIO_AUTH_TOKEN` | WhatsApp integration | Twilio Console |
| `TWILIO_WHATSAPP_NUMBER` | WhatsApp sender number | Twilio Sandbox |
| `DIGILOCKER_CLIENT_ID` | DigiLocker API | [developers.digilocker.gov.in](https://developers.digilocker.gov.in) |
| `USE_V3_GRAPH` | Enable LangGraph v3 pipeline | Set to `true` (default) |

---

## Data Flow: How a Form Gets Filled

```
User sends "ration card chahiye" (via WhatsApp or Web)
         │
         ▼
    ┌─────────────┐
    │ detect_intent│  ← LLM determines: form_fill + ration_card
    └──────┬──────┘
           ▼
    ┌──────────────────┐
    │ digilocker_fetch │  ← Pulls Aadhaar/PAN data from DigiLocker MCP (8103)
    └──────┬───────────┘
           ▼
    ┌──────────────┐
    │   confirm    │  ← Shows extracted data, asks "Is this correct? YES/NO"
    └──────┬───────┘
           ▼ (user sends YES)
    ┌──────────────┐
    │  fill_form   │  ← Playwright opens Chromium → navigates mock portal
    │              │     → fills all fields → takes screenshot → waits for OTP
    └──────┬───────┘
           ▼ (user sends 6-digit OTP)
    ┌──────────────┐
    │  fill_form   │  ← Submits OTP → form completed → sends confirmation
    └──────────────┘
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: playwright` | `.venv\Scripts\pip.exe install playwright==1.49.0` |
| Chromium not found | `.venv\Scripts\python.exe -m playwright install chromium` |
| Port 8000 already in use | `Stop-Process -Name "python" -ErrorAction SilentlyContinue` |
| MCP server won't start | Check `.venv` exists: `Test-Path .venv\Scripts\python.exe` |
| ngrok URL not showing | Open `http://localhost:4040` manually |
| WhatsApp not receiving messages | Verify Twilio webhook URL includes `/webhook` suffix |
| `NVIDIA_API_KEY` errors | Get free key at [build.nvidia.com](https://build.nvidia.com) |
| Next.js build fails | `cd webapp; Remove-Item -Recurse node_modules; npm install` |
| Hot-reload killing server | Use `-Prod` flag: `.\start.ps1 -Prod` |

---

## File Structure Quick Reference

```
gramsetu/
├── whatsapp_bot/main.py          ← FastAPI server (port 8000)
├── backend/agents/graph.py       ← LangGraph 5-node pipeline
├── backend/agents/schema.py      ← Pydantic state schema
├── backend/mcp_servers/
│   ├── whatsapp_mcp.py           ← Port 8100
│   ├── browser_mcp.py            ← Port 8101
│   ├── audit_mcp.py              ← Port 8102
│   └── digilocker_mcp.py         ← Port 8103
├── webapp/                       ← Next.js web app (port 3000)
│   ├── app/page.tsx              ← Landing page
│   └── app/app/page.tsx          ← AI chat interface
├── public/mock_portal.html       ← Fake govt portal for Playwright
├── dashboard/app.py              ← Streamlit dashboard (port 8501)
├── data/
│   ├── schemes.json              ← Government scheme database
│   ├── screenshots/              ← Playwright form-fill screenshots
│   └── forms/                    ← JSON form schemas (12 forms)
├── start.ps1                     ← One-click startup script
├── start_mcp.ps1                 ← MCP-only startup script
├── .env                          ← API keys and config
└── requirements.txt              ← Python dependencies
```
