"""LLM 客户端（PROX-9）：读取 LLM 配置并调用 OpenAI 兼容接口解析简历文本。

- load_config: 从 AppSetting key='llm' 读取配置，解密 api_key，返回运行时配置。
- call_llm: 构建覆盖全部 9 个字段的 prompt，调用 LLM，解析 JSON 并用 Profile schema 校验。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from openai import APIError, OpenAI
from pydantic import ValidationError
from sqlmodel import select

from autohunt_domain.models import AppSetting
from app.config import get_settings
from app.schemas import ProfileBase
from app.security import decrypt


@dataclass
class LLMConfig:
    """运行时 LLM 配置（已解密 api_key）。"""

    enabled: bool
    provider: str
    base_url: str | None
    model: str
    api_key: str


class LLMError(Exception):
    """LLM 调用、JSON 解析或 schema 校验失败。"""


_SYSTEM_PROMPT = (
    "你是一名简历解析助手。请从下方简历文本中提取结构化信息，"
    "以 JSON 对象返回，不要包含任何 markdown 代码块或额外说明。"
    "字段要求如下：\n"
    "- name: 姓名（字符串或 null）\n"
    "- phone: 手机号（字符串或 null）\n"
    "- email: 邮箱（字符串或 null）\n"
    "- educations: 教育经历列表，每项含 school(必填)、degree、major、start_date、end_date\n"
    "- experiences: 工作经历/实习经历列表，每项含 company(必填)、position、start_date、end_date、description\n"
    "- skills: 技能列表（字符串数组）\n"
    "- awards: 奖项/荣誉列表（字符串数组）\n"
    "- expected_city: 期望工作城市（字符串或 null）\n"
    "- expected_position: 期望职位（字符串或 null）\n"
    "对于未提及的字段，请使用 null 或空数组，不要编造。"
)


def load_config(session) -> LLMConfig | None:
    """从 AppSetting 读取 LLM 配置；未设置、未启用或缺少 Key 时返回 None。"""

    row = session.exec(select(AppSetting).where(AppSetting.key == "llm")).first()
    if row is None:
        return None
    value = row.value or {}
    if not value.get("enabled"):
        return None
    api_key_enc = value.get("api_key_enc")
    if not api_key_enc:
        return None
    try:
        api_key = decrypt(get_settings().data_dir, api_key_enc)
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"API Key 解密失败：{exc}") from exc
    if not api_key:
        return None
    return LLMConfig(
        enabled=True,
        provider=value.get("provider") or "openai",
        base_url=value.get("base_url"),
        model=value.get("model") or "gpt-4o-mini",
        api_key=api_key,
    )


def _clean_json(text: str) -> str:
    """去除可能的 markdown 代码块包裹。"""

    text = text.strip()
    if text.startswith("```"):
        text = text[text.find("\n") + 1 :]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
    return text.strip()


def call_llm(text: str, config: LLMConfig) -> dict:
    """调用 LLM 解析简历文本，返回 Profile 字段字典。"""

    client_kwargs: dict = {"api_key": config.api_key}
    if config.base_url:
        client_kwargs["base_url"] = config.base_url

    try:
        client = OpenAI(**client_kwargs)
        response = client.chat.completions.create(
            model=config.model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
    except APIError as exc:
        raise LLMError(f"LLM API 错误：{exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"LLM 调用异常：{exc}") from exc

    raw = response.choices[0].message.content
    if not raw:
        raise LLMError("LLM 返回空内容")

    try:
        data = json.loads(_clean_json(raw))
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM 返回非法 JSON：{exc}") from exc

    try:
        ProfileBase(**data)
    except ValidationError as exc:
        raise LLMError(f"LLM 返回字段校验失败：{exc}") from exc

    return data
