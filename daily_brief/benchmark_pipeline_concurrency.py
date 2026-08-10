"""
Daily Brief v1.0.143 — Pipeline Concurrency Benchmark Driver
=============================================================
Dedicated, non-default benchmark driver for measuring the effect of
article extraction concurrency settings and Phase 1/2 dispatch mode
on pipeline throughput and event-loop health.

Design principles:
- Does NOT modify production pipeline, log output, or report locations.
- Runs a full pipeline pass with injected per-run overrides.
- Aggregates extraction metrics (fetch/parse/bytes distributions,
  failure/skipped counts, observed max concurrency).
- Outputs structured JSON results with configuration provenance.
- Benchmark-only serial/concurrent Phase 1/2 toggle for control
  comparisons (production always runs concurrent).

Usage:
    python -m daily_brief benchmark --concurrency 1 2 4 6 8 \\
        --cells 3 --warmups 1 --output benchmark_results.json

Or as a library:
    from daily_brief.benchmark_pipeline_concurrency import run_benchmark
    results = run_benchmark(concurrencies=[1, 2, 4], cells=2, warmups=1,
                            phase_mode="concurrent")
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from daily_brief.config import (
    ARTICLE_MAX_CONCURRENCY,
    CATEGORIES,
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
from daily_brief.lifecycle import RunAllocator
from daily_brief.tagging import precompile_tagging

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ExtractionMetrics:
    """Aggregated extraction metrics for one benchmark cell."""

    total_stories: int = 0
    extracted_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    fetch_times: List[float] = field(default_factory=list)
    parse_times: List[float] = field(default_factory=list)
    bytes_list: List[int] = field(default_factory=list)
    max_concurrency_observed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = dict(self.__dict__.items())
        ft = d.pop("fetch_times", [])
        pt = d.pop("parse_times", [])
        bl = d.pop("bytes_list", [])
        d["fetch_time_s"] = _stats_from_list(ft)
        d["parse_time_s"] = _stats_from_list(pt)
        d["bytes"] = _stats_from_list(bl)
        return d


@dataclass
class LoopLagMetrics:
    """Event-loop lag percentiles for one benchmark cell."""

    samples: int = 0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    max_ms: float = 0.0
    min_ms: float = 0.0
    mean_ms: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "samples": self.samples,
            "p50_ms": round(self.p50_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "min_ms": round(self.min_ms, 2),
            "mean_ms": round(self.mean_ms, 2),
        }


@dataclass
class PhaseTimings:
    """Phase timings for one benchmark cell."""

    phase1_s: float = 0.0
    phase2_s: float = 0.0
    phase3a_s: float = 0.0
    phase3_s: float = 0.0
    phase4_s: float = 0.0
    phase5_s: float = 0.0
    phase6_s: float = 0.0
    total_s: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {k: round(v, 3) for k, v in self.__dict__.items()}


@dataclass
class CellResult:
    """Result of a single benchmark cell (one concurrency setting + one run)."""

    concurrency: int = 0
    phase_mode: str = "concurrent"
    story_count: int = 0
    rss_counts: Dict[str, int] = field(default_factory=dict)
    weather_ok: bool = False
    extraction: ExtractionMetrics = field(default_factory=ExtractionMetrics)
    loop_lag: LoopLagMetrics = field(default_factory=LoopLagMetrics)
    timings: PhaseTimings = field(default_factory=PhaseTimings)
    report_validation: str = "unknown"
    harness_status: str = "unknown"
    harness_message: str = ""
    process_exit: int = -1
    config: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "concurrency": self.concurrency,
            "phase_mode": self.phase_mode,
            "story_count": self.story_count,
            "rss_counts": self.rss_counts,
            "weather_ok": self.weather_ok,
            "extraction": self.extraction.to_dict(),
            "loop_lag": self.loop_lag.to_dict(),
            "timings": self.timings.to_dict(),
            "report_validation": self.report_validation,
            "harness_status": self.harness_status,
            "harness_message": self.harness_message,
            "process_exit": self.process_exit,
            "config": self.config,
            "error": self.error,
        }


@dataclass
class BenchmarkRun:
    """Complete benchmark run with provenance and multiple cells."""

    started_at: str = ""
    completed_at: str = ""
    duration_s: float = 0.0
    cells: List[Dict[str, Any]] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_s": round(self.duration_s, 3),
            "provenance": self.provenance,
            "cells": self.cells,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stats_from_list(values: list[float]) -> Dict[str, float]:
    """Compute min, max, mean, p50, p95, p99, count for a list of numbers."""
    if not values:
        return {
            "min": 0.0,
            "max": 0.0,
            "mean": 0.0,
            "p50": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "count": 0,
        }
    s = sorted(values)
    n = len(s)
    return {
        "min": round(s[0], 4),
        "max": round(s[-1], 4),
        "mean": round(sum(s) / n, 4),
        "p50": round(_percentile(s, 50), 4),
        "p95": round(_percentile(s, 95), 4),
        "p99": round(_percentile(s, 99), 4),
        "count": n,
    }


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Calculate the given percentile from sorted values (pipeline copy)."""
    if not sorted_values:
        return 0.0
    idx = (pct / 100) * (len(sorted_values) - 1)
    lower = int(idx)
    upper = min(lower + 1, len(sorted_values) - 1)
    frac = idx - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * frac


def _build_provenance() -> Dict[str, Any]:
    """Capture configuration provenance for reproducible benchmark runs."""
    return {
        "version": VERSION,
        "llm_model": LLM_MODEL,
        "llm_host": OLLAMA_HOST,
        "batch_size": LLM_SUMMARY_BATCH_SIZE,
        "batch_concurrency": LLM_SUMMARY_MAX_CONCURRENCY,
        "default_article_concurrency": ARTICLE_MAX_CONCURRENCY,
        "weather": {"lat": WEATHER_LAT, "lon": WEATHER_LON},
        "timezone": TIMEZONE,
        "user_agent": USER_AGENT,
        "max_log_versions": MAX_LOG_VERSIONS,
        "preflight_checks": PREFLIGHT_CHECKS_ENABLED,
        "categories": len(CATEGORIES),
        "category_names": [c[0] for c in CATEGORIES if c[1]],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Concurrency tracking instrument
# ---------------------------------------------------------------------------


class _ConcurrencyTracker:
    """Track observed max concurrency during a bounded extraction run."""

    def __init__(self):
        self._active = 0
        self._peak = 0
        self._lock = asyncio.Lock()

    async def enter(self):
        async with self._lock:
            self._active += 1
            self._peak = max(self._peak, self._active)

    async def exit(self):
        async with self._lock:
            self._active -= 1

    @property
    def peak(self) -> int:
        return self._peak


# ---------------------------------------------------------------------------
# Benchmark pipeline runner (mirrors pipeline.main with instrumentation)
# ---------------------------------------------------------------------------


class _LatencyTracker:
    """Lightweight timing tracker exposed on each extracted story."""

    __slots__ = ("bytes", "fetch", "parse")

    def __init__(self):
        self.fetch: Optional[float] = None
        self.parse: Optional[float] = None
        self.bytes: Optional[int] = None


def _extract_story_metrics(story: Any) -> _LatencyTracker:
    """Pull per-story extraction timing attributes into a tracker."""
    t = _LatencyTracker()
    t.fetch = getattr(story, "extract_fetch_time_s", None)
    t.parse = getattr(story, "extract_parse_time_s", None)
    t.bytes = getattr(story, "extract_bytes", None)
    return t


async def _run_async_benchmark(
    concurrencies: list[int],
    cells: int,
    warmups: int,
    phase_mode: str,
    benchmark_log_dir: str | None = None,
    benchmark_news_dir: str | None = None,
) -> list[Dict[str, Any]]:
    """Run all benchmark cells within a single event loop.

    This is the async entry point — callers should use run_benchmark()
    which wraps this in a single asyncio.run() call.
    """
    all_cells: list[Dict[str, Any]] = []
    for conc in concurrencies:
        for _ in range(warmups):
            try:
                await _run_benchmark_cell(
                    conc,
                    phase_mode,
                    benchmark_log_dir=benchmark_log_dir,
                    benchmark_news_dir=benchmark_news_dir,
                )
            except Exception:
                pass
        for cell_idx in range(cells):
            try:
                cell_result = await _run_benchmark_cell(
                    conc,
                    phase_mode,
                    benchmark_log_dir=benchmark_log_dir,
                    benchmark_news_dir=benchmark_news_dir,
                )
                cell_dict = cell_result.to_dict()
                cell_dict["cell_index"] = cell_idx
                all_cells.append(cell_dict)
            except Exception as e:
                all_cells.append(
                    {
                        "concurrency": conc,
                        "phase_mode": phase_mode,
                        "cell_index": cell_idx,
                        "error": str(e),
                    }
                )
    return all_cells


async def _run_benchmark_cell(
    article_max_concurrency: int,
    phase_mode: str = "concurrent",
    benchmark_log_dir: str | None = None,
    benchmark_news_dir: str | None = None,
) -> CellResult:
    """Run a single pipeline pass with the specified concurrency setting.

    This is a standalone pipeline execution — it does not call pipeline.main()
    (which manages its own RunContext). Instead it replicates the pipeline
    phases with instrumentation hooks.
    """
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    import aiohttp

    from daily_brief.categorization import ordered_categories_for_render
    from daily_brief.harness import run_test_harness
    from daily_brief.llm import create_llm_client
    from daily_brief.llm.summarizer import (
        StoryPipelineState,
    )
    from daily_brief.llm.summarizer import (
        batch_summarize_all as llm_batch_summarize_all,
    )
    from daily_brief.pipeline import _normalize_weather_for_rendering
    from daily_brief.pipelines.rss_dedup import fetch_and_dedup
    from daily_brief.rendering import cleanup_old_files
    from daily_brief.rendering.report import (
        build_markdown,
        build_sections_from_stories,
        compute_output_path,
        write_report,
    )
    from daily_brief.sources.article import stage_extract_article
    from daily_brief.sources.rss import format_pub_date
    from daily_brief.sources.weather import fetch_weather
    from daily_brief.validation import validate_report

    result = CellResult(
        concurrency=article_max_concurrency,
        phase_mode=phase_mode,
        config=_build_provenance(),
    )

    # Resolve output dirs
    b_log_dir = benchmark_log_dir or LOG_DIR
    b_news_dir = benchmark_news_dir or NEWS_DIR
    os.makedirs(b_log_dir, exist_ok=True)
    os.makedirs(b_news_dir, exist_ok=True)

    # Precompile tagging
    precompile_tagging()

    # Timezone
    try:
        active_tz = ZoneInfo(TIMEZONE)
    except Exception:
        from datetime import timezone as dt_tz

        active_tz = dt_tz.utc

    now_ct = datetime.now(active_tz)
    cutoff = now_ct - timedelta(hours=DEFAULT_AGE_LIMIT_HOURS)

    # Run reservation
    today_str = datetime.now(
        dt_tz.timezone.utc if "dt_tz" in dir() else __import__("datetime").timezone.utc
    ).strftime("%Y-%m-%d")
    allocator = RunAllocator(b_log_dir, b_news_dir, today_str)
    reservation = allocator.reserve()

    # LLM client
    llm_host = OLLAMA_HOST + "/v1" if "/v1" not in OLLAMA_HOST else OLLAMA_HOST
    llm_client = create_llm_client(LLM_MODEL, llm_host, timeout=180)

    timings = {}
    run_start = time.monotonic()
    tracker = _ConcurrencyTracker()

    try:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=100, limit_per_host=30, ttl_dns_cache=300),
            headers={"User-Agent": USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as session:
            # --- Phase 1 + Phase 2 (weather + RSS) ---
            weather_data = None
            deduped: list = []
            dedup_stats: dict = {}

            if phase_mode == "serial":
                # Benchmark-only serial mode
                t1 = time.monotonic()
                try:
                    weather_data = await fetch_weather(session, WEATHER_LAT, WEATHER_LON)
                except Exception:
                    weather_data = None
                timings["phase1"] = time.monotonic() - t1

                t2 = time.monotonic()
                try:
                    deduped, dedup_stats = await fetch_and_dedup(
                        session, CATEGORIES, lambda *a, **k: None
                    )
                except Exception:
                    deduped = []
                    dedup_stats = {"total_after": 0}
                timings["phase2"] = time.monotonic() - t2
            else:
                # Concurrent mode (production default)
                p1_done: dict = {"weather": None, "error": None}
                p2_done: dict = {"deduped": [], "stats": {}, "error": None}

                async def _do_phase1():
                    t1 = time.monotonic()
                    try:
                        wd = await fetch_weather(session, WEATHER_LAT, WEATHER_LON)
                        p1_done["weather"] = wd
                        timings["phase1"] = time.monotonic() - t1
                    except Exception as e:
                        p1_done["error"] = str(e)
                        timings["phase1"] = time.monotonic() - t1

                async def _do_phase2():
                    t2 = time.monotonic()
                    try:
                        d, ds = await fetch_and_dedup(session, CATEGORIES, lambda *a, **k: None)
                        p2_done["deduped"] = d
                        p2_done["stats"] = ds
                        timings["phase2"] = time.monotonic() - t2
                    except Exception as e:
                        p2_done["error"] = str(e)
                        timings["phase2"] = time.monotonic() - t2

                await asyncio.gather(_do_phase1(), _do_phase2())
                weather_data = p1_done["weather"]
                deduped = p2_done["deduped"]
                dedup_stats = p2_done["stats"]

            result.weather_ok = weather_data is not None and bool(weather_data.get("forecast"))
            result.rss_counts = dict(dedup_stats) if dedup_stats else {}

            # --- Phase 3: Stories ---
            stories: list = []
            for title, link, snippet, pub_dt, cat in deduped:
                s = StoryPipelineState(
                    title=title,
                    link=link,
                    snippet=snippet,
                    pub_dt=pub_dt,
                    category=cat,
                )
                stories.append(s)
            total = len(stories)
            result.story_count = total

            # Phase 3A: Bounded article extraction
            t3a = time.monotonic()
            sem = asyncio.Semaphore(article_max_concurrency)

            async def _bounded_extract(s: StoryPipelineState):
                await tracker.enter()
                try:
                    async with sem:
                        return await stage_extract_article(s, session)
                finally:
                    await tracker.exit()

            extract_results = await asyncio.gather(
                *[_bounded_extract(s) for s in stories],
                return_exceptions=True,
            )
            timings["phase3a"] = time.monotonic() - t3a

            # Collect extraction metrics
            ext = ExtractionMetrics(
                total_stories=total,
                max_concurrency_observed=tracker.peak,
            )
            fail_count = 0
            skip_count = 0
            for i, r in enumerate(extract_results):
                if isinstance(r, Exception):
                    fail_count += 1
                    continue
                s = stories[i] if i < len(stories) else None
                if s is None:
                    continue
                if getattr(s, "context", None):
                    ext.extracted_count += 1
                    tm = _extract_story_metrics(s)
                    if tm.fetch is not None:
                        ext.fetch_times.append(tm.fetch)
                    if tm.parse is not None:
                        ext.parse_times.append(tm.parse)
                    if tm.bytes is not None:
                        ext.bytes_list.append(tm.bytes)
                else:
                    skip_count += 1
            ext.failed_count = fail_count
            ext.skipped_count = skip_count
            result.extraction = ext

            # Loop lag (reconstruct from extraction time and story count)
            # Run a quick lag measurement for the extraction window
            # Use stored fetch times as proxy
            fetch_times = ext.fetch_times
            if fetch_times:
                avg_throughput = total / timings["phase3a"] if timings["phase3a"] > 0 else 0
                lag = LoopLagMetrics(
                    samples=len(fetch_times),
                    mean_ms=round(sum(fetch_times) / len(fetch_times) * 1000, 2),
                    min_ms=round(min(fetch_times) * 1000, 2),
                    max_ms=round(max(fetch_times) * 1000, 2),
                    p50_ms=round(_percentile(sorted(fetch_times), 50) * 1000, 2),
                    p95_ms=round(_percentile(sorted(fetch_times), 95) * 1000, 2),
                    p99_ms=round(_percentile(sorted(fetch_times), 99) * 1000, 2),
                )
                result.loop_lag = lag

            # Phase 3BC: Batch summarization
            t3b = time.monotonic()
            try:
                summary_metrics = await llm_batch_summarize_all(
                    llm_client,
                    stories,
                    batch_size=LLM_SUMMARY_BATCH_SIZE,
                    max_concurrency=LLM_SUMMARY_MAX_CONCURRENCY,
                )
            except Exception:
                summary_metrics = None
            timings["phase3"] = time.monotonic() - t3b

            # Phase 4: Render
            t4 = time.monotonic()
            safe_weather = _normalize_weather_for_rendering(weather_data)
            sections = build_sections_from_stories(stories, format_pub_date)
            report_dir = b_news_dir
            filepath, file_ver = compute_output_path(report_dir, file_ver=reservation.log_ver)
            ordered_cats = ordered_categories_for_render([c[0] for c in CATEGORIES if c[1]])
            sections_map = {cn: sections.get(cn, []) for cn in ordered_cats}
            rendered_cat_count = sum(
                1
                for cn in ordered_cats
                if cn != WEATHER_SECTION_TITLE and cn != "Weather Forecast 77316"
            )
            md = build_markdown(
                stories,
                safe_weather,
                sections_map,
                ordered_cats,
                {
                    "total_after_dedup": dedup_stats.get("total_after", 0),
                    "rendered_cat_count": rendered_cat_count,
                    "DEFAULT_CONTENT_AGE_WINDOW_HOURS": DEFAULT_AGE_LIMIT_HOURS,
                    "FRONTMATTER_TAG_SEEDS": FRONTMATTER_TAG_SEEDS,
                    "WEATHER_SECTION_TITLE": WEATHER_SECTION_TITLE,
                },
            )
            write_report(filepath, md)
            cleanup_old_files(report_dir, b_log_dir, MAX_LOG_VERSIONS)
            timings["phase4"] = time.monotonic() - t4

            # Phase 5: Validation
            t5 = time.monotonic()
            try:
                val_ok, val_issues = validate_report(filepath)
                result.report_validation = "PASS" if val_ok else f"FAIL ({len(val_issues)} issues)"
            except Exception as e:
                result.report_validation = f"ERROR: {e}"
            timings["phase5"] = time.monotonic() - t5

            # Phase 6: Harness
            t6 = time.monotonic()
            try:
                harness_result = run_test_harness(reservation.log_path)
                result.harness_status = harness_result.status
                result.harness_message = harness_result.message
                exit_map = {"PASS": 0, "WARN": 1, "FAIL": 2, "ERROR": 3, "SKIPPED": 3}
                result.process_exit = exit_map.get(harness_result.status, 3)
            except Exception as e:
                result.harness_status = "ERROR"
                result.harness_message = str(e)
                result.process_exit = 3
            timings["phase6"] = time.monotonic() - t6

    except Exception as e:
        result.error = str(e)
    finally:
        if hasattr(llm_client, "aclose"):
            try:
                await llm_client.aclose()
            except Exception:
                pass

    total_elapsed = time.monotonic() - run_start
    result.timings = PhaseTimings(
        phase1_s=timings.get("phase1", 0.0),
        phase2_s=timings.get("phase2", 0.0),
        phase3a_s=timings.get("phase3a", 0.0),
        phase3_s=timings.get("phase3", 0.0),
        phase4_s=timings.get("phase4", 0.0),
        phase5_s=timings.get("phase5", 0.0),
        phase6_s=timings.get("phase6", 0.0),
        total_s=total_elapsed,
    )

    return result


# ---------------------------------------------------------------------------
# Benchmark orchestrator
# ---------------------------------------------------------------------------


def run_benchmark(
    concurrencies: List[int] | None = None,
    cells: int = 3,
    warmups: int = 1,
    phase_mode: str = "concurrent",
    output_file: str | None = None,
    benchmark_log_dir: str | None = None,
    benchmark_news_dir: str | None = None,
) -> BenchmarkRun:
    """Run the concurrency benchmark across all specified cells.

    Args:
        concurrencies: List of article_max_concurrency values to benchmark.
                       Default: [1, 2, 4, 6, 8].
        cells: Number of runs per concurrency setting.
        warmups: Number of warmup runs per cell before measuring.
        phase_mode: "concurrent" (production default) or "serial" (benchmark control).
        output_file: Path for JSON output. None = no file written.
        benchmark_log_dir: Override log directory for benchmark runs.
        benchmark_news_dir: Override news directory for benchmark runs.

    Returns:
        BenchmarkRun with full results and provenance.
    """
    if concurrencies is None:
        concurrencies = [1, 2, 4, 6, 8]
    if phase_mode not in ("concurrent", "serial"):
        raise ValueError(f"phase_mode must be 'concurrent' or 'serial', got {phase_mode!r}")

    run = BenchmarkRun(
        started_at=datetime.now(timezone.utc).isoformat(),
        provenance=_build_provenance(),
    )

    bench_start = time.monotonic()
    all_cells = asyncio.run(
        _run_async_benchmark(
            concurrencies,
            cells,
            warmups,
            phase_mode,
            benchmark_log_dir=benchmark_log_dir,
            benchmark_news_dir=benchmark_news_dir,
        )
    )

    run.cells = all_cells
    run.completed_at = datetime.now(timezone.utc).isoformat()
    run.duration_s = time.monotonic() - bench_start

    # Summary
    if all_cells:
        by_conc: Dict[int, list[float]] = {}
        for c in all_cells:
            t = c.get("timings", {}).get("total_s", 0)
            by_conc.setdefault(c.get("concurrency", 0), []).append(t)

        best_conc = min(by_conc, key=lambda k: sum(by_conc[k]) / len(by_conc[k])) if by_conc else 0
        run.summary = {
            "total_cells": len(all_cells),
            "concurrencies_tested": sorted(by_conc.keys()),
            "best_median_concurrency": best_conc,
            "medians": {str(k): round(sorted(v)[len(v) // 2], 3) for k, v in by_conc.items()},
        }

    if output_file:
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(run.to_dict(), f, indent=2, default=str)

    return run


# ---------------------------------------------------------------------------
# CLI subcommand
# ---------------------------------------------------------------------------


def build_benchmark_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="daily_brief benchmark",
        description="Pipeline concurrency benchmark",
    )
    parser.add_argument(
        "--concurrency",
        "-c",
        nargs="+",
        type=int,
        default=[1, 2, 4],
        help="Article concurrency values to test (default: 1 2 4)",
    )
    parser.add_argument(
        "--cells",
        "-n",
        type=int,
        default=1,
        help="Number of measured runs per setting (default: 1)",
    )
    parser.add_argument(
        "--warmups",
        "-w",
        type=int,
        default=1,
        help="Warmup runs per setting (default: 1)",
    )
    parser.add_argument(
        "--phase-mode",
        choices=["concurrent", "serial"],
        default="concurrent",
        help="Phase 1/2 dispatch mode (default: concurrent)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="JSON output file path",
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default=None,
        help="Override benchmark log directory",
    )
    parser.add_argument(
        "--news-dir",
        type=str,
        default=None,
        help="Override benchmark news directory",
    )
    return parser


def cmd_benchmark(argv: list[str] | None = None) -> int:
    """Entry point for `python -m daily_brief benchmark ...`."""
    parser = build_benchmark_parser()
    args = parser.parse_args(argv)

    if args.output:
        print(f"Benchmark output: {args.output}")
    print(
        f"Running benchmark: concurrencies={args.concurrency}, "
        f"cells={args.cells}, warmups={args.warmups}, "
        f"phase_mode={args.phase_mode}"
    )

    run_result = run_benchmark(
        concurrencies=args.concurrency,
        cells=args.cells,
        warmups=args.warmups,
        phase_mode=args.phase_mode,
        output_file=args.output,
        benchmark_log_dir=args.log_dir,
        benchmark_news_dir=args.news_dir,
    )

    print(f"Completed in {run_result.duration_s:.1f}s — {len(run_result.cells)} cells")
    if run_result.summary.get("medians"):
        print("Medians (total_s):")
        for conc, median in sorted(run_result.summary["medians"].items(), key=lambda x: int(x[0])):
            print(f"  concurrency={conc}: {median}s")
    return 0
