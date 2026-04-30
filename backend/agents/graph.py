"""
graph.py — Compatibility stub. All logic now in pipeline.py.
"""
from backend.agents.pipeline import (  # noqa: F401
    process_message, _parse_corrections, _browser_ws_clients,
    _screenshot_cache, _FORM_INTENT_KEYWORDS,
)

# LangGraph-removed stubs for backward compatibility
def get_compiled_graph():
    """Stub — LangGraph removed in v5. Returns None."""
    return None
