import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, type ApplicationStatus } from '../api';
import Modal from '../components/Modal';
import { StatusBadge } from '../components/Badges';
import { EmptyState, Skeleton } from '../components/Feedback';
import { manualTargets } from '../utils/status';
import { fmtDateTime } from '../utils/time';

/** D-05 岗位详情（FR-3/30/31，BR-10/11） */
export default function JobDetail() {
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const job = useQuery({ queryKey: ['jobs', id], queryFn: () => api.getJob(id), retry: false });
  const apps = useQuery({ queryKey: ['applications'], queryFn: () => api.listApplications(), retry: false });
  const schedule = useQuery({ queryKey: ['schedule'], queryFn: () => api.getSchedule(), retry: false });

  const [tab, setTab] = useState<'history' | 'schedule' | 'mail' | 'confirm'>('history');
  const [statusMenu, setStatusMenu] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const moveMut = useMutation({
    mutationFn: ({ appId, status }: { appId: string; status: ApplicationStatus }) => api.updateApplication(appId, { status }),
    onSuccess: () => { setStatusMenu(false); setError(null); qc.invalidateQueries({ queryKey: ['applications'] }); },
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
  const app = apps.data?.items.find((a) => a.job_id === j.id);
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
            <div>
              <div className="banner banner-info" style={{ marginBottom: 12 }}>
                契约缺口：状态历史（FR-31，含来源标记 BR-11）端点未在冻结契约中，待扩展后此处展示时间线。
              </div>
              {app && (
                <div className="timeline">
                  <div className="timeline-item">
                    <div><StatusBadge status={app.status} /></div>
                    <div style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>当前状态 · {app.applied_at ? `投递于 ${fmtDateTime(app.applied_at)}` : '尚未投递'}</div>
                  </div>
                </div>
              )}
            </div>
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
            <div className="banner banner-info">契约缺口：原始邮件回溯（FR-43）端点未在冻结契约中（email_event 仅返回元数据，无原文读取端点），待扩展。</div>
          )}
          {tab === 'confirm' && (
            <div className="banner banner-info">契约缺口：按投递查询确认流历史（FR-23/24 留档）的端点未在冻结契约中，待扩展。单条确认任务可从工作台进入查看。</div>
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
