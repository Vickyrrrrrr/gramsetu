# 🌾 GramSetu — Post-Hackathon Scaling Guide

> **Current State:** Local Python monolith + SQLite, Twilio sandbox, demo DigiLocker mock data.  
> **Target State:** Cloud-native, multi-tenant, production-grade, serving millions of rural users across India.

---

## Table of Contents

1. [Architecture Overview (What You Built)](#1-architecture-overview)
2. [What Changes First — Priority Order](#2-what-changes-first)
3. [Phase 1 — Harden the Backend (Week 1–2)](#3-phase-1-harden-the-backend)
4. [Phase 2 — Real DigiLocker Integration](#4-phase-2-real-digilocker-integration)
5. [Phase 3 — Cloud Deployment](#5-phase-3-cloud-deployment)
6. [Phase 4 — Scale the WhatsApp Channel](#6-phase-4-scale-the-whatsapp-channel)
7. [Phase 5 — LLM & AI Optimization](#7-phase-5-llm--ai-optimization)
8. [Phase 6 — Observability & Security](#8-phase-6-observability--security)
9. [Phase 7 — Multi-State Expansion](#9-phase-7-multi-state-expansion)
10. [Infrastructure Reference](#10-infrastructure-reference)
11. [Environment Variables Checklist](#11-environment-variables-checklist)

---

## 1. Architecture Overview

### What You Built (Hackathon v3)

```
WhatsApp User
     │
     ▼
Twilio Sandbox ──► FastAPI (whatsapp_bot/main.py)  :8000
                        │
                        ▼
               LangGraph 5-Node Pipeline (backend/agents/graph.py)
               ┌──────────────────────────────────────────────┐
               │  1. TRANSCRIBE  (NVIDIA NeMo ASR)            │
               │  2. DETECT_INTENT (Keyword → LLM fallback)   │
               │  3. DIGILOCKER_FETCH (demo mock today)        │
               │  4. CONFIRM (user says YES/NO)                │
               │  5. FILL_FORM (Playwright + VLM)             │
               └──────────────────────────────────────────────┘
                        │
                 SQLite Checkpoint DB (data/checkpoints.db)
                        │
               4 MCP Servers  (ports 8100–8103)
               ┌───────────────────────────────┐
               │ whatsapp_mcp  :8100           │
               │ browser_mcp   :8101           │
               │ audit_mcp     :8102           │
               │ digilocker_mcp:8103           │
               └───────────────────────────────┘
                        │
               Next.js Webapp  :3000
               Streamlit Dashboard :8501
```

### Current Limitations (Be Honest)

| Area | Hackathon State | Production Needed |
|------|----------------|-------------------|
| Database | SQLite file | PostgreSQL / Cloud SQL |
| Sessions | In-memory `dict` | Redis / Memcached |
| Checkpoints | SQLite | PostgreSQL-backed LangGraph |
| DigiLocker | Mock demo data | Real OAuth 2.0 API |
| WhatsApp | Twilio sandbox | Twilio paid or WABA |
| Playwright | `headless=False` (visible) | `headless=True` on server |
| Deployment | `localhost` | Docker + Cloud Run / EKS |
| LLM | Keyword fallback ≫ NIM | NIM primary + caching |
| Auth | None | JWT + Twilio HMAC (partially done) |
| Multi-tenancy | Single server | Horizontal scaling |

---

## 2. What Changes First — Priority Order

```
Urgency: 🔴 Critical  🟡 Important  🟢 Nice to have

🔴  Replace SQLite with PostgreSQL
🔴  Replace in-memory sessions with Redis
🔴  Make DigiLocker integration REAL (not demo)
🔴  Switch Twilio sandbox → paid WABA number
🔴  Containerize with Docker
🟡  Deploy to Cloud Run or Railway
🟡  Add rate limiting per user (partially done)
🟡  Playwright headless=True + serverless-chrome
🟡  Structured logging + error alerting
🟡  Environment secrets via Vault / Secret Manager
🟢  Multi-language TTS expansion
🟢  Admin web panel beyond Streamlit
🟢  Analytics pipeline (BigQuery / ClickHouse)
🟢  Offline-capable Progressive Web App
```

---

## 3. Phase 1 — Harden the Backend (Week 1–2)

### 3.1 Replace SQLite with PostgreSQL

**Files to change:**
- `data/db.py` — swap `sqlite3` → `asyncpg` / `SQLAlchemy async`
- `backend/agents/graph.py` — swap `SqliteSaver` → `PostgresSaver`
- `backend/mcp_servers/audit_mcp.py` — swap audit DB connection

```bash
pip install asyncpg langgraph-checkpoint-postgres psycopg2-binary
```

**LangGraph PostgreSQL checkpoint:**
```python
# Instead of:
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
async with AsyncSqliteSaver.from_conn_string("data/checkpoints.db") as saver:

# Use:
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
async with AsyncPostgresSaver.from_conn_string(os.getenv("DATABASE_URL")) as saver:
```

**Add to `.env`:**
```env
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/gramsetu
```

---

### 3.2 Replace In-Memory Sessions with Redis

**Problem:** `_user_sessions: dict` in `whatsapp_bot/main.py` is lost on every restart. With multiple workers it's wrong.

```bash
pip install redis[asyncio]
```

```python
# whatsapp_bot/main.py — replace _user_sessions dict
import redis.asyncio as redis

redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))

async def get_session(phone: str) -> dict:
    data = await redis_client.get(f"session:{phone}")
    return json.loads(data) if data else {}

async def set_session(phone: str, session: dict):
    await redis_client.setex(f"session:{phone}", 21600, json.dumps(session))  # 6hr TTL
```

**Add to `.env`:**
```env
REDIS_URL=redis://localhost:6379
```

---

### 3.3 Switch Playwright to Headless

**File:** `backend/agents/graph.py`, line ~756

```python
# Change:
browser = await pw.chromium.launch(headless=False)  # visible for judges!

# To:
browser = await pw.chromium.launch(
    headless=True,
    args=["--no-sandbox", "--disable-dev-shm-usage"]
)
```

> ⚠️ On Cloud Run / Docker you'll also need `playwright install chromium --with-deps` in your Dockerfile.

---

### 3.4 Add Proper Uvicorn Workers

**Current (dev):**
```bash
uvicorn whatsapp_bot.main:app --host 0.0.0.0 --port 8000 --reload
```

**Production:**
```bash
uvicorn whatsapp_bot.main:app --host 0.0.0.0 --port 8000 --workers 4 --no-access-log
# or with Gunicorn:
gunicorn -w 4 -k uvicorn.workers.UvicornWorker whatsapp_bot.main:app
```

---

## 4. Phase 2 — Real DigiLocker Integration

Currently `digilocker_fetch_node` calls `_get_demo_data()` — a mock. Replace it with real OAuth.

### 4.1 Register Your App

1. Go to https://developers.digilocker.gov.in
2. Register → get `CLIENT_ID` and `CLIENT_SECRET`
3. Set redirect URI to `https://yourdomain.com/callback/digilocker`

### 4.2 OAuth Flow (Already Scaffolded)

The `/callback/digilocker` endpoint already exists in `whatsapp_bot/main.py`. You need to:

```python
# backend/mcp_servers/digilocker_mcp.py — replace _get_demo_data() calls

async def fetch_real_digilocker_data(auth_code: str, form_type: str) -> dict:
    """Exchange auth code for token and fetch actual Aadhaar/PAN data."""
    import httpx
    
    # Step 1: Exchange code → token
    token_resp = await httpx.AsyncClient().post(
        "https://api.digitallocker.gov.in/public/oauth2/1/token",
        data={
            "code": auth_code,
            "grant_type": "authorization_code",
            "client_id": os.getenv("DIGILOCKER_CLIENT_ID"),
            "client_secret": os.getenv("DIGILOCKER_CLIENT_SECRET"),
            "redirect_uri": os.getenv("DIGILOCKER_REDIRECT_URI"),
        }
    )
    access_token = token_resp.json()["access_token"]
    
    # Step 2: Fetch Aadhaar eKYC
    aadhaar_resp = await httpx.AsyncClient().get(
        "https://api.digitallocker.gov.in/public/oauth2/1/xml/eaadhaar",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    # Parse XML → extract fields → return structured dict
```

**Add to `.env`:**
```env
DIGILOCKER_CLIENT_ID=your_digilocker_client_id
DIGILOCKER_CLIENT_SECRET=your_digilocker_secret
DIGILOCKER_REDIRECT_URI=https://yourdomain.com/callback/digilocker
```

---

## 5. Phase 3 — Cloud Deployment

### 5.1 Dockerize

**Create `Dockerfile`:**
```dockerfile
FROM python:3.12-slim

# Install Playwright system deps
RUN apt-get update && apt-get install -y \
    wget curl gnupg libnss3 libatk1.0-0 libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium --with-deps

COPY . .
EXPOSE 8000
CMD ["uvicorn", "whatsapp_bot.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

**Create `docker-compose.yml`:**
```yaml
version: "3.9"
services:
  api:
    build: .
    ports: ["8000:8000"]
    environment:
      - DATABASE_URL=postgresql+asyncpg://gramsetu:password@db:5432/gramsetu
      - REDIS_URL=redis://redis:6379
    depends_on: [db, redis]

  webapp:
    build: ./webapp
    ports: ["3000:3000"]
    command: npm run start  # production build

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: gramsetu
      POSTGRES_USER: gramsetu
      POSTGRES_PASSWORD: password
    volumes: [postgres_data:/var/lib/postgresql/data]

  redis:
    image: redis:7-alpine
    volumes: [redis_data:/data]

volumes:
  postgres_data:
  redis_data:
```

### 5.2 Recommended Cloud Platforms

| Platform | Best For | Cost |
|----------|----------|------|
| **Google Cloud Run** | Auto-scaling, serverless containers | Pay per request |
| **Railway.app** | Simplest full-stack deploy | ~$5/mo to start |
| **Fly.io** | Global edge, cheap | ~$3/mo |
| **AWS ECS + RDS** | Enterprise, if you get AWS credits | Variable |
| **Render.com** | Easy Postgres + Redis bundled | ~$7/mo |

**Quick deploy to Railway:**
```bash
npm install -g railway
railway login
railway up
```

### 5.3 Webhook Configuration

After deploy, update Twilio:
```
WhatsApp Sandbox → When A Message Comes In:
  https://YOUR_DOMAIN/webhook  (HTTP POST)
```

---

## 6. Phase 4 — Scale the WhatsApp Channel

### 6.1 Upgrade from Sandbox to Production WABA

- Apply for **WhatsApp Business API** at https://business.whatsapp.com
- Alternatively use **Twilio WhatsApp Business** (same creds, remove sandbox limit)
- Cost: ~₹0.20–0.60 per conversation (24h window)

### 6.2 Handle Concurrent Users

Current flow is synchronous per user. For 1000+ concurrent:

```python
# whatsapp_bot/main.py — already uses BackgroundTasks for voice
# Add a Celery/ARQ queue for heavy Playwright tasks

# Install:
# pip install arq redis

# Create tasks/form_fill.py
async def fill_form_task(ctx, session_id: str, form_data: dict, form_type: str):
    """Async Playwright task — runs in worker pool, not in FastAPI thread."""
    ...
```

### 6.3 Twilio Webhook Timeout Handling

Twilio expects a response **within 15 seconds** or it retries. Currently text messages are synchronous — fine for intent detection (~200ms), but Playwright form filling takes 30–60s.

**Solution:** Move Playwright to background queue, send progress updates via Twilio REST API.

```python
# Already partially done for voice in main.py
# Extend to ALL form-fill operations
background_tasks.add_task(fill_form_background, phone, session_id, form_data)
resp = MessagingResponse()
resp.message("⏳ फ़ॉर्म भरा जा रहा है... 2-3 मिनट में अपडेट मिलेगा।")
return HTMLResponse(content=str(resp), media_type="application/xml")
```

---

## 7. Phase 5 — LLM & AI Optimization

### 7.1 Enable Real NVIDIA NIM (Intent is DISABLED now)

In `graph.py`, `_call_nim()` is a stub that just calls `_fallback_response()`. The keyword system works well enough for hackathon, but for edge cases:

```python
# backend/agents/graph.py — replace _call_nim stub with real call
async def _call_nim(messages, temperature=0.1, max_tokens=256):
    from backend.llm_client import chat_intent
    result = await chat_intent(messages, temperature, max_tokens)
    return result if result else _fallback_response(messages)
```

### 7.2 Add Response Caching

```python
# pip install aiocache
from aiocache import cached

@cached(ttl=3600, key_builder=lambda f, *a, **kw: f"scheme:{kw.get('age')}:{kw.get('occupation')}")
async def discover_schemes(age, gender, income, occupation, language):
    ...
```

### 7.3 Use Vision LLM for Real Portal Navigation

Currently `browser_mcp.py` uses CSS selectors. For dynamic/complex portals:

```python
# backend/mcp_servers/browser_mcp.py
# Enable VLM-guided navigation for portals that change their layout
NVIDIA_VLM_MODEL = os.getenv("NVIDIA_VLM_MODEL", "nvidia/llama-3.2-90b-vision-instruct")

async def vlm_find_field(screenshot_b64: str, field_description: str) -> str:
    """Use vision LLM to locate a form field by description."""
    ...
```

### 7.4 Multi-Language TTS Expansion

Currently `edge-tts` handles 11+ Indian languages. Add voice note replies:

```python
# backend/voice_tts.py — already implemented
# Enable voice replies per user preference
if user_prefers_voice:
    audio_path = await text_to_speech(reply_text, lang)
    await send_whatsapp_audio(phone, audio_path)
```

---

## 8. Phase 6 — Observability & Security

### 8.1 Structured Logging

`structlog` is already in `requirements.txt`. Wire it up:

```python
import structlog
logger = structlog.get_logger(__name__)

logger.info("form_submitted", 
    form_type="ration_card", 
    session_id=session_id, 
    user_district="Varanasi",
    latency_ms=elapsed
)
```

### 8.2 Error Alerting

```bash
pip install sentry-sdk
```

```python
# whatsapp_bot/main.py
import sentry_sdk
sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"), traces_sample_rate=0.1)
```

### 8.3 PII Audit Trail

The `audit_mcp.py` and `security.py` already have the scaffolding. Key things to actually enforce:

- **Never log raw Aadhaar numbers** (already partially done — `XXXX-XXXX-NNNN` masking in `confirm_node`)
- **Encrypt PII at rest** — `cryptography` is in requirements, wire it to DB writes
- **Delete data after 24h** — add a cron job:

```python
# scripts/cleanup.py
async def delete_old_sessions():
    """GDPR/DPDP compliance — purge PII after 24 hours."""
    await db.delete_conversations_older_than(hours=24)
```

### 8.4 JWT Auth for Admin APIs

`python-jose` is already in requirements. Protect `/api/logs`, `/api/submissions`:

```python
from fastapi.security import HTTPBearer
from backend.security import verify_jwt_token

security = HTTPBearer()

@app.get("/api/logs")
async def get_logs(credentials: HTTPCredentials = Depends(security)):
    verify_jwt_token(credentials.credentials)
    return JSONResponse(db.get_audit_logs(100))
```

---

## 9. Phase 7 — Multi-State Expansion

### 9.1 Add New Government Schemes

**File:** `backend/agents/graph.py` — `portal_urls` dict  
**File:** `backend/agents/graph.py` — `_detect_intent_keywords()`  
**File:** `backend/agents/schema.py` — `SCHEMA_REGISTRY`

To add **Ladli Behna Yojana (MP)** for example:
1. Add keyword detection: `"ladli", "behna", "बहना"`
2. Add portal URL: `"ladli_behna": "https://cmladlibahna.mp.gov.in/"`
3. Add form schema to `SCHEMA_REGISTRY`
4. Add DigiLocker field mapping

### 9.2 State-Specific Portals

```python
# backend/agents/schema.py — add state-aware routing
STATE_PORTALS = {
    "maharashtra": {
        "ration_card": "https://rcms.mahafood.gov.in/",
        "caste_certificate": "https://aaplesarkar.mahaonline.gov.in/",
    },
    "uttar_pradesh": {
        "ration_card": "https://fcs.up.gov.in/",
    },
    # ...
}
```

### 9.3 Offline-First WhatsApp Flow

For areas with poor connectivity, keep interaction minimal:
- Compress all text responses to <300 chars where possible
- Don't require internet for intent detection (keyword-only ✅ already done)
- Queue form submissions with retry logic

---

## 10. Infrastructure Reference

### Recommended Stack (Production)

```
                     ┌─────────────────────────────────┐
                     │   Cloudflare (DDoS + CDN)        │
                     └────────────────┬────────────────┘
                                      │
              ┌───────────────────────┼──────────────────────┐
              │                       │                       │
     ┌────────▼────────┐   ┌─────────▼──────────┐  ┌────────▼────────┐
     │  Load Balancer  │   │  Next.js (Vercel)   │  │  Streamlit      │
     │  (Cloud LB)     │   │  webapp :3000        │  │  Dashboard      │
     └────────┬────────┘   └────────────────────┘  └────────────────┘
              │
     ┌────────▼────────────────────────────────────────┐
     │       FastAPI Workers (Cloud Run / ECS)          │
     │   2–10 instances auto-scaled on CPU/RPS          │
     └────┬───────────┬──────────────┬────────────────┘
          │           │              │
   ┌──────▼──┐  ┌─────▼────┐  ┌────▼──────────────┐
   │PostgreSQL│  │  Redis   │  │  NVIDIA NIM API    │
   │(Cloud SQL│  │ (Cache + │  │  (LLM inference)   │
   │/ RDS)   │  │  Sessions)│  └────────────────────┘
   └─────────┘  └──────────┘
```

### Scaling Numbers

| Users | Workers | Redis | PostgreSQL | Monthly Cost (est.) |
|-------|---------|-------|-----------|---------------------|
| 100/day | 1 instance | 1 node | Shared | ~$15 |
| 1,000/day | 2 instances | 1 node | db-g1 | ~$50 |
| 10,000/day | 4 instances | 1 node | db-n1 | ~$200 |
| 100,000/day | Auto-scaled | Cluster | db-n2 | ~$1,500 |

---

## 11. Environment Variables Checklist

Copy `.env.example` → `.env` and fill everything:

```env
# === CRITICAL (must have before launch) ===
DATABASE_URL=postgresql+asyncpg://...         # Replace SQLite
REDIS_URL=redis://...                         # Replace in-memory sessions
NVIDIA_API_KEY=nvapi-...                      # LLM inference (free tier: build.nvidia.com)
TWILIO_ACCOUNT_SID=AC...                      # WhatsApp sender
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_NUMBER=whatsapp:+91...        # Your WABA number

# === IMPORTANT (for real data) ===
DIGILOCKER_CLIENT_ID=...                      # Real DigiLocker OAuth
DIGILOCKER_CLIENT_SECRET=...
DIGILOCKER_REDIRECT_URI=https://yourdomain.com/callback/digilocker

# === OPTIONAL (for observability) ===
SENTRY_DSN=https://...@sentry.io/...          # Error tracking
GROQ_API_KEY=gsk_...                          # LLM fallback

# === FEATURE FLAGS ===
USE_V3_GRAPH=true
HEADLESS_BROWSER=true                         # Set false only for local demos
```

---

## Quick Wins You Can Do This Week

1. **`headless=True`** in `graph.py` — one line change, makes it server-deployable
2. **Docker Compose** — paste the config above, run `docker compose up`
3. **Railway deploy** — `railway up` in 10 minutes, free $5 credit
4. **Real NVIDIA NIM key** — uncomment `_call_nim()` body, massive quality boost
5. **Enable Twilio production number** — remove sandbox join-code requirement for users

---

*Generated from reading the complete GramSetu v3 source code — 2026-03-04*
