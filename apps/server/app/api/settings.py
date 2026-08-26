"""提醒偏好（FR-32 配套，D-10，契约 v2 修订 —— 仅 UI session）。

持久化在 app_setting KV 表（key="reminders"），替代前端 localStorage 过渡态；
未写入时返回默认（全开）。M4 提醒调度按本设置过滤 24h/1h/截止提醒的生成。
"""

from fastapi import APIRouter, Request
from sqlmodel import select

import httpx

from autohunt_domain.models import AppSetting
from app.api.deps import UI_ONLY
from app.auth import require_ui
from app.config import get_settings
from app.db import session_for
from app.schemas import (
    ErrorEnvelope,
    LLMConfig,
    LLMConfigTestResult,
    LLMConfigUpdate,
    ReminderSettings,
)
from app.security import decrypt, encrypt

router = APIRouter(prefix="/settings", tags=["settings"])

UI_ERRORS = {
    401: {"model": ErrorEnvelope, "description": "UNAUTHORIZED — 未携带有效凭证"},
    403: {"model": ErrorEnvelope, "description": "FORBIDDEN — 本端点仅接受 UI session 凭证"},
}

KEY = "reminders"


def _load(session) -> ReminderSettings:
    row = session.exec(select(AppSetting).where(AppSetting.key == KEY)).first()
    if row is None:
        return ReminderSettings()
    return ReminderSettings(**row.value)


@router.get(
    "/reminders",
    response_model=ReminderSettings,
    responses=UI_ERRORS,
    summary="读取提醒偏好（FR-32，D-10）【契约 v2 修订】",
    description="未设置过时返回默认（三项全开）。",
    openapi_extra={"security": UI_ONLY},
)
def get_reminders(request: Request) -> ReminderSettings:
    require_ui(request)
    with session_for(get_settings().data_dir) as session:
        return _load(session)


@router.put(
    "/reminders",
    response_model=ReminderSettings,
    responses=UI_ERRORS,
    summary="保存提醒偏好（FR-32，D-10）【契约 v2 修订】",
    description="全量替换三项开关；M4 提醒调度按此过滤 24h/1h 日程提醒与网申截止提醒的生成。",
    openapi_extra={"security": UI_ONLY},
)
def put_reminders(request: Request, body: ReminderSettings) -> ReminderSettings:
    require_ui(request)
    with session_for(get_settings().data_dir) as session:
        row = session.exec(select(AppSetting).where(AppSetting.key == KEY)).first()
        if row is None:
            row = AppSetting(key=KEY, value=body.model_dump())
        else:
            row.value = body.model_dump()
        session.add(row)
        session.commit()
        return body


# ---------- LLM 配置（PROX-8，简历解析） ----------

LLM_KEY = "llm"

DEFAULT_LLM = {
    "enabled": True,
    "provider": "openai",
    "base_url": None,
    "model": "gpt-4o-mini",
    "api_key_enc": None,
    "api_key_last4": None,
    "timeout_seconds": 15,
    "max_tokens": 2048,
}


def _llm_to_config(stored: dict) -> LLMConfig:
    return LLMConfig(
        enabled=stored.get("enabled", True),
        provider=stored.get("provider", "openai"),
        base_url=stored.get("base_url"),
        model=stored.get("model", "gpt-4o-mini"),
        api_key_last4=stored.get("api_key_last4"),
        timeout_seconds=stored.get("timeout_seconds", 15),
        max_tokens=stored.get("max_tokens", 2048),
    )


def _load_llm(session) -> dict:
    row = session.exec(select(AppSetting).where(AppSetting.key == LLM_KEY)).first()
    if row is None:
        return dict(DEFAULT_LLM)
    return dict(row.value)


def _probe_llm(base_url: str | None, api_key: str, model: str, timeout_seconds: int, max_tokens: int) -> tuple[bool, str | None]:
    """向 LLM 端点发送最小连通性探测，成功返回 (True, None)。"""

    url = (base_url.rstrip("/") + "/chat/completions") if base_url else "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": min(max_tokens, 1),
    }
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return True, None
    except httpx.HTTPError as exc:
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001 — 网络/DNS/解析等统一转为失败原因
        return False, str(exc)


@router.get(
    "/llm",
    response_model=LLMConfig,
    responses=UI_ERRORS,
    summary="读取 LLM 配置（PROX-8）",
    description="未配置时返回默认空配置；永不回传 api_key_enc，仅返回 api_key_last4。",
    openapi_extra={"security": UI_ONLY},
)
def get_llm(request: Request) -> LLMConfig:
    require_ui(request)
    with session_for(get_settings().data_dir) as session:
        return _llm_to_config(_load_llm(session))


@router.put(
    "/llm",
    response_model=LLMConfig,
    responses=UI_ERRORS,
    summary="保存/更新 LLM 配置（PROX-8）",
    description="api_key 为写-only，经 Fernet 加密写入 app_setting；响应不回传明文。",
    openapi_extra={"security": UI_ONLY},
)
def put_llm(request: Request, body: LLMConfigUpdate) -> LLMConfig:
    require_ui(request)
    settings = get_settings()
    with session_for(settings.data_dir) as session:
        stored = _load_llm(session)
        stored.update(body.model_dump(exclude={"api_key"}))
        if body.api_key is not None:
            if body.api_key:
                stored["api_key_enc"] = encrypt(settings.data_dir, body.api_key)
                stored["api_key_last4"] = body.api_key[-4:]
            else:
                stored["api_key_enc"] = None
                stored["api_key_last4"] = None
        row = session.exec(select(AppSetting).where(AppSetting.key == LLM_KEY)).first()
        if row is None:
            row = AppSetting(key=LLM_KEY, value=stored)
        else:
            row.value = stored
        session.add(row)
        session.commit()
        return _llm_to_config(stored)


@router.post(
    "/llm/test",
    response_model=LLMConfigTestResult,
    responses=UI_ERRORS,
    summary="测试 LLM 连通性（PROX-8）",
    description="解密已存 API Key 后发最小探测请求；返回 ok / error。",
    openapi_extra={"security": UI_ONLY},
)
def test_llm(request: Request) -> LLMConfigTestResult:
    require_ui(request)
    settings = get_settings()
    with session_for(settings.data_dir) as session:
        stored = _load_llm(session)
    api_key_enc = stored.get("api_key_enc")
    if not api_key_enc:
        return LLMConfigTestResult(ok=False, error="未配置 API Key")
    try:
        api_key = decrypt(settings.data_dir, api_key_enc)
    except Exception as exc:  # noqa: BLE001 — 密钥损坏/迁移等统一报错
        return LLMConfigTestResult(ok=False, error=f"解密失败：{exc}")
    ok, error = _probe_llm(
        stored.get("base_url"),
        api_key,
        stored.get("model", "gpt-4o-mini"),
        stored.get("timeout_seconds", 15),
        stored.get("max_tokens", 2048),
    )
    return LLMConfigTestResult(ok=ok, error=error)
