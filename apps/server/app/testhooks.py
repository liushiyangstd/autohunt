"""测试钩子（仅 AUTOHUNT_TEST_HOOKS=1 时挂载，include_in_schema=False 不进 OpenAPI）。

应 Tester 请求（PROX-3 S3c 转达）：
- ② confirmed_fields 直接篡改：绕过确认接口改写落库值，用于验证 submit_token 哈希绑定；
- force-expire：把 token 过期时间拨到过去，避免 30 分钟时钟等待（TTL 亦可经
  AUTOHUNT_SUBMIT_TOKEN_TTL_SECONDS 整体调小 —— 钩子①）。

这些路由不属于对外契约，仅在测试环境开启；生产进程不设置该环境变量即不挂载。
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import select

from autohunt_domain.models import Confirmation
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
