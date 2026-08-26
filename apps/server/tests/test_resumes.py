"""M3 简历上传 / 版本管理 / 档案写（FR-1/2/3，AC-1）。

PDF 样例由 _make_pdf 手工构造（正确 xref，pypdf 可提取 ASCII 文本）。
"""

from __future__ import annotations

import pytest

from tests.conftest import UI_TOKEN, make_application


def _make_pdf(lines: list[str]) -> bytes:
    """构造一个最小合法单页 PDF（Helvetica + ASCII 文本，pypdf 可提取）。"""

    def esc(s: str) -> str:
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    # 显式设置行距（TL），否则 T* 换行不产生 y 位移，pypdf 会拼接成一行
    text_ops = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(f"({esc(ln)}) Tj T*" for ln in lines) + " ET"
    stream = text_ops.encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    return bytes(out)


FULL_PDF = _make_pdf(["Zhang San", "13800001111", "zhangsan@example.com"])
NO_EMAIL_PDF = _make_pdf(["Zhang San", "13800001111"])
GARBAGE_PDF = b"%PDF-1.4 broken bytes that pypdf cannot parse at all \x00\x01\x02"


def _upload(client, auth, pdf: bytes, filename="resume.pdf", name=None):
    data = {} if name is None else {"name": name}
    return client.post(
        "/api/v1/resumes", files={"file": (filename, pdf, "application/pdf")}, data=data, **auth
    )


def test_upload_parse_complete(client, ui):
    resp = _upload(client, ui, FULL_PDF)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "简历 v1"
    assert body["version"] == 1
    assert body["is_default"] is True  # 首个版本自动默认
    assert body["parse_status"] == "解析完成"
    assert body["missing_fields"] == []
    assert body["parse_error"] is None
    assert body["used_count"] == 0

    # 档案已由解析生成（GET /profile 双鉴权读侧）
    profile = client.get("/api/v1/profile", **ui)
    assert profile.status_code == 200
    pdata = profile.json()
    assert pdata["name"] == "Zhang San"
    assert pdata["phone"] == "13800001111"
    assert pdata["email"] == "zhangsan@example.com"
    assert pdata["resume_id"] == body["id"]


def test_upload_partial_missing_fields(client, ui):
    resp = _upload(client, ui, NO_EMAIL_PDF)
    assert resp.status_code == 201
    body = resp.json()
    assert body["parse_status"] == "部分字段缺失"  # AC-1 缺失标记
    assert body["missing_fields"] == ["email"]


def test_upload_parse_failure_not_blocking(client, ui):
    """§12：解析失败返回 201 + parse_status=解析失败，回退手动编辑。"""

    resp = _upload(client, ui, GARBAGE_PDF)
    assert resp.status_code == 201
    body = resp.json()
    assert body["parse_status"] == "解析失败"
    assert body["parse_error"]
    assert set(body["missing_fields"]) == {"name", "phone", "email"}
    # 空档案仍可读（profile 行已建立，字段为空）
    profile = client.get(f"/api/v1/profile?resume_id={body['id']}", **ui).json()
    assert profile["name"] is None


def test_upload_rejects_non_pdf_and_oversize(client, ui):
    resp = _upload(client, ui, FULL_PDF, filename="resume.docx")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    big = b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024 + 1)
    resp = _upload(client, ui, big)
    assert resp.status_code == 422


def test_resume_list_detail_rename_default(client, ui):
    r1 = _upload(client, ui, FULL_PDF).json()
    r2 = _upload(client, ui, NO_EMAIL_PDF, name="第二版").json()
    assert r2["name"] == "第二版"
    assert r2["version"] == 2
    assert r2["is_default"] is False

    listing = client.get("/api/v1/resumes", **ui).json()
    assert [item["id"] for item in listing["items"]] == [r2["id"], r1["id"]]  # 倒序

    detail = client.get(f"/api/v1/resumes/{r1['id']}", **ui).json()
    assert detail["parse_status"] == "解析完成"

    # 设第二版为默认 → 第一版自动取消；GET /profile 缺省跟随默认版本
    resp = client.patch(f"/api/v1/resumes/{r2['id']}", json={"is_default": True}, **ui)
    assert resp.status_code == 200 and resp.json()["is_default"] is True
    listing = client.get("/api/v1/resumes", **ui).json()["items"]
    assert {item["id"]: item["is_default"] for item in listing} == {r1["id"]: False, r2["id"]: True}
    profile = client.get("/api/v1/profile", **ui).json()
    assert profile["resume_id"] == r2["id"]

    # 重命名
    resp = client.patch(f"/api/v1/resumes/{r1['id']}", json={"name": "正式版"}, **ui)
    assert resp.json()["name"] == "正式版"


def test_resume_file_download(client, ui):
    r = _upload(client, ui, FULL_PDF).json()
    resp = client.get(f"/api/v1/resumes/{r['id']}/file", **ui)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content == FULL_PDF


def test_resume_delete_reference_guard(client, ui):
    r = _upload(client, ui, FULL_PDF).json()

    # 未被引用可删（204），再删 404
    resp = client.delete(f"/api/v1/resumes/{r['id']}", **ui)
    assert resp.status_code == 204
    assert client.get(f"/api/v1/resumes/{r['id']}", **ui).status_code == 404

    # 被投递引用 → 409 + used_count（FR-3 回溯保护）
    r2 = _upload(client, ui, FULL_PDF).json()
    job = client.post("/api/v1/jobs", json={"company": "腾讯", "title": "后端"}, **ui).json()
    client.post("/api/v1/applications", json={"job_id": job["id"], "resume_id": r2["id"]}, **ui)
    resp = client.delete(f"/api/v1/resumes/{r2['id']}", **ui)
    assert resp.status_code == 409
    body = resp.json()["error"]
    assert body["code"] == "STATE_CONFLICT"
    assert body["details"]["used_count"] == 1

    # 引用列表可跳岗位详情
    refs = client.get(f"/api/v1/resumes/{r2['id']}/references", **ui).json()
    assert len(refs["items"]) == 1
    assert refs["items"][0]["resume_id"] == r2["id"]


def test_put_profile_full_replace_and_missing_cleared(client, ui):
    """AC-1 往返：缺失标记 → 手动补全保存 → 标记消除；全量替换语义。"""

    r = _upload(client, ui, NO_EMAIL_PDF).json()
    assert r["missing_fields"] == ["email"]

    payload = {
        "resume_id": r["id"],
        "name": "Zhang San",
        "phone": "13800001111",
        "email": "zs@new.example.com",
        "skills": ["Python", "FastAPI"],
        "educations": [{"school": "Example University", "degree": "本科"}],
        "expected_city": "上海",
    }
    resp = client.put("/api/v1/profile", json=payload, **ui)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "zs@new.example.com"
    assert body["skills"] == ["Python", "FastAPI"]

    # 缺失标记消除
    detail = client.get(f"/api/v1/resumes/{r['id']}", **ui).json()
    assert detail["parse_status"] == "解析完成"
    assert detail["missing_fields"] == []

    # 全量替换：再次保存不带 skills → skills 清空
    payload2 = {**payload, "skills": [], "educations": []}
    body = client.put("/api/v1/profile", json=payload2, **ui).json()
    assert body["skills"] == []
    assert body["educations"] == []


def test_put_profile_email_fallback_to_bound_account(client, ui, monkeypatch):
    """§3.2 注：email 省略时回填已绑定求职邮箱（绑定的 IMAP 验证打桩）。"""

    from app.services import imap_client

    monkeypatch.setattr(imap_client, "verify_credentials", lambda *a, **k: None)
    client.post(
        "/api/v1/email-accounts",
        json={"email": "job@example.com", "imap_host": "imap.example.com", "auth_code": "x"},
        **ui,
    )
    r = _upload(client, ui, NO_EMAIL_PDF).json()
    body = client.put(
        "/api/v1/profile",
        json={"resume_id": r["id"], "name": "Zhang San", "phone": "13800001111"},
        **ui,
    ).json()
    assert body["email"] == "job@example.com"


def test_put_profile_unknown_resume_404_and_agent_forbidden(client, ui, agent):
    resp = client.put(
        "/api/v1/profile", json={"resume_id": "nonexistent", "name": "X"}, **ui
    )
    assert resp.status_code == 404

    # 档案写仅 UI（Agent 只读档案）
    r = _upload(client, ui, FULL_PDF).json()
    resp = client.put("/api/v1/profile", json={"resume_id": r["id"]}, **agent)
    assert resp.status_code == 403


def test_resumes_ui_only(client, agent):
    """M3 端点全部仅 UI session（契约 v2）。"""

    assert client.get("/api/v1/resumes", **agent).status_code == 403
    assert client.post("/api/v1/resumes", files={"file": ("a.pdf", FULL_PDF)}, **agent).status_code == 403
