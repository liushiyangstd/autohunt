"""IMAP 轮询 Worker（FR-41/44，技设 §6）。

- 每账户每 `AUTOHUNT_IMAP_POLL_SECONDS`（默认 300s）一轮：连接 →
  `UID SEARCH UID > last_uid` → 逐封走识别 pipeline → 推进 last_uid（不重不漏）。
- 认证失败（AuthFailed）→ 账户置 auth_failed 并暂停轮询（FR-44，AC-8 警示条数据源）；
  历史事件/日程不动，重授权后续跑。
- 网络等瞬时错误不置状态、不推进 last_uid，下轮重试。
- 后台循环挂 FastAPI lifespan；`AUTOHUNT_IMAP_WORKER=0` 关闭（测试默认不打网络，
  单测直接调 sync_account 并注入假 connector）。
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from sqlmodel import select

from autohunt_domain.models import EmailAccount, utcnow
from app.config import get_settings
from app.db import session_for
from app.security import decrypt
from app.services import email_recognize, imap_client

logger = logging.getLogger("autohunt.imap")


def sync_account(
    data_dir: Path,
    account_id: str,
    connector=imap_client.connect,
) -> int:
    """同步一个账户的新邮件；返回新增待确认事件数。可注入 connector 供测试。"""

    with session_for(data_dir) as session:
        account = session.exec(select(EmailAccount).where(EmailAccount.id == account_id)).first()
        if account is None:
            return 0
        try:
            client = connector(
                account.imap_host, account.port, account.email,
                decrypt(data_dir, account.auth_code_enc),
            )
        except imap_client.AuthFailed:
            # FR-44：授权失效 → auth_failed + 暂停轮询；历史数据不动
            account.status = "auth_failed"
            session.add(account)
            session.commit()
            logger.warning("email account %s auth failed, polling paused", account.email)
            return 0

        created = 0
        max_uid = account.last_uid
        try:
            client.select("INBOX")
            _, data = client.uid("SEARCH", None, f"UID {account.last_uid + 1}:*")
            uids = [u for u in (data[0] or b"").split() if int(u) > account.last_uid]
            for uid in uids:
                _, fetched = client.uid("FETCH", uid, "(RFC822)")
                raw = next(
                    (part[1] for part in fetched if isinstance(part, tuple) and part[1]), None
                )
                if raw is None:
                    continue
                if email_recognize.process_message(session, data_dir, account.id, raw) is not None:
                    created += 1
                max_uid = max(max_uid, int(uid))
        finally:
            try:
                client.logout()
            except Exception:  # noqa: BLE001
                pass

        account.last_uid = max_uid
        account.last_sync_at = utcnow()
        session.add(account)
        session.commit()
        return created


def sync_all_active(data_dir: Path, connector=imap_client.connect) -> dict[str, int]:
    """同步全部 active 账户（auth_failed 暂停，FR-44）。返回 {account_id: 新增数}。"""

    with session_for(data_dir) as session:
        ids = [
            row.id
            for row in session.exec(select(EmailAccount).where(EmailAccount.status == "active")).all()
        ]
    results: dict[str, int] = {}
    for account_id in ids:
        try:
            results[account_id] = sync_account(data_dir, account_id, connector=connector)
        except Exception:  # noqa: BLE001 — 单账户瞬时故障不影响其他账户
            logger.exception("sync account %s failed", account_id)
    return results


async def worker_loop(poll_seconds: int, connector=imap_client.connect) -> None:
    """后台轮询循环；首轮等待一个周期，避免启动即打网络。"""

    while True:
        await asyncio.sleep(poll_seconds)
        await asyncio.to_thread(sync_all_active, get_settings().data_dir, connector)


def poll_seconds_from_env() -> int:
    return int(os.environ.get("AUTOHUNT_IMAP_POLL_SECONDS", "300"))


def worker_enabled() -> bool:
    return os.environ.get("AUTOHUNT_IMAP_WORKER", "1") != "0"
