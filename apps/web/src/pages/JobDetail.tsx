import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, type ApplicationStatus, type HistorySource } from '../api';
import Modal from '../components/Modal';
import ApplyTrigger from '../components/ApplyTrigger';
import { ConfirmBadge, StatusBadge } from '../components/Badges';
import { EmptyState, Skeleton } from '../components/Feedback';
import { manualTargets } from '../utils/status';
import { fmtDateTime } from '../utils/time';

const SOURCE_LABEL: Record<HistorySource, string> = { ui: '手动', email: '邮箱识别', agent: 'Agent 回写' };

/** D-05 岗位详情（FR-3/30/31，BR-10/11）；历史/确认记录/邮件回溯接契约 v2 读侧端点 */
export default function JobDetail() {
  const { id = '' } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const job = useQuery({ queryKey: ['jobs', id], queryFn: () => api.getJob(id), retry: false });
  const apps = useQuery({ queryKey: ['applications'], queryFn: () => api.listApplications(), retry: false });
  const schedule = useQuery({ queryKey: ['schedule'], queryFn: () => api.getSchedule(), retry: false });

  const [tab, setTab] = useState<'history' | 'schedule' | 'mail' | 'confirm'>('history');
  const [statusMenu, setStatusMenu] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const app = apps.data?.items.find((a) => a.job_id === id);

  // 读侧三端点（FR-31/24/43，契约 v2）：仅在有投递记录时查询
  const history = useQuery({
    queryKey: ['applications', app?.id, 'history'],
    queryFn: () => api.getApplicationHistory(app!.id),
    enabled: !!app, retry: false,
  });
  const confirmations = useQuery({
    queryKey: ['applications', app?.id, 'confirmations'],
    queryFn: () => api.getApplicationConfirmations(app!.id),
    enabled: !!app, retry: false,
  });
  const emails = useQuery({
    queryKey: ['applications', app?.id, 'emails'],
    queryFn: () => api.getApplicationEmails(app!.id),
    enabled: !!app, retry: false,
  });

  const moveMut = useMutation({
    mutationFn: ({ appId, status }: { appId: string; status: ApplicationStatus }) => api.updateApplication(appId, { status }),
    onSuccess: () => {
      setStatusMenu(false); setError(null);
      qc.invalidateQueries({ queryKey: ['applications'] });
    },
    onError: (e) => {
      setStatusMenu(false);
      // AC-6 用户可见面：状态机 409 时给出提示
      setError(e instanceof ApiError && e.status === 409
        ? `状态推进被状态机拒绝（${e.message}）。当前状态已保留。`
        : e instanceof ApiError ? e.message : String(e));
    },
  });

  if (job.isLoading) return <Skeleton lines={5} />;
  if (job.isError || !job.data) return <EmptyState icon="⚠️" text="岗位不存在或加载失败" action={<Link to="/board">返回看板</Link>} />;
  const j = job.data;
  const events = (schedule.data?.items ?? []).filter((e) => e.application_id === app?.id);

  return (
    <div>
      {/* 摘要条 */}
      <div className="card section" style={{ padding: 16, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <Link to="/board" className="btn-link">← 看板</Link>
        <strong style={{ fontSize: 16 }}>{j.company} · {j.title}</strong>
        {app && (
          <button onClick={() => setStatusMenu(true)} style={{ border: 'none', background: 'none', padding: 0 }} title="点击手动推进状态（FR-30）">
            <StatusBadge status={app.status} />
          </button>
        )}
        {(!app || app.status === '待投递') && (
          <ApplyTrigger jobId={id} onApplied={(cfmId) => nav(`/confirmations/${cfmId}`)} buttonClass="btn-primary" />
        )}
        {j.jd_url && <a href={j.jd_url} target="_blank" rel="noreferrer">JD 链接 ↗</a>}
        {j.channel && <span className="badge" style={{ background: 'var(--st-pending-bg)', color: 'var(--st-pending)' }}>{j.channel}</span>}
        {j.deadline && <span style={{ color: 'var(--color-text-secondary)' }} className="num">网申截止 {fmtDateTime(j.deadline)}</span>}
      </div>

      {error && <div className="banner banner-info">已按你的手动更新保留当前状态（BR-11）：{error}</div>}

      <div className="detail-grid">
        <div className="card" style={{ padding: 20 }}>
          <div className="tabs">
            {([['history', '状态历史'], ['schedule', '关联日程'], ['mail', '邮件回溯'], ['confirm', '确认记录']] as const).map(([k, label]) => (
              <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{label}</button>
            ))}
          </div>

          {tab === 'history' && (
            !app ? <EmptyState text="该岗位暂无投递记录" />
              : history.isLoading ? <Skeleton lines={3} />
              : history.isError ? <EmptyState icon="⚠️" text="状态历史加载失败" />
              : (
                <div className="timeline">
                  {(history.data?.items ?? []).map((h, i) => (
                    <div key={i} className="timeline-item">
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                        {h.from_status && <><StatusBadge status={h.from_status} /><span>→</span></>}
                        <StatusBadge status={h.to_status} />
                        <span className="badge" style={{ background: 'var(--st-pending-bg)', color: 'var(--color-text-secondary)' }}>
                          来源：{SOURCE_LABEL[h.source]}
                        </span>
                        {h.rejected && (
                          <span className="badge" title="该自动写入被状态机拒绝，未生效（AC-6 排查）"
                            style={{ background: 'var(--st-rejected-bg)', color: 'var(--st-rejected)' }}>已被状态机拒绝</span>
                        )}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>{fmtDateTime(h.created_at)}</div>
                    </div>
                  ))}
                  {(history.data?.items.length ?? 0) === 0 && <EmptyState text="暂无状态历史" />}
                </div>
              )
          )}
          {tab === 'schedule' && (
            events.length === 0 ? <EmptyState text="暂无关联日程" /> : events.map((e) => (
              <div key={e.id} className="card" style={{ padding: 12, marginBottom: 8 }}>
                <span className="badge" style={{ background: 'var(--st-written-bg)', color: 'var(--st-written)' }}>{e.type}</span>{' '}
                <strong>{e.title}</strong>
                <div style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>{fmtDateTime(e.start_time)} · {e.location ?? e.meeting_link ?? ''} · <Link to="/schedule">日程 →</Link></div>
              </div>
            ))
          )}
          {tab === 'mail' && (
            !app ? <EmptyState text="该岗位暂无投递记录" />
              : emails.isLoading ? <Skeleton lines={3} />
              : emails.isError ? <EmptyState icon="⚠️" text="邮件回溯加载失败" />
              : (emails.data?.items.length ?? 0) === 0 ? <EmptyState icon="✉️" text="暂无匹配到该岗位的邮件事件" />
              : (emails.data?.items ?? []).map((e) => (
                <div key={e.id} className="card" style={{ padding: 12, marginBottom: 8 }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span className="badge" style={{ background: 'var(--st-submitted-bg)', color: 'var(--color-info)' }}>{e.type}</span>
                    <strong>{e.email_subject ?? '（无主题）'}</strong>
                    <span className="badge" style={{ background: 'var(--st-pending-bg)', color: 'var(--color-text-secondary)' }}>{e.status}</span>
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 4 }}>
                    发件人：{e.email_sender ?? '—'} · 收件于 {fmtDateTime(e.email_received_at)}
                    {e.event_time && <> · 事件时间 {fmtDateTime(e.event_time)}</>}
                  </div>
                </div>
              ))
          )}
          {tab === 'confirm' && (
            !app ? <EmptyState text="该岗位暂无投递记录" />
              : confirmations.isLoading ? <Skeleton lines={3} />
              : confirmations.isError ? <EmptyState icon="⚠️" text="确认记录加载失败" />
              : (confirmations.data?.items.length ?? 0) === 0 ? <EmptyState text="暂无确认记录" />
              : (confirmations.data?.items ?? []).map((c) => (
                <div key={c.id} className="card" style={{ padding: 12, marginBottom: 8, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                  <ConfirmBadge status={c.status} />
                  <span style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
                    创建于 {fmtDateTime(c.created_at)}{c.confirmed_at ? ` · 确认于 ${fmtDateTime(c.confirmed_at)}` : ''}
                  </span>
                  {c.submit_result === 'success' && <span className="badge" style={{ background: 'var(--st-offer-bg)', color: 'var(--color-success)' }}>提交成功</span>}
                  {c.submit_result === 'failed' && (
                    <span className="badge" title={c.fail_reason ?? ''} style={{ background: 'var(--st-rejected-bg)', color: 'var(--st-rejected)' }}>提交失败</span>
                  )}
                  <Link to={`/confirmations/${c.id}`} style={{ marginLeft: 'auto', fontSize: 13 }}>查看留档 →</Link>
                </div>
              ))
          )}
        </div>

        {/* 右侧栏 */}
        <div className="card" style={{ padding: 16 }}>
          <h3 className="section-title">岗位信息</h3>
          <p style={{ margin: '4px 0' }}><strong>{j.company}</strong></p>
          <p style={{ margin: '4px 0' }}>{j.title}</p>
          <p style={{ margin: '4px 0', color: 'var(--color-text-secondary)' }}>{j.location ?? '地点未知'}</p>
          <p style={{ margin: '4px 0', color: 'var(--color-text-secondary)', fontSize: 12 }}>创建于 {fmtDateTime(j.created_at)}</p>
          {app && <p style={{ margin: '8px 0 0', fontSize: 12, color: 'var(--color-text-secondary)' }}>简历版本：{app.resume_id}（FR-3 回溯）</p>}
        </div>
      </div>

      {statusMenu && app && (
        <Modal title="手动更新状态" onClose={() => setStatusMenu(false)}>
          <p style={{ color: 'var(--color-text-secondary)' }}>手动更新标记来源为「手动」（BR-11），自动来源后续不得回退该状态。</p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {manualTargets(app.status).map((s) => (
              <button key={s} disabled={moveMut.isPending} onClick={() => moveMut.mutate({ appId: app.id, status: s })}>{s}</button>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}
