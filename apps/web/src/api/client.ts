import type {
  ApiKeyCreate, ApiKeyCreated, ApiKeyInfo,
  Application, ApplicationCreate, ApplicationList, ApplicationUpdate,
  ConfirmationConfirm, ConfirmationConfirmed, ConfirmationCreate, ConfirmationCreated,
  ConfirmationReject, ConfirmationStatus, ConfirmationView,
  CreateJobResult, EmailEventList, Job, JobCreate, JobList, JobUpdate,
  PendingConfirmation, ProfileResponse, ScheduleEventList,
} from './types';

/**
 * [契约缺口] 确认单完整视图（D-06 对照表数据源）。
 * 冻结契约中 GET /confirmations/{id} 的「待确认」变体仅返回 {status}，
 * 不含字段快照 fields / 提交结果回写 —— D-06 对照表与 FR-24 结果视图
 * 依赖的字段在契约内不可得，已上报 Leader/BackendDev 待契约扩展。
 * 真实模式 snapshotUnavailable=true；mock 模式提供完整演示数据。
 */
export interface ConfirmationDetail {
  id: string;
  application_id: string;
  status: ConfirmationStatus;
  fields: Record<string, string>;
  confirmed_fields?: Record<string, string>;
  submit_token?: string | null;
  expires_at?: string;
  reason?: string | null;
  submit_result?: { result: 'success' | 'failed'; fail_reason?: string | null; submitted_at: string } | null;
  created_at?: string;
  snapshotUnavailable?: boolean;
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

/**
 * 数据接口 —— 前端唯一依赖面。
 * contract* 方法 = 冻结契约 19 端点（真实后端必须支持）；
 * 标注 [契约缺口] 的方法 = UI 设计需要但冻结契约未覆盖，真实模式抛 ApiError(501)，
 * mock 模式提供演示数据（见 mock.ts 顶部说明）。
 */
export interface AutohuntApi {
  // keys（FR-25，UI session）
  listKeys(): Promise<ApiKeyInfo[]>;
  createKey(body: ApiKeyCreate): Promise<ApiKeyCreated>;
  revokeKey(id: string): Promise<void>;

  // profile（FR-20）
  getProfile(resumeId?: string): Promise<ProfileResponse>;

  // jobs（FR-10/21，BR-3）
  createJob(body: JobCreate): Promise<CreateJobResult>;
  listJobs(cursor?: string, limit?: number): Promise<JobList>;
  getJob(id: string): Promise<Job>;
  updateJob(id: string, body: JobUpdate): Promise<Job>;

  // applications（FR-11/21/30）
  createApplication(body: ApplicationCreate): Promise<Application>;
  listApplications(filter?: { status?: string; company?: string; channel?: string }): Promise<ApplicationList>;
  updateApplication(id: string, body: ApplicationUpdate): Promise<Application>;

  // confirmations（FR-22/23/24，BR-1）
  createConfirmation(body: ConfirmationCreate): Promise<ConfirmationCreated>;
  getConfirmation(id: string): Promise<ConfirmationView>;
  confirm(id: string, body: ConfirmationConfirm): Promise<ConfirmationConfirmed>;
  reject(id: string, body: ConfirmationReject): Promise<ConfirmationView>;
  reissue(id: string): Promise<ConfirmationConfirmed>;

  // events / schedule（FR-42/43）
  listPendingEvents(): Promise<EmailEventList>;
  getSchedule(from?: string, to?: string): Promise<ScheduleEventList>;

  /** [契约缺口] 待确认投递列表 —— 契约无 GET /confirmations 列表端点 */
  listPendingConfirmations(): Promise<PendingConfirmation[]>;
  /** [契约缺口] 确认单完整视图（含待确认态字段快照，D-06 数据源） */
  getConfirmationDetail(id: string): Promise<ConfirmationDetail>;
  /** [契约缺口] 手动关闭确认任务（§12 已超时关闭）—— 契约无 close 端点 */
  closeConfirmation(id: string): Promise<void>;
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

/** 真实后端客户端 —— 只调用冻结契约内的端点 */
export const httpApi: AutohuntApi = {
  listKeys: async () => (await req<{ items: ApiKeyInfo[] }>('/keys')).items,
  createKey: (body) => req<ApiKeyCreated>('/keys', { method: 'POST', body: JSON.stringify(body) }),
  revokeKey: (id) => req<void>(`/keys/${id}`, { method: 'DELETE' }),

  getProfile: (resumeId) => req<ProfileResponse>(`/profile${qs({ resume_id: resumeId })}`),

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
  listApplications: (f) => req<ApplicationList>(`/applications${qs({ status: f?.status, company: f?.company, channel: f?.channel })}`),
  updateApplication: (id, body) => req<Application>(`/applications/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),

  createConfirmation: (body) => req<ConfirmationCreated>('/confirmations', { method: 'POST', body: JSON.stringify(body) }),
  getConfirmation: (id) => req<ConfirmationView>(`/confirmations/${id}`),
  confirm: (id, body) => req<ConfirmationConfirmed>(`/confirmations/${id}/confirm`, { method: 'POST', body: JSON.stringify(body) }),
  reject: (id, body) => req<ConfirmationView>(`/confirmations/${id}/reject`, { method: 'POST', body: JSON.stringify(body) }),
  reissue: (id) => req<ConfirmationConfirmed>(`/confirmations/${id}/reissue`, { method: 'POST' }),

  listPendingEvents: () => req<EmailEventList>('/events/pending'),
  getSchedule: (from, to) => req<ScheduleEventList>(`/schedule${qs({ from, to })}`),

  listPendingConfirmations: () => {
    throw new ApiError(501, 'NOT_IMPLEMENTED', '契约缺口：GET /confirmations 列表端点未在冻结契约中（已上报 Leader/BackendDev）');
  },
  async getConfirmationDetail(id) {
    // 真实模式只能取得契约内字段；待确认态快照不可得（snapshotUnavailable）
    const view = await req<ConfirmationView>(`/confirmations/${id}`);
    const base = {
      id, application_id: '', status: view.status,
      fields: {}, snapshotUnavailable: view.status === '待确认',
    } as ConfirmationDetail;
    if (view.status === '已确认') {
      return { ...base, confirmed_fields: view.confirmed_fields, submit_token: view.submit_token, expires_at: view.expires_at };
    }
    if (view.status !== '待确认') return { ...base, reason: view.reason ?? null };
    return base;
  },
  closeConfirmation: () => {
    throw new ApiError(501, 'NOT_IMPLEMENTED', '契约缺口：确认任务手动关闭端点未在冻结契约中（已上报 Leader/BackendDev）');
  },
};
