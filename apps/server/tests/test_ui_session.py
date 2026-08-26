"""UI session 引导端点（根因修复：浏览器首访无 cookie 全 401）。

Leader 指定用例：无凭证调用 → 200 + Set-Cookie；随后带 cookie 调其它端点 → 非 401。
"""


def test_ui_session_bootstrap_and_followup(client):
    """无凭证 GET /api/v1/ui/session → 200 + Set-Cookie；带 cookie 调其它端点 → 非 401。"""

    resp = client.get("/api/v1/ui/session")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    set_cookie = resp.headers.get("set-cookie", "")
    assert set_cookie.startswith("ah_session=")
    assert "; Path=/" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=Lax" in set_cookie

    # TestClient cookie jar 已自动保存 Set-Cookie；携带后调受保护端点不再 401
    follow = client.get("/api/v1/profile")
    assert follow.status_code == 200


def test_ui_session_still_guards_other_paths(client):
    """引导端点只豁免自身：其它 /api/v1 无凭证仍 401。"""

    assert client.get("/api/v1/profile").status_code == 401
