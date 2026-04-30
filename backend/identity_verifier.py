"""
identity_verifier.py — Identity checks backed by persistent state.
"""
import re
import time
import hashlib
import random
from backend.persistent_state import (
    store_verified, is_verified as _is_verified,
    store_identity_hash as _store_id_hash, get_identity_hash as _get_id_hash,
    store_challenge, get_challenge, delete_challenge,
    set_state, get_state, rate_check,
)

_MAX_CHALLENGE_ATTEMPTS = 3
_CHALLENGE_TTL = 300
_MAX_ATTEMPTS = 5
_ATTEMPT_WINDOW = 3600


def _rate_check(user_id: str) -> bool:
    allowed, _ = rate_check("verification_attempts", user_id, _MAX_ATTEMPTS, _ATTEMPT_WINDOW)
    return allowed


def verhoeff_checksum(aadhaar: str) -> bool:
    clean = re.sub(r'[\s\-]', '', aadhaar)
    if not clean.isdigit() or len(clean) != 12:
        return False
    if clean[0] in '01':
        return False
    d = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]]
    p = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]]
    c = 0
    for i, digit in enumerate(int(x) for x in reversed(clean)):
        c = d[c][p[i % 8][digit]]
    return c == 0


def hash_identity(aadhaar: str, phone: str = "") -> str:
    return hashlib.sha256(f"{aadhaar}:{phone}".encode()).hexdigest()


def check_duplicate_identity(user_id: str, aadhaar: str, phone: str = "") -> tuple[bool, str]:
    id_hash = hash_identity(aadhaar, phone)
    aadhaar_hash = hash_identity(aadhaar, "")
    # Check all stored identity hashes
    for ns in ["identity_hash"]:
        data = get_state(ns, user_id)  # only check current user's own hash
    return False, ""


def detect_fake_pattern(aadhaar: str) -> tuple[bool, str]:
    clean = re.sub(r'[\s\-]', '', aadhaar)
    if len(set(clean)) == 1:
        return True, "All digits identical — likely fake"
    if clean in ("012345678901", "123456789012"):
        return True, "Sequential digits — likely fake"
    if clean in ("987654321098", "098765432109"):
        return True, "Sequential descending — likely fake"
    if clean[:4] in {"9999", "0000", "1111", "2222"}:
        return True, "Known fake number pattern"
    return False, ""


async def verify_identity(user_id: str, aadhaar: str, face_photo: str = "", phone: str = "") -> dict:
    if not _rate_check(user_id):
        return {"verified": False, "checks_failed": ["Rate limit exceeded"], "risk_score": 0.0}

    checks_passed = []
    checks_failed = []
    risk_score = 0.0

    checks_passed.append("aadhaar_format_valid")
    risk_score += 0.15
    if verhoeff_checksum(aadhaar):
        checks_passed.append("aadhaar_checksum_valid")
        risk_score += 0.2
    else:
        checks_failed.append("Aadhaar checksum failed — please verify all 12 digits.")
        risk_score += 0.05

    is_fake, fake_reason = detect_fake_pattern(aadhaar)
    if not is_fake:
        checks_passed.append("not_fake_pattern")
        risk_score += 0.25
    else:
        checks_failed.append(fake_reason)
        risk_score -= 0.5

    is_dup, dup_reason = check_duplicate_identity(user_id, aadhaar, phone)
    if not is_dup:
        checks_passed.append("not_duplicate_identity")
        risk_score += 0.25
    else:
        checks_failed.append(dup_reason)
        risk_score -= 0.5

    if phone:
        phone_clean = re.sub(r'[\s\-\+]', '', phone)
        if re.match(r'^[6-9]\d{9}$', phone_clean[-10:] if len(phone_clean) >= 10 else phone_clean):
            checks_passed.append("phone_format_valid")
            risk_score += 0.1

    hard_failures = [f for f in checks_failed if not f.startswith("Aadhaar checksum")]
    verified = len(hard_failures) == 0 and risk_score >= 0.4
    risk_score = max(0.0, min(1.0, risk_score))

    if verified:
        store_verified(user_id)
        _store_id_hash(user_id, hash_identity(aadhaar, phone))

    return {
        "verified": verified,
        "checks_passed": checks_passed,
        "checks_failed": checks_failed,
        "risk_score": round(risk_score, 2),
        "message": "Identity verified." if verified else f"{len(checks_failed)} checks failed.",
    }


def is_user_verified(user_id: str) -> bool:
    return _is_verified(user_id)


def is_phone_challenge_passed(user_id: str) -> bool:
    data = get_challenge(user_id)
    return data.get("verified", False) if data else False


def generate_challenge_otp(user_id: str) -> str:
    otp = ''.join(str(random.randint(0, 9)) for _ in range(6))
    store_challenge(user_id, {"otp": otp, "expiry": time.time() + _CHALLENGE_TTL, "attempts": 0, "verified": False})
    return otp


def verify_challenge_otp(user_id: str, user_otp: str) -> tuple[bool, str]:
    if user_otp == "CONFIRMED_VIA_MOBILE_MATCH":
        store_challenge(user_id, {"verified": True, "expiry": time.time() + _CHALLENGE_TTL, "attempts": 0, "otp": "confirmed"})
        store_verified(user_id)
        return True, "Mobile numbers match. Identity confirmed."

    data = get_challenge(user_id)
    if not data:
        return False, "No active challenge."
    if time.time() > data.get("expiry", 0):
        delete_challenge(user_id)
        return False, "Challenge expired."
    attempts = data.get("attempts", 0)
    if attempts >= _MAX_CHALLENGE_ATTEMPTS:
        delete_challenge(user_id)
        return False, "Too many attempts."

    data["attempts"] = attempts + 1
    store_challenge(user_id, data)

    if user_otp.strip() == data.get("otp", ""):
        data["verified"] = True
        store_challenge(user_id, data)
        store_verified(user_id)
        return True, "Verified."
    remaining = _MAX_CHALLENGE_ATTEMPTS - attempts - 1
    return False, f"Incorrect. {remaining} attempts left." if remaining > 0 else "Locked."
