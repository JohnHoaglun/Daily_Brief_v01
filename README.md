# Daily Brief v1.0.11

## Overview

Automated daily news brief generator that fetches stories from 17 categories via Google News RSS, enriches them with AI-generated summaries, and produces a structured Markdown report with weather data, lake levels, and categorized news.

## Architecture

- **RSS Feed Integration** — pulls and deduplicates stories from Google News RSS via `feedparser`
- **Content Processing** — batched LLM summarization via vLLM (OpenAI-compatible client, one call per category)
- **Weather Data** — NWS forecast, Wunderground station metrics, Open-Meteo ERA5 climate normals, Texas reservoir levels
- **Tagging** — config-driven keyword-based tagging across 20+ topic categories
- **Report Generation** — structured Markdown with frontmatter, weather tables, and category sections

## Requirements

- Python 3.9+
- vLLM server with OpenAI-compatible API (e.g., `http://192.168.4.52:8007`)
- Required packages: `aiohttp`, `feedparser`, `beautifulsoup4`, `openai`, `pyyaml`

## Setup

1. Install dependencies:
   ```bash
   pip install aiohttp feedparser beautifulsoup4 openai pyyaml
   ```
2. Ensure vLLM server is running with the configured model (default: `gemma4-e2b`)
3. Configure `config.yaml` (see below)
4. Run the pipeline:
   ```bash
   python3 dashboard_pipeline.py
   ```

## Configuration

All runtime configuration is in `config.yaml`. Key settings:

| Key | Description | Default |
|---|---|---|
| `version` | Pipeline version | `1.0.11` |
| `llm.model` | Model for summarization | `gemma4-e2b` |
| `llm.host` | vLLM API endpoint | `http://192.168.4.52:8007` |
| `directories.log_dir` | Log file output directory | vault `Dev/logs/` |
| `directories.news_dir` | Report output directory | vault `Dev/news/` |
| `weather.lat` / `weather.lon` | Weather location | `30.286, -95.566` (Houston) |
| `weather.wunderground_station_id` | Wunderground station | `KTXMONTG645` |
| `categories.*` | 17 news categories with queries and limits | see `config.yaml` |
| `weather_labels.station_rows` | Weather table row labels | configurable |
| `tagging_mappings.*` | Keyword-to-tag mappings | 20+ categories |

## Usage

```bash
python3 dashboard_pipeline.py
```

The pipeline runs in phases:
1. **Weather** — fetches NWS forecast, station metrics, climate normals, lake levels (async)
2. **RSS** — fetches 16 Google News RSS feeds concurrently, deduplicates, filters
3. **Enrich** — extracts full articles, batch-summarizes, evaluates alerts per category
4. **Render** — assembles Markdown report with frontmatter, weather tables, category sections
5. **Cleanup** — retains only the 5 most recent log/report files

## Output

Generated Markdown reports in the configured `directories.news_dir`, named `DailyBrief-YYYY-MM-DD_vNN.md`.

Each report includes:
- YAML frontmatter with tags
- Weather section: 3-day forecast table, climate normal high, monthly rainfall, lake levels
- Category sections with numbered stories, summaries, and tags
- Horizontal rule separation between categories

## File Structure

```
config.yaml                 # All runtime configuration
config.py                   # YAML loader + validation
dashboard_pipeline.py       # Main pipeline (1,942 lines — refactoring planned)
PROJECT.md                  # Architecture and status
SUMMARY.md                  # Changelog
TODOS.md                    # Task board and refactoring plan (P0-P6)
PLAN.md                     # Strategic decisions and blockers
README.md                   # This file
```

## Refactoring (In Progress)

The codebase is undergoing modularization (see `TODOS.md` for phases P0–P6):
- Split `dashboard_pipeline.py` (1,942 lines) into 18 files (40–250 lines each)
- Pluggable `sources/` for weather, RSS, lakes, climate
- `llm/` module for summarization and alerting
- `rendering/` for Markdown generation
- Comprehensive test suite (unit, mocked, smoke, post-run validation)
- Config validation and CLI management

## License

MIT License
