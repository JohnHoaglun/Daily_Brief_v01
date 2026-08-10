"""
Daily Brief v1.0.143 — Pipeline Orchestration
The main() orchestrator — 6 phases: weather, RSS, LLM, render, validate, harness.
"""

import sys
import os
import re
import time
import asyncio
import logging
import aiohttp
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional
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


class _EventLoopLagMonitor:
    """Lightweight event-loop lag monitor.

    Records actual scheduling delays while running. Measures the difference
    between a scheduled deadline and the actual wake-up time at each tick.
    """

    def __init__(self, interval_s: float):
        self._interval = interval_s
        self._samples: list[float] = []
        self._task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None

    def start(self):
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._samples = []
        self._task = asyncio.create_task(self._run())

    def stop(self) -> list[float]:
        """Signal stop (synchronous — caller should schedule task cleanup)."""
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
        return list(self._samples)

    async def stop_async(self) -> list[float]:
        """Signal stop and await task completion."""
        self.stop()
        if self._task is not None and not self._task.done():
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        return list(self._samples)

    async def _run(self):
        while not self._stop_event.is_set():
            deadline = time.monotonic() + self._interval
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval)
                return
            except asyncio.TimeoutError:
                pass
            elapsed = time.monotonic() - deadline
            self._samples.append(max(0, elapsed))


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Calculate the given percentile from sorted values."""
    if not sorted_values:
        return 0.0
    sorted_v = sorted(sorted_values)
    idx = (pct / 100) * (len(sorted_v) - 1)
    lower = int(idx)
    upper = min(lower + 1, len(sorted_v) - 1)
    frac = idx - lower
    return sorted_v[lower] + (sorted_v[upper] - sorted_v[lower]) * frac


def _count_extracted(stories: list[Any]) -> int:
    """Count stories that have populated context from extraction."""
    return sum(1 for s in stories if getattr(s, "context", None))


@dataclass
class RunContext:
    """Per-run state — isolates mutable pipeline globals for concurrent safety."""
    phase_timings: Dict[str, float] = field(default_factory=dict)
    run_logfile: Optional[str] = None
    output_dir: Optional[str] = None
    input_log_dir: Optional[str] = None
    input_news_dir: Optional[str] = None
    article_max_concurrency: int = ARTICLE_MAX_CONCURRENCY
    llm_client: Any = None
    reservation: Optional[RunReservation] = None


class _RunTimestampFormatter(logging.Formatter):
    """Emits [YYYY-MM-DD HH:MM:SS] msg — same format as legacy _log_ctx."""

    def formatTime(self, record, datefmt=None):
        return datetime.utcfromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")

    def format(self, record):
        return f"[{self.formatTime(record)}] {record.getMessage()}"


def _setup_run_logger(logfile: str, name: str = "daily_brief") -> logging.Logger:
    """Create a dedicated logger with file + stderr handlers for one run.

    Handlers must be removed with `_teardown_run_logger` to prevent
    cross-run contamination during concurrent invocations.
    """
    logger = logging.getLogger(f"{name}_{id(logfile)}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False
    formatter = _RunTimestampFormatter()
    os.makedirs(os.path.dirname(logfile), exist_ok=True)
    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(formatter)
    logger.addHandler(sh)
    return logger


def _teardown_run_logger(logger: logging.Logger) -> None:
    """Close and remove all handlers from a run-scoped logger."""
    for h in list(logger.handlers):
        try:
            h.close()
        except Exception:
            pass
    logger.handlers.clear()


# Module-level globals — backwards compatibility shim for test fixtures
RUN_LOGFILE = None
PHASE_TIMINGS: Dict[str, float] = {}
OUTPUT_DIR = None
_llm_client = None

try:
    ACTIVE_TIMEZONE = ZoneInfo(TIMEZONE)
except Exception:
    ACTIVE_TIMEZONE = timezone.utc
    TIMEZONE = "UTC"

DEFAULT_CONTENT_AGE_WINDOW_HOURS = 48


def _coerce_temperature_f(val):
    """Safely convert temperature string/none to float and sanity check."""
    from daily_brief.utils import _coerce_temperature_f as _ct
    result = _ct(val)
    if result is not None and (result < -50 or result > 140):
        sys.stderr.write(f"  WARNING: Extreme temperature detected and discarded: {result}°F\n")
        sys.stderr.flush()
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

    # --- Run-scoped logger (file + stderr, attached only for this run) ---
    lgr: Optional[logging.Logger] = _setup_run_logger(reservation.log_path)

    try:
        lgr.info("=" * 60)
        lgr.info(f"RUN LOG: {ctx.run_logfile}")
        lgr.info("DAILY BRIEF v" + VERSION + " - Pipeline Starting")
        lgr.info("=" * 60)

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
                lgr.info("\n[Phase 1] Fetching NWS weather...")
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
                        lgr.info(
                            f"  Weather {status} -- "
                            f"{len(weather.get('forecast', []))} forecast periods | "
                            f"1 {station_label} record | "
                            f"{len(weather.get('lakes', {}))} lake sources"
                        )
                        if weather_errors:
                            lgr.info(f"  Weather errors ({len(weather_errors)}): " + "; ".join(weather_errors[:3]))
                    else:
                        lgr.info("  Weather returned empty")
                except Exception as exc:
                    weather_result["error"] = str(exc)
                    lgr.info(f"  Weather error: {exc}")
                elapsed = time.monotonic() - t1
                weather_result["timing"] = elapsed
                ctx.phase_timings["Phase 1"] = elapsed
                lgr.info(f"  Phase 1 completed in {elapsed:.2f}s")

            async def _phase2_rss():
                t2 = time.monotonic()
                try:
                    deduped, dedup_stats = await fetch_and_dedup(session, CATEGORIES, lgr.info)
                    rss_result["deduped"] = deduped
                    rss_result["stats"] = dedup_stats
                except Exception as exc:
                    rss_result["error"] = str(exc)
                    lgr.info(f"  RSS error: {exc}")
                    rss_result["deduped"] = []
                    rss_result["stats"] = {"total_after": 0}
                elapsed = time.monotonic() - t2
                rss_result["timing"] = elapsed
                ctx.phase_timings["Phase 2"] = elapsed
                lgr.info(f"  Phase 2 completed in {elapsed:.2f}s")

            await asyncio.gather(_phase1_weather(), _phase2_rss())

            weather = weather_result.get("data")
            deduped = rss_result["deduped"]
            dedup_stats = rss_result["stats"]
            total_after_dedup = dedup_stats.get("total_after", 0)

            # ---------- Phase 3: Summarization (single batch call) ----------
            lgr.info("\n[Phase 3] Enriching + summarizing...")
            t3 = time.monotonic()

            stories: List[StoryPipelineState] = []
            for title, link, snippet, pub_dt, cat in deduped:
                s = StoryPipelineState(title=title, link=link, snippet=snippet, pub_dt=pub_dt, category=cat)
                stories.append(s)

            total = len(stories)

            # ---------- Phase 3A: Bounded article fetching ----------
            lgr.info("  [3A] Fetching full articles from external sources...")
            sem_article = asyncio.Semaphore(ctx.article_max_concurrency)

            async def _bounded_extract(s: StoryPipelineState):
                async with sem_article:
                    return await stage_extract_article(s, session)

            t3a = time.monotonic()
            looplag = _EventLoopLagMonitor(interval_s=0.02)
            looplag.start()
            extract_results = await asyncio.gather(
                *[_bounded_extract(s) for s in stories],
                return_exceptions=True,
            )
            lag_samples = await looplag.stop_async()
            el3a = time.monotonic() - t3a
            ctx.phase_timings["Phase 3A"] = el3a
            extracted_count = _count_extracted(stories)
            throughput = total / el3a if el3a > 0 else 0
            lgr.info(f"  Extraction: {total} in {el3a:.2f}s ({throughput:.1f} stories/s, {extracted_count} contexts)")
            if lag_samples:
                p50 = _percentile(lag_samples, 50)
                p95 = _percentile(lag_samples, 95)
                p99 = _percentile(lag_samples, 99)
                lgr.info(f"  Loop lag during extraction: p50={p50*1000:.1f}ms p95={p95*1000:.1f}ms p99={p99*1000:.1f}ms max={max(lag_samples)*1000:.1f}ms ({len(lag_samples)} samples)")

            extract_errs = [r for r in extract_results if isinstance(r, Exception)]
            if extract_errs:
                lgr.info(f"  Article extraction errors ({len(extract_errs)}): " + "; ".join(str(e) for e in extract_errs[:5]))

            # ---------- Phase 3B/3C: Batch summary (recovery centralized in summarizer) ----------
            lgr.info(f"  [3BC] Running BATCH summaries via {LLM_MODEL}...")
            summary_metrics = await llm_batch_summarize_all(ctx.llm_client, stories, batch_size=LLM_SUMMARY_BATCH_SIZE, max_concurrency=LLM_SUMMARY_MAX_CONCURRENCY)
            if summary_metrics and isinstance(summary_metrics, SummaryMetrics):
                lgr.info(f"  Summaries: {summary_metrics.final_valid} valid / {summary_metrics.auto_fallbacks} [Auto] / {summary_metrics.unavailable_summaries} unavailable")
                if summary_metrics.batch_retries:
                    lgr.info(f"  Batch retries: {summary_metrics.batch_retries} sub-batches retried")
                if summary_metrics.individual_recovery_attempts:
                    lgr.info(f"  Recovery: {summary_metrics.individual_recovered}/{summary_metrics.individual_recovery_attempts} stories recovered individually")
                lgr.info(f"  Batch calls: {summary_metrics.batch_calls} sub-batches in {summary_metrics.elapsed_s:.1f}s")
            else:
                sum_ok = sum(1 for s in stories if s.summary and s.summary.strip())
                lgr.info(f"  Summaries: {sum_ok}/{total} with summaries")

            el3 = time.monotonic() - t3
            lgr.info(f"  Phase 3 completed in {el3:.2f}s")
            ctx.phase_timings["Phase 3"] = el3
            lgr.info(f"  Phase 3 LLM scheduler: batch_size={LLM_SUMMARY_BATCH_SIZE}, max_concurrency={LLM_SUMMARY_MAX_CONCURRENCY}")

            lgr.info(f"\n  PROCESSING COMPLETE: {total} stories in {time.monotonic() - run_started:.2f}s (Phases 1-3)")

            # ---------- Phase 4: Render report ----------
            lgr.info("\n[Phase 4] Rendering report...")
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
            lgr.info(f"\nFile written to {filepath}")
            lgr.info(f"  Stories: {total_after_dedup} | Time: {el4:.1f}s")
            ctx.phase_timings["Phase 4"] = el4
            lgr.info(f"  Phase 4 completed in {el4:.2f}s")

            # --- Phase 5: Internal report validation ---
            lgr.info("\n[Phase 5] Validating report...")
            t5 = time.monotonic()
            validation_passed, validation_issues = validate_report(filepath)
            el5 = time.monotonic() - t5
            ctx.phase_timings["Phase 5"] = el5
            lgr.info(f"  Phase 5 completed in {el5:.2f}s")

            if not validation_passed:
                total_elapsed = time.monotonic() - run_started
                lgr.info(f"TOTAL PIPELINE TIME: {total_elapsed:.2f}s")
                lgr.info("\n*** RUN VALIDATION FAILED — Report has broken summaries ***")
                lgr.info(f"STATUS: FAILED ({len(validation_issues)} issues found)")
                print(f"\n*** RUN FAILED — {len(validation_issues)} validation issues found ***")
                print(f"File: {filepath}")
                print(f"Log: {ctx.run_logfile}")
                lgr.info("\n=== PIPELINE EXIT CODE: VALIDATION FAILURE ===")
                return EXIT_CODE_VALIDATION

            # --- Phase 6: External test harness validation ---
            lgr.info("\n[Phase 6] Running test harness...")
            t6 = time.monotonic()
            harness_result = run_test_harness(ctx.run_logfile)
            el6 = time.monotonic() - t6
            ctx.phase_timings["Phase 6"] = el6
            lgr.info(f"  Phase 6 completed in {el6:.2f}s")
            lgr.info(f"  Harness result: {harness_result.status} — {harness_result.message}")
            for line in harness_result.stdout_lines:
                lgr.info(f"  [Harness] {line}")
            for line in harness_result.stderr_lines:
                lgr.info(f"  [Harness err] {line}")
            total_elapsed = time.monotonic() - run_started
            lgr.info(f"TOTAL PIPELINE TIME: {total_elapsed:.2f}s")

            exit_code = {
                "PASS": EXIT_CODE_SUCCESS,
                "WARN": EXIT_CODE_CONFIG,
                "FAIL": EXIT_CODE_VALIDATION,
                "ERROR": EXIT_CODE_HARNESS_ERROR,
                "SKIPPED": EXIT_CODE_HARNESS_ERROR,
            }.get(harness_result.status, EXIT_CODE_HARNESS_ERROR)

            if exit_code == EXIT_CODE_SUCCESS:
                lgr.info("\n=== PIPELINE COMPLETED SUCCESSFULLY ===")
            else:
                lgr.info(f"\n=== PIPELINE EXIT CODE: {exit_code} ({harness_result.status}) ===")
            print(f"\nDone. File: {filepath}")
            print(f"  Stories: {total_after_dedup} | Time: {el4:.1f}s")
            return exit_code
    finally:
        _teardown_run_logger(lgr)
