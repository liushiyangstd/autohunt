/* autohunt 职位抓取 — 页面内容脚本（PROX-19 技设 §7.6 / §8.3）。
 *
 * 由 background.js 通过 chrome.scripting.executeScript 注入执行，
 * 脚本的求值结果（本文件末尾 IIFE 的返回值）作为提取结果回传，
 * 无需消息通道，也避免重复注入的监听器问题。
 *
 * 站点判定与 DOM 选择器与后端 apps/server/app/services/crawl_parser.py
 * 的 _parse_boss / _parse_nowcoder 保持一致（技设 §4.3）。
 */

(() => {
  "use strict";

  // ---- 与后端 crawl_parser.py 同口径的分类正则 ----
  var SALARY_RE = /\d+[Kk]?[-~]\d+(?:[Kk元])?/;
  var DEGREE_RE = /^(博士|硕士|MBA|本科|大专|学历不限)$/;
  var EXP_RE = /^(\d+[-~]\d+年|\d+年以上|经验不限|应届)$/;

  // 其他站点回传正文摘要的截断上限（字符）；后端 LLM 路径再按 8000 tokens 截断
  var CONTENT_MAX_CHARS = 20000;

  function pickText(selector) {
    var el = document.querySelector(selector);
    return el ? el.textContent.trim() || null : null;
  }

  /** BOSS 直聘：h1 + .salary + .company-info .name + .job-primary-detail + .job-sec-text */
  function extractBoss() {
    var title = pickText("h1");
    var salary = pickText(".salary");
    var company = pickText(".company-info .name") || pickText(".company-info");
    var info =
      pickText(".job-primary-detail") || pickText('p[class*="job-tag"]');
    var description =
      pickText(".job-sec-text") || pickText('div[class*="job-detail"]');

    var location = null;
    var degree = null;
    var experience = null;
    if (info) {
      info.split(/[·\s]+/).forEach(function (tok) {
        if (!tok) return;
        if (DEGREE_RE.test(tok)) degree = tok;
        else if (EXP_RE.test(tok)) experience = tok;
        else if (location === null) location = tok;
      });
    }

    return buildExtracted({
      title: title,
      company: company,
      location: location,
      salary: salary,
      description: description,
      requirements: { degree: degree, experience: experience, salary: salary },
    });
  }

  /** 牛客：.job-title + .job-company + .job-info(span 集合) + .job-content */
  function extractNowcoder() {
    var title = pickText(".job-title");
    var company = pickText(".job-company");
    var description = pickText(".job-content");

    var location = null;
    var degree = null;
    var salary = null;
    var infoEl = document.querySelector(".job-info");
    if (infoEl) {
      Array.prototype.forEach.call(infoEl.querySelectorAll("span"), function (sp) {
        var tok = sp.textContent.trim();
        if (!tok) return;
        if (SALARY_RE.test(tok)) salary = tok;
        else if (DEGREE_RE.test(tok)) degree = tok;
        else if (location === null) location = tok;
      });
    }

    return buildExtracted({
      title: title,
      company: company,
      location: location,
      salary: salary,
      description: description,
      requirements: { degree: degree, salary: salary },
    });
  }

  /** 只保留非空字段，匹配后端 CrawlExtracted schema */
  function buildExtracted(raw) {
    var extracted = {};
    ["title", "company", "location", "salary", "description"].forEach(function (k) {
      if (raw[k]) extracted[k] = raw[k];
    });
    var req = {};
    Object.keys(raw.requirements || {}).forEach(function (k) {
      if (raw.requirements[k]) req[k] = raw.requirements[k];
    });
    if (Object.keys(req).length > 0) extracted.requirements = req;
    return extracted;
  }

  /** 非适配站点：最小化回传 title + 正文可见文本摘要（LLM 兜底路径输入） */
  function extractGeneric() {
    var text = "";
    if (document.body && document.body.innerText) {
      text = document.body.innerText.replace(/[ \t]+/g, " ").trim();
    }
    if (text.length > CONTENT_MAX_CHARS) {
      text = text.slice(0, CONTENT_MAX_CHARS);
    }
    return { title: document.title || null, content: text || null };
  }

  var host = location.hostname;
  if (host === "www.zhipin.com" || host === "zhipin.com") {
    return { source: "boss", extracted: extractBoss() };
  }
  if (host === "www.nowcoder.com" || host === "nowcoder.com") {
    return { source: "nowcoder", extracted: extractNowcoder() };
  }
  // 无法可靠区分「公司官网」与「未知站点」，统一 unknown；后端 official/unknown 均走 LLM 兜底
  return { source: "unknown", extracted: extractGeneric() };
})();
