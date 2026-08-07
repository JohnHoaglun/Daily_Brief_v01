# TODO: Daily Brief v01 - v1.0.115

## Status
v1.0.115: P0 pipeline exit-code contract implemented. 991/991 passing, config validate PASS, live smoke exit 1 (WARN, 53.86s, 78 stories). The backlog below records the review findings before implementation.

## Priority 0 - Correct Run Outcomes
- [ ] Make `pipeline.main()` return an explicit run result or exit code. Update `__main__.py` to exit nonzero for internal report-validation failure and harness `FAIL`/`ERROR`; decide and document the policy for `WARN` and `SKIPPED`. Evidence: `src/daily_brief/pipeline.py:276-297`, `src/daily_brief/__main__.py:39-55`.
- [ ] Add process-level tests for validation failure and each harness status. Verify the live runner does not log successful completion when the process status is failing.

## Priority 1 - LLM Reliability And Summary Correctness
- [ ] Make individual recovery use the canonical summary-quality predicate. It currently bypasses sentence-count, headline repetition, and stricter topic-alignment checks. Evidence: `src/daily_brief/llm/summarizer.py:558-572,645,759-765`; report validation: `src/daily_brief/validation.py:251-278`.
- [ ] Add recovery tests for one-sentence output, headline repetition, refusal output, and weak keyword overlap.
- [ ] Establish one bounded LLM retry owner. Explicitly configure SDK retries, retain a bounded application retry policy, and add a total recovery deadline. Current SDK, application, batch, and serial recovery retries can multiply endpoint-outage latency. Evidence: `src/daily_brief/llm/client.py:19-21`, `src/daily_brief/llm/summarizer.py:486-527,714-758`.
- [ ] Recover unresolved stories under a conservative configurable concurrency limit instead of serially. Add tests that assert request count, deadline, and maximum concurrency during an endpoint outage.
- [ ] Do not count deterministic `[Auto] <headline>` fallbacks as successful individual LLM recoveries. Evidence: `src/daily_brief/llm/summarizer.py:526-527,759-765,780-781`.
- [ ] Add `LLMClient.aclose()` and close the owned AsyncOpenAI transport in pipeline and benchmark `try/finally` paths. Evidence: `src/daily_brief/llm/client.py:19-25`, `src/daily_brief/pipeline.py:129-130`.
- [ ] Use `time.monotonic()` for LLM timings. Evidence: `src/daily_brief/llm/summarizer.py:488-497,600-620`.

## Priority 1 - Configuration And Degraded Operation
- [ ] Separate raw config loading, validation, and typed runtime config construction. Invalid numeric YAML values currently can crash during `config.py` import before `config validate` can diagnose them. Evidence: `src/daily_brief/config.py:101-272`, `src/daily_brief/config_validator.py:123-288,515-520`.
- [ ] Tighten config validator checks: use non-empty string validation for required strings and type-check values before numeric comparisons.
- [ ] Normalize missing weather data to `{}` before rendering and make weather rendering defensive against `None` and malformed nested data. Evidence: `src/daily_brief/pipeline.py:168-188,253-260`, `src/daily_brief/rendering/weather_table.py:9-10`.
- [ ] Add pipeline tests for weather `None`, empty weather, malformed station values, malformed lake values, and invalid numeric YAML startup behavior.

## Priority 1 - Test Validity And Warning Debt
- [ ] Fix the unawaited coroutine test warning by mocking `_cmd_check_connectivity_impl` with `AsyncMock`, not `asyncio.run`. Evidence: `tests/test_cli.py:135-145`, `src/daily_brief/cli.py:159-160`.
- [ ] Replace all project uses of deprecated `asyncio.coroutine` test mocks with `AsyncMock` or async stubs. The suite currently emits 145+ deprecation warnings. Representative files: `tests/test_sources/test_climate.py`, `test_lakes.py`, `test_weather.py`, `test_weather_extended.py`, `test_weather_provider_isolation.py`.
- [ ] Remove external network requests from the default test suite. Fully mock `tests/test_smoke_test.py:265-274`; move genuine connectivity checks to opt-in integration coverage.
- [ ] Repair `test_runs_in_parallel`, which currently injects no timing mock and asserts nothing. Evidence: `tests/test_smoke_test.py:276-295`.
- [ ] Replace timing-sensitive concurrency assertions with deterministic async barriers. Evidence: `tests/test_batch_failure_fixtures.py:476-535`.
- [ ] Replace direct pipeline-global mutations in `tests/test_startup_sequence.py:41-59` with restoring fixtures or `patch.object`.
- [ ] After migration, enforce project-originated `RuntimeWarning` and `DeprecationWarning` as errors in CI.

## Priority 2 - Parser, Rendering, And Data Integrity
- [ ] Make batch-summary parser assignment one-to-one: never overwrite occupied output slots; leave ambiguous output unresolved for recovery. Evidence: `src/daily_brief/llm/summarizer.py:160-165,188-193,250-269,380-381`.
- [ ] Add parser properties and fixtures for malformed/reordered `STORY_N` responses, duplicate headline excerpts, empty titles, and no-headline input.
- [ ] Correct bracket-tag slicing from `tag[2:-2]` to `tag[1:-1]`, and replace the test that codifies the truncation bug. Evidence: `src/daily_brief/rendering/report.py:127-135`, `tests/test_report.py:417-431`.
- [ ] Escape or normalize external Markdown values, especially pipes/newlines in table cells and Markdown-special story titles. Evidence: `src/daily_brief/rendering/report.py:159-175`, `src/daily_brief/rendering/weather_table.py:27-37`.
- [ ] Improve RSS dedup identity. Avoid first-dash truncation and 80-character title-only keys; prefer normalized full titles and canonical destination URLs. Evidence: `src/daily_brief/sources/rss.py:32-40`, `src/daily_brief/pipelines/rss_dedup.py:129-140`.
- [ ] Remove or implement the misleading no-op `widen_category` compatibility wrapper. Evidence: `src/daily_brief/pipelines/rss_dedup.py:298-316`.
- [ ] Correct `_fetch_json()` type contract to allow any valid JSON value, or constrain runtime behavior to objects. Evidence: `src/daily_brief/http_client.py:108-115`, `tests/test_http_client.py:306-311`.

## Priority 2 - Performance, Backpressure, And Network Safety
- [ ] Start independent weather providers concurrently rather than waiting for NWS, then climate/rainfall, then lakes. Evidence: `src/daily_brief/sources/weather.py:354-362`.
- [ ] Fetch independent Wunderground and weather.gov rainfall sources concurrently. Evidence: `src/daily_brief/sources/wunderground.py:96-118`.
- [ ] Start Phase 1 weather and Phase 2 RSS concurrently while retaining separate timing and failure metrics. Evidence: `src/daily_brief/pipeline.py:165-198`.
- [ ] Add configurable bounded concurrency for article extraction and RSS feeds; capture and report gathered exceptions. Evidence: `src/daily_brief/pipeline.py:212-217`, `src/daily_brief/pipelines/rss_dedup.py:50-54`.
- [ ] Add defensible RSS candidate-pool limits that still support seven-day widening. Evidence: `src/daily_brief/sources/rss.py:134-155`.
- [ ] Stream HTTP bodies with source-specific byte limits and reject excessive `Content-Length` before parsing. Evidence: `src/daily_brief/http_client.py:80-84`, `src/daily_brief/sources/article.py:45-49`.
- [ ] Move large HTML parsing off the event loop if benchmarked loop lag warrants it.
- [ ] Correct climate-normal semantics: use the configured/report reference date and an actual historical-normal calculation, not one ERA5 day for current UTC date. Evidence: `src/daily_brief/sources/climate.py:28-43`, `src/daily_brief/sources/weather.py:43-53`.
- [ ] Harden connectivity checks: preserve TLS verification, use production-equivalent headers, and parse configured URLs safely. Evidence: `src/daily_brief/connectivity.py:38-40,71-73,123-126`.
- [ ] Benchmark concurrent weather/RSS and bounded extraction against the current 50.41s live baseline before adopting settings.

## Priority 2 - Output Lifecycle And Shared State
- [ ] Make report/log version allocation atomic for overlapping runs and write reports via temporary file plus `os.replace`. Evidence: `src/daily_brief/pipeline.py:140-149`, `src/daily_brief/rendering/report.py:56-68`.
- [ ] Correct retention ordering so exactly `max_log_versions` reports remain after the new report is written. Evidence: `src/daily_brief/pipeline.py:245-260`, `src/daily_brief/rendering/cleanup.py:12-21`.
- [ ] Replace mutable pipeline module globals (`RUN_LOGFILE`, `PHASE_TIMINGS`, `_llm_client`) with a per-run context to support repeated and concurrent invocation. Evidence: `src/daily_brief/pipeline.py:60-64`.
- [ ] Consolidate direct pipeline logging and standard logging; correct failure output to report `RUN_LOGFILE` directly rather than an unset environment variable. Evidence: `src/daily_brief/pipeline.py:75-87,283`, `src/daily_brief/__main__.py:14-36`.
- [ ] Replace hard-coded `77316` weather-section checks with configuration-driven location/section identity. Evidence: `src/daily_brief/pipeline.py:250-251`, `src/daily_brief/rendering/report.py:149-151`, `src/daily_brief/rendering/weather_table.py:23`.

## Priority 3 - Packaging, CI, And Repository Hygiene
- [ ] Establish one canonical version source and add a release-consistency check for package/runtime/YAML/README/tracking files. Current stale values include `src/daily_brief/config.py:19`, `src/daily_brief/__init__.py:2`, `src/daily_brief/__main__.py:2`, `dashboard_pipeline.py:3`, `PLAN.md:1`, and README current-status references.
- [ ] Add `pyproject.toml` with `src` package discovery and declared runtime/test dependencies; replace per-test/script `sys.path` mutation with editable installation.
- [ ] Add dependency locking appropriate to the selected package manager and CI for supported Python versions, tests, config validation, lint/format/type checks, warnings policy, and opt-in integration checks.
- [ ] Repair `scripts/run_tests.sh` unreachable failure reporting caused by `set -e`; add a measured coverage threshold to `scripts/run_coverage.sh`.
- [ ] Remove tracked generated coverage databases and add standard Python, pytest, coverage, HTML-report, and virtual-environment patterns to `.gitignore`.
- [ ] Add the intended license text or remove the README MIT claim until licensing is confirmed.

## Verification Gates
- [ ] Run targeted tests for each changed failure, cancellation, timeout, parsing, and degraded-operation path.
- [ ] Run the full suite with project-originated runtime and deprecation warnings promoted to errors after warning remediation.
- [ ] Verify a fresh environment with `pip install .[test]`, `python -m pytest`, and `python -m daily_brief config validate` after packaging is added.
- [ ] Run controlled before/after benchmarks for concurrency and backpressure changes; retain only improvements that preserve report and harness validity.
- [ ] Run a live smoke test after each implementation slice and record report validation, harness status, process exit status, duration, story count, and retention behavior.

## Blockers
- [ ] Product decision: define whether harness `WARN` and `SKIPPED` should cause a nonzero process exit.
- [ ] Product decision: select the intended license before adding a license file and package metadata.
