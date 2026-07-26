# TODO: Daily Brief v01 — v1.0.13

## Status Legend
- `[ ]` — TODO (not started)
- `[~]` — IN_PROGRESS (actively being worked)
- `[!]` — BLOCKED (waiting on something external)
- `[x]` — DONE (completed and verified)

---

## Active Work: Architectural Refactoring

### P0 — Immediate Cleanup (Priority: Critical, Effort: 15 min, Risk: Zero)
- `[x]` Delete dead code at `dashboard_pipeline.py:365-376` (orphaned function body, no definition)
- `[x]` Remove duplicate `is_obituary_title` at `dashboard_pipeline.py:1561` (first definition at line 358)
- `[x]` Fix typo `config.py:120` — `wundereground_station_id` → `wunderground_station_id`
- `[x]` Delete `debug_climate.py` (dead debug script) — already deleted in commit `72e15d2`

### P1 — Foundation Extraction (Priority: High, Effort: 3 hrs, Risk: Zero)
- `[x]` Create `daily_brief/` package — `__init__.py`, `__main__.py` (src/daily_brief/)
- `[x]` Extract `utils.py` — `_safe_text`, `strip_html`, `_present_weather_value`, `_clean_number`, `_safe_sentence_summary`, `_count_sentences`, `_coerce_percent`
- `[x]` Extract `models.py` — dataclasses: `Story`, `WeatherData`, `LakeData`, `AlertResult`, `ForecastPeriod`, `BriefOutput`
- `[x]` Extract `http_client.py` — `_fetch_json`, `_fetch_text`, aiohttp session management
- `[x]` Replace custom `log()` with standard Python `logging` + `RotatingFileHandler` in all new modules

### P2 — Data Sources Split (Priority: High, Effort: 6 hrs, Risk: Low)
- `[ ]` Create `sources/` package — `__init__.py`, `base.py` (DataSource ABC)
- `[ ]` Extract `sources/weather.py` (250L) — NWS forecast fetch + parse, `_parse_climate_summary`
- `[ ]` Extract `sources/wunderground.py` (120L) — station metrics scraping
- `[ ]` Extract `sources/climate.py` (80L) — Open-Meteo ERA5 + climate.gov normals
- `[ ]` Extract `sources/lakes.py` (80L) — reservoir level extraction
- `[ ]` Extract `sources/rss.py` (150L) — feedparser + Google News URL building + dedup + filtering
- `[ ]` Extract `sources/article.py` (60L) — full article content extraction
- `[ ]` Fix `tagging.py` to read from `config.yaml:tagging_mappings` instead of inline dict
- `[ ]` Fix `ordered_categories_for_render` to use `config.yaml:category_priority` instead of hardcoded list

### P3 — LLM Module (Priority: High, Effort: 2 hrs, Risk: Low)
- `[ ]` Extract `llm/client.py` (80L) — OpenAI client wrapper, retry logic, per-call timeout
- `[ ]` Extract `llm/summarizer.py` (150L) — `batch_summarize`, context building, response parsing
- `[ ]` Extract `llm/alerter.py` (60L) — `batch_evaluate_alerts`, alert response parsing
- `[ ]` Make `_llm_client` instantiatable (not global singleton) for testability

### P4 — Rendering (Priority: Medium, Effort: 3 hrs, Risk: Low)
- `[ ]` Extract `rendering/weather_table.py` (80L) — weather markdown table generation
- `[ ]` Extract `rendering/report.py` (150L) — full report assembly + frontmatter
- `[ ]` Extract `rendering/cleanup.py` (60L) — old file cleanup logic

### P5 — Pipeline + Config (Priority: Medium, Effort: 4 hrs, Risk: Medium)
- `[ ]` Extract `pipeline.py` (200L) — orchestrator only (phases, no business logic)
- `[ ]` Extract `config.py` (120L) — load + validate config.yaml → Config dataclass, drop `globals().update()`
- `[ ]` Create `main.py` (30L) — entry point: `if __name__ == "__main__": asyncio.run(pipeline.main())`
- `[ ]` Delete `dashboard_pipeline.py` — all functions migrated

### P6 — Config Management & Validation (Priority: High, Effort: 2 hrs, Risk: Zero)
- `[ ]` Add config validation — check required keys, types, value ranges at startup
- `[ ]` Make `tagging.py` read from `config.yaml:tagging_mappings` (not inline dict)
- `[ ]` Make `ordered_categories_for_render` use `config.yaml:category_priority` (not hardcoded)
- `[ ]` Add CLI config command — `python -m daily_brief config show|validate|set|add-category`

---

## Testing Strategy

### Tier 1: Unit Tests (Fast, No Network)
- `[ ]` `tests/test_config.py` — YAML loads, required keys present, types correct, key typos caught, defaults applied
- `[ ]` `tests/test_utils.py` — `_safe_text`, `strip_html`, number parsing edge cases
- `[ ]` `tests/test_tagging.py` — keywords match config.yaml, scoring works, tag thresholds correct
- `[ ]` `tests/test_weather_table.py` — markdown table renders correctly with/without data, "Unavailable" handled
- `[ ]` `tests/test_report.py` — frontmatter correct, categories in priority order, 0-story categories omitted
- `[ ]` `tests/test_summarizer.py` — response parsing with mock LLM output, batch splitting, context truncation
- `[ ]` `tests/test_alerter.py` — alert format parsing, TRUE/FALSE extraction per story

### Tier 2: Source Tests (Mocked Network with `aioresponses`)
- `[ ]` `tests/test_sources/test_weather.py` — NWS forecast JSON parsed, date/period extraction, "Unavailable" on empty
- `[ ]` `tests/test_sources/test_wunderground.py` — station table scraping with sample HTML, precipitation row matching
- `[ ]` `tests/test_sources/test_climate.py` — Open-Meteo JSON parsed, climate.gov text parsed, timezone/date handling
- `[ ]` `tests/test_sources/test_lakes.py` — reservoir percentage extraction with sample HTML
- `[ ]` `tests/test_sources/test_rss.py` — feed parsing, age filtering, title dedup, real estate/obituary filtering

### Tier 3: Integration (Smoke + Validation, Every Run)
- `[ ]` Implement `smoke_test()` — can we reach every endpoint before pipeline runs? (NWS, Open-Meteo, vLLM, Google News, Wunderground, Lakes)
- `[ ]` Implement `validate_report()` — post-run assertions: frontmatter, weather section, no "Dynamic"/"Unavailable", story count, alert count plausible, no duplicate URLs, file size reasonable
- `[ ]` Add `scripts/run_tests.sh` — full pytest suite runner

### Tier 4: Coverage Target
| Area | Target |
|---|---|
| Config loading + validation | 95% |
| Weather parsing | 90% |
| RSS dedup + filtering | 90% |
| LLM response parsing | 90% |
| Markdown rendering | 95% |
| Pipeline orchestration | 80% (integration) |

---

## Completed Work

### Weather Station Fix — v1.0.10 (2026-07-25 to 2026-07-26)
- `[x]` Fix `SyntaxError` in `dashboard_pipeline.py` from broken indentation (Fixed: 2026-07-25 session 1)
- `[x]` Restore working regex patterns from `main` branch (commit 1833c3a)
- `[x]` Rewrite `_fetch_station_metrics` with BeautifulSoup table parser (commit df49693)
- `[x]` Fix "Weather OK" summary line — report PARTIAL when fallback applied (commit a72e559)
- `[x]` Run full pipeline end-to-end — verified real station data, no fallback misreporting
- `[x]` Clean up debug scripts: `debug_station.py`, `debug_tables.py`, `test_station.py` — deleted
- `[x]` `batch_evaluate_alerts` SyntaxError — already resolved in previous session
- `[x]` Switch from Ollama to OpenAI client, remove `num_ctx` (commit cb52c50)
- `[x]` Add Open-Meteo ERA5 climate normal for `avg_temp_today` (commit 6e00e46)
- `[x]` Move weather labels to `config.yaml:weather_labels.station_rows` (commit 299f4a0)
- `[x]` Fix "fallback-applied" log — only logs "partial/missing" when fallback actually used (commit TBD, session 2026-07-26 round 2)
- `[x]` Fix "Weather OK" summary — detects `(fallback)` markers, reports PARTIAL instead of OK (commit TBD, session 2026-07-26 round 2)

---

## Config UI Options (Deferred to After P5)

### Option A: CLI Config Manager (Recommended First)
```
python -m daily_brief config show                # Display current config
python -m daily_brief config validate            # Validate + report errors
python -m daily_brief config set weather.lat 30.286
python -m daily_brief config add-category "Name" "query" --max 10
python -m daily_brief config list-sources        # Show enabled data sources
```
**Pros:** No new deps, fits terminal workflow, works remotely, validates before run. (~2 hours)

### Option B: Web UI (Gradio/Streamlit)
```
python -m daily_brief dev    # Opens localhost:7860
```
Visual YAML editor, live validation, markdown preview, last run results dashboard.
**Pros:** Visual, can preview rendering, extensible. **Cons:** New dependency, requires browser, overkill for now. (~6 hours)

---

## Proposed File Structure (Target After P5)

```
Daily_Brief_v01/
├── config.yaml                          # Unchanged
├── main.py                              # Entry point (30L)
│
├── daily_brief/
│   ├── __init__.py                      # Package exports
│   ├── __main__.py                      # python -m daily_brief
│   ├── config.py                        # (120L) Load + validate config.yaml → Config dataclass
│   ├── models.py                        # (80L)   Story, WeatherData, LakeData dataclasses
│   ├── cli.py                           # (100L)  CLI arguments, run invocation
│   ├── utils.py                         # (80L)   _safe_text, strip_html, helpers
│   ├── tagging.py                       # (100L)  tag_story_with_keywords (reads config)
│   ├── http_client.py                   # (80L)   aiohttp session, _fetch_json, _fetch_text
│   │
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── base.py                      # (40L)   DataSource ABC
│   │   ├── weather.py                   # (250L)  NWS forecast fetch + parse
│   │   ├── wunderground.py              # (120L)  Station metrics scraping
│   │   ├── climate.py                   # (80L)   Open-Meteo ERA5 + climate.gov
│   │   ├── lakes.py                     # (80L)   Reservoir level extraction
│   │   ├── rss.py                       # (150L)  feedparser + dedup
│   │   └── article.py                   # (60L)   Article content extraction
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py                    # (80L)   OpenAI client wrapper, retries
│   │   ├── summarizer.py                # (150L)  Batch summarize, context building
│   │   └── alerter.py                   # (60L)   Batch alert evaluation
│   │
│   ├── rendering/
│   │   ├── __init__.py
│   │   ├── weather_table.py             # (80L)   Weather markdown table
│   │   ├── report.py                    # (150L)  Full report assembly + frontmatter
│   │   └── cleanup.py                   # (60L)   Old file cleanup
│   │
│   └── pipeline.py                      # (200L)  Orchestrator only — phases, no logic
│
├── tests/
│   ├── conftest.py                      # Fixtures, mocks, shared config
│   ├── test_config.py
│   ├── test_http_client.py
│   ├── test_tagging.py
│   ├── test_sources/
│   ├── test_llm/
│   ├── test_rendering/
│   └── test_pipeline.py
│
└── scripts/
    └── run_tests.sh
```

**Every file: 40-250 lines. Largest is `pipeline.py` at ~200. Current `dashboard_pipeline.py`: 1,942 lines → goal: 100-250 lines.**

---

## Relevant Files
- `/Users/johnhoaglun/opencode/projects/Daily_Brief_v01/dashboard_pipeline.py` — 1,942 line monolith (currently)
- `/Users/johnhoaglun/opencode/projects/Daily_Brief_v01/config.py` — 136 lines (mixed concerns)
- `/Users/johnhoaglun/opencode/projects/Daily_Brief_v01/config.yaml` — 176 lines
- `/Users/johnhoaglun/opencode/projects/Daily_Brief_v01/debug_climate.py` — 26 lines (delete)

---

## Recent Updates
- [2026-07-26 16:30] **P1 foundation extraction complete** — Created `src/daily_brief/` package (5 files): `__init__.py`, `__main__.py`, `models.py` (6 dataclasses), `utils.py` (7 helpers), `http_client.py` (async fetch). All imports verified. Logging uses standard Python `logging` throughout.
- [2026-07-26 16:20] **P0 cleanup complete** — Deleted dead code (12 lines), removed duplicate `is_obituary_title` (11 lines), fixed typo `wundereground` → `wunderground` in `config.py`. Full pipeline verified: 55 stories, 0 failures. Line count: 1944 → 1921.
- [2026-07-26 03:30] **Refactoring plan added** — Full modularization plan (P0-P6), testing strategy (Tiers 1-4), config UI options, proposed file structure. Target: 18 files, 40-250 lines each. ~35 hours total.
- [2026-07-26 03:25] **Weather fallback fix** — Removed unconditional "fallback-applied" log. Climate normal (Open-Meteo ERA5) now called before any forecast fallback. "Weather OK" summary properly detects fallback markers and reports PARTIAL.
- [2026-07-26 03:05] **ERA5 climate normal restored** — `_fetch_climate_normal_high` back in flow, UTC date sync with report date. Labels moved to `config.yaml:weather_labels.station_rows` (commit 299f4a0).
- [2026-07-26 02:32] **Ollama → OpenAI client** — `vLLM` integration with OpenAI-compatible client. Removed `num_ctx` from config (commit cb52c50).
- [2026-07-26 02:10] **ALL WEATHER FIXES COMPLETED — v1.0.10** — BeautifulSoup table parser (df49693), PARTIAL weather status (a72e559), full pipeline verified. Version bumped to v1.0.10 (commit 385afb8).
- [2026-07-25 01:30] **FIX RESTORED (committed 1833c3a)** — Restored working regex patterns and merge logic from `origin/main`.
- [2026-07-24 00:15] Fix resolved NameError crashes (`DEFAULT_CATEGORIES_COUNT`), verified e2e; version bumped to v1.0.9

---

## Version Notes
- Current version: **v1.0.13** (P1 complete — foundation extracted)
- Last stable: v1.0.12 (P0 cleanup complete, 2026-07-26)
- Branch: `dev_opencode`, ahead of `origin/dev_opencode`
