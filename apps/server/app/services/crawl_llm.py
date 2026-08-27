"""LLM 兜底解析（PROX-19 技设 §4.3）：官网/未知站点 JD 文本 → 结构化字段。

- 复用 llm_client.load_config（AppSetting key='llm'）；未配置 → LLMNotConfigured（BR-32 降级）。
- token 估算：中文 1 字 ≈ 1 token，英文 4 字符 ≈ 1 token；超 8000 截断并标记 content_truncated（RISK-5）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from openai import APIError, OpenAI

from app.services.crawl_parser import normalize_deadline
from app.services.llm_client import LLMConfig, LLMError, _clean_json, load_config

MAX_INPUT_TOKENS = 8000
# 技设 §2.1：LLM 调用 15s 超时（+ 抓取/截断 ≈ 30s 总超时）；OpenAI 默认 600s 会顶破预算
LLM_TIMEOUT_SECONDS = 15.0

_CJK_RE = re.compile(r"[一-鿿぀-ヿ가-힯]")

_SYSTEM_PROMPT = (
    "你是一名职位信息解析助手。请从下方职位描述文本中提取结构化信息，"
    "以 JSON 对象返回，不要包含任何 markdown 代码块或额外说明。"
    "字段要求如下：\n"
    "- company: 公司名称（字符串或 null）\n"
    "- title: 岗位名称（字符串或 null）\n"
    "- location: 工作地点（字符串或 null）\n"
    "- deadline: 网申截止日期（RFC3339 或 date-only 字符串，或 null）\n"
    "- description: 岗位描述摘要（字符串或 null）\n"
    "- requirements: 对象，含 degree(学历)、experience(经验)、salary(薪资)、tags(标签数组)，"
    "未提及的子字段用 null 或空数组\n"
    "对于未提及的字段，请使用 null，不要编造。"
)


class LLMNotConfigured(Exception):
    """LLM 未配置（BR-32）：返回 parse_failed + LLM_NOT_CONFIGURED 降级。"""


@dataclass
class LlmOutcome:
    fields: dict
    tokens_used: int | None
    content_truncated: bool


def estimate_tokens(text: str) -> int:
    """token 粗估（技设 §4.3）：CJK 1 字 ≈ 1 token，其余 4 字符 ≈ 1 token。"""

    cjk = len(_CJK_RE.findall(text))
    return cjk + (len(text) - cjk) // 4


def truncate_to_tokens(text: str, max_tokens: int = MAX_INPUT_TOKENS) -> tuple[str, bool]:
    """按估算 token 数截断；返回 (截断后文本, 是否截断)。"""

    budget = float(max_tokens)
    out: list[str] = []
    for ch in text:
        cost = 1.0 if _CJK_RE.match(ch) else 0.25
        if budget - cost < 0:
            return "".join(out), True
        out.append(ch)
        budget -= cost
    return text, False


def call_llm_jd(text: str, config: LLMConfig) -> tuple[dict, int | None]:
    """调用 LLM 解析 JD 文本，返回 (字段字典, total_tokens)。结构对齐 llm_client.call_llm。"""

    client_kwargs: dict = {"api_key": config.api_key, "timeout": LLM_TIMEOUT_SECONDS}
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
        data = json.loads(_clean_json(raw))  # 复用 llm_client 的 markdown 代码块清理
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM 返回非法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise LLMError("LLM 返回非 JSON 对象")

    tokens_used = response.usage.total_tokens if response.usage else None
    return data, tokens_used


def _coerce_fields(data: dict) -> dict:
    """输出校验与类型收敛：只认白名单字段，deadline 归一化，requirements 收敛为 dict。"""

    requirements = data.get("requirements")
    if not isinstance(requirements, dict):
        requirements = None
    return {
        "company": data.get("company") if isinstance(data.get("company"), str) else None,
        "title": data.get("title") if isinstance(data.get("title"), str) else None,
        "location": data.get("location") if isinstance(data.get("location"), str) else None,
        "deadline": normalize_deadline(data.get("deadline")),
        "description": data.get("description") if isinstance(data.get("description"), str) else None,
        "requirements": requirements,
    }


def parse_with_llm(text: str, session) -> LlmOutcome:
    """LLM 兜底入口：读配置 → 截断 → 调用 → 校验。未配置抛 LLMNotConfigured。"""

    config = load_config(session)
    if config is None:
        raise LLMNotConfigured("LLM 未配置（请到设置页配置模型与 API Key）")
    truncated_text, truncated = truncate_to_tokens(text)
    data, tokens_used = call_llm_jd(truncated_text, config)
    return LlmOutcome(fields=_coerce_fields(data), tokens_used=tokens_used, content_truncated=truncated)
