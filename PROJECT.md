# Project: Daily Brief v01 (v1.0.134)

## Purpose
Daily Brief aggregates RSS stories from configured categories, enriches them with weather and lake data, summarizes them through a vLLM OpenAI-compatible endpoint, and writes a Markdown report.

## Current Status
- Modular refactoring P0-P6 is complete.
- Test baseline: - Current verification baseline: 530/530 tests passing; config validate PASS (v1.0.134)., config validate PASS (v1.0.122).
- Current release/version locations are tracked in `versions_locations.md` and must be checked before every commit.
- Performance baseline (v1.0.67): 105–114s internal, 137–147s wall-clock. Phase 3 (LLM) dominates at ~96–100s.
- Phase A complete (v1.0.67). Phase B complete (v1.0.88). Phase C complete (v1.0.97).
- Preflight probes are now opt-in via `runtime.preflight_checks_enabled`. Default: `false` (disabled).
- Weather provider architecture separated:
- **Wave 4 concurrency safety** (v1.0.127): `RunContext`, atomic paired artifact reservations, atomic report writes, concurrent Phase 1/2 dispatch, bounded article extraction. All 13 concurrency-contract tests pass. NWS failure no longer prevents ERA5, rainfall, or lake collection.
- LLM client migrated to `AsyncOpenAI`; all LLM calls and retry backoffs are non-blocking (async/await).
- **LLM batch scheduler**: `batch_size=4`, `max_concurrency=2` — configured under `llm.*` in config.yaml, validated by `check_batch_scheduler()` (v1.0.98).
- **Centralized summary recovery** (v1.0.95): batch retry, single-story recovery, fallback, and structured `SummaryMetrics` centralized in `batch_summarize_all()`. Pipeline Phase 3D/3E duplicate recovery loops removed (−57 lines).
- **Centralized HTTP retry/status** (v1.0.96): `_request_with_retry()` with bounded attempts (3) and async backoff. Retries only `429`/`502`/`503`/`504`/timeout/client errors; never retries `4xx` non-transient.
- **Alert feature retired** (v1.0.97): Complete C.5 retirement — deleted `llm/alerter.py`, alert config/prompt/CLI, `AlertResult` model, alert report extraction, and alert validation.
- **Config unification** (v1.0.98): D.1 — unified config schema: `config.py` uses nested `DEFAULTS`, `_get_nested()` helper, single YAML read. `config_validator.py` validates canonical `llm.*`/`network.*`/`runtime.*` paths only. `pipeline.py` uses explicit imports (no star). Legacy root `config.py` deleted.
- **Canonical story model** (v1.0.99): D.2 — promoted `models.Story` to 7-field typed dataclass (title, link, snippet, category, pub_dt, context, summary). Replaced `StoryPipelineState` with alias. All pipeline, source, rendering, script, and test consumers use keyword construction. Unused `pubDate`, `tags`, `source` fields removed.
- **Duplicate utility canonicalization** (v1.0.100): D.3 — eliminated 4 exact-duplicate functions: `_safe_sentence_summary` and `_count_sentences` removed from `summarizer.py`; `build_context` promoted to `utils.py` (parametrized with `preview_chars`, default 600, no config dependencies); `_coerce_temperature_f` in `pipeline.py` delegates to `utils`. All imports redirect to `utils.py`.
- **Parser golden fixtures** (v1.0.101): D.4 — added 15 golden fixtures + 17 edge-case tests for `parse_batch_summary_response()` covering all LLM response formats: STORY_N with/without pipe/equals, numbered lists (1., 2), ### variants, plain paragraphs, summary-of headings, fuzzy headline remapping, adjacent swap, sentence trimming. Documents actual parser behavior including edge cases with positional fallback.
- **Startup crash fix** (v1.0.105): D.8 — `log()` guarded against `RUN_LOGFILE` being `None` before logfile initialization at pipeline start. Early logging writes stderr only until logfile initialized. 954/956 tests passing (2 pre-existing), config validate PASS, pipeline runs successfully.
- **Test isolation fix** (v1.0.107): Quality-7 — fixed `TestConfigUncoveredBranches` module state leak from `importlib.reload` with mocked `yaml.safe_load` that left `TIMEZONE="UTC"` and stale categories, causing `test_zoneinfo_uses_configured_timezone` to fail when tests ran after config tests. Added `tearDownClass` to restore real YAML config. 956/956 tests passing (0 pre-existing), config validate PASS.
- **Harness version alignment** (v1.0.108): The run log and report independently allocated versions from separate directories, causing the Phase 6 harness to seek a non-existent report file (e.g., log v12, report v10). Fixed by passing `log_ver` to `compute_output_path()` so log and report share the same version. Added 3 regression tests. 959/959 tests passing, config validate PASS, pipeline smoke test harness validates actual report.
- **Tag conflict policy fix** (v1.0.110): Removed `["international", "us-focused"]` from `tag_conflicts`. `international` + `us-focused` is now allowed — they describe different dimensions and can validly co-occur. `["international", "local"]` remains the sole conflict pair. Updated test conflicts, spec doc, and unit tests to reflect the new policy. 970/970 tests passing.
- **Frontmatter category count** (v1.0.111): Bug-13 — `rendered_cat_count` in `pipeline.py` excluded empty categories, but `report.py` renders all configured categories with `_No stories found._`. Frontmatter count didn't match section headers, triggering harness check 4.3 failure. Fixed by removing the non-empty guard. 968/975 passing (7 pre-existing), config validate PASS.
- **Summarizer topic-alignment** (v1.0.112): Batch and recovery summaries that share zero significant keywords with the headline are rejected and fall back to `\[Auto\] <headline>`. Eliminates harness check 3.3 zero-overlap failures on live runs. Added `_has_topic_overlap()` guard to `_is_valid_summary()`, batch path, and individual recovery. 977/984 passing (7 pre-existing), config validate PASS, live smoke test WARN (zero FAILs).
- **RSS dedup test repair** (v1.0.113): Fixed 7 pre-existing failures in `tests/test_sources/test_rss_dedup.py`. Mock RSS story dates (`Jul 30, 2026`) were age-filtered because `datetime.now()` returned the real current time (~Aug 7). Added `mock.patch("daily_brief.pipelines.rss_dedup.datetime", wraps=datetime)` with `dt_mock.now.return_value = NOW` to 7 integration tests across `TestFetchAndDedup` and `TestLocalWidening`. 984/984 passing, config validate PASS, live smoke test WARN (zero FAILs, 50.41s, 78 stories).
- **Full code review backlog** (v1.0.114): Recorded prioritized reliability, summary quality, configuration safety, test validity, data integrity, performance, lifecycle, packaging, CI, and repository-hygiene work in `TODOS.md`. No production behavior changed. Baseline remains 984/984 passing, config validate PASS, and live smoke WARN with zero FAILs.
- **Concurrency contract fixtures** (v1.0.123, resolved v1.0.127): 13 concurrency-contract tests — all passing.
- **Concurrent weather-provider collection** (v1.0.134): `fetch_weather()` launches NWS, climate, rainfall, lakes concurrently. `_fetch_station_monthly_rainfall()` also launches Wunderground/weather.gov rainfall requests simultaneously. Added `tests/test_concurrency_contract.py` (669 lines, 13 tests) documenting the Wave 4 concurrency bugs: (1) mutable module globals (`RUN_LOGFILE`, `PHASE_TIMINGS`, `OUTPUT_DIR`, `_llm_client`) shared across concurrent runs, (2) report/log version allocation not atomic — concurrent runs collide on v1, (3) `write_report()` writes directly to final path without temp file + `os.replace()`, (4) Phase 1 and Phase 2 run serially instead of concurrently, (5) article extraction via `asyncio.gather()` is unbounded with no concurrency limit, (6) pipeline global state leaks between concurrent runs. 4 tests fail (documenting bugs), 9 pass (contract baseline).
- **Pipeline exit-code contract** (v1.0.115): `pipeline.main()` returns explicit integer exit codes for all outcomes: 0=SUCCESS(PASS), 1=WARNING(WARN/CONFIG), 2=FAILURE(FAIL/VALIDATION), 3=ERROR(ERROR/SKIPPED). Replaced internal `sys.exit(1)` with consistent return contract. `__main__.py` propagates via `sys.exit(asyncio.run(main()))`. Added 7 new tests. 991/991 passing, config validate PASS, live smoke exit 1 (WARN).
- **Summary recovery correctness** (v1.0.116): Extended `_is_valid_summary()` as the sole quality gate for batch and individual LLM recovery — now also rejects refused output and internal fallback markers ([Auto], [Summary Unavailable]). Individual recovery uses `_is_valid_summary(retry, s.title)` instead of a weaker inline condition. [Auto] headline output no longer incorrectly increments `individual_recovered`. 20 new tests (11 unit, 9 recovery integration). 1009/1009 passing, config validate PASS, live smoke exit 1 (WARN, 52.68s, 76 stories).

## Architecture
- `daily_brief/pipeline.py`: asynchronous pipeline orchestration.
- `daily_brief/sources/`: NWS, Wunderground, Open-Meteo/climate.gov, reservoir, RSS, and article extraction integrations.
- `daily_brief/llm/`: Async `AsyncOpenAI` client, async batch summarization (configurable batch/concurrency), structured `SummaryMetrics`.
- `daily_brief/pipelines/rss_dedup.py`: RSS filtering, deduplication, and widening.
- `daily_brief/rendering/`: weather table generation, report assembly, and output cleanup.
- `daily_brief/config.py` and `config.yaml`: runtime configuration and defaults.
- `daily_brief/config_validator.py`: startup and CLI configuration validation.
- `daily_brief/validation_harness.py`: post-run validation (Phase 6).
- `daily_brief/benchmark_llm_batches.py`: LLM batch benchmark harness.
- `daily_brief/capture_corpus.py`: corpus capture utility.
- `tests/`: unit, mocked-source, integration, coverage, and pipeline tests.

## Configuration
- Runtime settings are in `config.yaml`; do not store credentials in repository documentation.
- Important groups: `directories`, `weather`, `llm`, `categories`, `tagging_mappings`, `category_priority`, and `weather_labels`.
- Validate configuration with `python -m daily_brief config validate`.

## Tracking Files
- `TODOS.md`: active executable work only.
- `PLAN.md`: optimization strategy, research findings, risks, decisions, and verification gates.
- `SUMMARY.md`: completed, dated change history.

## Current Priorities
All Phases A–C and P0–P1 items complete. Active P2 work tracked in `TODOS.md`.
