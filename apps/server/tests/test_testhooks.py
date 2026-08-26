"""Tester §17 三项测试钩子自验：事件种子 / 时间控制 / IMAP test double。"""

from __future__ import annotations

from sqlmodel import select

from autohunt_domain.models import EmailAccount, EmailEvent
from app.config import get_settings
from app.db import session_for
from app.services import imap_worker


def test_events_seed_creates_pending_event(client, ui):
    resp = client.post(
        "/__test__/events/seed",
        json={
            "type": "笔试",
            "event_time": "2026-09-01T14:00:00Z",
            "company": "字节跳动",
            "email_subject": "笔试邀请",
            "email_sender": "hr@bytedance.com",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "待确认"
    assert body["type"] == "笔试"
    assert body["company"] == "字节跳动"

    # 待确认列表可读，详情带证据区元数据
    listing = client.get("/api/v1/events/pending", **ui).json()
    assert any(item["id"] == body["id"] for item in listing["items"])
    detail = client.get(f"/api/v1/events/{body['id']}", **ui).json()
    assert detail["email_subject"] == "笔试邀请"
    assert detail["email_sender"] == "hr@bytedance.com"


def test_events_seed_raw_text_enables_raw(client, ui):
    resp = client.post(
        "/__test__/events/seed",
        json={"type": "面试", "raw_text": "From: hr@example.com\nSubject: 面试通知\n\n你好"},
    )
    body = resp.json()
    raw = client.get(f"/api/v1/events/{body['id']}/raw", **ui)
    assert raw.status_code == 200
    assert "面试通知" in raw.text


def test_time_set_overrides_utcnow(client, ui):
    client.post("/__test__/time/set", json={"now": "2026-01-01T00:00:00Z"})
    ev = client.post("/__test__/events/seed", json={"type": "面试"}).json()
    detail = client.get(f"/api/v1/events/{ev['id']}", **ui).json()
    assert detail["created_at"].startswith("2026-01-01T00:00:00")

    client.post("/__test__/time/reset")
    ev2 = client.post("/__test__/events/seed", json={"type": "面试"}).json()
    detail2 = client.get(f"/api/v1/events/{ev2['id']}", **ui).json()
    assert not detail2["created_at"].startswith("2026-01-01")


def test_imap_fake_auth_fail_blocks_bind(client, ui, monkeypatch):
    monkeypatch.setenv("AUTOHUNT_IMAP_BACKEND", "fake")
    client.post("/__test__/imap/configure", json={"mode": "auth_fail"})

    resp = client.post(
        "/api/v1/email-accounts",
        json={"email": "job@example.com", "imap_host": "imap.example.com", "auth_code": "x"},
        **ui,
    )
    assert resp.status_code == 422  # 预检失败不创建


def test_imap_fake_pipeline_sync_account(client, ui, monkeypatch):
    monkeypatch.setenv("AUTOHUNT_IMAP_BACKEND", "fake")
    client.post(
        "/__test__/imap/configure",
        json={
            "mode": "ok",
            "messages": [
                {
                    "subject": "笔试通知",
                    "from": "hr@example.com",
                    "body": "你好，请于 8月28日14:00 参加在线笔试，"
                    "链接 https://meeting.tencent.com/dm/abc",
                }
            ],
        },
    )

    resp = client.post(
        "/api/v1/email-accounts",
        json={"email": "job@example.com", "imap_host": "imap.example.com", "auth_code": "x"},
        **ui,
    )
    assert resp.status_code == 201, resp.text
    account_id = resp.json()["id"]

    data_dir = get_settings().data_dir
    created = imap_worker.sync_account(data_dir, account_id)
    assert created == 1

    with session_for(data_dir) as session:
        ev = session.exec(
            select(EmailEvent).where(EmailEvent.account_id == account_id)
        ).first()
        assert ev is not None
        assert ev.type == "笔试"
        assert ev.status == "待确认"
        assert ev.meeting_link and "meeting.tencent.com" in ev.meeting_link


def test_imap_fake_conn_fail_keeps_active_and_retries(client, ui, monkeypatch):
    """瞬时连接失败不置 auth_failed（区别于授权失效），下轮重试。"""

    monkeypatch.setenv("AUTOHUNT_IMAP_BACKEND", "fake")
    resp = client.post(
        "/api/v1/email-accounts",
        json={"email": "job@example.com", "imap_host": "imap.example.com", "auth_code": "x"},
        **ui,
    )
    account_id = resp.json()["id"]

    client.post("/__test__/imap/configure", json={"mode": "conn_fail"})
    data_dir = get_settings().data_dir
    with session_for(data_dir) as session:
        before = session.exec(select(EmailAccount).where(EmailAccount.id == account_id)).first()

    # sync_account 对瞬时错误不捕获 AuthFailed，异常上抛；账户状态不受影响
    import pytest

    from app.services.imap_client import AuthFailed

    with pytest.raises((ConnectionError, AuthFailed)):
        imap_worker.sync_account(data_dir, account_id)

    with session_for(data_dir) as session:
        after = session.exec(select(EmailAccount).where(EmailAccount.id == account_id)).first()
    assert after.status == "active"  # 与 auth_failed 区分
    assert after.last_uid == before.last_uid  # 不推进 last_uid，下轮重试
