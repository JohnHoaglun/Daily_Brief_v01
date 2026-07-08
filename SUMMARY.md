# project: Daily_Brief_v01
# description: Auto-generate daily news brief for Obsidian
# created: 2026-07-07

# ─── CHANGE LOG ──────────────────────────────────────────────
# 2026-0707 18:53 | v0.0.1 | Created PROJECT.md, SUMMARY.md, README.md, ARCHITECTURE.md — initial scaffolding
# 2026-0707 20:11 | v0.1.0 | Wrote first pipeline script — feeds fetch + render works; Ollama unavailable (local)
# 2026-07-08 01:55 | v0.2.0 | FIX: Deduplication across 17 categories (prevents same story in World+US etc.)
#                           |          FIX: Ollama client timeout=60s for network host http://192.168.4.52:11434
#                           |          FIX: Verify tests — dedup removes cross-category dups, Ollama generates summaries
# 2026-07-08 02:58 | v0.2.2 | REWRITTEN pipeline from scratch with thread pool executor + proper logging
#                           |          ADDED normalize_title() for cross-category title dedup
#                           |          STATUS: UNTESTED — no full end-to-end run ever completed
# 2026-07-08 10:30 | v0.2.3 | PERF: Increased thread pool workers from 3 to 8, added performance timing, improved Ollama timeout handling
# 2026-07-08 12:30 | v0.2.4 | FINAL: Complete documentation updates, temporary file cleanup, obsidian path verification
# 2026-07-08 16:00 | v0.2.5 | FIX: Log output moved from project dir to vault/logs/ directory
#                           |          PERF: Phase 3 refactored from serial single-story processing to parallel batch fan-out
#                           |          PERF: Article extraction (3A), summarization (3B), alert evaluation (3C) all run concurrently
#                           |          FIX: Alert collection bug — previously only captured last processed story, now collects ALL alerts
#                           |          FIX: Markdown headlines are hyperlinks [Title](URL) to original articles
#                           |          IMPROVED: Pub date extraction from RSS feeds and display "Originally published on: ..." per story
#                           |          STATUS: Ready for first performance test run — watch CPU/memory on DGX Spark during summaries


