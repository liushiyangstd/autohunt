import { describe, expect, it } from 'vitest';
import { funnel, reached, metrics } from './funnel';
import type { Application } from '../api/types';

const app = (status: Application['status']): Pick<Application, 'status'> => ({ status });

describe('投递漏斗（PRD §10.4 口径）', () => {
  it('「待投递」不计入漏斗范围', () => {
    const f = funnel([app('待投递'), app('已投递')]);
    expect(f.stages[0].count).toBe(1); // 已投递级只含 1 条
  });

  it('笔试转化率 = 进入笔试数 / 已投递及以后数', () => {
    const f = funnel([app('已投递'), app('已投递'), app('笔试'), app('面试')]);
    // 已投递及以后 = 4；进入笔试 = 2（笔试+面试）
    expect(f.stages[1].count).toBe(2);
    expect(f.stages[1].rateFromPrev).toBeCloseTo(0.5);
  });

  it('面试转化率 = 进入面试数 / 进入笔试数', () => {
    const f = funnel([app('笔试'), app('笔试'), app('面试'), app('offer')]);
    expect(f.stages[1].count).toBe(4); // 进入笔试 = 笔试×2 + 面试 + offer
    expect(f.stages[2].count).toBe(2); // 进入面试 = 面试 + offer
    expect(f.stages[2].rateFromPrev).toBeCloseTo(0.5);
  });

  it('offer 转化率 = 进入 offer 数 / 全部已投递数', () => {
    const f = funnel([app('已投递'), app('笔试'), app('面试'), app('offer'), app('已接受')]);
    expect(f.stages[3].count).toBe(2); // offer + 已接受
    expect(f.stages[3].rateFromPrev).toBeCloseTo(2 / 5);
  });

  it('分母为 0 时转化率为 null（不显示 NaN）', () => {
    const f = funnel([app('待投递')]);
    expect(f.stages[1].rateFromPrev).toBeNull();
  });

  it('旁路终止态无 rank，不归级进入任何漏斗级', () => {
    const f = funnel([app('未通过'), app('主动放弃'), app('已过期')]);
    expect(f.stages.every((s) => s.count === 0)).toBe(true);
  });

  it('reached：rank 近似判定', () => {
    expect(reached('面试', 2)).toBe(true);
    expect(reached('笔试', 3)).toBe(false);
    expect(reached('未通过', 1)).toBe(false);
  });
});

describe('关键指标卡（FR-52）', () => {
  it('进行中 = 已投递/笔试/面试/offer；offer 数含已接受', () => {
    const apps = [
      { status: '待投递' }, { status: '已投递' }, { status: '面试' },
      { status: 'offer' }, { status: '已接受' }, { status: '未通过' },
    ] as Application[];
    const m = metrics(apps, 3);
    expect(m.total).toBe(6);
    expect(m.active).toBe(3);
    expect(m.offers).toBe(2);
    expect(m.pending).toBe(3);
  });
});
