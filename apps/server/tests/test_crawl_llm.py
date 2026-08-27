"""crawl_llm 单测（PROX-19 技设 §4.3）：token 估算/截断、未配置降级、输出校验。

LLM 一律 mock，不打真实网络。
"""

import pytest

from app.services import crawl_llm
from app.services.llm_client import LLMConfig


def test_estimate_tokens_cjk_vs_latin():
    assert crawl_llm.estimate_tokens("你好世界") == 4
    assert crawl_llm.estimate_tokens("abcd" * 4) == 4


def test_truncate_to_tokens_marks_truncated():
    text = "岗" * (crawl_llm.MAX_INPUT_TOKENS + 100)
    out, truncated = crawl_llm.truncate_to_tokens(text)
    assert truncated is True
    assert crawl_llm.estimate_tokens(out) <= crawl_llm.MAX_INPUT_TOKENS


def test_truncate_to_tokens_short_text_untouched():
    out, truncated = crawl_llm.truncate_to_tokens("短文本")
    assert truncated is False
    assert out == "短文本"


def test_parse_with_llm_not_configured(tmp_path):
    from autohunt_domain.engine import make_engine
    from sqlmodel import Session

    with Session(make_engine(tmp_path / "t.db")) as session:
        with pytest.raises(crawl_llm.LLMNotConfigured):
            crawl_llm.parse_with_llm("职位文本", session)


def _fake_config() -> LLMConfig:
    return LLMConfig(
        enabled=True, provider="openai", base_url=None, model="gpt-4o-mini", api_key="sk-test"
    )


def test_parse_with_llm_success(monkeypatch, tmp_path):
    from autohunt_domain.engine import make_engine
    from sqlmodel import Session

    monkeypatch.setattr(crawl_llm, "load_config", lambda _session: _fake_config())
    captured: dict = {}

    def fake_call(text, config):
        captured["text"] = text
        return {
            "company": "示例科技",
            "title": "后端工程师",
            "location": "杭州",
            "deadline": "2026-09-01",
            "description": "负责后端服务",
            "requirements": {"degree": "本科", "salary": "20-30K"},
        }, 1234

    monkeypatch.setattr(crawl_llm, "call_llm_jd", fake_call)

    with Session(make_engine(tmp_path / "t.db")) as session:
        outcome = crawl_llm.parse_with_llm("职位文本", session)

    assert outcome.fields["company"] == "示例科技"
    assert outcome.fields["requirements"]["degree"] == "本科"
    # date-only 归一化为当天 23:59:59 UTC（技设 §3.3）
    assert outcome.fields["deadline"].hour == 23
    assert outcome.tokens_used == 1234
    assert outcome.content_truncated is False
    assert captured["text"] == "职位文本"


def test_parse_with_llm_truncates_long_input(monkeypatch, tmp_path):
    from autohunt_domain.engine import make_engine
    from sqlmodel import Session

    monkeypatch.setattr(crawl_llm, "load_config", lambda _session: _fake_config())
    captured: dict = {}

    def fake_call(text, config):
        captured["text"] = text
        return {"company": "示例科技", "title": "后端工程师"}, 8000

    monkeypatch.setattr(crawl_llm, "call_llm_jd", fake_call)

    long_text = "岗" * (crawl_llm.MAX_INPUT_TOKENS * 2)
    with Session(make_engine(tmp_path / "t.db")) as session:
        outcome = crawl_llm.parse_with_llm(long_text, session)

    assert outcome.content_truncated is True
    assert len(captured["text"]) < len(long_text)
    assert outcome.tokens_used == 8000


def test_call_llm_jd_sets_timeout(monkeypatch):
    """技设 §2.1：LLM 调用 15s 超时（+ 抓取 ≈ 30s 总预算），不得用 OpenAI 默认 600s。"""

    captured: dict = {}

    class _FakeCompletions:
        def create(self, **_kwargs):
            class _Msg:
                content = '{"company": "示例科技", "title": "后端"}'

            class _Choice:
                message = _Msg()

            class _Usage:
                total_tokens = 10

            class _Resp:
                choices = [_Choice()]
                usage = _Usage()

            return _Resp()

    class _FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = type("Chat", (), {"completions": _FakeCompletions()})()

    monkeypatch.setattr(crawl_llm, "OpenAI", _FakeClient)
    crawl_llm.call_llm_jd("职位文本", _fake_config())
    assert captured["timeout"] == crawl_llm.LLM_TIMEOUT_SECONDS


def test_coerce_fields_drops_bad_types():
    fields = crawl_llm._coerce_fields(
        {"company": 123, "title": "后端", "deadline": "尽快", "requirements": "本科"}
    )
    assert fields["company"] is None
    assert fields["title"] == "后端"
    assert fields["deadline"] is None
    assert fields["requirements"] is None
