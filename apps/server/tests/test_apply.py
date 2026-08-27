"""一键智能投递入口（PROX-18）。"""

from sqlmodel import select

from app.config import get_settings
from app.db import session_for
from autohunt_domain.models import Application as ApplicationRow
from autohunt_domain.models import Confirmation as ConfirmationRow
from autohunt_domain.models import Profile as ProfileRow
from autohunt_domain.models import Resume


def _make_resume_and_profile(client, ui, is_default=True):
    """直接落库：一份简历 + 结构化档案；返回 resume_id。"""

    with session_for(get_settings().data_dir) as session:
        resume = Resume(name="测试简历", version=1, is_default=is_default, file_path="resumes/test.pdf")
        session.add(resume)
        session.commit()
        session.refresh(resume)
        resume_id = resume.id

        profile = ProfileRow(
            resume_id=resume_id,
            resume_version=1,
            name="张三",
            phone="13800001234",
            email="qiuzhi@example.com",
            educations=[{"school": "某大学", "degree": "本科", "major": "计算机科学与技术", "start_date": "2022-09", "end_date": "2026-06"}],
            experiences=[{"company": "某科技公司", "position": "后端实习生", "start_date": "2025-06", "end_date": "2025-09"}],
            skills=["Java", "Python"],
            awards=["一等奖学金"],
            expected_city="杭州",
            expected_position="后端开发工程师",
        )
        session.add(profile)
        session.commit()
        return resume_id


def _get_application(session, app_id):
    return session.exec(select(ApplicationRow).where(ApplicationRow.id == app_id)).first()


def test_apply_job_creates_application_and_confirmation(client, ui):
    resume_id = _make_resume_and_profile(client, ui)
    job = client.post("/api/v1/jobs", json={"company": "阿里巴巴", "title": "后端开发"}, **ui)
    assert job.status_code == 201
    job_id = job.json()["id"]

    resp = client.post(f"/api/v1/jobs/{job_id}/apply", json={"resume_id": resume_id}, **ui)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["application_id"]
    assert body["confirmation_id"]
    assert body["fields"]["姓名"] == "张三"
    assert body["fields"]["学校"] == "某大学"
    assert body["context"]["target_url"] == ""
    assert "_field_meta" in body["context"]

    # 投递记录已生成
    with session_for(get_settings().data_dir) as session:
        app_row = _get_application(session, body["application_id"])
        assert app_row is not None
        assert app_row.status == "待投递"
        assert app_row.resume_id == resume_id

    # 确认单待确认
    detail = client.get(f"/api/v1/confirmations/{body['confirmation_id']}", **ui)
    assert detail.status_code == 200
    assert detail.json()["status"] == "待确认"
    assert detail.json()["fields"]["电话"] == "13800001234"


def test_apply_job_uses_default_resume(client, ui):
    resume_id = _make_resume_and_profile(client, ui, is_default=True)
    job = client.post("/api/v1/jobs", json={"company": "字节", "title": "后端"}, **ui)
    job_id = job.json()["id"]

    resp = client.post(f"/api/v1/jobs/{job_id}/apply", json={}, **ui)
    assert resp.status_code == 201, resp.text
    assert resp.json()["fields"]["姓名"] == "张三"

    with session_for(get_settings().data_dir) as session:
        app_row = _get_application(session, resp.json()["application_id"])
        assert app_row.resume_id == resume_id


def test_apply_job_reuses_pending_application(client, ui):
    resume_id = _make_resume_and_profile(client, ui)
    job = client.post("/api/v1/jobs", json={"company": "腾讯", "title": "后台"}, **ui)
    job_id = job.json()["id"]

    first = client.post(f"/api/v1/jobs/{job_id}/apply", json={"resume_id": resume_id}, **ui)
    assert first.status_code == 201
    app_id = first.json()["application_id"]

    second = client.post(f"/api/v1/jobs/{job_id}/apply", json={"resume_id": resume_id}, **ui)
    assert second.status_code == 201
    assert second.json()["application_id"] == app_id
    assert second.json()["confirmation_id"] != first.json()["confirmation_id"]


def test_apply_job_already_submitted_409(client, ui):
    resume_id = _make_resume_and_profile(client, ui)
    job = client.post("/api/v1/jobs", json={"company": "美团", "title": "后端"}, **ui)
    job_id = job.json()["id"]

    app_resp = client.post(f"/api/v1/jobs/{job_id}/apply", json={"resume_id": resume_id}, **ui)
    app_id = app_resp.json()["application_id"]
    client.patch(f"/api/v1/applications/{app_id}", json={"status": "已投递"}, **ui)

    resp = client.post(f"/api/v1/jobs/{job_id}/apply", json={"resume_id": resume_id}, **ui)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "STATE_CONFLICT"


def test_apply_job_agent_forbidden(client, agent):
    job = client.post("/api/v1/jobs", json={"company": "网易", "title": "Java"}, **agent)
    job_id = job.json()["id"]
    resp = client.post(f"/api/v1/jobs/{job_id}/apply", json={}, **agent)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_apply_job_missing_resume_422(client, ui):
    job = client.post("/api/v1/jobs", json={"company": "百度", "title": "服务端"}, **ui)
    job_id = job.json()["id"]
    resp = client.post(f"/api/v1/jobs/{job_id}/apply", json={}, **ui)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_apply_job_unknown_resume_404(client, ui):
    job = client.post("/api/v1/jobs", json={"company": "京东", "title": "后端"}, **ui)
    job_id = job.json()["id"]
    resp = client.post(f"/api/v1/jobs/{job_id}/apply", json={"resume_id": "no-such-resume"}, **ui)
    assert resp.status_code == 404


def test_form_agent_required_missing_flagged(client, ui):
    """档案缺少必填字段时，context._field_meta 中 missing=true。"""

    with session_for(get_settings().data_dir) as session:
        resume = Resume(name="残缺简历", version=1, is_default=True, file_path="resumes/partial.pdf")
        session.add(resume)
        session.commit()
        session.refresh(resume)
        resume_id = resume.id
        profile = ProfileRow(
            resume_id=resume_id,
            resume_version=1,
            name="张三",
            phone="",
            email="",
            educations=[],
            experiences=[],
            skills=[],
            awards=[],
        )
        session.add(profile)
        session.commit()

    job = client.post("/api/v1/jobs", json={"company": "小红书", "title": "后端"}, **ui)
    job_id = job.json()["id"]

    resp = client.post(f"/api/v1/jobs/{job_id}/apply", json={"resume_id": resume_id}, **ui)
    assert resp.status_code == 201
    meta = __import__("json").loads(resp.json()["context"]["_field_meta"])
    assert meta["电话"]["missing"] is True
    assert meta["邮箱"]["missing"] is True
    assert meta["学校"]["missing"] is True
    assert meta["专业"]["missing"] is True
