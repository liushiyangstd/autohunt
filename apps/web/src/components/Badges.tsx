import type { ApplicationStatus } from '../api/types';
import { statusColor } from '../utils/status';

export function StatusBadge({ status }: { status: ApplicationStatus }) {
  const c = statusColor(status);
  return <span className="badge" style={{ color: c.fg, background: c.bg }}>{status}</span>;
}

export function ConfirmBadge({ status }: { status: '待确认' | '已确认' | '已驳回' | '已超时关闭' }) {
  const map = {
    待确认: { fg: 'var(--color-warning)', bg: 'var(--st-written-bg)' },
    已确认: { fg: 'var(--color-success)', bg: 'var(--st-offer-bg)' },
    已驳回: { fg: 'var(--color-danger)', bg: 'var(--st-rejected-bg)' },
    已超时关闭: { fg: 'var(--color-text-disabled)', bg: 'var(--st-closed-bg)' },
  } as const;
  const c = map[status];
  return <span className="badge" style={{ color: c.fg, background: c.bg }}>{status}</span>;
}

/** 来源标记（§2.1：邮箱识别 info 色 / Agent 回写 primary 色 / 手动无标记） */
export function SourceMark({ source }: { source: '邮箱识别' | 'Agent 回写' | '手动' }) {
  if (source === '手动') return null;
  const color = source === '邮箱识别' ? 'var(--color-info)' : 'var(--color-primary)';
  return (
    <span className="badge" title={`来源：${source}`} style={{ color, background: 'transparent', border: `1px solid ${color}`, padding: '0 8px' }}>
      {source === '邮箱识别' ? '✉' : '🤖'} {source}
    </span>
  );
}
