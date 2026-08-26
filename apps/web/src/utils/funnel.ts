import { RANK } from './status';
import type { Application as App, ApplicationStatus } from '../api/types';

/**
 * 统计口径（PRD §10.4，已确认）：
 * - 漏斗范围：状态 ≠ 待投递
 * - 笔试转化率 = 进入笔试数 / 已投递及以后数
 * - 面试转化率 = 进入面试数 / 进入笔试数（无笔试环节不剔除）
 * - offer 转化率 = 进入 offer 数 / 全部已投递数
 *
 * 实现口径说明（已知限制）：冻结契约无 status_history 端点，"进入过 X 状态"
 * 以当前状态 rank 近似（rank ≥ X 视为已进入）；旁路终止态（未通过等）无 rank，
 * 按应用当前状态无法归级时不计入任何漏斗级 —— 待契约扩展历史端点后修正。
 */

export interface FunnelStage { label: string; count: number; rateFromPrev: number | null }

export function reached(status: ApplicationStatus, rank: number): boolean {
  const r = RANK[status];
  return r !== undefined && r >= rank;
}

export function funnel(apps: Pick<App, 'status'>[]): {
  stages: FunnelStage[];
  total: number;
  active: number;
  offers: number;
} {
  const inScope = apps.filter((a) => a.status !== '待投递');
  const submitted = inScope.filter((a) => reached(a.status, 1)).length;
  const written = inScope.filter((a) => reached(a.status, 2)).length;
  const interview = inScope.filter((a) => reached(a.status, 3)).length;
  const offer = inScope.filter((a) => reached(a.status, 4)).length;
  const rate = (num: number, den: number) => (den === 0 ? null : num / den);
  return {
    stages: [
      { label: '已投递', count: submitted, rateFromPrev: null },
      { label: '笔试', count: written, rateFromPrev: rate(written, submitted) },
      { label: '面试', count: interview, rateFromPrev: rate(interview, written) },
      { label: 'offer', count: offer, rateFromPrev: rate(offer, submitted) },
    ],
    total: apps.length,
    active: apps.filter((a) => ['已投递', '笔试', '面试', 'offer'].includes(a.status)).length,
    offers: offer + apps.filter((a) => a.status === '已接受').length,
  };
}

export function metrics(apps: App[], pendingCount: number) {
  return {
    total: apps.length,
    active: apps.filter((a) => ['已投递', '笔试', '面试', 'offer'].includes(a.status)).length,
    pending: pendingCount,
    offers: apps.filter((a) => a.status === 'offer' || a.status === '已接受').length,
  };
}
