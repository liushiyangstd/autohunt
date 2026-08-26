"""邮件识别 pipeline（FR-41，技设 §6；BR-2：识别结果一律先进待确认）。

规则实现（MVP；LLM provider 接口预留——`extract` 即未来 EventExtractor 抽象面）：
1. 粗筛：发件人/主题/正文命中招聘关键词才处理，否则跳过（不入库，RISK-3 最小留存）；
2. 解析：类型分类（拒信/offer/面试/笔试/测评）+ 中文时间归一化 + 会议链接/地点抽取；
3. 关联：公司名对 job 表子串模糊匹配，未命中 matched_job_id=NULL（用户确认时手动关联）；
4. 去重：Message-ID 唯一 + 内容哈希兜底；
5. 产出 email_event(待确认) + 原始 EML 落盘 data/mail/。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime, parseaddr
from pathlib import Path

from sqlmodel import Session, select

from autohunt_domain.models import EmailEvent, Job, naive_utc, utcnow
from app.security import sha256

# ---------- 1. 粗筛与类型词表（中英文） ----------

RELATED_KEYWORDS = (
    "笔试", "面试", "测评", "offer", "拒信", "感谢信", "录用", "网测", "在线测评",
    "投递", "简历", "秋招", "校招", "招聘",
    "interview", "assessment", "written test", "online test", "offer", "rejection",
)

# 判定顺序即优先级：拒信 > offer > 面试 > 笔试 > 测评
_TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("拒信", ("拒信", "感谢信", "很遗憾", "未通过", "未能通过", "rejection", "regret", "unfortunately")),
    ("offer", ("offer", "录用", "录取通知")),
    ("面试", ("面试", "interview", "约面")),
    ("笔试", ("笔试", "written test", "在线笔试")),
    ("测评", ("测评", "网测", "在线测评", "assessment", "online test")),
]

# ---------- 2. 时间 / 链接 / 地点抽取 ----------

_FULL_DT_RE = re.compile(
    r"(?P<y>20\d{2})\s*[-/年.]\s*(?P<mo>\d{1,2})\s*[-/月.]\s*(?P<d>\d{1,2})\s*[日号]?"
    r"[\sT]*(?P<h>\d{1,2})\s*[:：点]\s*(?P<mi>\d{1,2})?"
)
_CN_DT_RE = re.compile(
    r"(?P<mo>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*[日号]?\s*(?:上午|下午|晚上)?\s*"
    r"(?P<h>\d{1,2})\s*[:：点]\s*(?P<mi>\d{1,2})?"
)
_NEXT_WEEK_RE = re.compile(r"下周(?P<w>[一二三四五六日天])")
_WEEKDAY_MAP = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}

_MEETING_LINK_RE = re.compile(
    r"https?://(?:[\w-]+\.)*(?:meeting\.tencent\.com|zoom\.us|nowcoder\.com|"
    r"meeting\.feishu\.cn|teams\.microsoft\.com|webex\.com)[^\s<>\"')，。]*",
    re.IGNORECASE,
)
_LOCATION_RE = re.compile(r"(?:地点|地址|面试地点|笔试地点)[:：]\s*([^\n，。；]{2,60})")


def _decode_str(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(make_header(decode_header(value)))
    except Exception:  # noqa: BLE001
        return value


def _body_text(msg: Message) -> str:
    """提取正文文本（text/plain 优先，text/html 退化为去标签文本）。"""

    parts: list[str] = []
    candidates = [p for p in msg.walk() if p.get_content_type() == "text/plain"]
    if not candidates:
        candidates = [p for p in msg.walk() if p.get_content_type() == "text/html"]
    for part in candidates:
        try:
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            parts.append(payload.decode(charset, errors="replace"))
        except Exception:  # noqa: BLE001
            continue
    text = "\n".join(parts)
    if "<" in text:
        text = re.sub(r"<[^>]+>", " ", text)
    return text


def _parse_time(text: str, received_at: datetime) -> datetime | None:
    if m := _FULL_DT_RE.search(text):
        try:
            return datetime(
                int(m["y"]), int(m["mo"]), int(m["d"]),
                int(m["h"]), int(m["mi"] or 0),
            )
        except ValueError:
            pass
    if m := _CN_DT_RE.search(text):
        # 中文日期无年份：以收件日期为锚推断；早于收件 30 天以上视为明年
        try:
            candidate = datetime(
                received_at.year, int(m["mo"]), int(m["d"]),
                int(m["h"]), int(m["mi"] or 0),
            )
            if candidate < received_at - timedelta(days=30):
                candidate = candidate.replace(year=candidate.year + 1)
            return candidate
        except ValueError:
            pass
    if m := _NEXT_WEEK_RE.search(text):
        target = _WEEKDAY_MAP[m["w"]]
        days_ahead = (target - received_at.weekday()) % 7 + 7
        return (received_at + timedelta(days=days_ahead)).replace(
            hour=14, minute=0, second=0, microsecond=0
        )
    return None


def _classify(text: str) -> str | None:
    lowered = text.lower()
    for event_type, keywords in _TYPE_KEYWORDS:
        if any(kw.lower() in lowered for kw in keywords):
            return event_type
    return None


def is_recruitment_related(subject: str, sender: str, body: str) -> bool:
    haystack = f"{subject}\n{sender}\n{body[:2000]}".lower()
    return any(kw.lower() in haystack for kw in RELATED_KEYWORDS)


def process_message(
    session: Session,
    data_dir: Path,
    account_id: str,
    raw: bytes,
    msg: Message | None = None,
) -> EmailEvent | None:
    """识别一封原始邮件；命中则落 email_event(待确认) + EML 存档，否则返回 None。

    幂等：Message-ID / 内容哈希命中既有事件时跳过（返回 None）。
    """

    import email as _email_mod

    msg = msg or _email_mod.message_from_bytes(raw)
    subject = _decode_str(msg.get("Subject")) or ""
    sender = parseaddr(_decode_str(msg.get("From")) or "")[1] or (msg.get("From") or "")
    message_id = (msg.get("Message-ID") or "").strip()
    body = _body_text(msg)

    try:
        received_at = naive_utc(parsedate_to_datetime(msg.get("Date")))
    except Exception:  # noqa: BLE001
        received_at = utcnow().replace(tzinfo=None)

    # 1. 粗筛：非招聘相关直接跳过（不入库）
    if not is_recruitment_related(subject, sender, body):
        return None

    # 4. 去重：Message-ID 唯一 + 内容哈希兜底
    content_hash = sha256(f"{subject}|{sender}|{body[:4000]}")
    if message_id:
        if session.exec(select(EmailEvent).where(EmailEvent.message_id == message_id)).first():
            return None
    else:
        message_id = f"nohash-{content_hash}"
    if session.exec(
        select(EmailEvent)
        .where(EmailEvent.account_id == account_id, EmailEvent.content_hash == content_hash)
    ).first():
        return None

    # 2. 解析：类型 / 时间 / 链接 / 地点
    full_text = f"{subject}\n{body}"
    event_type = _classify(full_text)
    if event_type is None:
        return None  # 粗筛过但无法归类：不入库（避免噪音事件）
    event_time = _parse_time(full_text, received_at)
    meeting_link = None
    if m := _MEETING_LINK_RE.search(full_text):
        meeting_link = m.group(0)
    location = None
    if m := _LOCATION_RE.search(full_text):
        location = m.group(1).strip()
    if location is None and meeting_link is not None:
        location = "线上"

    # 3. 关联：公司名对 job 表子串模糊匹配（识别公司名：主题/正文中出现的已知公司）
    company = None
    matched_job_id = None
    for job in session.exec(select(Job)).all():
        if job.company and job.company in full_text:
            company = job.company
            matched_job_id = job.id
            break

    # 5. 产出事件 + EML 落盘 data/mail/
    event = EmailEvent(
        account_id=account_id,
        message_id=message_id,
        content_hash=content_hash,
        type=event_type,
        event_time=event_time,
        location=location,
        meeting_link=meeting_link,
        company=company,
        matched_job_id=matched_job_id,
        email_subject=subject,
        email_sender=sender,
        email_received_at=received_at,
        status="待确认",
    )
    session.add(event)
    session.flush()  # 取 event.id 供存档文件名

    mail_dir = Path(data_dir) / "mail"
    mail_dir.mkdir(parents=True, exist_ok=True)
    raw_path = mail_dir / f"{event.id}.eml"
    raw_path.write_bytes(raw)
    event.raw_path = str(raw_path.relative_to(data_dir))
    session.add(event)
    session.commit()
    session.refresh(event)
    return event
