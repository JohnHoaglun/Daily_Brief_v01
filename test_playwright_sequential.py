#!/usr/bin/env python3
"""Playwright article extraction test — sequential batches (5 URLs each) with 30s gap between batches.

This script tests whether Playwright can reliably extract article text from Google News tracking URLs
when accessed SEQUENTIALLY in small batches, avoiding the concurrent "Execution context destroyed" crash.

Run: cd /Users/johnhoaglun/opencode/projects/Daily_Brief_v01 && python3 test_playwright_sequential.py
"""

import asyncio
import aiohttp
import feedparser
import time

from playwright.async_api import async_playwright


async def fetch_sample_tracking_urls():
    """Fetch ~15 Google News tracking URLs from RSS feeds for testing."""
    async with aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}) as session:
        feeds = [
            ('World News',      'https://news.google.com/rss/search?q=world+news&hl=en-US&gl=US&ceid=US:en'),
            ('US News',         'https://news.google.com/rss/search?q=US+news&hl=en-US&gl=US&ceid=US:en'),
            ('Big Tech',        'https://news.google.com/rss/search?q=big+tech&hl=en-US&gl=US&ceid=US:en'),
        ]
        
        urls = []
        for name, url in feeds:
            try:
                async with session.get(url) as response:
                    content = await response.text()
                    parsed_feed = feedparser.parse(content)
                    for entry in parsed_feed.entries[:5]:  # Get first 5 entries from each feed
                        if hasattr(entry, 'link'):
                            urls.append(entry.link)
            except Exception as e:
                print(f"Error fetching {name} feed: {e}")
                continue
                
        return urls[:15]  # Return first 15 URLs


async def extract_article_content(page, url):
    """Extract article content from a Google News tracking URL."""
    try:
        await page.goto(url, wait_until='networkidle')
        await page.wait_for_timeout(2000)
        
        # Wait for the main article content to load
        await page.wait_for_selector('article, .article-content, [class*="story"], [id*="article"]', timeout=10000)
        
        # Extract main content
        content = await page.evaluate("""
            () => {
                const selectors = [
                    'article',
                    '.article-content',
                    '[class*="story"]',
                    '[id*="article"]',
                    '.entry-content',
                    '.post-content'
                ];
                
                for (let selector of selectors) {
                    const element = document.querySelector(selector);
                    if (element) {
                        return element.innerText;
                    }
                }
                
                // Fallback to body content
                return document.body.innerText;
            }
        """)
        
        return content[:2000]  # Return first 2000 characters
        
    except Exception as e:
        print(f"Error extracting content from {url}: {e}")
        return None


async def test_sequential_extraction():
    """Run sequential batches of article extraction with 30s gaps."""
    urls = await fetch_sample_tracking_urls()
    if not urls:
        print("No URLs fetched for testing")
        return
        
    print(f"Testing with {len(urls)} URLs in batches of 5...")
    
    async with async_playwright() as p:
        # Use a single browser instance for all tests
        browser = await p.chromium.launch(headless=True)
        
        try:
            # Process in batches of 5
            for i in range(0, len(urls), 5):
                batch = urls[i:i+5]
                print(f"\nProcessing batch {i//5 + 1} with {len(batch)} URLs")
                
                # Create a new page for each batch
                page = await browser.new_page()
                
                for j, url in enumerate(batch):
                    print(f"  Processing URL {j+1}/{len(batch)}: {url}")
                    content = await extract_article_content(page, url)
                    
                    if content:
                        print(f"    Successfully extracted {len(content)} characters")
                    else:
                        print("    Failed to extract content")
                        
                    # Add a small delay between individual URL processing
                    await page.wait_for_timeout(1000)
                
                # Close the page after each batch
                await page.close()
                
                # Wait 30 seconds between batches
                if i + 5 < len(urls):
                    print("Waiting 30 seconds before next batch...")
                    await asyncio.sleep(30)
                    
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(test_sequential_extraction())