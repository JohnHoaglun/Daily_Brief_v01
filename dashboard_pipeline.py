#!/usr/bin/env python3
"""
Daily Brief Pipeline v0.2.5-BETA09
===================================
BETA07: RSS snippets as primary summary context; headline fallback for low-context.
BETA08: BATCH summarization — single Ollama call processes all 40-90 stories at once (2.5x speedup over individual calls). 
        ARTICLE EXTRACTION REMOVED — Google News provides only internal article IDs, not real publisher URLs.
        ALERTS: also batched into single call. Removed threading deadlocks from server-side single-thread bottleneck.
        FILTER: excludes Conroe TX property listings; Big Tech query fixed.
BETA09 (current): BATCH summarization redesigned — one Ollama call per category instead of all stories combined,
                  prevents context overflow (was 92K chars → now ~400-1200 per batch). Switched to gemma4:e2b 
                  (~6s per batch vs ~45s with qwen3.6-256k). Google News tracking URLs handled via title+snippet context.

No API keys required. All sources are free and keyless.

Run: python dashboard_pipeline.py
"""

import asyncio
import aiohttp
import feedparser
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
import ollama
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import os
import time
from email.utils import parsedate_to_datetime
import threading
from playwright.async_api import async_playwright

# Ollama client -- network server at GX10 Ollama
_OLLAMA_HOST = "http://192.168.4.52:11434"
_llm_client = ollama.Client(host=_OLLAMA_HOST, timeout=180)

# Log file lives in the logs directory inside Obsidian vault (unique .md per run)
LOG_DIR = "/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/logs"
RUN_LOGFILE = None   # set dynamically at start of each run as .md
log_lock = threading.Lock()

# Thread pool with 3 workers to match Ollama NUM_PARALLEL=3 limit
_executor = ThreadPoolExecutor(max_workers=3)

# Browser pool for Playwright
_browser_lock = None  # Used only at startup
async def _get_browser():
    """Singleton browser instance — created once, reused."""
    if not hasattr(_get_browser, '_cache') or _get_browser._cache is None:
        p = await async_playwright().start()
        _get_browser._cache = await p.chromium.launch(headless=True)
    return _get_browser._cache

# Configuration: only include stories within last 24 hours (default)
DEFAULT_AGE_LIMIT_HOURS = 24
CATEGORY_AGE_LIMITS = {
    "Conroe TX News": 48,
    "Montgomery County TX News": 48,
    "Houston Tropical Weather": 48,
}


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

LLM_MODEL = "gemma4:e2b"
OUTPUT_DIR = "/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/"
WEATHER_LAT = "30.38"
WEATHER_LON = "-95.69"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

CATEGORIES = [
    ("World News",              "world+news",                 10),
    ("US News",                 "US+news",                    10),
    ("Texas News",              "Texas+news",                   5),
    ("Conroe TX News",          "news+Conroe+TX",               5),
    ("Montgomery County TX News", "Montgomery+County+TX",       5),
    ("Weather Forecast 77316",  None,                           0),
    ("Houston Tropical Weather","Houston+hurricane+tropical",   5),
    ("Market News",             "stock+market+economy",          5),
    ("Semiconductors",          "semiconductor+chip+industry",   5),
    ("Big Tech",                "big+tech",                      5),
    ("Artificial Intelligence","artificial+intelligence+LLM",   5),
    ("OpenAI News",             "OpenAI",                        5),
    ("Anthropic News",          "Anthropic",                     5),
    ("SpaceX News",             "SpaceX",                        5),
    ("OpenCode News",           "opencode+ai",                   5),
    ("Hermes Agent News",       "hermes+agent",                  5),
    ("Andrej Karpathy Activity","Andrej Karpathy",               5),
]

SUMMARY_PROMPT = (
    "You are an objective news editor. Write exactly 2-3 sentences summarizing the key facts of this article: "
    "what happened, who was involved, when and where.\n\n"
    "Be neutral - no opinions, predictions, or editorializing."
)

ALERT_PROMPT = (
    "You are a news classifier. Judge if this brief story deserves an urgent alert:\n\n"
    "1. Extreme weather: hurricane, tornado, flood, freeze - esp Houston/Texas/77316\n"
    "2. Major breakthroughs from OpenAI, Anthropic, SpaceX, OpenCode, Hermes Agent\n"
    "3. Critical economic disruption, geopolitical crisis, infrastructure failure\n\n"
    "Respond with exactly ONE word: TRUE or FALSE. Nothing else."
)

RSS_BASE = "https://news.google.com/rss/search?q="
RSS_PARAMS = "&hl=en-US&gl=US&ceid=US:en"


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
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(stripped, fmt)
        except ValueError:
            continue
    return None


def format_pub_date(raw):
    """Format a publication date into readable form."""
    if not raw:
        return None
    if isinstance(raw, datetime):
        tz = raw.strftime("%Z") if raw.tzinfo else ""
        return raw.strftime(f"%Y-%m-%d {tz}").strip()
    stripped = raw.strip()
    if len(stripped) >= 10 and stripped[:4].isdigit():
        return stripped[:10]
    return stripped[:40]


# -- HTTP helpers (async) ---------------------------------------------------

def build_rss_url(query):
    return f"{RSS_BASE}{query}{RSS_PARAMS}"


async def fetch_feed(session, name, rss_url, max_stories):
    try:
        async with session.get(rss_url, headers={"User-Agent": USER_AGENT}, timeout=10) as resp:
            text = await resp.text()
        feed = feedparser.parse(text)
        entries = []
        for e in feed.entries[:max_stories]:
            title = (e.get("title", "") or "").strip() if isinstance(e.get("title"), str) else ""
            link = e.get("link") or "#"
            raw = (e.get("summary") or e.get("description") or "").strip() if isinstance(e.get("summary"), str) and e["summary"] else ""
            pub_dt = parse_feed_date(e)
            # Strip HTML from snippet so we can measure REAL text length for extraction decision
            plain_snippet = strip_html(raw)
            if title and link:
                entries.append((title, link, plain_snippet, pub_dt))
        return (name, entries)
    except Exception as e:
        log(f"  WARNING {name}: feed fetch failed ({e})")
        return (name, [])


async def extract_article(session, url):
    """Extract article text using Playwright for JS-rendered pages (including Google News tracking URL redirects)."""
    if not url or url == "#" or not url.strip():
        return ""
    
    # If it's a Google tracking URL, skip — not a real publisher page.
    # The title + snippet from the RSS feed will be used instead for summarization.
    if "news.google.com/rss/articles/" in url:
        return ""
    
    # For non-Google URLs, fall through to existing aiohttp logic
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENT}, timeout=25) as resp:
            html = await resp.text()
        if resp.status != 200:
            return ""
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.extract()
        chunks = [t.get_text(separator=" ", strip=True) for t in soup.find_all(["p", "h1", "h2", "h3"])]
        text = " ".join(chunks).strip()
        return text if len(text) > 40 else ""
    except Exception as e:
        log(f"  [extract FAILED] '{url[:80]}...': {e}")
        return ""


async def fetch_weather(session, lat, lon):
    try:
        async with session.get(f"https://api.weather.gov/points/{lat},{lon}", headers={"User-Agent": USER_AGENT}, timeout=10) as resp:
            point = await resp.json()
        if "properties" not in point:
            return []
        fc_url = point["properties"]["forecast"]
        async with session.get(fc_url, headers={"User-Agent": USER_AGENT + "/DailyBrief/1.0"}, timeout=10) as resp:
            data = await resp.json()
        return data.get("properties", {}).get("periods", [])[:3]
    except Exception as e:
        log(f"  WARNING Weather fetch failed ({e})")
        return []


# -- Ollama helpers (blocking, run in thread pool) -------------------------

def _summarize(context, min_chars=100):
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
                    {"role": "user", "content": context[:6000]}
                ],
                options={"temperature": 0.3, "top_p": 0.8, "num_ctx": 4096}
            )
            log(f"SUMMARIZE: {time.time() - t0:.2f}s")
            return r["message"]["content"].strip().split('\n')[0].strip()
        except Exception as e:
            if attempt == 0:
                log(f"SUMMARIZE attempt 1 failed ({e}), retrying 3s...")
                time.sleep(3)
            else:
                log(f"SUMMARIZE ERROR (final): {e}")
    return None


def _evaluate_alert(title, summary):
    """Blocking alert eval call with retry."""
    for attempt in range(2):
        try:
            t0 = time.time()
            r = _llm_client.chat(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": ALERT_PROMPT},
                    {"role": "user", "content": f"{title}\n---\n{summary}"[:1200]}
                ],
                options={"temperature": 0.1, "top_p": 0.3, "num_ctx": 4096}
            )
            log(f"ALERT: {time.time() - t0:.2f}s")
            return r["message"]["content"].strip().upper() == "TRUE"
        except Exception as e:
            if attempt == 0:
                log(f"ALERT attempt 1 failed ({e}), retrying 3s...")
                time.sleep(3)
            else:
                log(f"ALERT ERROR (final): {e}")
    return False


def _run_blocking(fn, *args):
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(_executor, fn, *args)


# -- Stage workers (for parallel phase 3) -----------------------------------

class StoryPipelineState:
    __slots__ = ("title", "link", "snippet", "category", "pub_dt", "context", "summary", "is_alert", "_batch_context", "_alert_idx")

    def __init__(self, title, link, snippet, pub_dt, category):
        self.title = title
        self.link = link
        self.snippet = snippet
        self.category = category
        self.pub_dt = pub_dt
        self.context = None
        self.summary = None
        self.is_alert = False
        self._batch_context = None
        self._alert_idx = None


async def stage_extract_article(story, session):
    """Phase 3A: Fetch full article text from source URL for summary context."""
    url = story.link.strip()
    if not url or url == "#" or url.startswith("#"):
        return
    # Skip Google News links as they're tracking IDs (no real content) - we will extract them differently
    # We now handle them in the main extraction function that uses Playwright
    try:
        result = await extract_article(session, url)
        if result:
            story.context = result
    except Exception as e:
        log(f"  [extract error] '{story.title[:60]}...': {e}")


def build_context(story):
    """Build the text context for a single story — capped at 600 chars for batch processing."""
    context = story.context
    if context and len(str(context).strip()) >= 50:
        return str(context).strip()[:600]  # Cap article content
    
    parts = [v.strip() for v in [story.snippet, story.title] if v and len((v or "").strip()) > 0]
    if not parts:
        return f"{story.category}: {story.title}"
    
    inner = "\n---\n".join(parts + [f"Category: {story.category}"])
    return inner[:600]


def batch_summarize_all(stories, session=None):
    """One batch summarization call per category. Returns dict mapping story object -> summary text."""
    if not stories:
        return {}
    
    # Group by category
    by_category = {}
    for s in stories:
        by_category.setdefault(s.category, []).append(s)
    
    all_summaries = {}
    
    # System prompt (same as before but simplified - no STORY_X format since we do per-category batches)
    SYSTEM_BATCH = ("You are a news summarization engine. For each story I list, produce exactly 2-3 sentences:\n"
                    "What happened, who was involved, when and where.\n\n"
                    "For EACH story numbered below (1., 2., 3., etc.), reply with one line in this EXACT format:\n"
                    "1: <your 2-3 sentence summary>\n"
                    "2: <your 2-3 sentence summary>\n"
                    "\nRequirements:\n"
                    "- Start directly with '1:' (no preamble)\n"
                    "- Each story gets exactly one line starting with the numbered tag\n"  
                    "- No bullet points, no markdown formatting\n"
                    "- Factual and neutral tone")
    
    total_parsed = 0
    for cat_name, cat_stories in by_category.items():
        # Build contexts for this category's stories
        context_lines = []
        for idx, s in enumerate(cat_stories):
            # Build a shorter context: title + first 400 chars of article if available
            context_parts = [s.title]
            content = build_context(s)  # This returns story.context if available and >= 50 chars, else snippet+title
            if len(content) > 600:
                content = content[:600]
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
                options={"temperature": 0.3, "top_p": 0.8, "num_ctx": 8192}
            )
            elapsed = time.time() - t0
            log(f"BATCH SUMMARIZE ({cat_name}, {len(cat_stories)} stories): {elapsed:.1f}s")
            
            resp_text = r["message"]["content"] if r.get("message", {}).get("content") else ""
            log(f"BATCH OUTPUT ({cat_name}, {len(resp_text)} chars): {resp_text[:500]}")
            
            # Parse per-category response
            reply_lines = [l.strip() for l in resp_text.split('\n') if l.strip()]
            
            for idx, s in enumerate(cat_stories):
                line_num = str(idx + 1) + ":"
                match_found = False
                for line in reply_lines:
                    if line.startswith(line_num):
                        summary = line[len(line_num):].strip()
                        if len(summary) > 30:
                            s.summary = summary
                            total_parsed += 1
                            match_found = True
                
                # Fallback if no valid line found
                if not match_found or (idx < len(cat_stories) and not cat_stories[idx].summary):
                    cat_stories[idx].summary = f"[Headline] {cat_stories[idx].title}"
                    log(f"  [parse gap] {cat_name} story {idx+1}")
            
        except Exception as e:
            log(f"BATCH SUMMARIZE ERROR ({cat_name}): {e}")
            # Set fallback summary for all stories in this category
            for s in cat_stories:
                s.summary = f"[Headline] {s.title}"
    
    return all_summaries


def parse_batch_response(response, expected_count):
    """Parse numbered batch response into dict mapping index → summary string.
    
    Handles output like:
    STORY_0: France and Spain are preparing...
    STORY_1: President Trump has ordered...
    ...
    """
    summaries = {}
    for line in response.split('\n'):
        line = line.strip()
        # Match STORY_<number>: or <number>: patterns
        if line.startswith('STORY_'):
            try:
                idx_str = line.split(':')[0].replace('STORY_', '')
                idx = int(idx_str)
                summary = ':'.join(line.split(':', 1))[1:].strip()  # Everything after "STORY_N:"
                summaries[idx] = summary.strip()
            except (ValueError, IndexError):
                pass
        else:
            # Fallback: <number>:. <text>
            parts = line.split(':', 1)
            if len(parts) == 2 and parts[0].strip().isdigit():
                idx = int(parts[0].strip())
                summaries[idx] = parts[1].strip()
    
    # Fill any missing indices with fallback based on title+context
    for idx in range(expected_count):
        if idx not in summaries:
            # Try to find the story's index by matching snippet in available output
            log(f"  [parse gap] STORY {idx} — no response line, using headline fallback")
            summaries[idx] = f"[Summary unavailable]"
    
    return summaries


def batch_evaluate_alerts(stories):
    """Single Ollama call to evaluate ALL stories for alert priority.
    Returns dict mapping index → True/False."""
    if not stories:
        return {}

    # Group by category to prevent overload and ensure proper handling
    by_category = {}
    for s in stories:
        by_category.setdefault(s.category, []).append(s)
    
    # Process each category separately to avoid hitting context limits or timeouts
    all_alerts = {}
    for cat_name, cat_stories in by_category.items():
        # Build input text — only include stories that have valid summaries
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
        
        SYSTEM_ALERT_BATCH = ("You are a news priority classifier. For EACH story provided, respond with exactly one line:\n"
                              "Format: STORY_<number>: TRUE or FALSE\n"
                              "Judge: extreme weather (hurricane/tornado/flood/freeze in Houston/Texas/77316), major breakthroughs from top tech labs,\n"
                              "critical economic disruption, geopolitical crises, or infrastructure failure.\n"
                              "Be conservative — only flag TRUE for genuinely important news. No preamble.\n\n"
                              "Use EXACT format:\n"
                              "STORY_0: TRUE\n"
                              "STORY_1: FALSE\n"
                              "STORY_2: TRUE\n")

        for attempt in range(2):
            try:
                t0 = time.time()
                r = _llm_client.chat(
                    model=LLM_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_ALERT_BATCH},
                        {"role": "user", "content": alert_text}
                    ],
                    options={"temperature": 0.1, "top_p": 0.3, "num_ctx": 8192}
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
    
    return {}


def parse_alert_batch_response(response):
    """Parse alert batch response into dict mapping index → bool."""
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
    t0 = time.time()
    
    # Unique log file per run (same convention as markdown output)
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d__%H-%M-%S")
    global RUN_LOGFILE, OUTPUT_DIR
    RUN_LOGFILE = os.path.join(LOG_DIR, f"run_log_{now_ts}.md")
    # Create the log directory if needed and verify it exists
    os.makedirs(LOG_DIR, exist_ok=True)
    
    log("=" * 60)
    log(f"RUN LOG: {RUN_LOGFILE}")
    log("DAILY BRIEF v0.2.5-BETA08 - Pipeline Starting")
    log("=" * 60)

    # Track age threshold
    now_ct = datetime.now(ZoneInfo("America/Chicago"))
    cutoff = now_ct - timedelta(hours=DEFAULT_AGE_LIMIT_HOURS)

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=100, limit_per_host=30, ttl_dns_cache=300),
        headers={"User-Agent": USER_AGENT}
    ) as session:

        # ---------- Phase 1: Weather (async) ----------
        log("\n[Phase 1] Fetching NWS weather...")
        weather = await fetch_weather(session, WEATHER_LAT, WEATHER_LON)
        if weather:
            log(f"  Weather OK -- {len(weather)} periods")
        else:
            log("  Weather returned empty")

        # ---------- Phase 2: RSS feeds (all async, concurrent) ----------
        rss_items = [(c[0], build_rss_url(c[1]), c[2]) for c in CATEGORIES if c[1]]
        log(f"\n[Phase 2] Fetching {len(rss_items)} RSS feeds...")
        
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

                # 3. Filter out real estate listings for Conroe TX News (after dedup but before adding to deduped)
                if cat_name == "Conroe TX News" and is_realt_estate_title(title):
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

        # ---------- Phase 3: Summarization + Alerts (single batch calls) ----------
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
        sum_results = batch_summarize_all(stories, session)
        sum_ok = sum(1 for s in stories if s.summary is not None and not s.summary.startswith("[Summary"))
        sum_fail = total - sum_ok
        log(f"  Summaries done: {sum_ok} OK / {sum_fail} failed")

        # ---------- Phase 3C: Batch alert evaluation (single Ollama call) ----------
        log("  [3C] Evaluating alerts in BATCH...")
        alert_results = batch_evaluate_alerts(stories)
        alert_count = sum(1 for s in stories if s.is_alert)
        log(f"  Alerts flagged: {alert_count}")
        log(f"\n  PROCESSING COMPLETE: {total} stories in {time.time() - t0:.2f}s")

        # ---------- Phase 4: Build sections + render Markdown ----------
        log("\n[Phase 4] Rendering report...")

        sections = {}
        alerts_list = []
        for s in stories:
            smry = s.summary if s.summary else "[Summary unavailable]"
            entry = {
                "title": s.title,
                "link": s.link,
                "category": s.category,
                "summary": smry,
                "is_alert": s.is_alert,
                "pub_date": format_pub_date(s.pub_dt),
            }
            sections.setdefault(s.category, []).append(entry)
            if s.is_alert:
                alerts_list.append(entry)

        now = datetime.now(timezone.utc)
        fn_ts = now.strftime("%Y-%m-%d__%H-%M-%S")
        filepath = os.path.join(OUTPUT_DIR, f"DailyBrief-{fn_ts}.md")
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        ordered_cats = [c[0] for c in CATEGORIES if c[1]]
        sections_map = {cn: sections.get(cn, []) for cn in ordered_cats}

        # -- Build markdown --
        md = []
        md.append("---")
        md.append("title: Daily Brief")
        md.append(f"date: {now.strftime('%Y-%m-%d')}")
        md.append(f"time_generated: {now.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        md.append("status: active")
        md.append("content_age_window: 24 hours")
        md.append(f"story_count_total: {total_after_dedup}")
        md.append("categories: 17")
        md.append("---")
        md.append("")
        md.append(f"# Daily Brief -- {now.strftime('%B %d, %Y')}")

        # High-Priority Bulletins
        if alerts_list:
            md += ["", "---", "", "## HIGH-PRIORITY BULLETINS"]
            for a in alerts_list:
                pub_line = f"\n*Originally published on: {a['pub_date']}*" if a.get("pub_date") else ""
                md.append("")
                md.append(f"### [{a['title']}]({a['link']})")
                md.append(a["summary"] + pub_line)
                md.append(f"*Category: {a['category']}*")

        # Category sections
        for cn in ordered_cats:
            cat_stories = sections_map.get(cn, [])
            md += ["", f"## {cn} ({len(cat_stories)} stories)", ""]
            for idx, st in enumerate(cat_stories):
                title_text = st["title"]
                url_val = st["link"]
                link_md = f"[{title_text}]({url_val})" if url_val and url_val != "#" else title_text
                pub_line = f"\n*Originally published on: {st['pub_date']}*" if st.get("pub_date") else ""
                md.append("")
                md.append(f"### {idx + 1}. {link_md}")
                md.append(st["summary"] + pub_line)

        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write("\n".join(md) + "\n")

        elapsed = time.time() - t0
        log(f"\nFile written to {filepath}")
        log(f"  Stories: {total_after_dedup} | Alerts: {len(alerts_list)} | Failed: {sum_fail}/{total} | Time: {elapsed:.1f}s")
        log("=" * 60)

        print(f"\nDone. File: {filepath}")
        print(f"  Stories: {total_after_dedup} | Alerts: {len(alerts_list)} | Failed: {sum_fail}/{total} | Time: {elapsed:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
