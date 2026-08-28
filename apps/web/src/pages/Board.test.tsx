import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { Application, ApplicationList, Job, JobList } from '../api';

/** 可变的 fake api —— 用 vi.hoisted 保证 mock factory 可访问 */
const h = vi.hoisted(() => ({
  state: {
    jobs: [] as Job[],
    apps: [] as Application[],
  },
  updateApplication: vi.fn(),
}));

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    mockMode: true,
    api: {
      listJobs: vi.fn((): Promise<JobList> => Promise.resolve({ items: h.state.jobs, next_cursor: null })),
      listApplications: vi.fn((): Promise<ApplicationList> => Promise.resolve({ items: h.state.apps, next_cursor: null })),
      updateApplication: h.updateApplication,
    },
  };
});

import Board from './Board';

function renderBoard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/board']}>
        <Routes>
          <Route path="/board" element={<Board />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function job(partial: Partial<Job> & { id: string }): Job {
  return { company: '公司', title: '岗位', created_at: '2026-08-01T00:00:00Z', ...partial };
}

function app(partial: Partial<Application> & { id: string; job_id: string }): Application {
  return { resume_id: 'r1', status: '待投递', ...partial };
}

const cardOf = (name: string) => screen.getByText(name).closest('.board-card') as HTMLElement;

beforeEach(() => {
  h.state.jobs = [];
  h.state.apps = [];
  h.updateApplication.mockReset();
});

describe('Board 平铺布局与状态标签', () => {
  it('AC-1 无分列结构，全部岗位卡片平铺在一个 .board 容器中', async () => {
    h.state.jobs = [job({ id: 'j1', company: '蚂蚁', title: '前端' }), job({ id: 'j2', company: '字节', title: '后端' })];
    const { container } = renderBoard();
    await waitFor(() => expect(screen.getByText('蚂蚁')).toBeInTheDocument());
    expect(container.querySelector('.board-col')).toBeNull();
    const board = container.querySelector('.board') as HTMLElement;
    expect(within(board).getByText('蚂蚁')).toBeInTheDocument();
    expect(within(board).getByText('字节')).toBeInTheDocument();
    expect(container.querySelectorAll('.board-card')).toHaveLength(2);
  });

  it('AC-2 卡片状态标签：无记录 → 待投递；有记录 → 最新记录状态；面试含轮次徽标', async () => {
    h.state.jobs = [job({ id: 'j1', company: '蚂蚁', title: '前端' }), job({ id: 'j2', company: '腾讯', title: '后台' })];
    h.state.apps = [app({ id: 'a1', job_id: 'j2', status: '面试', interview_round: 2 })];
    renderBoard();
    await waitFor(() => expect(screen.getByText('蚂蚁')).toBeInTheDocument());
    expect(within(cardOf('蚂蚁')).getByText('待投递', { selector: '.badge' })).toBeInTheDocument();
    expect(within(cardOf('腾讯')).getByText('面试', { selector: '.badge' })).toBeInTheDocument();
    expect(within(cardOf('腾讯')).getByText('面试·二面')).toBeInTheDocument();
  });

  it('AC-2b 同一岗位多条投递记录 → 卡片只出现一次，按列表中最新（靠后）记录显示状态', async () => {
    h.state.jobs = [job({ id: 'j1', company: '蚂蚁', title: '前端' })];
    h.state.apps = [app({ id: 'a1', job_id: 'j1', status: '待投递' }), app({ id: 'a2', job_id: 'j1', status: '笔试' })];
    renderBoard();
    await waitFor(() => expect(screen.getByText('蚂蚁')).toBeInTheDocument());
    expect(screen.getAllByText('蚂蚁')).toHaveLength(1);
    expect(within(cardOf('蚂蚁')).getByText('笔试', { selector: '.badge' })).toBeInTheDocument();
  });

  it('AC-3 卡片不可拖拽（无 draggable 属性）', async () => {
    h.state.jobs = [job({ id: 'j1', company: '蚂蚁', title: '前端' }), job({ id: 'j2', company: '字节', title: '后端' })];
    h.state.apps = [app({ id: 'a1', job_id: 'j2', status: '待投递' })];
    renderBoard();
    await waitFor(() => expect(screen.getByText('蚂蚁')).toBeInTheDocument());
    expect(cardOf('蚂蚁')).not.toHaveAttribute('draggable', 'true');
    expect(cardOf('字节')).not.toHaveAttribute('draggable', 'true');
  });

  it('AC-7 页面无「未投递」文案', async () => {
    h.state.jobs = [job({ id: 'j1', company: '蚂蚁', title: '前端' })];
    renderBoard();
    await waitFor(() => expect(screen.getByText('蚂蚁')).toBeInTheDocument());
    expect(screen.queryByText('未投递')).not.toBeInTheDocument();
  });
});

describe('Board 卡片内改状态', () => {
  it('AC-4 有记录卡片可下拉改状态并出现撤销 toast；撤销回退', async () => {
    const user = userEvent.setup();
    h.state.jobs = [job({ id: 'j1', company: '蚂蚁', title: '前端' })];
    h.state.apps = [app({ id: 'a1', job_id: 'j1', status: '待投递' })];
    renderBoard();
    await waitFor(() => expect(screen.getByText('蚂蚁')).toBeInTheDocument());

    await user.selectOptions(within(cardOf('蚂蚁')).getByLabelText('修改状态'), '已投递');
    expect(h.updateApplication).toHaveBeenCalledWith('a1', { status: '已投递' });
    expect(screen.getByText(/状态已更新：待投递 → 已投递/)).toBeInTheDocument();

    await user.click(screen.getByText('撤销'));
    expect(h.updateApplication).toHaveBeenCalledWith('a1', { status: '待投递' });
  });

  it('AC-4b 无投递记录卡片无改状态入口', async () => {
    h.state.jobs = [job({ id: 'j1', company: '蚂蚁', title: '前端' })];
    renderBoard();
    await waitFor(() => expect(screen.getByText('蚂蚁')).toBeInTheDocument());
    expect(within(cardOf('蚂蚁')).queryByLabelText('修改状态')).not.toBeInTheDocument();
  });
});

describe('Board 状态过滤', () => {
  it('AC-5 勾选「待投递」同时命中无记录岗位与待投递记录岗位', async () => {
    const user = userEvent.setup();
    h.state.jobs = [
      job({ id: 'j1', company: '蚂蚁', title: '前端' }),
      job({ id: 'j2', company: '字节', title: '后端' }),
      job({ id: 'j3', company: '腾讯', title: '后台' }),
    ];
    h.state.apps = [
      app({ id: 'a1', job_id: 'j2', status: '待投递' }),
      app({ id: 'a2', job_id: 'j3', status: '笔试' }),
    ];
    renderBoard();
    await waitFor(() => expect(screen.getByText('蚂蚁')).toBeInTheDocument());

    await user.click(screen.getByText('状态筛选'));
    await user.click(screen.getByRole('checkbox', { name: '待投递' }));
    expect(screen.getByText('蚂蚁')).toBeInTheDocument();
    expect(screen.getByText('字节')).toBeInTheDocument();
    expect(screen.queryByText('腾讯')).not.toBeInTheDocument();
  });

  it('AC-5b 多选状态取并集；取消勾选恢复全部', async () => {
    const user = userEvent.setup();
    h.state.jobs = [job({ id: 'j1', company: '蚂蚁', title: '前端' }), job({ id: 'j2', company: '字节', title: '后端' }), job({ id: 'j3', company: '腾讯', title: '后台' })];
    h.state.apps = [
      app({ id: 'a1', job_id: 'j2', status: '笔试' }),
      app({ id: 'a2', job_id: 'j3', status: '面试' }),
    ];
    renderBoard();
    await waitFor(() => expect(screen.getByText('蚂蚁')).toBeInTheDocument());

    await user.click(screen.getByText('状态筛选'));
    await user.click(screen.getByRole('checkbox', { name: '笔试' }));
    await user.click(screen.getByRole('checkbox', { name: '面试' }));
    expect(screen.queryByText('蚂蚁')).not.toBeInTheDocument();
    expect(screen.getByText('字节')).toBeInTheDocument();
    expect(screen.getByText('腾讯')).toBeInTheDocument();

    await user.click(screen.getByRole('checkbox', { name: '笔试' }));
    await user.click(screen.getByRole('checkbox', { name: '面试' }));
    expect(screen.getByText('蚂蚁')).toBeInTheDocument();
    expect(screen.getByText('字节')).toBeInTheDocument();
    expect(screen.getByText('腾讯')).toBeInTheDocument();
  });

  it('AC-6 状态过滤与关键词、渠道筛选叠加生效', async () => {
    const user = userEvent.setup();
    h.state.jobs = [
      job({ id: 'j1', company: '蚂蚁', title: '前端', channel: 'BOSS直聘' }),
      job({ id: 'j2', company: '字节', title: '后端', channel: '牛客' }),
    ];
    renderBoard();
    await waitFor(() => expect(screen.getByText('蚂蚁')).toBeInTheDocument());

    // 两岗位均无记录（待投递）：勾选待投递后渠道筛选仍生效
    await user.click(screen.getByText('状态筛选'));
    await user.click(screen.getByRole('checkbox', { name: '待投递' }));
    await user.selectOptions(screen.getByLabelText('渠道筛选'), '牛客');
    expect(screen.queryByText('蚂蚁')).not.toBeInTheDocument();
    expect(screen.getByText('字节')).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText('搜索公司 / 岗位（FR-12）'), '不存在');
    expect(screen.queryByText('字节')).not.toBeInTheDocument();
  });

  it('AC-6b 零岗位 → 空态录入引导', async () => {
    renderBoard();
    await waitFor(() => expect(screen.getByText('还没有岗位记录')).toBeInTheDocument());
    expect(screen.getByText('录入第一个岗位')).toBeInTheDocument();
  });
});
