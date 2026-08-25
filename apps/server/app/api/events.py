"""邮箱事件与日程（FR-42/43，§3.5 —— UI 为主，Agent 只读）。"""

from datetime import datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse
from sqlmodel import select

from autohunt_domain.models import EmailEvent as EmailEventRow
from autohunt_domain.models import ScheduleEvent as ScheduleEventRow
from autohunt_domain.models import naive_utc
from app.api.deps import ANY_CALLER, UI_ONLY
from app.auth import any_caller, require_ui
from app.config import get_settings
from app.db import session_for
from app.schemas import (
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

router = APIRouter(tags=["events", "schedule"])

COMMON_ERRORS = {
    401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
}


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
    with session_for(get_settings().data_dir) as session:
        stmt = (
            select(EmailEventRow)
            .where(EmailEventRow.status == EmailEventStatus.pending.value)
            .order_by(EmailEventRow.seq)
        )
        if cursor is not None:
            stmt = stmt.where(EmailEventRow.seq > int(cursor))
        rows = session.exec(stmt.limit(limit + 1)).all()
        items, next_cursor = rows[:limit], None
        if len(rows) > limit:
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
    with session_for(get_settings().data_dir) as session:
        stmt = select(ScheduleEventRow).order_by(ScheduleEventRow.start_time)
        if from_ is not None:
            stmt = stmt.where(ScheduleEventRow.start_time >= naive_utc(datetime.fromisoformat(from_)))
        if to is not None:
            stmt = stmt.where(ScheduleEventRow.start_time <= naive_utc(datetime.fromisoformat(to)))
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
    ...  # M4 实现


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
    ...  # M4 实现


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
    ...  # M4 实现


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
    ...  # M4 实现
