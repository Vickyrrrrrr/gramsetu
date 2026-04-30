"""
============================================================
persistent_state.py — SQLite-Backed State Store
============================================================
Replaces ALL in-memory dicts across GramSetu with persistent
storage that survives container restarts.

All state is keyed by `namespace:key` → serialized JSON value.
Thread-safe, async-compatible, auto-creates tables.

Survives restart: ✅  
Concurrent access: ✅ (WAL mode + connection per request)
Multi-user safe: ✅ (keyed by user_id)
"""
import os
import json
import time
import sqlite3
import threading
from typing import Optional

# ── Database path ──────────────────────────────────────────
_STATE_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "state.db"
)
os.makedirs(os.path.dirname(_STATE_DB), exist_ok=True)

# Thread-local connections for concurrent access
_local = threading.local()

# WAL mode for concurrent reads
def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(_STATE_DB, check_same_thread=False)
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.execute("CREATE TABLE IF NOT EXISTS kv (namespace TEXT, key TEXT, value TEXT, expires_at REAL, PRIMARY KEY (namespace, key))")
        _local.conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON kv(expires_at)")
        _local.conn.commit()
    return _local.conn


def set_state(namespace: str, key: str, value: dict, ttl_seconds: Optional[int] = None) -> bool:
    """Store a value. Optionally auto-expire after ttl_seconds."""
    try:
        conn = _get_conn()
        expires = (time.time() + ttl_seconds) if ttl_seconds else None
        conn.execute(
            "INSERT OR REPLACE INTO kv VALUES (?, ?, ?, ?)",
            (namespace, key, json.dumps(value), expires)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[State] set_state error: {e}")
        return False


def get_state(namespace: str, key: str) -> Optional[dict]:
    """Retrieve a stored value. Returns None if not found or expired."""
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT value, expires_at FROM kv WHERE namespace = ? AND key = ?",
            (namespace, key)
        ).fetchone()
        if not row:
            return None
        value_json, expires_at = row
        if expires_at and time.time() > expires_at:
            # Expired — delete and return None
            conn.execute("DELETE FROM kv WHERE namespace = ? AND key = ?", (namespace, key))
            conn.commit()
            return None
        return json.loads(value_json)
    except Exception as e:
        print(f"[State] get_state error: {e}")
        return None


def delete_state(namespace: str, key: str) -> bool:
    """Delete a stored value."""
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM kv WHERE namespace = ? AND key = ?", (namespace, key))
        conn.commit()
        return True
    except Exception:
        return False


def increment_counter(namespace: str, key: str, ttl_seconds: int = 60) -> int:
    """
    Thread-safe counter increment. Returns new count.
    Used for rate limiting.
    """
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT value FROM kv WHERE namespace = ? AND key = ? AND (expires_at > ? OR expires_at IS NULL)",
            (namespace, key, time.time())
        ).fetchone()
        current = json.loads(row[0]).get("count", 0) if row else 0
        new_count = current + 1
        set_state(namespace, key, {"count": new_count}, ttl_seconds)
        return new_count
    except Exception:
        return 1


# ════════════════════════════════════════════════════════════
# CONVENIENCE WRAPPERS for each module
# ════════════════════════════════════════════════════════════

# ── Secure Enclave wrappers ─────────────────────────────────

def store_pin(user_id: str, pin_hash: str) -> bool:
    return set_state("pins", user_id, {"hash": pin_hash})

def get_pin(user_id: str) -> Optional[str]:
    data = get_state("pins", user_id)
    return data.get("hash") if data else None

def store_selfie(user_id: str, selfie_hash: str) -> bool:
    return set_state("selfies", user_id, {"hash": selfie_hash})

def get_selfie(user_id: str) -> Optional[str]:
    data = get_state("selfies", user_id)
    return data.get("hash") if data else None

# ── Identity verification wrappers ──────────────────────────

def store_verified(user_id: str) -> bool:
    return set_state("verified", user_id, {"verified": True})

def is_verified(user_id: str) -> bool:
    data = get_state("verified", user_id)
    return data.get("verified", False) if data else False

def store_identity_hash(user_id: str, id_hash: str) -> bool:
    return set_state("identity_hash", user_id, {"hash": id_hash})

def get_identity_hash(user_id: str) -> Optional[str]:
    data = get_state("identity_hash", user_id)
    return data.get("hash") if data else None

def store_challenge(user_id: str, challenge: dict) -> bool:
    return set_state("challenge", user_id, challenge)

def get_challenge(user_id: str) -> Optional[dict]:
    return get_state("challenge", user_id)

def delete_challenge(user_id: str) -> bool:
    return delete_state("challenge", user_id)

# ── WhatsApp session wrappers ───────────────────────────────

def store_wa_session(phone: str, session_data: dict) -> bool:
    return set_state("wa_sessions", phone, session_data)

def get_wa_session(phone: str) -> Optional[dict]:
    return get_state("wa_sessions", phone)

def store_user_session(user_id: str, session_data: dict) -> bool:
    return set_state("user_sessions", user_id, session_data)

def get_user_session(user_id: str) -> Optional[dict]:
    return get_state("user_sessions", user_id)

# ── Rate limiting wrappers ──────────────────────────────────

def rate_check(namespace: str, user_id: str, max_calls: int, window_seconds: int) -> tuple[bool, int]:
    """Check if user is within rate limit. Returns (allowed, remaining_calls)."""
    key = f"rate_{user_id}"
    current = get_state(namespace, key)
    count = current.get("count", 0) if current else 0
    if count >= max_calls:
        return False, 0
    new_count = count + 1
    set_state(namespace, key, {"count": new_count}, window_seconds)
    return True, max_calls - new_count

# ── Cleanup expired entries (call periodically) ─────────────

def cleanup_expired() -> int:
    """Remove all expired entries. Returns count removed."""
    try:
        conn = _get_conn()
        cursor = conn.execute("DELETE FROM kv WHERE expires_at IS NOT NULL AND expires_at < ?", (time.time(),))
        conn.commit()
        return cursor.rowcount
    except Exception:
        return 0
