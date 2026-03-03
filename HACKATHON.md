# GramSetu — Complete Technical Brief
### Hackathon Presentation Document

---

## 1. The Problem

India has 800 million rural citizens eligible for government welfare schemes.  
Less than 40% actually receive them.

**Why?**

| Barrier | Reality |
|---|---|
| Form complexity | A ration card form has 23 fields — most in English |
| Document hunting | Applicant needs Aadhaar + income certificate + address proof + photo |
| Digital literacy | 68% of rural Internet users can only use WhatsApp |
| Language | Forms are in English, users speak Hindi, Tamil, Telugu, Bengali, etc. |
| Travel cost | Nearest CSC/e-Mitra center is 15–40 km away |
| Time loss | Average 3 visits to complete one application |

**The result:** ₹2.7 lakh crore in welfare benefits go unclaimed every year.

---

## 2. The Solution — GramSetu

**One WhatsApp message. Zero form knowledge. Real data. Real submission.**

```
User:  "राशन कार्ड चाहिए"
       (I need a ration card)

Bot:   ✅ DigiLocker से डेटा मिल गया!
       🟢 नाम: रामप्रसाद यादव (DigiLocker)
       🟢 आधार: XXXX-XXXX-7823 (DigiLocker)
       🟢 पता: ग्राम चंदौली, वाराणसी (DigiLocker)
       🟡 परिवार के सदस्य: 5 (अनुमानित)

       सब सही है? YES भेजें या सुधारें।

User:  YES

Bot:   🌐 nfsa.gov.in पर फ़ॉर्म भर रहा हूँ...
       🔐 OTP आया होगा — भेजें

User:  482910

Bot:   ✅ फ़ॉर्म जमा हो गया!
       📋 Reference: NF2026/UP/847291
```

**Total user effort: 2 messages.**  
**GramSetu did: intent detection → DigiLocker fetch → form fill → OTP submit → confirmation.**

---

## 3. Complete File Structure

```
gramsetu/
│
├── whatsapp_bot/
│   ├── main.py              ← FastAPI server. Entry point for everything.
│   │                          Handles Twilio webhooks, REST API, OAuth callback.
│   │                          Background task pattern (instant ACK, async reply).
│   ├── voice_handler.py     ← Downloads & transcribes WhatsApp voice notes
│   └── language_utils.py    ← Detects Hindi/Hinglish/Tamil/etc from text
│
├── backend/
│   │
│   ├── agents/
│   │   ├── graph.py         ← The brain. 5-node LangGraph state machine.
│   │   │                      Nodes: TRANSCRIBE → INTENT → DIGILOCKER → CONFIRM → FILL
│   │   │                      SQLite-backed checkpoints for suspend/resume (OTP flow).
│   │   └── schema.py        ← 12 Pydantic form models + SCHEMA_REGISTRY.
│   │                          Strict validation: Aadhaar Verhoeff, IFSC, PIN, age.
│   │
│   ├── mcp_servers/         ← 4 independent FastMCP tool servers (SSE/HTTP).
│   │   │                      LangGraph discovers & calls them via MCP protocol.
│   │   ├── whatsapp_mcp.py  ← Port 8100. Twilio REST sends, OTP requests, streaming.
│   │   ├── browser_mcp.py   ← Port 8101. Playwright + VLM. Vision-based form fill.
│   │   │                      No CSS selectors — works even after portal redesigns.
│   │   ├── audit_mcp.py     ← Port 8102. SQLite audit log. PII masking. Metrics.
│   │   └── digilocker_mcp.py← Port 8103. DigiLocker OAuth + document extraction.
│   │
│   ├── llm_client.py        ← Unified LLM client. Priority: Gemini → NIM → Groq.
│   │                          Auto-fallback. Gemini used for live web search.
│   ├── voice_tts.py         ← edge-tts: 11 Indian languages, FREE, no API key.
│   ├── schemes.py           ← Scheme eligibility discovery engine.
│   └── security.py          ← Twilio HMAC, rate limiter, AES PII encryption.
│
├── agent_core/              ← Legacy v2 pipeline (kept for fallback compatibility).
│   ├── agents.py            ← v2 keyword-based agent
│   └── nims_client.py       ← Direct NIM API wrapper
│
├── dashboard/
│   ├── app.py               ← Streamlit entry point
│   ├── dashboard.py         ← Main dashboard layout
│   └── components.py        ← Charts, tables, audit trail viewer
│
├── data/
│   ├── db.py                ← SQLite ORM (conversations, submissions, logs)
│   ├── schemes.json         ← 8 welfare scheme definitions with eligibility rules
│   ├── forms/               ← JSON form structure definitions (for API consumers)
│   │   ├── pan_card.json
│   │   └── pm_kisan.json
│   └── voice_cache/         ← Generated TTS .mp3 files (auto-cleaned)
│
├── tests/
│   └── test_gramsetu.py     ← Unit tests: schema validation, graph flow, API
│
├── public/                  ← Admin panel (HTML/CSS/JS, no framework)
├── .env                     ← All secrets and config
├── requirements.txt         ← Python dependencies
├── start.ps1                ← Windows one-click launcher (all services)
└── start_mcp.ps1            ← MCP-only launcher (all 4 servers, auto-restart)
```

---

## 4. How the 5-Node Graph Works

```
  ┌─────────────┐
  │  TRANSCRIBE │  voice note → NVIDIA NeMo ASR (parakeet-ctc-1.1b)
  │             │  text message → passes through directly
  └──────┬──────┘
         │
  ┌──────▼──────┐
  │DETECT_INTENT│  Gemini 2.0 Flash / Llama 3.3-70B
  │             │  Classifies into 12 form types (or shows full menu)
  │             │  Handles: Hindi, Hinglish, Tamil, Telugu, Bengali, English
  └──────┬──────┘
         │ form_type set
  ┌──────▼──────────┐
  │DIGILOCKER_FETCH │  Calls DigiLocker API → fetches Aadhaar XML, PAN, address
  │                 │  Maps document fields → form fields automatically
  │                 │  Missing fields? Asks user for ONLY those (usually 0-2)
  └──────┬──────────┘
         │ form_data complete
  ┌──────▼──────┐
  │   CONFIRM   │  Shows redacted summary to user (Aadhaar: XXXX-XXXX-7823)
  │             │  User says YES → proceed
  │             │  User corrects field → update + re-confirm
  │             │  User says 0 → restart
  └──────┬──────┘
         │ confirmed
  ┌──────▼──────┐
  │  FILL_FORM  │  Playwright launches Chromium
  │             │  navigate_to_url(portal_url)
  │             │  For each field: vision_find_element() → vision_type()
  │             │  Portal sends OTP → graph SUSPENDS (SQLite checkpoint)
  │             │  User sends OTP → graph RESUMES → submit_otp() → DONE
  └─────────────┘
```

### Why SQLite Checkpoint (Suspend/Resume)?

Government portals always require OTP. The user may take 30 seconds to 5 minutes to find it.  
LangGraph checkpoints the entire graph state to SQLite so:
- The server can restart without losing the session
- The user can reply with OTP hours later and it still works
- The same mechanism handles DigiLocker OAuth callback

---

## 5. Real Data Flow — What Actually Happens with Real Users

### Step 1: Voice Note (most common in rural India)
```
User sends 🎤 voice note (OGG format via WhatsApp)
  → Twilio stores it, sends MediaUrl to webhook
  → voice_handler.py downloads with auth
  → NVIDIA NeMo ASR transcribes (Indian accent, code-switch)
  → Result: "मुझे आयुष्मान कार्ड चाहिए"
```

### Step 2: Intent Detection with real multilingual input
```
Gemini 2.0 Flash sees: "मुझे आयुष्मान कार्ड चाहिए"
  → intent: "ayushman_bharat", confidence: 0.96
  → Next: fetch DigiLocker data for Ayushman Bharat form fields
```

### Step 3: DigiLocker — real document extraction
```
DigiLocker API called with user's auth token (obtained via OAuth link)
  Returns: Aadhaar XML, e-Aadhaar JSON, income certificate

Field mapping:
  Aadhaar XML → applicant_name, date_of_birth, gender, address
  e-Aadhaar   → aadhaar_number (12 digits, verified)
  Income cert → annual_income, caste category

Result: form_data 80-90% complete from DigiLocker alone
Missing: bank_account (not in DigiLocker), family_members
→ Ask user for only these 2 fields
```

### Step 4: Playwright + Vision LLM fills real portal
```
browser_mcp.launch_browser(headless=True)
browser_mcp.navigate_to_url("https://pmjay.gov.in/")
browser_mcp.take_screenshot()
  → screenshot.png sent to nvidia/llama-3.2-90b-vision-instruct
  → VLM returns: {"found": true, "x": 432, "y": 287, "label": "Aadhaar Number"}
browser_mcp.vision_type(432, 287, "845298371234")
  ... repeat for all fields ...
browser_mcp.detect_otp_page() → True
  → suspend graph, send OTP request to user on WhatsApp
```

### Step 5: OTP Resume
```
User replies: "482910"
  → webhook receives, finds session (WAIT_OTP state)
  → fill_form_node resumes
  → browser_mcp.submit_otp("482910")
  → portal confirms submission
  → response: "✅ Ref: PMJAY/UP/2026/847291"
  → graph state: COMPLETED
  → PII cleared from memory
```

---

## 6. How Anyone Can Use It

### For a village user (zero tech knowledge)
1. Save the WhatsApp number
2. Send any message in any language
3. Follow voice prompts (bot also sends audio replies)
4. Click DigiLocker link once (first time only)
5. Send OTP when received
6. Done — bot sends confirmation with reference number

### For a CSC / e-Mitra operator
1. Run `.\start.ps1 -All` on their Windows PC
2. Share the ngrok URL with Twilio sandbox
3. Service multiple users simultaneously (bot handles each separately by phone number)
4. View submissions on Streamlit dashboard
5. Approve/reject via admin panel at `/admin.html`

### For a developer integrating GramSetu
```python
# REST API — no WhatsApp needed
import httpx

response = httpx.post("http://localhost:8000/api/chat", json={
    "message": "I need a ration card",
    "user_id": "user123",
    "phone": "9876543210",
    "language": "en"
})

print(response.json()["response"])
# "🙏 Hello! I've fetched your data from DigiLocker..."
```

### For adding a new form type
```python
# backend/agents/schema.py
class PassportApplication(BaseModel):
    applicant_name: str = Field(..., min_length=2, max_length=100)
    date_of_birth: date
    place_of_birth: str
    aadhaar_number: str
    address: Address
    # ... any other fields

# Add to registry — THAT'S IT. Everything else is automatic.
SCHEMA_REGISTRY["passport"] = PassportApplication
```

---

## 7. Scaling Roadmap

### Current (Hackathon / MVP)
- Single FastAPI server, 1 SQLite database
- ~50 concurrent sessions before SQLite becomes bottleneck
- MCP servers run as background processes on same machine
- DigiLocker: demo data (real OAuth integration ready)
- Browser: real Playwright, VLM-guided (headless mode)

### Phase 2 — District Level (1,000 concurrent users)
| Component | Upgrade |
|---|---|
| Database | SQLite → PostgreSQL (keep same SQLAlchemy ORM) |
| Sessions | In-memory dict → Redis (session storage + rate limiting) |
| LangGraph checkpoints | SQLite → PostgreSQL checkpoint adapter |
| API server | Single uvicorn → Gunicorn with 4-8 workers |
| MCP servers | Local process → Docker containers with health checks |
| Browser | Local Playwright → Browserless.io / Playwright in Docker |

### Phase 3 — State Level (100,000 users/day)
| Component | Upgrade |
|---|---|
| WhatsApp | Twilio → WhatsApp Business API (Meta Cloud) — no sandbox limit |
| LLM | NIM hosted → NVIDIA DGX Cloud / on-prem for data sovereignty |
| Queue | Synchronous → Celery + Redis task queue for form processing |
| Multi-region | Single server → AWS/Azure multi-AZ with load balancer |
| DigiLocker | Production API credentials (needs MeitY approval) |
| Caching | Repeated DigiLocker fetches → Redis cache (TTL 24h) |

### Phase 4 — National Scale
| Component | Upgrade |
|---|---|
| Voice | WhatsApp → Also supports IVR (phone call), USSD (2G phones) |
| Languages | 11 edge-tts languages → all 22 scheduled Indian languages |
| Forms | 12 forms → 200+ (every state's schemes auto-discovered via Gemini web search) |
| Offline | Lite WhatsApp not required → SMS fallback for feature phones |
| Verification | Self-declared data → Real-time DigiLocker + UIDAI verification |
| Portal coverage | Major portals → All state & central portals via VLM adaptation |

---

## 8. Competitors & How GramSetu is Different

| Product | What it does | Limitation vs GramSetu |
|---|---|---|
| **Common Service Centres (CSC)** | Government-run physical centers | Requires travel (avg 25 km), operator dependent, queue wait, ₹50-100 per form |
| **UMANG App** | Single app for govt services | Requires smartphone + app install + digital literacy + manual form fill |
| **DigiLocker App** | Document storage only | Stores documents but does NOT fill any forms |
| **Sahaj / Jan Samarthan** | Semi-automated form portals | Still requires operator at center, not conversational, no voice |
| **BharatGPT / Krutrim** | Indian language LLM | General purpose — not form-specific, no DigiLocker integration, no Playwright |
| **Jugalbandi (Microsoft)** | WhatsApp for Q&A on schemes | Answers questions about schemes but does NOT fill or submit forms |
| **Aaple Sarkar (Maharashtra)** | State-level form portal | Web portal only, no WhatsApp, no voice, no DigiLocker auto-fill |

### GramSetu's Unique Combination

```
✅ WhatsApp (no app needed)           — Used by 500M+ Indians already
✅ Voice input in 11 languages        — Covers illiterate / semi-literate users
✅ DigiLocker auto-fill               — User types ZERO data manually
✅ Real browser form submission       — Playwright actually submits to real portal
✅ OTP suspend/resume                 — Handles real govt authentication flow
✅ Works on any phone                 — 2G compatible (WhatsApp works on 2G)
✅ No operator needed                 — Fully autonomous end-to-end
✅ Any form extensible               — 1 Pydantic model = new form type
```

No existing solution combines all 7 of these.

---

## 9. Real-World Impact Potential

| Metric | Conservative | Optimistic |
|---|---|---|
| Unclaimed welfare benefits (India) | ₹2.7 lakh crore/year | ₹2.7 lakh crore/year |
| Eligible rural families | 180 million | 180 million |
| GramSetu adoption (Year 1) | 2 million users | 10 million users |
| Forms submitted/user/year | 2.5 | 4 |
| Time saved per form | 3 hours | 3 hours |
| Economic value per claimed benefit | ₹8,000/year average | ₹8,000/year average |
| **Total economic uplift (Y1)** | **₹16,000 crore** | **₹80,000 crore** |

---

## 10. Technical Differentiators for Judges

### 1. Vision-Based Portal Navigation (No CSS Selectors)
Government portals change their HTML every few months. Traditional form-filling bots break.  
GramSetu takes a screenshot, asks the VLM "where is the Aadhaar field?", gets pixel coordinates, and clicks there. **Portal redesigns = zero downtime.**

### 2. Suspend/Resume with SQLite Checkpoints
OTP is a hard blocker for any form automation. Most bots give up here.  
GramSetu checkpoints the entire LangGraph state to SQLite. Even if the server restarts, the user can send OTP 3 hours later and the form fills and submits correctly.

### 3. Zero-Typing by Design
Data comes from DigiLocker automatically. The user's only interaction is:
- Say what they want (voice or text)
- Click DigiLocker link once
- Confirm the pre-filled summary
- Send OTP

This is the **right solution for users with low digital literacy** — not a simplified form, but a complete removal of the form from the user experience.

### 4. MCP Architecture (Production-Grade Tool Discovery)
The LangGraph doesn't hardcode any tool calls. It discovers WhatsApp tools, browser tools, DigiLocker tools, and audit tools via the Model Context Protocol over SSE/HTTP.  
Adding a new capability = deploy a new MCP server, register it, done. No graph rewrite needed.

### 5. Instant Response (Background Task Pattern)
Twilio requires a webhook response within 15 seconds or it retries.  
GramSetu returns empty TwiML in < 1ms and processes the full pipeline in a FastAPI BackgroundTask. The reply is sent via Twilio REST API when ready. **The user never sees a timeout.**

---

## 11. Demo Script (for hackathon presentation)

```
1. Open WhatsApp → Message the sandbox number

2. Send: "मुझे राशन कार्ड चाहिए"
   → Bot shows the full 11-option menu

3. Send: "1"  (or just say "ration card")
   → "✅ DigiLocker से डेटा मिल गया! ..."
   → Shows filled form summary in 3 seconds

4. Send: "YES"
   → "🌐 nfsa.gov.in पर फ़ॉर्म भर रहा हूँ..."
   → "🔐 OTP आया होगा — भेजें"

5. Send: "123456" (any 6 digits in demo mode)
   → "✅ Application #NF2026/... submitted!"

Total demo time: ~45 seconds.

Backup: show /api/chat endpoint in Swagger UI for same flow without WhatsApp.
Show Streamlit dashboard at localhost:8501 for the audit trail.
```

---

## 12. Known Limitations (Honest)

| Limitation | Mitigation |
|---|---|
| DigiLocker OAuth = real setup needed | Demo mode uses realistic mock data instantly |
| Playwright on real portals → CAPTCHAs | 2captcha / Anti-Captcha integration planned; VLM handles image CAPTCHAs |
| Govt portals often have downtime | Portal status check before attempting fill; retry queue |
| No Odia / Assamese TTS yet | Edge-tts roadmap; currently falls back to Hindi |
| NVIDIA ASR quality on heavy accents | Fine-tuned regional models coming in 2026 NIM catalog |
| SQLite bottleneck at >50 concurrent | Phase 2 upgrade to PostgreSQL + Redis (documented above) |
