import { useEffect, useState } from 'react';

/** <768 提示页（DESIGN §2.3：MVP 不做移动端） */
export default function BreakpointGate({ children }: { children: React.ReactNode }) {
  const [narrow, setNarrow] = useState(() => typeof window !== 'undefined' && window.innerWidth < 768);
  useEffect(() => {
    const onResize = () => setNarrow(window.innerWidth < 768);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);
  if (narrow) {
    return (
      <div style={{ display: 'grid', placeItems: 'center', height: '100vh', padding: 24, textAlign: 'center' }}>
        <div>
          <div style={{ fontSize: 40, marginBottom: 16 }}>🖥️</div>
          <h2>请使用桌面浏览器</h2>
          <p style={{ color: 'var(--color-text-secondary)' }}>autohunt 当前版本面向桌面端（≥768px），移动端体验将在后续版本提供。</p>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
