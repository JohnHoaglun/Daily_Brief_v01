# Project: Daily Brief v01 (v1.0.13)

## Overview
Automated daily news brief generator that pulls category RSS stories and produces AI-summarized Markdown reports. Currently undergoing architectural refactoring to modularize the codebase.

## Architecture

### Current (v1.0.10 — monolithic)
- `dashboard_pipeline.py` (1,942 lines) — single-file orchestrator with all weather, RSS, LLM, rendering, and tagging logic
- `config.py` (136 lines) — YAML loading, constant extraction, category building
- `config.yaml` (176 lines) — all runtime configuration

### Target (v1.1.0 — modular, post-refactoring)
- `daily_brief/` package with ~18 files, 40-250 lines each
- `sources/` — pluggable data sources (NWS forecast, Wunderground station, Open-Meteo ERA5, Texas reservoirs, Google News RSS)
- `llm/` — summarization, alert evaluation, client wrapper
- `rendering/` — weather table, report assembly, file cleanup
- `pipeline.py` — orchestrator only (no business logic)
- `tests/` — unit, integration, and smoke tests with recorded responses

### Current (v1.0.10 — monolithic)
- **RSS Feed Integration**: pulls and deduplicates stories from multiple sources via `feedparser`
- **Content Processing**: batched LLM summarization via vLLM (OpenAI-compatible client, one call per content category)
- **Data Organization**: stories grouped by 17 categories including World News, US News, Texas News, and Texas-local business/tech beats
- **Tagging System**: automatic keyword-based tagging using predefined mappings from config
- **Weather Integration**: dynamic weather forecast (NWS), station metrics (Wunderground), climate normals (Open-Meteo ERA5), and lake metrics (waterdatafortexas)

## Configuration
Primary runtime configuration is loaded from `config.yaml` (parsed by `config.py`).
- Log/news directories: `directories.log_dir`, `directories.news_dir`
- Weather sources (NWS, Wunderground, Open-Meteo, Texas reservoirs): `weather.*`
- LLM: `llm.model`, `llm.host`, `llm.summary_options`, `llm.alert_options`
- Categories: 17 defined under `categories.*`
- Weather labels: `weather_labels.station_rows` (config-driven table row names)
- Tagging mappings: `tagging_mappings.*` (to be migrated from inline dict)
- Category priority: `category_priority` (to be used for render ordering)

## Features
- Automated daily news aggregation from 17 categories
- AI-powered story summarization via vLLM (gemma4-e2b)
- Multi-category organization by source feeds
- Configurable story limits per category
- Weather data integration: NWS forecast, Wunderground station, Open-Meteo climate normals, Texas reservoir levels
- Automatic keyword-based tagging of stories
- Markdown report generation with frontmatter, weather tables, and category sections

## Refactoring Plan (in progress)
See `TODOS.md` for detailed phase-by-phase plan (P0-P6).

## Status
**v1.0.10**: Functional. Weather fixes complete (BeautifulSoup parser, ERA5 climate normal, proper fallback logging). Now entering architectural refactoring (modularization, testing, config validation).

