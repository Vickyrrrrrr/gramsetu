"""Shared runtime state for GramSetu API."""
from __future__ import annotations
from typing import TypedDict
from backend.core import get_settings

settings = get_settings()

_user_sessions: dict[str, dict] = {}
_completed_forms: dict[str, dict] = {}

class ImpactStats(TypedDict):
    forms_filled: int
    schemes_discovered: int
    otp_handled: int
    voice_notes_processed: int
    users_served: set[str]

_impact: ImpactStats = {
    "forms_filled": 0,
    "schemes_discovered": 0,
    "otp_handled": 0,
    "voice_notes_processed": 0,
    "users_served": set(),
}
