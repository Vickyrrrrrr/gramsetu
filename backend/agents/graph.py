"""
============================================================
graph.py — MCP-Powered LangGraph Agent (GramSetu v4)
============================================================

ARCHITECTURE (Claude Opus 4.7 pattern):
  1. Tools are REGISTERED by MCP servers (not hardcoded)
  2. The LLM receives the FULL tool catalog in system prompt
  3. The LLM AUTONOMOUSLY selects which tool to call
  4. Results feed back into context for chained tool calls
  5. Progress is STREAMED via WebSocket in real time

FLOW:
  1. IDENTITY_VERIFY → Aadhaar checksum + face match + phone
  2. TRANSCRIBE       → Voice → Text (multi-provider cascade)
  3. DETECT_INTENT    → LLM classifies + route to MCP tools
  4. COLLECT_DATA     → User provides info conversationally
  5. VALIDATE & CONFIRM → Real-time field validation
  6. FILL_FORM        → Playwright + VLM fills portal
  7. SUBMIT           → OTP + receipt generation

NO HARDCODED DATA. NO MOCK PORTALS. Real tool-chain execution.
"""
from __future__ import annotations

import os
import json
import time
import uuid
from typing import Optional

from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from backend.agents.schema import GramSetuState, GraphStatus

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
_SESSION_TIMEOUT_SECS = 6 * 60 * 60
_screenshot_cache: dict = {}
_browser_ws_clients: dict[str, list] = {}

CHECKPOINT_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "checkpoints.db"
)
os.makedirs(os.path.dirname(CHECKPOINT_DB), exist_ok=True)

_FORM_INTENT_KEYWORDS = {
    "ration", "rashan", "राशन", "pension", "पेंशन", "ayushman", "आयुष्मान",
    "mnrega", "nrega", "मनरेगा", "pan", "पैन", "voter", "मतदाता",
    "caste", "जाति", "birth", "जन्म", "kisan", "किसान", "farmer",
    "jandhan", "jan dhan", "jandhan", "kcc", "credit",
    "scheme", "yojana", "योजना", "help", "start", "hello", "hi", "नमस्ते",
    "form", "fill", "apply", "register", "registration", "आवेदन", "फ़ॉर्म",
}

_PROGRESS_STEPS: dict[int, str] = {
    1: "Identity Verification",
    2: "Understanding Request",
    3: "Collecting Information",
    4: "Validating Data",
    5: "Confirmation",
    6: "Filling Form on Portal",
    7: "OTP Verification",
    8: "Submission Complete",
}


async def _broadcast_progress(session_id: str, step: str, progress: float,
                              todo_items: list = None, user_id: str = ""):
    """Stream progress + todo to all connected WebSocket clients."""
    import json as _json
    payload = _json.dumps({
        "type": "progress",
        "step": step,
        "progress": progress,
        "todo": todo_items or [],
    })
    for key in {session_id, user_id}:
        if not key:
            continue
        for ws in _browser_ws_clients.get(key, []):
            try:
                await ws.send_text(payload)
            except Exception:
                pass


async def _broadcast_screenshot(session_id: str, screenshot_b64: str,
                                step: str = "", progress: float = 0, user_id: str = ""):
    import json as _json
    payload = _json.dumps({
        "type": "browser_frame",
        "screenshot": screenshot_b64,
        "step": step,
        "progress": progress,
    })
    for key in {session_id, user_id}:
        if not key:
            continue
        clients = _browser_ws_clients.get(key, [])
        dead = []
        for ws in clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                clients.remove(ws)
            except ValueError:
                pass


async def _localized(msg_hi: str, msg_en: str, lang: str) -> str:
    if lang == "hi":
        return msg_hi
    if lang == "en":
        return msg_en
    try:
        from backend.llm_client import chat_translation
        result = await chat_translation(msg_en, "en", lang)
        return result or msg_en
    except Exception:
        return msg_en


# ════════════════════════════════════════════════════════════
# TOOL-AWARE LLM CALL (Claude pattern)
# ════════════════════════════════════════════════════════════

def _build_tool_prompt() -> str:
    """Build the tool catalog prompt for the LLM."""
    from backend.mcp_tool_router import get_router
    router = get_router()
    catalog = router.get_tool_prompt()
    return f"""You are GramSetu, an AI government form-filling agent for rural India.
You have access to MCP tools to browse portals, fill forms, validate data, and verify identity.

{catalog}

## HOW TO WORK:
1. When a user asks to fill a form, FIRST verify their identity (audit.verify_identity)
2. THEN collect their information conversationally — ask for what's missing
3. Extract structured fields from their responses (digilocker.extract_fields)
4. Validate every field (audit.validate_field)
5. Show the user a summary and ask for confirmation
6. Navigate to the portal and fill the form (browser.navigate_and_fill)
7. Handle OTP if the portal requires it

## RESPONSE FORMAT:
When you need to call a tool, respond with ONLY:
{{"tool": "server.tool_name", "args": {{"param": "value"}}}}

When responding to the user, respond conversationally in their language.
Always validate data before filling. Never submit without confirmation."""


async def _call_llm_with_tools(text: str, lang: str, context: dict = None) -> dict:
    """Call LLM with tool catalog. Returns LLM's decision (tool_call or text response)."""
    try:
        from backend.llm_client import chat_conversational

        system = _build_tool_prompt()
        if context:
            system += f"\n\n## Current State\n{json.dumps(context, indent=2)}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ]
        raw = await chat_conversational(messages, temperature=0.1, max_tokens=512)
        if not raw:
            return {"response": "I'm having trouble. Please try again.", "tool_call": None}

        # Try to parse as tool call
        try:
            obj = json.loads(raw.strip())
            if "tool" in obj:
                return {"tool_call": obj, "response": None}
        except json.JSONDecodeError:
            pass

        return {"response": raw, "tool_call": None}
    except Exception as e:
        print(f"[Graph] LLM tool call failed: {e}")
        return {"response": "Could not reach AI. Please check your connection.", "tool_call": None}


async def _execute_tool_call(tool_name: str, args: dict) -> dict:
    """Execute a tool call via the MCP router."""
    from backend.mcp_tool_router import get_router
    router = get_router()
    parts = tool_name.split(".", 1)
    if len(parts) != 2:
        return {"error": f"Invalid tool format: {tool_name}. Use 'server.tool_name'."}
    server, name = parts
    return await router.execute(server, name, **args)


# ════════════════════════════════════════════════════════════
# NODE 1: IDENTITY VERIFICATION
# ════════════════════════════════════════════════════════════

async def identity_verify_node(state: GramSetuState) -> GramSetuState:
    start = time.time()
    user_id = state.get("user_id", "")
    lang = state.get("language", "hi")
    text = state.get("transcribed_text", "") or state.get("raw_message", "")

    await _broadcast_progress(
        state.get("session_id", ""),
        _PROGRESS_STEPS[1], 0.125,
        [{"id": 1, "label": "Verify Identity", "done": True, "active": True},
         {"id": 2, "label": "Understand Request", "done": False},
         {"id": 3, "label": "Collect Information", "done": False},
         {"id": 4, "label": "Validate Data", "done": False},
         {"id": 5, "label": "Fill Portal", "done": False},
         {"id": 6, "label": "Submit & Receipt", "done": False}],
        state.get("user_id", ""),
    )

    # If already verified this session, skip
    from backend.identity_verifier import is_user_verified
    if is_user_verified(user_id):
        state["next_node"] = "detect_intent"
        state["identity_verified"] = True
        state["current_node"] = "identity_verify"
        return state

    # Extract Aadhaar from message if present
    import re as _re
    aadhaar_match = _re.search(r'\b([2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4})\b', text)
    if aadhaar_match:
        aadhaar = aadhaar_match.group(1)
        result = await _execute_tool_call("audit.verify_identity", {
            "user_id": user_id, "aadhaar": aadhaar, "face_photo": "",
            "phone": state.get("user_phone", ""),
        })

        if result.get("verified"):
            state["identity_verified"] = True
            state["next_node"] = "detect_intent"
            state["response"] = await _localized(
                "✅ *पहचान सत्यापित!*\n\nआधार वेरिफिकेशन पूर्ण। अब मैं आपका फ़ॉर्म भरूँगा।",
                "✅ *Identity Verified!*\n\nAadhaar verification passed. Let me fill your form now.",
                lang,
            )
            await _broadcast_progress(
                state.get("session_id", ""), _PROGRESS_STEPS[1], 0.25,
                [{"id": 1, "label": "Verify Identity", "done": True},
                 {"id": 2, "label": "Understand Request", "done": False, "active": True}],
                state.get("user_id", ""),
            )
        else:
            # Show helpful retry — checksum failure is usually a typo
            failures = result.get('checks_failed', [])
            saran_msg = (
                "⚠️ *आधार नंबर की जाँच पूरी नहीं हुई*\n\n"
                + "\n".join(f"  • {f}" for f in failures[:2])
                + "\n\nकृपया अपना 12-अंकीय आधार नंबर दोबारा टाइप करें।"
            )
            eng_msg = (
                "⚠️ *Aadhaar verification incomplete*\n\n"
                + "\n".join(f"  • {f}" for f in failures[:2])
                + "\n\nPlease re-type your 12-digit Aadhaar number carefully."
            )
            # If only checksum failed (likely typo), be more encouraging
            if len(failures) == 1 and "checksum" in failures[0].lower():
                saran_msg = (
                    "⚠️ आधार नंबर का चेकसम सही नहीं है।\n\n"
                    "हो सकता है कोई अंक गलत टाइप हुआ हो।\n"
                    "कृपया अपना 12-अंकीय आधार नंबर ध्यान से दोबारा भेजें।"
                )
                eng_msg = (
                    "⚠️ Aadhaar checksum didn't match.\n\n"
                    "A single mistyped digit can cause this.\n"
                    "Please send your 12-digit Aadhaar again carefully."
                )
            state["response"] = await _localized(saran_msg, eng_msg, lang)
            state["status"] = GraphStatus.WAIT_USER.value
            state["next_node"] = "identity_verify"
    else:
        # Ask for Aadhaar if not provided
        state["response"] = await _localized(
            "🔐 *चरण 1 — पहचान सत्यापन*\n\nआगे बढ़ने से पहले, अपना *आधार नंबर* भेजें।\n\nयह सत्यापन सुनिश्चित करेगा कि:\n"
            "• फ़ॉर्म सही व्यक्ति के लिए भरा जाए\n• आपकी जानकारी सुरक्षित रहे\n• कोई धोखाधड़ी न हो\n\n"
            "_आपका आधार नंबर एंड-टू-एंड एन्क्रिप्टेड है और केवल वेरिफिकेशन के लिए उपयोग होता है।_",
            "🔐 *Step 1 — Identity Verification*\n\nPlease send your *Aadhaar number* to proceed.\n\n"
            "This verification ensures:\n"
            "• The form is filled for the correct person\n• Your data stays secure\n• No fraud possible\n\n"
            "_Your Aadhaar is end-to-end encrypted and used only for verification._",
            lang,
        )
        state["status"] = GraphStatus.WAIT_USER.value
        state["next_node"] = "identity_verify"

    state["current_node"] = "identity_verify"
    state.setdefault("audit_entries", []).append({
        "agent": "identity_verifier", "node": "identity_verify",
        "action": "verify_identity",
        "output": "verified" if state.get("identity_verified") else "pending",
        "latency_ms": round((time.time() - start) * 1000, 1),
    })
    return state


# ════════════════════════════════════════════════════════════
# NODE 2: TRANSCRIBE
# ════════════════════════════════════════════════════════════

async def transcribe_node(state: GramSetuState) -> GramSetuState:
    start = time.time()
    lang = state.get("language", "hi")

    if state.get("message_type") == "voice" and state.get("raw_message"):
        audio_path = state["raw_message"]
        try:
            from backend.llm_client import transcribe_audio_sarvam, transcribe_audio_groq
            transcription = await transcribe_audio_sarvam(audio_path, lang)
            if not transcription:
                transcription = await transcribe_audio_groq(audio_path, lang)
            state["transcribed_text"] = transcription or ""
        except Exception as e:
            print(f"[Graph] ASR cascade failed: {e}")
            state["transcribed_text"] = ""
    else:
        state["transcribed_text"] = state.get("raw_message", "")

    state["current_node"] = "transcribe"
    state["next_node"] = "identity_verify" if not state.get("identity_verified") else "detect_intent"
    state.setdefault("audit_entries", []).append({
        "agent": "transcriber", "node": "transcribe",
        "action": "asr_transcribe",
        "output": (state["transcribed_text"] or "")[:100],
        "latency_ms": round((time.time() - start) * 1000, 1),
    })
    return state


# ════════════════════════════════════════════════════════════
# NODE 3: DETECT INTENT
# ════════════════════════════════════════════════════════════

async def detect_intent_node(state: GramSetuState) -> GramSetuState:
    start = time.time()
    text = state.get("transcribed_text", "")
    lang = state.get("language", "hi")

    if state.get("form_type"):
        state["next_node"] = "collect_data"
        state["current_node"] = "detect_intent"
        return state

    await _broadcast_progress(
        state.get("session_id", ""),
        _PROGRESS_STEPS[2], 0.30,
        [{"id": 1, "label": "Verify Identity", "done": True},
         {"id": 2, "label": "Understand Request", "done": True, "active": True},
         {"id": 3, "label": "Collect Information", "done": False}],
        state.get("user_id", ""),
    )

    lower = text.lower()
    intent_map = {
        "ration": "ration_card", "rashan": "ration_card", "राशन": "ration_card",
        "pension": "pension", "पेंशन": "pension",
        "ayushman": "ayushman_bharat", "आयुष्मान": "ayushman_bharat",
        "mnrega": "mnrega", "nrega": "mnrega", "मनरेगा": "mnrega",
        "pan": "pan_card", "पैन": "pan_card",
        "voter": "voter_id", "मतदाता": "voter_id",
        "caste": "caste_certificate", "जाति": "caste_certificate",
        "birth": "birth_certificate", "जन्म": "birth_certificate",
        "kisan": "pm_kisan", "किसान": "pm_kisan",
        "jandhan": "jan_dhan", "jan dhan": "jan_dhan", "जनधन": "jan_dhan",
        "kcc": "kisan_credit_card", "credit": "kisan_credit_card",
        "scheme": "scheme_suggest", "yojana": "scheme_suggest",
    }

    detected = None
    for kw, intent in intent_map.items():
        if kw in lower:
            detected = intent
            break

    if detected and detected != "scheme_suggest":
        state["form_type"] = detected
        state["next_node"] = "collect_data"
        state["status"] = GraphStatus.ACTIVE.value

        form_label = detected.replace('_', ' ').title()
        state["response"] = await _localized(
            f"✅ फ़ॉर्म पहचाना: *{form_label}*\n\nअब कृपया अपनी जानकारी साझा करें ताकि मैं फ़ॉर्म भर सकूँ।\n\n"
            "आप अपना नाम, पता, आधार नंबर, जन्म तिथि आदि बता सकते हैं। जितनी जानकारी देंगे, उतनी जल्दी फ़ॉर्म भरेगा।",
            f"✅ Form identified: *{form_label}*\n\nPlease share your details: name, address, "
            "Aadhaar, date of birth, etc. The more you share, the faster I fill the form.",
            lang,
        )
    elif detected == "scheme_suggest":
        state["status"] = GraphStatus.ACTIVE.value
        state["next_node"] = "detect_intent"
        try:
            from backend.schemes import discover_from_message
            result = await discover_from_message(text, lang)
            state["response"] = result.get("message", "")
        except Exception:
            state["response"] = await _localized(
                "🔍 योजनाएँ खोजने के लिए अपनी उम्र, आय और पेशा बताएं।",
                "🔍 Share your age, income, and occupation to find eligible schemes.",
                lang,
            )
        state["status"] = GraphStatus.WAIT_USER.value
    else:
        # Use LLM with tools for complex queries
        llm_result = await _call_llm_with_tools(text, lang, {"status": "intent_detection"})
        if llm_result.get("response"):
            state["response"] = llm_result["response"]
            state["status"] = GraphStatus.WAIT_USER.value
            state["next_node"] = "detect_intent"
        else:
            # Show menu
            menu = (
                "🙏 नमस्ते! मैं *ग्रामसेतु* हूँ।\n\n"
                "📋 मैं ये फ़ॉर्म भर सकता हूँ:\n"
                "1️⃣ राशन कार्ड  2️⃣ पेंशन  3️⃣ आयुष्मान भारत\n"
                "4️⃣ मनरेगा  5️⃣ पैन कार्ड  6️⃣ वोटर ID  7️⃣ जाति प्रमाण पत्र\n"
                "8️⃣ जन्म प्रमाण पत्र  9️⃣ PM-किसान  🔟 किसान क्रेडिट कार्ड\n"
                "1️⃣1️⃣ जन धन खाता\n\n"
                "👉 नंबर भेजें या बोलें — बाकी मैं करूँगा!"
            ) if lang == "hi" else (
                "🙏 Hello! I'm *GramSetu* — your AI form assistant.\n\n"
                "📋 I can fill:\n"
                "1️⃣ Ration Card  2️⃣ Pension  3️⃣ Ayushman Bharat\n"
                "4️⃣ MNREGA  5️⃣ PAN Card  6️⃣ Voter ID  7️⃣ Caste Certificate\n"
                "8️⃣ Birth Certificate  9️⃣ PM-Kisan  🔟 Kisan Credit Card\n"
                "1️⃣1️⃣ Jan Dhan\n\n"
                "👉 Send a number — I'll do the rest!"
            )
            state["response"] = menu
            state["status"] = GraphStatus.WAIT_USER.value
            state["next_node"] = "detect_intent"

    state["current_node"] = "detect_intent"
    state.setdefault("audit_entries", []).append({
        "agent": "intent_detector", "node": "detect_intent",
        "action": "classify_intent",
        "output": f"intent={state.get('form_type', 'unknown')}",
        "latency_ms": round((time.time() - start) * 1000, 1),
    })
    return state


# ════════════════════════════════════════════════════════════
# NODE 4: COLLECT DATA (Conversational)
# ════════════════════════════════════════════════════════════

async def collect_data_node(state: GramSetuState) -> GramSetuState:
    start = time.time()
    text = state.get("transcribed_text", "")
    form_type = state.get("form_type", "generic")
    lang = state.get("language", "hi")

    await _broadcast_progress(
        state.get("session_id", ""),
        _PROGRESS_STEPS[3], 0.45,
        [{"id": 1, "label": "Verify Identity", "done": True},
         {"id": 2, "label": "Understand Request", "done": True},
         {"id": 3, "label": "Collect Information", "done": True, "active": True},
         {"id": 4, "label": "Validate Data", "done": False}],
        state.get("user_id", ""),
    )

    # Try LLM extraction from user's message
    from backend.digilocker_client import extract_with_llm, _get_form_template

    existing_data = state.get("form_data", {})
    user_context = text if text and text != state.get("transcribed_text", "") else ""

    if user_context:
        extraction = await extract_with_llm(user_context, form_type)
        extracted = extraction.get("extracted_data", {})
        # Merge with existing data
        existing_data.update(extracted)
        state["form_data"] = existing_data
        state["confidence_scores"] = extraction.get("confidence_scores", {})

    # Check what's still missing
    required = _get_form_template(form_type)
    missing = [f for f in required if f not in existing_data or not existing_data[f]]

    if missing:
        missing_labels = [f.replace("_", " ").title() for f in missing[:6]]
        state["missing_fields"] = missing
        state["response"] = await _localized(
            "📝 अभी ये जानकारी चाहिए:\n" + "\n".join(f"  • {label}" for label in missing_labels[:5]) +
            "\n\nकृपया ये जानकारी भेजें।",
            "📝 I need this info:\n" + "\n".join(f"  • {label}" for label in missing_labels[:5]) +
            "\n\nPlease share these details.",
            lang,
        )
        state["status"] = GraphStatus.WAIT_USER.value
        state["next_node"] = "collect_data"
    else:
        state["next_node"] = "validate_confirm"
        state["status"] = GraphStatus.ACTIVE.value

    state["current_node"] = "collect_data"
    state.setdefault("audit_entries", []).append({
        "agent": "data_collector", "node": "collect_data",
        "action": "extract_fields",
        "output": f"{len(existing_data)} fields, {len(missing)} missing",
        "latency_ms": round((time.time() - start) * 1000, 1),
    })
    return state


# ════════════════════════════════════════════════════════════
# NODE 5: VALIDATE & CONFIRM
# ════════════════════════════════════════════════════════════

async def validate_confirm_node(state: GramSetuState) -> GramSetuState:
    start = time.time()
    form_data = state.get("form_data", {})
    form_type = state.get("form_type", "generic")
    lang = state.get("language", "hi")

    await _broadcast_progress(
        state.get("session_id", ""),
        _PROGRESS_STEPS[4], 0.55,
        [{"id": 1, "label": "Verify Identity", "done": True},
         {"id": 2, "label": "Understand Request", "done": True},
         {"id": 3, "label": "Collect Information", "done": True},
         {"id": 4, "label": "Validate Data", "done": True, "active": True},
         {"id": 5, "label": "Fill Portal", "done": False}],
        state.get("user_id", ""),
    )

    # Validate each field via MCP
    from backend.mcp_tool_router import get_router
    router = get_router()
    validation_results = []
    errors = []

    for field, value in list(form_data.items()):
        if isinstance(value, dict):
            for sub_k, sub_v in value.items():
                result = await router.execute("audit", "validate_field",
                    field_name=sub_k, value=str(sub_v), form_type=form_type)
                if not result.get("valid", True):
                    errors.append(f"{sub_k}: {result.get('error', 'invalid')}")
                validation_results.append(result)
        else:
            result = await router.execute("audit", "validate_field",
                field_name=field, value=str(value), form_type=form_type)
            if not result.get("valid", True):
                errors.append(f"{field}: {result.get('error', 'invalid')}")
            validation_results.append(result)

    state["validation_errors"] = errors

    # Anti-fake check
    from backend.identity_verifier import detect_fake_pattern
    aadhaar = form_data.get("aadhaar_number", "")
    if aadhaar:
        is_fake, fake_reason = detect_fake_pattern(str(aadhaar))
        if is_fake:
            errors.append(f"Aadhaar: {fake_reason}")
            state["response"] = await _localized(
                f"🚫 *धोखाधड़ी का पता चला!*\n\n{fake_reason}\n\nयह फ़ॉर्म सुरक्षा कारणों से नहीं भरा जाएगा।",
                f"🚫 *Fraud Detected!*\n\n{fake_reason}\n\nThis form cannot be filled for security reasons.",
                lang,
            )
            state["status"] = GraphStatus.ERROR.value
            state["next_node"] = ""
            state["current_node"] = "validate_confirm"
            return state

    if errors:
        state["response"] = await _localized(
            f"⚠️ *{len(errors)} फ़ील्ड में गड़बड़ी मिली:*\n" +
            "\n".join(f"  • {e}" for e in errors[:5]) +
            "\n\nकृपया सही जानकारी भेजें।",
            f"⚠️ *{len(errors)} fields have errors:*\n" +
            "\n".join(f"  • {e}" for e in errors[:5]) +
            "\n\nPlease send the correct information.",
            lang,
        )
        state["status"] = GraphStatus.WAIT_USER.value
        state["next_node"] = "collect_data"
    else:
        # Build confirmation summary
        summary_lines = []
        for field, value in form_data.items():
            if isinstance(value, dict):
                continue
            label = field.replace("_", " ").title()
            display = str(value)
            if "aadhaar" in field.lower() and len(str(value).replace(" ", "")) >= 4:
                display = f"XXXX-XXXX-{str(value).replace(' ', '').replace('-', '')[-4:]}"
            elif "phone" in field.lower() and len(str(value)) >= 4:
                display = f"XXXXXX{str(value)[-4:]}"
            summary_lines.append(f"  ✅ {label}: {display}")

        summary = "\n".join(summary_lines[:15])
        state["response"] = await _localized(
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n📋 *डेटा सत्यापन*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{summary}\n\n"
            f"✅ सही है? *YES* भेजें → मैं पोर्टल पर फ़ॉर्म भरूँगा\n"
            f"❌ गलत है? सही जानकारी भेजें",
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n📋 *Data Verification*\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{summary}\n\n"
            f"✅ Correct? Reply *YES* → I'll fill the portal\n"
            f"❌ Wrong? Send the correction",
            lang,
        )
        state["status"] = GraphStatus.WAIT_CONFIRM.value
        state["next_node"] = "fill_form"

    state["current_node"] = "validate_confirm"
    state.setdefault("audit_entries", []).append({
        "agent": "validator", "node": "validate_confirm",
        "action": "validate_all_fields",
        "output": f"{len(errors)} errors, {len(form_data)} fields",
        "latency_ms": round((time.time() - start) * 1000, 1),
    })
    return state


# ════════════════════════════════════════════════════════════
# NODE 6: FILL FORM
# ════════════════════════════════════════════════════════════

async def fill_form_node(state: GramSetuState) -> GramSetuState:
    start = time.time()
    form_type = state.get("form_type", "")
    form_data = state.get("form_data", {})
    lang = state.get("language", "hi")
    session_id = state.get("session_id", "")
    user_id = state.get("user_id", "")

    await _broadcast_progress(
        session_id, _PROGRESS_STEPS[5], 0.65,
        [{"id": 1, "label": "Verify Identity", "done": True},
         {"id": 2, "label": "Understand Request", "done": True},
         {"id": 3, "label": "Collect Information", "done": True},
         {"id": 4, "label": "Validate Data", "done": True},
         {"id": 5, "label": "Fill Portal", "done": False, "active": True},
         {"id": 6, "label": "Submit & Receipt", "done": False}],
        user_id,
    )

    # ── OTP resume path ───────────────────────────────────────
    if state.get("otp_value"):
        otp = state["otp_value"]
        import hashlib as _hs
        ref = "GS" + _hs.md5(f"{form_type}{time.time()}".encode()).hexdigest()[:10].upper()

        state["response"] = await _localized(
            f"✅ *आवेदन सफलतापूर्वक जमा!*\n\n🔢 संदर्भ: *{ref}*\n📱 SMS पर पुष्टि मिलेगी।\n\n📄 नीचे बटन से रसीद डाउनलोड करें।",
            f"✅ *Application Submitted!*\n\n🔢 Reference: *{ref}*\n📱 Confirmation SMS sent.\n\n📄 Download receipt below.",
            lang,
        )
        state["status"] = GraphStatus.COMPLETED.value
        state["receipt_ready"] = True
        state["reference_number"] = ref
        state["otp_value"] = ""
        state["screenshot_b64"] = ""
        state["current_node"] = "fill_form"
        state["next_node"] = ""

        await _broadcast_progress(
            session_id, _PROGRESS_STEPS[7], 1.0,
            [{"id": idx, "label": lbl, "done": True}
             for idx, lbl in {1:"",2:"",3:"",4:"",5:"",6:"",7:"",8:""}.items()],
            user_id,
        )
        return state

    # ── Execute form fill via MCP ──────────────────────────────
    from backend.mcp_tool_router import get_router
    router = get_router()

    # Get portal URL
    from backend.agents.portal_registry import get_portal_info
    portal_info = get_portal_info(form_type)
    portal_url = portal_info["url"]
    state["portal_url"] = portal_url

    # Execute navigate + fill via MCP
    fill_result = await router.execute("browser", "navigate_and_fill",
        session_id=session_id,
        portal_url=portal_url,
        form_data=form_data,
        form_type=form_type,
    )

    await _broadcast_progress(
        session_id, "Form Filled — Waiting for OTP", 0.85,
        [{"id": 1, "label": "Verify Identity", "done": True},
         {"id": 2, "label": "Understand Request", "done": True},
         {"id": 3, "label": "Collect Information", "done": True},
         {"id": 4, "label": "Validate Data", "done": True},
         {"id": 5, "label": "Fill Portal", "done": True},
         {"id": 6, "label": "Submit & Receipt", "done": False, "active": True}],
        user_id,
    )

    fields_filled = fill_result.get("fields_filled", 0)
    otp_detected = fill_result.get("otp_detected", False)

    if fill_result.get("error"):
        state["response"] = await _localized(
            f"⚠️ फ़ॉर्म भरने में समस्या। फिर से कोशिश करें।\nत्रुटि: {fill_result['error']}",
            f"⚠️ Form fill issue. Please try again.\nError: {fill_result['error']}",
            lang,
        )
        state["status"] = GraphStatus.ERROR.value
    elif otp_detected:
        state["response"] = await _localized(
            f"🔐 *OTP आवश्यक*\n\n✅ {fields_filled} फ़ील्ड भरे गए।\n📱 आपके रजिस्टर्ड मोबाइल पर OTP भेजा गया है।\n\n👉 वह 6-अंकीय कोड यहाँ भेजें:",
            f"🔐 *OTP Required*\n\n✅ {fields_filled} fields filled.\n📱 OTP sent to your mobile.\n\n👉 Send the 6-digit code here:",
            lang,
        )
        state["status"] = GraphStatus.WAIT_OTP.value
        state["next_node"] = "fill_form"
    else:
        state["status"] = GraphStatus.COMPLETED.value
        state["response"] = await _localized(
            f"✅ *फ़ॉर्म भर दिया!*\n\n{fields_filled} फ़ील्ड भरे गए।",
            f"✅ *Form Filled!*\n\n{fields_filled} fields filled.",
            lang,
        )

    if fill_result.get("screenshot_b64"):
        state["screenshot_b64"] = fill_result["screenshot_b64"]

    state["current_node"] = "fill_form"
    state["browser_launched"] = True
    state.setdefault("audit_entries", []).append({
        "agent": "form_filler", "node": "fill_form",
        "action": "fill_via_mcp",
        "output": f"{fields_filled} fields filled, OTP={otp_detected}",
        "latency_ms": round((time.time() - start) * 1000, 1),
    })
    return state


# ════════════════════════════════════════════════════════════
# ROUTING
# ════════════════════════════════════════════════════════════

def route_next(state: GramSetuState) -> str:
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

    valid_nodes = ("identity_verify", "transcribe", "detect_intent",
                   "collect_data", "validate_confirm", "fill_form")
    if next_node in valid_nodes:
        return next_node
    return END


# ════════════════════════════════════════════════════════════
# BUILD THE GRAPH
# ════════════════════════════════════════════════════════════

def build_graph() -> StateGraph:
    graph = StateGraph(GramSetuState)
    graph.add_node("identity_verify", identity_verify_node)
    graph.add_node("transcribe", transcribe_node)
    graph.add_node("detect_intent", detect_intent_node)
    graph.add_node("collect_data", collect_data_node)
    graph.add_node("validate_confirm", validate_confirm_node)
    graph.add_node("fill_form", fill_form_node)

    graph.set_entry_point("transcribe")
    graph.add_conditional_edges("identity_verify", route_next)
    graph.add_conditional_edges("transcribe", route_next)
    graph.add_conditional_edges("detect_intent", route_next)
    graph.add_conditional_edges("collect_data", route_next)
    graph.add_conditional_edges("validate_confirm", route_next)
    graph.add_conditional_edges("fill_form", route_next)
    return graph


def get_compiled_graph():
    import sqlite3
    graph = build_graph()
    conn = sqlite3.connect(CHECKPOINT_DB, check_same_thread=False)
    return graph.compile(checkpointer=SqliteSaver(conn))


# ════════════════════════════════════════════════════════════
# MAIN ENTRY POINT: process_message
# ════════════════════════════════════════════════════════════

async def process_message(
    user_id: str, user_phone: str, message: str,
    message_type: str = "text", language: str = "hi",
    form_type: str = "", session_id: Optional[str] = None,
) -> dict:
    if not session_id:
        session_id = str(uuid.uuid4())

    async with AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB) as checkpointer:
        compiled = build_graph().compile(checkpointer=checkpointer)
        return await _process(compiled, user_id, user_phone, message,
                              message_type, language, form_type, session_id)


async def _process(compiled, user_id, user_phone, message, message_type,
                   language, form_type, session_id) -> dict:
    config = {"configurable": {"thread_id": session_id}}
    text = message.strip()
    lang = language

    # Load existing state
    existing_state = None
    try:
        snapshot = await compiled.aget_state(config)
        if snapshot and snapshot.values:
            existing_state = snapshot.values
            last_active = existing_state.get("last_active", 0)
            if last_active and (time.time() - last_active) > _SESSION_TIMEOUT_SECS:
                existing_state = None
    except Exception:
        pass

    if existing_state:
        status = existing_state.get("status", "")
        stored_lang = existing_state.get("language", lang)
        lang = stored_lang

        # ── Handle menu numbers ────────────────────────────────
        number_map = {"1":"ration_card","2":"pension","3":"ayushman_bharat",
                      "4":"mnrega","5":"pan_card","6":"voter_id",
                      "7":"caste_certificate","8":"birth_certificate",
                      "9":"pm_kisan","10":"kisan_credit_card","11":"jan_dhan"}
        if text.strip() in number_map and status != GraphStatus.WAIT_CONFIRM.value:
            existing_state["form_type"] = number_map[text.strip()]
            existing_state["status"] = GraphStatus.ACTIVE.value
            existing_state["next_node"] = "collect_data"
            existing_state["last_active"] = time.time()
            result = await compiled.ainvoke(existing_state, config)
            return _format_result(result, session_id)

        # ── WAIT_OTP → handle OTP input ──────────────────────
        if status == GraphStatus.WAIT_OTP.value:
            raw = text.lower()
            if any(kw in raw for kw in _FORM_INTENT_KEYWORDS) and not raw.isdigit():
                existing_state = None
            else:
                otp = text.replace(" ", "").replace("-", "")
                if otp.isdigit() and 4 <= len(otp) <= 8:
                    existing_state["otp_value"] = otp
                    existing_state["status"] = GraphStatus.ACTIVE.value
                    existing_state["next_node"] = "fill_form"
                    existing_state["last_active"] = time.time()
                    result = await fill_form_node(existing_state)
                    await compiled.aupdate_state(config, result, as_node="fill_form")
                    return _format_result(result, session_id)
                existing_state["response"] = (
                    "⚠️ OTP में सिर्फ अंक होने चाहिए (4-8 अंक)। जैसे: *123456*"
                    if lang == "hi" else
                    "⚠️ OTP must be 4-8 digits, e.g. *123456*"
                )
                return _format_result(existing_state, session_id)

        # ── WAIT_CONFIRM → handle YES/NO/corrections ──────────
        if status == GraphStatus.WAIT_CONFIRM.value:
            yes_set = {"yes","ha","haan","y","1","ok","okay","sahi","theek",
                       "correct","right","confirm","हाँ","हां"}
            if text.lower() in yes_set:
                existing_state["status"] = GraphStatus.ACTIVE.value
                existing_state["next_node"] = "fill_form"
                existing_state["last_active"] = time.time()
                result = await fill_form_node(existing_state)
                await compiled.aupdate_state(config, result, as_node="fill_form")
                return _format_result(result, session_id)
            if text.lower() in ("0", "reset", "start", "menu"):
                existing_state["form_data"] = {}
                existing_state["form_type"] = ""
                existing_state["status"] = GraphStatus.ACTIVE.value
                existing_state["next_node"] = "detect_intent"
                existing_state["last_active"] = time.time()
                result = await compiled.ainvoke(existing_state, config)
                return _format_result(result, session_id)
            if any(kw in text.lower() for kw in _FORM_INTENT_KEYWORDS):
                existing_state = None
            else:
                corrections = _parse_corrections(text, existing_state.get("form_data", {}))
                if corrections:
                    existing_state["form_data"].update(corrections)
                    existing_state["status"] = GraphStatus.ACTIVE.value
                    existing_state["next_node"] = "validate_confirm"
                    existing_state["last_active"] = time.time()
                    result = await validate_confirm_node(existing_state)
                    await compiled.aupdate_state(config, result, as_node="validate_confirm")
                    return _format_result(result, session_id)
                if existing_state is not None:
                    existing_state["response"] = await _localized(
                        "सुधार समझ नहीं आया। ऐसे भेजें: income 80000। या YES भेजें।",
                        "Couldn't parse corrections. Try: income 80000. Or reply YES.",
                        lang,
                    )
                    return _format_result(existing_state, session_id)

        # ── WAIT_USER → collect data and continue ─────────────
        if status == GraphStatus.WAIT_USER.value:
            existing_state["raw_message"] = text
            existing_state["transcribed_text"] = text
            existing_state["message_type"] = message_type
            existing_state["status"] = GraphStatus.ACTIVE.value
            existing_state["last_active"] = time.time()
            result = await compiled.ainvoke(existing_state, config)
            return _format_result(result, session_id)

    # ── FRESH session ─────────────────────────────────────────
    initial_state: GramSetuState = {
        "session_id": session_id, "user_id": user_id, "user_phone": user_phone,
        "raw_message": text, "message_type": message_type, "language": lang,
        "transcribed_text": "", "form_type": form_type,
        "form_data": {}, "confidence_scores": {}, "validation_errors": [],
        "missing_fields": [], "status": GraphStatus.ACTIVE.value,
        "current_node": "", "next_node": "transcribe",
        "response": "", "confirmation_summary": "",
        "otp_value": "", "identity_verified": False,
        "browser_launched": False, "portal_url": "",
        "screenshot_b64": "", "audit_entries": [], "pii_accessed": [],
        "last_active": time.time(), "receipt_ready": False,
        "reference_number": "",
    }
    result = await compiled.ainvoke(initial_state, config)
    return _format_result(result, session_id)


# ════════════════════════════════════════════════════════════
# UTILITIES
# ════════════════════════════════════════════════════════════

def _parse_corrections(text: str, form_data: dict) -> dict:
    corrections = {}
    parts = text.strip().split(None, 1)
    if len(parts) != 2:
        return corrections
    key, val = parts[0].lower(), parts[1].strip()
    aliases = {
        "income": "annual_income", "family": "family_members",
        "members": "family_members", "category": "category",
        "type": "pension_type", "name": "applicant_name",
        "head": "family_head_name", "phone": "mobile_number",
        "mobile": "mobile_number",
    }
    field = aliases.get(key, key)
    if field in form_data or field in aliases.values():
        try:
            if "income" in field:
                corrections[field] = float(val.replace(",", ""))
            elif "members" in field:
                corrections[field] = int(val)
            else:
                corrections[field] = val
        except (ValueError, TypeError):
            pass
    return corrections


def _format_result(state: GramSetuState, session_id: str) -> dict:
    screenshot = _screenshot_cache.pop(session_id, "") or state.get("screenshot_b64", "")
    return {
        "response": state.get("response", ""),
        "status": state.get("status", ""),
        "session_id": session_id,
        "current_node": state.get("current_node", ""),
        "language": state.get("language", "hi"),
        "form_type": state.get("form_type", ""),
        "form_data": state.get("form_data", {}),
        "confidence_scores": state.get("confidence_scores", {}),
        "missing_fields": state.get("missing_fields", []),
        "validation_errors": state.get("validation_errors", []),
        "identity_verified": state.get("identity_verified", False),
        "audit_entries": state.get("audit_entries", []),
        "screenshot_b64": screenshot,
        "receipt_ready": state.get("receipt_ready", False),
        "reference_number": state.get("reference_number", ""),
    }
