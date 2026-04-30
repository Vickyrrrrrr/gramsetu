"""Cache abstraction with free-friendly fallback to in-memory store."""
from __future__ import annotations
import json
from typing import Any

from backend.core.config import get_settings

try:
    import redis.asyncio as redis
except Exception:
    redis = None


class InMemoryCache:
    def __init__(self):
        self._data: dict[str, str] = {}

    async def get_json(self, key: str):
        value = self._data.get(key)
        return json.loads(value) if value else None

    async def set_json(self, key: str, value: Any, ttl: int | None = None):
        self._data[key] = json.dumps(value)
        return True

    async def ping(self) -> bool:
        return True

    async def delete(self, key: str):
        self._data.pop(key, None)
        return True

    async def close(self):
        return None


class RedisCache:
    def __init__(self, url: str):
        self.client = redis.from_url(url, decode_responses=True)

    async def get_json(self, key: str):
        value = await self.client.get(key)
        return json.loads(value) if value else None

    async def set_json(self, key: str, value: Any, ttl: int | None = None):
        payload = json.dumps(value)
        if ttl:
            await self.client.setex(key, ttl, payload)
        else:
            await self.client.set(key, payload)
        return True

    async def ping(self) -> bool:
        try:
            return bool(await self.client.ping())
        except Exception:
            return False

    async def delete(self, key: str):
        await self.client.delete(key)
        return True

    async def close(self):
        await self.client.aclose()


_cache = None


def get_cache():
    global _cache
    if _cache is not None:
        return _cache
    settings = get_settings()
    if redis is None:
        _cache = InMemoryCache()
        return _cache
    try:
        _cache = RedisCache(settings.redis_url)
    except Exception:
        _cache = InMemoryCache()
    return _cache


async def close_cache():
    global _cache
    if _cache is not None:
        await _cache.close()
        _cache = None
