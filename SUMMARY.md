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
# 2026-07-08 16:00 | v0.2.5 | FIX: Log output moved from project dir to vault/logs/ directory in Obsidian
#                           |       PERF: Phase 3 refactored from serial single-story to parallel batch fan-out 
#                           |          (article extraction 3A, summary 3B, alert eval 3C all concurrent via thread pool)
#                           |          FIX: Alert collection bug — was only capturing last processed story; now collects ALL alerts flagged TRUE
#                           |          FIX: Markdown headlines changed from plain text ### Title to hyperlinks [Title](URL) pointing to original article
#                           |       IMPROVED: Pub date extracted from RSS feed and displayed at end of each summary as "Originally published on: ..."
#                           |          STATUS: v0.2.5 is the CLEAN baseline — all features working, verified in test run producing 89 stories with hyperlinks + pub dates + alert fix
#                           |          NOTE: Subsequent perf experiments from v0.2.6 onward introduced concurrent retry storms that caused Ollama timeout cascades; reverted to this clean state


