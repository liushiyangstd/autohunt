/* autohunt 抓取扩展 — 设置页：保存 API key 到 chrome.storage.local（技设 §8.3） */

"use strict";

var input = document.getElementById("apiKey");
var statusEl = document.getElementById("status");
var saveBtn = document.getElementById("save");

// 载入已保存的 key
chrome.storage.local.get("apiKey", function (stored) {
  if (stored.apiKey) input.value = stored.apiKey;
});

saveBtn.addEventListener("click", function () {
  var key = input.value.trim();
  if (key && key.indexOf("ah_live_") !== 0) {
    statusEl.style.color = "#dc2626";
    statusEl.textContent = "格式不正确：API key 应以 ah_live_ 开头。";
    return;
  }
  chrome.storage.local.set({ apiKey: key }, function () {
    statusEl.style.color = "#16a34a";
    statusEl.textContent = key ? "已保存。" : "已清空。";
    setTimeout(function () {
      statusEl.textContent = "";
    }, 3000);
  });
});
