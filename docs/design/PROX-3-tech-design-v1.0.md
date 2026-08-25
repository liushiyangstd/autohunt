# autohunt 技术设计 v1.0（S1a）

> 基线：PRD-autohunt-v1.0.md（G0 基线版，Issue PROX-3 附件）。
> 仓库现状：空仓库，无既有代码基线 —— 本文为绿地（greenfield）初始设计，"最小可行"原则体现为：单进程单体、嵌入式存储、无云依赖。
> 读者：@BackendDev @FrontendDev @Tester；判门：G1（Leader + Reviewer 业务评审）。

## 1. 当前架构

无。仓库为空，本设计定义首个版本的整体架构与对外契约。

## 2. 建议改动：总体架构与技术选型

### 2.1 形态（OP-11 / OP-5）

本地优先的单机 Web 应用：用户在本机运行一个后端进程，浏览器访问 `http://localhost:5173`（开发）/ 后端托管的静态构建产物（生产）。无云账号体系，全部数据存于本机。

```
┌────────────────────────────────────────────────────┐
│ 浏览器 (React SPA)                                  │
│  工作台/简历库/岗位看板/日程/统计/设置/确认界面        │
└──────────────┬─────────────────────────────────────┘
               │ HTTP /api/v1（UI Session 鉴权）
┌──────────────▼─────────────────────────────────────┐
│ 后端单体 (FastAPI, Python 3.12)                     │
│  ├─ REST API 层（同一套路由，双鉴权：UI session /    │
│  │   Agent Bearer key）                             │
│  ├─ 领域服务：档案/岗位/投递/确认流/日程/统计          │
│  ├─ 状态机服务（BR-10/BR-11 唯一裁决点）              │
│  ├─ IMAP 监控 Worker（asyncio 轮询）                 │
│  ├─ 事件识别 pipeline（规则解析，LLM 接口预留）        │
│  └─ 提醒调度器（24h/1h 两级，应用内通知）             │
└──────┬──────────────────────────┬──────────────────┘
       │ SQLModel/SQLite          │ IMAP
┌──────▼───────┐          ┌───────▼────────┐   ┌──────────────┐
│ autohunt.db  │          │ 用户求职邮箱     │   │ 外部 Agent CLI│
│ (单文件本地库) │          └────────────────┘   │ （独立运维，   │
└──────────────┘                                │ 仅经 API 交互)│
                                                └──────▲───────┘
                                        Bearer API key /api/v1
```

### 2.2 选型与理由

| 决策点 | 选择 | 理由 / 放弃的备选 |
|---|---|---|
| 后端 | Python 3.12 + FastAPI | PDF 解析（PyMuPDF）、IMAP（aioimaplib）生态最成熟；类型友好、OpenAPI 自动生成可直接作为对外契约文档。备选 NestJS：邮件/PDF 库成熟度弱，放弃 |
| 存储（OP-5） | SQLite（单文件，WAL 模式）+ SQLModel ORM | 单用户本地工具无需服务端数据库；零运维、可备份（复制文件即备份）。备选 IndexedDB 纯前端方案：无法支撑后台 IMAP 轮询与对外 API，放弃 |
| 前端 | React 18 + Vite + TypeScript + TanStack Query | 看板/日历交互成熟生态；细节 UI 组件库选型交 S1b 后与前端确认 |
| PDF 解析 | PyMuPDF 提取文本 + 规则/模板分段为档案字段 | 解析失败回退手动编辑（FR-2、§12）。LLM 抽取作为可选 provider 预留接口，MVP 不依赖 |
| IMAP | aioimaplib，5 分钟轮询（可配），UID 增量拉取 | IDLE 长连接放 v0.2；轮询对 MVP 足够且简单可靠 |
| 提醒 | 后端调度器 + 前端轮询/SSE 拉取应用内通知 | OP-8 已定应用内通知，无需系统级推送 |
| 密钥存储 | API key 仅存 SHA-256 哈希；邮箱授权码用本机对称加密（Fernet，密钥置于用户目录 0600 权限文件） | 单机威胁模型：防文件泄露后的明文扩散，不防本机入侵 |

部署/分发：MVP 以 `pip install` / 源码启动即可；一键打包（PyInstaller）列后续。

## 3. 系统对外 API 契约（最高优先级 —— 外部 Agent 唯一接口）

Base URL：`http://localhost:{port}/api/v1`（默认端口 8741，可配）。
通用约定：JSON；错误统一信封 `{"error": {"code", "message", "details?"}}`；时间一律 RFC3339（UTC 存储、前端本地化展示）；列表分页 `?cursor=&limit=`（默认 50）。

### 3.1 鉴权与密钥管理（FR-25）

- Agent 调用一律 `Authorization: Bearer ah_live_<random>`；密钥仅在创建时完整返回一次，服务端只存哈希 + 前缀（用于列表展示）。
- Web UI 使用首次启动生成的本地 session token（HttpOnly Cookie）。同一套路由由鉴权中间件按凭证类型打标 `caller ∈ {ui, agent}`，供状态机做来源裁决（BR-11）。
- 密钥管理端点（UI session 调用；Agent 不可自签发/自吊销）：
  - `POST /keys` → 201 `{id, name, key}`（key 仅此一次）
  - `GET /keys` → 列表（id/name/前缀/创建时间/最近使用时间，不含 key）
  - `DELETE /keys/{id}` → 吊销，即时生效（哈希缓存可短 TTL）
- 错误码：`UNAUTHORIZED`(401)、`FORBIDDEN`(403)。

### 3.2 档案读取（FR-20）

- `GET /profile?resume_id={id}` → 指定简历版本的结构化档案；缺省返回默认简历版本。
- 无简历时返回 200 + `{"empty": true}`（对应 §12 空态，Agent 可据此提示"先完善档案"）。
- 响应字段与 §10.1 字典一一对应：`name, phone, email, educations[], experiences[], skills[], awards[], expected_city, expected_position, resume_id, resume_version`。

### 3.3 岗位与投递读写（FR-21）

- `POST /jobs` / `GET /jobs` / `GET /jobs/{id}` / `PATCH /jobs/{id}` —— 字段同 §10.2（公司/岗位名/JD 链接/地点/渠道/截止日期）。同公司同岗位重复创建返回 200 + `duplicate_of`（BR-3 提示不拦截）。
- `POST /applications` `{job_id, resume_id}` → 创建投递记录，初始状态 `待投递`。
- `GET /applications?status=&company=&channel=` —— 看板数据源（FR-12）。
- `PATCH /applications/{id}` `{status, note?, interview_round?}` —— 状态推进，经状态机裁决（§5）；来源按 caller 打标。冲突返回 409 `STATE_CONFLICT`。

### 3.4 确认流（FR-22/23/24 + BR-1 —— 本契约的核心）

状态：`待确认 → 已确认 / 已驳回 / 已超时关闭`（§10.3）。

1. **创建待确认**：`POST /confirmations`（Agent）
   ```json
   {"application_id": "...", "request_id": "agent-uuid",
    "fields": {"姓名": "...", "电话": "...", "...": "..."},
    "context": {"target_url": "...", "note": "..."}}
   ```
   → 201 `{confirmation_id, status: "待确认"}`。**响应不携带任何可提交许可。**
   `request_id` 幂等去重：同一 Agent 重试返回首个 confirmation（满足 AC-3 异常重试路径要求）。
2. **人工确认（UI）**：用户在确认界面核对字段-值快照、可修改任意值，确认或驳回。服务端记录 `confirmed_fields`（含修改后值）、`confirmed_at`，并在确认瞬间签发 **submit_token**：一次性、绑定 confirmation_id + confirmed_fields 哈希、TTL 30 分钟。
3. **查询结果**：`GET /confirmations/{id}`（Agent）
   - `待确认` → `{status}`，无其他字段；
   - `已驳回/已超时关闭` → `{status, reason?}`，流程终止；
   - `已确认` → `{status, confirmed_fields, submit_token, expires_at}`。
   **BR-1 落地：submit_token 只在已确认时出现，这是系统内唯一的"可提交许可"。**
4. **回写提交结果**：`POST /applications/{id}/submit-result`（Agent）
   ```json
   {"submit_token": "...", "result": "success" | "failed",
    "fail_reason": "...", "submitted_at": "..."}
   ```
   服务端校验 token（有效、未用、未过期、字段哈希一致）→ 消费 token → 成功则将投递推进 `已投递`（来源=agent），失败则记录 fail_reason 并保留字段快照（FR-24），状态留待用户人工处置（UI 提供"标记已人工投递"按钮）。
   无 token / token 无效 → 403 `PERMIT_REQUIRED` / `PERMIT_INVALID`。
   **Agent 直调 `PATCH /applications/{id}` 将状态改为 `已投递` 也必须携带 submit_token**（`Permit` 头或 body 字段），确保不存在绕过确认流的已提交路径（AC-3）。手动（UI）推进不受此限 —— 用户本人即确认者。
5. **超时**：待确认超过 72h 未处理，前端标记"已超时关闭"（可手动关闭/重开为新任务，§12）。

### 3.5 邮箱事件与日程（UI 为主，Agent 只读）

- `GET /events/pending` —— 待确认事件列表（FR-42，UI 消费）。
- `GET /schedule?from=&to=` —— 日程视图（FR-43）。
- Agent 侧 MVP 只读；事件确认/丢弃为 UI 操作（BR-2 主体是用户）。

### 3.6 契约交付方式

FastAPI 自动生成 OpenAPI 3.1（`/openapi.json`），随仓库导出 `docs/design/api-openapi.json` 作为对外契约冻结版本；变更走 PR 评审。Agent 侧以此文件为准。

## 4. 数据模型（§10 字段字典落地，SQLite）

| 表 | 关键字段 | 说明 |
|---|---|---|
| `resume` | id, name, file_path, is_default, created_at | PDF 原件存 `data/resumes/` |
| `profile` | id, resume_id(FK), name, phone, email, educations(JSON), experiences(JSON), skills(JSON), awards(JSON), expected_city, expected_position | §10.1 全字段；JSON 列存列表，查询无需 join |
| `job` | id, company, title, jd_url, location, channel, deadline, created_at | company+title 建普通索引供重复提示（BR-3） |
| `application` | id, job_id, resume_id, applied_at, status, interview_round, note | status 取值即 BR-10 状态集 |
| `status_history` | id, application_id, from_status, to_status, source(ui/email/agent), created_at | FR-31 审计 |
| `confirmation` | id, application_id, request_id(unique), fields(JSON), status, confirmed_fields(JSON), confirmed_at, submit_token_hash, token_expires_at, token_consumed, submit_result, fail_reason, created_at | §10.3；token 同样只存哈希 |
| `email_account` | id, email, imap_host, port, auth_code_enc, status(active/auth_failed), last_uid, last_sync_at | FR-40/44 |
| `email_event` | id, account_id, message_id(unique), type(测评/笔试/面试/offer/拒信), event_time, location, meeting_link, company, matched_job_id, raw_path, status(待确认/已确认/已丢弃), created_at | raw_path 指向本地 EML 存档（FR-43 回溯） |
| `schedule_event` | id, application_id, source_event_id, title, type, start_time, end_time, location, meeting_link | 确认后生成（BR-2） |
| `notification` | id, schedule_event_id, kind(24h/1h), fire_at, status(待触发/已触发) | FR-32 |
| `api_key` | id, name, key_hash, prefix, created_at, revoked_at, last_used_at | FR-25 |

迁移：SQLModel + Alembic；`PRAGMA journal_mode=WAL`。

## 5. 状态机实现（BR-10 / BR-11 —— 唯一裁决点，所有写路径必经）

主链（rank 递增）：`待投递(0) → 已投递(1) → 笔试(2) → 面试(3) → offer(4) → 已接受/已拒绝(5)`；旁路终止态：`未通过 / 主动放弃 / 已过期`（可从任意非终态进入；进入后仅 UI 可重开为 `待投递`）。`interview_round` 为 application 字段，不单独设状态。

裁决规则 `can_transition(current, target, source)`：
- **UI（手动）**：允许任意合法流转，含回退（用户知情的修正）。
- **agent / email（自动来源）**：仅允许 rank 前进；**target.rank < current.rank 一律拒绝**；target.rank == current.rank 拒绝（同态重复写入忽略为幂等成功）。即"自动来源不得回退状态"（BR-11），不仅限手动推进的 —— 简化规则对 MVP 更安全，手动永远可纠正。
- Agent 写入 `已投递` 另需 submit_token（§3.4）。
- 每次流转写 `status_history`（FR-31）。被拒绝的自动写入也落一条 `rejected` 标记的 history，便于 AC-6 排查。

## 6. 邮箱 IMAP 监控与事件识别（FR-40～44）

- **Worker**：asyncio 任务，每账户每 5 分钟（可配）连接 → `UID SEARCH UNSEEN UID > last_uid` → 拉取新邮件 → 处理 → 推进 last_uid。崩溃重连指数退避。
- **识别 pipeline**（BR-2：全部先进待确认）：
  1. 粗筛：发件域/主题关键词（笔试、面试、测评、offer、感谢信等中英文词表）判定招聘相关；不相关直接跳过（不入库）。
  2. 解析：规则 + 正则抽取事件类型、时间（中文日期格式归一化，如"8月28日14:00"、"下周三下午"→ 结合收件日期推断并标记置信度）、地点/会议链接（腾讯会议/Zoom/牛客等链接模式）。
  3. 关联：公司名/岗位名对 `job` 表模糊匹配（别名表可后续扩展）；匹配不上则 `matched_job_id=NULL`，用户确认时手动关联。
  4. 去重：`message_id` 唯一约束；内容哈希兜底防重复邮件。
  5. 产出 `email_event(待确认)` + 原始 EML 落盘 `data/mail/`。
- **LLM provider 接口预留**（`EventExtractor` 抽象）：MVP 默认规则实现；接入 LLM 可提升 KPI-2，但不在 MVP 关键路径。
- **FR-44 授权失效**：认证异常 → account.status=auth_failed、暂停该账户轮询、UI 顶部持续横幅提示；历史数据不动；恢复授权后续跑（last_uid 保证不重复）。
- **隐私（RISK-3）**：仅保存粗筛命中的邮件；授权码加密存储；设置页提供解绑并清除凭据。

## 7. 受影响组件（全部为新建）

| 模块 | 归属 | 内容 |
|---|---|---|
| `apps/server` | BackendDev | FastAPI 应用：路由、鉴权中间件、领域服务、状态机、Worker、调度器 |
| `apps/web` | FrontendDev | React SPA：7 个页面（§7 信息架构），确认界面为最高交互优先级 |
| `packages/domain` | BackendDev | SQLModel 模型 + Alembic 迁移 |
| `docs/design/` | Architect | 本文档 + 后续导出 OpenAPI |
| 外部 Agent CLI | 非本系统 | 仅消费 §3 契约；契约评审需 Leader 拉 Agent 维护者确认 |

## 8. 实现步骤（建议里程碑，P0 优先）

1. **M1 地基**：monorepo 骨架；SQLModel 全表 + 迁移；鉴权中间件（session + API key，FR-25）；`POST/GET/DELETE /keys`；`GET /profile`（FR-20，含空态）。→ 对应 §12 空态基线。
2. **M2 确认流闭环（最高优先级）**：jobs/applications CRUD（FR-10/11/21）→ 状态机服务（BR-10/11）→ confirmations 三端点 + submit_token + submit-result 回写（FR-22/23/24、BR-1）→ UI 确认界面。**AC-2/3/4 在此里程碑全量可验。**
3. **M3 台账与看板**：简历上传 + PDF 解析 + 档案编辑（FR-1/2/3）；看板筛选搜索（FR-12）；状态历史展示（FR-31）。→ AC-1。
4. **M4 邮箱与日程**：email_account 绑定（FR-40）→ IMAP Worker + 识别 pipeline（FR-41）→ 待确认事件列表 + 确认入日程（FR-42、BR-2）→ 日程视图 + 邮件回溯（FR-43）→ 提醒调度（FR-32）→ 授权失效处理（FR-44）。→ AC-5/6/8。
5. **M5 统计**：漏斗 + 指标卡 + 维度筛选（FR-50/51/52，口径按 §10.4）。→ AC-7。

前端与后端按 OpenAPI 契约并行；S1b UI 稿到位前，M2 确认界面可先出低保真实现。

## 9. 验证方式（对齐 AC）

| AC | 验证手段 |
|---|---|
| AC-1 | 集成测试：上传样例 PDF → 断言必填字段解析/缺失标记 → 手动补全保存往返 |
| AC-2 | 端到端脚本（模拟 Agent）：建岗 → 建投递 → POST confirmation → UI（API 模拟用户）改值确认 → GET confirmation 断言返回修改后值与 submit_token |
| AC-3 | 负例矩阵：未确认查询无 token；伪造/过期/已消费 token 回写均 403；Agent 直 PATCH 已投递无 token 被拒；同 request_id 重试返回同一确认单 |
| AC-4 | 成功/失败两条回写路径断言台账与快照保留（FR-24） |
| AC-5 | 测试夹具：本地 GreenMail/Dovecot IMAP + 模拟笔试邮件 → 断言 5 分钟内进待确认 → 确认后日程可见且关联投递 |
| AC-6 | 状态机单测：手动推进后，email/agent 来源的回退写一律 409 且落 rejected history |
| AC-7 | 造 10 条台账数据，漏斗接口结果与 §10.4 手工核算对拍 |
| AC-8 | 置错授权码 → 断言 banner 提示、轮询暂停、历史数据完整；恢复后续跑不重不漏 |

另：OpenAPI 导出 diff 进 CI，契约变更必须过评审（保护外部 Agent）。

## 10. 风险与边界

| 风险 | 说明 | 缓解 |
|---|---|---|
| RISK-1 站点差异 | 填表稳定性在外部 Agent 侧 | 契约明确失败回写义务（§3.4）；KPI-1 监控 |
| RISK-2/3 隐私 | 简历/邮件敏感 | 本地存储、API 鉴权、授权码加密、最小化邮件留存 |
| BR-1 绕过 | 系统内出现无许可提交路径 | submit_token 单点签发 + 状态机单点裁决 + AC-3 负例矩阵 |
| 时间解析歧义 | 中文邮件时间格式多样（RISK-5） | 置信度标记 + 一律人工确认（BR-2）+ 原始邮件可回溯 |
| IMAP 兼容性 | 各服务商 UID/文件夹差异 | 主流邮箱（QQ/163/Gmail）实测矩阵列入 M4 验收 |
| 单机并发 | SQLite 写锁 | WAL + 短事务；单用户场景不构成瓶颈 |
| 端口占用/多实例 | 本地工具常见问题 | 端口可配 + 启动时实例锁文件 |
