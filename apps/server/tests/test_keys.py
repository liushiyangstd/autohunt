"""FR-25 密钥管理 + §3.1 鉴权（含 AC-3 负例：无凭证 / 已吊销 / Agent 自签发）。"""


def test_no_credential_401(client):
    resp = client.get("/api/v1/keys")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_create_list_revoke_flow(client, ui):
    created = client.post("/api/v1/keys", json={"name": "cli"}, **ui)
    assert created.status_code == 201
    body = created.json()
    assert body["key"].startswith("ah_live_")
    assert body["prefix"] == body["key"][:12]

    listed = client.get("/api/v1/keys", **ui)
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    assert "key" not in items[0]  # 列表永不包含完整 key
    assert items[0]["prefix"] == body["prefix"]

    revoked = client.delete(f"/api/v1/keys/{body['id']}", **ui)
    assert revoked.status_code == 204

    # 已吊销 key 立即失效
    again = client.get(
        "/api/v1/profile", headers={"Authorization": f"Bearer {body['key']}"}
    )
    assert again.status_code == 401


def test_revoke_unknown_404(client, ui):
    assert client.delete("/api/v1/keys/nope", **ui).status_code == 404


def test_agent_cannot_manage_keys(client, ui, agent):
    """AC-3 负例：Agent 不可自签发/自吊销/列密钥（§3.1）。"""

    assert client.post("/api/v1/keys", json={"name": "self"}, **agent).status_code == 403
    assert client.get("/api/v1/keys", **agent).status_code == 403
    assert client.delete("/api/v1/keys/whatever", **agent).status_code == 403
    resp = client.post("/api/v1/keys", json={"name": "self"}, **agent)
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_bogus_bearer_401(client):
    resp = client.get("/api/v1/profile", headers={"Authorization": "Bearer ah_live_bogus"})
    assert resp.status_code == 401
