import { useEffect, useRef } from 'react';

export default function Modal({
  title, children, onClose, danger,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  danger?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    ref.current?.querySelector<HTMLElement>('button, input, textarea, [tabindex]')?.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="modal-mask" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal card fade-in" ref={ref} style={danger ? { borderTop: `3px solid var(--color-danger)` } : undefined}>
        <h3 style={{ marginTop: 0 }}>{title}</h3>
        {children}
      </div>
    </div>
  );
}
