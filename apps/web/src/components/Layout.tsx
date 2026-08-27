import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api, mockMode } from '../api';

const NAV = [
  { to: '/', label: '工作台', icon: '🏠' },
  { to: '/resumes', label: '简历库', icon: '📄' },
  { to: '/profile', label: '档案编辑', icon: '✏️' },
  { to: '/board', label: '岗位看板', icon: '🗂️' },
  { to: '/schedule', label: '日程', icon: '📅' },
  { to: '/stats', label: '统计', icon: '📊' },
  { to: '/settings', label: '设置', icon: '⚙️' },
];

function usePendingCount(): number {
  const events = useQuery({ queryKey: ['events', 'pending'], queryFn: () => api.listPendingEvents(), retry: false });
  const cfms = useQuery({
    queryKey: ['confirmations', 'pending'],
    queryFn: () => api.listConfirmations({ status: '待确认' }),
    retry: false,
  });
  return (events.data?.items.length ?? 0) + (cfms.data?.items.length ?? 0);
}

/** AC-8：任一绑定邮箱授权失效 → 顶部持续警示条（历史数据保留，重授权在设置页） */
function AuthFailedBanner() {
  const accounts = useQuery({ queryKey: ['email-accounts'], queryFn: () => api.listEmailAccounts(), retry: false });
  const failed = (accounts.data?.items ?? []).filter((a) => a.status === 'auth_failed');
  if (failed.length === 0) return null;
  return (
    <div className="banner banner-danger" style={{ margin: '0 0 12px' }}>
      求职邮箱 {failed.map((a) => a.email).join('、')} 授权已失效，邮箱监控已暂停（历史数据保留）。
      <NavLink to="/settings" style={{ marginLeft: 8, fontWeight: 600 }}>前往设置重授权 →</NavLink>
    </div>
  );
}

export default function Layout() {
  const pending = usePendingCount();
  const [drawer, setDrawer] = useState(false);
  const location = useLocation();
  const title = NAV.find((n) => (n.to === '/' ? location.pathname === '/' : location.pathname.startsWith(n.to)))?.label
    ?? (location.pathname.startsWith('/confirmations') ? '投递确认'
      : location.pathname === '/jobs/new' ? '录入岗位'
        : location.pathname.startsWith('/jobs') ? '岗位详情' : '工作台');

  return (
    <div className="app-shell">
      <aside className={`app-nav ${drawer ? 'open' : ''}`}>
        <div className="app-logo">autohunt</div>
        {NAV.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={n.to === '/'}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
            onClick={() => setDrawer(false)}
          >
            <span className="nav-icon">{n.icon}</span>
            <span className="nav-label">{n.label}</span>
            {n.to === '/' && pending > 0 && <span className="nav-dot num">{pending}</span>}
          </NavLink>
        ))}
      </aside>
      {drawer && <div className="drawer-mask" onClick={() => setDrawer(false)} />}
      <div className="app-main">
        <header className="app-topbar">
          <button className="nav-burger" aria-label="菜单" onClick={() => setDrawer(true)}>☰</button>
          <h1 className="page-title">{title}</h1>
          {mockMode && <span className="badge" style={{ background: 'var(--st-written-bg)', color: 'var(--st-written)' }}>Mock 模式（后端未接入）</span>}
        </header>
        <main className="app-content">
          <AuthFailedBanner />
          <Outlet />
        </main>
      </div>
    </div>
  );
}
