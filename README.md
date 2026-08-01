# Daily Brief v1.0.80

## Overview

Automated daily news brief generator that fetches stories from 17 categories via Google News RSS, enriches them with weather and lake-level data, summarizes them with AI, and produces a structured Markdown report.

## Architecture

Modular codebase in `src/daily_brief/`:

- **`pipeline.py`** — asynchronous orchestrator (6 phases: weather, RSS, LLM, render, validate, test harness)
- **`sources/`** — NWS forecast, Wunderground station metrics, Open-Meteo/ERA5 climate normals, Texas reservoir levels, RSS feeds, and article extraction
- **`llm/`** — OpenAI-compatible client, batch-of-3 summarization, boilerplate/refusal detection, auto fallback
- **`pipelines/rss_dedup.py`** — RSS filtering, deduplication, and widening
- **`rendering/`** — weather table generation, Markdown report assembly, output cleanup
- **`config.py` / `config_validator.py`** — YAML-based configuration, loading, and validation
- **`tagging.py` / `categorization.py`** — config-driven keyword tagging, category ordering
- **`tests/`** — 764 tests (unit, mocked, integration, smoke, post-run validation)

## Requirements

- Python 3.9+
- vLLM server with OpenAI-compatible API (e.g., `http://192.168.4.52:8007`)
- Dependencies: `aiohttp`, `feedparser`, `beautifulsoup4`, `openai`, `pyyaml`

## Setup

```bash
pip install aiohttp feedparser beautifulsoup4 openai pyyaml
```

1. Ensure vLLM server is running with the configured model (default: `gemma4-e2b`)
2. Configure `config.yaml` — validate with `python -m daily_brief config validate`
3. Run: `PYTHONPATH=src python3 -m daily_brief`

## Configuration

All runtime settings in `config.yaml`. Key groups:

| Key | Description | Default |
|---|---|---|
| `version` | Pipeline version | `1.0.76` |
| `llm.model` | Model for summarization | `gemma4-e2b` |
| `llm.host` | vLLM API endpoint | `http://192.168.4.52:8007` |
| `directories.log_dir` | Log output directory | vault `Dev/logs/` |
| `directories.news_dir` | Report output directory | vault `Dev/news/` |
| `weather.lat` / `weather.lon` | Weather location | `30.286, -95.566` (Houston) |
| `weather.wunderground_station_id` | Wunderground station | `KTXMONTG645` |
| `categories.*` | 17 news categories with queries and limits | see `config.yaml` |
| `tagging_mappings.*` | Keyword-to-tag mappings | 20+ categories |

## Pipeline Phases

1. **Weather** — async fetch of NWS forecast, station metrics, climate normals, lake levels
2. **RSS** — 15 Google News RSS feeds, concurrent fetch, deduplication, date filtering
3. **LLM** — article extraction, batch-of-3 summarization, retry, boilerplate detection, auto fallback
4. **Render** — Markdown assembly with frontmatter, weather tables, categorized sections
5. **Validate** — internal report validation (story count, fallback thresholds)
6. **Test harness** — external post-run validation

## Output

Reports written to `directories.news_dir` as `DailyBrief-YYYY-MM-DD_vNN.md`.

Each report contains YAML frontmatter with tags, a weather section (forecast, climate normals, rainfall, lake levels), and categorized story sections with summaries and tags. Retains 5 most recent versions; older reports and logs are cleaned up.

## File Structure

```
config.yaml                 # All runtime configuration
src/daily_brief/            # Modular source code
  pipeline.py               # Async orchestrator
  sources/                  # Weather, RSS, lakes, article extraction
  llm/                      # LLM client, batch summarization, alerting
  pipelines/                # RSS deduplication and widening
  rendering/                # Report assembly, weather tables, cleanup
  config.py                 # YAML loader and defaults
  config_validator.py       # Configuration validation
  tagging.py                # Keyword tagging engine
  categorization.py         # Category ordering
tests/                      # 764 tests
PROJECT.md                  # Architecture and status
SUMMARY.md                  # Changelog
TODOS.md                    # Live task board
PLAN.md                     # Optimization strategy and findings
```

## Performance

Baseline (v1.0.67): ~105–114s internal pipeline time across 70–73 stories. LLM summarization (Phase 3) dominates at ~96–100s. Phase B optimization targets 10–20s reduction via weather and RSS concurrency.

## Tracking

See `PROJECT.md` for architecture, `PLAN.md` for active optimization strategy, and `SUMMARY.md` for changelog.

## License

MIT License
