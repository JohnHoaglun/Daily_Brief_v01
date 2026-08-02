# Project Summary: Daily_Brief_v01

## Overview
Automated daily news brief generator that fetches news from 17 content categories and produces Markdown reports with AI summaries via vLLM (OpenAI-compatible client).

## Change Log
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
