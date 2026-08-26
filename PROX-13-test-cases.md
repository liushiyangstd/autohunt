# PROX-13 简历模块验证矩阵与测试用例

> 状态：T1 提前准备（前后端尚未合入 main，待 G2.5 部署后执行 T3）  
> 基线：PROX-4 PRD v1.0、PROX-6 技术设计 v1.1、PROX-8/9/10/11/12 实现分支  
> 适用：功能用例 / 接口用例 / 前端单元测试 / 验证矩阵

---

## 1. 测试范围与策略

### 1.1 范围

| 模块 | 内容 |
|---|---|
| 简历上传 | 格式/大小/空文件校验、多版本、默认版本、重命名、删除保护、下载、引用查看 |
| 简历解析 | 同步解析、状态机、必填字段缺失标记、LLM 解析、规则兜底、无 Key 兜底 |
| 档案编辑 | 全字段增删改、显式保存、未保存离开提示、必填高亮、版本切换 |
| LLM 配置 | API Key 配置、测试连接、加密存储、last4 提示、未保存提示 |

### 1.2 测试策略

- **自动化优先**：后端接口用例纳入 `pytest` 套件；前端关键交互纳入 `Vitest`。
- **左移**：本用例在实现完成前产出，供开发自测与代码评审参考。
- **G2.5 后执行**：T3 真实环境验证需等待前后端合入 main 并完成部署。

---

## 2. 功能用例（逐条对照验收标准）

### AC-1 上传 PDF 后解析、补全、保存生效

| 用例 ID | 场景 | 前置条件 | 操作步骤 | 期望结果 |
|---|---|---|---|---|
| FC-01 | 正常 PDF 上传并解析完成 | LLM 已配置有效 Key | 1. POST `/resumes` 上传含姓名/电话/邮箱/教育经历的 PDF | 返回 201；`parse_status=解析完成`；`missing_fields=[]` |
| FC-02 | 必填字段缺失可补全 | 已上传部分缺失的简历 | 1. 进入 D-03 编辑页<br>2. 补全缺失必填字段<br>3. 点击保存 | `PUT /profile` 200；再次读取 `parse_status=解析完成` |
| FC-03 | 解析生效后 Agent 可读 | 档案已保存生效 | 1. 修改字段但不保存<br>2. 外部读取 `/profile` | 读取到保存前的生效档案，未保存的半成品不可见 |

### AC-9 上传校验

| 用例 ID | 场景 | 操作步骤 | 期望结果 |
|---|---|---|---|
| FC-04 | 非 PDF 扩展名 | POST `/resumes` 上传 `resume.docx` | 返回 422；`code=VALIDATION_ERROR`；不产生版本 |
| FC-05 | 改扩展名为 PDF 的非 PDF 内容 | POST `/resumes` 上传内容非 PDF 但文件名 `a.pdf` | 返回 422；不产生版本 |
| FC-06 | 超过 10MB | POST `/resumes` 上传 10MB+1 字节的 PDF | 返回 422；不产生版本 |
| FC-07 | 空文件 | POST `/resumes` 上传 0 字节 PDF | 返回 422；不产生版本 |

### AC-10 扫描件/加密 PDF 解析失败兜底

| 用例 ID | 场景 | 前置条件 | 操作步骤 | 期望结果 |
|---|---|---|---|---|
| FC-08 | pypdf 文本提取失败 | LLM 已配置 | POST `/resumes` 上传损坏/扫描件 PDF | 返回 201；`parse_status=解析失败`；`parse_error` 非空；可进入 D-03 手动录入 |
| FC-09 | 手动录入后保存 | FC-08 后 | 在 D-03 补全所有字段并保存 | `PUT /profile` 200；档案生效 |

### AC-11 显式保存语义

| 用例 ID | 场景 | 操作步骤 | 期望结果 |
|---|---|---|---|
| FC-10 | 未保存不生效 | 1. 进入 D-03<br>2. 修改 `name`<br>3. 不点保存直接刷新/切换页面 | 外部读取 `/profile` 仍为原值；页面返回时提示「有未保存的更改」 |
| FC-11 | 保存后生效 | FC-10 后点击保存 | `/profile` 返回新值 |

### AC-12 删除保护与级联

| 用例 ID | 场景 | 前置条件 | 操作步骤 | 期望结果 |
|---|---|---|---|---|
| FC-12 | 删除被引用版本 | 某版本已被投递引用 | DELETE `/resumes/{id}` | 返回 409；`details.used_count>0`；版本、档案、PDF 均保留 |
| FC-13 | 删除未引用版本 | 某版本未被引用 | DELETE `/resumes/{id}` | 返回 204；`resume` 行、`profile` 行、PDF 文件一并清除 |

### AC-13 多版本与默认版本

| 用例 ID | 场景 | 操作步骤 | 期望结果 |
|---|---|---|---|
| FC-14 | 首个版本自动默认 | 上传第一版 PDF | `is_default=true` |
| FC-15 | 上传第二版不默认 | 上传第二版 PDF | 列表出现两版；第二版 `is_default=false` |
| FC-16 | 切换默认版本 | PATCH `/resumes/{v2_id}` `is_default=true` | v2 默认；v1 自动取消默认；`GET /profile` 缺省返回 v2 |
| FC-17 | 投递可引用不同版本 | 创建两份投递分别关联 v1、v2 | `/resumes/{id}/references` 分别返回正确引用记录 |

### AC-14 D-02 列表展示

| 用例 ID | 场景 | 操作步骤 | 期望结果 |
|---|---|---|---|
| FC-18 | 列表展示解析状态 | 进入简历库页面 | 每行显示 `parse_status`、缺失字段标签、`used_count` |
| FC-19 | PDF 下载 | 点击某版本下载按钮 | 浏览器下载 `/{resume_id}.pdf`，内容与原文件一致 |

### BR-8 无 LLM Key 兜底

| 用例 ID | 场景 | 前置条件 | 操作步骤 | 期望结果 |
|---|---|---|---|---|
| FC-20 | 未配置 Key 上传 | 清空 LLM 配置或新环境 | POST `/resumes` 上传任意合法 PDF | 返回 201；`parse_status=解析失败`；`parse_error=未配置 API Key`；`missing_fields` 含全部必填字段 |
| FC-21 | 未配置 Key 时前端引导 | FC-20 后 | 进入 D-02/D-03 | 显示「未配置 API Key」横幅/提示，引导前往设置页 |

### LLM 解析配置（PROX-12）

| 用例 ID | 场景 | 操作步骤 | 期望结果 |
|---|---|---|---|
| FC-22 | 配置并保存 Key | 设置页输入 API Key 并保存 | `PUT /settings/llm` 200；数据库 `api_key_enc` 为密文；响应仅显示 `api_key_last4` |
| FC-23 | 测试连接成功 | 已保存有效 Key | 点击「测试连接」 | `POST /settings/llm/test` 返回 `ok=true` |
| FC-24 | 测试连接失败 | 输入无效 Key 或错误 base_url | 点击「测试连接」 | 返回 `ok=false`；`error` 说明失败原因 |
| FC-25 | 未保存离开提示 | 修改配置后未点击保存切换页面 | 页面提示「有未保存的更改」 |
| FC-26 | 禁用 LLM 后上传 | 关闭 enabled 开关并保存 | POST `/resumes` | 等效于未配置 Key：`parse_status=解析失败`；`parse_error=未配置 API Key` |

### 隐私与降级

| 用例 ID | 场景 | 操作步骤 | 期望结果 |
|---|---|---|---|
| FC-27 | API Key 加密存储 | 保存 Key 后检查 `app_setting` 表 | `value.api_key_enc` 为密文；无 `api_key` 明文 |
| FC-28 | 日志不泄露 Key/简历全文 | 上传 PDF、测试连接、保存 Key | 检查 `server-*.log` | 无完整 API Key、无完整 PDF 文本内容 |
| FC-29 | LLM 异常降级规则解析 | LLM 已配置但 mock 超时/非法 JSON | POST `/resumes` | 返回 201；降级到规则解析；不抛 500 |

---

## 3. 接口测试用例

### 3.1 POST /resumes（上传并同步解析）

| 用例 ID | 类型 | 输入 | 期望状态码 | 期望响应 |
|---|---|---|---|---|
| API-01 | 正例 | 合法 PDF，LLM 配置完整 | 201 | `parse_status=解析完成`；`missing_fields=[]`；返回 `id/name/version/is_default/used_count/created_at` |
| API-02 | 正例 | 合法 PDF，LLM 返回部分缺失 | 201 | `parse_status=部分字段缺失`；`missing_fields` 仅含缺失必填项 |
| API-03 | 反例 | 未配置 LLM Key | 201 | `parse_status=解析失败`；`parse_error=未配置 API Key`；`missing_fields` 含 `name/phone/email/educations` |
| API-04 | 反例 | LLM 配置但 `enabled=false` | 201 | 同 API-03 |
| API-05 | 反例 | 非 PDF 扩展名 | 422 | `code=VALIDATION_ERROR`；不产生版本 |
| API-06 | 反例 | 超过 10MB | 422 | `code=VALIDATION_ERROR`；不产生版本 |
| API-07 | 反例 | 空文件 | 422 | `code=VALIDATION_ERROR`；不产生版本 |
| API-08 | 边界 | 恰好 10MB | 201 | 正常处理 |
| API-09 | 异常 | pypdf 无法解析 | 201 | `parse_status=解析失败`；`parse_error` 非空 |
| API-10 | 降级 | LLM 超时/非法输出 | 201 | 降级规则解析或 `解析失败`；HTTP 500 禁止 |
| API-11 | 字段 | 含 `name` 表单字段 | 201 | 版本名使用传入值 |

### 3.2 GET /resumes & GET /resumes/{id}

| 用例 ID | 类型 | 操作 | 期望 |
|---|---|---|---|
| API-12 | 正例 | GET `/resumes` | 200；按创建时间倒序；含 `parse_status/missing_fields/used_count` |
| API-13 | 正例 | GET `/resumes/{id}` | 200；字段与列表项一致 |
| API-14 | 反例 | GET 不存在的 id | 404；`code=NOT_FOUND` |
| API-15 | 鉴权 | 未携带 UI session cookie | 401/403 |

### 3.3 PATCH /resumes/{id}

| 用例 ID | 类型 | 输入 | 期望 |
|---|---|---|---|
| API-16 | 正例 | `{"name":"新版名称"}` | 200；`name` 更新 |
| API-17 | 正例 | `{"is_default":true}` | 200；本版本默认，其余版本取消默认 |
| API-18 | 反例 | PATCH 不存在的 id | 404 |

### 3.4 DELETE /resumes/{id}

| 用例 ID | 类型 | 前置条件 | 期望 |
|---|---|---|---|
| API-19 | 正例 | 版本未被引用 | 204；级联删除 profile 与 PDF 文件 |
| API-20 | 反例 | 版本被投递引用 | 409；`details.used_count>0` |
| API-21 | 反例 | 删除不存在的 id | 404 |

### 3.5 GET /resumes/{id}/file

| 用例 ID | 类型 | 期望 |
|---|---|---|
| API-22 | 正例 | 返回 `Content-Type: application/pdf`；字节流与原文件一致 |
| API-23 | 反例 | PDF 文件被手动删除 | 404/明确提示文件缺失 |

### 3.6 GET /resumes/{id}/references

| 用例 ID | 类型 | 期望 |
|---|---|---|
| API-24 | 正例 | 返回引用该版本的投递列表；字段含 `id/company/position/status/created_at` |
| API-25 | 正例 | 无引用 | 200；`items=[]` |

### 3.7 GET /profile & PUT /profile

| 用例 ID | 类型 | 操作 | 期望 |
|---|---|---|---|
| API-26 | 正例 | GET `/profile`（无参数） | 200；返回默认版本的档案 |
| API-27 | 正例 | GET `/profile?resume_id={id}` | 200；返回指定版本的档案 |
| API-28 | 正例 | PUT `/profile` 补全缺失必填 | 200；该版本 `parse_status` 重算为 `解析完成` |
| API-29 | 正例 | PUT `/profile` 保存后缺必填 | 200；`parse_status=部分字段缺失` |
| API-30 | 反例 | PUT `/profile` 传入不存在 `resume_id` | 404 |
| API-31 | 边界 | PUT `/profile` `email=null` | 按现有口径回填绑定求职邮箱 |

### 3.8 /settings/llm*

| 用例 ID | 类型 | 操作 | 期望 |
|---|---|---|---|
| API-32 | 正例 | GET `/settings/llm`（未配置） | 200；返回默认值；`api_key_last4=null` |
| API-33 | 正例 | PUT `/settings/llm` 保存 Key | 200；`api_key_last4` 为末四位；响应不含 `api_key_enc` |
| API-34 | 正例 | GET `/settings/llm`（已配置） | 200；`api_key_last4` 正确；无 `api_key` 明文 |
| API-35 | 正例 | POST `/settings/llm/test`（有效 Key） | 200；`ok=true`；`error=null` |
| API-36 | 反例 | POST `/settings/llm/test`（未配置） | 200；`ok=false`；`error=未配置 API Key` |
| API-37 | 隐私 | 直接查询 `app_setting` 表 | `value.api_key_enc` 为密文；无 `api_key` 字段 |
| API-38 | 边界 | PUT 传 `api_key=""` | 清空密文；`api_key_last4=null` |
| API-39 | 边界 | PUT 不传 `api_key` | 保留原密文；其他字段更新 |

---

## 4. 前端单元测试补充清单

### 4.1 Resumes 页面（D-02）

| 用例 ID | 场景 | 断言 |
|---|---|---|
| WEB-01 | 空态 | 无简历时显示引导上传文案 |
| WEB-02 | 列表渲染 | 上传后列表显示版本名、状态徽章、缺失字段、引用数 |
| WEB-03 | 上传非法文件 | 选择 `.docx` 时触发校验提示，不调用 API |
| WEB-04 | 上传超大文件 | 选择 10MB+ 文件时触发校验提示 |
| WEB-05 | 设为默认 | 点击默认切换后 PATCH 调用正确，UI 同步更新 |
| WEB-06 | 删除未引用 | 点击删除后 DELETE 调用，列表移除该项 |
| WEB-07 | 删除被引用 | 删除按钮禁用或点击后提示「已被引用」 |
| WEB-08 | 重命名 | 失焦/确认后 PATCH name 更新 |
| WEB-09 | 下载链接 | `resumeFileUrl(id)` 生成正确 href |
| WEB-10 | 引用查看 | 点击查看引用弹出/跳转引用列表 |
| WEB-11 | 无 Key 引导 | 当任一版本 `parse_error=未配置 API Key` 时显示设置页引导横幅 |

### 4.2 ProfileEdit 页面（D-03）

| 用例 ID | 场景 | 断言 |
|---|---|---|
| WEB-12 | 渲染解析结果 | 解析字段正确回填各表单 |
| WEB-13 | 必填缺失高亮 | `missing_fields` 中的字段显示「待补全」样式 |
| WEB-14 | 教育经历增删改 | 可添加/删除/编辑多条教育经历 |
| WEB-15 | 实习/项目经历增删改 | 可添加/删除/编辑多条经历 |
| WEB-16 | 技能标签 | 可添加/删除技能标签 |
| WEB-17 | 获奖证书增删改 | 可添加/删除/编辑奖项 |
| WEB-18 | 未保存离开提示 | 修改后切换路由/关闭页面前弹出确认 |
| WEB-19 | 显式保存 | 点击保存后调用 `PUT /profile`，成功后提示 |
| WEB-20 | 版本切换 | 切换版本后表单加载对应档案 |
| WEB-21 | 解析失败手动录入 | `parse_status=解析失败` 时显示完整空模板 |

### 4.3 Settings 页面（LLM 配置卡片）

| 用例 ID | 场景 | 断言 |
|---|---|---|
| WEB-22 | 初始加载 | 挂载时调用 `GET /settings/llm`，表单回填 |
| WEB-23 | API Key 密码输入 | 输入框类型为 password |
| WEB-24 | last4 提示 | 已配置时显示「已配置 Key 末四位 xxxx」 |
| WEB-25 | 测试连接成功 | 点击测试调用 POST `/settings/llm/test`；显示成功提示 |
| WEB-26 | 测试连接失败 | mock 返回 `ok=false`；显示失败原因 |
| WEB-27 | 保存配置 | 点击保存调用 PUT `/settings/llm`；成功后更新 last4 |
| WEB-28 | 未保存离开提示 | 修改表单后离开页面弹出确认 |
| WEB-29 | 成本/隐私文案 | 设置页显示「API Key 仅存本地、由您自担成本」 |

---

## 5. 验证矩阵（T3 执行清单）

| 验收项 | 验证方式 | 通过标准 | 当前状态 |
|---|---|---|---|
| AC-1 必填对齐 | 上传无教育经历 PDF | `parse_status=部分字段缺失`，`missing_fields` 含 `educations` | 待 G2.5 |
| AC-9 上传校验 | 上传非 PDF/超大/空文件 | 均返回 422，无版本产生 | 待 G2.5 |
| AC-10 解析失败兜底 | 上传扫描件/损坏 PDF | 201 + `解析失败` + 原因；D-03 可手动录入并保存 | 待 G2.5 |
| AC-11 显式保存语义 | 修改字段不保存，读取 `/profile` | 读取到保存前值；页面有未保存提示 | 待 G2.5 |
| AC-12 删除保护 | 删除被引用/未引用版本 | 被引用 409；未引用级联删除 | 待 G2.5 |
| AC-13 多版本 | 上传两版并切换默认 | 列表正确；默认切换生效；投递可引用不同版本 | 待 G2.5 |
| AC-14 D-02 展示 | 查看列表与下载 | 展示状态/缺失字段/引用数；PDF 可下载 | 待 G2.5 |
| BR-8 无 Key 兜底 | 清空 LLM 配置后上传 | 201 + `解析失败` + `未配置 API Key` | 待 G2.5 |
| 隐私 | 查库/查日志 | `api_key_enc` 密文；日志无 Key/简历全文 | 待 G2.5 |
| 降级 | mock LLM 异常 | 返回规则解析或 201 失败，不抛 500 | 待 G2.5 |
| KPI-5 | 样例简历集 | 解析成功率 ≥80% | 待 G2.5 |
| KPI-6 | 样例简历集 | 上传→生效转化率 ≥90% | 待 G2.5 |

---

## 6. 建议新增的自动化测试文件

### 6.1 后端

| 文件 | 补充内容 |
|---|---|
| `apps/server/tests/test_resumes.py` | 已覆盖大部分；建议补充「禁用 enabled 后上传」和「LLM 返回 experiences/awards 格式校验」 |
| `apps/server/tests/test_settings_llm.py` | 新建：GET/PUT/test、明文不回显、密文存储、last4、删除 Key |
| `apps/server/tests/test_profile.py` | 补充：保存后 `parse_status` 重算、版本切换读取、email 默认回填 |
| `apps/server/tests/test_resume_download.py` | 可选：下载 PDF 字节一致性、文件缺失态 |

### 6.2 前端

| 文件 | 补充内容 |
|---|---|
| `apps/web/src/pages/Resumes.test.tsx` | 新建：列表、上传校验、默认切换、删除、引用 |
| `apps/web/src/pages/ProfileEdit.test.tsx` | 新建：字段编辑、教育/经历/技能/获奖增删、保存、未保存提示 |
| `apps/web/src/pages/Settings.test.tsx` | 补充：LLM 配置卡片表单、测试连接、保存 |

---

## 7. 阻塞与依赖

- **当前阻塞**：前后端实现分支（`agent/backenddev/82f68283823e`、`agent/backenddev/15dc25551c01`、`agent/frontenddev/58d700732fb8`）尚未合入 `main`，无部署环境 URL。
- **T3 执行条件**：G2.5 部署完成后提供环境 URL；届时使用 `multica-test-automation` skill 执行接口自动化并产出测试报告。
- **本阶段交付**：用例已就绪，可进入 T2 补充清单评审与开发自测参考。
