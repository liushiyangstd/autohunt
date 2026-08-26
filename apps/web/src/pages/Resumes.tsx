import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { api, isProfileEmpty } from '../api';
import { EmptyState, Skeleton } from '../components/Feedback';

/**
 * D-02 简历库（FR-1/2/3）。
 * 契约缺口：冻结契约无简历上传/版本管理端点（仅 GET /profile），
 * 本页展示契约可得的档案摘要，上传/多版本管理待契约扩展后开放。
 */
export default function Resumes() {
  const profile = useQuery({ queryKey: ['profile'], queryFn: () => api.getProfile(), retry: false });

  if (profile.isLoading) return <Skeleton lines={5} />;
  if (profile.isError) return <EmptyState icon="⚠️" text="简历数据加载失败，请确认后端已启动。" />;
  if (profile.data && isProfileEmpty(profile.data)) {
    return <EmptyState icon="📄" text="还没有简历。上传 PDF 后将自动解析为结构化档案。" action={
      <button className="btn-primary" disabled title="契约缺口：简历上传端点未在冻结契约中，待扩展">上传 PDF</button>
    } />;
  }
  const p = profile.data!;
  if (isProfileEmpty(p)) return null;

  return (
    <div>
      <div className="banner banner-info">
        契约缺口：简历上传 / 多版本管理端点未在冻结契约中（已上报）。当前展示默认简历版本的结构化档案（GET /profile，FR-20）。
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 24 }}>
        <div>
          <div className="card" style={{ padding: 16, border: '1px solid var(--color-primary)' }}>
            <div style={{ fontWeight: 600 }}>简历 v{p.resume_version}</div>
            <span className="badge" style={{ background: 'var(--st-submitted-bg)', color: 'var(--color-primary)', marginTop: 6 }}>默认</span>
            <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 8 }}>resume_id: {p.resume_id}</div>
          </div>
          <button className="btn-primary" style={{ width: '100%', marginTop: 12 }} disabled title="契约缺口：简历上传端点未在冻结契约中，待扩展">上传 PDF（待契约扩展）</button>
        </div>
        <div className="card" style={{ padding: 20 }}>
          <h3 style={{ marginTop: 0 }}>结构化档案摘要</h3>
          <p><strong>{p.name ?? '（姓名缺失）'}</strong> · {p.phone ?? '电话缺失'} · {p.email ?? '邮箱缺失'}</p>
          <p style={{ color: 'var(--color-text-secondary)' }}>
            教育经历 {p.educations.length} 条 · 实习/项目 {p.experiences.length} 条 · 技能 {p.skills.length} 项 · 证书 {p.awards.length} 项
          </p>
          <p>求职意向：{p.expected_city ?? '—'} · {p.expected_position ?? '—'}</p>
          <Link className="btn-primary" style={{ display: 'inline-block', padding: '6px 14px', borderRadius: 6, color: '#fff' }} to="/profile">查看/编辑档案 →</Link>
        </div>
      </div>
    </div>
  );
}
