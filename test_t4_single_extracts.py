#!/usr/bin/env python3
"""Test Playwright article extraction from Google News tracking URLs.
Sequential batches of 5 with 30s gap between each batch to prevent
'Execution context was destroyed' crash seen in concurrent mode."""
import asyncio, aiohttp, feedparser, time
from bs4 import BeautifulSoup

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("ERROR: playwright not installed. Run: pip3 install playwright")
    exit(1)


async def extract_batch(tracking_urls):
    """Extract articles from one batch of tracking URLs sequentially."""
    print(f"\n{'='*80}")
    print(f"Processing batch of {len(tracking_urls)} links...")
    print(f"{'='*80}")
    
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True)
    
    results = []
    
    for idx, item in enumerate(tracking_urls):
        try:
            t_start = time.time()
            page = await browser.new_page(user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
            
            response = await page.goto(item, wait_until='networkidle', timeout=45000)
            elapsed_nav = time.time() - t_start
            
            if not response or response.status >= 400:
                results.append({
                    'url': item[:100],
                    'status': response.status if response else 'none',
                    'error': 'http_failure',
                    'time': elapsed_nav
                })
                continue

            await asyncio.sleep(2)
            
            final_url = str(page.url())
            url_domain = final_url.split('/')[2] if len(final_url.split('/')) > 2 else 'unknown'

            texts = await page.evaluate('''() => {
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
                    acceptNode: (node) => {
                        if (['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(node.parentElement?.tagName)) return NodeFilter.FILTER_REJECT;
                        const ptag = node.parentElement?.tagName || '';
                        if (['NAV', 'HEADER', 'ASIDE', 'FOOTER'].includes(ptag)) return NodeFilter.FILTER_REJECT;
                        const cls = String(node.parentElement?.className || '');
                        if (['cookie', 'banner', 'ad', 'modal', 'footer'].some(c => cls.toLowerCase().includes(c))) 
                            return NodeFilter.FILTER_REJECT;
                        return node.textContent.trim().length > 40 ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
                    }
                });
                const texts = [];
                let node;
                while (node = walker.nextNode()) texts.push(node.textContent.trim());
                return texts.filter(t => t.length > 40).slice(0, 30);
            }''')

            elapsed_total = time.time() - t_start
            
            if texts and len(texts) > 0:
                text = '\n'.join([t.strip() for t in texts])
                results.append({
                    'url': f"{item[:80]}...",
                    'final_domain': url_domain,
                    'paragraph_count': len(texts),
                    'chars_extracted': len(text),
                    'nav_time_sec': round(elapsed_nav, 1),
                    'total_time_sec': round(elapsed_total, 1),
                    'preview': text[:200] + '...' if len(text) > 200 else text
                })
            else:
                results.append({
                    'url': f"{item[:80]}...",
                    'final_domain': url_domain,
                    'chars_extracted': 0,
                    'nav_time_sec': round(elapsed_nav, 1),
                    'total_time_sec': round(elapsed_total, 1),
                    'error': 'no_pars'
                })

            await page.close()
            
        except Exception as e:
            results.append({'url': f"{item[:80]}...", 'error': str(e)})

    await browser.close()
    return results


def print_results(result_batch):
    """Pretty print extraction results for one batch."""
    success = []
    fail_count = 0
    
    for r in result_batch:
        chars = r.get('chars_extracted')
        if isinstance(chars, int) and chars > 0:
            pg_count = r.get('paragraph_count', 0)
            time_taken = r.get('total_time_sec', 'N/A')
            domain = r.get('final_domain', '?')
            success.append(r)
            print(f"  SUCCESS {chars:>5} chars, {pg_count:2d} pgs, {time_taken}s -> {domain}")
        else:
            fail_count += 1
            error_info = ""
            if 'status' in r:
                error_info = f"HTTP {r['status']}"
            elif 'error' in r and r['error'] == 'http_failure':
                error_info = "http failure"
            else:
                error_info = str(r.get('error', 'unknown'))
            print(f"  FAIL: {error_info}")
    
    total_len = len(result_batch)
    suc_count = len(success)
    print(f"\nResults ({suc_count}/{total_len} success)")


async def fetch_sample_links():
    """Grab sample tracking IDs from Google News RSS feeds."""
    async with aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}) as s:
        feeds = [
            ('World News',      'https://news.google.com/rss/search?q=world+news&hl=en-US&gl=US&ceid=US:en'),
            ('US News',         'https://news.google.com/rss/search?q=US+news&hl=en-US&gl=US&ceid=US:en'),
            ('Big Tech',        'https://news.google.com/rss/search?q=big+tech&hl=en-US&gl=US&ceid=US:en'),
        ]
        
        all_links = []
        for name, url in feeds:
            try:
                async with s.get(url, timeout=15) as resp:
                    feed = feedparser.parse(await resp.text())
                
                count = 0
                for entry in feed.entries[:6]:
                    link = entry.get('link', '')
                    if 'news.google.com/rss/articles/' in link:
                        mid = link.split('/articles/')[-1].split('?')[0]
                        full_url = f"https://news.google.com/rss/articles/{mid}"
                        all_links.append((name, entry.get('title','')[:70], full_url))
                        count += 1
                
                print(f"  Fetched {count} tracking links from {name}")
                
            except Exception as e:
                print(f"  Error fetching {name}: {e}")
        
        return all_links


async def main():
    print("=" * 80)
    print("TESTING PLAYWRIGHT ARTICLE EXTRACTION — Sequential batches (5 at a time)")
    print("With a 30s gap between each batch to let redirects/JS finish cleanly.")
    print("=" * 80)
    
    # Fetch sample tracking URLs
    links_and_titles = await fetch_sample_links()
    
    if not links_and_titles:
        print("\nNo tracking URLs found. Exiting.")
        return
    
    test_urls = [url for _, _, url in links_and_titles[:15]]  # First 15 tests
    
    total_start = time.time()
    all_results = []
    
    BATCH_SIZE = 5
    GAP_SECONDS = 30
    
    for i in range(0, len(test_urls), BATCH_SIZE):
        batch = test_urls[i:i + BATCH_SIZE]
        
        if i > 0 and i + BATCH_SIZE <= len(test_urls):
            print(f"\nWaiting {GAP_SECONDS}s before next batch...")
            await asyncio.sleep(GAP_SECONDS)
        
        batch_results = await extract_batch(batch)
        all_results.extend(batch_results)
    
    total_time = time.time() - total_start
    
    # Summary output
    success_all = [r for r in all_results if isinstance(r.get('chars_extracted'), int) and r['chars_extracted'] > 0]
    fail_all = len(all_results) - len(success_all)
    all_success_rate = len(success_all) / max(len(all_results), 1) * 100
    
    print(f"\n{'='*80}")
    print("FINAL SUMMARY")
    print(f"{'='*80}")
    print(f"Total URLs tested: {len(all_results)}")
    print(f"Successful extractions: {len(success_all)} ({all_success_rate:.0f}%)")
    print(f"Failures: {fail_all}")
    
    if success_all:
        avg_chars = sum(r.get('chars_extracted', 0) for r in success_all) / len(success_all)
        avg_pgs = sum(r.get('paragraph_count', 0) for r in success_all) / len(success_all)
        avg_time = sum(r.get('total_time_sec', 0) for r in success_all) / len(success_all)
        print(f"\nAvg chars extracted: {avg_chars:.0f}")
        print(f"Avg paragraphs per article: {avg_pgs:.1f}")
        print(f"Avg time per extraction: {avg_time:.2f}s")
    print(f"Total test time: {total_time:.1f}s")


asyncio.run(main())

