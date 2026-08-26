"""简历 PDF 解析（FR-2，M3）：LLM 主解析 + 规则兜底（PROX-9）。

- 优先使用配置好的 LLM 解析全部 9 个字段；
- 未配置 LLM Key 时直接标记「未配置 API Key」；
- LLM 调用异常（超时、API 错误、非法 JSON、校验失败）降级到规则抽取；
- 必填字段缺失走「部分字段缺失」标记（AC-1），用户进 D-03 手动补全；
- 解析整体失败返回「解析失败」不阻塞上传（§12）。
"""

from __future__ import annotations

import io
import re

from pypdf import PdfReader

from app.config import Settings
from app.services.llm_client import LLMError, LLMConfig, call_llm, load_config

REQUIRED_FIELDS = ("name", "phone", "email", "educations")

_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_NAME_RE = re.compile(r"^(?:姓名[:：]\s*)?([一-龥]{2,4})(?:\s*(?:男|女))?$")
_LATIN_NAME_RE = re.compile(r"^(?:Name[:：]\s*)?([A-Za-z][A-Za-z'\-]*(?:\s+[A-Za-z][A-Za-z'\-]*){0,3})$")
_CITY_RE = re.compile(r"(?:期望工作地[点市]?|意向城市|期望城市)[:：]?\s*([一-龥A-Za-z（()、,，/\s]{2,30})")
_POSITION_RE = re.compile(r"(?:求职意向|期望职位|意向岗位)[:：]?\s*([一-龥A-Za-z0-9（()、,，/\s]{2,30})")
_EDU_RE = re.compile(
    r"([一-龥A-Za-z]{2,20}(?:大学|学院|职业技术学院|University|College|Institute))"
    r"[^\n]{0,40}?(博士|硕士|研究生|本科|大专|MBA|Bachelor|Master|PhD)?"
)
_DEGREE_MAP = {
    "博士": "博士", "PhD": "博士",
    "硕士": "硕士", "研究生": "硕士", "Master": "硕士", "MBA": "硕士",
    "本科": "本科", "Bachelor": "本科",
    "大专": "大专",
}
_SKILL_LINE_RE = re.compile(r"(?:技能|专业技能|IT 技能|IT技能)[:：]\s*(.+)")


class ParseFailure(Exception):
    """PDF 无法提取文本（损坏/扫描件/加密等）。"""


def extract_text(pdf_bytes: bytes) -> str:
    """pypdf 提取全部页面文本；提取不到任何文本视为失败（扫描件等）。"""

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise ParseFailure(f"PDF 加密无法读取：{exc}") from exc
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except ParseFailure:
        raise
    except Exception as exc:  # noqa: BLE001 — 任何解析异常都归为「解析失败」（§12 不阻塞）
        raise ParseFailure(f"PDF 解析异常：{exc}") from exc
    if not text.strip():
        raise ParseFailure("未提取到文本内容（可能为扫描件/图片型 PDF）")
    return text


def parse_fields(text: str) -> dict:
    """从简历文本抽取结构化档案字段（§10.1 子集：必填 + 意向 + 教育/技能）。"""

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    phone = None
    if m := _PHONE_RE.search(text):
        phone = m.group(0)
    email = None
    if m := _EMAIL_RE.search(text):
        email = m.group(0)

    name = None
    for ln in lines[:10]:  # 姓名一般在开头若干行（中文名优先，其次英文名）
        if m := _NAME_RE.match(ln):
            name = m.group(1)
            break
        if m := _LATIN_NAME_RE.match(ln):
            name = m.group(1)
            break

    expected_city = None
    if m := _CITY_RE.search(text):
        expected_city = m.group(1).strip(" ，,。") or None
    expected_position = None
    if m := _POSITION_RE.search(text):
        expected_position = m.group(1).strip(" ，,。") or None

    educations = [
        {"school": m.group(1), "degree": _DEGREE_MAP.get(m.group(2) or "") or None}
        for m in _EDU_RE.finditer(text)
    ][:5]

    skills: list[str] = []
    if m := _SKILL_LINE_RE.search(text):
        skills = [s.strip() for s in re.split(r"[,，、/|]", m.group(1)) if s.strip()][:20]

    return {
        "name": name,
        "phone": phone,
        "email": email,
        "educations": educations,
        "experiences": [],
        "skills": skills,
        "awards": [],
        "expected_city": expected_city,
        "expected_position": expected_position,
    }


def missing_required(fields: dict) -> list[str]:
    return [f for f in REQUIRED_FIELDS if not fields.get(f)]


def parse_resume(pdf_bytes: bytes, settings: Settings) -> tuple[str, dict, list[str], str | None]:
    """解析入口：返回 (parse_status, fields, missing_fields, parse_error)。

    - 未配置 LLM Key：parse_status=解析失败, parse_error=未配置 API Key
    - PDF 提取失败：parse_status=解析失败
    - LLM 成功且校验通过：按必填字段计算缺失状态
    - LLM 异常：降级到规则解析，再计算缺失状态
    """

    try:
        config = load_config_from_settings(settings)
    except LLMError as exc:
        return "解析失败", {}, list(REQUIRED_FIELDS), str(exc)
    if config is None:
        return "解析失败", {}, list(REQUIRED_FIELDS), "未配置 API Key"

    try:
        text = extract_text(pdf_bytes)
    except ParseFailure as exc:
        return "解析失败", {}, list(REQUIRED_FIELDS), str(exc)

    try:
        fields = call_llm(text, config)
    except LLMError:
        fields = parse_fields(text)

    missing = missing_required(fields)
    status = "解析完成" if not missing else "部分字段缺失"
    return status, fields, missing, None


def load_config_from_settings(settings: Settings) -> LLMConfig | None:
    """基于 Settings 从数据库加载 LLM 配置（不直接依赖 get_settings 便于测试）。"""

    from app.db import session_for

    with session_for(settings.data_dir) as session:
        return load_config(session)
