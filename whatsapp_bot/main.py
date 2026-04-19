"""Thin runtime entrypoint for GramSetu.

Keeps the CLI and Docker command stable while the real FastAPI app lives in
backend.api.app.
"""
from __future__ import annotations

import os
import uvicorn

from backend.api.app import app


def run() -> None:
    uvicorn.run(
        "backend.api.app:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    run()
