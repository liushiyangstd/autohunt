# PROX-19 S1a 技术设计 — 网页岗位自动抓取 v1.0

> 阶段：S1a 技术设计（G1 设计门禁事实来源）。
> 基线：PRD v1.2（Issue PROX-19 附件）、OP-8/OP-9 关闭结论、仓库当前 `main`。
> 范围：覆盖「网页 JD → 岗位看板」最小可用链路的技术设计，包括通信协议、数据模型、API 契约、解析服务、扩展与 Web 实现方案。

## 修订记录

| 版本 | 日期 | 作者 | 变更说明 |
|---|---|---|---|
| v1.0 | 2026-08-27 | Architect-小李 / Leader-王天琦 | 基于 PRD v1.2 与 OP-8/OP-9 结论输出完整 S1a 技术设计 |

## 1. 背景与目标

PRD v1.2 确定 G0 主入口为**浏览器扩展**，岗位看板粘贴链接作为 fallback。本设计明确：
- 扩展与本地后端的通信协议（已关闭 OP-8）
- LLM 解析成本阈值与模型选型（已关闭 OP-9）
- 新增 `/jobs/crawl` 端点的完整实现方案
- `Job` 表扩展与新增 `crawl_attempt` 表的数据模型
- 扩展侧与 Web 侧的最小实现路径

## 2. 当前架构（as-is）

```text
浏览器 (React SPA)
  │ 同一源（生产）或 Vite proxy（开发）
  ▼
FastAPI @ http://localhost:8741/api/v1
  │
  ├─ UI session 鉴权：HttpOnly Cookie `ah_session`（仅浏览器 SPA 使用）
  ├─ Agent Bearer 鉴权：`Authorization: Bearer ah_live_<random>`（外部 Agent CLI / 扩展使用）
  └─ 目前无 CORS 配置（生产同源，开发走 proxy）
```

- 后端已具备双鉴权中间件（`app/auth.py`），`caller ∈ {ui, agent}`。
- API key 管理端点（`/keys`）已存在，仅 UI session 可创建/吊销。
- 岗位相关端点（`/jobs`）已存在，仅覆盖持久化 CRUD，无「解析预览」语义。
- LLM 客户端（`app/services/llm_client.py`）已存在，用于简历解析，可复用配置读取与调用逻辑。

## 3. 通信协议（OP-8 结论）

### 3.1 协议选择

- **HTTP REST `POST /api/v1/jobs/crawl`**，不走 WebSocket。
- 请求/响应模型与现有 API 一致；30s 超时直接用 HTTP timeout。

### 3.2 认证方式

- 复用现有 **Agent Bearer API Key**。
- 用户在 Web UI `/settings/keys` 生成 key，粘贴到扩展 options 页。
- 扩展每次调用携带 `Authorization: Bearer ah_live_<random>`。
- 后端按 `ApiKey` 表校验 SHA-256 哈希，更新 `last_used_at`，吊销即时生效。

### 3.3 CORS 策略

- 默认 `allow_origins=["*"]`，`allow_credentials=False`，`allow_methods=["*"]`，`allow_headers=["Authorization", "Content-Type", "X-Request-Id"]`。
- 安全边界交给 Bearer token；无 token 请求一律 401。
- 可选严格模式：通过环境变量 `AUTOHUNT_CORS_ORIGINS` 配置逗号分隔的允许源。

## 4. 数据模型

### 4.1 `job` 表扩展

位置：`packages/domain/autohunt_domain/models.py`

新增字段：
- `description: str | None`：岗位描述（JD 原文/摘要）
- `requirements: dict`：JSON 存储学历、经验、薪资、标签等扩展字段
- `confidence: str | None`：解析置信度，`high/medium/low/manual`

### 4.2 新增 `crawl_attempt` 表

位置：`packages/domain/autohunt_domain/models.py`

字段：
- `seq`: int，自增主键
- `id`: str，uuid4，唯一索引
- `request_id`: str，幂等键，索引
- `source_url`: str，原始 JD 链接
- `caller`: str，`ui` / `agent`
- `status`: str，`ok/partial/unsupported_site/fetch_failed/parse_failed/timeout`
- `strategy_version`: str，解析策略版本
- `failure_reason`: str | None，失败原因分类
- `content_truncated`: bool，是否触发 token 截断
- `created_at`: datetime

用途：满足 FR-23 审计需求与 KPI-1/KPI-5 统计。

## 5. API 契约

### 5.1 新增端点

`POST /api/v1/jobs/crawl`

- 鉴权：`any_caller`（UI session 或 Agent Bearer）
- 语义：仅做「解析预览」，不持久化岗位
- 幂等：`request_id` 30s 内重复请求返回同一结果
- 超时：30s 未返回则 `status=timeout`

### 5.2 请求体 `CrawlRequest`

位置：`apps/server/app/schemas.py`

```python
class CrawlSource(str, Enum):
    boss = "boss"
    nowcoder = "nowcoder"
    liepin = "liepin"
    shixiseng = "shixiseng"
    official = "official"

class CrawlStatus(str, Enum):
    ok = "ok"
    partial = "partial"
    unsupported_site = "unsupported_site"
    fetch_failed = "fetch_failed"
    parse_failed = "parse_failed"
    timeout = "timeout"

class CrawlFieldConfidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"

class CrawlExtracted(BaseModel):
    company: str | None = None
    title: str | None = None
    location: str | None = None
    description: str | None = None
    deadline: str | None = None
    salary: str | None = None
    degree: str | None = None
    experience: str | None = None
    tags: list[str] = []

class CrawlRequest(BaseModel):
    url: HttpUrl
    source: CrawlSource
    request_id: str
    extracted: CrawlExtracted | None = None
```

### 5.3 响应体 `CrawlResult`

```python
class CrawlResult(BaseModel):
    status: CrawlStatus
    url: str
    source: CrawlSource
    request_id: str
    fields: JobCreate
    missing_fields: list[str] = []
    confidence: dict[str, CrawlFieldConfidence] = {}
    content_truncated: bool = False
    error_code: str | None = None
    error_message: str | None = None
```

`status` 枚举与 PRD §12.2 一致。

### 5.4 错误响应

复用现有统一错误信封：
- 401 `UNAUTHORIZED`：无有效 Bearer token
- 403 `FORBIDDEN`：token 已吊销
- 422 `VALIDATION_ERROR`：URL 非法或字段格式错误
- 429 `RATE_LIMITED`：单用户解析频率超限

## 6. 解析服务设计

### 6.1 模块拆分

新增 `apps/server/app/services/crawl.py`，职责：
- 接收 `CrawlRequest`，路由到结构化路径或 LLM 兜底路径
- 维护 `request_id` 30s 内存缓存（`dict + TTL`，单用户场景足够）
- 调用 `fetch_page()` 拉取页面（`httpx`，5s connect timeout + 25s read timeout，总上限 30s）
- 对 `source=official` 调用 LLM 抽取
- 写入 `crawl_attempt` 日志
- 返回 `CrawlResult`

### 6.2 结构化路径

- 适用：`boss` / `nowcoder` / `liepin` / `shixiseng`
- 扩展已预提取字段时，后端做校验与归一化
- 扩展未预提取时，后端按 `source` 选择静态 HTML 抓取 + 站点规则解析
- 规则版本化，写入 `strategy_version`

### 6.3 LLM 兜底路径

- 适用：`official` 及所有未识别站点
- 后端拉取可见文本，去除导航/广告/页脚噪声
- token 估算 > 8000 时截断并标记 `content_truncated=True`
- 调用 LLM 抽取结构化字段（复用 `llm_client.load_config` 与配置）
- 默认模型 `gpt-4o-mini`（从 `AppSetting key='llm'` 读取，缺省值）

### 6.4 频率限制

- 单用户 10 次/分钟
- 实现位置：`apps/server/app/services/crawl.py` 或中间件
- 超限时返回 429 `RATE_LIMITED`

## 7. 后端实现清单

| 文件 | 变更 |
|---|---|
| `apps/server/app/main.py` | 挂载 `CORSMiddleware`；读取 `AUTOHUNT_CORS_ORIGINS` |
| `apps/server/app/config.py` | 新增 `cors_origins: list[str]` |
| `apps/server/app/schemas.py` | 新增 Crawl 相关 schema |
| `apps/server/app/api/jobs.py` | 新增 `POST /jobs/crawl` 路由 |
| `apps/server/app/services/crawl.py` | 新增解析服务 |
| `packages/domain/autohunt_domain/models.py` | 扩展 `Job` 表，新增 `CrawlAttempt` 表 |
| `scripts/export_openapi.py` | 导出后 `docs/design/api-openapi.json` 零 diff |

## 8. 扩展侧实现

### 8.1 目录结构

```
apps/extension/
├── manifest.json
├── content.js
├── background.js
├── options.html
├── options.js
└── icons/
```

### 8.2 权限

```json
{
  "permissions": ["activeTab", "storage"],
  "host_permissions": ["http://localhost:8741/*"]
}
```

### 8.3 调用流程

1. 用户点击扩展图标
2. `content.js` 读取 `location.href`，知名站点按 DOM 规则预提取
3. `background.js` 从 `chrome.storage.local` 读取 token
4. `POST http://localhost:8741/api/v1/jobs/crawl`
5. 成功后打开 `http://localhost:5173/#/jobs/new?prefill=<base64url(CrawlResult)>`
6. 失败时按 PRD §14 文案提示

## 9. Web 侧实现

### 9.1 新增路由

`App.tsx` 新增：
```tsx
<Route path="jobs/new" element={<JobNew />} />
```

### 9.2 `JobNew.tsx`

- 解析 `?prefill=` 或 `?url=` query 参数
- `prefill` 存在时 base64url 解码为 `CrawlResult`，打开预览抽屉
- `url` 存在时进入手动录入并预填 URL
- 预览抽屉复用粘贴链路组件
- 保存调用 `httpApi.createJob`

### 9.3 岗位看板入口调整

`Board.tsx`：
- 「+ 录入岗位」按钮保留现有手动弹窗
- 新增「粘贴 JD 链接」入口，调用 `POST /jobs/crawl` 后打开预览抽屉

## 10. 与验收标准对照（G1 验证）

| 验收标准 | 设计方案覆盖 | 验证方式 |
|---|---|---|
| AC-1 | 看板粘贴链路 + `/jobs/crawl` + 预览抽屉 | 端到端测试 |
| AC-2 | `POST /jobs` 命中重复返回 `duplicate_of` + 用户选择更新 | 单元测试 |
| AC-3 | `status=unsupported_site` → 手动录入预填 URL | 单元测试 |
| AC-4 | `status=fetch_failed/timeout` + 重试/手动录入入口 | 单元测试 |
| AC-5 | `/jobs/crawl` 不持久化，保存必须经 `POST /jobs` | 代码审查 |
| AC-6 | 预览抽屉保存按钮在 company/title 为空时置灰 | UI 测试 |
| AC-7 | `request_id` 30s 幂等缓存 | 单元测试 |
| AC-8 | 岗位卡片字段展示与 PRD §8.6 一致 | UI 测试 |
| AC-9 | 扩展直接调用 `/jobs/crawl` + `?prefill=` 打开预览 | 端到端测试 |
| AC-10 | 无有效 Bearer token → 后端 401 | 单元测试 |
| AC-11 | 单用户 10 次/分钟频率限制 → 第 11 次 429 | 单元测试 |
| AC-12 | token > 8000 截断并标记 `content_truncated` | 单元测试 |

## 11. 风险与边界

| 风险 | 说明 | 缓解 |
|---|---|---|
| MV3 SW 30s 存活 | `fetch` 期间 Chrome 保持 SW 存活，但接近 30s 有不确定性 | G0 先同步实现；实测异常则升级到异步轮询 |
| 站点 DOM 变化 | 结构化规则可能失效 | 监控 `crawl_attempt` 成功率；失败兜底 |
| LLM 幻觉 | 返回错误字段 | 结构化输出 + 置信度 + 用户预览确认 |
| LLM 成本 | 高频使用费用上升 | token 上限 + 频率限制 + 默认低成本模型 |
| CORS 安全 | `allow_origins=["*"]` 看似宽松 | 安全边界为 Bearer token；无 token 一律 401 |

## 12. 待确认项状态

全部 OP-1 ~ OP-9 已关闭，本设计直接基于 PRD v1.2 事实来源。

## 13. 结论

本 S1a 技术设计明确：
- HTTP REST + Agent Bearer API Key + 默认全源 CORS
- 新增 `POST /api/v1/jobs/crawl`，30s 同步，不持久化
- `Job` 表扩展 + 新增 `crawl_attempt` 表
- 双路径解析：结构化路径 + LLM 兜底
- 扩展/Web 最小实现路径

建议 G1 设计门禁通过后，派发 BackendDev 实现 API 契约与解析服务，Tester 同步准备功能用例。
