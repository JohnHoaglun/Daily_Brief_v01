#!/usr/bin/env python3
"""
Daily Brief Pipeline v1.0.13
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
from functools import cmp_to_key
from bs4 import BeautifulSoup
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import os
import time
from email.utils import parsedate_to_datetime
import threading
import re

# Ensure src/ is on path for daily_brief package imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Load configuration at the top to avoid import issues
# We import config after defining all the necessary functions and constants
# Then set all values from config properly

# The main fix: properly load config at the beginning and only once
# Avoid circular imports and make sure all configuration is loaded before we start doing work
from config import *
from daily_brief.categorization import ordered_categories_for_render as _ordered_categories_for_render
from daily_brief.tagging import tag_story_with_keywords as _tag_story_with_keywords

# LLM subpackage — client factory + helpers
from daily_brief.llm import create_llm_client, _executor, _run_blocking, LLMClient
_llm_client = create_llm_client(LLM_MODEL, OLLAMA_HOST + "/v1" if "/v1" not in OLLAMA_HOST else OLLAMA_HOST, timeout=180)

# Re-export helpers used elsewhere in this monolith (moved to llm/ subpackage)
from daily_brief.llm.summarizer import (
    _safe_sentence_summary,
    _is_refusal,
    _is_boilerplate,
    _count_sentences,
    build_context,
    StoryPipelineState,
)
from daily_brief.llm.alerter import parse_alert_batch_response as _parse_alert_batch_response

# Rendering subpackage
from daily_brief.rendering import build_weather_markdown, cleanup_old_files
from daily_brief.rendering.report import build_markdown, write_report

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
SUMMARY_STRICT_PROMPT = SUMMARY_STRICT_PROMPT
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

    station_html = None
    for attempt in range(3):
        station_html = await _fetch_text(session, station_range_url)
        if station_html:
            break
        if attempt < 2:
            wait = (attempt + 1) * 2
            log(f"  [station retry] wunderground range fetch failed (attempt {attempt + 1}/3), waiting {wait}s...")
            import asyncio as _asyncio
            await _asyncio.sleep(wait)
    if not station_html:
        log(f"  Station monthly rainfall: no station monthly range html fetched ({station_range_url})")

    station_current_rain = _parse_wu_monthly_precipitation(station_html, month_start, month_end)
    if station_current_rain is not None:
        log(f"  Station monthly rainfall: parsed station current month value {station_current_rain}")

    # Houston monthly normals (average).
    climate_url = "https://www.weather.gov/hgx/climate_iah_normals_summary"
    climate_html = None
    for attempt in range(3):
        climate_html = await _fetch_text(session, climate_url)
        if climate_html:
            break
        if attempt < 2:
            wait = (attempt + 1) * 2
            log(f"  [station retry] climate page fetch failed (attempt {attempt + 1}/3), waiting {wait}s...")
            import asyncio as _asyncio
            await _asyncio.sleep(wait)
    if not climate_html:
        log("  Station monthly rainfall: no climate page HTML fetched after 3 attempts")
        return {
            "avg_monthly_rainfall": None,
            "current_monthly_rainfall": station_current_rain,
        }

    # Use original HTML for table parsing (do not strip text).
    text = BeautifulSoup(climate_html, "html.parser").get_text(" ", strip=True)
    log(f"  Station monthly rainfall: climate page text length {len(text)}")
    parsed = _parse_climate_summary(climate_html, reference.date())

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


async def _fetch_climate_normal_high(session):
    """Fetch the historical average high temperature for today's date from Open-Meteo ERA5.
    Returns the climate normal (long-term average) for this calendar date — NOT today's forecast.
    """
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        geo_url = "https://geocoding-api.open-meteo.com/v1/search"
        async with session.get(geo_url, params={"name": "77316", "count": 1, "language": "en", "format": "json"}, timeout=10) as resp:
            geo = await resp.json()
        if not geo.get("results"):
            return None
        lat = geo["results"][0]["latitude"]
        lon = geo["results"][0]["longitude"]

        archive_url = "https://archive-api.open-meteo.com/v1/era5"
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": today_str,
            "end_date": today_str,
            "daily": "temperature_2m_max",
            "temperature_unit": "fahrenheit"
        }
        async with session.get(archive_url, params=params, timeout=10) as resp:
            climate = await resp.json()
        daily = climate.get("daily", {})
        temps = daily.get("temperature_2m_max", [])
        if temps:
            val = round(temps[0])
            log(f"  Climate normal high for {today_str}: {val}°F")
            return val
    except Exception as e:
        log(f"  WARNING Open-Meteo climate normal fetch failed: {e}")
    return None


async def _fetch_station_metrics(session, station_id, reference):
    """Fetch station metrics from Wunderground monthly dashboard table.

    Returns current_monthly_rainfall (from the Precipitation row).
    avg_temp_today is NOT fetched here — it comes from _fetch_climate_normal_high (Open-Meteo).
    avg_monthly_rainfall comes from _fetch_station_monthly_rainfall (climate.gov).
    """
    payload = {"avg_temp_today": None, "avg_monthly_rainfall": None, "current_monthly_rainfall": None}
    template_date = reference.strftime("%Y-%m-%d")
    url = WUNDERGROUND_MONTHLY_TEMPLATE.format(station_id=station_id, date=template_date)
    station_html = None
    for attempt in range(3):
        station_html = await _fetch_text(session, url)
        if station_html:
            break
        if attempt < 2:
            wait = (attempt + 1) * 2
            log(f"  [station retry] wunderground fetch failed ({station_id}, attempt {attempt + 1}/3), waiting {wait}s...")
            import asyncio as _asyncio
            await _asyncio.sleep(wait)
    if not station_html:
        log("  WARNING Weather station monthly data unavailable (no content) after 3 attempts.")
        return payload

    soup = BeautifulSoup(station_html, "html.parser")
    current_precip = None

    for table in soup.find_all("table"):
        rows = [[c.get_text(strip=True) for c in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]
        for r in rows:
            if len(r) >= 4 and ("precipitation" in r[0].lower() or "rain" in r[0].lower()):
                m = re.search(r"(\d+\.?\d*)", r[1])
                if m:
                    current_precip = float(m.group(1))
                    break
        if current_precip is not None:
            break

    if current_precip is not None:
        val = float(current_precip)
        if 0.0 <= val <= 60.0:
            payload["current_monthly_rainfall"] = f"{val} Inches"

    return payload


async def _extract_lake_value(session, key, url, reference):
    today = reference.date()
    result = {"today": None, "one_week_ago": None, "thirty_days_ago": None}
    targets = [
        ("today", today),
        ("one_week_ago", today - timedelta(days=7)),
        ("thirty_days_ago", today - timedelta(days=30)),
    ]

    # Retry fetch up to 3 times with exponential backoff
    html = None
    for attempt in range(3):
        html = await _fetch_text(session, url)
        if html:
            break
        if attempt < 2:
            wait = (attempt + 1) * 2
            log(f"  [lake retry] '{key}' fetch failed (attempt {attempt + 1}/3), waiting {wait}s...")
            await asyncio.sleep(wait)
    if not html:
        log(f"  WARNING Lake data unavailable ({key}): no html after 3 attempts.")
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
        
        # Fetch climate normal (historical average high for this date)
        climate_high = await _fetch_climate_normal_high(session)
        if climate_high is not None:
            weather_data["station"]["avg_temp_today"] = f"{climate_high}°F"
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

        # Climate normal already fetched above at line 1129 — only apply fallback if it failed
        if weather_data["station"]:
            station = weather_data["station"]
            if not station.get("avg_temp_today") and weather_data["forecast"]:
                log("  [fetch_weather] Climate normal unavailable, falling back to forecast high")
                first_row = weather_data["forecast"][0]
                temp_candidates = [first_row.get("high"), first_row.get("low")]
                for val in temp_candidates:
                    m = re.search(r"(-?\d+(?:\.\d+)?)", _safe_text(val, ""))
                    if m:
                        station["avg_temp_today"] = f"{m.group(0)}°F (forecast fallback)"
                        break
            if station.get("avg_monthly_rainfall") == station.get("current_monthly_rainfall"):
                station["current_monthly_rainfall"] = None
            # If still missing, mark as unavailable rather than leaving Dynamic in markdown output.
            for key in ("avg_temp_today", "avg_monthly_rainfall", "current_monthly_rainfall"):
                if not station.get(key):
                    station[key] = "Unavailable"

            # Log actual source for each value
            has_fallback = any("(forecast fallback)" in str(station.get(k, "")) for k in ("avg_temp_today",))
            has_missing = any(k == "Unavailable" for k in ("avg_temp_today", "avg_monthly_rainfall", "current_monthly_rainfall") if station.get(k) == "Unavailable")
            
            if has_fallback or has_missing:
                log(
                    "  [fetch_weather] Station data (partial/missing): "
                    f"avg_temp_today={station.get('avg_temp_today')} "
                    f"avg_monthly_rainfall={station.get('avg_monthly_rainfall')} "
                    f"current_monthly_rainfall={station.get('current_monthly_rainfall')}"
                )
            else:
                log(
                    "  [fetch_weather] Station data complete: "
                    f"avg_temp_today={station.get('avg_temp_today')} "
                    f"avg_monthly_rainfall={station.get('avg_monthly_rainfall')} "
                    f"current_monthly_rainfall={station.get('current_monthly_rainfall')}"
                )

        for key in WEATHER_LAKE_URLS:
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
    """Delegate to rendering.weather_table — thin wrapper for backwards-compatibility."""
    return build_weather_markdown(weather)


# -- Ollama helpers (blocking, run in thread pool) -------------------------

def _summarize(context, min_chars=LLM_SUMMARY_TRIM_MIN_CHARS, strict=False):
    """Delegate to llm.summarizer — thin wrapper for backwards-compatibility."""
    from daily_brief.llm.summarizer import _summarize as _llm_summarize
    return _llm_summarize(_llm_client, context, min_chars=min_chars, strict=strict)


# -- Stage workers (for parallel phase 3) -----------------------------------

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


def batch_summarize_all(stories, session=None):
    """Delegate to llm.summarizer — thin wrapper for backwards-compatibility."""
    from daily_brief.llm.summarizer import batch_summarize_all as _llm_batch_summarize
    return _llm_batch_summarize(_llm_client, stories, session=session)


def batch_evaluate_alerts(stories):
    """Delegate to llm.alerter — thin wrapper for backwards-compatibility."""
    from daily_brief.llm.alerter import batch_evaluate_alerts as _llm_batch_alerts
    return _llm_batch_alerts(_llm_client, stories)


def ordered_categories_for_render(all_cats):
    """Thin wrapper — delegates to daily_brief.categorization (reads config.yaml:category_priority)."""
    return _ordered_categories_for_render(all_cats)


def tag_story_with_keywords(story_title, category=None):
    """Delegate to the new tagging module. Kept as wrapper for backwards-compatibility."""
    return _tag_story_with_keywords(story_title, category=category)



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



# -- Main -------------------------------------------------------------------

async def main():
    global PHASE_TIMINGS
    PHASE_TIMINGS = {}
    
    t0 = time.time()
    
    # Unique log file per run (same convention as markdown output)
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    global RUN_LOGFILE, OUTPUT_DIR
    
    # Find the highest existing version number for today's log files
    log_files = [f for f in os.listdir(LOG_DIR) if f.startswith('run_log_' + now_ts) and f.endswith('.md')]
    max_log_ver = 0
    for lf in log_files:
        m = re.search(r'_v(\d+)\.md$', lf)
        if m:
            max_log_ver = max(max_log_ver, int(m.group(1)))
    log_ver = max_log_ver + 1  # Next version
    
    # Format with proper naming convention
    run_log_name = f"run_log_{now_ts}_v{log_ver:02d}.md"
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

        def _dedup_category(cat_name, cat_entries, seen, age_limit_hours):
            """Dedup and age-filter a single category. Returns (added_count, age_filtered, dup_filtered)."""
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

        # Deduplicate + filter by age: per category
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

        # Adaptive widening: re-fetch underpopulated categories (<3 stories) with expanded age window (up to 7 days)
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
        log(f"  [3BC] Running BATCH summaries via {LLM_MODEL}...")
        t3 = time.time()
        sum_results = batch_summarize_all(stories, session)
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
                    retry_summary = _summarize(context)
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
                    strict_summary = _summarize(context, strict=True)
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
        
        # Find the highest existing version number for today's output files
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        daily_brief_files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith('DailyBrief-' + fn_ts) and f.endswith('.md')]
        max_file_ver = 0
        for bf in daily_brief_files:
            mf = re.search(r'_v(\d+)\.md$', bf)
            if mf:
                max_file_ver = max(max_file_ver, int(mf.group(1)))
        file_ver = max_file_ver + 1  # Next version
        
        # Format with proper naming convention
        filepath = os.path.join(OUTPUT_DIR, f"DailyBrief-{fn_ts}_v{file_ver:02d}.md")

        # Cleanup: keep MAX_LOG_VERSIONS most recent
        cleanup_old_files(OUTPUT_DIR, LOG_DIR, MAX_LOG_VERSIONS)

        ordered_cats = ordered_categories_for_render([c[0] for c in CATEGORIES if c[1]])
        sections_map = {cn: sections.get(cn, []) for cn in ordered_cats}

        # Count actual rendered categories (skip weather + empty)
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



        # Category sections — skip empty categories
        for cn in ordered_cats:
            if cn == WEATHER_SECTION_TITLE or cn == "Weather Forecast 77316":
                continue
            cat_stories = sections_map.get(cn, [])
            if not cat_stories:
                # Render header even for 0-story categories so harness sees the section
                log(f"  Empty category: {cn} (rendering header)")
                md += ["", f"## {cn} (0 stories)", ""]
                continue
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
        
        # --- Phase 5: Internal report validation (summary quality) ---
        log("\n[Phase 5] Validating report...")
        validation_passed, validation_issues = validate_report(filepath)
        
        if not validation_passed:
            log("\n*** RUN VALIDATION FAILED — Report has broken summaries ***")
            log(f"STATUS: FAILED ({len(validation_issues)} issues found)")
            print(f"\n*** RUN FAILED — {len(validation_issues)} validation issues found ***")
            print(f"File: {filepath}")
            print(f"See run log for details: {os.environ.get('RUN_LOGFILE', 'unknown')}")
            return  # Stop early on validation failure
        
        # --- Phase 6: External test harness validation ---
        log("\n[Phase 6] Running test harness...")
        _run_test_harness()
        
        log("\n=== PIPELINE COMPLETED SUCCESSFULLY ===")
        print(f"\nDone. File: {filepath}")
        print(f"  Stories: {total_after_dedup} | Alerts: {len(alerts_list)} | Failed: {sum_fail}/{total} | Time: {elapsed:.1f}s")


def validate_report(filepath):
    """Validate the rendered markdown report. Returns (passed, issues) tuple.
    
    Checks each story for:
    - Non-empty summary
    - Minimum sentence count (2 sentences or more)
    - Summary is not just the headline repeated
    - Headline/summary topic overlap (keyword matching)
    
    Returns False if >10% of stories have broken summaries.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            content = fh.read()
    except Exception as e:
        log(f"VALIDATE ERROR: Cannot read {filepath}: {e}")
        return False, [f"Cannot read file: {e}"]
    
    # Split into sections — find category headings
    sections = re.split(r'^##\s+', content, flags=re.MULTILINE)
    
    stories = []
    issues = []
    
    for section in sections:
        section_text = section.strip()
        if not section_text:
            continue
        
        # Find numbered stories: "N. [Title](URL)"
        story_blocks = re.split(r'\n(?=\d+\.\s+\[)', section_text)
        
        for block in story_blocks:
            block = block.strip()
            if not block:
                continue
            
            # Extract title from first line
            first_line_match = re.match(r'(\d+)\.\s+\[(.+?)\]\((.+?)\)', block)
            if not first_line_match:
                continue
            
            title = first_line_match.group(2).strip()
            block_lines = block.split('\n')
            if len(block_lines) < 2:
                continue
            
            # Summary is everything after the title line, before meta lines
            summary_lines = []
            for line in block_lines[1:]:
                line_stripped = line.strip()
                if line_stripped.startswith('*Originally published') or \
                   line_stripped.startswith('[[') or \
                   line_stripped.startswith('---') or \
                   line_stripped.startswith('##') or \
                   line_stripped == '':
                    continue
                summary_lines.append(line_stripped)
            
            summary = ' '.join(summary_lines).strip()
            stories.append((title, summary))
    
    if not stories:
        log(f"VALIDATE: No stories found in report")
        return False, ["No stories found in report"]
    
    total_stories = len(stories)
    bad_stories = 0
    
    for title, summary in stories:
        title_lower = title.lower()
        
        # Check 1: Empty summary
        if not summary or not summary.strip():
            issues.append(f"Empty summary for: {title[:80]}")
            bad_stories += 1
            continue
        
        summary_lower = summary.lower()
        
        # Check 2: Summary is just the headline
        title_norm = re.sub(r'\s+', ' ', title_lower)
        summary_norm = re.sub(r'\s+', ' ', summary_lower)
        if summary_norm == title_norm or summary_norm.startswith(title_norm + '.'):
            issues.append(f"Summary repeats headline: {title[:80]}")
            bad_stories += 1
            continue
        
        # Check 3: Minimum sentence count
        sentence_count = _count_sentences(summary)
        if sentence_count < 2:
            issues.append(f"Too short ({sentence_count} sentences): {title[:80]}")
            bad_stories += 1
            continue
        
        # Check 4: Fallback markers
        if summary.startswith("[Headline]") or "[unavailable" in summary_lower:
            issues.append(f"Fallback marker present: {title[:80]}")
            bad_stories += 1
            continue
        
        # Check 5: Topic overlap — extract key words from headline, check presence in summary
        headline_words = re.findall(r'\b[a-z]{4,}\b', title_lower)
        # Remove common words
        stop_words = {'news', 'says', 'live', 'update', 'updates', 'here', 'what', 'how', 'why', 'when', 'year', 'report', 'story', 'today'}
        headline_words = [w for w in headline_words if w not in stop_words]
        
        if headline_words:
            matching = [w for w in headline_words if w in summary_lower]
            overlap_ratio = len(matching) / len(headline_words) if headline_words else 1.0
            
            # If <25% of significant headline words appear in summary, it's likely wrong
            if overlap_ratio < 0.25:
                issues.append(f"Topic mismatch (overlap {overlap_ratio:.0%}): {title[:80]}")
                bad_stories += 1
                continue
    
    fail_threshold = total_stories * 0.10  # 10% failure rate
    total_bad_ratio = bad_stories / total_stories if total_stories > 0 else 0
    
    passed = bad_stories <= fail_threshold
    status = "PASS" if passed else "FAIL"
    log(f"VALIDATE: {total_stories} stories, {bad_stories} bad ({total_bad_ratio:.0%}), threshold {fail_threshold:.0f} — {status}")
    
    if issues:
        log(f"VALIDATE ISSUES ({len(issues)}):")
        for issue in issues[:20]:  # Log first 20 issues max
            log(f"  - {issue}")
        if len(issues) > 20:
            log(f"  ... and {len(issues) - 20} more")
    
    return passed, issues


def _run_test_harness():
    """Run the external Test_validate_run.py harness against the latest output.
    
    Uses subprocess to call Test_validate_run.py with auto-detected date/version
    from the run log filename. Logs output for archival.
    """
    import subprocess
    import sys
    
    # Find the project root directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    harness_script = os.path.join(script_dir, 'Test_validate_run.py')
    config_file = os.path.join(script_dir, 'config.yaml')
    
    if not os.path.exists(harness_script):
        log(f"Test harness script not found: {harness_script}")
        return
    
    # Auto-detect date and version from the run log filename
    if not RUN_LOGFILE:
        log("No RUN_LOGFILE set — skipping test harness")
        return
    
    basename = os.path.basename(RUN_LOGFILE)
    # Extract date and version from "run_log_2026-07-26_v18.md"
    match = re.match(r"run_log_(\d{4}-\d{2}-\d{2})_(v\d+)\.md$", basename)
    if not match:
        log(f"Cannot parse date/version from run log: {basename}")
        return
    
    run_date, run_version = match.group(1), match.group(2)
    
    log(f"Running test harness for {run_date} {run_version}...")
    cmd = [
        sys.executable, harness_script,
        "--config", config_file,
        "--date", run_date,
        "--version", run_version,
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        # Log the full output
        for line in result.stdout.strip().split('\n'):
            log(f"[TEST HARNES] {line}")
        if result.stderr.strip():
            for line in result.stderr.strip().split('\n'):
                log(f"[TEST HARNES ERROR] {line}")
        
        exit_code = result.returncode
        status_label = {0: "PASS", 1: "WARN", 2: "FAIL"}.get(exit_code, f"EXIT_{exit_code}")
        log(f"Test harness finished: {status_label} (exit code {exit_code})")
    except FileNotFoundError:
        log(f"Test harness script not found at: {harness_script}")
    except subprocess.TimeoutExpired:
        log("Test harness timed out (30s)")
    except Exception as e:
        log(f"Test harness error: {e}")


if __name__ == "__main__":
    asyncio.run(main())



