import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  api, ApiError,
  type CrawlFieldConfidence, type CrawlResult, type CrawlResultFields, type CrawlSource,
  type Job, type JobCreate,
} from '../api';
import Modal from '../components/Modal';
import { Skeleton } from '../components/Feedback';

/**
 * D-04 录入岗位（PROX-19 网页抓取入库）：
 * - `?prefill=<base64url(CrawlResult)>`：扩展跳转链路，解码后直接进预览（AC-9）
 * - `?url=<encoded>`：粘贴链接入口，进入即调用 /jobs/crawl 触发解析（AC-1）
 * - 无参数：展示粘贴链接输入 + 手动录入表单
 * 抓取结果绝不自动入库；保存走 POST /jobs，命中 duplicate_of 给 更新/修改后新建/取消 三选（AC-2）。
 */

const FIELD_LABELS: Record<string, string> = {
  company: '公司', title: '岗位名称', jd_url: 'JD 链接', location: '工作地点',
  channel: '来源渠道', deadline: '网申截止日期', description: '岗位描述',
};

const CONFIDENCE_STYLE: Record<CrawlFieldConfidence, { fg: string; bg: string; label: string }> = {
  high: { fg: 'var(--color-success)', bg: 'var(--st-offer-bg)', label: '置信度：高' },
  medium: { fg: 'var(--color-warning)', bg: 'var(--st-written-bg)', label: '置信度：中' },
  low: { fg: 'var(--color-danger)', bg: 'var(--st-rejected-bg)', label: '置信度：低' },
  manual: { fg: 'var(--color-text-secondary)', bg: 'var(--st-closed-bg)', label: '手动录入' },
};

/** 后端抓取结果 channel 回填的是 source 枚举（技设 §3.3），映射到看板/表单的渠道词表 */
const CHANNEL_FROM_SOURCE: Record<string, string> = {
  boss: 'BOSS直聘',
  nowcoder: '牛客',
  official: '公司官网',
  unknown: '', // 未知站点渠道不可知，留空由用户选择
};

export function displayChannel(channel: string | null | undefined): string {
  if (!channel) return '';
  return CHANNEL_FROM_SOURCE[channel] ?? channel;
}

/** 由 URL 猜测站点来源：boss/nowcoder 走结构化解析，其余交给后端 LLM 兜底 */
export function guessSource(url: string): CrawlSource {
  if (/zhipin\.com/i.test(url)) return 'boss';
  if (/nowcoder\.com/i.test(url)) return 'nowcoder';
  return 'unknown';
}

/** 扩展跳转入口：base64url(UTF-8 JSON) → CrawlResult */
export function decodePrefill(encoded: string): CrawlResult {
  const b64 = encoded.replace(/-/g, '+').replace(/_/g, '/');
  const bin = atob(b64);
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes)) as CrawlResult;
}

function newRequestId(): string {
  const id = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  return `ui-${id}`;
}

/** RFC3339 → datetime-local 输入值（本地时区） */
function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

interface Draft {
  company: string;
  title: string;
  jd_url: string;
  location: string;
  channel: string;
  deadline: string; // datetime-local
  description: string;
  confidence: CrawlFieldConfidence | '';
  // requirements 已知键拆为独立输入；未知键在 extras 中原样保留
  salary: string;
  degree: string;
  experience: string;
  tags: string;
  extras: Record<string, unknown>;
}

const EMPTY_DRAFT: Draft = {
  company: '', title: '', jd_url: '', location: '', channel: '', deadline: '',
  description: '', confidence: '', salary: '', degree: '', experience: '', tags: '', extras: {},
};

function draftFromFields(fields: CrawlResultFields): Draft {
  const req = { ...(fields.requirements ?? {}) } as Record<string, unknown>;
  const { salary, degree, experience, tags, ...extras } = req;
  return {
    company: fields.company ?? '',
    title: fields.title ?? '',
    jd_url: fields.jd_url ?? '',
    location: fields.location ?? '',
    channel: displayChannel(fields.channel),
    deadline: toLocalInput(fields.deadline),
    description: fields.description ?? '',
    confidence: fields.confidence ?? '',
    salary: typeof salary === 'string' ? salary : '',
    degree: typeof degree === 'string' ? degree : '',
    experience: typeof experience === 'string' ? experience : '',
    tags: Array.isArray(tags) ? tags.join('，') : typeof tags === 'string' ? tags : '',
    extras,
  };
}

type Phase =
  | { kind: 'idle' }
  | { kind: 'loading'; url: string }
  | { kind: 'failed'; url: string; status: string; message: string; retryable: boolean }
  | { kind: 'ready' };

function failMessage(r: CrawlResult): string {
  if (r.error_message) return r.error_message;
  switch (r.status) {
    case 'unsupported_site': return '暂不支持该站点的自动解析，已为你保留链接，请手动补全岗位信息。';
    case 'fetch_failed': return '目标页面抓取失败（可能被反爬拦截或需登录），可重试或手动录入。';
    case 'timeout': return '解析超时，请重试或手动录入。';
    case 'parse_failed': return '页面内容解析失败，请重试或手动录入。';
    default: return '解析失败，请重试或手动录入。';
  }
}

export default function JobNew() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [params] = useSearchParams();

  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [missing, setMissing] = useState<string[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [resultStatus, setResultStatus] = useState<CrawlResult['status'] | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);
  const [urlInput, setUrlInput] = useState('');
  const [dup, setDup] = useState<{ id: string; job: Job } | null>(null);
  const [editHint, setEditHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 入口参数只消费一次；StrictMode dev 下 effect 双跑会导致 ?url= 入口重复抓取（2 条 crawl_attempt + 双倍限流计数）
  const entryConsumed = useRef(false);

  const applyResult = (result: CrawlResult, fallbackUrl = '') => {
    setResultStatus(result.status);
    setTruncated(result.content_truncated);
    setRequestId(result.request_id ?? null);
    setMissing(result.missing_fields ?? []);
    if ((result.status === 'ok' || result.status === 'partial') && result.fields) {
      setDraft(draftFromFields(result.fields));
      setPhase({ kind: 'ready' });
      return;
    }
    // 失败态收敛进 CrawlResult.status（AC-3/AC-4）：给重试与手动录入入口
    setPhase({
      kind: 'failed',
      url: result.fields?.jd_url ?? fallbackUrl,
      status: result.status,
      message: failMessage(result),
      retryable: result.status !== 'unsupported_site',
    });
  };

  const startCrawl = async (url: string) => {
    setPhase({ kind: 'loading', url });
    setError(null);
    setEditHint(null);
    try {
      applyResult(await api.crawlJob({ url, source: guessSource(url), request_id: newRequestId() }), url);
    } catch (e) {
      // HTTP 层失败：429 限流走信封 RATE_LIMITED；401 提示去设置页检查
      const message = e instanceof ApiError && e.status === 429
        ? '抓取频率超限（10 次/分钟），请稍后重试。'
        : e instanceof ApiError && e.status === 401
          ? '鉴权失败（401），请刷新页面重建会话后重试。'
          : e instanceof ApiError ? e.message : '网络错误，请确认后端已启动。';
      setPhase({ kind: 'failed', url, status: e instanceof ApiError ? String(e.status) : 'network', message, retryable: true });
    }
  };

  /** AC-3/AC-4 手动录入口：预填链接，confidence 标记 manual */
  const enterManual = (url: string) => {
    setDraft({ ...EMPTY_DRAFT, jd_url: url, confidence: 'manual' });
    setMissing([]);
    setResultStatus(null);
    setTruncated(false);
    setPhase({ kind: 'ready' });
  };

  // 首帧处理入口参数：prefill 优先，其次 url
  useEffect(() => {
    if (entryConsumed.current) return;
    entryConsumed.current = true;
    const prefill = params.get('prefill');
    const url = params.get('url');
    if (prefill) {
      try {
        applyResult(decodePrefill(prefill));
      } catch {
        setPhase({ kind: 'failed', url: '', status: 'prefill_invalid', message: '预览数据无法解析（prefill 参数损坏），请从扩展重新发起抓取，或手动录入。', retryable: false });
      }
    } else if (url) {
      void startCrawl(url);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅首帧消费入口参数
  }, []);

  const buildRequirements = (): Record<string, unknown> | null => {
    const r: Record<string, unknown> = { ...draft.extras };
    if (draft.salary.trim()) r.salary = draft.salary.trim();
    if (draft.degree.trim()) r.degree = draft.degree.trim();
    if (draft.experience.trim()) r.experience = draft.experience.trim();
    const tags = draft.tags.split(/[,，]/).map((t) => t.trim()).filter(Boolean);
    if (tags.length) r.tags = tags;
    return Object.keys(r).length ? r : null;
  };

  const buildPayload = (): JobCreate => ({
    company: draft.company.trim(),
    title: draft.title.trim(),
    jd_url: draft.jd_url.trim() || null,
    location: draft.location.trim() || null,
    channel: draft.channel || null,
    deadline: draft.deadline ? new Date(draft.deadline).toISOString() : null,
    description: draft.description.trim() || null,
    requirements: buildRequirements(),
    confidence: draft.confidence || (resultStatus ? null : 'manual'),
    // 保存时透传 request_id，后端回填 crawl_attempt.job_id（AC-2 关联记录）
    crawl_request_id: requestId ?? undefined,
  });

  const saveMut = useMutation({
    mutationFn: () => api.createJob(buildPayload()),
    onSuccess: (r) => {
      // BR-3：200 命中重复 → 三选，不拦截
      if (r.kind === 'duplicate') { setDup({ id: r.duplicateOf, job: r.job }); return; }
      qc.invalidateQueries({ queryKey: ['jobs'] });
      nav('/board');
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : String(e)),
  });

  const updateMut = useMutation({
    mutationFn: (id: string) => api.updateJob(id, buildPayload()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['jobs'] });
      nav('/board');
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : String(e)),
  });

  // AC-6：company/title 为空时保存置灰
  const canSave = !!draft.company.trim() && !!draft.title.trim();
  const miss = (key: string) => missing.includes(key);
  const missStyle = (key: string) => (miss(key) ? { color: 'var(--color-warning)' } : undefined);
  const conf = draft.confidence ? CONFIDENCE_STYLE[draft.confidence] : null;

  return (
    <div>
      <div className="toolbar">
        <h2 className="page-title" style={{ margin: 0 }}>录入岗位</h2>
        <Link to="/board" style={{ marginLeft: 'auto' }}>返回看板</Link>
      </div>

      {phase.kind === 'idle' && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="section-title">粘贴链接抓取</div>
          <p style={{ color: 'var(--color-text-secondary)', fontSize: 13 }}>
            支持 BOSS 直聘 / 牛客结构化解析，公司官网等站点走 LLM 兜底；解析结果需你确认后才会入库。
          </p>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              aria-label="职位链接" style={{ flex: 1 }}
              placeholder="https://www.zhipin.com/job_detail/… 或 https://www.nowcoder.com/jobs/…"
              value={urlInput} onChange={(e) => setUrlInput(e.target.value)}
            />
            <button className="btn-primary" disabled={!urlInput.trim()} onClick={() => void startCrawl(urlInput.trim())}>开始解析</button>
          </div>
        </div>
      )}

      {phase.kind === 'loading' && (
        <div>
          <div className="banner banner-info" style={{ marginBottom: 12 }}>正在解析职位页面（最长约 30 秒）…</div>
          <Skeleton lines={5} />
        </div>
      )}

      {phase.kind === 'failed' && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="banner banner-danger" style={{ margin: 0 }}>{phase.message}</div>
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            {phase.retryable && phase.url && <button onClick={() => void startCrawl(phase.url)}>重试解析</button>}
            <button className="btn-primary" onClick={() => enterManual(phase.url)}>手动录入</button>
          </div>
        </div>
      )}

      {(phase.kind === 'idle' || phase.kind === 'ready') && (
        <div className="card">
          {phase.kind === 'ready' && resultStatus === 'partial' && missing.length > 0 && (
            <div className="banner banner-warning" style={{ marginBottom: 12 }}>
              以下字段未能自动解析，请手动补全：{missing.map((f) => FIELD_LABELS[f] ?? f).join('、')}
            </div>
          )}
          {truncated && (
            <div className="banner banner-info" style={{ marginBottom: 12 }}>JD 原文过长已截断（约 8000 tokens），岗位描述可能不完整。</div>
          )}
          <div className="form-grid">
            <div className="form-field">
              <label style={missStyle('company')}>公司 <span className="required-mark">*</span>{miss('company') && '（待补全）'}</label>
              <input aria-label="公司" value={draft.company} onChange={(e) => setDraft({ ...draft, company: e.target.value })} />
            </div>
            <div className="form-field">
              <label style={missStyle('title')}>岗位名称 <span className="required-mark">*</span>{miss('title') && '（待补全）'}</label>
              <input aria-label="岗位名称" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
            </div>
            <div className="form-field">
              <label style={missStyle('jd_url')}>JD 链接{miss('jd_url') && '（待补全）'}</label>
              <input aria-label="JD 链接" value={draft.jd_url} onChange={(e) => setDraft({ ...draft, jd_url: e.target.value })} placeholder="https://" />
            </div>
            <div className="form-field">
              <label style={missStyle('location')}>工作地点{miss('location') && '（待补全）'}</label>
              <input aria-label="工作地点" value={draft.location} onChange={(e) => setDraft({ ...draft, location: e.target.value })} />
            </div>
            <div className="form-field">
              <label>来源渠道</label>
              <select aria-label="来源渠道" value={draft.channel} onChange={(e) => setDraft({ ...draft, channel: e.target.value })}>
                <option value="">未填写</option>
                <option>公司官网</option><option>内推</option><option>牛客</option><option>BOSS直聘</option><option>其他</option>
              </select>
            </div>
            <div className="form-field">
              <label style={missStyle('deadline')}>网申截止日期{miss('deadline') && '（待补全）'}</label>
              <input aria-label="网申截止日期" type="datetime-local" value={draft.deadline} onChange={(e) => setDraft({ ...draft, deadline: e.target.value })} />
            </div>
            <div className="form-field">
              <label>薪资</label>
              <input aria-label="薪资" value={draft.salary} onChange={(e) => setDraft({ ...draft, salary: e.target.value })} placeholder="如 25k-40k·14薪" />
            </div>
            <div className="form-field">
              <label>学历要求</label>
              <input aria-label="学历要求" value={draft.degree} onChange={(e) => setDraft({ ...draft, degree: e.target.value })} placeholder="如 本科" />
            </div>
            <div className="form-field">
              <label>经验要求</label>
              <input aria-label="经验要求" value={draft.experience} onChange={(e) => setDraft({ ...draft, experience: e.target.value })} placeholder="如 3-5年 / 应届" />
            </div>
            <div className="form-field">
              <label>技能标签</label>
              <input aria-label="技能标签" value={draft.tags} onChange={(e) => setDraft({ ...draft, tags: e.target.value })} placeholder="逗号分隔，如 Java，MySQL" />
            </div>
            <div className="form-field" style={{ gridColumn: '1 / -1' }}>
              <label style={missStyle('description')}>岗位描述{miss('description') && '（待补全）'}</label>
              <textarea aria-label="岗位描述" rows={6} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
            </div>
            <div className="form-field">
              <label>解析置信度</label>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <select aria-label="解析置信度" value={draft.confidence} onChange={(e) => setDraft({ ...draft, confidence: e.target.value as Draft['confidence'] })}>
                  <option value="">未标记</option>
                  <option value="high">高</option>
                  <option value="medium">中</option>
                  <option value="low">低</option>
                  <option value="manual">手动</option>
                </select>
                {conf && <span className="badge" style={{ color: conf.fg, background: conf.bg }}>{conf.label}</span>}
              </div>
            </div>
          </div>
          {editHint && <div className="banner banner-warning" style={{ marginTop: 12 }}>{editHint}</div>}
          {error && <div className="banner banner-danger" style={{ marginTop: 12 }}>{error}</div>}
          <div className="modal-actions">
            {!canSave && <span style={{ color: 'var(--color-warning)', fontSize: 13, marginRight: 'auto' }}>公司与岗位名称为必填，请补全后保存</span>}
            <button onClick={() => nav('/board')}>取消</button>
            <button className="btn-primary" disabled={!canSave || saveMut.isPending} onClick={() => { setError(null); saveMut.mutate(); }}>保存岗位</button>
          </div>
        </div>
      )}

      {/* BR-3 重复三选（AC-2）：更新已有岗位（PATCH 覆盖）/ 修改后新建 / 取消 */}
      {dup && (
        <Modal title="已存在同公司同岗位" onClose={() => setDup(null)}>
          <p>
            系统已存在「{dup.job.company} · {dup.job.title}」（创建于 {dup.job.created_at.slice(0, 10)}）。
            同公司 + 同岗位名会被识别为同一岗位（BR-3），请选择处理方式：
          </p>
          <div className="modal-actions">
            <button onClick={() => setDup(null)}>取消</button>
            <button onClick={() => {
              setDup(null);
              setEditHint('请修改公司或岗位名称后再次点击「保存岗位」，即可作为新岗位入库。');
            }}>修改后新建</button>
            <button className="btn-primary" disabled={updateMut.isPending} onClick={() => { setError(null); updateMut.mutate(dup.id); }}>更新已有岗位</button>
          </div>
        </Modal>
      )}
    </div>
  );
}
