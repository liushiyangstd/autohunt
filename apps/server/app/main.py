"""autohunt FastAPI 应用（技术设计 v1.2 §3 契约的实现 + 契约 v2 增补骨架）。

导出 OpenAPI 3.1 冻结契约 docs/design/api-openapi.json：
    python scripts/export_openapi.py
（导出须与冻结文件零 diff；契约变更走 PR 评审，§3.6。）

运行：uvicorn app.main:app --port 8741（默认端口，§3）
"""

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
    stats,
)
from app.auth import AuthMiddleware
from app.config import get_settings
from app.errors import ApiError, api_error_handler

app = FastAPI(
    title="autohunt API",
    version="0.2.0",
    description=(
        "autohunt 系统对外 API 契约（技术设计 v1.2 §3）。\n\n"
        "通用约定：JSON；错误统一信封 `{\"error\": {\"code\", \"message\", \"details?\"}}`；"
        "时间一律 RFC3339（UTC 存储、前端本地化展示）；列表分页 `?cursor=&limit=`（默认 50）。\n\n"
        "鉴权（§3.1）：Web UI 使用 HttpOnly Cookie session（UISession）；外部 Agent 使用 "
        "`Authorization: Bearer ah_live_<random>`（AgentBearer）。同一套路由双鉴权，"
        "中间件按凭证类型打标 caller ∈ {ui, agent} 供状态机来源裁决（BR-11）。\n\n"
        "错误码表：UNAUTHORIZED(401)、FORBIDDEN(403)、NOT_FOUND(404)、"
        "PERMIT_REQUIRED(403)/PERMIT_INVALID(403)（submit_token 缺失或无效）、"
        "STATE_CONFLICT(409)（状态机裁决拒绝）、VALIDATION_ERROR(422)。\n\n"
        "契约 v2 增补（技设 v1.2 §3.7，M3–M5 写侧，全部仅 UI session，事件详情只读除外）："
        "简历上传/版本管理（/resumes，FR-1/2/3）、档案写（PUT /profile，FR-2）、"
        "邮箱账户绑定/解绑/状态/重授权（/email-accounts，FR-40/44）、"
        "事件确认/丢弃/修正与原文回溯（/events/{id}/confirm|discard|raw，FR-42/43，BR-2）、"
        "通知列表（/notifications，FR-32）、统计与 CSV 导出（/stats/*，FR-50/51/52，口径 §10.4）。"
        "既有 19 端点（v1 冻结）未变动。"
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
    ],
)

for module in (keys, profile, jobs, applications, confirmations, events):
    app.include_router(module.router, prefix="/api/v1")

# 契约 v2 增补路由（M3–M5 骨架，技设 v1.2 §3.7）
for module in (resumes, email_accounts, notifications, stats):
    app.include_router(module.router, prefix="/api/v1")

app.add_exception_handler(ApiError, api_error_handler)
app.add_middleware(AuthMiddleware)

if get_settings().test_hooks:
    from app import testhooks

    app.include_router(testhooks.router)
