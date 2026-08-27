"""岗位读写（FR-21，§3.3）与一键智能投递入口（PROX-18）。"""

import json

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from sqlmodel import select

from autohunt_domain.models import Application as ApplicationRow
from autohunt_domain.models import Confirmation as ConfirmationRow
from autohunt_domain.models import Job as JobRow
from autohunt_domain.models import Profile as ProfileRow
from autohunt_domain.models import Resume
from autohunt_domain.models import StatusHistory as StatusHistoryRow
from autohunt_domain.models import naive_utc, new_id, utcnow
from app.api.deps import ANY_CALLER, UI_ONLY, parse_cursor, parse_limit
from app.auth import any_caller, require_ui
from app.config import get_settings
from app.db import session_for
from app.errors import not_found, state_conflict, validation_error
from app.schemas import (
    ConfirmationStatus,
    ErrorEnvelope,
    Job,
    JobApplyRequest,
    JobApplyResponse,
    JobCreate,
    JobDuplicate,
    JobList,
    JobUpdate,
    ProfileBase,
)
from app.services import form_agent

router = APIRouter(prefix="/jobs", tags=["jobs"])

COMMON_ERRORS = {
    401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
}
UI_ERRORS = {
    401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
    403: {"model": ErrorEnvelope, "description": "FORBIDDEN — 本端点仅接受 UI session 凭证"},
}


def _to_schema(row: JobRow) -> Job:
    return Job(
        id=row.id,
        company=row.company,
        title=row.title,
        jd_url=row.jd_url,
        location=row.location,
        channel=row.channel,
        deadline=row.deadline,
        created_at=row.created_at,
    )


@router.post(
    "",
    response_model=Job,
    status_code=status.HTTP_201_CREATED,
    responses={
        **COMMON_ERRORS,
        200: {
            "model": JobDuplicate,
            "description": "BR-3：同公司同岗位重复创建 → 200 + duplicate_of，提示不拦截",
        },
    },
    summary="创建岗位",
    openapi_extra={"security": ANY_CALLER},
)
def create_job(request: Request, response: Response, body: JobCreate) -> Job | JobDuplicate:
    any_caller(request)
    with session_for(get_settings().data_dir) as session:
        existing = session.exec(
            select(JobRow).where(JobRow.company == body.company).where(JobRow.title == body.title)
        ).first()
        if existing is not None:
            # 200 分支绕过 201 的 response_model=Job 校验，直接序列化 JobDuplicate
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=JobDuplicate(
                    duplicate_of=existing.id, job=_to_schema(existing)
                ).model_dump(mode="json"),
            )
        row = JobRow(
            company=body.company,
            title=body.title,
            jd_url=body.jd_url,
            location=body.location,
            channel=body.channel,
            deadline=naive_utc(body.deadline) if body.deadline else None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_schema(row)


@router.get(
    "",
    response_model=JobList,
    responses=COMMON_ERRORS,
    summary="岗位列表",
    description="分页：?cursor=&limit=（默认 50）。",
    openapi_extra={"security": ANY_CALLER},
)
def list_jobs(request: Request, cursor: str | None = None, limit: int = 50) -> JobList:
    any_caller(request)
    cursor_seq = parse_cursor(cursor)
    page_size = parse_limit(limit)
    with session_for(get_settings().data_dir) as session:
        stmt = select(JobRow).order_by(JobRow.seq)
        if cursor_seq is not None:
            stmt = stmt.where(JobRow.seq > cursor_seq)
        rows = session.exec(stmt.limit(page_size + 1)).all()
        items, next_cursor = rows[:page_size], None
        if len(rows) > page_size:
            next_cursor = str(items[-1].seq)
        return JobList(items=[_to_schema(row) for row in items], next_cursor=next_cursor)


@router.get(
    "/{job_id}",
    response_model=Job,
    responses={
        **COMMON_ERRORS,
        404: {"model": ErrorEnvelope, "description": "NOT_FOUND"},
    },
    summary="岗位详情",
    openapi_extra={"security": ANY_CALLER},
)
def get_job(request: Request, job_id: str) -> Job:
    any_caller(request)
    with session_for(get_settings().data_dir) as session:
        row = session.exec(select(JobRow).where(JobRow.id == job_id)).first()
        if row is None:
            raise not_found("岗位不存在")
        return _to_schema(row)


@router.patch(
    "/{job_id}",
    response_model=Job,
    responses={
        **COMMON_ERRORS,
        404: {"model": ErrorEnvelope, "description": "NOT_FOUND"},
    },
    summary="更新岗位字段（公司/岗位名/JD 链接/地点/渠道/截止日期）",
    openapi_extra={"security": ANY_CALLER},
)
def update_job(request: Request, job_id: str, body: JobUpdate) -> Job:
    any_caller(request)
    with session_for(get_settings().data_dir) as session:
        row = session.exec(select(JobRow).where(JobRow.id == job_id)).first()
        if row is None:
            raise not_found("岗位不存在")
        for field, value in body.model_dump(exclude_unset=True).items():
            if field == "deadline" and value is not None:
                value = naive_utc(value)
            setattr(row, field, value)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_schema(row)


@router.post(
    "/{job_id}/apply",
    response_model=JobApplyResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        **UI_ERRORS,
        404: {"model": ErrorEnvelope, "description": "NOT_FOUND — 岗位或简历版本不存在"},
        409: {"model": ErrorEnvelope, "description": "STATE_CONFLICT — 投递已在进行中，无法重复发起"},
        422: {"model": ErrorEnvelope, "description": "VALIDATION_ERROR — 未选择简历或档案不可为空"},
    },
    summary="一键智能投递（PROX-18）",
    description=(
        "为指定岗位创建/复用投递记录，基于结构化档案生成字段快照并创建确认单。"
        "返回后用户进入确认页核对字段；确认后 Agent 凭 submit_token 提交。"
    ),
    openapi_extra={"security": UI_ONLY},
)
def apply_job(request: Request, job_id: str, body: JobApplyRequest) -> JobApplyResponse:
    require_ui(request)
    settings = get_settings()
    with session_for(settings.data_dir) as session:
        job = session.exec(select(JobRow).where(JobRow.id == job_id)).first()
        if job is None:
            raise not_found("岗位不存在")

        resume_id = body.resume_id
        if resume_id is None:
            default_resume = session.exec(select(Resume).where(Resume.is_default.is_(True))).first()
            if default_resume is None:
                raise validation_error("请先上传简历并设置默认版本")
            resume_id = default_resume.id
        else:
            resume = session.exec(select(Resume).where(Resume.id == resume_id)).first()
            if resume is None:
                raise not_found("简历版本不存在")

        application = session.exec(
            select(ApplicationRow).where(ApplicationRow.job_id == job_id).order_by(ApplicationRow.seq.desc())
        ).first()

        if application is None:
            application = ApplicationRow(job_id=job_id, resume_id=resume_id, status="待投递")
            session.add(application)
            session.commit()
            session.refresh(application)
            session.add(
                StatusHistoryRow(
                    application_id=application.id,
                    from_status=None,
                    to_status="待投递",
                    source="ui",
                    rejected=False,
                )
            )
        else:
            if application.status != "待投递":
                raise state_conflict("该岗位已存在进行中的投递，无法再次发起一键投递")
            application.resume_id = resume_id
            session.add(application)

        profile_row = session.exec(
            select(ProfileRow)
            .where(ProfileRow.resume_id == resume_id)
            .order_by(ProfileRow.resume_version.desc())
        ).first()
        if profile_row is None:
            raise validation_error("请先完善结构化档案")

        profile = ProfileBase(
            name=profile_row.name,
            phone=profile_row.phone,
            email=profile_row.email,
            educations=profile_row.educations,
            experiences=profile_row.experiences,
            skills=profile_row.skills,
            awards=profile_row.awards,
            expected_city=profile_row.expected_city,
            expected_position=profile_row.expected_position,
        )

        fields, meta = form_agent.build_snapshot(profile, target_url=job.jd_url)

        request_id = f"apply:{application.id}:{new_id()}"
        context = {
            "target_url": job.jd_url or "",
            "_field_meta": json.dumps(
                {k: v.__dict__ for k, v in meta.items()}, ensure_ascii=False
            ),
        }

        confirmation = ConfirmationRow(
            application_id=application.id,
            request_id=request_id,
            fields=fields,
            context=context,
            status=ConfirmationStatus.pending.value,
        )
        session.add(confirmation)
        session.commit()
        session.refresh(confirmation)

        return JobApplyResponse(
            application_id=application.id,
            confirmation_id=confirmation.id,
            fields=fields,
            context=context,
        )
