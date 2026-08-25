"""投递状态推进 + AC-6 负例（自动来源回退 409 + rejected history）。"""

from sqlmodel import select

from app.config import get_settings
from app.db import session_for
from autohunt_domain.models import StatusHistory
from tests.conftest import make_application


def test_create_application(client, agent):
    _, app_id = make_application(client, agent)
    listed = client.get("/api/v1/applications?status=待投递", **agent).json()
    assert [a["id"] for a in listed["items"]] == [app_id]


def test_create_application_unknown_job_404(client, agent):
    resp = client.post(
        "/api/v1/applications", json={"job_id": "nope", "resume_id": "r"}, **agent
    )
    assert resp.status_code == 404


def test_ui_free_transition_including_backtrack(client, ui):
    _, app_id = make_application(client, ui)
    forward = client.patch(f"/api/v1/applications/{app_id}", json={"status": "面试"}, **ui)
    assert forward.status_code == 200
    back = client.patch(f"/api/v1/applications/{app_id}", json={"status": "笔试"}, **ui)
    assert back.status_code == 200
    assert back.json()["status"] == "笔试"


def test_agent_backtrack_409_and_rejected_history(client, ui, agent):
    """AC-6：手动推进后，agent 来源回退一律 409 且落 rejected history。"""

    _, app_id = make_application(client, ui)
    client.patch(f"/api/v1/applications/{app_id}", json={"status": "面试"}, **ui)

    resp = client.patch(f"/api/v1/applications/{app_id}", json={"status": "笔试"}, **agent)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "STATE_CONFLICT"

    with session_for(get_settings().data_dir) as session:
        history = session.exec(
            select(StatusHistory).where(StatusHistory.application_id == app_id)
        ).all()
    rejected = [h for h in history if h.rejected]
    assert len(rejected) == 1
    assert rejected[0].from_status == "面试" and rejected[0].to_status == "笔试"
    assert rejected[0].source == "agent"

    # 状态未被改动
    current = client.get("/api/v1/applications", **ui).json()["items"][0]
    assert current["status"] == "面试"


def test_agent_terminal_whitelist_via_api(client, ui, agent):
    _, app_id = make_application(client, ui)
    ok = client.patch(f"/api/v1/applications/{app_id}", json={"status": "未通过"}, **agent)
    assert ok.status_code == 200

    _, app_id2 = make_application(client, ui, company="腾讯", title="运营")
    denied = client.patch(f"/api/v1/applications/{app_id2}", json={"status": "主动放弃"}, **agent)
    assert denied.status_code == 409


def test_agent_same_state_idempotent(client, ui, agent):
    _, app_id = make_application(client, ui)
    client.patch(f"/api/v1/applications/{app_id}", json={"status": "笔试"}, **ui)
    resp = client.patch(f"/api/v1/applications/{app_id}", json={"status": "笔试"}, **agent)
    assert resp.status_code == 200  # 同态重复写入幂等成功


def test_note_and_interview_round_without_status(client, ui):
    _, app_id = make_application(client, ui)
    resp = client.patch(
        f"/api/v1/applications/{app_id}", json={"note": "HR 电话沟通", "interview_round": 2}, **ui
    )
    assert resp.status_code == 200
    assert resp.json()["note"] == "HR 电话沟通"
    assert resp.json()["interview_round"] == 2
    assert resp.json()["status"] == "待投递"


# ---------- 契约 v2 修订：from/to 筛选 + D-05 读侧三端点 ----------


def test_list_from_to_filters_by_applied_at(client, ui):
    """from/to 按 applied_at 过滤；待投递（applied_at 为空）在指定区间时不返回。"""
    _, app_id = make_application(client, ui)
    client.patch(f"/api/v1/applications/{app_id}", json={"status": "已投递"}, **ui)

    with session_for(get_settings().data_dir) as session:
        from autohunt_domain.models import Application as ApplicationRow

        row = session.exec(
            select(ApplicationRow).where(ApplicationRow.id == app_id)
        ).first()
        row.applied_at = row.applied_at.replace(year=2026, month=8, day=20)
        session.add(row)
        session.commit()

    in_range = client.get("/api/v1/applications?from=2026-08-01T00:00:00Z&to=2026-08-31T23:59:59Z", **ui)
    assert [a["id"] for a in in_range.json()["items"]] == [app_id]

    out_of_range = client.get("/api/v1/applications?from=2026-09-01T00:00:00Z", **ui)
    assert out_of_range.json()["items"] == []

    # 未投递记录指定 from/to 时不返回
    _, pending_id = make_application(client, ui, company="腾讯", title="运营")
    filtered = client.get("/api/v1/applications?from=2026-08-01T00:00:00Z", **ui)
    assert pending_id not in [a["id"] for a in filtered.json()["items"]]


def test_application_history_endpoint(client, ui, agent):
    _, app_id = make_application(client, ui)
    client.patch(f"/api/v1/applications/{app_id}", json={"status": "笔试"}, **ui)
    client.patch(f"/api/v1/applications/{app_id}", json={"status": "待投递"}, **agent)  # 回退被拒

    resp = client.get(f"/api/v1/applications/{app_id}/history", **ui)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    assert items[0]["to_status"] == "笔试" and items[0]["source"] == "ui"
    assert items[1]["rejected"] is True and items[1]["source"] == "agent"

    assert client.get(f"/api/v1/applications/{app_id}/history", **agent).status_code == 200
    assert client.get("/api/v1/applications/nope/history", **ui).status_code == 404


def test_application_confirmations_endpoint(client, ui, agent):
    from tests.conftest import make_confirmation

    _, app_id = make_application(client, agent)
    confirmation_id = make_confirmation(client, agent, app_id)

    resp = client.get(f"/api/v1/applications/{app_id}/confirmations", **ui)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["id"] for i in items] == [confirmation_id]
    assert items[0]["status"] == "待确认"
    assert items[0]["submit_result"] is None


def test_application_emails_endpoint(client, ui):
    """按 matched_job_id = application.job_id 匹配；含证据区元数据字段。"""
    from autohunt_domain.models import EmailAccount, EmailEvent

    job_id, app_id = make_application(client, ui)
    _, other_app = make_application(client, ui, company="腾讯", title="运营")

    with session_for(get_settings().data_dir) as session:
        session.add(
            EmailAccount(
                id="acc-1", email="me@example.com", imap_host="imap.example.com",
                auth_code_enc="enc",
            )
        )
        session.add(
            EmailEvent(
                account_id="acc-1", message_id="m-1", type="面试",
                company="字节跳动", matched_job_id=job_id,
            )
        )
        session.add(
            EmailEvent(
                account_id="acc-1", message_id="m-2", type="拒信",
                company="腾讯", matched_job_id=None,
            )
        )
        session.commit()

    resp = client.get(f"/api/v1/applications/{app_id}/emails", **ui)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["type"] == "面试"
    assert "email_subject" in items[0]  # 证据区字段存在（M4 迁移落库前为 null）

    assert client.get(f"/api/v1/applications/{other_app}/emails", **ui).json()["items"] == []
    assert client.get("/api/v1/applications/nope/emails", **ui).status_code == 404
