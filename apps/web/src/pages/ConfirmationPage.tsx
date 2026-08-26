import { useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, isProfileEmpty, type Profile } from '../api';
import type { ConfirmationDetail } from '../api/client';
import Modal from '../components/Modal';
import { ConfirmBadge } from '../components/Badges';
import { EmptyState, Skeleton } from '../components/Feedback';
import { fmtDateTime, pendingDuration } from '../utils/time';

/** 必填校验口径：对照档案必填项（D-03/§10.1：姓名/电话/邮箱 + 至少一条教育经历） */
const REQUIRED_FIELDS = ['姓名', '电话', '邮箱'];

const PROFILE_SOURCE: Record<string, keyof Profile | null> = {
  姓名: 'name', 电话: 'phone', 邮箱: 'email', 期望城市: 'expected_city', 期望岗位: 'expected_position',
  学校: null, 专业: null,
};

function fieldSource(field: string, snapshot: string, profile?: Profile): string | null {
  if (!profile) return null;
  const key = PROFILE_SOURCE[field];
  if (key && profile[key] && String(profile[key]) === snapshot) return `来自结构化档案·${field}`;
  if (field === '学校' && profile.educations.some((e) => e.school === snapshot)) return '来自结构化档案·教育经历';
  if (field === '专业' && profile.educations.some((e) => e.major === snapshot)) return '来自结构化档案·教育经历';
  return null;
}

/** 权限闸门（AC-3 可视化）：非已确认 = 锁；已确认 = 放行 */
function PermitGate({ status }: { status: ConfirmationDetail['status'] }) {
  const granted = status === '已确认';
  return (
    <span
      className="confirm-lock"
      role="status"
      style={granted
        ? { background: 'var(--st-offer-bg)', color: 'var(--color-success)' }
        : { background: 'var(--st-written-bg)', color: 'var(--color-warning)' }}
    >
      {granted ? '🔓 已确认 · 提交许可已放行给 Agent' : '🔒 未确认 · 系统不会放行提交'}
    </span>
  );
}

export default function ConfirmationPage() {
  const { id = '' } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();

  const detail = useQuery({ queryKey: ['confirmation', id], queryFn: () => api.getConfirmationDetail(id), retry: false });
  const profile = useQuery({ queryKey: ['profile'], queryFn: () => api.getProfile(), retry: false });
  const apps = useQuery({ queryKey: ['applications'], queryFn: () => api.listApplications(), retry: false });
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => api.listJobs(), retry: false });
  // 已确认/已驳回/已关闭变体不携带 application_id（契约 v2），从确认单列表摘要补齐
  const cfmList = useQuery({ queryKey: ['confirmations'], queryFn: () => api.listConfirmations(), retry: false });

  const c = detail.data;
  const applicationId = c?.application_id ?? cfmList.data?.items.find((i) => i.id === id)?.application_id;
  const app = applicationId ? apps.data?.items.find((a) => a.id === applicationId) : undefined;
  const job = app ? jobs.data?.items.find((j) => j.id === app.job_id) : undefined;
  const profileData = profile.data && !isProfileEmpty(profile.data) ? profile.data : undefined;

  const [edited, setEdited] = useState<Record<string, string>>({});
  const [invalidFields, setInvalidFields] = useState<Set<string>>(new Set());
  const [modal, setModal] = useState<'confirm' | 'reject' | 'close' | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);
  const tableRef = useRef<HTMLTableElement>(null);

  const snapshot = c?.fields ?? {};
  const isPending = c?.status === '待确认';
  const terminal = c && !isPending;

  // 确认值 = 用户修改值 ?? 快照值
  const confirmValues = useMemo(() => {
    const v: Record<string, string> = {};
    for (const k of Object.keys(snapshot)) v[k] = edited[k] ?? snapshot[k];
    return v;
  }, [snapshot, edited]);

  const modifiedFields = Object.keys(edited).filter((k) => edited[k] !== snapshot[k]);
  const changeSummary = modifiedFields.length === 0 ? '无修改' : `${modifiedFields.length} 处修改`;

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['confirmation', id] });
    qc.invalidateQueries({ queryKey: ['confirmations'] });
  };

  const confirmMut = useMutation({
    mutationFn: () => api.confirm(id, { confirmed_fields: confirmValues }),
    onSuccess: () => { setModal(null); setActionError(null); invalidate(); },
    onError: (e) => setActionError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)),
  });
  const rejectMut = useMutation({
    mutationFn: () => api.reject(id, { reason: rejectReason }),
    onSuccess: () => { setModal(null); setActionError(null); invalidate(); },
    onError: (e) => setActionError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)),
  });
  const reissueMut = useMutation({
    mutationFn: () => api.reissue(id),
    onSuccess: () => { setActionError(null); invalidate(); },
    onError: (e) => setActionError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)),
  });
  const closeMut = useMutation({
    mutationFn: () => api.closeConfirmation(id),
    onSuccess: () => { setModal(null); setActionError(null); invalidate(); },
    onError: (e) => { setModal(null); setActionError(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e)); },
  });

  const tryConfirm = () => {
    // 校验：必填字段确认值为空 → 行内标红并锚点滚动至第一处
    const bad = new Set(REQUIRED_FIELDS.filter((f) => f in confirmValues && !confirmValues[f].trim()));
    setInvalidFields(bad);
    if (bad.size > 0) {
      const first = REQUIRED_FIELDS.find((f) => bad.has(f));
      tableRef.current?.querySelector(`[data-field="${first}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    setModal('confirm');
  };

  if (detail.isLoading) return <Skeleton lines={6} />;
  if (detail.isError || !c) {
    const e = detail.error;
    return <EmptyState icon="⚠️" text={e instanceof ApiError ? `加载失败：${e.message}` : '确认任务不存在'} action={<Link to="/">返回工作台</Link>} />;
  }

  const duration = c.created_at ? pendingDuration(c.created_at) : null;

  return (
    <div>
      {/* 任务条 */}
      <div className="card section" style={{ padding: 16 }}>
        <div className="confirm-taskbar">
          <Link to="/" className="btn-link">← 工作台</Link>
          <strong style={{ fontSize: 16 }}>{job ? `${job.company} · ${job.title}` : '投递确认'}</strong>
          {job && <Link to={`/jobs/${job.id}`}>岗位详情</Link>}
          <ConfirmBadge status={c.status} />
          {c.created_at && <span style={{ color: 'var(--color-text-secondary)' }}>Agent 创建于 {fmtDateTime(c.created_at)}</span>}
          {duration && isPending && (
            <span style={{ color: duration.hours > 24 ? 'var(--color-warning)' : 'var(--color-text-secondary)' }}>
              已挂起 {duration.text}
            </span>
          )}
          <PermitGate status={c.status} />
        </div>
      </div>

      {actionError && <div className="banner banner-danger">操作失败：{actionError}</div>}

      {/* 主体：对照表 / 终态留档 */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <table className="confirm-table" ref={tableRef} aria-label="字段-值快照对照表">
          <thead>
            <tr>
              <th style={{ width: '16%' }}>字段名</th>
              <th style={{ width: '32%' }}>Agent 填写值（快照）</th>
              <th style={{ width: '36%' }}>{isPending ? '确认值（可修改）' : '确认值（留档）'}</th>
              <th>数据来源</th>
            </tr>
          </thead>
          <tbody>
            {Object.keys(snapshot).length === 0 && c.status === '已确认' && c.confirmed_fields
              ? Object.entries(c.confirmed_fields).map(([k, v]) => (
                  <tr key={k} data-field={k}>
                    <td>{k}</td>
                    <td className="snapshot-val">—</td>
                    <td className="snapshot-val">{v}</td>
                    <td className="field-source">—</td>
                  </tr>
                ))
              : Object.entries(snapshot).map(([field, snapVal]) => {
                  const modified = edited[field] !== undefined && edited[field] !== snapVal;
                  const invalid = invalidFields.has(field);
                  const source = fieldSource(field, snapVal, profileData);
                  return (
                    <tr key={field} data-field={field} className={`${modified ? 'modified' : ''} ${invalid ? 'invalid' : ''}`}>
                      <td>
                        {field}
                        {REQUIRED_FIELDS.includes(field) && <span style={{ color: 'var(--color-danger)' }}> *</span>}
                        {modified && <span className="badge" style={{ marginLeft: 6, background: 'var(--st-submitted-bg)', color: 'var(--color-primary)' }}>已修改</span>}
                      </td>
                      <td className="snapshot-val">{snapVal || <span style={{ color: 'var(--color-text-disabled)' }}>（Agent 未填写）</span>}</td>
                      <td>
                        {isPending ? (
                          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                            <input
                              aria-label={`确认值-${field}`}
                              value={confirmValues[field]}
                              onChange={(e) => {
                                setEdited((p) => ({ ...p, [field]: e.target.value }));
                                setInvalidFields((p) => { const n = new Set(p); n.delete(field); return n; });
                              }}
                              style={invalid ? { borderColor: 'var(--color-danger)' } : undefined}
                            />
                            {modified && (
                              <button className="btn-text" title="还原为快照值" aria-label={`还原-${field}`}
                                onClick={() => setEdited((p) => { const n = { ...p }; delete n[field]; return n; })}>↩</button>
                            )}
                          </div>
                        ) : (
                          <span className="snapshot-val">{c.confirmed_fields?.[field] ?? snapVal}</span>
                        )}
                        {invalid && <div style={{ color: 'var(--color-danger)', fontSize: 12, marginTop: 4 }}>必填字段不能为空</div>}
                      </td>
                      <td className="field-source">{source ?? '—'}</td>
                    </tr>
                  );
                })}
          </tbody>
        </table>

        {/* 结果视图（FR-23/24，确认后） */}
        {c.status === '已确认' && (
          <div style={{ padding: 16 }}>
            {c.submit_result === 'success' && (
              <div className="banner banner-success">✅ 提交成功 · {fmtDateTime(c.submitted_at)}，投递状态已自动推进为「已投递」（来源：Agent 回写）</div>
            )}
            {c.submit_result === 'failed' && (
              <div className="banner banner-danger" style={{ display: 'block' }}>
                <div>❌ Agent 提交失败：{c.fail_reason ?? '未提供原因'}</div>
                <div style={{ marginTop: 8, fontSize: 13 }}>字段快照已在上方保留，可转人工完成：</div>
                <div style={{ marginTop: 8 }}>
                  {job?.jd_url
                    ? <a href={job.jd_url} target="_blank" rel="noreferrer" className="btn-primary" style={{ display: 'inline-block', padding: '6px 14px', borderRadius: 6, color: '#fff' }}>转人工完成（打开 JD 页面）</a>
                    : <span>（该岗位无 JD 链接）</span>}
                </div>
              </div>
            )}
            {!c.submit_result && (
              <div className="banner banner-info">
                {c.submit_token
                  ? `提交许可已放行（有效期至 ${fmtDateTime(c.expires_at)}），等待 Agent 提交并回写结果。`
                  : '提交许可已过期或已消耗。'}
                {!c.submit_token && (
                  <button className="btn-primary" style={{ marginLeft: 12 }} disabled={reissueMut.isPending}
                    onClick={() => reissueMut.mutate()}>
                    {reissueMut.isPending ? '放行中…' : '重新放行'}
                  </button>
                )}
              </div>
            )}
          </div>
        )}
        {c.status === '已驳回' && <div style={{ padding: 16 }}><div className="banner banner-danger">已驳回{c.reason ? `：${c.reason}` : ''}。结果将经 API 供 Agent 读取。</div></div>}
        {c.status === '已超时关闭' && <div style={{ padding: 16 }}><div className="banner" style={{ background: 'var(--st-closed-bg)', color: 'var(--st-closed)' }}>任务已手动关闭（已超时关闭），整页只读留档。</div></div>}
      </div>

      {/* 底部吸底操作栏（仅待确认） */}
      {isPending && (
        <div className="confirm-footer">
          <button className="btn-primary" title={`改动摘要：${changeSummary}`} onClick={tryConfirm} disabled={confirmMut.isPending}>
            确认并允许提交
          </button>
          <button className="btn-danger-outline" onClick={() => setModal('reject')} disabled={rejectMut.isPending}>驳回</button>
          <button className="btn-link" onClick={() => nav(-1)}>暂不处理</button>
          <button className="btn-text" style={{ marginLeft: 'auto', color: 'var(--color-text-disabled)' }} onClick={() => setModal('close')}>关闭任务</button>
          <span style={{ color: 'var(--color-text-secondary)', fontSize: 12 }}>{changeSummary}</span>
        </div>
      )}

      {/* 二次确认弹窗（BR-1 契约的用户侧表达，文案按设计稿） */}
      {modal === 'confirm' && (
        <Modal title="确认并允许提交" onClose={() => setModal(null)} danger>
          <p>确认后外部 Agent 将按以上确认值提交至该公司官网。<strong>提交动作不可撤销。</strong></p>
          <p style={{ color: 'var(--color-text-secondary)' }}>改动摘要：{changeSummary}{modifiedFields.length > 0 && `（${modifiedFields.join('、')}）`}</p>
          <div className="modal-actions">
            <button onClick={() => setModal(null)}>再想想</button>
            <button className="btn-primary" onClick={() => confirmMut.mutate()} disabled={confirmMut.isPending}>
              {confirmMut.isPending ? '确认中…' : '确认无误，允许提交'}
            </button>
          </div>
        </Modal>
      )}
      {modal === 'reject' && (
        <Modal title="驳回该投递确认" onClose={() => setModal(null)} danger>
          <p style={{ color: 'var(--color-text-secondary)' }}>驳回后 Agent 将读取到驳回状态与原因，本任务终止。</p>
          <textarea
            aria-label="驳回原因"
            placeholder="驳回原因（必填）"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            style={{ width: '100%', minHeight: 80 }}
          />
          <div className="modal-actions">
            <button onClick={() => setModal(null)}>取消</button>
            <button className="btn-danger-outline" disabled={!rejectReason.trim() || rejectMut.isPending} onClick={() => rejectMut.mutate()}>
              {rejectMut.isPending ? '提交中…' : '确认驳回'}
            </button>
          </div>
        </Modal>
      )}
      {modal === 'close' && (
        <Modal title="关闭确认任务" onClose={() => setModal(null)}>
          <p>任务将被标记为「已超时关闭」并转为只读留档。该操作不等同于确认或驳回。</p>
          <div className="modal-actions">
            <button onClick={() => setModal(null)}>取消</button>
            <button className="btn-danger-outline" onClick={() => closeMut.mutate()} disabled={closeMut.isPending}>确认关闭</button>
          </div>
        </Modal>
      )}
    </div>
  );
}
