"""抓取编排器（PROX-19 技设 §4.2）：POST /jobs/crawl 的核心流程。

时序（技设 §4.2）：校验 → 限流 → 幂等缓存 → 建 crawl_attempt → 选策略解析 →
归一化/置信度 → 更新 crawl_attempt → 写缓存 → 返回 CrawlResult。

铁律：只解析预览，绝不写 job 表（BR：人工确认后才入库，AC-5）。
"""

from __future__ import annotations

import time

from sqlmodel import Session

from autohunt_domain.models import CrawlAttempt
from app.errors import ApiError
from app.schemas import (
    CrawlErrorCode,
    CrawlFieldConfidence,
    CrawlRequest,
    CrawlResult,
    CrawlResultFields,
    CrawlStatus,
    ErrorCode,
)
from app.services import crawl_fetcher, crawl_llm, crawl_parser
from app.services.crawl_cache import crawl_cache
from app.services.crawl_rate_limit import crawl_rate_limiter

# 结构化适配器已注册的 P0 站点（技设 §4.3 / 任务裁剪：只 boss + nowcoder）
_STRUCTURED_SOURCES = frozenset(crawl_parser.PARSERS)
# 走 LLM 兜底的来源
_LLM_SOURCES = frozenset({"official", "unknown"})

# 核心字段：用于 missing_fields 与 ok/partial 判定
_CORE_FIELDS = ("company", "title", "location", "deadline", "description")


def _rate_limited() -> ApiError:
    return ApiError(429, ErrorCode.RATE_LIMITED, "抓取频率超限（10 次/分钟），请稍后重试")


def _build_fields(parsed: dict, url: str, source: str) -> CrawlResultFields:
    """解析产出 → CrawlResultFields；jd_url 回填请求 URL，channel 回填 source（技设 §3.3）。"""

    return CrawlResultFields(
        company=parsed.get("company"),
        title=parsed.get("title"),
        jd_url=url,
        location=parsed.get("location"),
        channel=source,
        deadline=parsed.get("deadline"),
        description=parsed.get("description"),
        requirements=parsed.get("requirements"),
    )


def _finalize(result: CrawlResult, parsed: dict | None, strategy: str) -> None:
    """计算 missing_fields / status / confidence（结构化 high，LLM medium 起评）。"""

    if parsed is None:
        return
    missing = [f for f in _CORE_FIELDS if not parsed.get(f)]
    result.missing_fields = missing
    has_core = bool(parsed.get("company")) and bool(parsed.get("title"))
    if result.status == CrawlStatus.ok and missing:
        result.status = CrawlStatus.partial
    confidence = parsed.get("confidence")
    if confidence is None:
        if strategy == "structured":
            confidence = CrawlFieldConfidence.high if has_core else CrawlFieldConfidence.medium
        else:
            confidence = CrawlFieldConfidence.medium if has_core else CrawlFieldConfidence.low
    result.confidence = confidence
    if result.fields is not None:
        result.fields.confidence = confidence


def _execute(body: CrawlRequest, session: Session) -> tuple[CrawlResult, dict | None, str]:
    """按来源选择策略执行解析，返回 (result, parsed, strategy)；异常收敛为失败状态。"""

    source = body.source.value

    if source in _STRUCTURED_SOURCES:
        if body.extracted is not None:
            # 技设 §4.3：扩展已传 extracted 时只校验归一化，不再拉取页面
            parsed = crawl_parser.normalize_extracted(body.extracted)
            return CrawlResult(status=CrawlStatus.ok, request_id=body.request_id), parsed, "structured"
        try:
            html = crawl_fetcher.fetch_page(body.url)
            parsed = crawl_parser.parse_structured(source, body.url, html)
        except crawl_fetcher.FetchError as exc:
            status = CrawlStatus.timeout if exc.kind == "timeout" else CrawlStatus.fetch_failed
            return (
                CrawlResult(status=status, error_message=exc.message, request_id=body.request_id),
                None,
                "structured",
            )
        except crawl_parser.ParseError as exc:
            return (
                CrawlResult(
                    status=CrawlStatus.parse_failed, error_message=str(exc),
                    request_id=body.request_id,
                ),
                None,
                "structured",
            )
        return CrawlResult(status=CrawlStatus.ok, request_id=body.request_id), parsed, "structured"

    if source in _LLM_SOURCES:
        try:
            if body.extracted is not None and body.extracted.content:
                text = body.extracted.content
            else:
                text = crawl_fetcher.html_to_text(crawl_fetcher.fetch_page(body.url))
        except crawl_fetcher.FetchError as exc:
            status = CrawlStatus.timeout if exc.kind == "timeout" else CrawlStatus.fetch_failed
            return (
                CrawlResult(status=status, error_message=exc.message, request_id=body.request_id),
                None,
                "llm",
            )
        try:
            outcome = crawl_llm.parse_with_llm(text, session)
        except crawl_llm.LLMNotConfigured as exc:
            return (
                CrawlResult(
                    status=CrawlStatus.parse_failed,
                    error_code=CrawlErrorCode.LLM_NOT_CONFIGURED,
                    error_message=str(exc),
                    request_id=body.request_id,
                ),
                None,
                "llm",
            )
        except Exception as exc:  # noqa: BLE001 — LLM 调用/JSON/校验失败统一 parse_failed（RISK-4）
            return (
                CrawlResult(
                    status=CrawlStatus.parse_failed, error_message=str(exc),
                    request_id=body.request_id,
                ),
                None,
                "llm",
            )
        parsed = dict(outcome.fields)
        # 扩展若同时预提取了标题/公司，优先用扩展值补齐（结构化优先于 LLM 幻觉，RISK-4）
        if body.extracted is not None:
            parsed["company"] = parsed["company"] or body.extracted.company
            parsed["title"] = parsed["title"] or body.extracted.title
        result = CrawlResult(
            status=CrawlStatus.ok,
            content_truncated=outcome.content_truncated,
            tokens_used=outcome.tokens_used,
            request_id=body.request_id,
        )
        return result, parsed, "llm"

    # liepin/shixiseng 等未注册适配器站点（任务裁剪：AC-3）
    return (
        CrawlResult(
            status=CrawlStatus.unsupported_site,
            error_message=f"暂不支持自动解析站点：{source}，请手动录入",
            request_id=body.request_id,
        ),
        None,
        "none",
    )


def crawl_job(body: CrawlRequest, caller: str, session: Session) -> CrawlResult:
    """编排入口（技设 §4.2）。429 限流走信封；其余失败收敛进 CrawlResult.status。"""

    # 步骤 2：限流（10/min/caller，技设 §6）
    if not crawl_rate_limiter.check(caller):
        raise _rate_limited()

    # 步骤 3：幂等缓存（30s，键 {caller}:{request_id}，技设 §5.3）
    cache_key = f"{caller}:{body.request_id}"
    cached = crawl_cache.get(cache_key)
    if cached is not None:
        return CrawlResult(**cached)

    started = time.monotonic()

    result, parsed, strategy = _execute(body, session)
    if parsed is not None:
        # 结构化/LLM 均未得到公司与岗位名 → 视为解析失败（用户走手动录入）
        if not parsed.get("company") and not parsed.get("title"):
            result.status = CrawlStatus.parse_failed
            result.error_message = "未解析到公司或岗位名，请手动录入"
            parsed = None
        else:
            result.fields = _build_fields(parsed, body.url, body.source.value)
    _finalize(result, parsed, strategy)

    # 步骤 4/8：落 crawl_attempt 审计（技设 §3.2；job_id 预览期为空，保存后由写侧关联）
    attempt = CrawlAttempt(
        url=body.url,
        source=body.source.value,
        request_id=body.request_id,
        caller=caller,
        status=result.status.value,
        strategy=strategy,
        fields_snapshot=result.fields.model_dump(mode="json") if result.fields else None,
        missing_fields=result.missing_fields,
        error_code=result.error_code.value if result.error_code else None,
        error_message=result.error_message,
        content_truncated=result.content_truncated,
        tokens_used=result.tokens_used,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    session.add(attempt)
    session.commit()

    # 步骤 9：写 30s 幂等缓存（含失败结果，避免重试放大反爬/LLM 成本）
    crawl_cache.set(cache_key, result.model_dump(mode="json"))
    return result
