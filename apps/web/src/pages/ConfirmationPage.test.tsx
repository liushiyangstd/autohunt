import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { ConfirmationDetail } from '../api/client';

/** 可变的 fake api —— 用 vi.hoisted 保证 mock factory 可访问 */
const h = vi.hoisted(() => {
  const state = {
    detail: null as ConfirmationDetail | null,
    calls: { confirm: [] as unknown[], reject: [] as unknown[], reissue: 0, close: 0 },
  };
  return { state };
});

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    mockMode: true,
    api: {
      getConfirmationDetail: vi.fn(() => Promise.resolve(h.state.detail)),
      listConfirmations: vi.fn(() => Promise.resolve({
        items: [{ id: 'cfm-1', application_id: 'app-1', status: h.state.detail?.status ?? '待确认', created_at: '2026-08-25T01:00:00Z' }],
        next_cursor: null,
      })),
      getProfile: vi.fn(() => Promise.resolve({
        name: '张三', phone: '13800001234', email: 'qiuzhi@example.com',
        educations: [{ school: '某大学' }], experiences: [], skills: [], awards: [],
        expected_city: '杭州', expected_position: null, resume_id: 'resume-1', resume_version: 1,
      })),
      listApplications: vi.fn(() => Promise.resolve({ items: [{ id: 'app-1', job_id: 'job-1', resume_id: 'resume-1', status: '待投递' }], next_cursor: null })),
      listJobs: vi.fn(() => Promise.resolve({ items: [{ id: 'job-1', company: '阿里巴巴', title: '后端开发工程师', created_at: '2026-08-20T00:00:00Z' }], next_cursor: null })),
      confirm: vi.fn((_id: string, body: { confirmed_fields: Record<string, string> }) => {
        h.state.calls.confirm.push(body);
        h.state.detail = {
          ...h.state.detail!, status: '已确认',
          confirmed_fields: body.confirmed_fields, submit_token: 'st_test', expires_at: '2026-08-25T14:00:00Z',
        };
        return Promise.resolve(h.state.detail);
      }),
      reject: vi.fn((_id: string, body: { reason?: string }) => {
        h.state.calls.reject.push(body);
        h.state.detail = { ...h.state.detail!, status: '已驳回', reason: body.reason };
        return Promise.resolve(h.state.detail);
      }),
      reissue: vi.fn(() => {
        h.state.calls.reissue += 1;
        h.state.detail = { ...h.state.detail!, submit_token: 'st_new', expires_at: '2026-08-25T15:00:00Z' };
        return Promise.resolve(h.state.detail);
      }),
      closeConfirmation: vi.fn(() => {
        h.state.calls.close += 1;
        h.state.detail = { ...h.state.detail!, status: '已超时关闭' };
        return Promise.resolve(undefined);
      }),
    },
  };
});

import ConfirmationPage from './ConfirmationPage';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/confirmations/cfm-1']}>
        <Routes><Route path="/confirmations/:id" element={<ConfirmationPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const pendingDetail: ConfirmationDetail = {
  id: 'cfm-1', application_id: 'app-1', status: '待确认',
  fields: { 姓名: '张三', 电话: '13800001234', 邮箱: 'qiuzhi@example.com' },
  created_at: '2026-08-25T01:00:00Z',
};

beforeEach(() => {
  h.state.detail = { ...pendingDetail, fields: { ...pendingDetail.fields } };
  h.state.calls = { confirm: [], reject: [], reissue: 0, close: 0 };
});

describe('D-06 人工确认界面（BR-1）', () => {
  it('待确认态：权限闸门显示锁定，对照表渲染快照与可编辑确认值', async () => {
    renderPage();
    expect(await screen.findByText(/未确认 · 系统不会放行提交/)).toBeInTheDocument();
    expect(screen.getByText('阿里巴巴 · 后端开发工程师')).toBeInTheDocument();
    // 快照值等宽展示，确认值输入框默认 = 快照值
    expect(screen.getByLabelText('确认值-姓名')).toHaveValue('张三');
    expect(screen.getByLabelText('确认值-电话')).toHaveValue('13800001234');
  });

  it('修改字段 → 行标「已修改」+ 可还原；确认后 confirmed_fields 携带修改值（AC-2 用户侧）', async () => {
    const user = userEvent.setup();
    renderPage();
    const phoneInput = await screen.findByLabelText('确认值-电话');
    await user.clear(phoneInput);
    await user.type(phoneInput, '13899998888');
    expect(screen.getByText('已修改')).toBeInTheDocument();
    expect(screen.getByText('1 处修改')).toBeInTheDocument();

    // 还原
    await user.click(screen.getByLabelText('还原-电话'));
    expect(screen.getByLabelText('确认值-电话')).toHaveValue('13800001234');

    // 再改并确认
    await user.clear(phoneInput);
    await user.type(phoneInput, '13899998888');
    await user.click(screen.getByRole('button', { name: '确认并允许提交' }));
    // 二次确认弹窗（BR-1 用户侧表达）
    expect(await screen.findByText(/提交动作不可撤销/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '确认无误，允许提交' }));

    await waitFor(() => expect(h.state.calls.confirm.length).toBe(1));
    expect(h.state.calls.confirm[0]).toEqual({
      confirmed_fields: { 姓名: '张三', 电话: '13899998888', 邮箱: 'qiuzhi@example.com' },
    });
    // 确认后：闸门变为放行
    expect(await screen.findByText(/已确认 · 提交许可已放行给 Agent/)).toBeInTheDocument();
  });

  it('必填字段清空后点确认 → 行内标红，不进入二次确认（校验反馈）', async () => {
    const user = userEvent.setup();
    renderPage();
    const phoneInput = await screen.findByLabelText('确认值-电话');
    await user.clear(phoneInput);
    await user.click(screen.getByRole('button', { name: '确认并允许提交' }));
    expect(await screen.findByText('必填字段不能为空')).toBeInTheDocument();
    expect(screen.queryByText(/提交动作不可撤销/)).not.toBeInTheDocument();
    expect(h.state.calls.confirm.length).toBe(0);
  });

  it('驳回必须填写原因，驳回后结果供 Agent 读取', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: '驳回' }));
    const okBtn = screen.getByRole('button', { name: '确认驳回' });
    expect(okBtn).toBeDisabled();
    await user.type(screen.getByLabelText('驳回原因'), '岗位与城市不符');
    await user.click(okBtn);
    await waitFor(() => expect(h.state.calls.reject).toEqual([{ reason: '岗位与城市不符' }]));
    expect(await screen.findByText(/已驳回：岗位与城市不符/)).toBeInTheDocument();
  });

  it('已确认但 token 已消耗 → 显示「重新放行」，点击调用 reissue（B-2 闭环 UI 侧）', async () => {
    h.state.detail = {
      ...pendingDetail, status: '已确认',
      confirmed_fields: { 姓名: '张三' }, submit_token: null, expires_at: '2026-08-25T13:00:00Z',
    };
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText(/提交许可已过期或已消耗/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '重新放行' }));
    await waitFor(() => expect(h.state.calls.reissue).toBe(1));
    expect(await screen.findByText(/有效期至/)).toBeInTheDocument();
  });

  it('Agent 提交失败 → 失败横幅 + 快照保留 + 转人工出口（FR-24）', async () => {
    h.state.detail = {
      ...pendingDetail, status: '已确认',
      confirmed_fields: { 姓名: '张三' }, submit_token: null,
      submit_result: 'failed', fail_reason: '验证码拦截', submitted_at: '2026-08-25T12:00:00Z',
    };
    renderPage();
    expect(await screen.findByText(/Agent 提交失败：验证码拦截/)).toBeInTheDocument();
    expect(screen.getByText(/转人工完成/)).toBeInTheDocument();
  });

  it('关闭任务 → 标记已超时关闭（PRD §12 主动出口，无自动超时）', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: '关闭任务' }));
    await user.click(await screen.findByRole('button', { name: '确认关闭' }));
    await waitFor(() => expect(h.state.calls.close).toBe(1));
    expect(await screen.findByText(/任务已手动关闭/)).toBeInTheDocument();
  });

  it('字段元数据高亮：必填缺失 + 低置信度（PROX-18）', async () => {
    h.state.detail = {
      ...pendingDetail,
      fields: { 姓名: '张三', 电话: '', 邮箱: 'qiuzhi@example.com' },
      context: {
        target_url: 'https://example.com/apply',
        _field_meta: JSON.stringify({
          姓名: { source: '结构化档案·基本信息', confidence: 'high', required: true, missing: false },
          电话: { source: '结构化档案·基本信息', confidence: 'low', required: true, missing: true },
          邮箱: { source: '结构化档案·基本信息', confidence: 'high', required: true, missing: false },
        }),
      },
    };
    renderPage();
    expect(await screen.findByText('必填缺失')).toBeInTheDocument();
    expect(screen.getByText('低置信度')).toBeInTheDocument();
  });
});
