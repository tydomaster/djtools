"""
Download queue and cache manager.

Limits concurrent yt-dlp workers via a semaphore so the server isn't
overwhelmed when many users request tracks simultaneously.
Caches recent downloads by URL so the same track isn't re-fetched within
the TTL window.
"""

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from collections import defaultdict

from downloader import download_track
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    track_info: dict
    expires_at: float


@dataclass
class RateLimitEntry:
    timestamps: list[float] = field(default_factory=list)


class DownloadQueue:
    def __init__(self) -> None:
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_downloads)
        self._waiters: int = 0
        self._lock = asyncio.Lock()

        # url → CacheEntry
        self._cache: dict[str, CacheEntry] = {}

        # user_id → RateLimitEntry
        self._rate_limits: dict[int, RateLimitEntry] = defaultdict(RateLimitEntry)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def queue_position(self) -> int:
        """Current number of requests waiting for a free worker slot."""
        return self._waiters

    def check_rate_limit(self, user_id: int) -> tuple[bool, int]:
        """
        Returns (allowed, seconds_until_reset).
        Prunes expired timestamps on every call.
        """
        now = time.monotonic()
        entry = self._rate_limits[user_id]
        entry.timestamps = [t for t in entry.timestamps if now - t < settings.rate_limit_window]

        if len(entry.timestamps) >= settings.rate_limit_max:
            oldest = entry.timestamps[0]
            reset_in = int(settings.rate_limit_window - (now - oldest)) + 1
            return False, reset_in

        return True, 0

    async def get(self, url: str, user_id: int) -> dict:
        """
        Fetch track info, using the cache when available.
        Raises RateLimitError or passes through downloader exceptions.
        """
        allowed, reset_in = self.check_rate_limit(user_id)
        if not allowed:
            raise RateLimitError(reset_in)

        cache_key = _url_key(url)
        cached = self._get_cached(cache_key)
        if cached:
            logger.info("Cache hit for %s (user %d)", url, user_id)
            return cached

        async with self._lock:
            self._waiters += 1
        try:
            async with self._semaphore:
                async with self._lock:
                    self._waiters -= 1

                # Double-check cache — another worker might have just finished
                cached = self._get_cached(cache_key)
                if cached:
                    return cached

                logger.info("Downloading %s (user %d)", url, user_id)
                track_info = await download_track(url)

                self._rate_limits[user_id].timestamps.append(time.monotonic())
                self._cache[cache_key] = CacheEntry(
                    track_info=track_info,
                    expires_at=time.time() + settings.cache_ttl_seconds,
                )
                return track_info
        except Exception:
            async with self._lock:
                self._waiters -= 1
            raise

    # ------------------------------------------------------------------ #
    # Internals                                                            #
    # ------------------------------------------------------------------ #

    def _get_cached(self, key: str) -> dict | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.time() > entry.expires_at:
            del self._cache[key]
            return None
        # Verify the file is still on disk (Railway ephemeral fs)
        if not os.path.exists(entry.track_info.get("path", "")):
            del self._cache[key]
            return None
        return entry.track_info


class RateLimitError(Exception):
    def __init__(self, reset_in_seconds: int) -> None:
        self.reset_in = reset_in_seconds
        super().__init__(f"Rate limit exceeded, reset in {reset_in_seconds}s")


def _url_key(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()


# Module-level singleton — created once when the bot starts
queue = DownloadQueue()
