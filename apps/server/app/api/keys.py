"""密钥管理（FR-25，§3.1）——仅 UI session；Agent 不可自签发/自吊销。"""

from fastapi import APIRouter, status

from app.api.deps import UI_ONLY
from app.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyInfo, ErrorEnvelope

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
def create_key(body: ApiKeyCreate) -> ApiKeyCreated: ...


@router.get(
    "",
    response_model=list[ApiKeyInfo],
    responses=AUTH_ERRORS,
    summary="列出 API keys",
    description="返回 id/name/前缀/创建时间/最近使用时间，不含完整 key。仅 UI session 可调用。",
    openapi_extra={"security": UI_ONLY},
)
def list_keys() -> list[ApiKeyInfo]: ...


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=AUTH_ERRORS,
    summary="吊销 API key",
    description="即时生效（哈希缓存可短 TTL）。仅 UI session 可调用。",
    openapi_extra={"security": UI_ONLY},
)
def revoke_key(key_id: str) -> None: ...
