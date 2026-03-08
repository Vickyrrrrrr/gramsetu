# GramSetu v3 🌾

## About the Project

**GramSetu** is an autonomous AI agent designed to bridge the digital divide by helping citizens—especially in rural India—fill out complex government forms directly over WhatsApp. Built for ultimate accessibility, it works on any phone with WhatsApp, requires no app downloads, and demands zero prior knowledge of complex government portals from the user.

A user simply sends a voice or text message on WhatsApp such as *"मुझे राशन कार्ड चाहिए"* (I need a ration card). GramSetu instantly understands the request in their native language, automatically fetches their verified identity documents from DigiLocker, and navigates the actual government portals to fill out the form using live browser automation. The user only needs to verify with an OTP. They never have to manually type their Aadhaar number, address, or any complex document details.

## 🧠 Powered by the Best LLMs

To achieve complete autonomy, **GramSetu relies on the best LLMs for all its processes**. Every single step of the workflow is powered by state-of-the-art models to ensure a frictionless, intelligent, and highly accurate user experience.

- **Lightning-Fast Intent Recognition:** We use highly optimized LLMs (like Llama 3.1 8B) to instantly analyze the user's message and determine the exact government scheme they need.
- **Multilingual Conversational Intelligence:** Powered by top-tier conversational LLMs (like Mixtral), GramSetu communicates warmly and naturally in 11 different Indian languages.
- **Advanced Reasoning & Data Extraction:** We utilize the industry's best reasoning models (like Llama 3.3 70B) to parse complex eligibility criteria, cross-reference DigiLocker documents, and extract precise structured data for form-filling.
- **State-of-the-Art Vision & OCR:** We leverage powerful vision LLMs to read regional text, interpret portal layouts, and handle legacy government websites in real-time.
- **Robust Voice Processing:** Best-in-class ASR models are deployed to transcribe Indian-accented speech and regional dialects flawlessly.

By deeply integrating the most capable Large Language Models available today, GramSetu successfully transforms a daunting bureaucratic task into a simple, natural, native-language conversation.

---

## Repository Structure & Quick Start

*For full setup details, refer to the included `SERVER_GUIDE.md` and `WHATSAPP_SETUP.md`.*

### Prerequisites
- Python 3.12+
- Node.js 18+
- Twilio WhatsApp sandbox (free)
- NVIDIA NIM API key

### 1. Backend (FastAPI + MCP Servers)
```bash
git clone https://github.com/Vickyrrrrrr/gramsetu.git
cd gramsetu
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
playwright install chromium

# Copy and configure environment variables
copy .env.example .env

# Start everything (FastAPI + all MCP servers)
.\start.ps1 -All
```

### 2. Live Preview Web App (Next.js)
```bash
cd webapp
npm install
npm run dev    # Opens at http://localhost:3000
```

---

## ⚠️ Notes on MCP Implementation

GramSetu is built on a future-proof architecture utilizing the Model Context Protocol (MCP). We developed 4 dedicated MCP servers (`browser_mcp`, `digilocker_mcp`, `whatsapp_mcp`, `audit_mcp`) to handle specific tools securely and modularly.

**Current Demo Limitation:**
In the current Hackathon demo environment, you may experience issues where the MCP servers are "not working" as expected out-of-the-box (e.g., connection refused, or tools failing to execute). This is due to:
1. **Local Ports & OS Differences:** The MCP servers run on individual ports (8100-8103) which can sometimes conflict or be blocked by local firewalls on different operating systems.
2. **Playwright & Headless Modes:** The Browser MCP requires a visible Chrome instance (`headless=False`) for the judges to see the live form auto-filling. Sandboxed or containerized environments often block this.
3. **API Key Dependencies:** The MCPs rely heavily on valid external keys (DigiLocker Mock OAuth, Twilio, NVIDIA NIMs) that must be precisely configured in the `.env` file. If keys are missing or rate-limited, the specific MCP will fail silently.

**Workaround for Demo:**
Currently, the core AI agent orchestrator (`graph.py`) has fallback mechanisms to execute the required tools directly if the remote MCP servers cannot be reached, ensuring the demo remains functional. 

---

## 🚀 From Demo to Live (Production Roadmap)

To transition GramSetu from a Hackathon prototype to a resilient, nation-wide production system, the following architectural upgrades are planned:

### 1. Robust Cloud Infrastructure (AWS/GCP)
- **Containerization:** All MCP servers and the FastAPI backend will be Dockerized and orchestrated via Kubernetes (EKS/GKE) for high availability and auto-scaling.
- **Microservices Architecture:** Moving from a monolithic local execution to true distributed microservices where MCPs run independently.
- **Serverless Automation:** Shifting Browser automation (Playwright/Stagehand) to specialized scalable cloud environments (like Browserbase) to handle thousands of concurrent form fills instead of running headful browsers on a single machine.

### 2. Security & Compliance
- **Data Privacy:** Full ISO 27001 & CERT-In compliance. Implementing strict data-at-rest encryption and transient data processing (no PII stored post-session).
- **Official API Integrations:** Transitioning from Playwright browser-automation (scraping) to official government API gateways (like UMANG APIs or direct state government APIs) for form submissions, ensuring 100% reliability and legal compliance.
- **Real Auth:** Migrating from mock DigiLocker OAuth to the official UIDAI Aadhaar eKYC and DigiLocker production APIs.

### 3. Reliability & Fallbacks
- **Queueing Systems:** Implementing RabbitMQ/Kafka to handle WhatsApp message spikes and queue form-filling tasks asynchronously.
- **LLM Redundancy:** Setting up multi-vendor LLM fallback routing (e.g., NVIDIA NIM -> Azure OpenAI -> AWS Bedrock) to ensure 99.9% uptime for intent and extraction models.
- **Comprehensive Monitoring:** Datadog or Prometheus/Grafana integration for live observability of MCP usage, LLM latency, and form submission success rates.
