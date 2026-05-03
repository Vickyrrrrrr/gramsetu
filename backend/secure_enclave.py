"""
============================================================
secure_enclave.py — GramSetu PIN + Selfie Security Module
============================================================
Now backed by persistent SQLite state — survives restarts.
"""
import hashlib
import base64
from backend.persistent_state import (
    store_pin as _store_pin, get_pin as _get_pin,
    store_selfie as _store_selfie, get_selfie as _get_selfie,
)

_MAX_CHALLENGE_ATTEMPTS = 3
_CHALLENGE_TTL = 300


def hash_pin(pin: str, user_id: str) -> str:
    salt = f"gramsetu_pin_{user_id}_2026"
    return hashlib.sha256(f"{salt}:{pin}".encode()).hexdigest()


def set_pin(user_id: str, pin: str) -> bool:
    if not pin.isdigit() or len(pin) != 4:
        return False
    return _store_pin(user_id, hash_pin(pin, user_id))


def verify_pin(user_id: str, pin: str) -> tuple[bool, str]:
    from backend.persistent_state import rate_check
    # Check lockout
    allowed, remaining = rate_check("pin_lock", user_id, _MAX_CHALLENGE_ATTEMPTS, 1800)
    if not allowed:
        return False, f"Account locked for 30 minutes. {remaining} attempts remaining."

    stored_hash = _get_pin(user_id)
    if not stored_hash:
        return False, "No PIN set. Send: SET PIN 1234"

    if pin.isdigit() and len(pin) == 4 and hash_pin(pin, user_id) == stored_hash:
        return True, "PIN verified."
    else:
        remaining -= 1
        return False, f"Wrong PIN. {remaining} attempts remaining." if remaining > 0 else "Locked 30 min."


def is_pin_set(user_id: str) -> bool:
    return _get_pin(user_id) is not None


def is_locked(user_id: str) -> tuple[bool, str]:
    from backend.persistent_state import rate_check
    allowed, _ = rate_check("pin_lock", user_id, _MAX_CHALLENGE_ATTEMPTS, 1800)
    if not allowed:
        return True, "Account locked."
    # Reset lockout if not locked
    from backend.persistent_state import delete_state
    delete_state("pin_lock", f"rate_{user_id}")
    return False, ""


def store_selfie_hash(user_id: str, image_b64: str) -> bool:
    print(f"[Selfie] store_selfie_hash called for user={user_id}")
    print(f"[Selfie] image_b64 length: {len(image_b64) if image_b64 else 0}")
    if not image_b64 or len(image_b64) < 500:
        print(f"[Selfie] FAILED: image_b64 too small or empty (len={len(image_b64) if image_b64 else 0})")
        return False
    try:
        img_bytes = base64.b64decode(image_b64)
        print(f"[Selfie] Decoded image bytes: {len(img_bytes)} bytes")
        _hash = hashlib.sha256(img_bytes[:2048]).hexdigest()
        print(f"[Selfie] Hash computed: {_hash[:16]}...")
        result = _store_selfie(user_id, _hash)
        print(f"[Selfie] _store_selfie result: {result}")
        return result
    except Exception as e:
        print(f"[Selfie] FAILED: Exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_selfie(user_id: str, fresh_image_b64: str) -> tuple[bool, str]:
    if not _get_selfie(user_id):
        return False, "No reference selfie enrolled."

    if not fresh_image_b64 or len(fresh_image_b64) < 500:
        return False, "Selfie too small. Send a clear face photo."

    stored_hash = _get_selfie(user_id)
    try:
        fresh_bytes = base64.b64decode(fresh_image_b64)
        fresh_hash = hashlib.sha256(fresh_bytes[:2048]).hexdigest()
        if fresh_hash == stored_hash:
            return False, "Same photo as reference. Send a fresh selfie."
        if len(fresh_bytes) < 10000:
            return False, "Selfie too small. Send a clear photo."
        return True, "Selfie accepted."
    except Exception as e:
        return False, f"Verification failed: {e}"


def is_selfie_enrolled(user_id: str) -> bool:
    return _get_selfie(user_id) is not None


def has_security_enrolled(user_id: str) -> bool:
    return is_pin_set(user_id) and is_selfie_enrolled(user_id)
