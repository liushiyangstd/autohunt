import { describe, expect, it, vi, beforeEach } from 'vitest';
import { StrictMode } from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { CrawlRequest, CrawlResult } from '../api';
import type { CreateJobResult, JobUpdate } from '../api/types';

/** 可变的 fake api —— 用 vi.hoisted 保证 mock factory 可访问 */
const h = vi.hoisted(() => ({
  state: {
    crawlResult: null as CrawlResult | null,
    crawlError: null as unknown,
    createResult: null as CreateJobResult | null,
    calls: {
      crawl: [] as CrawlRequest[],
      create: [] as unknown[],
      update: [] as { id: string; body: JobUpdate }[],
    },
  },
}));

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    mockMode: true,
    api: {
      crawlJob: vi.fn((body: CrawlRequest) => {
        h.state.calls.crawl.push(body);
        return h.state.crawlError ? Promise.reject(h.state.crawlError) : Promise.resolve(h.state.crawlResult);
      }),
      createJob: vi.fn((body: unknown) => {
        h.state.calls.create.push(body);
        return Promise.resolve(h.state.createResult);
      }),
      updateJob: vi.fn((id: string, body: JobUpdate) => {
        h.state.calls.update.push({ id, body });
        return Promise.resolve({ id });
      }),
    },
  };
});

import JobNew, { decodePrefill, guessSource } from './JobNew';

function renderPage(entry: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/jobs/new" element={<JobNew />} />
          <Route path="/board" element={<div>看板页</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** base64url(UTF-8 JSON)，与扩展跳转入口编码互逆 */
function encodePrefill(result: CrawlResult): string {
  const bytes = new TextEncoder().encode(JSON.stringify(result));
  let bin = '';
  bytes.forEach((b) => { bin += String.fromCharCode(b); });
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

const okResult: CrawlResult = {
  status: 'ok',
  fields: {
    company: '蚂蚁集团', title: '前端开发工程师', jd_url: 'https://www.zhipin.com/job_detail/1',
    // 后端契约：channel 回填 source 枚举（技设 §3.3），前端负责映射到渠道词表
    location: '杭州', channel: 'boss', deadline: '2026-09-01T15:59:59Z',
    description: '负责核心业务前端开发与稳定性建设。',
    requirements: { salary: '25k-40k·14薪', degree: '本科', tags: ['React', 'TypeScript'] },
    confidence: 'high',
  },
  missing_fields: [], confidence: 'high', error_code: null, error_message: null,
  content_truncated: false, tokens_used: 860, request_id: 'ui-test-1',
};

const partialResult: CrawlResult = {
  ...okResult,
  status: 'partial',
  fields: { ...okResult.fields, company: null, title: null, confidence: 'low' },
  missing_fields: ['company', 'title'],
  confidence: 'low',
};

beforeEach(() => {
  h.state.crawlResult = null;
  h.state.crawlError = null;
  h.state.createResult = null;
  h.state.calls = { crawl: [], create: [], update: [] };
});

describe('JobNew 入口与解码（PROX-19）', () => {
  it('decodePrefill 与扩展编码互逆（含中文）', () => {
    expect(decodePrefill(encodePrefill(okResult))).toEqual(okResult);
  });

  it('guessSource：zhipin → boss，nowcoder → nowcoder，其余 → unknown', () => {
    expect(guessSource('https://www.zhipin.com/job_detail/1')).toBe('boss');
    expect(guessSource('https://www.nowcoder.com/jobs/1')).toBe('nowcoder');
    expect(guessSource('https://careers.tencent.com/1')).toBe('unknown');
  });

  it('?prefill= 入口：解码后直接进预览，全部字段可编辑（AC-9）', async () => {
    renderPage(`/jobs/new?prefill=${encodePrefill(okResult)}`);
    expect(await screen.findByLabelText('公司')).toHaveValue('蚂蚁集团');
    expect(screen.getByLabelText('岗位名称')).toHaveValue('前端开发工程师');
    expect(screen.getByLabelText('JD 链接')).toHaveValue('https://www.zhipin.com/job_detail/1');
    expect(screen.getByLabelText('工作地点')).toHaveValue('杭州');
    expect(screen.getByLabelText('岗位描述')).toHaveValue('负责核心业务前端开发与稳定性建设。');
    expect(screen.getByLabelText('薪资')).toHaveValue('25k-40k·14薪');
    expect(screen.getByLabelText('技能标签')).toHaveValue('React，TypeScript');
    // 后端 channel=source 枚举（'boss'）→ 表单渠道词表（'BOSS直聘'）
    expect(screen.getByLabelText('来源渠道')).toHaveValue('BOSS直聘');
    expect(screen.getByText('置信度：高')).toBeInTheDocument();
    // prefill 链路不再重复调用 /jobs/crawl
    expect(h.state.calls.crawl.length).toBe(0);
  });

  it('?url= 入口：自动调用 crawlJob（按 URL 猜测 source），解析后进入预览（AC-1）', async () => {
    h.state.crawlResult = okResult;
    renderPage(`/jobs/new?url=${encodeURIComponent('https://www.zhipin.com/job_detail/1')}`);
    expect(await screen.findByLabelText('公司')).toHaveValue('蚂蚁集团');
    expect(h.state.calls.crawl.length).toBe(1);
    expect(h.state.calls.crawl[0].url).toBe('https://www.zhipin.com/job_detail/1');
    expect(h.state.calls.crawl[0].source).toBe('boss');
    expect(h.state.calls.crawl[0].request_id).toMatch(/^ui-/);
  });

  it('StrictMode 下 ?url= 入口只触发一次 crawl（effect 双跑防御）', async () => {
    h.state.crawlResult = okResult;
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <StrictMode>
        <QueryClientProvider client={qc}>
          <MemoryRouter initialEntries={[`/jobs/new?url=${encodeURIComponent('https://www.zhipin.com/job_detail/1')}`]}>
            <Routes>
              <Route path="/jobs/new" element={<JobNew />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </StrictMode>,
    );
    expect(await screen.findByLabelText('公司')).toHaveValue('蚂蚁集团');
    expect(h.state.calls.crawl.length).toBe(1);
  });
});

describe('JobNew 必填校验与缺失高亮（AC-6）', () => {
  it('partial 结果 company/title 缺失 → 保存置灰 + 提示补全 + missing 字段高亮', async () => {
    renderPage(`/jobs/new?prefill=${encodePrefill(partialResult)}`);
    const saveBtn = await screen.findByRole('button', { name: '保存岗位' });
    expect(saveBtn).toBeDisabled();
    expect(screen.getByText(/公司与岗位名称为必填/)).toBeInTheDocument();
    expect(screen.getByText(/以下字段未能自动解析/)).toBeInTheDocument();
    expect(screen.getByText(/公司、岗位名称/)).toBeInTheDocument();

    // 补全后解锁
    const user = userEvent.setup();
    await user.type(screen.getByLabelText('公司'), '蚂蚁集团');
    await user.type(screen.getByLabelText('岗位名称'), '前端开发工程师');
    expect(saveBtn).toBeEnabled();
  });
});

describe('JobNew 失败态（AC-3/AC-4）', () => {
  it('unsupported_site → 提示 + 手动录入入口（预填链接，confidence=manual）', async () => {
    h.state.crawlResult = {
      status: 'unsupported_site', fields: null, missing_fields: ['company', 'title'],
      confidence: null, error_code: null, error_message: null,
      content_truncated: false, tokens_used: null, request_id: 'ui-test-2',
    };
    const user = userEvent.setup();
    renderPage(`/jobs/new?url=${encodeURIComponent('https://example.com/job/1')}`);
    expect(await screen.findByText(/暂不支持该站点/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '重试解析' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '手动录入' }));
    expect(screen.getByLabelText('JD 链接')).toHaveValue('https://example.com/job/1');
    expect(screen.getByLabelText('解析置信度')).toHaveValue('manual');
  });

  it('fetch_failed → 重试与手动录入双入口；重试再次调用 crawlJob', async () => {
    h.state.crawlResult = {
      status: 'fetch_failed', fields: null, missing_fields: [],
      confidence: null, error_code: null, error_message: '目标页面返回 403',
      content_truncated: false, tokens_used: null, request_id: 'ui-test-3',
    };
    const user = userEvent.setup();
    renderPage(`/jobs/new?url=${encodeURIComponent('https://www.nowcoder.com/jobs/1')}`);
    expect(await screen.findByText('目标页面返回 403')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '重试解析' }));
    await waitFor(() => expect(h.state.calls.crawl.length).toBe(2));
  });

  it('HTTP 429 → 频率超限提示，可重试（AC-11 用户侧）', async () => {
    const { ApiError } = await import('../api/client');
    h.state.crawlError = new ApiError(429, 'RATE_LIMITED', '抓取频率超限（10 次/分钟），请稍后重试');
    renderPage(`/jobs/new?url=${encodeURIComponent('https://www.zhipin.com/job_detail/1')}`);
    expect(await screen.findByText(/抓取频率超限/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重试解析' })).toBeInTheDocument();
  });
});

describe('JobNew 保存与重复三选（AC-2/AC-5）', () => {
  it('保存成功：createJob 透传 crawl_request_id，跳转看板', async () => {
    h.state.createResult = { kind: 'created', job: { id: 'job-new-1', company: '蚂蚁集团', title: '前端开发工程师', created_at: '2026-08-27T00:00:00Z' } };
    const user = userEvent.setup();
    renderPage(`/jobs/new?prefill=${encodePrefill(okResult)}`);
    await user.click(await screen.findByRole('button', { name: '保存岗位' }));
    await waitFor(() => expect(h.state.calls.create.length).toBe(1));
    const body = h.state.calls.create[0] as Record<string, unknown>;
    expect(body.company).toBe('蚂蚁集团');
    expect(body.channel).toBe('BOSS直聘'); // source 枚举已映射到渠道词表，避免落库 'boss'
    expect(body.crawl_request_id).toBe('ui-test-1');
    expect(body.requirements).toEqual({ salary: '25k-40k·14薪', degree: '本科', tags: ['React', 'TypeScript'] });
    expect(await screen.findByText('看板页')).toBeInTheDocument();
  });

  it('命中 duplicate_of → 三选弹窗；选「更新已有岗位」走 PATCH 且透传 crawl_request_id（AC-2）', async () => {
    h.state.createResult = {
      kind: 'duplicate', duplicateOf: 'job-9',
      job: { id: 'job-9', company: '蚂蚁集团', title: '前端开发工程师', created_at: '2026-08-20T00:00:00Z' },
    };
    const user = userEvent.setup();
    renderPage(`/jobs/new?prefill=${encodePrefill(okResult)}`);
    await user.click(await screen.findByRole('button', { name: '保存岗位' }));
    // 三选弹窗
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/系统已存在/)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: '更新已有岗位' })).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: '修改后新建' })).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: '取消' })).toBeInTheDocument();

    await user.click(within(dialog).getByRole('button', { name: '更新已有岗位' }));
    await waitFor(() => expect(h.state.calls.update.length).toBe(1));
    expect(h.state.calls.update[0].id).toBe('job-9');
    expect(h.state.calls.update[0].body.crawl_request_id).toBe('ui-test-1');
    expect(await screen.findByText('看板页')).toBeInTheDocument();
  });

  it('命中 duplicate_of → 选「修改后新建」回到编辑并提示改名后保存', async () => {
    h.state.createResult = {
      kind: 'duplicate', duplicateOf: 'job-9',
      job: { id: 'job-9', company: '蚂蚁集团', title: '前端开发工程师', created_at: '2026-08-20T00:00:00Z' },
    };
    const user = userEvent.setup();
    renderPage(`/jobs/new?prefill=${encodePrefill(okResult)}`);
    await user.click(await screen.findByRole('button', { name: '保存岗位' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: '修改后新建' }));
    expect(await screen.findByText(/修改公司或岗位名称后再次点击/)).toBeInTheDocument();
    // 表单仍可编辑，未发起更新
    expect(screen.getByLabelText('公司')).toHaveValue('蚂蚁集团');
    expect(h.state.calls.update.length).toBe(0);
  });
});
