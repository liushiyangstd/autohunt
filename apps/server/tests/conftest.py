"""pytest 公共夹具：独立 tmp 数据目录 + 固定 UI token + 测试钩子开启。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

UI_TOKEN = "ah_ui_test_token_for_pytest"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOHUNT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AUTOHUNT_UI_TOKEN", UI_TOKEN)
    monkeypatch.setenv("AUTOHUNT_TEST_HOOKS", "1")
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def ui(client):
    """携带 UI session cookie 的请求头。"""

    return {"cookies": {"ah_session": UI_TOKEN}}


@pytest.fixture()
def agent_key(client, ui):
    """经 POST /keys 真实签发的 Agent key（含完整明文，仅此一次）。"""

    resp = client.post("/api/v1/keys", json={"name": "pytest-agent"}, **ui)
    assert resp.status_code == 201, resp.text
    return resp.json()["key"]


@pytest.fixture()
def agent(agent_key):
    return {"headers": {"Authorization": f"Bearer {agent_key}"}}


def make_application(client, auth, company="字节跳动", title="后端开发"):
    """建岗 → 建投递，返回 (job_id, application_id)。"""

    job = client.post("/api/v1/jobs", json={"company": company, "title": title}, **auth)
    assert job.status_code == 201, job.text
    job_id = job.json()["id"]
    app_resp = client.post(
        "/api/v1/applications", json={"job_id": job_id, "resume_id": "resume-placeholder"}, **auth
    )
    assert app_resp.status_code == 201, app_resp.text
    return job_id, app_resp.json()["id"]


def make_confirmation(client, auth, application_id, request_id="req-1", fields=None):
    resp = client.post(
        "/api/v1/confirmations",
        json={
            "application_id": application_id,
            "request_id": request_id,
            "fields": fields or {"姓名": "张三", "电话": "13800000000"},
        },
        **auth,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["confirmation_id"]
