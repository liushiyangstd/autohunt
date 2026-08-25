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


# ---------- 契约 v2 增补（技设 v1.2 §3.7；全部仅 UI session，事件详情/原文除外） ----------
# 覆盖 M3–M5 写侧：简历上传/版本管理（FR-1/2/3）、档案写（FR-2）、
# 邮箱账户绑定/解绑/状态（FR-40/44）、事件确认/丢弃/修正（FR-42，BR-2）、
# 通知列表（FR-32）、统计与 CSV 导出（FR-50/51/52，口径 §10.4）。


class ResumeParseStatus(str, Enum):
    """D-02 解析状态机；解析失败不阻塞，回退手动编辑（§12，AC-1）。"""

    parsing = "解析中"
    done = "解析完成"
    partial = "部分字段缺失"
    failed = "解析失败"


class ResumeInfo(BaseModel):
    id: str
    name: str = Field(description="版本名，默认「简历 v{n}」，可重命名")
    version: int = Field(description="版本号（即 profile.resume_version）")
    is_default: bool
    parse_status: ResumeParseStatus
    missing_fields: list[str] = Field(default=[], description="解析缺失的必填字段名（AC-1 缺失标记）")
    parse_error: str | None = Field(default=None, description="parse_status=解析失败 时的原因")
    used_count: int = Field(description="引用本版本的投递数（FR-3 回溯；>0 时禁止删除）")
    created_at: RFC3339


class ResumeList(BaseModel):
    items: list[ResumeInfo]


class ResumeUpdate(BaseModel):
    name: str | None = None
    is_default: bool | None = Field(
        default=None, description="传 true 将本版本设为默认简历（其余版本自动取消默认）"
    )


class ProfileUpdate(BaseModel):
    """档案写（FR-2/3，D-03 显式保存）：全量替换指定简历版本的结构化档案。"""

    resume_id: str
    name: str | None = None
    phone: str | None = None
    email: str | None = Field(
        default=None,
        description="传 null/省略时按 §3.2 默认回填已绑定求职邮箱；显式传入后以用户值为准",
    )
    educations: list[Education] = []
    experiences: list[Experience] = []
    skills: list[str] = []
    awards: list[str] = []
    expected_city: str | None = None
    expected_position: str | None = None


class EmailAccountStatus(str, Enum):
    """FR-44：auth_failed 时暂停轮询 + UI 全局警示，历史数据保留。"""

    active = "active"
    auth_failed = "auth_failed"


class EmailAccountBind(BaseModel):
    email: str
    imap_host: str
    port: int = 993
    auth_code: str = Field(description="IMAP 授权码（OP-4）；服务端 Fernet 加密落盘，任何响应不回传")


class EmailAccountInfo(BaseModel):
    """永不包含授权码。"""

    id: str
    email: str
    imap_host: str
    port: int
    status: EmailAccountStatus
    last_sync_at: RFC3339 | None = None
    created_at: RFC3339


class EmailAccountList(BaseModel):
    items: list[EmailAccountInfo]


class EmailAccountTestResult(BaseModel):
    ok: bool
    error: str | None = Field(default=None, description="连接/认证失败原因（D-10 即时反馈）")


class EmailAccountReauth(BaseModel):
    auth_code: str = Field(description="新授权码；验证通过则 status 恢复 active 并续跑轮询（FR-44）")


class EmailEventDetail(EmailEvent):
    """事件详情 = 列表字段 + 证据区元数据（D-07，RISK-5 可回溯）。"""

    email_subject: str | None = None
    email_sender: str | None = None
    email_received_at: RFC3339 | None = None


class EmailEventConfirm(BaseModel):
    """确认加入日程；任一字段均可修正（修正后加入 = 确认值取修改后值，D-07）。"""

    type: EmailEventType | None = None
    event_time: RFC3339 | None = None
    location: str | None = None
    meeting_link: str | None = None
    company: str | None = None
    matched_job_id: str | None = Field(default=None, description="关联投递的岗位；识别未命中时手动关联")


class EmailEventConfirmResult(BaseModel):
    event: EmailEvent
    schedule_event: ScheduleEvent = Field(
        description="确认后生成的日程事件（BR-2）；关联投递按 §5 以 email 来源推进状态"
    )


class EmailEventDiscard(BaseModel):
    reason: str | None = Field(default=None, description="误识别反馈（KPI-2 数据源）")


class NotificationKind(str, Enum):
    schedule_24h = "24h"
    schedule_1h = "1h"
    deadline = "deadline"


class Notification(BaseModel):
    id: str = Field(description="日程提醒为持久 id；网申截止提醒为虚拟 id（deadline:<job_id>，§4 即时计算不落库）")
    kind: NotificationKind
    title: str
    message: str | None = None
    fire_at: RFC3339
    schedule_event_id: str | None = None
    application_id: str | None = Field(default=None, description="网申截止提醒对应的投递")


class NotificationList(BaseModel):
    items: list[Notification]
    next_cursor: str | None = None


class StatsOverview(BaseModel):
    """FR-52 指标卡；筛选参数（channel/from/to）作用于全部指标（FR-51）。"""

    total_applications: int = Field(description="总投递数：状态≠待投递（与 §10.4 漏斗统计范围一致）")
    in_progress: int = Field(description="进行中：状态 ∈ {已投递, 笔试, 面试, offer}")
    pending_items: int = Field(description="待确认事项数 = 待确认投递数 + 待确认事件数（D-01 导航红点同口径）")
    offers: int = Field(description="offer 数：状态 ∈ {offer, 已接受}（OP-10 仅作数量记录）")


class FunnelStage(BaseModel):
    stage: ApplicationStatus
    entered_count: int = Field(
        description="进入过该状态的投递数：status_history 出现该状态或主链更后状态（去重）；待投递不计入漏斗（§10.4）"
    )


class FunnelConversions(BaseModel):
    """§10.4 口径；分母为 0 时对应转化率为 null。"""

    written_test_rate: float | None = Field(description="笔试转化率 = 进入笔试数 / 已投递及以后数")
    interview_rate: float | None = Field(description="面试转化率 = 进入面试数 / 进入笔试数（无笔试环节不剔除）")
    offer_rate: float | None = Field(description="offer 转化率 = 进入 offer 数 / 全部已投递数")


class StatsFunnel(BaseModel):
    stages: list[FunnelStage] = Field(description="固定四级：已投递 → 笔试 → 面试 → offer")
    conversions: FunnelConversions
