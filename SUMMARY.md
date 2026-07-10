# project: Daily_Brief_v01
# description: Auto-generate daily news brief for Obsidian
# created: 2026-07-07

## CHANGE LOG — BETA09 (2026-07-10)

### CRITICAL FIX: Per-category batching prevents context overflow
**Problem:** `batch_summarize_all()` sent ~92K characters to Ollama (46 stories x ~2000 chars each), but `num_ctx` is capped at 8192. Qwen returned empty output → 46/46 [Summary unavailable].
**Fix:** One batch call per category. Most categories have 1-9 stories, fitting well within limits.

### PERF: Model swap — qwen3.6-256k-agents (36B) → gemma4:e2b (5.1B)
| Metric | Qwen 256K | Gemma4:e2b | Improvement |
|---|---|---|---|
| Per-call time | ~45s avg | ~4-10s avg | **~8x faster** |
| Total pipeline | ~724s (12 min) | ~130s (2 min) | **~82% faster** |
| Summary quality | Excellent, detailed | Good-enough, 1-3 sentences | Slight tradeoff |

Confirmed via live run: 36 stories summarized, 0 failed, output file rendered clean markdown.

### ARCHITECTURE: Removed Playwright article extraction
Playwright crashed with `Execution context was destroyed` on concurrent Google News redirect navigation (36 pages × ~3s each). Redirect from Google tracking URL to real publisher is too fast for async aiohttp + JS extraction combined.

**Fix:** Skip Playwright. Pipeline uses title + snippet text directly — Google News RSS descriptions strip down to 50-95 chars of clean prose, sufficient for Gemma to produce useful summaries. (Verified: pipeline produces readable summaries without full article text.)

### NAMED: LLM config standardized
`_qwen_client` → `_llm_client` | `QWEN_MODEL` → `LLM_MODEL` = "gemma4:e2b"

### CLEANUP: Removed dead external RSS feeds
Guardian World, Guardian Technology, TechCrunch — added by failed Build agent refactor, all returned 0 stories. Removed from CATEGORIES. Only original Google News queries remain.

---
# v0.1.0 (2026-07-07) — First pipeline: feeds fetch + render works; Ollama unavailable locally
# v0.2.0 (2026-07-08 01:55) — Cross-category dedup; Ollama client timeout=60s for remote host
# v0.2.2 (2026-07-08 02:58) — Rewritten with thread pool executor + proper logging
# v0.2.3 (2026-07-08 10:30) — Thread pool workers 3→8; performance timing added
# v0.2.4 (2026-07-08 12:30) — Doc updates, temp file cleanup, Obsidian path verification
# v0.2.5 (2026-07-08 16:00) — Logs to vault/, batch fan-out (3A/3B/3C parallel), alert fix, hyperlinks + pub dates
# v0.2.5-BETA01 (2026-07-08 20:39) — workers=3, timeout=180s, retry loops; retries caused cascade timeouts
# v0.2.5-BETA02 (2026-07-08 20:39) — strip_html() on snippets, context-min 300 chars, 24h age filter, normalize_title(), dedup
