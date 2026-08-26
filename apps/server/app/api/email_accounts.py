"""邮箱账户绑定 / 解绑 / 状态（FR-40/44，技设 v1.2 §3.7 —— 仅 UI session）。

授权码 Fernet 加密落盘（§2.2 口径），任何响应不回传；绑定/重授权前先做连接预检；
auth_failed 账户暂停轮询（imap_worker.sync_all_active 只跑 active）。
"""

from fastapi import APIRouter, Request
from sqlmodel import select

from autohunt_domain.models import EmailAccount
from app.api.deps import UI_ONLY
from app.auth import require_ui
from app.config import get_settings
from app.db import session_for
from app.errors import not_found, state_conflict, validation_error
from app.schemas import (
    EmailAccountBind,
    EmailAccountInfo,
    EmailAccountList,
    EmailAccountReauth,
    EmailAccountStatus,
    EmailAccountTestResult,
    ErrorEnvelope,
)
from app.security import encrypt
from app.services import imap_client

router = APIRouter(prefix="/email-accounts", tags=["email-accounts"])

UI_ERRORS = {
    401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
    403: {"model": ErrorEnvelope, "description": "FORBIDDEN — 本端点仅接受 UI session 凭证"},
}
NOT_FOUND = {404: {"model": ErrorEnvelope, "description": "NOT_FOUND"}}


def _to_info(row: EmailAccount) -> EmailAccountInfo:
    return EmailAccountInfo(
        id=row.id,
        email=row.email,
        imap_host=row.imap_host,
        port=row.port,
        status=EmailAccountStatus(row.status),
        last_sync_at=row.last_sync_at,
        created_at=row.created_at,
    )


@router.post(
    "/test",
    response_model=EmailAccountTestResult,
    responses=UI_ERRORS,
    summary="测试 IMAP 连接（D-10「测试连接」）",
    description="即时验证授权码与服务器连通性，不落库；失败原因在 error 字段返回（始终 200）。",
    openapi_extra={"security": UI_ONLY},
)
def test_email_account(request: Request, body: EmailAccountBind) -> EmailAccountTestResult:
    require_ui(request)
    error = imap_client.verify_credentials(body.email, body.imap_host, body.port, body.auth_code)
    return EmailAccountTestResult(ok=error is None, error=error)


@router.post(
    "",
    response_model=EmailAccountInfo,
    status_code=201,
    responses=UI_ERRORS
    | {
        409: {"model": ErrorEnvelope, "description": "STATE_CONFLICT — 该邮箱已绑定"},
    },
    summary="绑定求职邮箱（FR-40，OP-4 IMAP 授权码）",
    description=(
        "绑定前先做连接验证：失败 → 422 VALIDATION_ERROR（统一信封，message 含原因），不创建账户。"
        "授权码 Fernet 加密落盘（§2.2 密钥存储口径），任何响应不回传。绑定成功即启动该账户轮询。"
    ),
    openapi_extra={"security": UI_ONLY},
)
def bind_email_account(request: Request, body: EmailAccountBind) -> EmailAccountInfo:
    require_ui(request)
    settings = get_settings()
    with session_for(settings.data_dir) as session:
        existing = session.exec(select(EmailAccount).where(EmailAccount.email == body.email)).first()
        if existing is not None:
            raise state_conflict("该邮箱已绑定")
        error = imap_client.verify_credentials(body.email, body.imap_host, body.port, body.auth_code)
        if error is not None:
            raise validation_error(f"邮箱连接验证失败：{error}")
        row = EmailAccount(
            email=body.email,
            imap_host=body.imap_host,
            port=body.port,
            auth_code_enc=encrypt(settings.data_dir, body.auth_code),
            status="active",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_info(row)


@router.get(
    "",
    response_model=EmailAccountList,
    responses=UI_ERRORS,
    summary="邮箱账户列表（含状态，FR-44）",
    description="status=auth_failed 时 UI 顶部持续警示条（AC-8）；永不包含授权码。",
    openapi_extra={"security": UI_ONLY},
)
def list_email_accounts(request: Request) -> EmailAccountList:
    require_ui(request)
    with session_for(get_settings().data_dir) as session:
        rows = session.exec(select(EmailAccount).order_by(EmailAccount.seq)).all()
        return EmailAccountList(items=[_to_info(row) for row in rows])


@router.patch(
    "/{account_id}",
    response_model=EmailAccountInfo,
    responses=UI_ERRORS | NOT_FOUND,
    summary="重授权（FR-44 恢复路径）",
    description=(
        "授权失效后提交新授权码：验证通过 → status 恢复 active、续跑轮询（last_uid 保证不重不漏）；"
        "验证失败 → 422 VALIDATION_ERROR，status 保持 auth_failed。"
    ),
    openapi_extra={"security": UI_ONLY},
)
def reauth_email_account(request: Request, account_id: str, body: EmailAccountReauth) -> EmailAccountInfo:
    require_ui(request)
    settings = get_settings()
    with session_for(settings.data_dir) as session:
        row = session.exec(select(EmailAccount).where(EmailAccount.id == account_id)).first()
        if row is None:
            raise not_found("邮箱账户不存在")
        error = imap_client.verify_credentials(row.email, row.imap_host, row.port, body.auth_code)
        if error is not None:
            raise validation_error(f"邮箱连接验证失败：{error}（状态保持 auth_failed）")
        row.auth_code_enc = encrypt(settings.data_dir, body.auth_code)
        row.status = "active"
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_info(row)


@router.delete(
    "/{account_id}",
    status_code=204,
    responses=UI_ERRORS | NOT_FOUND,
    summary="解绑并清除凭据（RISK-3）",
    description="停止轮询、删除加密凭据；历史已识别事件与日程完整保留（FR-44/AC-8）。",
    openapi_extra={"security": UI_ONLY},
)
def unbind_email_account(request: Request, account_id: str) -> None:
    require_ui(request)
    with session_for(get_settings().data_dir) as session:
        row = session.exec(select(EmailAccount).where(EmailAccount.id == account_id)).first()
        if row is None:
            raise not_found("邮箱账户不存在")
        session.delete(row)  # 历史 email_event/schedule_event 保留（AC-8）
        session.commit()
