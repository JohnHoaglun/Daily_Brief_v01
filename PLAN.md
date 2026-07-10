# Plan: Daily_Brief_v01

## BLOCKER (Resolved)
- [2026-07-09] **Wrong Obsidian vault path** — LOG_DIR and OUTPUT_DIR pointed to `Documents/Shared_AI/vault/...` instead of `Documents/Obsidian_Shared_AI/Shared_AI/vault/...`. The actual vault directory is named `Obsidian_Shared_AI`, not `Shared_AI`. This caused logs to be written to the wrong location (or fail silently). **RESOLVED**: Updated both LOG_DIR and OUTPUT_DIR to correct path in dashboard_pipeline.py.

## BLOCKER (New — 2026-07-09)
- **[Critical] All article extraction returns 0 chars** — Google News RSS now provides internal article IDs (`news.google.com/rss/articles/CBMin...`) instead of real URLs (cnn.com, reuters.com, etc.). `extract_article()` fetches these and returns empty text. Pipeline falls back to title-only context (~40-60 chars), which causes `_summarize()` to hang or produce no summary. **ALL 40 summaries in latest run returned "Summary unavailable"**. Root cause: Google News changed their feed format. Pivot: use RSS `<summary>`/`<description>` (after `strip_html()`) as primary summary context — it's the best available content without needing real URL access.
- **[Minor] Conroe TX query returns property listings** — The query `"news+Conroe+TX"` still surfaces Realtor.com listings. Need to exclude keywords like "Realtor", "Listings", "Sale", "For Sale".

## Strategy
### Fix 1: Use RSS snippets as summary context (primary fix)
- After `strip_html()`, the snippet often has 200-600 chars of useful text — more than enough for `_summarize()` with min_chars=300. Fall back to title+category for very short snippets.
- Store cleaned snippet in `story.snippet` (already done) and use it in `stage_summarize` as primary context source, not just a last resort.

### Fix 2: Improve fallback summary quality when extraction + snippet both fail
- When both extract_article fails AND snippet is too short, still attempt summary with enriched title context including category signal. Reduce min_chars to 50 for fallback-only cases.
- Add "Best effort" prefix in system prompt for minimal context so Qwen doesn't say "Summary unavailable".

### Fix 3: Narrow Conroe TX and Montgomery County queries
- Add negative keywords to filter out real estate/property listings from local news results.

### Fix 4: Update version string to BETA07 — document the fixes
- Bump pipeline version comment at top of file to BETA07.

---
- All paths must use the Obsidian vault at `/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/`
- Per-run unique `.md` log files are now created at `vault/logs/run_log_YYYY-MM-DD__HH-MM-SS.md`
- BETA02 pipeline is ready for end-to-end test run (article extraction, summarization with proper context lengths)
