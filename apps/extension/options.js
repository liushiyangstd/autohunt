/* autohunt 抓取扩展 — 设置页：保存 API key 与后端地址到 chrome.storage.local（技设 §8.3） */

"use strict";

var input = document.getElementById("apiKey");
var apiBaseInput = document.getElementById("apiBase");
var statusEl = document.getElementById("status");
var saveBtn = document.getElementById("save");

// 与 background.js 保持一致的默认后端地址（本仓库事实标准：uvicorn 跑在 8080）
var DEFAULT_API_BASE = "http://localhost:8080";

// 载入已保存的配置
chrome.storage.local.get(["apiKey", "api_base"], function (stored) {
  if (stored.apiKey) input.value = stored.apiKey;
  apiBaseInput.value = stored.api_base || DEFAULT_API_BASE;
});

/** 校验后端地址：http/https + host（可带端口），去掉尾部斜杠；非法返回 null */
function normalizeApiBase(raw) {
  var value = (raw || "").trim().replace(/\/+$/, "");
  if (!value) return DEFAULT_API_BASE;
  if (!/^https?:\/\/[A-Za-z0-9._-]+(:\d{1,5})?(\/.*)?$/.test(value)) return null;
  return value;
}

function showStatus(color, text) {
  statusEl.style.color = color;
  statusEl.textContent = text;
}

saveBtn.addEventListener("click", function () {
  var key = input.value.trim();
  if (key && key.indexOf("ah_live_") !== 0) {
    showStatus("#dc2626", "格式不正确：API key 应以 ah_live_ 开头。");
    return;
  }
  var apiBase = normalizeApiBase(apiBaseInput.value);
  if (apiBase === null) {
    showStatus("#dc2626", "后端地址格式不正确：应为 http(s)://host:port，例如 http://localhost:8080。");
    return;
  }
  chrome.storage.local.set({ apiKey: key, api_base: apiBase }, function () {
    showStatus("#16a34a", "已保存。");
    setTimeout(function () {
      statusEl.textContent = "";
    }, 3000);
  });
});
