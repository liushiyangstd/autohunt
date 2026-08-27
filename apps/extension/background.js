/* autohunt 职位抓取 — MV3 background service worker（PROX-19 技设 §7.6 / §8.3）。
 *
 * 流程：点击扩展图标 → 注入 content.js 收集页面字段 → 组装 CrawlRequest
 * → fetch POST /api/v1/jobs/crawl（Bearer ah_live_<random>）
 * → 成功打开 Web 预览页 /#/jobs/new?prefill=<base64url(CrawlResult)>。
 *
 * RISK-3：30s 同步等待期间 SW 可能被回收；本迭代用 storage 心跳保活 + 超时兜底，
 * 不实现异步 task_id 轮询（实测超时率偏高时再升级，见技设 §10）。
 */

"use strict";

var API_BASE = "http://localhost:8741";
var WEB_BASE = "http://localhost:5173";
var FETCH_TIMEOUT_MS = 35000; // 略大于后端 30s 总超时

/** 通知用户（PRD §14 文案风格） */
function notify(title, message) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icon48.png", // 缺图标时 Chrome 回退默认图标，不影响功能
    title: title,
    message: message,
  });
}

/** SW 保活：抓取期间每 20s 调一次扩展 API，重置 idle 计时（RISK-3 缓解） */
function keepAlive() {
  var timer = setInterval(function () {
    chrome.runtime.getPlatformInfo(function () {
      void chrome.runtime.lastError;
    });
  }, 20000);
  return function () {
    clearInterval(timer);
  };
}

/** CrawlResult 含中文，必须先按 UTF-8 字节编码再 base64url（atob/btoa 只认 Latin-1） */
function base64urlEncode(obj) {
  var bytes = new TextEncoder().encode(JSON.stringify(obj));
  var bin = "";
  for (var i = 0; i < bytes.length; i++) {
    bin += String.fromCharCode(bytes[i]);
  }
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function openPreview(result) {
  var url = WEB_BASE + "/#/jobs/new?prefill=" + encodeURIComponent(base64urlEncode(result));
  chrome.tabs.create({ url: url });
}

function openManual(jdUrl) {
  var url = WEB_BASE + "/#/jobs/new?url=" + encodeURIComponent(jdUrl);
  chrome.tabs.create({ url: url });
}

function newRequestId() {
  return "ext-" + crypto.randomUUID();
}

async function crawl(tab) {
  var stopKeepAlive = keepAlive();
  try {
    // 1. 注入 content.js，返回值即 {source, extracted}
    var collected = null;
    try {
      var results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["content.js"],
      });
      collected = results && results[0] ? results[0].result : null;
    } catch (e) {
      notify("autohunt 抓取失败", "无法读取当前页面内容，请刷新页面后重试。");
      return;
    }
    if (!collected || !collected.extracted) {
      notify("autohunt 抓取失败", "页面内容为空，请确认职位详情已加载完成。");
      return;
    }

    // 2. 读取 API key
    var stored = await chrome.storage.local.get("apiKey");
    var apiKey = (stored.apiKey || "").trim();
    if (!apiKey) {
      notify("autohunt 未配置 API key", "请先在扩展设置页粘贴 API key（Web 设置页 /#/settings 的「Agent 接入凭据」处生成）。");
      chrome.runtime.openOptionsPage();
      return;
    }

    // 3. 调用后端解析（只预览，绝不自动入库）
    var body = {
      url: tab.url,
      source: collected.source,
      request_id: newRequestId(),
      extracted: collected.extracted,
    };

    var controller = new AbortController();
    var timeout = setTimeout(function () {
      controller.abort();
    }, FETCH_TIMEOUT_MS);

    var resp;
    try {
      resp = await fetch(API_BASE + "/api/v1/jobs/crawl", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + apiKey,
          "X-Request-Id": body.request_id,
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (e) {
      if (e && e.name === "AbortError") {
        notify("autohunt 抓取超时", "解析超过 30 秒未完成，请重试或改用粘贴链接手动录入。");
      } else {
        notify("autohunt 无法连接后端", "请确认本地服务已启动（" + API_BASE + "）。");
      }
      return;
    } finally {
      clearTimeout(timeout);
    }

    if (resp.status === 401) {
      notify("autohunt API key 无效", "请在扩展设置页重新粘贴 API key（Web /#/settings 页生成）。");
      chrome.runtime.openOptionsPage();
      return;
    }
    if (resp.status === 429) {
      notify("autohunt 请求过于频繁", "限流 10 次/分钟，请稍候再试。");
      return;
    }
    if (!resp.ok) {
      notify("autohunt 抓取失败", "后端返回 HTTP " + resp.status + "，请稍后重试。");
      return;
    }

    var result = await resp.json();

    // 4. 按状态处理（CrawlStatus：ok/partial/unsupported_site/fetch_failed/parse_failed/timeout）
    if (result.status === "ok" || result.status === "partial") {
      openPreview(result);
      return;
    }
    if (result.status === "unsupported_site") {
      notify("autohunt 暂不支持该站点", "已为你保留链接，请在打开的手动录入页补全信息。");
      openManual(tab.url);
      return;
    }
    if (result.status === "timeout") {
      notify("autohunt 抓取超时", "目标页响应超时，可重试或手动录入。");
      return;
    }
    if (result.status === "fetch_failed") {
      // 反爬合规（BR-21）：不绕过，提示手动录入
      notify("autohunt 无法访问目标页", "站点拒绝了抓取（可能被反爬拦截），请手动录入。");
      return;
    }
    // parse_failed 及其他
    var msg = result.error_message ? "：" + result.error_message : "，请重试或手动录入。";
    if (result.error_code === "LLM_NOT_CONFIGURED") {
      msg = "：未配置 LLM，请先在 Web 设置页完成配置，或手动录入。";
    }
    notify("autohunt 解析失败", "职位字段解析失败" + msg);
  } finally {
    stopKeepAlive();
  }
}

chrome.action.onClicked.addListener(function (tab) {
  if (!tab || !tab.id || !/^https?:\/\//.test(tab.url || "")) {
    notify("autohunt 无法抓取", "请在职位详情页（BOSS 直聘 / 牛客 / 公司官网）点击本扩展。");
    return;
  }
  // 保持事件处理器 pending，配合 keepAlive 降低 SW 被回收概率（RISK-3）
  crawl(tab).catch(function () {
    notify("autohunt 抓取失败", "发生未知错误，请重试。");
  });
});
