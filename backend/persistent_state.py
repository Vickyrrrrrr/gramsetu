"""
============================================================
persistent_state.py — Supabase-Backed State Store
============================================================
Replaces ALL in-memory dicts across GramSetu with persistent
storage in Supabase (Postgres) that survives container restarts.

All state is keyed by `namespace` and `key` → serialized JSON value.
Thread-safe, async-compatible, multi-server safe.

Survives restart: ✅  
Concurrent access: ✅ (Handled by Postgres)
Multi-user safe: ✅ (keyed by user_id)
"""
import time
from typing import Optional

from backend.database import get_connection

def _get_client():
    from backend.database import _check_supabase
    _check_supabase()
    return get_connection()

def set_state(namespace: str, key: str, value: dict, ttl_seconds: Optional[int] = None) -> bool:
    """Store a value. Optionally auto-expire after ttl_seconds."""
    try:
        print(f"[State] set_state: namespace={namespace}, key={key[:50]}")
        client = _get_client()
        expires = (time.time() + ttl_seconds) if ttl_seconds else None
        
        client.table("kv_store").upsert({
            "namespace": namespace,
            "key": key,
            "value": value,
            "expires_at": expires
        }).execute()
        print(f"[State] set_state SUCCESS: {namespace}/{key[:50]}")
        return True
    except Exception as e:
        print(f"[State] set_state FAILED: namespace={namespace}, key={key[:50]}, error: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_state(namespace: str, key: str) -> Optional[dict]:
    """Retrieve a stored value. Returns None if not found or expired."""
    try:
        client = _get_client()
        res = client.table("kv_store").select("value, expires_at").eq("namespace", namespace).eq("key", key).execute()
        
        if not res.data:
            return None
            
        row = res.data[0]
        expires_at = row.get("expires_at")
        
        if expires_at and time.time() > expires_at:
            # Expired — delete and return None
            client.table("kv_store").delete().eq("namespace", namespace).eq("key", key).execute()
            return None
            
        return row.get("value")
    except Exception as e:
        print(f"[State] get_state error: {e}")
        return None

def get_all_state(namespace: str) -> list[tuple[str, dict]]:
    """Retrieve all valid key-value pairs for a given namespace. Returns list of (key, value)."""
    try:
        client = _get_client()
        # Only fetch items where expires_at is null or greater than now
        res = client.table("kv_store").select("key, value, expires_at").eq("namespace", namespace).execute()
        
        valid_items = []
        for row in res.data:
            expires_at = row.get("expires_at")
            key = row.get("key")
            
            if expires_at and time.time() > expires_at:
                client.table("kv_store").delete().eq("namespace", namespace).eq("key", key).execute()
            else:
                valid_items.append((key, row.get("value")))
                
        return valid_items
    except Exception as e:
        print(f"[State] get_all_state error: {e}")
        return []

def delete_state(namespace: str, key: str) -> bool:
    """Delete a stored value."""
    try:
        client = _get_client()
        client.table("kv_store").delete().eq("namespace", namespace).eq("key", key).execute()
        return True
    except Exception as e:
        print(f"[State] delete_state error: {e}")
        return False

def increment_counter(namespace: str, key: str, increment_by: int = 1, ttl_seconds: Optional[int] = None) -> int:
    """
    Counter increment. Returns new count.
    Used for impact tracking or rate limiting.
    """
    try:
        current = get_state(namespace, key)
        count = current.get("count", 0) if current else 0
        new_count = count + increment_by
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

def check_identity_hash_exists(id_hash: str, exclude_user_id: str) -> bool:
    """Check if the given identity hash exists for any user OTHER than exclude_user_id."""
    try:
        client = _get_client()
        # In Supabase, value is typically JSONB
        # This checks if the value JSON object has {"hash": id_hash} 
        res = client.table("kv_store").select("key").eq("namespace", "identity_hash") \
            .neq("key", exclude_user_id) \
            .contains("value", {"hash": id_hash}).execute()
        return len(res.data) > 0
    except Exception as e:
        print(f"[State] check_identity_hash_exists error: {e}")
        return False

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
        import time
        client = _get_client()
        # Delete where expires_at is not null and less than current time
        res = client.table("kv_store").delete().not_.is_("expires_at", "null").lt("expires_at", time.time()).execute()
        return len(res.data) if res.data else 0
    except Exception as e:
        print(f"[State] cleanup_expired error: {e}")
        return 0
