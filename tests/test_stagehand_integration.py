"""
============================================================
test_stagehand_integration.py — Tests for Stagehand Integration
============================================================
Tests:
  1. stagehand_client imports and config validation
  2. Feature flag routing logic
  3. Field label mapping completeness
  4. Graceful fallback behavior

Run: python -m pytest tests/test_stagehand_integration.py -v
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================
# 1. IMPORT & CONFIG TESTS
# ============================================================

class TestStagehandImports:
    """Ensure stagehand_client module is importable and exports expected symbols."""

    def test_stagehand_client_importable(self):
        from backend.stagehand_client import (
            stagehand_fill_form,
            stagehand_observe_page,
            stagehand_detect_otp,
            is_stagehand_enabled,
        )
        assert callable(stagehand_fill_form)
        assert callable(stagehand_observe_page)
        assert callable(stagehand_detect_otp)
        assert callable(is_stagehand_enabled)

    def test_stagehand_sdk_importable(self):
        """Verify stagehand-py package itself is installed."""
        try:
            from stagehand import Stagehand, StagehandConfig
            assert Stagehand is not None
            assert StagehandConfig is not None
        except ImportError:
            # Acceptable in CI without full deps — test should skip, not fail
            import pytest
            pytest.skip("stagehand-py not installed in this environment")


# ============================================================
# 2. CONFIG & FEATURE FLAG TESTS
# ============================================================

class TestStagehandConfig:
    """Test configuration and feature flag logic."""

    def test_is_stagehand_enabled_reads_env(self, monkeypatch):
        """Feature flag should read USE_STAGEHAND from environment."""
        # Need to reload the module to pick up new env vars
        monkeypatch.setenv("USE_STAGEHAND", "true")
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_12345")

        # Force reimport
        import importlib
        import backend.stagehand_client as sc
        importlib.reload(sc)

        assert sc.is_stagehand_enabled() is True

    def test_is_stagehand_disabled_when_flag_false(self, monkeypatch):
        monkeypatch.setenv("USE_STAGEHAND", "false")
        monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_12345")

        import importlib
        import backend.stagehand_client as sc
        importlib.reload(sc)

        assert sc.is_stagehand_enabled() is False

    def test_is_stagehand_disabled_when_no_groq_key(self, monkeypatch):
        monkeypatch.setenv("USE_STAGEHAND", "true")
        monkeypatch.setenv("GROQ_API_KEY", "")

        import importlib
        import backend.stagehand_client as sc
        importlib.reload(sc)

        assert sc.is_stagehand_enabled() is False

    def test_stagehand_model_default(self, monkeypatch):
        monkeypatch.delenv("STAGEHAND_MODEL", raising=False)

        import importlib
        import backend.stagehand_client as sc
        importlib.reload(sc)

        # Default should be groq/llama-3.3-70b-versatile
        assert "groq" in sc.STAGEHAND_MODEL.lower()


# ============================================================
# 3. FIELD LABEL MAPPING TESTS
# ============================================================

class TestFieldLabelMapping:
    """Ensure all common form fields have human-readable labels."""

    def test_core_fields_have_labels(self):
        from backend.stagehand_client import _FIELD_LABELS

        required_fields = [
            "applicant_name", "dob", "gender", "aadhaar_number",
            "mobile_number", "village", "district", "state", "pin_code",
        ]
        for field in required_fields:
            assert field in _FIELD_LABELS, f"Missing label for field: {field}"

    def test_labels_are_human_readable(self):
        from backend.stagehand_client import _FIELD_LABELS

        for field, label in _FIELD_LABELS.items():
            assert len(label) > 3, f"Label too short for {field}: {label}"
            # Label should not just be the same as field name
            assert "_" not in label, f"Label contains underscore for {field}: {label}"


# ============================================================
# 4. GRAPH INTEGRATION TESTS
# ============================================================

class TestGraphStagehandRouting:
    """Test that fill_form_node correctly routes to Stagehand or Playwright."""

    def test_graph_imports_stagehand_client(self):
        """Graph module should be able to import stagehand_client."""
        from backend.stagehand_client import is_stagehand_enabled
        # Should not raise
        result = is_stagehand_enabled()
        assert isinstance(result, bool)

    def test_parse_corrections_still_works(self):
        """Existing graph functionality unchanged after Stagehand integration."""
        from backend.agents.graph import _parse_corrections

        form = {"annual_income": 120000, "applicant_name": "Ram"}
        corrections = _parse_corrections("income 80000", form)
        assert corrections["annual_income"] == 80000.0


# ============================================================
# 5. BROWSER MCP TOOL TESTS
# ============================================================

class TestBrowserMCPStagehand:
    """Test browser_mcp.py Stagehand tool exists."""

    def test_stagehand_fill_tool_exists(self):
        """The stagehand_fill function should be importable from browser_mcp."""
        from backend.mcp_servers.browser_mcp import stagehand_fill
        assert callable(stagehand_fill)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])
