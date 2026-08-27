"""结构化站点解析（PROX-19 技设 §4.3）：BOSS 直聘 + 牛客两个 P0 适配器。

- 站点规则以函数表注册（RISK-1：便于版本化与增量新增）；本任务只注册 boss/nowcoder。
- 扩展已传 extracted 时走 normalize_extracted 校验归一化，不再拉取页面。
- deadline 允许 date-only 输入，归一化为当天 23:59:59 UTC（技设 §3.3）。
"""

from __future__ import annotations

import re
from datetime import datetime, time as dt_time, timezone

from app.schemas import CrawlExtracted

_TAG_RE = re.compile(r"<[^>]+>")
_SALARY_RE = re.compile(r"\d+[Kk]?[-~]\d+(?:[Kk元])?")
_DEGREE_RE = re.compile(r"(博士|硕士|MBA|本科|大专|学历不限)")
_EXP_RE = re.compile(r"(\d+[-~]\d+年|\d+年以上|经验不限|应届)")
_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ParseError(Exception):
    """结构化解析未得到任何有效字段。"""


def _clean(html_fragment: str) -> str:
    return _TAG_RE.sub("", html_fragment).strip()


def _first(pattern: str, html: str, flags: int = re.DOTALL) -> str | None:
    m = re.search(pattern, html, flags)
    return _clean(m.group(1)) if m else None


def _parse_boss(_url: str, html: str) -> dict:
    """BOSS 直聘职位页：job-primary（标题/薪资/地点经验学历）+ company-info + job-sec-text。"""

    title = _first(r"<h1[^>]*>(.*?)</h1>", html)
    salary = _first(r'class="salary"[^>]*>(.*?)<', html)
    company = _first(r'class="company-info".*?class="name"[^>]*>(.*?)<', html)
    info = _first(r'class="job-primary-detail"[^>]*>(.*?)</p>', html) or _first(
        r'<p[^>]*class="[^"]*job-tag[^"]*"[^>]*>(.*?)</p>', html
    )
    description = _first(r'class="job-sec-text"[^>]*>(.*?)</div>', html) or _first(
        r'class="job-detail[^"]*"[^>]*>(.*?)</div>', html
    )

    location = degree = experience = None
    if info:
        tokens = [t for t in re.split(r"[·\s]+", info) if t]
        for tok in tokens:
            if _DEGREE_RE.fullmatch(tok):
                degree = tok
            elif _EXP_RE.fullmatch(tok):
                experience = tok
            elif location is None:
                location = tok

    requirements = {
        k: v for k, v in {"degree": degree, "experience": experience, "salary": salary}.items() if v
    }
    return {
        "company": company,
        "title": title,
        "location": location,
        "description": description,
        "requirements": requirements or None,
    }


def _parse_nowcoder(_url: str, html: str) -> dict:
    """牛客职位页：job-title / job-company / job-info（地点·学历·薪资）/ job-content。"""

    title = _first(r'class="job-title"[^>]*>(.*?)<', html)
    company = _first(r'class="job-company"[^>]*>(.*?)<', html)
    info_html = None
    m = re.search(r'class="job-info"[^>]*>(.*?)</div>', html, re.DOTALL)
    if m:
        info_html = m.group(1)
    description = _first(r'class="job-content"[^>]*>(.*?)</div>', html)

    location = degree = salary = None
    if info_html:
        spans = [_clean(s) for s in re.findall(r"<span[^>]*>(.*?)</span>", info_html, re.DOTALL)]
        for tok in spans:
            if _SALARY_RE.search(tok):
                salary = tok
            elif _DEGREE_RE.fullmatch(tok):
                degree = tok
            elif location is None:
                location = tok

    requirements = {
        k: v for k, v in {"degree": degree, "salary": salary}.items() if v
    }
    return {
        "company": company,
        "title": title,
        "location": location,
        "description": description,
        "requirements": requirements or None,
    }


PARSERS = {
    "boss": _parse_boss,
    "nowcoder": _parse_nowcoder,
}


def parse_structured(source: str, url: str, html: str) -> dict:
    """按站点规则抽取字段；无适配器或零产出抛 ParseError。"""

    parser = PARSERS.get(source)
    if parser is None:
        raise ParseError(f"未注册站点适配器：{source}")
    fields = parser(url, html)
    if not fields.get("company") and not fields.get("title"):
        raise ParseError(f"结构化解析未得到公司/岗位名（站点 DOM 可能已变更，RISK-1）：{source}")
    return fields


def normalize_deadline(value: str | None) -> datetime | None:
    """deadline 归一化：date-only → 当天 23:59:59 UTC；RFC3339 原样解析（技设 §3.3）。"""

    if not value:
        return None
    value = value.strip()
    if _DATE_ONLY_RE.fullmatch(value):
        day = datetime.fromisoformat(value).date()
        return datetime.combine(day, dt_time(23, 59, 59), tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def normalize_extracted(extracted: CrawlExtracted) -> dict:
    """扩展预提取字段校验归一化（技设 §4.3：不再拉取页面）。"""

    requirements = dict(extracted.requirements or {})
    if extracted.salary and "salary" not in requirements:
        requirements["salary"] = extracted.salary
    return {
        "company": extracted.company.strip() if extracted.company else None,
        "title": extracted.title.strip() if extracted.title else None,
        "location": extracted.location,
        "deadline": normalize_deadline(extracted.deadline),
        "description": extracted.description or extracted.content,
        "requirements": requirements or None,
    }
