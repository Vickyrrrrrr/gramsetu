"""
============================================
agents.py — 4-Agent Multi-Agent System
============================================
Powered by NVIDIA NIMs (Llama 3.1 70B Instruct).
Uses a simple state-machine approach (LangGraph-style).

4 Agents:
  1. Orchestrator: Detects intent, routes to correct agent
  2. Form Filler: Extracts entities, fills JSON form, assigns confidence
  3. Validator: Rule-based checks (Aadhaar checksum, PAN format, etc.)
  4. Safety: Audit logs, human confirmation before submission
"""

import json
import uuid
from datetime import datetime
from typing import Optional

from agent_core.nims_client import (
    detect_intent,
    extract_entities,
    generate_response,
    translate_text,
    is_nim_available,
)
from agent_core.validator import validate_field
from agent_core.schemas import (
    load_form_schema,
    get_available_forms,
    get_next_missing_field,
)
import data.db as db


# ============================================
# AGENT STATE — Shared context between agents
# ============================================

class AgentState:
    """Shared state that flows between agents during a conversation turn."""
    def __init__(self, user_id: str, user_phone: str, message: str, language: str = "hi"):
        self.user_id = user_id
        self.user_phone = user_phone
        self.message = message              # Original user message
        self.language = language             # Detected language
        self.translated_message = message    # English translation (if needed)
        self.intent = None                   # Detected intent
        self.form_type = None                # Which form to fill
        self.active_agent = "orchestrator"   # Currently active agent
        self.response = ""                   # Final response to user
        self.form_data = {}                  # Filled form fields
        self.confidence_scores = {}          # Confidence per field
        self.validation_result = {}          # Validation results
        self.audit_entries = []              # Audit trail for this turn


# ============================================
# AGENT 1: ORCHESTRATOR
# ============================================

def orchestrator_agent(state: AgentState) -> AgentState:
    """
    The Orchestrator is the "brain" — it decides what to do.
    
    Responsibilities:
    - Detect language (Hindi/English)
    - Detect user intent (greeting, apply, check status, etc.)
    - Route to the correct agent
    - Manage conversation state
    """
    state.active_agent = "orchestrator"
    
    # Get or create user session
    session = db.get_session(state.user_id)
    if not session:
        db.set_session(state.user_id, "greeting", {}, state.language)
        session = {"current_state": "greeting", "context": {}, "language": state.language}
    
    current_state = session.get("current_state", "greeting")
    context = session.get("context", {})
    
    # Detect intent using NIM (or fallback)
    intent_result = detect_intent(state.message)
    state.intent = intent_result.get("intent", "unknown")
    state.form_type = intent_result.get("form_type") or context.get("form_type")
    state.language = intent_result.get("language", session.get("language", "hi"))
    
    # Log the orchestrator action
    state.audit_entries.append({
        "agent": "orchestrator",
        "action": "detect_intent",
        "input": {"message": state.message, "state": current_state},
        "output": intent_result,
        "confidence": 0.9 if is_nim_available() else 0.6,
    })
    
    # Handle "reset" command
    if state.message.strip().lower() in ["reset", "0", "restart"]:
        db.set_session(state.user_id, "greeting", {}, state.language)
        state.response = _greeting_message(state.language)
        return state
    
    # ---- State Machine ----
    
    if current_state == "greeting" or state.intent == "greeting":
        state.response = _greeting_message(state.language)
        db.set_session(state.user_id, "awaiting_choice", {}, state.language)
        return state
    
    if state.intent == "apply_form" or current_state == "awaiting_choice" and state.message.strip() in ["1", "2"]:
        # Determine form type
        if state.message.strip() == "1":
            state.form_type = "pan_card"
        elif state.message.strip() == "2":
            state.form_type = "pm_kisan"
        
        if not state.form_type:
            state.response = _form_selection_message(state.language)
            db.set_session(state.user_id, "awaiting_choice", {}, state.language)
            return state
        
        # Start form filling
        context["form_type"] = state.form_type
        context["form_data"] = {}
        context["confidence_scores"] = {}
        db.set_session(state.user_id, "filling_form", context, state.language)
        
        schema = load_form_schema(state.form_type)
        form_name = schema.name_hi if state.language == "hi" else schema.name
        
        # Get first field prompt
        next_field = get_next_missing_field(state.form_type, {})
        if next_field:
            prompt = next_field.ask_prompt_hi if state.language == "hi" else next_field.ask_prompt_en
            if state.language == "hi":
                state.response = f"✅ {form_name} शुरू करते हैं!\n\n{prompt}"
            else:
                state.response = f"✅ Let's start {form_name}!\n\n{prompt}"
        
        return state
    
    if current_state == "filling_form":
        # Route to Form Filler Agent
        state.form_type = context.get("form_type")
        state.form_data = context.get("form_data", {})
        state.confidence_scores = context.get("confidence_scores", {})
        state = form_filler_agent(state)
        return state
    
    if state.intent == "check_status":
        if state.language == "hi":
            state.response = "📊 आपका आवेदन प्रक्रियाधीन है। कृपया कुछ दिनों बाद जाँचें।\n\nमुख्य मेन्यू: 0 भेजें"
        else:
            state.response = "📊 Your application is being processed. Please check back in a few days.\n\nMain menu: send 0"
        return state
    
    if state.intent == "help":
        state.response = _greeting_message(state.language)
        return state
    
    # Default: try to continue conversation
    if current_state == "awaiting_choice":
        state.response = _form_selection_message(state.language)
        return state
    
    # Unknown intent
    if state.language == "hi":
        state.response = "🤔 मैं समझ नहीं पाया। कृपया चुनें:\n1️⃣ पैन कार्ड आवेदन\n2️⃣ पीएम-किसान आवेदन\n\nया 0 भेजें रीसेट के लिए"
    else:
        state.response = "🤔 I didn't understand. Please choose:\n1️⃣ PAN Card Application\n2️⃣ PM-KISAN Application\n\nOr send 0 to reset"
    
    return state


# ============================================
# AGENT 2: FORM FILLER
# ============================================

def form_filler_agent(state: AgentState) -> AgentState:
    """
    The Form Filler extracts entities from user messages and fills form fields.
    
    Responsibilities:
    - Extract entities (name, Aadhaar, DOB, etc.) using NIM
    - Fill form JSON structure
    - Assign confidence scores (0-100%) per field
    - Ask for next missing field
    """
    state.active_agent = "form_filler"
    
    session = db.get_session(state.user_id)
    context = session.get("context", {})
    form_data = context.get("form_data", {})
    confidence_scores = context.get("confidence_scores", {})
    form_type = context.get("form_type", state.form_type)
    
    if not form_type:
        state.response = _form_selection_message(state.language)
        return state
    
    # Use NIM to extract entities from the message
    extracted = extract_entities(state.message, form_type, form_data)
    
    # If NIM didn't extract anything, try simple value assignment
    next_field = get_next_missing_field(form_type, form_data)
    
    if not extracted and next_field:
        # Assume the user's message IS the answer to the last question
        value = state.message.strip()
        if value.lower() not in ["skip", "छोड़ें"]:
            extracted = {
                next_field.key: {
                    "value": value,
                    "confidence": 0.75  # Lower confidence for direct assignment
                }
            }
    
    # Update form data with extracted values
    for field_key, field_info in extracted.items():
        if isinstance(field_info, dict):
            form_data[field_key] = field_info.get("value", "")
            confidence_scores[field_key] = field_info.get("confidence", 0.5)
        else:
            form_data[field_key] = str(field_info)
            confidence_scores[field_key] = 0.5
    
    # Log extraction
    state.audit_entries.append({
        "agent": "form_filler",
        "action": "extract_entities",
        "input": {"message": state.message, "form_type": form_type},
        "output": {"extracted": extracted, "form_data": form_data},
        "confidence": sum(confidence_scores.values()) / max(len(confidence_scores), 1),
    })
    
    # Check if there are more fields to fill
    next_field = get_next_missing_field(form_type, form_data)
    
    if next_field:
        # Ask for the next field
        prompt = next_field.ask_prompt_hi if state.language == "hi" else next_field.ask_prompt_en
        
        # Show progress
        schema = load_form_schema(form_type)
        total = len([f for f in schema.fields if f.required])
        filled = len(form_data)
        progress = f"[{filled}/{total}]"
        
        state.response = f"✅ {progress} {prompt}"
        
        # Save progress
        context["form_data"] = form_data
        context["confidence_scores"] = confidence_scores
        db.set_session(state.user_id, "filling_form", context, state.language)
    else:
        # All fields filled → Route to Validator Agent
        state.form_data = form_data
        state.confidence_scores = confidence_scores
        
        # Save progress
        context["form_data"] = form_data
        context["confidence_scores"] = confidence_scores
        db.set_session(state.user_id, "validating", context, state.language)
        
        state = validator_agent(state)
    
    return state


# ============================================
# AGENT 3: VALIDATOR
# ============================================

def validator_agent(state: AgentState) -> AgentState:
    """
    The Validator checks all form fields using rule-based validation.
    
    Responsibilities:
    - Validate Aadhaar checksum, PAN format, PINCODE, phone, etc.
    - Adjust confidence scores based on validation
    - Flag errors before submission
    - Route to Safety Agent if everything is valid
    """
    state.active_agent = "validator"
    
    session = db.get_session(state.user_id)
    context = session.get("context", {})
    form_data = context.get("form_data", {})
    confidence_scores = context.get("confidence_scores", {})
    form_type = context.get("form_type", state.form_type)
    
    validation_results = {}
    errors = []
    
    # Validate each field
    for field_key, value in form_data.items():
        result = validate_field(field_key, value)
        validation_results[field_key] = result
        
        # Adjust confidence based on validation
        if field_key in confidence_scores:
            boost = result.get("confidence_boost", 0)
            confidence_scores[field_key] = min(1.0, max(0.0, confidence_scores[field_key] + boost))
        
        if not result["valid"]:
            errors.append(f"❌ {field_key}: {result['error']}")
    
    state.validation_result = validation_results
    state.confidence_scores = confidence_scores
    
    # Log validation
    avg_confidence = sum(confidence_scores.values()) / max(len(confidence_scores), 1)
    state.audit_entries.append({
        "agent": "validator",
        "action": "validate_form",
        "input": {"form_data": form_data},
        "output": {"validation_results": validation_results, "errors": errors},
        "confidence": avg_confidence,
    })
    
    if errors:
        # Show errors and ask for corrections
        error_text = "\n".join(errors)
        if state.language == "hi":
            state.response = f"⚠️ कुछ फ़ील्ड में त्रुटि मिली:\n\n{error_text}\n\nकृपया सही जानकारी दोबारा भेजें।\nरीसेट: 0 भेजें"
        else:
            state.response = f"⚠️ Some fields have errors:\n\n{error_text}\n\nPlease send corrected information.\nReset: send 0"
        
        # Go back to filling (remove invalid fields)
        for field_key in list(form_data.keys()):
            if field_key in validation_results and not validation_results[field_key]["valid"]:
                del form_data[field_key]
                if field_key in confidence_scores:
                    del confidence_scores[field_key]
        
        context["form_data"] = form_data
        context["confidence_scores"] = confidence_scores
        db.set_session(state.user_id, "filling_form", context, state.language)
    else:
        # All valid → Route to Safety Agent
        state = safety_agent(state)
    
    return state


# ============================================
# AGENT 4: SAFETY AGENT
# ============================================

def safety_agent(state: AgentState) -> AgentState:
    """
    The Safety Agent ensures human verification before submission.
    
    Responsibilities:
    - Generate immutable audit log
    - Create form summary for human review
    - Queue for admin confirmation
    - NEVER auto-submit — always require human approval
    """
    state.active_agent = "safety"
    
    session = db.get_session(state.user_id)
    context = session.get("context", {})
    form_data = context.get("form_data", {})
    confidence_scores = context.get("confidence_scores", {})
    form_type = context.get("form_type", state.form_type)
    
    # Save form submission to database (pending human confirmation)
    submission_id = db.save_form_submission(
        user_id=state.user_id,
        form_type=form_type,
        form_data=form_data,
        confidence_scores=confidence_scores,
        validation_result=state.validation_result,
    )
    
    # Generate audit log entry
    avg_confidence = sum(confidence_scores.values()) / max(len(confidence_scores), 1)
    state.audit_entries.append({
        "agent": "safety",
        "action": "queue_for_review",
        "input": {"form_type": form_type, "submission_id": submission_id},
        "output": {"status": "pending", "avg_confidence": round(avg_confidence * 100, 1)},
        "confidence": avg_confidence,
    })
    
    # Build summary for response
    schema = load_form_schema(form_type)
    form_name = schema.name_hi if state.language == "hi" else schema.name
    
    summary_lines = []
    for field in schema.fields:
        if field.key in form_data:
            label = field.label_hi if state.language == "hi" else field.label
            value = form_data[field.key]
            conf = confidence_scores.get(field.key, 0)
            conf_emoji = "🟢" if conf >= 0.8 else "🟡" if conf >= 0.5 else "🔴"
            summary_lines.append(f"  {conf_emoji} {label}: {value} ({int(conf*100)}%)")
    
    summary = "\n".join(summary_lines)
    
    if state.language == "hi":
        state.response = (
            f"📋 *{form_name}*\n\n"
            f"{summary}\n\n"
            f"📊 औसत विश्वसनीयता: {int(avg_confidence*100)}%\n\n"
            f"🛡️ आपका आवेदन एडमिन समीक्षा के लिए भेजा गया है।\n"
            f"✅ एडमिन द्वारा स्वीकृत होने के बाद ही सबमिट होगा।\n\n"
            f"मुख्य मेन्यू: 0 भेजें"
        )
    else:
        state.response = (
            f"📋 *{form_name}*\n\n"
            f"{summary}\n\n"
            f"📊 Average Confidence: {int(avg_confidence*100)}%\n\n"
            f"🛡️ Your application has been sent for admin review.\n"
            f"✅ It will only be submitted after admin approval.\n\n"
            f"Main menu: send 0"
        )
    
    # Reset session to greeting
    db.set_session(state.user_id, "greeting", {}, state.language)
    
    return state


# ============================================
# MAIN ENTRY POINT — Process a user message
# ============================================

def process_message(user_id: str, user_phone: str, message: str,
                    message_type: str = "text") -> dict:
    """
    Process an incoming message through the multi-agent pipeline.
    
    This is the main function called by the WhatsApp webhook.
    
    Args:
        user_id: Unique user identifier (phone number)
        user_phone: User's phone number
        message: Text message (or transcribed voice)
        message_type: "text" or "voice"
    
    Returns:
        {
            "response": "Bot's reply text",
            "language": "hi" or "en",
            "active_agent": "which agent handled this",
            "audit_entries": [...],
            "form_data": {...},
            "confidence_scores": {...}
        }
    """
    # Detect language from message
    has_hindi = any('\u0900' <= c <= '\u097F' for c in message)
    initial_lang = "hi" if has_hindi else "en"
    
    # Create shared state
    state = AgentState(user_id, user_phone, message, initial_lang)
    
    # Run through Orchestrator (which routes to other agents as needed)
    state = orchestrator_agent(state)
    
    # Save all audit entries to database
    for entry in state.audit_entries:
        db.log_audit(
            user_id=user_id,
            agent_name=entry["agent"],
            action=entry["action"],
            input_data=entry.get("input"),
            output_data=entry.get("output"),
            confidence_score=entry.get("confidence"),
        )
    
    # Log the conversation
    db.log_conversation(
        user_id=user_id,
        user_phone=user_phone,
        direction="incoming",
        original_text=message,
        detected_language=state.language,
        translated_text=state.translated_message if state.language != "en" else None,
        bot_response=state.response,
        active_agent=state.active_agent,
        message_type=message_type,
    )
    
    return {
        "response": state.response,
        "language": state.language,
        "active_agent": state.active_agent,
        "audit_entries": state.audit_entries,
        "form_data": state.form_data,
        "confidence_scores": state.confidence_scores,
    }


# ============================================
# HELPER: Pre-built response messages
# ============================================

def _greeting_message(lang: str) -> str:
    """Generate a warm greeting message."""
    if lang == "hi":
        return (
            "🙏 *ग्रामसेतु* में आपका स्वागत है!\n\n"
            "मैं आपकी सरकारी फ़ॉर्म भरने में मदद करता हूँ।\n\n"
            "कृपया चुनें:\n"
            "1️⃣ पैन कार्ड आवेदन\n"
            "2️⃣ पीएम-किसान आवेदन\n"
            "3️⃣ आवेदन स्थिति जाँचें\n\n"
            "📱 आप हिंदी या English में बात कर सकते हैं!"
        )
    return (
        "🙏 Welcome to *GramSetu*!\n\n"
        "I help you fill government forms automatically.\n\n"
        "Please choose:\n"
        "1️⃣ PAN Card Application\n"
        "2️⃣ PM-KISAN Application\n"
        "3️⃣ Check Application Status\n\n"
        "📱 You can chat in Hindi or English!"
    )


def _form_selection_message(lang: str) -> str:
    """Ask user to select a form."""
    if lang == "hi":
        return (
            "📝 कौन सा फ़ॉर्म भरना है?\n\n"
            "1️⃣ पैन कार्ड आवेदन (Form 49A)\n"
            "2️⃣ पीएम-किसान सम्मान निधि\n\n"
            "नंबर भेजें (1 या 2):"
        )
    return (
        "📝 Which form do you want to fill?\n\n"
        "1️⃣ PAN Card Application (Form 49A)\n"
        "2️⃣ PM-KISAN Samman Nidhi\n\n"
        "Send the number (1 or 2):"
    )
