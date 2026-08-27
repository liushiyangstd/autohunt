# PROX-19 网页岗位自动抓取 — 接口测试用例集 v1.0（T1 / S3c）

> 阶段：T1 接口用例（G2 汇合门禁输入之一）。作者：@Tester-鲁智深。
> 事实来源：PRD v1.2（Issue PROX-19 附件 `PROX-19-web-jd-crawl-prd-v1.2.md`）+ S1a 技术设计（`docs/design/PROX-19-s1a-tech-design-v1.0.md`，main @ `d5337f8`）+ 冻结契约 `docs/design/api-openapi.json`（待 BackendDev 导出后回填具体 commit）。
> 范围：聚焦新增 `POST /api/v1/jobs/crawl` 及与抓取链路直接相关的 `POST /jobs` 去重/保存行为；其余既有端点回归引用 PROX-3 接口用例集。
> 交付形态：同功能用例，本环境未接入 XMind/Jira，按 `multica-artifact-test-sync` 产物内容规范以全量文字用例稿交付，后续接入平台时以本文为蓝本导入。

## 1. 通用约定与测试夹具

- Base URL：`http://localhost:{port}/api/v1`（默认 8741）。
- 鉴权夹具：
  - `UI` = HttpOnly Cookie session；
  - `AGENT` = `Authorization: Bearer ah_live_<random>`（经 `POST /keys` 签发）；
  - `AGENT-REVOKED` = 已吊销的 key；
  - `NONE` = 无凭证；
  - `BAD` = 伪造 key。
- 请求体基准（CrawlRequest）：
  ```json
  {
    "url": "https://www.zhipin.com/job_detail/xxxx.html",
    "source": "boss",
    "request_id": "ext-uuid-001",
    "extracted": {
      "company": "字节跳动",
      "title": "后端开发工程师",
      "location": "北京·海淀区",
      "description": "JD 原文...",
      "deadline": "2026-09-30",
      "salary": "20-40K·15薪",
      "degree": "本科及以上",
      "experience": "应届/1-3年",
      "tags": ["Java", "后端", "实习"]
    }
  }
  ```
- 公共断言：
  - 401/403/404/409/429 响应体为统一错误信封 `{"error":{"code","message"}}`；
  - 422 响应体为 FastAPI 校验错误 `{"detail":[...]}`（与既有端点保持一致）；
  - 时间字段一律 RFC3339；
  - `CrawlResult` 必须包含 `status`、`url`、`source`、`request_id`、`fields`、`missing_fields`、`confidence`。

## 2. AC → 接口用例追溯矩阵

| 验收标准 | 接口用例 |
|---|---|
| AC-1 看板粘贴解析并保存修改后值 | CRL-01/02/03、JOB-11/12 |
| AC-2 重复提示 + 更新覆盖 | JOB-11/12/14 |
| AC-3 不支持站点 → 手动录入 | CRL-05 |
| AC-4 超时 / 403 → 重试 + 手动录入 | CRL-06/07/08 |
| AC-5 不经确认不自动保存 | CRL-21 |
| AC-6 公司 / 岗位名为空保存置灰 | CRL-04、JOB-13 |
| AC-7 30 秒内同一链接幂等 | CRL-09/10 |
| AC-8 看板卡片字段与空态文案 | （UI 面，由功能用例 TC-CRD-01 覆盖；API 侧 JOB-12 保证字段落库） |
| AC-9 扩展一键抓取并打开预览 | CRL-01（Agent Bearer 调用等价于扩展调用） |
| AC-10 无有效令牌 → 401 | CRL-11/12 |
| AC-11 10 次 / 分钟限流 | CRL-15/16 |
| AC-12 LLM 路径 >8000 token 截断标记 | CRL-20 |

## 3. 通用横切（COM）

**TC-API-CRL-COM-01**（P0·负例）错误信封形状
- 步骤：制造 `/jobs/crawl` 的 401（NONE）、403（若存在 UI-only 限制场景）、422（非法 URL）、429（限流）各一次。
- 预期：401/403/429 响应体均为统一错误信封 `{"error":{"code","message"}}`；422 为 FastAPI `detail` 数组。
- 追溯：§12.2、既有错误处理约定。

**TC-API-CRL-COM-02**（P0·负例）CORS 预检通过
- 步骤：从 `chrome-extension://test-extension-id` 源发起 `OPTIONS /jobs/crawl`，携带 `Access-Control-Request-Headers: authorization, content-type, x-request-id`。
- 预期：200，`Access-Control-Allow-Origin: *`，`Access-Control-Allow-Methods` 包含 `POST`，`Access-Control-Allow-Headers` 包含 `authorization`、`content-type`、`x-request-id`。
- 追溯：技设 §3.3、§12.2。

**TC-API-CRL-COM-03**（P1·边界）严格 CORS 模式预检
- 前置：后端配置 `AUTOHUNT_CORS_ORIGINS=chrome-extension://test-extension-id`。
- 步骤：从允许源与不允许源分别发起 OPTIONS 预检。
- 预期：允许源返回 `Access-Control-Allow-Origin: chrome-extension://test-extension-id`；不允许源无对应 CORS 头。
- 追溯：技设 §3.3。

## 4. `/jobs/crawl` 正例（CRL-01～04）

**TC-API-CRL-01**（P0·正向）Agent Bearer 调用 BOSS 结构化路径返回 ok
- `POST /jobs/crawl`（AGENT）body 含完整 extracted。
- 预期：200，`status=ok`；`fields` 中 `company`、`title`、`jd_url`（等于请求 url）、`location` 非空；`source=boss`；`missing_fields=[]`；`confidence` 中 company/title 为 `high`；`fields.requirements` 包含 degree/experience/salary/tags。
- 追溯：AC-9、§12.2。

**TC-API-CRL-02**（P0·正向）UI session 调用 BOSS 路径返回 ok
- 步骤：同 CRL-01，以 UI session 调用。
- 预期：200，结果与 CRL-01 一致；`caller` 被记录为 `ui`（可通过 `crawl_attempt` 表或日志断言）。
- 追溯：技设 §3.4、AC-1。

**TC-API-CRL-03**（P1·正向）无 extracted 字段，后端自行拉取
- 步骤：`POST /jobs/crawl` body 仅含 `url`/`source`/`request_id`。
- 预期：200，后端按 source 选择解析策略并返回 `ok` 或 `partial`；`fields` 至少含 company/title/jd_url；`request_id` 回显。
- 追溯：§12.2、FR-3。

**TC-API-CRL-04**（P0·正向）partial 状态返回缺失字段
- 前置：构造 extracted 中 `company` 或 `title` 为空（或后端拉取页面后核心字段缺失）。
- 步骤：`POST /jobs/crawl`。
- 预期：200，`status=partial`；`missing_fields` 包含缺失字段名；`confidence` 对应字段为 `low` 或缺失；`fields` 仍回显全部已解析字段。
- 追溯：AC-6、FR-12、§12.2。

## 5. `/jobs/crawl` 失败态返回（CRL-05～08）

**TC-API-CRL-05**（P0·正向）unsupported_site 状态
- 步骤：`source=official` 但 URL 域名明显不在支持清单，或 source 传不支持的枚举值（依实现口径）。
- 预期：200，`status=unsupported_site`；`fields` 至少回显 `jd_url`；`missing_fields` 包含 company/title；`error_code`/`error_message` 非空。
- 追溯：AC-3、FR-30。

**TC-API-CRL-06**（P0·正向）fetch_failed 状态
- 前置：通过测试钩子或代理使目标站返回 403 / 连接失败。
- 步骤：`POST /jobs/crawl`。
- 预期：200，`status=fetch_failed`；`error_code` 含 `FETCH_ERROR` 或类似；不抛 500。
- 追溯：AC-4、FR-31。

**TC-API-CRL-07**（P0·正向）parse_failed 状态
- 前置：构造 LLM 返回不可解析 JSON 或站点 DOM 规则失效。
- 步骤：`POST /jobs/crawl`。
- 预期：200，`status=parse_failed`；`error_code`/`error_message` 说明失败原因；`fields` 可空或仅含 `jd_url`。
- 追溯：FR-33、§12.2。

**TC-API-CRL-08**（P0·正向）timeout 状态
- 前置：通过测试钩子使解析服务 sleep > 30s。
- 步骤：`POST /jobs/crawl`。
- 预期：30s 后返回 200，`status=timeout`；`error_code` 含 `TIMEOUT`；请求在 30s 内必须返回，不得 hang 住。
- 追溯：AC-4、FR-13。

## 6. `/jobs/crawl` 幂等（CRL-09～10，AC-7）

**TC-API-CRL-09**（P0·边界）30 秒内同一 request_id 返回同一结果
- 步骤：同一 AGENT 连续 3 次 `POST /jobs/crawl`，url/source/request_id 完全相同，间隔 < 30s。
- 预期：第 2、3 次返回与第 1 次完全一致的 `CrawlResult`（含 `fields`、`confidence`、`missing_fields`）；后端实际解析任务仅执行 1 次；第 2、3 次响应时间明显更短。
- 追溯：AC-7、FR-4、BR-4。

**TC-API-CRL-10**（P1·边界）超过 30s 后同一 request_id 重新解析
- 步骤：首次调用后等待 > 30s（或用测试钩子加速 TTL 过期），再次使用同一 request_id 调用。
- 预期：返回新的解析结果（至少响应时间显示重新执行）；`crawl_attempt` 表新增独立记录。
- 追溯：BR-4。

## 7. `/jobs/crawl` 鉴权与安全（CRL-11～14，AC-10）

**TC-API-CRL-11**（P0·负例）无凭证调用
- 步骤：`POST /jobs/crawl`（NONE）。
- 预期：401 `UNAUTHORIZED`；响应为统一错误信封；不触发解析。
- 追溯：AC-10。

**TC-API-CRL-12**（P0·负例）无效 / 吊销 Agent key
- 步骤：分别用 `BAD` 与 `AGENT-REVOKED` 调用 `/jobs/crawl`。
- 预期：均 401；吊销 key 即时生效。
- 追溯：AC-10、§12.2。

**TC-API-CRL-13**（P1·负例）URL scheme 非法
- 步骤：`POST /jobs/crawl` body 中 `url` 为 `ftp://...` 或纯文本。
- 预期：422 `VALIDATION_ERROR`；`loc` 包含 `url`。
- 追溯：§12.2、技设 §3.4。

**TC-API-CRL-14**（P1·负例）source / request_id 缺失或非法
- 步骤：分别缺 `url`、缺 `source`、缺 `request_id`、`source` 传 `unknown`、`request_id` 为空字符串。
- 预期：均 422；错误定位准确。
- 追溯：§12.2。

## 8. 频率限制与 LLM 截断（CRL-15～20，AC-11/12）

**TC-API-CRL-15**（P0·负例）单用户 1 分钟 11 次限流
- 步骤：同一 AGENT key 在 60s 内对 `/jobs/crawl` 发起 11 次请求，每次使用不同 URL / request_id。
- 预期：第 1~10 次 200；第 11 次 429 `RATE_LIMITED`，响应含明确提示；第 12 次在窗口内仍 429；窗口结束后恢复 200。
- 追溯：AC-11、BR-31、§12.2。

**TC-API-CRL-16**（P1·边界）不同用户独立计数
- 步骤：AGENT-A 与 AGENT-B 各在 60s 内发起 10 次请求。
- 预期：两者均不触发 429；限流计数相互隔离。
- 追溯：BR-31。

**TC-API-CRL-17**（P0·负例）限流不计入非 crawl 端点
- 步骤：触发限流后，调用 `GET /jobs`、`POST /jobs`、`GET /profile`。
- 预期：其余端点不受 `/jobs/crawl` 限流计数影响，正常返回。
- 追溯：BR-31。

**TC-API-CRL-18**（P1·正向）`X-Request-Id` 头透传不影响幂等
- 步骤：携带不同 `X-Request-Id` 头但 body `request_id` 相同调用两次。
- 预期：按 body `request_id` 幂等，返回同一结果。
- 追溯：技设 §3.3、FR-4。

**TC-API-CRL-19**（P1·边界）`source=official` LLM 路径返回 shape
- 步骤：`source=official`，extracted 仅含 title、少量正文。
- 预期：200，`status∈{ok,partial}`；`fields.requirements` 结构合法；`confidence` 至少含 company/title。
- 追溯：AC-12、§8.3。

**TC-API-CRL-20**（P0·边界）LLM 输入 >8000 token 截断标记
- 前置：通过测试钩子构造 `description`/`content` 长度使输入 token > 8000。
- 步骤：`POST /jobs/crawl` `source=official`。
- 预期：200，`content_truncated=true`；`fields.description` 长度被截断但仍可解析；`status` 不为 `parse_failed`。
- 追溯：AC-12、FR-15、BR-30。

## 9. 不持久化与 crawl_attempt 记录（CRL-21～22，AC-5）

**TC-API-CRL-21**（P0·负例）`/jobs/crawl` 不写入 job 表
- 步骤：调用 CRL-01 成功后，立即 `GET /jobs` 并检查数据库。
- 预期：`GET /jobs` 列表不包含本次解析结果；数据库 `job` 表无新增记录。
- 追溯：AC-5、BR-20、技设 §3.4。

**TC-API-CRL-22**（P1·正向）`crawl_attempt` 表记录
- 步骤：调用 CRL-01 / CRL-04 / CRL-05 各一次。
- 预期：数据库 `crawl_attempt` 表新增对应记录，含 `request_id`、`url`、`source`、`status`、`caller`、`created_at`；成功/部分成功记录可关联到最终保存的 job_id（若用户后续保存）。
- 追溯：技设 §「数据模型」、FR-23。

## 10. `POST /jobs` 与抓取链路衔接（JOB-11～14，AC-1/2/6）

**TC-API-JOB-11**（P0·边界）保存 CrawlResult 命中重复返回 `duplicate_of`
- 前置：已存在 J1（公司 A / 岗位 X）。
- 步骤：用 CRL-01 返回的 `fields` 调 `POST /jobs`。
- 预期：200 `JobDuplicate` `{duplicate_of:<J1 id>, job:<J1>}`；`GET /jobs` 计数不变。
- 追溯：AC-2、BR-3、PROX-3 TC-API-JOB-04。

**TC-API-JOB-12**（P0·正向）保存 CrawlResult 落扩展字段
- 步骤：用 CRL-01 返回的 `fields` 调 `POST /jobs`（新岗位）。
- 预期：201 Job 回显，包含 `description`、`requirements`（JSON）、`confidence` 字段；`channel` 为 `boss`。
- 追溯：AC-1、§10.2、技设 §「数据模型」。

**TC-API-JOB-13**（P0·负例）保存时缺 company / title
- 步骤：构造 `POST /jobs` body 缺 `company` 或 `title`。
- 预期：422；不创建记录。
- 追溯：AC-6、§10.1。

**TC-API-JOB-14**（P1·边界）去重匹配口径
- 步骤：分别测试大小写差异（"ByteDance" vs "bytedance"）、全半角差异、同公司不同岗位、同岗位不同公司。
- 预期：按 BR-1「公司名 + 岗位名」精确匹配（去除首尾空格、统一半角全角、不区分大小写）；记录实际命中/不命中行为作为证据。
- 追溯：AC-2、BR-1、PROX-3 TC-API-JOB-05。

## 11. 回归用例（REG）

**TC-API-REG-01**（P1·回归）既有 `/jobs` 端点行为不变
- 步骤：部署后重跑 PROX-3 TC-API-JOB-01/04/07/08、TC-API-COM-01/03/04。
- 预期：断言与 PROX-3 一致；新增 `description`/`requirements`/`confidence` 字段不影响旧字段。
- 追溯：§15 依赖。

**TC-API-REG-02**（P1·回归）OpenAPI 契约零 diff
- 步骤：BackendDev 执行 `scripts/export_openapi.py` 后，对比 `docs/design/api-openapi.json`。
- 预期：无 diff；`/jobs/crawl` schema、security、CORS 相关声明完整。
- 追溯：技设 §4 实现步骤 6、§7 验证方式。

## 12. 测试钩子需求（T3 执行前需 BackendDev 提供）

1. **目标站模拟钩子**：支持让 `/jobs/crawl` 对特定 URL 返回 403、超时、HTML 结构缺失、LLM 输出不可解析等预设行为，用于 CRL-06/07/08。
2. **LLM token 模拟钩子**：支持构造输入 token > 8000 或让 LLM 路径直接返回 `content_truncated=true`，用于 CRL-20。
3. **限流时钟钩子**：支持将 1 分钟窗口加速或重置，用于 CRL-15/16。
4. **幂等 TTL 钩子**：支持将 30s 幂等缓存加速过期，用于 CRL-10。
5. 以上钩子沿用 `AUTOHUNT_TEST_HOOKS=1` 门控 + `include_in_schema=False`，不污染冻结契约。

## 13. 修订记录

| 版本 | 日期 | 作者 | 变更说明 |
|---|---|---|---|
| v1.0 | 2026-08-27 | Tester-鲁智深 | T1 首版：按 AC-1~AC-12 输出 `/jobs/crawl` 接口用例 22 条 + 相关 `POST /jobs` 用例 4 条 + 通用横切 3 条 + 回归 2 条，含幂等、鉴权、CORS、限流、LLM 截断、不持久化、测试钩子需求 |
