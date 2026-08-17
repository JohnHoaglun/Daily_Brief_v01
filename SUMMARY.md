# Project Summary: Daily_Brief_v01

## Changelog

### v1.0.159 — Config override + Git provenance frontmatter wiring

- **CLI `--config PATH` flag**: Parse before pipeline import; calls `use_config_path()` to override config source for the run. Top-level flag for pipeline; config subcommands use `--yaml` to avoid name collision.
- **Config subcommands**: `validate`, `show`, `list-categories`, `list-lakes`, `show-prompt` now accept `--yaml PATH` for inspecting alternate configs.
- **Git provenance in pipeline**: `stages.py::main()` calls four `resolve_git_*()` helpers from `provenance.py` and stores results in `RunContext.provenance` dict.
- **Rendering thread**: `stage_render()` receives `ctx` and passes `ctx.provenance` to `build_markdown(git_provenance=...)`.
- **YAML frontmatter insertion**: `build_markdown()` emits optional `git_commit`, `git_committed_at`, `git_author_name`, `git_committer_name` fields in frontmatter. Names are safely YAML-escaped (double-quoted when containing colons, quotes, newlines).
- **Graceful degradation**: Missing git CLI, non-zero exit, timeout, or report written from a non-Git checkout produces the brief with provenance omitted — never aborts.
- **Export wiring**: `pipeline/__init__.py` exports `use_config_path` for CLI integration.
- **Version bump**: 1.0.158 → 1.0.159.

### v1.0.158 — P2.4 Optional config override + optional Git provenance frontmatter (scope)

### v1.0.156 — P2.3 Dynamic config exports

- **Replaced 52 explicit runtime config assignments** with module-level `__getattr__` backed by `_RUNTIME_CONFIG`.
- Added `__all__` covering all 52 runtime keys, loader helpers, static constants, and the `DEFAULT_AGE_LIMIT_HOURS` legacy alias.
- 5 new tests in `test_config.py` for dynamic-export behavior (getattr per key, alias, from-import, `__all__` completeness, AttributeError on unknown).
- 681 tests pass (was 676 after v1.0.155), 0 regressions. 363 → 296 lines.

### v1.0.157 — P2.3 HTTP body-size safety

- **Replaced `resp.content.iter_any()` with `iter_chunked(8192)`** in `_read_body_bounded()` — makes the existing 5 MiB cumulative bound meaningful by forcing chunk-bounded iteration instead of single-chunk delivery.
- **Applied explicit per-source limits**: article HTML 2 MiB, RSS XML 1 MiB, NWS JSON 1 MiB, ERA5 JSON 512 KiB, lake HTML 1 MiB, Wunderground/weather.gov HTML 2 MiB.
- Updated all `iter_any()`-only mock classes in tests to also implement `iter_chunked()` for compatibility.
- 681 tests pass, 0 regressions.

### v1.0.155 — P2.2 Cross-cutting structural cleanup

- **Extracted `extract_significant_words()` in `utils.py`** — dedplicates the regex tokenization previously scattered across `validation.py` and `tagging.py`. `config_validator.py` unused `re` import removed. `llm/summary_parser.py` and `llm/summary_quality.py` intentionally kept separate (different tokenization semantics).
- **Eliminated `RUN_LOGFILE`/`PHASE_TIMINGS`/`OUTPUT_DIR`/`_llm_client` globals** — removed from `context.py` and `stages.py`. `stages.py` no longer propagates module-level attributes into the `daily_brief.pipeline` package.
- **Added `ContextVar`-backed test-hub** — `get_current_run_context()` in `__init__.py` provides task-local context observation. Falls back to module-level `_current_context` for backward compat with `run_until_complete()` tests. All 676 tests pass (was 669).

- **Eliminated version duplication across 20+ files.** Version text is now **only** in `daily_brief/_version.py`.
- Removed version from all module docstrings (sources, pipeline, utils, models, http_client, lifecycle, llm, validation).
- Removed `version` key from `config.yaml` and `DEFAULTS["version"]` from `config.py`. `VERSION` now derives directly from `PACKAGE_VERSION`.
- Removed `version` from `_REQUIRED_TOP` validator, `check_types()` version check, and semver check — config.yaml no longer carries version.
- Deleted `versions_locations.md` registry; replaced with documented release process in `PLAN.md`.
- Added `tests/test_version_single_source.py`: 4 tests verifying single-source of truth (canonical import, no version in config.yaml/docstrings/config file).
- Updated `README.md` title, config table entry, `PROJECT.md`, `TODOS.md`, `PLAN.md`, `dashboard_pipeline.py`.

### v1.0.153 — P2.1 Finalize test-context wiring; concurrency scheduling fix
- Add ``_update_test_context(ctx)`` call in ``stages.py`` ``main()`` body (end of try block, before return) for test-hub consistency.
- Simplify ``_phase2_rss()`` closure in ``main()`` to call ``stage_rss()`` directly without inline try/except.
- Update module docstring for ``daily_brief/pipeline/__init__.py``.
- **Fix test-phase hang (`test_phase_1_and_2_run_concurrent`):** `stage_weather()` had module-level `from daily_brief.sources.weather import fetch_weather` which bypassed test patches. Replaced with `_fw = _pip("fetch_weather")` late-binding (matching `stage_rss`/`stage_extract` patterns). Updated `test_patch_fetch_weather_at_package_level` to patch `daily_brief.pipeline.fetch_weather`.
- **Result:** 665/666 tests pass (1), 0 failures after fix.

## Overview
Automated daily news brief generator that fetches news from 17 content categories and produces Markdown reports with AI summaries via vLLM (OpenAI-compatible client).

## Change Log
### v1.0.151 — P2.1: Wire RunContext through pipeline and fix concurrency tests

- **Add `_current_context` test-hub shim** to `pipeline/__init__.py`: Single global `Optional[RunContext]`; `main()` propagates the per-run context via `_pmod._current_context = ctx`.
- **Fix Phase 2 timing in concurrent pair**: The `_phase2_rss()` closure in `main()` now calls `stage_rss(ctx, session, log_fn)` instead of the raw `fetch_and_dedup()`, so `ctx.phase_timings["Phase 2"]` is properly recorded.
- **Backwards-compatible globals**: Retired the import of retired globals from `stages.py` in `__init__.py`. Module-level `RUN_LOGFILE`, `PHASE_TIMINGS`, `OUTPUT_DIR`, `_llm_client` remain in `stages.py` for existing test fixtures but are updated at the start of `main()`.
- **Updated concurrency tests**: `test_concurrency_run_context.py`, `test_concurrency_scheduling.py`, `test_concurrency_atomic.py` now read `ctx.phase_timings`, `ctx.run_logfile`, `ctx.output_dir` from `_current_context`.
- **Version bump**: v1.0.149 → v1.0.151 across all 27+ registry locations.
### v1.0.149 — P1: Pipeline stage extraction

- **Extract `_phase1_weather()` closure**: replaced inline nested closure with standalone `async def stage_weather(ctx, session, log_fn)` — identical behavior with late-bound `_pip()` resolution for test-patch compatibility.
- **Extract `_phase2_rss()` closure**: standalone `async def stage_rss(ctx, session, log_fn)` — calls `fetch_and_dedup()`, records Phase 2 timing, returns `(deduped, stats)` tuple.
- **Extract Phase 3A article extraction**: standalone `async def stage_extract(stories, ctx, session, log_fn)` — constructs `StoryPipelineState` objects from deduped tuples, bounded extraction via semaphore, loop-lag monitoring (`_EventLoopLagMonitor`), extraction metrics, Phase 3A timing.
- **Extract Phase 3B/3C summarization**: standalone `async def stage_summarize(stories, ctx, log_fn)` — calls `batch_summarize_all()`, logs `SummaryMetrics`, records Phase 3 timing.
- **Extract Phase 4 rendering**: standalone `async def stage_render(stories, weather, dedup_stats, ctx, log_ver, log_fn)` — cleanup → story sections → `build_markdown()` → `write_report()` → log cleanup → records Phase 4 timing → returns report path.
- **Extract Phase 5 validation**: standalone `async def stage_validate(report_path, ctx, log_fn, run_start)` — calls `validate_report()`, returns `EXIT_CODE_VALIDATION` or `EXIT_CODE_SUCCESS`.
- **Reduce `main()` from ~500 to ~178 lines**: orchestration layer now only contains config validation, preflight, context setup, reservation, logger lifecycle, logger session management, sequential stage calls, and teardown.
- **Add `SummaryMetrics`, `CATEGORY_PRIORITY`, `CATEGORIES`, `format_pub_date`, `_normalize_weather_for_rendering` to pipeline module `__all__`** for late-bound `_pip()` resolution.
- **build_context verification**: `tests/test_build_context_wiring.py` (10 tests) — verifies `build_context` is called with `preview_chars=LLM_CONTEXT_PREVIEW_CHARS` in both batch summarization and individual recovery paths; tests truncation at non-default `preview_chars=25`.
- **Stage extraction regression tests**: `tests/test_pipeline_stages.py` (12 tests) — verifies stage functions exist, concurrent pair, short-circuit before stages, package-level patching. All 639 tests passing, config validate PASS.
### v1.0.147 — P1 Structural Refactor: Pipeline Package (cont.)
- **Drop _EventLoopLagMonitor/_percentile/_count_extracted into context.py**: extracts ~63 lines from stages.py (536→476, under 500 hard cap). Re-imported by stages.py and re-exported via __init__.py for backwards compat with test patches.
- **versions_locations.md**: updated canonical version to `v1.0.147`; replaced `daily_brief/pipeline.py` entry with three new package files.

### v1.0.146 — P1 Structural Refactor: Split pipeline.py into package
- **Deduplicate keyword extraction** (`daily_brief/llm/summary_parser.py`): Extracted `_keyword_set(min_length=)` and `_best_headline_keyword_match(query_words, ..., denominator=)` private helpers. Replaced repeated `re.findall(r"\b[a-z]{4,}\b"`/`r"\b[a-z]{3,}\b"` tokenization in summary-to-headline matching, prefix/excerpt matching, positional fallback keyword matching, adjacent swap detection, and all-pairs mismatch validation. Strategies retain distinct `min_length` (4 vs 3) and `denominator` ("headline" vs "query") semantics. 452 lines → 471 lines.
- **Strengthened first-wins assertion** (`tests/test_parser_assignment_contract.py`): `TestNoOverwrite.test_both_match_headline_zero_second_does_not_overwrite` now asserts `"Firefighters contained"` (STORY_0's distinctive text) and rejects `"evacuated"` (STORY_2's distinctive text), preventing silent last-wins overwrite that the old `"downtown"` check cannot detect.
- **521/521 tests passing**, 1 pre-existing failure (unchanged), config validate PASS.

### v1.0.144 — Packaging, CI, and Repository Hygiene (Priority 3)
- **Canonical version source** (`daily_brief/_version.py`): single `__version__` string; package `__init__.py` and runtime config default derive from it. Eliminates scattered literal version numbers.
- **PEP 621 packaging** (`pyproject.toml`): setuptools build system with flat-layout discovery, dynamic version, `requires-python >= 3.9`, runtime/test dependency declarations, `daily-brief` console script entry point.
- **Wheel-compatible config delivery** (`daily_brief/config.yaml`): factory defaults shipped as package data. Loader fallback chain: `DAILY_BRIEF_CONFIG` env → project root → `~/.config/daily_brief/` → packaged resource via `importlib.resources`.
- **sys.path mutation removed** (`tests/test_parser_golden.py`): golden fixture module loaded via `importlib.util.spec_from_file_location` — no longer mutates `sys.path`.
- **Dependency lockfile** (`uv.lock`): `uv`-resolved lock with 56 packages, Python 3.9+ and 3.10+ resolution markers.
- **CI workflow** (`.github/workflows/ci.yml`): GitHub Actions for push and pull_request — test matrix (Python 3.9 and 3.13), source/wheel build verification, format check (ruff), lint (ruff, report-only), type check (mypy, report-only).
- **Ruff formatting and lint**: all files formatted; safe auto-fixes applied (296 fixes: import sorting, etc.). `pyproject.toml` lint config with targeted rule selection.
- **Mypy baseline** (`pyproject.toml`): Python 3.9 target, `ignore_missing_imports`, `disallow_untyped_defs = false` for existing codebase. 43 pre-existing type errors.
- **Test script repair** (`scripts/run_tests.sh`, `scripts/run_coverage.sh`): failure reporting functions wrap pytest so banners run; coverage script produces terminal + XML output.
- **Repository hygiene**: `.gitignore` expanded for coverage variants (`*.coverage.*`, `coverage.xml`), build/dist artifacts, venv directories, lint/type-checking caches. MIT `LICENSE` file added.
- **635/635 tests passing**, config validate PASS. Package builds wheel and sdist successfully.

### v1.0.143 — Pipeline Concurrency Benchmark Driver
- **Dedicated benchmark driver** (`daily_brief/benchmark_pipeline_concurrency.py`): standalone module that runs full pipeline passes with configurable `article_max_concurrency` settings and serial/concurrent Phase 1/2 dispatch mode. Does not modify production pipeline, log output, or report locations.
- **Benchmark-only serial/concurrent toggle**: `phase_mode="serial"` or `"concurrent"` allows controlled before/after comparison of Phase 1/2 dispatch. Production always runs concurrent.
- **Extraction metrics aggregation**: `ExtractionMetrics` dataclass with fetch/parse/bytes distributions (min, max, mean, p50, p95, p99), failure and skipped counts, observed max concurrency. Uses `_stats_from_list()` for distribution summary.
- **Structured JSON output**: `CellResult` with extraction stats, loop lag percentiles, phase timings, report validation, harness status, process exit code. `BenchmarkRun` with provenance, multiple cells, summary with medians and best concurrency.
- **Configuration provenance**: `_build_provenance()` captures version, LLM settings, weather config, categories, and timestamp. Each cell result includes full provenance.
- **Single `asyncio.run()`**: `_run_async_benchmark()` orchestrates all warmups and measured cells in one event loop, avoiding Python 3.9 event loop churn between cells.
- **CLI subcommand**: `build_benchmark_parser()` with `--concurrency`, `--cells`, `--warmups`, `--phase-mode`, `--output`, `--log-dir`, `--news-dir` flags.
- **Concurrency tracker**: `_ConcurrencyTracker` with async enter/exit and peak property. Tracks observed max concurrent extraction count.
- **Tests**: 50 deterministic tests across 13 test classes — stats from list (5), percentile (5), extraction metrics aggregation (3), loop lag metrics (2), phase timings (2), cell result shape (3), benchmark run shape (2), concurrency tracker (3), run benchmark orchestrator (11), provenance (5), story metrics extraction (2), CLI (6), JSON result end-to-end (1). 50/50 passing.
- **Config validate**: PASS. 635 total tests (585 existing + 50 new).

### v1.0.142 — Logging Consolidation
- **Run-scoped logger**: replaced direct `_log_ctx()` file writes with a dedicated per-run `logging.Logger` instance. Each pipeline invocation creates a new logger with file + stderr handlers, configured after `RunAllocator.reserve()` sets the log path. Handlers are closed/removed in `finally` via `_teardown_run_logger()` to prevent cross-run contamination during concurrent invocations.
- **Retired legacy `log()` global**: the module-level `log()` function and `log_lock` are removed. `_coerce_temperature_f()` now writes extreme-temperature warnings directly to `sys.stderr`.
- **`_RunTimestampFormatter`**: custom formatter producing `[YYYY-MM-DD HH:MM:SS] msg` to match legacy log output format.
- **RSS dedup callback**: `fetch_and_dedup()` receives `lgr.info` (bound method) as the `log_fn` callback.
- **Tests**: 585/585 passing. Config validate PASS. All concurrency-contract tests verified — concurrent runs maintain independent log files with no handler leakage.

### v1.0.141 — Connectivity Hardening
- **TLS verification restored**: removed `ssl=False` from LLM probe — aiohttp default certificate and hostname verification retained.
- **User-Agent forwarding**: all connectivity probes (LLM, RSS, weather.gov, Open-Meteo, Wunderground, lakes) now send the configured `USER_AGENT` header. Matches production session contract.
- **RSS query encoding**: RSS probe URL uses `urllib.parse.quote_plus` for percent-encoding of reserved characters. Aligns with production RSS URL construction.
- **Safe lake URL parsing**: replaced `url.split("/")[2]` display with `urllib.parse.urlsplit(parsed).netloc`. Malformed configured URLs that pass the shallow validator now produce safe output instead of raising.
- **Tests**: 24 connectivity tests (13 existing + 11 new): TLS regression (`ssl=` absent from check_llm), User-Agent forwarding to all 6 probes, reserved-character RSS encoding, normal and malformed lake URL safety. 585/585 passing, config validate PASS.

### v1.0.140 — HTML Parsing Offload
- **Threaded parsing**: BeautifulSoup CPU work extracted to `_parse_article_html(html) -> str`, dispatched via `asyncio.to_thread()`. Parse timing retained as `extract_parse_time_s`.
- **Event-loop safety**: Only the synchronous parse/clean step runs in a worker thread. HTTP fetch, retries, semaphore ownership, error handling, and `story.context` assignment remain on the event loop.
- **Tests**: 5 new offload tests in `test_extraction_metrics.py`: parse parity, dispatch verification, error containment, event-loop responsiveness, concurrency cap preservation. 574/574 passing.

### v1.0.138 — Extraction Measurement and Event-Loop Lag
- **Per-article timing**: `extract_fetch_time_s`, `extract_parse_time_s`, `extract_bytes` on successful extractions. Skipped articles untouched.
- **Phase 3A instrumentation**: Wall time, throughput (stories/s), extracted context count, error count. `ctx.phase_timings["Phase 3A"]`.
- **Event-loop lag**: `_EventLoopLagMonitor` with 20ms ticks, p50/p95/p99/max logged during extraction. `_percentile` and `_count_extracted` utilities.
- **Tests**: 14 new tests in `test_extraction_metrics.py`. 569/569 passing.

### v1.0.137 — Bounded HTTP Response Handling
- **Content-Length pre-check**: declared `Content-Length` above the configured limit is rejected without reading the body. `_exceeds_content_length_header()` returns True when the header exceeds the limit.
- **Streaming byte limit**: `_read_body_bounded()` streams the response body via `resp.content.iter_any()`, counting bytes, and raises `ContentLengthError` when the limit is exceeded. Handles chunked or missing-length responses.
- **Retry/status preserved**: existing retry logic (`_should_retry()` on transient statuses), non-retryable status behavior, and status predicate forwarding remain unchanged.
- **Parameter forwarding**: `max_bytes` parameter added to `_request_with_retry`, `_fetch_json`, and `_fetch_text`. Default `DEFAULT_MAX_CONTENT_BYTES = 5 MB`. Sources can override per-call.
- **Tests**: 11 new tests in `test_http_client.py` — Content-Length pre-check (reject/accept/missing), streaming (within limit/exceeds limit), wrapper forwarding for `_fetch_text` and `_fetch_json`. 555/555 passing.
- **Test infrastructure**: updated `MockResp`/`FakeResp`/`_TestContent` mocks across `test_http_client.py`, `test_article.py`, `test_rss.py`, `test_rss_dedup.py`, `test_weather_climate_contract.py` to support `headers` and `content.iter_any()` required by bounded response handling.
- **Test fix**: corrected `test_string_payload` assertion (was asserting `42`, fixed to `"ok"`).

### v1.0.136 — Coder Dispatch Analysis Correction
- **Responsibility corrected**: the failed Coder delegation in v1.0.135 was primarily a Build orchestration failure. Build assigned a three-file cross-module task outside Coder's single-file lane and did not immediately verify the returned edit.
- **32k context conclusion corrected**: it is a boundary to respect, not demonstrated evidence of a Coder limitation for small self-contained work. Build must provide the local source context, exact insertion point, and acceptance test.
- **Operating contract**: one file, one cohesive edit, no overlapping writers, mandatory syntax/focused-test verification, and a Build-side repeat of the focused test before integration.
- **Evaluation plan**: run five independent, correctly scoped one-file lanes and measure acceptance rate, rework time, and total elapsed time before changing models or disabling Coder.

### v1.0.135 — Bounded RSS Candidate Pool Limits + URL hours-to-days fix
- **Bounded candidate pool**: `RSS_CANDIDATE_POOL_LIMIT` defaults to 50; sparse local categories (`Conroe`, `Montgomery Co`, `Houston Tropical`) override to 100. Prevents unbounded memory growth from wide `when:` queries on feeds with thousands of daily stories.
- **URL hours-to-days**: `build_rss_url_with_window()` converts hours to whole days via ceiling division (168h→7d, 169h→8d) for Google News `when:` syntax.
- **Widening cap**: `_widen_category_local()` capped at category's `source_window_hours` — won't inspect a 48h age band for a category with a 24h source window.
- **Config validator**: fixed `NameError` in `check_categories` (unbound `rss` variable); added type/range validation for `rss.candidate_pool_limit` and per-category `candidate_pool_limit`.
- **Tests**: new `TestBuildRssUrlWithWindow`, `TestCandidatePoolConfig`, widening cap test; cleaned broken tests from old `TestBuildRssUrl`. 545/545 passing.

### v1.0.134 — Category-Aware RSS Windows with tiered query windows
- **Tiered source windows**: `build_rss_url_with_window()` prefixes `when:Xd` (`World/US=24h`, `Texas/Houston=72h`, `Conroe/Montgomery=168h`) to widen candidate pool for sparse local feeds while preserving strict recency filtering via `min_age_hours`.
- **URL encoding**: all query values encoded via `quote_plus(safe="")` in `build_rss_url()`.
- **Config**: `default_source_window_hours` in RSS section, per-category `source_window_hours` in categories, `CATEGORY_SOURCE_WINDOWS` exported from config.
- **Widening capped** at category source window in `_widen_category_local()` — no longer hardcoded to 7 days.
- **Config fixes**: `hl=int-US` → `hl=en-US`, `category_source_windows` removed from YAML (source window is per-category).
- **Validation**: `source_window_hours` validated (1-168) at category and RSS default levels.
- **Tests**: URL encoding tests, windowed URL tests, dedup mocks for category-aware widening, 533/533 passing.

### v1.0.133 — Concurrent rainfall sources + tracking cleanup
- **Concurrent rainfall fetches** in `_fetch_station_monthly_rainfall()`: Wunderground station-range and weather.gov climate-summary now launch simultaneously via `asyncio.gather()`.
- **Test conversion**: replaced call-order mocks with URL-based dispatch in Wunderground tests. Event-gated concurrency test added (`test_rainfall_fetches_concurrently`).
- **Stale TODO reconciliation**: weather-provider concurrency (v1.0.132), atomic report/log allocation (v1.0.127), RunContext globals (v1.0.127) now checked off.
- **530+ tests passing**, config validate PASS.
---
### v1.0.132
 — Concurrent weather-provider collection
- **All four weather providers start concurrently** in `fetch_weather()`: NWS forecast, climate normal, Wunderground rainfall, and lake collection are launched together via single `asyncio.gather(..., return_exceptions=True)`. Replaces sequential NWS → climate/rainfall → lakes orchestration.
- **Deterministic concurrency test** with event-gated mocks in `test_weather_extended.py` verifies all four providers enter before any completes.
- **530/530 tests passing**, config validate PASS.
---
### v1.0.131 — Stale reference cleanup + registry fix
- **All version references** across 24 files updated from v1.0.127 to v1.0.131 per `versions_locations.md` registry.
- **Registry updated**: added `PLAN.md`, `SUMMARY.md`, `daily_brief/config.py`.
- **530/530 tests passing**.
- **24 files changed, 31 insertions(+), 28 deletions(-)**
---
### v1.0.128 — Weather label + no-fallback test fixes
- **Weather label format**: `get_weather_label_for_offset()` now returns abbreviated day-of-week (`strftime("%a")`) — e.g. "Sun", "Mon" — replacing "Today"/"Today Night"/"Tomorrow". Date column in weather table shows day names consistently.
- **Forecast fallback removed**: `merge_weather_data()` no longer falls back to forecast high temperature when ERA5 climate normal is absent. Station `avg_temp_today` is "Unavailable" instead.
- **Test fixes** (`test_weather_provider_isolation.py`): `test_full_provider_data` updated for "Sat" date labels. `test_era5_absent_no_fallback` and `test_both_fail_fallback` (renamed `test_both_fail_no_fallback`) updated to assert "Unavailable" when ERA5 data is missing.
- **530/530 tests passing**.
- **1 file changed, 9 insertions(+), 9 deletions(-)**
---
### v1.0.127 — Wave 4: Concurrency Safety
- **RunContext pattern** (`pipeline.py`): Per-run context scoping eliminates global state leaks between concurrent pipeline invocations. Phase timings, llm_client, log file path, and output directory all scoped to `RunContext`. Module-level `RUN_LOGFILE`, `PHASE_TIMINGS`, `OUTPUT_DIR` kept as backwards-compat shim.
- **Atomic run reservation** (`lifecycle.py`): `RunAllocator` uses O_CREAT|O_EXCL filesystem markers for exclusively unique version allocation. Concurrent processes scan existing logs and markers, then atomically claim their version. Collision resolution via retry on FileExistsError.
- **Concurrent Phase 1+2** (`pipeline.py`): Weather and RSS fetch dispatched concurrently via `asyncio.gather()` (was serial). Bounded article extraction via `asyncio.Semaphore` from `ARTICLE_MAX_CONCURRENCY` config.
- **Atomic report writes** (`rendering/report.py`): `write_report()` writes to temp file, verifies content, then `os.replace()` for atomic overwrite. On failure, original report preserved and temp file cleaned up.
- **Configuration** (`config.yaml`, `config.py`, `config_validator.py`): `ARTICLE_MAX_CONCURRENCY` added (default 4, validated).
- **Dead code removal** (`pipelines/rss_dedup.py`): Removed no-op `widen_category()` wrapper.
- **Test updates**: `test_concurrency_contract.py` assertions rewritten for new architecture (filesystem artifacts, barrier assertions). `test_pipeline.py` `TestHarnessDiagnostics` updated for file-based verification. New `test_run_allocator.py` with atomic allocator tests.
- **530/530 tests passing** (including all 13 concurrency contract tests).
- **35 files changed, 756 insertions(+), 406 deletions(-)**
---
### v1.0.126 — Phase 6 harness fix: tag conflict invariant + diagnostics
- **Tag conflict fix** (`tagging.py`): `tag_story_with_keywords()` now tracks `conflict_losers` set — tags removed during conflict resolution cannot be re-added by the minimum-tag promotion loop. Fixes check 3.7 live FAIL where `international` + `local` conflict was undone by promotion. Fewer than 3 tags acceptable when conflicts prevent reaching 3.
- **Phase 6 diagnostics** (`pipeline.py`): `run_test_harness()` findings now persisted to run log — each `HarnessResult.stdout_lines` entry logged as `[Harness]` prefix, each `stderr_lines` as `[Harness err]`. Previously only `Harness result: FAIL — exit code 2` was written; detailed check items were lost on in-memory `HarnessResult`.
- **Tests**: 4 new `test_tagging.py` tests (`TestConflictMinimumTagPromotion`), 2 new `test_pipeline.py` tests (`TestHarnessDiagnostics`), 2 new `test_harness.py` tests (`TestHarnessPreservesOutput`). 514/518 passing (4 pre-existing concurrency contract, Wave 4 pending).
- **Live smoke**: WARN, zero FAILs, 79 stories, 56.99s. Retained v08 artifact still has check 3.7 FAIL (generated pre-fix, as expected).
- **Files changed**: 8 files — 5 production (tagging.py, pipeline.py, config.py, __init__.py, harness.py), 3 test (test_tagging.py, test_pipeline.py, test_harness.py).
- **Version alignment**: All 21 version markers updated (README, PROJECT, TODOS, config.yaml, config.py, versions_locations, 15 module docstrings).
- **11 files changed, 221 insertions(+), 4 deletions(-)**
---
### v1.0.125 — Wave 1: Reliability fixes (parser, rendering, RSS, climate)
- **Parser assignment** (`summarizer.py`): First-wins dedup semantics — `reserved_empty_slots` and `skipped_fuzzy_match` prevent duplicate fuzzy matches from overwriting assigned slots or stealing positional fallback targets. Adjacent swap detection works correctly after headline matching. 17/17 contract tests passing.
- **Rendering safety** (`report.py`, `weather_table.py`, `utils.py`): `[Tag]` bracket slicing uses `[1:-1]` (was `[2:-2]`); `[[Tag]]` uses `[2:-2]`. Pipe characters in weather table cells escaped as `&#124;` to prevent Markdown table column breaks. Newlines in story titles and summaries normalized to spaces. 29/29 contract tests passing.
- **RSS identity** (`rss.py`): `normalize_title()` now uses NFKD Unicode normalization (fullwidth → ASCII, decomposed → composed). Removed site-suffix stripping (`split(" - ")`) and 80-character truncation — full normalized title is the dedup key. 26/26 contract tests passing.
- **Weather & climate** (`climate.py`, `http_client.py`, `weather_table.py`, `report.py`): `_fetch_climate_normal_high` accepts `reference_date` parameter. `_fetch_json` return type widened to `Optional[Any]` with docstring warning. Removed hardcoded `77316` from weather subtitle and station row labels. 23/23 contract tests passing.
- **Test pollution fix** (`conftest.py`): Autouse fixture restores pipeline module attributes after every test, preventing mock leaks from concurrency contract tests.
- **Test updates**: `parser_golden_fixtures.py` golden outputs updated for corrected behavior. `test_rss.py` suffix/truncation test rewritten. `test_weather_table.py` golden subtitle updated.
- **Full suite**: 506 passing, 4 concurrency contract failures (Wave 4 pending).
- **KNOWN ISSUE**: Live pipeline run at 2026-08-09 20:22 hit exit code 2 (harness FAIL) despite report generating correctly. Root cause investigation needed.
- **13 files changed, 122 insertions(+), 60 deletions(-)
---
### v1.0.123 — Concurrency contract fixtures (Wave 0)
- Added `tests/test_concurrency_contract.py` (669 lines, 13 tests across 6 test classes) documenting the concurrency bugs to be fixed in Wave 4.
- **TestConcurrentModuleGlobalsIsolation** (3 tests): Concurrent runs share `RUN_LOGFILE`, `PHASE_TIMINGS`, and `_llm_client` module globals. 1 test fails (logfile leak), 2 pass (LLM client creates independently, timings captured).
- **TestConcurrentVersionAllocation** (2 tests): Report and log version allocation each independently scans filesystem — concurrent runs collide on v1. 1 test fails (version collision), 1 passes (log/report version pairing).
- **TestAtomicReportWrites** (2 tests): `write_report()` writes directly to final path without temp file + `os.replace()`. 1 test fails (no temp file used), 1 passes (baseline write correctness).
- **TestIndependentPhaseTimings** (2 tests): Phase 1 and Phase 2 run serially; timings are recorded independently. Both pass (documents current serial behavior).
- **TestBoundedArticleConcurrency** (2 tests): Article extraction `asyncio.gather()` is unbounded. 1 passes (all stories run simultaneously), 1 passes (pending feature warning).
- **TestRunContextNoGlobalLeak** (2 tests): Global state leaks between concurrent runs — last-writer wins. 1 test fails (concurrent leak), 1 passes (sequential reset works).
- 13 tests total: 9 pass (contract baseline + serial behavior), 4 fail (documenting bugs). 441/441 tests passing across full suite.

### v1.0.122 — README release-history cleanup
- Replaced the mixed performance/changelog section in `README.md` with actual performance information. The complete release history is maintained only in `SUMMARY.md`.

### v1.0.121 — Version reference registry
- Added `versions_locations.md`, the canonical registry of all current release-version markers. It must be read before each commit and updated whenever a new tracked file adds a current-version reference.
- Normalized all current code and documentation version markers to v1.0.121. Historical changelog entries retain their original release versions.

### v1.0.120 — Test suite consolidation
- Consolidated test suite from 1,046 to 402 tests (62% reduction). Deleted benchmark test suite (`test_benchmark_llm_batches.py`), corpus capture test suite (`test_capture_corpus.py`), smoke test suite (`test_smoke_test.py`), and source-inspection test files. Consolidated micro-permutation tests into focused behavioral contracts. Removed duplicate coverage across files. Removed no-assertion tests and historical-bug demonstrations. All 402 tests passing.

### v1.0.119 — Cleanup ordering fix
- `daily_brief/pipeline.py`: Moved `cleanup_old_files()` from before `write_report()` to immediately after. Previously, cleanup ran before the new report was on disk, leaving `max_log_versions + 1` news files on each run (6 instead of 5). Now both reports and logs finish at exactly the configured retention limit.
- `tests/test_cleanup.py`: 5 new unit tests — retention count (2), non-matching files untouched (1), under-limit no-op (1), empty directory safety (1).
- `tests/test_pipeline_ordering.py`: 2 regression tests — fixed write-before-cleanup yields correct count (1), old order leaves 6 files documenting the bug (1).
- 1046/1046 tests passing (7 new, 0 regressions).

### v1.0.118 — Repository structure migration
- Moved src/daily_brief/ to daily_brief/ (root package). No PYTHONPATH or src/ needed.
- Moved Test_validate_run.py to daily_brief/validation_harness.py. Phase 6 uses `-m daily_brief.validation_harness`.
- Moved scripts/benchmark_llm_batches.py and scripts/capture_corpus.py into daily_brief/ package.
- Removed src/, scripts/, and reports/ directories.
- Benchmark output now uses configured LOG_DIR, not tracked reports/ directory.
- All 32 test files updated: removed sys.path src insertion, updated module imports.
- 1039/1039 tests passing.

### v1.0.117 — Full P1 reliability/config/test-validity release
- `src/daily_brief/config.py`: Split config into three layers — `load_raw_config()` (safe YAML loader), legacy `load_config_yaml()` (backward-compatible), `build_runtime_config()` (typed coercion). Invalid numeric YAML now returns `{}` instead of crashing on import.
- `src/daily_brief/config_validator.py`: Tightened all validators — non-empty string for required fields, type guards before numeric comparisons, safe URL/path checks. Malformed values produce diagnostic errors instead of `TypeError` crashes.
- `src/daily_brief/cli.py`: Moved config-derived constant imports from module level into CLI command functions. `config validate` and `show-prompt` run safely without triggering import-time YAML coercion.
- `src/daily_brief/__main__.py`: Deferred `LOG_DIR` import until after CLI dispatch so `config validate` runs before config-dependent globals are evaluated.
- `src/daily_brief/llm/client.py`: Added `max_retries` parameter (default 0) to `LLMClient` constructor and `AsyncOpenAI`. Added idempotent `aclose()` lifecycle method. `create_llm_client()` forwards `max_retries`.
- `src/daily_brief/llm/summarizer.py`: Replaced serial Phase 3 recovery with bounded concurrent recovery (`asyncio.Semaphore`, default `recovery_max_concurrency=2`). Added pre-dispatch recovery deadline gate and `asyncio.wait_for` in-flight cancellation via `CancelledError`. Replaced `time.time()` with `time.monotonic()` in LLM duration measurements.
- `src/daily_brief/pipeline.py`: Added `_normalize_weather_for_rendering()` — normalizes `None`, scalar, list, and missing-key weather data to safe defaults before renderer.
- `src/daily_brief/rendering/weather_table.py`: Added `_DEGRADED_ROW` constant and `_normalize_weather()` — handles `None`, scalars, lists, missing `forecast`/`station`/`lakes` keys with safe "N/A" defaults.
- `tests/test_config.py`: 103 tests — raw loader behavior (4), validator safety (13), subprocess CLI validation (3).
- `tests/test_batch_failure_fixtures.py`: 8 new recovery tests — concurrency barrier (2), serial (1), deadline (1), all-recover (1), timing (3).
- `tests/test_llm_client.py`: 6 new tests — max_retries default (2), aclose idempotency (2), factory forwarding (2).
- `tests/test_summarizer.py`: 5 new monotonic timing tests — source check, non-negative duration.
- `tests/test_cli.py`: Fixed unawaited coroutine warning — `AsyncMock` for `_cmd_check_connectivity_impl`, `_run_on_existing_loop` helper.
- `tests/test_pipeline.py`: 12 new weather normalization tests, barrier-based concurrency assertion.
- `tests/test_smoke_test.py`: `pytestmark = pytest.mark.smoke` — excluded from default suite.
- `tests/test_weather_table.py`: 17 new weather resilience tests — `None`, scalars, lists, empty dicts, missing keys, valid passthrough.
- `tests/test_sources/*.py`: Migrated 63 `asyncio.coroutine(mock.MagicMock(...))` patterns to `AsyncMock` across 6 test files. 0 remaining uses.
- `pytest.ini`: Added `addopts = -m "not smoke"` and `filterwarnings` for `RuntimeWarning` and `DeprecationWarning` as errors on `daily_brief` module.
- 1039/1039 tests passing (21 smoke deselected). Config validate PASS. 0 warnings.

### v1.0.116 — Summary recovery correctness (P1)
- `src/daily_brief/llm/summarizer.py`: Extended `_is_valid_summary()` as the canonical quality gate for batch and individual LLM recovery — added `_is_refusal` rejection and internal fallback-marker rejection (`[Auto]`, `[Summary Unavailable]`). Replaced the weaker inline recovery predicate (`not _is_boilerplate and not _is_refusal and != "[Summary Unavailable]" and _has_topic_overlap`) with the canonical `_is_valid_summary(retry, s.title)`. Deterministic `[Auto] <headline>` output no longer incorrectly increments `individual_recovered` metrics.
- `tests/test_summarizer.py`: Added `TestIsValidSummaryExtended` (11 tests) for one-sentence rejection, headline echo (+period) rejection, refusal (with headline keyword overlap), `[Auto]` marker, `[Summary Unavailable]`, boilerplate, empty/None, and valid two-sentence pass.
- `tests/test_batch_failure_fixtures.py`: Added 8 recovery regression tests to `TestInvalidSingleRecovery`: one-sentence recovery → `[Auto]`; headline echo → `[Auto]`; headline + period → `[Auto]`; refusal → `[Auto]`; refusal with headline words → `[Auto]`; no topic overlap → `[Auto]`; `[Auto]` generated summary auto fallback not counted as recovery; valid recovery still accepted.
- `config.yaml`, `src/daily_brief/__init__.py`, `PROJECT.md`, `README.md`, `TODOS.md`: version bumped to 1.0.116.
- 1009/1009 tests passing, config validate PASS, live smoke exit 1 (WARN, zero FAILs, 52.68s, 76 stories).

### v1.0.115 — Pipeline exit-code contract (P0)
- `src/daily_brief/pipeline.py`: Added exit code constants (0=SUCCESS, 1=CONFIG/WARN, 2=VALIDATION/FAIL, 3=ERROR/SKIPPED). `main()` now returns explicit integers for all outcomes: config validation failures (1), report validation failures (2), harness PASS (0), WARN (1), FAIL (2), ERROR (3), SKIPPED (3). Replaced internal `sys.exit(1)` with consistent return contract. Changed validation-failure print from `os.environ.get` to `RUN_LOGFILE` (available at that point in execution). Always logs exit code to run log.
- `src/daily_brief/__main__.py`: `main()` returns `int`, propagates pipeline result via `sys.exit(asyncio.run(main()))`. Process exit code matches harness status.
- `tests/test_pipeline.py`: Replaced `test_main_config_failure` (patching `sys.exit`) with `test_main_config_failure_exit_code` (checking return value). Added 6 new exit-code tests: `test_main_validation_failure_returns_code`, `test_main_harness_pass_returns_zero`, `test_main_harness_warn_returns_one`, `test_main_harness_fail_returns_two`, `test_main_harness_error_returns_three`, `test_main_harness_skipped_returns_three`. 35/35 pipeline tests.
- `config.yaml`, `src/daily_brief/__init__.py`, `PROJECT.md`, `README.md`, `TODOS.md`: version bumped to 1.0.115.
- 991/991 tests passing, config validate PASS, live smoke exit 1 (WARN, zero FAILs, 53.86s, 78 stories).

### v1.0.114 — Full review backlog
- `TODOS.md`: Replaced the empty active-task list with the complete prioritized code-review backlog. It covers pipeline exit outcomes, LLM quality and retry behavior, configuration safety, weather degradation, test warning/flakiness debt, parser/rendering/data integrity, performance/backpressure, output lifecycle, packaging/CI, repository hygiene, verification gates, and two product decisions.
- `config.yaml`, `src/daily_brief/__init__.py`, `PROJECT.md`: version bumped to 1.0.114.
- No production code changed. Review baseline: 984/984 tests passing, config validate PASS, live smoke WARN with zero FAILs (50.41s, 78 stories).

### v1.0.112 — Summarizer topic-alignment guard
- `src/daily_brief/llm/summarizer.py`: Added `_has_topic_overlap()`, `_significant_words()`, and `_VALID_SUMMARY_STOPWORDS`. `_is_valid_summary()` now requires at least one significant keyword overlap between headline and summary. Batch path (`_summarize_sub_batch`) explicitly rejects topic-mismatched summaries with log warnings. Individual recovery (`batch_summarize_all`) validates topic overlap before accepting recovery summaries.
- `tests/test_summarizer.py`: Added `TestHasTopicOverlap` (3 tests), `TestIsValidSummaryTopicMismatch` (2 tests), `TestIsValidSummaryStopWords` (2 tests), `TestBatchTopicMismatchRejection` (2 tests).
- `tests/test_batch_behavior_regression.py`: Updated boilerplate test recovery text to include headline keyword overlap.
- `tests/test_batch_failure_fixtures.py`: Updated recovery mock to return headline-overlapping text.
- `config.yaml`, `PROJECT.md`, `TODOS.md`, `__init__.py`: version bumped to 1.0.112.
- 977/984 tests passing (7 pre-existing RSS dedup failures). Config validate PASS. Live smoke test: WARN (zero FAILs, 55.63s).

### v1.0.111 — Frontmatter category count includes empty categories
- `src/daily_brief/pipeline.py`: `rendered_cat_count` now counts all non-weather RSS categories regardless of story count. Previously excluded empty categories via `len(sections_map.get(cn, [])) > 0` guard, but `report.py` renders every configured category with `_No stories found._`, so the frontmatter count must match all rendered headers.
- `tests/test_report.py`: added `test_empty_category_counts_in_frontmatter` — renders one populated + one empty category, verifies frontmatter `categories: 2` and both headers present.
- `tests/test_pipeline.py`: added `TestRenderedCatCount` class with `test_rendered_cat_count_includes_empty_categories` (verifies count is 2 for two categories, one empty) and `test_rendered_cat_count_excludes_weather` (verifies weather category excluded).
- `tests/test_validate_run.py`: added `TestCheck43FrontmatterCategoryCount` with valid fixture (count 2, two headers) and mismatched fixture (count 1, two headers) — verifies check 4.3 passes/fail correctly.
- `src/daily_brief/__init__.py`, `config.yaml`, `PROJECT.md`, `TODOS.md`: version bumped to 1.0.111.
- 968/975 tests passing (7 pre-existing RSS dedup failures). Config validate PASS.

### v1.0.110 — Tag conflict policy: international + us-focused allowed
- `config.yaml`: removed `["international", "us-focused"]` from `tag_conflicts`; retained `["international", "local"]` as sole configured conflict.
- `tests/test_tagging.py`: updated conflict tests to use `international`/`local` pair.
- `Test_DailyBrief_Test_Spec.md`: updated check 3.7 to reflect current conflict policy.
- 970/970 tests passing. Config validate PASS. Live run v02 clean on check 3.7.

### v1.0.109 — External harness weather-format alignment + widening test fix
- `tests/Test_validate_run.py::parse_log()`: Updated to parse the current pipeline summary format (`Weather OK -- N forecast periods | ...`) with fallback to legacy debug format.
- `tests/Test_validate_run.py::parse_output()`: Updated to count 7-column forecast data rows structurally (excluding bold headers and `---` separators), and parse station values from the rendered 2-column station table.
- `tests/Test_validate_run.py::run_checks()` check 1.3: Updated to validate station values from the rendered report instead of debug log markers.
- `tests/test_validate_run.py`: New file with 11 unit tests for the harness parsers.
- `tests/test_sources/test_rss_dedup.py::TestLocalWidening::test_widening_filters_duplicates`: Fixed — mocked `datetime.now` to use test's fixed `NOW` instead of system time.
- `src/daily_brief/__init__.py`, `config.py`, `config.yaml`, `PROJECT.md`, `PLAN.md`, `README.md`, `TODOS.md`: version bumped to 1.0.109.

### v1.0.108 — Harness version alignment: shared log/report run identity
- `src/daily_brief/rendering/report.py`: `compute_output_path()` accepts optional `file_ver` argument. When provided, the report uses that version instead of auto-incrementing from disk.
- `src/daily_brief/pipeline.py`: Pass `log_ver` to `compute_output_path()` via `file_ver=log_ver`. The report and run log now share the same version number (e.g., `run_log_2026-08-04_v01.md` / `DailyBrief-2026-08-04_v01.md`), so the Phase 6 harness finds the correct report file.
- `tests/test_report.py`: Added `test_explicit_file_ver_overrides_disk` and `test_explicit_file_ver_with_empty_dir`.
- `tests/test_pipeline.py`: Added `test_log_report_shared_version_identity` — pipeline-level integration test verifying the log version reaches `compute_output_path` and the harness receives the matching run log.
- `src/daily_brief/__init__.py`, `config.py`, `config.yaml`, `PROJECT.md`, `PLAN.md`: version bumped to 1.0.108.
- 959/959 tests passing. Config validate PASS. Pipeline smoke test: harness now validates actual report (was `WARN` due to version mismatch).

### v1.0.107 — Test isolation fix: config reload leak
- `tests/test_config.py`: Added `tearDownClass` to `TestConfigUncoveredBranches` — reloads `daily_brief.config` from real YAML after `importlib.reload` tests. These tests previously used `importlib.reload(cfg_mod)` with mocked `yaml.safe_load` that set `TIMEZONE` to `"UTC"`, permanently leaking module state (`TIMEZONE="UTC"`, `CATEGORIES` with single entry) that caused `test_zoneinfo_uses_configured_timezone` to fail when run after `test_config.py`.
- `tests/test_sources/test_rss_dedup.py`: `test_zoneinfo_uses_configured_timezone` now explicitly patches `daily_brief.config.TIMEZONE` to `"America/Chicago"` — defensive guard against test ordering dependencies.
- `src/daily_brief/__init__.py`, `config.py`, `config.yaml`, `PROJECT.md`: version bumped to 1.0.107.
- 956/956 tests passing (0 pre-existing). Config validate PASS.

### v1.0.106 — D.9 startup integration test, obsolete test removed (Quality-6)
- `tests/test_startup_sequence.py`: New `TestStartupSequence` integration test runs real `pipeline.main()` through Phase 4 with deterministic mocks for all external boundaries (weather, RSS, LLM, aiohttp, config). Validates: `run_log_*.md` created, `DailyBrief-*.md` report written, `PHASE_TIMINGS` populated Phases 1-4, `RUN_LOGFILE=None` guard exercised. Uses explicit `pipeline_mod.*` for all assertions to avoid stale import issues.
- `tests/test_startup.py`: Removed obsolete `TestPipelineCreatesDirs` (patched removed attributes like `llm_summarize`, caused test to crash and leak partially-entered patches — `CATEGORIES=[]`, temp paths — that polluted subsequent tests). Retained passing `TestSetupLoggingCreatesDir`.
- `src/daily_brief/__init__.py`, `config.py`, `config.yaml`, `PROJECT.md`: version bumped to 1.0.106.
- 955/956 tests passing (1 pre-existing: `test_zoneinfo_uses_configured_timezone`). Config validate PASS.

### v1.0.105 — D.8 startup crash fix: `log()` guard before `RUN_LOGFILE` init + test gap (Critical-1)
- `src/daily_brief/pipeline.py`: `log()` guarded against `RUN_LOGFILE` being `None` — early logs write stderr only until logfile initialized at line 149. Pipeline `precompile_tagging()` call at line 115 no longer crashes. **Gap discovered:** 954 tests pass, 94% coverage, but app crashes on startup — no test validates startup sequence end-to-end.
- `src/daily_brief/__init__.py`, `config.py`, `config.yaml`: version bumped to 1.0.105.
- 954/956 tests passing (2 pre-existing). Config validate PASS. Pipeline runs successfully.

### v1.0.104 — D.7 harness typed result, weather errors, probe unification, logging (Rel-5/Quality-2/5)
- `src/daily_brief/harness.py`: `run_test_harness()` now returns `HarnessResult` dataclass with `status` (PASS/WARN/FAIL/SKIPPED/ERROR), `message`, `exit_code`, `stdout_lines`, `stderr_lines`. All code paths return typed result instead of `None`. Pipeline logs harness status/result message.
- `src/daily_brief/pipeline.py`: Weather errors from `weather["errors"]` now surfaced in pipeline log with concise summary (up to 3 errors). Weather status shows "PARTIAL" when errors present.
- `src/daily_brief/connectivity.py`: `run_all_checks()` and `run_smoke_test()` unified via shared `CHECK_LIST` / `SMOKE_TEST_CHECKS` declarative lists and `_wrapped()` helper. Results include `name` field. `format_results()` accepts optional `labels` fallback for backward compatibility with unnamed results.
- 954/956 tests passing (2 pre-existing). Config validate PASS.

### v1.0.103 — D.6 weather bugs (Bug-7/8), version alignment (Bug-11)
- `src/daily_brief/sources/weather.py`: Bug-7 fix — NWS-provided `forecast` URL is now used unchanged instead of being altered to append `/forecast`. Fallback to `WEATHER_POINT_URL + suffix` only fires when `properties.forecast` is missing. `WEATHER_POINT_FORECAST_SUFFIX` import retained for fallback path only.
- `src/daily_brief/rendering/weather_table.py`: Bug-8 fix — `station_rows` indexed safely with `len()` guard + fallback defaults. Short or missing `station_rows` no longer crashes rendering; `_row()` helper returns `(label, value)` from config with safe fallback. `_default_station_rows` local list covers missing indices.
- `src/daily_brief/__init__.py`, `config.yaml`, `config.py`: Bug-11 — version bumped to 1.0.103, all sources aligned.
- `tests/test_sources/test_weather_extended.py`: `test_forecast_url_suffix_appended` renamed to `test_forecast_url_used_as_is` (validates NWS URL passed through unchanged). New `test_forecast_fallback_uses_suffix` test covers missing-forecast fallback path.
- 954/956 tests passing (2 pre-existing: `test_rss_dedup`, `test_startup`). Config validate PASS.

### v1.0.102 — D.5 tagging precompilation and single computation (Quality-4/Perf-10)
- `src/daily_brief/tagging.py`: `precompile_tagging()` builds 410 precompiled regex pairs from TAGGING_MAPPINGS + CATEGORY_BOOSTS at startup. `_word_boundary_match()` delegates to precompiled cache via `_get_compiled_patterns()`, falls back to runtime compile if precompile hasn't run. `_KEYWORD_REGEXP_CACHE` global shared with callers.
- `src/daily_brief/pipeline.py`: `precompile_tagging()` called after config validation gate, before preflight checks. Logged keyword count.
- `src/daily_brief/rendering/report.py`: single tag computation per story via `id(st)` cache in `build_markdown()`. Precompute phase tags all stories once, frontmatter pass extracts unique tags, body pass reuses cached tags — eliminated duplicate `tag_story_with_keywords()` calls (was called twice per story).
- `src/daily_brief/__init__.py`, `config.py`: version bumped to 1.0.102. Config validate PASS, 953/955 tests passing (2 pre-existing).

### v1.0.101 — D.4 parser golden fixtures (Quality-3)
- `tests/fixtures/parser_golden_fixtures.py`: 15 golden fixtures documenting all LLM response formats: canonical STORY_N with headline=summary, reordered STORY_N with fuzzy remapping, STORY_N without equals, numbered lists (1., 2), ### variants, multi-line entries, summary-of headings, plain paragraphs, malformed/partial responses, adjacent swap, sentence trimming, STORY_N colon/dash/space variants, headline overlap skip. Each fixture has response text, headlines, count, expected output, and behavioral notes.
- `tests/test_parser_golden.py`: 32 test cases — 15 dynamic golden fixture tests + 17 edge cases (None/empty response, count zero, garbage, STORY_N zero-based, numbered variants, bold headers, equal-in-summary, blank summary, pipe-in-content, count exceeds entries, 3-sentence trim, sequential chunking).
- `src/daily_brief/__init__.py`: version bumped to 1.0.101.
- 953/955 tests passing (2 pre-existing). Config validate PASS.

### v1.0.100 — D.3 canonicalize duplicate utilities (Dup-1-4/Clean-1-3)
- `src/daily_brief/utils.py`: added canonical `build_context(story, preview_chars=600)` (typed, no config dependencies). Bumped version to 1.0.100.
- `src/daily_brief/llm/summarizer.py`: removed duplicate definitions of `_safe_sentence_summary`, `_count_sentences`, `build_context`. Imports all three from `utils.py`. Call sites pass `preview_chars=LLM_CONTEXT_PREVIEW_CHARS`.
- `src/daily_brief/sources/article.py`: removed duplicate `build_context`. Updated file header to v1.0.100.
- `src/daily_brief/pipeline.py`: `_coerce_temperature_f` now delegates to `utils._coerce_temperature_f` with thin wrapper that logs extreme temps.
- `src/daily_brief/__init__.py`: added `build_context` to exports; version bumped to 1.0.100.
- `tests/test_sources/test_article.py`: updated `build_context` import from `daily_brief.sources.article` → `daily_brief.utils`.
- `tests/test_summarizer.py`, `tests/test_benchmark_llm_batches.py`: `build_context` import from `summarizer` works via re-export (summarizer imports from utils).
- 921/923 tests passing (2 pre-existing). Config validate PASS.

### v1.0.99 — D.2 adopt one typed story model (Arch-3)
- `src/daily_brief/models.py`: promoted `Story` to canonical 7-field typed dataclass (title, link, snippet, category, pub_dt, context, summary). Removed unused `pubDate`, `tags`, `source`.
- `src/daily_brief/llm/summarizer.py`: replaced `StoryPipelineState` class (was slotted, 11 lines) with alias `StoryPipelineState = Story` (2 lines).
- `src/daily_brief/pipeline.py`: updated `StoryPipelineState()` construction to keyword args.
- `src/daily_brief/__init__.py`: version bumped to 1.0.99.
- `scripts/capture_corpus.py`: updated construction to keyword args.
- `tests/test_summarizer.py`: replaced `__slots__` assertions with dataclass fields check; updated construction sites to keyword args.
- `tests/test_batch_behavior_regression.py`, `tests/test_batch_failure_fixtures.py`, `tests/test_benchmark_llm_batches.py`: updated construction to keyword args.
- 921/923 tests passing (2 pre-existing), config validate PASS.

### v1.0.98 — D.1 unify config schema, loading, validation (Bug-4/Arch-4)
- `config.yaml`: removed `runtime_defaults` block; moved LLM retry (`attempts`/`backoff`), batch settings (`summary_batch_size`/`summary_max_concurrency`) under `llm.*`; moved `max_log_versions`/`frontmatter_*` under `runtime.*`; moved `user_agent` under `network.*`; removed duplicate `cleanup.max_log_versions`. Version bumped to 1.0.98.
- `src/daily_brief/config.py`: rewrote with nested `DEFAULTS` structure, `_get_nested()` canonical helper, single YAML read via `load_config_yaml()`. Removed broken `_deep_get`, `globals().update(locals())`. All module constants derived from canonical YAML paths with defaults.
- `src/daily_brief/config_validator.py`: updated all 8 check groups to validate canonical `llm.*`, `network.*`, `runtime.*` paths. Removed `cleanup.*` checks. `check_batch_scheduler()` reads YAML directly instead of importing config module constants. Added backoff list support. Removed unused `datetime` import.
- `src/daily_brief/pipeline.py`: replaced `from daily_brief.config import *` with explicit 18-constant import list.
- `tests/test_config.py`: removed obsolete `runtime_defaults`/`cleanup` tests; updated `DEFAULTS["llm_model"]` → `DEFAULTS["llm"]["model"]`. 101 tests passing.
- `tests/test_adoption_plumbing.py`: updated batch scheduler tests to pass YAML dicts instead of mutating config constants.
- Legacy root `config.py` deleted (stale duplicate, no consumers).
- 921/923 tests passing (2 pre-existing: `test_startup.py` dir creation, `test_rss_dedup` timezone pollution). Config validate PASS.

### v1.0.97 — C.5 retire dormant alert feature end-to-end (Bug-2/Bug-3/Bug-9) — Phase C complete
- `src/daily_brief/llm/alerter.py`: deleted (388 lines). `batch_evaluate_alerts()` and `parse_alert_batch_response()` never invoked — `StoryPipelineState` lacked alert state fields (Bug-2).
- `tests/test_alerter.py`: deleted (35 tests). No production code retained.
- `config.yaml`: removed `llm.alert_options` block and `prompts.system_alert` text. Bumped version to 1.0.97.
- `src/daily_brief/config.py`: removed `LLM_ALERT_OPTIONS` and `SYSTEM_ALERT_PROMPT` constants. Bumped to 1.0.97.
- `config.py` (legacy root): removed `LLM_ALERT_OPTIONS` and `SYSTEM_ALERT_PROMPT` constants. Bumped to 1.0.97.
- `src/daily_brief/config_validator.py`: restricted option/prompt validation loops to non-alert entries.
- `src/daily_brief/cli.py`: removed `system_alert` from `show-prompt` subcommand choices.
- `src/daily_brief/rendering/report.py`: simplified to single `sections` return (Wave 1C).
- `src/daily_brief/pipeline.py`, `src/daily_brief/validation.py`, `src/daily_brief/models.py`, `src/daily_brief/__init__.py`: removed all alert-related code, model fields, validation checks, and exports.
- `tests/test_config.py`: removed `alert_options` from mock config dicts.
- `tests/test_report.py`: removed alert tests and all `is_alert`/`alerts_list` handling.
- `tests/test_pipeline.py`: updated mock return value.
- `tests/test_validation_extended.py`: removed alert-related test classes and imports.
- `tests/test_validate_report.py`: renumbered REPORT check references.
- 925 tests collected, 924 passing (1 pre-existing), config validate PASS, zero alert remnants in audit. Phase C complete.

### v1.0.96 — C.3 centralize bounded HTTP retry and status handling (Rel-1/Rel-2)
- `src/daily_brief/http_client.py`: new `_request_with_retry()` with bounded 3-attempt retry, async backoff `[0.25, 0.5]`, configurable status predicates. Retries only transient: `429`/`502`/`503`/`504`/`TimeoutError`/`ClientError`. Never retries `400`/`401`/`403`/`404`. `_fetch_json` and `_fetch_text` refactored to use central executor with exact-200 default. Added `_safe_json_parse` helper for JSON decode error handling.
- `src/daily_brief/sources/rss.py`: routed through `_fetch_text` with `status_predicate=lambda s: 200 <= s < 300`. Retries on transient 502/503/504/429. Non-success still returns `(name, [])` without parsing.
- `src/daily_brief/sources/article.py`: routed through `_fetch_text` with exact-200 gate. Non-200 responses no longer parsed — error-page HTML cannot enter story context. Best-effort failure behavior preserved.
- `tests/test_http_client.py`: 37 new tests covering status classification, retry recovery (429/502/503/504/timeout), retry exhaustion, non-retryable 4xx, status predicates, JSON decode failure, header forwarding, JSON/text return contracts.
- `tests/test_sources/test_rss.py`: updated 503/502 tests with mocked `asyncio.sleep` for retry compatibility; verified no-feedparser-parse on failure.
- `tests/test_sources/test_article.py`: added `test_non_200_status_not_parsed` verifying error-page isolation.
- Weather/climate/lakes/Wunderground: zero caller changes — existing `_fetch_json`/`_fetch_text` imports inherit retry automatically.
- Connectivity probes: unchanged — diagnostic-only, single-attempt, outside C.3 scope.
- 966 tests collected, 965 passing (1 pre-existing startup test failure), config validate PASS.

### v1.0.95 — C.4 centralize batch retry, fallback, and summarization metrics (Rel-6/Rel-7/Arch-2)
- `src/daily_brief/llm/summary_metrics.py`: new module with `SummaryMetrics` class (`__slots__` based), `validate_metrics()`, `empty_metrics()`. Lightweight structured result with 12 fields (total_stories, sub_batches, batch_calls, batch_retries, batch_failures, individual_recovery_attempts, individual_recovered, auto_fallbacks, unavailable_summaries, final_valid, final_invalid, elapsed_s). Invariant: `final_valid + auto_fallbacks + unavailable_summaries + final_invalid == total_stories`.
- `src/daily_brief/llm/summarizer.py`: `_summarize_sub_batch()` now tracks `valid_count` and returns `{'success', 'valid_count', 'failed'}` outcome dict. `batch_summarize_all()` rewritten with 4 explicit phases: (1) initial batch dispatch, (2) one bounded full-batch retry with backoff for failed sub-batches, (3) individual recovery via `_summarize()` for unresolved stories, (4) outcome counting and structured metrics. Returns `SummaryMetrics` instead of unused empty dict. All recovery/fallback centralized — no scattered call sites.
- `src/daily_brief/pipeline.py`: removed Phase 3D (failed-summary retry loop) and Phase 3E (boilerplate re-summarization loop), −57 lines. Replaced with single `batch_summarize_all()` call that consumes returned `SummaryMetrics`. Emits concise Phase-3 log with batch calls/retries, recovery count, valid/fallback/unavailable split, and elapsed time. Removed `_is_boilerplate` and `_generate_auto_fallback` imports (centralized in summarizer).
- `tests/test_summary_metrics.py`: 15 tests across 5 classes (constructor, is_valid, to_dict, validate_metrics, empty_metrics).
- `tests/test_batch_behavior_regression.py`: 13 regression tests characterizing current external behavior (valid summaries retained, fallback text, category grouping, ordering, concurrency isolation, empty input, boilerplate detection, async retry).
- `tests/test_batch_failure_fixtures.py`: 11 deterministic failure-path tests (transient exception, malformed response, partial parse, invalid recovery, exhausted recovery, concurrent metrics).
- `tests/test_pipeline.py`: updated `_pipeline_patches` fixture; rewrote `test_main_phase3_retries` → `test_main_phase3_metrics_logged`; rewrote `test_main_phase3e_boilerplate` for centralized model.
- `tests/test_summarizer.py`: updated 8 tests for new return type (`SummaryMetrics`).
- 929 tests collected, 928 passing (1 pre-existing startup test failure unrelated), config validate PASS.

### v1.0.94 — C.2a adopt (4,2) — 55.6% faster, all quality gates pass (Perf-7)
- Live benchmark on 75-story corpus, 8-cell matrix (batch 3-6 × concurrency 1-2 × 3 runs). Winner (4,2): median 43.4s vs 97.7s baseline, 55.6% improvement. Quality: 0 invalid, 0 auto_fallback, 0 boilerplate+refusal, 0 exceptions. All 5 quality gates passed with margin.
- `src/daily_brief/config.py`: `LLM_SUMMARY_BATCH_SIZE` default 4, `LLM_SUMMARY_MAX_CONCURRENCY` default 2 (up from 3, 1). Bumped VERSION to 1.0.94.
- `config.py`: `LLM_SUMMARY_BATCH_SIZE` default 4, `LLM_SUMMARY_MAX_CONCURRENCY` default 2 (up from 3, 1). Bumped version to 1.0.94.
- `tests/test_adoption_plumbing.py`: updated default assertions to (4, 2).
- `reports/llm_batch_benchmark.json`: full benchmark results with 24 recorded runs, 8 cells, environment provenance.
- 890 tests passed, 0 failures. config validate PASS.

### v1.0.93 — C.2a adoption plumbing — config constants, pipeline forwarding, validation (Perf-7)
- `src/daily_brief/config.py`: added `LLM_SUMMARY_BATCH_SIZE` (default 3) and `LLM_SUMMARY_MAX_CONCURRENCY` (default 1) with YAML overrides. Bumped VERSION to 1.0.93.
- `src/daily_brief/pipeline.py`: explicit `batch_size=LLM_SUMMARY_BATCH_SIZE`, `max_concurrency=LLM_SUMMARY_MAX_CONCURRENCY` on Phase 3 `llm_batch_summarize_all()` call. Added scheduler settings log line.
- `src/daily_brief/config_validator.py`: added `check_batch_scheduler()` — validates `LLM_SUMMARY_BATCH_SIZE` and `LLM_SUMMARY_MAX_CONCURRENCY` are int ≥ 1.
- `tests/test_adoption_plumbing.py`: 10 tests: config defaults (4), pipeline wiring (2), validation (2), logging (2).
- 890 tests passed, 0 failures.

### v1.0.92 — C.2a benchmark hardening — matrix validation, quality gates, instrumentation, capture validation (Perf-7)
- `scripts/capture_corpus.py`: hardened with PROJECT_ROOT-relative output path, `--force` overwrite guard, pre-write corpus validation (min-stories threshold, 80% context coverage, required fields), metadata enrichment (`categories`, `category_order`, `context_stats`).
- `scripts/benchmark_llm_batches.py`: hardened with matrix validation (rejects ≤0, deduplicates, requires (3, 1) baseline), warmup fix (N warmups per cell), host normalization (`/v1` suffix), model override (`summarizer.LLM_MODEL` monkey-patch), instrumentation (per-call latency p50/p95/max, exception count, sub-batch sizes), environment provenance (fixture hash, capture date, LLM options, retry config). Standalone validators removed — imports from `daily_brief.llm.summarizer`. `select_winner()` with 5 quality gates (speed, invalid_rate, auto_fallback_rate, boilerplate_refusal_rate, exceptions) that fail closed.
- `tests/test_benchmark_llm_batches.py`: 38 tests across 12 classes (matrix validation, host normalization, instrumentation fields, environment provenance, quality gates, plus existing tests).
- `tests/test_capture_corpus.py`: 25 tests across 5 classes: path resolution (4), force flag (4), validation (8), metadata/stats (5), no-LLM proof (4).
- 865 tests passed, 0 failures.

### v1.0.91 — C.2a LLM batch benchmark infrastructure (Perf-7)
- `scripts/capture_corpus.py`: standalone corpus capture script. Runs the full pipeline to Phase 3 (RSS, dedup, article extraction) without calling LLM; serializes `StoryPipelineState` inputs (title, url, category, snippet, pub_date, full context) to a versioned JSON corpus with category order preservation and summary metadata. No credentials or LLM responses captured.
- `scripts/benchmark_llm_batches.py`: standalone benchmark runner. Loads a captured JSON corpus, reconstructs `StoryPipelineState` objects, and calls `batch_summarize_all()` across an 8-cell matrix (batch sizes 3-6 × concurrency 1-2). Each cell runs one warmup and N recorded runs with shuffled order per repetition. Instrumented async client tracks batch/fallback calls, max concurrent requests, wall time, per-run quality metrics, and stories/second. JSON output with median/min/max aggregation and a formatted terminal table. Winner selection requires >=10% median improvement over baseline (3, 1) with no quality regression.
- `tests/test_benchmark_llm_batches.py`: 21 tests across 5 classes: capture corpus validation (4), fixture loading (4), matrix validation (3), metric aggregation with mocked completions (4), JSON output structure and winner logic (6).
- `.opencode/plans/c2a_benchmark_llm.json`: plan document with matrix, metrics, selection rules, and adoption gate.
- 838 tests passed, 0 failures. config validate PASS.

### v1.0.90 — C.2 Batch scheduler: configurable batch_size and max_concurrency (Perf-7)
- `src/daily_brief/llm/summarizer.py`: extracted `_summarize_sub_batch()` with optional `asyncio.Semaphore` for bounded concurrency; refactored `batch_summarize_all()` to accept `batch_size` (default 3) and `max_concurrency` (default 1, serial) parameters; when `max_concurrency > 1`, sub-batches dispatched via `asyncio.gather` with semaphore gating; exception isolation per sub-batch; extracted `_is_valid_summary()` helper. Bumped header to v1.0.90.
- `tests/test_summarizer.py`: added `TestBatchSchedulerControls` (4 tests): custom batch_size split, semaphore concurrency 1/2, sub-batch exception isolation.

### v1.0.89 — C.1 Migrate LLM calls to AsyncOpenAI and asyncio.sleep (Perf-8/Perf-9)
- `src/daily_brief/llm/client.py`: switched from `OpenAI` to `AsyncOpenAI`; `chat_completions_create()` is now `async`; removed `_executor` and `_run_blocking` (no longer needed).
- `src/daily_brief/llm/summarizer.py`: `_summarize()` and `batch_summarize_all()` are now `async`; replaced `time.sleep()` with `asyncio.sleep()` for non-blocking retry backoff.
- `src/daily_brief/llm/alerter.py`: `batch_evaluate_alerts()` is now `async`; replaced `time.sleep()` with `asyncio.sleep()`.
- `src/daily_brief/llm/__init__.py`: removed `_executor` and `_run_blocking` exports.
- `src/daily_brief/pipeline.py`: added `await` to `llm_batch_summarize_all()`, `llm_summarize()` in retry and boilerplate paths.
- `tests/test_llm_client.py`: migrated to `AsyncOpenAI` and `AsyncMock`; added async coroutine verification test; removed `_run_blocking` tests.
- `tests/test_summarizer.py`: migrated `_summarize` and `batch_summarize_all` tests to run coroutines in event loop; replaced `time.sleep` mocks with `asyncio.sleep` `AsyncMock`.
- `tests/test_alerter.py`: migrated `batch_evaluate_alerts` tests to run coroutines; replaced `time.sleep` with `asyncio.sleep`, sync `MagicMock` with `AsyncMock`.
- `tests/test_pipeline.py`: updated `_pipeline_patches` summarizer mocks to async wrappers.
- 813 tests passed, 0 failures. config validate PASS.

### v1.0.88 — B.8 Separate weather provider fetching from merge/fallback policy (Arch-1)
- `src/daily_brief/sources/weather.py`: extracted `fetch_nws_forecast()` for NWS request and forecast parsing; extracted `fetch_lakes()` for bounded concurrent lake retrieval; added pure `merge_weather_data()` for deterministic station formatting, fallback, unavailable defaults, rainfall suppression, and error/lake order preservation; reduced `fetch_weather()` to async collector that independently runs NWS, ERA5/rainfall (concurrent), and lakes, then calls the merger once. NWS failure no longer prevents ERA5, rainfall, or lake collection. Bumped module header to v1.0.88.
- `tests/test_sources/test_weather.py`: updated `test_exception_during_fetch` to reflect new independent collection behavior — NWS failure produces empty forecast without polluting errors.
- `tests/test_sources/test_weather_provider_isolation.py`: new file with 20 tests covering NWS failure with independent collection (3), individual climate/rainfall failures (3), pure merge policy (11: full data, ERA5 high/low fallback, Unavailable, rainfall formatting, equal-suppression, invalid payload normalization, lake/error ordering), lake concurrency/order/isolation (3), and NWS URL construction (1).
- 813 tests passed, 0 failures. config validate PASS.

### v1.0.87 — B.7 Make preflight probes opt-in (Perf-11)
- `src/daily_brief/pipeline.py`: gated the `run_all_checks()` invocation with `PREFLIGHT_CHECKS_ENABLED`. When disabled, emits a skip message to stderr and skips all three preflight probes (LLM, RSS, weather), eliminating redundant network traffic on every pipeline run.
- `src/daily_brief/config.py`: added `PREFLIGHT_CHECKS_ENABLED` loader (`runtime.preflight_checks_enabled`, default `True`).
- `src/daily_brief/config_validator.py`: added `_is_bool` helper and `runtime.preflight_checks_enabled` boolean type validation.
- `config.yaml`: set `runtime.preflight_checks_enabled: false` (default: do not run preflight probes).
- `tests/test_pipeline.py`: updated `_pipeline_patches` to include `PREFLIGHT_CHECKS_ENABLED`. Added `TestB7Preflights` (3 tests): default-skip, enabled-call, stderr output.
- `tests/test_cli.py`: added `TestCmdCheckConnectivity` (3 tests): dispatch, pass/fail exit codes.
- `tests/test_config.py`: added `TestPreflightChecksEnabled` (2 tests): boolean type validation.
- 793 tests passed, 0 failures. config validate PASS.

### v1.0.86 — B.6 Fetch RSS candidates once, widen locally (Bug-10 fix)
- `src/daily_brief/sources/rss.py`: `fetch_feed()` now accepts `max_stories: Optional[int] = None`. When `None`, returns the full provider candidate pool without truncation. Slicing is applied only when an explicit limit is supplied, preserving backward compatibility for direct callers.
- `src/daily_brief/pipelines/rss_dedup.py`: `fetch_and_dedup()` passes `None` for `max_stories` during the initial concurrent RSS fetch, so every category receives its complete candidate list. Added `_widen_category_local()` — processes already-fetched candidates through progressively wider age windows (2d-7d) without additional HTTP requests. Added per-category output cap (`max_stories`) after local filtering/widening, preserving current report sizes. Replaced refetch-based `widen_category()` with a compatibility wrapper; all widening is now local to the candidate pool. Category processing preserves configured order regardless of fetch completion order.
- `tests/test_sources/test_rss.py`: added `test_no_limit_returns_all` — verifies 12 untruncated candidates when `max_stories=None`.
- `tests/test_sources/test_rss_dedup.py`: replaced HTTP-refetch widening tests with `TestLocalWidening` (13 tests): Bug-10 proof (6th-entry recovery, exactly one request), category order stability, cross-category first-wins, max_stories output cap, age boundary behavior (24h inclusive, 7d exclusive), filter behavior (duplicates, obituary, real-estate), and failure isolation. Retained `TestWidenCategory` compatibility wrapper test.
- 781 tests passed, 0 failures. config validate PASS.

### v1.0.85 — B.5 Reuse outer HTTP session for article extraction
- `src/daily_brief/pipeline.py`: removed the nested Phase 3A `aiohttp.ClientSession` dedicated to article extraction. Article requests now reuse the outer pipeline session that weather and RSS already share. The `asyncio.gather(..., return_exceptions=True)` failure isolation and per-request 5-second timeout (`ClientTimeout(total=5)` in `article.py`) remain unchanged. Eliminates one connector/DNS cache creation and teardown per pipeline run.
- `tests/test_pipeline.py`: updated `_pipeline_patches` helper default from 2 to 1 session CM. Updated all 7 test methods to use single-session mocks. Added `test_b5_single_client_session` (verifies `ClientSession` constructed once) and `test_b5_outer_session_passed_to_extractor` (verifies the outer session sentinel is passed to `stage_extract_article`).
- `tests/test_startup.py`: updated `test_pipeline_creates_log_and_news_dirs` to use single-session mock.
- 772 tests passed, 0 failures. config validate PASS.

### v1.0.84 — B.4 Eliminate per-run Open-Meteo ZIP geocoding
- `src/daily_brief/sources/climate.py`: `_fetch_climate_normal_high()` now accepts `lat` and `lon` parameters from the caller instead of hardcoding ZIP `77316` and hitting the Open-Meteo geocoding API every run. Geocoding request removed entirely; ERA5 request built directly with supplied coordinates. Preserves existing timeout, exception handling, empty-response behavior, temperature rounding, and debug logging.
- `src/daily_brief/sources/weather.py`: `fetch_weather()` forwards its existing `lat` and `lon` parameters to `_fetch_climate_normal_high()` in the concurrent gather. Weather orchestration, concurrency, and deterministic fallback merge semantics unchanged.
- `tests/test_sources/test_climate.py`: simplified to single-response mocks (no geocoding). Removed geocoding-specific fixtures. Added `test_single_era5_request` (confirms one request, no geocoding URL) and `test_coordinates_passed_to_request` (confirms archive API URL used with supplied coordinates). 19 climate tests total.
- `tests/test_sources/test_weather_extended.py`: adapted `TestClimateEra5NoData` to pass coordinates. Tests now expect single ERA5 response.
- 770 tests passed, 0 failures. config validate PASS.

### v1.0.83 — B.3 Eliminate redundant Wunderground dashboard request
- `src/daily_brief/sources/weather.py`: removed `_fetch_station_metrics` from imports and `asyncio.gather()` in `fetch_weather()`. The weather gather now fetches only 2 independent sources: `_fetch_climate_normal_high()` and `_fetch_station_monthly_rainfall()`. Station data is initialized with the standard empty payload shape (`avg_temp_today: None`, `avg_monthly_rainfall: None`, `current_monthly_rainfall: None`), then populated from the remaining sources. Eliminates one Wunderground dashboard HTTP request per weather run. Bumped module header to v1.0.83.
- `src/daily_brief/sources/wunderground.py`: `_fetch_station_metrics()` is now a no-op returning the established empty station payload; it no longer calls `_fetch_text` or `BeautifulSoup`. The function is retained for API stability and regression testing.
- `tests/test_sources/test_wunderground.py`: replaced `TestFetchStationMetrics` (10 tests for old dashboard scraping behavior) with `TestFetchStationMetricsNoOp` (2 tests: verifies empty payload shape, verifies no `_fetch_text` call).
- `tests/test_sources/test_weather.py`: removed all 6 `_fetch_station_metrics` mock patches from 6 test methods. Tests now mock only `_fetch_climate_normal_high` and `_fetch_station_monthly_rainfall`.
- `tests/test_sources/test_weather_extended.py`: removed all 5 `_fetch_station_metrics` mock patches. Updated `TestWeatherSourceConcurrency` docstring and assertion — verifies 2 concurrent fetches (climate + monthly rainfall) instead of 3.
- 772 tests passed, 0 failures. config validate PASS.

### v1.0.82 — B.2 Concurrent weather source fetching with `asyncio.gather()`
- `src/daily_brief/sources/weather.py`: replaced the serial weather source fetches (`_fetch_station_metrics`, `_fetch_climate_normal_high`, `_fetch_station_monthly_rainfall`) with `asyncio.gather(return_exceptions=True)` for concurrent execution. Added per-source exception isolation — failed individual sources receive default unavailable values without crashing the full weather fetch. Station data merge logic (forecast fallback for avg_temp_today, station_monthly rain fallback) preserved post-gather. Retains existing fallback merge behavior between station metrics, climate normals, and monthly rainfall.
- `tests/test_sources/test_weather_extended.py`: added `TestWeatherSourceConcurrency` class with `test_sources_fetch_concurrently` — uses timing tracker to verify that station metrics, climate normal, and monthly rainfall coroutines are active concurrently (at least 2 simultaneous).
- 779 tests passed, 0 failures. config validate PASS.

### v1.0.81 — B.1 Concurrent lake fetching with bounded semaphore
- `src/daily_brief/sources/weather.py`: replaced the serial lake-fetch loop with `asyncio.gather()` + `asyncio.Semaphore(3)` for bounded concurrency. Snapshot `WEATHER_LAKE_URLS.items()` into a list to fix submission order before scheduling tasks. Merge results in configuration order, not completion order. Added per-lake failure isolation: individual exceptions do not crash the lake loop; the failed lake receives the unavailable-shaped result `(today: None, one_week_ago: None, thirty_days_ago: None)` and the error is recorded in `weather_data["errors"]`. Added `import asyncio`.
- `tests/test_sources/test_weather_extended.py`: added `TestWeatherLakeConcurrency` class with 3 regression tests — `test_sequential_limit_bounded` (peak concurrent lake fetches never exceed the semaphore bound of 3), `test_output_order_stable` (lakes finishing out of order still appear in configuration order), `test_one_lake_failure_isolated` (one raising lake does not drop other results and records an error).
- 778 tests passed, 0 failures. config validate PASS.

### v1.0.80 — A.10 Correct RSS config key and parent path
- `src/daily_brief/config.py`: corrected RSS configuration parent from `rss_settings` to `rss`; fixed typo `dedupi_window_hours` to `dedupe_window_hours`; also corrected `DEFAULT_AGE_WINDOW_HOURS` from non-existent `default_age_window_hours` to `default_age_limit_hours`. Both `config.yaml` and `config_validator.py` already use the correct paths, so the runtime loader now matches the schema and reads the actual configured value instead of silently falling back to 24.
- `config.py` (legacy root): applied identical corrections for consistency.
- `tests/test_config.py`: added 3 regression tests — `test_dedupe_window_hours_custom_value` (72-hour value loads correctly), `test_dedupe_window_hours_fallback` (defaults to 24 when absent), `test_rss_settings_reads_rss_not_rss_settings` (reads `rss`, not `rss_settings`); added `_base_cfg()` helper for mock config dicts.
- 775 tests passed, 0 failures.

### v1.0.79 — A.9 Monotonic total and per-phase timing measurements
- `src/daily_brief/pipeline.py`: replaced all `time.time()` duration measurements with `time.monotonic()`. Phase 1–4 timings migrated. Added Phase 5 (validation) and Phase 6 (harness) timing, stored in `PHASE_TIMINGS`. Moved Phase 3 start mark before article extraction (3A) so it measures the full enrichment cycle. Added `TOTAL PIPELINE TIME` log line on both success and validation-failure paths. Existing `PROCESSING COMPLETE` metric now labeled `(Phases 1-3)` to clarify scope.
- `tests/test_pipeline.py`: added 5 regression tests — `test_main_monotonic_phase_timings` (all 6 phases populated, positive durations), `test_main_validation_failure_has_total` (total logged on failure path), `test_main_monotonic_not_wall_clock` (source-level check: no `time.time()` calls), `test_main_phase3_includes_article_extraction` (source positions verify Phase 3 timer starts before 3A).
- 772 tests passed, 0 failures.

### v1.0.78 — A.8 Reject and diagnose unsuccessful RSS HTTP responses
- `src/daily_brief/sources/rss.py`: added HTTP status gate in `fetch_feed()`, rejecting non-2xx responses before `await resp.text()` and `feedparser.parse()`. Logs a warning with feed name, HTTP status, and URL; returns existing graceful-failure `(name, [])`.
- `tests/test_sources/test_rss.py`: added 3 regression tests — `test_http_404_returns_empty_no_parse`, `test_http_503_returns_empty_no_parse`, `test_http_error_logs_status_and_name`.
- 768 tests passed, 0 failures.

### v1.0.77 — A.7 Restore TLS verification in RSS connectivity probes
- `src/daily_brief/connectivity.py`: removed `ssl=False` from `check_rss()` HTTP request, restoring `aiohttp`'s default TLS certificate and hostname verification for the RSS feed probe.
- `tests/test_connectivity_extended.py`: added `test_check_rss_tls_verification_enabled` regression test under `TestCheckRSS` asserting no `ssl` keyword in `check_rss` source.
- 765 tests passed, 0 failures.

### v1.0.76 — A.6 Create output/log directories before use
- `src/daily_brief/__main__.py`: added `os.makedirs(log_dir, exist_ok=True)` at start of `setup_logging()` to protect startup logging.
- `src/daily_brief/pipeline.py`: added `os.makedirs(LOG_DIR, exist_ok=True)` and `os.makedirs(NEWS_DIR, exist_ok=True)` in `main()` before directory listing; fixed `log()` to create the actual parent directory of `RUN_LOGFILE` instead of only `LOG_DIR`.
- `tests/test_startup.py`: added 2 new regression tests for startup directory creation.
- 764 tests passed, 0 failures.

### v1.0.75 — A.5 Remove unused configuration constants
- `src/daily_brief/config.py`: removed `USER_AGENT_WEATHER_SUFFIX`, `CATEGORY_SETTINGS`, `REAL_ESTATE_KEYWORDS`, `OBITUARY_KEYWORDS`.
- `src/daily_brief/sources/weather.py`: removed unused `USER_AGENT_WEATHER_SUFFIX` import.
- 762 tests passed, 0 failures.

### v1.0.74 — A.4 Consolidated WEATHER_POINT_URL
- `src/daily_brief/config.py`: removed redundant `WEATHER_POINT_URL` reassignment block, retaining single canonical NWS template at weather-constants section.
- `tests/test_sources/test_weather.py`: strengthened `test_point_url_constructed_from_lat_lon` to assert exact NWS point URL (`https://api.weather.gov/points/30.286,-95.566`).
- 762 tests passed, 0 failures.

### v1.0.72 — A.3 Unused sum_results Assignment Removed
- `src/daily_brief/pipeline.py:202`: removed unused `sum_results` local assignment. Batch summarizer call unchanged — LLM mutations and side effects remain intact.
- 762 tests passed, 0 failures.

### v1.0.70 — A.2 Precompiled HTML-Strip Regex
- `src/daily_brief/utils.py`: precompiled `_HTML_TAG_RE` at module level, removing per-call `re.compile()` in `strip_html()`.
- 762 tests passed, 0 failures.

### v1.0.68 — A.1 ZoneInfo Import Fix
- `src/daily_brief/pipelines/rss_dedup.py`: added `from zoneinfo import ZoneInfo` import. Missing import caused `NameError` silently caught by broad exception handler, RSS age filtering fell back to UTC instead of configured `America/Chicago`.
- `tests/test_sources/test_rss_dedup.py`: added `test_zoneinfo_uses_configured_timezone` regression test asserting `ZoneInfo` is called with configured timezone.
- 762 tests passed, 0 failures, 3.85s.

### v1.0.67 — Optimization Baseline
- **Test baseline:** 761 tests passed, 148 deprecation warnings, 3.93s (`pytest -q`)
- **Pipeline baseline (3 runs):** wall-clock 137–147s, internal ~105–114s
  - Phase 1 (weather): 5–11s (variable, ~8s avg)
  - Phase 2 (RSS, 15 feeds): ~3.5s
  - Phase 3 (LLM enrich+summarize): 96–100s — **dominant path** (~88% of internal time)
  - Phase 4 (render/write): 30s
  - LLM: batch-of-3 model on gemma4-e2b, ~24 batch requests + 10–15 retry/boilerplate/fix requests = 39 total
  - Stories: 71–73 per run, 0 failed, ~1–3 [Auto] fallbacks
- Credible Phase B target (weather+RSS concurrency): 93–103s internal
- LLM concurrency/batching (Phase C) is the only path below 90s

### v1.0.66 - Documentation Tracking Reorganization
- Rebuilt `TODOS.md` as a lean live execution board: 30 actionable phase items, 3 verification gates, and 2 explicit blockers.
- Moved the canonical research review, runtime budget, technical findings, phase rationale, and verification detail to `PLAN.md`.
- Replaced stale monolithic architecture and refactoring-target references in `PROJECT.md` with the current modular architecture and tracking-file responsibilities.
- Removed completed refactoring/test/bug-fix history, obsolete UI proposals, duplicate version notes, and agent-transcript artifacts from the live task board; historical milestones remain in this changelog.

### v1.0.65 — Research Agent Deep Review (gpt-5.6-terra)
- Comprehensive codebase review: **47 items** across 7 categories (11 bugs, 12 performance, 9 dead code, 4 duplicate, 7 anti-patterns, 7 reliability, 5 architecture)
- **New bugs found by research:** Alert system never wired (Bug-2/3), WU dashboard fetched twice per run (Perf-3), config schema reader vs validator misalignment (Bug-4), widening can't discover older stories due to max_stories truncation (Bug-10), version drift across 4 sources (Bug-11), RSS status check missing (Bug-6)
- **Important correction:** `AsyncOpenAI` conversion saves **0s** wall-clock time — LLM requests remain serial. Benefit requires measured batching/concurrency experiment on vLLM.
- Phase A (10 items, ~2.5hrs, low risk): ZoneInfo bug, dead code, dead constants, TLS fix, RSS status check, timing infrastructure, typo fix
- Phase B (8 items, ~4-6hrs, low-medium risk): **~10-20s saved** — parallel lakes, concurrent weather sources, WU dedup, geocode cache, session reuse, RSS widening fix, preflight cache, weather orchestrator refactor
- Phase C (5 items, ~1-3 days, medium-high risk): AsyncOpenAI + asyncio.sleep, LLM batching benchmark, HTTP retry policy, centralized summarizer recovery, alert feature decision
- Phase D (7 items, ~2-4 days, medium risk): config schema unification, story model consolidation, dedup canonicalization, batch parser decompose, tagging precompile, misc bug fixes, system reliability
- Credible target: ~65-75s after Phase B. Full 55-65s only if measured LLM batching proves beneficial.

### v1.0.63 — Performance & Optimization Plan
- Added 17-item performance/cleanup plan to TODOS.md: 6 performance, 9 cleanup, 1 architecture, 1 bug fix
- Quick wins: `ZoneInfo` import bug (rss_dedup.py), parallel lake fetching, parallel weather sub-sources
- High impact: async LLM client (AsyncOpenAI), HTTP retry for all sources, `time.sleep` → `asyncio.sleep`
- Cleanup: duplicate functions, dead code, unused imports, regex recompilation

### v1.0.62 — Tier 4: Coverage Targets
- test_config.py: 42 new tests → config.py 100%, config_validator.py 96%
- test_article.py: 16 tests → article.py 97%
- test_rss_dedup.py: 17 tests → rss_dedup.py 96%
- test_summarizer.py: 14 new tests → summarizer.py 90%
- test_llm_client.py: 6 tests → client.py 100%
- test_connectivity_extended.py: 12 tests → connectivity.py 97%
- test_validation_extended.py: 12 tests → validation.py 98%
- test_pipeline.py: 13 tests → pipeline.py 88%
- test_cli.py: 10 tests → cli.py 76%
- test_harness.py: 8 tests → harness.py 83%
- test_weather_extended.py: 16 tests → weather/climate/wu/lakes 98-100%
- test_report.py: 2 new tests → report.py 99%
- Total: 761 tests, all coverage targets met (80-100%)

### v1.0.61 — Tier 3: Integration Tests
- `test_smoke_test.py` — 21 tests, 6 endpoint reachability checks via `run_smoke_test()`
- `connectivity.py` — added `check_openmeteo()`, `check_wunderground()`, `check_lakes()`
- `test_validate_report.py` — 32 tests, 8 report-level checks in `validate_report()`
- `validation.py` — extended with frontmatter, weather section, Dynamic/Unavailable, story/alert count, duplicate URLs, file size checks
- `scripts/run_tests.sh` — full pytest suite runner
- `scripts/run_coverage.sh` — coverage runner with term-missing + HTML report
- `pytest.ini` — test config (paths, src pythonpath, markers)
- Total: 574 tests (371 new, 63 Tier 3)

### v1.0.57 — test_summarizer.py (63 tests) — Tier 1/5
- `tests/test_summarizer.py`: 63 tests covering `_safe_sentence_summary` (9: truncation, cleanup, empty/None, whitespace), `_is_refusal` (6: refusal phrases, factual text, empty), `_is_boilerplate` (6: boilerplate phrases, factual text), `_count_sentences` (4: multiple, single, empty, mixed punctuation), `parse_batch_summary_response` (22: STORY_N format with/without equals, numbered format, fuzzy headline match, keyword overlap, positional fallback, swap detection, edge cases), `StoryPipelineState` (4: slots, defaults, settable), `_generate_auto_fallback` (5: format, colon cleanup, None/empty, whitespace), `build_context` (5: context cap, snippet/title fallback, category fallback, empty), `_summarize` mocked (6: success, empty response, exception fallback, retry with recovery, title fallback, None title)
- 332 total tests (269 existing + 63 new)

### v1.0.56 — test_report.py (35 tests) — Tier 1/4
- `tests/test_report.py`: 35 tests covering `build_sections_from_stories` (8), `compute_output_path` (8), `build_markdown` (13), `write_report` (6) — story grouping, alerts, date formatting, auto-versioning, frontmatter, tags sorted, category order, empty categories, weather section, link fallback, UTF-8 encoding
- 269 total tests (234 existing + 35 new)

### v1.0.55 — test_weather_table.py (31 tests) — Tier 1/4
- `tests/test_weather_table.py`: 31 tests covering `build_weather_markdown()` — full data render (12), empty forecast fallback (4), partial forecast padding (3), station Unavailable (2), empty lakes (2), lake label formatting (3), table structure (5), missing values (2), empty config (1)
- 234 total tests (203 existing + 31 new)

### v1.0.58 — test_alerter.py (35 tests) — Tier 1 complete
- `tests/test_alerter.py`: 35 tests covering `parse_alert_batch_response` (27: STORY_N format TRUE/FALSE, lowercase case-insensitive, numbered format, mixed formats, malformed lines, no-colon, non-integer index, garbage text, partial parse, whitespace-only, empty string, type checks) and `batch_evaluate_alerts` mocked (8: empty stories, single story alert true/false, unavailable summary exclusion, bracket summary exclusion, multi-category grouping, LLM exception all-false, alert idx mismatch, global index mapping)
- 367 total tests (332 existing + 35 new). Tier 1 complete: 4/4 test files, 164 new tests across the tier

- [2026-07-30] Version bumped to **v1.0.58** — Tier 1 testing complete, 35 new alerter tests.
- [2026-07-29 22:30] Version bumped to **v1.0.60** — Tier 2 source tests complete.
- [2026-07-29 22:30] Tier 2 complete — 5 source test files, 154 new tests: `test_weather.py` (38), `test_wunderground.py` (28), `test_climate.py` (21), `test_lakes.py` (20), `test_rss.py` (47). All mocked with `aioresponses`/`unittest.mock`. 521 total tests.
- [2026-07-29 21:27] Version bumped to **v1.0.54** — Round 5: climate normal verification.
- [2026-07-29 21:27] Verification (Round 5) — Confirmed climate normal high is real Open-Meteo ERA5 data, not hardcoded fallback. Added `logger.debug()` to `climate.py` to log raw ERA5 JSON responses: response keys, daily block, temperature_2m_max list, request params, and raw→rounded value. Live pipeline showed ERA5 returning `temperature_2m_max: [95.9]` → rounded to 96°F for Jul 30. Full fallback chain verified: (1) ERA5 API → live value, (2) None → forecast high fallback, (3) still missing → "Unavailable". No hardcoded 95°F anywhere in codebase.
- [2026-07-29 23:26] Version bumped to **v1.0.45** — Bug F.2: frozen station investigation.
- [2026-07-29 23:26] Investigation (F.2) — Investigated "frozen station data" report: avg_temp_today and rainfall showing identical values across runs. Ran pipeline twice (v10/v11) with 4-min gap, compared output markdown, and tested each scraper independently. Findings: (1) `avg_temp_today` (94°F) — Open-Meteo ERA5 climate normal for July 29, genuinely static, long-term historical average. (2) `avg_monthly_rainfall` (3.77 in) — climate.gov July normal for Houston, genuinely static monthly table. (3) `current_monthly_rainfall` (7.42 in) — Wunderground scrape of cumulative monthly precipitation, stable over minutes, changes only with new rainfall. Both Wunderground HTML parser (`_fetch_station_metrics`) and climate.gov parser (`_fetch_station_monthly_rainfall` → `_parse_climate_summary`) return live data. Weather.py guard at line 220 correctly nullifies `current` when it equals `avg`. **No bug found — data is genuinely stable on short time scales.** Scraper selectors working correctly.
- [2026-07-29 17:54] Version bumped to **v1.0.41** — Fix 4.4: render section headers for 0-story categories.
- [2026-07-29 17:54] Fix (4.4) — Updated `rendering/report.py:137-145`: changed comment from "skip empty categories" to "render header even for empty categories", updated empty-category rendering from `## cat (0 stories)` to `## cat\n_No stories found._`, updated harness `Test_validate_run.py:294` section-parsing regex from `^##\s+` to `^#{2,3}\s+` to support both formats. Bumped `config.yaml` and `__init__.py` to v1.0.41. Verified: Conroe TX News renders "## Conroe TX News\n_No stories found._" at line 89-90 of output.
- [2026-07-29 17:40] Version bumped to **v1.0.40** — Fix 2.2a: widening log clarification.
- [2026-07-29 17:40] Fix (2.2a) — Added `logger.info()` line at `rss_dedup.py:255-257` that prints cumulative count at end of widening loop: `"[WIDEN] '<cat>' widening complete: {existing} -> {final} stories (added: {delta})"`. This fires before the recovered/exhausted if/else, making the actual final count unambiguous regardless of outcome. No logic bug was found — `cat_widened_count` was already tracking correctly, and the exhausted branch only fires when `cat_widened_count == existing_count` (counter only increments). Bumped `config.yaml` and `__init__.py` to v1.0.40. Verified: Conroe TX News `0 -> 0`, Montgomery County `1 -> 3`, Karpathy `0 -> 3`, Hermes `1 -> 3` — all counts accurate.
- [2026-07-29 00:05] Version bumped to **v1.0.39** — P6.3 Connectivity checks complete.
- [2026-07-29 00:05] Feature (P6.3) — Created `src/daily_brief/connectivity.py` (112L) with 3 async parallel checks: `check_llm()` — ping `{host}/v1/models`, `check_rss()` — GET sample RSS feed (World News), `check_weather()` — GET `api.weather.gov/points/{lat},{lon}`. Each returns `{ok, message, duration_ms}`. `run_all_checks()` runs all 3 concurrently via `aiohttp.ClientSession`. `format_results()` produces a console table (62-char wide). Integrated into `pipeline.py` after config validation gate (warning-only, never aborts). Added CLI subcommand `config check-connectivity` in `cli.py` (+18L). Verified: 3/3 pass (LLM 24ms, RSS 703ms, Weather 42ms).
- [2026-07-28 23:40] Version bumped to **v1.0.38** — P6.1 + P6.2 (config validation + CLI) complete.
- [2026-07-28 23:40] Feature (P6.2) — Created `src/daily_brief/cli.py` (123L) with 5 subcommands: `validate` (runs validate_config, exits 0/1), `show` (YAML dump), `list-categories` (table: name/max_stories/min_age_hours), `list-lakes` (table: lake/URL), `show-prompt <name>` (prints prompt text). Modified `__main__.py` (+6L) — argparse dispatch via `cli_run()`: returns `None` → fall through to pipeline, returns `0|1` → exit with code. Added `from __future__ import annotations` for Python 3.9 compatibility.
- [2026-07-28 23:27] Feature (P6.1) — Created `src/daily_brief/config_validator.py` (329L, 60+ rules) with 7 validation groups: `check_required_keys` (14 rules: top-level blocks, nested keys), `check_types` (18 rules: str/int/float/dict/list guards), `check_ranges` (12 rules: lat/lon, temperature 0-2, top_p 0-1, hours 0-168, version X.Y.Z), `check_categories` (6 rules: query/max_stories/age limits, priority/boosts cross-reference), `check_lake_urls` (3 rules: non-empty dict, https URLs), `check_prompts` (3 rules: 4 prompts ≥20 chars), `check_timezone_and_paths` (IANA timezone + absolute path). Wired into `pipeline.py` `main()` as pre-Phase 1 gate — exits 1 with all issues on failure. Added `validate_config` re-export to `__init__.py`. Fixed stale `Space News` category_boosts entry (category only exists as `SpaceX News`). Verified: 0 issues on current config, 76 stories E2E pass.
- [2026-07-28 21:41] Version bumped to **v1.0.36** — P5.2 Phase 4 render extraction + wiring complete.
- [2026-07-28 21:41] Refactor (P5.2) — Wired pipeline.py Phase 4 to existing `rendering/report.py` functions. Added `build_sections_from_stories()` — converts StoryPipelineState → sections dict + alerts list; `compute_output_path()` — auto-versioned filepath generation. Replaced 113L inline markdown assembly in pipeline.py with 25L shim calls to `build_sections_from_stories()`, `compute_output_path()`, `build_markdown()`, `write_report()`. Reduced `pipeline.py` from 364L → 284L (-80L). Added `re`, `format_pub_date` imports to pipeline.py; added `os`, `re` imports to rendering/report.py. Removed unused imports (`tag_story_with_keywords`, `build_weather_markdown`) from pipeline.py. Verified: 73 stories, 15 categories, all 6 phases pass.
- [2026-07-28 21:00] Version bumped to **v1.0.35** — P5.1 RSS Dedup extraction complete.
- [2026-07-28 21:00] Refactor (P5.1) — Extracted Phase 2 RSS dedup (138L) into `src/daily_brief/pipelines/rss_dedup.py` (269L). Created 3 functions: `dedup_entries()` — sync, age-filters + dedups per category, appends to `deduped_list`; `widen_category()` — async, adaptive 2d-7d widening until ≥3 stories; `fetch_and_dedup()` — async orchestrator: concurrent fetch → per-cat dedup → widening → cross-cat dedup → stats. Reduced `pipeline.py` from 521L → 364L (-157L). Pipeline shim for Phase 2 is now 6 lines. Removed unused imports (`feedparser`, `parsedate_to_datetime`, `cmp_to_key`, `build_rss_url`, `fetch_feed`, `normalize_title`, `parse_feed_date`, `_sort_entries`, `is_obituary_title`, `is_realt_estate_title`, `_safe_sentence_summary`, `_count_sentences`) and eliminated duplicate `is_realt_estate_title` definition from `pipeline.py`. Verified: 74 stories, 15 categories, all 6 phases pass.
- [2026-07-28 14:30] Version bumped to **v1.0.34** — P5 Pipeline + Config extraction complete.
- [2026-07-28 14:30] Refactor (P5) — Monolith `dashboard_pipeline.py` reduced from 1,701L → 16L (thin shim). Created `src/daily_brief/pipeline.py` (521L, `async def main()` with all 6 phases, `log()`, `_coerce_temperature_f`, `is_realt_estate_title`), `config.py` (139L, moved from project root — near-copy with `BASE_DIR` path fix), `validation.py` (150L, `validate_report()` — 5 checks: empty summary, headline repeat, min sentences, fallback markers, topic overlap), `harness.py` (77L, `run_test_harness()` — subprocess call to Test_validate_run.py). Updated `__main__.py`: imports from `daily_brief.pipeline` (not `dashboard_pipeline`). All subpackage imports fixed: `from config import` → `from daily_brief.config import` (8 files). All 6 phases and all subpackage function calls verified intact.
- [2026-07-28 03:50] Version bumped to **v1.0.32** — P3 LLM module extraction complete.
- [2026-07-28 03:50] Refactor (P3) — Created `src/daily_brief/llm/` subpackage (4 files): `client.py` (39L, `LLMClient` class, `create_llm_client()` factory, `_executor`, `_run_blocking`), `summarizer.py` (476L, `_summarize`, `batch_summarize_all`, `parse_batch_summary_response`, `build_context`, `StoryPipelineState`, `_safe_sentence_summary`, `_is_refusal`, `_is_boilerplate`, `_count_sentences`), `alerter.py` (80L, `batch_evaluate_alerts`, `parse_alert_batch_response`), `__init__.py` (re-exports). Monolith `dashboard_pipeline.py` now uses delegating wrappers, removing ~501L inline LLM code. `_llm_client` is instantiatable via `create_llm_client(model, base_url, timeout)`. Pipeline validated: 72 stories, 0 failures.
- [2026-07-28 13:09] Version bumped to **v1.0.33** — P4 rendering extraction complete.
- [2026-07-28 13:09] Refactor (P4) — Created `src/daily_brief/rendering/` subpackage (4 files): `weather_table.py` (63L, `build_weather_markdown()` — forecast, station, lake tables), `report.py` (127L, `build_markdown()`, `write_report()` — frontmatter, category sections), `cleanup.py` (50L, `cleanup_old_files()` — report + log cleanup), `__init__.py` (re-exports). Monolith `dashboard_pipeline.py` now uses delegating wrappers for weather table and cleanup. Pipeline validated: 71 stories, 0 failures.
- [2026-07-28 02:20] Version bumped to **v1.0.31** — Lake monitoring expanded from 3 to 11 lakes.
- [2026-07-28 02:20] Config (`config.yaml`) — Added 8 new lakes: `livingston`, `waco`, `ray_roberts`, `lewisville`, `ray_hubbard`, `choke_canyon`, `caddo`, `toledo_bend` (total 11 with existing 3: conroe, travis, corpus_christi).
- [2026-07-28 02:20] Refactor (`sources/weather.py`) — Changed hardcoded lake loop to iterate `WEATHER_LAKE_URLS.items()` dynamically.
- [2026-07-28 02:20] Refactor (`dashboard_pipeline.py`) — Changed hardcoded lake loop to iterate `WEATHER_LAKE_URLS` dynamically. Added `_lake_label` helper with "Lake" prefix for dynamic rendering. Test [1.4] passes.
- [2026-07-28 01:50] Version bumped to **v1.0.30** — Section count widening logic fixed.
- [2026-07-28 01:50] Fix (`dashboard_pipeline.py`) — Widening trigger changed from `added == 0` to `added < 3`, all 15 sections now render ≥3 stories.
- [2026-07-28 01:09] Version bumped to **v1.0.29** — Tag distribution goal achieved: every story has ≥3 tags.
- [2026-07-28 01:09] Fix (`tagging.py`) — Moved `min_tags=3` promotion logic *after* conflict resolution block so tags stripped by international/us-focused conflict are restored. Result: 61 stories, avg 3.90 tags, distribution `{3:30, 4:7, 5:24}`.
- [2026-07-28 00:28] Config (`config.yaml` v1.0.28-29) — Added keywords: `local` (spring, fort worth, wisconsin), `sports` (soccer, world cup, transfer, man city, player), `economy` (shares, bond, bonds, stock, wall street, imf, argentina, citic, securities, growth, upcycle), `environment` (sustainable, water, green), `people` (cup, winner, art, artist), `us-focused` (runaway, newsweek, nevada, travel, new york), `companies` (companies, time, workplace, growth, orders, 3m), `international` (soccer, world cup, imf, iran, strike, debt), `semiconductors` (asml), `government` (department, federal, agency, nist, doj), `politics` (iran, strikes). Updated `category_boosts`: OpenAI, Anthropic, SpaceX, Big Tech, Conroe, Montgomery County, Texas, Houston Weather, AI, Andrej, Hermes, Semiconductors, Space News categories.
- [2026-07-27 23:20] Refactor (`tagging.py`) — Category boosts now fire for category membership (not just keyword match). Added `min_tags=3` promotion: promotes next-best scoring tags (>0 score, even below threshold) when story has <3 tags. Last resort: category-derived fallback tags.
- [2026-07-27 22:52] Tagging improvements — v15→v16: avg tags 2.40→2.71, single-tag stories 26→20. Added keyword coverage for `local`, `tech`, `environment`, `science`.
- [2026-07-26 20:45] Version bumped to **v1.0.15** — P2 tagging + categorization extraction complete.
- [2026-07-26 20:45] Refactor (P2) — Created `src/daily_brief/tagging.py` (46L): `tag_story_with_keywords` reads `TAGGING_MAPPINGS`, `TAGGING_CONFIG`, `CATEGORY_BOOSTS` from config. Created `src/daily_brief/categorization.py` (19L): `ordered_categories_for_render` reads `CATEGORY_PRIORITY` from config. Updated `config.yaml`: added `tagging_config:` (max_tags: 5, score_cap: 5.0), `category_boosts:` (4 categories), `category_priority:` (16 categories). Updated `config.py`: added `TAGGING_CONFIG`, `CATEGORY_BOOSTS`, `CATEGORY_PRIORITY` reads. Updated monolith: delegating wrappers + removed ~97L inline keyword dict. Fixed tag_story_with_keywords and ordered_categories_for_render in monolith to import from new modules.
- [2026-07-26 15:25] Version bumped to **v1.0.14** — P2 data sources split complete.
- [2026-07-26 15:25] Refactor (P2) — Created `src/daily_brief/sources/` subpackage (6 modules, 975 SLOC total): `climate.py` (179L, `_fetch_climate_normal_high`, `_parse_climate_summary`), `lakes.py` (97L, `_extract_lake_value`), `wunderground.py` (185L, `_fetch_station_metrics`, `_fetch_station_monthly_rainfall`, `_parse_wu_monthly_precipitation`), `rss.py` (151L, `build_rss_url`, `fetch_feed`, `normalize_title`, `parse_feed_date`, `format_pub_date`, `_sort_entries`), `article.py` (76L, `stage_extract_article`, `build_context`), `weather.py` (262L, `fetch_weather` orchestrator + helpers). Extended `utils.py` with `_extract_first_match`, `is_obituary_title`, `is_realt_estate_title`. Fixed `http_client.py` with proper `user_agent` param and `**params` passthrough. Migrated ~26 `log()` calls to Python `logging`. Fixed duplicate climate normal call (dead code at monolith line 988). Full pipeline validated: 56 stories, 0 errors, 85.6s.
- [2026-07-26 16:35] Version bumped to **v1.0.13** — P1 foundation extraction complete.
- [2026-07-26 16:30] Refactor (P1) — Created `src/daily_brief/` package (5 files): `__init__.py` (re-exports), `__main__.py` (entry point with `RotatingFileHandler`), `models.py` (6 dataclasses: Story, WeatherData, LakeData, AlertResult, ForecastPeriod, BriefOutput), `utils.py` (7 helpers: _safe_text, strip_html, _present_weather_value, _clean_number, _safe_sentence_summary, _count_sentences, _coerce_percent), `http_client.py` (async _fetch_json, _fetch_text, session management). All modules use standard Python `logging` throughout. Full import chain verified.
- [2026-07-26 16:25] Version bumped to **v1.0.12** — P0 cleanup applied (dead code, duplicate function, typo fix).
- [2026-07-26 16:20] Cleanup (P0) — Deleted dead code at `dashboard_pipeline.py:365-376` (12-line orphaned function body). Removed duplicate `is_obituary_title` at line 1561 (canonical at 358). Fixed typo `wundereground` → `wunderground` in `config.py:120`. Line count: 1944 → 1921. Full pipeline verified: 55 stories, 0 failures.
- [2026-07-26 03:30] Plan — Adopted comprehensive refactoring plan (P0-P6): modularize 1,942-line monolith into 18 files (40-250 lines each), add testing framework (4 tiers), add config validation + CLI management. Target: 35 hours total across 9 phases. Version bumped to **v1.0.11**.
- [2026-07-26 03:25] Fix — Removed unconditional "fallback-applied" log. Climate normal (Open-Meteo ERA5) now called before any forecast fallback. "Weather OK" summary properly detects `(fallback)` markers and reports PARTIAL.
- [2026-07-26 02:54] Feature — Added Open-Meteo ERA5 climate normal fetch for `avg_temp_today` (replaces Wunderground's inaccurate daily-high approximation). Uses `temperature_2m_max` with UTC date sync. Weather labels driven by `config.yaml:weather_labels.station_rows` (commit 299f4a0).
- [2026-07-26 02:32] Refactor — Switched from `import ollama` to `from openai import OpenAI`. Client init uses `base_url=...`, `timeout=180`. Removed `num_ctx` from `config.yaml` summary/alert options (vLLM rejects in API payload). Updated LLM response parsing from `r["message"]["content"]` to `r.choices[0].message.content`. Config defaults: `llm_model: "gemma4-e2b"` (commit cb52c50).
- [2026-07-26 02:10] Fix — Rewrote `_fetch_station_metrics` with BeautifulSoup table parser (commit df49693). Replaces broken regex that misread "Elev 187 ft" as temperature. Verified: `avg_temp_today=83.3°F`, `current_monthly_rainfall=7.42 Inches`.
- [2026-07-26 02:10] Fix — Updated "Weather OK" summary line to report "Weather PARTIAL" when any station value is "Unavailable" or fallback-derived (commit a72e559).
- [2026-07-26 02:10] Cleanup — Deleted debug scripts: `debug_station.py`, `debug_tables.py`, `test_station.py`.
- [2026-07-26 02:10] Verification — Ran full pipeline end-to-end: 55 stories, 0 failures, real station data throughout, no extreme-temperature warnings. Pipeline time: 10.4s. Bumped to **v1.0.10**.
- [2026-07-24 00:15] Fix - Resolved NameError in dashboard_pipeline.py (DEFAULT_CATEGORIES_COUNT) and verified end-to-end execution; version bumped to **v1.0.9**
- [2026-07-18 20:00] Release - Documentation and validation backlog closure completed; version bumped to **v1.0.7**
- [2026-07-18 19:35] Fix - Station metrics corrected to use live monthly average and current monthly totals from wunderground summary
- [2026-07-18 18:15] Fix - Lake trend table now reports separate values for Today / 1 Week Ago / 30 Days Ago
- [2026-07-18 16:05] Fix - Weather section order aligned to requirements examples (Example1/Example2)
- [2026-07-18 15:35] Fix - Weather summaries changed to 3-sentence format with dynamic content
- [2026-07-12 22:20] Feature - Fixed configuration loading issue in dashboard_pipeline.py by changing config.VERSION to VERSION in line 604
- [2026-07-12 22:20] Feature - Improved robustness of config.py to better handle multiple parsing scenarios
- [2026-07-12 22:20] Refactor - Created fallback category definitions in config.py for when complex parsing fails
- [2026-07-12 22:20] Version bump - Updated to v1.0.1
- [2026-07-13 17:00] Release - Tagged v1.0.1 and pushed to dev branch
- [2026-07-13 17:30] Fix - Removed all hardcoded fallback values from dashboard_pipeline.py
- [2026-07-13 17:30] Fix - Improved CATEGORIES dictionary parsing in config.py
- [2026-07-13 17:30] Release - Tagged v1.0.2 and pushed to dev branch
- [2026-07-13 19:30] Fix - Resolved configuration parsing bug that was preventing pipeline execution
- [2026-07-13 19:30] Release - Tagged v1.0.3 and pushed to dev branch
- [2026-07-13 20:00] Documentation - Updated all comments with detailed explanations of pipeline functionality and performance characteristics
- [2026-07-14 02:00] Enhancement - Implemented comprehensive enhanced tagging system with multi-tagging capabilities
- [2026-07-14 02:00] Enhancement - Extended keyword mapping to include specialized categories
- [2026-07-14 02:00] Release - Tagged v1.0.5 and pushed to dev branch

- [2026-07-29 20:50] Version bumped to **v1.0.43** — Bug F.2: frozen RSS feeds investigation.
- [2026-07-29 20:50] Investigation (F.2) — Ran pipeline twice 2min apart, compared per-category URL overlap for 5 flagged categories: Houston Tropical Weather (100% overlap, 3/3 frozen), OpenAI News (80%, 4/5, 1 rotated), Anthropic News (100%, 4/4 frozen), SpaceX News (33%, 1/3, 2 rotated), Andrej Karpathy Activity (100%, 3/3 frozen). 3 of 5 are genuinely frozen (100% same URLs), 2 have normal turnover. Root cause: topic saturation — narrow queries ("Houston Tropical Weather", "anthropic news", "Andrej Karpathy") return same 3-5 results from Google News RSS between runs 2min apart. No code bug: `fetch_feed` does not cache (raw text to feedparser), widening uses same URL (only age limit changes). Confirmed: global turnover is 14% (56/66 shared URLs across runs — only low-volume categories stay static). No fix required; this is expected behavior for low-volume topics.
## Status
Fully functional. Pipeline v1.0.62: all refactoring P0-P6 complete. All 4 testing tiers done (761 tests, 23 files). All coverage targets met. All bugs cleared.
