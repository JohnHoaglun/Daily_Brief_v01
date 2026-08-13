# TODO: Daily Brief v01 — v1.0.145

## Code Review Findings (2026-08-12)

Full review performed: structural issues, files exceeding 500/300 lines, performance optimizations, cross-cutting duplication. Plan only — no implementation.

### P0 — File size cap (hard policy)

**Python source files must not exceed 500 lines of code.** Anything above this degrades tool call performance for edits/reviews, increases cognitive load, and makes test authoring harder. This is a firm cap, not a soft recommendation.

- [x] **Enforce 500-line cap on every Python file** — Any file edited, created, or refactored must stay under 500 lines. If a file is approaching the cap, it is a signal to split *before* reaching it.

**Current state:** 2 files split under 500-line cap (P0 summarizer + config_validator). Remaining large files to audit.

- [ ] **Audit high-overhead test modules** — 9 test files exceed 400 lines:
  - `test_rendering_safety_contract.py` (884 lines)
  - `test_concurrency_contract.py` (744 lines)
  - `test_summarizer.py` (741 lines)
  - `test_weather_climate_contract.py` (711 lines)
  - `test_sources/test_weather.py` (600 lines)
  - `test_tagging.py` (469 lines)
  - `test_connectivity_extended.py` (467 lines)
  - `test_report.py` (455 lines)
  - `test_http_client.py` (454 lines)
- [ ] **Identify tests that validate what the production validator already does** — `validation.py` checks for "Dynamic"/"Unavailable"/summary quality. Test classes likely mirror these same checks. Reduce test duplication: test the validator's inputs/outputs once; don't test the validator's implementation details in every test module.
- [ ] **Consolidate test fixtures** (`tests/fixtures/parser_golden_fixtures.py`, 322 lines) — These are loaded by tests for golden-match parsing. Verify they don't also test behavior (fixtures should be data + minimal helpers, not assertions).

### P0 — Files > 500 lines (High complexity, high reward)

- [x] **Split `llm/summarizer.py` (1,014 lines)** into four modules:
  - [x] `llm/summary_parser.py` (452) — Extract `parse_batch_summary_response()` and all matching strategies.
  - [x] `llm/summary_quality.py` (189) — Extract refusal/boilerplate/topic checks, auto-fallback.
  - [x] `llm/summary_service.py` (200) — Single-story and sub-batch LLM call transport.
  - [x] `llm/summary_coordinator.py` (226) — `batch_summarize_all()` orchestration.
  - [x] `llm/summarizer.py` (67) — Thin compatibility facade re-exporting all public/test-facing APIs.
  - [x] **Test fix:** Added missing imports to coordinator (`_summarize`, `_is_valid_summary`, `_generate_auto_fallback`, `build_context`); fixed empty-backoff `IndexError` in retry path.
- [x] **Deduplicate parser logic** — Extracted `_keyword_set()` and `_best_headline_keyword_match()` helpers in `summary_parser.py`. Replaced all repeated `re.findall(r"\b[a-z]{3,}\b"`/`r"\b[a-z]{4,}\b"` tokenization (7 contexts, ~17 occurrences). Strategies retain distinct `min_length` and `denominator` semantics.

### P0 — `config_validator.py` (614 → split into 2 files)

- [x] **Replace procedural cascade with declarative rule system** — Three check functions per field (required, type, range). Every new config key requires editing 3+ functions.
  - [x] Kept `validate_config()` dispatcher + helpers + required/types/ranges in `config_validator.py` (454 lines).
  - [x] New `config_validation_rules.py` (187) — Domain checks: `check_categories`, `check_lake_urls`, `check_prompts`, `check_batch_scheduler`, `check_timezone_and_paths`.

### P1 — `pipeline.py` (584 lines)

- [ ] **Extract phases into standalone async functions** — `main()` is ~280 lines of sequential orchestration with nested closures.
  - [ ] `pipeline/stage.py` — `async def stage_weather(...)`, `stage_rss(...)`, `stage_extract(...)`, `stage_summarize(...)`, `stage_render(...)`, `stage_validate(...)`.
  - [ ] `pipeline.py` — Keep orchestration layer only (~100 lines): calls stages in order, collects timings, handles errors/logging.

### P1 — Cross-cutting duplication

- [ ] **Deduplicate `build_context` usage** — Already in `utils.py` but called from `summarizer.py` with explicit `preview_chars` param. Verify consistency across all call sites.

### P2 — Files in 300–500 line range

- [ ] **Reduce `config.py` exports (363 lines)** — Lines 311–363 are 50+ module-level one-liner exports from `_RUNTIME_CONFIG`.
  - [ ] Option A: Export directly from `_RUNTIME_CONFIG` or a `Config` dataclass.
  - [ ] Option B: Keep current structure but generate exports programmatically via `__all__` or dynamic attribute access.
- [ ] **Improve `validation.py` (326 lines)** — Re-parses rendered Markdown to validate summaries, coupling to the MD format.
  - [ ] Primary validation should run on in-memory `Story` objects after summarization, not re-parse Markdown.
  - [ ] Keep render-format checking as a secondary sanity gate only.
- [ ] **Optimize `rss_dedup.py` widening (324 lines)** — `_widen_category_local` iterates ALL candidates per widen day (O(windows × candidates)). Pre-sort candidates by publish time to eliminate redundant scans.

### P2 — Cross-cutting structural issues (from review section 3)

- [ ] **Deduplicate regex patterns across the codebase** — `re.findall(r"\b[a-z]{3,}\b"` and `r"\b[a-z]{4,}\b"` appear in:
  - `summary_parser.py` — Already handled via `_keyword_set()` and `_best_headline_keyword_match()` (v1.0.145). Remaining uses in `config_validator.py` and `validation.py` still need dedup.
  - `validation.py` (1 location in topic overlap check)
  - `tagging.py` (implicitly via stop-word logic)
  - Create `utils.py` helper: `extract_significant_words(text, min_len=4)`.
- [ ] **Consolidate `_safe_text()` / `_coerce_temperature_f()` double-dispatching** — Both exist in `utils.py` and are re-wrapped elsewhere (`pipeline.py:260-269` delegates to `utils._coerce_temperature_f()`). Remove pipeline-level shim.
- [ ] **Investigate module-level globals shim (`pipeline.py:246-255`)** — `RUN_LOGFILE`, `PHASE_TIMINGS`, `OUTPUT_DIR`, `_llm_client` are set to `None` as module-level defaults, then reassigned in `main()`. Tests depend on reading these, but they contradict the `RunContext` concurrency isolation. Consider whether they're still needed once all paths use `RunContext`.

### P2 — Performance optimizations (from review section 4)

- [ ] **Optimize all-pairs mismatch detection O(n²×m)** — `summary_parser.py:422-434`: for each result, loop through all headlines to find best keyword match. Pre-compute significant-word sets for all headlines once, cache them, do set intersections instead of repeated regex + allocations.
- [ ] **Optimize fuzzy matching O(n×m) per STORY_N line** — `summary_parser.py:153-162`: every `STORY_N` line with `story_headlines` triggers a difflib `SequenceMatcher` against ALL headlines. With batch_size=4 and 76+ stories, that's 300+ difflib ratio calculations per response. Cache normalized headlines, consider `fuzzymatch`/`thefuzz` if batches grow.
- [ ] **Pre-compute keyword word counts in `tagging.py:131`** — `len([w for w in keyword.split() if w not in _STOP_WORDS])` creates a list allocation for every keyword match (~200 per report). Pre-compute during `precompile_tagging()`.
- [ ] **Pre-cache headline word sets in summarizer mismatch detection** — Lines 490–511 re-extract words per story × per headline. Compute once during `batch_summarize_all()` setup.
- [ ] **Add caching to `config.py` for test scenarios** — Module is re-imported by tests, triggering YAML parse + config build each time. Consider `@lru_cache` guard or module-level `_config_loaded` flag.

### P2 — Minor code quality

- [ ] **Remove unused `batch_size` parameter** — `summary_service.py:115` `_summarize_sub_batch` accepts `batch_size` but docstring says "Unused parameter kept for API compatibility".
- [ ] **Move `_EventLoopLagMonitor` out of `pipeline.py`** — 50 lines of profiling instrumentation mixed into core production code (~18% of pipeline file). Suggested: `pipeline/lag_monitor.py`.
- [ ] **Move `merge_weather_data` to separate `weather_model.py`** — `weather.py:279-365` is 87 lines of formatting logic. Orchestration (`fetch_weather`) and data modeling (`merge_weather_data`) should be separate.

### P3 — Investigate / deferred

- [ ] **Verify `build_context` import** — `summary_coordinator.py` (was `summarizer.py:23` before P0 split at v1.0.144) imports `build_context` from `utils.py`. Confirm it exists in the final version (review showed it moved there in v1.0.100).
