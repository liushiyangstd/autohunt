"""邮箱事件与日程（FR-42/43，§3.5 —— UI 为主，Agent 只读）。"""

from fastapi import APIRouter, Query

from app.api.deps import ANY_CALLER
from app.schemas import EmailEventList, ErrorEnvelope, ScheduleEventList

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
def list_pending_events(cursor: str | None = None, limit: int = 50) -> EmailEventList: ...


@router.get(
    "/schedule",
    response_model=ScheduleEventList,
    responses=COMMON_ERRORS,
    summary="日程视图（FR-43）",
    description="按时间区间返回已确认的日程事件。",
    openapi_extra={"security": ANY_CALLER},
)
def get_schedule(
    from_: str | None = Query(default=None, alias="from", description="RFC3339 起"),
    to: str | None = Query(default=None, description="RFC3339 止"),
) -> ScheduleEventList: ...
