"""30s 幂等缓存（PROX-19 技设 §5）：进程内内存 + TTL。

- 键 `{caller}:{request_id}`；30 秒内同一 request_id 返回同一结果（FR-4/BR-4）。
- 不持久化：重启丢失仅导致重复解析，不影响正确性（RISK-6）。
- 与保存时 company+title 去重是两回事（§5.4）。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock


@dataclass
class _Entry:
    result: dict
    expires_at: float


class CrawlCache:
    def __init__(self, ttl_seconds: float = 30.0):
        self._ttl = ttl_seconds
        self._store: dict[str, _Entry] = {}
        self._lock = Lock()

    def get(self, key: str) -> dict | None:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if now > entry.expires_at:
                self._store.pop(key, None)
                return None
            return entry.result

    def set(self, key: str, result: dict) -> None:
        now = time.monotonic()
        with self._lock:
            self._store[key] = _Entry(result=result, expires_at=now + self._ttl)
            self._evict_expired(now)

    def reset(self) -> None:
        """测试钩子：清空缓存，避免跨用例泄漏。"""

        with self._lock:
            self._store.clear()

    def _evict_expired(self, now: float) -> None:
        expired = [k for k, e in self._store.items() if now > e.expires_at]
        for k in expired:
            self._store.pop(k, None)


crawl_cache = CrawlCache(ttl_seconds=30.0)
