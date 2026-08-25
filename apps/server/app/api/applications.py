"""投递读写（FR-21，§3.3；状态推进经状态机裁决 §5）。"""

from fastapi import APIRouter, Header, Query, status

from app.api.deps import ANY_CALLER, AGENT_ONLY
from app.schemas import (
    Application,
    ApplicationCreate,
    ApplicationList,
    ApplicationStatus,
    ApplicationUpdate,
    ErrorEnvelope,
    SubmitResult,
    SubmitResultAck,
)

router = APIRouter(prefix="/applications", tags=["applications"])

COMMON_ERRORS = {
    401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
}


@router.post(
    "",
    response_model=Application,
    status_code=status.HTTP_201_CREATED,
    responses=COMMON_ERRORS,
    summary="创建投递记录",
    description="初始状态为「待投递」。",
    openapi_extra={"security": ANY_CALLER},
)
def create_application(body: ApplicationCreate) -> Application: ...


@router.get(
    "",
    response_model=ApplicationList,
    responses=COMMON_ERRORS,
    summary="投递列表（看板数据源，FR-12）",
    description="筛选：status / company / channel；分页 ?cursor=&limit=（默认 50）。",
    openapi_extra={"security": ANY_CALLER},
)
def list_applications(
    status_: ApplicationStatus | None = Query(default=None, alias="status"),
    company: str | None = None,
    channel: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> ApplicationList: ...


@router.patch(
    "/{application_id}",
    response_model=Application,
    responses={
        **COMMON_ERRORS,
        403: {
            "model": ErrorEnvelope,
            "description": "PERMIT_REQUIRED / PERMIT_INVALID — Agent 推进「已投递」未携带有效 submit_token（§3.4 步骤 4）",
        },
        404: {"model": ErrorEnvelope, "description": "NOT_FOUND"},
        409: {
            "model": ErrorEnvelope,
            "description": "STATE_CONFLICT — 状态机裁决拒绝（BR-10/11，§5）：自动来源回退、非法流转等",
        },
    },
    summary="状态推进 / 备注更新",
    description=(
        "经状态机单点裁决（§5）：UI 手动允许任意合法流转；agent/email 自动来源仅许 rank 前进，"
        "旁路终止态按来源白名单（email→未通过/已拒绝，agent→未通过，主动放弃/已过期仅 UI）。"
        "Agent 改为「已投递」必须携带 submit_token（body 字段或 Permit 头），来源按 caller 打标。"
    ),
    openapi_extra={"security": ANY_CALLER},
)
def update_application(
    application_id: str,
    body: ApplicationUpdate,
    permit: str | None = Header(
        default=None,
        description="submit_token 的头部携带方式，与 body.submit_token 二选一（§3.4 步骤 4）",
    ),
) -> Application: ...


@router.post(
    "/{application_id}/submit-result",
    response_model=SubmitResultAck,
    responses={
        **COMMON_ERRORS,
        403: {
            "model": ErrorEnvelope,
            "description": "PERMIT_REQUIRED — 无 token；PERMIT_INVALID — token 伪造/过期/已消耗/字段哈希不一致",
        },
        404: {"model": ErrorEnvelope, "description": "NOT_FOUND"},
    },
    summary="回写提交结果（FR-24，§3.4 步骤 4）",
    description=(
        "校验 submit_token（有效、未用、未过期、字段哈希一致）→ 消费 token。"
        "success：投递推进「已投递」（来源=agent）；failed：记录 fail_reason 并保留字段快照，"
        "状态留待用户人工处置（UI 提供「标记已人工投递」）。"
    ),
    openapi_extra={"security": AGENT_ONLY},
)
def submit_result(application_id: str, body: SubmitResult) -> SubmitResultAck: ...
