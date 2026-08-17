"""
Daily Brief — Core pipeline stages: extract, summarize, render.

Extracted from ``stages.py`` to stay under the 500-line cap.

Each function uses ``_pip()`` late-resolution for test-patch
compatibility.  Alias names are re-exported from ``stages.py`` for
backwards-compatible patching by tests.
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Tuple

import aiohttp

from daily_brief.llm.summarizer import (
    StoryPipelineState,
    batch_summarize_all as llm_batch_summarize_all,
)
from daily_brief.llm.summary_metrics import SummaryMetrics
from daily_brief.pipeline.context import (
    RunContext,
    _EventLoopLagMonitor,
    _count_extracted,
    _normalize_weather_for_rendering,
    _percentile,
)
from daily_brief.pipelines.rss_dedup import fetch_and_dedup
from daily_brief.rendering import cleanup_old_files
# Stage extract and compute output path resolved via _pip() for test-patch compatibility
from daily_brief.sources.rss import format_pub_date
from daily_brief.categorization import ordered_categories_for_render
from daily_brief.rendering.report import build_markdown, build_sections_from_stories

logger = logging.getLogger(__name__)


def _pip(name: str):
    """Resolve *name* from ``daily_brief.pipeline`` at call time."""
    import daily_brief.pipeline as _p  # noqa: F811, local import

    return getattr(_p, name)


# ---------------------------------------------------------------------------
# Phase 3A – Article extraction
# ---------------------------------------------------------------------------


async def stage_extract(
    stories: List[StoryPipelineState],
    ctx: RunContext,
    session: aiohttp.ClientSession,
    log_fn: Callable[[str], None],
) -> List[StoryPipelineState]:
    """Bounded article extraction (Phase 3A)."""
    sem_article = asyncio.Semaphore(ctx.article_max_concurrency)

    total = len(stories)
    if not stories:
        ctx.phase_timings["Phase 3A"] = 0.0
        log_fn("  Extraction: 0 stories")
        return stories

    log_fn("  [3A] Fetching full articles from external sources...")

    async def _bounded_extract(s: StoryPipelineState) -> StoryPipelineState:
        extract_stg = _pip("stage_extract_article")
        async with sem_article:
            return await extract_stg(s, session)

    t3a = time.monotonic()
    looplag = _EventLoopLagMonitor(interval_s=0.02)
    looplag.start()
    extract_results = await asyncio.gather(
        *[_bounded_extract(s) for s in stories], return_exceptions=True
    )
    lag_samples = await looplag.stop_async()
    el3a = time.monotonic() - t3a
    ctx.phase_timings["Phase 3A"] = el3a
    extracted_count = _count_extracted(stories)
    throughput = total / el3a if el3a > 0 else 0
    log_fn(
        f"  Extraction: {total} in {el3a:.2f}s ({throughput:.1f} stories/s, {extracted_count} contexts)"
    )
    if lag_samples:
        p50 = _percentile(lag_samples, 50)
        p95 = _percentile(lag_samples, 95)
        p99 = _percentile(lag_samples, 99)
        log_fn(
            f"  Loop lag: p50={p50*1000:.1f}ms p95={p95*1000:.1f}ms "
            f"p99={p99*1000:.1f}ms max={max(lag_samples)*1000:.1f}ms ({len(lag_samples)} samples)"
        )

    extract_errs = [r for r in extract_results if isinstance(r, Exception)]
    if extract_errs:
        log_fn(
            f"  Article extraction errors ({len(extract_errs)}): "
            + "; ".join(str(e) for e in extract_errs[:5])
        )
    return stories


# ---------------------------------------------------------------------------
# Phase 3B/3C – Batch summarization
# ---------------------------------------------------------------------------


async def stage_summarize(
    stories: List[StoryPipelineState],
    ctx: RunContext,
    log_fn: Callable[[str], None],
) -> List[StoryPipelineState]:
    """Batch LLM summarization (Phase 3B/3C)."""
    LLM_MODEL = _pip("LLM_MODEL")
    LLM_SUMMARY_BATCH_SIZE = _pip("LLM_SUMMARY_BATCH_SIZE")
    LLM_SUMMARY_MAX_CONCURRENCY = _pip("LLM_SUMMARY_MAX_CONCURRENCY")

    t3 = time.monotonic()
    total = len(stories)
    log_fn(f"  [3BC] Running BATCH summaries via {LLM_MODEL}...")

    summary_metrics = await llm_batch_summarize_all(
        ctx.llm_client,
        stories,
        batch_size=LLM_SUMMARY_BATCH_SIZE,
        max_concurrency=LLM_SUMMARY_MAX_CONCURRENCY,
    )
    if summary_metrics and isinstance(summary_metrics, SummaryMetrics):
        log_fn(
            f"  Summaries: {summary_metrics.final_valid} valid / "
            f"{summary_metrics.auto_fallbacks} [Auto] / "
            f"{summary_metrics.unavailable_summaries} unavailable"
        )
        if summary_metrics.batch_retries:
            log_fn(f"  Batch retries: {summary_metrics.batch_retries}")
        if summary_metrics.individual_recovery_attempts:
            log_fn(
                f"  Recovery: {summary_metrics.individual_recovered}/"
                f"{summary_metrics.individual_recovery_attempts} recovered individually"
            )
        log_fn(
            f"  Batch calls: {summary_metrics.batch_calls} in {summary_metrics.elapsed_s:.1f}s"
        )
    else:
        sum_ok = sum(1 for s in stories if s.summary and s.summary.strip())
        log_fn(f"  Summaries: {sum_ok}/{total} with summaries")

    el3 = time.monotonic() - t3
    ctx.phase_timings["Phase 3"] = el3
    log_fn(f"  Phase 3 completed in {el3:.2f}s")
    log_fn(
        f"  Phase 3 LLM scheduler: batch_size={LLM_SUMMARY_BATCH_SIZE}, "
        f"max_concurrency={LLM_SUMMARY_MAX_CONCURRENCY}"
    )
    return stories


# ---------------------------------------------------------------------------
# Phase 4 – Report rendering
# ---------------------------------------------------------------------------


async def stage_render(
    stories: List[StoryPipelineState],
    weather: Dict[str, Any],
    dedup_stats: Dict[str, Any],
    ctx: RunContext,
    log_ver: int,
    log_fn: Callable[[str], None],
) -> str:
    """Render Markdown report and write to disk (Phase 4)."""
    CATEGORIES = _pip("CATEGORIES")
    MAX_LOG_VERSIONS = _pip("MAX_LOG_VERSIONS")
    DEFAULT_CONTENT_AGE_WINDOW_HOURS = _pip("DEFAULT_CONTENT_AGE_WINDOW_HOURS")
    WEATHER_SECTION_TITLE = _pip("WEATHER_SECTION_TITLE")
    FRONTMATTER_TAG_SEEDS = _pip("FRONTMATTER_TAG_SEEDS")

    t4 = time.monotonic()
    cleanup_old_files(ctx.output_dir, MAX_LOG_VERSIONS, "md")

    sections = build_sections_from_stories(stories, format_pub_date)
    copt = _pip("compute_output_path")
    filepath, file_ver = copt(ctx.output_dir, file_ver=log_ver)

    ordered_cats = ordered_categories_for_render([c[0] for c in CATEGORIES if c[1]])
    sections_map = {cn: sections.get(cn, []) for cn in ordered_cats}
    rendered_cat_count = sum(
        1 for cn in ordered_cats if cn not in ("Weather", "Weather Forecast 77316")
    ) if ordered_cats else 0

    safe_weather = weather if weather is None else _normalize_weather_for_rendering(weather)
    md = build_markdown(
        stories, safe_weather, sections_map, ordered_cats,
        {
            "total_after_dedup": dedup_stats.get("total_after", 0),
            "rendered_cat_count": rendered_cat_count,
            "DEFAULT_CONTENT_AGE_WINDOW_HOURS": DEFAULT_CONTENT_AGE_WINDOW_HOURS,
            "FRONTMATTER_TAG_SEEDS": FRONTMATTER_TAG_SEEDS,
            "WEATHER_SECTION_TITLE": WEATHER_SECTION_TITLE,
        },
        git_provenance=ctx.provenance,
    )
    _pip("write_report")(filepath, md)
    cleanup_old_files(ctx.output_dir, ctx.input_log_dir, MAX_LOG_VERSIONS)

    el4 = time.monotonic() - t4
    log_fn(f"\nFile written to {filepath}")
    log_fn(f"  Stories: {dedup_stats.get('total_after', 0)} | Time: {el4:.1f}s")
    ctx.phase_timings["Phase 4"] = el4
    log_fn(f"  Phase 4 completed in {el4:.2f}s")
    return filepath
