#!/usr/bin/env python3
"""
Test script for browser-based article extraction from Google News tracking URLs.

This script tests whether we can use Playwright or Selenium to access 
Google News tracking URLs and extract full article text.
"""

import asyncio
import aiohttp
import feedparser
from bs4 import BeautifulSoup
import time

# Check if playwright is available
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

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

async def extract_with_browser(url):
    """Extract article text using browser automation."""
    if not PLAYWRIGHT_AVAILABLE:
        return None
        
    try:
        async with async_playwright() as p:
            # Launch browser in headless mode
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Set user agent to match the RSS feed's expected behavior  
            await page.set_extra_http_headers({"User-Agent": USER_AGENT})
            
            # Navigate to URL and wait for redirect
            await page.goto(url, wait_until="networkidle")
            
            # Wait for content to load - try different strategies if needed
            await page.wait_for_timeout(3000)
            
            # Try to extract article text using common selectors
            text_content = ""
            
            # Strategy 1: Look for article content containers
            selectors = [
                "article",
                ".article-content",
                "[class*='article']",
                "[data-article]",
                "main",
                ".content"
            ]
            
            for selector in selectors:
                elements = await page.query_selector_all(selector)
                if elements:
                    text_content = await elements[0].evaluate("el => el.textContent")
                    if len(text_content.strip()) > 500:  # Only use if substantial content
                        break
            
            # Fallback: try getting text from body
            if not text_content or len(text_content.strip()) < 500:
                text_content = await page.evaluate("document.body.textContent")
            
            await browser.close()
            
            return text_content if text_content and len(text_content.strip()) > 100 else None
            
    except Exception as e:
        print(f"Browser extraction failed for {url}: {e}")
        return None

async def main():
    print("Testing browser-based article extraction from Google News tracking URLs...")
    
    if not PLAYWRIGHT_AVAILABLE:
        print("\nPlaywright is NOT available in this environment.")
        print("To run this test, please install Playwright:")
        print("  pip install playwright")
        print("  playwright install chromium")
        print("\nThen rerun this script.")
        return
        
    print("\nFetching RSS feeds to get tracking URLs...")
    
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
        
        # Collect tracking URLs
        tracking_urls = []
        by_cat = {}
        for result in all_results:
            if isinstance(result, Exception):
                continue
            name, entries = result
            if not isinstance(entries, list):
                entries = []
            by_cat[name] = entries
            
            for i, (title, link, snippet) in enumerate(entries):
                # Only consider tracking URLs
                if link.startswith("https://news.google.com/rss/articles/"):
                    tracking_urls.append((name, title, link))
                    
        print(f"\nFound {len(tracking_urls)} tracking URLs to test with browser...")
        
        success_count = 0
        total_chars_extracted = 0
        
        # Test extraction on 5 tracking URLs
        test_urls = tracking_urls[:5]
        for i, (category, title, url) in enumerate(test_urls):
            print(f"\nTest {i+1}: {category} - {title[:80]}...")
            
            extracted_text = await extract_with_browser(url)
            
            if extracted_text:
                char_count = len(extracted_text.strip())
                success_count += 1
                total_chars_extracted += char_count
                print(f"  SUCCESS: Extracted {char_count} characters")
            else:
                print("  FAILED: Could not extract article content")
                
        # Summary report
        print("\n" + "="*50)
        print("SUMMARY REPORT")
        print("="*50)
        if test_urls:
            success_rate = (success_count / len(test_urls)) * 100
            avg_chars = total_chars_extracted / success_count if success_count > 0 else 0
            print(f"Test URLs: {len(test_urls)}")
            print(f"Successful extractions: {success_count}")
            print(f"Success rate: {success_rate:.1f}%")
            print(f"Average chars extracted: {avg_chars:.0f}")
        else:
            print("No tracking URLs found for testing.")

if __name__ == "__main__":
    asyncio.run(main())