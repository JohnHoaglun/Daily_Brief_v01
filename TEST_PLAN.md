# Test Plan: Daily Brief — Article Extraction + Data Sources Recovery

## Goal
Restore high-quality summaries by ensuring the pipeline has rich article context (real article content, not just titles + snippets). Test two approaches in parallel: adding stable external RSS sources (A) and hybrid article extraction with current sources (C).

---

## PREREQUISITE — Verify Link Validity (Tests 1-2)

**T1: Sample Google News link analysis**
- Fetch 45+ feed entries from all active categories in `dashboard_pipeline.py`
- Extract every `<link>` value and classify as "real URL" or "Google tracking ID"
- Parse each URL to check domain (google.com vs publisher domain)
- Also extract `<guid>` — Google sometimes puts real URLs there even when `<link>` is a tracking ID

**T2: Quick async fetch test on 20 randomly-selected real-looking links**
- From entries where link looks like `cnn.com`, `reuters.com`, etc., try async fetch with 5s timeout
- Measure what % return >=200 chars of article text (content from `<p>`/`<h1>` tags)
- This establishes a real-world baseline: are any links actually usable?

---

## APPROACH A — External RSS Sources

**T3: Fetch test for each candidate external RSS feed**
- Fetch feeds one at a time with timeout. Verify:
  - Feed parses in `feedparser` (no XML errors)
  - Entries have non-empty titles and snippets
  - At least 3/4 entries have real publisher URLs (not tracking IDs)
  - Entry age distribution is reasonable (<48h old)
- Test feeds to evaluate:
  - Reuters Top News → `https://www.reutersagency.com/feed/?best=top-news&taxonomy=na`
  - Reuters Technology → `https://www.reutersagency.com/feed/..." 
  - AP News (via RSSHub or direct if available)
  - MarketWatch World News → `feeds.a.dj.com/rss/RSSWorldNews.xml`

**T4: Integration test — add 2-3 working external feeds to pipeline**
- Add successful feeds to CATEGORIES list in `dashboard_pipeline.py`
- Run full pipeline with external feeds only (no Google News) for one iteration
- Measure: total stories, % with article text fetched, avg summary length
- Verify output renders correctly in Obsidian vault

---

## APPROACH C — Hybrid Article Extraction (works with ANY feed)

**T5: Implement async fetch of all real-looking links from RSS entries**
- Add logic before batch summarization: scan all story titles for article URLs (skip google.com/googlevideo.com links)
- Async `extract_article()` on each valid URL using aiohttp with 5s timeout
- Measure: what % of links resolve to >=200 chars, avg fetch time

**T6: Build context from fetched articles + snippet fallback**
- Update `build_context()`: if story.context (fetched article text) exists and is >=50 chars, use it; otherwise fall back to title+snippet
- This should transparently benefit both external feeds AND old Google News entries that happen to have real URLs

---

## APPROACH B — Batch Prompt Enhancement

**T7: Test improved batch prompt variants**
After T1 results inform what context is available, test which approach produces better summaries given the same input data:
- Variant 1 (entity extraction): "Extract from this title/snippet: key actors, location, event type, date/time"
- Variant 2 (knowledge-augmented): "Based on this title and your knowledge of recent events..."  
- Variant 3 (structured JSON output): ask for `{event_type, key_facts, who_involved}` then format as prose

---

## ACCEPTANCE CRITERIA

1. Pipeline must produce at least **50% of summaries with >=2 sentences** of actual article content (not "[Summary unavailable]")
2. External feeds (Approach A) must have real publisher URLs in >60% of entries
3. All async fetches must use bounded timeouts (no hangs on slow/dead links)
4. Full pipeline run must complete within 600s (10 minutes wall clock)
5. Output markdown must render cleanly in Obsidian

---

## TEST ORDER (dependencies)

```
T1 → T2                (verify link validity, sets baseline)
    ↓
T3                     (evaluate external source feeds)
    ↓                    (if T3 finds ≥2 working feeds)
T4 + T5 + T6           (integrate + hybrid extraction in parallel)
    ↓                    (both approaches benefit from same extraction logic)
T7                     (prompt engineering — only if article text is insufficient)
```
