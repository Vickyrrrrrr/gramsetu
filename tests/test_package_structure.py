import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_new_package_layout_imports():
    from backend.storage import db
    from backend.agents.pipeline import process_message
    from backend.agents.schema import GraphStatus
    from backend.security import sanitize_input
    from backend.schemes import discover_schemes
    from backend.llm_client import chat
    from backend.core import get_settings
    from backend.mcp_servers.audit_mcp import validate_field

    assert callable(process_message)
    assert callable(sanitize_input)
    assert callable(discover_schemes)
    assert callable(chat)
    assert GraphStatus is not None
    assert callable(get_settings)
    assert callable(validate_field)
    assert hasattr(db, 'init_db')
