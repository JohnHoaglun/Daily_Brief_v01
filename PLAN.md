# Plan: Daily_Brief_v01

## CURRENT STATUS — BETA12 Base Line

Working baseline: commit `02ab117` (verified 61 stories, 0 failed, ~162s)

---

## OPEN ISSUES — See SUMMARY.md for live TODO list
1. Remove HIGH-PRIORITY BULLETINS section, keep alert stories in their regular category sections
2. Playwright article extraction fails (headless blocked by publisher sites)
3. Conroe TX News = 0 stories (Google has no fresh content for this query)
4. Summary length ~2 sentences, need 3+
5. "Last available" date for empty categories

---

## BLOCKERS (Resolved)
- [2026-07-09] **Wrong Obsidian vault path** — LOG_DIR/OUTPUT_DIR pointed to wrong directory. Fixed by moving everything under `Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/`. See commit 562fe28 (BETA09).

## RESOLVED FIXES (Documented in SUMMARY.md)
### BETA09: Context overflow fix + model swap + batch-per-category
- **Problem:** Single-batch call sent ~92K chars → Ollama returned empty output.
- **Fix:** One batch call per category. Switched from qwen3.6-256k-agents to gemma4:e2b (~8x faster, ~130s total).
- Removed Playwright extraction (concurrent navigation crashed the browser).
- Removed dead external feeds (Guardian World/Technology, TechCrunch all returned 0 stories).

### BETA10: Per-category age window for local feeds  
- **Problem:** Conroe/Montgomery/Tropical categories always returned 0 stories — blanket 24h limit dropped their content when Google served articles >24h old.
- **Fix:** `CATEGORY_AGE_LIMITS` dict gives those 3 feeds 48h instead of 24h default.

### BETA11: RSS entries sorted by pub_date before taking top N  
- **Problem:** Google News RSS returns oldest articles at the TOP of each feed list. Pipeline grabbed `feed.entries[:max_stories]` which meant stale content, not newest. Local feeds had fresh articles buried deep in 100+ entry list.
- **Fix:** All entries sorted by pub_date descending (`_sort_entries()` with `cmp_to_key()`), THEN take top N. Also fixed: Conroe/Montgomery/Tropical age limits use 48h via `CATEGORY_AGE_LIMITS` dict.
- Montgomery County TX now surfaces content (e.g., "4 events this weekend in Conroe, Montgomery").
