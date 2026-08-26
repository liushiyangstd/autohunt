"""UI session 引导（根因修复：浏览器首访无 cookie，此端点签发）。

- GET /api/v1/ui/session：AuthMiddleware 白名单路径（见 app/auth.AUTH_BYPASS_PATHS），
  不要求凭证；读取 load_ui_token(data_dir, ui_token) 并以
  Set-Cookie: ah_session=<token>; Path=/; HttpOnly; SameSite=Lax 下发。
- 仅供 Web UI 首帧引导；成功 200 {"ok":true}，无鉴权失败语义。
"""

from fastapi import APIRouter, Response

from app.auth import UI_COOKIE, load_ui_token
from app.config import get_settings
from app.schemas import UiSessionOk

router = APIRouter(prefix="/ui", tags=["ui"])


@router.get(
    "/session",
    response_model=UiSessionOk,
    summary="UI session 引导（签发 ah_session cookie）",
    description=(
        "浏览器首访无任何凭证时调用本端点，服务端读取/生成 UI session token 并以 "
        "Set-Cookie: ah_session 下发（HttpOnly; SameSite=Lax）。"
        "后续 /api/v1 请求携带该 cookie 即可通过鉴权中间件。"
    ),
)
def ui_session(response: Response) -> UiSessionOk:
    settings = get_settings()
    token = load_ui_token(settings.data_dir, settings.ui_token)
    # 手动构造以精确匹配契约：Path=/; HttpOnly; SameSite=Lax（Starlette set_cookie 会输出小写 lax 且属性顺序不同）
    response.headers["set-cookie"] = (
        f"{UI_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax"
    )
    return UiSessionOk(ok=True)
