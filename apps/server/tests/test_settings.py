"""提醒偏好（契约 v2 修订，D-10）：GET 默认全开 / PUT 全量替换 / 仅 UI。"""


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
