import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api, mockMode } from '../api';

const NAV = [
  { to: '/', label: '工作台', icon: '🏠' },
  { to: '/resumes', label: '简历库', icon: '📄' },
  { to: '/board', label: '岗位看板', icon: '🗂️' },
  { to: '/schedule', label: '日程', icon: '📅' },
  { to: '/stats', label: '统计', icon: '📊' },
  { to: '/settings', label: '设置', icon: '⚙️' },
];

function usePendingCount(): number {
  const events = useQuery({ queryKey: ['events', 'pending'], queryFn: () => api.listPendingEvents(), retry: false });
  const cfms = useQuery({
    queryKey: ['confirmations', 'pending'],
    queryFn: () => api.listPendingConfirmations(),
    retry: false,
  });
  return (events.data?.items.length ?? 0) + (cfms.data?.length ?? 0);
}

export default function Layout() {
  const pending = usePendingCount();
  const [drawer, setDrawer] = useState(false);
  const location = useLocation();
  const title = NAV.find((n) => (n.to === '/' ? location.pathname === '/' : location.pathname.startsWith(n.to)))?.label
    ?? (location.pathname.startsWith('/confirmations') ? '投递确认' : location.pathname.startsWith('/jobs') ? '岗位详情' : '工作台');

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
          <Outlet />
        </main>
      </div>
    </div>
  );
}
