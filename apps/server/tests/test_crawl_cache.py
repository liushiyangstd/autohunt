"""crawl_cache 单测（PROX-19 技设 §5）：TTL、键隔离、过期淘汰。"""

from app.services.crawl_cache import CrawlCache


def test_get_set_roundtrip():
    cache = CrawlCache(ttl_seconds=30.0)
    cache.set("ui:req-1", {"status": "ok"})
    assert cache.get("ui:req-1") == {"status": "ok"}


def test_expired_entry_returns_none():
    cache = CrawlCache(ttl_seconds=-1.0)  # 立即过期
    cache.set("ui:req-1", {"status": "ok"})
    assert cache.get("ui:req-1") is None


def test_caller_key_isolation():
    cache = CrawlCache(ttl_seconds=30.0)
    cache.set("ui:req-1", {"status": "ok"})
    assert cache.get("agent:req-1") is None


def test_reset_clears_all():
    cache = CrawlCache(ttl_seconds=30.0)
    cache.set("ui:req-1", {"status": "ok"})
    cache.reset()
    assert cache.get("ui:req-1") is None
