"""Polite HTTP client with retries and an optional on-disk cache.

The cache keeps local development cheap (re-parse without re-fetching). CI runs
with the cache off so each scheduled run sees fresh pages.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Optional

import requests

from . import config


class Fetcher:
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        delay: float = config.REQUEST_DELAY_SECONDS,
        timeout: int = config.REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.USER_AGENT})
        self._last_request = 0.0

    def _cache_path(self, url: str) -> Optional[Path]:
        if not self.cache_dir:
            return None
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / f"{key}.html"

    def get(self, url: str, *, use_cache: bool = True) -> str:
        """Fetch ``url`` as text, honoring the cache and rate limit."""
        cache_path = self._cache_path(url) if use_cache else None
        if cache_path and cache_path.exists():
            return cache_path.read_text(encoding="utf-8", errors="replace")

        self._throttle()
        text = self._get_with_retries(url)

        if cache_path:
            cache_path.write_text(text, encoding="utf-8", errors="replace")
        return text

    def get_bytes(self, url: str) -> bytes:
        """Fetch raw bytes (for PDFs); never cached as text."""
        self._throttle()
        last_exc: Optional[Exception] = None
        for attempt in range(config.MAX_RETRIES):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                return resp.content
            except requests.RequestException as exc:  # pragma: no cover - network
                last_exc = exc
                time.sleep(self._backoff(attempt))
        raise RuntimeError(f"Failed to fetch {url}: {last_exc}")

    def _get_with_retries(self, url: str) -> str:
        last_exc: Optional[Exception] = None
        for attempt in range(config.MAX_RETRIES):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                resp.encoding = resp.encoding or "utf-8"
                return resp.text
            except requests.RequestException as exc:  # pragma: no cover - network
                last_exc = exc
                time.sleep(self._backoff(attempt))
        raise RuntimeError(f"Failed to fetch {url}: {last_exc}")

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_request = time.monotonic()

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(2.0 ** attempt, 30.0)
