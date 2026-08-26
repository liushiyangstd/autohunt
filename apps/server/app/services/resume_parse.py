"""简历 PDF 解析（FR-2，M3）：pypdf 提取文本 + 规则抽取 §10.1 结构化字段。

规则实现的定位：MVP 够用即可——必填字段（姓名/电话/邮箱）缺失走
「部分字段缺失」标记（AC-1），用户进 D-03 手动补全；解析整体失败返回
「解析失败」不阻塞上传（§12）。
"""

from __future__ import annotations

import io
import re

from pypdf import PdfReader

REQUIRED_FIELDS = ("name", "phone", "email")

_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_NAME_RE = re.compile(r"^(?:姓名[:：]\s*)?([一-龥]{2,4})(?:\s*(?:男|女))?$")
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
    for ln in lines[:10]:  # 姓名一般在开头若干行
        if m := _NAME_RE.match(ln):
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


def parse_resume(pdf_bytes: bytes) -> tuple[str, dict, list[str], str | None]:
    """解析入口：返回 (parse_status, fields, missing_fields, parse_error)。

    - 解析完成：必填字段齐全
    - 部分字段缺失：必填字段有缺（AC-1 缺失标记）
    - 解析失败：无法提取文本（fields 为空，回退 D-03 手动编辑）
    """

    try:
        text = extract_text(pdf_bytes)
    except ParseFailure as exc:
        return "解析失败", {}, list(REQUIRED_FIELDS), str(exc)
    fields = parse_fields(text)
    missing = missing_required(fields)
    status = "解析完成" if not missing else "部分字段缺失"
    return status, fields, missing, None
