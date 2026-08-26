import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, isProfileEmpty, type Education, type Experience } from '../api';
import { EmptyState, Skeleton } from '../components/Feedback';

/**
 * D-03 结构化档案编辑（FR-2，§10.1）。
 * 契约缺口：冻结契约只有 GET /profile（只读），无档案写端点 ——
 * 表单完整实现但保存按钮禁用并标注，待契约扩展。
 */
export default function ProfileEdit() {
  const profile = useQuery({ queryKey: ['profile'], queryFn: () => api.getProfile(), retry: false });
  const [dirty, setDirty] = useState(false);

  if (profile.isLoading) return <Skeleton lines={6} />;
  if (profile.isError) return <EmptyState icon="⚠️" text="档案加载失败，请确认后端已启动。" />;
  if (!profile.data || isProfileEmpty(profile.data)) return <EmptyState icon="📄" text="先上传简历或手动填写档案。" />;
  const p = profile.data;

  const missing: string[] = [];
  if (!p.name) missing.push('姓名');
  if (!p.phone) missing.push('电话');
  if (!p.email) missing.push('邮箱');
  if (p.educations.length === 0) missing.push('教育经历');

  return (
    <div>
      {missing.length > 0 && (
        <div className="banner banner-warning">部分必填字段缺失：{missing.join('、')}（AC-1 缺失标记）</div>
      )}
      <div className="banner banner-info">
        契约缺口：冻结契约未提供档案写端点（PUT /profile 不存在），本页为只读预览 + 编辑表单骨架；保存待契约扩展后开放。
      </div>

      <section className="card section" style={{ padding: 20 }}>
        <h3 className="section-title">基本信息 {missing.some((m) => ['姓名', '电话', '邮箱'].includes(m)) && <span title="有必填缺失" style={{ color: 'var(--color-warning)' }}>●</span>}</h3>
        <div className="form-grid">
          {([['姓名', p.name, true], ['电话', p.phone, true], ['邮箱', p.email, true]] as const).map(([label, val, required]) => (
            <div className="form-field" key={label}>
              <label>{label}{required && <span className="required-mark"> *</span>}</label>
              <input defaultValue={val ?? ''} readOnly style={!val ? { borderColor: 'var(--color-warning)' } : undefined}
                title={!val ? '待补全' : undefined} />
              {!val && <span style={{ fontSize: 12, color: 'var(--color-warning)' }}>待补全</span>}
            </div>
          ))}
          <div className="form-field">
            <label>期望城市</label>
            <input defaultValue={p.expected_city ?? ''} readOnly />
          </div>
          <div className="form-field">
            <label>期望岗位</label>
            <input defaultValue={p.expected_position ?? ''} readOnly />
          </div>
        </div>
      </section>

      <section className="card section" style={{ padding: 20 }}>
        <h3 className="section-title">教育经历 <span style={{ color: 'var(--color-danger)' }}>*</span>（{p.educations.length} 条）</h3>
        {p.educations.map((e: Education, i: number) => (
          <div key={i} className="card" style={{ padding: 12, marginBottom: 8, background: 'var(--color-bg)' }}>
            <strong>{e.school}</strong> · {e.degree ?? '—'} · {e.major ?? '—'}
            <span style={{ color: 'var(--color-text-secondary)', marginLeft: 8 }} className="num">{e.start_date ?? '—'} ~ {e.end_date ?? '至今'}</span>
          </div>
        ))}
      </section>

      <section className="card section" style={{ padding: 20 }}>
        <h3 className="section-title">实习 · 项目经历（{p.experiences.length} 条）</h3>
        {p.experiences.map((e: Experience, i: number) => (
          <div key={i} className="card" style={{ padding: 12, marginBottom: 8, background: 'var(--color-bg)' }}>
            <strong>{e.company}</strong> · {e.position ?? '—'}
            <span style={{ color: 'var(--color-text-secondary)', marginLeft: 8 }} className="num">{e.start_date ?? '—'} ~ {e.end_date ?? '至今'}</span>
            {e.description && <div style={{ marginTop: 6, color: 'var(--color-text-secondary)', fontSize: 13 }}>{e.description}</div>}
          </div>
        ))}
      </section>

      <section className="card section" style={{ padding: 20 }}>
        <h3 className="section-title">技能</h3>
        <div className="chips">{p.skills.map((s) => <span key={s} className="chip">{s}</span>)}</div>
        <h3 className="section-title" style={{ marginTop: 16 }}>获奖证书</h3>
        <div className="chips">{p.awards.map((s) => <span key={s} className="chip">{s}</span>)}</div>
      </section>

      <div style={{ position: 'sticky', bottom: 0, background: 'var(--color-surface)', borderTop: '1px solid var(--color-border)', padding: '12px 0', display: 'flex', gap: 12 }}>
        <button className="btn-primary" disabled title="契约缺口：档案写端点未在冻结契约中，待扩展">保存（待契约扩展）</button>
        {dirty && <span style={{ color: 'var(--color-warning)' }}>有未保存改动</span>}
      </div>
    </div>
  );
}
