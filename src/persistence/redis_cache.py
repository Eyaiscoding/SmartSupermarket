"""
Redis Current-State Cache
===========================
Caches only the *latest* state (coverage status, battery SOC, active
actions) for low-latency reads by the API's "latest state" endpoint
and the WebSocket stream.  TimescaleDB remains the durable record;
Redis is a disposable cache.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)

# Redis is optional -- if unavailable, the cache is a no-op.
try:
    import redis as redis_lib
except ImportError:
    redis_lib = None  # type: ignore[assignment]


class RedisCache:
    """Thin wrapper around Redis for caching the latest pipeline state."""

    LATEST_KEY = "b2g:latest_state"

    def __init__(self, url: str | None = None) -> None:
        self._client: Optional[object] = None
        if redis_lib is None:
            logger.warning("redis package not installed; cache disabled.")
            return
        try:
            self._client = redis_lib.Redis.from_url(
                url or settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            self._client.ping()
            logger.info("Redis cache connected.")
        except Exception as exc:
            logger.warning("Redis unavailable (cache disabled): %s", exc)
            self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def set_latest(self, record_dict: dict) -> None:
        """Cache the complete record, including optional tariffs and nested P2P trades."""
        if not self.available:
            return
        try:
            self._client.set(self.LATEST_KEY, json.dumps(record_dict, ensure_ascii=False, allow_nan=False))
        except Exception as exc:
            logger.warning("Redis SET failed: %s", exc)

    def get_latest(self) -> dict | None:
        """Retrieve the cached latest state, or None."""
        if not self.available:
            return None
        try:
            raw = self._client.get(self.LATEST_KEY)
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.warning("Redis GET failed: %s", exc)
            return None

    def clear(self) -> None:
        """Delete the cached state."""
        if not self.available:
            return
        try:
            self._client.delete(self.LATEST_KEY)
        except Exception:
            pass
