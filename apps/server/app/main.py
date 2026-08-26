"""autohunt FastAPI 应用（技术设计 v1.3 §3 契约的实现 + 契约 v2 增补骨架）。

导出 OpenAPI 3.1 冻结契约 docs/design/api-openapi.json：
    python scripts/export_openapi.py
（导出须与冻结文件零 diff；契约变更走 PR 评审，§3.6。）

运行：uvicorn app.main:app --port 8741（默认端口，§3）
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import (
    applications,
    confirmations,
    email_accounts,
    events,
    jobs,
    keys,
    notifications,
    profile,
    resumes,
    settings as settings_api,
    stats,
    ui,
)
from app.auth import AuthMiddleware
from app.config import get_settings
from app.errors import ApiError, api_error_handler
from app.services import imap_worker


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """M4：启动 IMAP 轮询 Worker（AUTOHUNT_IMAP_WORKER=0 可关，测试环境不打网络）。"""

    task = None
    if imap_worker.worker_enabled():
        import asyncio

        task = asyncio.create_task(imap_worker.worker_loop(imap_worker.poll_seconds_from_env()))
    yield
    if task is not None:
        task.cancel()


app = FastAPI(
    lifespan=lifespan,
    title="autohunt API",
    version="0.2.1",
    description=(
        "autohunt 系统对外 API 契约（技术设计 v1.3 §3）。\n\n"
        "通用约定：JSON；错误统一信封 `{\"error\": {\"code\", \"message\", \"details?\"}}`；"
        "时间一律 RFC3339（UTC 存储、前端本地化展示）；列表分页 `?cursor=&limit=`（默认 50）。\n\n"
        "鉴权（§3.1）：Web UI 使用 HttpOnly Cookie session（UISession）；外部 Agent 使用 "
        "`Authorization: Bearer ah_live_<random>`（AgentBearer）。同一套路由双鉴权，"
        "中间件按凭证类型打标 caller ∈ {ui, agent} 供状态机来源裁决（BR-11）。\n\n"
        "错误码表：UNAUTHORIZED(401)、FORBIDDEN(403)、NOT_FOUND(404)、"
        "PERMIT_REQUIRED(403)/PERMIT_INVALID(403)（submit_token 缺失或无效）、"
        "STATE_CONFLICT(409)（状态机裁决拒绝）、VALIDATION_ERROR(422)。\n\n"
        "契约 v2 增补（技设 §3.7，M3–M5 写侧，全部仅 UI session，事件详情只读除外）："
        "简历上传/版本管理（/resumes，FR-1/2/3）、档案写（PUT /profile，FR-2）、"
        "邮箱账户绑定/解绑/状态/重授权（/email-accounts，FR-40/44）、"
        "事件确认/丢弃/修正与原文回溯（/events/{id}/confirm|discard|raw，FR-42/43，BR-2）、"
        "通知列表（/notifications，FR-32）、统计与 CSV 导出（/stats/*，FR-50/51/52，口径 §10.4）。\n\n"
        "契约 v2 修订（0.2.1）：确认流补 4 项——GET /confirmations 列表（仅 UI）、"
        "GET /confirmations/{id} 待确认变体按 caller 区分（UI 返回快照，Agent 仍仅 status）、"
        "POST /confirmations/{id}/close 手动关闭（仅 UI）、已确认响应含提交结果回写"
        "（submit_result/fail_reason/submitted_at，FR-24）；D-05 读侧三端点"
        "（/applications/{id}/history|confirmations|emails，FR-31/24/43）；"
        "提醒偏好 GET/PUT /settings/reminders（仅 UI）；GET /applications 增可选 from/to 筛选。"
        "既有 v1 冻结 19 端点语义未变动。"
    ),
    openapi_tags=[
        {"name": "keys", "description": "API key 管理（FR-25）——仅 UI session"},
        {"name": "profile", "description": "档案读取（FR-20）"},
        {"name": "jobs", "description": "岗位读写（FR-21）"},
        {"name": "applications", "description": "投递读写与提交结果回写（FR-21/24，状态机 §5）"},
        {"name": "confirmations", "description": "确认流（FR-22/23/24 + BR-1，§3.4 核心）"},
        {"name": "events", "description": "待确认邮箱事件（FR-42，BR-2）"},
        {"name": "schedule", "description": "日程视图（FR-43）"},
        {"name": "resumes", "description": "简历上传与版本管理（FR-1/2/3）——仅 UI session【契约 v2】"},
        {"name": "email-accounts", "description": "邮箱账户绑定/解绑/状态（FR-40/44）——仅 UI session【契约 v2】"},
        {"name": "notifications", "description": "应用内通知列表（FR-32）——仅 UI session【契约 v2】"},
        {"name": "stats", "description": "统计与 CSV 导出（FR-50/51/52，口径 §10.4）——仅 UI session【契约 v2】"},
        {"name": "settings", "description": "设置（提醒偏好，FR-32 配套）——仅 UI session【契约 v2 修订】"},
    ],
)

for module in (keys, profile, jobs, applications, confirmations, events):
    app.include_router(module.router, prefix="/api/v1")

# 契约 v2 增补路由（M3–M5 骨架，技设 §3.7）
for module in (resumes, email_accounts, notifications, stats):
    app.include_router(module.router, prefix="/api/v1")

# 契约 v2 修订路由（设置，已实现）
app.include_router(settings_api.router, prefix="/api/v1")

# UI session 引导（根因修复：浏览器首访签发 cookie，白名单无鉴权）
app.include_router(ui.router, prefix="/api/v1")

app.add_exception_handler(ApiError, api_error_handler)
app.add_middleware(AuthMiddleware)

if get_settings().test_hooks:
    from app import testhooks

    app.include_router(testhooks.router)
