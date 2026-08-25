/**
 * Mock 适配器 —— 后端（S3b）未就绪时的先行开发数据源。
 * 与冻结契约同形：mock 覆盖契约 19 端点的全部语义（含 BR-3 重复提示、
 * 幂等 200/201、token 签发/过期/重新放行），另补齐契约缺口的演示数据
 * （待确认投递列表），该缺口已在代码与交付说明中标注、待契约扩展。
 * 启用：URL 加 ?mock=1 或环境变量 VITE_MOCK=1。
 */
import type {
  ApiKeyCreated, ApiKeyInfo, Application, ApplicationList, ApplicationStatus,
  ApplicationUpdate, ConfirmationConfirmed, ConfirmationCreate, ConfirmationCreated,
  ConfirmationView, CreateJobResult, EmailEventList, Job, JobCreate, JobList,
  JobUpdate, PendingConfirmation, Profile, ProfileResponse, ScheduleEventList,
} from './types';
import { ApiError, type AutohuntApi } from './client';

const now = () => new Date().toISOString();
const hoursAgo = (h: number) => new Date(Date.now() - h * 3600_000).toISOString();
const hoursLater = (h: number) => new Date(Date.now() + h * 3600_000).toISOString();
const uid = () => Math.random().toString(36).slice(2, 10);

interface MockConfirmation {
  id: string;
  application_id: string;
  request_id: string;
  fields: Record<string, string>;
  status: '待确认' | '已确认' | '已驳回' | '已超时关闭';
  confirmed_fields?: Record<string, string>;
  submit_token?: string | null;
  expires_at?: string;
  consumed?: boolean;
  reason?: string | null;
  submit_result?: { result: 'success' | 'failed'; fail_reason?: string | null; submitted_at: string } | null;
  created_at: string;
}

const db = {
  keys: [
    { id: 'key-1', name: '本机 Agent CLI', prefix: 'ah_live_ab12', created_at: hoursAgo(72), last_used_at: hoursAgo(3) },
  ] as ApiKeyInfo[],
  profile: {
    name: '张三', phone: '13800001234', email: 'qiuzhi@example.com',
    educations: [{ school: '某大学', degree: '本科', major: '计算机科学与技术', start_date: '2022-09', end_date: '2026-06' }],
    experiences: [{ company: '某科技公司', position: '后端开发实习生', start_date: '2025-06', end_date: '2025-09', description: '负责订单服务接口开发' }],
    skills: ['Java', 'Python', 'MySQL', 'Redis'],
    awards: ['校级一等奖学金'],
    expected_city: '杭州', expected_position: '后端开发工程师',
    resume_id: 'resume-1', resume_version: 3,
  } as Profile,
  jobs: [
    { id: 'job-1', company: '阿里巴巴', title: '后端开发工程师', jd_url: 'https://campus.alibaba.com/position/1', location: '杭州', channel: '公司官网', deadline: hoursLater(60), created_at: hoursAgo(100) },
    { id: 'job-2', company: '字节跳动', title: '后端开发工程师', jd_url: 'https://jobs.bytedance.com/1', location: '北京', channel: '公司官网', deadline: hoursLater(20), created_at: hoursAgo(90) },
    { id: 'job-3', company: '腾讯', title: '后台开发', jd_url: 'https://careers.tencent.com/1', location: '深圳', channel: '内推', deadline: hoursLater(200), created_at: hoursAgo(80) },
    { id: 'job-4', company: '美团', title: '后端开发', jd_url: null, location: '北京', channel: '公司官网', deadline: null, created_at: hoursAgo(70) },
    { id: 'job-5', company: '百度', title: '服务端研发', jd_url: null, location: '北京', channel: '公司官网', deadline: null, created_at: hoursAgo(60) },
    { id: 'job-6', company: '网易', title: 'Java 开发', jd_url: null, location: '杭州', channel: '公司官网', deadline: null, created_at: hoursAgo(50) },
  ] as Job[],
  applications: [
    { id: 'app-1', job_id: 'job-1', resume_id: 'resume-1', applied_at: null, status: '待投递' },
    { id: 'app-2', job_id: 'job-2', resume_id: 'resume-1', applied_at: hoursAgo(48), status: '已投递' },
    { id: 'app-3', job_id: 'job-3', resume_id: 'resume-1', applied_at: hoursAgo(96), status: '笔试' },
    { id: 'app-4', job_id: 'job-4', resume_id: 'resume-1', applied_at: hoursAgo(120), status: '面试', interview_round: 2 },
    { id: 'app-5', job_id: 'job-5', resume_id: 'resume-1', applied_at: hoursAgo(200), status: '未通过' },
    { id: 'app-6', job_id: 'job-6', resume_id: 'resume-1', applied_at: hoursAgo(24), status: '已投递' },
  ] as Application[],
  confirmations: [
    {
      id: 'cfm-1', application_id: 'app-1', request_id: 'req-mock-1',
      fields: { 姓名: '张三', 电话: '13800001234', 邮箱: 'qiuzhi@example.com', 学校: '某大学', 专业: '计算机科学与技术', 期望城市: '杭州' },
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
      status: '已确认', confirmed_fields: { 姓名: '张三', 电话: '13800001234' },
      submit_token: null, expires_at: hoursAgo(1), consumed: true,
      submit_result: { result: 'failed', fail_reason: '目标站点验证码拦截，需人工处理', submitted_at: hoursAgo(1) },
      created_at: hoursAgo(50),
    },
  ] as MockConfirmation[],
  events: [
    { id: 'evt-1', type: '笔试', event_time: hoursLater(30), location: null, meeting_link: 'https://meeting.example.com/abc', company: '阿里巴巴', matched_job_id: 'job-1', status: '待确认', created_at: hoursAgo(5) },
    { id: 'evt-2', type: '面试', event_time: hoursLater(80), location: '北京市海淀区某大厦 3F', meeting_link: null, company: '美团', matched_job_id: 'job-4', status: '待确认', created_at: hoursAgo(10) },
  ],
  schedule: [
    { id: 'sch-1', application_id: 'app-3', source_event_id: null, title: '腾讯 后台开发 笔试', type: '笔试', start_time: hoursLater(26), end_time: hoursLater(28), location: null, meeting_link: 'https://meeting.example.com/tx' },
    { id: 'sch-2', application_id: 'app-4', source_event_id: null, title: '美团 后端开发 三面', type: '面试', start_time: hoursLater(70), end_time: hoursLater(71), location: '线上', meeting_link: 'https://meeting.example.com/mt' },
  ],
} as const;

const mutable = {
  keys: [...db.keys] as ApiKeyInfo[],
  jobs: [...db.jobs] as Job[],
  applications: [...db.applications] as Application[],
  confirmations: db.confirmations.map((c) => ({ ...c })) as MockConfirmation[],
  events: db.events.map((e) => ({ ...e })) as EmailEventList['items'][number][],
};

const delay = <T>(v: T): Promise<T> => new Promise((r) => setTimeout(() => r(v), 120));

function confirmationView(c: MockConfirmation): ConfirmationView {
  if (c.status === '待确认') return { status: '待确认' };
  if (c.status === '已确认') {
    return {
      status: '已确认',
      confirmed_fields: c.confirmed_fields ?? {},
      submit_token: c.consumed ? null : (c.submit_token ?? null),
      expires_at: c.expires_at ?? now(),
    };
  }
  return { status: c.status, reason: c.reason ?? null };
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

  getProfile: () => delay(db.profile as ProfileResponse),

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
    return delay(app);
  },
  listApplications: (f) => delay({
    items: mutable.applications.filter((a) => {
      if (f?.status && a.status !== f.status) return false;
      if (f?.company && !mutable.jobs.find((j) => j.id === a.job_id)?.company.includes(f.company)) return false;
      if (f?.channel && mutable.jobs.find((j) => j.id === a.job_id)?.channel !== f.channel) return false;
      return true;
    }),
    next_cursor: null,
  } as ApplicationList),
  updateApplication: (id, body: ApplicationUpdate) => {
    const a = mutable.applications.find((x) => x.id === id);
    if (!a) return Promise.reject(new ApiError(404, 'NOT_FOUND', '投递不存在'));
    if (body.status != null) a.status = body.status as ApplicationStatus;
    if (body.note !== undefined && body.note !== null) a.note = body.note;
    if (body.interview_round !== undefined) a.interview_round = body.interview_round;
    return delay(a);
  },

  createConfirmation: (body: ConfirmationCreate) => {
    const hit = mutable.confirmations.find((c) => c.request_id === body.request_id);
    if (hit) return delay({ confirmation_id: hit.id, status: hit.status } as ConfirmationCreated); // 幂等命中
    const c: MockConfirmation = {
      id: `cfm-${uid()}`, application_id: body.application_id, request_id: body.request_id,
      fields: body.fields, status: '待确认', created_at: now(),
    };
    mutable.confirmations.push(c);
    return delay({ confirmation_id: c.id, status: '待确认' } as ConfirmationCreated);
  },
  getConfirmation: (id) => {
    const c = mutable.confirmations.find((x) => x.id === id);
    return c ? delay(confirmationView(c)) : Promise.reject(new ApiError(404, 'NOT_FOUND', '确认任务不存在'));
  },
  confirm: (id, body) => {
    const c = mutable.confirmations.find((x) => x.id === id);
    if (!c) return Promise.reject(new ApiError(404, 'NOT_FOUND', '确认任务不存在'));
    if (c.status !== '待确认') return Promise.reject(new ApiError(409, 'STATE_CONFLICT', '仅待确认状态可确认'));
    c.status = '已确认';
    c.confirmed_fields = body.confirmed_fields;
    c.submit_token = `st_${uid()}${uid()}`;
    c.expires_at = hoursLater(0.5);
    c.consumed = false;
    return delay(confirmationView(c) as ConfirmationConfirmed);
  },
  reject: (id, body) => {
    const c = mutable.confirmations.find((x) => x.id === id);
    if (!c) return Promise.reject(new ApiError(404, 'NOT_FOUND', '确认任务不存在'));
    if (c.status !== '待确认') return Promise.reject(new ApiError(409, 'STATE_CONFLICT', '仅待确认状态可驳回'));
    c.status = '已驳回';
    c.reason = body.reason ?? null;
    return delay(confirmationView(c));
  },
  reissue: (id) => {
    const c = mutable.confirmations.find((x) => x.id === id);
    if (!c) return Promise.reject(new ApiError(404, 'NOT_FOUND', '确认任务不存在'));
    if (c.status !== '已确认') return Promise.reject(new ApiError(409, 'STATE_CONFLICT', '仅已确认状态可重新放行'));
    if (c.submit_token && !c.consumed) return Promise.reject(new ApiError(409, 'STATE_CONFLICT', 'token 仍有效，无需重新放行'));
    c.submit_token = `st_${uid()}${uid()}`;
    c.expires_at = hoursLater(0.5);
    c.consumed = false;
    return delay(confirmationView(c) as ConfirmationConfirmed);
  },

  listPendingEvents: () => delay({ items: mutable.events.filter((e) => e.status === '待确认'), next_cursor: null } as EmailEventList),
  getSchedule: () => delay({ items: [...db.schedule] } as ScheduleEventList),

  // [契约缺口] 演示数据：契约无列表端点，真实模式会 501
  listPendingConfirmations: () => delay(
    mutable.confirmations
      .filter((c) => c.status === '待确认')
      .map((c) => {
        const app = mutable.applications.find((a) => a.id === c.application_id);
        const job = app && mutable.jobs.find((j) => j.id === app.job_id);
        return {
          confirmation_id: c.id, application_id: c.application_id,
          company: job?.company ?? '未知公司', title: job?.title ?? '未知岗位', created_at: c.created_at,
        } as PendingConfirmation;
      }),
  ),
  // [契约缺口] 确认单完整视图（mock 提供全量演示数据）
  getConfirmationDetail: (id) => {
    const c = mutable.confirmations.find((x) => x.id === id);
    if (!c) return Promise.reject(new ApiError(404, 'NOT_FOUND', '确认任务不存在'));
    return delay({
      id: c.id, application_id: c.application_id, status: c.status,
      fields: c.fields, confirmed_fields: c.confirmed_fields,
      submit_token: c.consumed ? null : (c.submit_token ?? null),
      expires_at: c.expires_at, reason: c.reason ?? null,
      submit_result: c.submit_result ?? null, created_at: c.created_at,
      snapshotUnavailable: false,
    });
  },
  // [契约缺口] 手动关闭（标记已超时关闭，PRD §12 主动出口）
  closeConfirmation: (id) => {
    const c = mutable.confirmations.find((x) => x.id === id);
    if (!c) return Promise.reject(new ApiError(404, 'NOT_FOUND', '确认任务不存在'));
    if (c.status !== '待确认') return Promise.reject(new ApiError(409, 'STATE_CONFLICT', '仅待确认状态可关闭'));
    c.status = '已超时关闭';
    return delay(undefined);
  },
};

export function isMockMode(): boolean {
  if (import.meta.env.VITE_MOCK === '1') return true;
  if (typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('mock') === '1') return true;
  return false;
}
