import { useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, type Application, type ApplicationStatus, type Job } from '../api';
import Modal from '../components/Modal';
import { EmptyState, Skeleton } from '../components/Feedback';
import { BOARD_CLOSED, BOARD_COLUMNS, isTerminal, statusColor } from '../utils/status';
import { daysUntil } from '../utils/time';

interface UndoState { appId: string; from: ApplicationStatus; to: ApplicationStatus }

/** D-04 岗位看板（FR-10/11/12，BR-3/10/11） */
export default function Board() {
  const qc = useQueryClient();
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => api.listJobs(), retry: false });
  const apps = useQuery({ queryKey: ['applications'], queryFn: () => api.listApplications(), retry: false });

  const [showCreate, setShowCreate] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [channel, setChannel] = useState('');
  const [undo, setUndo] = useState<UndoState | null>(null);
  const [closedPick, setClosedPick] = useState<string | null>(null); // appId 待选终止态
  const undoTimer = useRef<ReturnType<typeof setTimeout>>();
  const [dragOver, setDragOver] = useState<string | null>(null);

  const invalidate = () => qc.invalidateQueries({ queryKey: ['applications'] });

  const moveMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: ApplicationStatus }) => api.updateApplication(id, { status }),
    onSuccess: invalidate,
    onError: (e) => alert(e instanceof ApiError ? `状态更新被拒绝：${e.message}` : String(e)),
  });

  const doMove = (appId: string, from: ApplicationStatus, to: ApplicationStatus) => {
    moveMut.mutate({ id: appId, status: to });
    // 拖拽即改 + 可撤销 toast 5s（Leader 拍板 §9-3）
    clearTimeout(undoTimer.current);
    setUndo({ appId, from, to });
    undoTimer.current = setTimeout(() => setUndo(null), 5000);
  };

  const onDropTo = (col: ApplicationStatus | '已结束') => (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(null);
    const appId = e.dataTransfer.getData('text/app-id');
    const from = e.dataTransfer.getData('text/app-status') as ApplicationStatus;
    if (!appId || !from) return;
    if (col === '已结束') { setClosedPick(appId); return; }
    if (col !== from) doMove(appId, from, col);
  };

  const jobOf = useMemo(() => {
    const m = new Map<string, Job>();
    jobs.data?.items.forEach((j) => m.set(j.id, j));
    return m;
  }, [jobs.data]);

  const filtered = useMemo(() => {
    let items = apps.data?.items ?? [];
    if (channel) items = items.filter((a) => jobOf.get(a.job_id)?.channel === channel);
    if (keyword) {
      const kw = keyword.toLowerCase();
      items = items.filter((a) => {
        const j = jobOf.get(a.job_id);
        return j?.company.toLowerCase().includes(kw) || j?.title.toLowerCase().includes(kw);
      });
    }
    return items;
  }, [apps.data, channel, keyword, jobOf]);

  const channels = useMemo(() => [...new Set((jobs.data?.items ?? []).map((j) => j.channel).filter(Boolean))] as string[], [jobs.data]);

  if (jobs.isLoading || apps.isLoading) return <Skeleton lines={5} />;
  if (jobs.isError || apps.isError) return <EmptyState icon="⚠️" text="看板数据加载失败，请确认后端已启动（或使用 ?mock=1 查看演示）。" />;

  const allApps = apps.data?.items ?? [];

  const colCard = (a: Application) => {
    const j = jobOf.get(a.job_id);
    const dLeft = daysUntil(j?.deadline);
    return (
      <div
        key={a.id}
        className="card board-card"
        draggable
        onDragStart={(e) => {
          e.dataTransfer.setData('text/app-id', a.id);
          e.dataTransfer.setData('text/app-status', a.status);
          e.currentTarget.classList.add('dragging');
        }}
        onDragEnd={(e) => e.currentTarget.classList.remove('dragging')}
      >
        <div className="company">{j?.company ?? '未知公司'}</div>
        <div>{j?.title ?? '未知岗位'}</div>
        <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          {j?.channel && <span className="badge" style={{ background: 'var(--st-pending-bg)', color: 'var(--st-pending)' }}>{j.channel}</span>}
          {a.status === '面试' && a.interview_round && <span className="badge" style={{ background: 'var(--st-interview-bg)', color: 'var(--st-interview)' }}>面试·{['一', '二', '三', '四', '五'][a.interview_round - 1] ?? a.interview_round}面</span>}
          {dLeft !== null && !isTerminal(a.status) && a.status === '待投递' && (
            <span className="badge num" style={dLeft <= 3 ? { background: 'var(--st-written-bg)', color: 'var(--color-warning)' } : { background: 'var(--st-pending-bg)', color: 'var(--color-text-secondary)' }}>
              {dLeft < 0 ? '已截止' : `截止 ${dLeft} 天`}
            </span>
          )}
        </div>
        <Link to={`/jobs/${a.job_id}`} style={{ fontSize: 12, display: 'inline-block', marginTop: 6 }}>详情 →</Link>
      </div>
    );
  };

  return (
    <div>
      <div className="toolbar">
        <button className="btn-primary" onClick={() => setShowCreate(true)}>+ 录入岗位</button>
        <input placeholder="搜索公司 / 岗位（FR-12）" value={keyword} onChange={(e) => setKeyword(e.target.value)} style={{ width: 220 }} />
        <select value={channel} onChange={(e) => setChannel(e.target.value)} aria-label="渠道筛选">
          <option value="">全部渠道</option>
          {channels.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      {allApps.length === 0 ? (
        <EmptyState icon="🗂️" text="还没有投递记录" action={<button className="btn-primary" onClick={() => setShowCreate(true)}>录入第一个岗位</button>} />
      ) : (
        <div className="board">
          {BOARD_COLUMNS.map((col) => {
            const items = filtered.filter((a) => a.status === col);
            const c = statusColor(col);
            return (
              <div key={col} className={`board-col ${dragOver === col ? 'drag-over' : ''}`}
                onDragOver={(e) => { e.preventDefault(); setDragOver(col); }}
                onDragLeave={() => setDragOver(null)}
                onDrop={onDropTo(col)}>
                <div className="board-col-title" style={{ color: c.fg }}><span>{col}</span><span className="num">{items.length}</span></div>
                {items.map(colCard)}
              </div>
            );
          })}
          <div className={`board-col ${dragOver === '已结束' ? 'drag-over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver('已结束'); }}
            onDragLeave={() => setDragOver(null)}
            onDrop={onDropTo('已结束')}>
            <div className="board-col-title" style={{ color: 'var(--st-closed)' }}><span>已结束</span><span className="num">{filtered.filter((a) => isTerminal(a.status)).length}</span></div>
            {filtered.filter((a) => isTerminal(a.status)).map(colCard)}
          </div>
        </div>
      )}

      {/* 可撤销 toast（拖拽即改，5s） */}
      {undo && (
        <div className="card fade-in" style={{ position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)', padding: '10px 16px', display: 'flex', gap: 12, alignItems: 'center', zIndex: 60 }}>
          <span>状态已更新：{undo.from} → {undo.to}（来源：手动）</span>
          <button className="btn-link" onClick={() => {
            moveMut.mutate({ id: undo.appId, status: undo.from });
            clearTimeout(undoTimer.current);
            setUndo(null);
          }}>撤销</button>
        </div>
      )}

      {/* 拖入已结束 → 选择具体终止态 */}
      {closedPick && (
        <Modal title="选择终止状态" onClose={() => setClosedPick(null)}>
          <div style={{ display: 'grid', gap: 8 }}>
            {BOARD_CLOSED.map((s) => (
              <button key={s} onClick={() => {
                const from = (apps.data?.items.find((a) => a.id === closedPick)?.status) ?? '待投递';
                doMove(closedPick, from, s);
                setClosedPick(null);
              }}>{s}</button>
            ))}
          </div>
        </Modal>
      )}

      {showCreate && <CreateJobModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}

/** 录入岗位弹窗（字段 = §10.2；BR-3 重复提示不拦截） */
function CreateJobModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({ company: '', title: '', jd_url: '', location: '', channel: '公司官网', deadline: '' });
  const [dupHint, setDupHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const createMut = useMutation({
    mutationFn: () => api.createJob({
      company: form.company.trim(), title: form.title.trim(),
      jd_url: form.jd_url || null, location: form.location || null,
      channel: form.channel || null,
      deadline: form.deadline ? new Date(form.deadline).toISOString() : null,
    }),
    onSuccess: (r) => {
      if (r.kind === 'duplicate') {
        // BR-3：提示不拦截，展示已有记录信息
        setDupHint(`已有该公司的同岗位投递（创建于 ${r.job.created_at.slice(0, 10)}），确认重复投递请再次点击「保存」。`);
        return;
      }
      qc.invalidateQueries({ queryKey: ['jobs'] });
      onClose();
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : String(e)),
  });

  const submit = () => {
    setError(null);
    // 重复提示后用户二次确认（BR-3 不拦截）：再次提交同一请求，由后端按契约处理
    createMut.mutate();
  };

  return (
    <Modal title="录入岗位" onClose={onClose}>
      <div className="form-grid">
        <div className="form-field"><label>公司 <span className="required-mark">*</span></label>
          <input value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} autoFocus /></div>
        <div className="form-field"><label>岗位名称 <span className="required-mark">*</span></label>
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></div>
        <div className="form-field"><label>JD 链接</label>
          <input value={form.jd_url} onChange={(e) => setForm({ ...form, jd_url: e.target.value })} placeholder="https://" /></div>
        <div className="form-field"><label>工作地点</label>
          <input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></div>
        <div className="form-field"><label>来源渠道</label>
          <select value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })}>
            <option>公司官网</option><option>内推</option><option>牛客</option><option>BOSS直聘</option><option>其他</option>
          </select></div>
        <div className="form-field"><label>网申截止日期</label>
          <input type="datetime-local" value={form.deadline} onChange={(e) => setForm({ ...form, deadline: e.target.value })} /></div>
      </div>
      {dupHint && <div className="banner banner-warning" style={{ marginTop: 12 }}>{dupHint}</div>}
      {error && <div className="banner banner-danger" style={{ marginTop: 12 }}>{error}</div>}
      <div className="modal-actions">
        <button onClick={onClose}>取消</button>
        <button className="btn-primary" disabled={!form.company.trim() || !form.title.trim() || createMut.isPending} onClick={submit}>
          {dupHint ? '确认重复投递并保存' : '保存'}
        </button>
      </div>
    </Modal>
  );
}
