"""crawl_rate_limit 单测（PROX-19 技设 §6）：10/min 滑动窗口。"""

from app.services.crawl_rate_limit import CrawlRateLimiter


def test_allows_up_to_max_then_blocks():
    limiter = CrawlRateLimiter(max_requests=10, window_seconds=60.0)
    for _ in range(10):
        assert limiter.check("ui") is True
    assert limiter.check("ui") is False


def test_callers_are_independent():
    limiter = CrawlRateLimiter(max_requests=1, window_seconds=60.0)
    assert limiter.check("ui") is True
    assert limiter.check("ui") is False
    assert limiter.check("agent") is True


def test_window_slides():
    limiter = CrawlRateLimiter(max_requests=1, window_seconds=-1.0)  # 窗口立即过期
    assert limiter.check("ui") is True
    assert limiter.check("ui") is True


def test_reset_clears_buckets():
    limiter = CrawlRateLimiter(max_requests=1, window_seconds=60.0)
    assert limiter.check("ui") is True
    limiter.reset()
    assert limiter.check("ui") is True
