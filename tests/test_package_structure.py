import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_new_package_layout_imports():
    from backend.storage import db
    from backend.orchestrator.flow import process_message
    from backend.orchestrator.models import GraphStatus
    from backend.integrations.security import sanitize_input
    from backend.integrations.schemes import discover_schemes
    from backend.integrations.voice import text_to_speech
    from backend.integrations.browser import build_fill_plan
    from backend.core import get_settings

    assert callable(process_message)
    assert callable(sanitize_input)
    assert callable(discover_schemes)
    assert callable(text_to_speech)
    assert callable(build_fill_plan)
    assert GraphStatus is not None
    assert callable(get_settings)
    assert hasattr(db, 'init_db')
