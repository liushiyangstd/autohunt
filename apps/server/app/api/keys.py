"""密钥管理（FR-25，§3.1）——仅 UI session；Agent 不可自签发/自吊销。"""

from fastapi import APIRouter, Request, Response, status
from sqlmodel import select

from autohunt_domain.models import ApiKey, utcnow
from app.api.deps import UI_ONLY
from app.auth import require_ui
from app.config import get_settings
from app.db import session_for
from app.errors import not_found
from app.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyInfo, ErrorEnvelope
from app.security import generate_api_key, sha256

router = APIRouter(prefix="/keys", tags=["keys"])

AUTH_ERRORS = {
    401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
    403: {"model": ErrorEnvelope, "description": "FORBIDDEN — Agent Bearer 调用密钥管理端点"},
}


@router.post(
    "",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    responses=AUTH_ERRORS,
    summary="签发 Agent API key",
    description="完整 key 仅此一次返回；服务端只存 SHA-256 哈希 + 前缀。仅 UI session 可调用。",
    openapi_extra={"security": UI_ONLY},
)
def create_key(request: Request, body: ApiKeyCreate) -> ApiKeyCreated:
    require_ui(request)
    key = generate_api_key()
    with session_for(get_settings().data_dir) as session:
        record = ApiKey(name=body.name, key_hash=sha256(key), prefix=key[:12])
        session.add(record)
        session.commit()
        session.refresh(record)
        return ApiKeyCreated(
            id=record.id, name=record.name, key=key, prefix=record.prefix, created_at=record.created_at
        )


@router.get(
    "",
    response_model=list[ApiKeyInfo],
    responses=AUTH_ERRORS,
    summary="列出 API keys",
    description="返回 id/name/前缀/创建时间/最近使用时间，不含完整 key。仅 UI session 可调用。",
    openapi_extra={"security": UI_ONLY},
)
def list_keys(request: Request) -> list[ApiKeyInfo]:
    require_ui(request)
    with session_for(get_settings().data_dir) as session:
        rows = session.exec(
            select(ApiKey).where(ApiKey.revoked_at.is_(None)).order_by(ApiKey.seq)
        ).all()
        return [
            ApiKeyInfo(
                id=row.id,
                name=row.name,
                prefix=row.prefix,
                created_at=row.created_at,
                last_used_at=row.last_used_at,
            )
            for row in rows
        ]


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=AUTH_ERRORS,
    summary="吊销 API key",
    description="即时生效（哈希缓存可短 TTL）。仅 UI session 可调用。",
    openapi_extra={"security": UI_ONLY},
)
def revoke_key(request: Request, key_id: str) -> Response:
    require_ui(request)
    with session_for(get_settings().data_dir) as session:
        record = session.exec(select(ApiKey).where(ApiKey.id == key_id)).first()
        if record is None or record.revoked_at is not None:
            raise not_found("API key 不存在或已吊销")
        record.revoked_at = utcnow()
        session.add(record)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
