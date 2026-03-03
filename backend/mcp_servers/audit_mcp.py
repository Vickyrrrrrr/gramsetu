"""
============================================================
audit_mcp.py — Audit & Observability MCP Tool Server
============================================================
FastMCP server for real-time logging of agent reasoning.
Exposes tools for the LangGraph to log decisions, track PII access,
and stream audit events to the Streamlit dashboard.

Tools:
  - log_reasoning:     Log an agent's decision with confidence score
  - log_pii_access:    Record when PII is accessed (with redaction)
  - get_audit_trail:   Retrieve the full audit trail for a session
  - get_agent_metrics: Dashboard metrics (latency, confidence, etc.)
  - redact_pii:        Mask PII fields for safe display

PII Redaction Rules:
  - Aadhaar: XXXX-XXXX-1234 (show last 4 only)
  - Phone:   XXXXXX3210 (show last 4 only)
  - PAN:     XXXXX1234X (show digits only)
"""

import os
import re
import time
import json
import asyncio
from datetime import datetime, timezone
from typing import Optional

import aiosqlite
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

DB_PATH = os.getenv("AUDIT_DB_PATH", os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "audit.db"
))

# ── FastMCP Server ───────────────────────────────────────────
mcp = FastMCP(
    name="gramsetu-audit",
    instructions="Real-time audit logging and PII redaction for GramSetu — "
                 "streams agent reasoning to the dashboard.",
)

# ── In-memory event buffer for streaming ─────────────────────
_event_buffer: list[dict] = []
_MAX_BUFFER = 500


# ============================================================
# Database Setup
# ============================================================

async def _ensure_db():
    """Create audit tables if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                node_name TEXT,
                action TEXT NOT NULL,
                input_summary TEXT,
                output_summary TEXT,
                confidence REAL DEFAULT 0.0,
                latency_ms REAL DEFAULT 0.0,
                pii_accessed BOOLEAN DEFAULT FALSE,
                metadata TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pii_access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                action TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                redacted_value TEXT
            )
        """)
        await db.commit()


# ============================================================
# TOOL 1: Log Agent Reasoning
# ============================================================

@mcp.tool()
async def log_reasoning(
    session_id: str,
    user_id: str,
    agent_name: str,
    node_name: str,
    action: str,
    input_summary: str,
    output_summary: str,
    confidence: float = 0.0,
    latency_ms: float = 0.0,
    pii_accessed: bool = False,
    metadata: Optional[dict] = None,
) -> dict:
    """
    Log an agent's reasoning step to the audit trail.
    PII must be redacted from input_summary and output_summary BEFORE calling this.

    Args:
        session_id:     Unique session identifier
        user_id:        User identifier (phone hash, not raw phone)
        agent_name:     Which agent made the decision
        node_name:      LangGraph node name (Transcribe, Extract, etc.)
        action:         What the agent did (e.g., 'extract_entities')
        input_summary:  PII-redacted summary of input
        output_summary: PII-redacted summary of output
        confidence:     Agent's confidence (0.0–1.0)
        latency_ms:     Time taken for this step in milliseconds
        pii_accessed:   Whether PII was accessed in this step
        metadata:       Optional extra metadata dict

    Returns:
        {"logged": True, "audit_id": N}
    """
    await _ensure_db()

    timestamp = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(metadata) if metadata else None

    # Redact any accidental PII in summaries
    input_summary = _redact_text(input_summary)
    output_summary = _redact_text(output_summary)

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO audit_log
               (timestamp, session_id, user_id, agent_name, node_name,
                action, input_summary, output_summary, confidence,
                latency_ms, pii_accessed, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, session_id, user_id, agent_name, node_name,
             action, input_summary, output_summary, confidence,
             latency_ms, pii_accessed, meta_json),
        )
        await db.commit()
        audit_id = cursor.lastrowid

    # Buffer for real-time streaming
    event = {
        "id": audit_id,
        "timestamp": timestamp,
        "agent": agent_name,
        "node": node_name,
        "action": action,
        "confidence": confidence,
        "latency_ms": latency_ms,
    }
    _event_buffer.append(event)
    if len(_event_buffer) > _MAX_BUFFER:
        _event_buffer.pop(0)

    return {"logged": True, "audit_id": audit_id}


# ============================================================
# TOOL 2: Log PII Access
# ============================================================

@mcp.tool()
async def log_pii_access(
    session_id: str,
    user_id: str,
    field_name: str,
    action: str,
    agent_name: str,
    raw_value: str,
) -> dict:
    """
    Record when PII data is accessed or used.
    The raw_value is automatically redacted before storage.

    Args:
        session_id:  Unique session identifier
        user_id:     User identifier
        field_name:  PII field name (e.g., 'aadhaar_number', 'phone')
        action:      What was done ('read', 'typed_to_portal', 'validated')
        agent_name:  Which agent accessed the PII
        raw_value:   The actual PII value (will be redacted before storage)

    Returns:
        {"logged": True, "redacted_value": "XXXX-XXXX-1234"}
    """
    await _ensure_db()

    timestamp = datetime.now(timezone.utc).isoformat()
    redacted = _redact_value(field_name, raw_value)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO pii_access_log
               (timestamp, session_id, user_id, field_name, action,
                agent_name, redacted_value)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, session_id, user_id, field_name, action,
             agent_name, redacted),
        )
        await db.commit()

    return {"logged": True, "redacted_value": redacted}


# ============================================================
# TOOL 3: Get Audit Trail
# ============================================================

@mcp.tool()
async def get_audit_trail(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """
    Retrieve the audit trail for a session or user.

    Args:
        session_id: Filter by session (optional)
        user_id:    Filter by user (optional)
        limit:      Maximum number of entries to return

    Returns:
        {"entries": [...], "total": N}
    """
    await _ensure_db()

    query = "SELECT * FROM audit_log"
    params = []
    conditions = []

    if session_id:
        conditions.append("session_id = ?")
        params.append(session_id)
    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        entries = []
        for row in rows:
            entries.append({
                "id": row["id"],
                "timestamp": row["timestamp"],
                "agent_name": row["agent_name"],
                "node_name": row["node_name"],
                "action": row["action"],
                "input_summary": row["input_summary"],
                "output_summary": row["output_summary"],
                "confidence": row["confidence"],
                "latency_ms": row["latency_ms"],
                "pii_accessed": bool(row["pii_accessed"]),
            })

    return {"entries": entries, "total": len(entries)}


# ============================================================
# TOOL 4: Get Agent Metrics
# ============================================================

@mcp.tool()
async def get_agent_metrics(hours: int = 24) -> dict:
    """
    Get aggregated metrics for the Streamlit dashboard.

    Args:
        hours: Look-back period in hours (default 24)

    Returns:
        {
            "total_sessions": N,
            "avg_confidence": 0.85,
            "avg_latency_ms": 250.0,
            "agents": {"orchestrator": {"calls": N, "avg_conf": ...}, ...},
            "recent_events": [last 10 events]
        }
    """
    await _ensure_db()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Total sessions
        cursor = await db.execute(
            "SELECT COUNT(DISTINCT session_id) as cnt FROM audit_log"
        )
        row = await cursor.fetchone()
        total_sessions = row["cnt"] if row else 0

        # Overall averages
        cursor = await db.execute(
            "SELECT AVG(confidence) as avg_conf, AVG(latency_ms) as avg_lat FROM audit_log"
        )
        row = await cursor.fetchone()
        avg_confidence = round(row["avg_conf"] or 0, 3)
        avg_latency = round(row["avg_lat"] or 0, 1)

        # Per-agent metrics
        cursor = await db.execute(
            """SELECT agent_name,
                      COUNT(*) as calls,
                      AVG(confidence) as avg_conf,
                      AVG(latency_ms) as avg_lat
               FROM audit_log
               GROUP BY agent_name"""
        )
        agent_rows = await cursor.fetchall()
        agents = {}
        for r in agent_rows:
            agents[r["agent_name"]] = {
                "calls": r["calls"],
                "avg_confidence": round(r["avg_conf"] or 0, 3),
                "avg_latency_ms": round(r["avg_lat"] or 0, 1),
            }

    return {
        "total_sessions": total_sessions,
        "avg_confidence": avg_confidence,
        "avg_latency_ms": avg_latency,
        "agents": agents,
        "recent_events": _event_buffer[-10:],
    }


# ============================================================
# TOOL 5: Redact PII
# ============================================================

@mcp.tool()
async def redact_pii(data: dict) -> dict:
    """
    Redact PII fields from a data dictionary for safe display.

    Args:
        data: Dictionary that may contain PII fields

    Returns:
        {"redacted": {...}, "fields_redacted": ["aadhaar_number", ...]}
    """
    pii_fields = {
        "aadhaar_number", "aadhaar", "phone", "mobile_number",
        "phone_number", "pan_number", "pan", "bank_account",
        "account_number", "ifsc_code",
    }

    redacted = {}
    fields_redacted = []

    for key, value in data.items():
        if key.lower() in pii_fields and value:
            redacted[key] = _redact_value(key, str(value))
            fields_redacted.append(key)
        elif isinstance(value, str):
            redacted[key] = _redact_text(value)
        else:
            redacted[key] = value

    return {"redacted": redacted, "fields_redacted": fields_redacted}


# ============================================================
# PII Redaction Helpers (NEVER store raw PII)
# ============================================================

def _redact_value(field_name: str, value: str) -> str:
    """Redact a specific PII field value."""
    field = field_name.lower()
    clean = re.sub(r"[\s\-]", "", value)

    if "aadhaar" in field:
        if len(clean) >= 4:
            return f"XXXX-XXXX-{clean[-4:]}"
        return "XXXX-XXXX-XXXX"

    if "phone" in field or "mobile" in field:
        if len(clean) >= 4:
            return f"XXXXXX{clean[-4:]}"
        return "XXXXXXXXXX"

    if "pan" in field:
        if len(clean) >= 5:
            return f"XXXXX{clean[5:]}"
        return "XXXXXXXXXX"

    if "account" in field or "bank" in field:
        if len(clean) >= 4:
            return f"{'X' * (len(clean) - 4)}{clean[-4:]}"
        return "X" * len(clean)

    # Generic: show first 2, mask middle, show last 2
    if len(value) > 6:
        return value[:2] + "X" * (len(value) - 4) + value[-2:]

    return "X" * len(value)


def _redact_text(text: str) -> str:
    """Scan free text and redact any PII patterns found."""
    # Aadhaar: 12 digits (with optional spaces/dashes)
    text = re.sub(
        r"\b(\d{4})[\s\-]?(\d{4})[\s\-]?(\d{4})\b",
        lambda m: f"XXXX-XXXX-{m.group(3)}",
        text,
    )
    # Phone: 10 digits starting with 6-9
    text = re.sub(
        r"\b([6-9]\d{5})(\d{4})\b",
        lambda m: f"XXXXXX{m.group(2)}",
        text,
    )
    # PAN: ABCDE1234F
    text = re.sub(
        r"\b([A-Z]{5})(\d{4}[A-Z])\b",
        lambda m: f"XXXXX{m.group(2)}",
        text,
    )
    return text


# ── Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="sse", host="0.0.0.0", port=8102)
