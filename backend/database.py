"""
============================================
db.py — SQLite Database for Audit Logs
============================================
Stores:
  - Conversations (user messages + bot replies)
  - Audit Logs (every agent action with timestamps)
  - Form Submissions (filled forms pending confirmation)

SQLite is built into Python — no installation needed!
"""

import sqlite3
import json
import os
from datetime import datetime

# Database file path — sits in the data/ folder for persistence
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "gramsetu.db")


def get_connection():
    """Get a database connection with row_factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Create all database tables if they don't exist.
    Call this once when the server starts.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Conversations: stores each message exchange
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            user_phone TEXT,
            direction TEXT NOT NULL,           -- 'incoming' or 'outgoing'
            message_type TEXT DEFAULT 'text',   -- 'text', 'voice', 'image'
            original_text TEXT,                 -- original user message
            detected_language TEXT DEFAULT 'en',
            translated_text TEXT,               -- English translation (if Hindi input)
            bot_response TEXT,                  -- bot's reply
            active_agent TEXT,                  -- which agent handled this
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Audit Logs: immutable record of every agent action
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,           -- 'orchestrator', 'form_filler', 'validator', 'safety'
            action TEXT NOT NULL,               -- what the agent did
            input_data TEXT,                    -- JSON: what was sent to the agent
            output_data TEXT,                   -- JSON: what the agent returned
            confidence_score REAL,              -- 0.0 to 1.0
            status TEXT DEFAULT 'success',      -- 'success', 'error', 'pending'
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Form Submissions: filled forms waiting for human confirmation
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS form_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            form_type TEXT NOT NULL,            -- 'pan_card', 'pm_kisan', etc.
            form_data TEXT NOT NULL,            -- JSON: filled form fields
            confidence_scores TEXT,             -- JSON: confidence per field
            validation_result TEXT,             -- JSON: validator output
            status TEXT DEFAULT 'pending',      -- 'pending', 'confirmed', 'rejected', 'submitted'
            reviewer_notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # User Sessions: tracks conversation state per user
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_sessions (
            user_id TEXT PRIMARY KEY,
            current_state TEXT DEFAULT 'greeting',
            context TEXT DEFAULT '{}',          -- JSON: conversation context
            language TEXT DEFAULT 'hi',
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print(f"[DB] Database initialized at {DB_PATH}")


# ---- Conversation Logging ----

def log_conversation(user_id: str, user_phone: str, direction: str,
                     original_text: str, detected_language: str = "en",
                     translated_text: str = None, bot_response: str = None,
                     active_agent: str = None, message_type: str = "text"):
    """Log a single message exchange to the conversations table."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO conversations 
        (user_id, user_phone, direction, message_type, original_text,
         detected_language, translated_text, bot_response, active_agent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, user_phone, direction, message_type, original_text,
          detected_language, translated_text, bot_response, active_agent))
    conn.commit()
    conn.close()


def get_recent_conversations(limit: int = 50):
    """Get the most recent conversations (for dashboard live feed)."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM conversations ORDER BY timestamp DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---- Audit Logging ----

def log_audit(user_id: str, agent_name: str, action: str,
              input_data: dict = None, output_data: dict = None,
              confidence_score: float = None, status: str = "success"):
    """Log an agent action to the audit trail (immutable)."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO audit_logs 
        (user_id, agent_name, action, input_data, output_data, confidence_score, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, agent_name, action,
          json.dumps(input_data) if input_data else None,
          json.dumps(output_data) if output_data else None,
          confidence_score, status))
    conn.commit()
    conn.close()


def get_audit_logs(limit: int = 100):
    """Get recent audit logs (for dashboard)."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        if d.get("input_data"):
            try:
                d["input_data"] = json.loads(d["input_data"])
            except json.JSONDecodeError:
                pass
        if d.get("output_data"):
            try:
                d["output_data"] = json.loads(d["output_data"])
            except json.JSONDecodeError:
                pass
        result.append(d)
    return result


# ---- Form Submissions ----

def save_form_submission(user_id: str, form_type: str, form_data: dict,
                         confidence_scores: dict, validation_result: dict):
    """Save a completed form for human review."""
    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO form_submissions 
        (user_id, form_type, form_data, confidence_scores, validation_result)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, form_type, json.dumps(form_data),
          json.dumps(confidence_scores), json.dumps(validation_result)))
    submission_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return submission_id


def get_pending_submissions():
    """Get all forms waiting for human confirmation."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM form_submissions WHERE status = 'pending' ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        for key in ["form_data", "confidence_scores", "validation_result"]:
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except json.JSONDecodeError:
                    pass
        result.append(d)
    return result


def confirm_submission(submission_id: int, notes: str = ""):
    """Admin confirms a form submission."""
    conn = get_connection()
    conn.execute("""
        UPDATE form_submissions 
        SET status = 'confirmed', reviewer_notes = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (notes, submission_id))
    conn.commit()
    conn.close()


def reject_submission(submission_id: int, notes: str = ""):
    """Admin rejects a form submission."""
    conn = get_connection()
    conn.execute("""
        UPDATE form_submissions 
        SET status = 'rejected', reviewer_notes = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (notes, submission_id))
    conn.commit()
    conn.close()


def get_all_submissions():
    """Get all form submissions (for dashboard history)."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM form_submissions ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        for key in ["form_data", "confidence_scores", "validation_result"]:
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except json.JSONDecodeError:
                    pass
        result.append(d)
    return result


# ---- User Sessions ----

def get_session(user_id: str):
    """Get the current conversation state for a user."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM user_sessions WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    if row:
        d = dict(row)
        try:
            d["context"] = json.loads(d["context"])
        except json.JSONDecodeError:
            d["context"] = {}
        return d
    return None


def set_session(user_id: str, state: str, context: dict = None, language: str = None):
    """Update or create a user's conversation state."""
    conn = get_connection()
    existing = conn.execute("SELECT user_id FROM user_sessions WHERE user_id = ?", (user_id,)).fetchone()
    
    if existing:
        updates = ["current_state = ?", "updated_at = CURRENT_TIMESTAMP"]
        params = [state]
        if context is not None:
            updates.append("context = ?")
            params.append(json.dumps(context))
        if language is not None:
            updates.append("language = ?")
            params.append(language)
        params.append(user_id)
        conn.execute(f"UPDATE user_sessions SET {', '.join(updates)} WHERE user_id = ?", params)
    else:
        conn.execute("""
            INSERT INTO user_sessions (user_id, current_state, context, language)
            VALUES (?, ?, ?, ?)
        """, (user_id, state, json.dumps(context or {}), language or "hi"))
    
    conn.commit()
    conn.close()


def get_stats():
    """Get dashboard statistics."""
    conn = get_connection()
    total_convos = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    total_submissions = conn.execute("SELECT COUNT(*) FROM form_submissions").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM form_submissions WHERE status = 'pending'").fetchone()[0]
    confirmed = conn.execute("SELECT COUNT(*) FROM form_submissions WHERE status = 'confirmed'").fetchone()[0]
    rejected = conn.execute("SELECT COUNT(*) FROM form_submissions WHERE status = 'rejected'").fetchone()[0]
    total_audits = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    avg_conf_row = conn.execute("""
        SELECT AVG(confidence_score) FROM audit_logs
        WHERE confidence_score IS NOT NULL
    """).fetchone()
    conn.close()
    avg_confidence = round((avg_conf_row[0] or 0) * 100, 1)
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
