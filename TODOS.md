# TODO: Daily Brief v01

## Completed
- **Fix concurrency test hang:** `stage_weather()` used module-level `from daily_brief.sources.weather import fetch_weather` which bypassed test patches. Replaced with `_fw = _pip("fetch_weather")` late-binding. Updated test to patch `daily_brief.pipeline.fetch_weather`. Result: all 665/666 tests pass (1 skipped, 0 failures).
- **Fix concurrency test bugs**: Added `_current_context` test-hub shim in `pipeline/__init__.py`; wired `stage_rss(ctx, session, log_fn)` in concurrent `_phase2_rss` closure so Phase 2 timing is recorded. Retired `RUN_LOGFILE` import from `__init__.py`. Tests read per-run state from `_current_context`.

## Code Review Findings (2026-08-12)

Full review performed: structural issues, files exceeding 500/300 lines, performance optimizations, cross-cutting duplication. Plan only — no implementation.

### P0 — File size cap (hard policy)

**Python source files must not exceed 500 lines of code.** Anything above this degrades tool call performance for edits/reviews, increases cognitive load, and makes test authoring harder. This is a firm cap, not a soft recommendation.

- [x] **Enforce 500-line cap on every Python file** — Any file edited, created, or refactored must stay under 500 lines. If a file is approaching the cap, it is a signal to split *before* reaching it.

**Current state:** 2 files split under 500-line cap (P0 summarizer + config_validator). Remaining large files to audit.

- [x] **Audit high-overhead test modules** — 9 test files audited. 5 modules split under 500-line cap (completed below). 4 modules remain below cap and do not require splitting:
  - `test_tagging.py` (469 lines), `test_connectivity_extended.py` (467 lines), `test_report.py` (455 lines), `test_http_client.py` (454 lines).
- [x] **Identify tests that validate what the production validator already does** — Audit complete. No duplicate tests found for `validate_report()`. `TestIsValidSummary`, rendering safety tests, report tests, pipeline exit-code tests, and batch topic-mismatch tests are all needed coverage. Validator contract unification deferred to P2 `validation.py`.
- [x] **Consolidate test fixtures** — `tests/fixtures/parser_golden_fixtures.py` is data-only (no assertions, functions, or imports). 322 lines, 15 fixture dicts, one consumer. No consolidation needed. Two non-executed fixtures retained as documented coverage gaps.
- [x] **Split high-overhead test modules under 500-line cap** — 9 test modules audited; 5 split into 11 new modules, all under 500 lines:
  - `test_rendering_safety_contract.py` (884 → `test_rendering_story_safety.py` (499) + `test_rendering_weather_safety.py` (320) + re-export (22))
  - `test_summarizer.py` (741 → `test_summarizer_quality.py` (405) + `test_summarizer_batch.py` (333) + re-export (30))
  - `test_weather_climate_contract.py` (711 → `test_climate_contract.py` (437) + `test_weather_labels_contract.py` (289) + re-export (29))
  - `tests/test_sources/test_weather.py` (600 → `test_weather_helpers.py` (76) + `test_weather_fetch.py` (499) + re-export (12))
  - `test_concurrency_contract.py` (744 → `tests/concurrency_support.py` (124) + `test_concurrency_run_context.py` (198) + `test_concurrency_atomic.py` (168) + `test_concurrency_scheduling.py` (152) + re-export (22))

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

### P1 — `pipeline.py` (584 lines → reduced to ~178 in main())

- [x] **Extract phases into standalone async functions** — `main()` reduced from ~500 to ~178 lines.
  - [x] `pipeline/stages.py` — `async def stage_weather(...)`, `stage_rss(...)`, `stage_extract(...)`, `stage_summarize(...)`, `stage_render(...)`, `stage_validate(...)`.
  - [x] `pipeline.py` (`main()`) — Orchestration layer only: config validation, preflight, context setup, reservation, logger lifecycle, sequential stage calls, teardown.
  - [x] All stage functions use `_pip()` late-resolution for test-patch compatibility.

### P1 — Cross-cutting duplication

- [x] **Deduplicate `build_context` usage** — Verified consistency: `utils.py` defines `build_context(story, preview_chars=600)`, all production callers pass `preview_chars=LLM_CONTEXT_PREVIEW_CHARS` (configured to 600). Added regression tests (`tests/test_build_context_wiring.py`) verifying batch recovery and individual recovery wiring. Truncation tested at non-default 25-char value.

### P2 — Files in 300–500 line range

- [ ] **Reduce `config.py` exports (363 lines)** — Lines 311–363 are 50+ module-level one-liner exports from `_RUNTIME_CONFIG`.
  - [ ] Option A: Export directly from `_RUNTIME_CONFIG` or a `Config` dataclass.
  - [ ] Option B: Keep current structure but generate exports programmatically via `__all__` or dynamic attribute access.
- [ ] **Improve `validation.py` (326 lines)** — Re-parses rendered Markdown to validate summaries, coupling to the MD format.
  - [ ] Primary validation should run on in-memory `Story` objects after summarization, not re-parse Markdown.
  - [ ] Keep render-format checking as a secondary sanity gate only.
- [ ] **Optimize `rss_dedup.py` widening (324 lines)** — `_widen_category_local` iterates ALL candidates per widen day (O(windows × candidates)). Pre-sort candidates by publish time to eliminate redundant scans.

### P2.4 Optional config override + optional Git provenance frontmatter (v1.0.159)

- [x] Refactor `config.py` — rename `CONFIG_HOME → DEFAULT_CONFIG_FILE_PATH`, add `use_config_path()`, `config_source()`, fix initialization ordering.
- [x] CLI — add top-level `--config PATH` in `cli.py` and `__main__.py` (parse before importing `daily_brief.config`), propagate to `use_config_path()`.
- [x] Config subcommands — `validate`, `show`, `list-categories`, `list-lakes`, `show-prompt` accept `--yaml PATH` for alternate config inspection.
- [x] `daily_brief/provenance.py` — small helper resolving commit SHA, committed timestamp, author name, committer name via `subprocess.run([...], shell=False, timeout=5)`.
- [x] Extend `RunContext` with optional `provenance` field; populate once in `main()` before rendering via `resolve_git_*` helpers.
- [x] Thread provenance through `stage_render()` → `build_markdown()` → safe YAML-escaped frontmatter (names only, no email). Names with colons/quotes/newlines are safely double-quoted.
- [x] Focused tests: `tests/test_provenance.py` (17 tests); `tests/test_config_override.py` (6 tests).
- [x] Updated PLAN.md, PROJECT.md, SUMMARY.md, TODOS.md with implementation status.
- [x] **Correctness fix (v1.0.159.1)**: Fixed `_find_config_path` precedence (env was checked before CLI override, now correct), `use_config_path()` now rebuilds `_RUNTIME_CONFIG` (was only updating `CONFIG_YAML`), explicit missing config now raises `FileNotFoundError` (was silently degrading).

### P2 — Cross-cutting structural issues (from review section 3)

- [x] **Deduplicate regex patterns across the codebase** — `re.findall(r"\b[a-z]{3,}\b"` and `r"\b[a-z]{4,}\b"` appear in:
  - Extracted `extract_significant_words(text, min_len=4)` in `utils.py`.
  - Migrated `validation.py` topic-overlap check to use helper.
  - Migrated `tagging.py._keyword_has_stop()` to use helper.
  - Removed unused `re` import from `config_validator.py`.
  - Summary-parser and summary-quality kept separate (different semantics — separate task).
- [x] **Consolidate `_safe_text()` / `_coerce_temperature_f()` double-dispatching** — Already canonical in `utils.py` after P1 split. The `daily_brief.pipeline` module only re-exports `_coerce_temperature_f` as a compatibility alias. No functional duplication remains; shim retained for import-level compatibility.
- [x] **Investigate module-level globals shim (`pipeline.py:246-255`)** — `RUN_LOGFILE`, `PHASE_TIMINGS`, `OUTPUT_DIR`, `_llm_client` are dead in production. Removed from `context.py` (legacy globals deleted) and `stages.py` (assignments and exports removed). Added `ContextVar`-based `_current_context_var` + `get_current_run_context()` in `__init__.py` for task-local test observation. Backward-compat `get_current_run_context()` falls back to module-level `_current_context` for sequential `run_until_complete()` tests. All 4 tests using old pattern updated.
- [x] **HTTP body-size safety** — Replaced `resp.content.iter_any()` with `iter_chunked(8192)` in http_client.py. Applied per-source limits: article 2 MiB, RSS 1 MiB, NWS JSON 1 MiB, ERA5 512 KiB, lake 1 MiB, Wunderground 2 MiB. Updated all test mocks. 681 tests pass.

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
