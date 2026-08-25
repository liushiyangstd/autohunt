"""邮箱事件与日程（FR-42/43，§3.5 —— UI 为主，Agent 只读）。"""

from datetime import datetime

from fastapi import APIRouter, Query, Request
from sqlmodel import select

from autohunt_domain.models import EmailEvent as EmailEventRow
from autohunt_domain.models import ScheduleEvent as ScheduleEventRow
from autohunt_domain.models import naive_utc
from app.api.deps import ANY_CALLER
from app.auth import any_caller
from app.config import get_settings
from app.db import session_for
from app.schemas import (
    EmailEvent,
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
