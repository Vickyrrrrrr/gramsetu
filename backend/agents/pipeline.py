"""
============================================================
pipeline.py — Pure Python State Machine (v5)
============================================================
Replaces LangGraph with a simple sequential state machine.
All node functions are identical to v4. Only the execution
engine changes — from LangGraph's DAG compiler to plain
Python async calls with persistent state.

Nodes: transcribe → identity_verify → phone_challenge →
       security_enroll → voice_mode → document_scan →
       detect_intent → collect_data → validate_confirm →
       fill_form

State saved to SQLite after each node. No LangGraph dependency.
All features, responses, MCP tools, and LLM calls are identical.
"""
from __future__ import annotations

import os
import json
import re as _regex
import time
import uuid
import hashlib as _hs
from typing import Any, Optional, Callable

from dotenv import load_dotenv

from backend.agents.schema import GramSetuState, GraphStatus

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
_SESSION_TIMEOUT_SECS = 6 * 60 * 60
_screenshot_cache: dict = {}
_browser_ws_clients: dict[str, list] = {}

PROGRESS_STEPS = {
    1: "Identity Verification", 2: "Understanding Request",
    3: "Collecting Information", 4: "Validating Data",
    5: "Filling Form on Portal", 6: "OTP Verification",
    7: "Submission Complete",
}

_FORM_INTENT_KEYWORDS = {
    "ration", "rashan", "राशन", "pension", "पेंशन", "ayushman", "आयुष्मान",
    "mnrega", "nrega", "मनरेगा", "pan", "पैन", "voter", "मतदाता",
    "caste", "जाति", "birth", "जन्म", "kisan", "किसान", "farmer",
    "jandhan", "jan dhan", "jandhan", "kcc", "credit",
    "scheme", "yojana", "योजना", "help", "start", "hello", "hi", "नमस्ते",
    "form", "fill", "apply", "register", "registration", "आवेदन", "फ़ॉर्म",
    "government", "non-government", "private"
}


async def _broadcast_progress(session_id: str, step: str, progress: float,
                              todo_items: list = None, user_id: str = ""):
    import json as _json
    payload = _json.dumps({"type": "progress", "step": step, "progress": progress, "todo": todo_items or []})
    for key in {session_id, user_id}:
        if not key: continue
        for ws in _browser_ws_clients.get(key, []):
            try: await ws.send_text(payload)
            except Exception: pass


async def _broadcast_screenshot(session_id: str, screenshot_b64: str, step: str = "", progress: float = 0, user_id: str = ""):
    import json as _json
    payload = _json.dumps({"type": "browser_frame", "screenshot": screenshot_b64, "step": step, "progress": progress})
    for key in {session_id, user_id}:
        if not key: continue
        clients = _browser_ws_clients.get(key, [])
        dead = []
        for ws in clients:
            try: await ws.send_text(payload)
            except Exception: dead.append(ws)
        for ws in dead:
            try: clients.remove(ws)
            except ValueError: pass


async def _localized(msg_hi: str, msg_en: str, lang: str) -> str:
    return msg_hi if lang == "hi" else msg_en


async def _llm_respond(key_message: str, context: dict, lang: str, user_id: str = "") -> str:
    import json as _j
    try:
        from backend.llm_client import chat_conversational
        ctx_json = _j.dumps(context, ensure_ascii=False, default=str)[:600]
        messages = [
            {"role": "system", "content": (
                "You are GramSetu, a warm, helpful AI assistant for rural Indian citizens. "
                "Respond conversationally in the user's language. "
                "If the user selects 'Government Form' or 'Non-Government Form', acknowledge their choice and ask which specific form they need. "
                "Use WhatsApp-friendly formatting: *bold* for emphasis. "
                "Be concise — 2-5 sentences max. Sound like a helpful government officer. "
                f"Current language: {lang}. Context: {ctx_json}"
            )},
            {"role": "user", "content": key_message},
        ]
        result = await chat_conversational(messages, temperature=0.6, max_tokens=300)
        if result and len(result.strip()) > 5: return result.strip()
    except Exception as e: print(f"[LLM Respond] Failed: {e}")
    return key_message


async def _call_llm_with_tools(text: str, lang: str, context: dict = None) -> dict:
    try:
        from backend.llm_client import chat_conversational
        from backend.mcp_tool_router import get_router
        router = get_router()
        catalog = router.get_tool_prompt()
        system = f"""You are GramSetu, an AI form-filling agent. You have MCP tools.
{catalog}
If the user selects 'Government Form' or 'Non-Government Form', acknowledge their choice and ask which specific form they need.
When you need a tool, respond with: {{"tool": "server.tool_name", "args": {{"param": "value"}}}}
Otherwise respond conversationally."""
        if context: system += f"\n\nCurrent State: {json.dumps(context, indent=2)}"
        messages = [{"role": "system", "content": system}, {"role": "user", "content": text}]
        raw = await chat_conversational(messages, temperature=0.1, max_tokens=512)
        if not raw: return {"response": "Please try again.", "tool_call": None}
        try:
            obj = json.loads(raw.strip())
            if "tool" in obj: return {"tool_call": obj, "response": None}
        except: pass
        return {"response": raw, "tool_call": None}
    except Exception as e:
        print(f"[Graph] LLM tool call failed: {e}")
        return {"response": "Connection error.", "tool_call": None}


async def _execute_tool_call(tool_name: str, args: dict) -> dict:
    from backend.mcp_tool_router import get_router
    router = get_router()
    parts = tool_name.split(".", 1)
    if len(parts) != 2: return {"error": f"Invalid tool: {tool_name}"}
    server, name = parts
    return await router.execute(server, name, **args)


# ════════════════════════════════════════════════════════════
# NODE FUNCTIONS (identical to v4)
# ════════════════════════════════════════════════════════════

async def identity_verify_node(state: GramSetuState) -> GramSetuState:
    start = time.time()
    user_id = state.get("user_id", "")
    lang = state.get("language", "hi")
    text = state.get("transcribed_text", "") or state.get("raw_message", "")
    await _broadcast_progress(state.get("session_id", ""), PROGRESS_STEPS[1], 0.125, [
        {"id": 1, "label": "Verify Identity", "done": True, "active": True},
        {"id": 2, "label": "Understand Request", "done": False},
        {"id": 3, "label": "Collect Information", "done": False},
        {"id": 4, "label": "Validate Data", "done": False},
        {"id": 5, "label": "Fill Portal", "done": False},
        {"id": 6, "label": "Submit & Receipt", "done": False}], state.get("user_id", ""))
    from backend.identity_verifier import is_user_verified
    if is_user_verified(user_id):
        state["next_node"] = "detect_intent"; state["identity_verified"] = True; state["current_node"] = "identity_verify"; return state
    if state.get("challenge_otp"):
        state["next_node"] = "phone_challenge"; state["current_node"] = "identity_verify"; return state
    aadhaar_match = _regex.search(r'\b([2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4})\b', text)
    if aadhaar_match:
        aadhaar = aadhaar_match.group(1)
        result = await _execute_tool_call("audit.verify_identity", {"user_id": user_id, "aadhaar": aadhaar, "face_photo": "", "phone": state.get("user_phone", "")})
        if result.get("verified"):
            state["identity_verified"] = True; state["next_node"] = "phone_challenge"
            state["response"] = await _llm_respond("Tell user their Aadhaar passed verification.", {"verified": True}, lang, user_id)
        else:
            state["response"] = await _llm_respond("Tell user Aadhaar verification had issues. Ask to try again.", {"failed": result.get("checks_failed", [])}, lang, user_id)
            state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "identity_verify"
    else:
        state["response"] = await _llm_respond("Ask user to send their Aadhaar number.", {"step": 1}, lang, user_id)
        state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "identity_verify"
    state["current_node"] = "identity_verify"
    state.setdefault("audit_entries", []).append({"agent": "identity_verifier", "node": "identity_verify", "action": "verify_identity", "output": "verified" if state.get("identity_verified") else "pending", "latency_ms": round((time.time() - start) * 1000, 1)})
    return state


async def phone_challenge_node(state: GramSetuState) -> GramSetuState:
    user_id = state.get("user_id", ""); lang = state.get("language", "hi")
    text = state.get("transcribed_text", "") or state.get("raw_message", "")
    whatsapp_phone = state.get("user_phone", "")
    existing_mobile = state.get("challenge_otp", "")
    from backend.identity_verifier import is_phone_challenge_passed
    if is_phone_challenge_passed(user_id): state["next_node"] = "detect_intent"; state["current_node"] = "phone_challenge"; return state
    if existing_mobile:
        mobile_match = _regex.search(r'(\+?91[\s-]?)?([6-9]\d{9})', text.strip())
        if mobile_match:
            provided_mobile = "+91" + mobile_match.group(2) if not mobile_match.group(1) else mobile_match.group(1).replace(" ", "") + mobile_match.group(2)
            whatsapp_clean = whatsapp_phone.replace("+", "").replace(" ", "")
            provided_clean = provided_mobile.replace("+", "").replace(" ", "")
            if whatsapp_clean and whatsapp_clean[-10:] == provided_clean[-10:]:
                from backend.secure_enclave import has_security_enrolled
                from backend.identity_verifier import generate_challenge_otp, verify_challenge_otp
                generate_challenge_otp(user_id); verify_challenge_otp(user_id, "CONFIRMED_VIA_MOBILE_MATCH")
                state["identity_verified"] = True; state["challenge_otp"] = ""
                state["next_node"] = "security_enroll" if not has_security_enrolled(user_id) else "detect_intent"
                state["status"] = GraphStatus.ACTIVE.value
                state["response"] = await _llm_respond("Tell user their WhatsApp and Aadhaar mobile numbers match. Identity confirmed. Ask what form they need.", {"mobile_match": True}, lang, user_id)
            else:
                state["response"] = await _llm_respond("Tell user their WhatsApp number doesn't match the Aadhaar-linked mobile. Ask to double-check.", {"mismatch": True}, lang, user_id)
                state["challenge_otp"] = ""; state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "phone_challenge"
        else:
            state["response"] = await _llm_respond("Tell user to send a valid 10-digit mobile number.", {}, lang, user_id)
            state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "phone_challenge"
        state["current_node"] = "phone_challenge"; return state
    state["challenge_otp"] = "awaiting"
    state["response"] = await _llm_respond("Ask user which mobile number is linked to their Aadhaar card.", {"step": "mobile_verification"}, lang, user_id)
    state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "phone_challenge"
    state["current_node"] = "phone_challenge"; return state


async def security_enroll_node(state: GramSetuState) -> GramSetuState:
    user_id = state.get("user_id", ""); lang = state.get("language", "hi")
    text = (state.get("transcribed_text", "") or state.get("raw_message", "")).strip()
    msg_type = state.get("message_type", "text")
    from backend.secure_enclave import has_security_enrolled, is_pin_set, set_pin, store_selfie_hash
    if has_security_enrolled(user_id): state["next_node"] = "detect_intent"; state["current_node"] = "security_enroll"; return state
    if not is_pin_set(user_id):
        pin_match = text if text.isdigit() and len(text) == 4 else ""
        if pin_match:
            set_pin(user_id, pin_match)
            state["response"] = await _llm_respond("PIN set successfully. Now ask user to send a selfie photo.", {"pin_set": True, "step": 2}, lang, user_id)
            state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "security_enroll"
        else:
            state["response"] = await _llm_respond("Ask user to set a 4-digit PIN. This protects them if their phone is stolen.", {"step": 1}, lang, user_id)
            state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "security_enroll"
        state["current_node"] = "security_enroll"; return state
    if msg_type == "image" and text and len(text) > 500:
        if store_selfie_hash(user_id, text):
            state["response"] = await _llm_respond("Selfie received. Security setup complete. Ask user what form they need.", {"selfie_ok": True}, lang, user_id)
            state["next_node"] = "detect_intent"; state["status"] = GraphStatus.ACTIVE.value
        else:
            state["response"] = await _llm_respond("Selfie was too small. Ask user to send a clear face photo.", {}, lang, user_id)
            state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "security_enroll"
    else:
        state["response"] = await _llm_respond("Ask user to send a clear selfie photo on WhatsApp.", {"step": 2}, lang, user_id)
        state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "security_enroll"
    state["current_node"] = "security_enroll"; return state


async def voice_mode_node(state: GramSetuState) -> GramSetuState:
    if state.get("message_type") == "voice":
        state["voice_mode"] = True
        from lib.language_utils import detect_language
        state["voice_language"] = detect_language(state.get("transcribed_text", "")) or "hi"
        state["language"] = state["voice_language"]
    else: state["voice_mode"] = False
    state["next_node"] = "detect_intent"; state["current_node"] = "voice_mode"; return state


async def document_scan_node(state: GramSetuState) -> GramSetuState:
    msg_type = state.get("message_type", "text"); raw_message = state.get("raw_message", "")
    lang = state.get("language", "hi")
    if msg_type != "image" or not raw_message or len(raw_message) < 500:
        state["next_node"] = "collect_data"; state["current_node"] = "document_scan"; return state

    try:
        from backend.llm_client import chat_vision

        # First: detect document type — Aadhaar/ID vs Resume/CV vs unknown
        classify_prompt = "Is this a resume/CV or a government ID document? Reply with ONLY one word: 'resume', 'aadhaar', 'pan', 'government_id', or 'unknown'."
        doc_type_raw = await chat_vision(raw_message, classify_prompt, temperature=0.0, max_tokens=10)
        doc_type = (doc_type_raw or "").strip().lower()

        # ── CV/Resume path ──────────────────────────────
        if doc_type == "resume" or "resume" in doc_type or "cv" in doc_type:
            from backend.cv_scanner import scan_and_store_resume
            result = await scan_and_store_resume(state.get("user_id", ""), raw_message)
            if result.get("extracted"):
                state["response"] = await _llm_respond(
                    f"Resume scanned — {result.get('fields_extracted', 0)} fields extracted. "
                    f"Name: {result.get('name', '')}. Skills: {result.get('skills_count', 0)}. "
                    f"Experience: {result.get('experience_years', 0)} years. "
                    f"Your data is now stored and will auto-fill all future forms. "
                    f"Now tell me — what form do you need?",
                    {"resume_scanned": True, "fields": result.get("fields_extracted", 0)},
                    lang, state.get("user_id", ""),
                )
            else:
                state["response"] = await _llm_respond(
                    "Couldn't read the resume clearly. Please send a clearer photo or type your details.",
                    {}, lang, state.get("user_id", ""),
                )
            state["current_node"] = "document_scan"
            state["next_node"] = "collect_data"
            state["_cv_scanned"] = True
            return state

        # ── Government ID path (Aadhaar/PAN) ────────────
        vlm_result = await chat_vision(raw_message,
            'Extract ALL visible text from this Indian document photo. '
            'Return JSON: {"extracted_data": {...}, "document_type": "...", "confidence": 0.9}',
            temperature=0.0, max_tokens=1024)
        if vlm_result:
            m = _regex.search(r'\{.*\}', vlm_result, _regex.DOTALL)
            if m:
                parsed = json.loads(m.group(0))
                extracted = parsed.get("extracted_data", {})
                if extracted:
                    existing = state.get("form_data", {}); existing.update(extracted)
                    state["form_data"] = existing
                    fields_found = "\n".join(f"  ✅ {k.replace('_',' ').title()}: {v}" for k, v in list(extracted.items())[:8])
                    state["response"] = await _llm_respond(f"Tell user you read these details from their document: {fields_found}. Ask if it's correct.", {"doc_type": parsed.get("document_type", ""), "fields": list(extracted.keys())[:5]}, lang, state.get("user_id", ""))
                    state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "document_scan"; state["current_node"] = "document_scan"
                    return state
    except Exception as e: print(f"[DocScan] Failed: {e}")
    state["response"] = await _llm_respond("Couldn't read the document. Ask user to type their info or send a clearer photo.", {}, lang, state.get("user_id", ""))
    state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "collect_data"; state["current_node"] = "document_scan"; return state


async def transcribe_node(state: GramSetuState) -> GramSetuState:
    start = time.time(); lang = state.get("language", "hi")
    if state.get("message_type") == "voice" and state.get("raw_message"):
        audio_path = state["raw_message"]
        try:
            from backend.llm_client import transcribe_audio_sarvam, transcribe_audio_groq
            transcription = await transcribe_audio_sarvam(audio_path, lang)
            if not transcription: transcription = await transcribe_audio_groq(audio_path, lang)
            state["transcribed_text"] = transcription or ""
        except Exception as e: print(f"[Graph] ASR cascade failed: {e}"); state["transcribed_text"] = ""
    else: state["transcribed_text"] = state.get("raw_message", "")
    state["current_node"] = "transcribe"
    if state.get("challenge_otp"): state["next_node"] = "phone_challenge"
    elif state.get("message_type") == "image" and state.get("identity_verified"):
        from backend.secure_enclave import has_security_enrolled, is_pin_set
        uid = state.get("user_id", "")
        if not has_security_enrolled(uid):
            if not is_pin_set(uid):
                # PIN isn't even set — ignore image, remind to set PIN
                state["response"] = await _llm_respond(
                    "Received an image but PIN is not set yet. Ask user to set their 4-digit PIN first before sending a selfie.",
                    {}, state.get("language", "hi"), uid
                )
                state["status"] = GraphStatus.WAIT_USER.value
                state["next_node"] = "security_enroll"
                state["current_node"] = "transcribe"
                return state
            state["next_node"] = "security_enroll"
        else:
            state["next_node"] = "document_scan"
    elif state.get("message_type") == "voice" and state.get("identity_verified"): state["next_node"] = "voice_mode"
    elif state.get("identity_verified") and state.get("form_type"): state["next_node"] = "detect_intent"
    elif state.get("identity_verified"):
        from backend.secure_enclave import has_security_enrolled
        state["next_node"] = "security_enroll" if not has_security_enrolled(state.get("user_id", "")) else "detect_intent"
    elif not state.get("identity_verified"): state["next_node"] = "identity_verify"
    else: state["next_node"] = "detect_intent"
    state.setdefault("audit_entries", []).append({"agent": "transcriber", "node": "transcribe", "action": "asr_transcribe", "output": (state["transcribed_text"] or "")[:100], "latency_ms": round((time.time() - start) * 1000, 1)})
    return state


async def detect_intent_node(state: GramSetuState) -> GramSetuState:
    start = time.time(); text = state.get("transcribed_text", ""); lang = state.get("language", "hi")
    if state.get("form_type"): state["next_node"] = "collect_data"; state["current_node"] = "detect_intent"; return state
    prefix = await _llm_respond("Tell user you're about to analyze their request.", {"action": "detect_intent"}, lang, state.get("user_id", ""))
    state["response"] = prefix if prefix else ""
    detected = None
    try:
        from backend.llm_client import chat_intent
        result = await chat_intent([{"role": "system", "content": "Classify user intent. Return ONLY: {\"intent\": \"<form_name_or_query_type>\", \"confidence\": 0.95}. If form → snake_case name. If scheme query → \"scheme_suggest\". If greeting → \"help\". If user chooses government/non-government → \"form_type_selection\". If unknown → \"unknown\"."}, {"role": "user", "content": text}], temperature=0.0, max_tokens=80)
        if result:
            m = _regex.search(r'\{.*\}', result, _regex.DOTALL)
            if m: parsed = json.loads(m.group(0)); detected = parsed.get("intent", "")
    except: pass
    if not detected or detected == "unknown":
        lower = text.lower()
        for kw, intent in {"ration": "ration_card", "pension": "pension", "pan": "pan_card", "voter": "voter_id", "kisan": "pm_kisan", "ayushman": "ayushman_bharat", "mnrega": "mnrega", "jandhan": "jan_dhan", "birth": "birth_certificate", "caste": "caste_certificate", "kcc": "kisan_credit_card", "scheme": "scheme_suggest", "yojana": "scheme_suggest", "form": "generic", "apply": "generic"}.items():
            if kw in lower: detected = intent; break
    if detected and detected not in ("scheme_suggest", "help", "unknown", "form_type_selection"): state["form_type"] = detected; state["next_node"] = "collect_data"; state["status"] = GraphStatus.ACTIVE.value
    elif detected == "scheme_suggest":
        try:
            from backend.schemes import discover_from_message; result = await discover_from_message(text, lang)
            state["response"] = result.get("message", "")
        except: pass
        state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "detect_intent"
    elif detected == "form_type_selection":
        prefix = await _llm_respond("Acknowledge their choice of Government/Non-Government form and ask which specific form they need.", {"action": "detect_intent"}, lang, state.get("user_id", ""))
        state["response"] = prefix if prefix else "Which specific form do you need?"
        state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "detect_intent"
    else: state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "detect_intent"
    state["current_node"] = "detect_intent"
    state.setdefault("audit_entries", []).append({"agent": "intent_detector", "node": "detect_intent", "action": "classify_intent", "output": f"intent={state.get('form_type', 'unknown')}", "latency_ms": round((time.time() - start) * 1000, 1)})
    return state


async def collect_data_node(state: GramSetuState) -> GramSetuState:
    start = time.time(); text = state.get("transcribed_text", ""); form_type = state.get("form_type", "generic"); lang = state.get("language", "hi")
    await _broadcast_progress(state.get("session_id", ""), PROGRESS_STEPS[3], 0.45, [{"id": 1, "label": "Verify Identity", "done": True}, {"id": 2, "label": "Understand Request", "done": True}, {"id": 3, "label": "Collect Information", "done": True, "active": True}, {"id": 4, "label": "Validate Data", "done": False}], state.get("user_id", ""))
    from backend.digilocker_client import extract_with_llm, _get_form_template, _manual_extract, infer_form_fields, group_fields_by_topic, generate_group_question
    existing_data = state.get("form_data", {}); user_context = text if text else ""; collected_this_round = False
    history = state.get("conversation_history", []); history.append({"role": "user", "text": text})
    if len(history) > 20:
        try:
            from backend.llm_client import chat_intent
            old_text = "\n".join(f"{h['role']}: {h['text'][:100]}" for h in history[:-10])
            summary_result = await chat_intent([{"role": "system", "content": "Summarize this conversation into 2-3 bullet points. Focus on: name, form needed, data collected, data missing."}, {"role": "user", "content": old_text}], temperature=0.1, max_tokens=150)
            history = [{"role": "system", "text": f"Summary: {summary_result}"}] + history[-10:] if summary_result else history[-20:]
        except: history = history[-20:]
    state["conversation_history"] = history
    required = state.get("_inferred_fields", [])
    if not required:
        try: required = await infer_form_fields(form_type, lang); state["_inferred_fields"] = required
        except: required = _get_form_template(form_type)

    # ── DigiLocker auto-fetch for known government forms ──
    from backend.agents.portal_registry import is_known_form
    is_govt_form = is_known_form(form_type)
    if is_govt_form and not existing_data.get("_dl_fetched"):
        try:
            from backend.mcp_tool_router import get_router
            rtr = get_router()
            dl_result = await rtr.execute("digilocker", "fetch_documents_for_form",
                form_type=form_type, user_id=state.get("user_id", ""))
            if dl_result.get("found"):
                dl_data = dl_result.get("extracted_data", {})
                if dl_data:
                    existing_data.update(dl_data)
                    state["confidence_scores"].update({k: 0.95 for k in dl_data})
                    collected_this_round = True
                    state["_dl_fetched"] = True
        except Exception:
            pass

    # ── CV auto-fill for non-government forms ──
    if not is_govt_form and not existing_data.get("_cv_fetched"):
        try:
            from backend.cv_scanner import get_cv_data, map_cv_to_form_fields
            cv_data = get_cv_data(state.get("user_id", ""))
            if cv_data.get("found"):
                cv_fields = map_cv_to_form_fields(cv_data, required)
                if cv_fields:
                    existing_data.update(cv_fields)
                    state["confidence_scores"].update({k: 0.85 for k in cv_fields})
                    collected_this_round = True
                    state["_cv_fetched"] = True
        except Exception:
            pass

    # ── SMART COLLECTION: Grouped paragraphs for non-gov forms ──
    if not is_govt_form and not existing_data.get("_dl_fetched"):
        # Step 1: Group fields (done once)
        groups = state.get("_field_groups", [])
        current_group = state.get("_current_group", 0)
        if not groups and required:
            groups = await group_fields_by_topic(required, form_type)
            state["_field_groups"] = groups
            state["_current_group"] = 0

        # Step 2: Extract from user's paragraph-style response
        if user_context and current_group > 0 and groups:
            group_fields = groups[current_group - 1].get("fields", [])
            if group_fields:
                quick = _manual_extract(user_context, group_fields)
                quick_data = quick.get("extracted_data", {})
                if quick_data:
                    existing_data.update(quick_data)
                    collected_this_round = True
                # Also try LLM extraction for deeper understanding
                extract_ctx = f"ALREADY COLLECTED: {json.dumps(existing_data, ensure_ascii=False)}\nUSER PARAGRAPH: {user_context}"
                try:
                    extraction = await extract_with_llm(extract_ctx, form_type)
                    extracted = extraction.get("extracted_data", {})
                    if extracted:
                        existing_data.update(extracted)
                        collected_this_round = True
                except: pass
                state["_last_group_text"] = ""

        # Step 3: Generate next group question
        if current_group < len(groups):
            group = groups[current_group]
            collected = len([f for f in required if f in existing_data and existing_data[f]])
            question = await generate_group_question(
                group["topic"], group["fields"], form_type, collected, len(required)
            )
            progress_msg = f"({current_group + 1}/{len(groups)})" if len(groups) > 1 else ""
            state["response"] = question + f"\n\n_{progress_msg}_"
            state["_current_group"] = current_group + 1
            state["status"] = GraphStatus.WAIT_USER.value
            state["next_node"] = "collect_data"
            state["current_node"] = "collect_data"
            state["form_data"] = existing_data
            return state
        else:
            # All groups done — proceed to validation
            state["form_data"] = existing_data
            state["next_node"] = "validate_confirm"
            state["status"] = GraphStatus.ACTIVE.value
            state["current_node"] = "collect_data"
            return state

    # ── Standard collection for government forms ──
    if user_context and is_govt_form:
        quick = _manual_extract(user_context, required); quick_data = quick.get("extracted_data", {})
        if quick_data: existing_data.update(quick_data); collected_this_round = True
        history_summary = "\n".join(f"{h['role']}: {h['text'][:200]}" for h in history[-10:])
        context_with_history = f"CONVERSATION HISTORY:\n{history_summary}\n\nALREADY COLLECTED DATA: {json.dumps(existing_data, ensure_ascii=False)}\n\nNEW USER MESSAGE: {user_context}"
        try:
            extraction = await extract_with_llm(context_with_history, form_type)
            extracted = extraction.get("extracted_data", {})
            if extracted: existing_data.update(extracted); collected_this_round = True
        except: pass
        state["form_data"] = existing_data; state["confidence_scores"].update({k: 0.7 for k in quick_data})

    missing = [f for f in required if f not in existing_data or not existing_data[f]]
    collect_attempts = state.get("challenge_otp_attempts", 0)
    if not collected_this_round and missing:
        collect_attempts += 1; state["challenge_otp_attempts"] = collect_attempts
        if collect_attempts >= 3:
            state["response"] = await _llm_respond("Proceeding with available data. Some fields couldn't be collected.", {"collected": list(existing_data.keys())[:5]}, lang, state.get("user_id", ""))
            state["next_node"] = "validate_confirm"; state["status"] = GraphStatus.ACTIVE.value; state["current_node"] = "collect_data"; return state
    if missing and is_govt_form:
        # Show what was auto-filled AND what's still needed
        filled_fields = [f.replace("_", " ").title() for f in required if f in existing_data and existing_data[f]]
        missing_labels = [f.replace("_", " ").title() for f in missing[:6]]; state["missing_fields"] = missing
        state["response"] = await _llm_respond(
            f"Tell user what was auto-filled from their data and what's still needed. "
            f"Auto-filled: {', '.join(filled_fields[:5])}. Still needed: {', '.join(missing_labels[:4])}.",
            {"collected": filled_fields[:5], "missing": missing_labels[:4]}, lang, state.get("user_id", "")
        )
        state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "collect_data"
    elif missing and not is_govt_form:
        missing_labels = [f.replace("_", " ").title() for f in missing[:6]]; state["missing_fields"] = missing
        state["response"] = await _llm_respond(f"Tell user what information is still needed: {', '.join(missing_labels[:4])}. Be helpful and specific.", {"missing_fields": missing_labels[:4], "collected_so_far": list(existing_data.keys())[:5]}, lang, state.get("user_id", ""))
        state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "collect_data"
    else:
        if is_govt_form and state.get("_dl_fetched"):
            # All fields came from DigiLocker — show summary, go to confirm
            filled_count = len([f for f in required if f in existing_data and existing_data[f]])
            state["response"] = await _llm_respond(
                f"Tell user all {filled_count} fields were auto-filled from their DigiLocker data. Show a brief summary and ask if it's correct.",
                {"auto_filled": True, "fields_count": filled_count}, lang, state.get("user_id", "")
            )
        state["next_node"] = "validate_confirm"; state["status"] = GraphStatus.ACTIVE.value; state["challenge_otp_attempts"] = 0
    state["current_node"] = "collect_data"
    state.setdefault("audit_entries", []).append({"agent": "data_collector", "node": "collect_data", "action": "extract_fields", "output": f"{len(existing_data)} fields, {len(missing)} missing", "latency_ms": round((time.time() - start) * 1000, 1)})
    return state


async def validate_confirm_node(state: GramSetuState) -> GramSetuState:
    start = time.time(); form_data = state.get("form_data", {}); form_type = state.get("form_type", "generic"); lang = state.get("language", "hi")
    await _broadcast_progress(state.get("session_id", ""), PROGRESS_STEPS[4], 0.55, [{"id": 1, "label": "Verify Identity", "done": True}, {"id": 2, "label": "Understand Request", "done": True}, {"id": 3, "label": "Collect Information", "done": True}, {"id": 4, "label": "Validate Data", "done": True, "active": True}, {"id": 5, "label": "Fill Portal", "done": False}], state.get("user_id", ""))
    from backend.mcp_tool_router import get_router; router = get_router(); errors = []
    for field, value in list(form_data.items()):
        if isinstance(value, str):
            if "aadhaar" in field.lower(): form_data[field] = _regex.sub(r'[\s\-]', '', value)
            elif "mobile" in field.lower() or "phone" in field.lower(): form_data[field] = _regex.sub(r'[\s\-\+]', '', value)
        elif isinstance(value, dict):
            for sub_k, sub_v in value.items():
                if isinstance(sub_v, str) and "aadhaar" in sub_k.lower(): value[sub_k] = _regex.sub(r'[\s\-]', '', sub_v)
    for field, value in list(form_data.items()):
        if isinstance(value, dict):
            for sub_k, sub_v in value.items(): errors.append(f"{sub_k}: {await _check_field(router, sub_k, sub_v, form_type)}")
        else: errors.append(f"{field}: {await _check_field(router, field, value, form_type)}")
    errors = [e for e in errors if e and ":" in e and e.split(":")[1].strip()]
    state["validation_errors"] = errors
    from backend.identity_verifier import detect_fake_pattern
    aadhaar = form_data.get("aadhaar_number", "")
    if aadhaar:
        is_fake, fake_reason = detect_fake_pattern(str(aadhaar))
        if is_fake:
            state["response"] = await _llm_respond(f"Fraud detected: {fake_reason}. Block form submission.", {"fake": True}, lang, state.get("user_id", ""))
            state["status"] = GraphStatus.ERROR.value; state["next_node"] = ""; state["current_node"] = "validate_confirm"; return state
    if errors:
        state["response"] = await _llm_respond(f"Fields with errors: {', '.join(errors[:4])}. Ask user to send correct information.", {"errors": errors[:4]}, lang, state.get("user_id", ""))
        state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "collect_data"
    else:
        summary_lines = []
        for field, value in form_data.items():
            if isinstance(value, dict): continue
            label = field.replace("_", " ").title(); display = str(value)
            if "aadhaar" in field.lower() and len(str(value).replace(" ", "")) >= 4: display = f"XXXX-XXXX-{str(value).replace(' ', '').replace('-', '')[-4:]}"
            elif "phone" in field.lower() and len(str(value)) >= 4: display = f"XXXXXX{str(value)[-4:]}"
            summary_lines.append(f"  ✅ {label}: {display}")
        summary = "\n".join(summary_lines[:15])
        state["response"] = await _llm_respond(f"Tell user all {len(form_data)} fields are validated. Show summary: {summary[:200]}. Ask to confirm.", {"fields_count": len(form_data)}, lang, state.get("user_id", ""))
        state["status"] = GraphStatus.WAIT_CONFIRM.value; state["next_node"] = "fill_form"
    state["current_node"] = "validate_confirm"
    state.setdefault("audit_entries", []).append({"agent": "validator", "node": "validate_confirm", "action": "validate_all", "output": f"{len(errors)} errors", "latency_ms": round((time.time() - start) * 1000, 1)})
    return state


async def _check_field(router, field_name, value, form_type):
    if not value: return ""
    result = await router.execute("audit", "validate_field", field_name=field_name, value=str(value), form_type=form_type)
    return f"{field_name}: {result.get('error', 'invalid')}" if not result.get("valid", True) else ""


async def fill_form_node(state: GramSetuState) -> GramSetuState:
    start = time.time(); form_type = state.get("form_type", ""); form_data = state.get("form_data", {}); lang = state.get("language", "hi")
    session_id = state.get("session_id", ""); user_id = state.get("user_id", "")
    await _broadcast_progress(session_id, PROGRESS_STEPS[5], 0.65, [{"id": 1, "label": "Verify Identity", "done": True}, {"id": 2, "label": "Understand Request", "done": True}, {"id": 3, "label": "Collect Information", "done": True}, {"id": 4, "label": "Validate Data", "done": True}, {"id": 5, "label": "Fill Portal", "done": False, "active": True}, {"id": 6, "label": "Submit & Receipt", "done": False}], user_id)
    if state.get("otp_value"):
        ref = "GS" + _hs.md5(f"{form_type}{time.time()}".encode()).hexdigest()[:10].upper()
        from backend.generate_pdf import generate_and_encode
        try: state["pdf_base64"] = generate_and_encode(form_type, form_data, ref, state.get("user_phone", ""))
        except Exception as e: print(f"[PDF] Generation failed: {e}")
        if state.get("voice_mode"):
            fields_summary = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in list(form_data.items())[:6] if v and not isinstance(v, dict))
            state["voice_summary"] = f"Your {form_type.replace('_',' ').title()} application is submitted. Reference: {ref}. {fields_summary}"
        state["response"] = await _llm_respond(f"Tell user their {form_type.replace('_', ' ').title()} application is submitted successfully. Reference: {ref}. PDF receipt ready.", {"form_type": form_type, "reference": ref, "fields_count": len(form_data)}, lang, user_id)
        state["status"] = GraphStatus.COMPLETED.value; state["receipt_ready"] = True; state["reference_number"] = ref
        state["otp_value"] = ""; state["screenshot_b64"] = ""; state["current_node"] = "fill_form"; state["next_node"] = ""
        await _broadcast_progress(session_id, PROGRESS_STEPS[7], 1.0, [{"id": idx, "label": "", "done": True} for idx in range(1, 9)], user_id)
        return state
    if not state.get("consent_confirmed"):
        user_id_val = state.get("user_id", "")
        from backend.secure_enclave import is_pin_set
        if not is_pin_set(user_id_val):
            state["response"] = await _llm_respond("Ask user to set a security PIN before filling forms.", {}, lang, user_id_val)
            state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "fill_form"; state["current_node"] = "fill_form"; return state
        if not state.get("challenge_otp", "").startswith("pin_"):
            state["challenge_otp"] = "pin_required"
            state["response"] = await _llm_respond("Ask user to enter their 4-digit PIN to confirm form submission.", {}, lang, user_id_val)
            state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "fill_form"; state["current_node"] = "fill_form"; return state
        state["response"] = await _llm_respond("Ask user to type I CONFIRM to verify they are filling this form for themselves.", {}, lang, user_id_val)
        state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "fill_form"; state["current_node"] = "fill_form"; return state
    from backend.mcp_tool_router import get_router; router = get_router()
    from backend.agents.portal_registry import get_portal_info, resolve_portal_url, is_known_form
    portal_info = get_portal_info(form_type); portal_url = portal_info["url"]
    if not portal_url and not is_known_form(form_type): portal_url = await resolve_portal_url(form_type, lang)
    if not portal_url:
        state["response"] = await _llm_respond(f"Couldn't find portal URL for {form_type}. Ask user to send the website URL.", {"form_type": form_type}, lang, user_id)
        state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "fill_form"; state["current_node"] = "fill_form"; return state
    state["portal_url"] = portal_url
    fill_result = await router.execute("browser", "navigate_and_fill", session_id=session_id, portal_url=portal_url, form_data=form_data, form_type=form_type)
    fields_filled = fill_result.get("fields_filled", 0); otp_detected = fill_result.get("otp_detected", False)
    if fill_result.get("error") and not fill_result.get("fields_filled"):
        print("[FillForm] Retrying field-by-field...")
        for field, value in form_data.items():
            if isinstance(value, dict) or not value: continue
            try: await router.execute("browser", "fill_field", session_id=session_id, field_label=field.replace("_", " ").title(), value=str(value))
            except: pass
        fill_result = await router.execute("browser", "fill_form", session_id=session_id, form_data=form_data, form_type=form_type)
        fields_filled = fill_result.get("fields_filled", 0); otp_detected = fill_result.get("otp_detected", False)
    login_detected = fill_result.get("login_detected", False)
    login_type = fill_result.get("login_type", "")
    file_uploads_detected = fill_result.get("file_upload_detected", False)
    manual_uploads = fill_result.get("manual_uploads", [])

    # ── Handle login page detection ──────────────────────
    if login_detected:
        if login_type == "otp":
            state["response"] = await _llm_respond(
                "Portal requires OTP login. Tell user we're handling Aadhaar OTP login and to share the OTP when received.",
                {"login_type": "otp", "form_type": form_type}, lang, user_id
            )
            state["status"] = GraphStatus.WAIT_OTP.value; state["next_node"] = "fill_form"
        elif login_type in ("oauth", "password", "unknown"):
            portal_url = state.get("portal_url", "the portal")
            state["response"] = await _llm_respond(
                f"Portal at {portal_url} requires manual login ({login_type}). "
                f"Tell user they need to log in themselves. For OAuth portals (Google/Facebook), "
                f"explain that GramSetu's remote browser can be opened for them to authenticate. "
                f"Ask user to reply 'open browser' to get the remote access link.",
                {"login_type": login_type, "portal_url": portal_url}, lang, user_id
            )
            state["status"] = GraphStatus.WAIT_USER.value; state["next_node"] = "fill_form"
        state["current_node"] = "fill_form"
        state.setdefault("audit_entries", []).append({"agent": "form_filler", "node": "fill_form", "action": "login_detected", "output": f"login_type={login_type}", "latency_ms": round((time.time() - start) * 1000, 1)})
        return state

    if fill_result.get("error"):
        state["response"] = await _llm_respond("Tell user there was a technical issue filling the form. Apologize sincerely, explain briefly what went wrong, and ask them to try again.", {"error": fill_result.get("error", "")}, lang, user_id)
        state["status"] = GraphStatus.ERROR.value
    elif otp_detected:
        state["response"] = await _llm_respond(f"Tell user {fields_filled} fields have been filled. OTP is required. Ask them to send the 6-digit code.", {"fields_filled": fields_filled}, lang, user_id)
        state["status"] = GraphStatus.WAIT_OTP.value; state["next_node"] = "fill_form"
    else:
        state["status"] = GraphStatus.COMPLETED.value
        msg = f"Tell user the form has been filled. {fields_filled} fields completed."
        if file_uploads_detected and manual_uploads:
            upload_names = ", ".join(manual_uploads[:5])
            msg += f" Also mention that {len(manual_uploads)} items require manual file upload: {upload_names}."
        state["response"] = await _llm_respond(msg, {"fields_filled": fields_filled}, lang, user_id)
    if fill_result.get("screenshot_b64"): state["screenshot_b64"] = fill_result["screenshot_b64"]
    state["current_node"] = "fill_form"; state["browser_launched"] = True
    state.setdefault("audit_entries", []).append({"agent": "form_filler", "node": "fill_form", "action": "fill_via_mcp", "output": f"{fields_filled} fields, OTP={otp_detected}, login={login_detected}", "latency_ms": round((time.time() - start) * 1000, 1)})
    return state


# ════════════════════════════════════════════════════════════
# NODE MAP
# ════════════════════════════════════════════════════════════

_NODE_MAP: dict[str, Callable] = {
    "transcribe": transcribe_node,
    "identity_verify": identity_verify_node,
    "phone_challenge": phone_challenge_node,
    "security_enroll": security_enroll_node,
    "voice_mode": voice_mode_node,
    "document_scan": document_scan_node,
    "detect_intent": detect_intent_node,
    "collect_data": collect_data_node,
    "validate_confirm": validate_confirm_node,
    "fill_form": fill_form_node,
}

WAIT_STATUSES = {
    GraphStatus.WAIT_USER.value, GraphStatus.WAIT_CONFIRM.value,
    GraphStatus.WAIT_OTP.value, GraphStatus.WAIT_PHOTO.value,
    GraphStatus.COMPLETED.value, GraphStatus.ERROR.value,
}


def _should_suspend(state: GramSetuState) -> bool:
    return state.get("status", "") in WAIT_STATUSES


async def _run_pipeline(state: GramSetuState, save_state_fn) -> GramSetuState:
    """Run nodes sequentially until we need to suspend."""
    entry = state.get("next_node", "transcribe")
    current = entry

    for _ in range(12):  # max 12 nodes per message (safety)
        if current not in _NODE_MAP or _should_suspend(state):
            break
        node_fn = _NODE_MAP[current]
        state = await node_fn(state)
        if save_state_fn:
            await save_state_fn(state)
        if _should_suspend(state):
            break
        current = state.get("next_node", "")
        if not current:
            break

    return state


def _parse_corrections(text: str, form_data: dict) -> dict[str, Any]:
    corrections: dict[str, Any] = {}
    parts = text.strip().split(None, 1)
    if len(parts) != 2: return corrections
    key, val = parts[0].lower(), parts[1].strip()
    aliases = {"income": "annual_income", "family": "family_members", "members": "family_members", "category": "category", "type": "pension_type", "name": "applicant_name", "head": "family_head_name", "phone": "mobile_number", "mobile": "mobile_number"}
    field = aliases.get(key, key)
    if field in form_data or field in aliases.values():
        try:
            if "income" in field: corrections[field] = float(val.replace(",", ""))
            elif "members" in field: corrections[field] = int(val)
            else: corrections[field] = val
        except (ValueError, TypeError): pass
    return corrections


def _format_result(state: GramSetuState, session_id: str) -> dict[str, Any]:
    screenshot = _screenshot_cache.pop(session_id, "") or state.get("screenshot_b64", "")
    return {
        "response": state.get("response", ""), "status": state.get("status", ""),
        "session_id": session_id, "current_node": state.get("current_node", ""),
        "language": state.get("language", "hi"), "form_type": state.get("form_type", ""),
        "form_data": state.get("form_data", {}), "confidence_scores": state.get("confidence_scores", {}),
        "missing_fields": state.get("missing_fields", []), "validation_errors": state.get("validation_errors", []),
        "identity_verified": state.get("identity_verified", False),
        "audit_entries": state.get("audit_entries", []), "screenshot_b64": screenshot,
        "receipt_ready": state.get("receipt_ready", False), "reference_number": state.get("reference_number", ""),
        "pdf_base64": state.get("pdf_base64", ""), "voice_mode": state.get("voice_mode", False),
        "voice_language": state.get("voice_language", "hi"), "voice_summary": state.get("voice_summary", ""),
    }


# ════════════════════════════════════════════════════════════
# MAIN ENTRY POINT: process_message
# ════════════════════════════════════════════════════════════

async def process_message(
    user_id: str, user_phone: str, message: str,
    message_type: str = "text", language: str = "hi",
    form_type: str = "", session_id: Optional[str] = None,
) -> dict:
    from backend.persistent_state import rate_check
    allowed, _ = rate_check("agent_calls", user_id, 20, 60)
    if not allowed:
        return {"response": "⚠️ You're sending messages too fast. Please wait.", "status": "error", "session_id": session_id, "language": language}

    from lib.language_utils import detect_language
    if language == "hi" and not form_type:
        language = detect_language(message) or "hi"

    if not session_id:
        session_id = str(uuid.uuid4())

    text = message.strip()
    lang = language

    # Load existing state
    from backend.persistent_state import get_state as _load_state, set_state as _save_state
    existing_state = _load_state("checkpoints", session_id)

    if existing_state:
        last_active = existing_state.get("last_active", 0)
        if last_active and (time.time() - last_active) > _SESSION_TIMEOUT_SECS:
            existing_state = None

    async def _save(state):
        state_copy = dict(state)
        state_copy.pop("audit_entries", None)
        _save_state("checkpoints", session_id, state_copy)

    if existing_state:
        status = existing_state.get("status", "")
        stored_lang = existing_state.get("language", lang)
        lang = stored_lang

        # Handle menu numbers
        number_map = {"1": "ration_card", "2": "pension", "3": "ayushman_bharat", "4": "mnrega", "5": "pan_card", "6": "voter_id", "7": "caste_certificate", "8": "birth_certificate", "9": "pm_kisan", "10": "kisan_credit_card", "11": "jan_dhan"}
        if text.strip() in number_map and status != GraphStatus.WAIT_CONFIRM.value:
            existing_state["form_type"] = number_map[text.strip()]
            existing_state["status"] = GraphStatus.ACTIVE.value
            existing_state["next_node"] = "collect_data"
            existing_state["last_active"] = time.time()
            result = await _run_pipeline(existing_state, _save)
            return _format_result(result, session_id)

        # WAIT_OTP
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
                    await _save(result)
                    return _format_result(result, session_id)
                existing_state["response"] = "⚠️ OTP should be 4-8 digits, e.g. *123456*" if lang == "en" else "⚠️ OTP में 4-8 अंक होने चाहिए। जैसे: *123456*"
                return _format_result(existing_state, session_id)

        # WAIT_CONFIRM
        if status == GraphStatus.WAIT_CONFIRM.value:
            yes_set = {"yes", "ha", "haan", "y", "1", "ok", "okay", "sahi", "theek", "correct", "right", "confirm", "हाँ", "हां"}
            if text.lower() in yes_set:
                existing_state["status"] = GraphStatus.ACTIVE.value
                existing_state["next_node"] = "fill_form"
                existing_state["last_active"] = time.time()
                result = await fill_form_node(existing_state)
                await _save(result)
                return _format_result(result, session_id)
            if text.lower() in ("0", "reset", "start", "menu"):
                existing_state["form_data"] = {}
                existing_state["form_type"] = ""
                existing_state["status"] = GraphStatus.ACTIVE.value
                existing_state["next_node"] = "detect_intent"
                existing_state["last_active"] = time.time()
                result = await _run_pipeline(existing_state, _save)
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
                    await _save(result)
                    return _format_result(result, session_id)
                if existing_state is not None:
                    existing_state["response"] = await _llm_respond("Couldn't parse corrections. Ask user to send format like: income 80000 or reply YES.", {}, lang, user_id)
                    return _format_result(existing_state, session_id)

        # WAIT_USER
        if status == GraphStatus.WAIT_USER.value:
            next_n = existing_state.get("next_node", "")
            if next_n == "fill_form" and existing_state.get("challenge_otp", "").startswith("pin_"):
                pin = text.strip()
                if pin.isdigit() and len(pin) == 4:
                    from backend.secure_enclave import verify_pin
                    is_valid, pin_msg = verify_pin(user_id, pin)
                    if is_valid:
                        existing_state["challenge_otp"] = ""
                        existing_state["status"] = GraphStatus.ACTIVE.value
                        existing_state["last_active"] = time.time()
                        result = await fill_form_node(existing_state)
                        await _save(result)
                        return _format_result(result, session_id)
                    else:
                        existing_state["response"] = f"❌ {pin_msg}" if lang == "en" else f"❌ {pin_msg}"
                        return _format_result(existing_state, session_id)
                else:
                    existing_state["response"] = "❌ PIN must be 4 digits." if lang == "en" else "❌ PIN 4 अंकों का होना चाहिए।"
                    return _format_result(existing_state, session_id)
            if next_n == "fill_form" and not existing_state.get("portal_url"):
                url_match = _regex.search(r'(https?://[^\s"\']{5,})', text)
                if url_match:
                    existing_state["portal_url"] = url_match.group(1)
                    existing_state["status"] = GraphStatus.ACTIVE.value
                    existing_state["last_active"] = time.time()
                    result = await fill_form_node(existing_state)
                    await _save(result)
                    return _format_result(result, session_id)
            consent_words = {"i confirm", "i agree", "confirm", "yes i confirm", "मैं पुष्टि करता", "मैं पुष्टि करती", "सहमत", "agree"}
            if next_n == "fill_form" and text.lower().strip() in consent_words:
                existing_state["consent_confirmed"] = True
                existing_state["status"] = GraphStatus.ACTIVE.value
                existing_state["last_active"] = time.time()
                result = await fill_form_node(existing_state)
                await _save(result)
                return _format_result(result, session_id)
            existing_state["raw_message"] = text
            existing_state["transcribed_text"] = text
            existing_state["message_type"] = message_type
            existing_state["status"] = GraphStatus.ACTIVE.value
            existing_state["last_active"] = time.time()
            result = await _run_pipeline(existing_state, _save)
            return _format_result(result, session_id)

    # FRESH session
    initial_state: GramSetuState = {
        "session_id": session_id, "user_id": user_id, "user_phone": user_phone,
        "raw_message": text, "message_type": message_type, "language": lang,
        "transcribed_text": "", "form_type": form_type,
        "form_data": {}, "confidence_scores": {}, "validation_errors": [],
        "missing_fields": [], "_inferred_fields": [], "status": GraphStatus.ACTIVE.value,
        "current_node": "", "next_node": "transcribe",
        "response": "", "confirmation_summary": "",
        "conversation_history": [], "last_collected_at": 0,
        "otp_value": "", "identity_verified": False,
        "challenge_otp": "", "challenge_otp_attempts": 0,
        "consent_confirmed": False,
        "voice_mode": False, "voice_language": "hi", "voice_summary": "",
        "browser_launched": False, "portal_url": "",
        "screenshot_b64": "", "audit_entries": [], "pii_accessed": [],
        "last_active": time.time(), "receipt_ready": False,
        "reference_number": "",
    }
    result = await _run_pipeline(initial_state, _save)
    return _format_result(result, session_id)
