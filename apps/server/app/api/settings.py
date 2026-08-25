"""提醒偏好（FR-32 配套，D-10，契约 v2 修订 —— 仅 UI session）。

持久化在 app_setting KV 表（key="reminders"），替代前端 localStorage 过渡态；
未写入时返回默认（全开）。M4 提醒调度按本设置过滤 24h/1h/截止提醒的生成。
"""

from fastapi import APIRouter, Request
from sqlmodel import select

from autohunt_domain.models import AppSetting
from app.api.deps import UI_ONLY
from app.auth import require_ui
from app.config import get_settings
from app.db import session_for
from app.schemas import ErrorEnvelope, ReminderSettings

router = APIRouter(prefix="/settings", tags=["settings"])

UI_ERRORS = {
    401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
    403: {"model": ErrorEnvelope, "description": "FORBIDDEN — 本端点仅接受 UI session 凭证"},
}

KEY = "reminders"


def _load(session) -> ReminderSettings:
    row = session.exec(select(AppSetting).where(AppSetting.key == KEY)).first()
    if row is None:
        return ReminderSettings()
    return ReminderSettings(**row.value)


@router.get(
    "/reminders",
    response_model=ReminderSettings,
    responses=UI_ERRORS,
    summary="读取提醒偏好（FR-32，D-10）【契约 v2 修订】",
    description="未设置过时返回默认（三项全开）。",
    openapi_extra={"security": UI_ONLY},
)
def get_reminders(request: Request) -> ReminderSettings:
    require_ui(request)
    with session_for(get_settings().data_dir) as session:
        return _load(session)


@router.put(
    "/reminders",
    response_model=ReminderSettings,
    responses=UI_ERRORS,
    summary="保存提醒偏好（FR-32，D-10）【契约 v2 修订】",
    description="全量替换三项开关；M4 提醒调度按此过滤 24h/1h 日程提醒与网申截止提醒的生成。",
    openapi_extra={"security": UI_ONLY},
)
def put_reminders(request: Request, body: ReminderSettings) -> ReminderSettings:
    require_ui(request)
    with session_for(get_settings().data_dir) as session:
        row = session.exec(select(AppSetting).where(AppSetting.key == KEY)).first()
        if row is None:
            row = AppSetting(key=KEY, value=body.model_dump())
        else:
            row.value = body.model_dump()
        session.add(row)
        session.commit()
        return body
