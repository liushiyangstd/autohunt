"""邮箱事件与日程（FR-42/43，§3.5 —— UI 为主，Agent 只读）。

事件确认副作用（BR-2）：事件 → 已确认、生成 schedule_event、按提醒偏好建 24h/1h 提醒、
关联投递按 §5 以 email 来源推进状态（被状态机拒绝的推进落 rejected history，不影响确认本身）。
"""

from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse
from sqlmodel import select

from autohunt_domain.models import AppSetting
from autohunt_domain.models import Application as ApplicationRow
from autohunt_domain.models import EmailEvent as EmailEventRow
from autohunt_domain.models import Notification as NotificationRow
from autohunt_domain.models import ScheduleEvent as ScheduleEventRow
from autohunt_domain.models import naive_utc, utcnow
from app.api.deps import ANY_CALLER, UI_ONLY, parse_cursor, parse_limit, parse_rfc3339_query
from app.auth import any_caller, require_ui
from app.config import get_settings
from app.db import session_for
from app.errors import ApiError, not_found, state_conflict
from app.schemas import (
    ApplicationStatus,
    EmailEvent,
    EmailEventConfirm,
    EmailEventConfirmResult,
    EmailEventDetail,
    EmailEventDiscard,
    EmailEventList,
    EmailEventStatus,
    EmailEventType,
    ErrorEnvelope,
    ScheduleEvent,
    ScheduleEventList,
)
from app.services import statemachine

router = APIRouter(tags=["events", "schedule"])

COMMON_ERRORS = {
    401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
}

# 事件类型 → 投递状态推进目标（§5 email 来源；测评无对应状态不推进）
_TYPE_TO_STATUS: dict[str, ApplicationStatus] = {
    "笔试": ApplicationStatus.written_test,
    "面试": ApplicationStatus.interview,
    "offer": ApplicationStatus.offer,
    "拒信": ApplicationStatus.rejected,  # email 白名单允许进入「已拒绝」（§5）
}


def _to_event_schema(row: EmailEventRow) -> EmailEvent:
    return EmailEvent(
        id=row.id,
        type=EmailEventType(row.type),
        event_time=row.event_time,
        location=row.location,
        meeting_link=row.meeting_link,
        company=row.company,
        matched_job_id=row.matched_job_id,
        status=EmailEventStatus(row.status),
        created_at=row.created_at,
    )


def _to_detail_schema(row: EmailEventRow) -> EmailEventDetail:
    return EmailEventDetail(
        **_to_event_schema(row).model_dump(),
        email_subject=row.email_subject,
        email_sender=row.email_sender,
        email_received_at=row.email_received_at,
    )


def _to_schedule_schema(row: ScheduleEventRow) -> ScheduleEvent:
    return ScheduleEvent(
        id=row.id,
        application_id=row.application_id,
        source_event_id=row.source_event_id,
        title=row.title,
        type=EmailEventType(row.type),
        start_time=row.start_time,
        end_time=row.end_time,
        location=row.location,
        meeting_link=row.meeting_link,
    )


def _get_event_or_404(session, event_id: str) -> EmailEventRow:
    row = session.exec(select(EmailEventRow).where(EmailEventRow.id == event_id)).first()
    if row is None:
        raise not_found("事件不存在")
    return row


@router.get(
    "/events/pending",
    response_model=EmailEventList,
    responses=COMMON_ERRORS,
    summary="待确认事件列表（FR-42，BR-2：识别结果一律先进待确认）",
    description="事件确认/丢弃为 UI 操作；Agent 侧 MVP 只读。",
    openapi_extra={"security": ANY_CALLER},
)
def list_pending_events(request: Request, cursor: str | None = None, limit: int = 50) -> EmailEventList:
    any_caller(request)
    cursor_seq = parse_cursor(cursor)
    page_size = parse_limit(limit)
    with session_for(get_settings().data_dir) as session:
        stmt = (
            select(EmailEventRow)
            .where(EmailEventRow.status == EmailEventStatus.pending.value)
            .order_by(EmailEventRow.seq)
        )
        if cursor_seq is not None:
            stmt = stmt.where(EmailEventRow.seq > cursor_seq)
        rows = session.exec(stmt.limit(page_size + 1)).all()
        items, next_cursor = rows[:page_size], None
        if len(rows) > page_size:
            next_cursor = str(items[-1].seq)
        return EmailEventList(
            items=[
                EmailEvent(
                    id=row.id,
                    type=EmailEventType(row.type),
                    event_time=row.event_time,
                    location=row.location,
                    meeting_link=row.meeting_link,
                    company=row.company,
                    matched_job_id=row.matched_job_id,
                    status=EmailEventStatus(row.status),
                    created_at=row.created_at,
                )
                for row in items
            ],
            next_cursor=next_cursor,
        )


@router.get(
    "/schedule",
    response_model=ScheduleEventList,
    responses=COMMON_ERRORS,
    summary="日程视图（FR-43）",
    description="按时间区间返回已确认的日程事件。",
    openapi_extra={"security": ANY_CALLER},
)
def get_schedule(
    request: Request,
    from_: str | None = Query(default=None, alias="from", description="RFC3339 起"),
    to: str | None = Query(default=None, description="RFC3339 止"),
) -> ScheduleEventList:
    any_caller(request)
    from_dt = parse_rfc3339_query(from_, field="from")
    to_dt = parse_rfc3339_query(to, field="to")
    with session_for(get_settings().data_dir) as session:
        stmt = select(ScheduleEventRow).order_by(ScheduleEventRow.start_time)
        if from_dt is not None:
            stmt = stmt.where(ScheduleEventRow.start_time >= naive_utc(from_dt))
        if to_dt is not None:
            stmt = stmt.where(ScheduleEventRow.start_time <= naive_utc(to_dt))
        rows = session.exec(stmt).all()
        return ScheduleEventList(
            items=[
                ScheduleEvent(
                    id=row.id,
                    application_id=row.application_id,
                    source_event_id=row.source_event_id,
                    title=row.title,
                    type=EmailEventType(row.type),
                    start_time=row.start_time,
                    end_time=row.end_time,
                    location=row.location,
                    meeting_link=row.meeting_link,
                )
                for row in rows
            ]
        )


# ---------- 契约 v2 增补（技设 v1.2 §3.7；FR-42 确认/丢弃/修正，BR-2） ----------
# 以下为骨架：只定义 schema 与路由用于 OpenAPI 导出，业务逻辑在 M4 实现。

EVENT_NOT_FOUND = {404: {"model": ErrorEnvelope, "description": "NOT_FOUND"}}
EVENT_UI_FORBIDDEN = {
    403: {"model": ErrorEnvelope, "description": "FORBIDDEN — 本端点仅接受 UI session 凭证"}
}
EVENT_CONFLICT = {
    409: {
        "model": ErrorEnvelope,
        "description": "STATE_CONFLICT — 事件非「待确认」态（重复确认/丢弃幂等拒绝）",
    }
}


@router.get(
    "/events/{event_id}",
    response_model=EmailEventDetail,
    responses=COMMON_ERRORS | EVENT_NOT_FOUND,
    summary="事件详情（含证据区元数据，D-07）",
    description="列表字段 + 原始邮件主题/发件人/收件时间（RISK-5 可回溯）。Agent 只读可查。",
    openapi_extra={"security": ANY_CALLER},
)
def get_event(request: Request, event_id: str) -> EmailEventDetail:
    any_caller(request)
    with session_for(get_settings().data_dir) as session:
        return _to_detail_schema(_get_event_or_404(session, event_id))


@router.get(
    "/events/{event_id}/raw",
    response_class=PlainTextResponse,
    responses=COMMON_ERRORS
    | EVENT_UI_FORBIDDEN
    | EVENT_NOT_FOUND
    | {200: {"content": {"text/plain": {}}, "description": "原始邮件摘录（EML headers + 正文）"}},
    summary="原始邮件回溯（FR-43，D-07「查看原文」）",
    description="原始邮件含敏感内容，仅 UI 可查（最小化暴露，RISK-3）；Agent Bearer 一律 403。",
    openapi_extra={"security": UI_ONLY},
)
def get_event_raw(request: Request, event_id: str):
    require_ui(request)
    settings = get_settings()
    with session_for(settings.data_dir) as session:
        row = _get_event_or_404(session, event_id)
        raw_path = row.raw_path
    if not raw_path or not (Path(settings.data_dir) / raw_path).exists():
        raise not_found("原始邮件存档不存在")
    content = (Path(settings.data_dir) / raw_path).read_bytes()
    return PlainTextResponse(content=content.decode("utf-8", errors="replace"))


@router.post(
    "/events/{event_id}/confirm",
    response_model=EmailEventConfirmResult,
    responses=COMMON_ERRORS | EVENT_UI_FORBIDDEN | EVENT_NOT_FOUND | EVENT_CONFLICT,
    summary="确认加入日程（BR-2；「修正后加入」共用本端点）",
    description=(
        "body 中任一字段均为可选修正项，确认值取修改后值（D-07）。确认后：事件状态 → 已确认、"
        "生成 schedule_event、关联投递按 §5 以 email 来源推进状态（如 笔试/面试；回退仍被状态机拒绝）。"
        "matched_job_id 用于识别未命中时的手动关联。"
    ),
    openapi_extra={"security": UI_ONLY},
)
def confirm_event(request: Request, event_id: str, body: EmailEventConfirm) -> EmailEventConfirmResult:
    require_ui(request)
    with session_for(get_settings().data_dir) as session:
        row = _get_event_or_404(session, event_id)
        if row.status != EmailEventStatus.pending.value:
            raise state_conflict("事件非「待确认」态，不可重复确认/丢弃")

        # 「修正后加入」：body 中提供的字段覆盖识别值
        if body.type is not None:
            row.type = body.type.value
        if body.event_time is not None:
            row.event_time = naive_utc(body.event_time)
        if body.location is not None:
            row.location = body.location
        if body.meeting_link is not None:
            row.meeting_link = body.meeting_link
        if body.company is not None:
            row.company = body.company
        if body.matched_job_id is not None:
            row.matched_job_id = body.matched_job_id
        row.status = EmailEventStatus.confirmed.value

        # 关联投递（matched_job_id → 该岗位最新投递）
        application = None
        if row.matched_job_id is not None:
            application = session.exec(
                select(ApplicationRow)
                .where(ApplicationRow.job_id == row.matched_job_id)
                .order_by(ApplicationRow.seq.desc())
            ).first()

        # BR-2：确认后生成日程事件；无明确时间时回退收件时间/当前时间（统一 naive UTC 存储）
        start_time = naive_utc(row.event_time or row.email_received_at or utcnow())
        schedule = ScheduleEventRow(
            application_id=application.id if application else None,
            source_event_id=row.id,
            title=f"{row.company} {row.type}" if row.company else row.type,
            type=row.type,
            start_time=start_time,
            location=row.location,
            meeting_link=row.meeting_link,
        )
        session.add(schedule)
        session.flush()

        # FR-32：按提醒偏好创建 24h/1h 两级提醒（fire_at 已过的不补发）
        settings_row = session.exec(select(AppSetting).where(AppSetting.key == "reminders")).first()
        prefs = settings_row.value if settings_row else {}
        now = utcnow().replace(tzinfo=None)
        start_naive = start_time
        for kind, delta, enabled_key in (
            ("24h", timedelta(hours=24), "schedule_24h"),
            ("1h", timedelta(hours=1), "schedule_1h"),
        ):
            fire_at = start_naive - delta
            if prefs.get(enabled_key, True) and fire_at > now:
                session.add(
                    NotificationRow(schedule_event_id=schedule.id, kind=kind, fire_at=fire_at)
                )
        session.add(row)
        session.commit()

        # §5：关联投递按 email 来源推进状态；被状态机拒绝（回退/白名单外）时
        # apply_transition 已落 rejected history，确认本身不受影响（事件仍已确认）
        target = _TYPE_TO_STATUS.get(row.type)
        if application is not None and target is not None:
            try:
                statemachine.apply_transition(session, application, target, "email")
            except ApiError:
                pass

        session.refresh(row)
        session.refresh(schedule)
        return EmailEventConfirmResult(
            event=_to_event_schema(row), schedule_event=_to_schedule_schema(schedule)
        )


@router.post(
    "/events/{event_id}/discard",
    response_model=EmailEvent,
    responses=COMMON_ERRORS | EVENT_UI_FORBIDDEN | EVENT_NOT_FOUND | EVENT_CONFLICT,
    summary="丢弃误识别事件（FR-42）",
    description="事件状态 → 已丢弃，reason 作为误识别反馈留存（KPI-2 数据源）。",
    openapi_extra={"security": UI_ONLY},
)
def discard_event(request: Request, event_id: str, body: EmailEventDiscard) -> EmailEvent:
    require_ui(request)
    with session_for(get_settings().data_dir) as session:
        row = _get_event_or_404(session, event_id)
        if row.status != EmailEventStatus.pending.value:
            raise state_conflict("事件非「待确认」态，不可重复确认/丢弃")
        row.status = EmailEventStatus.discarded.value
        row.discard_reason = body.reason  # 误识别反馈留存（KPI-2 数据源）
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_event_schema(row)
