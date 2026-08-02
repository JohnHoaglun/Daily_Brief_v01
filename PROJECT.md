# Project: Daily Brief v01 (v1.0.90)

## Purpose
Daily Brief aggregates RSS stories from configured categories, enriches them with weather and lake data, summarizes them through a vLLM OpenAI-compatible endpoint, and writes a Markdown report.

## Current Status
- Modular refactoring P0-P6 is complete.
- Test baseline: 793 tests (v1.0.87), 813 with B.8 (v1.0.88), 813 with C.1 (v1.0.89), all passing.
- Research review at v1.0.65 identified the active 4-phase optimization program in `PLAN.md`.
- Performance baseline (v1.0.67): 105–114s internal, 137–147s wall-clock. Phase 3 (LLM) dominates at ~96–100s.
- Phase A complete (v1.0.67). Phase B complete (v1.0.88). Phase C in progress (C.1: v1.0.89).
- Preflight probes are now opt-in via `runtime.preflight_checks_enabled`. Default: `false` (disabled).
- Weather provider architecture separated: NWS failure no longer prevents ERA5, rainfall, or lake collection.
- LLM client migrated to `AsyncOpenAI`; all LLM calls and retry backoffs are non-blocking (async/await).

## Architecture
- `src/daily_brief/pipeline.py`: asynchronous pipeline orchestration.
- `src/daily_brief/sources/`: NWS, Wunderground, Open-Meteo/climate.gov, reservoir, RSS, and article extraction integrations.
- `src/daily_brief/llm/`: Async `AsyncOpenAI` client, async batch summarization, and async alert evaluation.
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
1. Execute Phase A (10 correctness/quick-wins items).
2. Execute Phase B (weather + RSS concurrency) before attempting LLM changes.
3. Resolve alert-system disposition blocker before Phase C.5.
