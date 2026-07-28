"""
Daily Brief Pipeline Orchestration
The main() orchestrator extracted from dashboard_pipeline.py.
"""

import sys
import os
import time
import re
import threading
import asyncio
import aiohttp
import feedparser
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from email.utils import parsedate_to_datetime
from functools import cmp_to_key

from daily_brief.config import *
from daily_brief.sources.rss import (
    build_rss_url,
    fetch_feed,
    normalize_title,
    parse_feed_date,
    format_pub_date,
    _sort_entries,
)
from daily_brief.sources.article import stage_extract_article
from daily_brief.sources.weather import fetch_weather
from daily_brief.tagging import tag_story_with_keywords
from daily_brief.categorization import ordered_categories_for_render
from daily_brief.llm import create_llm_client
from daily_brief.llm.summarizer import (
    _summarize as llm_summarize,
    batch_summarize_all as llm_batch_summarize_all,
    StoryPipelineState,
    build_context,
    _safe_sentence_summary,
    _is_refusal,
    _is_boilerplate,
    _count_sentences,
)
from daily_brief.rendering import build_weather_markdown, cleanup_old_files
from daily_brief.validation import validate_report
from daily_brief.harness import run_test_harness
from daily_brief.utils import (
    is_obituary_title,
    is_realt_estate_title,
)

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
    os.makedirs(LOG_DIR, exist_ok=True)
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


def is_realt_estate_title(title):
    """Check if a title contains real estate markers that should be filtered out."""
    if not title:
        return False
    realtor_keywords = [
        "realtor", "zillow", "redfin", "listing", "for sale", "house for",
        "home for", "property", "$"
    ]
    title_lower = title.lower()
    return any(keyword in title_lower for keyword in realtor_keywords)


# -- Main -------------------------------------------------------------------

async def main():
    global PHASE_TIMINGS
    PHASE_TIMINGS = {}

    global RUN_LOGFILE, OUTPUT_DIR, _llm_client
    _llm_client = create_llm_client(LLM_MODEL, OLLAMA_HOST + "/v1" if "/v1" not in OLLAMA_HOST else OLLAMA_HOST, timeout=180)
    OUTPUT_DIR = NEWS_DIR

    t0 = time.time()

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
        t1 = time.time()
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
        elapsed = time.time() - t1
        PHASE_TIMINGS['Phase 1'] = elapsed
        log(f"  Phase 1 completed in {elapsed:.2f}s")

        # ---------- Phase 2: RSS feeds (all async, concurrent) ----------
        rss_items = [(c[0], build_rss_url(c[1]), c[2]) for c in CATEGORIES if c[1]]
        log(f"\n[Phase 2] Fetching {len(rss_items)} RSS feeds...")
        t2 = time.time()

        log("  [DEBUG] Categories being fetched:")
        for name, url, max_stories in rss_items:
            log(f"    {name}: {url[:100]}... (max: {max_stories})")

        all_results = await asyncio.gather(
            *(fetch_feed(session, n, u, m) for n, u, m in rss_items),
            return_exceptions=True
        )

        by_cat = {}
        for result in all_results:
            if isinstance(result, Exception):
                continue
            name, entries = result
            if not isinstance(entries, list):
                entries = []
            by_cat[name] = entries

        total_before_dedup = sum(len(v) for v in by_cat.values())
        log(f"  Fetched {total_before_dedup} stories from {len(by_cat)} categories")

        log("  [DEBUG] Feed results by category:")
        for name in sorted(by_cat.keys()):
            count = len(by_cat[name])
            log(f"    {name}: {count} stories")

        def _dedup_category(cat_name, cat_entries, seen, age_limit_hours):
            """Dedup and age-filter a single category."""
            added = age_filtered = dup_filtered = 0
            for title, link, snippet, pub_dt in cat_entries:
                is_old = False
                if pub_dt is not None:
                    try:
                        age_secs = (now_ct - pub_dt).total_seconds()
                        if age_secs > age_limit_hours * 3600:
                            age_filtered += 1
                            is_old = True
                    except Exception:
                        age_filtered += 1
                        is_old = True
                if is_old:
                    continue
                norm = normalize_title(title)
                if norm in seen.get(cat_name, set()):
                    dup_filtered += 1
                    continue
                seen.setdefault(cat_name, set()).add(norm)
                if is_realt_estate_title(title) or is_obituary_title(title):
                    continue
                deduped.append((title, link, snippet, pub_dt, cat_name))
                added += 1
            return added, age_filtered, dup_filtered

        deduped = []
        total_age_filtered = 0
        total_dup_filtered = 0
        total_cross_dup_filtered = 0
        seen_per_cat = {}
        cats_with_zero_stories = []

        for cat_name in by_cat:
            age_limit = CATEGORY_AGE_LIMITS.get(cat_name, DEFAULT_AGE_LIMIT_HOURS)
            added, af, df = _dedup_category(cat_name, by_cat[cat_name], seen_per_cat, age_limit)
            total_age_filtered += af
            total_dup_filtered += df
            if added < 3:
                cats_with_zero_stories.append((cat_name, added))

        # Adaptive widening
        widened_cats = {}
        for cat_name, existing_count in cats_with_zero_stories:
            matching_cat = next((c for c in CATEGORIES if c[0] == cat_name), None)
            if not matching_cat or not matching_cat[1]:
                continue
            query = matching_cat[1]
            max_stories = matching_cat[2]
            default_limit = CATEGORY_AGE_LIMITS.get(cat_name, DEFAULT_AGE_LIMIT_HOURS)

            cat_widened_count = existing_count
            last_wide_days = 0
            log(f"  [WIDEN] '{cat_name}' had {existing_count} stories at {default_limit}h — attempting widening (2d-7d)")
            for widen_days in range(2, 8):
                widen_hours = widen_days * 24
                rss_url = build_rss_url(query)
                result = await fetch_feed(session, cat_name, rss_url, max_stories)
                name, entries = result
                if not entries:
                    log(f"    [{widen_days}d] no entries from feed")
                    continue
                added, af, df = _dedup_category(name, entries, seen_per_cat, widen_hours)
                total_age_filtered += af
                total_dup_filtered += df
                if added > 0:
                    cat_widened_count += added
                    last_wide_days = widen_days
                    log(f"    [{widen_days}d] +{added} stories (cumulative: {cat_widened_count})")
                else:
                    log(f"    [{widen_days}d] 0 added")
                if cat_widened_count >= 3:
                    break
            if cat_widened_count > existing_count:
                log(f"  [WIDEN] '{cat_name}' recovered {cat_widened_count - existing_count} additional stories (total: {cat_widened_count}, last successful: {last_wide_days}d)")
            else:
                log(f"  [WIDEN] '{cat_name}' exhausted to 7d: still at {existing_count} stories")

        # Cross-category dedup
        global_seen = set()
        cross_deduped = []
        for entry in deduped:
            title, link, snippet, pub_dt, cat_name = entry
            norm = normalize_title(title)
            if norm in global_seen:
                total_cross_dup_filtered += 1
                continue
            global_seen.add(norm)
            cross_deduped.append(entry)
        deduped = cross_deduped

        total_after_dedup = len(deduped)
        log(f"  Deduplicated: {total_before_dedup} -> {total_after_dedup} stories "
            f"(age-filtered: {total_age_filtered}, dup-filtered: {total_dup_filtered}, cross-cat-filtered: {total_cross_dup_filtered})")

        log("  [DEBUG] Per-category story count AFTER dedup:")
        cat_counts = {}
        for entry in deduped:
            cat = entry[4]
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
        for cn in sorted(cat_counts.keys()):
            log(f"    {cn}: {cat_counts[cn]}")

        elapsed = time.time() - t2
        PHASE_TIMINGS['Phase 2'] = elapsed
        log(f"  Phase 2 completed in {elapsed:.2f}s")

        # ---------- Phase 3: Summarization (single batch call) ----------
        log("\n[Phase 3] Enriching + summarizing...")

        stories = []
        for title, link, snippet, pub_dt, cat in deduped:
            s = StoryPipelineState(title, link, snippet, pub_dt, cat)
            stories.append(s)

        total = len(stories)

        # ---------- Phase 3A: Async article fetching for non-Google links ----------
        log("  [3A] Fetching full articles from external sources...")
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=20, limit_per_host=10, ttl_dns_cache=300),
            headers={"User-Agent": USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=5)
        ) as extract_session:
            await asyncio.gather(
                *[stage_extract_article(s, extract_session) for s in stories],
                return_exceptions=True
            )

        # ---------- Phase 3B/3C: Batch summary ----------
        log(f"  [3BC] Running BATCH summaries via {LLM_MODEL}...")
        t3 = time.time()
        sum_results = llm_batch_summarize_all(_llm_client, stories, session=session)
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
                    retry_summary = llm_summarize(_llm_client, context)
                    if retry_summary and not _is_refusal(retry_summary):
                        s.summary = retry_summary
                        retry_count += 1
            if retry_count < sum_fail:
                unhandled = sum_fail - retry_count
                log(f"  [3D] {unhandled} still failed — falling back to snippets")
                for s in stories:
                    if not s.summary or not s.summary.strip() or s.summary.strip().startswith("[Summary") or _is_refusal(s.summary):
                        s.summary = s.snippet[:250].strip() if s.snippet else "[Summary unavailable]"

            sum_ok = sum(1 for s in stories if s.summary and s.summary.strip() and not s.summary.strip().startswith("[Summary") and not _is_refusal(s.summary))
            sum_fail = total - sum_ok
            log(f"  Summaries done: {sum_ok} OK / {sum_fail} failed (retry recovered {retry_count})")

        # ---------- Phase 3E: Detect and fix boilerplate summaries ----------
        boilerplate_count = sum(1 for s in stories if s.summary and _is_boilerplate(s.summary))
        if boilerplate_count > 0:
            log(f"  [3E] Detected {boilerplate_count} boilerplate summaries — re-summarizing with strict prompt...")
            recovered = 0
            for s in stories:
                if s.summary and _is_boilerplate(s.summary):
                    context = build_context(s)
                    strict_summary = llm_summarize(_llm_client, context, strict=True)
                    if strict_summary and not _is_boilerplate(strict_summary) and not _is_refusal(strict_summary):
                        s.summary = strict_summary
                        recovered += 1
            if recovered < boilerplate_count:
                remaining = boilerplate_count - recovered
                log(f"  [3E] Recovered {recovered}/{boilerplate_count} boilerplate summaries ({remaining} remain)")
            else:
                log(f"  [3E] Recovered all {recovered}/{boilerplate_count} boilerplate summaries")

        elapsed = time.time() - t3
        log(f"  Phase 3 completed in {elapsed:.2f}s")
        PHASE_TIMINGS['Phase 3'] = elapsed

        log(f"\n  PROCESSING COMPLETE: {total} stories in {time.time() - t0:.2f}s")

        # ---------- Phase 4: Build sections + render Markdown ----------
        log("\n[Phase 4] Rendering report...")

        alerts_list = [s for s in stories if hasattr(s, 'is_alert') and s.is_alert]

        sections = {}
        for s in stories:
            smry = s.summary if s.summary else "[Summary unavailable]"
            entry = {
                "title": s.title,
                "link": s.link,
                "category": s.category,
                "summary": smry,
                "pub_date": format_pub_date(s.pub_dt),
            }
            sections.setdefault(s.category, []).append(entry)

        now = datetime.now(timezone.utc)
        fn_ts = now.strftime("%Y-%m-%d")

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        daily_brief_files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith('DailyBrief-' + fn_ts) and f.endswith('.md')]
        max_file_ver = 0
        for bf in daily_brief_files:
            mf = re.search(r'_v(\d+)\.md$', bf)
            if mf:
                max_file_ver = max(max_file_ver, int(mf.group(1)))
        file_ver = max_file_ver + 1

        filepath = os.path.join(OUTPUT_DIR, f"DailyBrief-{fn_ts}_v{file_ver:02d}.md")

        cleanup_old_files(OUTPUT_DIR, LOG_DIR, MAX_LOG_VERSIONS)

        ordered_cats = ordered_categories_for_render([c[0] for c in CATEGORIES if c[1]])
        sections_map = {cn: sections.get(cn, []) for cn in ordered_cats}

        rendered_cat_count = sum(1 for cn in ordered_cats
            if cn != WEATHER_SECTION_TITLE and cn != "Weather Forecast 77316"
            and len(sections_map.get(cn, [])) > 0)

        # -- Build markdown --
        md = []
        md.append("---")
        md.append("title: Daily Brief")
        md.append(f"date: {now.strftime('%Y-%m-%d')}")
        md.append(f"time_generated: {now.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        md.append("status: active")
        md.append(f"content_age_window: {DEFAULT_CONTENT_AGE_WINDOW_HOURS}")
        md.append(f"story_count_total: {total_after_dedup}")
        md.append(f"categories: {rendered_cat_count}")

        all_tags = set(FRONTMATTER_TAG_SEEDS or [])

        section_tag_map = {}
        for cn in ordered_cats:
            cat_stories = sections_map.get(cn, [])
            for st in cat_stories:
                if "title" in st and st["title"]:
                    title = st["title"]
                    story_tags = tag_story_with_keywords(title, cn)
                    individual_tags = []
                    for tag in story_tags.split():
                        tag = tag.strip()
                        if tag.startswith('#'):
                            individual_tags.append(tag.lstrip('#'))
                        elif tag.startswith('[') and tag.endswith(']'):
                            tag_content = tag[2:-2]
                            individual_tags.append(tag_content)
                    for tag in individual_tags:
                        all_tags.add(tag.lower())
            section_tag_map[cn] = cat_stories

        md.append("tags:")
        sorted_tags = sorted(list(all_tags))
        for tag in sorted_tags:
            md.append(f"  - {tag}")

        md.append("---")
        md.append("")
        md.append(f"# Daily Brief -- {now.strftime('%B %d, %Y')}")
        md.extend(build_weather_markdown(weather))

        # Category sections
        for cn in ordered_cats:
            if cn == WEATHER_SECTION_TITLE or cn == "Weather Forecast 77316":
                continue
            cat_stories = sections_map.get(cn, [])
            if not cat_stories:
                log(f"  Empty category: {cn} (rendering header)")
                md += ["", f"## {cn} (0 stories)", ""]
                continue
            md += ["", f"## {cn} ({len(cat_stories)} stories)", ""]
            for idx, st in enumerate(cat_stories):
                title_text = st["title"]
                url_val = st["link"]
                link_md = f"[{title_text}]({url_val})" if url_val and url_val != "#" else title_text
                pub_line = f"\n*Originally published on:* {st['pub_date']}" if st.get("pub_date") else ""
                tags_md = ""
                if "title" in st and st["title"]:
                    title = st["title"]
                    tags_md = tag_story_with_keywords(title, cn)
                md.append("")
                md.append(f"{idx + 1}. {link_md}")
                md.append(st["summary"] + pub_line)
                md.append(tags_md)

            md.append("---")

        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write("\n".join(md) + "\n")

        elapsed = time.time() - t0
        log(f"\nFile written to {filepath}")
        log(f"  Stories: {total_after_dedup} | Alerts: {len(alerts_list)} | Failed: {sum_fail}/{total} | Time: {elapsed:.1f}s")

        # --- Phase 5: Internal report validation ---
        log("\n[Phase 5] Validating report...")
        validation_passed, validation_issues = validate_report(filepath)

        if not validation_passed:
            log("\n*** RUN VALIDATION FAILED — Report has broken summaries ***")
            log(f"STATUS: FAILED ({len(validation_issues)} issues found)")
            print(f"\n*** RUN FAILED — {len(validation_issues)} validation issues found ***")
            print(f"File: {filepath}")
            print(f"See run log for details: {os.environ.get('RUN_LOGFILE', 'unknown')}")
            return

        # --- Phase 6: External test harness validation ---
        log("\n[Phase 6] Running test harness...")
        run_test_harness(RUN_LOGFILE)

        log("\n=== PIPELINE COMPLETED SUCCESSFULLY ===")
        print(f"\nDone. File: {filepath}")
        print(f"  Stories: {total_after_dedup} | Alerts: {len(alerts_list)} | Failed: {sum_fail}/{total} | Time: {elapsed:.1f}s")
