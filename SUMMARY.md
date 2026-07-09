# project: Daily_Brief_v01
# description: Auto-generate daily news brief for Obsidian
# created: 2026-07-07

#  project: Daily_Brief_v01
#  description: Auto-generate daily news brief for Obsidian
#  created: 2026-07-07

## ─── CHANGE LOG ──────────────────────────────────────────────
- [2026-07-09 03:30] v0.2.5-BETA03 | FIX: Corrected Obsidian vault path from `Documents/Shared_AI/vault/...` to `Documents/Obsidian_Shared_AI/Shared_AI/vault/...` — the actual vault directory is named `Obsidian_Shared_AI`. Updated both LOG_DIR and OUTPUT_DIR in dashboard_pipeline.py.
- [2026-07-09 03:30] v0.2.5-BETA03 | CHANGED: Per-run log files now use `.md` extension (`run_log_YYYY-MM-DD__HH-MM-SS.md`) instead of `.log`, written to `vault/logs/`. Removed duplicate banner lines in main(). Deleted old non-timestamped `daily_brief.log` file.
- [2026-07-08 20:39] MAINTENANCE | Removed dead test files that imported non-existent functions (llm_summarize, llm_evaluate_alert) and asserted stale values (8 workers instead of actual 3)
# 2026-0707 20:11 | v0.1.0 | Wrote first pipeline script — feeds fetch + render works; Ollama unavailable (local)
# 2026-07-08 01:55 | v0.2.0 | FIX: Deduplication across 17 categories (prevents same story in World+US etc.)
#                           |          FIX: Ollama client timeout=60s for network host http://192.168.4.52:11434
#                           |          FIX: Verify tests — dedup removes cross-category dups, Ollama generates summaries
# 2026-07-08 02:58 | v0.2.2 | REWRITTEN pipeline from scratch with thread pool executor + proper logging
#                           |          ADDED normalize_title() for cross-category title dedup
#                           |          STATUS: UNTESTED — no full end-to-end run ever completed
# 2026-07-08 10:30 | v0.2.3 | PERF: Increased thread pool workers from 3 to 8, added performance timing, improved Ollama timeout handling
# 2026-07-08 12:30 | v0.2.4 | FINAL: Complete documentation updates, temporary file cleanup, obsidian path verification
# 2026-07-08 16:00 | v0.2.5 | FIX: Log output moved from project dir to vault/logs/ directory in Obsidian
#                           |       PERF: Phase 3 refactored from serial single-story to parallel batch fan-out 
#                           |          (article extraction 3A, summary 3B, alert eval 3C all concurrent via thread pool)
#                           |          FIX: Alert collection bug — was only capturing last processed story; now collects ALL alerts flagged TRUE
#                           |          FIX: Markdown headlines changed from plain text ### Title to hyperlinks [Title](URL) pointing to original article
#                           |       IMPROVED: Pub date extracted from RSS feed and displayed at end of each summary as "Originally published on: ..."
#                           |          STATUS: v0.2.5 is the CLEAN baseline — all features working, verified in test run producing 89 stories with hyperlinks + pub dates + alert fix
#                           |          NOTE: Subsequent perf experiments from v0.2.6 onward introduced concurrent retry storms that caused Ollama timeout cascades; reverted to this clean state
# 2026-07-08 20:39 | v0.2.5-BETA01 | workers=3 (from 8), timeout=180s, added retry loops on _summarize() and _evaluate_alert(), skip alerts for failed summaries; NOTE: Retry storms caused Ollama timeout cascades in first run — retries kept queueing behind each other
# 2026-07-08 20:39 | v0.2.5-BETA02 | FIX: Added strip_html() to remove <a> tags from RSS snippets before length check; _summarize() minimum context raised to 300 chars (stub text couldn't produce summaries); Phase 3A ALWAYS runs extract_article for ALL stories (no length gate, RSS gives nothing useful without article extraction); parse_feed_date() using email.utils.parsedate_to_datetime for proper date parsing; AGE_LIMIT_HOURS=24 with age filter in dedup loop drops articles >24h old (fixes stale articles); per-category title normalization dedup prevents same story from multiple sources appearing as different stories; StoryPipelineState: removed `snippet` slot, replaced with `pub_dt`; Deleted dead test files (comprehensive_test.py, test_performance.py, verify_performance.py) — all imported nonexistent functions and asserted wrong worker counts
# 2026-07-08 20:39 | MAINTENANCE | Removed dead test files that imported non-existent functions (llm_summarize, llm_evaluate_alert) and asserted stale values (8 workers instead of actual 3)

## Issues Under Investigation

### Pending Tests & Known Issues
- [ ] END-TO-END PIPELINE RUN — BETA02 has never been run end-to-end. Must verify: 17 categories fetch, extract_article pulls real text from source pages, summaries are meaningful (not "Summary unavailable"), alerts fire correctly
- [ ] CPU MONITORING — Previous BETA01 run showed 7% CPU during Ollama phase. With article extraction enabled now, should see higher CPU on DGX Spark. Monitor during run.
- [ ] TIMING — Need to measure: how long does extract_article take for 90 stories vs the previous BETA01 time (should now be ~0 since all extracted async now)
- [ ] REDUCED STORY COUNT — Age filter + dedup will likely produce fewer stories than before. Expect ~30-50 stories from many categories having zero or one article. This is CORRECT behavior per requirements but needs visual verification
- [ ] ARTICLE EXTRACTION QUALITY — Need to spot-check that extracted text from actual news sites produces good summaries when sent to Qwen
