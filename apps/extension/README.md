# autohunt 职位抓取扩展（MV3）

抓取当前职位页 → 调用本地后端 `POST /api/v1/jobs/crawl` 解析 → 打开 Web 预览页，用户确认保存后才入库（绝不自动入库）。

## 文件

| 文件 | 职责 |
|---|---|
| `manifest.json` | MV3 清单：权限 activeTab / storage / scripting / notifications，host `http://localhost:8080/*` 与 `http://localhost:8741/*`（兼容两种端口；自定义端口见「配置」说明） |
| `content.js` | 注入页面执行：BOSS 直聘 / 牛客按 DOM 选择器预提取（与后端 `crawl_parser.py` 规则一致）；其他站点回传 title + 正文摘要（截断 20000 字符） |
| `background.js` | 点击图标 → 注入 content.js → 组装 CrawlRequest（`ext-<uuid>`）→ 调后端（地址从 storage 的 `api_base` 读取，默认 8080）→ 打开预览页 `/#/jobs/new?prefill=<base64url>`；401/429/超时/失败均有中文提示 |
| `options.html` / `options.js` | API key 与后端地址录入与保存（chrome.storage.local） |
| `icon48.png` | 通知图标 |

## 安装

1. 启动本地后端（默认 `http://localhost:8080`，与 `apps/web/vite.config.ts` proxy target 一致）与前端（`http://localhost:5173`）。
2. Chrome / Edge 打开 `chrome://extensions`，开启「开发者模式」。
3. 点「加载已解压的扩展程序」，选择本目录（`apps/extension/`）。

## 配置

打开扩展「选项」页（右键扩展图标 →「选项」，或详情页 → 扩展程序选项），有两项设置：

- **API key**：在 `http://localhost:5173/#/settings` 的「Agent 接入凭据」一节生成，完整复制 `ah_live_` 开头的密钥（仅显示一次）粘贴到此处。
- **后端地址**：默认 `http://localhost:8080`，需与你启动后端的 uvicorn 端口一致；若后端跑在 8741 则改为 `http://localhost:8741`。保存时做格式校验（http/https + host:port，自动去尾部斜杠）。

两项均保存在 `chrome.storage.local`（`apiKey` / `api_base`），`background.js` 每次请求时读取。

> 自定义端口说明：manifest 的 `host_permissions` 已内置 `localhost:8080` 与 `localhost:8741` 两个端口。若后端跑在其他端口，MV3 的 `fetch` 会因缺少主机权限被拒；本迭代不实现动态权限申请，请临时在 `manifest.json` 的 `host_permissions` 中加入对应 `http://localhost:<端口>/*` 后重新加载扩展。

## 使用

- 在 BOSS 直聘（`www.zhipin.com`）或牛客（`www.nowcoder.com`）职位详情页点击扩展图标。
- 其他站点同样可点击，走 LLM 兜底解析（需已配置 LLM）。
- 解析成功（ok / partial）自动打开 `http://localhost:5173/#/jobs/new?prefill=...` 预览页，编辑确认后点保存入库。
- 不支持站点 / 抓取失败会弹出通知，并视情况打开手动录入页（URL 已预填）。

## 注意事项

- 30 秒同步等待期间 MV3 service worker 可能被回收（RISK-3）：已用 storage 心跳保活 + 35s 超时兜底；若实测超时率偏高，后续升级为「task_id + 轮询」异步模式。
- base64url 编码前先做 UTF-8 字节转换（TextEncoder），避免中文乱码。
- 后端 CORS 需允许扩展来源（`AUTOHUNT_CORS_ORIGINS`，默认 `*` 即可）。
