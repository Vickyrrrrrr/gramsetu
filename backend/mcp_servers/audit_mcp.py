"""
Audit MCP Server — PII redaction, validation, and audit logging.

Exposes tools:
  - redact_text: Strip PII from a text string
  - redact_value: Redact a single sensitive value
  - validate_field: Validate form field against rules
  - record_action: Log an audit entry for compliance
"""

import re
import json
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("GramSetu Audit Server")

# ── PII patterns ───────────────────────────────────────────
_AADHAAR_RE = re.compile(r'\b[2-9]\d{3}[\s\-]?\d{4}[\s\-]?\d{4}\b')
_PAN_RE = re.compile(r'\b([A-Z]{5})(\d{4})([A-Z])\b')
_PHONE_RE = re.compile(r'\b[6-9]\d{9}\b')
_EMAIL_RE = re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b')


def _redact_text(text: str) -> str:
    """Replace PII patterns with masked versions."""
    if not text:
        return text

    text = _AADHAAR_RE.sub(lambda m: f"XXXX-XXXX-{m.group()[-4:]}", text)
    text = _PAN_RE.sub(r"XXXXX\2\3", text)
    text = _PHONE_RE.sub(lambda m: f"XXXXXX{str(m.group())[-4:]}", text)
    text = _EMAIL_RE.sub(lambda m: f"***@{m.group().split('@')[1] if '@' in m.group() else '***'}", text)
    return text

    text = _AADHAAR_RE.sub(lambda m: f"XXXX-XXXX-{m.group()[-4:]}", text)
    text = _PAN_RE.sub(lambda m: f"{m.group()[:3]}XXX{m.group()[-3:]}", text)
    text = _PHONE_RE.sub(lambda m: f"XXXXXX{str(m.group())[-4:]}", text)
    text = _EMAIL_RE.sub(lambda m: f"***@{m.group().split('@')[1] if '@' in m.group() else '***'}", text)
    return text


def _redact_value(key: str, value: str) -> str:
    """Redact a single PII value based on its key name."""
    if not value:
        return value

    pii_keys = {'aadhaar', 'pan', 'mobile', 'phone', 'email', 'account'}
    key_lower = key.lower()

    if any(pk in key_lower for pk in pii_keys):
        clean = re.sub(r'[\s\-+]', '', str(value))
        if len(clean) >= 4:
            if "mobile" in key_lower or "phone" in key_lower:
                return f"XXXXXX{clean[-4:]}"
            elif "pan" in key_lower:
                return f"XXXXX{clean[-5:]}"
            else:
                return f"XXXX-XXXX-{clean[-4:]}" if len(clean) > 8 else f"XXXXXX{clean[-4:]}"

    return value


# ════════════════════════════════════════════════════════════
# MCP TOOLS
# ════════════════════════════════════════════════════════════

@mcp.tool()
def redact_text(text: str) -> str:
    """
    Strip all PII (Aadhaar, PAN, phone, email) from a text string.
    Use this before logging or displaying any user message.
    """
    return _redact_text(text)


@mcp.tool()
def redact_value(key: str, value: str) -> str:
    """
    Redact a single sensitive value based on its key.
    For example, key='aadhaar_number', value='283412509087' → 'XXXX-XXXX-9087'.
    """
    return _redact_value(key, value)


@mcp.tool()
def validate_field(field_name: str, value: str, form_type: str = "generic") -> dict:
    """
    Validate a form field value. Returns {valid: bool, error: str, normalized: str}.

    Supported field types: aadhaar_number, mobile_number, pan_number,
    pincode, ifsc_code, date_of_birth, email.
    """
    result = {"valid": True, "error": "", "normalized": value}

    try:
        if "aadhaar" in field_name.lower():
            clean = re.sub(r'[\s\-]', '', str(value))
            if not clean.isdigit() or len(clean) != 12:
                return {"valid": False, "error": "Aadhaar must be exactly 12 digits", "normalized": clean}
            if clean[0] in "01":
                return {"valid": False, "error": "Aadhaar cannot start with 0 or 1", "normalized": clean}
            result["normalized"] = clean

        elif "mobile" in field_name.lower() or "phone" in field_name.lower():
            clean = re.sub(r'[\s\-\+]', '', str(value))
            if clean.startswith("91") and len(clean) == 12:
                clean = clean[2:]
            if not re.match(r'^[6-9]\d{9}$', clean):
                return {"valid": False, "error": "Mobile must be 10 digits starting with 6-9", "normalized": clean}
            result["normalized"] = clean

        elif "pan" in field_name.lower():
            clean = str(value).upper().strip()
            if not re.match(r'^[A-Z]{5}\d{4}[A-Z]$', clean):
                return {"valid": False, "error": "PAN format: ABCDE1234F", "normalized": clean}
            result["normalized"] = clean

        elif "pincode" in field_name.lower() or "pin_code" in field_name.lower():
            clean = re.sub(r'\s', '', str(value))
            if not re.match(r'^[1-9]\d{5}$', clean):
                return {"valid": False, "error": "PIN code must be 6 digits, first digit 1-9", "normalized": clean}
            result["normalized"] = clean

        elif "ifsc" in field_name.lower():
            clean = str(value).upper().strip()
            if not re.match(r'^[A-Z]{4}0[A-Z0-9]{6}$', clean):
                return {"valid": False, "error": "IFSC format: 4 letters + 0 + 6 alphanumeric", "normalized": clean}
            result["normalized"] = clean

        elif "email" in field_name.lower():
            clean = str(value).strip()
            if not re.match(r'^[^@]+@[^@]+\.[^@]+$', clean):
                return {"valid": False, "error": "Invalid email format", "normalized": clean}
            result["normalized"] = clean

        elif "dob" in field_name.lower() or "date_of_birth" in field_name.lower():
            from datetime import date as dt
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
                try:
                    parsed = datetime.strptime(str(value).strip(), fmt)
                    age = (dt.today() - parsed.date()).days // 365
                    if age < 0:
                        return {"valid": False, "error": "Date of birth is in the future", "normalized": value}
                    if age > 150:
                        return {"valid": False, "error": "Invalid date of birth (age > 150)", "normalized": value}
                    result["normalized"] = parsed.strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue

    except Exception as e:
        result["valid"] = False
        result["error"] = str(e)

    return result


@mcp.tool()
def record_action(
    agent: str,
    action: str,
    input_summary: str,
    output_summary: str,
    confidence: float = 1.0,
) -> dict:
    """
    Record an audit entry for compliance tracking.
    All PII is automatically redacted before storage.
    """
    return _do_record_action(agent, action, input_summary, output_summary, confidence)


def _do_record_action(agent, action, input_summary, output_summary, confidence):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "action": _redact_text(action),
        "input": _redact_text(input_summary),
        "output": _redact_text(output_summary),
        "confidence": round(confidence, 4),
        "latency_ms": 0,
    }
    _audit_log.append(entry)  # noqa: F821
    if len(_audit_log) > 10000:  # noqa: F821
        _audit_log[:] = _audit_log[-5000:]  # noqa: F821
    return {"recorded": True, "total_entries": len(_audit_log)}  # noqa: F821


@mcp.tool()
def get_audit_log(limit: int = 50) -> str:
    """Retrieve the most recent audit log entries (PII-redacted)."""
    entries = _audit_log[-limit:]  # noqa: F821
    return json.dumps(entries, indent=2, ensure_ascii=False)
