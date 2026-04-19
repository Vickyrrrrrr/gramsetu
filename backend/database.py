"""
============================================
database.py — Supabase Postgres Database
============================================
Stores:
  - Conversations (user messages + bot replies)
  - Audit Logs (every agent action with timestamps)
  - Form Submissions (filled forms pending confirmation)
  - User Sessions (conversation state per user)

Uses supabase-py client — set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in env.
"""

import os
import json
from datetime import datetime, timezone
from typing import Optional

from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

_client: Optional[Client] = None


def _get_client() -> Client:
    """Return a cached Supabase client, creating it on first call."""
    global _client
    if _client is None:
        if not _SUPABASE_URL or not _SUPABASE_KEY:
            raise RuntimeError(
                "[DB] SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment."
            )
        _client = create_client(_SUPABASE_URL, _SUPABASE_KEY)
    return _client


# Keep get_connection as a no-op for backward compat (storage/db.py references it)
def get_connection():
    """Legacy shim — returns the Supabase client instead of a sqlite3 connection."""
    return _get_client()


def init_db():
    """
    Validate that the Supabase connection works on startup.
    Tables are created via SQL migrations in Supabase dashboard — not here.
    """
    try:
        client = _get_client()
        # Light ping — fetch 1 row from conversations
        client.table("conversations").select("id").limit(1).execute()
        print("[DB] Supabase connection OK")
    except RuntimeError as e:
        print(f"[DB] WARNING: {e}")
    except Exception as e:
        print(f"[DB] Supabase ping failed: {e}")


# ============================================================
# Conversations
# ============================================================

def log_conversation(
    user_id: str,
    user_phone: str,
    direction: str,
    original_text: str,
    detected_language: str = "en",
    translated_text: str = None,
    bot_response: str = None,
    active_agent: str = None,
    message_type: str = "text",
):
    """Log a single message exchange to the conversations table."""
    try:
        _get_client().table("conversations").insert({
            "user_id": user_id,
            "user_phone": user_phone,
            "direction": direction,
            "message_type": message_type,
            "original_text": original_text,
            "detected_language": detected_language,
            "translated_text": translated_text,
            "bot_response": bot_response,
            "active_agent": active_agent,
        }).execute()
    except Exception as e:
        print(f"[DB] log_conversation error: {e}")


# Alias used by storage/db.py
def save_conversation(
    user_id: str,
    user_phone: str,
    direction: str,
    original_text: str,
    detected_language: str = "en",
    translated_text: str = None,
    bot_response: str = None,
    active_agent: str = None,
    message_type: str = "text",
):
    log_conversation(
        user_id=user_id, user_phone=user_phone, direction=direction,
        original_text=original_text, detected_language=detected_language,
        translated_text=translated_text, bot_response=bot_response,
        active_agent=active_agent, message_type=message_type,
    )


def get_recent_conversations(limit: int = 50) -> list:
    """Get the most recent conversations (for dashboard live feed)."""
    try:
        res = (
            _get_client()
            .table("conversations")
            .select("*")
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"[DB] get_recent_conversations error: {e}")
        return []


# ============================================================
# Audit Logs
# ============================================================

def log_audit(
    user_id: str,
    agent_name: str,
    action: str,
    input_data: dict = None,
    output_data: dict = None,
    confidence_score: float = None,
    status: str = "success",
):
    """Log an agent action to the audit trail (immutable)."""
    try:
        _get_client().table("audit_logs").insert({
            "user_id": user_id,
            "agent_name": agent_name,
            "action": action,
            "input_data": input_data,
            "output_data": output_data,
            "confidence_score": confidence_score,
            "status": status,
        }).execute()
    except Exception as e:
        print(f"[DB] log_audit error: {e}")


# Alias used by storage/db.py
def save_audit_log(
    user_id: str,
    agent_name: str,
    action: str,
    input_data: dict = None,
    output_data: dict = None,
    confidence_score: float = None,
    status: str = "success",
):
    log_audit(
        user_id=user_id, agent_name=agent_name, action=action,
        input_data=input_data, output_data=output_data,
        confidence_score=confidence_score, status=status,
    )


def get_audit_logs(limit: int = 100) -> list:
    """Get recent audit logs (for dashboard)."""
    try:
        res = (
            _get_client()
            .table("audit_logs")
            .select("*")
            .order("timestamp", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"[DB] get_audit_logs error: {e}")
        return []


# ============================================================
# Form Submissions
# ============================================================

def save_form_submission(
    user_id: str,
    form_type: str,
    form_data: dict,
    confidence_scores: dict,
    validation_result: dict,
) -> Optional[int]:
    """Save a completed form for human review."""
    try:
        res = _get_client().table("form_submissions").insert({
            "user_id": user_id,
            "form_type": form_type,
            "form_data": form_data,
            "confidence_scores": confidence_scores,
            "validation_result": validation_result,
            "status": "pending",
        }).execute()
        if res.data:
            return res.data[0].get("id")
    except Exception as e:
        print(f"[DB] save_form_submission error: {e}")
    return None


def get_form_submission(submission_id: int) -> Optional[dict]:
    """Get a single form submission by ID."""
    try:
        res = (
            _get_client()
            .table("form_submissions")
            .select("*")
            .eq("id", submission_id)
            .single()
            .execute()
        )
        return res.data
    except Exception as e:
        print(f"[DB] get_form_submission error: {e}")
        return None


def get_pending_submissions() -> list:
    """Get all forms waiting for human confirmation."""
    try:
        res = (
            _get_client()
            .table("form_submissions")
            .select("*")
            .eq("status", "pending")
            .order("created_at", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"[DB] get_pending_submissions error: {e}")
        return []


def get_all_submissions() -> list:
    """Get all form submissions (for dashboard history)."""
    try:
        res = (
            _get_client()
            .table("form_submissions")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f"[DB] get_all_submissions error: {e}")
        return []


def update_form_submission_status(
    submission_id: int, status: str, notes: str = ""
):
    """Update a form submission status (confirm / reject / submitted)."""
    try:
        _get_client().table("form_submissions").update({
            "status": status,
            "reviewer_notes": notes,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", submission_id).execute()
    except Exception as e:
        print(f"[DB] update_form_submission_status error: {e}")


def confirm_submission(submission_id: int, notes: str = ""):
    update_form_submission_status(submission_id, "confirmed", notes)


def reject_submission(submission_id: int, notes: str = ""):
    update_form_submission_status(submission_id, "rejected", notes)


# ============================================================
# User Sessions
# ============================================================

def get_session(user_id: str) -> Optional[dict]:
    """Get the current conversation state for a user."""
    try:
        res = (
            _get_client()
            .table("user_sessions")
            .select("*")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        return res.data
    except Exception:
        return None


def set_session(
    user_id: str,
    state: str,
    context: dict = None,
    language: str = None,
):
    """Upsert a user's conversation state."""
    try:
        payload = {
            "user_id": user_id,
            "current_state": state,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if context is not None:
            payload["context"] = context
        if language is not None:
            payload["language"] = language
        _get_client().table("user_sessions").upsert(payload).execute()
    except Exception as e:
        print(f"[DB] set_session error: {e}")


# ============================================================
# Dashboard Stats
# ============================================================

def get_stats() -> dict:
    """Get dashboard statistics."""
    try:
        client = _get_client()

        total_convos = (client.table("conversations").select("id", count="exact").execute()).count or 0
        total_submissions = (client.table("form_submissions").select("id", count="exact").execute()).count or 0
        pending = (client.table("form_submissions").select("id", count="exact").eq("status", "pending").execute()).count or 0
        confirmed = (client.table("form_submissions").select("id", count="exact").eq("status", "confirmed").execute()).count or 0
        rejected = (client.table("form_submissions").select("id", count="exact").eq("status", "rejected").execute()).count or 0
        total_audits = (client.table("audit_logs").select("id", count="exact").execute()).count or 0

        # Average confidence score
        conf_res = client.table("audit_logs").select("confidence_score").not_.is_("confidence_score", "null").execute()
        scores = [r["confidence_score"] for r in (conf_res.data or []) if r.get("confidence_score") is not None]
        avg_confidence = round((sum(scores) / len(scores)) * 100, 1) if scores else 0.0

        return {
            "total_conversations": total_convos,
            "total_submissions": total_submissions,
            "pending": pending,
            "pending_reviews": pending,
            "confirmed": confirmed,
            "rejected": rejected,
            "total_audit_logs": total_audits,
            "avg_confidence": avg_confidence,
        }
    except Exception as e:
        print(f"[DB] get_stats error: {e}")
        return {
            "total_conversations": 0,
            "total_submissions": 0,
            "pending": 0,
            "pending_reviews": 0,
            "confirmed": 0,
            "rejected": 0,
            "total_audit_logs": 0,
            "avg_confidence": 0.0,
        }
