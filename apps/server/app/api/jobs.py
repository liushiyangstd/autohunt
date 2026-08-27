"""岗位读写（FR-21，§3.3）。"""

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from sqlmodel import select

from autohunt_domain.models import CrawlAttempt, Job as JobRow
from autohunt_domain.models import naive_utc
from app.api.deps import ANY_CALLER, parse_cursor, parse_limit
from app.auth import any_caller
from app.config import get_settings
from app.db import session_for
from app.errors import not_found
from app.schemas import (
    CrawlRequest,
    CrawlResult,
    ErrorEnvelope,
    Job,
    JobCreate,
    JobDuplicate,
    JobList,
    JobUpdate,
)
from app.services import crawl

router = APIRouter(prefix="/jobs", tags=["jobs"])

COMMON_ERRORS = {
    401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
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
        description=row.description,
        requirements=row.requirements,
        confidence=row.confidence,
        created_at=row.created_at,
    )


def _link_crawl_attempt(session, crawl_request_id: str | None, job_id: str) -> None:
    """PROX-19 技设 §3.2：保存/更新后回填 crawl_attempt.job_id（预览期为空，AC-2）。"""

    if not crawl_request_id:
        return
    rows = session.exec(
        select(CrawlAttempt)
        .where(CrawlAttempt.request_id == crawl_request_id)
        .where(CrawlAttempt.job_id.is_(None))
    ).all()
    for attempt in rows:
        attempt.job_id = job_id
        session.add(attempt)


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
            description=body.description,
            requirements=body.requirements,
            confidence=body.confidence,
        )
        session.add(row)
        _link_crawl_attempt(session, body.crawl_request_id, row.id)
        session.commit()
        session.refresh(row)
        return _to_schema(row)


@router.post(
    "/crawl",
    response_model=CrawlResult,
    responses={
        **COMMON_ERRORS,
        429: {"model": ErrorEnvelope, "description": "RATE_LIMITED — 抓取频率超限（10 次/分钟/调用方）"},
    },
    summary="解析职位网页字段（PROX-19：只解析预览，绝不写 job 表）",
    description=(
        "输入 url/source/request_id（可选 extracted 扩展预提取字段），返回 CrawlResult。"
        "boss/nowcoder 走结构化解析，official/unknown 走 LLM 兜底；"
        "30s 内同一 request_id 幂等返回同一结果（BR-4）。"
        "保存须用户确认后走 POST /jobs（BR：绝不自动入库）。"
    ),
    openapi_extra={"security": ANY_CALLER},
)
def crawl_job_endpoint(request: Request, body: CrawlRequest) -> CrawlResult:
    # 注：本路由须在 /{job_id} 之前注册，避免被路径参数吞掉
    caller = any_caller(request)
    with session_for(get_settings().data_dir) as session:
        return crawl.crawl_job(body, caller, session)


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
            if field == "crawl_request_id":
                continue  # 非 job 列：仅用于回填 crawl_attempt（技设 §3.2）
            if field == "deadline" and value is not None:
                value = naive_utc(value)
            setattr(row, field, value)
        _link_crawl_attempt(session, body.crawl_request_id, row.id)
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_schema(row)
