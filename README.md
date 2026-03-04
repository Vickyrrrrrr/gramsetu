# GramSetu v3 🌾

> **Autonomous AI agent that fills Indian government forms over WhatsApp — in the user''s own language, using their real data from DigiLocker, with zero typing.**

Built for rural India. Works on **any phone with WhatsApp**. No app download. No form knowledge required.

---

## What It Does

A village farmer sends one WhatsApp message: *"राशन कार्ड चाहिए"*  
GramSetu replies in under 2 seconds, fetches all required data from DigiLocker automatically, fills the government portal form using Playwright (live browser automation visible on screen), handles the OTP, and sends back a confirmation — **the user never types their Aadhaar number, address, or any document numbers**.

---

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
cd gramsetu/gramsetu      # ← must be in this subfolder

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
# Terminal 1 — backend (IMPORTANT: run from the gramsetu subfolder)
cd gramsetu\gramsetu
.venv\Scripts\activate
python -m whatsapp_bot.main
# or for full MCP stack:
.\start.ps1 -All

# Terminal 2 — web app
cd gramsetu\gramsetu\webapp
npm run dev

# Terminal 3 — ngrok (named tunnel, bypasses browser warning page)
# Edit %APPDATA%\Local\ngrok\ngrok.yml to add:
# tunnels:
#   gramsetu:
#     proto: http
#     addr: 8000
#     inspect: false
ngrok start gramsetu
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

## WhatsApp Provider Options

| Provider | Cost | Limit | Best For |
|---|---|---|---|
| **Twilio Sandbox** | Free | ~10 msgs/day cap (error 63038) | Quick testing |
| **Meta Cloud API** | Free | No cap | Hackathon / staging |
| **360dialog** | ~€49/month | Unlimited | Production |
| **whatsapp-web.js** | Free (unofficial) | Your own number | Internal demos only |

> **Switching to Meta Cloud API** is recommended when Twilio sandbox daily cap is hit.  
> Webhook format changes slightly (JSON vs form-data) but routes to the same backend.

---

## Troubleshooting

### Twilio error 63038 — "Daily cap reached"
Twilio sandbox allows only a limited number of unique WhatsApp conversations per day.  
**Fix:** Wait 24 hours for reset, or switch to Meta Cloud API (free, no cap).

### ngrok browser warning page blocking Twilio
Twilio's servers don't send a browser User-Agent, so ngrok may intercept requests with an HTML challenge page.  
**Fix (already applied):** The FastAPI server includes `NgrokBypassMiddleware` that adds the `ngrok-skip-browser-warning: true` header to all responses. Use a named ngrok tunnel with `inspect: false` in `ngrok.yml`.

### `ModuleNotFoundError: No module named 'whatsapp_bot'`
You're running from the wrong directory.  
**Fix:** Always run `python -m whatsapp_bot.main` from inside `gramsetu/gramsetu/`, not the repo root.

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
| [API_GUIDE.md](API_GUIDE.md) | Full API usage with curl examples |
| [WHATSAPP_SETUP.md](WHATSAPP_SETUP.md) | Twilio sandbox + ngrok setup |
| [SERVER_GUIDE.md](SERVER_GUIDE.md) | All server processes, ports, troubleshooting |
