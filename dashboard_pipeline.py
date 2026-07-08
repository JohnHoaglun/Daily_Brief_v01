#!/usr/bin/env python3
"""
Daily Brief Pipeline v0.2.5
===========================
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
import threading

# Ollama client -- network server at GX10 Ollama
_OLLAMA_HOST = "http://192.168.4.52:11434"
_qwen_client = ollama.Client(host=_OLLAMA_HOST, timeout=60)

# Log file lives in the vault's logs directory
LOG_DIR = "/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/logs"
LOGFILE = os.path.join(LOG_DIR, "daily_brief.log")
log_lock = threading.Lock()

# Thread pool with 6 workers for concurrent Ollama calls
_executor = ThreadPoolExecutor(max_workers=6)


def log(msg):
    """Log to file AND stderr. Thread-safe via lock."""
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    os.makedirs(LOG_DIR, exist_ok=True)
    with log_lock:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


# -- CONFIGURATION ----------------------------------------------------------

QWEN_MODEL = "qwen3.6-256k-agents:latest"
OUTPUT_DIR = "/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/"
WEATHER_LAT = "30.38"
WEATHER_LON = "-95.69"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

CATEGORIES = [
    ("World News",              "world+news",                 10),
    ("US News",                 "US+news",                    10),
    ("Texas News",              "Texas+news",                   5),
    ("Conroe TX News",          "Conroe+TX",                    5),
    ("Montgomery County TX News", "Montgomery+County+TX",       5),
    ("Weather Forecast 77316",  None,                           0),
    ("Houston Tropical Weather","Houston+hurricane+tropical",   5),
    ("Market News",             "stock+market+economy",          5),
    ("Semiconductors",          "semiconductor+chip+industry",   5),
    ("Big Tech",                "\"big+tech\"",                  5),
    ("Artificial Intelligence","artificial+intelligence+LLM",   5),
    ("OpenAI News",             "OpenAI",                        5),
    ("Anthropic News",          "Anthropic",                     5),
    ("SpaceX News",             "SpaceX",                        5),
    ("OpenCode News",           "opencode+ai",                   5),
    ("Hermes Agent News",       "hermes+agent",                  5),
    ("Andrej Karpathy Activity","Andrej Karpathy",               5),
]

SUMMARY_PROMPT = (
    "You are an objective news editor. You will be given a short news snippet from a search engine RSS feed. "
    "Write exactly 2-3 sentences summarizing the key facts: what happened, who was involved, when and where. "
    "Be neutral - no opinions, predictions, or editorializing.\n\n"
    "Use **bold** to highlight 3-5 key words or phrases: company names, technical terms, locations, numbers, dates, action verbs."
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


def normalize_title(title):
    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    return (parts[0] if parts else title.lower().strip())[:80].lower()


def get_pub_date(entry):
    for attr in ("published", "updated"):
        val = entry.get(attr)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return None


def format_pub_date(raw):
    if not raw:
        return None
    stripped = raw.strip()
    if len(stripped) >= 10 and stripped[:4].isdigit():
        return stripped[:10]
    try:
        ts = feedparser._parse_date(stripped)[0]
        if ts:
            return datetime.utcfromtimestamp(ts).strftime("%B %d, %Y")
    except Exception:
        pass
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
            pub_date = get_pub_date(e)
            if title and link:
                entries.append((title, link, raw, pub_date))
        return (name, entries)
    except Exception as e:
        log(f"  WARNING {name}: feed fetch failed ({e})")
        return (name, [])


async def extract_article(session, url):
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENT}, timeout=15) as resp:
            html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.extract()
        chunks = [t.get_text(separator=" ", strip=True) for t in soup.find_all(["p", "h1", "h2", "h3"])]
        text = " ".join(chunks).strip()
        return text if len(text) > 500 else ""
    except Exception:
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

def _summarize(context):
    """Blocking summary call."""
    if not context or len(context.strip()) < 50:
        return None
    try:
        t0 = time.time()
        r = _qwen_client.chat(
            model=QWEN_MODEL,
            messages=[
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": context[:6000]}
            ],
            options={"temperature": 0.3, "top_p": 0.8, "num_ctx": 4096}
        )
        log(f"SUMMARIZE: {time.time() - t0:.2f}s")
        return r["message"]["content"].strip().split('\n')[0].strip()
    except Exception as e:
        log(f"SUMMARIZE ERROR: {e}")
        return None


def _evaluate_alert(title, summary):
    """Blocking alert eval call."""
    try:
        t0 = time.time()
        r = _qwen_client.chat(
            model=QWEN_MODEL,
            messages=[
                {"role": "system", "content": ALERT_PROMPT},
                {"role": "user", "content": f"{title}\n---\n{summary}"[:1200]}
            ],
            options={"temperature": 0.1, "top_p": 0.3, "num_ctx": 4096}
        )
        log(f"ALERT: {time.time() - t0:.2f}s")
        return r["message"]["content"].strip().upper() == "TRUE"
    except Exception as e:
        log(f"ALERT ERROR: {e}")
        return False


def _run_blocking(fn, *args):
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(_executor, fn, *args)


# -- Stage workers (for parallel phase 3) -----------------------------------

class StoryPipelineState:
    __slots__ = ('title', 'link', 'category', 'pub_date', 'context', 'summary', 'is_alert')

    def __init__(self, title, link, snippet, category, pub_date):
        self.title = title
        self.link = link
        self.category = category
        self.pub_date = pub_date
        self.context = None
        self.summary = None
        self.is_alert = False


async def stage_enrich(story):
    """Phase 3A: If snippet is too short, extract full article from page."""
    if story.context is not None:
        return
    text = await extract_article(aiohttp_session, story.link)
    if text and len(text) > 500:
        story.context = text


def stage_summarize(story):
    """Phase 3B: Summarize via Ollama. Blocking -> runs in thread pool."""
    if not story.context or len(story.context.strip()) < 50:
        story.summary = None
        return
    summary = _summarize(story.context)
    story.summary = summary


def stage_alert(story):
    """Phase 3C: Evaluate alert via Ollama. Blocking -> runs in thread pool."""
    if not story.summary or 'Ollama' in story.summary or 'unavailable' in story.summary:
        return
    story.is_alert = _evaluate_alert(story.title, story.summary)


# -- Main -------------------------------------------------------------------

async def main():
    t0 = time.time()
    log("=" * 60)
    log("DAILY BRIEF v0.2.5 -- Pipeline Starting")
    log("=" * 60)

    global aiohttp_session
    aiohttp_session = None

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=100, limit_per_host=30, ttl_dns_cache=300),
        headers={"User-Agent": USER_AGENT}
    ) as session:
        global aiohttp_session
        aiohttp_session = session

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

        # Deduplicate: link + title normalize
        seen_links, seen_titles = set(), set()
        deduped = []
        for cat_name in by_cat:
            for title, link, snippet, pub_date in by_cat[cat_name]:
                norm = normalize_title(title)
                if link not in seen_links and norm not in seen_titles:
                    seen_links.add(link)
                    seen_titles.add(norm)
                    deduped.append((title, link, snippet, cat_name, pub_date))

        total_after_dedup = len(deduped)
        log(f"  Deduplicated: {total_before_dedup} -> {total_after_dedup} stories")

        # ---------- Phase 3A: Article extraction (async fan-out) ----------
        log("\n[Phase 3] Enriching + summarizing...")
        log("  [3A] Extracting article text where snippets are short...")

        stories = []
        for title, link, snippet, cat, pub_date in deduped:
            s = StoryPipelineState(title, link, snippet, cat, pub_date)
            if snippet and len(snippet) >= 50:
                s.context = snippet
            stories.append(s)

        total = len(stories)
        need_fetch = sum(1 for s in stories if s.context is None)
        log(f"  {need_fetch} articles need full extraction")

        fetch_done = await asyncio.gather(*(stage_enrich(s) for s in stories), return_exceptions=True)
        still_no_text = sum(1 for i, r in enumerate(fetch_done) if stories[i].context is None and need_fetch > 0)

        enriched = sum(1 for s in stories if s.context is not None)
        log(f"  Articles ready for summarization: {enriched}")

        # ---------- Phase 3B: Summarize (thread pool, fan-out) ----------
        log("  [3B] Running summaries...")
        summary_tasks = [_run_blocking(stage_summarize, s) for s in stories]
        await asyncio.gather(*summary_tasks, return_exceptions=True)

        sum_ok = sum(1 for s in stories if s.summary is not None)
        sum_fail = total - sum_ok
        log(f"  Summaries done: {sum_ok} OK / {sum_fail} failed")

        # ---------- Phase 3C: Alert evaluation (thread pool, fan-out) ----------
        log("  [3C] Evaluating alerts...")
        alert_tasks = [_run_blocking(stage_alert, s) for s in stories]
        await asyncio.gather(*alert_tasks, return_exceptions=True)

        alert_count = sum(1 for s in stories if s.is_alert)
        log(f"  Alerts flagged: {alert_count}")
        log(f"\n  PROCESSING COMPLETE: {total} stories in {time.time() - t0:.2f}s")

        # ---------- Phase 4: Build sections + render Markdown ----------
        log("\n[Phase 4] Rendering report...")

        sections = {}
        alerts_list = []
        for s in stories:
            smry = s.summary if s.summary else "[Summary unavailable]"
            entry = {'title': s.title, 'link': s.link, 'category': s.category,
                     'summary': smry, 'is_alert': s.is_alert, 'pub_date': s.pub_date}
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
                pub = format_pub_date(a['pub_date'])
                pub_line = f"\n*Originally published on: {pub}*" if pub else ""
                md.append("")
                md.append(f"### [{a['title']}]({a['link']})")
                md.append(a['summary'] + pub_line)
                md.append(f"*Category: {a['category']}*")

        # Category sections
        for cn in ordered_cats:
            cat_stories = sections_map.get(cn, [])
            md += ["", f"## {cn} ({len(cat_stories)} stories)", ""]
            for idx, st in enumerate(cat_stories):
                title_text = st['title']
                url_val = st['link']
                link_md = f"[{title_text}]({url_val})" if url_val and url_val != '#' else title_text
                pub = format_pub_date(st.get('pub_date'))
                pub_line = f"\n*Originally published on: {pub}*" if pub else ""
                md.append("")
                md.append(f"### {idx + 1}. {link_md}")
                md.append(st['summary'] + pub_line)

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
