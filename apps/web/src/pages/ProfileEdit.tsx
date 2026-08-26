import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { api, ApiError, type Education, type Experience, type Profile, type ProfileUpdate } from '../api';
import { EmptyState, Skeleton } from '../components/Feedback';

const fieldLabels: Record<string, string> = {
  name: '姓名', phone: '电话', email: '邮箱', educations: '教育经历',
};

interface DraftProfile {
  resume_id: string;
  name: string;
  phone: string;
  email: string;
  educations: Education[];
  experiences: Experience[];
  skills: string[];
  awards: string[];
  expected_city: string;
  expected_position: string;
}

function emptyProfile(resumeId: string): DraftProfile {
  return {
    resume_id: resumeId,
    name: '', phone: '', email: '',
    educations: [], experiences: [], skills: [], awards: [],
    expected_city: '', expected_position: '',
  };
}

function cloneProfile(p: Profile): DraftProfile {
  return {
    resume_id: p.resume_id,
    name: p.name ?? '',
    phone: p.phone ?? '',
    email: p.email ?? '',
    educations: p.educations.map((e) => ({ ...e })),
    experiences: p.experiences.map((e) => ({ ...e })),
    skills: [...p.skills],
    awards: [...p.awards],
    expected_city: p.expected_city ?? '',
    expected_position: p.expected_position ?? '',
  };
}

function isDirty(a: DraftProfile, b: DraftProfile): boolean {
  return JSON.stringify(a) !== JSON.stringify(b);
}

function toUpdate(d: DraftProfile): ProfileUpdate {
  return {
    ...d,
    name: d.name.trim() || null,
    phone: d.phone.trim() || null,
    email: d.email.trim() || null,
    expected_city: d.expected_city.trim() || null,
    expected_position: d.expected_position.trim() || null,
  };
}

/** D-03 结构化档案编辑（FR-2/3，PROX-11） */
export default function ProfileEdit() {
  const [searchParams, setSearchParams] = useSearchParams();
  const qc = useQueryClient();
  const resumeId = searchParams.get('resume') ?? undefined;

  const profile = useQuery({
    queryKey: ['profile', resumeId],
    queryFn: () => api.getProfile(resumeId),
    retry: false,
  });

  const [form, setForm] = useState<DraftProfile | null>(null);
  const [saved, setSaved] = useState<DraftProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (profile.data && !('empty' in profile.data)) {
      const initial = cloneProfile(profile.data);
      setForm(initial);
      setSaved(initial);
      setSuccess(false);
    } else if (profile.data && 'empty' in profile.data && resumeId) {
      const initial = emptyProfile(resumeId);
      setForm(initial);
      setSaved(initial);
      setSuccess(false);
    }
  }, [profile.data, resumeId]);

  useEffect(() => {
    if (!form || !saved || !isDirty(form, saved)) return;
    const onBefore = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onBefore);
    return () => window.removeEventListener('beforeunload', onBefore);
  }, [form, saved]);

  const saveMut = useMutation({
    mutationFn: (body: ProfileUpdate) => api.putProfile(body),
    onSuccess: (p) => {
      const next = cloneProfile(p);
      setSaved(next);
      setForm(next);
      setSuccess(true);
      setError(null);
      qc.invalidateQueries({ queryKey: ['profile'] });
      qc.invalidateQueries({ queryKey: ['resumes'] });
      setTimeout(() => setSuccess(false), 3000);
    },
    onError: (e) => {
      setSuccess(false);
      setError(e instanceof ApiError ? e.message : String(e));
    },
  });

  const dirty = useMemo(() => !!(form && saved && isDirty(form, saved)), [form, saved]);

  if (profile.isLoading) return <Skeleton lines={6} />;
  if (profile.isError) return <EmptyState icon="⚠️" text="档案加载失败，请确认后端已启动。" />;
  if (!profile.data || ('empty' in profile.data && !resumeId)) {
    return <EmptyState icon="📄" text="先上传简历或手动填写档案。" action={<Link className="btn-primary" to="/resumes" style={{ display: 'inline-block' }}>前往简历库</Link>} />;
  }

  if (!form) return <Skeleton lines={6} />;

  const missing: string[] = [];
  if (!form.name?.trim()) missing.push('姓名');
  if (!form.phone?.trim()) missing.push('电话');
  if (!form.email?.trim()) missing.push('邮箱');
  if (form.educations.length === 0) missing.push('教育经历');

  const update = (patch: Partial<DraftProfile>) => {
    setForm((prev) => (prev ? { ...prev, ...patch } : prev));
    setSuccess(false);
  };

  const save = () => {
    if (!form) return;
    saveMut.mutate(toUpdate(form));
  };

  const reset = () => {
    if (!saved) return;
    if (dirty && !window.confirm('有未保存改动，确定要放弃修改吗？')) return;
    setForm({ ...saved });
    setError(null);
    setSuccess(false);
  };

  const setResume = (id: string) => {
    if (dirty && !window.confirm('切换版本前是否放弃当前未保存改动？')) return;
    setSearchParams({ resume: id });
  };

  const hasMissing = missing.length > 0;

  return (
    <div>
      <h2 className="page-title" style={{ marginBottom: 16 }}>档案编辑</h2>

      {success && <div className="banner banner-success">档案已保存生效</div>}
      {error && <div className="banner banner-danger">{error}</div>}
      {dirty && <div className="banner banner-warning">有未保存改动，保存后才会生效。</div>}
      {hasMissing && <div className="banner banner-warning">部分必填字段缺失：{missing.map((f) => fieldLabels[f] ?? f).join('、')}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 24, alignItems: 'start' }}>
        <VersionCard currentId={resumeId} onSelect={setResume} />

        <div>
          <section className="card section" style={{ padding: 20 }}>
            <h3 className="section-title">基本信息 {hasMissing && <span title="有必填缺失" style={{ color: 'var(--color-warning)' }}>●</span>}</h3>
            <div className="form-grid">
              <TextField label="姓名 *" value={form.name} onChange={(v) => update({ name: v })} required invalid={!form.name.trim()} />
              <TextField label="电话 *" value={form.phone} onChange={(v) => update({ phone: v })} required invalid={!form.phone.trim()} />
              <TextField label="邮箱 *" value={form.email} onChange={(v) => update({ email: v })} required invalid={!form.email.trim()} />
              <TextField label="期望城市" value={form.expected_city} onChange={(v) => update({ expected_city: v })} />
              <TextField label="期望岗位" value={form.expected_position} onChange={(v) => update({ expected_position: v })} />
            </div>
          </section>

          <section className="card section" style={{ padding: 20 }}>
            <h3 className="section-title">教育经历 <span style={{ color: 'var(--color-danger)' }}>*</span></h3>
            {form.educations.length === 0 && <p style={{ color: 'var(--color-text-secondary)' }}>暂无教育经历，点击添加。</p>}
            {form.educations.map((e, i) => (
              <div key={i} className="card" style={{ padding: 12, marginBottom: 8, background: 'var(--color-bg)' }}>
                <div className="form-grid" style={{ gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr auto' }}>
                  <TextField label="学校 *" value={e.school} onChange={(v) => {
                    const next = [...form.educations];
                    next[i] = { ...e, school: v };
                    update({ educations: next });
                  }} />
                  <TextField label="学历" value={e.degree ?? ''} onChange={(v) => {
                    const next = [...form.educations];
                    next[i] = { ...e, degree: v || null };
                    update({ educations: next });
                  }} />
                  <TextField label="专业" value={e.major ?? ''} onChange={(v) => {
                    const next = [...form.educations];
                    next[i] = { ...e, major: v || null };
                    update({ educations: next });
                  }} />
                  <TextField label="开始时间" value={e.start_date ?? ''} onChange={(v) => {
                    const next = [...form.educations];
                    next[i] = { ...e, start_date: v || null };
                    update({ educations: next });
                  }} placeholder="YYYY-MM" />
                  <TextField label="结束时间" value={e.end_date ?? ''} onChange={(v) => {
                    const next = [...form.educations];
                    next[i] = { ...e, end_date: v || null };
                    update({ educations: next });
                  }} placeholder="YYYY-MM" />
                  <button className="btn-danger-outline" style={{ alignSelf: 'end' }} onClick={() => {
                    const next = form.educations.filter((_, idx) => idx !== i);
                    update({ educations: next });
                  }}>删除</button>
                </div>
              </div>
            ))}
            <button onClick={() => update({ educations: [...form.educations, { school: '' }] })} style={{ marginTop: 8 }}>+ 添加一条</button>
          </section>

          <section className="card section" style={{ padding: 20 }}>
            <h3 className="section-title">实习 · 项目经历</h3>
            {form.experiences.length === 0 && <p style={{ color: 'var(--color-text-secondary)' }}>暂无经历，点击添加。</p>}
            {form.experiences.map((e, i) => (
              <div key={i} className="card" style={{ padding: 12, marginBottom: 8, background: 'var(--color-bg)' }}>
                <div className="form-grid">
                  <TextField label="公司/项目名 *" value={e.company} onChange={(v) => {
                    const next = [...form.experiences];
                    next[i] = { ...e, company: v };
                    update({ experiences: next });
                  }} />
                  <TextField label="职位/角色" value={e.position ?? ''} onChange={(v) => {
                    const next = [...form.experiences];
                    next[i] = { ...e, position: v || null };
                    update({ experiences: next });
                  }} />
                  <TextField label="开始时间" value={e.start_date ?? ''} onChange={(v) => {
                    const next = [...form.experiences];
                    next[i] = { ...e, start_date: v || null };
                    update({ experiences: next });
                  }} placeholder="YYYY-MM" />
                  <TextField label="结束时间" value={e.end_date ?? ''} onChange={(v) => {
                    const next = [...form.experiences];
                    next[i] = { ...e, end_date: v || null };
                    update({ experiences: next });
                  }} placeholder="YYYY-MM" />
                  <div className="form-field" style={{ gridColumn: '1 / -1' }}>
                    <label>描述</label>
                    <textarea
                      rows={3}
                      value={e.description ?? ''}
                      onChange={(ev) => {
                        const next = [...form.experiences];
                        next[i] = { ...e, description: ev.target.value || null };
                        update({ experiences: next });
                      }}
                    />
                  </div>
                  <button className="btn-danger-outline" onClick={() => {
                    const next = form.experiences.filter((_, idx) => idx !== i);
                    update({ experiences: next });
                  }}>删除本条</button>
                </div>
              </div>
            ))}
            <button onClick={() => update({ experiences: [...form.experiences, { company: '' }] })} style={{ marginTop: 8 }}>+ 添加一条</button>
          </section>

          <section className="card section" style={{ padding: 20 }}>
            <h3 className="section-title">技能</h3>
            <ChipList items={form.skills} onChange={(v) => update({ skills: v })} placeholder="例如：Python、React、数据分析" />
            <h3 className="section-title" style={{ marginTop: 16 }}>获奖证书</h3>
            <ChipList items={form.awards} onChange={(v) => update({ awards: v })} placeholder="奖学金、竞赛奖项、专业证书等" />
          </section>
        </div>
      </div>

      <div className="confirm-footer">
        <button className="btn-primary" disabled={saveMut.isPending} onClick={save}>{saveMut.isPending ? '保存中…' : '保存'}</button>
        <button disabled={!dirty} onClick={reset}>取消</button>
        {dirty && <span style={{ color: 'var(--color-warning)' }}>有未保存改动</span>}
      </div>
    </div>
  );
}

function VersionCard({ currentId, onSelect }: { currentId?: string; onSelect: (id: string) => void }) {
  const resumes = useQuery({ queryKey: ['resumes'], queryFn: () => api.listResumes(), retry: false });
  if (resumes.isLoading) return <div className="card" style={{ padding: 16 }}><Skeleton lines={3} /></div>;
  if (resumes.isError) return <div className="card" style={{ padding: 16 }}><div className="banner banner-danger">版本列表加载失败</div></div>;

  const items = resumes.data?.items ?? [];
  const current = items.find((r) => r.id === currentId) ?? items.find((r) => r.is_default) ?? items[0];

  return (
    <div className="card" style={{ padding: 16 }}>
      <h3 className="section-title">当前编辑版本</h3>
      {current ? (
        <>
          <div style={{ fontWeight: 600 }}>{current.name} {current.is_default && <span className="badge" style={{ background: 'var(--color-primary)', color: '#fff' }}>默认</span>}</div>
          <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 4 }}>{current.parse_status}</div>
          {current.missing_fields.length > 0 && (
            <div style={{ fontSize: 12, color: 'var(--color-warning)', marginTop: 4 }}>缺失：{current.missing_fields.join('、')}</div>
          )}
        </>
      ) : (
        <p style={{ color: 'var(--color-text-secondary)' }}>无简历版本</p>
      )}

      {items.length > 1 && (
        <div style={{ marginTop: 12 }}>
          <label style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>切换版本</label>
          <select value={current?.id ?? ''} onChange={(e) => onSelect(e.target.value)} style={{ width: '100%', marginTop: 4 }}>
            {items.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} {r.is_default ? '（默认）' : ''}
              </option>
            ))}
          </select>
        </div>
      )}
      <Link to="/resumes" style={{ display: 'inline-block', marginTop: 12, fontSize: 13 }}>← 返回简历库</Link>
    </div>
  );
}

function TextField({
  label, value, onChange, required, invalid, placeholder,
}: {
  label: string; value: string; onChange: (v: string) => void;
  required?: boolean; invalid?: boolean; placeholder?: string;
}) {
  const id = useMemo(() => Math.random().toString(36).slice(2, 9), []);
  return (
    <div className="form-field">
      <label htmlFor={id}>{label}{required && <span className="required-mark"> *</span>}</label>
      <input
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-invalid={invalid}
        style={invalid ? { borderColor: 'var(--color-warning)' } : undefined}
      />
      {invalid && <span style={{ fontSize: 12, color: 'var(--color-warning)' }}>待补全</span>}
    </div>
  );
}

function ChipList({ items, onChange, placeholder }: { items: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [input, setInput] = useState('');
  const add = (raw: string) => {
    const v = raw.trim();
    if (!v || items.includes(v)) return;
    onChange([...items, v]);
    setInput('');
  };
  return (
    <div>
      <div className="chips">
        {items.map((s) => (
          <span key={s} className="chip">
            {s}
            <button
              onClick={() => onChange(items.filter((x) => x !== s))}
              style={{ border: 'none', background: 'none', padding: '0 0 0 6px', cursor: 'pointer', color: 'var(--color-text-secondary)' }}
            >×</button>
          </span>
        ))}
      </div>
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(input); } }}
        onBlur={() => input.trim() && add(input)}
        placeholder={placeholder ?? '输入后回车添加'}
        style={{ marginTop: 8, width: '100%' }}
      />
    </div>
  );
}
