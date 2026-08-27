# PROX-19 S1a 技术设计 — 网页岗位自动抓取 v1.0

> 阶段：S1a 技术设计（G1 判门）。
> 基线：PRD v1.2（Issue PROX-19 附件）、OP-8 技术设计 v1.0、仓库当前 `main`（commit `5fae7fe` 之后）。
> 范围：覆盖「网页 JD → 岗位看板」完整实现方案，包括模型选型、数据模型、解析服务拆分、30s 幂等缓存、受影响文件清单与实现步骤。
> 读者：@BackendDev @FrontendDev @Tester；判门：G1（Leader + Reviewer 业务评审）。

## 修订记录

| 版本 | 日期 | 作者 | 变更说明 |
|---|---|---|---|
| v1.0 | 2026-08-27 | Architect-小李 | S1a 初版；真实落盘到 `docs/design/PROX-19-s1a-tech-design-v1.0.md` |

## 1. 当前架构与改动总览

### 1.1 as-is

```text
浏览器 (React SPA @ localhost:5173)
  │ 同一源（生产）或 Vite proxy（开发）
  ▼
FastAPI @ http://localhost:8741/api/v1
  │
  ├─ UI session 鉴权：HttpOnly Cookie ah_session
  ├─ Agent Bearer 鉴权：Authorization: Bearer ah_live_<random>
  ├─ /jobs CRUD（company/title/jd_url/location/channel/deadline）
  ├─ /settings/llm（AppSetting key='llm'）
  └─ 无 CORS 配置（生产同源，开发走 proxy）
```

### 1.2 建议改动总览

- 后端新增 `POST /api/v1/jobs/crawl`「解析预览」端点，**不持久化岗位**。
- 后端新增解析服务模块，按站点拆分「结构化 DOM 路径」与「LLM 兜底路径」。
- 后端新增 `crawl_attempt` 表记录每次抓取；扩展 `job` 表存储 `description`、`requirements`、`confidence`。
- 后端新增 30s `request_id` 幂等缓存、单用户 10/min 频率限制、CORS 配置。
- 前端新增 `/jobs/new` 页面与预览抽屉，支持从 `?prefill=` 进入预览。
- 新增 `apps/extension/` 浏览器扩展（MV3），直接调用 `/jobs/crawl`。

## 2. LLM 模型选型与配置位置

### 2.1 选型

| 决策点 | 结论 | 说明 |
|---|---|---|
| 默认模型 | `gpt-4o-mini` | OpenAI 低成本模型，满足 PRD §13.3 / BR-32「默认低成本模型」要求 |
| 用户可配置 | 是 | 复用现有 `AppSetting key='llm'`（`apps/server/app/services/llm_client.py`） |
| 调用方式 | OpenAI 兼容接口 | 通过 `app.services.llm_client.load_config` 读取 provider/base_url/model/api_key |
| 输出格式 | JSON Schema / `response_format={"type": "json_object"}` | 与简历解析一致，强制结构化输出 |
| 超时 | 15s（LLM 调用）+ 抓取/截断时间 ≈ 30s 总超时 | 与现有 `LLMConfig.timeout_seconds` 一致 |

### 2.2 配置读取代码位置

```python
# apps/server/app/services/crawl_llm.py
from app.services.llm_client import load_config, LLMError

def parse_with_llm(text: str, session) -> dict:
    config = load_config(session)
    if config is None:
        raise LLMError("LLM 未配置")
    # 复用 call_llm 或按 JD 字段构造新 prompt
    ...
```

- `load_config` 已存在，无需新建配置表或读取逻辑。
- 若用户未配置 LLM，`source=official` 路径返回 `status=parse_failed` + `error_code=LLM_NOT_CONFIGURED`。

## 3. 数据模型

### 3.1 已有 `job` 表扩展

在 `packages/domain/autohunt_domain/models.py` 的 `Job` 表中新增三列：

| 字段 | 类型 | 说明 |
|---|---|---|
| `description` | `str \| None` | 岗位描述（JD 原文/摘要）；BR-12 要求替换时全量替换 |
| `requirements` | `JSON` | 学历、经验、薪资、标签等扩展字段；SQLModel 中用 `Field(sa_column=Column(JSON))` |
| `confidence` | `str \| None` | 解析置信度：`high` / `medium` / `low` / `manual` |

现有 `company/title/jd_url/location/channel/deadline/created_at` 保持不变，`company+title` 索引继续供去重使用。

### 3.2 新增 `crawl_attempt` 表

```python
# packages/domain/autohunt_domain/models.py
class CrawlAttempt(SQLModel, table=True):
    __tablename__ = "crawl_attempt"

    seq: int | None = Field(default=None, primary_key=True)
    id: str = Field(default_factory=new_id, unique=True, index=True)
    job_id: str | None = Field(default=None, foreign_key="job.id", index=True)
    url: str = Field(index=True)
    source: str  # boss/nowcoder/liepin/shixiseng/official/unknown
    request_id: str | None = Field(default=None, index=True)
    caller: str  # ui / agent
    status: str  # ok/partial/unsupported_site/fetch_failed/parse_failed/timeout
    strategy: str  # structured / llm / fallback / none
    fields_snapshot: dict | None = Field(default=None, sa_column=Column(JSON))
    missing_fields: list = Field(default_factory=list, sa_column=Column(JSON))
    error_code: str | None = None
    error_message: str | None = None
    content_truncated: bool = False
    tokens_used: int | None = None
    duration_ms: int | None = None
    created_at: datetime = Field(default_factory=utcnow)
```

**索引设计：**

- `url`：按 URL 查询历史抓取记录（FR-23 审计）。
- `request_id`：幂等去重与问题排查。
- `job_id`：关联已保存的岗位，支持更新日志。
- `created_at`：KPI-1/KPI-5 统计时间窗口。

**与 `job` 表关系：**

- `crawl_attempt.job_id` 为可空外键。
- 首次保存时写入新 `job.id`；更新已有岗位时写入原 `job.id`；未保存时保持 `None`。
- 不破坏 `job` 表现有去重逻辑（BR-1/BR-3）。

### 3.3 `CrawlResult.fields` 与 `JobCreate` / 数据库表的字段映射

PRD §12 / OP-8 §4 建议 `CrawlResult.fields: JobCreate`。本设计保留该映射，并向下补全新增字段：

| CrawlResult.fields | 类型 | 落库位置 | 说明 |
|---|---|---|---|
| `company` | str | `job.company` | 必填 |
| `title` | str | `job.title` | 必填 |
| `jd_url` | str | `job.jd_url` | 必填 |
| `location` | str \| None | `job.location` | |
| `channel` | str \| None | `job.channel` | 回填 `source` 枚举值 |
| `deadline` | RFC3339 \| None | `job.deadline` | 日期-only 输入归一化为当天 23:59:59 UTC |
| `description` | str \| None | `job.description` | 新增字段 |
| `requirements` | dict \| None | `job.requirements`（JSON） | 新增字段；含 degree/experience/salary/tags |
| `confidence` | str \| None | `job.confidence` | 新增字段；取 `fields` 中最低置信度或 `manual` |

API 契约层面，`CrawlResult.fields` 仍复用现有 `JobCreate` 并扩展两个新增字段。新增 schema 定义：

```python
# apps/server/app/schemas.py
class CrawlResultFields(JobCreate):
    description: str | None = None
    requirements: dict[str, Any] | None = None
    confidence: str | None = None
```

这样既保留 OP-8 技设 §4 的 `fields: JobCreate` 映射，又明确新增字段如何进入数据库。

## 4. 解析服务模块拆分与调用关系

### 4.1 模块职责

| 文件 | 职责 | 调用方 |
|---|---|---|
| `apps/server/app/services/crawl.py` | 编排入口：校验、幂等、限流、选路径、落 `crawl_attempt`、构造 `CrawlResult` | `app/api/jobs.py` |
| `apps/server/app/services/crawl_fetcher.py` | HTTP 拉取目标页可见文本；处理超时/403/反爬 | `crawl_parser` / `crawl_llm` |
| `apps/server/app/services/crawl_parser.py` | 结构化解析：BOSS/牛客/猎聘/实习僧站点适配器 | `crawl.py` |
| `apps/server/app/services/crawl_llm.py` | LLM 兜底：构造 prompt、调用 `llm_client`、校验输出 | `crawl.py` |
| `apps/server/app/services/crawl_cache.py` | 30s `request_id` 幂等缓存（内存 + TTL） | `crawl.py` |
| `apps/server/app/services/crawl_rate_limit.py` | 单用户 10 req/min 滑动窗口限流 | `crawl.py` |

### 4.2 调用时序

```text
POST /jobs/crawl
    │
    ▼
[auth middleware] caller ∈ {ui, agent}
    │
    ▼
jobs.crawl_job(req)
    │
    ├── 1. 校验 url / source / request_id
    │
    ├── 2. rate_limit.check(caller_id) → 429 RATE_LIMITED
    │
    ├── 3. cache.get(request_id) → 命中直接返回缓存结果
    │
    ├── 4. 创建 crawl_attempt 初始记录
    │
    ├── 5. 选择策略：
    │      source ∈ {boss, nowcoder, liepin, shixiseng} → structured
    │      source = official / unknown → llm
    │
    ├── 6a. structured: parser.parse(url, extracted)
    │       若 extracted 已带字段 → 校验归一化
    │       否则 fetcher 拉取页面 → 按站点 DOM 规则抽取
    │
    ├── 6b. llm: fetcher 拉取可见文本 → 截断到 8000 tokens
    │       → crawl_llm.parse(text) → JSON 校验
    │
    ├── 7. 归一化字段，计算 missing_fields / confidence
    │
    ├── 8. 更新 crawl_attempt 结果记录
    │
    ├── 9. 写入 cache(request_id, result, ttl=30s)
    │
    └── 10. 返回 CrawlResult
```

### 4.3 策略实现细节

**结构化路径（`source=boss/nowcoder/liepin/shixiseng`）：**

- 扩展已传 `extracted` 时，后端只校验字段完整性与格式（如 `deadline` 转 RFC3339），不再拉取页面。
- 扩展未传 `extracted` 时（如岗位看板粘贴链路），`crawl_fetcher` 拉取目标页 HTML，`crawl_parser` 按站点规则抽取。
- 站点规则以函数表注册，便于版本化与增量新增：

```python
# apps/server/app/services/crawl_parser.py
PARSERS = {
    "boss": _parse_boss,
    "nowcoder": _parse_nowcoder,
    "liepin": _parse_liepin,
    "shixiseng": _parse_shixiseng,
}
```

**LLM 兜底路径（`source=official`）：**

- 扩展最小化回传 `title + content`。
- `crawl_fetcher` 仅作为可选补充；BR-21 要求遇到 403/验证码立即失败，不绕过反爬。
- `crawl_llm` 构造 prompt，要求返回 §10.1 字段字典，缺失字段为 `null`。
- token 估算按字符数近似（中文 1 字 ≈ 1 token，英文 4 字符 ≈ 1 token），超过 8000 截断并标记 `content_truncated=True`。

## 5. 30s 幂等缓存实现方案

### 5.1 实现位置

`apps/server/app/services/crawl_cache.py`

### 5.2 方案

单用户本地工具，采用**进程内内存缓存 + TTL**，足够覆盖 PRD FR-4 / BR-4「30 秒内同一 `request_id` 返回同一结果」。

```python
# apps/server/app/services/crawl_cache.py
from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class _Entry:
    result: dict
    expires_at: float


class CrawlCache:
    def __init__(self, ttl_seconds: float = 30.0):
        self._ttl = ttl_seconds
        self._store: dict[str, _Entry] = {}
        self._lock = Lock()

    def get(self, key: str) -> dict | None:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if now > entry.expires_at:
                self._store.pop(key, None)
                return None
            return entry.result

    def set(self, key: str, result: dict) -> None:
        now = time.monotonic()
        with self._lock:
            self._store[key] = _Entry(result=result, expires_at=now + self._ttl)
            self._evict_expired(now)

    def _evict_expired(self, now: float) -> None:
        expired = [k for k, e in self._store.items() if now > e.expires_at]
        for k in expired:
            self._store.pop(k, None)


crawl_cache = CrawlCache(ttl_seconds=30.0)
```

### 5.3 缓存键

```python
key = f"{caller}:{request_id}"
```

- `caller` 来自鉴权中间件（`ui` / `agent`），防止不同调用者互相命中。
- `request_id` 由调用方生成；UI 侧可用 `ui-<uuid>`，扩展用 `ext-<uuid>`。

### 5.4 与数据库去重的区别

- 缓存：30s 内同一 `request_id` 不重复解析，**不持久化**结果。
- 去重：保存时按 `company+title` 匹配已有岗位，由 `POST /jobs` 处理。

## 6. 频率限制实现方案

### 6.1 实现位置

`apps/server/app/services/crawl_rate_limit.py`

### 6.2 方案

同样采用进程内内存滑动窗口，单用户场景足够。

```python
class CrawlRateLimiter:
    def __init__(self, max_requests: int = 10, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: dict[str, list[float]] = {}
        self._lock = Lock()

    def check(self, caller_id: str) -> bool:
        now = time.monotonic()
        with self._lock:
            timestamps = self._buckets.get(caller_id, [])
            # 清理过期
            timestamps = [t for t in timestamps if now - t <= self.window]
            if len(timestamps) >= self.max_requests:
                self._buckets[caller_id] = timestamps
                return False
            timestamps.append(now)
            self._buckets[caller_id] = timestamps
            return True
```

- `caller_id` 取 `caller`（`ui` / `agent`）。单用户产品无需细分到用户 ID。
- 超限时 `jobs.crawl_job` 返回 429，错误码新增 `RATE_LIMITED`。

## 7. API 契约与受影响文件清单

### 7.1 新增/修改端点

| 端点 | 文件 | 变更 | 鉴权 |
|---|---|---|---|
| `POST /api/v1/jobs/crawl` | `apps/server/app/api/jobs.py` | 新增 | `ANY_CALLER`（ui / agent） |
| CORS 中间件 | `apps/server/app/main.py` | 新增 | 全局 |
| `cors_origins` 配置 | `apps/server/app/config.py` | 新增 | 全局 |

### 7.2 Schema 变更

`apps/server/app/schemas.py` 新增：

- `CrawlSource(str, Enum)`
- `CrawlStatus(str, Enum)`
- `CrawlErrorCode(str, Enum)`：新增 `RATE_LIMITED` / `LLM_NOT_CONFIGURED` / `COST_LIMIT_EXCEEDED`
- `CrawlExtracted(BaseModel)`
- `CrawlRequest(BaseModel)`
- `CrawlFieldConfidence(str, Enum)`
- `CrawlResultFields(JobCreate)`：含 `description` / `requirements` / `confidence`
- `CrawlResult(BaseModel)`

### 7.3 服务层新增文件

- `apps/server/app/services/crawl.py`：编排器
- `apps/server/app/services/crawl_fetcher.py`：页面拉取
- `apps/server/app/services/crawl_parser.py`：站点规则解析
- `apps/server/app/services/crawl_llm.py`：LLM 兜底
- `apps/server/app/services/crawl_cache.py`：30s 幂等缓存
- `apps/server/app/services/crawl_rate_limit.py`：频率限制

### 7.4 数据模型变更

- `packages/domain/autohunt_domain/models.py`：
  - `Job` 表新增 `description`、`requirements`、`confidence`
  - 新增 `CrawlAttempt` 表
- 新增 Alembic 迁移脚本（如项目已启用 Alembic）；否则首次启动由 SQLModel `create_all` 自动建表。

### 7.5 前端变更

- `apps/web/src/App.tsx`：新增 `<Route path="jobs/new" element={<JobNew />} />`
- `apps/web/src/pages/JobNew.tsx`：新增页面，解析 `?prefill=` / `?url=`，展示预览抽屉。
- `apps/web/src/api/types.ts`：新增 `CrawlRequest` / `CrawlResult` / `CrawlStatus` 类型。
- `apps/web/src/api/client.ts`：新增 `crawlJob(body: CrawlRequest): Promise<CrawlResult>`。
- `apps/web/src/pages/Board.tsx`：「录入岗位」按钮增加「粘贴链接抓取」入口，或复用 `JobNew` 弹窗。

### 7.6 浏览器扩展新增目录

- `apps/extension/manifest.json`（MV3）
- `apps/extension/content.js`
- `apps/extension/background.js`
- `apps/extension/options.html`
- `apps/extension/options.js`

## 8. 实现步骤（按范围派发）

### 8.1 BackendDev

1. **配置与中间件**
   - `app/config.py`：读取 `AUTOHUNT_CORS_ORIGINS`（逗号分隔，空则 `["*"]`）。
   - `app/main.py`：挂载 `CORSMiddleware`，默认 `allow_origins=["*"]`、`allow_credentials=False`、`allow_headers=["Authorization", "Content-Type", "X-Request-Id"]`。
2. **数据模型**
   - `packages/domain/autohunt_domain/models.py`：扩展 `Job` 表，新增 `CrawlAttempt` 表。
   - 生成/更新迁移脚本。
3. **Schema**
   - `app/schemas.py`：新增 Crawl 相关模型。
4. **服务实现**
   - 实现 `crawl_cache.py`、`crawl_rate_limit.py`。
   - 实现 `crawl_fetcher.py`（超时、UA、403 处理）。
   - 实现 `crawl_parser.py`（至少 BOSS、牛客两个 P0 站点规则）。
   - 实现 `crawl_llm.py`（prompt、JSON 校验、token 截断）。
   - 实现 `crawl.py` 编排器，含 `crawl_job(url, source, request_id, extracted, caller)`。
5. **API 端点**
   - `app/api/jobs.py`：新增 `POST /jobs/crawl`，调用 `crawl.crawl_job`。
   - `app/schemas.py` 错误码：新增 `RATE_LIMITED`。
6. **契约冻结**
   - 运行 `python scripts/export_openapi.py`，将 `/jobs/crawl` 写入 `docs/design/api-openapi.json`，零 diff 后提交。

### 8.2 FrontendDev（Web 侧）

1. 新增 `apps/web/src/pages/JobNew.tsx`：
   - 解析 `?prefill=<base64url>` 进入预览抽屉；
   - 解析 `?url=<encoded>` 进入手动录入并预填链接；
   - 展示 `fields` / `missing_fields` / `confidence`；
   - 必填项（company/title）缺失时保存按钮置灰；
   - 保存调用 `httpApi.createJob`；命中重复展示更新/新建/取消。
2. `App.tsx` 增加 `/jobs/new` 路由。
3. `api/types.ts` 与 `api/client.ts` 增加 `crawlJob`。
4. `Board.tsx` 调整「录入岗位」入口：点击后弹出/跳转到 `JobNew`（保留原手动录入能力）。

### 8.3 FrontendDev（扩展侧）

1. 新建 `apps/extension/`：
   - `manifest.json`：权限 `activeTab`、`storage`；`host_permissions: ["http://localhost:8741/*"]`。
   - `content.js`：点击扩展图标后读取 `location.href`，知名站点按 DOM 预提取字段。
   - `background.js`：从 `chrome.storage.local` 读取 key，调用 `POST /jobs/crawl`。
   - `options.html/options.js`：粘贴 API key，保存到 storage，提供 `/settings/keys` 链接。
2. 成功后打开 `http://localhost:5173/#/jobs/new?prefill=<base64url(CrawlResult)>`；失败按 PRD §14 文案提示。

### 8.4 Tester

- 覆盖 AC-1 ~ AC-12 的功能用例（详见 §10）。

## 9. 验证方式

| AC | 验证手段 |
|---|---|
| AC-1 | 岗位看板粘贴 BOSS/牛客链接 → 断言 30s 内返回 `status=ok` / `partial` → 预览抽屉可编辑 → 保存后 `job` 表新增记录 |
| AC-2 | 同一公司+岗位再次抓取 → `POST /jobs` 返回 200 + `duplicate_of` → 选择更新 → 原 `job.id` 不变、`location` 被覆盖、`crawl_attempt` 新增关联记录 |
| AC-3 | 粘贴不支持站点 → 断言 `status=unsupported_site` → Web UI 预填 URL |
| AC-4 | 模拟目标页 403 / 超时 → 断言 `status=fetch_failed` / `timeout` → 提供重试与手动录入入口 |
| AC-5 | 扩展返回结果后断言 `job` 表无新增记录，须经用户点击保存 |
| AC-6 | 构造 `company` 或 `title` 为空 → 保存按钮置灰、提示补全 |
| AC-7 | 连续 3 次同一 `request_id` 调用 → 仅产生一次 `crawl_attempt` 记录、返回同一结果 |
| AC-8 | 看板卡片断言展示公司/岗位/地点/截止/渠道/状态，空值展示默认文案 |
| AC-9 | 扩展在 BOSS/牛客页点击抓取 → 30s 内返回结果并打开 `/#/jobs/new?prefill=...` |
| AC-10 | 扩展不带 token / 错误 token → 后端返回 401 `UNAUTHORIZED` |
| AC-11 | 1 分钟内发起 11 次解析 → 第 11 次返回 429 `RATE_LIMITED` |
| AC-12 | LLM 路径输入构造 >8000 tokens → 返回 `status=partial/ok` 并标记 `content_truncated=True` |

**额外验收：**

- `scripts/export_openapi.py` 导出零 diff。
- 新增 `crawl_attempt` 表记录覆盖所有抓取状态。

## 10. 风险与边界

| 风险 | 说明 | 缓解 |
|---|---|---|
| RISK-1 站点 DOM 变化 | BOSS/牛客等站点结构变化导致规则失效 | 站点规则版本化；失败兜底人工录入；通过 `crawl_attempt` 监控各站点成功率 |
| RISK-2 反爬/403 | 目标站拦截后端抓取 | BR-21：不绕过反爬，`fetch_failed` 立即提示手动录入 |
| RISK-3 MV3 SW 被杀 | 30s 同步请求期间 service worker 被回收 | G0 先按同步实现；实测超时率/SW 被杀率偏高时升级到「返回 `task_id` + 扩展轮询」异步模式 |
| RISK-4 LLM 幻觉 | 官网 JD 解析字段错误 | 结构化输出 + 置信度标记 + 用户预览确认 |
| RISK-5 LLM 成本 | 高频官网解析超预算 | token 上限 8000 + 10/min 限流 + 默认 `gpt-4o-mini` |
| RISK-6 缓存进程内 | 重启后端后缓存丢失 | 30s 短缓存，丢失仅导致重复解析，不影响正确性 |
| RISK-7 跨浏览器扩展差异 | Chrome/Edge/Firefox API 差异 | G0 优先 Chrome/Edge MV3 |
| RISK-8 字段映射口径 | `requirements` JSON 结构需前后端一致 | schema 统一定义；落库前校验 |

## 11. 结论

本设计明确：

- LLM 默认模型 `gpt-4o-mini`，复用现有 `AppSetting key='llm'` 配置。
- `job` 表扩展 `description` / `requirements` / `confidence`；新增 `crawl_attempt` 表记录抓取日志。
- `CrawlResult.fields` 复用 `JobCreate` 并扩展新增字段，映射到数据库表。
- 解析服务拆分为 `crawl.py` 编排器 + `crawl_fetcher/parser/llm/cache/rate_limit` 五个子模块。
- 30s 幂等缓存采用进程内内存 + TTL，键为 `{caller}:{request_id}`。
- 受影响文件与实现步骤已按 BackendDev / FrontendDev（Web/扩展）/ Tester 拆分。

G1 判门通过后，BackendDev 可先行实现 API 契约与数据模型；FrontendDev Web 侧与扩展侧可并行开发。
