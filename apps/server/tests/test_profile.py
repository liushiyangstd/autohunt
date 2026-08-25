"""FR-20 档案读取（§3.2，含 §12 空态）。"""


def test_profile_empty_state(client, ui, agent):
    """无简历时返回 200 + {"empty": true}（UI / Agent 双鉴权均可读）。"""

    for auth in (ui, agent):
        resp = client.get("/api/v1/profile", **auth)
        assert resp.status_code == 200
        assert resp.json() == {"empty": True}


def test_profile_requires_auth(client):
    assert client.get("/api/v1/profile").status_code == 401
