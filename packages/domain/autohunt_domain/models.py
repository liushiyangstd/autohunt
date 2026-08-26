"""SQLModel 表定义（技术设计 v1.1 §4，10 张表 + status_history 的 rejected 标记）。

约定：
- 对外暴露的 `id` 为 uuid4 字符串；`seq` 自增主键仅用于 cursor 分页（keyset）。
- 时间一律 UTC 存储（RFC3339 在 API 边界序列化）。
- JSON 列存列表/字典（SQLite 无需 join）。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def new_id() -> str:
    return uuid.uuid4().hex


_now_override: datetime | None = None


def set_clock_override(dt: datetime | None) -> None:
    """测试钩子（§17 ③）：覆盖全局「现在」，传 None 恢复真实时钟。仅测试环境调用。"""

    global _now_override
    _now_override = dt


def utcnow() -> datetime:
    if _now_override is not None:
        return _now_override
    return datetime.now(timezone.utc)


def naive_utc(dt: datetime) -> datetime:
    """带时区的 RFC3339 输入统一转 naive UTC（SQLite 按字符串比较，混排会错序）。"""

    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


class Resume(SQLModel, table=True):
    __tablename__ = "resume"

    seq: int | None = Field(default=None, primary_key=True)
    id: str = Field(default_factory=new_id, unique=True, index=True)
    name: str
    file_path: str
    is_default: bool = False
    version: int = 1
    # 解析状态机（§3.7，AC-1）：解析中/解析完成/部分字段缺失/解析失败
    parse_status: str = "解析中"
    missing_fields: list = Field(default_factory=list, sa_column=Column(JSON))
    parse_error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Profile(SQLModel, table=True):
    __tablename__ = "profile"

    seq: int | None = Field(default=None, primary_key=True)
    id: str = Field(default_factory=new_id, unique=True, index=True)
    resume_id: str = Field(foreign_key="resume.id", index=True)
    resume_version: int = 1
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    educations: list = Field(default_factory=list, sa_column=Column(JSON))
    experiences: list = Field(default_factory=list, sa_column=Column(JSON))
    skills: list = Field(default_factory=list, sa_column=Column(JSON))
    awards: list = Field(default_factory=list, sa_column=Column(JSON))
    expected_city: str | None = None
    expected_position: str | None = None


class Job(SQLModel, table=True):
    __tablename__ = "job"

    seq: int | None = Field(default=None, primary_key=True)
    id: str = Field(default_factory=new_id, unique=True, index=True)
    company: str = Field(index=True)  # company+title 供 BR-3 重复提示
    title: str = Field(index=True)
    jd_url: str | None = None
    location: str | None = None
    channel: str | None = None
    deadline: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Application(SQLModel, table=True):
    __tablename__ = "application"

    seq: int | None = Field(default=None, primary_key=True)
    id: str = Field(default_factory=new_id, unique=True, index=True)
    job_id: str = Field(foreign_key="job.id", index=True)
    resume_id: str
    applied_at: datetime | None = None
    status: str = "待投递"
    interview_round: int | None = None
    note: str | None = None
    created_at: datetime = Field(default_factory=utcnow)  # 统计 from/to 按创建时间（FR-51）


class StatusHistory(SQLModel, table=True):
    __tablename__ = "status_history"

    seq: int | None = Field(default=None, primary_key=True)
    id: str = Field(default_factory=new_id, unique=True, index=True)
    application_id: str = Field(foreign_key="application.id", index=True)
    from_status: str | None = None
    to_status: str
    source: str  # ui / email / agent
    rejected: bool = False  # 被状态机拒绝的自动写入也落一条标记（§5，AC-6 排查）
    created_at: datetime = Field(default_factory=utcnow)


class Confirmation(SQLModel, table=True):
    __tablename__ = "confirmation"

    seq: int | None = Field(default=None, primary_key=True)
    id: str = Field(default_factory=new_id, unique=True, index=True)
    application_id: str = Field(foreign_key="application.id", index=True)
    request_id: str = Field(unique=True, index=True)  # Agent 幂等键（AC-3）
    fields: dict = Field(default_factory=dict, sa_column=Column(JSON))
    context: dict | None = Field(default=None, sa_column=Column(JSON))
    status: str = "待确认"
    reason: str | None = None
    confirmed_fields: dict | None = Field(default=None, sa_column=Column(JSON))
    confirmed_at: datetime | None = None
    # submit_token 需经 GET 返回给 Agent（§3.4 步骤 3），无法只存哈希 —— 存 Fernet 密文；
    # fields_hash 为 confirmed_fields 的绑定哈希，校验时重算比对（篡改即 PERMIT_INVALID）。
    fields_hash: str | None = None
    submit_token_enc: str | None = None
    token_expires_at: datetime | None = None
    token_consumed: bool = False
    submit_result: str | None = None  # success / failed
    fail_reason: str | None = None
    submitted_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class EmailAccount(SQLModel, table=True):
    __tablename__ = "email_account"

    seq: int | None = Field(default=None, primary_key=True)
    id: str = Field(default_factory=new_id, unique=True, index=True)
    email: str
    imap_host: str
    port: int = 993
    auth_code_enc: str
    status: str = "active"  # active / auth_failed
    last_uid: int = 0
    last_sync_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class EmailEvent(SQLModel, table=True):
    __tablename__ = "email_event"

    seq: int | None = Field(default=None, primary_key=True)
    id: str = Field(default_factory=new_id, unique=True, index=True)
    account_id: str = Field(foreign_key="email_account.id", index=True)
    message_id: str = Field(unique=True, index=True)
    content_hash: str | None = Field(default=None, index=True)  # 去重兜底（§6 步骤 4）
    type: str  # 测评/笔试/面试/offer/拒信
    event_time: datetime | None = None
    location: str | None = None
    meeting_link: str | None = None
    company: str | None = None
    matched_job_id: str | None = None
    raw_path: str | None = None
    # 证据区元数据（§3.7，RISK-5 可回溯）
    email_subject: str | None = None
    email_sender: str | None = None
    email_received_at: datetime | None = None
    discard_reason: str | None = None  # 误识别反馈留存（KPI-2 数据源）
    status: str = "待确认"  # 待确认/已确认/已丢弃
    created_at: datetime = Field(default_factory=utcnow)


class ScheduleEvent(SQLModel, table=True):
    __tablename__ = "schedule_event"

    seq: int | None = Field(default=None, primary_key=True)
    id: str = Field(default_factory=new_id, unique=True, index=True)
    application_id: str | None = Field(default=None, foreign_key="application.id")
    source_event_id: str | None = Field(default=None, foreign_key="email_event.id")
    title: str
    type: str
    start_time: datetime
    end_time: datetime | None = None
    location: str | None = None
    meeting_link: str | None = None


class Notification(SQLModel, table=True):
    __tablename__ = "notification"

    seq: int | None = Field(default=None, primary_key=True)
    id: str = Field(default_factory=new_id, unique=True, index=True)
    schedule_event_id: str = Field(foreign_key="schedule_event.id", index=True)
    kind: str  # 24h / 1h
    fire_at: datetime
    status: str = "待触发"  # 待触发/已触发


class ApiKey(SQLModel, table=True):
    __tablename__ = "api_key"

    seq: int | None = Field(default=None, primary_key=True)
    id: str = Field(default_factory=new_id, unique=True, index=True)
    name: str
    key_hash: str = Field(unique=True, index=True)
    prefix: str
    created_at: datetime = Field(default_factory=utcnow)
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None


class AppSetting(SQLModel, table=True):
    """应用设置 KV（契约 v2 修订：提醒偏好等 D-10 持久化，替代前端 localStorage 过渡态）。"""

    __tablename__ = "app_setting"

    seq: int | None = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    value: dict = Field(default_factory=dict, sa_column=Column(JSON))
