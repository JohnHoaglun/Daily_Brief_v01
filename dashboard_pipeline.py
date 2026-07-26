#!/usr/bin/env python3
"""
Daily Brief Pipeline v1.0.0
============================

Full working base model.

BETA07: RSS snippets as primary summary context; headline fallback for low-context.
BETA08: BATCH summarization â€” single Ollama call processes all 40-90 stories at once (2.5x speedup over individual calls). 
        ARTICLE EXTRACTION REMOVED â€” Google News provides only internal article IDs, not real publisher URLs.
        ALERTS: also batched into single call. Removed threading deadlocks from server-side single-thread bottleneck.
        FILTER: excludes Conroe TX property listings; Big Tech query fixed.
BETA09 (current): BATCH summarization redesigned â€” one Ollama call per category instead of all stories combined,
                  prevents context overflow (was 92K chars â†’ now ~400-1200 per batch). Switched to gemma4:e2b 
                  (~6s per batch vs ~45s with qwen3.6-256k). Google News tracking URLs handled via title+snippet context.
BETA11: RSS entries sorted by pub_date (newest first) instead of taking arbitrary first N stories from Google News RSS feed.
BETA12: Updated version bump â€” documented in all markdown files (PROJECT, SUMMARY, PLAN, README).

No API keys required. All sources are free and keyless.

Run: python dashboard_pipeline.py
"""

import asyncio
import aiohttp
import feedparser
from concurrent.futures import ThreadPoolExecutor
from functools import cmp_to_key
from bs4 import BeautifulSoup
import ollama
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import os
import time
from email.utils import parsedate_to_datetime
import threading
import re

# Load configuration at the top to avoid import issues
# We import config after defining all the necessary functions and constants
# Then set all values from config properly

# The main fix: properly load config at the beginning and only once
# Avoid circular imports and make sure all configuration is loaded before we start doing work
from config import *

# Ollama client
_llm_client = ollama.Client(host=OLLAMA_HOST, timeout=180)

# Pull configuration values after importing config
# Note: These are already loaded globally by config.py via the globals().update(locals()) pattern. 
# We just ensure they are available in the local scope if needed.
LLM_MODEL = LLM_MODEL
LOG_DIR = LOG_DIR
NEWS_DIR = NEWS_DIR
OUTPUT_DIR = NEWS_DIR  # For backwards compatibility with existing code

# Log file lives in the logs directory inside Obsidian vault (unique .md per run)
RUN_LOGFILE = None   # set dynamically at start of each run as .md
log_lock = threading.Lock()

# Thread pool with 3 workers to match Ollama NUM_PARALLEL=3 limit
_executor = ThreadPoolExecutor(max_workers=3)

# Browser pool for Playwright

# Configuration from config
DEFAULT_AGE_LIMIT_HOURS = DEFAULT_AGE_LIMIT_HOURS
CATEGORY_AGE_LIMITS = CATEGORY_AGE_LIMITS_EFFECTIVE

# Timing measurements for phase breakdowns
PHASE_TIMINGS = {}


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


# -- CONFIGURATION ----------------------------------------------------------

WEATHER_LAT = WEATHER_LAT
WEATHER_LON = WEATHER_LON
USER_AGENT = USER_AGENT
WEATHER_POINT_URL = WEATHER_POINT_URL
WEATHER_POINT_FORECAST_SUFFIX = WEATHER_POINT_FORECAST_SUFFIX
WEATHER_WUNDERGROUND_STATION_ID = WEATHER_WUNDERGROUND_STATION_ID
WUNDERGROUND_MONTHLY_TEMPLATE = WUNDERGROUND_MONTHLY_TEMPLATE
WEATHER_LAKE_URLS = WEATHER_LAKE_URLS or {}
USER_AGENT_WEATHER_SUFFIX = USER_AGENT_WEATHER_SUFFIX
WEATHER_SECTION_TITLE = WEATHER_SECTION_TITLE
DATE_OVERRIDE = DATE_OVERRIDE

# Load categories from config if available and correctly processed
if 'CATEGORIES' in globals() and CATEGORIES:
    # If CATEGORIES is provided in config, use it directly
    pass  # Already loaded via config.py
else:
    raise ValueError("CATEGORIES must be properly defined in config.py")

# RSS configuration from config
RSS_BASE = RSS_BASE
RSS_PARAMS = RSS_PARAMS

# Timezone from config (with runtime-safe fallback)
TIMEZONE = TIMEZONE
try:
    ACTIVE_TIMEZONE = ZoneInfo(TIMEZONE)
except Exception:
    ACTIVE_TIMEZONE = timezone.utc
    TIMEZONE = "UTC"
SUMMARY_PROMPT = SUMMARY_PROMPT
SYSTEM_BATCH_PROMPT = SYSTEM_BATCH_PROMPT
SYSTEM_ALERT_PROMPT = SYSTEM_ALERT_PROMPT
LLM_SUMMARY_OPTIONS = LLM_SUMMARY_OPTIONS
LLM_ALERT_OPTIONS = LLM_ALERT_OPTIONS
LLM_SUMMARY_CONTEXT_CHARS = LLM_SUMMARY_CONTEXT_CHARS
LLM_CONTEXT_PREVIEW_CHARS = LLM_CONTEXT_PREVIEW_CHARS
LLM_SUMMARY_TRIM_MIN_CHARS = LLM_SUMMARY_TRIM_MIN_CHARS
FRONTMATTER_TAG_SEEDS = FRONTMATTER_TAG_SEEDS
FRONTMATTER_FALLBACK_TAG = FRONTMATTER_FALLBACK_TAG
MAX_LOG_VERSIONS = MAX_LOG_VERSIONS
DEFAULT_CONTENT_AGE_WINDOW_HOURS = 48
DEFAULT_CATEGORIES_COUNT = getattr(config, 'CATEGORIES', {}).get('count_for_report', 15) if 'config' in globals() else 15


def _safe_text(value, fallback="N/A"):
    """Normalize user-facing text values for markdown rendering."""
    if value is None:
        return fallback
    try:
        s = str(value).strip()
        return s if s else fallback
    except Exception:
        return fallback


def _present_weather_value(value, fallback="Unavailable"):
    if value is None:
        return fallback
    try:
        text = str(value).strip()
        if not text or text.lower() in {"none", "n/a", "na"}:
            return fallback
        # Do NOT replace "Dynamic" with the fallback. "Dynamic" is a valid placeholder used for forecasted periods.
        return text
    except Exception:
        return fallback


def get_reference_datetime():
    """Return current runtime date/time in configured timezone, optionally overridden."""
    if DATE_OVERRIDE:
        try:
            dt = datetime.fromisoformat(str(DATE_OVERRIDE))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=ACTIVE_TIMEZONE)
            return dt.astimezone(ACTIVE_TIMEZONE)
        except Exception:
            pass
    return datetime.now(ACTIVE_TIMEZONE)


def get_weather_label_for_offset(reference, offset_days, style="long"):
    """Build forecast row date label from dynamic date and offset."""
    target = reference.date() + timedelta(days=offset_days)
    weekday = target.strftime("%A")
    month_day = f"{target.strftime('%B')} {target.day}"
    if offset_days == 0:
        suffix = "Today"
    elif offset_days == 1:
        suffix = "Tomorrow"
    elif offset_days == 2:
        suffix = "In 2 Days"
    else:
        suffix = target.strftime("%m/%d")
    if style == "long":
        return f"**{weekday}, {month_day} ({suffix})**"
    return f"{weekday}, {month_day} ({suffix})"


def strip_html(html_text):
    """Remove HTML tags from a string, leaving only plain text."""
    if not html_text:
        return ""
    s = BeautifulSoup(html_text, "html.parser")
    return s.get_text(separator=" ", strip=True)


def normalize_title(title):
    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    return (parts[0] if parts else title.lower().strip())[:80].lower()


def parse_feed_date(entry):
    """Parse entry published date into a datetime object."""
    raw_date = None
    for attr in ("published", "updated"):
        val = entry.get(attr)
        if val and isinstance(val, str) and val.strip():
            raw_date = val.strip()
            break
    if not raw_date:
        return None
    try:
        dt = parsedate_to_datetime(raw_date)
        return dt
    except Exception:
        pass
    stripped = raw_date.strip()
    tz = ACTIVE_TIMEZONE
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            result = datetime.strptime(stripped, fmt)
            return result.replace(tzinfo=tz)
        except ValueError:
            continue
    return None


def format_pub_date(raw):
    """Format a publication date into readable form."""
    if not raw:
        return None
    if isinstance(raw, datetime):
        tz = raw.strftime("%Z") if raw.tzinfo else ""
        # Show full datetime instead of just date
        return raw.strftime(f"%Y-%m-%d %H:%M:%S {tz}").strip()
    stripped = raw.strip()
    if len(stripped) >= 10 and stripped[:4].isdigit():
        # Show the entire datetime, not just date part
        return stripped
    return stripped[:40]


def _sort_entries(a, b):
    """Sort entries by publication date descending (newest first)."""
    pa, pb = a[3], b[3]  # pub_dt tuples
    if pa is None and pb is None:
        return 0
    if pa is None:
        return 1   # push None dates to end
    if pb is None:
        return -1
    return (pb - pa).total_seconds()  # newest first


# -- HTTP helpers (async) ---------------------------------------------------

def build_rss_url(query):
    return f"{RSS_BASE}{query}{RSS_PARAMS}"


async def fetch_feed(session, name, rss_url, max_stories):
    try:
        async with session.get(rss_url, headers={"User-Agent": USER_AGENT}, timeout=10) as resp:
            text = await resp.text()
        feed = feedparser.parse(text)
        entries = []
        for e in feed.entries:
            title = (e.get("title", "") or "").strip() if isinstance(e.get("title"), str) else ""
            link = e.get("link") or "#"
            raw = (e.get("summary") or e.get("description") or "").strip() if isinstance(e.get("summary"), str) and e["summary"] else ""
            pub_dt = parse_feed_date(e)
            # Strip HTML from snippet so we can measure REAL text length for extraction decision
            plain_snippet = strip_html(raw)
            if title and link:
                entries.append((title, link, plain_snippet, pub_dt))
        
        # Sort entries by publication date (newest first) then take top N
        entries.sort(key=cmp_to_key(_sort_entries))
        entries = entries[:max_stories]
        
        return (name, entries)
    except Exception as e:
        log(f"  WARNING {name}: feed fetch failed ({e})")
        return (name, [])

def _parse_date_for_weather(raw_value):
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).astimezone(ACTIVE_TIMEZONE)
    except Exception:
        pass
    try:
        return datetime.strptime(raw_value, "%Y-%m-%dT%H:%M:%S%z").astimezone(ACTIVE_TIMEZONE)
    except Exception:
        pass
    try:
        return datetime.strptime(raw_value, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=ACTIVE_TIMEZONE)
    except Exception:
        try:
            # Example: 2026-07-18T20:00:00-05:00[America/Chicago] (rare but seen in weather payloads)
            cleaned = raw_value.split("[", 1)[0]
            return datetime.fromisoformat(cleaned).astimezone(ACTIVE_TIMEZONE)
        except Exception:
            return None


def _extract_first_match(text, patterns):
    if not text:
        return None
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1)
    return None


async def _fetch_json(session, url, suffix=""):
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENT}, timeout=15) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                log(f"  [fetch_json error] {url} returned status {resp.status}")
                return None
    except Exception:
        return None


async def _fetch_text(session, url, suffix=""):
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENT}, timeout=15) as resp:
            if resp.status == 200:
                return await resp.text()
            else:
                log(f"  [fetch_text error] {url} returned status {resp.status}")
                return None
    except Exception:
        return None


def _coerce_percent(value):
    if value is None:
        return None
    text = _safe_text(value)
    m = re.match(r"^(\d+(?:\.\d+)?).*?$", text)
    if not m:
        return None
    try:
        return f"{float(m.group(1)):.1f}%"
    except Exception:
        return None


def is_obituary_title(title):
    """Check if a title contains obituary-related keywords."""
    keywords = ["obituary", "passed away", "death notice", "funeral services for", "memorial service for"]
    title_lower = title.lower()
    return any(kw in title_lower for kw in keywords)


    if text is None:
        return None
    m = re.search(r"(-?\d{1,3}(?:\.\d+)?)", _safe_text(text))
    if not m:
        return None
    try:
        val = float(m.group(1))
        if 30.0 <= val <= 140.0:
            return f"{int(val) if val.is_integer() else val}"
    except Exception:
        return None
        return None


def _parse_climate_summary(text, current_month):
    """Parse Houston HGX climate summary text for monthly normals and current values.

    Returns a dict with:
      - avg_monthly_rainfall: normal precipitation for the current month
      - current_monthly_rainfall: best-effort total/value for current month
    """
    if not text:
        return {"avg_monthly_rainfall": None, "current_monthly_rainfall": None}

    month_names = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    ]
    month_short = current_month.strftime("%b")
    month_idx = month_names.index(month_short) if month_short in month_names else 0

    def _clean_number(value):
        if value is None:
            return None
        cleaned = _safe_text(value).replace(",", "").replace(" ", "")
        m = re.search(r"\d+(?:\.\d+)?", cleaned)
        if not m:
            return None
        try:
            return float(m.group(0))
        except Exception:
            return None

    soup = BeautifulSoup(text, "html.parser")
    tables = soup.find_all("table")
    avg_rainfall = None
    current_rainfall = None

    # Parse normals table first: row labeled "Rain Totals (in)" with Jan..Dec columns.
    for table in tables:
        rows = table.find_all("tr")
        cleaned_rows = []
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if cells:
                cleaned_rows.append(cells)
        for i, row in enumerate(cleaned_rows):
            if not row or "rain totals" not in row[0].lower():
                continue
            header_row = None
            for j in range(i - 1, max(-1, i - 4), -1):
                if j < 0:
                    continue
                candidate = [c.lower() for c in cleaned_rows[j]]
                if len(candidate) >= 12 and any(month.lower() in candidate for month in month_names):
                    header_row = cleaned_rows[j]
                    break
            if header_row:
                # map by fixed offset: first value corresponds to Jan, then Feb...
                norm_col = month_idx + 1
                if len(row) > norm_col:
                    avg_rainfall = _clean_number(row[norm_col])
            # Keep first matching normals row.
            if avg_rainfall is not None:
                break
        if avg_rainfall is not None:
            break

    # Parse annual summary only for current-year rows when available; do not
    # fallback to older years for current-month values.
    target_year = str(current_month.year)
    for table in tables:
        rows = table.find_all("tr")
        cleaned_rows = []
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if cells:
                cleaned_rows.append(cells)

        # Find row for current year and strip departure text from month cells.
        year_row = None
        for row in cleaned_rows:
            if row and _safe_text(row[0]).strip() == target_year and len(row) > month_idx + 1:
                year_row = row
                break
        if year_row is None:
            continue

        for row in cleaned_rows:
            if not row or "rain totals" not in row[0].lower():
                continue
            if row is year_row or all(c == "" for c in row):
                continue
            rain_col = month_idx + 1
            if len(row) > rain_col:
                candidate_text = _safe_text(row[rain_col])
                candidate = _clean_number(candidate_text.split("(")[0].strip())
                if candidate is not None:
                    current_rainfall = candidate
                    break
        if current_rainfall is not None:
            break

    # Keep values in plausible range and distinct when one-side data is absent.
    if avg_rainfall is not None and not (0.0 <= avg_rainfall <= 40.0):
        avg_rainfall = None
    if current_rainfall is not None and not (0.0 <= current_rainfall <= 40.0):
        current_rainfall = None

    return {
        "avg_monthly_rainfall": avg_rainfall,
        "current_monthly_rainfall": current_rainfall,
    }


def _parse_wu_monthly_precipitation(html, start_date, end_date):
    """Extract monthly precipitation summary total (High) from WU monthly range page."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    if not text:
        return None

    # Format expected month-to-date labels for date-range matching.
    def _pretty_date(d):
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            return f"{dt.strftime('%B')} {dt.day}, {dt.year}"
        except Exception:
            return None

    start_label = _pretty_date(start_date)
    end_label = _pretty_date(end_date)

    # Prefer the Summary block that matches the active date range (if present).
    start_idx = text.find("Summary")
    if start_idx == -1:
        return None

    # Heuristic trim: summary block is before the next major page section marker.
    end_idx = text.find("graph", start_idx)
    candidate = text[start_idx:end_idx] if end_idx != -1 else text[start_idx:]
    # If no explicit range labels in summary, fall back to the first candidate summary block.
    m = re.search(
        r"Summary.*?Precipitation\s+([0-9]+(?:\.[0-9]+)?)\s*°?\s*in",
        candidate,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if m and start_label and end_label:
        if not (start_label in candidate and end_label in candidate):
            date_pattern = re.escape(f"{start_label} - {end_label}")
            dated_match = re.search(
                rf"{date_pattern}.*?Precipitation\s+([0-9]+(?:\.[0-9]+)?)\s*°?\s*in",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            # Keep the broader Summary match if date-specific extraction fails.
            if dated_match:
                m = dated_match
    if not m:
        return None
    try:
        val = float(m.group(1))
    except Exception:
        return None
    if 0.0 <= val <= 40.0:
        return val
    return None


async def _fetch_station_monthly_rainfall(session, reference):
    """Fetch station weather summary for current-month rain and Houston normals for average."""
    station_url = WUNDERGROUND_MONTHLY_TEMPLATE.format(
        station_id=WEATHER_WUNDERGROUND_STATION_ID,
        date=reference.strftime("%Y-%m-%d")
    )
    # Build a month-to-date range URL for the station summary.
    month_start = reference.replace(day=1).strftime("%Y-%m-%d")
    month_end = reference.strftime("%Y-%m-%d")
    station_range_url = re.sub(
        r"/graph/[^/]+/[^/]+/monthly$",
        f"/graph/{month_start}/{month_end}/monthly",
        station_url,
    )

    station_html = await _fetch_text(session, station_range_url)
    if not station_html:
        log(f"  Station monthly rainfall: no station monthly range html fetched ({station_range_url})")

    station_current_rain = _parse_wu_monthly_precipitation(station_html, month_start, month_end)
    if station_current_rain is not None:
        log(f"  Station monthly rainfall: parsed station current month value {station_current_rain}")

    # Houston monthly normals (average).
    climate_url = "https://www.weather.gov/hgx/climate_iah_normals_summary"
    html = await _fetch_text(session, climate_url)
    if not html:
        log("  Station monthly rainfall: no climate page HTML fetched")
        return {
            "avg_monthly_rainfall": None,
            "current_monthly_rainfall": station_current_rain,
        }

    # Use original HTML for table parsing (do not strip text).
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    log(f"  Station monthly rainfall: climate page text length {len(text)}")
    parsed = _parse_climate_summary(html, reference.date())

    avg_rain = parsed.get("avg_monthly_rainfall")
    curr_rain = parsed.get("current_monthly_rainfall")

    def _safe_rainfall(v):
        if v is None:
            return None
        try:
            val = float(v)
            if 0.0 <= val <= 40.0:
                return f"{val}"
        except Exception:
            return None
        return None

    return {
        "avg_monthly_rainfall": _safe_rainfall(avg_rain),
        "current_monthly_rainfall": f"{station_current_rain}" if station_current_rain is not None else _safe_rainfall(curr_rain),
    }


def _safe_sentence_summary(text):
    if not text:
        return ""
    s = re.sub(r"\s+", " ", str(text)).strip()
    s = s.replace("..", ".").strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", s)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 3:
        return " ".join(parts[:3]).strip()
    return s


def _count_sentences(text):
    if not text:
        return 0
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", re.sub(r"\s+", " ", str(text)).strip())
    parts = [p.strip() for p in parts if p.strip()]
    return len(parts)


def parse_batch_summary_response(response, count):
    """
    Parse summaries from flexible batch output formats:
      ### 1. ..., 1. ..., 1) ..., STORY_0 ...
    Returns list of length count.
    """
    results = ["" for _ in range(count)]
    if not response:
        return results

    lines = response.splitlines()

    heading_re = re.compile(
        r"^\s*(?:###\s*)?(?:\*\*)?(?:(\d+)[\)\.]\s*|STORY[_\-\s]*(\d+)\s*[:\)]?\s*)(.*)$",
        flags=re.IGNORECASE
    )

    headers = []
    story_key_re = re.compile(r"STORY[_\-\s]*(\d+)", flags=re.IGNORECASE)

    for i, line in enumerate(lines):
        m = heading_re.match(line.strip())
        if m:
            idx = m.group(1) or m.group(2)
            if not idx:
                continue
            idx = int(idx)
            if m.group(1) is not None and idx > 0:
                idx -= 1
            if 0 <= idx < count:
                headers.append((i, idx, line))

            m2 = story_key_re.match(line.strip())
            if m2 and m2.group(1):
                idx = int(m2.group(1))
                if idx > 0:
                    idx -= 1
                if 0 <= idx < count:
                    if (i, idx, line) not in headers:
                        headers.append((i, idx, line))

    # If the model used a 'Summary of ...:' style heading, capture those too.
    if not headers:
        for i, line in enumerate(lines):
            l = line.lower()
            if l.startswith("summary") and ":" in line and count > 1:
                headers.append((i, None, line))

    if not headers:
        # If the model returned a single plain paragraph for one story, use it as fallback.
        if count == 1:
            cleaned = "\n".join(
                [l for l in lines if l.strip() and not l.strip().startswith("Here are") and not l.strip().startswith("***")]
            ).strip()
            if cleaned:
                results[0] = _safe_sentence_summary(cleaned)
        return results

    # Normalize duplicate headers and assign missing indexes in sequence.
    normalized = []
    for line_idx, idx, raw in headers:
        if idx is None:
            normalized.append((line_idx, None, raw))
        else:
            normalized.append((line_idx, idx, raw))
    headers = normalized
    if count > 1 and all(h[1] is None for h in headers):
        # No explicit index markers; distribute chunks sequentially across lines.
        fallback_chunks = []
        current = []
        for i, line in enumerate(lines):
            if line.strip().lower().startswith("summary of") and i > 0:
                if current:
                    fallback_chunks.append(current)
                    current = []
            current.append(line)
        if current:
            fallback_chunks.append(current)
        for i, chunk in enumerate(fallback_chunks[:count]):
            results[i] = _safe_sentence_summary("\n".join(chunk).strip())
        return results

    for n, (line_idx, idx, raw) in enumerate(headers):
        start = line_idx
        end = len(lines)
        if n + 1 < len(headers):
            end = headers[n + 1][0]

        chunk = "\n".join(lines[start:end]).strip()
        if not chunk:
            continue
        chunk_lines = [l for l in lines[start:end] if l.strip()]

        head = raw.strip()
        summary = head
        for sep in (":", "-", ")"):
            _, sep_token, rest = head.partition(sep)
            if sep_token:
                summary = rest.strip()
                break
        # If heading was followed by summary text on later lines (most common case), prefer that.
        if len(chunk_lines) > 1:
            summary = "\n".join(chunk_lines[1:]).strip()
        elif not summary and "." in head:
            summary = head.split(".", 1)[1].strip()
        if not summary:
            summary = "\n".join(chunk_lines).strip()

        summary = re.sub(r"^\*+\s*", "", summary)
        summary = re.sub(r"^(###\s*)?\**\d+[\)\.]\s*", "", summary)
        summary = re.sub(r"^Summary:\s*", "", summary, flags=re.IGNORECASE)
        summary = re.sub(r"\*\*|\*{2,}$", "", summary).strip()
        results[idx] = _safe_sentence_summary(summary)

    return results


async def _fetch_station_metrics(session, station_id, reference):
    """Fetch station metrics from Wunderground monthly dashboard table.

    Returns avg_temp_today (from the Average Temperature row) and
    current_monthly_rainfall (from the Precipitation row).
    avg_monthly_rainfall is NOT available on this page — it comes from
    _fetch_station_monthly_rainfall via climate.gov.
    """
    payload = {"avg_temp_today": None, "avg_monthly_rainfall": None, "current_monthly_rainfall": None}
    template_date = reference.strftime("%Y-%m-%d")
    url = WUNDERGROUND_MONTHLY_TEMPLATE.format(station_id=station_id, date=template_date)
    html = await _fetch_text(session, url)
    if not html:
        log("  WARNING Weather station metrics unavailable (no content).")
        return payload

    soup = BeautifulSoup(html, "html.parser")

    # Parse the monthly summary table:
    # Structure: tr[0] = ['', 'High', 'Low', 'Average'] (header)
    #            tr[1..] = ['Temperature', '101.8°F', '72.1°F', '83.1°F'] (data rows)
    avg_temp = None
    current_precip = None

    for table in soup.find_all("table"):
        all_rows = []
        for row in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) >= 4:
                all_rows.append(cells)
        if not all_rows:
            continue

        # The first row is the header: ['', 'High', 'Low', 'Average']
        # Data rows start from index 1
        header_text = " ".join(c.lower() for c in all_rows[0])
        if "average" not in header_text:
            continue
        if "high" not in header_text and "low" not in header_text:
            continue

        # Data rows start at index 1
        for row in all_rows[1:]:
            label = row[0].lower()
            # Extract numeric values from cells (skip first cell which is the label)
            values = []
            for cell in row[1:]:
                m = re.search(r"(\d+\.?\d*)", cell)
                if m:
                    values.append(float(m.group(1)))
                else:
                    values.append(None)

            if "temperature" in label:
                # Average temp is the last value (column: High, Low, Average)
                if len(values) >= 3 and values[2] is not None:
                    avg_temp = values[2]
                elif values and values[-1] is not None:
                    avg_temp = values[-1]
            elif "precipitation" in label or "rain" in label:
                # Current monthly total is the first numeric value
                if values and values[0] is not None:
                    current_precip = values[0]

    # Coerce temperature
    avg_temp = _coerce_temperature_f(avg_temp)
    if avg_temp is not None:
        payload["avg_temp_today"] = f"{avg_temp}°F"

    # Coerce precipitation
    if current_precip is not None:
        try:
            val = float(current_precip)
            if 0.0 <= val <= 60.0:
                payload["current_monthly_rainfall"] = f"{val} Inches"
        except Exception:
            pass

    return payload


async def _extract_lake_value(session, key, url, reference):
    today = reference.date()
    result = {"today": None, "one_week_ago": None, "thirty_days_ago": None}
    targets = [
        ("today", today),
        ("one_week_ago", today - timedelta(days=7)),
        ("thirty_days_ago", today - timedelta(days=30)),
    ]

    html = await _fetch_text(session, url)
    if not html:
        log(f"  WARNING Lake data unavailable ({key}): no html.")
        return result

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    parsed_pairs = []

    for row in soup.select("tbody tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
        if len(cells) < 3:
            continue
        label = _safe_text(cells[0]).strip().lower()
        raw_date = _safe_text(cells[1]).strip()
        raw_percent = _safe_text(cells[2]).strip()
        percent = _coerce_percent(raw_percent)
        if not percent:
            continue

        if "today" in label or "current" in label:
            result["today"] = percent
        elif "1 week ago" in label or "week ago" in label or "7 day" in label:
            result["one_week_ago"] = percent
        elif "30 days ago" in label or "thirty days ago" in label or "1 month ago" in label or "30d" in label:
            result["thirty_days_ago"] = percent

        try:
            row_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
            parsed_pairs.append((row_date, percent))
        except Exception:
            pass

    # Map by date when label values are missing.
    for label, target_date in targets:
        if result.get(label):
            continue
        exact = next((val for (d, val) in parsed_pairs if d == target_date), None)
        if exact:
            result[label] = exact
            continue
        if not parsed_pairs:
            break
        before = [(d, val) for d, val in parsed_pairs if d <= target_date]
        candidates = before if before else parsed_pairs
        pick = min(candidates, key=lambda pair: abs((pair[0] - target_date).days))
        result[label] = pick[1]

    # Legacy fallback path if table parsing fails.
    if any(v is None for v in result.values()):
        for m in re.finditer(r"(\d{1,3}(?:\.\d+)?)\s*%", text):
            all_pct = _coerce_percent(m.group(1))
            if all_pct is not None and result["today"] is None:
                result["today"] = all_pct
            elif all_pct is not None and result["one_week_ago"] is None:
                result["one_week_ago"] = all_pct
            elif all_pct is not None and result["thirty_days_ago"] is None:
                result["thirty_days_ago"] = all_pct

    return result


async def fetch_weather(session, lat, lon):
    """Fetch all required weather data blocks used by the Weather section."""
    now_ref = get_reference_datetime()
    log("  [fetch_weather] Entering weather fetch")
    weather_data = {
        "forecast": [],
        "station": {"avg_temp_today": None, "avg_monthly_rainfall": None, "current_monthly_rainfall": None},
        "lakes": {},
        "errors": [],
    }
    try:
        weather_point_url = WEATHER_POINT_URL.format(lat=lat, lon=lon)
        log(f"  [fetch_weather] Point URL: {weather_point_url}")
        point = await _fetch_json(session, weather_point_url)
        if not isinstance(point, dict) or "properties" not in point:
            log("  [fetch_weather] Point response invalid or missing properties")
            return weather_data
 
        fc_url = point["properties"].get("forecast")

        if not fc_url:
            fc_url = WEATHER_POINT_URL.split('?')[0] + WEATHER_POINT_FORECAST_SUFFIX
        if WEATHER_POINT_FORECAST_SUFFIX and not fc_url.rstrip("/").endswith(WEATHER_POINT_FORECAST_SUFFIX):
            fc_url = fc_url.rstrip("/") + f"/{WEATHER_POINT_FORECAST_SUFFIX}"
        log(f"  [fetch_weather] Forecast URL: {fc_url}")
        forecast_payload = await _fetch_json(session, fc_url, USER_AGENT_WEATHER_SUFFIX)
        if isinstance(forecast_payload, dict):
            periods = forecast_payload.get("properties", {}).get("periods", []) or []
            log(f"  Weather forecast periods fetched: {len(periods)}")
            by_date = {}
            day_periods = []
            night_periods = []
            for p in periods:
                if not isinstance(p, dict):
                    continue
                day_start = _parse_date_for_weather(p.get("startTime"))
                if not day_start:
                    continue
                if p.get("isDaytime"):
                    day_periods.append((day_start, p))
                else:
                    night_periods.append((day_start, p))
                day_key = day_start.date()
                slot = by_date.setdefault(day_key, {})
                slot_type = "day" if p.get("isDaytime") else "night"
                slot[slot_type] = p

            def _nearest_for_day(day_dt, slots):
                if not slots:
                    return None
                return min(slots, key=lambda it: abs((it[0].date() - day_dt.date()).days))[1]

            for offset in range(3):
                row_date = now_ref.date() + timedelta(days=offset)
                day_slot = by_date.get(row_date, {})
                day = day_slot.get("day", {})
                night = day_slot.get("night", {})
                if not day:
                    day = _nearest_for_day(datetime.combine(row_date, datetime.min.time(), tzinfo=ACTIVE_TIMEZONE), day_periods) or {}
                if not night:
                    night = _nearest_for_day(datetime.combine(row_date, datetime.min.time(), tzinfo=ACTIVE_TIMEZONE), night_periods) or {}

                wind_speed = None
                wind_dir = None
                if isinstance(day, dict):
                    wind_speed = day.get("windSpeed")
                    wind_dir = day.get("windDirection")
                wind = _safe_text(wind_speed, "")
                if wind and wind_dir:
                    wind = f"{wind} {wind_dir}"
                row = {
                    "date": get_weather_label_for_offset(now_ref, offset),
                    "day": _safe_text((day or {}).get("shortForecast"), "Dynamic"),
                    "night": _safe_text((night or {}).get("shortForecast"), _safe_text((day or {}).get("shortForecast"), "Dynamic")),
                    "high": _safe_text((day or {}).get("temperature"), "Dynamic"),
                    "low": _safe_text((night or {}).get("temperature"), "Dynamic"),
                    "precip": _safe_text((day or {}).get("probabilityOfPrecipitation", {}).get("value"), "Dynamic"),
                    "wind": _safe_text(wind, "Dynamic"),
                }
                row["high"] = f"{row['high']}°{day.get('temperatureUnit', 'F')}" if row["high"] != "Dynamic" else "Dynamic"
                row["low"] = f"{row['low']}°{night.get('temperatureUnit', day.get('temperatureUnit', 'F'))}" if row["low"] != "Dynamic" else "Dynamic"
                if row["precip"] and row["precip"] != "Dynamic":
                    row["precip"] = f"{row['precip']}%"
                weather_data["forecast"].append(row)
            log(f"  Weather forecast rows: {len(weather_data['forecast'])}")
        else:
            log("  [fetch_weather] Forecast payload was not a dict; skipping period parse")

        weather_data["station"] = await _fetch_station_metrics(session, WEATHER_WUNDERGROUND_STATION_ID, now_ref)
        log("  [fetch_weather] Completed station fetch")
        log(
            "  Weather station data: "
            f"avg_temp_today={weather_data['station'].get('avg_temp_today', 'Dynamic')} "
            f"avg_monthly_rainfall={weather_data['station'].get('avg_monthly_rainfall', 'Dynamic')} "
            f"current_monthly_rainfall={weather_data['station'].get('current_monthly_rainfall', 'Dynamic')}"
        )

        # Merge with climate normals source for monthly rain values.
        station_monthly = await _fetch_station_monthly_rainfall(session, now_ref)
        log(
            "  Station monthly rainfall: "
            f"avg={station_monthly.get('avg_monthly_rainfall', 'Dynamic')} "
            f"current={station_monthly.get('current_monthly_rainfall', 'Dynamic')}"
        )
        # Merge monthly rainfall from station_monthly into station data
        if station_monthly.get("avg_monthly_rainfall") and not weather_data["station"].get("avg_monthly_rainfall"):
            weather_data["station"]["avg_monthly_rainfall"] = f"{station_monthly['avg_monthly_rainfall']} Inches"
        if station_monthly.get("current_monthly_rainfall") and not weather_data["station"].get("current_monthly_rainfall"):
            weather_data["station"]["current_monthly_rainfall"] = f"{station_monthly['current_monthly_rainfall']} Inches"

        # Fallback: ensure temperature is populated from forecast if station scraping is unavailable.
        if weather_data["station"]:
            station = weather_data["station"]
            if not station.get("avg_temp_today") and weather_data["forecast"]:
                first_row = weather_data["forecast"][0]
                temp_candidates = [first_row.get("high"), first_row.get("low")]
                for val in temp_candidates:
                    m = re.search(r"(-?\d+(?:\.\d+)?)", _safe_text(val, ""))
                    if m:
                        station["avg_temp_today"] = f"{m.group(0)}°F"
                        break
            if station.get("avg_monthly_rainfall") == station.get("current_monthly_rainfall"):
                station["current_monthly_rainfall"] = None
            # If still missing, mark as unavailable rather than leaving Dynamic in markdown output.
            for key in ("avg_temp_today", "avg_monthly_rainfall", "current_monthly_rainfall"):
                if not station.get(key):
                    station[key] = "Unavailable"

            log(
                "  [fetch_weather] Station fallback-applied: "
                f"avg_temp_today={station.get('avg_temp_today')} "
                f"avg_monthly_rainfall={station.get('avg_monthly_rainfall')} "
                f"current_monthly_rainfall={station.get('current_monthly_rainfall')}"
            )

        for key in ("conroe", "corpus_christi", "travis"):
            url = WEATHER_LAKE_URLS.get(key)
            if not url:
                continue
            weather_data["lakes"][key] = await _extract_lake_value(session, key, url, now_ref)
            log(f"  [fetch_weather] Completed lake fetch: {key}")
            log(
                f"  Lake {key}: "
                f"today={weather_data['lakes'][key].get('today')} "
                f"one_week_ago={weather_data['lakes'][key].get('one_week_ago')} "
                f"thirty_days_ago={weather_data['lakes'][key].get('thirty_days_ago')}"
            )

    except Exception as e:
        log(f"  WARNING Weather fetch failed ({e})")
        weather_data["errors"].append(str(e))

    return weather_data


def _build_weather_markdown(weather):
    """Build markdown section for the weather block."""
    rows = weather.get("forecast", [])
    if not rows:
        rows = [
            {"date": "Dynamic", "day": "Dynamic", "night": "Dynamic", "high": "Dynamic", "low": "Dynamic", "precip": "Dynamic", "wind": "Dynamic"}
        ] * 3
    if len(rows) < 3:
        rows.extend([{"date": "Dynamic", "day": "Dynamic", "night": "Dynamic", "high": "Dynamic", "low": "Dynamic", "precip": "Dynamic", "wind": "Dynamic"}] * (3 - len(rows)))

    md = []
    md.append("")
    md.append("---")
    md.append(f"## {WEATHER_SECTION_TITLE}")
    md.append("")
    md.append("**3 Day forecast for 77316:**")
    md.append("")
    md.append("| **Date** | **Day Condition** | **Night Condition** | **High Temp** | **Low Temp** | **Precip. Chance** | **Wind** |")
    md.append("| --- | --- | --- | --- | --- | --- | --- |")
    for row in rows[:3]:
        md.append(
            "| "
            f"{_present_weather_value(row.get('date'), 'Unavailable')} | "
            f"{_present_weather_value(row.get('day'), 'Unavailable')} | "
            f"{_present_weather_value(row.get('night'), 'Unavailable')} | "
            f"{_present_weather_value(row.get('high'), 'Unavailable')} | "
            f"{_present_weather_value(row.get('low'), 'Unavailable')} | "
            f"{_present_weather_value(row.get('precip'), 'Unavailable')} | "
            f"{_present_weather_value(row.get('wind'), 'Unavailable')} |"
        )

    md.append("")
    station = weather.get("station", {})
    md.append(f"| Average Temperature for today 77316 | {_present_weather_value(station.get('avg_temp_today'), 'Unavailable')} |")
    md.append("| --- | --- |")
    md.append(f"| Average Monthly rainfall for 77316  | {_present_weather_value(station.get('avg_monthly_rainfall'), 'Unavailable')} |")
    md.append(f"| Current Monthly rainfall for 77316  | {_present_weather_value(station.get('current_monthly_rainfall'), 'Unavailable')} |")
    md.append("")
    md.append("| Where | Today | 1 Week Ago | 30 Days ago |")
    md.append("| --- | --- | --- | --- |")
    labels = {"conroe": "Lake Conroe", "corpus_christi": "Lake Corpus Christi", "travis": "Lake Travis"}
    for key, label in labels.items():
        vals = weather.get("lakes", {}).get(key, {})
        md.append(
            f"| {label} | {_present_weather_value(vals.get('today'), 'Unavailable')} | "
            f"{_present_weather_value(vals.get('one_week_ago'), 'Unavailable')} | "
            f"{_present_weather_value(vals.get('thirty_days_ago'), 'Unavailable')} |"
        )

    md.append("")
    md.append("---")
    return md


# -- Ollama helpers (blocking, run in thread pool) -------------------------

def _summarize(context, min_chars=LLM_SUMMARY_TRIM_MIN_CHARS):
    """Blocking summary call with retry."""
    if not context or len(context.strip()) < min_chars:
        return None
    for attempt in range(2):
        try:
            t0 = time.time()
            r = _llm_client.chat(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": SUMMARY_PROMPT},
                    {"role": "user", "content": context[:LLM_SUMMARY_CONTEXT_CHARS]}
                ],
                options=LLM_SUMMARY_OPTIONS
            )
            log(f"SUMMARIZE: {time.time() - t0:.2f}s")
            summary_text = r["message"]["content"] or ""
            summary_text = " ".join([ln.strip() for ln in str(summary_text).splitlines() if ln.strip()])
            return summary_text
        except Exception as e:
            if attempt == 0:
                log(f"SUMMARIZE attempt 1 failed ({e}), retrying 3s...")
                time.sleep(3)
            else:
                log(f"SUMMARIZE ERROR (final): {e}")
    return None





def _run_blocking(fn, *args):
    """Run a blocking function in the thread pool executor."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(_executor, fn, *args)


# -- Stage workers (for parallel phase 3) -----------------------------------

class StoryPipelineState:
    __slots__ = ("title", "link", "snippet", "category", "pub_dt", "context", "summary")

    def __init__(self, title, link, snippet, pub_dt, category):
        self.title = title
        self.link = link
        self.snippet = snippet
        self.category = category
        self.pub_dt = pub_dt
        self.context = None
        self.summary = None


async def stage_extract_article(story, session):
    """Phase 3A: Fetch full article text from source URL for summary context when link is an external publisher URL."""
    if is_obituary_title(story.title) and story.category in ["Conroe TX News", "Houston TX News"]:
        return

    url = story.link.strip()
    if not url or url == "#" or url.startswith("#"):
        return
    # Skip Google News tracking URLs
    if "news.google.com" in url:
        return
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENT}, timeout=5) as resp:
            html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        # Remove script/style/noise elements
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        # Strip whitespace and cap context size
        text = " ".join(text.split())[:LLM_CONTEXT_PREVIEW_CHARS]
        if len(text) >= 50:  # Only update if we got meaningful content
            story.context = text
    except Exception as e:
        log(f"  [extract error] '{story.title[:60]}...': {e}")


def build_context(story):
    """Build the text context for a single story â€” capped at 600 chars for batch processing."""
    context = story.context
    if context and len(str(context).strip()) >= 50:
        return str(context).strip()[:LLM_CONTEXT_PREVIEW_CHARS]  # Cap article content
    
    parts = [v.strip() for v in [story.snippet, story.title] if v and len((v or "").strip()) > 0]
    if not parts:
        return f"{story.category}: {story.title}"
    
    inner = "\n---\n".join(parts + [f"Category: {story.category}"])
    return inner[:LLM_CONTEXT_PREVIEW_CHARS]


def batch_summarize_all(stories, session=None):
    """One batch summarization call per category. Returns dict mapping story object -> summary text."""
    if not stories:
        return {}
    
    # Group by category
    by_category = {}
    for s in stories:
        by_category.setdefault(s.category, []).append(s)
    
    all_summaries = {}
    
    SYSTEM_BATCH = SYSTEM_BATCH_PROMPT
    
    total_parsed = 0
    for cat_name, cat_stories in by_category.items():
        # Build contexts for this category's stories
        context_lines = []
        for idx, s in enumerate(cat_stories):
            # Build a shorter context: title + first 400 chars of article if available
            context_parts = [s.title]
            content = build_context(s)  # This returns story.context if available and >= 50 chars, else snippet+title
            if len(content) > LLM_CONTEXT_PREVIEW_CHARS:
                content = content[:LLM_CONTEXT_PREVIEW_CHARS]
            context_parts.append(content)
            
            entry = f"{idx + 1}. {cat_name}\n" + "\n".join(context_parts)
            context_lines.append(entry)
        
        batch_text = "\n---\n\n".join(context_lines)
        
        # Make ONE batch call for this category
        try:
            t0 = time.time()
            r = _llm_client.chat(
                model=LLM_MODEL,
                messages=[
                {"role": "system", "content": SYSTEM_BATCH},
                {"role": "user", "content": batch_text}
            ],
                options=LLM_SUMMARY_OPTIONS
            )
            elapsed = time.time() - t0
            log(f"BATCH SUMMARIZE ({cat_name}, {len(cat_stories)} stories): {elapsed:.1f}s")
            
            resp_text = r["message"]["content"] if r.get("message", {}).get("content") else ""
            log(f"BATCH OUTPUT ({cat_name}, {len(resp_text)} chars): {resp_text[:500]}")

            parsed_summaries = parse_batch_summary_response(resp_text, len(cat_stories))
            for idx, s in enumerate(cat_stories):
                summary = parsed_summaries[idx] if idx < len(parsed_summaries) else ""
                headline = s.title.strip()
                def is_invalid_summary(value):
                    if not value:
                        return True
                    normalized = re.sub(r"\s+", " ", value).strip().lower()
                    headline_norm = reed_safe(headline)
                    if normalized == headline_norm or normalized.startswith(headline_norm + "."):
                        return True
                    return _count_sentences(value) < 2

                def reed_safe(text):
                    return re.sub(r"\s+", " ", text).strip().lower()

                if not summary or not summary.strip():
                    s.summary = ""
                    continue
                
                safe_summary = summary
                if not is_invalid_summary(safe_summary):
                    s.summary = safe_summary
                    total_parsed += 1
                else:
                    s.summary = ""

            
        except Exception as e:
            log(f"BATCH SUMMARIZE ERROR ({cat_name}): {e}")
            # Set fallback summary for all stories in this category
            for s in cat_stories:
                s.summary = f"[Headline] {s.title}"
    
    return all_summaries


def batch_evaluate_alerts(stories):
    """Single Ollama call to evaluate ALL stories for alert priority.
    Returns dict mapping index â†’ True/False."""
    if not stories:
        return {}

    # Group by category to prevent overload and ensure proper handling
    by_category = {}
    for s in stories:
        by_category.setdefault(s.category, []).append(s)
    
    # Process each category separately to avoid hitting context limits or timeouts
    all_alerts = {}
    for cat_name, cat_stories in by_category.items():
        # Build input text â€” only include stories that have valid summaries
        labeled_summaries = []
        summary_indices = []  # Track which stories are included
        idx = 0
        
        for s in cat_stories:
            if not s.summary or s.summary.startswith("[") or "unavailable" in s.summary.lower():
                continue
            label = f"STORY_{idx}"
            entry = f"{label} | Headline: {s.title}\nSummary: {s.summary}"
            labeled_summaries.append(entry)
            s._alert_idx = idx  # Tag the story with its batch index
            summary_indices.append(idx)
            idx += 1
        
        if not labeled_summaries:
            continue

        alert_text = "\n\n".join(labeled_summaries)
        
        SYSTEM_ALERT_BATCH = SYSTEM_ALERT_PROMPT

        for attempt in range(2):
            try:
                t0 = time.time()
                r = _llm_client.chat(
                    model=LLM_MODEL,
                    messages=[
                {"role": "system", "content": SYSTEM_ALERT_BATCH},
                {"role": "user", "content": alert_text}
            ],
                    options=LLM_ALERT_OPTIONS
                )
                log(f"BATCH ALERT EVAL ({cat_name}, {len(labeled_summaries)} stories): {time.time() - t0:.2f}s")
                
                resp_text = r["message"]["content"]
                alert_results = parse_alert_batch_response(resp_text)
                
                # Map results back to stories
                alerts_flagged = 0
                for s in cat_stories:
                    if hasattr(s, '_alert_idx') and s._alert_idx in alert_results:
                        s.is_alert = alert_results[s._alert_idx]
                        if s.is_alert:
                            alerts_flagged += 1
                    else:
                        s.is_alert = False
                
                break  # Success, exit retry loop
            except Exception as e:
                if attempt == 0:
                    log(f"BATCH ALERT EVAL ({cat_name}) attempt 1 failed ({e}), retrying...")
                    time.sleep(3)
                else:
                    log(f"BATCH ALERT ERROR ({cat_name}, final): {e}")
                    # Even if we fail, continue to next category - don't crash the whole pipeline
                    for s in cat_stories:
                        s.is_alert = False
    
    # Build return dict mapping global index â†’ bool for all stories
    alert_index = {}
    for i, s in enumerate(stories):
        if hasattr(s, "is_alert"):
            alert_index[i] = s.is_alert
        else:
            alert_index[i] = False
    
    return alert_index


def parse_alert_batch_response(response):
    """Parse alert batch response into dict mapping index â†’ bool."""
    results = {}
    for line in response.split('\n'):
        line = line.strip()
        if line.startswith('STORY_'):
            try:
                parts = line.split(':', 1)
                idx_str = parts[0].replace('STORY_', '')
                val = parts[1].strip().upper()
                idx = int(idx_str)
                results[idx] = (val == "TRUE")
            except (ValueError, IndexError):
                pass
        else:
            # Fallback: <number>: TRUE/FALSE
            parts = line.split(':', 1)
            if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip() in ('TRUE', 'FALSE'):
                idx = int(parts[0].strip())
                results[idx] = (parts[1].strip().upper() == "TRUE")
    return results


def ordered_categories_for_render(all_cats):
    """Keep local/priority categories near the front to match requirement examples."""
    preferred = [
        "Conroe TX News",
        "Houston Tropical Weather",
        "Montgomery County TX News",
        "World News",
        "US News",
        "Texas News",
        "Market News",
        "Semiconductors",
        "Big Tech",
        "Artificial Intelligence",
        "OpenAI News",
        "Anthropic News",
        "SpaceX News",
        "Andrej Karpathy Activity",
        "Hermes Agent News",
        "Weather Forecast 77316",
    ]
    ordered = [c for c in preferred if c in all_cats]
    for c in all_cats:
        if c not in ordered:
            ordered.append(c)
    return ordered


def tag_story_with_keywords(story_title, category=None):
    """Generate meaningful tags for a story based on its title using enhanced keyword matching."""
    
    # Expanded keywords mapping with more comprehensive coverage
    keywords_to_tags = {
        # Existing broad tags (expanded)
        'AI': ['artificial intelligence', 'machine learning', 'neural network', 'llm', 'transformer', 'ai', 'deep learning', 'generative ai', 'model', 'algorithm'],
        'tech': ['technology', 'digital', 'software', 'programming', 'computing', 'cloud', 'data', 'startup', 'innovation'],
        'economy': ['economy', 'market', 'finance', 'stock', 'invest', 'trade', 'business', 'growth', 'earnings', 'revenue'],
        'weather': ['weather', 'climate', 'storm', 'rain', 'snow', 'hurricane', 'tornado', 'forecast', 'temperature', 'atmospheric'],
        'politics': ['election', 'government', 'politic', 'policy', 'congress', 'senate', 'president', 'regulation', 'law'],
        'science': ['science', 'research', 'discovery', 'study', 'experiment', 'physics', 'biology', 'breakthrough'],
        'health': ['health', 'medical', 'hospital', 'doctor', 'treatment', 'vaccine', 'disease', 'pandemic', 'pharma'],
        'space': ['space', 'rocket', 'astronaut', 'nasa', 'mission', 'satellite', 'launch', 'orbit', 'lunar'],
        
        # New category-specific tags
        'semiconductors': ['semiconductor', 'chip', 'processor', 'gpu', 'cpu', 'transistor', 'fab', 'manufacturing', 'intel', 'nvidia', 'tsmc', 'qualcomm', 'amd'],
        'energy': ['energy', 'power', 'renewable', 'solar', 'wind', 'grid', 'electric', 'battery', 'charging', 'fuel cell'],
        'infrastructure': ['infrastructure', 'construction', 'development', 'project', 'building', 'road', 'bridge', 'transit'],
        'security': ['security', 'cybersecurity', 'privacy', 'breach', 'hacking', 'encryption', 'data protection', 'threat'],
        'companies': ['company', 'corporation', 'startup', 'ipo', 'acquisition', 'merger', 'partnership', 'venture'],
        'people': ['founder', 'ceo', 'entrepreneur', 'investor', 'researcher', 'scientist'],
        
        # Company/entity-specific tags
        'openai': ['openai', 'chatgpt', 'gpt-4', 'gpt-5'],
        'anthropic': ['anthropic', 'claude'],
        'spacex': ['spacex', 'starship', 'elon musk', 'falcon'],
        'big-tech': ['google', 'meta', 'apple', 'microsoft', 'amazon', 'meta'],
        
        # Geographic tags (especially relevant given your local focus)
        'local': ['houston', 'texas', 'conroe', 'montgomery county', 'tx', 'houston metro', 'galveston'],
        'us-focused': ['united states', 'us', 'america', 'american', 'washington dc', 'dc'],
        'international': ['world', 'global', 'international', 'foreign', 'european', 'asian', 'global'],
        
        # Meta/cross-cutting tags
        'regulatory': ['regulation', 'legal', 'law', 'legislation', 'lawsuit', 'compliance', 'ruling', 'court'],
        'innovation': ['innovation', 'new', 'novel', 'breakthrough', 'first', 'advancement', 'unveil'],
        'market-impact': ['market', 'stock', 'trading', 'investment', 'return', 'valuation', 'earnings'],
        'environment': ['environment', 'climate', 'sustainability', 'carbon', 'emissions', 'green', 'ecological'],
    }
    
    # Convert title to lowercase for matching
    title_lower = story_title.lower()
    
    # Initialize scoring system
    tag_scores = {}
    
    # Score each tag based on keyword matches
    for tag, keywords in keywords_to_tags.items():
        score = 0
        for keyword in keywords:
            if keyword in title_lower:
                # Position-based boosting (higher weight for keywords early in title)
                pos = title_lower.find(keyword)
                if pos >= 0:
                    # Boost score for matches in first 100 characters
                    boost = 2.0 if pos < 100 else 1.0
                    # Add partial score based on how many keywords match
                    score += boost * (1.0 / len(keyword))  # Normalize by keyword length
        
        # Apply category-specific boosting if available
        if category:
            category_boosts = {
                'OpenAI News': ['openai', 'chatgpt'],
                'Anthropic News': ['anthropic', 'claude'],
                'SpaceX News': ['spacex', 'starship'],
                'Big Tech': ['google', 'meta', 'apple', 'microsoft', 'amazon']
            }
            
            if category in category_boosts:
                for keyword in category_boosts[category]:
                    if keyword in title_lower:
                        score += 2.0  # Strong boost for category-specific matches
        
        # Store final score
        if score > 0:
            tag_scores[tag] = min(score, 5.0)  # Cap at 5.0 to avoid extreme values
    
    # Return the tags sorted by score (highest first)
    sorted_tags = sorted(tag_scores.items(), key=lambda x: x[1], reverse=True)
    
    # Apply maximum limit and return just tag names
    max_tags = 5
    if len(sorted_tags) <= max_tags:
        tag_list = [tag for tag, score in sorted_tags]
    else:
        tag_list = [tag for tag, score in sorted_tags[:max_tags]] 
    
    # If no tags found but we have a category, return at least the category tag
    if not tag_list and category:
        # Convert category name to appropriate tag format (e.g., "World News" -> "world-news")
        category_tag = category.lower().replace(' ', '-').replace('/', '-')
        tag_list = [category_tag]
    
    # Return joined tags with spaces, formatted as Obsidian wiki links
    formatted_tags = ["[[%s]]" % tag for tag in tag_list]
    return " ".join(formatted_tags) if formatted_tags else FRONTMATTER_FALLBACK_TAG



def _coerce_temperature_f(val):
    """Safely convert temperature string/none to float and sanity check."""
    if val is None:
        return None
    try:
        # Remove non-numeric characters except for the decimal point
        clean_val = re.sub(r"[^\d.]", "", str(val))
        if not clean_val:
            return None
        temp = float(clean_val)
        # Sanity check: Temperature should be within a reasonable range (-50 to 140 F)
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

def is_obituary_title(title):
    """Check if a title contains mortality/obituary markers that should be filtered out."""
    if not title:
        return False
    mortality_keywords = [
        "obituary", "passed away", "died", "deceased", "funeral services", 
        "death notice", "memorial service", "passed at age", "remembering"
    ]
    title_lower = title.lower()
    return any(keyword in title_lower for keyword in mortality_keywords)


# -- Main -------------------------------------------------------------------

async def main():
    global PHASE_TIMINGS
    PHASE_TIMINGS = {}
    
    t0 = time.time()
    
    # Unique log file per run (same convention as markdown output)
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    global RUN_LOGFILE, OUTPUT_DIR
    
    # Count existing files for the same date to get correct increment
    log_files = [f for f in os.listdir(LOG_DIR) if f.startswith('run_log_' + now_ts) and f.endswith('.md')]
    file_count = len(log_files) + 1  # Start from v01
    
    # Format with proper naming convention
    run_log_name = f"run_log_{now_ts}_v{file_count:02d}.md"
    RUN_LOGFILE = os.path.join(LOG_DIR, run_log_name)
    
    # Log startup
    log("=" * 60)
    log(f"RUN LOG: {RUN_LOGFILE}")
    log("DAILY BRIEF v" + VERSION + " - Pipeline Starting")
    log("=" * 60)

    # Track age threshold
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
            log(
                "  Weather OK -- "
                f"{len(weather.get('forecast', []))} forecast periods | "
                f"{1 if weather.get('station') else 0} station record | "
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
        
        # DEBUG: Show all categories we're actually going to fetch
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

        # DEBUG: Show which feed queries are returning data (helpful to identify if query is too specific)
        log("  [DEBUG] Feed results by category:")
        for name in sorted(by_cat.keys()):
            count = len(by_cat[name])
            log(f"    {name}: {count} stories")

        # Deduplicate + filter by age: per category, keep first occurrence of each normalized title
        deduped = []
        total_age_filtered = 0
        total_dup_filtered = 0
        total_cross_dup_filtered = 0
        seen_per_cat = {}

        for cat_name in by_cat:
            if cat_name not in seen_per_cat:
                seen_per_cat[cat_name] = set()
            for title, link, snippet, pub_dt in by_cat[cat_name]:
                # 1. Age filter - more lenient approach due to timezone issues with RSS timestamps
                is_old = False
                if pub_dt is not None:
                    try:
                        age_secs = (now_ct - pub_dt).total_seconds()
                        # If we have a meaningful timestamp and it's newer than the category's age limit, keep it
                        age_limit = CATEGORY_AGE_LIMITS.get(cat_name, DEFAULT_AGE_LIMIT_HOURS)
                        if age_secs > age_limit * 3600:
                            total_age_filtered += 1
                            is_old = True
                    except Exception:
                        # If there are timezone conversion issues or malformed dates, treat as expired
                        total_age_filtered += 1
                        is_old = True
                        
                if is_old:
                    continue

                # 2. Title dedup within category (prevents same story from 3 sources)
                norm = normalize_title(title)
                if norm in seen_per_cat[cat_name]:
                    total_dup_filtered += 1
                    continue
                seen_per_cat[cat_name].add(norm)

                # 3. Filter out real estate and mortality content (after dedup but before adding to deduped)
                if is_realt_estate_title(title) or is_obituary_title(title):
                    continue

                deduped.append((title, link, snippet, pub_dt, cat_name))

        # Cross-category dedup: prevent same story appearing in multiple categories
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
        log(f"  Deduplicated: {total_before_dedup} -> {total_after_dedup} stories " +
            f"(age-filtered: {total_age_filtered}, dup-filtered: {total_dup_filtered}, cross-cat-filtered: {total_cross_dup_filtered})")

        # DEBUG: Show per-category breakdown before summarization
        log("  [DEBUG] Per-category story count AFTER dedup:")
        cat_counts = {}
        for entry in deduped:
            cat = entry[4]  # cat_name
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
        # Use bounded concurrency (20) with 5s timeout
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=20, limit_per_host=10, ttl_dns_cache=300),
            headers={"User-Agent": USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=5)
        ) as extract_session:
            await asyncio.gather(
                *[stage_extract_article(s, extract_session) for s in stories],
                return_exceptions=True
            )

        # ---------- Phase 3B/3C: Batch summary (single Ollama call for all stories) ----------
        log("  [3BC] Running BATCH summaries via Qwen...")
        t3 = time.time()
        sum_results = batch_summarize_all(stories, session)
        sum_ok = sum(1 for s in stories if s.summary is not None and not s.summary.startswith("[Summary"))
        sum_fail = total - sum_ok
        log(f"  Summaries done: {sum_ok} OK / {sum_fail} failed")
        
        elapsed = time.time() - t3
        log(f"  Phase 3 completed in {elapsed:.2f}s")
        PHASE_TIMINGS['Phase 3'] = elapsed

        log(f"\n  PROCESSING COMPLETE: {total} stories in {time.time() - t0:.2f}s")

        # ---------- Phase 4: Build sections + render Markdown ----------
        log("\n[Phase 4] Rendering report...")

        # Build the alerts list for final stats display
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
        
        # Count existing files for the same date to get correct increment
        daily_brief_files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith('DailyBrief-' + fn_ts) and f.endswith('.md')]
        file_count = len(daily_brief_files) + 1  # Start from v01
        
        # Format with proper naming convention  
        filepath = os.path.join(OUTPUT_DIR, f"DailyBrief-{fn_ts}_v{file_count:02d}.md")
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # Cleanup old DailyBrief files (keep only MAX_LOG_VERSIONS most recent)
        if MAX_LOG_VERSIONS > 0:
            try:
                # Ensure OUTPUT_DIR exists before trying to list it
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                
                # Get all DailyBrief and run_log files
                all_files = [f for f in os.listdir(OUTPUT_DIR) 
                           if (f.startswith('DailyBrief-') or f.startswith('run_log_')) and f.endswith('.md')]
                
                # Sort by modification time (newest first)
                all_files.sort(key=lambda x: os.path.getmtime(os.path.join(OUTPUT_DIR, x)), reverse=True)
                
                # Keep only MAX_LOG_VERSIONS most recent files
                files_to_remove = all_files[MAX_LOG_VERSIONS:]
                for old_file in files_to_remove:
                    os.remove(os.path.join(OUTPUT_DIR, old_file))
                    log(f"Removed old file: {old_file}")
                    
                # Also cleanup logs directory - keep only 5 most recent run_log_ files
                logs_dir = LOG_DIR if 'LOG_DIR' in globals() else '/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/logs'
                os.makedirs(logs_dir, exist_ok=True)
                log_files = [f for f in os.listdir(logs_dir) if f.startswith('run_log_') and f.endswith('.md')]
                # Filter out any non-standard entries
                valid_log_files = [f for f in log_files if 'run_log_' in f and f.endswith('.md')]
                valid_log_files.sort(key=lambda x: os.path.getmtime(os.path.join(logs_dir, x)), reverse=True)
                
                # Keep only MAX_LOG_VERSIONS most recent logs (same limit as DailyBrief)
                logs_to_remove = valid_log_files[MAX_LOG_VERSIONS:]
                for old_log in logs_to_remove:
                    os.remove(os.path.join(logs_dir, old_log))
                    log(f"Removed old log file: {old_log}")
            except Exception as e:
                print(f"Warning: Could not cleanup old files: {e}")

        ordered_cats = ordered_categories_for_render([c[0] for c in CATEGORIES if c[1]])
        sections_map = {cn: sections.get(cn, []) for cn in ordered_cats}

        # -- Build markdown --
        md = []
        md.append("---")
        md.append("title: Daily Brief")
        md.append(f"date: {now.strftime('%Y-%m-%d')}")
        md.append(f"time_generated: {now.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        md.append("status: active")
        md.append(f"content_age_window: {DEFAULT_CONTENT_AGE_WINDOW_HOURS}")
        md.append(f"story_count_total: {total_after_dedup}")
        md.append(f"categories: {DEFAULT_CATEGORIES_COUNT}")
        
        # Create a set to collect all unique tags from story titles
        all_tags = set(FRONTMATTER_TAG_SEEDS or [])
        
        # Process category sections to extract story tags for frontmatter
        section_tag_map = {}
        for cn in ordered_cats:
            cat_stories = sections_map.get(cn, [])
            for st in cat_stories:
                if "title" in st and st["title"]:
                    title = st["title"]
                    # Pass category to enable category-specific boosting
                    story_tags = tag_story_with_keywords(title, cn)
                    # Extract just the tag names from the string (handle both #tag and [[tag]] formats)
                    individual_tags = []
                    for tag in story_tags.split():
                        tag = tag.strip()
                        if tag.startswith('#'):
                            individual_tags.append(tag.lstrip('#'))
                        elif tag.startswith('[') and tag.endswith(']'):
                            # Handle [[tag]] format
                            tag_content = tag[2:-2]  # Remove [[ and ]]
                            individual_tags.append(tag_content)
                    for tag in individual_tags:
                        all_tags.add(tag.lower())  # Add to set (normalized to lowercase)
            section_tag_map[cn] = cat_stories
            
        # Add tags to YAML frontmatter (remove duplicates and sort)
        md.append("tags:")
        sorted_tags = sorted(list(all_tags))
        for tag in sorted_tags:
            md.append(f"  - {tag}")
        
        md.append("---")
        md.append("")
        md.append(f"# Daily Brief -- {now.strftime('%B %d, %Y')}")
        md.extend(_build_weather_markdown(weather))



        # Category sections
        for cn in ordered_cats:
            if cn == WEATHER_SECTION_TITLE or cn == "Weather Forecast 77316":
                continue
            cat_stories = sections_map.get(cn, [])
            md += ["", f"## {cn} ({len(cat_stories)} stories)", ""]
            for idx, st in enumerate(cat_stories):
                title_text = st["title"]
                url_val = st["link"]
                link_md = f"[{title_text}]({url_val})" if url_val and url_val != "#" else title_text
                pub_line = f"\n*Originally published on:* {st['pub_date']}" if st.get("pub_date") else ""
                # Add tags to each summary - use the tag_story_with_keywords function for meaningful keywords-based tags
                tags_md = ""
                if "title" in st and st["title"]:
                    title = st["title"]
                    # Pass category to enable category-specific boosting
                    tags_md = tag_story_with_keywords(title, cn)
                md.append("")
                # Remove the H3 header for cleaner look, use regular text instead
                md.append(f"{idx + 1}. {link_md}")
                md.append(st["summary"] + pub_line)
                md.append(tags_md)  # Add tags after each story summary
            
            # Add horizontal rule between categories
            md.append("---")

        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write("\n".join(md) + "\n")

        elapsed = time.time() - t0
        log(f"\nFile written to {filepath}")
        log(f"  Stories: {total_after_dedup} | Alerts: {len(alerts_list)} | Failed: {sum_fail}/{total} | Time: {elapsed:.1f}s")
        
        # Add detailed timing breakdown at the end of log file
        log("\n--- TIMING BREAKDOWN ---")
        total_phase_time = 0
        for phase, duration in PHASE_TIMINGS.items():
            log(f"{phase}: ~{duration:.2f}s")
            total_phase_time += duration
        
        log(f"Total: ~{total_phase_time:.2f}s")
        log("=" * 60)

        print(f"\nDone. File: {filepath}")
        print(f"  Stories: {total_after_dedup} | Alerts: {len(alerts_list)} | Failed: {sum_fail}/{total} | Time: {elapsed:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())



