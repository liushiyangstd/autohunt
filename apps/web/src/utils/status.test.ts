import { describe, expect, it } from 'vitest';
import { BOARD_CLOSED, BOARD_COLUMNS, isTerminal, manualTargets, RANK } from './status';

describe('BR-10 状态机展示规则', () => {
  it('主链 5 列顺序与契约一致', () => {
    expect(BOARD_COLUMNS).toEqual(['待投递', '已投递', '笔试', '面试', 'offer']);
  });

  it('主链 rank 递增，已接受/已拒绝 rank=5', () => {
    expect(RANK['待投递']).toBe(0);
    expect(RANK['offer']).toBe(4);
    expect(RANK['已接受']).toBe(5);
    expect(RANK['已拒绝']).toBe(5);
    expect(RANK['未通过']).toBeUndefined(); // 旁路终止态无 rank
  });

  it('已结束折叠列 = 旁路终止态 + 终态', () => {
    expect(BOARD_CLOSED).toContain('未通过');
    expect(BOARD_CLOSED).toContain('已接受');
    expect(BOARD_CLOSED).not.toContain('已投递');
  });

  it('UI 手动推进允许任意流转（含回退），仅排除当前态', () => {
    const targets = manualTargets('面试');
    expect(targets).toContain('已投递'); // 回退允许（用户知情修正）
    expect(targets).toContain('未通过');
    expect(targets).not.toContain('面试');
    expect(targets.length).toBe(9);
  });

  it('终态判定', () => {
    expect(isTerminal('已接受')).toBe(true);
    expect(isTerminal('已过期')).toBe(true);
    expect(isTerminal('笔试')).toBe(false);
  });
});
