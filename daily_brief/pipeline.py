"""
Daily Brief Pipeline Orchestration
The main() orchestrator — 6 phases: weather, RSS, LLM, render, validate, harness.
"""

import sys
import os
import re
import time
import threading
import asyncio
import aiohttp
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Callable, Dict, List, Optional
from daily_brief.lifecycle import RunAllocator, RunReservation

from daily_brief.config import (
    ARTICLE_MAX_CONCURRENCY,
    CATEGORIES,
    CONFIG_YAML,
    DEFAULT_AGE_LIMIT_HOURS,
    FRONTMATTER_TAG_SEEDS,
    LOG_DIR,
    LLM_MODEL,
    LLM_SUMMARY_BATCH_SIZE,
    LLM_SUMMARY_MAX_CONCURRENCY,
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
from daily_brief.sources.rss import format_pub_date
from daily_brief.sources.article import stage_extract_article
from daily_brief.sources.weather import fetch_weather
from daily_brief.categorization import ordered_categories_for_render


def _normalize_weather_for_rendering(weather_data) -> Optional[Dict]:
    """Normalize weather data for safe rendering. Handles None, scalars, missing keys."""
    if weather_data is None:
        return {
            "forecast": [
                {"date": "N/A", "day": "N/A", "night": "N/A", "high": "N/A", "low": "N/A", "precip": "N/A", "wind": "N/A"}
            ] * 3,
            "station": {},
            "lakes": {},
        }
    if not isinstance(weather_data, dict):
        return {
            "forecast": [
                {"date": "N/A", "day": "N/A", "night": "N/A", "high": "N/A", "low": "N/A", "precip": "N/A", "wind": "N/A"}
            ] * 3,
            "station": {},
            "lakes": {},
        }
    result = dict(weather_data)
    if "forecast" not in result or not isinstance(result.get("forecast"), list):
        result["forecast"] = [
            {"date": "N/A", "day": "N/A", "night": "N/A", "high": "N/A", "low": "N/A", "precip": "N/A", "wind": "N/A"}
        ] * 3
    if "station" not in result or not isinstance(result.get("station"), dict):
        result["station"] = {}
    if "lakes" not in result or not isinstance(result.get("lakes"), dict):
        result["lakes"] = {}
    return result
from daily_brief.pipelines.rss_dedup import fetch_and_dedup
from daily_brief.llm import create_llm_client
from daily_brief.llm.summarizer import (
    batch_summarize_all as llm_batch_summarize_all,
    StoryPipelineState,
)
from daily_brief.llm.summary_metrics import SummaryMetrics
from daily_brief.rendering import cleanup_old_files
from daily_brief.rendering.report import (
    build_sections_from_stories,
    build_markdown,
    compute_output_path,
    write_report,
)
from daily_brief.validation import validate_report
from daily_brief.harness import run_test_harness
from daily_brief.config_validator import validate_config
from daily_brief.tagging import precompile_tagging


@dataclass
class RunContext:
    """Per-run state — isolates mutable pipeline globals for concurrent safety."""
    log_lock: threading.Lock = field(default_factory=threading.Lock)
    phase_timings: Dict[str, float] = field(default_factory=dict)
    run_logfile: Optional[str] = None
    output_dir: Optional[str] = None
    input_log_dir: Optional[str] = None
    input_news_dir: Optional[str] = None
    article_max_concurrency: int = ARTICLE_MAX_CONCURRENCY
    llm_client: Any = None
    reservation: Optional[RunReservation] = None


def _log_ctx(ctx: RunContext, msg: str):
    """Log to file AND stderr. Thread-safe via per-run context lock."""
    if ctx.run_logfile is not None:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {msg}\n"
        os.makedirs(os.path.dirname(ctx.run_logfile), exist_ok=True)
        with ctx.log_lock:
            with open(ctx.run_logfile, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
    else:
        sys.stderr.write(f"{msg}\n")
        sys.stderr.flush()


# Module-level globals — backwards compatibility shim for test fixtures
RUN_LOGFILE = None
log_lock = threading.Lock()
PHASE_TIMINGS = {}
OUTPUT_DIR = None
_llm_client = None

try:
    ACTIVE_TIMEZONE = ZoneInfo(TIMEZONE)
except Exception:
    ACTIVE_TIMEZONE = timezone.utc
    TIMEZONE = "UTC"

DEFAULT_CONTENT_AGE_WINDOW_HOURS = 48


def log(msg):
    """Log to file AND stderr. Thread-safe via lock."""
    global RUN_LOGFILE
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    if RUN_LOGFILE is not None:
        os.makedirs(os.path.dirname(RUN_LOGFILE), exist_ok=True)
        with log_lock:
            with open(RUN_LOGFILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


def _coerce_temperature_f(val):
    """Safely convert temperature string/none to float and sanity check."""
    from daily_brief.utils import _coerce_temperature_f as _ct
    result = _ct(val)
    if result is not None and (result < -50 or result > 140):
        log(f"  WARNING: Extreme temperature detected and discarded: {result}°F")
        return None
    return result


# Exit codes
EXIT_CODE_SUCCESS = 0
EXIT_CODE_CONFIG = 1
EXIT_CODE_VALIDATION = 2
EXIT_CODE_HARNESS_ERROR = 3

# -- Main -------------------------------------------------------------------

async def main():
    # --- Config validation gate ---
    config_ok, config_issues = validate_config(CONFIG_YAML)
    if not config_ok:
        print(f"\nFATAL: {len(config_issues)} config validation error(s). Aborting.", file=sys.stderr)
        for ci in config_issues:
            print(f"CONFIG ERROR: {ci}", file=sys.stderr)
        return EXIT_CODE_CONFIG

    # --- Precompile tagging regexes ---
    n_kw = precompile_tagging()

    # --- Pre-flight connectivity checks (opt-in, warning only, never abort) ---
    if PREFLIGHT_CHECKS_ENABLED:
        from daily_brief.connectivity import run_all_checks, format_results
        conn_results = await run_all_checks(timeout=5.0)
        conn_output = format_results(conn_results)
        sys.stderr.write(conn_output + "\n")
        sys.stderr.flush()
    else:
        sys.stderr.write("Connectivity preflight skipped (runtime.preflight_checks_enabled=false).\n")
        sys.stderr.flush()

    # --- Per-run context (isolates mutable state) ---
    ctx = RunContext(article_max_concurrency=ARTICLE_MAX_CONCURRENCY)
    lgr: Callable[[str], None] = lambda msg: _log_ctx(ctx, msg)

    # Backwards-compat shim for test fixtures that inspect module globals
    global RUN_LOGFILE, PHASE_TIMINGS, OUTPUT_DIR, _llm_client
    RUN_LOGFILE = None
    PHASE_TIMINGS = ctx.phase_timings
    OUTPUT_DIR = NEWS_DIR
    _llm_client = create_llm_client(LLM_MODEL, OLLAMA_HOST + "/v1" if "/v1" not in OLLAMA_HOST else OLLAMA_HOST, timeout=180)
    ctx.llm_client = _llm_client
    ctx.output_dir = ctx.output_dir or NEWS_DIR
    ctx.input_log_dir = LOG_DIR
    ctx.input_news_dir = NEWS_DIR

    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(NEWS_DIR, exist_ok=True)

    # --- Atomic run reservation ---
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    allocator = RunAllocator(LOG_DIR, NEWS_DIR, now_ts)
    reservation = allocator.reserve()
    ctx.reservation = reservation
    ctx.run_logfile = reservation.log_path
    log_ver = reservation.log_ver
    RUN_LOGFILE = reservation.log_path
    OUTPUT_DIR = reservation.report_dir
    ctx.output_dir = reservation.report_dir

    lgr("=" * 60)
    lgr(f"RUN LOG: {ctx.run_logfile}")
    lgr("DAILY BRIEF v" + VERSION + " - Pipeline Starting")
    lgr("=" * 60)

    run_started = time.monotonic()

    now_ct = datetime.now(ACTIVE_TIMEZONE)
    cutoff = now_ct - timedelta(hours=DEFAULT_AGE_LIMIT_HOURS)

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=100, limit_per_host=30, ttl_dns_cache=300),
        headers={"User-Agent": USER_AGENT},
        timeout=aiohttp.ClientTimeout(total=30)
    ) as session:

        # ---------- Phase 1 + Phase 2: Concurrent weather + RSS ----------
        weather_result: Dict[str, Any] = {"data": None, "timing": 0.0, "error": None}
        rss_result: Dict[str, Any] = {"deduped": [], "stats": {}, "timing": 0.0, "error": None}

        async def _phase1_weather():
            t1 = time.monotonic()
            lgr("\n[Phase 1] Fetching NWS weather...")
            try:
                weather = await fetch_weather(session, WEATHER_LAT, WEATHER_LON)
                weather_result["data"] = weather
                if weather:
                    station = weather.get("station", {})
                    station_keys = ("avg_temp_today", "avg_monthly_rainfall", "current_monthly_rainfall")
                    station_partial = any(
                        not station.get(k) or station[k] == "Unavailable" or "(fallback)" in str(station.get(k, ""))
                        for k in station_keys
                    )
                    station_label = "station (partial — fallback applied)" if station_partial else "station"
                    weather_errors = weather.get("errors", [])
                    status = "PARTIAL" if (station_partial or weather_errors) else "OK"
                    lgr(
                        f"  Weather {status} -- "
                        f"{len(weather.get('forecast', []))} forecast periods | "
                        f"1 {station_label} record | "
                        f"{len(weather.get('lakes', {}))} lake sources"
                    )
                    if weather_errors:
                        lgr(f"  Weather errors ({len(weather_errors)}): " + "; ".join(weather_errors[:3]))
                else:
                    lgr("  Weather returned empty")
            except Exception as exc:
                weather_result["error"] = str(exc)
                lgr(f"  Weather error: {exc}")
            elapsed = time.monotonic() - t1
            weather_result["timing"] = elapsed
            ctx.phase_timings["Phase 1"] = elapsed
            lgr(f"  Phase 1 completed in {elapsed:.2f}s")

        async def _phase2_rss():
            t2 = time.monotonic()
            try:
                deduped, dedup_stats = await fetch_and_dedup(session, CATEGORIES, lgr)
                rss_result["deduped"] = deduped
                rss_result["stats"] = dedup_stats
            except Exception as exc:
                rss_result["error"] = str(exc)
                lgr(f"  RSS error: {exc}")
                rss_result["deduped"] = []
                rss_result["stats"] = {"total_after": 0}
            elapsed = time.monotonic() - t2
            rss_result["timing"] = elapsed
            ctx.phase_timings["Phase 2"] = elapsed
            lgr(f"  Phase 2 completed in {elapsed:.2f}s")

        await asyncio.gather(_phase1_weather(), _phase2_rss())

        weather = weather_result.get("data")
        deduped = rss_result["deduped"]
        dedup_stats = rss_result["stats"]
        total_after_dedup = dedup_stats.get("total_after", 0)

        # ---------- Phase 3: Summarization (single batch call) ----------
        lgr("\n[Phase 3] Enriching + summarizing...")
        t3 = time.monotonic()

        stories: List[StoryPipelineState] = []
        for title, link, snippet, pub_dt, cat in deduped:
            s = StoryPipelineState(title=title, link=link, snippet=snippet, pub_dt=pub_dt, category=cat)
            stories.append(s)

        total = len(stories)

        # ---------- Phase 3A: Bounded article fetching ----------
        lgr("  [3A] Fetching full articles from external sources...")
        sem_article = asyncio.Semaphore(ctx.article_max_concurrency)

        async def _bounded_extract(s: StoryPipelineState):
            async with sem_article:
                return await stage_extract_article(s, session)

        extract_results = await asyncio.gather(
            *[_bounded_extract(s) for s in stories],
            return_exceptions=True,
        )
        extract_errs = [r for r in extract_results if isinstance(r, Exception)]
        if extract_errs:
            lgr(f"  Article extraction errors ({len(extract_errs)}): " + "; ".join(str(e) for e in extract_errs[:5]))

        # ---------- Phase 3B/3C: Batch summary (recovery centralized in summarizer) ----------
        lgr(f"  [3BC] Running BATCH summaries via {LLM_MODEL}...")
        summary_metrics = await llm_batch_summarize_all(ctx.llm_client, stories, batch_size=LLM_SUMMARY_BATCH_SIZE, max_concurrency=LLM_SUMMARY_MAX_CONCURRENCY)
        if summary_metrics and isinstance(summary_metrics, SummaryMetrics):
            lgr(f"  Summaries: {summary_metrics.final_valid} valid / {summary_metrics.auto_fallbacks} [Auto] / {summary_metrics.unavailable_summaries} unavailable")
            if summary_metrics.batch_retries:
                lgr(f"  Batch retries: {summary_metrics.batch_retries} sub-batches retried")
            if summary_metrics.individual_recovery_attempts:
                lgr(f"  Recovery: {summary_metrics.individual_recovered}/{summary_metrics.individual_recovery_attempts} stories recovered individually")
            lgr(f"  Batch calls: {summary_metrics.batch_calls} sub-batches in {summary_metrics.elapsed_s:.1f}s")
        else:
            sum_ok = sum(1 for s in stories if s.summary and s.summary.strip())
            lgr(f"  Summaries: {sum_ok}/{total} with summaries")

        el3 = time.monotonic() - t3
        lgr(f"  Phase 3 completed in {el3:.2f}s")
        ctx.phase_timings["Phase 3"] = el3
        lgr(f"  Phase 3 LLM scheduler: batch_size={LLM_SUMMARY_BATCH_SIZE}, max_concurrency={LLM_SUMMARY_MAX_CONCURRENCY}")

        lgr(f"\n  PROCESSING COMPLETE: {total} stories in {time.monotonic() - run_started:.2f}s (Phases 1-3)")

        # ---------- Phase 4: Render report ----------
        lgr("\n[Phase 4] Rendering report...")
        t4 = time.monotonic()

        sections = build_sections_from_stories(stories, format_pub_date)
        filepath, file_ver = compute_output_path(ctx.output_dir, file_ver=log_ver)

        ordered_cats = ordered_categories_for_render([c[0] for c in CATEGORIES if c[1]])
        sections_map = {cn: sections.get(cn, []) for cn in ordered_cats}
        rendered_cat_count = sum(1 for cn in ordered_cats
            if cn != WEATHER_SECTION_TITLE and cn != "Weather Forecast 77316")

        safe_weather = _normalize_weather_for_rendering(weather)
        md = build_markdown(stories, safe_weather, sections_map, ordered_cats, {
            "total_after_dedup": total_after_dedup,
            "rendered_cat_count": rendered_cat_count,
            "DEFAULT_CONTENT_AGE_WINDOW_HOURS": DEFAULT_CONTENT_AGE_WINDOW_HOURS,
            "FRONTMATTER_TAG_SEEDS": FRONTMATTER_TAG_SEEDS,
            "WEATHER_SECTION_TITLE": WEATHER_SECTION_TITLE,
        })
        write_report(filepath, md)
        cleanup_old_files(ctx.output_dir, ctx.input_log_dir, MAX_LOG_VERSIONS)

        el4 = time.monotonic() - t4
        lgr(f"\nFile written to {filepath}")
        lgr(f"  Stories: {total_after_dedup} | Time: {el4:.1f}s")
        ctx.phase_timings["Phase 4"] = el4
        lgr(f"  Phase 4 completed in {el4:.2f}s")

        # --- Phase 5: Internal report validation ---
        lgr("\n[Phase 5] Validating report...")
        t5 = time.monotonic()
        validation_passed, validation_issues = validate_report(filepath)
        el5 = time.monotonic() - t5
        ctx.phase_timings["Phase 5"] = el5
        lgr(f"  Phase 5 completed in {el5:.2f}s")

        if not validation_passed:
            total_elapsed = time.monotonic() - run_started
            lgr(f"TOTAL PIPELINE TIME: {total_elapsed:.2f}s")
            lgr("\n*** RUN VALIDATION FAILED — Report has broken summaries ***")
            lgr(f"STATUS: FAILED ({len(validation_issues)} issues found)")
            print(f"\n*** RUN FAILED — {len(validation_issues)} validation issues found ***")
            print(f"File: {filepath}")
            print(f"Log: {ctx.run_logfile}")
            lgr("\n=== PIPELINE EXIT CODE: VALIDATION FAILURE ===")
            return EXIT_CODE_VALIDATION

        # --- Phase 6: External test harness validation ---
        lgr("\n[Phase 6] Running test harness...")
        t6 = time.monotonic()
        harness_result = run_test_harness(ctx.run_logfile)
        el6 = time.monotonic() - t6
        ctx.phase_timings["Phase 6"] = el6
        lgr(f"  Phase 6 completed in {el6:.2f}s")
        lgr(f"  Harness result: {harness_result.status} — {harness_result.message}")
        for line in harness_result.stdout_lines:
            lgr(f"  [Harness] {line}")
        for line in harness_result.stderr_lines:
            lgr(f"  [Harness err] {line}")
        total_elapsed = time.monotonic() - run_started
        lgr(f"TOTAL PIPELINE TIME: {total_elapsed:.2f}s")

        exit_code = {
            "PASS": EXIT_CODE_SUCCESS,
            "WARN": EXIT_CODE_CONFIG,
            "FAIL": EXIT_CODE_VALIDATION,
            "ERROR": EXIT_CODE_HARNESS_ERROR,
            "SKIPPED": EXIT_CODE_HARNESS_ERROR,
        }.get(harness_result.status, EXIT_CODE_HARNESS_ERROR)

        if exit_code == EXIT_CODE_SUCCESS:
            lgr("\n=== PIPELINE COMPLETED SUCCESSFULLY ===")
        else:
            lgr(f"\n=== PIPELINE EXIT CODE: {exit_code} ({harness_result.status}) ===")
        print(f"\nDone. File: {filepath}")
        print(f"  Stories: {total_after_dedup} | Time: {el4:.1f}s")
        return exit_code
