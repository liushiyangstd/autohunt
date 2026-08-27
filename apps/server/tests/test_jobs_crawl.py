"""POST /jobs/crawl API 测试（PROX-19）：覆盖 AC-3/4/7/10/11/12、401/429、幂等。

LLM 与网络一律 mock，不打真实外部请求。
"""

from __future__ import annotations

import pytest
from sqlmodel import select

from autohunt_domain.models import CrawlAttempt
from app.config import get_settings
from app.db import session_for
from app.services import crawl_fetcher, crawl_llm
from app.services.llm_client import LLMConfig

from tests.test_crawl_parser import BOSS_HTML


def _attempts() -> list[CrawlAttempt]:
    with session_for(get_settings().data_dir) as session:
        return list(session.exec(select(CrawlAttempt)).all())


def _body(**overrides) -> dict:
    body = {
        "url": "https://www.zhipin.com/job_detail/abc.html",
        "source": "boss",
        "request_id": "req-test-1",
    }
    body.update(overrides)
    return body


# ---------- AC-10：无凭证 / 错误凭证 → 401 ----------


def test_crawl_unauthorized_without_credentials(client):
    resp = client.post("/api/v1/jobs/crawl", json=_body())
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_crawl_unauthorized_with_bad_bearer(client):
    resp = client.post(
        "/api/v1/jobs/crawl",
        json=_body(),
        headers={"Authorization": "Bearer ah_live_wrong"},
    )
    assert resp.status_code == 401


# ---------- AC-3：不支持站点 → unsupported_site ----------


def test_crawl_unsupported_site(client, ui):
    resp = client.post(
        "/api/v1/jobs/crawl", json=_body(source="liepin", url="https://www.liepin.com/job/1"), **ui
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "unsupported_site"
    assert data["fields"] is None
    # 落 crawl_attempt 审计（技设 §3.2）
    attempts = _attempts()
    assert len(attempts) == 1
    assert attempts[0].status == "unsupported_site"
    assert attempts[0].strategy == "none"


# ---------- 结构化路径：extracted 已传 → 不拉取页面 ----------


def test_crawl_extracted_skips_fetch(client, ui, monkeypatch):
    def no_fetch(_url, timeout=15.0):
        raise AssertionError("extracted 已传时不应拉取页面（技设 §4.3）")

    monkeypatch.setattr(crawl_fetcher, "fetch_page", no_fetch)
    resp = client.post(
        "/api/v1/jobs/crawl",
        json=_body(
            extracted={
                "company": "字节跳动",
                "title": "后端开发",
                "location": "北京",
                "deadline": "2026-09-01",
                "description": "负责后端服务开发",
            }
        ),
        **ui,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["fields"]["company"] == "字节跳动"
    assert data["fields"]["channel"] == "boss"
    assert data["fields"]["jd_url"] == _body()["url"]
    assert data["fields"]["deadline"].startswith("2026-09-01T23:59:59")
    assert data["confidence"] == "high"
    assert data["missing_fields"] == []
    # 不落 job 表（AC-5 后端侧：crawl 绝不写 job）
    jobs = client.get("/api/v1/jobs", **ui).json()["items"]
    assert jobs == []


# ---------- 结构化路径：未传 extracted → fetch + parser ----------


def test_crawl_structured_fetch_and_parse(client, ui, monkeypatch):
    monkeypatch.setattr(crawl_fetcher, "fetch_page", lambda _url, timeout=15.0: BOSS_HTML)
    resp = client.post("/api/v1/jobs/crawl", json=_body(), **ui)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("ok", "partial")
    assert data["fields"]["company"] == "字节跳动"
    assert data["fields"]["title"] == "高级后端开发工程师"


# ---------- AC-4：403 / 超时 → fetch_failed / timeout ----------


def test_crawl_fetch_failed_on_403(client, ui, monkeypatch):
    def raise_403(_url, timeout=15.0):
        raise crawl_fetcher.FetchError("fetch_failed", "目标站拒绝访问（HTTP 403），可能触发反爬")

    monkeypatch.setattr(crawl_fetcher, "fetch_page", raise_403)
    resp = client.post("/api/v1/jobs/crawl", json=_body(), **ui)
    data = resp.json()
    assert data["status"] == "fetch_failed"
    assert "403" in data["error_message"]


def test_crawl_timeout(client, ui, monkeypatch):
    def raise_timeout(_url, timeout=15.0):
        raise crawl_fetcher.FetchError("timeout", "抓取超时（>15s）")

    monkeypatch.setattr(crawl_fetcher, "fetch_page", raise_timeout)
    resp = client.post("/api/v1/jobs/crawl", json=_body(), **ui)
    assert resp.json()["status"] == "timeout"


# ---------- LLM 路径：未配置 → parse_failed + LLM_NOT_CONFIGURED ----------


def test_crawl_llm_not_configured(client, ui):
    resp = client.post(
        "/api/v1/jobs/crawl",
        json=_body(
            source="official",
            url="https://careers.example.com/job/1",
            extracted={"content": "某公司招聘后端工程师"},
        ),
        **ui,
    )
    data = resp.json()
    assert data["status"] == "parse_failed"
    assert data["error_code"] == "LLM_NOT_CONFIGURED"


# ---------- AC-12：LLM 输入 >8000 tokens → 截断标记 ----------


def test_crawl_llm_truncation(client, ui, monkeypatch):
    monkeypatch.setattr(
        crawl_llm,
        "load_config",
        lambda _session: LLMConfig(
            enabled=True, provider="openai", base_url=None, model="gpt-4o-mini", api_key="sk-test"
        ),
    )
    captured: dict = {}

    def fake_call(text, config):
        captured["len"] = len(text)
        return {"company": "示例科技", "title": "后端工程师"}, 8000

    monkeypatch.setattr(crawl_llm, "call_llm_jd", fake_call)

    long_content = "岗" * (crawl_llm.MAX_INPUT_TOKENS * 2)
    resp = client.post(
        "/api/v1/jobs/crawl",
        json=_body(
            source="official",
            url="https://careers.example.com/job/1",
            extracted={"content": long_content},
        ),
        **ui,
    )
    data = resp.json()
    assert data["status"] in ("ok", "partial")
    assert data["content_truncated"] is True
    assert data["tokens_used"] == 8000
    assert captured["len"] < len(long_content)


# ---------- AC-7：30s 内同一 request_id 幂等 ----------


def test_crawl_idempotent_same_request_id(client, ui, monkeypatch):
    monkeypatch.setattr(crawl_fetcher, "fetch_page", lambda _url, timeout=15.0: BOSS_HTML)
    first = client.post("/api/v1/jobs/crawl", json=_body(), **ui).json()
    for _ in range(2):
        again = client.post("/api/v1/jobs/crawl", json=_body(), **ui).json()
        assert again == first
    # 仅产生一条 crawl_attempt（BR-4）
    assert len(_attempts()) == 1


def test_crawl_idempotent_cache_scoped_by_caller(client, ui, agent, monkeypatch):
    monkeypatch.setattr(crawl_fetcher, "fetch_page", lambda _url, timeout=15.0: BOSS_HTML)
    client.post("/api/v1/jobs/crawl", json=_body(), **ui)
    client.post("/api/v1/jobs/crawl", json=_body(), **agent)
    # 缓存键 {caller}:{request_id}（技设 §5.3）：不同 caller 不互相命中
    assert len(_attempts()) == 2


# ---------- AC-11：10/min 限流 → 第 11 次 429 ----------


def test_crawl_rate_limited(client, ui):
    for i in range(10):
        resp = client.post(
            "/api/v1/jobs/crawl",
            json=_body(source="liepin", request_id=f"req-{i}"),
            **ui,
        )
        assert resp.status_code == 200
    resp = client.post(
        "/api/v1/jobs/crawl", json=_body(source="liepin", request_id="req-11"), **ui
    )
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMITED"


# ---------- parse_failed：结构化零产出 ----------


def test_crawl_parse_failed_when_no_company_and_title(client, ui, monkeypatch):
    monkeypatch.setattr(
        crawl_fetcher, "fetch_page", lambda _url, timeout=15.0: "<html><body></body></html>"
    )
    resp = client.post("/api/v1/jobs/crawl", json=_body(), **ui)
    assert resp.json()["status"] == "parse_failed"


# ---------- 技设 §3.2 / AC-2：保存/更新时回填 crawl_attempt.job_id ----------


def _crawl_extracted(client, ui, request_id: str, company="字节跳动", title="后端开发"):
    resp = client.post(
        "/api/v1/jobs/crawl",
        json=_body(
            request_id=request_id,
            extracted={"company": company, "title": title, "location": "北京"},
        ),
        **ui,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] in ("ok", "partial")  # 只传 company/title/location → partial
    return resp.json()


def test_save_links_crawl_attempt(client, ui):
    """首次保存：POST /jobs 带 crawl_request_id → 预览期 attempt 回填 job_id（技设 §3.2）。"""

    result = _crawl_extracted(client, ui, "req-save-1")
    resp = client.post(
        "/api/v1/jobs",
        json={
            "company": "字节跳动",
            "title": "后端开发",
            "jd_url": result["fields"]["jd_url"],
            "crawl_request_id": "req-save-1",
        },
        **ui,
    )
    assert resp.status_code == 201, resp.text
    job_id = resp.json()["id"]
    attempts = _attempts()
    assert len(attempts) == 1
    assert attempts[0].job_id == job_id


def test_duplicate_update_links_crawl_attempt(client, ui):
    """AC-2：重复保存 → 200 duplicate_of → PATCH 更新 → 原 job.id 不变、字段覆盖、attempt 关联原岗位。"""

    _crawl_extracted(client, ui, "req-dup-1")
    first = client.post(
        "/api/v1/jobs",
        json={"company": "字节跳动", "title": "后端开发", "crawl_request_id": "req-dup-1"},
        **ui,
    )
    assert first.status_code == 201
    job_id = first.json()["id"]

    # 再次抓取同公司+岗位 → 新 attempt（job_id 暂空）
    _crawl_extracted(client, ui, "req-dup-2")
    dup = client.post(
        "/api/v1/jobs",
        json={"company": "字节跳动", "title": "后端开发", "crawl_request_id": "req-dup-2"},
        **ui,
    )
    assert dup.status_code == 200
    assert dup.json()["duplicate_of"] == job_id
    # duplicate 分支未保存，req-dup-2 的 attempt 不应提前关联
    attempts = {a.request_id: a for a in _attempts()}
    assert attempts["req-dup-2"].job_id is None

    # 用户选择更新：PATCH 覆盖 location 并回传 crawl_request_id
    patch = client.patch(
        f"/api/v1/jobs/{job_id}",
        json={"location": "上海", "crawl_request_id": "req-dup-2"},
        **ui,
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["id"] == job_id  # 原 job.id 不变
    assert patch.json()["location"] == "上海"  # 字段覆盖
    attempts = {a.request_id: a for a in _attempts()}
    assert attempts["req-dup-1"].job_id == job_id
    assert attempts["req-dup-2"].job_id == job_id  # 新增关联记录


def test_patch_crawl_request_id_not_written_to_job(client, ui):
    """crawl_request_id 不是 job 列：PATCH 不得落入 setattr 循环。"""

    job = client.post("/api/v1/jobs", json={"company": "A", "title": "B"}, **ui).json()
    resp = client.patch(
        f"/api/v1/jobs/{job['id']}", json={"crawl_request_id": "req-nonexistent"}, **ui
    )
    assert resp.status_code == 200, resp.text


# ---------- CORS：预检不经鉴权（技设 §8.1） ----------

def test_cors_preflight_bypasses_auth(client):
    resp = client.options(
        "/api/v1/jobs/crawl",
        headers={
            "Origin": "chrome-extension://abcdef",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "*"
