"""
============================================================
security.py — Security Middleware for GramSetu v3
============================================================
Provides:
  - Twilio webhook signature validation
  - Rate limiting (in-memory, no Redis needed)
  - PII encryption/decryption for checkpoint DB
  - Input sanitization
"""

import os
import re
import time
import hmac
import hashlib
import base64
from typing import Optional
from functools import wraps
from collections import defaultdict
from urllib.parse import urlencode
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

# ── Encryption Key ───────────────────────────────────────────
# Auto-generate if not set; in production, set PII_ENCRYPTION_KEY in .env
_ENC_KEY = os.getenv("PII_ENCRYPTION_KEY", "")
if not _ENC_KEY:
    _ENC_KEY = Fernet.generate_key().decode()
    # Store for this session
    os.environ["PII_ENCRYPTION_KEY"] = _ENC_KEY

_fernet = Fernet(_ENC_KEY.encode() if isinstance(_ENC_KEY, str) else _ENC_KEY)


# ============================================================
# 1. Twilio Webhook Signature Validation
# ============================================================

def validate_twilio_signature(url: str, params: dict, signature: str) -> bool:
    """
    Validate that a webhook request actually came from Twilio.
    Uses HMAC-SHA1 as per Twilio docs.

    Args:
        url:       The full webhook URL (https://your-domain.com/webhook)
        params:    The POST body parameters as a dict
        signature: The X-Twilio-Signature header value

    Returns:
        True if signature is valid (request is from Twilio)
    """
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not auth_token:
        # No auth token configured — skip validation (dev mode)
        return True

    # Allow disabling validation for local dev/ngrok testing
    if os.getenv("TWILIO_VALIDATION", "true").lower() in ("false", "0", "no", "skip"):
        return True

    # Sort params and append to URL
    sorted_params = sorted(params.items())
    data = url + "".join(f"{k}{v}" for k, v in sorted_params)

    # HMAC-SHA1
    computed = base64.b64encode(
        hmac.new(
            auth_token.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha1,
        ).digest()
    ).decode("utf-8")

    return hmac.compare_digest(computed, signature)


# ============================================================
# 2. Rate Limiting (In-Memory, No Redis)
# ============================================================

class RateLimiter:
    """
    Simple in-memory rate limiter.
    Window-based: allows N requests per window.
    """

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        """Check if a request from this key is allowed."""
        now = time.time()
        window_start = now - self.window

        # Clean old entries
        self._requests[key] = [t for t in self._requests[key] if t > window_start]

        if len(self._requests[key]) >= self.max_requests:
            return False

        self._requests[key].append(now)
        return True

    def remaining(self, key: str) -> int:
        """How many requests remaining in the current window."""
        now = time.time()
        window_start = now - self.window
        recent = [t for t in self._requests[key] if t > window_start]
        return max(0, self.max_requests - len(recent))


# Global rate limiters
webhook_limiter = RateLimiter(max_requests=30, window_seconds=60)   # 30 msgs/min per user
api_limiter = RateLimiter(max_requests=60, window_seconds=60)       # 60 req/min per IP


# ============================================================
# 3. PII Encryption
# ============================================================

PII_FIELD_NAMES = {
    "aadhaar_number", "mobile_number", "phone_number", "pan_number",
    "account_number", "ifsc_code", "user_phone", "otp_value",
}


def encrypt_pii(value: str) -> str:
    """Encrypt a PII value for storage."""
    if not value:
        return value
    return _fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_pii(value: str) -> str:
    """Decrypt a PII value."""
    if not value:
        return value
    try:
        return _fernet.decrypt(value.encode("utf-8")).decode("utf-8")
    except Exception:
        return value  # Already decrypted or not encrypted


def encrypt_state_pii(state: dict) -> dict:
    """Encrypt PII fields in a graph state dict before checkpointing."""
    encrypted = state.copy()
    for key in PII_FIELD_NAMES:
        if key in encrypted and encrypted[key]:
            encrypted[key] = encrypt_pii(str(encrypted[key]))

    # Also encrypt PII inside form_data
    if "form_data" in encrypted and isinstance(encrypted["form_data"], dict):
        form = encrypted["form_data"].copy()
        for key in PII_FIELD_NAMES:
            if key in form and form[key]:
                form[key] = encrypt_pii(str(form[key]))
        encrypted["form_data"] = form

    return encrypted


def decrypt_state_pii(state: dict) -> dict:
    """Decrypt PII fields in a graph state dict after loading."""
    decrypted = state.copy()
    for key in PII_FIELD_NAMES:
        if key in decrypted and decrypted[key]:
            decrypted[key] = decrypt_pii(str(decrypted[key]))

    if "form_data" in decrypted and isinstance(decrypted["form_data"], dict):
        form = decrypted["form_data"].copy()
        for key in PII_FIELD_NAMES:
            if key in form and form[key]:
                form[key] = decrypt_pii(str(form[key]))
        decrypted["form_data"] = form

    return decrypted


# ============================================================
# 4. Input Sanitization
# ============================================================

def sanitize_input(text: str, max_length: int = 500) -> str:
    """
    Sanitize user input:
    - Strip leading/trailing whitespace
    - Limit length
    - Remove control characters
    - Basic XSS prevention
    """
    if not text:
        return ""

    # Truncate
    text = text[:max_length].strip()

    # Remove control characters (keep newlines)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Basic script tag removal
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)

    return text


def validate_otp_input(text: str) -> Optional[str]:
    """
    Validate OTP input — must be 4-6 digits.
    Handles common formats: "4839 21", "4-8-3-9-2-1", "four eight three..."
    """
    # Remove spaces, dashes, dots
    clean = re.sub(r"[\s\-\.]", "", text.strip())

    # Word-to-digit for Hindi/English voice input
    word_map = {
        "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
        "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
        "शून्य": "0", "एक": "1", "दो": "2", "तीन": "3", "चार": "4",
        "पांच": "5", "छह": "6", "सात": "7", "आठ": "8", "नौ": "9",
    }

    # Try word-based OTP (voice input)
    words = text.lower().strip().split()
    if all(w in word_map for w in words) and 4 <= len(words) <= 6:
        clean = "".join(word_map[w] for w in words)

    # Must be 4-6 digits
    if re.match(r"^\d{4,6}$", clean):
        return clean

    return None


# ============================================================
# 5. Session Cleanup
# ============================================================

def cleanup_expired_sessions(sessions: dict, max_age_hours: int = 24) -> int:
    """Remove sessions older than max_age_hours. Returns count removed."""
    now = time.time()
    max_age = max_age_hours * 3600
    expired = [k for k, v in sessions.items()
               if isinstance(v, dict) and
               (now - v.get("created_at", now)) > max_age]

    for k in expired:
        del sessions[k]

    return len(expired)
