from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

RFC3339 = Annotated[datetime, Field(description="RFC3339 时间戳（UTC 存储）")]


class ErrorCode(str, Enum):
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    PERMIT_REQUIRED = "PERMIT_REQUIRED"
    PERMIT_INVALID = "PERMIT_INVALID"
    STATE_CONFLICT = "STATE_CONFLICT"
    VALIDATION_ERROR = "VALIDATION_ERROR"


class ErrorBody(BaseModel):
    code: ErrorCode
    message: str
    details: dict[str, Any] | None = None


class ErrorEnvelope(BaseModel):
    """统一错误信封（§3 通用约定）。"""

    error: ErrorBody


class ApplicationStatus(str, Enum):
    """BR-10 状态机状态集。主链 rank 递增；未通过/主动放弃/已过期为旁路终止态。"""

    pending = "待投递"
    submitted = "已投递"
    written_test = "笔试"
    interview = "面试"
    offer = "offer"
    accepted = "已接受"
    rejected = "已拒绝"
    failed = "未通过"
    abandoned = "主动放弃"
    expired = "已过期"


class ConfirmationStatus(str, Enum):
    """§10.3 确认流状态。"""

    pending = "待确认"
    confirmed = "已确认"
    rejected = "已驳回"
    closed = "已超时关闭"


class EmailEventType(str, Enum):
    assessment = "测评"
    written_test = "笔试"
    interview = "面试"
    offer = "offer"
    rejection = "拒信"


class EmailEventStatus(str, Enum):
    pending = "待确认"
    confirmed = "已确认"
    discarded = "已丢弃"


class HistorySource(str, Enum):
    ui = "ui"
    email = "email"
    agent = "agent"


# ---------- keys（FR-25，仅 UI session） ----------


class ApiKeyCreate(BaseModel):
    name: str = Field(description="密钥用途备注，便于在列表中识别")


class ApiKeyCreated(BaseModel):
    id: str
    name: str
    key: str = Field(description="完整密钥 ah_live_<random>，仅此一次返回，服务端只存哈希")
    prefix: str
    created_at: RFC3339


class ApiKeyInfo(BaseModel):
    """列表展示用，永不包含完整 key。"""

    id: str
    name: str
    prefix: str
    created_at: RFC3339
    last_used_at: RFC3339 | None = None


# ---------- profile（FR-20，§10.1 字段字典） ----------


class Education(BaseModel):
    school: str
    degree: str | None = None
    major: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class Experience(BaseModel):
    company: str
    position: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None


class Profile(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = Field(
        default=None,
        description="未显式填写时默认回填已绑定求职邮箱；用户修改后以用户值为准（§3.2 注）",
    )
    educations: list[Education] = []
    experiences: list[Experience] = []
    skills: list[str] = []
    awards: list[str] = []
    expected_city: str | None = None
    expected_position: str | None = None
    resume_id: str
    resume_version: int


class ProfileEmpty(BaseModel):
    """无简历时的空态响应（§12，HTTP 200）。"""

    empty: Literal[True] = True


# ---------- jobs / applications（FR-21，§10.2） ----------


class JobCreate(BaseModel):
    company: str
    title: str
    jd_url: str | None = None
    location: str | None = None
    channel: str | None = None
    deadline: RFC3339 | None = None


class JobUpdate(BaseModel):
    company: str | None = None
    title: str | None = None
    jd_url: str | None = None
    location: str | None = None
    channel: str | None = None
    deadline: RFC3339 | None = None


class Job(BaseModel):
    id: str
    company: str
    title: str
    jd_url: str | None = None
    location: str | None = None
    channel: str | None = None
    deadline: RFC3339 | None = None
    created_at: RFC3339


class JobDuplicate(BaseModel):
    """BR-3：同公司同岗位重复创建 → 200 提示不拦截。"""

    duplicate_of: str = Field(description="已存在的 job id")
    job: Job


class JobList(BaseModel):
    items: list[Job]
    next_cursor: str | None = None


class ApplicationCreate(BaseModel):
    job_id: str
    resume_id: str


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = Field(
        default=None,
        description="状态推进经状态机裁决（§5）；Agent 改为「已投递」必须携带 submit_token",
    )
    note: str | None = None
    interview_round: int | None = None
    submit_token: str | None = Field(
        default=None,
        description="Agent 推进「已投递」时必填（亦可用 Permit 头），UI 手动推进不受限（§3.4 步骤 4）",
    )


class Application(BaseModel):
    id: str
    job_id: str
    resume_id: str
    applied_at: RFC3339 | None = None
    status: ApplicationStatus
    interview_round: int | None = None
    note: str | None = None


class ApplicationList(BaseModel):
    items: list[Application]
    next_cursor: str | None = None


# ---------- confirmations（FR-22/23/24 + BR-1，§3.4 核心） ----------


class ConfirmationCreate(BaseModel):
    application_id: str
    request_id: str = Field(description="Agent 侧幂等键；重试返回首个确认单（AC-3）")
    fields: dict[str, str] = Field(description="待确认字段-值快照")
    context: dict[str, str] | None = Field(default=None, description="如 target_url、note")


class ConfirmationCreated(BaseModel):
    """创建响应：不携带任何可提交许可（BR-1）。"""

    confirmation_id: str
    status: Literal[ConfirmationStatus.pending] = ConfirmationStatus.pending


class ConfirmationPending(BaseModel):
    """待确认：除状态外无其他字段。"""

    status: Literal[ConfirmationStatus.pending] = ConfirmationStatus.pending


class ConfirmationClosed(BaseModel):
    """已驳回 / 已超时关闭：流程终止。"""

    status: Literal[ConfirmationStatus.rejected, ConfirmationStatus.closed]
    reason: str | None = None


class ConfirmationConfirmed(BaseModel):
    """已确认：submit_token 仅在此时出现（BR-1 唯一点）；token 过期/已消耗时为 null，走 UI「重新放行」恢复。"""

    status: Literal[ConfirmationStatus.confirmed] = ConfirmationStatus.confirmed
    confirmed_fields: dict[str, str] = Field(description="确认后的字段值（含用户修改）")
    submit_token: str | None = Field(
        description="一次性提交许可：绑定 confirmation_id + confirmed_fields 哈希，TTL 30 分钟；已过期/已消耗时为 null"
    )
    expires_at: RFC3339


ConfirmationDetail = ConfirmationPending | ConfirmationConfirmed | ConfirmationClosed


class ConfirmationConfirm(BaseModel):
    confirmed_fields: dict[str, str] = Field(description="用户核对/修改后的最终字段值")


class ConfirmationReject(BaseModel):
    reason: str | None = None


class SubmitResult(BaseModel):
    submit_token: str
    result: Literal["success", "failed"]
    fail_reason: str | None = Field(default=None, description="result=failed 时必填（FR-24）")
    submitted_at: RFC3339


class SubmitResultAck(BaseModel):
    application_id: str
    status: ApplicationStatus = Field(
        description="success → 已投递（来源=agent）；failed → 状态不变，留待用户人工处置"
    )
    recorded: Literal[True] = True


# ---------- events / schedule（FR-42/43，UI 为主，Agent 只读） ----------


class EmailEvent(BaseModel):
    id: str
    type: EmailEventType
    event_time: RFC3339 | None = None
    location: str | None = None
    meeting_link: str | None = None
    company: str | None = None
    matched_job_id: str | None = None
    status: EmailEventStatus
    created_at: RFC3339


class EmailEventList(BaseModel):
    items: list[EmailEvent]
    next_cursor: str | None = None


class ScheduleEvent(BaseModel):
    id: str
    application_id: str | None = None
    source_event_id: str | None = None
    title: str
    type: EmailEventType
    start_time: RFC3339
    end_time: RFC3339 | None = None
    location: str | None = None
    meeting_link: str | None = None


class ScheduleEventList(BaseModel):
    items: list[ScheduleEvent]
