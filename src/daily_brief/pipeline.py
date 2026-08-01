"""
Daily Brief Pipeline Orchestration
The main() orchestrator extracted from dashboard_pipeline.py.
"""

import sys
import os
import re
import time
import threading
import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from daily_brief.config import *
from daily_brief.sources.rss import format_pub_date
from daily_brief.sources.article import stage_extract_article
from daily_brief.sources.weather import fetch_weather
from daily_brief.categorization import ordered_categories_for_render
from daily_brief.pipelines.rss_dedup import fetch_and_dedup
from daily_brief.llm import create_llm_client
from daily_brief.llm.summarizer import (
    _summarize as llm_summarize,
    batch_summarize_all as llm_batch_summarize_all,
    StoryPipelineState,
    build_context,
    _is_refusal,
    _is_boilerplate,
    _generate_auto_fallback,
)
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
    os.makedirs(os.path.dirname(RUN_LOGFILE), exist_ok=True)
    with log_lock:
        with open(RUN_LOGFILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


def _coerce_temperature_f(val):
    """Safely convert temperature string/none to float and sanity check."""
    if val is None:
        return None
    try:
        clean_val = re.sub(r"[^\d.]", "", str(val))
        if not clean_val:
            return None
        temp = float(clean_val)
        if temp < -50 or temp > 140:
            log(f"  WARNING: Extreme temperature detected and discarded: {temp}°F")
            return None
        return temp
    except (ValueError, TypeError):
        return None


# -- Main -------------------------------------------------------------------

async def main():
    global PHASE_TIMINGS
    PHASE_TIMINGS = {}

    # --- Config validation gate ---
    config_ok, config_issues = validate_config(CONFIG_YAML)
    if not config_ok:
        print(f"\nFATAL: {len(config_issues)} config validation error(s). Aborting.", file=sys.stderr)
        for ci in config_issues:
            print(f"CONFIG ERROR: {ci}", file=sys.stderr)
        sys.exit(1)

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

    global RUN_LOGFILE, OUTPUT_DIR, _llm_client
    _llm_client = create_llm_client(LLM_MODEL, OLLAMA_HOST + "/v1" if "/v1" not in OLLAMA_HOST else OLLAMA_HOST, timeout=180)
    OUTPUT_DIR = NEWS_DIR

    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(NEWS_DIR, exist_ok=True)

    run_started = time.monotonic()

    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    log_files = [f for f in os.listdir(LOG_DIR) if f.startswith('run_log_' + now_ts) and f.endswith('.md')]
    max_log_ver = 0
    for lf in log_files:
        m = re.search(r'_v(\d+)\.md$', lf)
        if m:
            max_log_ver = max(max_log_ver, int(m.group(1)))
    log_ver = max_log_ver + 1

    run_log_name = f"run_log_{now_ts}_v{log_ver:02d}.md"
    RUN_LOGFILE = os.path.join(LOG_DIR, run_log_name)

    log("=" * 60)
    log(f"RUN LOG: {RUN_LOGFILE}")
    log("DAILY BRIEF v" + VERSION + " - Pipeline Starting")
    log("=" * 60)

    now_ct = datetime.now(ACTIVE_TIMEZONE)
    cutoff = now_ct - timedelta(hours=DEFAULT_AGE_LIMIT_HOURS)

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=100, limit_per_host=30, ttl_dns_cache=300),
        headers={"User-Agent": USER_AGENT},
        timeout=aiohttp.ClientTimeout(total=30)
    ) as session:

        # ---------- Phase 1: Weather (async) ----------
        log("\n[Phase 1] Fetching NWS weather...")
        t1 = time.monotonic()
        weather = await fetch_weather(session, WEATHER_LAT, WEATHER_LON)
        if weather:
            station = weather.get("station", {})
            station_keys = ("avg_temp_today", "avg_monthly_rainfall", "current_monthly_rainfall")
            station_partial = any(
                not station.get(k) or station[k] == "Unavailable" or "(fallback)" in str(station.get(k, ""))
                for k in station_keys
            )
            station_label = "station (partial — fallback applied)" if station_partial else "station"
            status = "PARTIAL" if station_partial else "OK"
            log(
                f"  Weather {status} -- "
                f"{len(weather.get('forecast', []))} forecast periods | "
                f"1 {station_label} record | "
                f"{len(weather.get('lakes', {}))} lake sources"
            )
        else:
            log("  Weather returned empty")
        elapsed = time.monotonic() - t1
        PHASE_TIMINGS['Phase 1'] = elapsed
        log(f"  Phase 1 completed in {elapsed:.2f}s")

        # ---------- Phase 2: RSS feeds (extracted) ----------
        t2 = time.monotonic()
        deduped, dedup_stats = await fetch_and_dedup(session, CATEGORIES, log)
        elapsed = time.monotonic() - t2
        PHASE_TIMINGS['Phase 2'] = elapsed
        log(f"  Phase 2 completed in {elapsed:.2f}s")
        total_after_dedup = dedup_stats["total_after"]

        # ---------- Phase 3: Summarization (single batch call) ----------
        log("\n[Phase 3] Enriching + summarizing...")
        t3 = time.monotonic()

        stories = []
        for title, link, snippet, pub_dt, cat in deduped:
            s = StoryPipelineState(title, link, snippet, pub_dt, cat)
            stories.append(s)

        total = len(stories)

        # ---------- Phase 3A: Async article fetching for non-Google links ----------
        log("  [3A] Fetching full articles from external sources...")
        await asyncio.gather(
            *[stage_extract_article(s, session) for s in stories],
            return_exceptions=True
        )

        # ---------- Phase 3B/3C: Batch summary ----------
        log(f"  [3BC] Running BATCH summaries via {LLM_MODEL}...")
        await llm_batch_summarize_all(_llm_client, stories, session=session)
        sum_ok = sum(1 for s in stories if s.summary and s.summary.strip() and not s.summary.strip().startswith("[Summary") and not _is_refusal(s.summary))
        sum_fail = total - sum_ok
        log(f"  Batch summaries: {sum_ok} OK / {sum_fail} failed")

        # ---------- Phase 3D: Retry failed summaries individually ----------
        if sum_fail > 0:
            log(f"  [3D] Retrying {sum_fail} failed summaries individually...")
            retry_count = 0
            for s in stories:
                if not s.summary or not s.summary.strip() or s.summary.strip().startswith("[Summary") or _is_refusal(s.summary):
                    context = build_context(s)
                    retry_summary = await llm_summarize(_llm_client, context, title=s.title)
                    if retry_summary and not _is_refusal(retry_summary):
                        s.summary = retry_summary
                        retry_count += 1
            if retry_count < sum_fail:
                unhandled = sum_fail - retry_count
                log(f"  [3D] {unhandled} still failed — applying [Auto] headline fallback")
                for s in stories:
                    if not s.summary or not s.summary.strip() or s.summary.strip().startswith("[Summary") or _is_refusal(s.summary):
                        s.summary = _generate_auto_fallback(s.title)

            sum_ok = sum(1 for s in stories if s.summary and s.summary.strip() and not s.summary.strip().startswith("[Summary") and not _is_refusal(s.summary))
            sum_fail = total - sum_ok
            auto_count = sum(1 for s in stories if s.summary and s.summary.strip().startswith("[Auto]"))
            log(f"  Summaries done: {sum_ok} OK / {sum_fail} fallback (retry recovered {retry_count}, [{auto_count:>2}] [Auto])")

        # ---------- Phase 3E: Detect and fix boilerplate summaries ----------
        boilerplate_count = sum(1 for s in stories if s.summary and _is_boilerplate(s.summary))
        if boilerplate_count > 0:
            log(f"  [3E] Detected {boilerplate_count} boilerplate summaries — re-summarizing with strict prompt...")
            recovered = 0
            for s in stories:
                if s.summary and _is_boilerplate(s.summary):
                    context = build_context(s)
                    strict_summary = await llm_summarize(_llm_client, context, title=s.title, strict=True)
                    if strict_summary and not _is_boilerplate(strict_summary) and not _is_refusal(strict_summary):
                        if strict_summary != "[Summary Unavailable]":
                            s.summary = strict_summary
                            recovered += 1
                        else:
                            s.summary = _generate_auto_fallback(s.title)
                    elif not s.summary or s.summary.strip().startswith("[Summary"):
                        s.summary = _generate_auto_fallback(s.title)
            auto_count = sum(1 for s in stories if s.summary and s.summary.strip().startswith("[Auto]"))
            unavailable_count = sum(1 for s in stories if s.summary and "[Summary Unavailable]" in s.summary)
            if auto_count:
                log(f"  [3E] Total [Auto] fallbacks in report: {auto_count}")
            if unavailable_count:
                log(f"  [3E] WARNING: {unavailable_count} stories still [Summary Unavailable]")
            if recovered < boilerplate_count:
                remaining = boilerplate_count - recovered
                log(f"  [3E] Recovered {recovered}/{boilerplate_count} boilerplate summaries ({remaining} fell back)")
            else:
                log(f"  [3E] Recovered all {recovered}/{boilerplate_count} boilerplate summaries")

        elapsed = time.monotonic() - t3
        log(f"  Phase 3 completed in {elapsed:.2f}s")
        PHASE_TIMINGS['Phase 3'] = elapsed

        log(f"\n  PROCESSING COMPLETE: {total} stories in {time.monotonic() - run_started:.2f}s (Phases 1-3)")

        # ---------- Phase 4: Render report ----------
        log("\n[Phase 4] Rendering report...")
        t4 = time.monotonic()

        sections, alerts_list = build_sections_from_stories(stories, format_pub_date)
        filepath, file_ver = compute_output_path(OUTPUT_DIR)
        cleanup_old_files(OUTPUT_DIR, LOG_DIR, MAX_LOG_VERSIONS)

        ordered_cats = ordered_categories_for_render([c[0] for c in CATEGORIES if c[1]])
        sections_map = {cn: sections.get(cn, []) for cn in ordered_cats}
        rendered_cat_count = sum(1 for cn in ordered_cats
            if cn != WEATHER_SECTION_TITLE and cn != "Weather Forecast 77316"
            and len(sections_map.get(cn, [])) > 0)

        md = build_markdown(stories, weather, sections_map, ordered_cats, {
            "total_after_dedup": total_after_dedup,
            "rendered_cat_count": rendered_cat_count,
            "DEFAULT_CONTENT_AGE_WINDOW_HOURS": DEFAULT_CONTENT_AGE_WINDOW_HOURS,
            "FRONTMATTER_TAG_SEEDS": FRONTMATTER_TAG_SEEDS,
            "WEATHER_SECTION_TITLE": WEATHER_SECTION_TITLE,
        })
        write_report(filepath, md)

        elapsed = time.monotonic() - t4
        log(f"\nFile written to {filepath}")
        log(f"  Stories: {total_after_dedup} | Alerts: {len(alerts_list)} | Failed: {sum_fail}/{total} | Time: {elapsed:.1f}s")
        PHASE_TIMINGS['Phase 4'] = elapsed
        log(f"  Phase 4 completed in {elapsed:.2f}s")

        # --- Phase 5: Internal report validation ---
        log("\n[Phase 5] Validating report...")
        t5 = time.monotonic()
        validation_passed, validation_issues = validate_report(filepath)
        elapsed_5 = time.monotonic() - t5
        PHASE_TIMINGS['Phase 5'] = elapsed_5
        log(f"  Phase 5 completed in {elapsed_5:.2f}s")

        if not validation_passed:
            total_elapsed = time.monotonic() - run_started
            log(f"TOTAL PIPELINE TIME: {total_elapsed:.2f}s")
            log("\n*** RUN VALIDATION FAILED — Report has broken summaries ***")
            log(f"STATUS: FAILED ({len(validation_issues)} issues found)")
            print(f"\n*** RUN FAILED — {len(validation_issues)} validation issues found ***")
            print(f"File: {filepath}")
            print(f"See run log for details: {os.environ.get('RUN_LOGFILE', 'unknown')}")
            return

        # --- Phase 6: External test harness validation ---
        log("\n[Phase 6] Running test harness...")
        t6 = time.monotonic()
        run_test_harness(RUN_LOGFILE)
        elapsed_6 = time.monotonic() - t6
        PHASE_TIMINGS['Phase 6'] = elapsed_6
        log(f"  Phase 6 completed in {elapsed_6:.2f}s")
        total_elapsed = time.monotonic() - run_started
        log(f"TOTAL PIPELINE TIME: {total_elapsed:.2f}s")

        log("\n=== PIPELINE COMPLETED SUCCESSFULLY ===")
        print(f"\nDone. File: {filepath}")
        print(f"  Stories: {total_after_dedup} | Alerts: {len(alerts_list)} | Failed: {sum_fail}/{total} | Time: {elapsed:.1f}s")
