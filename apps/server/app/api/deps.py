"""鉴权声明（§3.1） + 查询参数解析助手。

骨架阶段只声明安全方案用于 OpenAPI 导出，不做真实校验。
- UISession：Web UI 的 HttpOnly Cookie session token
- AgentBearer：外部 Agent 的 `Authorization: Bearer ah_live_<random>`

同一套路由由鉴权中间件按凭证类型打标 caller ∈ {ui, agent}，供状态机做来源裁决（BR-11）。
"""

from datetime import datetime

from fastapi.security import APIKeyCookie, HTTPBearer

from app.errors import validation_error

UI_SESSION = APIKeyCookie(name="ah_session", scheme_name="UISession")
AGENT_BEARER = HTTPBearer(scheme_name="AgentBearer", bearerFormat="ah_live_<random>")

ANY_CALLER: list[dict[str, list[str]]] = [{"UISession": []}, {"AgentBearer": []}]
UI_ONLY: list[dict[str, list[str]]] = [{"UISession": []}]
AGENT_ONLY: list[dict[str, list[str]]] = [{"AgentBearer": []}]


def parse_rfc3339_query(value: str | None, *, field: str) -> datetime | None:
    """解析 from/to 查询参数；非法值 → 422 VALIDATION_ERROR（不 500）。"""

    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise validation_error(f"{field} 不是合法 RFC3339 时间（如 2026-08-01T00:00:00Z）") from None


def parse_cursor(value: str | None, *, field: str = "cursor") -> int | None:
    """解析 keyset/偏移 cursor；非整数 → 422 VALIDATION_ERROR（不 500）。"""

    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise validation_error(f"{field} 必须为整数") from None


def parse_limit(value: int, *, field: str = "limit") -> int:
    """分页 limit 必须 >= 1（limit=0/-1 曾触发 IndexError 500）。"""

    if value < 1:
        raise validation_error(f"{field} 必须为 >= 1 的整数")
    return value
