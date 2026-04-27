<p align="center">
  <h1 align="center">🌾 GramSetu</h1>
  <p align="center">
    <strong>AI-powered government form assistant for rural India</strong><br>
    Voice-first · Multilingual · Zero typing required
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12+-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Next.js-14-black?logo=next.js" alt="Next.js">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-green?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/LangGraph-v3-orange" alt="LangGraph">
  <img src="https://img.shields.io/badge/Docker-ready-blue?logo=docker" alt="Docker">
</p>

---

## What is GramSetu?

GramSetu ("Village Bridge") is an autonomous AI agent that fills Indian government forms on behalf of citizens — in their own language, using their real data from DigiLocker, with **zero manual typing**.

A citizen opens the web app and says: *"राशन कार्ड चाहिए"* (I need a ration card).
GramSetu detects the intent, fetches the citizen's Aadhaar, PAN, and address from DigiLocker, validates every field with deterministic checks, fills the government portal using live browser automation (Playwright), handles the OTP — and sends back a confirmation with a downloadable receipt.

**The user never types their Aadhaar number, address, or any document numbers.**

### Built For

- 🌾 **Rural citizens** who can't navigate complex government portals
- 🗣️ **Voice-first** — speak in Hindi, Tamil, Bengali, or 8 other Indian languages
- 🌐 **Web app** — works on any browser, any device, no app download
- 🔒 **Privacy-first** — PII is encrypted, never logged, Aadhaar displayed as `XXXX-XXXX-1234`

---

## Key Features

| Feature | Description |
|---|---|
| 🗣️ **Realtime Voice STT** | WebSocket-based live transcription via Sarvam AI — speak and see words appear instantly |
| 🤖 **11 Government Forms** | Ration card, PAN, Voter ID, Pension, Ayushman Bharat, MNREGA, PM-KISAN, and more |
| 🔍 **Scheme Discovery** | LLM-powered search across `myscheme.gov.in`, `india.gov.in` to find eligible schemes |
| 🔐 **DigiLocker Auto-Fill** | All personal data fetched automatically — user only confirms |
| 🌐 **Live Browser Automation** | Playwright fills real government portals; live JPEG screenshots stream to the UI |
| ✅ **Deterministic Safety** | Verhoeff checksum for Aadhaar, PAN format validation, cross-field consistency checks |
| 🔊 **Text-to-Speech** | Sarvam Bulbul TTS for spoken responses in 11 Indian languages |
| 🌍 **11 Languages** | Hindi, English, Bengali, Tamil, Telugu, Marathi, Gujarati, Kannada, Malayalam, Punjabi, Urdu |

---

## Architecture

```
User (Web App — Voice / Text)
         │
         ▼
   FastAPI server.py (:8000)
   ┌──────────────────────────────────────────────────────────────┐
   │  /api/chat          — Text conversation                      │
   │  /api/voice         — Audio upload → Sarvam/Groq/NVIDIA STT  │
   │  /api/voice/realtime — WebSocket live STT (Sarvam streaming)  │
   │  /api/schemes       — LLM-powered scheme discovery            │
   │  /api/tts           — Text-to-speech (Sarvam Bulbul)          │
   │  /ws/browser/{id}   — Live Playwright screenshot stream       │
   └──────────────────────────────────────────────────────────────┘
         │
         ▼
   LangGraph v3 State Machine (5 Nodes)
   ┌──────────────────────────────────────────────────────┐
   │  1. TRANSCRIBE     → Sarvam / Groq Whisper / NeMo    │
   │  2. DETECT_INTENT  → Keyword + LLM fallback          │
   │  3. DIGILOCKER     → Auto-fetch all citizen data      │
   │  4. CONFIRM        → User verifies (YES/NO only)      │
   │  5. FILL_FORM      → Playwright live browser fill     │
   └──────────────────────────────────────────────────────┘
         │
         ▼
   Reliability Layer
   ┌──────────────────────────────────────────────────────┐
   │  • Verhoeff checksum (Aadhaar)                        │
   │  • PAN / IFSC / PIN code format validation            │
   │  • Cross-field consistency (name ≠ father, etc.)      │
   │  • Confidence threshold gate (0.98+)                  │
   │  • Human review for risky/low-confidence submissions  │
   │  • Dry-run fill plan before live automation           │
   └──────────────────────────────────────────────────────┘
```

### AI Provider Strategy

| Task | Primary | Fallback |
|---|---|---|
| **Intent Classification** | Groq `llama-3.1-8b-instant` (~50ms) | Keyword-based (instant) |
| **Conversational Chat** | Groq `llama-3.3-70b-versatile` | NVIDIA NIM |
| **Speech-to-Text** | Sarvam Saaras v1 | Groq Whisper Large v3 → NVIDIA Parakeet |
| **Text-to-Speech** | Sarvam Bulbul v1 | — |
| **Scheme Research** | Groq 70B with web search | Local curated database |
| **Field Extraction** | Groq 70B | — |
| **Vision (Portal OCR)** | NVIDIA LLaMA 3.2 11B Vision | Groq Vision Preview |
| **Translation** | Groq 70B | — |

---

## Supported Forms — 11 Types

| Category | Form | Real Portal |
|---|---|---|
| 🏠 Welfare | Ration Card (BPL/APL) | nfsa.gov.in |
| 🏠 Welfare | Old Age / Widow / Disability Pension | nsap.nic.in |
| 🏠 Welfare | Ayushman Bharat PMJAY (₹5L health cover) | pmjay.gov.in |
| 🏠 Welfare | MNREGA Job Card (100 days work) | nrega.nic.in |
| 🪪 Identity | PAN Card | onlineservices.nsdl.com |
| 🪪 Identity | Voter ID | voters.eci.gov.in |
| 🪪 Identity | Caste Certificate (SC/ST/OBC) | services.india.gov.in |
| 🪪 Identity | Birth Certificate | crsorgi.gov.in |
| 🌾 Agriculture | PM-KISAN Samman Nidhi (₹6,000/year) | pmkisan.gov.in |
| 🌾 Agriculture | Kisan Credit Card (farm loans) | kisancreditcard.in |
| 🏦 Banking | Jan Dhan Account (zero balance) | pmjdy.gov.in |

**Adding a new form = 1 Pydantic model + 1 entry in `SCHEMA_REGISTRY`.** Voice, validation, DigiLocker auto-fill, and browser automation work automatically.

---

## Quick Start

### Prerequisites

- **Python 3.12+**
- **Node.js 18+** (for the webapp)
- **Groq API key** — free at [console.groq.com](https://console.groq.com)
- **Sarvam API key** — for Indian-language STT/TTS at [sarvam.ai](https://www.sarvam.ai)
- **NVIDIA NIM API key** (optional) — free at [build.nvidia.com](https://build.nvidia.com)

### Option A: Docker (Recommended)

```bash
# Clone
git clone https://github.com/Vickyrrrrrr/gramsetu.git
cd gramsetu

# Configure
cp .env.example .env
# → Fill in GROQ_API_KEY and SARVAM_API_KEY

# Build and run everything
docker compose up --build
```

- **Backend**: http://localhost:8000
- **Web App**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs

### Option B: Local Development

```bash
# Clone
git clone https://github.com/Vickyrrrrrr/gramsetu.git
cd gramsetu

# Python backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt
playwright install chromium

# Configure environment
cp .env.example .env
# → Fill in GROQ_API_KEY and SARVAM_API_KEY

# Start backend
python server.py
# → http://localhost:8000

# Start frontend (new terminal)
cd webapp
npm install
npm run dev
# → http://localhost:3000
```

### Environment Variables

```env
# ── Required ──────────────────────────────────────────
GROQ_API_KEY=gsk_your_key_here        # LLM inference (free tier)
SARVAM_API_KEY=sk_your_key_here       # Indian STT/TTS

# ── Optional ──────────────────────────────────────────
NVIDIA_API_KEY=nvapi-your-key-here    # Vision + ASR fallback
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1

# ── Server ────────────────────────────────────────────
PORT=8000
HOST=0.0.0.0
BACKEND_URL=http://localhost:8000     # Used by Next.js proxy
```

---

## Project Structure

```
gramsetu/
├── server.py                    # FastAPI entrypoint — all API endpoints
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Backend container (uvicorn server:app)
├── docker-compose.yml           # Full-stack: backend + webapp
├── .env.example                 # Environment template
│
├── backend/
│   ├── agents/
│   │   ├── graph.py             # LangGraph 5-node state machine (core pipeline)
│   │   ├── schema.py            # Pydantic models for all 11 forms + SCHEMA_REGISTRY
│   │   ├── portal_registry.py   # Government portal URLs and selectors
│   │   └── form_fill_agent.py   # Playwright browser automation agent
│   │
│   ├── llm_client.py            # Multi-provider LLM client (Groq + NVIDIA + Sarvam)
│   ├── schemes.py               # LLM-powered scheme discovery engine
│   ├── database.py              # SQLite/Supabase storage layer
│   ├── digilocker_client.py     # DigiLocker API client (demo data for now)
│   ├── security.py              # Rate limiter, PII encryption, input sanitization
│   ├── reliability.py           # Deterministic safety layer before automation
│   ├── voice_tts.py             # Text-to-speech (Sarvam Bulbul)
│   ├── sarvam_client.py         # Sarvam AI direct API wrapper
│   └── stagehand_client.py      # Browser fill plan generator
│
├── agent_core/
│   └── validator.py             # Rule-based validators (Aadhaar, PAN, IFSC, DOB, etc.)
│
├── lib/
│   ├── language_utils.py        # Script-based language detection (11 languages)
│   └── voice_handler.py         # Audio transcription (Sarvam → Groq → NVIDIA cascade)
│
├── webapp/                      # Next.js 14 frontend
│   ├── app/app/page.tsx         # Main chat UI (1600+ lines)
│   ├── next.config.js           # API proxy configuration
│   └── Dockerfile               # Frontend container
│
├── public/
│   ├── mock_portal.html         # Pixel-faithful GOI portal replica for demos
│   └── admin.html               # Admin dashboard
│
├── data/
│   ├── checkpoints.db           # LangGraph session checkpoints (SQLite)
│   ├── gramsetu.db              # Application database
│   └── schemes.json             # Fallback scheme data
│
├── deploy/
│   ├── prometheus/              # Prometheus config
│   └── grafana/                 # Grafana dashboards
│
├── tests/                       # Test suite
│
└── .github/workflows/           # CI/CD (lint, test, Docker build, deploy)
```

---

## API Reference

Base URL: `http://localhost:8000`

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/chat` | Send a text message, get AI response |
| `POST` | `/api/voice` | Upload audio file → transcribed text + AI response |
| `WS` | `/api/voice/realtime` | **Realtime STT** — stream PCM audio, get live transcripts |
| `POST` | `/api/otp/{user_id}` | Submit OTP to resume a suspended form session |
| `POST` | `/api/schemes` | Discover eligible government schemes |
| `POST` | `/api/tts` | Text-to-speech (returns audio/wav) |
| `GET` | `/api/mcp-status` | Status of all backend services |
| `GET` | `/api/health` | Health check + active session count |
| `GET` | `/api/impact` | Impact metrics (forms filled, users served) |
| `GET` | `/api/receipt/{id}` | Downloadable HTML receipt for submitted forms |
| `WS` | `/ws/browser/{user_id}` | Live JPEG stream of Playwright browser automation |

### Realtime Voice (WebSocket)

```javascript
// Connect
const ws = new WebSocket('ws://localhost:8000/api/voice/realtime')

// Start session
ws.send(JSON.stringify({ type: 'start', language: 'hi' }))

// Stream 16kHz PCM audio
ws.send(pcmAudioBuffer)  // ArrayBuffer of Int16Array

// Receive transcripts
ws.onmessage = (event) => {
  const data = JSON.parse(event.data)
  // { type: 'transcript', text: 'राशन कार्ड चाहिए', is_final: true }
}

// Stop
ws.send(JSON.stringify({ type: 'stop' }))
```

---

## How It Works — User Flow

```
1. User speaks or types: "I need a ration card" (any language)
         │
         ▼
2. TRANSCRIBE — Sarvam Saaras converts voice → text
         │
         ▼
3. DETECT INTENT — Keywords + LLM identify: form_type = "ration_card"
         │
         ▼
4. DIGILOCKER — Auto-fetch Aadhaar, PAN, address, bank details
         │
         ▼
5. CONFIRM — Show pre-filled form summary with confidence scores
   🟢 High confidence (DigiLocker)  🟡 Estimated  🔴 Needs review
   User says YES or corrects specific fields
         │
         ▼
6. RELIABILITY GATE — Verhoeff checksum, format validation,
   cross-field checks, confidence threshold, human review gate
         │
         ▼
7. FILL FORM — Playwright opens real portal, fills field by field
   Live screenshots stream to the web app via WebSocket
         │
         ▼
8. OTP — Portal asks for OTP → graph SUSPENDS → user sends OTP
         │
         ▼
9. DONE — Confirmation + reference number + downloadable receipt
```

---

## Reliability Layer

GramSetu never trusts the LLM blindly. A deterministic safety layer runs before any live form submission:

| Check | What It Does |
|---|---|
| **Verhoeff Checksum** | Validates Aadhaar numbers mathematically (12-digit + checksum) |
| **PAN Format** | Validates `ABCDE1234F` pattern + holder category letter |
| **IFSC Format** | 4 letters + `0` + 6 alphanumeric |
| **Phone Validation** | 10 digits, starts with 6-9, strips `+91` prefix |
| **PIN Code** | 6 digits, first digit 1-9 |
| **Date of Birth** | Age ≥ 18, ≤ 150, not in future |
| **Cross-Field** | Name ≠ father name, mobile prefix valid, PIN code valid |
| **Confidence Gate** | All fields must be ≥ 98% confidence for auto-submit |
| **Human Review** | Low-confidence, OTP steps, or PII changes require explicit review |
| **Dry-Run Plan** | Generate fill plan before touching real portals |

---

## Voice Support — 11 Languages

| Language | Code | Script Detection |
|---|---|---|
| Hindi | `hi` | Devanagari `\u0900-\u097F` |
| Bengali | `bn` | Bengali `\u0980-\u09FF` |
| Tamil | `ta` | Tamil `\u0B80-\u0BFF` |
| Telugu | `te` | Telugu `\u0C00-\u0C7F` |
| Marathi | `mr` | Devanagari + keyword disambiguation |
| Gujarati | `gu` | Gujarati `\u0A80-\u0AFF` |
| Kannada | `kn` | Kannada `\u0C80-\u0CFF` |
| Malayalam | `ml` | Malayalam `\u0D00-\u0D7F` |
| Punjabi | `pa` | Gurmukhi `\u0A00-\u0A7F` |
| Urdu | `ur` | Arabic `\u0600-\u06FF` |
| English | `en` | Latin (default fallback) |

Language is auto-detected from the Unicode script of the input text. Romanized Hindi/Tamil/Telugu are detected via keyword matching.

---

## Security

| Feature | Implementation |
|---|---|
| **PII Encryption** | Fernet (AES-128-CBC) for all PII in checkpoints |
| **PII Redaction** | Aadhaar shown as `XXXX-XXXX-1234` in logs and UI |
| **Rate Limiting** | 60 req/min per IP (in-memory, no Redis needed) |
| **Input Sanitization** | XSS prevention, control char removal, length limits |
| **OTP Validation** | 4-6 digits only, supports Hindi word-to-digit ("एक दो तीन") |
| **Session Cleanup** | Auto-expire after 24 hours |
| **Git Security** | `.env` gitignored, API keys never committed |

---

## Docker

### Full Stack (Backend + Web App)

```bash
cp .env.example .env
# Fill in API keys
docker compose up --build
```

| Service | Port | Description |
|---|---|---|
| `gramsetu-backend` | 8000 | FastAPI + all endpoints |
| `gramsetu-webapp` | 3000 | Next.js frontend |

### Backend Only

```bash
docker compose up --build backend
```

The backend Dockerfile:
- Uses `python:3.12-slim`
- Installs Chromium via Playwright (for form automation)
- Includes `ffmpeg` for audio processing
- Healthcheck against `/api/health`
- Entrypoint: `uvicorn server:app`

---

## Tests

```bash
python -m pytest tests/ -v
```

---

## Demo Setup

```
Your Laptop
├── FastAPI server.py       →  localhost:8000
└── Next.js web app         →  localhost:3000
```

### Steps

```powershell
# Terminal 1 — Backend
cd gramsetu
.venv\Scripts\activate
python server.py

# Terminal 2 — Frontend
cd gramsetu\webapp
npm run dev
```

### Demo Script

1. Open `localhost:3000` on the big screen
2. Type or speak: *"राशन कार्ड चाहिए"*
3. GramSetu replies in Hindi, identifies the form
4. Say *"हाँ"* (yes) → Playwright browser opens, live form fill begins
5. Screenshots stream into the web app floating preview panel
6. Enter mock OTP → form "submitted" with confirmation + receipt

---

## Contributing

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

MIT

---

<p align="center">
  <strong>Built for the people who need it most.</strong><br>
  GramSetu — bridging the digital divide, one form at a time. 🌾
</p>
