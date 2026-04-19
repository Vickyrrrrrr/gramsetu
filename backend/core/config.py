"""Central settings for GramSetu backend."""
from __future__ import annotations
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    headless_browser: bool = os.getenv("HEADLESS_BROWSER", "true").lower() in {"1", "true", "yes"}
    use_stagehand: bool = os.getenv("USE_STAGEHAND", "false").lower() in {"1", "true", "yes"}
    api_base_url: str = os.getenv("API_BASE_URL", "http://localhost:8000")

def get_settings() -> Settings:
    return Settings()
