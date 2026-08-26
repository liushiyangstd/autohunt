import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api';
import { EmptyState, Skeleton } from '../components/Feedback';
import { fmtDateTime, pendingDuration, withinHours } from '../utils/time';

/** D-01 工作台首页：待确认区（置顶）+ 近期日程 + 关键指标卡 */
export default function Dashboard() {
  const nav = useNavigate();
  const cfms = useQuery({ queryKey: ['confirmations', 'pending'], queryFn: () => api.listConfirmations({ status: '待确认' }), retry: false });
  const events = useQuery({ queryKey: ['events', 'pending'], queryFn: () => api.listPendingEvents(), retry: false });
  const apps = useQuery({ queryKey: ['applications'], queryFn: () => api.listApplications(), retry: false });
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => api.listJobs(), retry: false });
  const schedule = useQuery({ queryKey: ['schedule'], queryFn: () => api.getSchedule(), retry: false });
  // 关键指标卡（FR-52）：服务端口径，pending_items 与导航红点同口径
  const overview = useQuery({ queryKey: ['stats', 'overview'], queryFn: () => api.getStatsOverview(), retry: false });

  const pendingCfms = cfms.data?.items ?? [];
  const pendingEvents = events.data?.items ?? [];

  const jobOf = (appId: string) => {
    const app = apps.data?.items.find((a) => a.id === appId);
    return app ? jobs.data?.items.find((j) => j.id === app.job_id) : undefined;
  };

  const upcoming = (schedule.data?.items ?? [])
    .filter((e) => withinHours(e.start_time, 24 * 7))
    .sort((a, b) => a.start_time.localeCompare(b.start_time));

  const cards = overview.data ? [
    { label: '总投递数', value: overview.data.total_applications, to: '/board' },
    { label: '进行中', value: overview.data.in_progress, to: '/board' },
    { label: '待确认事项', value: overview.data.pending_items, to: '/' },
    { label: 'offer 数', value: overview.data.offers, to: '/stats' },
  ] : [
    // 统计端点未就绪（M5 实现中）时退化为本地计数，保证卡片可用
    { label: '总投递数', value: apps.data?.items.length ?? 0, to: '/board' },
    { label: '进行中', value: (apps.data?.items ?? []).filter((a) => ['已投递', '笔试', '面试', 'offer'].includes(a.status)).length, to: '/board' },
    { label: '待确认事项', value: pendingCfms.length + pendingEvents.length, to: '/' },
    { label: 'offer 数', value: (apps.data?.items ?? []).filter((a) => a.status === 'offer' || a.status === '已接受').length, to: '/stats' },
  ];

  return (
    <div>
      {/* 待确认区（置顶，warning 左边条） */}
      <section className="section">
        <h2 className="section-title">待确认投递 <span className="badge" style={{ background: 'var(--st-written-bg)', color: 'var(--color-warning)' }}>{pendingCfms.length}</span></h2>
        {cfms.isLoading ? <Skeleton /> : pendingCfms.length === 0 ? (
          <div className="card" style={{ padding: '10px 16px', color: 'var(--color-text-secondary)' }}>没有待确认事项 ✅</div>
        ) : (
          pendingCfms.map((c) => {
            const d = pendingDuration(c.created_at);
            const job = jobOf(c.application_id);
            return (
              <div key={c.id} className="card pending-card" style={{ marginBottom: 8 }}>
                <div style={{ flex: 1 }}>
                  <strong>{job ? `${job.company} · ${job.title}` : `投递 ${c.application_id}`}</strong>
                  <div style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>
                    Agent 创建于 {fmtDateTime(c.created_at)} ·{' '}
                    <span style={d.hours > 24 ? { color: 'var(--color-warning)', fontWeight: 500 } : undefined}>已挂起 {d.text}</span>
                  </div>
                </div>
                <Link className="btn-primary" style={{ padding: '6px 14px', borderRadius: 6, color: '#fff' }} to={`/confirmations/${c.id}`}>去确认</Link>
              </div>
            );
          })
        )}
      </section>

      <section className="section">
        <h2 className="section-title">待确认事件 <span className="badge" style={{ background: 'var(--st-written-bg)', color: 'var(--color-warning)' }}>{pendingEvents.length}</span></h2>
        {events.isLoading ? <Skeleton /> : pendingEvents.length === 0 ? (
          <div className="card" style={{ padding: '10px 16px', color: 'var(--color-text-secondary)' }}>没有待确认事项 ✅</div>
        ) : (
          pendingEvents.map((e) => (
            <div key={e.id} className="card pending-card" style={{ marginBottom: 8 }}>
              <span className="badge" style={{ background: 'var(--st-submitted-bg)', color: 'var(--color-info)' }}>{e.type}</span>
              <div style={{ flex: 1 }}>
                <strong>{e.company ?? '未匹配公司'}</strong>
                <div style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>{fmtDateTime(e.event_time)} · 来源：邮箱识别</div>
              </div>
              <Link className="btn-primary" style={{ padding: '6px 14px', borderRadius: 6, color: '#fff' }} to="/events">去确认</Link>
            </div>
          ))
        )}
      </section>

      {/* 近期日程（未来 7 天） */}
      <section className="section">
        <h2 className="section-title">近期日程（未来 7 天） <Link to="/schedule" style={{ fontSize: 13, fontWeight: 400 }}>查看日程 →</Link></h2>
        {schedule.isLoading ? <Skeleton /> : upcoming.length === 0 ? (
          <div className="card" style={{ padding: '10px 16px', color: 'var(--color-text-secondary)' }}>未来 7 天暂无日程</div>
        ) : (
          <div className="card" style={{ padding: 8 }}>
            {upcoming.map((e) => (
              <div key={e.id} style={{ display: 'flex', gap: 12, padding: '8px 12px', borderBottom: '1px solid var(--color-border)' }}>
                <span className="num" style={{ minWidth: 130 }}>{fmtDateTime(e.start_time)}</span>
                <span className="badge" style={{ background: 'var(--st-written-bg)', color: 'var(--st-written)' }}>{e.type}</span>
                <span style={{ flex: 1 }}>{e.title}</span>
                {withinHours(e.start_time, 24) && <span className="badge" style={{ background: 'var(--st-written-bg)', color: 'var(--color-warning)' }}>24h 内</span>}
                <span style={{ color: 'var(--color-text-secondary)', fontSize: 12 }}>{e.location ?? e.meeting_link ?? ''}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* 关键指标卡（FR-52） */}
      <section className="section">
        <h2 className="section-title">关键指标</h2>
        {apps.isLoading ? <Skeleton lines={2} /> : (
          <div className="metric-row">
            {cards.map((c) => (
              <div key={c.label} className="card metric-card" onClick={() => nav(c.to)} role="button" tabIndex={0}
                onKeyDown={(e) => e.key === 'Enter' && nav(c.to)}>
                <div className="metric-value num">{c.value}</div>
                <div className="metric-label">{c.label}</div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
