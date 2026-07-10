# Notes & Lessons Learned — Daily_Brief_v01

## Session: 2026-07-09

---

## Lessons Learned

### 1. Google News RSS Feed Change (Root Cause)
**WHAT:** Google News RSS feeds no longer provide real publisher URLs in the `<link>` field. All links are internal article IDs: `news.google.com/rss/articles/CBMin...`. Attempting to fetch these returns empty HTML.
**WHY IT MATTERS:** The pipeline's "article extraction" phase (fetching full article text from source URLs) has been dead since BETA01 — it always returned 0 extracted articles. This was never caught because the fallback mechanism silently covered for it with "[Summary unavailable]".
**LESSON:** Test your data assumptions against real feed output before building features on top of it. RSS feeds change; verify format periodically.

### 2. Ollama Server is Single-Threaded (Critical Bottleneck)
**WHAT:** The DGX Spark server at `192.168.4.52:11434` processes requests sequentially regardless of client-side parallelism. All four testing approaches produced ~1.0x speedup:
- Python ollama client (sequential): 84s for 4 calls
- Python ollama client (parallel, ThreadExecutor): 82s — SAME as sequential  
- curl subprocess (sequential): 83s
- curl subprocess (parallel asyncio.gather): 82s — SAME as sequential

**WHY IT MATTERS:** All parallelism work in BETA06+ was wasted. The server itself is the bottleneck, not the client. Each ~20s response means 43 stories × 20s = **14 minutes minimum** for summaries alone through individual calls.
**LESSON:** Profile server-side concurrency before investing in client-side parallel architecture.

### 3. Batch Single-Call Is the Only Way to Speed Up Throughput
**WHAT:** One batch call with all 39 stories completed in ~114s vs ~860s for individual calls (~7.5x reduction). This is NOT speedup from parallelism — it's because Ollama processes one logical request, then generates multiple outputs sequentially.
**WHY IT MATTERS:** Batch single-call architecture reduces N×20s to just 1×(~20s + processing overhead). But parsing the structured output becomes critical.
**LESSON:** When server-side is sequential, batch processing into a single call is the primary optimization strategy. Parsing robustness matters more than anything else in this pattern.

### 4. Qwen Model Response Format Is Unpredictable
**WHAT:** We don't yet know what format Qwen returns for batch prompts. Our parser expected `STORY_0: summary text` but all 39 responses failed to parse. Possible issues:
- Qwen might add a thinking/reasoning preamble before the actual formatted response
- Qwen might use bullet points, numbered lists, or plain paragraphs instead of our requested `STORY_N:` format  
- The system prompt may not be strong enough to enforce strict formatting
**WHY IT MATTERS:** An unparseable batch response means every story defaults to "[Summary unavailable]" — worse than nothing.
**LESSON:** Always capture and log the raw model output during development to understand actual response formats. Never assume format matches intent in system prompts.

### 5. Model Choice Has Tradeoffs
**WHAT:** `qwen3.6-256k-agents:latest` includes extensive thinking/training reasoning blocks (the "agents" and "256k" variants tend to do this). It takes ~20s per call, but most of that time is reasoning before output starts.
**WHY IT MATTERS:** This model has strong reasoning capability but slow response times due to internal deliberation. For simple summarization tasks, it's overkill and adds latency.
**LESSON:** Consider using a smaller/faster model for batch summarization where deep reasoning isn't needed. Save the large model for complex analysis tasks only.

### 6. Incremental Edits on Complex Refactors Break Things
**WHAT:** Multiple rounds of partial edits to `dashboard_pipeline.py` left behind dead code, mismatched references (`_batch_context` vs `snippets`, typo `"STOPY_N:"`), and UnboundLocalErrors. Each round fixed one issue but introduced another.
**WHY IT MATTERS:** After 5+ edit rounds, the file was in progressively worse shape with cascading bugs from forgotten old references.
**LESSON:** For major refactors, either: (a) delegate to a build agent that does it all at once, or (b) write the entire new version rather than patching incrementally. Incremental edits on complex multi-function files are unreliable for large changes.

### 7. Google News RSS Snippets Are Short
**WHAT:** Diagnostic confirmed RSS snippets average ~95 chars (range ~70-140). This is too short for deep summaries but sufficient for a factual 2-sentence summary if the prompt is concise ("What happened?").
**WHY IT MATTERS:** The pipeline was designed around article extraction as primary context. Without it, everything relies on title + ~95 char snippet — tight but workable with strong system prompts.

---

## Technical Decisions Made

1. **Batch single-call over individual calls:** Confirmed ~7.5x improvement at scale. Must make parsing robust.
2. **Skip article extraction entirely:** No viable path to real URLs from Google News RSS. Title + snippet is the only context available.
3. **Accept sequential server bottleneck at ~20s/batch:** For 43 stories = ~1-2 min total for both sum + alerts (vs previous ~30+ min attempts that timed out).

---

## Pending / Not Yet Executed TODOs

### Categorized by Priority

#### HIGH PRIORITY (Blocking Pipeline Operation)
- [ ] **Fix batch response parsing** — determine exact Qwen output format and make parser robust. This is the primary blocker. Debug script `debug_batch.py` needs fixing, then run to see actual output. After seeing output, update `parse_batch_response()` and `parse_alert_batch_response()`.
- [ ] **Clean up pipeline file** — several edit rounds left dead code, unused functions (`stage_extract_article`, `stage_summarize`), and potential unreachable blocks. Clean refactor needed.
- [ ] **Run full end-to-end validation** — execute the pipeline with real data and verify: meaningful summaries (not "[Summary unavailable]"), correct alert batching, clean markdown output, proper file naming.

#### MEDIUM PRIORITY (Quality Improvements)
- [ ] **Consider smaller/faster model** for batch summarization — `qwen3.6-256k-agents` adds overhead with reasoning blocks. A smaller model might complete same batch faster while still producing adequate summaries.
- [ ] **Conroe TX real estate filtering improvement** — current regex filter (`is_realt_estate_title`) catches "Realtor", "$", but may be too aggressive or too broad. Need to test results from actual Q1 run.
- [ ] **Alert batch accuracy validation** — confirm that single-batch alert evaluation produces same quality as per-story evaluation when it worked correctly (never properly tested in any version).

#### LOW PRIORITY (Future Improvements)
- [ ] **Explore alternative Google News data source** — if real article URLs are needed, investigate: (a) alternative RSS feed aggregator services, (b) Google News custom feeds with full URLs, (c) direct publisher APIs.
- [ ] **Per-story "best effort" summaries as fallback** — if batch parsing fails for some indices but succeeds for others, fill gaps with headline-only summaries rather than all-failing.
- [ ] **Pipeline timing benchmark** — once fixed, measure: Phase 1 (weather), Phase 2 (RSS fetch + dedup), Phase 3AB (batch summary), Phase 3C (batch alerts), Phase 4 (render). Target: <5 min total runtime.
- [ ] **Test on multiple days** — verify the pipeline handles varying story counts (some days ~10, some ~90) without format overflow or parsing breakdown.

#### OPERATIONAL NOTES
- [ ] **Clean up temp/debug test files** — `debug_batch.py`, `diag_batch.py` in project directory after their purpose is served.
- [ ] **Update PROJECT.md** with BETA08 findings, performance measurements, and current status.
- [ ] **Update SUMMARY.md** with this session's changelog entry.

---

## Files Created/Modified This Session

| File | Action | Notes |
|------|--------|-------|
| `dashboard_pipeline.py` | Modified (BETA08) | Added batch_summarize_all(), batch_evaluate_alerts(), parse_batch_response(), parse_alert_batch_response(). Multiple incremental edits left some dead code. |
| `PLAN.md` | Modified | Added new BLOCKER about Google News article extraction failure |
| `debug_batch.py` | Created | Intended: debug batch parsing with real Qwen output. Has UnboundLocalError bug (variable i before assignment). |
| `diag_batch.py` | Created | Quick diagnostic test for curl-based batch response format. Not yet run successfully. |
| `test_ollama_strategies.py` | Created | Benchmarked 4 Ollama calling strategies — proved server is single-threaded. |
| `test_real.py` | Created | Failed to compile (await outside function syntax error). Superseded by diag_batch.py. |
| `ollama_perf_simple.sh` | Deleted | Moved out of projects root. Was stray temp file. |
| `ollama_final_test.py` | Deleted | Stray temp file from prior session. Removed. |
| `ollama_test.py` | Deleted | Stray temp file. Removed. |
| `simple_test.py` | Deleted | Stray temp file. Removed. |
| `projects/ollama_diagnostics.sh` | Deleted earlier | Was outside project directory, cleaned up at session start. |
