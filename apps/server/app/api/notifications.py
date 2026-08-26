"""通知列表（FR-32，技设 v1.2 §3.7 —— 仅 UI session）。

合并两类来源：
1. 持久化的日程 24h/1h 提醒：fire_at 到达后出现（返回时置「已触发」，不重复出现）；
2. 网申截止提醒（§4 口径即时计算不落库）：截止前 24h 窗口内、且该 job 下无
   已提交投递（状态≠待投递）时出现；虚拟 id `deadline:<job_id>`。
按 fire_at 倒序，cursor 为合并后偏移量。
"""

from datetime import timedelta

from fastapi import APIRouter, Request
from sqlmodel import select

from autohunt_domain.models import AppSetting
from autohunt_domain.models import Application as ApplicationRow
from autohunt_domain.models import Job
from autohunt_domain.models import Notification as NotificationRow
from autohunt_domain.models import ScheduleEvent as ScheduleEventRow
from autohunt_domain.models import naive_utc, utcnow
from app.api.deps import UI_ONLY, parse_cursor, parse_limit
from app.auth import require_ui
from app.config import get_settings
from app.db import session_for
from app.schemas import ErrorEnvelope, Notification, NotificationKind, NotificationList

router = APIRouter(prefix="/notifications", tags=["notifications"])

DEADLINE_WINDOW = timedelta(hours=24)


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
    cursor_int = parse_cursor(cursor)
    page_size = parse_limit(limit)
    with session_for(get_settings().data_dir) as session:
        now = utcnow().replace(tzinfo=None)
        prefs_row = session.exec(select(AppSetting).where(AppSetting.key == "reminders")).first()
        prefs = prefs_row.value if prefs_row else {}
        items: list[Notification] = []

        # ① 持久化日程提醒：到达即出现并置「已触发」（不重复打扰）
        fired = session.exec(
            select(NotificationRow)
            .where(NotificationRow.status == "待触发", NotificationRow.fire_at <= now)
            .order_by(NotificationRow.seq)
        ).all()
        for row in fired:
            # D5：按 schedule_24h / schedule_1h 偏好过滤（与生成侧 events.py 口径一致）；
            # 被过滤的保持「待触发」，重开偏好后可恢复提醒。
            if not prefs.get("schedule_24h" if row.kind == "24h" else "schedule_1h", True):
                continue
            schedule = session.exec(
                select(ScheduleEventRow).where(ScheduleEventRow.id == row.schedule_event_id)
            ).first()
            if schedule is None:
                continue
            items.append(
                Notification(
                    id=row.id,
                    kind=NotificationKind.schedule_24h if row.kind == "24h" else NotificationKind.schedule_1h,
                    title=schedule.title,
                    message=f"{schedule.title} 将于 {naive_utc(schedule.start_time).isoformat()} 开始",
                    fire_at=row.fire_at,
                    schedule_event_id=schedule.id,
                    application_id=schedule.application_id,
                )
            )
            row.status = "已触发"
            session.add(row)

        # ② 网申截止提醒：即时计算不落库（§4 口径）
        if prefs.get("include_deadline", True):
            jobs = session.exec(select(Job).where(Job.deadline.is_not(None))).all()
            for job in jobs:
                deadline = naive_utc(job.deadline)
                if not (deadline - DEADLINE_WINDOW <= now <= deadline):
                    continue
                submitted = session.exec(
                    select(ApplicationRow)
                    .where(ApplicationRow.job_id == job.id, ApplicationRow.status != "待投递")
                ).first()
                if submitted is not None:
                    continue
                items.append(
                    Notification(
                        id=f"deadline:{job.id}",
                        kind=NotificationKind.deadline,
                        title=f"网申截止：{job.company} {job.title}",
                        message=f"{job.company} {job.title} 网申将于 {deadline.isoformat()} 截止，尚未投递",
                        fire_at=deadline - DEADLINE_WINDOW,
                        application_id=None,
                    )
                )

        session.commit()

        items.sort(key=lambda n: naive_utc(n.fire_at), reverse=True)
        offset = cursor_int or 0
        page = items[offset : offset + page_size]
        next_cursor = str(offset + page_size) if offset + page_size < len(items) else None
        return NotificationList(items=page, next_cursor=next_cursor)
