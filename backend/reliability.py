"""
============================================================
reliability.py — Deterministic Safety Layer for GramSetu v2
============================================================
Prevents unsafe automation by enforcing:
  - normalization of extracted values
  - required-field checks
  - confidence threshold checks
  - cross-field consistency checks
  - explicit human review for risky flows
"""

from __future__ import annotations

from typing import Any

from agent_core.validator import final_submission_gate, normalize_field_value
from backend.security import require_human_review
from backend.stagehand_client import build_fill_plan

LOW_CONFIDENCE_THRESHOLD = 0.98
SENSITIVE_FIELDS = {
    "aadhaar_number", "pan_number", "bank_account", "ifsc", "mobile", "phone",
    "date_of_birth", "dob", "pincode", "address", "applicant_name", "full_name"
}


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in (payload or {}).items():
        cleaned[key] = normalize_field_value(key, value)
    return cleaned


def evaluate_confidence(confidence_scores: dict[str, float] | None, payload: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    confidence_scores = confidence_scores or {}
    for field, value in (payload or {}).items():
        if value in (None, "", []):
            continue
        score = float(confidence_scores.get(field, 1.0))
        if score < LOW_CONFIDENCE_THRESHOLD:
            reasons.append(f"low_confidence:{field}:{score:.2f}")
    return len(reasons) == 0, reasons


def detect_risk_flags(payload: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    text_fields = [str(v).strip().lower() for v in payload.values() if isinstance(v, str) and v.strip()]
    if len(text_fields) != len(set(text_fields)):
        flags.append("duplicate_values_across_fields")
    if any(len(str(v)) > 120 for v in payload.values() if isinstance(v, str)):
        flags.append("suspiciously_long_field_value")
    return flags


def generate_review_checklist(form_type: str, payload: dict[str, Any], required_fields: list[str], risk_flags: list[str] | None = None) -> list[str]:
    items: list[str] = []
    present = set(k for k, v in (payload or {}).items() if v not in (None, "", []))
    for field in required_fields:
        if field in present:
            items.append(f"Verified {field.replace('_', ' ')}")
        else:
            items.append(f"Missing {field.replace('_', ' ')}")
    for flag in (risk_flags or []):
        items.append(f"Risk check: {flag.replace('_', ' ')}")
    if not items:
        items.append(f"Review core details for {form_type.replace('_', ' ')}")
    return items[:10]


def build_safe_submission_decision(form_type: str, payload: dict[str, Any], confidence_scores: dict[str, float] | None, required_fields: list[str] | None = None) -> dict[str, Any]:
    normalized = normalize_payload(payload or {})
    gate = final_submission_gate(form_type, normalized, required_fields or [])
    confidence_ok, confidence_reasons = evaluate_confidence(confidence_scores, normalized)
    risk_flags = detect_risk_flags(normalized)
    review = require_human_review(
        confidence=1.0 if confidence_ok else 0.0,
        has_otp=False,
        pii_fields_changed=False,
        consistency_errors=gate.get("consistency_errors", []) + confidence_reasons + risk_flags,
    )
    fill_plan = build_fill_plan(normalized)
    return {
        "normalized": gate.get("normalized", normalized),
        "errors": list(gate.get("field_errors", {}).values()) + gate.get("consistency_errors", []) + confidence_reasons,
        "missing": gate.get("missing", []),
        "review_required": (not gate.get("valid", False)) or (not review.get("allowed", False)),
        "review_reasons": review.get("reasons", []) + confidence_reasons,
        "risk_flags": risk_flags,
        "fill_plan": fill_plan,
        "valid": gate.get("valid", False) and confidence_ok and not risk_flags,
    }
