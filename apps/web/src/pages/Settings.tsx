import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, type ApiKeyCreated, type LLMConfigUpdate } from '../api';
import Modal from '../components/Modal';
import { Skeleton } from '../components/Feedback';
import { fmtDateTime } from '../utils/time';

/** D-10 设置（FR-25/40/44，§12） */
export default function Settings() {
  return (
    <div style={{ display: 'grid', gap: 24 }}>
      <EmailBinding />
      <LLMConfig />
      <ApiKeys />
      <ReminderPrefs />
      <DataManagement />
    </div>
  );
}

/** 邮箱绑定（FR-40/44）—— 契约缺口：绑定/状态端点未在冻结契约中 */
function EmailBinding() {
  return (
    <section className="card" style={{ padding: 20 }}>
      <h3 className="section-title">邮箱绑定（IMAP）</h3>
      <div className="banner banner-warning">
        契约缺口：邮箱绑定 / 授权状态 / 测试连接端点未在冻结契约中（FR-40/44 的 UI 落点待契约扩展）。
        授权失效时全局警示条与本卡重授权表单将随契约扩展开放；历史已识别事件与日程完整保留（AC-8）。
      </div>
      <div className="form-grid">
        <div className="form-field"><label>邮箱地址</label><input disabled placeholder="qiuzhi@example.com" /></div>
        <div className="form-field"><label>IMAP 授权码</label><input disabled type="password" placeholder="授权码（非登录密码）" /></div>
      </div>
      <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
        <button disabled title="待契约扩展">测试连接</button>
        <button className="btn-primary" disabled title="待契约扩展">绑定</button>
      </div>
    </section>
  );
}

/** LLM 解析配置（PROX-12）—— 用户自带 API Key */
function LLMConfig() {
  const qc = useQueryClient();
  const cfg = useQuery({ queryKey: ['llm-config'], queryFn: () => api.getLLMConfig(), retry: false });
  const [form, setForm] = useState<LLMConfigUpdate>({});
  const [error, setError] = useState<string | null>(null);
  const [testMsg, setTestMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const saveMut = useMutation({
    mutationFn: (body: LLMConfigUpdate) => api.putLLMConfig(body),
    onSuccess: () => {
      setForm({});
      setError(null);
      qc.invalidateQueries({ queryKey: ['llm-config'] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.message : String(e)),
  });

  const testMut = useMutation({
    mutationFn: () => api.testLLMConfig(),
    onSuccess: (r) => setTestMsg({ ok: r.ok, text: r.ok ? '连接成功' : (r.error ?? '连接失败') }),
    onError: (e) => setTestMsg({ ok: false, text: e instanceof ApiError ? e.message : String(e) }),
  });

  if (cfg.isLoading) return <section className="card" style={{ padding: 20 }}><Skeleton lines={3} /></section>;
  if (cfg.isError) return <section className="card" style={{ padding: 20 }}><div className="banner banner-danger">LLM 配置加载失败：{cfg.error instanceof ApiError ? cfg.error.message : '未知错误'}</div></section>;
  if (!cfg.data) return <section className="card" style={{ padding: 20 }}><div className="banner banner-danger">LLM 配置数据异常</div></section>;

  const current = cfg.data;
  const changed = Object.keys(form).length > 0;

  const update = <K extends keyof LLMConfigUpdate>(k: K, v: LLMConfigUpdate[K]) => {
    setForm((prev) => ({ ...prev, [k]: v === '' ? null : v }));
    setTestMsg(null);
  };

  const save = () => {
    const body: LLMConfigUpdate = { ...form };
    if (body.api_key === '') body.api_key = null;
    saveMut.mutate(body);
  };

  return (
    <section className="card" style={{ padding: 20 }}>
      <h3 className="section-title">LLM 解析配置</h3>
      <p style={{ fontSize: 13, color: 'var(--color-text-secondary)', marginTop: -8, marginBottom: 12 }}>
        API Key 仅加密存储在本地，由您自担调用成本；未配置 Key 时上传的简历将标记为解析失败。
      </p>

      <div className="form-grid">
        <div className="form-field">
          <label>启用 LLM 解析</label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              type="checkbox"
              checked={form.enabled ?? current.enabled}
              onChange={(e) => update('enabled', e.target.checked)}
            />
            启用
          </label>
        </div>
        <div className="form-field">
          <label>提供方</label>
          <input
            value={form.provider ?? current.provider ?? ''}
            onChange={(e) => update('provider', e.target.value)}
            placeholder="openai"
          />
        </div>
        <div className="form-field">
          <label>Base URL（可选，兼容第三方代理）</label>
          <input
            value={form.base_url ?? current.base_url ?? ''}
            onChange={(e) => update('base_url', e.target.value)}
            placeholder="https://api.openai.com/v1"
          />
        </div>
        <div className="form-field">
          <label>模型</label>
          <input
            value={form.model ?? current.model ?? ''}
            onChange={(e) => update('model', e.target.value)}
            placeholder="gpt-4o-mini"
          />
        </div>
        <div className="form-field">
          <label>API Key{current.api_key_last4 && <span style={{ color: 'var(--color-text-secondary)', fontWeight: 'normal' }}>（已配置 ···{current.api_key_last4}）</span>}</label>
          <input
            type="password"
            value={form.api_key ?? ''}
            onChange={(e) => update('api_key', e.target.value)}
            placeholder={current.api_key_last4 ? '留空则保留原 Key' : 'sk-...'}
          />
        </div>
        <div className="form-field">
          <label>超时（秒）</label>
          <input
            type="number"
            min={1}
            value={form.timeout_seconds ?? current.timeout_seconds ?? 15}
            onChange={(e) => update('timeout_seconds', Number(e.target.value))}
          />
        </div>
        <div className="form-field">
          <label>最大 tokens</label>
          <input
            type="number"
            min={1}
            value={form.max_tokens ?? current.max_tokens ?? 2048}
            onChange={(e) => update('max_tokens', Number(e.target.value))}
          />
        </div>
      </div>

      {testMsg && (
        <div className={`banner ${testMsg.ok ? 'banner-success' : 'banner-danger'}`} style={{ marginTop: 12 }}>
          {testMsg.ok ? '连接成功' : `连接失败：${testMsg.text}`}
        </div>
      )}
      {error && <div className="banner banner-danger" style={{ marginTop: 12 }}>{error}</div>}
      {changed && <div className="banner banner-warning" style={{ marginTop: 12 }}>有未保存改动</div>}

      <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
        <button className="btn-primary" disabled={!changed || saveMut.isPending} onClick={save}>{saveMut.isPending ? '保存中…' : '保存'}</button>
        <button disabled={testMut.isPending} onClick={() => testMut.mutate()}>{testMut.isPending ? '测试中…' : '测试连接'}</button>
        {changed && <button onClick={() => { setForm({}); setTestMsg(null); }}>取消</button>}
      </div>
    </section>
  );
}

/** Agent 接入凭据（FR-25）—— 契约完整支持 */
function ApiKeys() {
  const qc = useQueryClient();
  const keys = useQuery({ queryKey: ['keys'], queryFn: () => api.listKeys(), retry: false });
  const [name, setName] = useState('');
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const createMut = useMutation({
    mutationFn: () => api.createKey({ name: name.trim() }),
    onSuccess: (k) => { setCreated(k); setName(''); setError(null); qc.invalidateQueries({ queryKey: ['keys'] }); },
    onError: (e) => setError(e instanceof ApiError ? e.message : String(e)),
  });
  const revokeMut = useMutation({
    mutationFn: (id: string) => api.revokeKey(id),
    onSuccess: () => { setRevoking(null); qc.invalidateQueries({ queryKey: ['keys'] }); },
    onError: (e) => setError(e instanceof ApiError ? e.message : String(e)),
  });

  return (
    <section className="card" style={{ padding: 20 }}>
      <h3 className="section-title">Agent 接入凭据（API 密钥）</h3>
      {keys.isLoading ? <Skeleton lines={2} /> : keys.isError ? (
        <div className="banner banner-warning">密钥列表加载失败：{keys.error instanceof ApiError ? keys.error.message : '未知错误'}。未配置不影响手动使用台账（§12）。</div>
      ) : (
        <>
          {(keys.data ?? []).length === 0 && (
            <p style={{ color: 'var(--color-text-secondary)' }}>尚未签发密钥。外部 Agent CLI 需要密钥才能调用系统 API；未配置不影响手动使用台账。</p>
          )}
          {(keys.data ?? []).map((k) => (
            <div key={k.id} className="card" style={{ padding: 12, marginBottom: 8, display: 'flex', gap: 12, alignItems: 'center', background: 'var(--color-bg)' }}>
              <strong>{k.name}</strong>
              <span className="mono" style={{ color: 'var(--color-text-secondary)' }}>{k.prefix}…</span>
              <span style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>创建于 {fmtDateTime(k.created_at)}{k.last_used_at ? ` · 最近调用 ${fmtDateTime(k.last_used_at)}` : ''}</span>
              <button className="btn-danger-outline" style={{ marginLeft: 'auto' }} onClick={() => setRevoking(k.id)}>吊销</button>
            </div>
          ))}
        </>
      )}
      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <input placeholder="密钥名称（如：本机 Agent CLI）" value={name} onChange={(e) => setName(e.target.value)} style={{ flex: 1 }} />
        <button className="btn-primary" disabled={!name.trim() || createMut.isPending} onClick={() => createMut.mutate()}>签发新密钥</button>
      </div>
      {error && <div className="banner banner-danger" style={{ marginTop: 8 }}>{error}</div>}

      {created && (
        <Modal title="密钥已签发" onClose={() => setCreated(null)} danger>
          <p>完整密钥仅此一次展示，请立即保存：</p>
          <div className="card mono" style={{ padding: 12, wordBreak: 'break-all', background: 'var(--color-bg)' }}>{created.key}</div>
          <div className="modal-actions">
            <button className="btn-primary" onClick={() => navigator.clipboard?.writeText(created.key)}>复制密钥</button>
            <button onClick={() => setCreated(null)}>我已保存</button>
          </div>
        </Modal>
      )}
      {revoking && (
        <Modal title="吊销密钥" onClose={() => setRevoking(null)} danger>
          <p>吊销后该 Agent <strong>立即停止访问</strong>，操作不可撤销。</p>
          <div className="modal-actions">
            <button onClick={() => setRevoking(null)}>取消</button>
            <button className="btn-danger-outline" disabled={revokeMut.isPending} onClick={() => revokeMut.mutate(revoking)}>确认吊销</button>
          </div>
        </Modal>
      )}
    </section>
  );
}

/** 提醒偏好（FR-32/OP-8）—— 契约缺口：偏好持久化端点缺失，暂存 localStorage */
function ReminderPrefs() {
  const [prefs, setPrefs] = useState(() => {
    try { return JSON.parse(localStorage.getItem('autohunt.reminders') ?? '{}'); } catch { return {}; }
  });
  const set = (k: string, v: boolean) => {
    const n = { h24: true, h1: true, deadline: true, ...prefs, [k]: v };
    setPrefs(n);
    localStorage.setItem('autohunt.reminders', JSON.stringify(n));
  };
  const v = { h24: true, h1: true, deadline: true, ...prefs };
  return (
    <section className="card" style={{ padding: 20 }}>
      <h3 className="section-title">提醒偏好</h3>
      <p style={{ fontSize: 12, color: 'var(--color-text-secondary)' }}>契约缺口：偏好持久化端点未在冻结契约中，当前暂存于本机浏览器。</p>
      {([['h24', '事件前 24 小时提醒'], ['h1', '事件前 1 小时提醒'], ['deadline', '包含网申截止提醒']] as const).map(([k, label]) => (
        <label key={k} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '6px 0' }}>
          <input type="checkbox" checked={v[k]} onChange={(e) => set(k, e.target.checked)} /> {label}
        </label>
      ))}
    </section>
  );
}

/** 数据管理（BR-20 本地优先） */
function DataManagement() {
  const [confirmText, setConfirmText] = useState('');
  return (
    <section className="card" style={{ padding: 20 }}>
      <h3 className="section-title">数据管理</h3>
      <p style={{ color: 'var(--color-text-secondary)' }}>
        本地优先存储（BR-20）：全部数据保存在本机后端数据目录（默认 <span className="mono">data/autohunt.db</span>），无云端账号。
      </p>
      <div className="banner banner-warning">契约缺口：「导出全部数据 / 清除全部数据」端点未在冻结契约中，待扩展后开放。</div>
      <div className="form-field" style={{ maxWidth: 320 }}>
        <label>清除全部数据（危险区）：输入「确认清除」解锁</label>
        <input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder="确认清除" />
      </div>
      <button className="btn-danger-outline" style={{ marginTop: 8 }} disabled={confirmText !== '确认清除'} title="待契约扩展">清除全部数据</button>
    </section>
  );
}
