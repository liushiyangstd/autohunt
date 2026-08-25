"""鉴权声明（§3.1）。

骨架阶段只声明安全方案用于 OpenAPI 导出，不做真实校验。
- UISession：Web UI 的 HttpOnly Cookie session token
- AgentBearer：外部 Agent 的 `Authorization: Bearer ah_live_<random>`

同一套路由由鉴权中间件按凭证类型打标 caller ∈ {ui, agent}，供状态机做来源裁决（BR-11）。
"""

from fastapi.security import APIKeyCookie, HTTPBearer

UI_SESSION = APIKeyCookie(name="ah_session", scheme_name="UISession")
AGENT_BEARER = HTTPBearer(scheme_name="AgentBearer", bearerFormat="ah_live_<random>")

ANY_CALLER: list[dict[str, list[str]]] = [{"UISession": []}, {"AgentBearer": []}]
UI_ONLY: list[dict[str, list[str]]] = [{"UISession": []}]
AGENT_ONLY: list[dict[str, list[str]]] = [{"AgentBearer": []}]
