# PLAN — Single-source versioning direction

## Status: COMPLETE — All pipelines and tests verified clean. Fixed test-phase hang via _pip late-binding.

## v1.0.153 — Concurrency scheduling fix
- **Bug:** `test_phase_1_and_2_run_concurrent` hung indefinitely.  Root cause: `stage_weather()` called `fetch_weather` via module-level import (line 47 of `stages.py`), but test patched `daily_brief.pipeline.fetch_weather`. The mock never fired because the import resolved to `daily_brief.sources.weather.fetch_weather`.
- **Fix:** Added `_fw = _pip("fetch_weather")` late-binding inside `stage_weather()`, matching `stage_rss()` and `stage_extract()` patterns. Updated `test_patch_fetch_weather_at_package_level` to patch `daily_brief.pipeline.fetch_weather` (consistent with the late-bound resolution).
- **Result:** 665/666 tests pass (1 skipped), 0 failures.

## P1 — Pipeline Stage Extraction
### Changes
- `daily_brief/pipeline/stages.py`: Six standalone stage functions extracted:
  - `stage_weather(ctx, session, log_fn)` — Phase 1 weather fetch
  - `stage_rss(ctx, session, log_fn)` — Phase 2 RSS dedup
  - `stage_extract(stories, ctx, session, log_fn)` — Phase 3A article extraction
  - `stage_summarize(stories, ctx, log_fn)` — Phase 3B/3C batch summarization
  - `stage_render(stories, weather, dedup_stats, ctx, log_ver, log_fn)` — Phase 4 report rendering
  - `stage_validate(report_path, ctx, log_fn, run_start)` — Phase 5 report validation
- All stages use `_pip()` late-resolution for test-patch compatibility.
- `main()` reduced to orchestration layer: config validation, preflight, context setup, reservation, logger lifecycle, sequential stage calls, teardown.

### Tests
- `tests/test_pipeline_stages.py`: 12 regression tests for stage extraction (existence, concurrent pair, short-circuit, package-level patching).
- `tests/test_build_context_wiring.py`: 10 regression tests for build_context consistency.

### Verification
- `python3 -m pytest --tb=no -q` — 639 passed, 1 skipped
- `python3 -m daily_brief config validate` — PASS
- `python3 -c "import daily_brief.llm.summary_parser; import daily_brief.pipeline; print('OK')"` — OK


## Scope and Order
1. **Connectivity Hardening** — TLS verification, User-Agent forwarding, safe URL parsing. `daily_brief/connectivity.py`
2. **Logging Consolidation** — run-scoped logger, retire direct file writes, per-run file handler. `daily_brief/pipeline.py`
3. **Benchmark Driver** — dedicated concurrency benchmark module with benchmark-only serial/concurrent toggle. `daily_brief/benchmark_pipeline_concurrency.py`

**Execution order:** connectivity → logging consolidation → benchmark driver. Each slice tested, committed, and pushed before the next begins.

## 1. Connectivity Hardening
### Changes
- `daily_brief/connectivity.py`
  - Remove `ssl=False` from LLM probe — restore aiohttp default TLS verification
  - Import and send `USER_AGENT` with all probes (LLM, RSS, weather, Open-Meteo, Wunderground, lakes)
  - RSS probe URL: use `urllib.parse.quote_plus` for query encoding to match production
  - Lake probe: replace `url.split("/")[2]` with `urllib.parse.urlsplit(parsed).netloc`, safe fallback for malformed URLs

### Tests
- `tests/test_connectivity_extended.py`: add tests for TLS defaults, User-Agent forwarding to each probe, RSS query encoding, malformed lake URL safety

### Verification
- `python3 -m pytest tests/test_connectivity_extended.py` (targeted)
- `python3 -m pytest` (full suite)
- `python3 -m daily_brief config validate`

## 2. Run-Scoped Logging Consolidation
### Changes
- `daily_brief/pipeline.py`
  - Replace direct `_log_ctx()` file writes with a dedicated `daily_brief` logger with run-scoped handlers
  - Retire legacy `log()` global. Update `_coerce_temperature_f()` to use standard logger
  - Configure logging only after RunAllocator reserves log path. Pre-reservation: stderr-only
  - Handlers closed/removed in finally to prevent cross-run duplication

### Tests
- Validation failure prints reserved run-log path
- Standard `daily_brief.*` warnings reach correct run log exactly once
- Pipeline phase and harness diagnostics remain logged
- Startup works before log path exists
- Concurrent runs don't leak across files

### Verification
- `python3 -m pytest` (full suite)
- `python3 -m daily_brief config validate`

## 3. Benchmark Driver — COMPLETE v1.0.145
### Changes
- `daily_brief/benchmark_pipeline_concurrency.py` (new module)
  - Dedicated, non-default benchmark driver
  - Benchmark-only serial/concurrent Phase 1/2 toggle
  - Aggregates extraction metrics (fetch/parse/bytes distributions, failure/skipped counts, observed max concurrency)
  - Structured JSON results output
  - Configuration provenance capture
  - Single `asyncio.run()` via `_run_async_benchmark()` for all cells — avoids event loop churn

### Tests
- Deterministic tests for benchmark overrides, metric aggregation, phase mode selection, JSON result shape

### Verification
- `python3 -m pytest` (full suite)
- `python3 -m daily_brief config validate`

## Release Process (single canonical source)
Every release touches **one** file: `daily_brief/_version.py`.

1. Increment version in `daily_brief/_version.py`
2. Update `SUMMARY.md` with a new immutable `<section header>` entry for this release
3. Update `PLAN.md` and `TODOS.md` status lines as work evolves
4. Run full test suite, then config validate
5. Commit, then create and push a Git tag `vX.Y.Z`
6. If needed, create a GitHub release from that tag

**Never** bump versions in module docstrings, test files, or `config.yaml`.

## Non-Goals
- Do not change RSS candidate-pool widening behavior
- Do not alter extraction concurrency limits or HTTP bounds
- Do not expand connectivity checks into broader endpoint redesign beyond hardening
- Do not change exit code policy for WARN/SKIPPED.
