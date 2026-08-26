export function EmptyState({ icon, text, action }: { icon?: string; text: string; action?: React.ReactNode }) {
  return (
    <div className="empty-state">
      <div style={{ fontSize: 36 }}>{icon ?? '📭'}</div>
      <p style={{ color: 'var(--color-text-secondary)' }}>{text}</p>
      {action}
    </div>
  );
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="card" style={{ padding: 16 }} aria-busy="true" aria-label="加载中">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton-line" style={{ width: `${90 - i * 15}%` }} />
      ))}
    </div>
  );
}
