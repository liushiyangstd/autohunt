import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { api, ApiError, type ResumeInfo, type ResumeParseStatus } from '../api';
import { EmptyState, Skeleton } from '../components/Feedback';
import Modal from '../components/Modal';

const MAX_PDF_BYTES = 10 * 1024 * 1024;

const statusMap: Record<ResumeParseStatus, { label: string; fg: string; bg: string }> = {
  解析中: { label: '解析中', fg: 'var(--color-text-secondary)', bg: 'var(--color-bg)' },
  解析完成: { label: '解析完成', fg: 'var(--color-success)', bg: 'var(--st-offer-bg)' },
  部分字段缺失: { label: '部分字段缺失', fg: 'var(--color-warning)', bg: 'var(--st-written-bg)' },
  解析失败: { label: '解析失败', fg: 'var(--color-danger)', bg: 'var(--st-rejected-bg)' },
};

const fieldLabels: Record<string, string> = {
  name: '姓名', phone: '电话', email: '邮箱', educations: '教育经历',
  experiences: '实习·项目经历', skills: '技能', awards: '获奖证书',
  expected_city: '期望城市', expected_position: '期望岗位',
};

function fmtDate(iso: string) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/** D-02 简历库（FR-1/2/3，PROX-10） */
export default function Resumes() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [rename, setRename] = useState<ResumeInfo | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [deleting, setDeleting] = useState<ResumeInfo | null>(null);
  const [references, setReferences] = useState<ResumeInfo | null>(null);

  const list = useQuery({ queryKey: ['resumes'], queryFn: () => api.listResumes(), retry: false });

  const uploadMut = useMutation({
    mutationFn: ({ file, name }: { file: File; name?: string }) => api.uploadResume(file, name),
    onSuccess: (newResume) => {
      qc.invalidateQueries({ queryKey: ['resumes'] });
      qc.invalidateQueries({ queryKey: ['profile'] });
      setError(null);
      if (fileRef.current) fileRef.current.value = '';
      navigate(`/profile?resume=${newResume.id}`);
    },
    onError: (e) => {
      setError(e instanceof ApiError ? e.message : String(e));
      if (fileRef.current) fileRef.current.value = '';
    },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: { name?: string; is_default?: boolean } }) => api.updateResume(id, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['resumes'] }); setError(null); },
    onError: (e) => setError(e instanceof ApiError ? e.message : String(e)),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.deleteResume(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['resumes'] }); setDeleting(null); setError(null); },
    onError: (e) => {
      setDeleting(null);
      setError(e instanceof ApiError ? e.message : String(e));
    },
  });

  const refsQuery = useQuery({
    queryKey: ['resume-references', references?.id],
    queryFn: () => references ? api.listResumeReferences(references.id) : Promise.reject(),
    enabled: !!references,
    retry: false,
  });

  const onFile = (files: FileList | null) => {
    const file = files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError('仅支持 .pdf 格式，请重新选择');
      return;
    }
    if (file.size > MAX_PDF_BYTES) {
      setError('简历大小超过 10MB，请压缩后重试');
      return;
    }
    if (file.size === 0) {
      setError('文件内容为空，请检查 PDF 后重试');
      return;
    }
    const base = file.name.replace(/\.pdf$/i, '');
    uploadMut.mutate({ file, name: base });
  };

  const startRename = (r: ResumeInfo) => { setRename(r); setRenameValue(r.name); };
  const commitRename = () => {
    if (rename && renameValue.trim() && renameValue.trim() !== rename.name) {
      updateMut.mutate({ id: rename.id, body: { name: renameValue.trim() } });
    }
    setRename(null);
  };

  const failedVersions = list.data?.items.filter((r) => r.parse_status === '解析失败') ?? [];
  const missingKey = failedVersions.some((r) => r.parse_error === '未配置 API Key');

  if (list.isLoading) return <Skeleton lines={5} />;
  if (list.isError) return <EmptyState icon="⚠️" text="简历数据加载失败，请确认后端已启动。" />;

  const items = list.data?.items ?? [];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 className="page-title">简历库</h2>
        <button className="btn-primary" disabled={uploadMut.isPending} onClick={() => fileRef.current?.click()}>
          {uploadMut.isPending ? '上传中…' : '上传 PDF'}
        </button>
        <input ref={fileRef} type="file" accept=".pdf" style={{ display: 'none' }} onChange={(e) => onFile(e.target.files)} />
      </div>

      {missingKey && (
        <div className="banner banner-warning">
          未配置 LLM API Key，上传的简历将无法自动解析。
          <Link to="/settings" style={{ marginLeft: 12, textDecoration: 'underline' }}>前往配置</Link>
        </div>
      )}
      {failedVersions.length > 0 && !missingKey && (
        <div className="banner banner-danger">
          {failedVersions.length} 份简历解析失败，请进入档案编辑手动补全。
          <Link to={`/profile?resume=${failedVersions[0].id}`} style={{ marginLeft: 12, textDecoration: 'underline' }}>前往补全</Link>
        </div>
      )}
      {error && <div className="banner banner-danger" style={{ marginBottom: 16 }}>{error}</div>}

      {items.length === 0 ? (
        <EmptyState
          icon="📄"
          text="还没有简历。上传 PDF 后将自动解析为结构化档案。"
          action={
            <button className="btn-primary" disabled={uploadMut.isPending} onClick={() => fileRef.current?.click()}>
              {uploadMut.isPending ? '上传中…' : '上传 PDF'}
            </button>
          }
        />
      ) : (
        <div style={{ display: 'grid', gap: 12 }}>
          {items.map((r) => {
            const st = statusMap[r.parse_status];
            const canDelete = r.used_count === 0;
            return (
              <div key={r.id} className="card" style={{ padding: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                      <strong style={{ fontSize: 16 }}>{r.name}</strong>
                      {r.is_default && <span className="badge" style={{ background: 'var(--color-primary)', color: '#fff' }}>默认</span>}
                      <span className="badge" style={{ background: st.bg, color: st.fg }}>{st.label}</span>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 6 }}>
                      <span className="num">{fmtDate(r.created_at)}</span>
                      {r.missing_fields.length > 0 && (
                        <span style={{ marginLeft: 12, color: 'var(--color-warning)' }}>
                          缺失：{r.missing_fields.map((f) => fieldLabels[f] ?? f).join('、')}
                        </span>
                      )}
                      {r.used_count > 0 && <span style={{ marginLeft: 12 }}>引用：{r.used_count}</span>}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <Link className="btn-text" to={`/profile?resume=${r.id}`}>查看/编辑档案</Link>
                    <a className="btn-text" href={api.resumeFileUrl(r.id)} download>下载</a>
                    {!r.is_default && (
                      <button className="btn-text" disabled={updateMut.isPending} onClick={() => updateMut.mutate({ id: r.id, body: { is_default: true } })}>
                        设为默认
                      </button>
                    )}
                    <button className="btn-text" onClick={() => startRename(r)}>重命名</button>
                    <button className="btn-text" onClick={() => setReferences(r)}>引用</button>
                    <button
                      className="btn-danger-outline"
                      disabled={!canDelete}
                      title={canDelete ? '删除' : `已被 ${r.used_count} 份投递引用，无法删除`}
                      onClick={() => canDelete && setDeleting(r)}
                    >
                      删除
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {rename && (
        <Modal title="重命名简历版本" onClose={() => setRename(null)}>
          <div className="form-field">
            <label>版本名</label>
            <input value={renameValue} onChange={(e) => setRenameValue(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && commitRename()} autoFocus />
          </div>
          <div className="modal-actions">
            <button onClick={() => setRename(null)}>取消</button>
            <button className="btn-primary" disabled={!renameValue.trim() || renameValue.trim() === rename.name} onClick={commitRename}>保存</button>
          </div>
        </Modal>
      )}

      {deleting && (
        <Modal title="删除简历版本" onClose={() => setDeleting(null)} danger>
          <p>删除后该版本的 PDF 与结构化档案将一并清除，不可恢复。</p>
          <div className="modal-actions">
            <button onClick={() => setDeleting(null)}>取消</button>
            <button className="btn-danger-outline" disabled={deleteMut.isPending} onClick={() => deleteMut.mutate(deleting.id)}>删除</button>
          </div>
        </Modal>
      )}

      {references && (
        <Modal title={`${references.name} 的投递引用`} onClose={() => setReferences(null)}>
          {refsQuery.isLoading ? <Skeleton lines={2} /> : refsQuery.isError ? (
            <div className="banner banner-danger">加载失败：{refsQuery.error instanceof ApiError ? refsQuery.error.message : '未知错误'}</div>
          ) : (refsQuery.data?.items.length ?? 0) === 0 ? (
            <p style={{ color: 'var(--color-text-secondary)' }}>暂无投递引用该版本。</p>
          ) : (
            <ul style={{ padding: 0, listStyle: 'none' }}>
              {refsQuery.data!.items.map((app) => (
                <li key={app.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--color-border)' }}>
                  <Link to={`/jobs/${app.job_id}`}>{app.job_id}</Link>
                  <span style={{ marginLeft: 12, color: 'var(--color-text-secondary)' }}>{app.status}</span>
                </li>
              ))}
            </ul>
          )}
        </Modal>
      )}
    </div>
  );
}
