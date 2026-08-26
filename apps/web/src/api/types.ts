/**
 * 契约类型 — 逐字对应 docs/design/api-openapi.json（契约 v2，info.version 0.2.1 @ adcae45）。
 * 修改契约需走 PR 评审，此处只读对齐。
 */

export type ApplicationStatus =
  | '待投递' | '已投递' | '笔试' | '面试' | 'offer'
  | '已接受' | '已拒绝' | '未通过' | '主动放弃' | '已过期';

export type EmailEventType = '测评' | '笔试' | '面试' | 'offer' | '拒信';
export type EmailEventStatus = '待确认' | '已确认' | '已丢弃';

export type ConfirmationStatus = '待确认' | '已确认' | '已驳回' | '已超时关闭';

export type ErrorCode =
  | 'UNAUTHORIZED' | 'FORBIDDEN' | 'NOT_FOUND'
  | 'PERMIT_REQUIRED' | 'PERMIT_INVALID' | 'STATE_CONFLICT' | 'VALIDATION_ERROR';

export interface ErrorEnvelope {
  error: { code: ErrorCode; message: string; details?: unknown };
}

export interface Education {
  school: string;
  degree?: string | null;
  major?: string | null;
  start_date?: string | null;
  end_date?: string | null;
}

export interface Experience {
  company: string;
  position?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  description?: string | null;
}

export interface Profile {
  name?: string | null;
  phone?: string | null;
  email?: string | null;
  educations: Education[];
  experiences: Experience[];
  skills: string[];
  awards: string[];
  expected_city?: string | null;
  expected_position?: string | null;
  resume_id: string;
  resume_version: number;
}

/** 无简历空态（§12，HTTP 200） */
export interface ProfileEmpty { empty: true }
export type ProfileResponse = Profile | ProfileEmpty;
export function isProfileEmpty(p: ProfileResponse): p is ProfileEmpty {
  return (p as ProfileEmpty).empty === true;
}

export interface Job {
  id: string;
  company: string;
  title: string;
  jd_url?: string | null;
  location?: string | null;
  channel?: string | null;
  deadline?: string | null; // RFC3339 UTC
  created_at: string;
}

export interface JobCreate {
  company: string;
  title: string;
  jd_url?: string | null;
  location?: string | null;
  channel?: string | null;
  deadline?: string | null;
}

export type JobUpdate = Partial<JobCreate>;

/** 重复投递提示（BR-3，HTTP 200） */
export interface JobDuplicate { duplicate_of: string; job: Job }
export type CreateJobResult = { kind: 'created'; job: Job } | { kind: 'duplicate'; duplicateOf: string; job: Job };

export interface JobList { items: Job[]; next_cursor?: string | null }

export interface Application {
  id: string;
  job_id: string;
  resume_id: string;
  applied_at?: string | null;
  status: ApplicationStatus;
  interview_round?: number | null;
  note?: string | null;
}

export interface ApplicationCreate { job_id: string; resume_id: string }

export interface ApplicationUpdate {
  status?: ApplicationStatus | null;
  note?: string | null;
  interview_round?: number | null;
  submit_token?: string | null; // 请求侧 Permit 入参（Agent 推进「已投递」）
}

export interface ApplicationList { items: Application[]; next_cursor?: string | null }

export interface ConfirmationCreate {
  application_id: string;
  request_id: string;
  fields: Record<string, string>;
  context?: Record<string, string> | null;
}

/** 创建响应（201 首次 / 200 幂等命中）——不携带任何可提交许可 */
export interface ConfirmationCreated { confirmation_id: string; status: string }

export interface ConfirmationPending { status: '待确认' }

/** 待确认（UI session 视图，契约 v2）：字段-值快照供 D-06 对照表渲染；Agent Bearer 仅 ConfirmationPending */
export interface ConfirmationPendingUI {
  status: '待确认';
  application_id: string;
  fields: Record<string, string>;
  context?: Record<string, string> | null;
  created_at: string;
}

export interface ConfirmationConfirmed {
  status: '已确认';
  confirmed_fields: Record<string, string>;
  /** token 过期/已消耗时为空 —— 走 UI「重新放行」恢复 */
  submit_token: string | null;
  expires_at: string;
  /** 提交结果回写（FR-24，契约 v2）；未回写为 null */
  submit_result?: 'success' | 'failed' | null;
  fail_reason?: string | null;
  submitted_at?: string | null;
}

export interface ConfirmationClosed {
  status: '已驳回' | '已超时关闭';
  reason?: string | null;
}

export type ConfirmationView = ConfirmationPending | ConfirmationPendingUI | ConfirmationConfirmed | ConfirmationClosed;

/** 手动关闭请求体（契约 v2，可选）：待确认 → 已超时关闭 */
export interface ConfirmationClose { reason?: string | null }

/** 确认单摘要（契约 v2 列表端点，D-01 待确认分组/红点数据源） */
export interface ConfirmationListItem {
  id: string;
  application_id: string;
  status: ConfirmationStatus;
  created_at: string;
  confirmed_at?: string | null;
  submit_result?: 'success' | 'failed' | null;
}
export interface ConfirmationList { items: ConfirmationListItem[]; next_cursor?: string | null }

export interface ConfirmationConfirm { confirmed_fields: Record<string, string> }
export interface ConfirmationReject { reason?: string | null }

export type SubmitResultOutcome = 'success' | 'failed';
export interface SubmitResult {
  submit_token: string;
  result: SubmitResultOutcome;
  fail_reason?: string | null;
  submitted_at: string;
}
export interface SubmitResultAck { application_id: string; status: ApplicationStatus; recorded: boolean }

export interface EmailEvent {
  id: string;
  type: EmailEventType;
  event_time?: string | null;
  location?: string | null;
  meeting_link?: string | null;
  company?: string | null;
  matched_job_id?: string | null;
  status: EmailEventStatus;
  created_at: string;
}
export interface EmailEventList { items: EmailEvent[]; next_cursor?: string | null }

export interface ScheduleEvent {
  id: string;
  application_id?: string | null;
  source_event_id?: string | null;
  title: string;
  type: EmailEventType;
  start_time: string;
  end_time?: string | null;
  location?: string | null;
  meeting_link?: string | null;
}
export interface ScheduleEventList { items: ScheduleEvent[] }

export interface ApiKeyCreate { name: string }
export interface ApiKeyCreated { id: string; name: string; key: string; prefix: string; created_at: string }
export interface ApiKeyInfo { id: string; name: string; prefix: string; created_at: string; last_used_at?: string | null }

// ---- 契约 v2：D-05 读侧 ----

export type HistorySource = 'ui' | 'email' | 'agent';

/** 状态历史（FR-31，D-05 状态历史 Tab） */
export interface StatusHistoryEntry {
  from_status?: ApplicationStatus | null;
  to_status: ApplicationStatus;
  source: HistorySource;
  /** 被状态机拒绝的自动写入标记（§5，AC-6 排查） */
  rejected: boolean;
  created_at: string;
}
export interface StatusHistoryList { items: StatusHistoryEntry[] }

/** 投递关联的确认单记录（FR-24，D-05 确认记录 Tab） */
export interface ConfirmationRecord {
  id: string;
  status: ConfirmationStatus;
  created_at: string;
  confirmed_at?: string | null;
  submit_result?: 'success' | 'failed' | null;
  fail_reason?: string | null;
  submitted_at?: string | null;
}
export interface ConfirmationRecordList { items: ConfirmationRecord[] }

/** 事件详情 = 列表字段 + 证据区元数据（D-07，RISK-5） */
export interface EmailEventDetail extends EmailEvent {
  email_subject?: string | null;
  email_sender?: string | null;
  email_received_at?: string | null;
}
export interface EmailEventDetailList { items: EmailEventDetail[] }

// ---- 契约 v2：事件写侧（D-07） ----

/** 确认加入日程；任一字段均可修正（修正后加入 = 确认值取修改后值） */
export interface EmailEventConfirm {
  type?: EmailEventType | null;
  event_time?: string | null;
  location?: string | null;
  meeting_link?: string | null;
  company?: string | null;
  matched_job_id?: string | null;
}
export interface EmailEventConfirmResult { event: EmailEvent; schedule_event: ScheduleEvent }
export interface EmailEventDiscard { reason?: string | null }

// ---- 契约 v2：简历（D-02，FR-1/2/3） ----

export type ResumeParseStatus = '解析中' | '解析完成' | '部分字段缺失' | '解析失败';

export interface ResumeInfo {
  id: string;
  name: string;
  version: number;
  is_default: boolean;
  parse_status: ResumeParseStatus;
  missing_fields: string[];
  parse_error?: string | null;
  /** 引用本版本的投递数（FR-3 回溯；>0 时禁止删除） */
  used_count: number;
  created_at: string;
}
export interface ResumeList { items: ResumeInfo[] }
export interface ResumeUpdate { name?: string | null; is_default?: boolean | null }

/** 档案写（FR-2/3，D-03 显式保存）：全量替换指定简历版本 */
export interface ProfileUpdate {
  resume_id: string;
  name?: string | null;
  phone?: string | null;
  /** 传 null/省略时按 §3.2 默认回填已绑定求职邮箱 */
  email?: string | null;
  educations: Education[];
  experiences: Experience[];
  skills: string[];
  awards: string[];
  expected_city?: string | null;
  expected_position?: string | null;
}

// ---- 契约 v2：邮箱账户（D-10，FR-40/44） ----

export type EmailAccountStatus = 'active' | 'auth_failed';

export interface EmailAccountBind {
  email: string;
  imap_host: string;
  port?: number;
  /** IMAP 授权码（OP-4）；服务端加密落盘，任何响应不回传 */
  auth_code: string;
}
export interface EmailAccountInfo {
  id: string;
  email: string;
  imap_host: string;
  port: number;
  status: EmailAccountStatus;
  last_sync_at?: string | null;
  created_at: string;
}
export interface EmailAccountList { items: EmailAccountInfo[] }
export interface EmailAccountTestResult { ok: boolean; error?: string | null }
export interface EmailAccountReauth { auth_code: string }

// ---- 契约 v2：通知（FR-32） ----

export type NotificationKind = '24h' | '1h' | 'deadline';
export interface Notification {
  id: string;
  kind: NotificationKind;
  title: string;
  message?: string | null;
  fire_at: string;
  schedule_event_id?: string | null;
  application_id?: string | null;
}
export interface NotificationList { items: Notification[]; next_cursor?: string | null }

// ---- 契约 v2：统计（FR-50/51/52，口径 §10.4） ----

export interface StatsOverview {
  total_applications: number;
  in_progress: number;
  /** 待确认事项数 = 待确认投递数 + 待确认事件数（D-01 导航红点同口径） */
  pending_items: number;
  offers: number;
}

export interface StatsFunnelStage {
  stage: ApplicationStatus;
  /** 进入过该状态的投递数：status_history 出现该状态或主链更后状态（去重） */
  entered_count: number;
}
export interface StatsFunnelConversions {
  written_test_rate: number | null;
  interview_rate: number | null;
  offer_rate: number | null;
}
export interface StatsFunnel { stages: StatsFunnelStage[]; conversions: StatsFunnelConversions }

export interface StatsFilter { channel?: string; from?: string; to?: string }

// ---- 契约 v2：提醒偏好（FR-32，D-10） ----

export interface ReminderSettings {
  schedule_24h: boolean;
  schedule_1h: boolean;
  include_deadline: boolean;
}

// ---- 契约 v2 增补：LLM 解析配置（PROX-8/PROX-12） ----

export interface LLMConfig {
  enabled: boolean;
  provider: string;
  base_url?: string | null;
  model: string;
  api_key_last4?: string | null;
  timeout_seconds: number;
  max_tokens: number;
}

export interface LLMConfigUpdate {
  enabled?: boolean | null;
  provider?: string | null;
  base_url?: string | null;
  model?: string | null;
  api_key?: string | null;
  timeout_seconds?: number | null;
  max_tokens?: number | null;
}

export interface LLMConfigTestResult {
  ok: boolean;
  error?: string | null;
}
