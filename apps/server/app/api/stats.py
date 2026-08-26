"""统计与 CSV 导出（FR-50/51/52，口径 §10.4 —— 仅 UI session）。

- overview：指标卡（D-01/D-09 同口径）；
- funnel：entered_count = status_history（非 rejected）出现过该级或主链更后状态的投递数
  ∪ 当前状态已达该级的投递（去重）；「待投递」不计入漏斗；分母为 0 时转化率为 null；
- export：§10.2 台账列，UTF-8 带 BOM 便于 Excel 打开。
筛选（FR-51）：channel 走 job；from/to 按投递创建时间（created_at）。
"""

import csv
import io

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlmodel import select

from autohunt_domain.models import Application as ApplicationRow
from autohunt_domain.models import Confirmation as ConfirmationRow
from autohunt_domain.models import EmailEvent as EmailEventRow
from autohunt_domain.models import Job
from autohunt_domain.models import StatusHistory
from autohunt_domain.models import naive_utc
from app.api.deps import UI_ONLY, parse_rfc3339_query
from app.auth import require_ui
from app.config import get_settings
from app.db import session_for
from app.schemas import (
    ApplicationStatus,
    ErrorEnvelope,
    FunnelConversions,
    FunnelStage,
    StatsFunnel,
    StatsOverview,
)
from app.services.statemachine import MAIN_RANK

IN_PROGRESS = {"已投递", "笔试", "面试", "offer"}
OFFER_STATES = {"offer", "已接受"}
FUNNEL_STAGES = [
    ApplicationStatus.submitted,
    ApplicationStatus.written_test,
    ApplicationStatus.interview,
    ApplicationStatus.offer,
]


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


def _filtered_applications(session, channel, from_dt, to_dt) -> list[ApplicationRow]:
    stmt = select(ApplicationRow)
    if channel is not None:
        stmt = stmt.join(Job, ApplicationRow.job_id == Job.id).where(Job.channel == channel)
    if from_dt is not None:
        stmt = stmt.where(ApplicationRow.created_at >= naive_utc(from_dt))
    if to_dt is not None:
        stmt = stmt.where(ApplicationRow.created_at <= naive_utc(to_dt))
    return session.exec(stmt).all()


def _max_rank_reached(session, application: ApplicationRow) -> int:
    """status_history（非 rejected）主链最高 rank ∪ 当前状态 rank；未进主链为 0。"""

    ranks = [
        MAIN_RANK[ApplicationStatus(h.to_status)]
        for h in session.exec(
            select(StatusHistory).where(
                StatusHistory.application_id == application.id,
                StatusHistory.rejected.is_(False),
            )
        ).all()
        if h.to_status in MAIN_RANK
    ]
    current = ApplicationStatus(application.status)
    if current in MAIN_RANK:
        ranks.append(MAIN_RANK[current])
    return max(ranks, default=0)


def _pending_items(session, channel, from_dt, to_dt) -> int:
    """待确认投递 + 待确认事件（D-01 红点口径）；筛选作用于两侧。"""

    conf_stmt = select(ConfirmationRow).where(ConfirmationRow.status == "待确认")
    if channel is not None or from_dt is not None or to_dt is not None:
        conf_stmt = conf_stmt.join(
            ApplicationRow, ConfirmationRow.application_id == ApplicationRow.id
        )
        if channel is not None:
            conf_stmt = conf_stmt.join(Job, ApplicationRow.job_id == Job.id).where(
                Job.channel == channel
            )
        if from_dt is not None:
            conf_stmt = conf_stmt.where(
                ApplicationRow.created_at >= naive_utc(from_dt)
            )
        if to_dt is not None:
            conf_stmt = conf_stmt.where(
                ApplicationRow.created_at <= naive_utc(to_dt)
            )
    n_conf = len(session.exec(conf_stmt).all())

    event_stmt = select(EmailEventRow).where(EmailEventRow.status == "待确认")
    if channel is not None:
        event_stmt = event_stmt.join(Job, EmailEventRow.matched_job_id == Job.id).where(
            Job.channel == channel
        )
    if from_dt is not None:
        event_stmt = event_stmt.where(
            EmailEventRow.created_at >= naive_utc(from_dt)
        )
    if to_dt is not None:
        event_stmt = event_stmt.where(
            EmailEventRow.created_at <= naive_utc(to_dt)
        )
    n_events = len(session.exec(event_stmt).all())
    return n_conf + n_events


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
    from_dt = parse_rfc3339_query(from_, field="from")
    to_dt = parse_rfc3339_query(to, field="to")
    with session_for(get_settings().data_dir) as session:
        apps = _filtered_applications(session, channel, from_dt, to_dt)
        return StatsOverview(
            total_applications=sum(1 for a in apps if a.status != "待投递"),
            in_progress=sum(1 for a in apps if a.status in IN_PROGRESS),
            pending_items=_pending_items(session, channel, from_dt, to_dt),
            offers=sum(1 for a in apps if a.status in OFFER_STATES),
        )


@router.get(
    "/funnel",
    response_model=StatsFunnel,
    responses=UI_ERRORS,
    summary="投递漏斗（FR-50，口径 §10.4，AC-7 可核对）",
    description=(
        "固定四级：已投递 → 笔试 → 面试 → offer；各级 entered_count 与转化率口径见响应字段描述。"
        "「待投递」（收藏未投）不计入（§10.4）。筛选参数作用于整页（FR-51）。"
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
    from_dt = parse_rfc3339_query(from_, field="from")
    to_dt = parse_rfc3339_query(to, field="to")
    with session_for(get_settings().data_dir) as session:
        apps = _filtered_applications(session, channel, from_dt, to_dt)
        max_ranks = {a.id: _max_rank_reached(session, a) for a in apps}

        entered = {
            stage: sum(1 for a in apps if max_ranks[a.id] >= MAIN_RANK[stage])
            for stage in FUNNEL_STAGES
        }
        n_submitted = entered[ApplicationStatus.submitted]
        n_written = entered[ApplicationStatus.written_test]
        n_interview = entered[ApplicationStatus.interview]
        n_offer = entered[ApplicationStatus.offer]

        return StatsFunnel(
            stages=[
                FunnelStage(stage=stage, entered_count=entered[stage]) for stage in FUNNEL_STAGES
            ],
            conversions=FunnelConversions(
                written_test_rate=(n_written / n_submitted) if n_submitted else None,
                interview_rate=(n_interview / n_written) if n_written else None,
                offer_rate=(n_offer / n_submitted) if n_submitted else None,
            ),
        )


CSV_COLUMNS = ["公司", "岗位名", "渠道", "地点", "JD 链接", "简历版本 ID", "投递时间", "当前状态", "面试轮次", "备注"]


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
    from_dt = parse_rfc3339_query(from_, field="from")
    to_dt = parse_rfc3339_query(to, field="to")
    with session_for(get_settings().data_dir) as session:
        apps = _filtered_applications(session, channel, from_dt, to_dt)
        jobs = {j.id: j for j in session.exec(select(Job)).all()}

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(CSV_COLUMNS)
        for a in sorted(apps, key=lambda x: x.seq):
            job = jobs.get(a.job_id)
            writer.writerow(
                [
                    job.company if job else "",
                    job.title if job else "",
                    (job.channel or "") if job else "",
                    (job.location or "") if job else "",
                    (job.jd_url or "") if job else "",
                    a.resume_id,
                    naive_utc(a.applied_at).isoformat() if a.applied_at else "",
                    a.status,
                    a.interview_round if a.interview_round is not None else "",
                    a.note or "",
                ]
            )
        content = "﻿" + buf.getvalue()  # BOM 便于 Excel 识别 UTF-8
        return CSVResponse(
            content=content,
            headers={"Content-Disposition": 'attachment; filename="applications-export.csv"'},
        )
