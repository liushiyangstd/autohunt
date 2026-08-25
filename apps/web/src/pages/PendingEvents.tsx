import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api';
import { EmptyState, Skeleton } from '../components/Feedback';
import { fmtDateTime } from '../utils/time';

/**
 * D-07 待确认事件列表（FR-41/42，BR-2，AC-5）。
 * 契约缺口：确认入日程 / 丢弃的写端点未在冻结契约中（仅 GET /events/pending），
 * 操作按钮禁用并标注，待契约扩展；列表与证据区完整可用。
 */
export default function PendingEvents() {
  const events = useQuery({ queryKey: ['events', 'pending'], queryFn: () => api.listPendingEvents(), retry: false });
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => api.listJobs(), retry: false });
  const [expanded, setExpanded] = useState<string | null>(null);

  if (events.isLoading) return <Skeleton lines={4} />;
  if (events.isError) return <EmptyState icon="⚠️" text="待确认事件加载失败，请确认后端已启动（或 ?mock=1 查看演示）。" />;

  const items = [...(events.data?.items ?? [])].sort((a, b) => (a.event_time ?? '').localeCompare(b.event_time ?? ''));
  const expired = items.filter((e) => e.event_time && new Date(e.event_time).getTime() < Date.now());
  const fresh = items.filter((e) => !expired.includes(e));

  const card = (e: (typeof items)[number]) => {
    const isExpired = expired.includes(e);
    const job = jobs.data?.items.find((j) => j.id === e.matched_job_id);
    return (
      <div key={e.id} className="card event-card" style={isExpired ? { opacity: 0.75 } : undefined}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="badge" style={{ background: 'var(--st-submitted-bg)', color: 'var(--color-info)' }}>{e.type}</span>
          <span className="badge" title="解析置信来源" style={{ color: 'var(--color-info)', border: '1px solid var(--color-info)', background: 'transparent' }}>✉ 邮箱识别</span>
          <strong>{e.company ?? '未匹配公司'}</strong>
          {job && <span style={{ color: 'var(--color-text-secondary)' }}>关联：{job.company} · {job.title}</span>}
          {isExpired && <span className="badge" style={{ background: 'var(--st-written-bg)', color: 'var(--color-warning)' }}>时间已过</span>}
          <span style={{ marginLeft: 'auto', color: 'var(--color-text-secondary)' }} className="num">{fmtDateTime(e.event_time)}</span>
        </div>
        <div style={{ marginTop: 8, fontSize: 13, color: 'var(--color-text-secondary)' }}>
          {e.location && <span>地点：{e.location} · </span>}
          {e.meeting_link && <span>链接：{e.meeting_link} · </span>}
          <button className="btn-link" onClick={() => setExpanded(expanded === e.id ? null : e.id)}>
            {expanded === e.id ? '收起证据' : '查看原始邮件摘要'}
          </button>
        </div>
        {expanded === e.id && (
          <div className="card" style={{ background: 'var(--color-bg)', padding: 12, marginTop: 8, fontSize: 13 }}>
            <div>邮件事件 ID：<span className="mono">{e.id}</span> · 识别于 {fmtDateTime(e.created_at)}</div>
            <div style={{ marginTop: 4, color: 'var(--color-text-secondary)' }}>
              契约缺口：原始邮件原文读取端点未在冻结契约中（RISK-5 回溯能力待契约扩展）。
            </div>
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <button className="btn-primary" disabled title="契约缺口：事件确认入日程端点未在冻结契约中，待扩展">确认加入日程</button>
          <button disabled title="契约缺口：事件修正端点未在冻结契约中，待扩展">修正后加入</button>
          <button className="btn-text" disabled title="契约缺口：事件丢弃端点未在冻结契约中，待扩展">丢弃（误识别反馈）</button>
        </div>
      </div>
    );
  };

  return (
    <div>
      {items.length === 0
        ? <EmptyState icon="✉️" text="暂无待确认事件，识别到招聘邮件会先出现在这里（BR-2：一律先确认后入日程）。" />
        : <>{fresh.map(card)}{expired.map(card)}</>}
    </div>
  );
}
