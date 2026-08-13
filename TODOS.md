# TODO: Daily Brief v01 — v1.0.144

## Code Review Findings (2026-08-12)

Full review performed: structural issues, files exceeding 500/300 lines, performance optimizations, cross-cutting duplication. Plan only — no implementation.

### P0 — File size cap (hard policy)

**Python source files must not exceed 500 lines of code.** Anything above this degrades tool call performance for edits/reviews, increases cognitive load, and makes test authoring harder. This is a firm cap, not a soft recommendation.

- [ ] **Enforce 500-line cap on every Python file** — Any file edited, created, or refactored must stay under 500 lines. If a file is approaching the cap, it is a signal to split *before* reaching it.

Current state: **1,145 test lines vs 5,970 production lines = 1.7:1 ratio** (tests are nearly 2× production). This is inverted — tests should be leaner.

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
- [ ] **Set a target ratio** — Recommend 1:1 or less (test lines ≤ production lines). That means reducing ~5,200 test lines or refactoring production down. Start by cutting the 9 files above that exceed 400 lines.
- [ ] **Consolidate test fixtures** (`tests/fixtures/parser_golden_fixtures.py`, 322 lines) — These are loaded by tests for golden-match parsing. Verify they don't also test behavior (fixtures should be data + minimal helpers, not assertions).

### P0 — Files > 500 lines (High complexity, high reward)

- [ ] **Split `llm/summarizer.py` (1,014 lines)** into three modules:
  - [ ] `llm/summary_parser.py` — Extract `parse_batch_summary_response()` and all matching strategies (~430 lines). Isolated parsing logic: fuzzy/keyword fallback/positional/adjacent-swap-fix.
  - [ ] `llm/quality.py` — Extract `_is_refusal`, `_is_boilerplate`, `_is_valid_summary`, `_has_topic_overlap`, `_generate_auto_fallback`, `_significant_words` (~130 lines).
  - [ ] `llm/summarizer.py` — Keep `_summarize`, `_summarize_sub_batch`, `batch_summarize_all` (~250 lines).
  - [ ] **NOTE — test splitting:** Current `tests/test_summarizer.py` (741 lines) tests the monolithic file. When the module splits, tests must split proportionally — move unit tests for quality/parser to their own test files to avoid a 740-line test file that imports from three new modules. Goal: tests should not exceed production code.
- [ ] **Deduplicate parser logic** — Strategies 1 and 2 both do keyword overlap with near-identical `re.findall(r"\b[a-z]{4,}\b", ...)` extraction. All-pairs mismatch detection (lines 486–522) repeats the same work. Pre-compute significant-word sets, cache normalized headlines, use a shared `extract_significant_words()` helper.

### P0 — `config_validator.py` (614 lines)

- [ ] **Replace procedural cascade with declarative rule system** — Three check functions per field (required, type, range). Every new config key requires editing 3+ functions.
  - [ ] Keep `validate_config()` dispatcher in current file (~100 lines).
  - [ ] New `config/rules.py` — registry where validations are data: `[{"field": "llm.model", "check": "required_str"}, ...]`.
  - [ ] New `config/types.py` — `check_types()` becomes a single loop over the rule registry.
  - [ ] New `config/ranges.py` — Range checks as rule-driven.

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
  - `summarizer.py` (8+ locations in parsing/validation)
  - `validation.py` (1 location in topic overlap check)
  - `tagging.py` (implicitly via stop-word logic)
  - Create `utils.py` helper: `extract_significant_words(text, min_len=4)`.
- [ ] **Consolidate `_safe_text()` / `_coerce_temperature_f()` double-dispatching** — Both exist in `utils.py` and are re-wrapped elsewhere (`pipeline.py:260-269` delegates to `utils._coerce_temperature_f()`). Remove pipeline-level shim.
- [ ] **Investigate module-level globals shim (`pipeline.py:246-255`)** — `RUN_LOGFILE`, `PHASE_TIMINGS`, `OUTPUT_DIR`, `_llm_client` are set to `None` as module-level defaults, then reassigned in `main()`. Tests depend on reading these, but they contradict the `RunContext` concurrency isolation. Consider whether they're still needed once all paths use `RunContext`.

### P2 — Performance optimizations (from review section 4)

- [ ] **Optimize all-pairs mismatch detection O(n²×m)** — `summarizer.py:486-522`: for each result, loop through all headlines to find best keyword match. Pre-compute significant-word sets for all headlines once, cache them, do set intersections instead of repeated regex + allocations.
- [ ] **Optimize fuzzy matching O(n×m) per STORY_N line** — `summarizer.py:153-162`: every `STORY_N` line with `story_headlines` triggers a difflib `SequenceMatcher` against ALL headlines. With batch_size=4 and 76+ stories, that's 300+ difflib ratio calculations per response. Cache normalized headlines, consider `fuzzymatch`/`thefuzz` if batches grow.
- [ ] **Pre-compute keyword word counts in `tagging.py:131`** — `len([w for w in keyword.split() if w not in _STOP_WORDS])` creates a list allocation for every keyword match (~200 per report). Pre-compute during `precompile_tagging()`.
- [ ] **Pre-cache headline word sets in summarizer mismatch detection** — Lines 490–511 re-extract words per story × per headline. Compute once during `batch_summarize_all()` setup.
- [ ] **Add caching to `config.py` for test scenarios** — Module is re-imported by tests, triggering YAML parse + config build each time. Consider `@lru_cache` guard or module-level `_config_loaded` flag.

### P2 — Minor code quality

- [ ] **Remove unused `batch_size` parameter** — `summarizer.py:727` `_summarize_sub_batch` accepts `batch_size` but comment says "unused parameter kept for API compatibility".
- [ ] **Move `_EventLoopLagMonitor` out of `pipeline.py`** — 50 lines of profiling instrumentation mixed into core production code (~18% of pipeline file). Suggested: `pipeline/lag_monitor.py`.
- [ ] **Move `merge_weather_data` to separate `weather_model.py`** — `weather.py:279-365` is 87 lines of formatting logic. Orchestration (`fetch_weather`) and data modeling (`merge_weather_data`) should be separate.

### P3 — Investigate / deferred

- [ ] **Verify `build_context` import** — `summarizer.py:23` imports `build_context` from `utils.py`. Confirm it exists in the final version (review showed it moved there in v1.0.100).
