/**
 * Mock 适配器 —— 后端未就绪时的先行开发数据源。
 * 与契约 v2 同形（api-openapi.json @ 0.2.1）：覆盖确认流（列表 / PendingUI 快照 /
 * close / submit_result 回写）、D-05 读侧三端点、简历、档案写、邮箱账户、事件写侧、
 * 通知、统计、提醒偏好的演示数据。漏斗/指标卡的 status_history 口径在 mock 中以
 * 当前状态 rank 近似（演示数据，真实后端按 status_history 精确计算）。
 * 启用：URL 加 ?mock=1 或环境变量 VITE_MOCK=1。
 */
import type {
  ApiKeyCreated, ApiKeyInfo, Application, ApplicationList, ApplicationStatus,
  ApplicationUpdate, ConfirmationClose, ConfirmationConfirmed, ConfirmationCreate,
  ConfirmationCreated, ConfirmationList, ConfirmationRecordList, ConfirmationReject,
  ConfirmationStatus, EmailAccountBind, EmailAccountInfo, EmailAccountList,
  EmailAccountReauth, EmailEvent, EmailEventConfirm, EmailEventDetail,
  EmailEventDetailList, EmailEventDiscard, EmailEventList, Job, JobCreate, JobList,
  JobUpdate, LLMConfig, LLMConfigTestResult, LLMConfigUpdate, NotificationList, Profile, ProfileResponse, ProfileUpdate, ReminderSettings,
  ResumeInfo, ResumeList, ResumeUpdate, ScheduleEvent, ScheduleEventList,
  StatsFilter, StatsFunnel, StatsOverview, StatusHistoryEntry, StatusHistoryList,
  CreateJobResult, ConfirmationView,
} from './types';
import { ApiError, type AutohuntApi, type ConfirmationDetail } from './client';
import { funnel, metrics } from '../utils/funnel';

const now = () => new Date().toISOString();
const hoursAgo = (h: number) => new Date(Date.now() - h * 3600_000).toISOString();
const hoursLater = (h: number) => new Date(Date.now() + h * 3600_000).toISOString();
const uid = () => Math.random().toString(36).slice(2, 10);

interface MockConfirmation {
  id: string;
  application_id: string;
  request_id: string;
  fields: Record<string, string>;
  context?: Record<string, string> | null;
  status: ConfirmationStatus;
  confirmed_fields?: Record<string, string>;
  confirmed_at?: string | null;
  submit_token?: string | null;
  expires_at?: string;
  consumed?: boolean;
  reason?: string | null;
  submit_result?: 'success' | 'failed' | null;
  fail_reason?: string | null;
  submitted_at?: string | null;
  created_at: string;
}

type MockEvent = EmailEventDetail;

const db = {
  keys: [
    { id: 'key-1', name: '本机 Agent CLI', prefix: 'ah_live_ab12', created_at: hoursAgo(72), last_used_at: hoursAgo(3) },
  ] as ApiKeyInfo[],
  jobs: [
    { id: 'job-1', company: '阿里巴巴', title: '后端开发工程师', jd_url: 'https://campus.alibaba.com/position/1', location: '杭州', channel: '公司官网', deadline: hoursLater(60), created_at: hoursAgo(100) },
    { id: 'job-2', company: '字节跳动', title: '后端开发工程师', jd_url: 'https://jobs.bytedance.com/1', location: '北京', channel: '公司官网', deadline: hoursLater(20), created_at: hoursAgo(90) },
    { id: 'job-3', company: '腾讯', title: '后台开发', jd_url: 'https://careers.tencent.com/1', location: '深圳', channel: '内推', deadline: hoursLater(200), created_at: hoursAgo(80) },
    { id: 'job-4', company: '美团', title: '后端开发', jd_url: null, location: '北京', channel: '公司官网', deadline: null, created_at: hoursAgo(70) },
    { id: 'job-5', company: '百度', title: '服务端研发', jd_url: null, location: '北京', channel: '公司官网', deadline: null, created_at: hoursAgo(60) },
    { id: 'job-6', company: '网易', title: 'Java 开发', jd_url: null, location: '杭州', channel: '公司官网', deadline: null, created_at: hoursAgo(50) },
  ] as Job[],
  schedule: [
    { id: 'sch-1', application_id: 'app-3', source_event_id: null, title: '腾讯 后台开发 笔试', type: '笔试', start_time: hoursLater(26), end_time: hoursLater(28), location: null, meeting_link: 'https://meeting.example.com/tx' },
    { id: 'sch-2', application_id: 'app-4', source_event_id: null, title: '美团 后端开发 三面', type: '面试', start_time: hoursLater(70), end_time: hoursLater(71), location: '线上', meeting_link: 'https://meeting.example.com/mt' },
  ] as ScheduleEvent[],
} as const;

const mutable = {
  keys: [...db.keys] as ApiKeyInfo[],
  jobs: [...db.jobs] as Job[],
  profile: {
    name: '张三', phone: '13800001234', email: 'qiuzhi@example.com',
    educations: [{ school: '某大学', degree: '本科', major: '计算机科学与技术', start_date: '2022-09', end_date: '2026-06' }],
    experiences: [{ company: '某科技公司', position: '后端开发实习生', start_date: '2025-06', end_date: '2025-09', description: '负责订单服务接口开发' }],
    skills: ['Java', 'Python', 'MySQL', 'Redis'],
    awards: ['校级一等奖学金'],
    expected_city: '杭州', expected_position: '后端开发工程师',
    resume_id: 'resume-1', resume_version: 3,
  } as Profile,
  resumes: [
    { id: 'resume-1', name: '简历 v3', version: 3, is_default: true, parse_status: '解析完成', missing_fields: [], parse_error: null, used_count: 6, created_at: hoursAgo(200) },
    { id: 'resume-2', name: '简历 v2', version: 2, is_default: false, parse_status: '部分字段缺失', missing_fields: ['电话'], parse_error: null, used_count: 0, created_at: hoursAgo(400) },
  ] as ResumeInfo[],
  applications: [
    { id: 'app-1', job_id: 'job-1', resume_id: 'resume-1', applied_at: null, status: '待投递' },
    { id: 'app-2', job_id: 'job-2', resume_id: 'resume-1', applied_at: hoursAgo(48), status: '已投递' },
    { id: 'app-3', job_id: 'job-3', resume_id: 'resume-1', applied_at: hoursAgo(96), status: '笔试' },
    { id: 'app-4', job_id: 'job-4', resume_id: 'resume-1', applied_at: hoursAgo(120), status: '面试', interview_round: 2 },
    { id: 'app-5', job_id: 'job-5', resume_id: 'resume-1', applied_at: hoursAgo(200), status: '未通过' },
    { id: 'app-6', job_id: 'job-6', resume_id: 'resume-1', applied_at: hoursAgo(24), status: '已投递' },
  ] as Application[],
  history: {
    'app-3': [
      { from_status: null, to_status: '待投递', source: 'ui', rejected: false, created_at: hoursAgo(100) },
      { from_status: '待投递', to_status: '已投递', source: 'agent', rejected: false, created_at: hoursAgo(96) },
      { from_status: '已投递', to_status: '笔试', source: 'email', rejected: false, created_at: hoursAgo(30) },
    ],
    'app-4': [
      { from_status: null, to_status: '待投递', source: 'ui', rejected: false, created_at: hoursAgo(130) },
      { from_status: '待投递', to_status: '已投递', source: 'agent', rejected: false, created_at: hoursAgo(120) },
      { from_status: '已投递', to_status: '面试', source: 'email', rejected: false, created_at: hoursAgo(72) },
      { from_status: '面试', to_status: '笔试', source: 'email', rejected: true, created_at: hoursAgo(20) },
    ],
  } as Record<string, StatusHistoryEntry[]>,
  confirmations: [
    {
      id: 'cfm-1', application_id: 'app-1', request_id: 'req-mock-1',
      fields: { 姓名: '张三', 电话: '13800001234', 邮箱: 'qiuzhi@example.com', 学校: '某大学', 专业: '计算机科学与技术', 期望城市: '杭州' },
      context: { target_url: 'https://campus.alibaba.com/apply/1' },
      status: '待确认', created_at: hoursAgo(30),
    },
    {
      id: 'cfm-2', application_id: 'app-6', request_id: 'req-mock-2',
      fields: { 姓名: '张三', 电话: '13899998888', 邮箱: 'qiuzhi@example.com' },
      status: '待确认', created_at: hoursAgo(2),
    },
    {
      id: 'cfm-3', application_id: 'app-2', request_id: 'req-mock-3',
      fields: { 姓名: '张三', 电话: '13800001234' },
      status: '已确认', confirmed_fields: { 姓名: '张三', 电话: '13800001234' }, confirmed_at: hoursAgo(49),
      submit_token: null, expires_at: hoursAgo(1), consumed: true,
      submit_result: 'failed', fail_reason: '目标站点验证码拦截，需人工处理', submitted_at: hoursAgo(1),
      created_at: hoursAgo(50),
    },
  ] as MockConfirmation[],
  events: [
    { id: 'evt-1', type: '笔试', event_time: hoursLater(30), location: null, meeting_link: 'https://meeting.example.com/abc', company: '阿里巴巴', matched_job_id: 'job-1', status: '待确认', created_at: hoursAgo(5), email_subject: '【阿里巴巴】笔试邀请', email_sender: 'campus@alibaba.com', email_received_at: hoursAgo(5) },
    { id: 'evt-2', type: '面试', event_time: hoursLater(80), location: '北京市海淀区某大厦 3F', meeting_link: null, company: '美团', matched_job_id: 'job-4', status: '待确认', created_at: hoursAgo(10), email_subject: '【美团】面试通知', email_sender: 'hr@meituan.com', email_received_at: hoursAgo(10) },
  ] as MockEvent[],
  schedule: [...db.schedule] as ScheduleEvent[],
  emailAccounts: [
    { id: 'ea-1', email: 'qiuzhi@example.com', imap_host: 'imap.example.com', port: 993, status: 'active', last_sync_at: hoursAgo(1), created_at: hoursAgo(300) },
  ] as EmailAccountInfo[],
  reminders: { schedule_24h: true, schedule_1h: true, include_deadline: true } as ReminderSettings,
  llm: { enabled: false, provider: 'openai', base_url: null, model: 'gpt-4o-mini', api_key_last4: null, timeout_seconds: 15, max_tokens: 2048 } as LLMConfig,
};

const delay = <T>(v: T): Promise<T> => new Promise((r) => setTimeout(() => r(v), 120));

function findConfirmation(id: string): MockConfirmation {
  const c = mutable.confirmations.find((x) => x.id === id);
  if (!c) throw new ApiError(404, 'NOT_FOUND', '确认任务不存在');
  return c;
}

function findApplication(id: string): Application {
  const a = mutable.applications.find((x) => x.id === id);
  if (!a) throw new ApiError(404, 'NOT_FOUND', '投递不存在');
  return a;
}

/** UI session 视图：待确认携带 PendingUI 快照；已确认携带回写结果 */
function confirmationDetail(c: MockConfirmation): ConfirmationDetail {
  const base = { id: c.id, status: c.status, created_at: c.created_at };
  if (c.status === '待确认') {
    return { ...base, application_id: c.application_id, fields: c.fields, context: c.context ?? null };
  }
  if (c.status === '已确认') {
    return {
      ...base,
      confirmed_fields: c.confirmed_fields ?? {},
      submit_token: c.consumed ? null : (c.submit_token ?? null),
      expires_at: c.expires_at ?? now(),
      submit_result: c.submit_result ?? null,
      fail_reason: c.fail_reason ?? null,
      submitted_at: c.submitted_at ?? null,
    };
  }
  return { ...base, reason: c.reason ?? null };
}

function confirmationView(c: MockConfirmation): ConfirmationView {
  const { id: _id, ...view } = confirmationDetail(c);
  return view as ConfirmationView;
}

function inRange(a: Application, f?: StatsFilter): boolean {
  if (f?.from && (a.applied_at ?? '') < f.from) return false;
  if (f?.to && (a.applied_at ?? '') > f.to) return false;
  if (f?.channel) {
    const j = mutable.jobs.find((x) => x.id === a.job_id);
    if (j?.channel !== f.channel) return false;
  }
  return true;
}

export const mockApi: AutohuntApi = {
  listKeys: () => delay(mutable.keys.filter((k) => k)),
  createKey: ({ name }) => {
    const created: ApiKeyCreated = { id: `key-${uid()}`, name, key: `ah_live_${uid()}${uid()}`, prefix: `ah_live_${uid().slice(0, 4)}`, created_at: now() };
    const { key: _k, ...info } = created;
    mutable.keys.push(info);
    return delay(created);
  },
  revokeKey: (id) => {
    mutable.keys = mutable.keys.filter((k) => k.id !== id);
    return delay(undefined);
  },

  getProfile: () => delay(mutable.profile as ProfileResponse),
  putProfile: (body: ProfileUpdate) => {
    mutable.profile = {
      ...body,
      email: body.email ?? mutable.profile.email,
      resume_id: body.resume_id,
      resume_version: mutable.resumes.find((r) => r.id === body.resume_id)?.version ?? mutable.profile.resume_version,
    };
    return delay(mutable.profile);
  },

  listResumes: () => delay({ items: [...mutable.resumes].sort((a, b) => b.created_at.localeCompare(a.created_at)) } as ResumeList),
  uploadResume: (file, name) => {
    const version = Math.max(0, ...mutable.resumes.map((r) => r.version)) + 1;
    const r: ResumeInfo = {
      id: `resume-${uid()}`, name: name ?? `简历 v${version}`, version,
      is_default: mutable.resumes.length === 0,
      parse_status: '解析完成', missing_fields: [], parse_error: null,
      used_count: 0, created_at: now(),
    };
    if (r.is_default) mutable.resumes.forEach((x) => { x.is_default = false; });
    mutable.resumes.push(r);
    return delay(r);
  },
  updateResume: (id, body: ResumeUpdate) => {
    const r = mutable.resumes.find((x) => x.id === id);
    if (!r) return Promise.reject(new ApiError(404, 'NOT_FOUND', '简历版本不存在'));
    if (body.name != null) r.name = body.name;
    if (body.is_default === true) {
      mutable.resumes.forEach((x) => { x.is_default = false; });
      r.is_default = true;
    }
    return delay(r);
  },
  deleteResume: (id) => {
    const r = mutable.resumes.find((x) => x.id === id);
    if (!r) return Promise.reject(new ApiError(404, 'NOT_FOUND', '简历版本不存在'));
    if (r.used_count > 0) {
      return Promise.reject(new ApiError(409, 'STATE_CONFLICT', '已被投递引用，禁止删除（FR-3 回溯保护）', { used_count: r.used_count }));
    }
    mutable.resumes = mutable.resumes.filter((x) => x.id !== id);
    return delay(undefined);
  },
  resumeFileUrl: () => '#mock-pdf',
  listResumeReferences: (id) => delay({
    items: mutable.applications.filter((a) => a.resume_id === id), next_cursor: null,
  } as ApplicationList),

  createJob: (body: JobCreate) => {
    const dup = mutable.jobs.find((j) => j.company === body.company && j.title === body.title);
    const job: Job = { id: `job-${uid()}`, created_at: now(), ...body };
    if (dup) return delay({ kind: 'duplicate', duplicateOf: dup.id, job: dup } as CreateJobResult);
    mutable.jobs.push(job);
    return delay({ kind: 'created', job } as CreateJobResult);
  },
  listJobs: () => delay({ items: mutable.jobs, next_cursor: null } as JobList),
  getJob: (id) => {
    const j = mutable.jobs.find((x) => x.id === id);
    return j ? delay(j) : Promise.reject(new ApiError(404, 'NOT_FOUND', '岗位不存在'));
  },
  updateJob: (id: string, body: JobUpdate) => {
    const j = mutable.jobs.find((x) => x.id === id);
    if (!j) return Promise.reject(new ApiError(404, 'NOT_FOUND', '岗位不存在'));
    Object.assign(j, body);
    return delay(j);
  },

  createApplication: ({ job_id, resume_id }) => {
    const app: Application = { id: `app-${uid()}`, job_id, resume_id, applied_at: null, status: '待投递' };
    mutable.applications.push(app);
    mutable.history[app.id] = [{ from_status: null, to_status: '待投递', source: 'ui', rejected: false, created_at: now() }];
    return delay(app);
  },
  listApplications: (f) => delay({
    items: mutable.applications.filter((a) => {
      if (f?.status && a.status !== f.status) return false;
      if (f?.company && !mutable.jobs.find((j) => j.id === a.job_id)?.company.includes(f.company)) return false;
      if (!inRange(a, f)) return false;
      return true;
    }),
    next_cursor: null,
  } as ApplicationList),
  updateApplication: (id, body: ApplicationUpdate) => {
    const a = findApplication(id);
    if (body.status != null && body.status !== a.status) {
      (mutable.history[id] ??= []).push({ from_status: a.status, to_status: body.status as ApplicationStatus, source: 'ui', rejected: false, created_at: now() });
      a.status = body.status as ApplicationStatus;
      if (body.status === '已投递' && !a.applied_at) a.applied_at = now();
    }
    if (body.note !== undefined && body.note !== null) a.note = body.note;
    if (body.interview_round !== undefined) a.interview_round = body.interview_round;
    return delay(a);
  },
  getApplicationHistory: (id) => {
    findApplication(id);
    return delay({ items: mutable.history[id] ?? [] } as StatusHistoryList);
  },
  getApplicationConfirmations: (id) => {
    findApplication(id);
    return delay({
      items: mutable.confirmations
        .filter((c) => c.application_id === id)
        .map((c) => ({
          id: c.id, status: c.status, created_at: c.created_at,
          confirmed_at: c.confirmed_at ?? null,
          submit_result: c.submit_result ?? null,
          fail_reason: c.fail_reason ?? null,
          submitted_at: c.submitted_at ?? null,
        })),
    } as ConfirmationRecordList);
  },
  getApplicationEmails: (id) => {
    const a = findApplication(id);
    return delay({ items: mutable.events.filter((e) => e.matched_job_id === a.job_id) } as EmailEventDetailList);
  },

  createConfirmation: (body: ConfirmationCreate) => {
    const hit = mutable.confirmations.find((c) => c.request_id === body.request_id);
    if (hit) return delay({ confirmation_id: hit.id, status: hit.status } as ConfirmationCreated); // 幂等命中
    const c: MockConfirmation = {
      id: `cfm-${uid()}`, application_id: body.application_id, request_id: body.request_id,
      fields: body.fields, context: body.context ?? null, status: '待确认', created_at: now(),
    };
    mutable.confirmations.push(c);
    return delay({ confirmation_id: c.id, status: '待确认' } as ConfirmationCreated);
  },
  listConfirmations: (f) => delay({
    items: mutable.confirmations
      .filter((c) => !f?.status || c.status === f.status)
      .map((c) => ({
        id: c.id, application_id: c.application_id, status: c.status,
        created_at: c.created_at, confirmed_at: c.confirmed_at ?? null,
        submit_result: c.submit_result ?? null,
      })),
    next_cursor: null,
  } as ConfirmationList),
  getConfirmation: (id) => delay(confirmationView(findConfirmation(id))),
  getConfirmationDetail: (id) => delay(confirmationDetail(findConfirmation(id))),
  confirm: (id, body) => {
    const c = findConfirmation(id);
    if (c.status !== '待确认') return Promise.reject(new ApiError(409, 'STATE_CONFLICT', '仅待确认状态可确认'));
    c.status = '已确认';
    c.confirmed_fields = body.confirmed_fields;
    c.confirmed_at = now();
    c.submit_token = `st_${uid()}${uid()}`;
    c.expires_at = hoursLater(0.5);
    c.consumed = false;
    return delay(confirmationView(c) as ConfirmationConfirmed);
  },
  reject: (id, body: ConfirmationReject) => {
    const c = findConfirmation(id);
    if (c.status !== '待确认') return Promise.reject(new ApiError(409, 'STATE_CONFLICT', '仅待确认状态可驳回'));
    c.status = '已驳回';
    c.reason = body.reason ?? null;
    return delay(confirmationView(c));
  },
  reissue: (id) => {
    const c = findConfirmation(id);
    if (c.status !== '已确认') return Promise.reject(new ApiError(409, 'STATE_CONFLICT', '仅已确认状态可重新放行'));
    if (c.submit_result === 'success') return Promise.reject(new ApiError(409, 'STATE_CONFLICT', '已回写成功的确认单不可重新放行'));
    if (c.submit_token && !c.consumed) return Promise.reject(new ApiError(409, 'STATE_CONFLICT', 'token 仍有效，无需重新放行'));
    c.submit_token = `st_${uid()}${uid()}`;
    c.expires_at = hoursLater(0.5);
    c.consumed = false;
    return delay(confirmationView(c) as ConfirmationConfirmed);
  },
  closeConfirmation: (id, _body?: ConfirmationClose) => {
    const c = findConfirmation(id);
    if (c.status !== '待确认') return Promise.reject(new ApiError(409, 'STATE_CONFLICT', '仅待确认状态可关闭'));
    c.status = '已超时关闭';
    return delay(confirmationView(c));
  },

  listPendingEvents: () => delay({ items: mutable.events.filter((e) => e.status === '待确认'), next_cursor: null } as EmailEventList),
  getEvent: (id) => {
    const e = mutable.events.find((x) => x.id === id);
    return e ? delay(e) : Promise.reject(new ApiError(404, 'NOT_FOUND', '事件不存在'));
  },
  getEventRaw: (id) => {
    const e = mutable.events.find((x) => x.id === id);
    if (!e) return Promise.reject(new ApiError(404, 'NOT_FOUND', '事件不存在'));
    return delay(`Subject: ${e.email_subject ?? ''}\nFrom: ${e.email_sender ?? ''}\nDate: ${e.email_received_at ?? ''}\n\n（mock 演示）您好，感谢您投递我司${e.company ?? ''}相关岗位，现邀请您参加${e.type}，时间：${e.event_time ?? '待定'}。`);
  },
  confirmEvent: (id, body: EmailEventConfirm) => {
    const e = mutable.events.find((x) => x.id === id);
    if (!e) return Promise.reject(new ApiError(404, 'NOT_FOUND', '事件不存在'));
    if (e.status !== '待确认') return Promise.reject(new ApiError(409, 'STATE_CONFLICT', '仅待确认状态可确认'));
    Object.assign(e, Object.fromEntries(Object.entries(body).filter(([, v]) => v !== undefined && v !== null)));
    e.status = '已确认';
    const app = mutable.applications.find((a) => a.job_id === e.matched_job_id);
    if (app && ['笔试', '面试'].includes(e.type)) {
      (mutable.history[app.id] ??= []).push({ from_status: app.status, to_status: e.type as ApplicationStatus, source: 'email', rejected: false, created_at: now() });
      app.status = e.type as ApplicationStatus;
    }
    const se: ScheduleEvent = {
      id: `sch-${uid()}`, application_id: app?.id ?? null, source_event_id: e.id,
      title: `${e.company ?? ''} ${e.type}`, type: e.type,
      start_time: e.event_time ?? now(), end_time: null,
      location: e.location ?? null, meeting_link: e.meeting_link ?? null,
    };
    mutable.schedule.push(se);
    return delay({ event: e, schedule_event: se });
  },
  discardEvent: (id, _body: EmailEventDiscard) => {
    const e = mutable.events.find((x) => x.id === id);
    if (!e) return Promise.reject(new ApiError(404, 'NOT_FOUND', '事件不存在'));
    if (e.status !== '待确认') return Promise.reject(new ApiError(409, 'STATE_CONFLICT', '仅待确认状态可丢弃'));
    e.status = '已丢弃';
    return delay(e);
  },
  getSchedule: () => delay({ items: [...mutable.schedule] } as ScheduleEventList),

  testEmailAccount: (body: EmailAccountBind) =>
    delay(body.auth_code === 'fail' ? { ok: false, error: 'IMAP 认证失败：授权码无效' } : { ok: true, error: null }),
  listEmailAccounts: () => delay({ items: mutable.emailAccounts } as EmailAccountList),
  bindEmailAccount: (body: EmailAccountBind) => {
    if (mutable.emailAccounts.some((a) => a.email === body.email)) {
      return Promise.reject(new ApiError(409, 'STATE_CONFLICT', '该邮箱已绑定'));
    }
    if (body.auth_code === 'fail') {
      return Promise.reject(new ApiError(422, 'VALIDATION_ERROR', 'IMAP 连接验证失败：授权码无效'));
    }
    const a: EmailAccountInfo = {
      id: `ea-${uid()}`, email: body.email, imap_host: body.imap_host,
      port: body.port ?? 993, status: 'active', last_sync_at: null, created_at: now(),
    };
    mutable.emailAccounts.push(a);
    return delay(a);
  },
  reauthEmailAccount: (id, body: EmailAccountReauth) => {
    const a = mutable.emailAccounts.find((x) => x.id === id);
    if (!a) return Promise.reject(new ApiError(404, 'NOT_FOUND', '邮箱账户不存在'));
    if (body.auth_code === 'fail') {
      return Promise.reject(new ApiError(422, 'VALIDATION_ERROR', 'IMAP 连接验证失败：授权码无效'));
    }
    a.status = 'active';
    return delay(a);
  },
  unbindEmailAccount: (id) => {
    mutable.emailAccounts = mutable.emailAccounts.filter((a) => a.id !== id);
    return delay(undefined);
  },

  listNotifications: () => delay({
    items: [
      { id: 'ntf-1', kind: '24h', title: '腾讯 后台开发 笔试 24 小时后开始', message: '请提前准备', fire_at: hoursLater(2), schedule_event_id: 'sch-1', application_id: 'app-3' },
      { id: 'deadline:job-2', kind: 'deadline', title: '字节跳动 后端开发工程师 网申 24 小时内截止', message: null, fire_at: hoursLater(19), schedule_event_id: null, application_id: 'app-2' },
    ],
    next_cursor: null,
  } as NotificationList),

  getStatsOverview: (f) => {
    const apps = mutable.applications.filter((a) => inRange(a, f));
    const m = metrics(
      apps,
      mutable.confirmations.filter((c) => c.status === '待确认').length
        + mutable.events.filter((e) => e.status === '待确认').length,
    );
    return delay({
      total_applications: apps.filter((a) => a.status !== '待投递').length,
      in_progress: m.active,
      pending_items: m.pending,
      offers: m.offers,
    } as StatsOverview);
  },
  // mock 演示口径：以当前状态 rank 近似「进入过」（真实后端按 status_history 精确去重）
  getStatsFunnel: (f) => {
    const r = funnel(mutable.applications.filter((a) => inRange(a, f)));
    const stageOf = (label: string) => r.stages.find((s) => s.label === label)?.count ?? 0;
    return delay({
      stages: (['已投递', '笔试', '面试', 'offer'] as const).map((s) => ({ stage: s, entered_count: stageOf(s) })),
      conversions: {
        written_test_rate: r.stages[1].rateFromPrev,
        interview_rate: r.stages[2].rateFromPrev,
        offer_rate: r.stages[3].rateFromPrev,
      },
    } as StatsFunnel);
  },
  downloadStatsExport(f) {
    const rows = [['公司', '岗位名', '渠道', '地点', 'JD 链接', '简历版本 ID', '投递时间', '当前状态', '面试轮次', '备注']];
    for (const a of mutable.applications.filter((x) => inRange(x, f))) {
      const j = mutable.jobs.find((x) => x.id === a.job_id);
      rows.push([j?.company ?? '', j?.title ?? '', j?.channel ?? '', j?.location ?? '', j?.jd_url ?? '', a.resume_id, a.applied_at ?? '', a.status, String(a.interview_round ?? ''), a.note ?? '']);
    }
    const csv = rows.map((r) => r.map((c) => `"${String(c).replaceAll('"', '""')}"`).join(',')).join('\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'applications-export.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  },

  getReminders: () => delay({ ...mutable.reminders }),
  putReminders: (body: ReminderSettings) => {
    mutable.reminders = { ...body };
    return delay({ ...mutable.reminders });
  },

  getLLMConfig: () => delay({ ...mutable.llm }),
  putLLMConfig: (body: LLMConfigUpdate) => {
    mutable.llm = {
      ...mutable.llm,
      ...Object.fromEntries(Object.entries(body).filter(([, v]) => v !== undefined)),
      api_key_last4: body.api_key ? body.api_key.slice(-4) : mutable.llm.api_key_last4,
    };
    return delay({ ...mutable.llm });
  },
  testLLMConfig: () => delay({ ok: false, error: 'mock 环境不支持真实 LLM 连接测试' } as LLMConfigTestResult),
};

export function isMockMode(): boolean {
  if (import.meta.env.VITE_MOCK === '1') return true;
  if (typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('mock') === '1') return true;
  return false;
}
