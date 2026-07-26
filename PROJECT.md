# Project: Daily Brief v01 (v1.0.10)

## Overview
Automated daily news brief generator that pulls category RSS stories and produces AI-summarized Markdown reports.

## Architecture
- **RSS Feed Integration**: pulls and deduplicates stories from multiple sources via `feedparser`
- **Content Processing**: batched LLM summarization via Ollama (one call per content category)
- **Data Organization**: stories grouped by 17 categories including World News, US News, Texas News, and Texas-local business/tech beats
- **Tagging System**: automatic keyword-based tagging using predefined mappings
- **Weather Integration**: dynamic weather forecast, station, and lake metrics rendered in report output

## Configuration
Primary runtime configuration is loaded from `config.txt` (parsed by `config.py`).
- Weather sources, user-agents, and date utilities are now config-driven.
- Output directories are configurable via `LOG_DIR` and `NEWS_DIR`.
- Category caps/age windows and model behavior are all in config.

## Features
- Automated daily news aggregation
- AI-powered story summarization via batch processing
- Multi-category organization by source feeds
- Configurable story limits per category
- Weather data integration with dynamic lookup for forecast + monthly/lake metrics
- Automatic keyword-based tagging of stories

## Status
Functional and validated against current requirements. Pipeline now produces dynamic weather sections in example-matching layout, without hardcoded weather placeholders, and retains news pipeline behavior from `v1.0.x`.

