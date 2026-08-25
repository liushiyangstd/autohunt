import type { ApplicationStatus } from '../api/types';

/** BR-10 主链 rank（技设 §5）；旁路终止态无 rank */
export const MAIN_CHAIN: ApplicationStatus[] = ['待投递', '已投递', '笔试', '面试', 'offer'];
export const TERMINAL_OK: ApplicationStatus[] = ['已接受', '已拒绝'];
export const SIDE_TERMINAL: ApplicationStatus[] = ['未通过', '主动放弃', '已过期'];

export const RANK: Partial<Record<ApplicationStatus, number>> = {
  待投递: 0, 已投递: 1, 笔试: 2, 面试: 3, offer: 4, 已接受: 5, 已拒绝: 5,
};

export function isTerminal(s: ApplicationStatus): boolean {
  return TERMINAL_OK.includes(s) || SIDE_TERMINAL.includes(s);
}

/** 看板列（D-04）：主链 5 列 + 已结束折叠列 */
export const BOARD_COLUMNS: ApplicationStatus[] = MAIN_CHAIN;
export const BOARD_CLOSED: ApplicationStatus[] = [...SIDE_TERMINAL, ...TERMINAL_OK];

export type Source = '手动' | '邮箱识别' | 'Agent 回写';

const STATUS_COLOR: Record<ApplicationStatus, { fg: string; bg: string }> = {
  待投递: { fg: 'var(--st-pending)', bg: 'var(--st-pending-bg)' },
  已投递: { fg: 'var(--st-submitted)', bg: 'var(--st-submitted-bg)' },
  笔试: { fg: 'var(--st-written)', bg: 'var(--st-written-bg)' },
  面试: { fg: 'var(--st-interview)', bg: 'var(--st-interview-bg)' },
  offer: { fg: 'var(--st-offer)', bg: 'var(--st-offer-bg)' },
  已接受: { fg: 'var(--st-accepted)', bg: 'var(--st-accepted-bg)' },
  已拒绝: { fg: 'var(--st-rejected)', bg: 'var(--st-rejected-bg)' },
  未通过: { fg: 'var(--st-rejected)', bg: 'var(--st-rejected-bg)' },
  主动放弃: { fg: 'var(--st-closed)', bg: 'var(--st-closed-bg)' },
  已过期: { fg: 'var(--st-closed)', bg: 'var(--st-closed-bg)' },
};

export function statusColor(s: ApplicationStatus) {
  return STATUS_COLOR[s];
}

/** UI 手动推进的合法目标（技设 §5：UI 允许任意合法流转，含回退） */
export function manualTargets(current: ApplicationStatus): ApplicationStatus[] {
  const all: ApplicationStatus[] = [...MAIN_CHAIN, ...TERMINAL_OK, ...SIDE_TERMINAL];
  return all.filter((s) => s !== current);
}
