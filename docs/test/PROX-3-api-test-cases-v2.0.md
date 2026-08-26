# autohunt 接口测试用例集 v2.0（S3c 增补，对应 OpenAPI 契约 v2 / info.version 0.2.1）

> 阶段：S3c 接口用例扩展（契约 v2 冻结后下游门禁重置，本文为本线 G2 判门输入）。作者：@Tester-鲁智深。
> 事实来源：冻结契约 `docs/design/api-openapi.json`（main @ `adcae45`，OpenAPI 3.1，info.version 0.2.1，35 paths / 47 ops，唯一事实来源）+ 技术设计 v1.2 + 接口用例集 v1.0（`docs/test/PROX-3-api-test-cases-v1.0.md`）。
> **与 v1.0 的关系**：v1.0 的 83 条用例对契约 v1 的 19 个端点**继续有效**（契约 v2 对既有端点仅 3 处已裁决变更，见 §2）；本文只覆盖**新增的 28 个操作 + 3 处既有端点变更**，并给出受影响的 v1.0 用例修订（§3）。用例 ID 延续 v1.0 编号体系，新增组：HIS/ACF/AEM/RSM/EMA/NTF/STA/SET。
> 交付形态：同 v1.0，本环境未接入 XMind/Jira，按 `multica-artifact-test-sync` 产物内容规范以全量文字用例稿交付，后续接入平台时以本文为蓝本导入。

## 1. 通用约定增补

- Base URL、鉴权夹具（UI / AGENT / AGENT-REVOKED / NONE / BAD）、统一信封断言同 v1.0 §1。
- 新增夹具：
  - 简历 PDF：合法小 PDF（<1MB）、非 PDF 文件（.docx/.txt）、超限 PDF（>10MB）、损坏 PDF（触发解析失败）。
  - IMAP 夹具：可控的 IMAP test double（或后端提供的测试钩子），支持「认证通过 / 认证失败 / 连接失败」三种行为（EMA 组依赖）。
  - 事件夹具：待确认邮件事件 E1（type=面试，matched_job_id=J1）、E2（识别未命中，matched_job_id=null）——需要后端提供种子钩子（§12）。
  - 时间夹具：可控时钟或直接写库钩子（NTF 的 fire_at、from/to 边界、token TTL 之外的时间断言依赖）。
- 媒体类型断言（v2 新增二进制/文本端点）：`/resumes/{id}/file` → application/pdf；`/events/{id}/raw` → text/plain；`/stats/export` → text/csv；错误响应仍为 JSON 信封（契约在 401/403/404 上声明了对应媒体类型，断言 Content-Type 与 body 可解析为信封）。

## 2. 契约 v2 变更总览（28 新增 + 3 变更）

**新增 28 个操作**：`GET /confirmations`（列表）、`POST /confirmations/{id}/close`、`GET /applications/{id}/history`、`GET /applications/{id}/confirmations`、`GET /applications/{id}/emails`、`PUT /profile`、`GET/PUT /settings/reminders`、resumes×7（POST/GET列表/GET/PATCH/DELETE/GET file/GET references）、email-accounts×5（POST test/GET/POST/PATCH/DELETE）、events×4（GET /{id}、GET raw、POST confirm、POST discard）、`GET /notifications`、stats×3（overview/funnel/export）。

**既有端点 3 处变更（Leader 已裁决，v1.0 用例需修订，见 §3）**：

1. `GET /confirmations/{id}` 待确认态响应按 caller 区分：UI session → `ConfirmationPendingUI`（fields 快照 + context）；Agent Bearer → 仍仅 `{status}`。响应 union 增 `ConfirmationPendingUI` 变体。
2. `ConfirmationConfirmed` 增 `submit_result` / `fail_reason` / `submitted_at`（未回写为 null）——submit_result 读回（FR-24）。
3. `GET /applications` 增可选 `from`/`to`（RFC3339，按 **applied_at** 过滤）；applied_at 为空的记录在指定 from/to 时不返回。注意与 stats 三端点的 from/to 口径不同（stats 按**投递创建时间**），两组用例分别钉住。

**既有 19 端点零改动**：经逐操作比对确认（Leader G2 复跑证据），v1.0 其余用例断言不变。

## 3. v1.0 用例修订（因契约变更）

| v1.0 用例 | 修订 |
|---|---|
| TC-API-CFM-05（待确认查询无许可） | 拆为 caller 双断言：**AGENT 调用**维持原断言（仅 `{status}`，无任何 fields/token 字段）；**UI 调用**改由本文 TC-API-CFM-21/22 覆盖（PendingUI 变体有 fields 快照但**仍无 submit_token**——BR-1 不变）。原用例的 Agent 面断言保留有效。 |
| TC-API-CFM-06/07（已确认查询） | 响应 schema 扩展：在原断言基础上增断 `submit_result`/`fail_reason`/`submitted_at` 三字段存在且未回写时为 null（详见本文 CFM-25/26）。 |
| TC-API-SUB-01/02（success/failed 回写） | 增补读回断言：回写后 `GET /confirmations/{id}` 的 submit_result/fail_reason/submitted_at 与回写内容一致（本文 CFM-25/26 为主断言，SUB-01/02 交叉引用）。 |
| TC-API-APP-03（列表筛选） | 增补：不传 from/to 时行为与 v1 完全一致（向后兼容回归断言）；from/to 语义由本文 APP-18～22 覆盖。 |
| TC-API-COM-03（全端点无凭证扫描） | 扫描范围从 19 端点扩到 47 操作，新增 28 操作逐一 401（本文 COM-05）。 |

## 4. 通用横切增补（COM）

**TC-API-COM-05**（P0·负例）v2 新增端点无凭证扫描
- 步骤：以 `NONE` 逐一调用 28 个新操作（各取最小合法请求；multipart 端点带最小文件）。
- 预期：全部 401 `UNAUTHORIZED` 统一信封，无一漏鉴权。

**TC-API-COM-06**（P0·负例）UI-only 端点 Agent 扫描
- 步骤：以 `AGENT` 逐一调用契约声明仅 UISession 的新端点：GET /confirmations、POST /confirmations/{id}/close、PUT /profile、GET/PUT /settings/reminders、resumes×7、email-accounts×5、GET /events/{id}/raw、POST /events/{id}/confirm、POST /events/{id}/discard、GET /notifications、stats×3。
- 预期：全部 403 `FORBIDDEN` 统一信封。
- 反向对照：D-05 读侧三端点与 GET /events/{id} 为**双鉴权只读**（Leader 裁决批准），AGENT 调用应 200（见 HIS/ACF/AEM/EVT 各组正例），不在本扫描内。

**TC-API-COM-07**（P1·正向）v1 既有端点回归
- 步骤：契约 v2 部署后抽跑 v1.0 的 KEY-01、JOB-04、APP-10、CFM-02、SUB-01 各一遍。
- 预期：断言全部与 v1.0 一致（纯增补不破既有行为）。

## 5. 确认流 v2 增补（CFM-19～26）

**TC-API-CFM-19**（P0·正向）确认单列表（D-01 数据源）
- 前置：造 3 张确认单（待确认/已确认/已驳回各一）。
- `GET /confirmations`（UI）→ 200 ConfirmationList `{items, next_cursor}`；每项 ConfirmationListItem 含 id/application_id/status/created_at，已确认项 confirmed_at 非空；**任一项无 submit_token / fields 快照字段**（摘要不含许可与快照）。
- `?status=待确认` → 仅命中待确认项；非法 status 值 → 422。

**TC-API-CFM-20**（P0·负例）列表端点仅 UI
- `GET /confirmations`（AGENT）→ 403 `FORBIDDEN`（BR-1：Agent 只能按 id 轮询自己的确认单，无全列表面）。

**TC-API-CFM-21**（P0·正向）caller 区分——UI 看待确认快照（契约变更 1，D-06 前提）
- C1 待确认态，`GET /confirmations/{C1}`（UI）→ 200 `ConfirmationPendingUI`：status=待确认，含 **fields**（= 创建时 Agent 提交的字段-值快照原文）、context（含 target_url）、application_id、created_at。
- **关键负断言**：响应中无 submit_token / confirmed_fields / expires_at——快照可见 ≠ 许可下发，BR-1 语义不破。

**TC-API-CFM-22**（P0·负例）caller 区分——Agent 仍仅 status
- 同一 C1 待确认态，`GET /confirmations/{C1}`（AGENT）→ 200 `ConfirmationPending` **仅** `{status:"待确认"}`；无 fields/context（Agent 自己提交的快照不经读侧回漏，最小暴露）。
- 附：Agent 调已确认单仍得 `ConfirmationConfirmed`（v1 CFM-06 面）；caller 区分仅作用于待确认变体。

**TC-API-CFM-23**（P0·正向）手动关闭（§12 手动出口，无自动超时）
- C1 待确认态，`POST /confirmations/{C1}/close`（UI）body `{"reason":"岗位已下架"}` → 200 `ConfirmationClosed`：status=**已超时关闭**，reason 回显；不带 body（或可空 reason）→ 同样 200（reason 可空）。
- 后置断言：`GET /confirmations/{C1}` → status=已超时关闭；`GET /confirmations?status=已超时关闭` 命中；该单 confirm/reject/reissue → 409（终态）。
- 防回归锚点（功能稿 TC-CFM-10）：服务端**不存在**自动超时——待确认单挂起 >24h 后查询仍为待确认（时间夹具拨快），只能经本端点手动关闭。

**TC-API-CFM-24**（P0·负例）close 前置与鉴权
- 对 `已确认` / `已驳回` / `已超时关闭` 单 close → 均 409 `STATE_CONFLICT`（契约 409 描述：非待确认态不可手动关闭）。
- AGENT 调 close → 403 `FORBIDDEN`；不存在 id → 404。

**TC-API-CFM-25**（P0·正向）submit_result 读回——success（契约变更 2，FR-24）
- C1 确认 → Agent 携 token 回写 `{result:"success", submitted_at:t}` → `GET /confirmations/{C1}`（UI 与 AGENT 各一遍）→ `ConfirmationConfirmed`：submit_result=`success`、submitted_at=t、fail_reason=null；submit_token=null（已消耗，v1 CFM-07 面）。

**TC-API-CFM-26**（P0·正向）submit_result 读回——failed 与未回写
- failed 回写 `{result:"failed", fail_reason:"官网验证码拦截"}` → 查询：submit_result=`failed`、fail_reason 原文回显、submitted_at 非空；投递状态不推进（v1 SUB-02 面）。
- 未回写对照：确认后未回写的 C2 → 查询 submit_result/fail_reason/submitted_at **均为 null**，submit_token 有效非空。

## 6. 投递列表 from/to（APP-18～22，契约变更 3）

**TC-API-APP-18**（P0·正向）from/to 按 applied_at 过滤
- 前置：APP1（applied_at=2026-08-01T10:00:00Z）、APP2（applied_at=2026-08-10T10:00:00Z）、APP3（待投递，applied_at=null）。
- `GET /applications?from=2026-08-05T00:00:00Z&to=2026-08-15T00:00:00Z` → 仅 APP2；**APP3 不出现**（契约明示：applied_at 为空的记录在指定 from/to 时不返回）。
- 仅 from / 仅 to 单边界各验一遍。

**TC-API-APP-19**（P0·正向）向后兼容
- 不传 from/to → 结果与 v1 完全一致（APP1/2/3 均在，其余筛选参数行为不变）。

**TC-API-APP-20**（P1·边界）边界包含性与 from>to
- applied_at 恰好等于 from / 恰好等于 to 的记录是否命中：契约未定义开闭区间 → 记录实际行为（§11 O-6），但两端行为必须自洽（from 与 to 同侧一致）。
- `from > to` → 契约未定义 → 记录实际行为（期望空集或 422，不得 500）。

**TC-API-APP-21**（P1·负例）非法格式
- from/to 非 RFC3339（如 `2026-08-01`、`abc`）→ 422。

**TC-API-APP-22**（P1·正向）组合筛选与 Agent 可用
- from/to + status + channel 组合 → 取交集；AGENT 重放 18/19 均 200（双鉴权端点）。

## 7. D-05 读侧三端点（HIS/ACF/AEM，双鉴权只读——Leader 裁决批准）

**TC-API-HIS-01**（P0·正向）状态历史（FR-31）
- APP1 经 UI 推进两轮 + submit-result 推进「已投递」后，`GET /applications/{APP1}/history`（UI）→ 200 StatusHistoryList，按时间顺序；每项含 from_status/to_status/**source**/**rejected**/created_at；source ∈ {ui, email, agent} 与实际 caller 一致（submit-result 推进的条目 source=agent）。

**TC-API-HIS-02**（P0·正向）rejected 标记可查（AC-6 排查面）
- Agent 回退被 409 拒绝一次后查 history → 存在 rejected=true 的条目，且 to_status=被拒目标状态；状态本身未被改动（与 v1 APP-10 联动）。

**TC-API-HIS-03**（P0·负例）鉴权与 404
- AGENT 调用 → 200（双鉴权只读，Leader 裁决）；NONE → 401；不存在 application → 404。

**TC-API-ACF-01**（P0·正向）确认记录列表（FR-22/24）
- APP1 关联 2 张确认单（一张已确认+success 回写、一张已驳回）→ `GET /applications/{APP1}/confirmations` → 200 ConfirmationRecordList：含各单 id/status/created_at/confirmed_at；已回写项 submit_result=success、submitted_at 非空、fail_reason=null；**无 submit_token 字段**（记录面不回放许可）。

**TC-API-ACF-02**（P1·空态）无确认单 → 200 `{items:[]}`；不存在 application → 404；AGENT 200 / NONE 401。

**TC-API-AEM-01**（P0·正向）邮件回溯（FR-43，RISK-5）
- E1 确认并关联 APP1 后，`GET /applications/{APP1}/emails` → 200 EmailEventDetailList：含邮件元数据（email_subject/email_sender/email_received_at）+ 事件字段；**不含邮件原文**（原文仅走 `/events/{id}/raw` 且仅 UI）。

**TC-API-AEM-02**（P1·空态/鉴权）无匹配邮件 → `{items:[]}`；AGENT 200（只读）/ NONE 401 / 不存在 application 404。

## 8. 档案写（PRF-07～11，FR-2/3，D-03 显式保存）

**TC-API-PRF-07**（P0·正向）PUT 全量替换
- `PUT /profile`（UI）body 含 resume_id + 全字段 → 200 Profile 回显；再 `GET /profile?resume_id=<同>` 与写入值逐项一致。
- **全量语义**：第二次 PUT 仅传 `{resume_id, name:"新名"}` → 200；GET 验证 educations/experiences/skills/awards 回空数组（未传字段被替换为默认，不是 merge）。

**TC-API-PRF-08**（P0·负例）仅 UI
- AGENT 调 PUT /profile → 403 `FORBIDDEN`（档案是 Agent 填表数据源，写面只给人——显式保存语义的契约担保）。

**TC-API-PRF-09**（P0·负例）resume_id 校验
- 缺 resume_id → 422；resume_id 不存在 → 404 `NOT_FOUND`（契约新增 404，落地 v1 O-3 中"resume_id 不存在未定义"的一项——GET 面仍存在，见 §11 O-3 遗留）。

**TC-API-PRF-10**（P1·边界）email 回填规则（§3.2）
- PUT 省略 email（或传 null）→ 200，GET 显示 email=已绑定求职邮箱；显式 PUT email 用户值后，换绑邮箱再 GET → 仍为旧用户值不跟随（与 v1 PRF-05 同口径，写面落地）。

**TC-API-PRF-11**（P1·正向）半完成状态不可读（显式保存）
- 档案 A 已保存；用户编辑中（未调 PUT）→ Agent `GET /profile` 仍为旧保存值。API 层面无自动保存通道即断言通过（写仅 PUT 一个入口）。

## 9. 简历（RSM-01～14，FR-1/2/3，D-02/D-03）

**TC-API-RSM-01**（P0·正向）上传解析成功
- `POST /resumes`（UI，multipart：合法 PDF + 可选 name）→ 201 ResumeInfo：id/version=1/is_default=**true**（首个版本自动默认）/parse_status=解析完成/used_count=0/created_at；缺省 name → 「简历 v1」。
- 再传第二份 → version=2、is_default=false。

**TC-API-RSM-02**（P0·边界）解析失败不阻塞（§12）
- 上传损坏/无文本 PDF → **201** + parse_status=`解析失败` + parse_error 非空；`GET /profile?resume_id=<新>` 为空档案可手动编辑（与 PRF-07 联动）；版本记录正常存在。

**TC-API-RSM-03**（P1·正向）部分字段缺失
- 上传缺必填项的 PDF → 201 + parse_status=`部分字段缺失` + missing_fields 含缺失字段名（AC-1 缺失标记数据源）。

**TC-API-RSM-04**（P0·负例）文件约束
- 非 .pdf（改后缀伪装也算）→ 422 `VALIDATION_ERROR`；>10MB → 422；缺 file 字段 → 422。

**TC-API-RSM-05**（P0·负例）仅 UI + 无凭证
- resumes 全部 7 端点 AGENT → 403；NONE → 401（COM-05/06 覆盖，此处为组锚点）。

**TC-API-RSM-06**（P0·正向）列表
- `GET /resumes` → 200 ResumeList，按创建时间倒序，每项含 parse_status 与 used_count。

**TC-API-RSM-07**（P0·正/负）详情
- 存在 → 200 ResumeInfo；不存在 → 404。

**TC-API-RSM-08**（P0·正向）重命名与设默认
- `PATCH /resumes/{v2}` `{name:"后端版"}` → 200 name 更新；`{is_default:true}` → 200，随后 GET 列表验证 v2.is_default=true 且 v1.is_default=false（**排他默认**）；`GET /profile` 缺省即返回 v2 档案（与 PRF-01 联动）。

**TC-API-RSM-09**（P1·负例）PATCH 不存在 id → 404。

**TC-API-RSM-10**（P0·正向）删除未引用版本
- `DELETE /resumes/{未引用}` → 204（无响应体）；再 GET → 404。

**TC-API-RSM-11**（P0·负例）被引用禁止删除（FR-3 回溯保护）
- APP1 引用 v1 后 `DELETE /resumes/{v1}` → 409 `STATE_CONFLICT`，信封 `details.used_count` ≥1；简历与投递记录均不变。

**TC-API-RSM-12**（P0·正向）PDF 原件下载
- `GET /resumes/{v1}/file` → 200，Content-Type=application/pdf，Content-Disposition=attachment；字节与上传原件一致（哈希比对）；不存在 → 404。

**TC-API-RSM-13**（P0·正向）投递引用列表（FR-3）
- `GET /resumes/{v1}/references` → 200 ApplicationList，恰好含引用 v1 的投递；未被引用版本 → `{items:[]}`。

**TC-API-RSM-14**（P1·边界）解析状态机口径
- parse_status 四值（解析中/解析完成/部分字段缺失/解析失败）逐一构造或经钩子断言；「解析中」为同步解析设计下的瞬态——若实际不可观测，记录为设计备注而非 FAIL（§11 O-7）。

## 10. 邮箱账户（EMA-01～12，FR-40/44，AC-8，OP-4）

**TC-API-EMA-01**（P0·正向）测试连接——始终 200
- `POST /email-accounts/test`（UI）合法参数 + IMAP 夹具认证通过 → 200 `{ok:true, error:null}`；认证失败 → 200 `{ok:false, error:<原因>}`；连接失败同形。**任何情况不为 4xx/5xx**（D-10 即时反馈语义）。

**TC-API-EMA-02**（P0·正向）绑定
- `POST /email-accounts` 合法参数（夹具通过）→ 201 EmailAccountInfo：id/email/imap_host/port（缺省 993）/status=active/last_sync_at；**响应不含 auth_code 或任何凭据形态字段**。

**TC-API-EMA-03**（P0·负例）绑定前验证失败
- 夹具认证失败 → 422 `VALIDATION_ERROR` 统一信封（message 含原因），**不创建账户**（GET 列表计数不变）。

**TC-API-EMA-04**（P0·负例）重复绑定
- 同 email 二次绑定 → 409 `STATE_CONFLICT`。

**TC-API-EMA-05**（P0·负例）凭据最小暴露（OP-4/RISK-3）
- 绑定时抓全部响应（201）、随后 GET 列表、PATCH/DELETE 响应——逐字段断言无 auth_code 明文/密文（密文亦不应出 API 面）。

**TC-API-EMA-06**（P0·正向）列表与状态（AC-8 警示条数据源）
- `GET /email-accounts` → 200 EmailAccountList；构造授权失效（夹具改为拒绝）触发轮询失败后 → status=`auth_failed`（M4 实现后置断言；本阶段可先断言 schema 与 active 态）。

**TC-API-EMA-07**（P0·正向）重授权恢复（FR-44）
- auth_failed 账户 `PATCH /email-accounts/{id}` `{auth_code:<新有效码>}` → 200 status=active。

**TC-API-EMA-08**（P0·负例）重授权验证失败
- 新码无效 → 422 `VALIDATION_ERROR`；status **保持 auth_failed** 不误判恢复。

**TC-API-EMA-09**（P0·正向）解绑清凭据
- `DELETE /email-accounts/{id}` → 204；再 GET 列表不含该项；**历史已识别事件与日程完整保留**（EVT/SCH 查询交叉断言，FR-44/AC-8）。

**TC-API-EMA-10**（P1·负例）不存在 account_id → PATCH/DELETE 均 404。

**TC-API-EMA-11**（P0·负例）仅 UI 组
- 5 端点 AGENT → 403（邮箱凭据绝不向 Agent 面暴露）。

**TC-API-EMA-12**（P1·负例）缺字段
- bind 缺 email/imap_host/auth_code → 422；port 非整数 → 422。

## 11. 事件写侧与原文（EVT-05～12，FR-42/43，BR-2，RISK-3/5）

**TC-API-EVT-05**（P0·正向）事件详情含证据区
- `GET /events/{E1}`（UI 与 AGENT 各一遍）→ 200 EmailEventDetail：列表字段 + email_subject/email_sender/email_received_at（RISK-5 可回溯）；不存在 → 404。

**TC-API-EVT-06**（P0·负例）原文仅 UI（RISK-3 最小暴露）
- `GET /events/{E1}/raw`（UI）→ 200 text/plain，含 EML headers + 正文；**AGENT → 403 `FORBIDDEN`**；不存在 → 404。

**TC-API-EVT-07**（P0·正向）确认加入日程（BR-2 写入面）
- `POST /events/{E1}/confirm`（UI）空 body → 200 EmailEventConfirmResult：event.status=已确认；**schedule_event 生成**（id/start_time/type 与事件一致）。
- 交叉断言：`GET /schedule` 出现该日程（确认前不出现——BR-2 未确认绝不入日程）；关联投递 APP1 按 §5 以 email 来源推进（如 待投递/已投递 → 面试），`GET /applications/{APP1}/history` 新增条目 **source=email**、rejected=false。

**TC-API-EVT-08**（P0·正向）修正后加入
- E2（识别未命中）confirm body `{type:"笔试", event_time:<修正值>, location:"线上", matched_job_id:<J2 对应投递>}` → 200：event 各字段取**修改后值**；schedule_event 同步取修正值；手动关联的投递状态按 email 来源推进。

**TC-API-EVT-09**（P0·负例）非待确认态 409
- 已确认事件再 confirm → 409 `STATE_CONFLICT`；已丢弃事件 confirm → 409；confirm 后 discard → 409（重复确认/丢弃幂等拒绝）。

**TC-API-EVT-10**（P0·正向）丢弃（FR-42）
- `POST /events/{E2}/discard`（UI）`{reason:"非求职邮件"}` → 200 event.status=已丢弃（reason 留存为 KPI-2 数据源——经后续查询/导出可见，具体可见面 M4 后补断）；**不生成日程**（GET /schedule 无此项）；`GET /events/pending` 不再含 E2。

**TC-API-EVT-11**（P0·负例）写侧仅 UI
- confirm/discard 以 AGENT 调用 → 403（BR-2：人确认才入日程，Agent 无写入面）。

**TC-API-EVT-12**（P1·负例）参数校验
- confirm 的 event_time 非 RFC3339 → 422；type 枚举外 → 422；不存在 event_id → 404（confirm/discard/raw 同）。

## 12. 通知（NTF-01～07，FR-32，D-01 铃铛）

**TC-API-NTF-01**（P0·正向）合并列表与排序
- 造 24h 日程提醒 + 截止提醒各一 → `GET /notifications`（UI）→ 200 NotificationList：按 fire_at 倒序；日程提醒为持久 id，截止提醒 id = `deadline:<job_id>`（虚拟 id，§4 即时计算不落库）。

**TC-API-NTF-02**（P0·正向）截止提醒生成口径
- job.deadline 在未来 24h 窗口内、且该 job 下无「已投递」及之后状态的投递 → 出现 deadline 通知；把该 job 的投递推进到已投递后 → 通知**消失**（即时计算口径，已投不提醒）。

**TC-API-NTF-03**（P0·正向）两级提醒
- 日程事件 start_time 分别处于 24h 与 1h 窗口 → 对应 kind=`24h`/`1h` 通知在 fire_at 到达后出现（时间夹具拨快验证 fire_at 前不出现）。

**TC-API-NTF-04**（P1·正向）提醒偏好过滤（与 SET 联动）
- PUT /settings/reminders 关闭 schedule_1h 后 → 1h 类通知不再出现；include_deadline=false 后 deadline 通知不出现（M4 调度按设置过滤，契约描述钉死）。

**TC-API-NTF-05**（P1·正向）分页 → 同 v1 COM-02 语义（cursor/limit 默认 50）。

**TC-API-NTF-06**（P0·负例）AGENT → 403；NONE → 401。

**TC-API-NTF-07**（P1·空态）无提醒 → 200 `{items:[], next_cursor:null}`。

## 13. 统计（STA-01～12，FR-50/51/52，§10.4 口径，AC-7）

**TC-API-STA-01**（P0·正向）overview 四指标口径
- 造数：待投递×1、已投递×2、笔试×1、面试×1、offer×1、已接受×1、未通过×1；待确认投递×2、待确认事件×1。
- `GET /stats/overview` → 200：total_applications=7（状态≠待投递）、in_progress=5（已投递+笔试+面试+offer）、pending_items=3（待确认投递+待确认事件，与 D-01 红点同口径）、offers=2（offer+已接受）。

**TC-API-STA-02**（P0·正向）funnel 四级与 entered_count 去重（§10.4）
- 造数：A 走到面试后回退已投递（history 含已投递/笔试/面试）、B 停在笔试、C 待投递。
- `GET /stats/funnel` → stages 固定四级 [已投递， 笔试， 面试， offer]；entered_count：已投递=2、笔试=2、面试=1、offer=0——**按 status_history「进入过」去重，回退不影响计数**（A 在面试级仍计 1）；C（待投递）不计入任何级。

**TC-API-STA-03**（P0·边界）分母为 0 转化率为 null
- 全新实例或无任何已投递 → conversions.written_test_rate/interview_rate/offer_rate 均为 **null**（非 0、非报错）。

**TC-API-STA-04**（P0·正向）转化率口径
- 以上述造数：written_test_rate = 进入笔试数/已投递及以后数 = 2/2；interview_rate = 进入面试/进入笔试 = 1/2（无笔试环节不剔除的口径注意单独造数验证：直接 已投递→面试 的投递在面试级计数且笔试级**也**计数——「进入该状态或主链更后状态」）；offer_rate = 进入 offer/全部已投递。
- 本条逐值断言，锁定 §10.4 口径（前端 v1 近似算法的修正基准）。

**TC-API-STA-05**（P0·正向）筛选参数（FR-51）
- 多渠道造数后 `?channel=官网` → 三端点指标仅含该渠道；`?from=&to=`（按**投递创建时间**）过滤后指标收缩——与 APP-18 的 applied_at 口径差异为本条断言点。

**TC-API-STA-06**（P0·正向）export CSV 形状
- `GET /stats/export` → 200 Content-Type=text/csv，Content-Disposition 含 `filename=applications-export.csv`；首字节为 **UTF-8 BOM**（EF BB BF）；表头与数据列为 §10.2 台账字段（公司/岗位名/渠道/地点/JD 链接/简历版本 ID/投递时间/当前状态/面试轮次/备注）；行数=当前筛选下投递数。

**TC-API-STA-07**（P1·正向）export 筛选一致性
- 带 channel/from/to 的 export 行集 = 同参数字面 funnel 覆盖的投递集（抽样比对 id）。

**TC-API-STA-08**（P1·边界）export 特殊字符
- 公司名含逗号/引号/换行 → CSV 正确转义（RFC4180）；中文不乱码。

**TC-API-STA-09**（P0·负例）stats 三端点 AGENT → 403；NONE → 401。

**TC-API-STA-10**（P1·负例）from/to 非法 → 422（三端点同）。

**TC-API-STA-11**（P1·空态）无数据 → overview 全 0；funnel entered_count 全 0、conversions 全 null；export 仅表头。

**TC-API-STA-12**（P1·正向）旁路终止态不计歧义
- 未通过/主动放弃/已过期的投递：total_applications 计入（状态≠待投递）、in_progress 不计、funnel 按其 history 到达的最高主链级计数——造数逐一钉住。

## 14. 提醒偏好（SET-01～06，FR-32 配套，D-10）

**TC-API-SET-01**（P0·正向）默认值
- 全新实例 `GET /settings/reminders`（UI）→ 200 `{schedule_24h:true, schedule_1h:true, include_deadline:true}`（未设置过返回默认全开）。

**TC-API-SET-02**（P0·正向）PUT 全量替换并读回
- `PUT /settings/reminders` `{schedule_24h:false, schedule_1h:true, include_deadline:false}` → 200 回显；GET 读回一致（持久化，非 localStorage）。

**TC-API-SET-03**（P1·边界）部分字段缺省
- PUT `{}` 或缺字段 → schema 默认 true 补齐（全量替换语义，缺省=true）；逐字段缺省各验一遍并记录（若实现按"未传保持旧值"则为偏离契约 schema 默认值语义，上报）。

**TC-API-SET-04**（P0·负例）AGENT 调 GET/PUT → 403；NONE → 401。

**TC-API-SET-05**（P1·负例）非布尔值 → 422。

**TC-API-SET-06**（P1·正向）与通知联动 → 见 NTF-04（设置是 M4 调度的过滤输入）。

## 15. AC / FR → v2 接口用例追溯矩阵（增补 v1.0 §2）

| 验收标准 / 需求 | v2 接口用例 |
|---|---|
| AC-1 简历管理（FR-1/2/3） | RSM-01～14、PRF-07～11 |
| AC-2 确认修改后值回读 | CFM-21（快照=Agent 提交原文）、CFM-25/26（回写读回） |
| AC-3 无许可不提交（BR-1） | CFM-19/20（列表无许可字段、Agent 403）、CFM-21/22（caller 区分，UI 有快照无许可 / Agent 仅 status）、CFM-24（close Agent 403）、COM-06 |
| AC-4 提交结果回写（FR-24） | CFM-25/26（submit_result/fail_reason/submitted_at 读回）、ACF-01 |
| AC-5 邮件事件（FR-42/43，BR-2） | EVT-05～12、AEM-01/02 |
| AC-6 手动优先防回退 | HIS-02（rejected 标记可查） |
| AC-7 统计（FR-50/51/52，§10.4） | STA-01～12 |
| AC-8 邮箱监控与授权失效（FR-40/44） | EMA-01～12、NTF-01～07、SET-01～06 |
| RISK-3 最小暴露 | EVT-06（原文仅 UI）、EMA-05/11（凭据不出 API 面） |
| RISK-5 可回溯 | EVT-05、AEM-01 |
| §12 空/异常态 | RSM-02（解析失败 201）、CFM-23（无自动超时+手动出口）、EVT-04 沿用 |
| FR-31 状态历史 | HIS-01/02/03 |
| FR-32 提醒 | NTF-01～07、SET-01～06 |
| FR-51 筛选 | STA-05/07、APP-18～22 |

## 16. 契约观察项（v2 增补，T3 记录实际行为；沿用 v1.0 O-1～O-5）

| 编号 | 项 | 契约现状 | T3 处置 |
|---|---|---|---|
| O-6 | from/to 开闭区间、from>to 行为 | 未定义 | 按 APP-20 记录实际行为；自洽性不满足则 FAIL 上报 |
| O-7 | parse_status=「解析中」瞬态 | 同步解析设计下可能不可观测 | 按 RSM-14 记录；不可观测记设计备注不判 FAIL |
| O-8 | GET /profile?resume_id=不存在 | v1 O-3 遗留：GET 面契约仍未列 404（PUT 面已明确 404） | 记录实际行为，建议下版契约补齐 |
| O-9 | SET-03 缺省字段语义 | schema 默认值=true vs 描述「全量替换」 | 按 SET-03 断言并与实现对齐，偏离上报 |
| O-10 | 401/403/404 响应在非 JSON 端点（file/raw/export）上的媒体类型 | 契约声明为对应媒体类型（pdf/text-plain/csv）承载信封 | 断言 Content-Type 与信封可解析性；实现若统一回 JSON 信封属合理偏离，记录后提请契约修订 |
| O-11 | EMA 组对真实 IMAP 的依赖 | 契约假定连接验证可同步完成 | T3 用 IMAP test double；超时/慢响应上限契约未定义，记录实际耗时 |

## 17. 测试钩子需求（v2 增补，随 M3–M5 实现预留）

v1 已交付钩子（TTL 加速、tamper-fields、force-expire，`AUTOHUNT_TEST_HOOKS=1` 门控）继续有效。v2 新增需求：

1. **IMAP test double**：`AUTOHUNT_IMAP_BACKEND=fake` 或等价机制，支持脚本化切换「认证通过/认证失败/连接失败」与预置邮件（驱动 EMA 全组与事件识别 pipeline）；无此钩子时 EMA-06/07/08 与 EVT 组降级为人工 + 真实邮箱慢速用例。
2. **事件种子钩子**：`POST /__test__/events/seed`（直接造待确认 email_event，含证据区元数据）——否则 EVT-05～12 依赖完整 IMAP 链路才能造数。
3. **时间控制**：通知 fire_at、截止提醒窗口、stats from/to 的边界断言需要可控时钟或直接写库设置时间字段的钩子；无钩子时 NTF-02/03 降级为长等待用例。
4. 以上钩子沿用 `AUTOHUNT_TEST_HOOKS=1` 门控 + `include_in_schema=False`，不污染冻结契约（同 v1 口径，已验证零 diff 模式）。

## 18. 自动化衔接（T3）

- 本文新增用例 87 条（COM 3 + CFM 8 + APP 5 + HIS 3 + ACF 2 + AEM 2 + PRF 5 + RSM 14 + EMA 12 + EVT 8 + NTF 7 + STA 12 + SET 6），连同 v1.0 的 83 条与 §3 修订，覆盖契约 v2 全部 47 个操作；均为 HTTP 级用例，G2.5 部署后以环境 URL + 双凭证夹具 + §17 钩子直接执行。
- M3–M5 实现完成后（后端 G2），先跑 COM-07 回归 + 本文全部新用例对齐实现行为，再随 G2.5 进入正式 T3。
- 统计口径（STA 组）是前端漏斗从「当前状态 rank 近似」切换到 status_history 真实口径的验收基准，执行时与前端 D-09 联测。

## 19. 修订记录

| 版本 | 日期 | 作者 | 变更说明 |
|---|---|---|---|
| v1.0 | 2026-08-25 | Tester-鲁智深 | S3c 首版：契约 v1 十九端点 83 条 |
| v2.0 | 2026-08-26 | Tester-鲁智深 | 契约 v2（0.2.1）增补：28 个新操作 + 3 处既有变更全覆盖；caller 区分（CFM-21/22）、close 409（CFM-24）、submit_result 读回（CFM-25/26）、from/to 边界（APP-18～22）、D-05 读侧（HIS/ACF/AEM）、简历/邮箱/事件写侧/通知/统计/提醒偏好/档案写；修订 v1.0 五条用例（§3）；新增观察项 O-6～O-11 与钩子需求 3 项 |
