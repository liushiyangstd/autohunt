"""FR-21 岗位读写 + BR-3 重复提示不拦截。"""


def test_create_and_get_job(client, agent):
    created = client.post(
        "/api/v1/jobs",
        json={"company": "字节跳动", "title": "后端开发", "channel": "BOSS直聘"},
        **agent,
    )
    assert created.status_code == 201
    job = created.json()
    assert job["company"] == "字节跳动"

    got = client.get(f"/api/v1/jobs/{job['id']}", **agent)
    assert got.status_code == 200
    assert got.json()["id"] == job["id"]


def test_duplicate_job_200_not_blocked(client, ui):
    """BR-3：同公司同岗位重复创建 → 200 + duplicate_of，提示不拦截。"""

    first = client.post("/api/v1/jobs", json={"company": "美团", "title": "前端"}, **ui)
    assert first.status_code == 201
    dup = client.post("/api/v1/jobs", json={"company": "美团", "title": "前端"}, **ui)
    assert dup.status_code == 200
    assert dup.json()["duplicate_of"] == first.json()["id"]
    # 不拦截语义：再次创建不产生新记录
    listed = client.get("/api/v1/jobs", **ui).json()
    assert len(listed["items"]) == 1


def test_update_job_and_404(client, ui):
    assert client.patch("/api/v1/jobs/nope", json={"channel": "官网"}, **ui).status_code == 404
    job = client.post("/api/v1/jobs", json={"company": "阿里", "title": "测开"}, **ui).json()
    patched = client.patch(f"/api/v1/jobs/{job['id']}", json={"channel": "官网"}, **ui)
    assert patched.status_code == 200
    assert patched.json()["channel"] == "官网"


def test_jobs_pagination(client, ui):
    for i in range(5):
        client.post("/api/v1/jobs", json={"company": f"公司{i}", "title": "岗"}, **ui)
    page1 = client.get("/api/v1/jobs?limit=2", **ui).json()
    assert len(page1["items"]) == 2
    assert page1["next_cursor"]
    page2 = client.get(f"/api/v1/jobs?limit=2&cursor={page1['next_cursor']}", **ui).json()
    assert len(page2["items"]) == 2
    page3 = client.get(f"/api/v1/jobs?limit=2&cursor={page2['next_cursor']}", **ui).json()
    assert len(page3["items"]) == 1
    assert page3["next_cursor"] is None
