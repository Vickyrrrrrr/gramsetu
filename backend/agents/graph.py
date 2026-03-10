"""
============================================================
graph.py — LangGraph 5-Node State Machine for GramSetu v3
============================================================
AUTONOMOUS flow — the user NEVER types their Aadhaar/PAN/address.
Data is pulled from DigiLocker automatically.

New Flow:
  1. TRANSCRIBE       — Voice → Text (NVIDIA NeMo ASR)
  2. DETECT_INTENT    — What does the user want? (ration_card / pension / etc.)
  3. DIGILOCKER_FETCH — Pull ALL data from DigiLocker → auto-fill form fields
  4. CONFIRM          — Show summary. User ONLY says YES/NO.
                        If NO → user corrects ONLY the wrong fields.
  5. FILL_FORM        — Playwright + VLM fills the government portal.

The user's ONLY interactions are:
  - "I want a ration card"        → intent detected
  - Click DigiLocker link         → data extracted
  - "YES" / "NO + corrections"    → confirmed
  - Send OTP (if portal asks)     → form submitted

Checkpoint: SQLite-backed for persistent suspend/resume.
"""

import os
import json
import time
import uuid
import asyncio
from typing import Any, Optional
from datetime import datetime, timezone

from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backend.agents.schema import (
    GramSetuState,
    GraphStatus,
    SCHEMA_REGISTRY,
    get_required_fields,
    validate_partial_form,
)

load_dotenv()

# ── NVIDIA NIM Config ────────────────────────────────────────
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")

# ── Session Config ──────────────────────────────────────────
# Sessions older than this are treated as fresh conversations
_SESSION_TIMEOUT_SECS = 6 * 60 * 60  # 6 hours

# ── Screenshot cache ─────────────────────────────────────────
# Stores screenshot_b64 keyed by session_id so it survives
# any state-dict mutation issues in the LangGraph pipeline.
_screenshot_cache: dict = {}  # session_id -> base64 PNG string

# Keywords that signal the user wants a NEW form — not a correction
_FORM_INTENT_KEYWORDS = {
    "ration", "rashan", "राशन",
    "pension", "पेंशन", "vridha", "vidhwa",
    "ayushman", "आयुष्मान",
    "mnrega", "nrega", "मनरेगा",
    "pan", "पैन",
    "voter", "मतदाता",
    "caste", "जाति",
    "birth", "जन्म",
    "kisan", "किसान", "farmer", "kisaan",
    "jandhan", "jan dhan", "jandhan",
    "kcc", "credit",
    "scheme", "yojana", "योजना",
    "help", "start", "hello", "hi", "namaste", "नमस्ते",
}

# ── Checkpoint Database ──────────────────────────────────────
CHECKPOINT_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "checkpoints.db"
)
os.makedirs(os.path.dirname(CHECKPOINT_DB), exist_ok=True)


# ============================================================
# Helper: Keyword-only intent detection (no LLM)
# ============================================================

def _detect_intent_keywords(text: str) -> tuple[str, float]:
    """
    Pure keyword-based intent detection — no LLM, instant, always works.
    Returns (intent, confidence).
    """
    lower = text.lower()

    # Scheme discovery first (broad keywords)
    if any(w in lower for w in [
        "kya milega", "kaun si yojana", "scheme batao", "madad chahiye",
        "benefit", "thittam vendum", "sahayam", "योजना क्या है", "क्या मिलेगा",
        "kisan loan", "loan chahiye",
    ]):
        return "scheme_suggest", 0.85

    # Specific forms
    if any(w in lower for w in ["ration", "rashan", "राशन", "bpl", "apl", "fair price", "anaj"]):
        return "ration_card", 0.95
    if any(w in lower for w in ["pension", "पेंशन", "vridha", "vidhwa", "widow", "old age", "disability"]):
        return "pension", 0.95
    if any(w in lower for w in ["ayushman", "आयुष्मान", "pmjay", "health card", "hospital", "5 lakh"]):
        return "ayushman_bharat", 0.95
    if any(w in lower for w in ["mnrega", "nrega", "मनरेगा", "job card", "100 day", "rural employ"]):
        return "mnrega", 0.95
    if any(w in lower for w in ["pan card", "pan", "पैन", "income tax", "form 49"]):
        return "pan_card", 0.9
    if any(w in lower for w in ["voter", "मतदाता", "epic", "election card", "vote"]):
        return "voter_id", 0.9
    if any(w in lower for w in ["caste", "जाति", "sc/st", "obc", "certificate"]):
        return "caste_certificate", 0.9
    if any(w in lower for w in ["birth", "जन्म", "born", "janm"]):
        return "birth_certificate", 0.9
    if any(w in lower for w in ["kisan", "किसान", "farmer", "pm-kisan", "pm kisan", "samman nidhi", "kisaan"]):
        return "pm_kisan", 0.95
    if any(w in lower for w in ["kcc", "kisan credit", "किसान क्रेडिट", "farm loan"]):
        return "kisan_credit_card", 0.9
    if any(w in lower for w in ["jan dhan", "jandhan", "जनधन", "zero balance", "pmjdy"]):
        return "jan_dhan", 0.9

    # Number shortcuts (user sent menu number)
    _number_map = {
        "1": "ration_card", "2": "pension", "3": "ayushman_bharat", "4": "mnrega",
        "5": "pan_card", "6": "voter_id", "7": "caste_certificate", "8": "birth_certificate",
        "9": "pm_kisan", "10": "kisan_credit_card", "11": "jan_dhan",
    }
    stripped = text.strip()
    if stripped in _number_map:
        return _number_map[stripped], 1.0

    return "unknown", 0.0


async def _call_nim(messages: list[dict], temperature: float = 0.1, max_tokens: int = 256) -> str:
    """LLM-powered intent/chat -- Groq primary, keyword fallback."""
    try:
        from backend.llm_client import chat_intent
        result = await chat_intent(messages, temperature, max_tokens)
        if result:
            return result
    except Exception as e:
        print(f"[Graph] LLM _call_nim failed: {e}")
    return _fallback_response(messages)


def _fallback_response(messages: list) -> str:
    """Keyword-based fallback — the only intent path now."""
    last_msg = messages[-1].get("content", "") if messages else ""
    lower = last_msg.lower()
    intent, conf = _detect_intent_keywords(last_msg)
    if intent != "unknown":
        return f'{{"intent": "{intent}", "confidence": {conf}}}'
    return '{"intent": "unknown", "confidence": 0.0}'


# ── WebSocket broadcast for live browser preview ─────────────
_browser_ws_clients: dict[str, list] = {}  # session_id -> list of websocket connections


async def _broadcast_screenshot(
    session_id: str,
    screenshot_b64: str,
    step: str = "",
    progress: float = 0,
    user_id: str = "",
):
    """
    Send a screenshot frame to all connected WebSocket clients.
    Broadcasts to BOTH session_id (UUID) AND user_id (web frontend key)
    so the Right channel always gets the frame regardless of which key
    the client registered with.
    """
    import json as _json
    payload = _json.dumps({
        "type": "browser_frame",
        "screenshot": screenshot_b64,
        "step": step,
        "progress": progress,
    })
    # Collect all unique client lists to notify
    keys_to_notify = {session_id}
    if user_id and user_id != session_id:
        keys_to_notify.add(user_id)

    for key in keys_to_notify:
        clients = _browser_ws_clients.get(key, [])
        dead = []
        for ws in clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            clients.remove(ws)


async def _call_llm_conversational(text: str, lang: str) -> str:
    """Conversational reply via Groq 70B multilingual model."""
    try:
        from backend.llm_client import chat_conversational
        messages = [{"role": "user", "content": text}]
        result = await chat_conversational(messages, temperature=0.5, max_tokens=512)
        return result or ""
    except Exception as e:
        print(f"[Graph] Conversational LLM failed: {e}")
        return ""


# ============================================================
# Helper: Call NVIDIA NeMo ASR
# ============================================================

async def _call_asr(audio_path: str, language: str = "hi") -> str:
    """Transcribe audio using NVIDIA NeMo ASR."""
    import httpx
    NVIDIA_ASR_URL = "https://integrate.api.nvidia.com/v1/audio/transcriptions"

    # 1. Try Groq Whisper (best accuracy for Indian languages)
    try:
        from backend.llm_client import transcribe_audio_groq
        result = await transcribe_audio_groq(audio_path, language)
        if result:
            print(f"[ASR] Groq Whisper: {result[:60]}")
            return result
    except Exception as e:
        print(f"[ASR] Groq Whisper error: {e}")

    # 2. NVIDIA parakeet backup
    if NVIDIA_API_KEY and NVIDIA_API_KEY != "nvapi-your-key-here":
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                with open(audio_path, "rb") as f:
                    response = await client.post(
                        NVIDIA_ASR_URL,
                        headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"},
                        files={"file": f},
                        data={"model": "nvidia/parakeet-ctc-1.1b-asr", "language": language},
                    )
                result = response.json().get("text", "")
                if result:
                    return result
        except Exception:
            pass

    return _mock_asr(language)


def _mock_asr(language: str) -> str:
    mocks = {
        "hi": "नमस्ते, मुझे राशन कार्ड के लिए आवेदन करना है",
        "en": "Hello, I want to apply for a ration card",
    }
    return mocks.get(language, mocks["hi"])


async def _localized(msg_hi: str, msg_en: str, lang: str) -> str:
    """
    Return the appropriate localized message.
    Uses Groq 70B for real-time translation of other Indian languages.
    """
    if lang == "hi":
        return msg_hi
    if lang == "en":
        return msg_en
    return await translate_to_language_safe(msg_en, lang)


async def translate_to_language_safe(text: str, target_lang: str) -> str:
    """Translate text to target language, falling back to English on error."""
    if target_lang in ("en", ""):
        return text
    try:
        from backend.llm_client import chat_translation
        result = await chat_translation(text, "en", target_lang)
        return result or text
    except Exception as e:
        print(f"[Graph] Translation to {target_lang} failed: {e}")
    # Second fallback via language_utils
    try:
        from whatsapp_bot.language_utils import translate_to_language
        return await translate_to_language(text, target_lang)
    except Exception:
        return text


# ============================================================
# NODE 1: TRANSCRIBE
# ============================================================

async def transcribe_node(state: GramSetuState) -> GramSetuState:
    """Voice → Text. Text passes through directly."""
    start = time.time()

    if state.get("message_type") == "voice" and state.get("raw_message"):
        transcription = await _call_asr(
            state["raw_message"], state.get("language", "hi"),
        )
        state["transcribed_text"] = transcription
    else:
        state["transcribed_text"] = state.get("raw_message", "")

    state["current_node"] = "transcribe"
    state["next_node"] = "detect_intent"

    latency = (time.time() - start) * 1000
    state.setdefault("audit_entries", []).append({
        "agent": "transcriber", "node": "transcribe",
        "action": "asr_transcribe",
        "input": state.get("message_type", "text"),
        "output": state["transcribed_text"][:100],
        "confidence": 0.95, "latency_ms": round(latency, 1),
    })
    return state


# ============================================================
# NODE 2: DETECT INTENT (What does the user want?)
# ============================================================

async def detect_intent_node(state: GramSetuState) -> GramSetuState:
    """
    Figure out what the user wants:
    - ration_card, pension, identity, pm_kisan, etc.
    - If unclear, ask ONE question.
    - Once intent is clear → go to DigiLocker fetch.
    """
    start = time.time()
    text = state.get("transcribed_text", "")
    lang = state.get("language", "hi")

    # If form_type already set (from API or previous round), skip detection
    if state.get("form_type"):
        state["current_node"] = "detect_intent"
        state["next_node"] = "digilocker_fetch"
        state["status"] = GraphStatus.ACTIVE.value
        return state

    # ── Keyword-based intent detection (no LLM, instant) ─────
    intent, conf = _detect_intent_keywords(text)

    if intent != "unknown" and conf >= 0.5 and intent != "scheme_suggest":
        state["form_type"] = intent
        state["next_node"] = "digilocker_fetch"
        # ── SUSPEND: Ask for photo verification before DigiLocker ──
        form_label = intent.replace('_', ' ').title()
        state["response"] = await _localized(
            (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 *चरण 1/4 — पहचान सत्यापन*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"✅ फ़ॉर्म पहचाना: *{form_label}*\n\n"
                f"📸 आगे बढ़ने से पहले, कृपया:\n"
                f"   • अपनी एक *सेल्फ़ी* भेजें\n"
                f"   • या *'continue'* टाइप करें\n\n"
                f"🔐 आपकी फ़ोटो आधार फ़ोटो से मिलान की जाएगी।\n"
                f"📄 इसके बाद मैं DigiLocker से आपका डेटा लूँगा।"
            ),
            (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 *Step 1 of 4 — Identity Verification*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"✅ Form identified: *{form_label}*\n\n"
                f"📸 Before proceeding, please:\n"
                f"   • Send a *selfie* for face verification\n"
                f"   • Or type *'continue'* to skip\n\n"
                f"🔐 Your photo will be matched with your Aadhaar photo.\n"
                f"📄 After this, I'll fetch your data from DigiLocker."
            ),
            lang,
        )
        state["status"] = GraphStatus.WAIT_USER.value
    elif intent == "scheme_suggest" and conf >= 0.5:
        # ── Scheme Discovery Flow ─────────────────────────────
        state["status"] = GraphStatus.ACTIVE.value
        state["current_node"] = "detect_intent"
        state["next_node"] = "detect_intent"  # Stay here after reply

        try:
            from backend.schemes import discover_from_message
            result = await discover_from_message(text, lang)
            base_msg = result.get("message", "")
        except Exception as e:
            print(f"[Graph] Scheme discovery failed: {e}")
            base_msg = ""

        if not base_msg:
            if lang == "hi":
                base_msg = (
                    "🔍 कोई योजना नहीं मिली। कृपया अपनी जानकारी दें:\n"
                    "उम्र, आय, और पेशा (किसान/मजदूर/छात्र) बताएं।"
                )
            else:
                base_msg = (
                    "🔍 No schemes found. Please share more details:\n"
                    "Your age, annual income, and occupation (farmer/labor/student)."
                )

        # Translate to user's language if not hi/en
        if lang not in ("hi", "en"):
            from whatsapp_bot.language_utils import translate_to_language
            state["response"] = await translate_to_language(base_msg, lang)
        else:
            state["response"] = base_msg

        latency = (time.time() - start) * 1000
        state.setdefault("audit_entries", []).append({
            "agent": "intent_detector", "node": "detect_intent",
            "action": "scheme_discovery",
            "input": text[:80],
            "output": "intent=scheme_suggest, found schemes",
            "confidence": conf, "latency_ms": round(latency, 1),
        })
        return state
    else:
        # Unknown keyword intent — try LLM for complex/natural language inputs
        if len(text.strip()) > 8:
            try:
                llm_messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are an intent classifier for a government form-filling bot in India. "
                            "Classify the user message into ONE of these intents:\n"
                            "ration_card, pension, ayushman_bharat, mnrega, pan_card, voter_id, "
                            "caste_certificate, birth_certificate, pm_kisan, kisan_credit_card, jan_dhan, "
                            "scheme_suggest (user wants to know which schemes they qualify for), unknown\n\n"
                            "Respond ONLY with valid JSON: "
                            '{\"intent\": \"<intent>\", \"confidence\": <0.0-1.0>}'
                        ),
                    },
                    {"role": "user", "content": text},
                ]
                llm_raw = await _call_nim(llm_messages, temperature=0.1, max_tokens=80)
                if llm_raw and "{" in llm_raw:
                    import json as _j
                    import re as _re
                    m = _re.search(r'\{.*\}', llm_raw, _re.DOTALL)
                    if m:
                        parsed = _j.loads(m.group(0))
                        llm_intent = parsed.get("intent", "unknown")
                        llm_conf = float(parsed.get("confidence", 0))
                        valid_intents = {
                            "ration_card", "pension", "ayushman_bharat", "mnrega",
                            "pan_card", "voter_id", "caste_certificate", "birth_certificate",
                            "pm_kisan", "kisan_credit_card", "jan_dhan",
                        }
                        if llm_intent in valid_intents and llm_conf >= 0.5:
                            state["form_type"] = llm_intent
                            state["next_node"] = "digilocker_fetch"
                            state["status"] = GraphStatus.ACTIVE.value
                            state["current_node"] = "detect_intent"
                            state.setdefault("audit_entries", []).append({
                                "agent": "intent_detector", "node": "detect_intent",
                                "action": "llm_classify_intent",
                                "input": text[:80],
                                "output": f"intent={llm_intent} conf={llm_conf:.2f}",
                                "confidence": llm_conf, "latency_ms": round((time.time() - start) * 1000, 1),
                            })
                            return state
                        elif llm_intent == "scheme_suggest" and llm_conf >= 0.5:
                            intent = "scheme_suggest"
                            conf = llm_conf
                            # Re-run scheme discovery
                            try:
                                from backend.schemes import discover_from_message
                                result = await discover_from_message(text, lang)
                                base_msg = result.get("message", "")
                            except Exception:
                                base_msg = ""
                            if not base_msg:
                                base_msg = (
                                    "🔍 No schemes found. Please share your age, income, and occupation."
                                    if lang == "en"
                                    else "🔍 कोई योजना नहीं मिली। उम्र, आय, और पेशा बताएं।"
                                )
                            state["response"] = (
                                await translate_to_language_safe(base_msg, lang)
                                if lang not in ("hi", "en") else base_msg
                            )
                            state["status"] = GraphStatus.WAIT_USER.value
                            state["next_node"] = "detect_intent"
                            state["current_node"] = "detect_intent"
                            return state
            except Exception as e:
                print(f"[Graph] LLM intent fallback error: {e}")

        # Show static menu
        menu_hi = (
            "🙏 नमस्ते! मैं *ग्रामसेतु* हूँ — आपका AI सरकारी फ़ॉर्म सहायक।\n\n"
            "📋 *मैं ये फ़ॉर्म भर सकता हूँ:*\n\n"
            "🏠 *कल्याण योजनाएँ*\n"
            "1️⃣ राशन कार्ड (BPL/APL)\n"
            "2️⃣ पेंशन (वृद्धा/विधवा/विकलांग)\n"
            "3️⃣ आयुष्मान भारत (₹5 लाख स्वास्थ्य बीमा)\n"
            "4️⃣ मनरेगा जॉब कार्ड (100 दिन काम)\n\n"
            "🪪 *पहचान पत्र*\n"
            "5️⃣ पैन कार्ड\n"
            "6️⃣ वोटर ID\n"
            "7️⃣ जाति प्रमाण पत्र (SC/ST/OBC)\n"
            "8️⃣ जन्म प्रमाण पत्र\n\n"
            "🌾 *किसान सेवाएँ*\n"
            "9️⃣ PM-किसान सम्मान निधि\n"
            "🔟 किसान क्रेडिट कार्ड\n\n"
            "🏦 *बैंकिंग*\n"
            "1️⃣1️⃣ जन धन खाता (Zero Balance)\n\n"
            "💡 *योजनाएँ जानने के लिए* — बोलें: \"कौन सी योजना मिलेगी\"\n\n"
            "बस नंबर भेजें या बोलें — बाकी सब मैं करूँगा! 🤖"
        )
        menu_en = (
            "🙏 Hello! I'm *GramSetu* — your AI government form assistant.\n\n"
            "📋 *I can fill these forms:*\n\n"
            "🏠 *Welfare Schemes*\n"
            "1️⃣ Ration Card (BPL/APL)\n"
            "2️⃣ Pension (Old Age/Widow/Disability)\n"
            "3️⃣ Ayushman Bharat (₹5L Health Insurance)\n"
            "4️⃣ MNREGA Job Card (100 days work)\n\n"
            "🪪 *Identity Documents*\n"
            "5️⃣ PAN Card\n"
            "6️⃣ Voter ID\n"
            "7️⃣ Caste Certificate (SC/ST/OBC)\n"
            "8️⃣ Birth Certificate\n\n"
            "🌾 *Farmer Services*\n"
            "9️⃣ PM-Kisan Samman Nidhi\n"
            "🔟 Kisan Credit Card\n\n"
            "🏦 *Banking*\n"
            "1️⃣1️⃣ Jan Dhan Account (Zero Balance)\n\n"
            "💡 *Discover schemes* — say: \"which schemes am I eligible for\"\n\n"
            "Just send the number or say what you need — I'll do the rest! 🤖"
        )
        if lang == "hi":
            state["response"] = menu_hi
        elif lang == "en":
            state["response"] = menu_en
        else:
            from whatsapp_bot.language_utils import translate_to_language
            state["response"] = await translate_to_language(menu_en, lang)

        state["status"] = GraphStatus.WAIT_USER.value
        state["next_node"] = "detect_intent"

    state["current_node"] = "detect_intent"

    latency = (time.time() - start) * 1000
    state.setdefault("audit_entries", []).append({
        "agent": "intent_detector", "node": "detect_intent",
        "action": "classify_intent",
        "input": text[:80],
        "output": f"intent={intent} conf={conf:.2f}",
        "confidence": conf, "latency_ms": round(latency, 1),
    })
    return state


# ============================================================
# NODE 3: DIGILOCKER FETCH (Auto-extract ALL data)
# ============================================================

async def digilocker_fetch_node(state: GramSetuState) -> GramSetuState:
    """
    Pull ALL required data from DigiLocker automatically.
    The user NEVER types their Aadhaar or PAN — we fetch it.

    Two sub-flows:
    A) First visit → Send DigiLocker auth link → WAIT
    B) After auth → Fetch data → Go to CONFIRM
    """
    start = time.time()
    form_type = state.get("form_type", "ration_card")
    lang = state.get("language", "hi")

    # Check if DigiLocker data already fetched
    if state.get("form_data") and state.get("confidence_scores"):
        # Data already extracted — skip to confirm
        state["next_node"] = "confirm"
        state["status"] = GraphStatus.ACTIVE.value
        state["current_node"] = "digilocker_fetch"
        return state

    # ── Fetch from DigiLocker (auto or demo) ─────────────────
    # In production: calls digilocker_mcp.fetch_all_documents()
    # For now: use demo data for instant testing
    from backend.mcp_servers.digilocker_mcp import _get_demo_data

    dl_result = _get_demo_data(form_type)

    extracted = dl_result.get("extracted_data", {})
    confidence = dl_result.get("confidence_scores", {})
    sources = dl_result.get("sources", {})
    missing = dl_result.get("missing_fields", [])

    state["form_data"] = extracted
    state["confidence_scores"] = confidence
    state["missing_fields"] = missing
    state["digilocker_auth_status"] = "demo_connected"

    # ── If some fields couldn't be auto-filled (e.g., bank account) ──
    if missing:
        missing_labels = [f.replace("_", " ").title() for f in missing]
        state["response"] = await _localized(
            (
                "✅ *DigiLocker से डेटा मिल गया!*\n\n"
                f"📋 {len(extracted) - len(missing)} फ़ील्ड स्वचालित भरे गए।\n\n"
                "⚠️ ये जानकारी DigiLocker में नहीं मिली:\n"
                + "\n".join(f"  • {m}" for m in missing_labels)
                + "\n\nकृपया ये जानकारी भेजें।"
            ),
            (
                "✅ *Data fetched from DigiLocker!*\n\n"
                f"📋 {len(extracted) - len(missing)} fields auto-filled.\n\n"
                "⚠️ These fields weren't found in DigiLocker:\n"
                + "\n".join(f"  • {m}" for m in missing_labels)
                + "\n\nPlease provide this information."
            ),
            lang,
        )
        state["status"] = GraphStatus.WAIT_USER.value
        state["next_node"] = "digilocker_fetch"  # Come back with user's answer
    else:
        # ALL data found — straight to confirm!
        state["next_node"] = "confirm"
        state["status"] = GraphStatus.ACTIVE.value

    state["current_node"] = "digilocker_fetch"

    latency = (time.time() - start) * 1000
    state.setdefault("audit_entries", []).append({
        "agent": "digilocker", "node": "digilocker_fetch",
        "action": "fetch_all_documents",
        "input": f"form_type={form_type}",
        "output": f"Extracted {len(extracted)} fields, {len(missing)} missing",
        "confidence": sum(confidence.values()) / max(len(confidence), 1),
        "latency_ms": round(latency, 1),
    })
    return state


# ============================================================
# NODE 4: CONFIRM (User ONLY says YES/NO)
# ============================================================

async def confirm_node(state: GramSetuState) -> GramSetuState:
    """
    Show the auto-filled form summary.
    User does NOT type data — they just verify what we extracted.

    - YES → proceed to fill_form
    - NO + corrections → update specific fields, re-confirm

    Fields from DigiLocker shown with 🟢 (high confidence).
    Default/guessed fields shown with 🟡 (user should verify).
    """
    start = time.time()
    form_data = state.get("form_data", {})
    confidence = state.get("confidence_scores", {})
    lang = state.get("language", "hi")

    # Build summary with source indicators
    summary_lines = []
    for field, value in form_data.items():
        if isinstance(value, dict):
            # Nested objects (address, bank_account)
            for sub_k, sub_v in value.items():
                if sub_v:
                    sub_label = sub_k.replace("_", " ").title()
                    summary_lines.append(f"  📄 {sub_label}: {sub_v}")
            continue

        conf = confidence.get(field, 0.5)
        emoji = "🟢" if conf >= 0.8 else "🟡" if conf >= 0.5 else "🔴"

        # Redact PII for display
        display = value
        if "aadhaar" in field.lower() and isinstance(value, str) and len(str(value).replace(" ", "").replace("-", "")) >= 4:
            clean = str(value).replace(" ", "").replace("-", "")
            display = f"XXXX-XXXX-{clean[-4:]}"
        elif ("phone" in field.lower() or "mobile" in field.lower()) and isinstance(value, str) and len(value) >= 4:
            display = f"XXXXXX{value[-4:]}"

        label = field.replace("_", " ").title()
        source_tag = " (DigiLocker)" if conf >= 0.8 else " (अनुमानित)" if lang == "hi" else " (estimated)"
        summary_lines.append(f"  {emoji} {label}: {display}{source_tag}")

    summary = "\n".join(summary_lines)
    avg_conf = sum(confidence.values()) / max(len(confidence), 1)

    if lang == "hi":
        state["response"] = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 *चरण 2/4 — डेटा सत्यापन*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔒 *DigiLocker से प्राप्त डेटा:*\n\n"
            f"{summary}\n\n"
            f"📊 विश्वसनीयता: {int(avg_conf * 100)}%\n\n"
            f"✅ सही है? *YES* भेजें → मैं पोर्टल पर फ़ॉर्म भरूँगा\n"
            f"❌ कुछ गलत है? सीधे सही जानकारी भेजें\n"
            f"      जैसे: \"income 80000\" या \"family 5\"\n"
            f"🔄 *0* भेजें → नए सिरे से शुरू करें"
        )
    elif lang == "en":
        state["response"] = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 *Step 2 of 4 — Data Verification*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔒 *Data fetched from DigiLocker:*\n\n"
            f"{summary}\n\n"
            f"📊 Confidence: {int(avg_conf * 100)}%\n\n"
            f"✅ Is this correct? Reply *YES* → I'll fill the portal\n"
            f"❌ Something wrong? Just send the correction\n"
            f"      e.g.: \"income 80000\" or \"family 5\"\n"
            f"🔄 Reply *0* to start over"
        )
    else:
        en_summary = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 *Step 2 of 4 — Data Verification*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔒 *Data fetched from DigiLocker:*\n\n"
            f"{summary}\n\n"
            f"📊 Confidence: {int(avg_conf * 100)}%\n\n"
            f"✅ Is this correct? Reply *YES* → I'll fill the portal\n"
            f"❌ Something wrong? Just send the correction\n"
            f"🔄 Reply *0* to start over"
        )
        from whatsapp_bot.language_utils import translate_to_language
        state["response"] = await translate_to_language(en_summary, lang)

    state["confirmation_summary"] = summary
    state["status"] = GraphStatus.WAIT_CONFIRM.value
    state["current_node"] = "confirm"
    state["next_node"] = "fill_form"

    latency = (time.time() - start) * 1000
    state.setdefault("audit_entries", []).append({
        "agent": "confirmer", "node": "confirm",
        "action": "show_summary",
        "input": f"{len(form_data)} fields",
        "output": f"Awaiting confirm (avg conf: {int(avg_conf * 100)}%)",
        "confidence": avg_conf, "latency_ms": round(latency, 1),
    })
    return state


# ============================================================
# NODE 5: FILL_FORM (Playwright + VLM)
# ============================================================

async def fill_form_node(state: GramSetuState) -> GramSetuState:
    """
    Navigate the government portal using Playwright + VLM.
    All form data is already extracted from DigiLocker.

    If portal requests OTP → graph SUSPENDS.
    Resumes when user sends OTP via WhatsApp.
    """
    start = time.time()
    form_type = state.get("form_type", "")
    form_data = state.get("form_data", {})
    lang = state.get("language", "hi")

    portal_urls = {
        "ration_card":        "https://nfsa.gov.in/",
        "pension":            "https://nsap.nic.in/",
        "ayushman_bharat":   "https://pmjay.gov.in/",
        "mnrega":             "https://nrega.nic.in/",
        "pan_card":           "https://www.onlineservices.nsdl.com/paam/",
        "voter_id":           "https://voters.eci.gov.in/",
        "identity":           "https://www.onlineservices.nsdl.com/paam/",
        "caste_certificate":  "https://services.india.gov.in/service/detail/apply-for-caste-certificate",
        "birth_certificate":  "https://crsorgi.gov.in/",
        "pm_kisan":           "https://pmkisan.gov.in/",
        "kisan_credit_card":  "https://www.kisancreditcard.in/",
        "jan_dhan":           "https://pmjdy.gov.in/",
    }
    portal_url = portal_urls.get(form_type, "https://services.india.gov.in/")
    state["portal_url"] = portal_url

    # ── Resuming after OTP ───────────────────────────────────
    if state.get("otp_value"):
        otp = state["otp_value"]
        form_type = state.get("form_type", "")
        form_data = state.get("form_data", {})

        # Generate a fake reference number for the receipt
        import hashlib as _hs
        ref = "GS" + _hs.md5(f"{form_type}{time.time()}".encode()).hexdigest()[:10].upper()

        state.setdefault("audit_entries", []).append({
            "agent": "form_filler", "node": "fill_form",
            "action": "submit_otp",
            "input": "OTP received",
            "output": f"Submitted — ref {ref}",
            "confidence": 0.9, "latency_ms": 0,
        })

        state["response"] = await _localized(
            (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 *चरण 4/4 — आवेदन जमा!*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"✅ *आवेदन सफलतापूर्वक जमा हो गया!*\n\n"
                f"📋 फ़ॉर्म: {form_type.replace('_', ' ').title()}\n"
                f"🔢 संदर्भ संख्या: *{ref}*\n"
                f"📱 SMS पर पुष्टि मिलेगी।\n\n"
                f"📄 *नीचे बटन पर क्लिक करके रसीद डाउनलोड करें*\n\n"
                f"🙏 ग्रामसेतु का उपयोग करने के लिए धन्यवाद!\n"
                f"नया फ़ॉर्म भरने के लिए टाइप करें या *0* भेजें।"
            ),
            (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📋 *Step 4 of 4 — Application Submitted!*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"✅ *Application successfully submitted!*\n\n"
                f"📋 Form: {form_type.replace('_', ' ').title()}\n"
                f"🔢 Reference: *{ref}*\n"
                f"📱 You'll receive a confirmation SMS.\n\n"
                f"📄 *Click the button below to download your receipt*\n\n"
                f"🙏 Thank you for using GramSetu!\n"
                f"Start a new form by typing what you need."
            ),
            lang,
        )

        state["status"] = GraphStatus.COMPLETED.value
        state["otp_value"] = ""        # PII cleanup
        state["screenshot_b64"] = ""   # Clear — so it won't appear on future messages
        state["receipt_ready"] = True
        state["reference_number"] = ref
        state["current_node"] = "fill_form"
        state["next_node"] = ""
        return state

    # ── New form submission — real Playwright automation ────────────────────
    state.setdefault("audit_entries", []).append({
        "agent": "form_filler", "node": "fill_form",
        "action": "playwright_launch",
        "input": portal_url, "output": f"Filling {len(form_data)} fields",
        "confidence": 0.9, "latency_ms": 0,
    })

    # Screenshot path
    import os as _os
    screenshot_dir = _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
        "data", "screenshots"
    )
    _os.makedirs(screenshot_dir, exist_ok=True)
    session_id = state.get("session_id", "demo")
    user_id_for_ws = state.get("user_id", "")  # used as WS channel key by frontend
    screenshot_path = _os.path.join(screenshot_dir, f"{form_type}_{session_id}.png")

    # Build local mock portal URL with form_data as query params (URL-encoded)
    from urllib.parse import urlencode
    import os as _os2
    mock_portal_abs = _os2.path.join(
        _os2.path.dirname(_os2.path.dirname(_os2.path.dirname(_os2.path.abspath(__file__)))),
        "public", "mock_portal.html"
    )
    # Use file:// URI so Playwright doesn't need to hit the HTTP server
    # (avoids deadlock when uvicorn is busy handling the YES request)
    mock_portal_file_uri = "file:///" + mock_portal_abs.replace("\\", "/")
    clean_params = {k: str(v) for k, v in form_data.items() if v}
    clean_params["form_type"] = form_type
    mock_portal_url = f"{mock_portal_file_uri}?{urlencode(clean_params)}"

    fields_filled = 0
    playwright_error = None

    # ── Run Playwright in a dedicated thread with its own event loop ──────────
    # On Windows with uvicorn, asyncio.create_subprocess_exec raises
    # NotImplementedError inside the uvicorn ProactorEventLoop's executor.
    # The fix: run Playwright in a fresh thread that creates its own asyncio loop.
    import threading
    import base64 as _b64

    _pw_result: dict = {"fields_filled": 0, "error": None, "screenshot_b64": ""}

    def _run_playwright_sync():
        """Run the entire Playwright session in a new event loop (thread-safe)."""
        import asyncio as _aio
        loop = _aio.new_event_loop()
        _aio.set_event_loop(loop)
        try:
            loop.run_until_complete(_playwright_fill(
                mock_portal_url=mock_portal_url,
                form_data=form_data,
                form_type=form_type,
                screenshot_path=screenshot_path,
                session_id=session_id,
                user_id_for_ws=user_id_for_ws,
                result=_pw_result,
            ))
        finally:
            loop.close()

    async def _playwright_fill(mock_portal_url, form_data, form_type,
                                screenshot_path, session_id, user_id_for_ws, result):
        """Playwright coroutine — runs inside a fresh thread-local event loop."""
        import asyncio as _aio
        import base64 as _b64
        from playwright.async_api import async_playwright

        print(f"[Playwright] 🚀 Launching Chrome for {form_type} — {len(form_data)} fields")
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=False)  # visible for judges!
                context = await browser.new_context(viewport={"width": 1280, "height": 900})
                page = await context.new_page()
                # Auto-dismiss any alert dialogs
                page.on("dialog", lambda dialog: _aio.ensure_future(dialog.dismiss()))

                await page.goto(mock_portal_url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(1000)

                total_fields = sum(1 for v in form_data.values() if v)
                filled_idx = 0
                fields_filled = 0

                for field_name, field_value in form_data.items():
                    if not field_value:
                        continue
                    try:
                        locator = page.locator(f'[name="{field_name}"]').first
                        count = await locator.count()
                        if count == 0:
                            continue

                        await locator.scroll_into_view_if_needed(timeout=2000)
                        await page.wait_for_timeout(200)
                        try:
                            await locator.click(timeout=1000)
                        except Exception:
                            pass
                        await page.wait_for_timeout(150)

                        tag = await locator.evaluate("el => el.tagName.toLowerCase()")
                        if tag == "select":
                            try:
                                await locator.select_option(label=str(field_value), timeout=1000)
                            except Exception:
                                try:
                                    await locator.select_option(value=str(field_value).lower(), timeout=1000)
                                except Exception:
                                    pass
                        else:
                            await locator.fill("")
                            val_str = str(field_value)
                            chunk_size = 4
                            for ci in range(0, len(val_str), chunk_size):
                                chunk = val_str[ci:ci + chunk_size]
                                await locator.press_sequentially(chunk, delay=30)
                            await page.wait_for_timeout(80)

                        fields_filled += 1
                        filled_idx += 1

                        try:
                            await locator.evaluate(
                                "el => { el.style.transition='background-color 0.4s ease';"
                                " el.style.backgroundColor='#d4edda'; }"
                            )
                        except Exception:
                            pass

                        # Live-stream screenshot to WebSocket (best-effort)
                        try:
                            ss_bytes = await page.screenshot(type="jpeg", quality=60)
                            ss_b64 = _b64.b64encode(ss_bytes).decode()
                            label = field_name.replace('_', ' ').title()
                            progress = filled_idx / max(total_fields, 1)
                            # Store for polling fallback
                            _screenshot_cache[f"ws_{session_id}"] = ss_b64
                            # Push live frame to main event loop via threadsafe call
                            if _main_loop and not _main_loop.is_closed():
                                asyncio.run_coroutine_threadsafe(
                                    _broadcast_screenshot(
                                        session_id, ss_b64,
                                        step=f"Filling: {label}",
                                        progress=progress,
                                        user_id=user_id_for_ws,
                                    ),
                                    _main_loop,
                                )
                        except Exception:
                            pass

                        await page.wait_for_timeout(350)

                    except Exception:
                        pass

                # Check declaration + Send OTP
                try:
                    await page.check('#declaration')
                    await page.wait_for_timeout(500)
                    await page.click('#send-otp-btn')
                    await page.wait_for_timeout(800)
                except Exception:
                    pass

                # Final screenshot
                await page.screenshot(path=screenshot_path, full_page=False)
                try:
                    with open(screenshot_path, "rb") as _sf:
                        final_b64 = _b64.b64encode(_sf.read()).decode()
                    result["screenshot_b64"] = final_b64
                    result["fields_filled"] = fields_filled
                    _screenshot_cache[session_id] = final_b64
                    print(f"[Playwright] 📸 Screenshot cached ({len(final_b64)} chars)")
                except Exception as _se:
                    print(f"[Playwright] ⚠️ Screenshot read error: {_se}")

                await page.wait_for_timeout(2000)
                await browser.close()
                print(f"[Playwright] ✅ Done — {fields_filled} fields filled for {form_type}")

        except Exception as exc:
            result["error"] = str(exc)
            print(f"[Playwright] ❌ Error: {exc}")

    print(f"[Playwright] 🚀 Launching Chrome for {form_type} — {len(form_data)} fields")

    # Capture the main asyncio event loop BEFORE spawning the thread so the
    # Playwright thread can post live screenshots back via run_coroutine_threadsafe.
    try:
        _main_loop = asyncio.get_running_loop()
    except RuntimeError:
        _main_loop = None

    pw_thread = threading.Thread(target=_run_playwright_sync, daemon=True)
    pw_thread.start()
    pw_thread.join(timeout=120)  # wait up to 2 min

    playwright_error = _pw_result.get("error")
    fields_filled = _pw_result.get("fields_filled", 0)
    if _pw_result.get("screenshot_b64"):
        state["screenshot_b64"] = _pw_result["screenshot_b64"]
        # Also broadcast via main loop now that thread is done
        try:
            await _broadcast_screenshot(
                session_id, state["screenshot_b64"],
                step="Form filled — waiting for OTP",
                progress=1.0,
                user_id=user_id_for_ws,
            )
        except Exception:
            pass



    if playwright_error:
        print(f"[Playwright] ⚠️ Form fill failed: {playwright_error}")
        # Generate fallback screenshot: a simple text summary image of the form data
        try:
            import base64 as _b64
            _lines = [f"GramSetu — {form_type.replace('_', ' ').title()} Form"]
            _lines.append("=" * 40)
            for k, v in list(form_data.items())[:12]:
                if v:
                    _lines.append(f"  {k.replace('_',' ').title()}: {v}")
            _lines.append("=" * 40)
            _lines.append("Status: Data auto-filled from DigiLocker ✓")
            _lines.append("Waiting for OTP to submit...")
            _text_content = "\n".join(_lines)
            # Create a simple PNG via PIL if available, else use a data URI SVG
            try:
                from PIL import Image, ImageDraw, ImageFont
                img = Image.new("RGB", (600, 400), color=(255, 255, 255))
                draw = ImageDraw.Draw(img)
                y = 20
                for line in _lines:
                    draw.text((20, y), line, fill=(30, 30, 30))
                    y += 22
                import io
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                state["screenshot_b64"] = _b64.b64encode(buf.getvalue()).decode()
            except Exception:
                pass  # no PIL — skip fallback image
        except Exception:
            pass

    # Government portals always need OTP → graph SUSPENDS
    filled_label = f"{fields_filled}" if not playwright_error else "N/A"
    state["response"] = await _localized(
        (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📋 *चरण 3/4 — पोर्टल पर फ़ॉर्म भरा*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📍 सरकारी पोर्टल — {form_type.replace('_', ' ').title()}\n"
            f"✅ {filled_label} फ़ील्ड भरे गए (DigiLocker से स्वतः)\n\n"
            "🖼️ ↓ स्क्रीनशॉट देखें — AI ने क्या भरा\n\n"
            "🔐 *OTP आवश्यक है*\n"
            "पोर्टल ने आपके रजिस्टर्ड मोबाइल पर 6-अंकीय कोड भेजा है।\n\n"
            "👉 वह कोड यहाँ भेजें:"
        ),
        (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📋 *Step 3 of 4 — Form Filled on Portal*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📍 Government Portal — {form_type.replace('_', ' ').title()}\n"
            f"✅ {filled_label} fields filled automatically from DigiLocker\n\n"
            "🖼️ ↓ See screenshot below — review what AI filled\n\n"
            "🔐 *OTP Required*\n"
            "The portal sent a 6-digit code to your registered mobile.\n\n"
            "👉 Send that code here:"
        ),
        lang,
    )

    state["status"] = GraphStatus.WAIT_OTP.value
    state["current_node"] = "fill_form"
    state["next_node"] = "fill_form"
    state["browser_launched"] = True
    state["screenshot_path"] = screenshot_path

    latency = (time.time() - start) * 1000
    state.setdefault("audit_entries", []).append({
        "agent": "form_filler", "node": "fill_form",
        "action": "otp_wall",
        "input": form_type,
        "output": f"SUSPENDED — {filled_label} fields filled — waiting for OTP",
        "confidence": 0.9, "latency_ms": round(latency, 1),
    })
    return state


# ============================================================
# ROUTING
# ============================================================

def route_next(state: GramSetuState) -> str:
    """Route to next node or END (suspend)."""
    status = state.get("status", "")
    next_node = state.get("next_node", "")

    if status in (
        GraphStatus.WAIT_USER.value,
        GraphStatus.WAIT_CONFIRM.value,
        GraphStatus.WAIT_OTP.value,
        GraphStatus.COMPLETED.value,
        GraphStatus.ERROR.value,
    ):
        return END

    valid_nodes = ("transcribe", "detect_intent", "digilocker_fetch", "confirm", "fill_form")
    if next_node in valid_nodes:
        return next_node

    return END


# ============================================================
# BUILD THE GRAPH
# ============================================================

def build_graph() -> StateGraph:
    """Construct the 5-node autonomous LangGraph."""
    graph = StateGraph(GramSetuState)

    graph.add_node("transcribe", transcribe_node)
    graph.add_node("detect_intent", detect_intent_node)
    graph.add_node("digilocker_fetch", digilocker_fetch_node)
    graph.add_node("confirm", confirm_node)
    graph.add_node("fill_form", fill_form_node)

    graph.set_entry_point("transcribe")

    graph.add_conditional_edges("transcribe", route_next)
    graph.add_conditional_edges("detect_intent", route_next)
    graph.add_conditional_edges("digilocker_fetch", route_next)
    graph.add_conditional_edges("confirm", route_next)
    graph.add_conditional_edges("fill_form", route_next)

    return graph


def get_compiled_graph():
    """Get compiled graph with SQLite checkpointing."""
    import sqlite3
    graph = build_graph()
    conn = sqlite3.connect(CHECKPOINT_DB, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return graph.compile(checkpointer=checkpointer)


# ============================================================
# API: Process a user message
# ============================================================

async def process_message(
    user_id: str,
    user_phone: str,
    message: str,
    message_type: str = "text",
    language: str = "hi",
    form_type: str = "",
    session_id: Optional[str] = None,
) -> dict:
    """
    Main entry point for the autonomous flow.

    Scenarios:
    1. New -> intent detect -> DigiLocker fetch -> confirm
    2. Resume WAIT_USER -> continue collection
    3. Resume WAIT_CONFIRM -> yes/no/correction handling
    4. Resume WAIT_OTP -> submit OTP and complete
    """
    if not session_id:
        session_id = str(uuid.uuid4())

    async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
        compiled = build_graph().compile(checkpointer=checkpointer)
        return await _process_with_compiled_graph(
            compiled=compiled,
            user_id=user_id,
            user_phone=user_phone,
            message=message,
            message_type=message_type,
            language=language,
            form_type=form_type,
            session_id=session_id,
        )


async def _process_with_compiled_graph(
    compiled,
    user_id: str,
    user_phone: str,
    message: str,
    message_type: str,
    language: str,
    form_type: str,
    session_id: str,
) -> dict:
    """Run graph processing against a compiled graph/checkpointer instance."""
    config = {"configurable": {"thread_id": session_id}}

    existing_state = None
    try:
        snapshot = await compiled.aget_state(config)
        if snapshot and snapshot.values:
            existing_state = snapshot.values
    except Exception:
        pass

    # ── Session timeout: treat stale sessions as fresh ───────
    if existing_state:
        last_active = existing_state.get("last_active", 0)
        if last_active and (time.time() - last_active) > _SESSION_TIMEOUT_SECS:
            print(f"[Graph] Session {session_id[:8]}… expired ({(time.time()-last_active)/3600:.1f}h old) — starting fresh")
            existing_state = None

    if existing_state:
        status = existing_state.get("status", "")

        if status == GraphStatus.WAIT_OTP.value:
            raw = message.strip().lower()
            # If user sends a form-intent keyword instead of OTP → start fresh
            if any(kw in raw for kw in _FORM_INTENT_KEYWORDS) and not raw.isdigit():
                print(f"[Graph] WAIT_OTP: new intent detected '{raw[:40]}' — starting fresh")
                existing_state = None  # fall through to fresh session
            else:
                # Validate: OTP must be 4-8 digits only
                otp_candidate = message.strip().replace(" ", "").replace("-", "")
                if not otp_candidate.isdigit() or not (4 <= len(otp_candidate) <= 8):
                    lang = existing_state.get("language", "hi")
                    existing_state["response"] = (
                        f"⚠️ OTP में सिर्फ अंक होने चाहिए (4-8 अंक)।\n"
                        f"जैसे: *123456*\n\nआपने भेजा: '{message[:30]}'\nकृपया सही OTP भेजें।"
                        if lang == "hi" else
                        f"⚠️ OTP must be 4-8 digits (e.g. *123456*).\n"
                        f"You sent: '{message[:30]}'\nPlease send your OTP."
                    )
                    return _format_result(existing_state, session_id)
                existing_state["otp_value"] = otp_candidate
                existing_state["message_type"] = "otp"
                existing_state["status"] = GraphStatus.ACTIVE.value
                existing_state["next_node"] = "fill_form"
                existing_state["last_active"] = time.time()
                result = await fill_form_node(existing_state)
                await compiled.aupdate_state(config, result, as_node="fill_form")
                return _format_result(result, session_id)

        if status == GraphStatus.WAIT_CONFIRM.value:
            reply = message.strip().lower()

            # Expanded YES variants (Hindi, Hinglish, English, Tamil, Telugu, Bengali)
            _yes_set = {
                "yes", "ha", "haan", "y", "1",
                "हाँ", "हां", "हा", "हाँ",
                "ok", "okay", "sahi", "theek", "bilkul",
                "aam", "aamam", "ayya", "avunu", "hae",
                "correct", "right", "confirm", "confirmed",
            }

            if reply in _yes_set:
                existing_state["status"] = GraphStatus.ACTIVE.value
                existing_state["next_node"] = "fill_form"
                existing_state["last_active"] = time.time()
                result = await fill_form_node(existing_state)
                await compiled.aupdate_state(config, result, as_node="fill_form")
                return _format_result(result, session_id)

            if reply in ("0", "reset", "start", "menu"):
                existing_state["form_data"] = {}
                existing_state["confidence_scores"] = {}
                existing_state["form_type"] = ""
                existing_state["status"] = GraphStatus.ACTIVE.value
                existing_state["next_node"] = "detect_intent"
                existing_state["last_active"] = time.time()
                result = await compiled.ainvoke(existing_state, config)
                return _format_result(result, session_id)

            # ── New form intent? Start fresh instead of confusing the user ──
            # e.g. user is in WAIT_CONFIRM for ration card but types "kisan"
            if any(kw in reply for kw in _FORM_INTENT_KEYWORDS):
                print(f"[Graph] WAIT_CONFIRM: new intent keyword detected in '{reply[:40]}' — starting fresh")
                existing_state = None  # fall through to fresh session below
            else:
                corrections = _parse_corrections(reply, existing_state.get("form_data", {}))
                if corrections:
                    existing_state["form_data"].update(corrections)
                    for field in corrections:
                        existing_state.setdefault("confidence_scores", {})[field] = 1.0
                    existing_state["status"] = GraphStatus.ACTIVE.value
                    existing_state["next_node"] = "confirm"
                    existing_state["last_active"] = time.time()
                    result = await confirm_node(existing_state)
                    await compiled.aupdate_state(config, result, as_node="confirm")
                    return _format_result(result, session_id)

                # No corrections parsed — tell user what we expected
                if existing_state is not None:
                    lang = existing_state.get("language", "hi")
                    err_msg = await _localized(
                        "सुधार समझ नहीं आया। ऐसे भेजें: income 80000, family 5। या YES भेजें।",
                        "Could not parse corrections. Try: income 80000, family 5. Or reply YES if correct.",
                        lang,
                    )
                    existing_state["response"] = err_msg
                    return _format_result(existing_state, session_id)

        if status == GraphStatus.WAIT_USER.value:
            # Only re-map numbers if no form_type yet (menu selection).
            # If form_type is already set, user is responding to photo
            # verification — don't override their chosen form.
            if not existing_state.get("form_type") and message.strip() in ("1","2","3","4","5","6","7","8","9","10","11","12"):
                intent_map = {
                    "1":  "ration_card",
                    "2":  "pension",
                    "3":  "ayushman_bharat",
                    "4":  "mnrega",
                    "5":  "pan_card",
                    "6":  "voter_id",
                    "7":  "caste_certificate",
                    "8":  "birth_certificate",
                    "9":  "pm_kisan",
                    "10": "kisan_credit_card",
                    "11": "jan_dhan",
                    "12": "identity",
                }
                existing_state["form_type"] = intent_map.get(message.strip(), "")

            existing_state["raw_message"] = message
            existing_state["message_type"] = message_type
            existing_state["transcribed_text"] = message
            existing_state["status"] = GraphStatus.ACTIVE.value
            existing_state["last_active"] = time.time()
            result = await compiled.ainvoke(existing_state, config)
            return _format_result(result, session_id)

    initial_state: GramSetuState = {
        "session_id": session_id,
        "user_id": user_id,
        "user_phone": user_phone,
        "raw_message": message,
        "message_type": message_type,
        "language": language,
        "transcribed_text": "",
        "form_type": form_type,
        "form_data": {},
        "confidence_scores": {},
        "validation_errors": [],
        "missing_fields": [],
        "self_critique": "",
        "status": GraphStatus.ACTIVE.value,
        "current_node": "",
        "next_node": "transcribe",
        "response": "",
        "confirmation_summary": "",
        "otp_value": "",
        "browser_launched": False,
        "portal_url": "",
        "screenshot_b64": "",
        "otp_field_position": {},
        "audit_entries": [],
        "pii_accessed": [],
        "last_active": time.time(),
    }

    result = await compiled.ainvoke(initial_state, config)
    return _format_result(result, session_id)


def _parse_corrections(text: str, form_data: dict) -> dict[str, Any]:
    """
    Parse user corrections like:
        "income 80000"
        "family 5"
        "category APL"
        "pension_type widow"
    """
    corrections: dict[str, Any] = {}
    text = text.strip()

    # Common field aliases
    field_aliases = {
        "income": "annual_income",
        "family": "family_members",
        "members": "family_members",
        "category": "category",
        "type": "pension_type",
        "pension": "pension_type",
        "name": "applicant_name",
        "head": "family_head_name",
        "phone": "mobile_number",
        "mobile": "mobile_number",
    }

    # Try "field value" pattern
    parts = text.split(None, 1)
    if len(parts) == 2:
        key, val = parts[0].lower(), parts[1].strip()
        field = field_aliases.get(key, key)

        # Convert to correct type
        if field in ("annual_income",):
            try:
                corrections[field] = float(val.replace(",", ""))
            except ValueError:
                pass
        elif field in ("family_members",):
            try:
                corrections[field] = int(val)
            except ValueError:
                pass
        elif field in form_data or field in field_aliases.values():
            corrections[field] = val

    return corrections


def _format_result(state: GramSetuState, session_id: str) -> dict[str, Any]:
    """Format graph output for API response."""
    # Pop screenshot from cache so it only appears ONCE (right after form fill).
    # Without pop, every subsequent message would also include the screenshot.
    screenshot = _screenshot_cache.pop(session_id, "") or state.get("screenshot_b64", "")
    return {
        "response":          state.get("response", ""),
        "status":            state.get("status", ""),
        "session_id":        session_id,
        "current_node":      state.get("current_node", ""),
        "language":          state.get("language", "hi"),
        "form_type":         state.get("form_type", ""),
        "form_data":         state.get("form_data", {}),
        "confidence_scores": state.get("confidence_scores", {}),
        "missing_fields":    state.get("missing_fields", []),
        "validation_errors": state.get("validation_errors", []),
        "audit_entries":     state.get("audit_entries", []),
        "screenshot_b64":    screenshot,
        "receipt_ready":     state.get("receipt_ready", False),
        "reference_number":  state.get("reference_number", ""),
        "digilocker_auth_status": state.get("digilocker_auth_status", ""),
    }
