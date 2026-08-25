"""统计与 CSV 导出（FR-50/51/52，口径 §10.4，技设 v1.2 §3.7 —— 仅 UI session）。

契约 v2 骨架：只定义 schema 与路由用于 OpenAPI 导出，业务逻辑（漏斗核算、
CSV 生成）在 M5 实现。
"""

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from app.api.deps import UI_ONLY
from app.auth import require_ui
from app.schemas import ErrorEnvelope, StatsFunnel, StatsOverview


class CSVResponse(Response):
    media_type = "text/csv"

router = APIRouter(prefix="/stats", tags=["stats"])

UI_ERRORS = {
    401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
    403: {"model": ErrorEnvelope, "description": "FORBIDDEN — 本端点仅接受 UI session 凭证"},
}

FILTERS = {
    "channel": Query(default=None, description="按来源渠道筛选（FR-51）"),
    "from_": Query(default=None, alias="from", description="时间段起（RFC3339，按投递创建时间，FR-51）"),
    "to": Query(default=None, description="时间段止（RFC3339）"),
}


@router.get(
    "/overview",
    response_model=StatsOverview,
    responses=UI_ERRORS,
    summary="关键指标卡（FR-52，D-01/D-09 同口径）",
    description="筛选参数作用于全部指标（FR-51）。各指标口径见响应字段描述。",
    openapi_extra={"security": UI_ONLY},
)
def get_stats_overview(
    request: Request,
    channel: str | None = FILTERS["channel"],
    from_: str | None = FILTERS["from_"],
    to: str | None = FILTERS["to"],
) -> StatsOverview:
    require_ui(request)
    ...  # M5 实现


@router.get(
    "/funnel",
    response_model=StatsFunnel,
    responses=UI_ERRORS,
    summary="投递漏斗（FR-50，口径 §10.4，AC-7 可核对）",
    description=(
        "固定四级：已投递 → 笔试 → 面试 → offer；各级 entered_count 与转化率口径见响应字段描述。"
        "「待投递」（收藏未投）不计入（§10.4）。筛选参数作用于整表（FR-51）。"
    ),
    openapi_extra={"security": UI_ONLY},
)
def get_stats_funnel(
    request: Request,
    channel: str | None = FILTERS["channel"],
    from_: str | None = FILTERS["from_"],
    to: str | None = FILTERS["to"],
) -> StatsFunnel:
    require_ui(request)
    ...  # M5 实现


@router.get(
    "/export",
    response_class=CSVResponse,
    responses=UI_ERRORS
    | {
        200: {
            "content": {"text/csv": {}},
            "description": (
                "投递台账 CSV（Content-Disposition: attachment; filename=applications-export.csv；"
                "UTF-8 带 BOM 便于 Excel 打开）。列：公司/岗位名/渠道/地点/JD 链接/简历版本 ID/"
                "投递时间/当前状态/面试轮次/备注（§10.2）。"
            ),
        }
    },
    summary="台账导出 CSV（D-09 明细表导出，本地优先产品的数据可携带性）",
    description="导出当前筛选条件下的投递明细；筛选参数与 funnel 一致（FR-51）。",
    openapi_extra={"security": UI_ONLY},
)
def export_stats_csv(
    request: Request,
    channel: str | None = FILTERS["channel"],
    from_: str | None = FILTERS["from_"],
    to: str | None = FILTERS["to"],
):
    require_ui(request)
    ...  # M5 实现
