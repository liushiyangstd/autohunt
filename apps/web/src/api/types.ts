/**
 * 契约类型 — 逐字对应 docs/design/api-openapi.json (8dfc641)。
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

export interface ConfirmationConfirmed {
  status: '已确认';
  confirmed_fields: Record<string, string>;
  /** token 过期/已消耗时为空 —— 走 UI「重新放行」恢复 */
  submit_token: string | null;
  expires_at: string;
}

export interface ConfirmationClosed {
  status: '已驳回' | '已超时关闭';
  reason?: string | null;
}

export type ConfirmationView = ConfirmationPending | ConfirmationConfirmed | ConfirmationClosed;

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

/** 前端内部使用：待确认投递列表项（契约暂无 list 端点，见 api/mock.ts 标注） */
export interface PendingConfirmation {
  confirmation_id: string;
  application_id: string;
  company: string;
  title: string;
  created_at: string;
}
