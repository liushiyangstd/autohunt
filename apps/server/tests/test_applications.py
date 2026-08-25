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
