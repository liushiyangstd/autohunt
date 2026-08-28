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
}));

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    mockMode: true,
    api: {
      listJobs: vi.fn((): Promise<JobList> => Promise.resolve({ items: h.state.jobs, next_cursor: null })),
      listApplications: vi.fn((): Promise<ApplicationList> => Promise.resolve({ items: h.state.apps, next_cursor: null })),
      updateApplication: vi.fn(),
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

/** 按列标题定位列容器 */
function column(title: string): HTMLElement {
  const colTitle = screen.getAllByText(title).find((el) => el.classList.contains('board-col-title') || el.parentElement?.classList.contains('board-col-title'));
  const col = colTitle?.closest('.board-col');
  if (!col) throw new Error(`列不存在: ${title}`);
  return col as HTMLElement;
}

beforeEach(() => {
  h.state.jobs = [];
  h.state.apps = [];
});

describe('Board 归列逻辑', () => {
  it('AC-1 有岗位无投递记录 → 全部进未投递列，其余列计数 0', async () => {
    h.state.jobs = [job({ id: 'j1', company: '蚂蚁', title: '前端' }), job({ id: 'j2', company: '字节', title: '后端' })];
    renderBoard();
    await waitFor(() => expect(within(column('未投递')).getAllByText('未投递', { selector: '.badge' })).toHaveLength(2));
    expect(within(column('未投递')).getByText('蚂蚁')).toBeInTheDocument();
    expect(within(column('未投递')).getByText('字节')).toBeInTheDocument();
    for (const col of ['待投递', '已投递', '笔试', '面试', 'offer', '已结束']) {
      expect(within(column(col)).getByText('0')).toBeInTheDocument();
    }
  });

  it('AC-2 岗位有投递记录 → 归对应状态列；面试含轮次徽标', async () => {
    h.state.jobs = [job({ id: 'j1', company: '蚂蚁', title: '前端' }), job({ id: 'j2', company: '腾讯', title: '后台' })];
    h.state.apps = [
      app({ id: 'a1', job_id: 'j1', status: '已投递' }),
      app({ id: 'a2', job_id: 'j2', status: '面试', interview_round: 2 }),
    ];
    renderBoard();
    await waitFor(() => expect(within(column('已投递')).getByText('蚂蚁')).toBeInTheDocument());
    expect(within(column('面试')).getByText('腾讯')).toBeInTheDocument();
    expect(within(column('面试')).getByText('面试·二面')).toBeInTheDocument();
    expect(within(column('未投递')).queryByText('蚂蚁')).not.toBeInTheDocument();
  });

  it('AC-3 同一岗位多条投递记录 → 卡片只出现一次，按列表中最新（靠后）记录归列', async () => {
    h.state.jobs = [job({ id: 'j1', company: '蚂蚁', title: '前端' })];
    // 后端按 seq 升序返回：a1 先建（待投递），a2 后建（笔试）→ 归笔试列
    h.state.apps = [app({ id: 'a1', job_id: 'j1', status: '待投递' }), app({ id: 'a2', job_id: 'j1', status: '笔试' })];
    renderBoard();
    await waitFor(() => expect(within(column('笔试')).getByText('蚂蚁')).toBeInTheDocument());
    expect(screen.getAllByText('蚂蚁')).toHaveLength(1);
    expect(within(column('待投递')).queryByText('蚂蚁')).not.toBeInTheDocument();
  });

  it('AC-4 未投递卡片不可拖拽；有投递记录卡片可拖拽', async () => {
    h.state.jobs = [job({ id: 'j1', company: '蚂蚁', title: '前端' }), job({ id: 'j2', company: '字节', title: '后端' })];
    h.state.apps = [app({ id: 'a1', job_id: 'j2', status: '待投递' })];
    const { container } = renderBoard();
    await waitFor(() => expect(screen.getByText('蚂蚁')).toBeInTheDocument());
    const cardOf = (name: string) => screen.getByText(name).closest('.board-card') as HTMLElement;
    expect(cardOf('蚂蚁')).not.toHaveAttribute('draggable', 'true');
    expect(cardOf('字节')).toHaveAttribute('draggable', 'true');
    expect(container.querySelectorAll('.board-card')).toHaveLength(2);
  });

  it('AC-5 关键词搜索与渠道筛选作用于未投递列', async () => {
    const user = userEvent.setup();
    h.state.jobs = [
      job({ id: 'j1', company: '蚂蚁', title: '前端', channel: 'BOSS直聘' }),
      job({ id: 'j2', company: '字节', title: '后端', channel: '牛客' }),
    ];
    renderBoard();
    await waitFor(() => expect(screen.getByText('蚂蚁')).toBeInTheDocument());

    await user.type(screen.getByPlaceholderText('搜索公司 / 岗位（FR-12）'), '蚂蚁');
    expect(within(column('未投递')).getByText('蚂蚁')).toBeInTheDocument();
    expect(within(column('未投递')).queryByText('字节')).not.toBeInTheDocument();

    await user.clear(screen.getByPlaceholderText('搜索公司 / 岗位（FR-12）'));
    await user.selectOptions(screen.getByLabelText('渠道筛选'), '牛客');
    expect(within(column('未投递')).getByText('字节')).toBeInTheDocument();
    expect(within(column('未投递')).queryByText('蚂蚁')).not.toBeInTheDocument();
  });

  it('AC-6 零岗位 → 空态录入引导；有岗位无投递记录时不显示「还没有投递记录」', async () => {
    const { unmount } = renderBoard();
    await waitFor(() => expect(screen.getByText('还没有岗位记录')).toBeInTheDocument());
    expect(screen.getByText('录入第一个岗位')).toBeInTheDocument();
    unmount();

    h.state.jobs = [job({ id: 'j1', company: '蚂蚁', title: '前端' })];
    renderBoard();
    await waitFor(() => expect(screen.getByText('蚂蚁')).toBeInTheDocument());
    expect(screen.queryByText('还没有投递记录')).not.toBeInTheDocument();
  });
});
