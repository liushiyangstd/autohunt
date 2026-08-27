"""Agent 表单读取与自动填充（MVP）。

当前实现基于结构化档案生成常见网申字段值，不实际打开浏览器（第一期先跑通
「一键投递 → 字段预览 → 用户确认 → Agent 提交」的闭环）。后续可在此模块接入
Playwright/CDP 读取目标页面真实字段，再与 profile 做映射。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.schemas import ProfileBase

FieldConfidence = Literal["high", "medium", "low"]

REQUIRED_FIELDS = {"姓名", "电话", "邮箱", "学校", "专业"}


@dataclass
class FieldMeta:
    """字段级元数据，供 UI 高亮不一致 / 低置信度 / 必填缺失。"""

    source: str
    confidence: FieldConfidence
    required: bool
    missing: bool


def _first_edu(profile: ProfileBase):
    return profile.educations[0] if profile.educations else None


def _first_exp(profile: ProfileBase):
    return profile.experiences[0] if profile.experiences else None


def _format_date_range(start: str | None, end: str | None) -> str:
    if start and end:
        return f"{start} 至 {end}"
    return start or end or ""


def build_snapshot(
    profile: ProfileBase, target_url: str | None = None
) -> tuple[dict[str, str], dict[str, FieldMeta]]:
    """基于结构化档案生成字段快照与元数据。

    返回 (fields, meta)。fields 的 key 使用中文字段名，与现有确认流 D-06 对照表对齐。
    """

    edu = _first_edu(profile)
    exp = _first_exp(profile)

    raw: list[tuple[str, str, str]] = [
        ("姓名", profile.name or "", "结构化档案·基本信息"),
        ("电话", profile.phone or "", "结构化档案·基本信息"),
        ("邮箱", profile.email or "", "结构化档案·基本信息"),
        ("学校", edu.school if edu else "", "结构化档案·教育经历"),
        ("专业", edu.major if edu else "", "结构化档案·教育经历"),
        ("学历", edu.degree if edu else "", "结构化档案·教育经历"),
        ("教育起止时间", _format_date_range(edu.start_date if edu else None, edu.end_date if edu else None), "结构化档案·教育经历"),
        ("最近公司", exp.company if exp else "", "结构化档案·工作经历"),
        ("最近岗位", exp.position if exp else "", "结构化档案·工作经历"),
        ("期望城市", profile.expected_city or "", "结构化档案·求职意向"),
        ("期望岗位", profile.expected_position or "", "结构化档案·求职意向"),
        ("技能", "、".join(profile.skills), "结构化档案·技能"),
        ("奖项", "、".join(profile.awards), "结构化档案·奖项"),
    ]

    fields: dict[str, str] = {}
    meta: dict[str, FieldMeta] = {}

    for label, value, source in raw:
        fields[label] = value
        required = label in REQUIRED_FIELDS
        missing = required and not value.strip()
        if missing:
            confidence: FieldConfidence = "low"
        elif not value.strip():
            confidence = "medium"
        else:
            confidence = "high"
        meta[label] = FieldMeta(
            source=source,
            confidence=confidence,
            required=required,
            missing=missing,
        )

    return fields, meta
