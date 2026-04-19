# GramSetu v3 🌾

> **Autonomous AI agent that fills Indian government forms over WhatsApp — in the user''s own language, using their real data from DigiLocker, with zero typing.**

Built for rural India. Works on **any phone with WhatsApp**. No app download. No form knowledge required.

---

## What It Does

A village farmer sends one WhatsApp message: *"राशन कार्ड चाहिए"*  
GramSetu replies in under 2 seconds, fetches all required data from DigiLocker automatically, fills the government portal form using Playwright (live browser automation visible on screen), handles the OTP, and sends back a confirmation — **the user never types their Aadhaar number, address, or any document numbers**.

---

## Reliability Layer (v2)

GramSetu v2 adds a deterministic safety layer before any live form submission:

- **Normalization first**: values are cleaned into canonical formats before validation.
- **Rule-based validation**: Aadhaar, PAN, mobile, PIN code, DOB and more are validated in pure Python.
- **Cross-field checks**: contradictory values (for example, invalid mobile prefixes or identical applicant/guardian names) are blocked before automation.
- **Final submission gate**: browser automation only starts if required fields are present and the form passes deterministic checks.
- **Human review guard**: low-confidence extraction, OTP steps, or edits to sensitive PII require explicit review.
- **Dry-run browser plan**: the agent can generate a fill plan before touching the real government portal.

This architecture reduces hallucinations by making the LLM responsible for extraction and language understanding, while deterministic code owns correctness and submission safety.


## Edge Cases Covered in v2

GramSetu v2 adds explicit protection for common failure modes in AI-assisted form filling:

- malformed Aadhaar, PAN, phone, PIN code, email and DOB values
- contradictory values across fields
- duplicate values copied into multiple fields
- low-confidence field extraction
- missing required values before submission
- risky automation without human review

The goal is simple: the LLM may suggest values, but deterministic code decides whether submission is safe.


## Production Structure (v2)


## Production package layout

The backend now exposes a cleaner package layout without breaking existing behavior:

```text
backend/
  api/            # request-layer helpers and future route modules
  core/           # settings and shared runtime utilities
  integrations/   # browser, LLM, security, schemes, TTS wrappers
  orchestrator/   # LangGraph flow + typed models
  storage/        # database access facade
  mcp_servers/    # DigiLocker, browser, audit, WhatsApp connectors
```

The original modules remain in place for compatibility, but the application entrypoint now imports through the new package structure so future refactors can move implementation behind stable interfaces.


GramSetu is now organized around the real production flow instead of demo-only helpers:

- `whatsapp_bot/main.py` — FastAPI entrypoint for API, OTP, TTS, health and DigiLocker callback.
- `backend/agents/` — LangGraph workflow, schema validation, and state handling.
- `backend/reliability.py` — deterministic safety checks before live automation.
- `backend/mcp_servers/` — DigiLocker, browser, audit, and WhatsApp integration services.
- `webapp/` — citizen-facing Next.js application.
- `data/` — persistent SQLite checkpoints, audit logs, screenshots, and runtime artifacts.

Removed from the production path:

- `index.html` is treated as an old presentation artifact, not part of the deployed backend.
- `start_demo.ps1` is treated as legacy demo tooling, not part of the container deployment path.
- `backend/llm_client.py.bak` is treated as a stale backup file and excluded from Docker builds.

## Deploy Anywhere (Docker)

Backend only:

```bash
cp .env.example .env
docker compose up --build gramsetu-backend
```

Full stack:

```bash
cp .env.example .env
docker compose --profile fullstack up --build
```

The backend exposes port `8000`, persists runtime state in the `gramsetu_data` volume, and includes a healthcheck against `/api/health` for container orchestration.


## How GramSetu Works

GramSetu follows a real production flow built for low-friction public-service access:

1. **User starts in web app or WhatsApp** — a citizen asks for a service in natural language or voice.
2. **Intent + language detection** — the backend identifies the required form, scheme, or service.
3. **Data collection and prefilling** — the system gathers available user details and prepares structured form data.
4. **Deterministic safety checks** — normalization, field validation, cross-field consistency checks, and low-confidence detection run before live automation.
5. **Human review gate** — risky or incomplete cases are paused for review instead of silently submitting bad data.
6. **Dry-run fill plan** — GramSetu generates a planned field-by-field browser action sequence.
7. **Live portal automation** — only validated submissions continue to browser automation and OTP handling.
8. **Receipt and state tracking** — application progress, reference numbers, and session state are persisted for recovery.
9. **Observability** — metrics flow to Prometheus and dashboards appear in Grafana for backend visibility.

This keeps the LLM responsible for understanding and extraction, while deterministic code owns correctness, reliability, and submission safety.



## Entrypoint refactor

The runtime entrypoint is now intentionally thin:

- `backend/api/app.py` contains the assembled FastAPI application.
- `whatsapp_bot/main.py` is now only a stable launcher for Docker and local CLI usage.

This makes it easier to keep the deployment command stable while continuing to split routes and orchestration logic into smaller backend modules.

## Workflow Startup

The default Docker workflow now starts the full backend runtime needed for GramSetu's real flow:

- `gramsetu-backend` for API, orchestration, OTP flow, and browser automation.
- `gramsetu-redis` for cache, chat-session persistence, and short-lived workflow state.
- `gramsetu-prometheus` for metrics scraping.
- `gramsetu-grafana` for dashboards.

Start the core workflow:

```bash
cp .env.example .env
docker compose up --build
```

Start the core workflow plus the web app:

```bash
docker compose --profile fullstack up --build
```

Start developer tools as well:

```bash
docker compose --profile fullstack --profile devtools up --build
```

## Session Persistence

GramSetu now mirrors active chat sessions into the cache layer so a restart no longer depends only on in-memory dictionaries. Redis is used when available, and the in-memory cache remains as a free fallback for local development.

## Deploy and Run

Backend only:

```bash
cp .env.example .env
docker compose up --build gramsetu-backend gramsetu-redis
```

Full stack with monitoring:

```bash
cp .env.example .env
docker compose --profile fullstack --profile observability up --build
```

Useful endpoints after startup:

- API health: `http://localhost:8000/api/health`
- Liveness: `http://localhost:8000/live`
- Readiness: `http://localhost:8000/ready`
- Metrics: `http://localhost:8000/metrics`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001`

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+ (for the webapp)
- Twilio WhatsApp sandbox (free) or production number
- NVIDIA NIM API key — free at [build.nvidia.com](https://build.nvidia.com)

### 1 — Backend (FastAPI + MCP Servers)

```bash
# Clone
git clone https://github.com/Vickyrrrrrr/gramsetu.git
cd gramsetu

# Create venv and install
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
playwright install chromium

# Copy and configure environment
copy .env.example .env
# → fill in NVIDIA_API_KEY and Twilio keys

# Start everything (FastAPI on :8000 + all 4 MCP servers)
.\start.ps1 -All
```

### 2 — Web App (Next.js)

```bash
cd webapp
npm install
npm run dev    # → http://localhost:3000
```

### 3 — Environment (`.env`)

```env
# NVIDIA NIM — ALL LLM inference (no Gemini needed)
NVIDIA_API_KEY=nvapi-your-key-here
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1

# Purpose-specific NIM models (all free tier)
NIM_MODEL_INTENT=meta/llama-3.1-8b-instruct
NIM_MODEL_CONVERSATIONAL=mistralai/mixtral-8x7b-instruct-v0.1
NIM_MODEL_EXTRACTION=meta/llama-3.1-70b-instruct
NIM_MODEL_GENERAL=meta/llama-3.3-70b-instruct

# Twilio (WhatsApp sandbox — free)
TWILIO_ACCOUNT_SID=ACxxxx
TWILIO_AUTH_TOKEN=xxxx
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
```

---

## Supported Forms — 11 Types

| Category | Form | Real Portal |
|---|---|---|
| Welfare | Ration Card (BPL/APL) | nfsa.gov.in |
| Welfare | Old Age / Widow / Disability Pension | nsap.nic.in |
| Welfare | Ayushman Bharat PMJAY (₹5L health cover) | pmjay.gov.in |
| Welfare | MNREGA Job Card (100 days work) | nrega.nic.in |
| Identity | PAN Card | onlineservices.nsdl.com |
| Identity | Voter ID | voters.eci.gov.in |
| Identity | Caste Certificate (SC/ST/OBC) | services.india.gov.in |
| Identity | Birth Certificate | crsorgi.gov.in |
| Agriculture | PM-KISAN Samman Nidhi (₹6000/year) | pmkisan.gov.in |
| Agriculture | Kisan Credit Card (farm loans) | kisancreditcard.in |
| Banking | Jan Dhan Account (zero balance) | pmjdy.gov.in |

**Adding a new form = 1 Pydantic model + 1 line in `SCHEMA_REGISTRY`.**  
Voice, validation, DigiLocker auto-fill, and Playwright browser automation work automatically.

---

## Architecture

```
WhatsApp message (any language)
         │
         ▼
   FastAPI /webhook  ─────────────────────────────────────────────┐
     (Twilio)          Background task                             │
         │             Empty TwiML ACK < 1ms                      │
         ▼                                                         ▼
   LangGraph v3 State Machine                          4 MCP Tool Servers
   ┌────────────────────────────────────────────────┐  ┌──────────────────┐
   │  1. TRANSCRIBE  → NIM parakeet ASR             │  │ WhatsApp  :8100  │
   │  2. DETECT_INTENT → llama-3.1-8b (fast JSON)   │  │ Browser   :8101  │
   │  3. DIGILOCKER  → OAuth auto-fetch real data    │  │ Audit     :8102  │
   │  4. CONFIRM     → User says YES/NO only         │  │ DigiLocker:8103  │
   │  5. FILL_FORM   → Playwright live browser fill  │  └──────────────────┘
   └────────────────────────────────────────────────┘
         │
         ▼
   Twilio REST API → WhatsApp reply + OTP request
```

### NIM Models — One Per Task

| Task | Model | Why |
|---|---|---|
| Intent classification | `meta/llama-3.1-8b-instruct` | Fastest — JSON output in <0.5s |
| Conversational replies | `mistralai/mixtral-8x7b-instruct-v0.1` | Best multilingual warmth |
| Field extraction | `meta/llama-3.1-70b-instruct` | Precise structured output |
| Scheme research / reasoning | `meta/llama-3.3-70b-instruct` | Best general reasoning |
| Portal OCR / vision | `nvidia/llama-3.2-90b-vision-instruct` | Hindi text on govt portals |
| Voice ASR | `nvidia/parakeet-ctc-1.1b-asr` | Indian-accented speech |

---

## Live Browser Preview (Playwright) — ✅ Working

Playwright opens a real Chromium window (`headless=False`) on the laptop when a form is submitted.  
Judges watch every field typed character-by-character in real time.  
Simultaneously, JPEG screenshots stream via WebSocket (`/ws/browser/{userId}`) to the web app floating panel.

**What the mock portal looks like:**  
`http://localhost:8000/static/public/mock_portal.html` — a pixel-faithful GOI portal replica (navy/orange scheme, Ashoka emblem, all 11 form types, DigiLocker connect button, OTP step).

**To verify it works locally:**
```bash
# 1. Backend must be running
python -m whatsapp_bot.main

# 2. Open webapp
cd webapp && npm run dev

# 3. Go to localhost:3000 → type "I want ration card"
# 4. Playwright window opens on screen, web app shows live preview
```

**Known requirements for Playwright to work:**
- `playwright install chromium` must have been run
- Backend running on port 8000 (mock portal is served from FastAPI static files)
- `headless=False` in graph.py line ~737 (already set)

---

## Hackathon Live Demo Setup

**Everything runs on your laptop — no cloud required for the demo.**

```
Your Laptop
├── FastAPI + 4 MCP servers  →  localhost:8000
├── Next.js web app          →  localhost:3000
└── ngrok tunnel             →  https://xxxx.ngrok-free.app  (WhatsApp webhook only)
```

**Steps before demo:**

```powershell
# Terminal 1 — backend
cd gramsetu
.venv\Scripts\activate
.\start.ps1 -All

# Terminal 2 — web app
cd gramsetu\webapp
npm run dev

# Terminal 3 — ngrok (for WhatsApp to reach your laptop)
ngrok http 8000
# Copy the https URL → Twilio console → WhatsApp sandbox webhook
```

**Demo script for judges:**
1. Project `localhost:3000` (web app) on the big screen
2. Send WhatsApp message from any phone: `"राशन कार्ड चाहिए"`
3. GramSetu replies in Hindi instantly
4. Say `"हाँ"` (yes) → Playwright browser opens on laptop — judges see live form fill
5. Screenshot streams into the web app floating preview panel in real time
6. Enter the mock OTP → form "submitted" with confirmation message

> ⚠️ Keep laptop plugged in and on a stable WiFi or hotspot. Playwright is CPU-heavy.

---

## Deploying the Web App to Vercel (Backend Stays on Laptop)

**You can deploy Next.js to Vercel, but there are important limitations.**

The `webapp/next.config.js` rewrites `/api/*` and `/ws/*` to `http://localhost:8000`.  
On Vercel, `localhost` is the Vercel server — not your laptop. You must change it to your ngrok URL.

**Step 1 — Update `webapp/next.config.js`:**

```js
const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

const nextConfig = {
  async rewrites() {
    return [
      { source: '/api/:path*', destination: `${BACKEND}/api/:path*` },
      // ⚠️ Remove the /ws rewrite — Vercel serverless can't proxy WebSockets
    ]
  },
}
module.exports = nextConfig
```

**Step 2 — Vercel Environment Variables:**
```
NEXT_PUBLIC_BACKEND_URL = https://your-ngrok-url.ngrok-free.app
```

**Step 3 — Deploy:**
```bash
cd webapp
npx vercel --prod
```

**What works on Vercel + ngrok backend:**
| Feature | Works? | Notes |
|---|---|---|
| Chat `/api/chat` | ✅ | Via ngrok proxy |
| Voice input `/api/voice` | ✅ | Via ngrok proxy |
| MCP status panel | ✅ | Via ngrok proxy |
| Scheme discovery | ✅ | Via ngrok proxy |
| Screenshot viewer | ✅ | Static PNG after fill |
| **Live browser preview WebSocket** | ❌ | Vercel serverless = no WS |
| **Playwright form fill** | ✅ | Runs on your laptop, not Vercel |

> **For the hackathon demo, running everything on `localhost` is simpler and more reliable.**  
> Use Vercel only to share a public URL after the event.

---

## Security

- Twilio HMAC signature validation on every webhook
- AES encryption for PII in transit
- PII never written to logs — Aadhaar shown as `XXXX-XXXX-1234`
- Rate limiting: 10 messages/minute per phone number
- OTP validated as 4–6 digits only before graph resume
- SQLite checkpoint — sessions survive server restarts
- `.env` is gitignored — API keys never committed

---

## Voice Support — 11 Indian Languages (FREE, No API Key)

All TTS via Microsoft Edge TTS.

| Language | Code | Female | Male |
|---|---|---|---|
| Hindi | `hi` | SwaraNeural | MadhurNeural |
| Bengali | `bn` | TanishaaNeural | BashkarNeural |
| Tamil | `ta` | PallaviNeural | ValluvarNeural |
| Telugu | `te` | ShrutiNeural | MohanNeural |
| Marathi | `mr` | AarohiNeural | ManoharNeural |
| Gujarati | `gu` | DhwaniNeural | NiranjanNeural |
| Kannada | `kn` | SapnaNeural | GaganNeural |
| Malayalam | `ml` | SobhanaNeural | MidhunNeural |
| Punjabi | `pa` | OjasNeural | VaaniNeural |
| Urdu | `ur` | GulNeural | SalmanNeural |
| English (IN) | `en` | NeerjaNeural | PrabhatNeural |

---

## API Reference

Base URL: `http://localhost:8000`

| Method | Endpoint | Description |
|---|---|---|
| POST | `/webhook` | Twilio WhatsApp webhook |
| POST | `/api/chat` | Direct chat API (no WhatsApp needed) |
| POST | `/api/otp/{user_id}` | Submit OTP to resume suspended form session |
| POST | `/api/schemes` | Scheme eligibility discovery |
| POST | `/api/voice` | Audio upload → transcribed text |
| GET | `/api/mcp-status` | Live status of all 4 MCP servers |
| GET | `/api/screenshot/{form}/{session}` | Latest Playwright screenshot PNG |
| GET | `/api/audit-logs` | Full audit trail (PII-redacted) |
| GET | `/api/health` | Health check + active session count |
| GET | `/api/impact` | Impact metrics |
| WS | `/ws/browser/{user_id}` | Live JPEG stream of browser form fill |

---

## Dashboard

```bash
streamlit run dashboard/app.py
# → http://localhost:8501
```

Live conversation log · form submission queue · per-agent latency heatmap · PII access audit trail · district impact counters.

---

## Tests

```bash
python -m pytest tests/ -v
```

---

## Project Docs

| File | Content |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Beginner-friendly explanation of the project structure, demo mode, real mode, servers, and LangGraph flow |
| [API_GUIDE.md](API_GUIDE.md) | Full API usage with curl examples |
| [WHATSAPP_SETUP.md](WHATSAPP_SETUP.md) | Twilio sandbox + ngrok setup |
| [SERVER_GUIDE.md](SERVER_GUIDE.md) | All server processes, ports, troubleshooting |


## Free-now infrastructure

GramSetu v2 is now set up for a **free-first deployment path**:

- Backend runs in a single Python container.
- Redis is included for future-safe caching and session coordination.
- Prometheus and Grafana are wired through Docker Compose for observability.
- The backend still falls back safely if Redis is unavailable, which helps on low-cost or local setups.

Useful commands:

```bash
# Backend + Redis only
docker compose up --build gramsetu-backend gramsetu-redis

# Add web app
docker compose --profile fullstack up --build

# Add monitoring stack
docker compose --profile observability up --build
```
