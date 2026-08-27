"""抓取频率限制（PROX-19 技设 §6）：单调用方 10 req/min 进程内滑动窗口。

单用户本地工具，无需细分到用户 ID；超限由编排器返回 429 RATE_LIMITED。
"""

from __future__ import annotations

import time
from threading import Lock


class CrawlRateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: dict[str, list[float]] = {}
        self._lock = Lock()

    def check(self, caller_id: str) -> bool:
        """返回 True 放行并计数；False 表示超限。"""

        now = time.monotonic()
        with self._lock:
            timestamps = self._buckets.get(caller_id, [])
            # 清理窗口外时间戳
            timestamps = [t for t in timestamps if now - t <= self.window]
            if len(timestamps) >= self.max_requests:
                self._buckets[caller_id] = timestamps
                return False
            timestamps.append(now)
            self._buckets[caller_id] = timestamps
            return True

    def reset(self) -> None:
        """测试钩子：清空窗口，避免跨用例泄漏。"""

        with self._lock:
            self._buckets.clear()


crawl_rate_limiter = CrawlRateLimiter(max_requests=10, window_seconds=60.0)
