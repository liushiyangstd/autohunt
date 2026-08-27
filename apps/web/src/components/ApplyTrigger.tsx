import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../api';
import Modal from './Modal';

interface ApplyTriggerProps {
  jobId: string;
  disabled?: boolean;
  onApplied?: (confirmationId: string) => void;
  buttonClass?: string;
  label?: string;
}

/** 一键投递触发器：简历选择弹窗 + 调用 /jobs/{id}/apply */
export default function ApplyTrigger({ jobId, disabled, onApplied, buttonClass, label = '一键投递' }: ApplyTriggerProps) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resumes = useQuery({ queryKey: ['resumes'], queryFn: () => api.listResumes(), retry: false, enabled: open });

  const defaultResumeId = resumes.data?.items.find((r) => r.is_default)?.id ?? resumes.data?.items[0]?.id;
  const [selected, setSelected] = useState<string>('');

  // 弹窗打开时同步默认选中
  if (open && selected === '' && defaultResumeId) {
    setSelected(defaultResumeId);
  }

  const applyMut = useMutation({
    mutationFn: () => api.applyJob(jobId, { resume_id: selected || defaultResumeId || null }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['applications'] });
      qc.invalidateQueries({ queryKey: ['jobs', jobId] });
      qc.invalidateQueries({ queryKey: ['confirmations'] });
      setOpen(false);
      setError(null);
      onApplied?.(r.confirmation_id);
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : String(e)),
  });

  const handleOpen = () => {
    setOpen(true);
    setSelected('');
    setError(null);
  };

  return (
    <>
      <button className={buttonClass ?? 'btn-primary'} disabled={disabled} onClick={handleOpen}>{label}</button>
      {open && (
        <Modal title="选择本次使用的简历版本" onClose={() => setOpen(false)}>
          {resumes.isLoading ? <div>加载中…</div> : resumes.isError ? <div>简历列表加载失败</div> : (
            <div style={{ display: 'grid', gap: 8 }}>
              {(resumes.data?.items ?? []).map((r) => (
                <label key={r.id} className="card" style={{ padding: 10, display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                  <input
                    type="radio"
                    name={`resume-${jobId}`}
                    value={r.id}
                    checked={selected === r.id}
                    onChange={(e) => setSelected(e.target.value)}
                  />
                  <span>{r.name}</span>
                  {r.is_default && <span className="badge" style={{ background: 'var(--st-offer-bg)', color: 'var(--color-success)' }}>默认</span>}
                  <span className="badge" style={{ background: 'var(--st-pending-bg)', color: 'var(--color-text-secondary)' }}>{r.parse_status}</span>
                </label>
              ))}
              {(resumes.data?.items.length ?? 0) === 0 && <div>暂无简历，请先上传简历。</div>}
            </div>
          )}
          {error && <div className="banner banner-danger" style={{ marginTop: 12 }}>{error}</div>}
          <div className="modal-actions" style={{ marginTop: 16 }}>
            <button onClick={() => setOpen(false)}>取消</button>
            <button
              className="btn-primary"
              disabled={!selected || applyMut.isPending || resumes.isLoading}
              onClick={() => applyMut.mutate()}
            >
              {applyMut.isPending ? '准备字段快照…' : '确认并生成字段预览'}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
