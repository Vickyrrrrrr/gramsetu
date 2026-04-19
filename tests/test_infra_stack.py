import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_cache_and_metrics_modules_import():
    from backend.core.cache import get_cache
    from backend.core.metrics import instrument_fastapi
    from backend.core import get_settings

    assert callable(get_cache)
    assert callable(instrument_fastapi)
    settings = get_settings()
    assert hasattr(settings, 'redis_url')
    assert hasattr(settings, 'metrics_enabled')
