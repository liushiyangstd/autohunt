"""测试钩子（仅 AUTOHUNT_TEST_HOOKS=1 时挂载，include_in_schema=False 不进 OpenAPI）。

应 Tester 请求（PROX-3 S3c 转达；v2 §17 增补）：
- confirmed_fields 直接篡改：绕过确认接口改写落库值，用于验证 submit_token 哈希绑定；
- force-expire：把 token 过期时间拨到过去，避免 30 分钟时钟等待（TTL 亦可经
  AUTOHUNT_SUBMIT_TOKEN_TTL_SECONDS 整体调小）；
- IMAP test double（§17 ①）：脚本化「认证通过/失败/连接失败」+ 预置邮件，
  配合 `AUTOHUNT_IMAP_BACKEND=fake` 驱动 EMA/EVT 全组，免真实网络；
- 事件种子（§17 ②）：直接造待确认 email_event（含证据区元数据），
  不依赖完整 IMAP 链路；
- 时间控制（§17 ③）：覆盖全局 utcnow 时钟，供通知 fire_at / 截止窗口 /
  stats from/to 边界断言。

这些路由不属于对外契约，仅在测试环境开启；生产进程不设置该环境变量即不挂载。
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import select

from autohunt_domain.models import (
    Confirmation,
    EmailAccount,
    EmailEvent,
    naive_utc,
    set_clock_override,
    utcnow,
)
from app.config import get_settings
from app.db import session_for
from app.errors import not_found

router = APIRouter(prefix="/__test__", include_in_schema=False)


class TamperFields(BaseModel):
    fields: dict[str, str]


@router.post("/confirmations/{confirmation_id}/tamper-fields")
def tamper_fields(confirmation_id: str, body: TamperFields) -> dict:
    """测试钩子②：直接篡改 confirmed_fields（不更新绑定哈希），验 PERMIT_INVALID。"""

    with session_for(get_settings().data_dir) as session:
        row = session.exec(select(Confirmation).where(Confirmation.id == confirmation_id)).first()
        if row is None:
            raise not_found("确认单不存在")
        row.confirmed_fields = body.fields
        session.add(row)
        session.commit()
        return {"tampered": True}


@router.post("/confirmations/{confirmation_id}/force-expire")
def force_expire(confirmation_id: str) -> dict:
    """把 submit_token 过期时间拨到过去，免 30min 时钟等待。"""

    with session_for(get_settings().data_dir) as session:
        row = session.exec(select(Confirmation).where(Confirmation.id == confirmation_id)).first()
        if row is None:
            raise not_found("确认单不存在")
        row.token_expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        session.add(row)
        session.commit()
        return {"expired": True}


# ---------- §17 ① IMAP test double ----------


class ImapMessage(BaseModel):
    subject: str = ""
    from_: str = "hr@example.com"
    to: str = "candidate@example.com"
    date: str | None = None  # RFC2822；缺省用当前时间
    message_id: str | None = None
    body: str = ""


class ImapConfigure(BaseModel):
    mode: str = "ok"  # ok / auth_fail / conn_fail
    messages: list[ImapMessage] = []


def _build_eml(m: ImapMessage) -> bytes:
    msg = EmailMessage()
    msg["Subject"] = m.subject
    msg["From"] = m.from_
    msg["To"] = m.to
    msg["Date"] = m.date or formatdate(localtime=False)
    msg["Message-ID"] = m.message_id or f"<{uuid.uuid4().hex}@test.local>"
    msg.set_content(m.body)
    return msg.as_bytes()


@router.post("/imap/configure")
def configure_imap(body: ImapConfigure) -> dict:
    """脚本化 fake IMAP 行为与预置邮件（配合 AUTOHUNT_IMAP_BACKEND=fake）。"""

    from app.services.imap_fake import get_store

    if body.mode not in ("ok", "auth_fail", "conn_fail"):
        raise not_found("mode 必须是 ok / auth_fail / conn_fail")
    store = get_store()
    store.mode = body.mode
    store.messages = [_build_eml(m) for m in body.messages]
    return {"mode": store.mode, "messages": len(store.messages)}


# ---------- §17 ② 事件种子 ----------


class SeedEvent(BaseModel):
    type: str = "面试"  # 测评/笔试/面试/offer/拒信
    event_time: str | None = None  # RFC3339；缺省不设
    location: str | None = None
    meeting_link: str | None = None
    company: str | None = None
    matched_job_id: str | None = None
    email_subject: str | None = None
    email_sender: str | None = None
    email_received_at: str | None = None
    status: str = "待确认"
    raw_text: str | None = None  # 提供则落盘 EML 并设置 raw_path（回溯端点可用）
    account_id: str | None = None  # 缺省自动建测试账户


@router.post("/events/seed")
def seed_event(body: SeedEvent) -> dict:
    """直接造一条 email_event（含证据区元数据），返回事件 id 与详情。"""

    from autohunt_domain.models import new_id

    settings = get_settings()
    with session_for(settings.data_dir) as session:
        account_id = body.account_id
        if account_id is None:
            acc = EmailAccount(
                email="seed@test.local", imap_host="seed.test", auth_code_enc="seed", status="active"
            )
            session.add(acc)
            session.flush()
            account_id = acc.id
        else:
            acc = session.exec(select(EmailAccount).where(EmailAccount.id == account_id)).first()
            if acc is None:
                acc = EmailAccount(
                    id=account_id, email="seed@test.local", imap_host="seed.test",
                    auth_code_enc="seed", status="active",
                )
                session.add(acc)
                session.flush()

        received_at = (
            naive_utc(datetime.fromisoformat(body.email_received_at)) if body.email_received_at else None
        )
        event = EmailEvent(
            account_id=account_id,
            message_id=f"seed-{new_id()}",
            content_hash=f"seed-{new_id()}",
            type=body.type,
            event_time=naive_utc(datetime.fromisoformat(body.event_time)) if body.event_time else None,
            location=body.location,
            meeting_link=body.meeting_link,
            company=body.company,
            matched_job_id=body.matched_job_id,
            email_subject=body.email_subject,
            email_sender=body.email_sender,
            email_received_at=received_at,
            status=body.status,
        )
        session.add(event)
        session.flush()

        if body.raw_text is not None:
            raw_path = f"mail/{event.id}.eml"
            target = settings.data_dir / raw_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body.raw_text, encoding="utf-8")
            event.raw_path = raw_path

        session.add(event)
        session.commit()
        session.refresh(event)
        return {
            "id": event.id,
            "type": event.type,
            "event_time": event.event_time,
            "location": event.location,
            "company": event.company,
            "matched_job_id": event.matched_job_id,
            "email_subject": event.email_subject,
            "email_sender": event.email_sender,
            "email_received_at": event.email_received_at,
            "status": event.status,
            "account_id": event.account_id,
            "raw_path": event.raw_path,
        }


# ---------- §17 ③ 时间控制 ----------


class TimeSet(BaseModel):
    now: str  # RFC3339（带或不带时区；naive 按 UTC 解释）


@router.post("/time/set")
def time_set(body: TimeSet) -> dict:
    """覆盖全局时钟（utcnow），供 fire_at / 截止窗口 / stats from/to 边界断言。"""

    dt = datetime.fromisoformat(body.now)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    set_clock_override(dt)
    return {"now": naive_utc(utcnow()).isoformat()}


@router.post("/time/reset")
def time_reset() -> dict:
    set_clock_override(None)
    return {"reset": True}
