# Project: Daily Brief v01 (v1.0.97)

## Purpose
Daily Brief aggregates RSS stories from configured categories, enriches them with weather and lake data, summarizes them through a vLLM OpenAI-compatible endpoint, and writes a Markdown report.

## Current Status
- Modular refactoring P0-P6 is complete.
- Test baseline: 966 tests, 965 passing (1 pre-existing), config validate PASS (v1.0.96).
- Research review at v1.0.65 identified the active 4-phase optimization program in `PLAN.md`.
- Performance baseline (v1.0.67): 105–114s internal, 137–147s wall-clock. Phase 3 (LLM) dominates at ~96–100s.
- Phase A complete (v1.0.67). Phase B complete (v1.0.88). Phase C in progress (C.1-C.2a: v1.0.94).
- Preflight probes are now opt-in via `runtime.preflight_checks_enabled`. Default: `false` (disabled).
- Weather provider architecture separated: NWS failure no longer prevents ERA5, rainfall, or lake collection.
- LLM client migrated to `AsyncOpenAI`; all LLM calls and retry backoffs are non-blocking (async/await).
- **LLM batch scheduler**: `batch_size=4`, `max_concurrency=2` — adopted after live benchmark showed 55.6% speedup (97.7s → 43.4s) with zero quality regression (v1.0.94).
- **Centralized summary recovery** (v1.0.95): batch retry, single-story recovery, fallback, and structured `SummaryMetrics` centralized in `batch_summarize_all()`. Pipeline Phase 3D/3E duplicate recovery loops removed (−57 lines).
- **Centralized HTTP retry/status** (v1.0.96): `_request_with_retry()` with bounded attempts (3) and async backoff. Retries only `429`/`502`/`503`/`504`/timeout/client errors; never retries `4xx` non-transient. RSS routed through central helper with 2xx acceptance; article extraction gated to exact-200 before parsing. Existing weather/climate/lakes/Wunderground helpers inherit retry automatically (zero caller changes).
- **Alert list removed** (v1.0.97): `build_sections_from_stories()` no longer extracts or returns `alerts_list`. Simplified to return-only `sections` dict. Pipeline log/print lines cleaned of alert count.

## Architecture
- `src/daily_brief/pipeline.py`: asynchronous pipeline orchestration.
- `src/daily_brief/sources/`: NWS, Wunderground, Open-Meteo/climate.gov, reservoir, RSS, and article extraction integrations.
- `src/daily_brief/llm/`: Async `AsyncOpenAI` client, async batch summarization (configurable batch/concurrency), and async alert evaluation.
- `src/daily_brief/pipelines/rss_dedup.py`: RSS filtering, deduplication, and widening.
- `src/daily_brief/rendering/`: weather table generation, report assembly, and output cleanup.
- `src/daily_brief/config.py` and `config.yaml`: runtime configuration and defaults.
- `src/daily_brief/config_validator.py`: startup and CLI configuration validation.
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
1. ~~Execute Phase A (10 correctness/quick-wins items).~~ — Complete.
2. ~~Execute Phase B (weather + RSS concurrency) before attempting LLM changes.~~ — Complete.
3. ~~Produce live LLM batch benchmark and adopt winning settings.~~ — Complete (v1.0.94, 55.6% speedup).
4. Resolve alert-system disposition blocker before Phase C.5.
5. Execute Phase C remaining: C.3 (centralized HTTP retry), C.4 (batch retry/fallback/metrics), C.5 (alert end-to-end).