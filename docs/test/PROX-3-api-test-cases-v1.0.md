# autohunt 接口测试用例集 v1.0（S3c，对应冻结 OpenAPI 契约）

> 阶段：S3c 接口用例（G3 汇合门禁输入之一：前端 + 后端 + 接口用例）。作者：@Tester-鲁智深。
> 事实来源：冻结契约 `docs/design/api-openapi.json`（commit 8dfc641，OpenAPI 3.1，唯一事实来源）+ 技术设计 v1.1（ffaa485）+ 功能用例集 v1.0（`docs/test/PROX-3-functional-test-cases-v1.0.md`，S2b）。
> 与功能用例的关系：本集为**接口级用例**（逐端点正/反/边界/鉴权/幂等，可直接对接契约做自动化断言）；S2b 功能稿中标注"以契约为準"的待定项已在 §8 全部落地。用例 ID 与功能稿互不冲突（功能=TC-XXX-nn，接口=TC-API-XXX-nn）。
> 交付形态：同 S2b，本环境未接入 XMind/Jira，按 `multica-artifact-test-sync` 产物内容规范以全量文字用例稿交付（含 AC 逐条追溯），后续接入平台时以本文为蓝本导入。

## 1. 通用约定与测试夹具

- Base URL：`http://localhost:{port}/api/v1`（默认 8741）。
- 鉴权夹具：
  - `UI` = HttpOnly Cookie session（首次启动生成）；
  - `AGENT` = `Authorization: Bearer ah_live_<random>`（经 `POST /keys` 签发）；
  - `AGENT-REVOKED` = 已吊销的 key；`NONE` = 无凭证；`BAD` = 伪造 key。
- 数据夹具：简历 v1/v2（v2 默认）、岗位 J1（公司A/岗位X）、J2（公司B/岗位Y）、投递 APP1（J1+v1，初始 `待投递`）、确认单 C1（APP1，request_id=r-001）。
- 测试钩子需求（T3 执行前需后端提供，正式申请见 §9）：① submit_token TTL 加速过期（或将时钟拨快 >30min）；② 状态历史/来源标记可查询（断言 caller 打标用）。
- 公共断言：
  - 401/403/404/409 响应体 = 统一信封 `{"error":{"code","message"}}`，code ∈ ErrorCode 枚举；
  - 422 响应体 = FastAPI 校验错误 `{"detail":[{loc,msg,type,...}]}`（**与统一信封不一致，见 §7 观察项 O-2**）；
  - 时间字段一律 RFC3339。

## 2. AC → 接口用例追溯矩阵

| 验收标准 | 接口用例 |
|---|---|
| AC-1（FR-20 档案读取面） | TC-API-PRF-01～06 |
| AC-2 确认修改后值回读 | TC-API-CFM-01/06/10/15 |
| AC-3 无许可不提交（BR-1） | TC-API-CFM-01/05/11/14/16、TC-API-SUB-04～11、TC-API-APP-13/14/15、TC-API-KEY-02/05/08 |
| AC-4 提交结果回写（FR-23/24） | TC-API-SUB-01/02/03/12、TC-API-CFM-15/17（B-2 闭环） |
| AC-5（FR-42/43 读取面） | TC-API-EVT-01～04、TC-API-SCH-01～04 |
| AC-6 手动优先防回退（BR-11） | TC-API-APP-09/10/11/12/16 |
| BR-3 重复投递提示 | TC-API-JOB-04/05 |
| BR-10 状态机 | TC-API-APP-05～12 |
| FR-25 密钥管理 | TC-API-KEY-01～08、TC-API-COM-03/04 |
| §12 空态 | TC-API-PRF-03、TC-API-EVT-04 |

## 3. 通用横切（COM）

**TC-API-COM-01**（P0·负例）错误信封形状
- 步骤：制造 401（无凭证）、403（Agent 调 /keys）、404（GET 不存在 job）、409（Agent 状态回退）各一次。
- 预期：响应体均为 `{"error":{"code":<对应枚举>,"message":<非空字符串>}}`；code 分别为 UNAUTHORIZED / FORBIDDEN / NOT_FOUND / STATE_CONFLICT。

**TC-API-COM-02**（P1·边界）分页通用语义
- 步骤：造 >50 条岗位；`GET /jobs` 不带参数 → 再携返回的 next_cursor 翻页直至 next_cursor=null。
- 预期：默认 limit=50；翻页链完整遍历且不重复、不漏；末页 next_cursor=null。无效 cursor 与 limit 越界（0/负数/超大）契约未定义 → 记录实际行为（§7 O-3）。

**TC-API-COM-03**（P0·负例）全端点无凭证扫描
- 步骤：以 `NONE` 逐一调用 19 个端点（各取最小合法请求）。
- 预期：全部 401 `UNAUTHORIZED`，无一漏鉴权。

**TC-API-COM-04**（P0·负例）无效/吊销凭证
- 步骤：以 `BAD` 与 `AGENT-REVOKED` 分别调 `GET /jobs`、`GET /profile`、`GET /confirmations/{id}`。
- 预期：均 401；吊销即时生效（允许哈希缓存短 TTL，TTL 内放行需在设计备注中确认口径）。

## 4. 密钥管理（KEY，仅 UI session）

**TC-API-KEY-01**（P0·正向）签发 key
- `POST /keys`（UI）body `{"name":"agent-cli"}`
- 预期：201；响应含 id/name/key/prefix/created_at；key 以 `ah_live_` 开头且**完整返回仅此一次**；随后 `GET /keys` 中同 id 记录**不含 key 字段**（仅 prefix）。

**TC-API-KEY-02**（P0·负例）Agent 自签发
- `POST /keys`（AGENT）→ 403 `FORBIDDEN`。

**TC-API-KEY-03**（P1·边界）缺 name → 422。

**TC-API-KEY-04**（P0·正向）列表不回显完整 key
- `GET /keys`（UI）→ 200 数组，每项含 id/name/prefix/created_at/last_used_at；任一项均无 `key` 字段。

**TC-API-KEY-05**（P0·负例）Agent 查列表
- `GET /keys`（AGENT）→ 403。

**TC-API-KEY-06**（P0·正向）吊销即时生效
- `DELETE /keys/{id}`（UI）→ 204（无响应体）；立即用该 key 调 `GET /jobs` → 401。

**TC-API-KEY-07**（P1·边界）吊销不存在的 key_id → 契约未列 404 → 记录实际行为（§7 O-3）。

**TC-API-KEY-08**（P0·负例）Agent 自吊销
- `DELETE /keys/{id}`（AGENT）→ 403。

## 5. 档案读取（PRF，FR-20）

**TC-API-PRF-01**（P0·正向）默认简历档案
- `GET /profile`（UI 与 AGENT 各一遍）→ 200，Profile schema：resume_id=v2、resume_version 正确；字段与 §10.1 字典一一对应（name/phone/email/educations[]/experiences[]/skills[]/awards[]/expected_city/expected_position）。

**TC-API-PRF-02**（P0·正向）指定版本
- `GET /profile?resume_id=<v1>` → 200 返回 v1 档案。

**TC-API-PRF-03**（P0·空态）无简历
- 全新实例 `GET /profile` → 200 + `{"empty": true}`（**非 404/500**；ProfileEmpty schema）。

**TC-API-PRF-04**（P1·边界）resume_id 不存在 → 契约未定义 → 记录实际行为（§7 O-3）。

**TC-API-PRF-05**（P1·边界）email 默认值规则（§3.2 注）
- 档案 email 未显式填写 → 回填已绑定求职邮箱；用户改过后再换绑邮箱 → 保持用户值不跟随。

**TC-API-PRF-06**（P0·负例）无凭证 → 401（COM-03 覆盖，此处作 AC-1 锚点）。

## 6. 岗位（JOB，FR-21 + BR-3）

**TC-API-JOB-01**（P0·正向）全字段创建
- `POST /jobs` 全字段 → 201，Job schema 完整回显 + 服务端生成 id/created_at（RFC3339）。

**TC-API-JOB-02**（P0·正向）仅必填创建
- body 仅 `{company, title}` → 201，可空字段为 null。

**TC-API-JOB-03**（P1·负例）缺 company 或 title → 422。

**TC-API-JOB-04**（P0·边界）BR-3 重复创建
- 已存在 J1（公司A/岗位X）后再 `POST /jobs` 同公司同岗位 → **200** + JobDuplicate `{duplicate_of:<J1 id>, job:<J1>}`；`GET /jobs` 计数不变（提示不拦截，不产生新记录）。对比：新公司为 201。

**TC-API-JOB-05**（P1·边界）重复匹配口径
- 大小写差异（"ByteDance" vs "bytedance"）、全半角差异、同公司不同岗位、同岗位不同公司 —— 逐组记录命中/不命中，作为 BR-3 匹配口径的实际行为证据（契约只承诺"同公司同岗位"，口径未定义 → §7 O-3）。

**TC-API-JOB-06**（P1·正向）列表分页 → 200 JobList `{items, next_cursor}`（细节同 COM-02）。

**TC-API-JOB-07**（P0·正/负）详情
- 存在 → 200 Job；不存在 → 404 `NOT_FOUND`。

**TC-API-JOB-08**（P0·正向）部分更新
- `PATCH /jobs/{id}` 仅传 `{location}` → 200，location 更新、其余字段不变；传 deadline 为 RFC3339 字符串正常落库。

**TC-API-JOB-09**（P1·负例）PATCH 不存在 id → 404。

**TC-API-JOB-10**（P0·正向）Agent 全量可用
- 上述 01/06/07/08 以 AGENT 重放均通过（双鉴权端点）。

## 7. 投递与状态机（APP，FR-21 + BR-10/11）

**TC-API-APP-01**（P0·正向）创建投递
- `POST /applications` `{job_id:J1, resume_id:v1}` → 201，初始 status=`待投递`，applied_at=null。

**TC-API-APP-02**（P1·负例）缺字段/不存在引用
- 缺 job_id 或 resume_id → 422；job_id 不存在 → 契约未列 404 → 记录实际行为（§7 O-3）。

**TC-API-APP-03**（P0·正向）列表筛选
- `GET /applications?status=面试&company=公司A&channel=官网` → 200，仅命中项；非法 status 值 → 422。

**TC-API-APP-04**（P1·正向）note / interview_round 更新
- `PATCH` 仅传 `{note}` 或 `{interview_round:2}` → 200，状态不变（轮次为子属性，BR-10）。

**TC-API-APP-05**（P0·正向）UI 主链全路径
- UI session 沿 `待投递→已投递→笔试→面试→offer→已接受` 逐次 PATCH → 每步 200；无需 submit_token。

**TC-API-APP-06**（P0·正向）UI 回退与重开
- UI：`面试→已投递` 200（任意合法流转）；终态 `未通过→待投递` 200（重开仅 UI）。

**TC-API-APP-07**（P0·正向）UI 进旁路终止态
- 从 `待投递`、`笔试` 分别进 `未通过`/`主动放弃`/`已过期` → 均 200。

**TC-API-APP-08**（P1·负例）UI 非法目标值 → 422（status 枚举外）。

**TC-API-APP-09**（P0·正向）Agent rank 前进
- 当前 `笔试`，AGENT PATCH `{status:"面试"}` → 200（非"已投递"目标不需 token）。

**TC-API-APP-10**（P0·负例）Agent 回退拒绝（BR-11/AC-6）
- 当前 `面试`，AGENT PATCH `笔试`、`已投递`（携合法 token 也一样）→ 409 `STATE_CONFLICT`；状态保持 `面试`。

**TC-API-APP-11**（P1·边界）Agent 同态幂等
- 当前 `笔试`，AGENT PATCH `笔试` → 幂等成功（200，不报错；按技设 §5"同态重复写入忽略为幂等成功"）。

**TC-API-APP-12**（P0·负例）旁路终止态来源白名单
- AGENT → `未通过` → 200（白名单内）；AGENT → `主动放弃`/`已过期` → 409。email 来源不可经公开 API 直接模拟 → T3 以集成方式验证（邮件识别确认后驱动），本条仅覆盖 agent 面。

**TC-API-APP-13**（P0·负例）Agent 推"已投递"无 token（AC-3）
- AGENT PATCH `{status:"已投递"}`，不带 Permit 头与 body.submit_token → 403 `PERMIT_REQUIRED`；状态不变。

**TC-API-APP-14**（P0·负例）伪造/过期 token（AC-3）
- 同上传伪造 token、过期 token（测试钩子①）→ 403 `PERMIT_INVALID`。

**TC-API-APP-15**（P0·正向）合法 token 两种携带方式
- C1 确认后取得 token：① body.submit_token 方式 → 200；② 另取新 token（reissue）用 `Permit` 头方式 → 200。两种等价。

**TC-API-APP-16**（P0·正向）UI 推"已投递"免 token
- UI PATCH `{status:"已投递"}` 无任何 token → 200（用户即确认者，§3.4 步骤 4）。

**TC-API-APP-17**（P1·负例）PATCH 不存在 application → 404。

## 8. 提交结果回写（SUB，FR-24，AgentBearer-only）

**TC-API-SUB-01**（P0·正向）success 回写
- C1 已确认取得 token → `POST /applications/{APP1}/submit-result`（AGENT）`{submit_token, result:"success", submitted_at:<RFC3339>}` → 200 SubmitResultAck `{application_id:APP1, status:"已投递", recorded:true}`；token 被消费；`GET /applications/{APP1}` status=`已投递`。

**TC-API-SUB-02**（P0·正向）failed 回写
- 重新放行取新 token 后 `{result:"failed", fail_reason:"官网验证码拦截"}` → 200，Ack.status 仍为原状态（**不推进**）；fail_reason 与字段快照留档（经 UI/后续查询验证）；token 被消耗。

**TC-API-SUB-03**（P1·负例）failed 缺 fail_reason
- schema 层 fail_reason 可空、FR-24 业务规则必填 → 记录实际行为：若 422 则符合 FR-24 预期；若 200 则记为缺口上报（§7 O-3）。

**TC-API-SUB-04**（P0·负例）无 token → 403 `PERMIT_REQUIRED`。

**TC-API-SUB-05**（P0·负例）伪造 token → 403 `PERMIT_INVALID`；投递状态不变。

**TC-API-SUB-06**（P0·负例）过期 token（测试钩子①）→ 403 `PERMIT_INVALID`；确认单保持 `已确认`；`GET /confirmations/{C1}` 的 submit_token 为 null。

**TC-API-SUB-07**（P0·负例）已消费 token 重放
- SUB-01 成功后用同一 token 再回写 → 403 `PERMIT_INVALID`（一次性语义）。

**TC-API-SUB-08**（P0·负例）跨确认单/跨投递 token
- 确认单 A、B 各确认取 token；用 A 的 token 回写 B 所属投递（或回写 A 的 token 到别的 application_id 路径）→ 403（token 绑定 confirmation_id + confirmed_fields 哈希）。

**TC-API-SUB-09**（P0·负例）字段哈希不一致
- token 签发后篡改该确认单的 confirmed_fields（需测试钩子直接改库）→ 回写 403 `PERMIT_INVALID`。无钩子时本条降级为设计断言评审项。

**TC-API-SUB-10**（P0·负例）UI session 调 submit-result
- 契约 security 仅 AgentBearer → UI 凭证调用应 403 `FORBIDDEN`（BR-1 反向门：人也不能冒充 Agent 回写通道）。

**TC-API-SUB-11**（P1·负例）路径 application 不存在 → 404（先于 token 校验或后于，记录顺序行为）。

**TC-API-SUB-12**（P1·边界）submitted_at 非法格式 → 422；缺 submitted_at → 422。

## 9. 确认流（CFM，FR-22/23 + BR-1 核心）

**TC-API-CFM-01**（P0·正向）创建确认单，响应无许可（BR-1）
- `POST /confirmations`（AGENT）`{application_id:APP1, request_id:"r-001", fields:{...}, context:{target_url}}` → 201，响应体**仅** `{confirmation_id, status:"待确认"}`；断言无任何 token/permit 类字段。

**TC-API-CFM-02**（P0·边界）request_id 幂等（含 200/201 双状态码落地）
- 同一 request_id 立刻重发 → **200** + 同一 confirmation_id（首个确认单），不产生重复记录；换 request_id 重发同 application → 201 新单。
- 注：幂等命中 200 vs 首次 201 的双状态码为已知问题（Leader 记录在案），断言按"首次 201、命中 200"执行。

**TC-API-CFM-03**（P1·负例）缺 request_id/fields/application_id → 422。

**TC-API-CFM-04**（P0·正向）双鉴权创建
- CFM-01 以 UI session 重放同样 201（契约 security 含 UISession；实际创建者为 Agent 的场景为主路径）。

**TC-API-CFM-05**（P0·负例）待确认查询无许可（AC-3）
- `GET /confirmations/{C1}`（待确认态）→ 200 ConfirmationPending，**仅** `{status:"待确认"}`；无 confirmed_fields / submit_token / expires_at。

**TC-API-CFM-06**（P0·正向）已确认查询携带许可（BR-1 唯一签发面）
- C1 确认后 `GET /confirmations/{C1}` → 200 ConfirmationConfirmed `{status:"已确认", confirmed_fields, submit_token, expires_at}`；断言 confirmed_fields = UI 确认时的**修改后值**（AC-2）；expires_at − confirmed_at ≈ 30min（TTL 断言，容差秒级）。

**TC-API-CFM-07**（P0·边界）token 失效后查询
- token 过期（钩子①）或消耗后查询 → submit_token 为 null、expires_at 仍在；status 保持 `已确认`。

**TC-API-CFM-08**（P0·正向）驳回查询
- 驳回后查询 → 200 ConfirmationClosed `{status:"已驳回", reason}`；无 submit_token。

**TC-API-CFM-09**（P1·负例）查询不存在 id → 404。

**TC-API-CFM-10**（P0·正向）人工确认（UI）
- `POST /confirmations/{C1}/confirm`（UI）`{confirmed_fields:{...修改后值...}}` → 200 ConfirmationConfirmed：服务端记录 confirmed_fields/confirmed_at 并**在确认瞬间签发** submit_token（一次性、绑定 C1 + 字段哈希、TTL 30min）。

**TC-API-CFM-11**（P0·负例）Agent 直调 confirm（BR-1 最后一道门）
- AGENT 调 confirm → 403 `FORBIDDEN`；不签发 token；状态不变。reject、reissue 同理（见 14/16）。

**TC-API-CFM-12**（P1·边界）重复 confirm
- 对 `已确认`/`已驳回` 单再 confirm → 契约未列 409 → 记录实际行为（§7 O-3；期望 409 或幂等返回原单，不得二次签发有效新 token 绕过一次性语义）。

**TC-API-CFM-13**（P0·正向）人工驳回（UI）
- `POST /confirmations/{C1}/reject`（UI）`{reason:"字段有误"}` → 200 ConfirmationClosed `{status:"已驳回"}`；不带 reason（契约允许 null）也 200——注意与功能用例 TC-CFM-03 的 UI 层必填校验不矛盾：必填是前端约束，API 层可空（§7 O-4 记录）。

**TC-API-CFM-14**（P0·负例）Agent 直调 reject → 403 `FORBIDDEN`。

**TC-API-CFM-15**（P0·正向）重新放行（B-2 恢复路径）
- C1 已确认且 token 已过期/已消耗（含 failed 回写消耗场景）→ `POST /confirmations/{C1}/reissue`（UI）→ 200 ConfirmationConfirmed：新 submit_token、confirmed_fields **不变**、重新绑定哈希、expires_at 重置（≈30min 后）。

**TC-API-CFM-16**（P0·负例）Agent 直调 reissue → 403 `FORBIDDEN`（Agent 侧无任何换发/续期接口）。

**TC-API-CFM-17**（P0·负例）reissue 前提裁决（落地 S2b "以契约为準"）
- 三种前提逐一断言，均 409 `STATE_CONFLICT`：
  ① 确认单非 `已确认` 态（待确认/已驳回）；
  ② token 仍有效（未过期未消耗）；
  ③ 已回写成功（token 正常消耗、投递已 `已投递`）——**不可重新放行**。
- 此条即 S2b TC-SUB-05 待定项的契约落地：错误码 = **409 STATE_CONFLICT**（非 403）。

**TC-API-CFM-18**（P1·负例）confirm/reject/reissue 不存在 id → 404。

## 10. 邮箱事件与日程（EVT/SCH，FR-42/43，BR-2 读取面）

**TC-API-EVT-01**（P0·正向）待确认事件列表
- `GET /events/pending`（UI 与 AGENT 各一遍）→ 200 EmailEventList，items 均为 `status:"待确认"` 的 EmailEvent（type ∈ 测评/笔试/面试/offer/拒信），不含已确认/已丢弃。

**TC-API-EVT-02**（P1·正向）分页 → 同 COM-02 语义。

**TC-API-EVT-03**（P1·正向）事件字段完整性
- 抽样断言字段：id/type/event_time/location/meeting_link/company/matched_job_id/status/created_at；event_time 为 RFC3339。

**TC-API-EVT-04**（P0·空态）无事件 → 200 `{items:[], next_cursor:null}`。

**TC-API-SCH-01**（P0·正向）日程区间查询
- `GET /schedule?from=<t1>&to=<t2>` → 200 ScheduleEventList，items 均为 start_time ∈ [t1,t2) 的**已确认**事件；不含待确认（BR-2：未确认绝不入日程）。

**TC-API-SCH-02**（P1·正向）缺省参数 → 返回全部已确认日程事件。

**TC-API-SCH-03**（P1·负例）from/to 非 RFC3339 → 422。

**TC-API-SCH-04**（P0·正向）Agent 只读 → AGENT 调 01/02 均 200（事件确认/丢弃为 UI 操作，MVP 无 Agent 写接口，契约面无暴露即断言通过）。

## 11. 契约观察项与已知问题（T3 执行时记录实际行为）

| 编号 | 项 | 契约现状 | T3 处置 |
|---|---|---|---|
| O-1 | 幂等命中 200/201 双状态码 | 已知问题，Leader 记录在案 | 按"首次 201、命中 200"断言（CFM-02） |
| O-2 | 422 响应体为 FastAPI `{"detail":[...]}` 而非统一错误信封 | 契约 schema 即如此（HTTPValidationError） | 按契约断言；建议后续版本统一或在契约中显式说明，提为改进项 |
| O-3 | 契约未定义行为：无效 cursor、limit 越界、resume_id 不存在、DELETE 不存在 key、POST /applications 引用不存在 job、重复 confirm、failed 缺 fail_reason | 未列响应 | 逐一记录实际行为，FAIL 与否按 §5 状态机/BR 精神裁决，缺口上报 Leader |
| O-4 | reject 的 reason：API 可空 vs UI 必填 | 契约可空 | 双层断言，不冲突（CFM-13） |
| O-5 | submit-result 仅 AgentBearer：UI 调用 403 为推断（security 声明语义） | 契约未显式列 403 描述 | 按 403 断言（SUB-10）；若实现放行 UI 则 FAIL 上报 |

## 12. 自动化衔接（T3）

- 全部 83 条均为 HTTP 级用例，天然可脚本化（pytest + httpx / REST Assured 均可）；G2.5 部署后以环境 URL + 双凭证夹具直接执行。
- 依赖后端提供两个测试钩子（§1）：token TTL 加速、（可选）confirmed_fields 篡改——M2 实现时请 @BackendDev-王工 预留，缺口将阻塞 SUB-06/09 与 CFM-07 的自动执行（届时降级为时钟等待 30min 的慢速用例）。
- 用例对功能稿的覆盖关系：SEC 负例矩阵（TC-SEC-01～14）全部由本集 CFM/SUB/APP/KEY/COM 对应条目在 API 层覆盖；TC-SUB-04/05/06 的 B-2 闭环由 SUB-06/07 + CFM-15/17 覆盖；SM 系列由 APP-05～12 覆盖。功能稿的 UI 可见面断言（D-06 提示条等）不在本集范围，留待 T3 UI 自动化/人工。

## 13. 修订记录

| 版本 | 日期 | 作者 | 变更说明 |
|---|---|---|---|
| v1.0 | 2026-08-25 | Tester-鲁智深 | S3c 首版：19 端点全覆盖，正/反/边界/鉴权/幂等共 83 条；落地 S2b 全部"以契约为準"待定项（reissue 409、submit-result 403 双码、幂等 200/201、submit-result AgentBearer-only）；附 5 项契约观察项 |
