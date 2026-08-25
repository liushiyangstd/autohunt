"""确认流（FR-22/23/24 + BR-1，§3.4 —— 本契约的核心）。

状态：待确认 → 已确认 / 已驳回 / 已超时关闭（§10.3）。
- 创建 / 查询：Agent（UI 同套路由可读）。
- confirm / reject / reissue：**仅 UI session**，Agent Bearer 一律 403 FORBIDDEN —— BR-1 担保的最后一道门。
- submit_token 只在「已确认」响应中出现，是系统内唯一的可提交许可。
- 挂起无自动超时（PRD §12）：仅用户手动关闭为「已超时关闭」或重开为新任务。
"""

from fastapi import APIRouter, Request, Response, status
from sqlmodel import select

from autohunt_domain.models import Application as ApplicationRow
from autohunt_domain.models import Confirmation as ConfirmationRow
from autohunt_domain.models import utcnow
from app.api.deps import ANY_CALLER, UI_ONLY
from app.auth import any_caller, require_ui
from app.config import get_settings
from app.db import session_for
from app.errors import not_found, state_conflict
from app.schemas import (
    ConfirmationClosed,
    ConfirmationConfirm,
    ConfirmationConfirmed,
    ConfirmationCreate,
    ConfirmationCreated,
    ConfirmationDetail,
    ConfirmationPending,
    ConfirmationReject,
    ConfirmationStatus,
    ErrorEnvelope,
)
from app.services import permits

router = APIRouter(prefix="/confirmations", tags=["confirmations"])

COMMON_ERRORS = {
    401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
}
NOT_FOUND = {404: {"model": ErrorEnvelope, "description": "NOT_FOUND"}}
AGENT_FORBIDDEN = {
    403: {
        "model": ErrorEnvelope,
        "description": "FORBIDDEN — 本端点仅接受 UI session 凭证；Agent Bearer 调用一律 403（BR-1 最后一道门，AC-3 负例）",
    }
}


def _to_detail(request: Request, row: ConfirmationRow) -> ConfirmationDetail:
    settings = get_settings()
    if row.status == ConfirmationStatus.pending.value:
        return ConfirmationPending()
    if row.status == ConfirmationStatus.confirmed.value:
        token = permits.readable_token(settings.data_dir, row)
        return ConfirmationConfirmed(
            confirmed_fields=row.confirmed_fields or {},
            submit_token=token,
            expires_at=row.token_expires_at,
        )
    return ConfirmationClosed(status=ConfirmationStatus(row.status), reason=row.reason)


def _get_or_404(session, confirmation_id: str) -> ConfirmationRow:
    row = session.exec(select(ConfirmationRow).where(ConfirmationRow.id == confirmation_id)).first()
    if row is None:
        raise not_found("确认单不存在")
    return row


@router.post(
    "",
    response_model=ConfirmationCreated,
    status_code=status.HTTP_201_CREATED,
    responses={
        **COMMON_ERRORS,
        200: {
            "model": ConfirmationCreated,
            "description": "request_id 幂等命中：同一 Agent 重试返回首个确认单（AC-3 异常重试路径）",
        },
    },
    summary="创建待确认（Agent）",
    description="提交待确认字段-值快照。**响应不携带任何可提交许可（BR-1）。**",
    openapi_extra={"security": ANY_CALLER},
)
def create_confirmation(
    request: Request, response: Response, body: ConfirmationCreate
) -> ConfirmationCreated:
    any_caller(request)
    with session_for(get_settings().data_dir) as session:
        existing = session.exec(
            select(ConfirmationRow).where(ConfirmationRow.request_id == body.request_id)
        ).first()
        if existing is not None:
            # request_id 幂等命中：返回首个确认单（AC-3 异常重试路径），HTTP 200
            response.status_code = status.HTTP_200_OK
            return ConfirmationCreated(confirmation_id=existing.id)
        application = session.exec(
            select(ApplicationRow).where(ApplicationRow.id == body.application_id)
        ).first()
        if application is None:
            raise not_found("投递记录不存在")
        row = ConfirmationRow(
            application_id=body.application_id,
            request_id=body.request_id,
            fields=body.fields,
            context=body.context,
            status=ConfirmationStatus.pending.value,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return ConfirmationCreated(confirmation_id=row.id)


@router.get(
    "/{confirmation_id}",
    response_model=ConfirmationDetail,
    responses={**COMMON_ERRORS, **NOT_FOUND},
    summary="查询确认结果（Agent 轮询）",
    description=(
        "按状态返回不同载荷：待确认 → 仅 status；已驳回/已超时关闭 → status + reason?，流程终止；"
        "已确认 → status + confirmed_fields + submit_token + expires_at"
        "（token 过期/已消耗时 submit_token 为 null，走 UI「重新放行」恢复）。"
        "**BR-1 落地：submit_token 只在已确认时出现。**"
    ),
    openapi_extra={"security": ANY_CALLER},
)
def get_confirmation(request: Request, confirmation_id: str) -> ConfirmationDetail:
    any_caller(request)
    with session_for(get_settings().data_dir) as session:
        return _to_detail(request, _get_or_404(session, confirmation_id))


@router.post(
    "/{confirmation_id}/confirm",
    response_model=ConfirmationConfirmed,
    responses={**COMMON_ERRORS, **AGENT_FORBIDDEN, **NOT_FOUND},
    summary="人工确认（仅 UI）",
    description=(
        "用户在确认界面核对快照、可修改任意值后确认。服务端记录 confirmed_fields（含修改后值）与 confirmed_at，"
        "并在确认瞬间签发 submit_token：一次性、绑定 confirmation_id + confirmed_fields 哈希、TTL 30 分钟。"
    ),
    openapi_extra={"security": UI_ONLY},
)
def confirm(request: Request, confirmation_id: str, body: ConfirmationConfirm) -> ConfirmationConfirmed:
    require_ui(request)
    settings = get_settings()
    with session_for(settings.data_dir) as session:
        row = _get_or_404(session, confirmation_id)
        if row.status != ConfirmationStatus.pending.value:
            raise state_conflict(f"确认单当前为「{row.status}」，仅「待确认」可执行确认")
        row.status = ConfirmationStatus.confirmed.value
        row.confirmed_fields = body.confirmed_fields
        row.confirmed_at = utcnow()
        session.add(row)
        session.commit()
        token, expires_at = permits.issue_token(
            session, settings.data_dir, row, settings.submit_token_ttl_seconds
        )
        return ConfirmationConfirmed(
            confirmed_fields=row.confirmed_fields, submit_token=token, expires_at=expires_at
        )


@router.post(
    "/{confirmation_id}/reject",
    response_model=ConfirmationDetail,
    responses={**COMMON_ERRORS, **AGENT_FORBIDDEN, **NOT_FOUND},
    summary="人工驳回（仅 UI）",
    description="驳回后流程终止，状态为「已驳回」。",
    openapi_extra={"security": UI_ONLY},
)
def reject(request: Request, confirmation_id: str, body: ConfirmationReject) -> ConfirmationDetail:
    require_ui(request)
    with session_for(get_settings().data_dir) as session:
        row = _get_or_404(session, confirmation_id)
        if row.status != ConfirmationStatus.pending.value:
            raise state_conflict(f"确认单当前为「{row.status}」，仅「待确认」可执行驳回")
        row.status = ConfirmationStatus.rejected.value
        row.reason = body.reason
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_detail(request, row)


@router.post(
    "/{confirmation_id}/reissue",
    response_model=ConfirmationConfirmed,
    responses={
        **COMMON_ERRORS,
        **AGENT_FORBIDDEN,
        **NOT_FOUND,
        409: {
            "model": ErrorEnvelope,
            "description": "STATE_CONFLICT — 确认单非「已确认」态、token 仍有效，或已回写成功（不可重新放行）",
        },
    },
    summary="重新放行（仅 UI）——token 过期/消耗后的唯一恢复路径",
    description=(
        "确认单处于「已确认」但 submit_token 已过期或已消耗（含回写失败被消耗）时，重新签发 token："
        "原 confirmed_fields 不变、重新绑定哈希、重置 30 分钟 TTL。"
        "**Agent 侧不设任何换发/续期接口**；已回写成功的确认单不可重新放行（§3.4 步骤 5）。"
    ),
    openapi_extra={"security": UI_ONLY},
)
def reissue(request: Request, confirmation_id: str) -> ConfirmationConfirmed:
    require_ui(request)
    settings = get_settings()
    with session_for(settings.data_dir) as session:
        row = _get_or_404(session, confirmation_id)
        if row.status != ConfirmationStatus.confirmed.value:
            raise state_conflict(f"确认单当前为「{row.status}」，仅「已确认」可重新放行")
        if row.submit_result == "success":
            raise state_conflict("已回写成功的确认单不可重新放行（§3.4 步骤 5）")
        if permits.token_active(row):
            raise state_conflict("submit_token 仍有效，无需重新放行")
        token, expires_at = permits.issue_token(
            session, settings.data_dir, row, settings.submit_token_ttl_seconds
        )
        return ConfirmationConfirmed(
            confirmed_fields=row.confirmed_fields or {}, submit_token=token, expires_at=expires_at
        )
