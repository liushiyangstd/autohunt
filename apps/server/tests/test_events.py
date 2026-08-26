"""events / schedule（§3.5 + §3.7）——M4 确认流端到端（BR-2）：确认 → 日程 → 提醒。"""

from sqlmodel import select

from autohunt_domain.models import Notification
from app.config import get_settings
from app.db import session_for


def test_pending_events_empty(client, agent):
    resp = client.get("/api/v1/events/pending", **agent)
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "next_cursor": None}


def test_schedule_empty(client, ui):
    resp = client.get("/api/v1/schedule?from=2026-08-01T00:00:00Z&to=2026-09-01T00:00:00Z", **ui)
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_confirm_event_creates_schedule_and_advances_application(client, ui):
    """BR-2：事件确认 → 生成日程 + 24h/1h 提醒 + 关联投递按 email 来源推进状态。"""

    job = client.post("/api/v1/jobs", json={"company": "字节跳动", "title": "后端开发"}, **ui).json()
    app = client.post(
        "/api/v1/applications", json={"job_id": job["id"], "resume_id": "resume-placeholder"}, **ui
    ).json()

    ev = client.post(
        "/__test__/events/seed",
        json={
            "type": "面试",
            "event_time": "2026-09-01T10:00:00Z",
            "location": "线上",
            "company": "字节跳动",
            "matched_job_id": job["id"],
        },
    ).json()

    resp = client.post(f"/api/v1/events/{ev['id']}/confirm", json={}, **ui)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["event"]["status"] == "已确认"
    assert body["schedule_event"]["type"] == "面试"
    assert body["schedule_event"]["start_time"] == "2026-09-01T10:00:00"
    assert body["schedule_event"]["application_id"] == app["id"]

    # 日程视图可见
    schedule = client.get("/api/v1/schedule?from=2026-09-01T00:00:00Z&to=2026-09-02T00:00:00Z", **ui).json()
    assert any(item["id"] == body["schedule_event"]["id"] for item in schedule["items"])

    # 关联投递已推进到「面试」（email 来源，§5 白名单内）
    listing = client.get("/api/v1/applications", **ui).json()
    detail = next(item for item in listing["items"] if item["id"] == app["id"])
    assert detail["status"] == "面试"

    # 提醒已按 event_time 生成：24h/1h 两级（fire_at 未来 → 已创建）
    with session_for(get_settings().data_dir) as session:
        kinds = {n.kind for n in session.exec(select(Notification)).all()}
    assert kinds == {"24h", "1h"}


def test_notification_lazy_fire_once(client, ui):
    """FR-32：日程提醒 fire_at 到达后出现在通知列表并置「已触发」，不重复出现。"""

    # T1：确认事件，生成 fire_at 在未来（相对 T1）的提醒
    client.post("/__test__/time/set", json={"now": "2026-01-01T00:00:00Z"})
    ev = client.post(
        "/__test__/events/seed",
        json={"type": "笔试", "event_time": "2026-01-02T12:00:00Z", "company": "腾讯"},
    ).json()
    client.post(f"/api/v1/events/{ev['id']}/confirm", json={}, **ui)

    # T2：拨快时钟到 24h 提醒已到、1h 提醒未到
    client.post("/__test__/time/set", json={"now": "2026-01-02T00:00:00Z"})
    listing = client.get("/api/v1/notifications", **ui).json()
    kinds = [item["kind"] for item in listing["items"]]
    assert kinds == ["24h"]  # 仅 24h 到达

    # 再读一次：已触发的不重复出现
    listing2 = client.get("/api/v1/notifications", **ui).json()
    assert listing2["items"] == []

