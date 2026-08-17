"""
Daily Brief — Pipeline stage orchestration.

Contains the main() function and all per-phase logic. Re-imports from
daily_brief.context for shared state, from other internal modules for
production dependencies.
"""


import aiohttp
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo


from daily_brief.config import (
    ARTICLE_MAX_CONCURRENCY,
    CATEGORIES,
    CONFIG_YAML,
    DEFAULT_AGE_LIMIT_HOURS,
    FRONTMATTER_TAG_SEEDS,
    LLM_MODEL,
    LLM_SUMMARY_BATCH_SIZE,
    LLM_SUMMARY_MAX_CONCURRENCY,
    LOG_DIR,
    MAX_LOG_VERSIONS,
    NEWS_DIR,
    OLLAMA_HOST,
    PREFLIGHT_CHECKS_ENABLED,
    TIMEZONE,
    USER_AGENT,
    VERSION,
    WEATHER_LAT,
    WEATHER_LON,
    WEATHER_SECTION_TITLE,
)
from daily_brief.lifecycle import RunAllocator, RunReservation
from daily_brief.config_validator import validate_config
from daily_brief.llm import create_llm_client
from daily_brief.llm.summarizer import StoryPipelineState

from daily_brief.sources.weather import fetch_weather
from daily_brief.tagging import precompile_tagging
from daily_brief.validation import validate_report
from daily_brief.provenance import (
    resolve_git_commit_sha,
    resolve_git_committed_at,
    resolve_git_author_name,
    resolve_git_committer_name,
)
from daily_brief.pipeline.stages_core import (
    stage_extract as _stage_extract,
    stage_summarize as _stage_summarize,
    stage_render as _stage_render,
)
from daily_brief.pipeline.stages_validation import (
    stage_validate as _stage_validate,
    stage_validate_stories as _stage_validate_stories,
)
from daily_brief.pipeline.context import (
    ACTIVE_TIMEZONE,
    DEFAULT_CONTENT_AGE_WINDOW_HOURS,
    RunContext,
    _EventLoopLagMonitor,
    _count_extracted,
    _normalize_weather_for_rendering,
    _percentile,
    _setup_run_logger,
    _teardown_run_logger,
)


from daily_brief.pipeline import context as _run_ctx  # noqa: F401

# Exit codes
EXIT_CODE_SUCCESS = 0
EXIT_CODE_CONFIG = 1
EXIT_CODE_VALIDATION = 2

__all__ = [
    # Stages: main and stage logic
    "main",
    "stage_weather",
    "stage_rss",
    "stage_extract",
    "stage_summarize",
    "stage_render",
    "stage_validate",
    "_EventLoopLagMonitor",
    "_percentile",
    "_count_extracted",
    "_normalize_weather_for_rendering",
    # Context: shared state
    "ACTIVE_TIMEZONE",
    "DEFAULT_CONTENT_AGE_WINDOW_HOURS",
    "RunContext",
    "_setup_run_logger",
    "_teardown_run_logger",
    "_EventLoopLagMonitor",
    "_percentile",
    "_count_extracted",
]

# --- Test-patch resolution (late import to avoid circular imports) ---
# _EventLoopLagMonitor, _percentile, _count_extracted moved to context.py
# Because ``stages`` is loaded by ``__init__`` while the package is still
# being assembled, these helpers pull names from the package at runtime
# so that ``patch("daily_brief.pipeline.X", ...)`` takes effect.

def _pip(name: str):
    """Resolve *name* from ``daily_brief.pipeline`` at call time."""
    import daily_brief.pipeline as _p  # noqa: F811, local import

    return getattr(_p, name)


# --- Weather stage ----------------------------------------------------------


async def stage_weather(
    ctx: RunContext,
    session: aiohttp.ClientSession,
    log_fn: Callable[[str], None],
) -> Dict[str, Any]:
    """Fetch NWS weather data (Phase 1).

    Returns ``{"data": ..., "timing": ..., "error": ...}``.
    On success ``data`` is the weather dict; on failure ``error`` holds
    the exception message.  Timing is recorded into ``ctx.phase_timings``.
    """
    t1 = time.monotonic()
    log_fn("\n[Phase 1] Fetching NWS weather...")

    # Late-bind to preserve test-patch resolution
    _fw = _pip("fetch_weather")

    try:
        weather = await _fw(session, WEATHER_LAT, WEATHER_LON)
        if weather:
            station = weather.get("station", {})
            station_keys = (
                "avg_temp_today",
                "avg_monthly_rainfall",
                "current_monthly_rainfall",
            )
            station_partial = any(
                not station.get(k)
                or station[k] == "Unavailable"
                or "(fallback)" in str(station.get(k, ""))
                for k in station_keys
            )
            station_label = (
                "station (partial — fallback applied)"
                if station_partial
                else "station"
            )
            weather_errors = weather.get("errors", [])
            status = "PARTIAL" if (station_partial or weather_errors) else "OK"
            log_fn(
                f"  Weather {status} -- "
                f"{len(weather.get('forecast', []))} forecast periods | "
                f"1 {station_label} record | "
                f"{len(weather.get('lakes', {}))} lake sources"
            )
            if weather_errors:
                log_fn(
                    f"  Weather errors ({len(weather_errors)}): "
                    + "; ".join(weather_errors[:3])
                )
        else:
            log_fn("  Weather returned empty")
        elapsed = time.monotonic() - t1
        ctx.phase_timings["Phase 1"] = elapsed
        log_fn(f"  Phase 1 completed in {elapsed:.2f}s")
        return {"data": weather, "timing": elapsed, "error": None}
    except Exception as exc:
        elapsed = time.monotonic() - t1
        ctx.phase_timings["Phase 1"] = elapsed
        log_fn(f"  Weather error: {exc}")
        log_fn(f"  Phase 1 completed in {elapsed:.2f}s")
        return {"data": None, "timing": elapsed, "error": str(exc)}


# -- RSS dedup stage --------------------------------------------------------


async def stage_rss(
    ctx: RunContext,
    session: aiohttp.ClientSession,
    log_fn: Callable[[str], None],
) -> Tuple[List, Dict[str, Any]]:
    """Fetch and deduplicate RSS stories (Phase 2).

    Returns ``(deduped, stats)`` on success and ``([], {"error": ..., "total_after": 0})``
    on failure.  Timing is recorded into ``ctx.phase_timings["Phase 2"]``.
    """
    t2 = time.monotonic()

    # Late-bind to preserve test-patch resolution
    fetch_and_dedup = _pip("fetch_and_dedup")
    CATEGORIES = _pip("CATEGORIES")

    try:
        deduped, dedup_stats = await fetch_and_dedup(session, CATEGORIES, log_fn)
        elapsed = time.monotonic() - t2
        ctx.phase_timings["Phase 2"] = elapsed
        log_fn(f"  Phase 2 completed in {elapsed:.2f}s")
        return deduped, dedup_stats
    except Exception as exc:
        elapsed = time.monotonic() - t2
        ctx.phase_timings["Phase 2"] = elapsed
        log_fn(f"  RSS error: {exc}")
        log_fn(f"  Phase 2 completed in {elapsed:.2f}s")
        return [], {"error": str(exc), "total_after": 0}


# -- Main -------------------------------------------------------------------


async def main():
    # Test-patch context update (late binding — _set_current_run_context lives in __init__)
    import sys as _sys
    _pmod = _sys.modules.get("daily_brief.pipeline")
    if _pmod is not None:
        _set_current_run_context = _pmod._set_current_run_context
    else:
        from daily_brief.pipeline import _set_current_run_context as _set_current_run_context

    # ------------------------------------------------------------------
    # Resolve patchable names late so that ``patch("daily_brief.pipeline.*")``
    # applied by tests actually takes effect inside this function.
    # ------------------------------------------------------------------
    validate_config = _pip("validate_config")
    validate_report = _pip("validate_report")
    create_llm_client = _pip("create_llm_client")
    llm_batch_summarize_all = _pip("llm_batch_summarize_all")
    fetch_weather = _pip("fetch_weather")
    fetch_and_dedup = _pip("fetch_and_dedup")
    stage_extract_article = _pip("stage_extract_article")
    aiohttp = _pip("aiohttp")  # tests patch daily_brief.pipeline.aiohttp.ClientSession
    _normalize_weather_for_rendering = _pip("_normalize_weather_for_rendering")
    CATEGORIES = _pip("CATEGORIES")
    CATEGORY_PRIORITY = _pip("CATEGORY_PRIORITY")
    format_pub_date = _pip("format_pub_date")
    # Config dir/values that tests patch on the pipeline module
    LOG_DIR = _pip("LOG_DIR")
    NEWS_DIR = _pip("NEWS_DIR")
    PREFLIGHT_CHECKS_ENABLED = _pip("PREFLIGHT_CHECKS_ENABLED")

    # --- Config validation gate ---
    config_ok, config_issues = validate_config(CONFIG_YAML)
    if not config_ok:
        print(
            f"\nFATAL: {len(config_issues)} config validation error(s). Aborting.", file=sys.stderr
        )
        for ci in config_issues:
            print(f"CONFIG ERROR: {ci}", file=sys.stderr)
        return EXIT_CODE_CONFIG

    # --- Precompile tagging regexes ---
    n_kw = precompile_tagging()

    # --- Pre-flight connectivity checks (opt-in, warning only, never abort) ---
    if PREFLIGHT_CHECKS_ENABLED:
        from daily_brief.connectivity import format_results, run_all_checks

        conn_results = await run_all_checks(timeout=5.0)
        conn_output = format_results(conn_results)
        sys.stderr.write(conn_output + "\n")
        sys.stderr.flush()
    else:
        sys.stderr.write(
            "Connectivity preflight skipped (runtime.preflight_checks_enabled=false).\n"
        )
        sys.stderr.flush()

    # --- Per-run context (isolates mutable state) ---
    ctx = RunContext(article_max_concurrency=ARTICLE_MAX_CONCURRENCY)

    # Set context into task-local storage for test observation.
    _set_current_run_context = _pip("_set_current_run_context")
    _set_current_run_context(ctx)
    ctx.llm_client = _pip("create_llm_client")(
        LLM_MODEL, OLLAMA_HOST + "/v1" if "/v1" not in OLLAMA_HOST else OLLAMA_HOST, timeout=180
    )
    ctx.output_dir = ctx.output_dir or NEWS_DIR
    ctx.input_log_dir = LOG_DIR
    ctx.input_news_dir = NEWS_DIR

    # --- Collect Git provenance (optional, non-Git-safe) ---
    ctx.provenance = {
        k: v for k, v in {
            "git_commit": resolve_git_commit_sha(),
            "git_committed_at": resolve_git_committed_at(),
            "git_author_name": resolve_git_author_name(),
            "git_committer_name": resolve_git_committer_name(),
        }.items() if v
    }

    # --- Atomic run reservation ---
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    allocator = RunAllocator(LOG_DIR, NEWS_DIR, now_ts)
    reservation = allocator.reserve()
    ctx.reservation = reservation
    ctx.run_logfile = reservation.log_path
    log_ver = reservation.log_ver
    ctx.output_dir = reservation.report_dir

    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(NEWS_DIR, exist_ok=True)

    # --- Run-scoped logger (file + stderr, attached only for this run) ---
    lgr: Optional[logging.Logger] = _setup_run_logger(reservation.log_path)

    try:
        lgr.info("=" * 60)
        lgr.info(f"RUN LOG: {ctx.run_logfile}")
        lgr.info("DAILY BRIEF v" + VERSION + " - Pipeline Starting")
        lgr.info("=" * 60)

        run_started = time.monotonic()

        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=100, limit_per_host=30, ttl_dns_cache=300),
            headers={"User-Agent": USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as session:
            # Phase 1 + Phase 2: Concurrent weather + RSS
            weather_result: Dict[str, Any] = {"data": None, "timing": 0.0, "error": None}
            rss_result: Dict[str, Any] = {"deduped": [], "stats": {}, "timing": 0.0, "error": None}

            async def _phase1_weather():
                result = await stage_weather(ctx, session, lgr.info)
                weather_result["data"] = result["data"]
                weather_result["timing"] = result["timing"]
                weather_result["error"] = result["error"]

            async def _phase2_rss():
                deduped, dup_stats = await stage_rss(ctx, session, lgr.info)
                rss_result["deduped"] = deduped
                rss_result["stats"] = dup_stats

            await asyncio.gather(_phase1_weather(), _phase2_rss())

            weather = weather_result.get("data")
            deduped = rss_result["deduped"]
            dedup_stats = rss_result["stats"]
            total_after_dedup = dedup_stats.get("total_after", 0)

            # Phase 3A: Story construction + bounded article extraction
            lgr.info("  [3A] Constructing stories and fetching articles...")
            stories: List[StoryPipelineState] = []
            for title, link, snippet, pub_dt, cat in deduped:
                stories.append(StoryPipelineState(
                    title=title, link=link, snippet=snippet, pub_dt=pub_dt, category=cat
                ))
            stories = await stage_extract(stories, ctx, session, lgr.info)

            # Phase 3B/3C: Batch summarization
            lgr.info("\n[Phase 3] Summarizing articles...")
            stories = await stage_summarize(stories, ctx, lgr.info)

            # Phase 3D: Story validation
            passed, issues = stage_validate_stories(stories, ctx, lgr.info)
            if not passed:
                lgr.info(
                    f"  Validation: {len(issues)} issue(s) — proceeding with render "
                    f"({len(stories)} stories after summarization)"
                )

            lgr.info(
                f"\n  PROCESSING COMPLETE: {len(stories)} stories in {time.monotonic() - run_started:.2f}s (Phases 1-3)"
            )

            # Phase 4: Report rendering
            report_path = await stage_render(
                stories, weather, dedup_stats, ctx, log_ver, lgr.info
            )

            # Phase 5: Validation
            exit_code = await stage_validate(report_path, ctx, lgr.info, run_started)

            # Late-bound: inform test hooks about the final context
            _set_current_run_context(ctx)

            return exit_code

        print(f"\nNo stories to process — nothing to render.")
        return EXIT_CODE_SUCCESS
    finally:
        # Flush handlers before teardown so data reaches disk
        for h in lgr.handlers:
            try:
                h.flush()
            except Exception:
                pass
        _teardown_run_logger(lgr)



# Compatibility aliases from extracted stage modules.
# These preserve the module-level names so that tests can still
# patch("daily_brief.pipeline.stage_*") and have them resolve correctly.
stage_validate_stories = _stage_validate_stories
stage_validate = _stage_validate
stage_extract = _stage_extract
stage_summarize = _stage_summarize
stage_render = _stage_render
