"""
graph.py — Compatibility stub. All logic now in pipeline.py.
"""
from backend.agents.pipeline import *  # noqa: F403
# Explicit re-exports for test compatibility
from backend.agents.pipeline import _parse_corrections, _browser_ws_clients, _screenshot_cache, _FORM_INTENT_KEYWORDS
