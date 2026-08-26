"""通知列表（FR-32）—— G3 D5：列表侧按 schedule_24h/schedule_1h 偏好过滤（与生成侧一致）。"""

from sqlmodel import select

from autohunt_domain.models import Notification
from app.config import get_settings
from app.db import session_for


def _seed_confirmed_reminders(client, ui, event_time="2026-01-02T12:00:00Z", now="2026-01-01T00:00:00Z"):
    """默认偏好下确认一个事件，生成 24h + 1h 两级提醒（均在 now 之后触发）。"""
    client.post("/__test__/time/set", json={"now": now})
    ev = client.post(
        "/__test__/events/seed",
        json={"type": "笔试", "event_time": event_time, "company": "腾讯"},
    ).json()
    client.post(f"/api/v1/events/{ev['id']}/confirm", json={}, **ui)

    with session_for(get_settings().data_dir) as session:
        kinds = {n.kind for n in session.exec(select(Notification)).all()}
    assert kinds == {"24h", "1h"}


def test_notification_prefs_filter_1h_disabled(client, ui):
    """D5：schedule_1h 关闭后，已到期的 1h 提醒不出现在列表且保持「待触发」；重开后恢复。"""
    _seed_confirmed_reminders(client, ui)

    # 关闭 1h 偏好（含 deadline 一并关闭避免噪音），拨快时钟使两级提醒均到期
    client.put(
        "/api/v1/settings/reminders",
        json={"schedule_24h": True, "schedule_1h": False, "include_deadline": False},
        **ui,
    )
    client.post("/__test__/time/set", json={"now": "2026-01-02T12:00:00Z"})

    listed = client.get("/api/v1/notifications", **ui).json()
    kinds = [item["kind"] for item in listed["items"]]
    assert kinds == ["24h"]  # 1h 被偏好过滤

    with session_for(get_settings().data_dir) as session:
        notif_1h = session.exec(
            select(Notification).where(Notification.kind == "1h")
        ).first()
        assert notif_1h.status == "待触发"  # 被过滤的不置「已触发」，可恢复

    # 重开 1h 偏好 → 到期的 1h 提醒恢复出现
    client.put(
        "/api/v1/settings/reminders",
        json={"schedule_24h": True, "schedule_1h": True, "include_deadline": False},
        **ui,
    )
    listed2 = client.get("/api/v1/notifications", **ui).json()
    kinds2 = [item["kind"] for item in listed2["items"]]
    assert kinds2 == ["1h"]  # 24h 已触发不重复出现


def test_notifications_bad_cursor_limit_422(client, ui):
    resp = client.get("/api/v1/notifications?cursor=abc", **ui)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    for bad in ("0", "-1"):
        resp = client.get(f"/api/v1/notifications?limit={bad}", **ui)
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
