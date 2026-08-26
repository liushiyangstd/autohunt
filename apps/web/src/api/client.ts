import type {
  ApiKeyCreate, ApiKeyCreated, ApiKeyInfo,
  Application, ApplicationCreate, ApplicationList, ApplicationUpdate,
  ConfirmationClose, ConfirmationConfirm, ConfirmationConfirmed, ConfirmationCreate, ConfirmationCreated,
  ConfirmationList, ConfirmationRecordList, ConfirmationReject, ConfirmationStatus, ConfirmationView,
  CreateJobResult, EmailAccountBind, EmailAccountInfo, EmailAccountList, EmailAccountReauth,
  EmailAccountTestResult, EmailEventConfirm, EmailEventConfirmResult, EmailEventDetail,
  EmailEventDetailList, EmailEventDiscard, EmailEventList,
  Job, JobCreate, JobList, JobUpdate,
  LLMConfig, LLMConfigTestResult, LLMConfigUpdate,
  NotificationList, Profile, ProfileResponse, ProfileUpdate, ReminderSettings,
  ResumeInfo, ResumeList, ResumeUpdate,
  ScheduleEventList, StatsFilter, StatsFunnel, StatsOverview, StatusHistoryList,
} from './types';

/**
 * 确认单完整视图（D-06 对照表 / FR-24 结果视图数据源）。
 * 契约 v2：GET /confirmations/{id} 按 caller 区分 —— UI session 待确认变体
 * 携带 fields/context 快照（ConfirmationPendingUI）；已确认变体携带
 * submit_result / fail_reason / submitted_at 回写。本类型为各变体的合并视图；
 * application_id 仅待确认变体保证存在，其余变体由调用方从确认单列表补齐。
 */
export interface ConfirmationDetail {
  id: string;
  status: ConfirmationStatus;
  application_id?: string;
  fields?: Record<string, string>;
  context?: Record<string, string> | null;
  created_at?: string;
  confirmed_fields?: Record<string, string>;
  submit_token?: string | null;
  expires_at?: string;
  submit_result?: 'success' | 'failed' | null;
  fail_reason?: string | null;
  submitted_at?: string | null;
  reason?: string | null;
}

/** 统一错误信封解析（契约 §3 通用约定） */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** 数据接口 —— 前端唯一依赖面，逐端点对应契约 v2（api-openapi.json @ 0.2.1） */
export interface AutohuntApi {
  // keys（FR-25，UI session）
  listKeys(): Promise<ApiKeyInfo[]>;
  createKey(body: ApiKeyCreate): Promise<ApiKeyCreated>;
  revokeKey(id: string): Promise<void>;

  // profile（FR-20 读 / FR-2 写，D-03 显式保存）
  getProfile(resumeId?: string): Promise<ProfileResponse>;
  putProfile(body: ProfileUpdate): Promise<Profile>;

  // resumes（FR-1/2/3，D-02）
  listResumes(): Promise<ResumeList>;
  uploadResume(file: File, name?: string): Promise<ResumeInfo>;
  updateResume(id: string, body: ResumeUpdate): Promise<ResumeInfo>;
  deleteResume(id: string): Promise<void>;
  /** PDF 原件下载地址（cookie 会话，直接作 <a href>） */
  resumeFileUrl(id: string): string;
  listResumeReferences(id: string): Promise<ApplicationList>;

  // jobs（FR-10/21，BR-3）
  createJob(body: JobCreate): Promise<CreateJobResult>;
  listJobs(cursor?: string, limit?: number): Promise<JobList>;
  getJob(id: string): Promise<Job>;
  updateJob(id: string, body: JobUpdate): Promise<Job>;

  // applications（FR-11/21/30；from/to 为契约 v2 服务端筛选）
  createApplication(body: ApplicationCreate): Promise<Application>;
  listApplications(filter?: { status?: string; company?: string; channel?: string; from?: string; to?: string }): Promise<ApplicationList>;
  updateApplication(id: string, body: ApplicationUpdate): Promise<Application>;
  getApplicationHistory(id: string): Promise<StatusHistoryList>;
  getApplicationConfirmations(id: string): Promise<ConfirmationRecordList>;
  getApplicationEmails(id: string): Promise<EmailEventDetailList>;

  // confirmations（FR-22/23/24，BR-1；列表/PendingUI 快照/close 为契约 v2）
  createConfirmation(body: ConfirmationCreate): Promise<ConfirmationCreated>;
  listConfirmations(filter?: { status?: ConfirmationStatus; cursor?: string; limit?: number }): Promise<ConfirmationList>;
  getConfirmation(id: string): Promise<ConfirmationView>;
  getConfirmationDetail(id: string): Promise<ConfirmationDetail>;
  confirm(id: string, body: ConfirmationConfirm): Promise<ConfirmationConfirmed>;
  reject(id: string, body: ConfirmationReject): Promise<ConfirmationView>;
  reissue(id: string): Promise<ConfirmationConfirmed>;
  closeConfirmation(id: string, body?: ConfirmationClose): Promise<ConfirmationView>;

  // events / schedule（FR-42/43，BR-2；写侧为契约 v2，仅 UI）
  listPendingEvents(): Promise<EmailEventList>;
  getEvent(id: string): Promise<EmailEventDetail>;
  getEventRaw(id: string): Promise<string>;
  confirmEvent(id: string, body: EmailEventConfirm): Promise<EmailEventConfirmResult>;
  discardEvent(id: string, body: EmailEventDiscard): Promise<EmailEventDetail>;
  getSchedule(from?: string, to?: string): Promise<ScheduleEventList>;

  // email-accounts（FR-40/44，D-10）
  testEmailAccount(body: EmailAccountBind): Promise<EmailAccountTestResult>;
  listEmailAccounts(): Promise<EmailAccountList>;
  bindEmailAccount(body: EmailAccountBind): Promise<EmailAccountInfo>;
  reauthEmailAccount(id: string, body: EmailAccountReauth): Promise<EmailAccountInfo>;
  unbindEmailAccount(id: string): Promise<void>;

  // notifications（FR-32）
  listNotifications(cursor?: string, limit?: number): Promise<NotificationList>;

  // stats（FR-50/51/52，口径 §10.4，服务端 status_history 计算）
  getStatsOverview(filter?: StatsFilter): Promise<StatsOverview>;
  getStatsFunnel(filter?: StatsFilter): Promise<StatsFunnel>;
  /** 台账导出 CSV（触发浏览器下载） */
  downloadStatsExport(filter?: StatsFilter): void;

  // settings（FR-32 配套，D-10）
  getReminders(): Promise<ReminderSettings>;
  putReminders(body: ReminderSettings): Promise<ReminderSettings>;

  // llm config（PROX-8/PROX-12）
  getLLMConfig(): Promise<LLMConfig>;
  putLLMConfig(body: LLMConfigUpdate): Promise<LLMConfig>;
  testLLMConfig(): Promise<LLMConfigTestResult>;
}

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api/v1';

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include', // UI session: HttpOnly Cookie（§3.1）
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    ...init,
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const env = data?.error;
    throw new ApiError(res.status, env?.code ?? 'UNKNOWN', env?.message ?? res.statusText, env?.details);
  }
  return data as T;
}

function qs(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') sp.set(k, String(v));
  const s = sp.toString();
  return s ? `?${s}` : '';
}

/** 真实后端客户端 —— 只调用契约 v2 内的端点 */
export const httpApi: AutohuntApi = {
  listKeys: async () => (await req<{ items: ApiKeyInfo[] }>('/keys')).items,
  createKey: (body) => req<ApiKeyCreated>('/keys', { method: 'POST', body: JSON.stringify(body) }),
  revokeKey: (id) => req<void>(`/keys/${id}`, { method: 'DELETE' }),

  getProfile: (resumeId) => req<ProfileResponse>(`/profile${qs({ resume_id: resumeId })}`),
  putProfile: (body) => req<Profile>('/profile', { method: 'PUT', body: JSON.stringify(body) }),

  listResumes: () => req<ResumeList>('/resumes'),
  async uploadResume(file, name) {
    const fd = new FormData();
    fd.append('file', file);
    if (name) fd.append('name', name);
    // multipart：不手动设置 Content-Type，由浏览器带 boundary
    const res = await fetch(`${BASE}/resumes`, { method: 'POST', credentials: 'include', body: fd });
    const text = await res.text();
    const data = text ? JSON.parse(text) : undefined;
    if (!res.ok) {
      const env = data?.error;
      throw new ApiError(res.status, env?.code ?? 'UNKNOWN', env?.message ?? res.statusText, env?.details);
    }
    return data as ResumeInfo;
  },
  updateResume: (id, body) => req<ResumeInfo>(`/resumes/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteResume: (id) => req<void>(`/resumes/${id}`, { method: 'DELETE' }),
  resumeFileUrl: (id) => `${BASE}/resumes/${id}/file`,
  listResumeReferences: (id) => req<ApplicationList>(`/resumes/${id}/references`),

  async createJob(body) {
    const res = await fetch(`${BASE}/jobs`, {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new ApiError(res.status, data?.error?.code ?? 'UNKNOWN', data?.error?.message ?? res.statusText);
    // 契约：201 首次创建返回 Job；200 命中重复返回 JobDuplicate（BR-3 提示不拦截）
    if (res.status === 200) return { kind: 'duplicate', duplicateOf: data.duplicate_of, job: data.job };
    return { kind: 'created', job: data };
  },
  listJobs: (cursor, limit) => req<JobList>(`/jobs${qs({ cursor, limit })}`),
  getJob: (id) => req<Job>(`/jobs/${id}`),
  updateJob: (id, body) => req<Job>(`/jobs/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),

  createApplication: (body) => req<Application>('/applications', { method: 'POST', body: JSON.stringify(body) }),
  listApplications: (f) => req<ApplicationList>(`/applications${qs({ status: f?.status, company: f?.company, channel: f?.channel, from: f?.from, to: f?.to })}`),
  updateApplication: (id, body) => req<Application>(`/applications/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  getApplicationHistory: (id) => req<StatusHistoryList>(`/applications/${id}/history`),
  getApplicationConfirmations: (id) => req<ConfirmationRecordList>(`/applications/${id}/confirmations`),
  getApplicationEmails: (id) => req<EmailEventDetailList>(`/applications/${id}/emails`),

  createConfirmation: (body) => req<ConfirmationCreated>('/confirmations', { method: 'POST', body: JSON.stringify(body) }),
  listConfirmations: (f) => req<ConfirmationList>(`/confirmations${qs({ status: f?.status, cursor: f?.cursor, limit: f?.limit })}`),
  getConfirmation: (id) => req<ConfirmationView>(`/confirmations/${id}`),
  // UI session 下待确认变体即 PendingUI（含 fields/context 快照），直接展开合并
  getConfirmationDetail: async (id) => ({ id, ...(await req<Omit<ConfirmationDetail, 'id'>>(`/confirmations/${id}`)) }),
  confirm: (id, body) => req<ConfirmationConfirmed>(`/confirmations/${id}/confirm`, { method: 'POST', body: JSON.stringify(body) }),
  reject: (id, body) => req<ConfirmationView>(`/confirmations/${id}/reject`, { method: 'POST', body: JSON.stringify(body) }),
  reissue: (id) => req<ConfirmationConfirmed>(`/confirmations/${id}/reissue`, { method: 'POST' }),
  closeConfirmation: (id, body) => req<ConfirmationView>(`/confirmations/${id}/close`, { method: 'POST', body: JSON.stringify(body ?? {}) }),

  listPendingEvents: () => req<EmailEventList>('/events/pending'),
  getEvent: (id) => req<EmailEventDetail>(`/events/${id}`),
  async getEventRaw(id) {
    const res = await fetch(`${BASE}/events/${id}/raw`, { credentials: 'include' });
    const text = await res.text();
    if (!res.ok) {
      let env: { code?: string; message?: string } | undefined;
      try { env = JSON.parse(text)?.error; } catch { /* text/plain 错误体 */ }
      throw new ApiError(res.status, env?.code ?? 'UNKNOWN', env?.message ?? res.statusText);
    }
    return text;
  },
  confirmEvent: (id, body) => req<EmailEventConfirmResult>(`/events/${id}/confirm`, { method: 'POST', body: JSON.stringify(body) }),
  discardEvent: (id, body) => req<EmailEventDetail>(`/events/${id}/discard`, { method: 'POST', body: JSON.stringify(body) }),
  getSchedule: (from, to) => req<ScheduleEventList>(`/schedule${qs({ from, to })}`),

  testEmailAccount: (body) => req<EmailAccountTestResult>('/email-accounts/test', { method: 'POST', body: JSON.stringify(body) }),
  listEmailAccounts: () => req<EmailAccountList>('/email-accounts'),
  bindEmailAccount: (body) => req<EmailAccountInfo>('/email-accounts', { method: 'POST', body: JSON.stringify(body) }),
  reauthEmailAccount: (id, body) => req<EmailAccountInfo>(`/email-accounts/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  unbindEmailAccount: (id) => req<void>(`/email-accounts/${id}`, { method: 'DELETE' }),

  listNotifications: (cursor, limit) => req<NotificationList>(`/notifications${qs({ cursor, limit })}`),

  getStatsOverview: (f) => req<StatsOverview>(`/stats/overview${qs({ channel: f?.channel, from: f?.from, to: f?.to })}`),
  getStatsFunnel: (f) => req<StatsFunnel>(`/stats/funnel${qs({ channel: f?.channel, from: f?.from, to: f?.to })}`),
  downloadStatsExport(f) {
    const a = document.createElement('a');
    a.href = `${BASE}/stats/export${qs({ channel: f?.channel, from: f?.from, to: f?.to })}`;
    a.download = 'applications-export.csv';
    a.click();
  },

  getReminders: () => req<ReminderSettings>('/settings/reminders'),
  putReminders: (body) => req<ReminderSettings>('/settings/reminders', { method: 'PUT', body: JSON.stringify(body) }),

  getLLMConfig: () => req<LLMConfig>('/settings/llm'),
  putLLMConfig: (body) => req<LLMConfig>('/settings/llm', { method: 'PUT', body: JSON.stringify(body) }),
  testLLMConfig: () => req<LLMConfigTestResult>('/settings/llm/test', { method: 'POST' }),
};

/**
 * UI session 引导（契约新增 GET /ui/session）：浏览器首次访问时后端从未签发过
 * ah_session cookie，所有 /api/v1 请求会被鉴权中间件 401。应用启动时先调用本函数
 * 换取 Set-Cookie，再发起数据查询。失败（后端未就绪 / 网络错误）静默 —— 不阻断
 * 首帧，数据请求会照常收到鉴权错误。
 */
export async function ensureUiSession(): Promise<void> {
  try {
    await fetch(`${BASE}/ui/session`, { credentials: 'include' });
  } catch {
    // 网络错误：后端未启动或暂不可达，交由后续数据请求自行报告
  }
}
