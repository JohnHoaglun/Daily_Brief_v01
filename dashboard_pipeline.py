#!/usr/bin/env python3
"""
Daily Brief Pipeline v0.1.0
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
from bs4 import BeautifulSoup
import ollama

# Ollama client configured for your network server at GX10 Ollama
OLLAMA_HOST = "http://192.168.4.52:11434"
_qwen_client = ollama.Client(host=OLLAMA_HOST, timeout=60)
from datetime import datetime, timezone
import os
import time

# ─── CONFIGURATION ───────────────────────────────────────────

QWEN_MODEL = "qwen3.6-256k-agents:latest"

OLLAMA_BASE_URL = "http://192.168.4.52:11434/v1"

OUTPUT_DIR = "/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/"

WEATHER_LAT = "30.38"
WEATHER_LON = "-95.69"

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# 17 Categories: (display_name, rss_query, max_stories)
CATEGORIES = [
    ("World News",             "world+news",                10),
    ("US News",                "US+news",                   10),
    ("Texas News",             "Texas+news",                 5),
    ("Conroe TX News",         "Conroe+TX",                  5),
    ("Montgomery County TX News", "Montgomery+County+TX",    5),
    ("Weather Forecast 77316", None,                         0),  # handled separately
    ("Houston Tropical Weather", "Houston+hurricane+tropical", 5),
    ("Market News",            "stock+market+economy",        5),
    ("Semiconductors",         "semiconductor+chip+industry",  5),
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
    "Be neutral – no opinions, predictions, or editorializing.\n\n"
    "Use **bold** to highlight 3-5 key words or phrases: company names, technical terms, locations, numbers, dates, action verbs."
)

ALERT_PROMPT = (
    "You are a news classifier. Judge if this brief story deserves an urgent alert based on these criteria:\n\n"
    "1. Extreme weather: hurricane, tornado, flood, freeze warnings – especially Houston/Texas/77316\n"
    "2. Major breakthroughs from OpenAI, Anthropic, SpaceX, OpenCode, or Hermes Agent\n"
    "3. Critical economic disruption, geopolitical crisis, or infrastructure failure\n\n"
    "Respond with exactly ONE word: TRUE or FALSE. Nothing else."
)

RSS_BASE = "https://news.google.com/rss/search?q="
RSS_PARAMS = "&hl=en-US&gl=US&ceid=US:en"


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
            title = e.get("title", "").strip() if isinstance(e.get("title"), str) else ""
            link = e.get("link", "") or "#"
            # Google RSS summary/description has a short paragraph per story – this is our source text for Qwen
            raw = (e.get("summary") or e.get("description") or "").strip() if isinstance(e.get("summary"), str) else ""
            if title and link:
                entries.append((title, link, raw))
        return category_name, entries
    except Exception as e:
        print(f"  ⚠ {category_name}: feed fetch failed ({e})")
        return category_name, []


async def fallback_fetch(session, url):
    """Optional: try to follow Google redirect and scrape full article text. Returns clean text or ''."""
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENT}, timeout=12, allow_redirects=True) as resp:
            html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.extract()
        chunks = [t.get_text() for t in soup.find_all(["p", "h1", "h2", "h3"])]
        text = " ".join(chunks).strip()
        return text[:6000] if len(text) > 500 else ""
    except Exception:
        return ""


def summarize_with_ollama(context_text):
    """Ask local Qwen to turn the context (snippet ± optional full text) into a 2-3 sentence summary."""
    if not context_text or len(context_text.strip()) < 50:
        return None  # signal empty context (pipeline will try fallback fetch or skip)
    try:
        r = _qwen_client.chat(
            model=QWEN_MODEL,
            messages=[
                {"role": "system", "content": SUMMARY_PROMPT},
                {"role": "user", "content": f"Snippet:\n{context_text}"}
            ],
            options={"temperature": 0.15},
        )
        return r["message"]["content"].strip()
    except Exception:
        return f"[Ollama unavailable]"


def evaluate_alert_with_ollama(title, summary):
    """Qwen one-shot classifier — TRUE or FALSE."""
    try:
        text = f"{title} — {summary}"[:1200]
        r = _qwen_client.chat(
            model=QWEN_MODEL,
            messages=[
                {"role": "system", "content": ALERT_PROMPT},
                {"role": "user", "content": text},
            ],
            options={"temperature": 0.0},
        )
        return "TRUE" in r["message"]["content"].strip().upper()
    except Exception:
        return False


async def fetch_weather(session, lat, lon):
    """Fetch NWS forecast for coordinates → next 3 periods."""
    try:
        async with session.get(
            f"https://api.weather.gov/points/{lat},{lon}",
            headers={"User-Agent": USER_AGENT}, timeout=10) as resp:
            point = await resp.json()
        if "properties" not in point:
            return []
        fc_url = point["properties"]["forecast"]
        async with session.get(
            fc_url, headers={"User-Agent": USER_AGENT + "/WeatherAgent"}, timeout=10) as resp:
            data = await resp.json()
        periods = data.get("properties", {}).get("periods", [])
        return periods[:3]
    except Exception as e:
        print(f"  ⚠ Weather fetch failed ({e})")
        return []


# ─── MAIN PIPELINE ──────────────────────────────────────────

async def main():
    t0 = time.time()
    print("=" * 60)
    print("  DAILY BRIEF v0.1.0 — Pipeline Starting")
    print("=" * 60)

    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=50, limit_per_host=20),
        headers={"User-Agent": USER_AGENT}
    ) as session:

        # --- Phase 1: Weather ---
        print("\n[Phase 1] Fetching NWS weather...")
        weather = await fetch_weather(session, WEATHER_LAT, WEATHER_LON)

        # --- Phase 2: RSS feeds (all concurrent) ---
        rss_items = [(c[0], build_rss_url(c[1]), c[2]) for c in CATEGORIES if c[1]]
        print(f"[Phase 2] Fetching {len(rss_items)} RSS feeds...")
        results = await asyncio.gather(*(fetch_feed(session, n, u, m) for n, u, m in rss_items))
        by_cat = {n: ents for n, ents in results}

        # DEDUPLICATION: flatten all stories, keep first (higher-priority category wins)
        seen_links = set()
        deduped = {}  # cat -> list of (title, link, snippet)
        for _cat_name, entries in by_cat.items():
            for title, link, snippet in entries:
                if link not in seen_links:
                    seen_links.add(link)
                    deduped.setdefault(_cat_name, []).append((title, link, snippet))
        # --- Phase 3: Enrich + Summarize (category-by-category) ---
        print("\n[Phase 3] Enriching articles and summarizing...")
        sections = []   # [(cat_name, [...story_dicts])]
        alerts = []     # high-priority story_dicts

        for cat, stories in deduped.items():
            if not stories:
                print(f"  - {cat}: no entries")
                continue

            cat_stories = []
            for title, link, snippet in stories:
                # Strategy: use RSS snippet as primary context.
                # If it's very short (<100 chars), try a fallback full-article fetch concurrently with the summarization step.
                if len(snippet) < 100:
                    # Launch async article fetch alongside ollama calls
                    fetch_task = asyncio.create_task(fallback_fetch(session, link))
                    summary = summarize_with_ollama(snippet)
                    if not summary or "[Ollama" in (summary or ""):
                        full_text = await fetch_task
                        summary = summarize_with_ollama(full_text)
                    if not summary:
                        summary = f"[Could not generate summary for this article]"
                else:
                    summary = summarize_with_ollama(snippet)

                is_alert = False
                if summary and "[Ollama" in (summary or ""):
                    is_alert = False
                elif summary:
                    is_alert = evaluate_alert_with_ollama(title, summary)

                cat_stories.append({"title": title, "link": link, "summary": summary or "", "category": cat, "is_alert": bool(is_alert)})

            sections.append((cat, cat_stories))
            # Collect alerts early for priority section
            for s in cat_stories:
                if s["is_alert"]:
                    alerts.append(s)

        # --- Phase 4: Render Markdown ---
        print("\n[Phase 4] Rendering report...")

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        ts_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        fn_ts = now.strftime("%Y-%m-%d__%H-%M-%S")
        filepath = os.path.join(OUTPUT_DIR, f"DailyBrief-{fn_ts}.md")
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        total = sum(len(s[1]) for s in sections)

        md = []
        # Frontmatter
        md += [
            "---",
            "title: Daily Brief",
            f"date: {date_str}",
            f"time_generated: {ts_iso}",
            "status: active",
            "content_age_window: 24 hours",
            f"story_count_total: {total}",
            "categories: 17",
            "---",
            "",
            f"# Daily Brief — {now.strftime('%B %d, %Y')}",
        ]

        # High-Priority section (if any)
        if alerts:
            md += ["", "---", "", "## HIGH-PRIORITY BULLETINS"]
            for a in alerts:
                md += [
                    "",
                    f"### {a['title']}",
                    a["summary"],
                    f"*Category: {a['category']}*",
                ]

        # Category sections — ordered by spec
        cat_order = [c[0] for c in CATEGORIES if c[1]]  # excludes "Weather Forecast 77316"
        sections_map = dict(sections)

        for cn in cat_order:
            stories = sections_map.get(cn, [])
            md += ["", f"## {cn} ({len(stories)} stories)", ""]
            for i, st in enumerate(stories, 1):
                # Headline as h3 — title is already the article headline from Google RSS
                md += [
                    f"### {st['title']}",
                    st["summary"],
                    "",
                ]

        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write("\n".join(md) + "\n")

        elapsed = time.time() - t0
        print(f"\n✓ Written to {filepath}")
        print(f"  Stories: {total} | Alerts: {len(alerts)} | Time: {elapsed:.1f}s")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
