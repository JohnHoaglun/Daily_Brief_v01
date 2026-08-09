# Daily Brief v1.0.117
Automated daily news brief generator that fetches stories from 17 configured categories via Google News RSS, enriches them with weather and lake-level data, summarizes them with AI, and produces a structured Markdown report.

## Architecture

Modular codebase in `src/daily_brief/`:

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
- **`tests/`** — 1039 tests (unit, mocked, integration, smoke, post-run validation; 1039 passing, 21 smoke deselected)

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
| `version` | Pipeline version | `1.0.117` |
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
src/daily_brief/            # Modular source code
  pipeline.py               # Async orchestrator
  sources/                  # Weather, RSS, lakes, article extraction
  llm/                      # LLM client, batch summarization
  pipelines/                # RSS deduplication and widening
  rendering/                # Report assembly, weather tables, cleanup
  config.py                 # YAML loader and defaults
  config_validator.py       # Configuration validation
  tagging.py                # Keyword tagging engine
  categorization.py         # Category ordering
tests/                      # 1039 tests (1039 passing, 21 smoke deselected)
PROJECT.md                  # Architecture and status
SUMMARY.md                  # Changelog
TODOS.md                    # Live task board
PLAN.md                     # Optimization strategy and findings
reports/                    # Benchmark results and performance data
```

## Performance

- v1.0.67 baseline: ~105–114s internal pipeline time across 70–73 stories. LLM summarization (Phase 3) dominates at ~96–100s.
- v1.0.94 (C.2a adopted): Phase 3 median 43.4s (from 97.7s baseline) — 55.6% speedup via `batch_size=4`, `max_concurrency=2`. Quality: zero invalid/boilerplate/refusal/exceptions across 24 benchmark runs.
- v1.0.95 (C.4): centralized batch retry, single-story recovery, and structured `SummaryMetrics`. Pipeline Phase 3D/3E duplicate recovery loops removed (−57 lines). Transient batch failures now retried as full batches before falling to individual recovery.
- v1.0.96 (C.3): centralized HTTP retry/status — bounded 3-attempt retry with async backoff for transient failures (502/503/504/429/timeout). RSS routed with 2xx acceptance; article extraction gated to exact-200 before parsing. Weather/climate/lakes/Wunderground inherit retry automatically (zero caller changes).
- v1.0.97 (C.5): retired the dormant alert feature — removed `llm/alerter.py` and all alert references. 925 tests (924 passing, 1 pre-existing), config validate PASS.
- v1.0.98 (D.1): unified config schema — nested `DEFAULTS`, `_get_nested()` helper, single YAML read. Config validator validates canonical `llm.*`/`network.*`/`runtime.*` paths. Pipeline uses explicit imports.
- v1.0.99 (D.2): promoted `Story` to 7-field typed dataclass. Replaced `StoryPipelineState` with alias. All consumers use keyword construction. Deleted unused fields.
- v1.0.100 (D.3): canonicalized 4 duplicate utility functions — `_safe_sentence_summary`, `_count_sentences`, `build_context`, `_coerce_temperature_f` — consolidated in `utils.py`. 921 tests (2 pre-existing), config validate PASS.
- v1.0.101 (D.4): added 32 parser golden fixture tests for `parse_batch_summary_response()` (15 format fixtures + 17 edge cases). 953 tests (2 pre-existing), config validate PASS.
- v1.0.102 (D.5): tagging precompilation — `precompile_tagging()` builds 410 precompiled regex pairs at startup. Single tag computation per story via `id(st)` cache, reused for frontmatter + body. 953/955 tests (2 pre-existing), config validate PASS.
- v1.0.103 (D.6): Bug-7 — NWS `forecast` URL safe suffix. Bug-8 — `station_rows` safe indexing with `len()` guard. Bug-11 — version alignment across all sources. 954/956 tests (2 pre-existing), config validate PASS.
- v1.0.104 (D.7): typed `HarnessResult` dataclass. Weather errors surfaced in pipeline log. Declarative `CHECK_LIST`/`SMOKE_TEST_CHECKS` + `_wrapped()` helper. 954/956 tests passing, config validate PASS.
- v1.0.105 (D.8): startup crash fix — `log()` guarded against `RUN_LOGFILE=None` before logfile init. Early logs write stderr only. 954/956 tests (2 pre-existing), config validate PASS.
- v1.0.106 (D.9): startup integration test — `TestStartupSequence` runs real `pipeline.main()` through Phase 4 with deterministic boundary mocks. Removed obsolete `TestPipelineCreatesDirs`. 955/956 tests (1 pre-existing), config validate PASS.
- v1.0.107 (Quality-7): fixed `TestConfigUncoveredBranches` module state leak — `importlib.reload` with mocked `yaml.safe_load` left `TIMEZONE="UTC"` and stale categories, causing `test_zoneinfo_uses_configured_timezone` to fail when run after config tests. Added `tearDownClass` to restore real YAML config. 956/956 tests passing (0 pre-existing), config validate PASS.
- v1.0.108 (Harness): shared log/report version identity — `compute_output_path()` now accepts explicit `file_ver` from the pipeline. Run log and report share the same version number, so Phase 6 harness finds the correct report. 959/959 tests passing (0 pre-existing), config validate PASS, pipeline smoke test harness validates actual report.
- v1.0.112 (Summarizer): added topic-alignment guard. 977/984 tests passing (7 pre-existing RSS dedup), config validate PASS.
- v1.0.115 (P0): pipeline exit-code contract — 0=PASS, 1=WARN/CONFIG, 2=FAIL/VALIDATION, 3=ERROR/SKIPPED. 991/991 tests passing.
- v1.0.116 (P1): summary recovery correctness — canonical `_is_valid_summary()` gate for batch and recovery. 1009/1009 tests passing.
- v1.0.117 (P1): config safety (raw loader, typed builder, CLI imports), validator hardening, LLM core (`max_retries=0`, `aclose()`, recovery concurrency=2, deadline), weather rendering resilience, 63 async mock migrations, test validity fixes. 1039/1039 tests passing (21 smoke deselected), 0 warnings.

## Tracking

See `PROJECT.md` for architecture, `PLAN.md` for active optimization strategy, and `SUMMARY.md` for changelog.

## License

MIT License
