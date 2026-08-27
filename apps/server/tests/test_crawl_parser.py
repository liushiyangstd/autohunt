"""crawl_parser 单测（PROX-19 技设 §4.3）：BOSS/牛客 fixture HTML + extracted 归一化。"""

from datetime import datetime, timezone

import pytest

from app.schemas import CrawlExtracted
from app.services.crawl_fetcher import html_to_text
from app.services.crawl_parser import (
    ParseError,
    normalize_deadline,
    normalize_extracted,
    parse_structured,
)

BOSS_HTML = """
<html><head><title>高级后端开发工程师招聘</title></head><body>
<div class="job-banner">
  <div class="job-primary">
    <div class="name"><h1>高级后端开发工程师</h1><span class="salary">25-40K·14薪</span></div>
    <p class="job-primary-detail">北京·朝阳区·望京 5-10年 本科</p>
  </div>
</div>
<div class="company-info"><span class="name">字节跳动</span></div>
<div class="job-sec"><div class="job-sec-text">负责后端服务开发与架构设计，参与核心系统建设。</div></div>
</body></html>
"""

NOWCODER_HTML = """
<html><body>
<div class="nc-job-detail">
  <h1 class="job-title">前端开发实习生</h1>
  <div class="job-company">美团</div>
  <div class="job-info"><span>上海</span><span>本科</span><span>3k-4k</span></div>
  <div class="job-content">参与前端页面开发与组件库维护。</div>
</div>
</body></html>
"""


def test_parse_boss():
    fields = parse_structured("boss", "https://www.zhipin.com/job_detail/abc.html", BOSS_HTML)
    assert fields["title"] == "高级后端开发工程师"
    assert fields["company"] == "字节跳动"
    assert fields["location"] == "北京"
    assert fields["description"] == "负责后端服务开发与架构设计，参与核心系统建设。"
    assert fields["requirements"]["salary"] == "25-40K·14薪"
    assert fields["requirements"]["degree"] == "本科"
    assert fields["requirements"]["experience"] == "5-10年"


def test_parse_nowcoder():
    fields = parse_structured("nowcoder", "https://www.nowcoder.com/jobs/123", NOWCODER_HTML)
    assert fields["title"] == "前端开发实习生"
    assert fields["company"] == "美团"
    assert fields["location"] == "上海"
    assert fields["description"] == "参与前端页面开发与组件库维护。"
    assert fields["requirements"]["degree"] == "本科"
    assert fields["requirements"]["salary"] == "3k-4k"


def test_unregistered_source_raises():
    with pytest.raises(ParseError):
        parse_structured("liepin", "https://www.liepin.com/job/1", "<html></html>")


def test_empty_result_raises():
    with pytest.raises(ParseError):
        parse_structured("boss", "https://www.zhipin.com/x", "<html><body></body></html>")


def test_normalize_deadline_date_only():
    dt = normalize_deadline("2026-09-01")
    assert dt == datetime(2026, 9, 1, 23, 59, 59, tzinfo=timezone.utc)


def test_normalize_deadline_rfc3339_passthrough():
    dt = normalize_deadline("2026-09-01T10:00:00+08:00")
    assert dt == datetime(2026, 9, 1, 2, 0, 0, tzinfo=timezone.utc)


def test_normalize_deadline_invalid():
    assert normalize_deadline("尽快") is None
    assert normalize_deadline(None) is None


def test_normalize_extracted_merges_salary():
    extracted = CrawlExtracted(
        company=" 字节跳动 ", title="后端开发", deadline="2026-09-01", salary="25-40K"
    )
    fields = normalize_extracted(extracted)
    assert fields["company"] == "字节跳动"
    assert fields["requirements"]["salary"] == "25-40K"
    assert fields["deadline"].hour == 23


def test_html_to_text_strips_script_and_style():
    html = "<html><head><style>.a{color:red}</style><script>var x=1;</script></head><body><p>你好</p></body></html>"
    text = html_to_text(html)
    assert "你好" in text
    assert "var x" not in text
    assert "color" not in text
