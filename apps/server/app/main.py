"""autohunt FastAPI 应用（技术设计 v1.1 §3 契约的实现）。

导出 OpenAPI 3.1 冻结契约 docs/design/api-openapi.json：
    python scripts/export_openapi.py
（导出须与冻结文件零 diff；契约变更走 PR 评审，§3.6。）

运行：uvicorn app.main:app --port 8741（默认端口，§3）
"""

from fastapi import FastAPI

from app.api import applications, confirmations, events, jobs, keys, profile
from app.auth import AuthMiddleware
from app.config import get_settings
from app.errors import ApiError, api_error_handler

app = FastAPI(
    title="autohunt API",
    version="0.1.0",
    description=(
        "autohunt 系统对外 API 契约（技术设计 v1.1 §3，ffaa485）。\n\n"
        "通用约定：JSON；错误统一信封 `{\"error\": {\"code\", \"message\", \"details?\"}}`；"
        "时间一律 RFC3339（UTC 存储、前端本地化展示）；列表分页 `?cursor=&limit=`（默认 50）。\n\n"
        "鉴权（§3.1）：Web UI 使用 HttpOnly Cookie session（UISession）；外部 Agent 使用 "
        "`Authorization: Bearer ah_live_<random>`（AgentBearer）。同一套路由双鉴权，"
        "中间件按凭证类型打标 caller ∈ {ui, agent} 供状态机来源裁决（BR-11）。\n\n"
        "错误码表：UNAUTHORIZED(401)、FORBIDDEN(403)、NOT_FOUND(404)、"
        "PERMIT_REQUIRED(403)/PERMIT_INVALID(403)（submit_token 缺失或无效）、"
        "STATE_CONFLICT(409)（状态机裁决拒绝）、VALIDATION_ERROR(422)。"
    ),
    openapi_tags=[
        {"name": "keys", "description": "API key 管理（FR-25）——仅 UI session"},
        {"name": "profile", "description": "档案读取（FR-20）"},
        {"name": "jobs", "description": "岗位读写（FR-21）"},
        {"name": "applications", "description": "投递读写与提交结果回写（FR-21/24，状态机 §5）"},
        {"name": "confirmations", "description": "确认流（FR-22/23/24 + BR-1，§3.4 核心）"},
        {"name": "events", "description": "待确认邮箱事件（FR-42，BR-2）"},
        {"name": "schedule", "description": "日程视图（FR-43）"},
    ],
)

for module in (keys, profile, jobs, applications, confirmations, events):
    app.include_router(module.router, prefix="/api/v1")

app.add_exception_handler(ApiError, api_error_handler)
app.add_middleware(AuthMiddleware)

if get_settings().test_hooks:
    from app import testhooks

    app.include_router(testhooks.router)
