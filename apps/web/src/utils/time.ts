/** 时间工具：RFC3339 UTC 存储，前端本地化展示（契约 §3 通用约定） */

export function fmtDateTime(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fmtDate(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** 已挂起时长（D-01/D-06）：>24h 由调用方决定 warning 化 */
export function pendingDuration(createdIso: string, nowMs = Date.now()): { text: string; hours: number } {
  const ms = nowMs - new Date(createdIso).getTime();
  const hours = Math.max(0, ms / 3600_000);
  if (hours < 1) return { text: `${Math.floor(hours * 60)} 分钟`, hours };
  if (hours < 24) return { text: `${Math.floor(hours)} 小时`, hours };
  return { text: `${Math.floor(hours / 24)} 天 ${Math.floor(hours % 24)} 小时`, hours };
}

/** 距截止天数（D-04 卡片）：负数表示已过 */
export function daysUntil(iso?: string | null, nowMs = Date.now()): number | null {
  if (!iso) return null;
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return null;
  return Math.ceil((d - nowMs) / 86400_000);
}

export function withinHours(iso: string, h: number, nowMs = Date.now()): boolean {
  const t = new Date(iso).getTime();
  return t >= nowMs && t <= nowMs + h * 3600_000;
}
