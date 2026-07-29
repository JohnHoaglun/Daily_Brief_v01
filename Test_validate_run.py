#!/usr/bin/env python3
"""
validate_run.py — Daily Brief pipeline validation harness

Implements the checks defined in DailyBrief_TestHarness.md against a
run_log_*.md + DailyBrief-*.md pair, driven by config.yaml.

USAGE:
    python3 validate_run.py --config /path/to/config.yaml --date 2026-07-26 --version v01

    Optional:
    --prev-date / --prev-version   Explicitly point at the prior run for the
                                    F.2 cross-run comparison checks. If omitted,
                                    the script auto-detects the most recent
                                    earlier run_log_*.md in the same log_dir.
    --no-write                     Print the report to stdout only; don't
                                    write validation_log_<date>_<version>.md

OUTPUT:
    Writes validation_log_<date>_<version>.md next to run_log_<date>_<version>.md
    (in config.yaml's directories.log_dir). Prints the same report to stdout.

EXIT CODES:
    0 = PASS (no FAIL-level findings)
    1 = WARN only (no FAIL-level findings, but WARNs present)
    2 = FAIL (one or more FAIL-level findings — treat run as needing review)

NOTE ON SPEC GAPS:
    Some checks reference pipeline instrumentation that doesn't exist yet
    (see DailyBrief_TestHarness.md "Open / Tunable Items"):
      - F.1 explicit [LIVE]/[FALLBACK] logging — not wired up. F.2/F.3/F.4
        run as the working backstop.
      - 2.2a adaptive day-window widening — not implemented. 0-story
        categories are reported as known gaps, not hard failures, EXCEPT
        where 2.6 (Hermes query typo) already explains the root cause.
    These are marked in code with `# SPEC-GAP:` comments.
"""

import argparse
import glob
import os
import re
import sys
from collections import defaultdict

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml --break-system-packages")


# --------------------------------------------------------------------------
# Result collection
# --------------------------------------------------------------------------

class Results:
    def __init__(self):
        self.items = []  # list of (level, check_id, message)

    def fail(self, check_id, message):
        self.items.append(("FAIL", check_id, message))

    def warn(self, check_id, message):
        self.items.append(("WARN", check_id, message))

    def info(self, check_id, message):
        self.items.append(("INFO", check_id, message))

    def by_level(self, level):
        return [(cid, msg) for lvl, cid, msg in self.items if lvl == level]

    def status(self):
        if self.by_level("FAIL"):
            return "FAIL"
        if self.by_level("WARN"):
            return "WARN"
        return "PASS"


STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "at", "by", "from", "is", "are", "was", "were", "be", "been",
    "this", "that", "these", "those", "as", "it", "its", "into", "after",
    "over", "amid", "than", "their", "his", "her", "has", "have", "had",
    "will", "would", "could", "should", "about", "which", "who", "what",
    "says", "said", "new", "more", "not", "also", "some", "such", "each",
}

BOILERPLATE_PHRASES = [
    "this highlights",
    "this suggests",
    "this indicates",
    "further details",
    "this serves as a general roundup",
    "this demonstrates",
    "this underscores",
    "this reflects",
    "this signals",
]


# --------------------------------------------------------------------------
# Config loading / path resolution
# --------------------------------------------------------------------------

def load_config(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_paths(config, date, version):
    log_dir = config["directories"]["log_dir"]
    news_dir = config["directories"]["news_dir"]
    log_path = os.path.join(log_dir, f"run_log_{date}_{version}.md")
    output_path = os.path.join(news_dir, f"DailyBrief-{date}_{version}.md")
    return log_dir, news_dir, log_path, output_path


def find_previous_run(log_dir, date, version):
    """Auto-detect the most recent run_log_*.md strictly before (date, version)."""
    candidates = sorted(glob.glob(os.path.join(log_dir, "run_log_*.md")))
    current_name = f"run_log_{date}_{version}.md"
    earlier = [c for c in candidates if os.path.basename(c) < current_name]
    if not earlier:
        return None, None
    prev_log = earlier[-1]
    m = re.search(r"run_log_(\d{4}-\d{2}-\d{2})_(v\d+)\.md$", os.path.basename(prev_log))
    if not m:
        return None, None
    return m.group(1), m.group(2)


# --------------------------------------------------------------------------
# Log parsing
# --------------------------------------------------------------------------

def parse_log(text):
    # Every log line is prefixed with a "[YYYY-MM-DD HH:MM:SS]" timestamp bracket.
    # Strip it so all downstream ^-anchored regexes work against the actual content.
    text = re.sub(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\s?", "", text, flags=re.MULTILINE)

    data = {}

    # 1.1 / 1.2 — forecast periods / rows
    m = re.search(r"Weather forecast periods fetched:\s*(\d+)", text)
    data["forecast_periods"] = int(m.group(1)) if m else None
    m = re.search(r"Weather forecast rows:\s*(\d+)", text)
    data["forecast_rows"] = int(m.group(1)) if m else None

    # 1.3 — station data complete (values may carry a unit suffix, e.g. "3.77 Inches")
    m = re.search(
        r"\[fetch_weather\] Station data complete: "
        r"avg_temp_today=(\S+)\s+avg_monthly_rainfall=([\d.]+\s*\S*)\s+current_monthly_rainfall=([\d.]+\s*\S*)",
        text,
    )
    data["station_complete"] = m.groups() if m else None

    # Climate normal high (F.4)
    highs = re.findall(r"Climate normal high for [\d-]+:\s*(\d+)°F", text)
    data["climate_normal_highs"] = [int(h) for h in highs]

    # Lake data (1.4 / 1.5)
    lakes = {}
    for m in re.finditer(
        r"Lake (\w+): today=([\d.]+)% one_week_ago=([\d.]+)% thirty_days_ago=([\d.]+)%",
        text,
    ):
        lakes[m.group(1)] = {
            "today": float(m.group(2)),
            "one_week_ago": float(m.group(3)),
            "thirty_days_ago": float(m.group(4)),
        }
    data["lakes"] = lakes

    # Phase timings (1.6 / 2.5 / 3.6 / P.1)
    phases = {}
    for m in re.finditer(r"Phase (\d) completed in ([\d.]+)s", text):
        phases[int(m.group(1))] = float(m.group(2))
    data["phase_timings"] = phases

    m = re.search(r"PROCESSING COMPLETE:\s*(\d+) stories in ([\d.]+)s", text)
    data["total_stories"] = int(m.group(1)) if m else None
    data["total_time"] = float(m.group(2)) if m else None

    # 2.0 — categories being fetched, with max
    cat_max = {}
    for m in re.finditer(
        r"^\s*([A-Za-z][A-Za-z0-9 ]+?):\s*.*?\.\.\.\s*\(max:\s*(\d+)\)",
        text, re.MULTILINE,
    ):
        cat_max[m.group(1).strip()] = int(m.group(2))
    data["categories_fetched"] = cat_max

    # Raw fetch total
    m = re.search(r"Fetched (\d+) stories from (\d+) categories", text)
    data["raw_total"] = int(m.group(1)) if m else None
    data["category_count_log"] = int(m.group(2)) if m else None

    # Feed results by category (raw, pre-dedup)
    raw_counts = {}
    block = re.search(
        r"\[DEBUG\] Feed results by category:(.*?)(?:\n\s*\n|\[DEBUG\]|Deduplicated:)",
        text, re.DOTALL,
    )
    if block:
        for m in re.finditer(r"^\s*([A-Za-z][A-Za-z0-9 ]+?):\s*(\d+)\s*stories", block.group(1), re.MULTILINE):
            raw_counts[m.group(1).strip()] = int(m.group(2))
    data["raw_counts_by_category"] = raw_counts

    # Dedup stats (2.4)
    m = re.search(
        r"Deduplicated:\s*(\d+)\s*->\s*(\d+)\s*stories\s*"
        r"\(age-filtered:\s*(\d+),\s*dup-filtered:\s*(\d+),\s*cross-cat-filtered:\s*(\d+)\)",
        text,
    )
    data["dedup"] = (
        {
            "pre": int(m.group(1)),
            "post": int(m.group(2)),
            "age_filtered": int(m.group(3)),
            "dup_filtered": int(m.group(4)),
            "cross_cat_filtered": int(m.group(5)),
        }
        if m
        else None
    )

    # Per-category count AFTER dedup
    post_counts = {}
    block = re.search(
        r"\[DEBUG\] Per-category story count AFTER dedup:(.*?)(?:\n\s*\n|Phase 2 completed)",
        text, re.DOTALL,
    )
    if block:
        for m in re.finditer(r"^\s*([A-Za-z][A-Za-z0-9 ]+?):\s*(\d+)\s*$", block.group(1), re.MULTILINE):
            post_counts[m.group(1).strip()] = int(m.group(2))
    data["post_dedup_by_category"] = post_counts

    # Summaries done / failed (3.2)
    m = re.search(r"Summaries done:\s*(\d+)\s*OK\s*/\s*(\d+)\s*failed", text)
    data["summaries_ok_failed"] = (int(m.group(1)), int(m.group(2))) if m else None

    # File written path (4.7)
    m = re.search(r"File written to (.+?)\s*$", text, re.MULTILINE)
    data["file_written_to"] = m.group(1).strip() if m else None

    # FAIL string scan (F.3)
    data["fail_count"] = len(re.findall(r"\bFAIL\b", text, re.IGNORECASE))

    # Unhandled errors (P.3)
    data["error_lines"] = re.findall(r"^.*(?:\bERROR\b|Traceback|Exception).*$", text, re.MULTILINE)

    return data


# --------------------------------------------------------------------------
# Output (rendered .md) parsing
# --------------------------------------------------------------------------

def parse_output(text):
    data = {}

    # Frontmatter
    fm_match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    frontmatter = yaml.safe_load(fm_match.group(1)) if fm_match else {}
    data["frontmatter"] = frontmatter or {}

    body = text[fm_match.end():] if fm_match else text

    # Unavailable string scan (F.3)
    data["unavailable_count"] = len(re.findall(r"Unavailable", body, re.IGNORECASE))

    # Weather table rows (1.2)
    forecast_rows = re.findall(r"^\|\s*\*\*\w+day.*?\|\s*$", body, re.MULTILINE)
    data["forecast_row_count"] = len(forecast_rows)

    # Climate normal high value rendered (F.4)
    m = re.search(r"Climate Normal High for today \S+\s*\|\s*(\d+)°F", body)
    data["climate_normal_high_rendered"] = int(m.group(1)) if m else None

    # Lake table rows
    lake_rows = re.findall(
        r"^\|\s*Lake (\w[\w ]*?)\s*\|\s*([\d.]+)%\s*\|\s*([\d.]+)%\s*\|\s*([\d.]+)%\s*\|\s*$",
        body, re.MULTILINE,
    )
    data["lake_rows"] = {
        name.strip(): {"today": float(t), "one_week_ago": float(w), "thirty_days_ago": float(m30)}
        for name, t, w, m30 in lake_rows
    }

    # Category sections in order: ## <Category> (N stories)
    section_order = []
    sections = {}
    section_iter = list(re.finditer(r"^#{2,3}\s+(.+?)(?:\s*\((\d+)\s*stories\))?\s*$", body, re.MULTILINE))
    for i, m in enumerate(section_iter):
        name = m.group(1).strip()
        count_str = m.group(2)
        start = m.end()
        end = section_iter[i + 1].start() if i + 1 < len(section_iter) else len(body)
        section_text = body[start:end]
        section_order.append(name)
        sections[name] = {
            "declared_count": int(count_str) if count_str is not None else None,
            "text": section_text,
        }
    data["section_order"] = section_order
    data["sections"] = sections

    # Parse individual stories within each (non-weather) section
    story_pattern = re.compile(
        r"(\d+)\.\s+\[(.*?)\]\((.*?)\)\s*\n"
        r"(.*?)\n"
        r"\*Originally published on:\*\s*(.*?)\s*\n"
        r"((?:\[\[.*?\]\]\s*)*)",
        re.DOTALL,
    )
    all_stories = {}
    for name, section in sections.items():
        if name == "Weather Forecast":
            continue
        stories = []
        for sm in story_pattern.finditer(section["text"]):
            idx, title, url, summary, pub, tags_raw = sm.groups()
            tags = re.findall(r"\[\[(.*?)\]\]", tags_raw or "")
            stories.append(
                {
                    "index": int(idx),
                    "title": title.strip(),
                    "url": url.strip(),
                    "summary": summary.strip(),
                    "published": pub.strip(),
                    "tags": tags,
                }
            )
        all_stories[name] = stories
    data["stories_by_category"] = all_stories

    return data


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def significant_words(s):
    words = re.findall(r"[a-zA-Z']+", s.lower())
    return {w for w in words if len(w) > 3 and w not in STOPWORDS}


def run_checks(config, log_data, out_data, prev_log_data, prev_out_data):
    r = Results()

    # ---------------- Phase 1: Weather ----------------
    if not log_data["forecast_periods"] or log_data["forecast_periods"] < 3:
        r.fail("1.1", f"Forecast periods fetched = {log_data['forecast_periods']} (expected >= 3)")

    if out_data["forecast_row_count"] != 3:
        r.fail("1.2", f"Rendered forecast rows = {out_data['forecast_row_count']} (expected 3)")

    if not log_data["station_complete"]:
        r.fail("1.3", "Station data incomplete or missing in log (avg_temp_today / avg_monthly_rainfall / current_monthly_rainfall)")
    else:
        for val, label in zip(log_data["station_complete"], ["avg_temp_today", "avg_monthly_rainfall", "current_monthly_rainfall"]):
            if val in ("None", "null", ""):
                r.fail("1.3", f"Station field '{label}' is {val}")

    configured_lakes = set(config.get("weather", {}).get("lake_urls", {}).keys())
    rendered_lakes = {k.lower().replace(" ", "_") for k in out_data["lake_rows"].keys()}
    # Try loose match: "Lake Conroe" -> "conroe"
    rendered_lake_names = {k.lower().replace("lake", "").strip().replace(" ", "_") for k in out_data["lake_rows"].keys()}
    missing_lakes = [lk for lk in configured_lakes if lk not in rendered_lake_names]
    if len(missing_lakes) == 1:
        r.warn("1.4", f"1 configured lake missing from output: {missing_lakes}")
    elif len(missing_lakes) > 1:
        r.fail("1.4", f"{len(missing_lakes)} configured lakes missing from output: {missing_lakes}")

    # 1.5 / F.4 — sane temp ranges, elevation mis-source, fallback default
    for high in log_data["climate_normal_highs"]:
        if high > 115:
            r.fail("F.4", f"Climate Normal High = {high}°F exceeds 115°F ceiling for 77316 — likely elevation field, not temperature")
        elif high == 95:
            r.warn("F.4", "Climate Normal High == 95°F exactly — matches known fallback default, verify live parse actually succeeded")
    if out_data["climate_normal_high_rendered"] is not None:
        h = out_data["climate_normal_high_rendered"]
        if h > 115:
            r.fail("1.5", f"Rendered Climate Normal High = {h}°F exceeds 115°F real-world ceiling for 77316")

    if 1 in log_data["phase_timings"] and log_data["phase_timings"][1] > 30:
        r.warn("1.6", f"Phase 1 took {log_data['phase_timings'][1]}s (> 30s)")

    # ---------------- Phase 2: RSS ----------------
    config_categories = {k: v for k, v in config.get("categories", {}).items()}
    rss_categories = {k: v for k, v in config_categories.items() if k != "Weather Forecast 77316"}  # 2.7

    log_cat_max = log_data["categories_fetched"]
    config_cat_max = {k: v.get("max_stories") for k, v in rss_categories.items()}

    if set(log_cat_max.keys()) != set(config_cat_max.keys()):
        missing_in_log = set(config_cat_max) - set(log_cat_max)
        extra_in_log = set(log_cat_max) - set(config_cat_max)
        r.fail("2.0", f"Category set mismatch between config.yaml and log. Missing in log: {missing_in_log or 'none'}; unexpected in log: {extra_in_log or 'none'}")
    else:
        for cat, cfg_max in config_cat_max.items():
            log_max = log_cat_max.get(cat)
            if log_max != cfg_max:
                r.fail("2.0", f"'{cat}' max mismatch: config.yaml={cfg_max}, log={log_max}")

    for cat in rss_categories:
        if cat not in log_data.get("raw_counts_by_category", {}):
            r.fail("2.1", f"Category '{cat}' missing from log's raw fetch results")

    for cat, raw_count in log_data.get("raw_counts_by_category", {}).items():
        if cat in rss_categories and raw_count == 0 and config_cat_max.get(cat, 0) > 0:
            r.warn("2.3", f"'{cat}' raw fetch count = 0 (configured max {config_cat_max.get(cat)})")
    if log_data.get("raw_total") == 0:
        r.fail("2.3", "Total raw stories fetched = 0 across all categories")

    if log_data.get("dedup"):
        d = log_data["dedup"]
        if d["pre"] > 0:
            removed_ratio = (d["pre"] - d["post"]) / d["pre"]
            if removed_ratio > 0.4:
                r.warn("2.4", f"Dedup removed {removed_ratio:.0%} of stories (pre={d['pre']}, post={d['post']})")
            if removed_ratio == 0 and d["pre"] >= 50:
                r.warn("2.4", f"Dedup removed 0% of {d['pre']} stories — dedup may not be running")

    if 2 in log_data["phase_timings"] and log_data["phase_timings"][2] > 10:
        r.warn("2.5", f"Phase 2 took {log_data['phase_timings'][2]}s (> 10s)")

    # 2.6 — known Hermes query typo
    hermes_query = config.get("categories", {}).get("Hermes Agent News", {}).get("query", "")
    if hermes_query.strip().lower() != "hermes agent":
        r.fail("2.6", f"'Hermes Agent News' query = '{hermes_query}' (expected 'hermes agent' — known typo bug)")

    # 2.2a — adaptive widening (SPEC-GAP: not implemented, report as known gap)
    for cat in rss_categories:
        post_count = log_data.get("post_dedup_by_category", {}).get(cat, 0)
        if post_count == 0:
            if cat == "Hermes Agent News":
                r.warn("2.2a", f"'{cat}' returned 0 stories — root cause already identified in 2.6 (query typo), not a widening gap")
            else:
                r.warn("2.2a", f"'{cat}' returned 0 stories, no widening evidence in log — known gap, adaptive widening not yet implemented (SPEC-GAP)")

    # ---------------- Phase 3: Enrichment & Summarization ----------------
    for cat in rss_categories:
        cfg_max = config_cat_max.get(cat)
        log_post = log_data.get("post_dedup_by_category", {}).get(cat)
        rendered_count = out_data["sections"].get(cat, {}).get("declared_count")
        if log_post is not None and cfg_max is not None and log_post < cfg_max:
            r.warn("3.1", f"'{cat}' under expected max: {log_post}/{cfg_max}")
        if log_post is not None and rendered_count is not None and log_post != rendered_count:
            r.fail("3.1", f"'{cat}' rendered count ({rendered_count}) != log post-dedup count ({log_post})")

    if out_data["unavailable_count"] > 0:
        r.fail("3.2", f"{out_data['unavailable_count']} occurrence(s) of 'Unavailable' in rendered output")
    if log_data.get("summaries_ok_failed"):
        ok, failed = log_data["summaries_ok_failed"]
        if failed == 0 and out_data["unavailable_count"] > 0:
            r.fail("3.2", f"Log reports 0 failed summaries but output has {out_data['unavailable_count']} unavailable — failure counter itself is broken")

    zero_overlap = []
    tag_over_limit = []
    tag_conflicts_hit = []
    generic_summaries = []
    max_tags = config.get("tagging_config", {}).get("max_tags", 5)
    conflict_pairs = [tuple(p) for p in config.get("tag_conflicts", [])]

    for cat, stories in out_data["stories_by_category"].items():
        for s in stories:
            if "unavailable" in s["summary"].lower():
                continue  # already counted under 3.2 — don't double-flag as a 3.3/3.5 issue

            hw = significant_words(s["title"])
            sw = significant_words(s["summary"])
            overlap = hw & sw
            if len(overlap) == 0:
                zero_overlap.append((cat, s["index"], s["title"]))
            elif len(overlap) == 1:
                r.warn("3.3", f"[{cat} #{s['index']}] only 1 shared keyword between headline and summary — borderline")

            if len(s["tags"]) > max_tags:
                tag_over_limit.append((cat, s["index"], len(s["tags"])))

            tagset = set(s["tags"])
            for a, b in conflict_pairs:
                if a in tagset and b in tagset:
                    tag_conflicts_hit.append((cat, s["index"], a, b))

            summary_lower = s["summary"].lower()
            if any(p in summary_lower for p in BOILERPLATE_PHRASES) and not re.search(r"\d", s["summary"]):
                generic_summaries.append((cat, s["index"]))

    for cat, idx, title in zero_overlap:
        r.fail("3.3", f"[{cat} #{idx}] zero shared keywords between headline and summary — possible misalignment: \"{title}\"")

    for cat, idx, n in tag_over_limit:
        r.fail("3.6", f"[{cat} #{idx}] has {n} tags (max {max_tags})")

    for cat, idx, a, b in tag_conflicts_hit:
        r.fail("3.7", f"[{cat} #{idx}] has conflicting tags '{a}' + '{b}'")

    total_story_count = sum(len(v) for v in out_data["stories_by_category"].values())
    if total_story_count > 0:
        generic_ratio = len(generic_summaries) / total_story_count
        for cat, idx in generic_summaries:
            r.warn("3.5", f"[{cat} #{idx}] summary looks generic/boilerplate")
        if generic_ratio > 0.10:
            r.fail("3.5", f"{generic_ratio:.0%} of summaries flagged as generic/boilerplate (> 10% threshold)")

    if 3 in log_data["phase_timings"] and log_data["phase_timings"][3] > 200:
        r.warn("3.timing", f"Phase 3 took {log_data['phase_timings'][3]}s (> 200s)")

    # ---------------- Phase 4: Output structure ----------------
    fm = out_data["frontmatter"]
    required_fm_fields = ["title", "date", "time_generated", "content_age_window", "story_count_total", "categories", "tags"]
    for field in required_fm_fields:
        if not fm.get(field) and fm.get(field) != 0:
            r.fail("4.1", f"Frontmatter missing or empty field: '{field}'")

    if fm.get("story_count_total") is not None and fm["story_count_total"] != total_story_count:
        r.fail("4.2", f"Frontmatter story_count_total ({fm['story_count_total']}) != actual rendered story count ({total_story_count})")

    rendered_category_headers = [n for n in out_data["section_order"] if n != "Weather Forecast"]
    if fm.get("categories") is not None and fm["categories"] != len(rendered_category_headers):
        r.fail("4.3", f"Frontmatter categories ({fm['categories']}) != actual section headers ({len(rendered_category_headers)})")

    for cat in rss_categories:
        if cat not in out_data["sections"]:
            r.warn("4.4", f"'{cat}' has no section header in rendered output at all")

    for cat, stories in out_data["stories_by_category"].items():
        for s in stories:
            if not s["url"]:
                r.fail("4.5", f"[{cat} #{s['index']}] missing URL")
            if not s["published"]:
                r.fail("4.6", f"[{cat} #{s['index']}] missing publish timestamp")

    expected_news_dir = config["directories"]["news_dir"]
    if log_data.get("file_written_to"):
        written_dir = os.path.dirname(log_data["file_written_to"])
        if os.path.normpath(written_dir) != os.path.normpath(expected_news_dir):
            r.fail("4.7", f"Log wrote to '{written_dir}', expected config.yaml's directories.news_dir = '{expected_news_dir}'")

    required_tag_segments = config.get("runtime", {}).get("frontmatter_tag_segments", [])
    fm_tags = set(fm.get("tags", []) or [])
    for seg in required_tag_segments:
        if seg not in fm_tags:
            r.fail("4.8", f"Frontmatter missing required tag segment: '{seg}'")

    priority = [c for c in config.get("category_priority", []) if c != "Weather Forecast 77316"]
    if priority:
        expected_order = [c for c in priority if c in rendered_category_headers]
        actual_order = [c for c in rendered_category_headers if c in priority]
        if expected_order != actual_order:
            r.fail("4.9", f"Section order mismatch. Expected: {expected_order} | Actual: {actual_order}")

    # ---------------- Cross-cutting: Live data integrity ----------------
    if log_data.get("fail_count", 0) > 0:
        r.warn("F.3", f"Log contains {log_data['fail_count']} occurrence(s) of 'FAIL'")
    if out_data.get("unavailable_count", 0) > 0:
        r.warn("F.3", f"Output contains {out_data['unavailable_count']} occurrence(s) of 'Unavailable'")

    # F.2 — indirect fallback detection vs. previous run
    if prev_log_data and prev_out_data:
        prev_station = prev_log_data.get("station_complete")
        cur_station = log_data.get("station_complete")
        if prev_station and cur_station and prev_station == cur_station:
            r.warn("F.2", "avg_temp_today / rainfall fields identical to previous run — possible frozen/fallback data")

        prev_lakes = prev_log_data.get("lakes", {})
        cur_lakes = log_data.get("lakes", {})
        for lake in cur_lakes:
            if lake in prev_lakes and cur_lakes[lake] == prev_lakes[lake]:
                r.warn("F.2", f"Lake '{lake}' values identical to previous run")

        for cat in rss_categories:
            cur_urls = {s["url"] for s in out_data["stories_by_category"].get(cat, [])}
            prev_urls = {s["url"] for s in prev_out_data["stories_by_category"].get(cat, [])}
            if cur_urls and prev_urls:
                overlap = len(cur_urls & prev_urls) / len(cur_urls)
                if overlap > 0.9:
                    r.warn("F.2", f"'{cat}' story URLs {overlap:.0%} identical to previous run — feed may not be refreshing")
    else:
        r.info("F.2", "No previous run found for cross-run comparison — skipping frozen-data checks")

    if 1 in log_data["phase_timings"] and log_data["phase_timings"][1] < 2:
        r.warn("F.2", f"Phase 1 completed in {log_data['phase_timings'][1]}s — implausibly fast, possible skipped live call")

    # ---------------- Pipeline-level gates ----------------
    if log_data.get("total_time") is not None and log_data["total_time"] > 300:
        r.warn("P.1", f"Total runtime {log_data['total_time']}s exceeds 300s gate")

    if log_data.get("total_stories") is not None:
        if log_data["total_stories"] < 20 or log_data["total_stories"] > 100:
            r.warn("P.2", f"Total story count {log_data['total_stories']} outside expected 20-100 band")

    if log_data.get("error_lines"):
        for line in log_data["error_lines"]:
            r.fail("P.3", f"Unhandled error line in log: {line.strip()}")

    return r


# --------------------------------------------------------------------------
# Report writing
# --------------------------------------------------------------------------

def build_report(date, version, results, log_data):
    status = results.status()
    lines = [f"Run: DailyBrief-{date}_{version}", f"Status: {status}", ""]

    fails = results.by_level("FAIL")
    warns = results.by_level("WARN")
    infos = results.by_level("INFO")

    lines.append(f"FAIL ({len(fails)}):")
    if fails:
        for cid, msg in fails:
            lines.append(f"  - [{cid}] {msg}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append(f"WARN ({len(warns)}):")
    if warns:
        for cid, msg in warns:
            lines.append(f"  - [{cid}] {msg}")
    else:
        lines.append("  (none)")
    lines.append("")

    if infos:
        lines.append(f"INFO ({len(infos)}):")
        for cid, msg in infos:
            lines.append(f"  - [{cid}] {msg}")
        lines.append("")

    total_time = log_data.get("total_time")
    if total_time is not None:
        gate_note = "within 300s gate" if total_time <= 300 else "EXCEEDS 300s gate"
        lines.append(f"Timing: {total_time}s total ({gate_note})")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Validate a Daily Brief pipeline run against DailyBrief_TestHarness.md")
    ap.add_argument("--config", required=True, help="Path to config.yaml")
    ap.add_argument("--date", required=True, help="Run date, YYYY-MM-DD")
    ap.add_argument("--version", required=True, help="Run version, e.g. v01")
    ap.add_argument("--prev-date", help="Explicit previous run date for F.2 comparison")
    ap.add_argument("--prev-version", help="Explicit previous run version for F.2 comparison")
    ap.add_argument("--no-write", action="store_true", help="Print report only, don't write validation_log file")
    args = ap.parse_args()

    config = load_config(args.config)
    log_dir, news_dir, log_path, output_path = resolve_paths(config, args.date, args.version)

    if not os.path.exists(log_path):
        sys.exit(f"Log file not found: {log_path}")
    if not os.path.exists(output_path):
        sys.exit(f"Output file not found: {output_path}")

    with open(log_path, "r", encoding="utf-8") as f:
        log_text = f.read()
    with open(output_path, "r", encoding="utf-8") as f:
        output_text = f.read()

    log_data = parse_log(log_text)
    out_data = parse_output(output_text)

    prev_date, prev_version = args.prev_date, args.prev_version
    if not prev_date or not prev_version:
        prev_date, prev_version = find_previous_run(log_dir, args.date, args.version)

    prev_log_data, prev_out_data = None, None
    if prev_date and prev_version:
        _, _, prev_log_path, prev_output_path = resolve_paths(config, prev_date, prev_version)
        if os.path.exists(prev_log_path) and os.path.exists(prev_output_path):
            with open(prev_log_path, "r", encoding="utf-8") as f:
                prev_log_data = parse_log(f.read())
            with open(prev_output_path, "r", encoding="utf-8") as f:
                prev_out_data = parse_output(f.read())

    results = run_checks(config, log_data, out_data, prev_log_data, prev_out_data)
    report = build_report(args.date, args.version, results, log_data)

    print(report)

    if not args.no_write:
        validation_path = os.path.join(log_dir, f"validation_log_{args.date}_{args.version}.md")
        with open(validation_path, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"\nWritten to: {validation_path}")

    status = results.status()
    sys.exit({"PASS": 0, "WARN": 1, "FAIL": 2}[status])


if __name__ == "__main__":
    main()
