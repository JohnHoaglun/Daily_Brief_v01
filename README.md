# Daily Brief v1.0.143
Automated daily news brief generator that fetches stories from 17 configured categories via Google News RSS, enriches them with weather and lake-level data, summarizes them with AI, and produces a structured Markdown report.

## Architecture

Modular codebase in `daily_brief/`:

- **`pipeline.py`** — asynchronous orchestrator (6 phases: weather, RSS, LLM, render, validate, test harness)
- **`sources/`** — NWS forecast, Wunderground station metrics, Open-Meteo/ERA5 climate normals, Texas reservoir levels, RSS feeds, and article extraction
- **`llm/`** — OpenAI-compatible client (AsyncOpenAI), configurable batch-of-N summarization with semaphore-concurrency (default: `batch_size=4`, `max_concurrency=2`), boilerplate/refusal detection, auto fallback, structured metrics
- **`pipelines/rss_dedup.py`** — RSS filtering, deduplication, and widening
- **`rendering/`** — weather table generation, Markdown report assembly, output cleanup
- **`config.py` / `config_validator.py`** — YAML-based configuration, loading, and validation
- **`categorization.py`** — config-driven keyword tagging, category ordering
- **`tagging.py`** — keyword tagging engine with precompiled regex cache
- **`models.py`** — typed data models: `Story`, `HarnessResult`
- **`utils.py`** — shared utilities: sentence extraction, context building, temperature coercion
- **`http_client.py`** — centralized HTTP request helpers with retry/backoff
- **`tests/`** — 402 deterministic tests (unit, mocked, integration, post-run validation; 402 passing)

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
3. Run: `python3 dashboard_pipeline.py`

## Configuration

All runtime settings in `config.yaml`. Key groups:

| Key | Description | Configured Value |
|---|---|---|
| `version` | Pipeline version | `1.0.143` |
| `llm.model` | Model for summarization | `gemma4-e2b` |
| `llm.host` | vLLM API endpoint | `http://192.168.4.52:8007` |
| `directories.log_dir` | Log output directory | `.../Shared_AI/vault/OpenCode/Daily_Brief_v01/Dev/logs` |
| `directories.news_dir` | Report output directory | `.../Shared_AI/vault/OpenCode/Daily_Brief_v01/Dev/news` |
| `weather.lat` / `weather.lon` | Weather location | `30.286, -95.566` (Houston) |
| `weather.wunderground_station_id` | Wunderground station | `KTXMONTG645` |
| `categories.*` | 16 news categories with queries and limits | see `config.yaml` |
| `tagging_mappings.*` | Keyword-to-tag mappings | 20+ categories |

## Pipeline Phases

1. **Weather** — async fetch of NWS forecast, station metrics, climate normals, lake levels
2. **RSS** — 17 Google News RSS feeds, concurrent fetch, deduplication, date filtering
3. **LLM** — article extraction, batch-of-N summarization (configurable `batch_size`/`max_concurrency`), async retry, boilerplate detection, auto fallback
4. **Render** — Markdown assembly with frontmatter, weather tables, categorized sections
5. **Validate** — internal report validation (story count, fallback thresholds)
6. **Test harness** — external post-run validation

## Output

Reports written to `directories.news_dir` as `DailyBrief-YYYY-MM-DD_vNN.md`.

Each report contains YAML frontmatter with tags, a weather section (forecast, climate normals, rainfall, lake levels), and categorized story sections with summaries and tags. Retains 5 most recent versions; older reports and logs are cleaned up.

## File Structure

```
config.yaml                 # All runtime configuration
daily_brief/                # All source code (root package)
  pipeline.py               # Async orchestrator
  sources/                  # Weather, RSS, lakes, article extraction
  llm/                      # LLM client, batch summarization
  pipelines/                # RSS deduplication and widening
  rendering/                # Report assembly, weather tables, cleanup
  config.py                 # YAML loader and defaults
  config_validator.py       # Configuration validation
  tagging.py                # Keyword tagging engine
  categorization.py         # Category ordering
  validation_harness.py     # Post-run validation (was Test_validate_run.py)
  benchmark_llm_batches.py  # LLM batch benchmark harness
  capture_corpus.py         # Corpus capture utility
tests/                      # 402 tests (402 passing)
PROJECT.md                  # Architecture and status
SUMMARY.md                  # Changelog
TODOS.md                    # Live task board
```

## Performance

- Baseline: ~105-114 seconds of internal pipeline time across 70-73 stories, with Phase 3 LLM summarization consuming ~96-100 seconds.
- Adopted batch scheduling: Phase 3 median 43.4 seconds, down from 97.7 seconds (55.6% faster), using `batch_size=4` and `max_concurrency=2`.
- Benchmark and corpus-capture utilities remain available as explicit module commands for performance investigations.

## Module Commands

```bash
python3 -m daily_brief  # main pipeline
python3 -m daily_brief.validation_harness --help
python3 -m daily_brief.capture_corpus --help
python3 -m daily_brief.benchmark_llm_batches --help
```

## Tracking

See `PROJECT.md` for architecture and current status, `SUMMARY.md` for the complete release changelog, and `TODOS.md` for the active backlog.

## License

MIT License
