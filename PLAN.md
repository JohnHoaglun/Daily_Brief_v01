# PLAN — Cross-cutting structural improvements

## Status: COMPLETE — All tests pass. P1/P2 cleanup done. Current baseline: 261 tests.

## v1.0.161 — Phase 3D semantic validation enforcement COMPLETE

- **`stages.py::main()`**: Now records `story_validation_failed` flag after Phase 3D calling `stage_validate_stories()`. After Phase 5, if `story_validation_failed` is True, returns `EXIT_CODE_VALIDATION` (2) regardless of Phase 5 result.
- **`stages_validation.py::stage_validate_stories()`**: Corrected docstring that claimed function returns `True` on failure — now accurately reflects that it returns `(passed, issues)` where `passed` is `False` on failure.
- **Regression test**: Added `test_story_validation_failure_writes_report_and_returns_validation_exit()` to `tests/test_pipeline_stages.py` verifying exit code is 2, report is written, and Phase 5 executes even when Phase 3D fails.

### Verification
- `python3 -m pytest tests/test_pipeline_stages.py::TestShortCircuit -xvs` — all 4 short-circuit tests pass
- `python3 -m pytest tests/ -x --tb=short` — 261 passed

---

## v1.0.159 — P2.4 Config override correctness fix + Git provenance implementation COMPLETE

### Config override correctness (fixed three bugs in v1.0.159.1)
- **`_find_config_path()` precedence**: Now checks CLI override *before* `DAILY_BRIEF_CONFIG` env var (env was checked first — reversed).
- **`use_config_path()`**: Now rebuilds both `CONFIG_YAML` and `_RUNTIME_CONFIG` (previously only `CONFIG_YAML`).
- **`__main__.py` parsing**: Parses `--config` via `_parse_cli_before_import()` *before* importing `cli.py`, ensuring overrides apply before config-dependent modules load.
- **Explicit missing config**: Raises `FileNotFoundError` with clear message instead of silently degrading to `{}`.
- **CLI flags**: Top-level `--config PATH` for pipeline runs; config subcommand flags use `--yaml` to avoid naming collision.
- **Regression tests**: 6 tests in `tests/test_config_override.py`.

### Git provenance (v1.0.159.0)
- **`provenance.py`**: Subprocess helper resolving commit SHA, committed timestamp, author name, committer name.
- **`stages.py::main()`**: Calls four `resolve_git_*()` helpers, stores results in `ctx.provenance` dict.
- **`stages_core.py::stage_render()`**: Passes `ctx.provenance` to `build_markdown()`.
- **`report.py::build_markdown()`**: Emits optional YAML frontmatter with safe escaping for colons, quotes, newlines.
- **`pipeline/__init__.py`**: Exports `use_config_path` for CLI integration.

### Verification
- `python3 -m pytest --tb=no -q` — 260 passed (was 254, +6)
- `python3 -m daily_brief config validate` — PASS
- `python3 -c "import daily_brief.pipeline; print('OK')"` — OK
- `python3 dashboard_pipeline.py` — Phase 1–5, report written

---

## v1.0.158 — P2.4 Optional config override + optional Git provenance frontmatter (scope only)

### Config override
- **`--config PATH` CLI flag**: parse before any `daily_brief.config` import so the selected file drives all subsequent resolution.
- **Resolver precedence** (highest to lowest): CLI `--config`, `DAILY_BRIEF_CONFIG` env var, project `config.yaml`, `~/.config/daily_brief/config.yaml`, packaged defaults.
- **Selected-source reporting**: `config show` includes the resolved file path; pipeline logs the source.
- **Explicit failure policy**: when `--config` or `DAILY_BRIEF_CONFIG` points to a missing file, fail with a clear error message instead of silently falling back to the next source.
- **Renamed `CONFIG_HOME` to `DEFAULT_CONFIG_FILE_PATH`** in `config.py` — the old name read like a directory but it is a full file path.
- **Implementation points**: `config.py` (resolver), `cli.py` (`--config` arg), `__main__.py` (parse-before-import), `config_validator.py` (source reporting).

### Git provenance frontmatter
- **Optional commit metadata**: `git_commit`, `git_committed_at`, `git_author_name`, `git_committer_name` — names only, no email addresses.
- **Non-Git safety**: `git` missing, non-zero exit, timeout, or report written from a non-Git checkout produces the brief with provenance fields omitted — never aborts.
- **Implementation points**: new module `daily_brief/provenance.py` (subprocess call), `RunContext` field in `pipeline/context.py`, thread into `stage_render()` → `build_markdown()` → rendered frontmatter, validate frontmatter accepts optional fields.

### Tests
- Config resolver precedence (CLI path, CLI dir, env var, project, user, packaged).
- Explicit missing/malformed config errors.
- CLI propagation to validate/show and normal pipeline startup.
- Git helper: normal commit, unavailable executable, error exit, timeout, malformed output.
- RunContext → rendering propagation.
- Frontmatter: populated provenance, omitted unavailable provenance, YAML-safe escaping of names containing quotes, colons, newlines.

### Verification
- `python3 -m pytest --tb=no -q` (must match or improve baseline)
- `python3 -m daily_brief config validate` (PASS)
- `python3 -c "import daily_brief.pipeline; print('OK')"` (imports)
- `python3 dashboard_pipeline.py` (production smoke: Phase 1–5, report written)

---

## v1.0.157 — P2.3 HTTP body-size safety

- **Bounded streamed chunks**: replaced `iter_any()` with `iter_chunked(8192)` in `_read_body_bounded()`.
- **Per-source limits**: article HTML 2 MiB, RSS XML 1 MiB, NWS JSON 1 MiB, ERA5 512 KiB, lake HTML 1 MiB, Wunderground/weather.gov HTML 2 MiB.
- 681 tests pass, 0 regressions.

## v1.0.155 — P2.2 Cross-cutting structural cleanup
- **Tokenization dedup:** Extracted `extract_significant_words()` utility in `utils.py`. Migrated `validation.py` topic-overlap check and `tagging.py._keyword_has_stop()` to use the helper. Removed unused `re` import from `config_validator.py`.
- **Dead globals elimination:** Removed `RUN_LOGFILE`/`PHASE_TIMINGS`/`OUTPUT_DIR`/`_llm_client` from `context.py` and `stages.py`. Replaced `_current_context` with `ContextVar`-backed accessor (`get_current_run_context()`) in `__init__.py` for task-local test observation.

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
- RSS widening optimization deferred (bounded 50–100 candidates × ≤6 passes; behavioral risk outweighs benefit).
- Do not change connectivity checks into broader endpoint redesign beyond hardening.
- Do not change exit code policy for WARN/SKIPPED.
