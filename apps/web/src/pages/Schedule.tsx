import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api, type ScheduleEvent } from '../api';
import Modal from '../components/Modal';
import { EmptyState, Skeleton } from '../components/Feedback';
import { fmtDateTime } from '../utils/time';

const TYPE_COLOR: Record<string, { fg: string; bg: string }> = {
  测评: { fg: 'var(--color-info)', bg: 'var(--st-submitted-bg)' },
  笔试: { fg: 'var(--st-written)', bg: 'var(--st-written-bg)' },
  面试: { fg: 'var(--st-interview)', bg: 'var(--st-interview-bg)' },
  offer: { fg: 'var(--st-offer)', bg: 'var(--st-offer-bg)' },
  拒信: { fg: 'var(--st-rejected)', bg: 'var(--st-rejected-bg)' },
};

function overlaps(a: ScheduleEvent, b: ScheduleEvent): boolean {
  const aEnd = a.end_time ?? a.start_time;
  const bEnd = b.end_time ?? b.start_time;
  return a.start_time < bEnd && b.start_time < aEnd;
}

/** D-08 日程（FR-32/43）：月历 + 列表视图、冲突展示、截止日进日历 */
export default function Schedule() {
  const [view, setView] = useState<'month' | 'list'>('month');
  const [month, setMonth] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [typeFilter, setTypeFilter] = useState('');
  const [selected, setSelected] = useState<ScheduleEvent | null>(null);

  const from = new Date(month.getFullYear(), month.getMonth(), 1).toISOString();
  const to = new Date(month.getFullYear(), month.getMonth() + 1, 1).toISOString();
  const schedule = useQuery({ queryKey: ['schedule', from, to], queryFn: () => api.getSchedule(from, to), retry: false });
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => api.listJobs(), retry: false });
  const apps = useQuery({ queryKey: ['applications'], queryFn: () => api.listApplications(), retry: false });

  const events = useMemo(() => (schedule.data?.items ?? []).filter((e) => !typeFilter || e.type === typeFilter), [schedule.data, typeFilter]);

  // 网申截止日也进日历（D-08，来源：台账）；type 超出契约枚举，仅作日历展示项
  const deadlines = useMemo(() => (jobs.data?.items ?? [])
    .filter((j) => j.deadline)
    .map((j) => ({ id: `dl-${j.id}`, title: `${j.company} 网申截止`, type: '截止', start_time: j.deadline!, application_id: null, source_event_id: null }) as unknown as ScheduleEvent),
    [jobs.data]);

  const allEvents = useMemo(() => [...events, ...deadlines], [events, deadlines]);

  const conflicts = useMemo(() => {
    const map = new Map<string, number>();
    for (const a of events) for (const b of events) {
      if (a.id < b.id && overlaps(a, b)) {
        map.set(a.id, (map.get(a.id) ?? 0) + 1);
        map.set(b.id, (map.get(b.id) ?? 0) + 1);
      }
    }
    return map;
  }, [events]);

  if (schedule.isLoading) return <Skeleton lines={5} />;

  const year = month.getFullYear();
  const mon = month.getMonth();
  const firstDay = new Date(year, mon, 1).getDay(); // 0=Sun
  const daysInMonth = new Date(year, mon + 1, 0).getDate();
  const cells: (number | null)[] = [...Array(firstDay).fill(null), ...Array.from({ length: daysInMonth }, (_, i) => i + 1)];
  while (cells.length % 7 !== 0) cells.push(null);

  const eventsOn = (day: number) => {
    const d0 = new Date(year, mon, day).toDateString();
    return allEvents.filter((e) => new Date(e.start_time).toDateString() === d0);
  };

  const today = new Date();
  const isToday = (day: number) => today.getFullYear() === year && today.getMonth() === mon && today.getDate() === day;

  return (
    <div>
      <div className="toolbar">
        <div className="chips">
          {(['month', 'list'] as const).map((v) => (
            <button key={v} className={`chip ${view === v ? 'active' : ''}`} onClick={() => setView(v)}>{v === 'month' ? '月历' : '列表'}</button>
          ))}
        </div>
        <div className="chips" style={{ marginLeft: 16 }}>
          <button className={`chip ${typeFilter === '' ? 'active' : ''}`} onClick={() => setTypeFilter('')}>全部类型</button>
          {['测评', '笔试', '面试', 'offer'].map((t) => (
            <button key={t} className={`chip ${typeFilter === t ? 'active' : ''}`} onClick={() => setTypeFilter(t)}>{t}</button>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <button onClick={() => setMonth(new Date(year, mon - 1, 1))}>←</button>
          <strong className="num">{year} 年 {mon + 1} 月</strong>
          <button onClick={() => setMonth(new Date(year, mon + 1, 1))}>→</button>
        </div>
      </div>

      {events.length === 0 && !schedule.isError && (
        <div className="banner banner-info">绑定邮箱后自动识别笔试面试安排（FR-41）；手动已有事件不受影响。</div>
      )}

      {view === 'month' ? (
        <div>
          <div className="cal-grid" style={{ marginBottom: 4 }}>
            {['日', '一', '二', '三', '四', '五', '六'].map((d) => <div key={d} style={{ textAlign: 'center', color: 'var(--color-text-secondary)', fontSize: 12 }}>{d}</div>)}
          </div>
          <div className="cal-grid">
            {cells.map((day, i) => (
              <div key={i} className={`cal-cell ${day && isToday(day) ? 'today' : ''}`}>
                {day && (
                  <>
                    <div className="num" style={{ color: isToday(day) ? 'var(--color-primary)' : undefined }}>{day}</div>
                    {eventsOn(day).slice(0, 3).map((e) => {
                      const c = TYPE_COLOR[e.type] ?? { fg: 'var(--st-closed)', bg: 'var(--st-closed-bg)' };
                      return (
                        <button key={e.id} className="cal-pill" style={{ background: c.bg, color: c.fg, border: 'none', width: '100%', textAlign: 'left', padding: '1px 6px', fontSize: 11 }}
                          onClick={() => setSelected(e)}>
                          {e.title}
                        </button>
                      );
                    })}
                    {eventsOn(day).length > 3 && <div style={{ fontSize: 11, color: 'var(--color-text-secondary)' }}>+{eventsOn(day).length - 3}</div>}
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : (
        allEvents.length === 0 ? <EmptyState icon="📅" text="本月暂无日程" /> : (
          <div className="card" style={{ padding: 8 }}>
            {allEvents.sort((a, b) => a.start_time.localeCompare(b.start_time)).map((e) => (
              <button key={e.id} onClick={() => setSelected(e)}
                style={{ display: 'flex', gap: 12, width: '100%', border: 'none', background: 'none', padding: '10px 12px', borderBottom: '1px solid var(--color-border)', textAlign: 'left', borderRadius: 0 }}>
                <span className="num" style={{ minWidth: 130 }}>{fmtDateTime(e.start_time)}</span>
                <span className="badge" style={(TYPE_COLOR[e.type] ?? { background: 'var(--st-closed-bg)', color: 'var(--st-closed)' }) as never}>{e.type}</span>
                <span style={{ flex: 1 }}>{e.title}</span>
                {conflicts.has(e.id) && <span className="badge" style={{ background: 'var(--st-written-bg)', color: 'var(--color-warning)' }}>冲突 ×{conflicts.get(e.id)}</span>}
              </button>
            ))}
          </div>
        )
      )}

      {selected && (
        <Modal title={selected.title} onClose={() => setSelected(null)}>
          {conflicts.has(selected.id) && <div className="banner banner-warning">该时段有 {conflicts.get(selected.id)} 个事件冲突</div>}
          <p>时间：{fmtDateTime(selected.start_time)}{selected.end_time ? ` ~ ${fmtDateTime(selected.end_time)}` : ''}</p>
          <p>类型：{selected.type}</p>
          {selected.location && <p>地点：{selected.location}</p>}
          {selected.meeting_link && (
            <p>会议链接：<span className="mono">{selected.meeting_link}</span>{' '}
              <button className="btn-link" onClick={() => navigator.clipboard?.writeText(selected.meeting_link!)}>复制</button></p>
          )}
          {selected.application_id && <p><Link to="/board">查看关联投递 →</Link></p>}
          {selected.source_event_id && <p style={{ color: 'var(--color-text-secondary)', fontSize: 12 }}>来源：邮箱识别（事件 {selected.source_event_id}）· 原始邮件回溯端点待契约扩展</p>}
          <div className="modal-actions"><button onClick={() => setSelected(null)}>关闭</button></div>
        </Modal>
      )}
    </div>
  );
}
