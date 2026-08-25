"""鉴权（§3.1）：UI session（HttpOnly Cookie）+ Agent Bearer，双鉴权打标 caller ∈ {ui, agent}。

- 纯 ASGI 中间件解析凭证：只守 /api/v1，无效凭证 401 统一信封（OpenAPI 导出不受影响）。
- UI session token：首启生成并落盘 data/ui_session_token（可被 AUTOHUNT_UI_TOKEN 覆盖）。
- Agent key：SHA-256 哈希查表，已吊销即拒；命中更新 last_used_at。
- caller 写入 request.state，供状态机来源裁决（BR-11）与端点内 403 角色判定。
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import select


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

from autohunt_domain.models import ApiKey
from app.config import get_settings
from app.db import session_for
from app.errors import forbidden, unauthorized
from app.security import sha256

UI_COOKIE = "ah_session"


def load_ui_token(data_dir: Path, configured: str | None) -> str:
    if configured:
        return configured
    data_dir.mkdir(parents=True, exist_ok=True)
    token_path = data_dir / "ui_session_token"
    if token_path.exists():
        return token_path.read_text(encoding="utf-8").strip()
    token = f"ah_ui_{secrets.token_urlsafe(24)}"
    token_path.write_text(token, encoding="utf-8")
    try:
        token_path.chmod(0o600)
    except OSError:
        pass
    return token


def _error_response(status_code: int, code: str, message: str) -> bytes:
    import json

    return json.dumps(
        {"error": {"code": code, "message": message}}, ensure_ascii=False
    ).encode("utf-8")


class AuthMiddleware:
    """解析凭证并打标 caller；/api/v1 下无有效凭证一律 401。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1"):
            await self.app(scope, receive, send)
            return

        settings = get_settings()
        ui_token = load_ui_token(settings.data_dir, settings.ui_token)
        headers = {k.decode(): v.decode() for k, v in scope["headers"]}

        caller: str | None = None
        cookie_header = headers.get("cookie", "")
        cookies = dict(
            pair.strip().split("=", 1) for pair in cookie_header.split(";") if "=" in pair
        )
        if cookies.get(UI_COOKIE) and secrets.compare_digest(cookies[UI_COOKIE], ui_token):
            caller = "ui"
        else:
            auth = headers.get("authorization", "")
            if auth.startswith("Bearer "):
                presented = auth.removeprefix("Bearer ").strip()
                with session_for(settings.data_dir) as session:
                    key = session.exec(
                        select(ApiKey).where(ApiKey.key_hash == sha256(presented))
                    ).first()
                    if key is not None and key.revoked_at is None:
                        caller = "agent"
                        key.last_used_at = utcnow()
                        session.add(key)
                        session.commit()

        if caller is None:
            body = _error_response(401, "UNAUTHORIZED", "未携带有效凭证")
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        scope["state"] = {**scope.get("state", {}), "caller": caller}
        await self.app(scope, receive, send)


def caller_of(request) -> str:
    return request.scope["state"]["caller"]


def require_ui(request) -> str:
    """仅 UI session（BR-1 最后一道门：Agent Bearer 一律 403）。"""

    caller = caller_of(request)
    if caller != "ui":
        raise forbidden("本端点仅接受 UI session 凭证；Agent Bearer 调用一律 403（BR-1）")
    return caller


def require_agent(request) -> str:
    caller = caller_of(request)
    if caller != "agent":
        raise forbidden("本端点仅接受 Agent Bearer 凭证")
    return caller


def any_caller(request) -> str:
    caller = caller_of(request)
    if caller not in ("ui", "agent"):
        raise unauthorized()
    return caller
