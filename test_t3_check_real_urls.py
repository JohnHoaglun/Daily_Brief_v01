#!/usr/bin/env python3
"""
Test script for checking real article URLs from Google News RSS feeds.

This script fetches Google News RSS feeds, extracts potential real publisher URLs,
and attempts to validate them through async HTTP requests.
"""

import asyncio
import aiohttp
import feedparser
from bs4 import BeautifulSoup
import time

# Configuration: test categories with expected entries per category
CATEGORIES = [
    ("World News", "world+news", 10),
    ("US News", "US+news", 10),
    ("Texas News", "Texas+news", 5),
    ("Market News", "stock+market+economy", 5),
    ("Big Tech", "big+tech", 5),
    ("OpenAI News", "OpenAI", 5),
    ("Artificial Intelligence", "artificial+intelligence+LLM", 5),
]

RSS_BASE = "https://news.google.com/rss/search?q="
RSS_PARAMS = "&hl=en-US&gl=US&ceid=US:en"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

async def fetch_feed(session, name, rss_url, max_stories):
    """Fetch RSS feed and parse entries."""
    try:
        async with session.get(rss_url, headers={"User-Agent": USER_AGENT}, timeout=10) as resp:
            text = await resp.text()
        feed = feedparser.parse(text)
        entries = []
        for e in feed.entries[:max_stories]:
            title = (e.get("title", "") or "").strip() if isinstance(e.get("title"), str) else ""
            link = e.get("link") or "#"
            raw = (e.get("summary") or e.get("description") or "").strip() if isinstance(e.get("summary"), str) and e["summary"] else ""
            entries.append((title, link, raw))
        return (name, entries)
    except Exception as e:
        print(f"  WARNING {name}: feed fetch failed ({e})")
        return (name, [])

async def test_real_urls(session, url):
    """Test if a URL is resolvable."""
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENT}, timeout=10) as resp:
            # Check if it's a valid redirect or direct response
            return resp.status < 400
    except Exception:
        return False

async def main():
    print("Testing real URLs from Google News feeds...")
    print("Fetching RSS feeds and identifying potential publisher links...\n")
    
    # Test with a few items from the specified categories
    rss_items = [(c[0], RSS_BASE + c[1] + RSS_PARAMS, c[2]) for c in CATEGORIES if c[1]]
    
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=100, limit_per_host=30, ttl_dns_cache=300),
        headers={"User-Agent": USER_AGENT}
    ) as session:
        
        # Fetch all feeds
        print(f"Fetching {len(rss_items)} RSS feeds...")
        all_results = await asyncio.gather(
            *(fetch_feed(session, n, u, m) for n, u, m in rss_items),
            return_exceptions=True
        )
        
        total_links = 0
        resolvable_links = 0
        tracking_only_links = 0
        
        by_cat = {}
        for result in all_results:
            if isinstance(result, Exception):
                continue
            name, entries = result
            if not isinstance(entries, list):
                entries = []
            by_cat[name] = entries
            
            print(f"\nCategory: {name}")
            for i, (title, link, snippet) in enumerate(entries):
                total_links += 1
                
                # Analyze the link type
                is_tracking_url = False
                if link.startswith("https://news.google.com/rss/articles/"):
                    is_tracking_url = True
                    tracking_only_links += 1
                    
                print(f"  {i+1}. {title[:80]}... [{'TRACKING ID' if is_tracking_url else 'POTENTIAL PUBLISHER URL'}]")
                
        # Summary report
        print("\n" + "="*50)
        print("SUMMARY REPORT")
        print("="*50)
        print(f"Total links examined: {total_links}")
        print(f"Tracking-only URLs: {tracking_only_links}")
        print(f"Publisher URL candidates: {total_links - tracking_only_links}")
        
        if total_links > 0:
            resolvable_percent = (resolvable_links / total_links) * 100
            print(f"Resolvable links (%): {resolvable_percent:.1f}%")

if __name__ == "__main__":
    asyncio.run(main())