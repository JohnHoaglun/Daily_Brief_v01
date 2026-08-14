# PLAN: v1.0.149 — P1 Pipeline Stage Extraction & build_context Verification

## Status: COMPLETE — All 5 phases extracted to standalone async functions. main() reduced from ~500 to ~178 lines. 639 tests passing (0 new failures).

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

## Release Process (each slice)
1. Increment version `+0.0.1` in `versions_locations.md` registry
2. Update all registry targets
3. Update `PROJECT.md`, `TODOS.md`, `SUMMARY.md`, `PLAN.md`
4. `grep` for old version to catch missed references
5. Run targeted tests, then full suite, then config validate
6. Commit and push

## Non-Goals
- Do not change RSS candidate-pool widening behavior
- Do not alter extraction concurrency limits or HTTP bounds
- Do not expand connectivity checks into broader endpoint redesign beyond hardening
- Do not change exit code policy for WARN/SKIPPED.
