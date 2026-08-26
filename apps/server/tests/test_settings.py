"""提醒偏好（契约 v2 修订，D-10）：GET 默认全开 / PUT 全量替换 / 仅 UI。"""

from autohunt_domain.models import AppSetting
from app.api import settings as settings_module
from app.config import get_settings
from app.db import session_for
from sqlmodel import select


def test_get_reminders_defaults(client, ui):
    resp = client.get("/api/v1/settings/reminders", **ui)
    assert resp.status_code == 200
    assert resp.json() == {"schedule_24h": True, "schedule_1h": True, "include_deadline": True}


def test_put_reminders_roundtrip(client, ui):
    saved = client.put(
        "/api/v1/settings/reminders",
        json={"schedule_24h": True, "schedule_1h": False, "include_deadline": False},
        **ui,
    )
    assert saved.status_code == 200
    assert saved.json()["schedule_1h"] is False

    reread = client.get("/api/v1/settings/reminders", **ui)
    assert reread.json() == {"schedule_24h": True, "schedule_1h": False, "include_deadline": False}


def test_reminders_agent_forbidden(client, agent):
    assert client.get("/api/v1/settings/reminders", **agent).status_code == 403
    put = client.put(
        "/api/v1/settings/reminders",
        json={"schedule_24h": True, "schedule_1h": True, "include_deadline": True},
        **agent,
    )
    assert put.status_code == 403


# ---------- LLM 配置（PROX-8） ----------


def test_get_llm_defaults(client, ui):
    resp = client.get("/api/v1/settings/llm", **ui)
    assert resp.status_code == 200
    assert resp.json()["api_key_last4"] is None
    assert resp.json()["provider"] == "openai"


def test_put_llm_roundtrip_and_encryption(client, ui):
    put = client.put(
        "/api/v1/settings/llm",
        json={
            "enabled": True,
            "provider": "openai",
            "model": "gpt-4o",
            "api_key": "sk-1234567890abcdef",
            "timeout_seconds": 10,
            "max_tokens": 1024,
        },
        **ui,
    )
    assert put.status_code == 200
    body = put.json()
    assert body["api_key_last4"] == "cdef"
    assert "api_key_enc" not in body
    assert "api_key" not in body

    reread = client.get("/api/v1/settings/llm", **ui)
    assert reread.status_code == 200
    assert reread.json()["api_key_last4"] == "cdef"
    assert "api_key" not in reread.json()

    with session_for(get_settings().data_dir) as session:
        row = session.exec(select(AppSetting).where(AppSetting.key == "llm")).first()
        assert row is not None
        from app.security import decrypt

        assert decrypt(get_settings().data_dir, row.value["api_key_enc"]) == "sk-1234567890abcdef"
        assert row.value["api_key_last4"] == "cdef"


def test_put_llm_preserves_key_when_not_provided(client, ui):
    client.put(
        "/api/v1/settings/llm",
        json={"provider": "openai", "api_key": "sk-keepme-secret"},
        **ui,
    )
    client.put(
        "/api/v1/settings/llm",
        json={"model": "gpt-4o-mini", "timeout_seconds": 30},
        **ui,
    )

    reread = client.get("/api/v1/settings/llm", **ui)
    assert reread.json()["api_key_last4"] == "cret"
    assert reread.json()["model"] == "gpt-4o-mini"
    assert reread.json()["timeout_seconds"] == 30


def test_post_llm_test(client, ui, monkeypatch):
    def fake_probe(base_url, api_key, model, timeout_seconds, max_tokens):
        return True, None

    monkeypatch.setattr(settings_module, "_probe_llm", fake_probe)

    client.put(
        "/api/v1/settings/llm",
        json={"provider": "openai", "api_key": "sk-test"},
        **ui,
    )
    resp = client.post("/api/v1/settings/llm/test", **ui)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_post_llm_test_no_key(client, ui):
    resp = client.post("/api/v1/settings/llm/test", **ui)
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert "API Key" in resp.json()["error"]


def test_llm_agent_forbidden(client, agent):
    assert client.get("/api/v1/settings/llm", **agent).status_code == 403
    assert (
        client.put("/api/v1/settings/llm", json={"provider": "openai"}, **agent).status_code == 403
    )
    assert client.post("/api/v1/settings/llm/test", **agent).status_code == 403
