import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api';
import { EmptyState, Skeleton } from '../components/Feedback';
import { StatusBadge } from '../components/Badges';
import { funnel, metrics } from '../utils/funnel';
import { fmtDate } from '../utils/time';

/**
 * D-09 统计（FR-50/51/52，§10.4 口径）。
 * 口径 tooltip 直接引用 §10.4（AC-7 可核对性）。
 * 已知限制：无 status_history 端点，"进入过 X 状态"以当前状态 rank 近似（见 utils/funnel.ts）。
 */
export default function Stats() {
  const apps = useQuery({ queryKey: ['applications'], queryFn: () => api.listApplications(), retry: false });
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => api.listJobs(), retry: false });
  const cfms = useQuery({ queryKey: ['confirmations', 'pending'], queryFn: () => api.listPendingConfirmations(), retry: false });
  const events = useQuery({ queryKey: ['events', 'pending'], queryFn: () => api.listPendingEvents(), retry: false });

  const [channel, setChannel] = useState<string[]>([]);
  const [since, setSince] = useState('');

  const jobOf = useMemo(() => new Map((jobs.data?.items ?? []).map((j) => [j.id, j])), [jobs.data]);
  const channels = useMemo(() => [...new Set((jobs.data?.items ?? []).map((j) => j.channel).filter(Boolean))] as string[], [jobs.data]);

  const filtered = useMemo(() => {
    let items = apps.data?.items ?? [];
    if (channel.length) items = items.filter((a) => channel.includes(jobOf.get(a.job_id)?.channel ?? ''));
    if (since) items = items.filter((a) => (a.applied_at ?? '') >= new Date(since).toISOString());
    return items;
  }, [apps.data, channel, since, jobOf]);

  if (apps.isLoading) return <Skeleton lines={5} />;
  if (apps.isError) return <EmptyState icon="⚠️" text="统计数据加载失败（或 ?mock=1 查看演示）。" />;

  const f = funnel(filtered);
  const m = metrics(apps.data?.items ?? [], (cfms.data?.length ?? 0) + (events.data?.items.length ?? 0));
  const maxCount = Math.max(1, ...f.stages.map((s) => s.count));

  const exportCsv = () => {
    // 范围外微增补（Leader 已批准）：本地优先产品的数据可携带性
    const rows = [['公司', '岗位', '渠道', '状态', '投递时间']];
    for (const a of filtered) {
      const j = jobOf.get(a.job_id);
      rows.push([j?.company ?? '', j?.title ?? '', j?.channel ?? '', a.status, a.applied_at ?? '']);
    }
    const csv = rows.map((r) => r.map((c) => `"${String(c).replaceAll('"', '""')}"`).join(',')).join('\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `autohunt-投递明细-${fmtDate(new Date().toISOString())}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div>
      <div className="metric-row section">
        {([['总投递数', m.total], ['进行中', m.active], ['待确认事项', m.pending], ['offer 数', m.offers]] as const).map(([label, v]) => (
          <div key={label} className="card metric-card"><div className="metric-value num">{v}</div><div className="metric-label">{label}</div></div>
        ))}
      </div>

      <div className="toolbar">
        <span style={{ color: 'var(--color-text-secondary)' }}>渠道：</span>
        <div className="chips">
          {channels.map((c) => (
            <button key={c} className={`chip ${channel.includes(c) ? 'active' : ''}`}
              onClick={() => setChannel((p) => p.includes(c) ? p.filter((x) => x !== c) : [...p, c])}>{c}</button>
          ))}
        </div>
        <span style={{ color: 'var(--color-text-secondary)', marginLeft: 16 }}>起始：</span>
        <input type="date" value={since} onChange={(e) => setSince(e.target.value)} />
        <button className="btn-link" onClick={() => { setChannel([]); setSince(''); }}>清除筛选</button>
        <button className="btn-text" style={{ marginLeft: 'auto' }} onClick={exportCsv}>导出 CSV</button>
      </div>

      <div className="card section" style={{ padding: 20 }}>
        <h3 className="section-title">
          投递漏斗
          <span style={{ fontSize: 12, fontWeight: 400, color: 'var(--color-text-secondary)' }}
            title="口径（PRD §10.4）：笔试转化率=进入笔试数/已投递及以后数；面试转化率=进入面试数/进入笔试数（无笔试环节岗位不剔除）；offer 转化率=进入 offer 数/全部已投递数；「待投递」不计入漏斗。">
            口径：§10.4 ⓘ
          </span>
        </h3>
        {f.stages.map((s) => (
          <div key={s.label} className="funnel-row">
            <span style={{ width: 60 }}>{s.label}</span>
            <div className="funnel-bar num" style={{ width: `${(s.count / maxCount) * 60 + 8}%` }}>{s.count}</div>
            {s.rateFromPrev !== null && <span className="num" style={{ color: 'var(--color-text-secondary)' }}>{(s.rateFromPrev * 100).toFixed(0)}%</span>}
          </div>
        ))}
        <p style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>注：「待投递」（收藏未投）不计入漏斗（§10.4）。</p>
      </div>

      <div className="card" style={{ padding: 20 }}>
        <h3 className="section-title">明细（{filtered.length} 条）</h3>
        {filtered.length === 0 ? <EmptyState text="当前筛选下无投递记录" /> : (
          <table className="confirm-table">
            <thead><tr><th>公司</th><th>岗位</th><th>渠道</th><th>状态</th><th>投递时间</th></tr></thead>
            <tbody>
              {filtered.map((a) => {
                const j = jobOf.get(a.job_id);
                return (
                  <tr key={a.id}>
                    <td>{j?.company ?? '—'}</td><td>{j?.title ?? '—'}</td><td>{j?.channel ?? '—'}</td>
                    <td><StatusBadge status={a.status} /></td>
                    <td className="num">{a.applied_at ? fmtDate(a.applied_at) : '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
