"""页面拉取（PROX-19 技设 §4.1）：httpx 抓目标页 HTML，抽可见文本。

- 反爬合规（BR-21/RISK-2）：遇 403/验证码立即 fetch_failed，不绕过反爬。
- 超时 15s（与 LLM 调用合计 ≈30s 总超时，技设 §2.1）。
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

_FETCH_TIMEOUT_SECONDS = 15.0
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# 验证码/人机校验页面特征（命中即视为反爬拦截）
_CAPTCHA_MARKERS = ("验证码", "人机验证", "安全验证", "captcha", "slider-verify")

_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t ]+")
_BLANK_LINES_RE = re.compile(r"\n{2,}")


class FetchError(Exception):
    """抓取失败；kind ∈ {fetch_failed, timeout}（技设 §3.2 status 口径）。"""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def fetch_page(url: str, timeout: float = _FETCH_TIMEOUT_SECONDS) -> str:
    """拉取目标页 HTML；403/验证码/超时/网络异常一律抛 FetchError。"""

    # SSRF 收敛：用户可控 url 仅允许 http/https，其他协议（file/gopher 等）直接拒绝
    if urlparse(url).scheme not in ("http", "https"):
        raise FetchError("fetch_failed", f"仅支持 http/https 链接：{url}")

    try:
        with httpx.Client(
            timeout=timeout, follow_redirects=True, headers={"User-Agent": _UA}
        ) as client:
            resp = client.get(url)
    except httpx.TimeoutException as exc:
        raise FetchError("timeout", f"抓取超时（>{timeout:.0f}s）：{url}") from exc
    except httpx.HTTPError as exc:
        raise FetchError("fetch_failed", f"网络错误：{exc}") from exc

    if resp.status_code in (401, 403, 418, 429):
        raise FetchError("fetch_failed", f"目标站拒绝访问（HTTP {resp.status_code}），可能触发反爬")
    if resp.status_code >= 400:
        raise FetchError("fetch_failed", f"目标页返回 HTTP {resp.status_code}")

    html = resp.text
    if any(marker in html for marker in _CAPTCHA_MARKERS) and len(html) < 20000:
        # 短页面 + 验证码特征 ≈ 被拦截到验证页（BR-21：不绕过）
        raise FetchError("fetch_failed", "目标页触发验证码/人机验证，请改为手动录入")
    return html


def html_to_text(html: str) -> str:
    """抽可见文本：去 script/style/标签，压缩空白（供结构化解析与 LLM 兜底共用）。"""

    text = _SCRIPT_RE.sub("\n", html)
    text = _TAG_RE.sub("\n", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    lines = [_WS_RE.sub(" ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return _BLANK_LINES_RE.sub("\n", "\n".join(lines))
