"""投递读写（FR-21，§3.3；状态推进经状态机裁决 §5）。

契约 v2 修订（D-05 读侧 + D-09 筛选）：
- `GET /applications` 增加可选 from/to 时间段筛选（按投递时间 applied_at）；
- `GET /applications/{id}/history` 状态历史（FR-31）；
- `GET /applications/{id}/confirmations` 确认记录（FR-24 结果留档）；
- `GET /applications/{id}/emails` 关联邮件回溯（FR-43，按岗位匹配）。
"""

from fastapi import APIRouter, Header, Query, Request, status
from sqlmodel import select

from autohunt_domain.models import Application as ApplicationRow
from autohunt_domain.models import Confirmation as ConfirmationRow
from autohunt_domain.models import EmailEvent as EmailEventRow
from autohunt_domain.models import Job as JobRow
from autohunt_domain.models import StatusHistory as StatusHistoryRow
from autohunt_domain.models import naive_utc, utcnow
from app.api.deps import ANY_CALLER, AGENT_ONLY, parse_cursor, parse_limit, parse_rfc3339_query
from app.auth import any_caller, caller_of, require_agent
from app.config import get_settings
from app.db import session_for
from app.errors import not_found, permit_required, validation_error
from app.schemas import (
    Application,
    ApplicationCreate,
    ApplicationList,
    ApplicationStatus,
    ApplicationUpdate,
    ConfirmationRecord,
    ConfirmationRecordList,
    ConfirmationStatus,
    EmailEventDetail,
    EmailEventDetailList,
    EmailEventStatus,
    EmailEventType,
    ErrorEnvelope,
    HistorySource,
    StatusHistoryEntry,
    StatusHistoryList,
    SubmitResult,
    SubmitResultAck,
)
from app.services import permits, statemachine

router = APIRouter(prefix="/applications", tags=["applications"])

COMMON_ERRORS = {
    401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
}


def _to_schema(row: ApplicationRow) -> Application:
    return Application(
        id=row.id,
        job_id=row.job_id,
        resume_id=row.resume_id,
        applied_at=row.applied_at,
        status=ApplicationStatus(row.status),
        interview_round=row.interview_round,
        note=row.note,
    )


def _get_or_404(session, application_id: str) -> ApplicationRow:
    row = session.exec(select(ApplicationRow).where(ApplicationRow.id == application_id)).first()
    if row is None:
        raise not_found("投递记录不存在")
    return row


@router.post(
    "",
    response_model=Application,
    status_code=status.HTTP_201_CREATED,
    responses=COMMON_ERRORS,
    summary="创建投递记录",
    description="初始状态为「待投递」。",
    openapi_extra={"security": ANY_CALLER},
)
def create_application(request: Request, body: ApplicationCreate) -> Application:
    any_caller(request)
    with session_for(get_settings().data_dir) as session:
        job = session.exec(select(JobRow).where(JobRow.id == body.job_id)).first()
        if job is None:
            raise not_found("岗位不存在")
        row = ApplicationRow(
            job_id=body.job_id, resume_id=body.resume_id, status=ApplicationStatus.pending.value
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_schema(row)


@router.get(
    "",
    response_model=ApplicationList,
    responses=COMMON_ERRORS,
    summary="投递列表（看板数据源，FR-12）",
    description=(
        "筛选：status / company / channel；分页 ?cursor=&limit=（默认 50）。"
        "契约 v2 修订：新增可选 from/to（RFC3339）按投递时间 applied_at 过滤（D-09 明细表时间段筛选，FR-51）；"
        "applied_at 为空（尚未投递）的记录在指定 from/to 时不返回。"
    ),
    openapi_extra={"security": ANY_CALLER},
)
def list_applications(
    request: Request,
    status_: ApplicationStatus | None = Query(default=None, alias="status"),
    company: str | None = None,
    channel: str | None = None,
    from_: str | None = Query(default=None, alias="from", description="投递时间起（RFC3339，按 applied_at）"),
    to: str | None = Query(default=None, description="投递时间止（RFC3339，按 applied_at）"),
    cursor: str | None = None,
    limit: int = 50,
) -> ApplicationList:
    any_caller(request)
    from_dt = parse_rfc3339_query(from_, field="from")
    to_dt = parse_rfc3339_query(to, field="to")
    cursor_seq = parse_cursor(cursor)
    page_size = parse_limit(limit)
    with session_for(get_settings().data_dir) as session:
        stmt = select(ApplicationRow).order_by(ApplicationRow.seq)
        if status_ is not None:
            stmt = stmt.where(ApplicationRow.status == status_.value)
        if from_dt is not None:
            stmt = stmt.where(ApplicationRow.applied_at >= naive_utc(from_dt))
        if to_dt is not None:
            stmt = stmt.where(ApplicationRow.applied_at <= naive_utc(to_dt))
        if company is not None or channel is not None:
            stmt = stmt.join(JobRow, ApplicationRow.job_id == JobRow.id)
            if company is not None:
                stmt = stmt.where(JobRow.company == company)
            if channel is not None:
                stmt = stmt.where(JobRow.channel == channel)
        if cursor_seq is not None:
            stmt = stmt.where(ApplicationRow.seq > cursor_seq)
        rows = session.exec(stmt.limit(page_size + 1)).all()
        items, next_cursor = rows[:page_size], None
        if len(rows) > page_size:
            next_cursor = str(items[-1].seq)
        return ApplicationList(items=[_to_schema(row) for row in items], next_cursor=next_cursor)


@router.patch(
    "/{application_id}",
    response_model=Application,
    responses={
        **COMMON_ERRORS,
        403: {
            "model": ErrorEnvelope,
            "description": "PERMIT_REQUIRED / PERMIT_INVALID — Agent 推进「已投递」未携带有效 submit_token（§3.4 步骤 4）",
        },
        404: {"model": ErrorEnvelope, "description": "NOT_FOUND"},
        409: {
            "model": ErrorEnvelope,
            "description": "STATE_CONFLICT — 状态机裁决拒绝（BR-10/11，§5）：自动来源回退、非法流转等",
        },
    },
    summary="状态推进 / 备注更新",
    description=(
        "经状态机单点裁决（§5）：UI 手动允许任意合法流转；agent/email 自动来源仅许 rank 前进，"
        "旁路终止态按来源白名单（email→未通过/已拒绝，agent→未通过，主动放弃/已过期仅 UI）。"
        "Agent 改为「已投递」必须携带 submit_token（body 字段或 Permit 头），来源按 caller 打标。"
    ),
    openapi_extra={"security": ANY_CALLER},
)
def update_application(
    request: Request,
    application_id: str,
    body: ApplicationUpdate,
    permit: str | None = Header(
        default=None,
        description="submit_token 的头部携带方式，与 body.submit_token 二选一（§3.4 步骤 4）",
    ),
) -> Application:
    caller = any_caller(request)
    settings = get_settings()
    with session_for(settings.data_dir) as session:
        row = _get_or_404(session, application_id)

        if body.status is None:
            if body.note is not None:
                row.note = body.note
            if body.interview_round is not None:
                row.interview_round = body.interview_round
            session.add(row)
            session.commit()
            session.refresh(row)
            return _to_schema(row)

        confirmation = None
        if caller == "agent" and body.status == ApplicationStatus.submitted:
            # §3.4 步骤 4：Agent 直调 PATCH 推「已投递」同样必须携带有效 submit_token（BR-1 反绕过）
            confirmation = permits.find_confirmed_for_application(session, application_id)
            permits.validate_token(settings.data_dir, confirmation, permit or body.submit_token)

        updated = statemachine.apply_transition(
            session, row, body.status, caller, note=body.note, interview_round=body.interview_round
        )
        if confirmation is not None:
            permits.consume_token(session, confirmation)
        return _to_schema(updated)


@router.post(
    "/{application_id}/submit-result",
    response_model=SubmitResultAck,
    responses={
        **COMMON_ERRORS,
        403: {
            "model": ErrorEnvelope,
            "description": "PERMIT_REQUIRED — 无 token；PERMIT_INVALID — token 伪造/过期/已消耗/字段哈希不一致",
        },
        404: {"model": ErrorEnvelope, "description": "NOT_FOUND"},
    },
    summary="回写提交结果（FR-24，§3.4 步骤 4）",
    description=(
        "校验 submit_token（有效、未用、未过期、字段哈希一致）→ 消费 token。"
        "success：投递推进「已投递」（来源=agent）；failed：记录 fail_reason 并保留字段快照，"
        "状态留待用户人工处置（UI 提供「标记已人工投递」）。"
    ),
    openapi_extra={"security": AGENT_ONLY},
)
def submit_result(request: Request, application_id: str, body: SubmitResult) -> SubmitResultAck:
    require_agent(request)
    # §3.4：submit_token 缺失 → 403 PERMIT_REQUIRED（契约语义，非 422 请求体校验）
    if not body.submit_token:
        raise permit_required()
    if body.result == "failed" and not body.fail_reason:
        raise validation_error("result=failed 时 fail_reason 必填（FR-24）")
    settings = get_settings()
    with session_for(settings.data_dir) as session:
        row = _get_or_404(session, application_id)
        confirmation = permits.find_confirmed_for_application(session, application_id)
        permits.validate_token(settings.data_dir, confirmation, body.submit_token)

        if body.result == "success":
            updated = statemachine.apply_transition(session, row, ApplicationStatus.submitted, "agent")
            permits.consume_token(session, confirmation)
            confirmation.submit_result = "success"
            confirmation.submitted_at = body.submitted_at
            session.add(confirmation)
            session.commit()
            return SubmitResultAck(application_id=application_id, status=ApplicationStatus(updated.status))

        # failed：消费 token、记录 fail_reason、保留字段快照；状态留待用户人工处置（FR-24）
        permits.consume_token(session, confirmation)
        confirmation.submit_result = "failed"
        confirmation.fail_reason = body.fail_reason
        confirmation.submitted_at = body.submitted_at
        session.add(confirmation)
        session.commit()
        return SubmitResultAck(application_id=application_id, status=ApplicationStatus(row.status))


# ---------- 契约 v2 修订：D-05 读侧三端点（只读，双鉴权，与既有读端点同口径） ----------


@router.get(
    "/{application_id}/history",
    response_model=StatusHistoryList,
    responses={**COMMON_ERRORS, 404: {"model": ErrorEnvelope, "description": "NOT_FOUND"}},
    summary="状态历史（FR-31，D-05 状态历史 Tab）【契约 v2 修订】",
    description=(
        "按时间正序返回该投递的全部 status_history 记录（含 source 与 rejected 标记，"
        "被拒绝的自动写入也可查，AC-6 排查）。"
    ),
    openapi_extra={"security": ANY_CALLER},
)
def get_application_history(request: Request, application_id: str) -> StatusHistoryList:
    any_caller(request)
    with session_for(get_settings().data_dir) as session:
        _get_or_404(session, application_id)
        rows = session.exec(
            select(StatusHistoryRow)
            .where(StatusHistoryRow.application_id == application_id)
            .order_by(StatusHistoryRow.seq)
        ).all()
        return StatusHistoryList(
            items=[
                StatusHistoryEntry(
                    from_status=ApplicationStatus(row.from_status) if row.from_status else None,
                    to_status=ApplicationStatus(row.to_status),
                    source=HistorySource(row.source),
                    rejected=row.rejected,
                    created_at=row.created_at,
                )
                for row in rows
            ]
        )


@router.get(
    "/{application_id}/confirmations",
    response_model=ConfirmationRecordList,
    responses={**COMMON_ERRORS, 404: {"model": ErrorEnvelope, "description": "NOT_FOUND"}},
    summary="确认记录（FR-22/24，D-05 确认记录 Tab）【契约 v2 修订】",
    description="返回该投递关联的全部确认单（状态、确认时间、提交结果回写），按创建时间正序。",
    openapi_extra={"security": ANY_CALLER},
)
def get_application_confirmations(request: Request, application_id: str) -> ConfirmationRecordList:
    any_caller(request)
    with session_for(get_settings().data_dir) as session:
        _get_or_404(session, application_id)
        rows = session.exec(
            select(ConfirmationRow)
            .where(ConfirmationRow.application_id == application_id)
            .order_by(ConfirmationRow.seq)
        ).all()
        return ConfirmationRecordList(
            items=[
                ConfirmationRecord(
                    id=row.id,
                    status=ConfirmationStatus(row.status),
                    created_at=row.created_at,
                    confirmed_at=row.confirmed_at,
                    submit_result=row.submit_result,
                    fail_reason=row.fail_reason,
                    submitted_at=row.submitted_at,
                )
                for row in rows
            ]
        )


@router.get(
    "/{application_id}/emails",
    response_model=EmailEventDetailList,
    responses={**COMMON_ERRORS, 404: {"model": ErrorEnvelope, "description": "NOT_FOUND"}},
    summary="关联邮件回溯（FR-43，D-05 邮件 Tab）【契约 v2 修订】",
    description=(
        "返回识别匹配到该投递所属岗位（matched_job_id = application.job_id）的全部邮箱事件，"
        "含证据区元数据（主题/发件人/收件时间，RISK-5）。按识别时间正序。"
    ),
    openapi_extra={"security": ANY_CALLER},
)
def get_application_emails(request: Request, application_id: str) -> EmailEventDetailList:
    any_caller(request)
    with session_for(get_settings().data_dir) as session:
        application = _get_or_404(session, application_id)
        rows = session.exec(
            select(EmailEventRow)
            .where(EmailEventRow.matched_job_id == application.job_id)
            .order_by(EmailEventRow.seq)
        ).all()
        return EmailEventDetailList(
            items=[
                EmailEventDetail(
                    id=row.id,
                    type=EmailEventType(row.type),
                    event_time=row.event_time,
                    location=row.location,
                    meeting_link=row.meeting_link,
                    company=row.company,
                    matched_job_id=row.matched_job_id,
                    status=EmailEventStatus(row.status),
                    created_at=row.created_at,
                    # 证据区列随 M4 迁移落库（技设 §4）；迁移前为 None
                    email_subject=getattr(row, "email_subject", None),
                    email_sender=getattr(row, "email_sender", None),
                    email_received_at=getattr(row, "email_received_at", None),
                )
                for row in rows
            ]
        )
