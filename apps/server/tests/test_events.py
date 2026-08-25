"""events / schedule 只读端点冒烟（§3.5）——数据写入侧（IMAP pipeline）属 M4 后续。"""


def test_pending_events_empty(client, agent):
    resp = client.get("/api/v1/events/pending", **agent)
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "next_cursor": None}


def test_schedule_empty(client, ui):
    resp = client.get("/api/v1/schedule?from=2026-08-01T00:00:00Z&to=2026-09-01T00:00:00Z", **ui)
    assert resp.status_code == 200
    assert resp.json() == {"items": []}
