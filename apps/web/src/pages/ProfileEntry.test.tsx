import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { ResumeInfo } from '../api';
import Layout from '../components/Layout';
import Resumes from './Resumes';

/** 可变的 fake api —— 用 vi.hoisted 保证 mock factory 可访问 */
const h = vi.hoisted(() => {
  const state = {
    resumes: [] as ResumeInfo[],
    upload: vi.fn(),
  };
  return { state };
});

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    mockMode: true,
    api: {
      listResumes: vi.fn(() => Promise.resolve({ items: h.state.resumes, next_cursor: null })),
      uploadResume: h.state.upload,
      updateResume: vi.fn(() => Promise.resolve(h.state.resumes[0])),
      deleteResume: vi.fn(() => Promise.resolve(undefined)),
      listResumeReferences: vi.fn(() => Promise.resolve({ items: [], next_cursor: null })),
      resumeFileUrl: vi.fn((id: string) => `#file-${id}`),
      listPendingEvents: vi.fn(() => Promise.resolve({ items: [] })),
      listConfirmations: vi.fn(() => Promise.resolve({ items: [], next_cursor: null })),
      listEmailAccounts: vi.fn(() => Promise.resolve({ items: [] })),
    },
  };
});

function renderResumes() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/resumes']}>
        <Routes>
          <Route path="/resumes" element={<Resumes />} />
          <Route path="/profile" element={<div>档案编辑占位</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderLayout() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/resumes']}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<div>工作台占位</div>} />
            <Route path="resumes" element={<div>简历库占位</div>} />
            <Route path="profile" element={<div>档案编辑占位</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  h.state.resumes = [];
  h.state.upload.mockReset();
});

describe('PROX-15 档案编辑入口体验', () => {
  it('左侧导航出现「档案编辑」，点击进入 /profile，页面标题为档案编辑', async () => {
    const user = userEvent.setup();
    renderLayout();
    const navLink = screen.getByRole('link', { name: /档案编辑/ });
    expect(navLink).toHaveAttribute('href', '/profile');
    await user.click(navLink);
    expect(await screen.findByText('档案编辑占位')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: '档案编辑' })).toBeInTheDocument();
  });

  it('每张简历卡片有「查看/编辑档案」入口，指向对应版本', async () => {
    h.state.resumes = [
      { id: 'r-1', name: '简历 A', version: 1, is_default: true, parse_status: '解析完成', missing_fields: [], used_count: 0, created_at: '2026-08-27T01:00:00Z' },
      { id: 'r-2', name: '简历 B', version: 2, is_default: false, parse_status: '解析失败', missing_fields: ['name'], parse_error: '解析超时', used_count: 1, created_at: '2026-08-27T02:00:00Z' },
    ];
    renderResumes();
    const links = await screen.findAllByRole('link', { name: '查看/编辑档案' });
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute('href', '/profile?resume=r-1');
    expect(links[1]).toHaveAttribute('href', '/profile?resume=r-2');
  });

  it('上传 PDF 成功后自动跳转到新版本的档案编辑页', async () => {
    const user = userEvent.setup();
    h.state.upload.mockResolvedValue({
      id: 'r-new', name: '新简历', version: 1, is_default: true, parse_status: '解析中', missing_fields: [], used_count: 0, created_at: '2026-08-27T03:00:00Z',
    });
    const { container } = renderResumes();
    await waitFor(() => expect(container.querySelector('input[type="file"]')).not.toBeNull());
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(['fake'], 'resume.pdf', { type: 'application/pdf' }));
    expect(await screen.findByText('档案编辑占位')).toBeInTheDocument();
    expect(h.state.upload).toHaveBeenCalledTimes(1);
  });

  it('上传失败不跳转，仅显示错误横幅', async () => {
    const user = userEvent.setup();
    const { ApiError } = await import('../api');
    h.state.upload.mockRejectedValue(new ApiError(413, 'TOO_LARGE', '简历大小超过 10MB'));
    const { container } = renderResumes();
    await waitFor(() => expect(container.querySelector('input[type="file"]')).not.toBeNull());
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(['fake'], 'resume.pdf', { type: 'application/pdf' }));
    expect(await screen.findByText('简历大小超过 10MB')).toBeInTheDocument();
    expect(screen.queryByText('档案编辑占位')).not.toBeInTheDocument();
  });
});
