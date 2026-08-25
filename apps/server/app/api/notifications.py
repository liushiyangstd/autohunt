"""通知列表（FR-32，技设 v1.2 §3.7 —— 仅 UI session）。

契约 v2 骨架：只定义 schema 与路由用于 OpenAPI 导出，业务逻辑（提醒调度、
网申截止即时计算合并）在 M4 实现。
"""

from fastapi import APIRouter, Request

from app.api.deps import UI_ONLY
from app.auth import require_ui
from app.schemas import ErrorEnvelope, NotificationList

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    response_model=NotificationList,
    responses={
        401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
        403: {"model": ErrorEnvelope, "description": "FORBIDDEN — 本端点仅接受 UI session 凭证"},
    },
    summary="应用内通知列表（FR-32，D-01 铃铛 / D-08 提醒）",
    description=(
        "合并两类来源：① 日程事件 24h/1h 两级提醒（持久化，fire_at 到达后出现）；"
        "② 网申截止提醒（按 job.deadline 即时计算不落库，§4 口径：截止前 24h/1h 窗口内、"
        "且该 job 下无「已投递」及之后状态的投递时出现；虚拟 id 形如 deadline:<job_id>）。"
        "按 fire_at 倒序，分页 ?cursor=&limit=（默认 50）。"
    ),
    openapi_extra={"security": UI_ONLY},
)
def list_notifications(request: Request, cursor: str | None = None, limit: int = 50) -> NotificationList:
    require_ui(request)
    ...  # M4 实现：持久提醒 + 截止即时计算合并
