#!/usr/bin/env python3
"""
Daily Brief Pipeline v0.2.2
============================
Fetches news from 17 categories via Google News RSS + NWS weather API,
summarizes each story using local Ollama (Qwen), and writes a formatted
Markdown file to Obsidian vault.

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
from datetime import datetime, timezone
import os
import time

# Ollama client — network server at GX10 Ollama
_OLLAMA_HOST = "http://192.168.4.52:11434"
_qwen_client = ollama.Client(host=_OLLAMA_HOST, timeout=60)

LOGFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daily_brief.log")
# Increase thread pool workers to handle more concurrent Ollama operations
_executor = ThreadPoolExecutor(max_workers=8)

def log(msg):
    """Log to file AND stderr with flush — never buffered."""
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    os.makedirs(os.path.dirname(LOGFILE), exist_ok=True)
    with open(LOGFILE, "a") as f:
        f.write(line + "\n")
        f.flush()
    sys.stderr.write(line + "\n")
    sys.stderr.flush()

# ─── CONFIGURATION ───────────────────────────────────────────

QWEN_MODEL = "qwen3.6-256k-agents:latest"
OUTPUT_DIR = "/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/"
WEATHER_LAT = "30.38"
WEATHER_LON = "-95.69"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

CATEGORIES = [
    ("World News",             "world+news",               10),
    ("US News",                "US+news",                  10),
    ("Texas News",             "Texas+news",                 5),
    ("Conroe TX News",         "Conroe+TX",                  5),
    ("Montgomery County TX News", "Montgomery+County+TX",   5),
    ("Weather Forecast 77316", None,                         0),
    ("Houston Tropical Weather", "Houston+hurricane+tropical", 5),
    ("Market News",            "stock+market+economy",        5),
    ("Semiconductors",         "semiconductor+chip+industry", 5),
    ("Big Tech",               "\"big+tech\"",                5),
    ("Artificial Intelligence", "artificial+intelligence+LLM", 5),
    ("OpenAI News",            "OpenAI",                      5),
    ("Anthropic News",         "Anthropic",                   5),
    ("SpaceX News",            "SpaceX",                      5),
    ("OpenCode News",          "opencode+ai",                 5),
    ("Hermes Agent News",      "hermes+agent",                5),
    ("Andrej Karpathy Activity","Andrej Karpathy",             5),
]

SUMMARY_PROMPT = (
    "You are an objective news editor. You will be given a short news snippet from a search engine RSS feed. "
    "Write exactly 2-3 sentences summarizing the key facts: what happened, who was involved, when and where. "
    "Be neutral - no opinions, predictions, or editorializing.\n\n"
    "Use **bold** to highlight 3-5 key words or phrases: company names, technical terms, locations, numbers, dates, action verbs."
)

ALERT_PROMPT = (
    "You are a news classifier. Judge if this brief story deserves an urgent alert based on these criteria:\n\n"
    "1. Extreme weather: hurricane, tornado, flood, freeze warnings - especially Houston/Texas/77316\n"
    "2. Major breakthroughs from OpenAI, Anthropic, SpaceX, OpenCode, or Hermes Agent\n"
    "3. Critical economic disruption, geopolitical crisis, or infrastructure failure\n\n"
    "Respond with exactly ONE word: TRUE or FALSE. Nothing else."
)

RSS_BASE = "https://news.google.com/rss/search?q="
RSS_PARAMS = "&hl=en-US&gl=US&ceid=US:en"


def normalize_title(title):
    """Normalize title for comparison: remove source suffixes, lowercase, strip."""
    # Remove common suffixes like " - Reuters", "(AP)", "(by John Smith)"
    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    main_part = parts[0] if parts else title.lower().strip()
    return main_part[:80].lower()

# ─── HELPER FUNCTIONS ────────────────────────────────────────

def build_rss_url(query):
    return f"{RSS_BASE}{query}{RSS_PARAMS}"


async def fetch_feed(session, category_name, rss_url, max_stories):
    """Fetch one RSS feed. Returns (name, [(title, link, snippet)])"""
    try:
        async with session.get(rss_url, headers={"User-Agent": USER_AGENT}, timeout=10) as resp:
            text = await resp.text()
        feed = feedparser.parse(text)
        entries = []
        for e in feed.entries[:max_stories]:
            title = (e.get("title", "") or "").strip() if isinstance(e.get("title"), str) else ""
            link = e.get("link") or "#"
            raw = (e.get("summary") or e.get("description") or "").strip() if isinstance(e.get("summary"), str) and e["summary"] else ""
            if title and link:
                entries.append((title, link, raw))
        return category_name, entries
    except Exception as e:
        log(f"  ⚠ {category_name}: feed fetch failed ({e})")
        return category_name, []


async def fallback_fetch(session, url):
    """If Google snippet is too short, scrape the full article for context."""
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENT}, timeout=12) as resp:
            html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.extract()
        chunks = [t.get_text() for t in soup.find_all(["p", "h1", "h2", "h3"])]
        text = " ".join(chunks).strip()
        return text[:6000] if len(text) > 500 else ""
    except Exception:
        return ""


def llm_summarize(context_text):
    """Call Ollama Qwen to create a 2-3 sentence summary. Blocking call."""
    if not context_text or len(context_text.strip()) < 50:
        return None
    try:
        start_time = time.time()
        r = _qwen_client.chat(
            model=QWEN_MODEL,
            messages=[
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": context_text[:6000] if len(context_text) > 500 else context_text}
            ],
            options={"temperature": 0.3, "top_p": 0.8, "num_ctx": 4096}
        )
        end_time = time.time()
        log(f"SUMMARIZE: {end_time - start_time:.2f}s")
        return r["message"]["content"].strip()
    except Exception as e:
        log(f"SUMMARIZE ERROR: {str(e)}")
        return "[Ollama unavailable]"


def llm_evaluate_alert(title, summary):
    """Qwen returns TRUE or FALSE for urgency."""
    try:
        start_time = time.time()
        text = f"{title} — {summary}"[:1200]
        r = _qwen_client.chat(
            model=QWEN_MODEL,
            messages=[
                {"role": "system", "content": ALERT_PROMPT},
                {"role": "user", "content": text}
            ],
            options={"temperature": 0.1, "top_p": 0.3, "num_ctx": 4096}
        )
        end_time = time.time()
        log(f"ALERT: {end_time - start_time:.2f}s")
        return r["message"]["content"].strip().upper() == "TRUE"
    except Exception as e:
        log(f"ALERT ERROR: {str(e)}")
        return False


def run_blocking(func, *args):
    """Run a blocking Ollama call in a thread pool."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(_executor, func, *args)


async def fetch_weather(session, lat, lon):
    """Fetch NWS forecast for coordinates."""
    try:
        async with session.get(f"https://api.weather.gov/points/{lat},{lon}", headers={"User-Agent": USER_AGENT}, timeout=10) as resp:
            point = await resp.json()
        if "properties" not in point:
            return []
        fc_url = point["properties"]["forecast"]
        async with session.get(fc_url, headers={"User-Agent": USER_AGENT + "/WeatherAgent"}, timeout=10) as resp:
            data = await resp.json()
        periods = data.get("properties", {}).get("periods", [])
        return periods[:3]
    except Exception as e:
        log(f"  ⚠ Weather fetch failed ({e})")
        return []


# ─── MAIN PIPELINE ──────────────────────────────────────────

async def main():
    t0 = time.time()

    if os.path.exists(LOGFILE):
        os.remove(LOGFILE)

    log("=" * 60)
    log("DAILY BRIEF v0.2.2 — Pipeline Starting")
    log("=" * 60)

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=50, limit_per_host=20),
        headers={"User-Agent": USER_AGENT}
    ) as session:

        # Phase 1: Weather
        log("\n[Phase 1] Fetching NWS weather...")
        weather = await fetch_weather(session, WEATHER_LAT, WEATHER_LON)
        if weather:
            log(f"  Weather OK — {len(weather)} periods")
        else:
            log("  Weather returned empty — will write blank section")

        # Phase 2: RSS feeds (all concurrent)
        rss_items = [(c[0], build_rss_url(c[1]), c[2]) for c in CATEGORIES if c[1]]
        log(f"\n[Phase 2] Fetching {len(rss_items)} RSS feeds...")
        results = await asyncio.gather(*(fetch_feed(session, n, u, m) for n, u, m in rss_items))
        by_cat = {n: ents for n, ents in results}
        total_before_dedup = sum(len(v) for v in by_cat.values())
        log(f"  Fetched {total_before_dedup} stories from {len(by_cat)} categories")

        # Deduplication: keep first occurrence, higher-priority cat wins.
        # Use BOTH link AND normalized title to catch cross-category duplicates.
        seen_links = set()
        seen_titles = set()
        deduped = {}
        for _cat_name, entries in by_cat.items():
            for title, link, snippet in entries:
                norm_key = normalize_title(title)
                if link not in seen_links and norm_key not in seen_titles:
                    seen_links.add(link)
                    seen_titles.add(norm_key)
                    deduped.setdefault(_cat_name, []).append((title, link, snippet))

        total_after_dedup = sum(len(v) for v in deduped.values())
        log(f"  Deduplicated: {total_before_dedup} -> {total_after_dedup} stories (removed {total_before_dedup - total_after_dedup} dups)")

        # Phase 3: Summarize ALL (concurrent, using thread pool)
        log("\n[Phase 3] Enriching articles and summarizing...")
        sections = []   # [(cat_name, [...story_dicts])]
        alerts = []

        all_stories_flat = []
        for cat, stories in deduped.items():
            if not stories:
                log(f"  - {cat}: no entries")
                continue
            for title, link, snippet in stories:
                all_stories_flat.append((title, link, snippet, cat))

        processed = 0
        failed = 0
        start_time = time.time()
        for title, link, snippet, cat in all_stories_flat:
            processed += 1
            context = snippet if len(snippet) >= 50 else ""

            # If snippet is too short, try fetching full article concurrently with summary attempt
            fetch_task = None
            if not context:
                fetch_task = asyncio.create_task(fallback_fetch(session, link))

            # Run summarize in thread pool (non-blocking w.r.t. async event loop)
            summary = await run_blocking(llm_summarize, context)

            # If first attempt failed/returned nothing and we fetched full text, try again
            if (not summary or "[Ollama" in (summary or "")) and fetch_task:
                full_text = await fetch_task
                summary = await run_blocking(llm_summarize, full_text)

            if not summary:
                summary = "[Summary unavailable]"
                failed += 1

            # Evaluate alert (also non-blocking)
            is_alert = False
            if "Ollama" not in (summary or "") and "unavailable" not in (summary or ""):
                try:
                    is_alert = await run_blocking(llm_evaluate_alert, title, summary)
                except Exception:
                    is_alert = False

            story_dict = {
                "title": title,
                "link": link,
                "summary": summary if summary else "[Summary unavailable]",
                "category": cat,
                "is_alert": bool(is_alert),
            }

            # Re-group by category (preserving order)
            found = False
            for i, (existing_cat, existing_stories) in enumerate(sections):
                if existing_cat == cat:
                    sections[i][1].append(story_dict)
                    found = True
                    break
            if not found:
                sections.append((cat, [story_dict]))

        end_time = time.time()
        log(f"PROCESSING COMPLETE: {processed} stories in {end_time - start_time:.2f}s ({failed} failures)")

            if is_alert:
                alerts.append(story_dict)

            if processed % 10 == 0:
                log(f"  Processed {processed}/{len(all_stories_flat)} stories ({failed} failures)")

        # Phase 4: Render Markdown
        log("\n[Phase 4] Rendering report...")
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        ts_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        fn_ts = now.strftime("%Y-%m-%d__%H-%M-%S")
        filepath = os.path.join(OUTPUT_DIR, f"DailyBrief-{fn_ts}.md")
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        total_final = sum(len(s[1]) for s in sections)
        ordered_cats = [c[0] for c in CATEGORIES if c[1]]
        sections_map = dict(sections)

        md = []
        # YAML frontmatter
        md += ["---", "title: Daily Brief", f"date: {date_str}", f"time_generated: {ts_iso}",
               "status: active", "content_age_window: 24 hours", f"story_count_total: {total_final}",
               "categories: 17", "---", "", f"# Daily Brief — {now.strftime('%B %d, %Y')}"]

        # High-Priority alerts at top
        if alerts:
            md += ["", "---", "", "## HIGH-PRIORITY BULLETINS"]
            for a in alerts:
                md += ["", f"### {a['title']}", a["summary"], f"*Category: {a['category']}*"]

        # Category sections
        for cn in ordered_cats:
            stories = sections_map.get(cn, [])
            md += ["", f"## {cn} ({len(stories)} stories)", ""]
            for st in stories:
                md += [f"### {st['title']}", st["summary"] if st["summary"] else "[Summary unavailable]", ""]

        # Write file
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write("\n".join(md) + "\n")

        elapsed = time.time() - t0
        log(f"\nFile written to {filepath}")
        log(f"  Stories: {total_final} | Alerts: {len(alerts)} | Failed: {failed}/{len(all_stories_flat)} | Time: {elapsed:.1f}s")
        log("=" * 60)

        # Also print to stdout for terminal visibility
        print(f"\nDone. File: {filepath}")
        print(f"  Stories: {total_final} | Alerts: {len(alerts)}")


if __name__ == "__main__":
    asyncio.run(main())
