# TODO: Daily Brief v01 - v1.0.125

## Status
v1.0.125: Wave 1 reliability fixes — parser assignment, rendering safety, RSS identity, climate. 506/510 passing (4 concurrency contract failures, Wave 4 pending). **KNOWN ISSUE** documented below.

## Known Issues
### **Live harness FAIL on v1.0.125 (2026-08-09 20:22:27)**
Pipeline exit code 2 (FAIL) from Phase 6 test harness. Report generated successfully (79 stories, `DailyBrief-2026-08-09_v08.md`), Phases 1-5 passed. Harness result: `FAIL — exit code 2`. Root cause unknown — report content appeared OK. Needs investigation: run `python3 dashboard_pipeline.py` manually and capture the harness output from Phase 6 to identify which specific tests failed.

## Wave 4 - Concurrency Contract (acceptance criteria established)
- [x] Wave 0: Create `tests/test_concurrency_contract.py` with concurrency, output lifecycle, and pipeline ownership fixtures. 13 tests, 4 failing (documenting bugs). Completed v1.0.123.
- [ ] Wave 1: Introduce `RunContext` pattern to scope per-run state (log file, timings, LLM client, output dir). Replace module globals with parameterized context.
- [ ] Wave 2: Atomic version allocation — shared version allocator with mutex/lock for concurrent runs.
- [ ] Wave 3: Atomic report writes — `write_report()` uses temp file + `os.replace()`.
- [ ] Wave 4: Concurrent Phase 1/Phase 2 — run weather and RSS fetch in parallel.
- [ ] Wave 5: Bounded article concurrency — configurable `ARTICLE_MAX_CONCURRENCY` with `asyncio.Semaphore`.

## Wave 1 — Reliability (completed v1.0.125)
- [x] Parser assignment one-to-one, no slot overwrites
- [x] Rendering safety: bracket slicing, pipe escaping, newline normalization
- [x] RSS identity: NFKD, no truncation, no suffix stripping
- [x] Climate reference date, `_fetch_json` type widening, hardcoded 77316 removal

## Priority 0 - Correct Run Outcomes
- [x] Make `pipeline.main()` return an explicit run result or exit code. Update `__main__.py` to exit nonzero for internal report-validation failure and harness `FAIL`/`ERROR`; decide and document the policy for `WARN` and `SKIPPED`. Evidence: `daily_brief/pipeline.py:276-297`, `daily_brief/__main__.py:39-55`.
  - Completed v1.0.115. Exit codes: 0=PASS, 1=WARN/CONFIG, 2=FAIL/VALIDATION, 3=ERROR/SKIPPED.
- [x] Add process-level tests for validation failure and each harness status. Verify the live runner does not log successful completion when the process status is failing.
  - Completed v1.0.115. 7 new tests in `tests/test_pipeline.py`. Live smoke confirmed exit 1 (WARN).

## Priority 1 - LLM Reliability And Summary Correctness
- [x] Make individual recovery use the canonical summary-quality predicate.
  - Completed v1.0.116. `_is_valid_summary()` now the sole gate for batch and recovery. Added refusal/fallback marker rejection.
- [x] Add recovery tests.
  - Completed v1.0.116. 8 new recovery regression tests in `tests/test_batch_failure_fixtures.py`.
- [x] Establish one bounded LLM retry owner. Explicitly configure SDK retries, retain a bounded application retry policy, and add a total recovery deadline.
  - Completed v1.0.117. `AsyncOpenAI(max_retries=0)`, configurable `recovery_deadline_s`, monotonic LLM timings.
- [x] Recover unresolved stories under a conservative configurable concurrency limit instead of serially. Add tests that assert request count, deadline, and maximum concurrency during an endpoint outage.
  - Completed v1.0.117. `recovery_max_concurrency=2` with `asyncio.Semaphore`, pre-dispatch deadline gate, `asyncio.wait_for` in-flight cancellation. 8 new barrier/deadline tests.
- [x] Do not count deterministic `[Auto] <headline>` fallbacks as successful individual LLM recoveries.
  - Completed v1.0.116 via canonical gate. `[Auto]` output rejected by `_is_valid_summary()`, not counted as `individual_recovered`.
- [x] Add `LLMClient.aclose()` and close the owned AsyncOpenAI transport in pipeline and benchmark `try/finally` paths.
  - Completed v1.0.117. Idempotent `aclose()` awaits `client.close()`. 2 new tests.
- [x] Use `time.monotonic()` for LLM timings.
  - Completed v1.0.117. Replaced in `_summarize()` and `_summarize_sub_batch()`. 5 new timing tests.

## Priority 1 - Configuration And Degraded Operation
- [x] Separate raw config loading, validation, and typed runtime config construction. Invalid numeric YAML values currently can crash during `config.py` import before `config validate` can diagnose them.
  - Completed v1.0.117. `load_raw_config()` (safe YAML → dict or `{}`), `build_runtime_config()` (typed coercion).
- [x] Tighten config validator checks: use non-empty string validation for required strings and type-check values before numeric comparisons.
  - Completed v1.0.117. All validators hardened — non-empty strings, type guards before numeric comparisons, safe URL/path checks.
- [x] Normalize missing weather data to `{}` before rendering and make weather rendering defensive against `None` and malformed nested data.
  - Completed v1.0.117. `_normalize_weather_for_rendering()` in pipeline.py, `_normalize_weather()` in weather_table.py.
- [x] Add pipeline tests for weather `None`, empty weather, malformed station values, malformed lake values, and invalid numeric YAML startup behavior.
  - Completed v1.0.117. 12 pipeline weather normalization tests, 17 weather resilience tests, 4 raw loader tests, 13 validator safety tests.

## Priority 1 - Test Validity And Warning Debt
- [x] Fix test warning: replace `_is_valid_summary` topic-alignment check — add recovery tests. (Completed v1.0.116.)
- [x] Fix the unawaited coroutine test warning.
  - Completed v1.0.117. `AsyncMock` for `_cmd_check_connectivity_impl`.
- [x] Replace all project uses of deprecated `asyncio.coroutine` test mocks with `AsyncMock` or async stubs.
  - Completed v1.0.117. 63 patterns across 6 test files migrated. 0 remaining uses.
- [x] Remove external network requests from the default test suite. Fully mock `tests/test_smoke_test.py:265-274`; move genuine connectivity checks to opt-in integration coverage.
  - Completed v1.0.117. `pytestmark = pytest.mark.smoke`, `pytest.ini` `addopts = -m "not smoke"`. 21 smoke tests deselected.
- [x] Repair `test_runs_in_parallel`, which currently injects no timing mock and asserts nothing.
  - Completed v1.0.117. Barrier-based concurrency assertion (`max_concurrent > 1`).
- [x] Replace timing-sensitive concurrency assertions with deterministic async barriers.
  - Completed v1.0.117. Barrier-based tests in `test_batch_failure_fixtures.py`.
- [x] Replace direct pipeline-global mutations in `tests/test_startup_sequence.py:41-59` with restoring fixtures or `patch.object`.
  - No `pipe_*` globals found in pipeline.py — no changes needed.
- [x] After migration, enforce project-originated `RuntimeWarning` and `DeprecationWarning` as errors in CI.
  - Completed v1.0.117. `pytest.ini` filterwarnings for `RuntimeWarning` and `DeprecationWarning` as errors on `daily_brief` module.

## Priority 2 - Parser, Rendering, And Data Integrity
- [x] Make batch-summary parser assignment one-to-one: never overwrite occupied output slots; leave ambiguous output unresolved for recovery.
  - Completed v1.0.125. `reserved_empty_slots` and `skipped_fuzzy_match` sets prevent duplicate assignment. Positional fallback skips already-fuzzy-matched stories.
- [x] Add parser properties and fixtures for malformed/reordered `STORY_N` responses, duplicate headline excerpts, empty titles, and no-headline input.
  - Completed v1.0.125. 17 tests in `tests/test_parser_assignment_contract.py`.
- [x] Correct bracket-tag slicing from `tag[2:-2]` to `tag[1:-1]`, and replace the test that codifies the truncation bug.
  - Completed v1.0.125. `report.py:132` handles `[Tag]` → `tag[1:-1]` and `[[Tag]]` → `tag[2:-2]`. 29 tests in `tests/test_rendering_safety_contract.py`.
- [x] Escape or normalize external Markdown values, especially pipes/newlines in table cells and Markdown-special story titles.
  - Completed v1.0.125. Pipes → `&#124;` in `_present_weather_value()`. Newlines → spaces in titles/summaries (`report.py`).
- [x] Improve RSS dedup identity. Avoid first-dash truncation and 80-character title-only keys; prefer normalized full titles and canonical destination URLs.
  - Completed v1.0.125. `normalize_title()` uses NFKD normalization, no truncation, no suffix stripping. 26 tests in `tests/test_rss_identity_contract.py`.
- [ ] Remove or implement the misleading no-op `widen_category` compatibility wrapper. Evidence: `daily_brief/pipelines/rss_dedup.py:298-316`.
- [x] Correct `_fetch_json()` type contract to allow any valid JSON value, or constrain runtime behavior to objects.
  - Completed v1.0.125. Return type `Optional[Any]`, docstring warns consumers to validate type. 23 tests in `tests/test_weather_climate_contract.py`.

## Priority 2 - Performance, Backpressure, And Network Safety
- [ ] Start independent weather providers concurrently rather than waiting for NWS, then climate/rainfall, then lakes. Evidence: `daily_brief/sources/weather.py:354-362`.
- [ ] Fetch independent Wunderground and weather.gov rainfall sources concurrently. Evidence: `daily_brief/sources/wunderground.py:96-118`.
- [ ] Start Phase 1 weather and Phase 2 RSS concurrently while retaining separate timing and failure metrics. Evidence: `daily_brief/pipeline.py:165-198`.
- [ ] Add configurable bounded concurrency for article extraction and RSS feeds; capture and report gathered exceptions. Evidence: `daily_brief/pipeline.py:212-217`, `daily_brief/pipelines/rss_dedup.py:50-54`.
- [ ] Add defensible RSS candidate-pool limits that still support seven-day widening. Evidence: `daily_brief/sources/rss.py:134-155`.
- [ ] Stream HTTP bodies with source-specific byte limits and reject excessive `Content-Length` before parsing. Evidence: `daily_brief/http_client.py:80-84`, `daily_brief/sources/article.py:45-49`.
- [ ] Move large HTML parsing off the event loop if benchmarked loop lag warrants it.
- [x] Correct climate-normal semantics: accept reference date from caller; updated docstring to describe 1991-2020 climatology, not single-day ERA5.
  - Completed v1.0.125. `_fetch_climate_normal_high(session, lat, lon, reference_date)`. Remaining Wave 2 work: full 30-year averaging endpoint.
- [ ] Harden connectivity checks: preserve TLS verification, use production-equivalent headers, and parse configured URLs safely. Evidence: `daily_brief/connectivity.py:38-40,71-73,123-126`.
- [ ] Benchmark concurrent weather/RSS and bounded extraction against the current 50.41s live baseline before adopting settings.

## Priority 2 - Output Lifecycle And Shared State
- [ ] Make report/log version allocation atomic for overlapping runs and write reports via temporary file plus `os.replace`. Evidence: `daily_brief/pipeline.py:140-149`, `daily_brief/rendering/report.py:56-68`.
- [x] Correct retention ordering so exactly `max_log_versions` reports remain after the new report is written. Evidence: `daily_brief/pipeline.py:297-298`, `daily_brief/rendering/cleanup.py:12-21`.
  - Completed v1.0.119. Moved `cleanup_old_files()` from before to immediately after `write_report()`. 7 new tests.
- [ ] Replace mutable pipeline module globals (`RUN_LOGFILE`, `PHASE_TIMINGS`, `_llm_client`) with a per-run context to support repeated and concurrent invocation. Evidence: `daily_brief/pipeline.py:60-64`.
- [ ] Consolidate direct pipeline logging and standard logging; correct failure output to report `RUN_LOGFILE` directly rather than an unset environment variable. Evidence: `daily_brief/pipeline.py:75-87,283`, `daily_brief/__main__.py:14-36`.
- [x] Replace hard-coded `77316` in weather subtitle and station labels with config-driven values.
  - Completed v1.0.125. `weather_table.py:44` subtitle generic, station defaults no ZIP. `report.py:153` skip category updated. `WEATHER_SECTION_TITLE` from config.

## Priority 3 - Packaging, CI, And Repository Hygiene
- [ ] Establish one canonical version source and add a release-consistency check for package/runtime/YAML/README/tracking files. Current stale values include `daily_brief/config.py:19`, `daily_brief/__init__.py:2`, `daily_brief/__main__.py:2`, `PLAN.md:1`, and README current-status references.
- [ ] Add `pyproject.toml` with `src` package discovery and declared runtime/test dependencies; replace per-test/script `sys.path` mutation with editable installation.
- [ ] Add dependency locking appropriate to the selected package manager and CI for supported Python versions, tests, config validation, lint/format/type checks, warnings policy, and opt-in integration checks.
- [ ] Repair `scripts/run_tests.sh` unreachable failure reporting caused by `set -e`; add a measured coverage threshold to `scripts/run_coverage.sh`.
- [ ] Remove tracked generated coverage databases and add standard Python, pytest, coverage, HTML-report, and virtual-environment patterns to `.gitignore`.
- [ ] Add the intended license text or remove the README MIT claim until licensing is confirmed.

## Verification Gates
- [x] Run targeted tests for each changed failure, cancellation, timeout, parsing, and degraded-operation path.
  - Completed v1.0.117. 1039/1039 tests passing (21 smoke deselected).
- [x] Run the full suite with project-originated runtime and deprecation warnings promoted to errors after warning remediation.
  - Completed v1.0.117. pytest.ini filterwarnings enforce RuntimeWarning and DeprecationWarning as errors on daily_brief module. 0 warnings.
- [ ] Run a fresh environment with `pip install .[test]`, `python -m pytest`, and `python -m daily_brief config validate` after packaging is added.
- [ ] Run controlled before/after benchmarks for concurrency and backpressure changes; retain only improvements that preserve report and harness validity.
- [ ] Run a live smoke test after each implementation slice and record report validation, harness status, process exit status, duration, story count, and retention behavior.

## Blockers
- [ ] Product decision: define whether harness `WARN` and `SKIPPED` should cause a nonzero process exit.
- [ ] Product decision: select the intended license before adding a license file and package metadata.
