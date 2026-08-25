"""submit_token 许可服务（§3.4 —— BR-1 唯一点）。

- 签发：确认瞬间（或 UI「重新放行」）生成，一次性、绑定 confirmation_id + confirmed_fields 哈希、
  TTL 默认 30 分钟（AUTOHUNT_SUBMIT_TOKEN_TTL_SECONDS 可配，测试钩子①）。
- 存储：token 本体 Fernet 加密落盘（GET 需回读给 Agent，无法只存哈希，见 models.py 注）；
  confirmed_fields 单独存绑定哈希，校验时重算比对（防篡改，测试钩子②可验）。
- 校验：无 token → PERMIT_REQUIRED；伪造/跨确认单/过期/已消耗/字段哈希失配 → PERMIT_INVALID。
- 消耗：回写或 Agent 携 token 推「已投递」成功时消费；过期/消耗后唯一恢复路径是 UI「重新放行」。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Session, select

from autohunt_domain.models import Confirmation
from app import security
from app.errors import permit_invalid, permit_required
from app.schemas import ConfirmationStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def issue_token(session: Session, data_dir: Path, confirmation: Confirmation, ttl_seconds: int) -> tuple[str, datetime]:
    """签发新 token（确认或重新放行时调用）：confirmed_fields 不变、重绑哈希、重置 TTL。"""

    assert confirmation.confirmed_fields is not None
    token = security.generate_submit_token()
    confirmation.fields_hash = security.fields_hash(confirmation.confirmed_fields)
    confirmation.submit_token_enc = security.encrypt(data_dir, token)
    confirmation.token_expires_at = _now() + timedelta(seconds=ttl_seconds)
    confirmation.token_consumed = False
    session.add(confirmation)
    session.commit()
    return token, confirmation.token_expires_at


def token_active(confirmation: Confirmation) -> bool:
    return (
        confirmation.submit_token_enc is not None
        and not confirmation.token_consumed
        and confirmation.token_expires_at is not None
        and _aware(confirmation.token_expires_at) > _now()
    )


def readable_token(data_dir: Path, confirmation: Confirmation) -> str | None:
    """GET /confirmations/{id} 用：已确认且 token 有效时返回明文，否则 None（§3.4 步骤 3）。"""

    if confirmation.status != ConfirmationStatus.confirmed.value or not token_active(confirmation):
        return None
    return security.decrypt(data_dir, confirmation.submit_token_enc)


def find_confirmed_for_application(session: Session, application_id: str) -> Confirmation | None:
    return session.exec(
        select(Confirmation)
        .where(Confirmation.application_id == application_id)
        .where(Confirmation.status == ConfirmationStatus.confirmed.value)
        .order_by(Confirmation.seq.desc())
    ).first()


def validate_token(
    data_dir: Path,
    confirmation: Confirmation | None,
    presented: str | None,
) -> None:
    """校验通过则返回；任何失败抛 403（PERMIT_REQUIRED / PERMIT_INVALID）。不消费。"""

    if not presented:
        raise permit_required()
    if confirmation is None or confirmation.submit_token_enc is None:
        raise permit_invalid("无有效确认单或未签发 submit_token")
    try:
        expected = security.decrypt(data_dir, confirmation.submit_token_enc)
    except Exception:
        raise permit_invalid("submit_token 无法解析") from None
    if not secrets_compare(expected, presented):
        raise permit_invalid("submit_token 与本确认单不匹配（伪造/跨确认单）")
    if confirmation.token_consumed:
        raise permit_invalid("submit_token 已被消耗（一次性许可）")
    if confirmation.token_expires_at is None or _aware(confirmation.token_expires_at) <= _now():
        raise permit_invalid("submit_token 已过期（可走 UI「重新放行」恢复）")
    if security.fields_hash(confirmation.confirmed_fields or {}) != confirmation.fields_hash:
        raise permit_invalid("confirmed_fields 与签发时绑定哈希不一致（疑似篡改）")


def consume_token(session: Session, confirmation: Confirmation) -> None:
    confirmation.token_consumed = True
    session.add(confirmation)
    session.commit()


def secrets_compare(a: str, b: str) -> bool:
    import secrets as _secrets

    return _secrets.compare_digest(a, b)
