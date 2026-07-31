# Project: Daily Brief v01 (v1.0.66)

## Purpose
Daily Brief aggregates RSS stories from configured categories, enriches them with weather and lake data, summarizes them through a vLLM OpenAI-compatible endpoint, and writes a Markdown report.

## Current Status
- Modular refactoring P0-P6 is complete.
- Test baseline: 761 tests with coverage targets met at v1.0.62.
- Research review at v1.0.65 identified the active 4-phase optimization program in `PLAN.md`.
- Current performance baseline is approximately 85 seconds per pipeline run; Phase B has a credible 10-20 second reduction opportunity.

## Architecture
- `src/daily_brief/pipeline.py`: asynchronous pipeline orchestration.
- `src/daily_brief/sources/`: NWS, Wunderground, Open-Meteo/climate.gov, reservoir, RSS, and article extraction integrations.
- `src/daily_brief/llm/`: OpenAI-compatible client, batch summarization, and alert evaluation.
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
1. Establish a three-run performance baseline.
2. Execute Phase A correctness and measurement fixes.
3. Execute Phase B weather and RSS concurrency work before attempting LLM changes.
