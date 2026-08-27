"""crawl_fetcher 单测（PROX-19 技设 §4.1）：SSRF 协议收敛、反爬状态码与验证码识别。

网络一律 mock，不打真实外部请求。
"""

import httpx
import pytest

from app.services import crawl_fetcher
from app.services.crawl_fetcher import FetchError, fetch_page


def test_rejects_non_http_scheme():
    """SSRF 收敛：用户可控 url 仅允许 http/https，file 等协议直接 fetch_failed。"""

    with pytest.raises(FetchError) as exc_info:
        fetch_page("file:///etc/passwd")
    assert exc_info.value.kind == "fetch_failed"
    assert "http" in exc_info.value.message


def test_403_raises_fetch_failed(monkeypatch):
    """BR-21：目标站 403 立即 fetch_failed，不绕过反爬。"""

    class _FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, _url):
            request = httpx.Request("GET", "https://example.com")
            return httpx.Response(403, request=request)

    monkeypatch.setattr(crawl_fetcher.httpx, "Client", _FakeClient)
    with pytest.raises(FetchError) as exc_info:
        fetch_page("https://www.zhipin.com/job_detail/x.html")
    assert exc_info.value.kind == "fetch_failed"


def test_captcha_page_raises_fetch_failed(monkeypatch):
    """BR-21：短页面 + 验证码特征 ≈ 被拦截到验证页，立即 fetch_failed。"""

    class _FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, _url):
            request = httpx.Request("GET", "https://example.com")
            return httpx.Response(
                200, text="<html><body>请完成安全验证</body></html>", request=request
            )

    monkeypatch.setattr(crawl_fetcher.httpx, "Client", _FakeClient)
    with pytest.raises(FetchError) as exc_info:
        fetch_page("https://www.zhipin.com/job_detail/x.html")
    assert exc_info.value.kind == "fetch_failed"


def test_timeout_raises_timeout_kind(monkeypatch):
    """超时 → FetchError(kind=timeout)，供编排器映射 CrawlStatus.timeout（AC-4）。"""

    class _FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url):
            raise httpx.ReadTimeout("slow", request=httpx.Request("GET", url))

    monkeypatch.setattr(crawl_fetcher.httpx, "Client", _FakeClient)
    with pytest.raises(FetchError) as exc_info:
        fetch_page("https://www.zhipin.com/job_detail/x.html")
    assert exc_info.value.kind == "timeout"
