"""Redis-backed session storage with free-friendly in-memory fallback."""
from __future__ import annotations
from typing import Any

from backend.core.cache import get_cache

SESSION_PREFIX = "session:chat:"
COMPLETED_PREFIX = "session:completed:"
DEFAULT_TTL = 60 * 60 * 6
COMPLETED_TTL = 60 * 60 * 24 * 7

async def get_chat_session(session_key: str) -> dict[str, Any] | None:
    cache = get_cache()
    return await cache.get_json(f"{SESSION_PREFIX}{session_key}")

async def save_chat_session(session_key: str, payload: dict[str, Any], ttl: int = DEFAULT_TTL) -> bool:
    cache = get_cache()
    return await cache.set_json(f"{SESSION_PREFIX}{session_key}", payload, ttl=ttl)

async def delete_chat_session(session_key: str) -> bool:
    cache = get_cache()
    return await cache.delete(f"{SESSION_PREFIX}{session_key}")

async def save_completed_session(session_id: str, payload: dict[str, Any], ttl: int = COMPLETED_TTL) -> bool:
    cache = get_cache()
    return await cache.set_json(f"{COMPLETED_PREFIX}{session_id}", payload, ttl=ttl)

async def get_completed_session(session_id: str) -> dict[str, Any] | None:
    cache = get_cache()
    return await cache.get_json(f"{COMPLETED_PREFIX}{session_id}")
