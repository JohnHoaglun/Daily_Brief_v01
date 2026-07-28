# Project Summary: Daily_Brief_v01

## Overview
Automated daily news brief generator that fetches news from 17 content categories and produces Markdown reports with AI summaries via vLLM (OpenAI-compatible client).

## Change Log
- [2026-07-28 14:30] Version bumped to **v1.0.34** — P5 Pipeline + Config extraction complete.
- [2026-07-28 14:30] Refactor (P5) — Monolith `dashboard_pipeline.py` reduced from 1,701L → 16L (thin shim). Created `src/daily_brief/pipeline.py` (521L, `async def main()` with all 6 phases, `log()`, `_coerce_temperature_f`, `is_realt_estate_title`), `config.py` (139L, moved from project root — near-copy with `BASE_DIR` path fix), `validation.py` (150L, `validate_report()` — 5 checks: empty summary, headline repeat, min sentences, fallback markers, topic overlap), `harness.py` (77L, `run_test_harness()` — subprocess call to Test_validate_run.py). Updated `__main__.py`: imports from `daily_brief.pipeline` (not `dashboard_pipeline`). All subpackage imports fixed: `from config import` → `from daily_brief.config import` (8 files). All 6 phases and all subpackage function calls verified intact.
- [2026-07-28 03:50] Version bumped to **v1.0.32** — P3 LLM module extraction complete.
- [2026-07-28 03:50] Refactor (P3) — Created `src/daily_brief/llm/` subpackage (4 files): `client.py` (39L, `LLMClient` class, `create_llm_client()` factory, `_executor`, `_run_blocking`), `summarizer.py` (476L, `_summarize`, `batch_summarize_all`, `parse_batch_summary_response`, `build_context`, `StoryPipelineState`, `_safe_sentence_summary`, `_is_refusal`, `_is_boilerplate`, `_count_sentences`), `alerter.py` (80L, `batch_evaluate_alerts`, `parse_alert_batch_response`), `__init__.py` (re-exports). Monolith `dashboard_pipeline.py` now uses delegating wrappers, removing ~501L inline LLM code. `_llm_client` is instantiatable via `create_llm_client(model, base_url, timeout)`. Pipeline validated: 72 stories, 0 failures.
- [2026-07-28 13:09] Version bumped to **v1.0.33** — P4 rendering extraction complete.
- [2026-07-28 13:09] Refactor (P4) — Created `src/daily_brief/rendering/` subpackage (4 files): `weather_table.py` (63L, `build_weather_markdown()` — forecast, station, lake tables), `report.py` (127L, `build_markdown()`, `write_report()` — frontmatter, category sections), `cleanup.py` (50L, `cleanup_old_files()` — report + log cleanup), `__init__.py` (re-exports). Monolith `dashboard_pipeline.py` now uses delegating wrappers for weather table and cleanup. Pipeline validated: 71 stories, 0 failures.
- [2026-07-28 02:20] Version bumped to **v1.0.31** — Lake monitoring expanded from 3 to 11 lakes.
- [2026-07-28 02:20] Config (`config.yaml`) — Added 8 new lakes: `livingston`, `waco`, `ray_roberts`, `lewisville`, `ray_hubbard`, `choke_canyon`, `caddo`, `toledo_bend` (total 11 with existing 3: conroe, travis, corpus_christi).
- [2026-07-28 02:20] Refactor (`sources/weather.py`) — Changed hardcoded lake loop to iterate `WEATHER_LAKE_URLS.items()` dynamically.
- [2026-07-28 02:20] Refactor (`dashboard_pipeline.py`) — Changed hardcoded lake loop to iterate `WEATHER_LAKE_URLS` dynamically. Added `_lake_label` helper with "Lake" prefix for dynamic rendering. Test [1.4] passes.
- [2026-07-28 01:50] Version bumped to **v1.0.30** — Section count widening logic fixed.
- [2026-07-28 01:50] Fix (`dashboard_pipeline.py`) — Widening trigger changed from `added == 0` to `added < 3`, all 15 sections now render ≥3 stories.
- [2026-07-28 01:09] Version bumped to **v1.0.29** — Tag distribution goal achieved: every story has ≥3 tags.
- [2026-07-28 01:09] Fix (`tagging.py`) — Moved `min_tags=3` promotion logic *after* conflict resolution block so tags stripped by international/us-focused conflict are restored. Result: 61 stories, avg 3.90 tags, distribution `{3:30, 4:7, 5:24}`.
- [2026-07-28 00:28] Config (`config.yaml` v1.0.28-29) — Added keywords: `local` (spring, fort worth, wisconsin), `sports` (soccer, world cup, transfer, man city, player), `economy` (shares, bond, bonds, stock, wall street, imf, argentina, citic, securities, growth, upcycle), `environment` (sustainable, water, green), `people` (cup, winner, art, artist), `us-focused` (runaway, newsweek, nevada, travel, new york), `companies` (companies, time, workplace, growth, orders, 3m), `international` (soccer, world cup, imf, iran, strike, debt), `semiconductors` (asml), `government` (department, federal, agency, nist, doj), `politics` (iran, strikes). Updated `category_boosts`: OpenAI, Anthropic, SpaceX, Big Tech, Conroe, Montgomery County, Texas, Houston Weather, AI, Andrej, Hermes, Semiconductors, Space News categories.
- [2026-07-27 23:20] Refactor (`tagging.py`) — Category boosts now fire for category membership (not just keyword match). Added `min_tags=3` promotion: promotes next-best scoring tags (>0 score, even below threshold) when story has <3 tags. Last resort: category-derived fallback tags.
- [2026-07-27 22:52] Tagging improvements — v15→v16: avg tags 2.40→2.71, single-tag stories 26→20. Added keyword coverage for `local`, `tech`, `environment`, `science`.
- [2026-07-26 20:45] Version bumped to **v1.0.15** — P2 tagging + categorization extraction complete.
- [2026-07-26 20:45] Refactor (P2) — Created `src/daily_brief/tagging.py` (46L): `tag_story_with_keywords` reads `TAGGING_MAPPINGS`, `TAGGING_CONFIG`, `CATEGORY_BOOSTS` from config. Created `src/daily_brief/categorization.py` (19L): `ordered_categories_for_render` reads `CATEGORY_PRIORITY` from config. Updated `config.yaml`: added `tagging_config:` (max_tags: 5, score_cap: 5.0), `category_boosts:` (4 categories), `category_priority:` (16 categories). Updated `config.py`: added `TAGGING_CONFIG`, `CATEGORY_BOOSTS`, `CATEGORY_PRIORITY` reads. Updated monolith: delegating wrappers + removed ~97L inline keyword dict. Fixed tag_story_with_keywords and ordered_categories_for_render in monolith to import from new modules.
- [2026-07-26 15:25] Version bumped to **v1.0.14** — P2 data sources split complete.
- [2026-07-26 15:25] Refactor (P2) — Created `src/daily_brief/sources/` subpackage (6 modules, 975 SLOC total): `climate.py` (179L, `_fetch_climate_normal_high`, `_parse_climate_summary`), `lakes.py` (97L, `_extract_lake_value`), `wunderground.py` (185L, `_fetch_station_metrics`, `_fetch_station_monthly_rainfall`, `_parse_wu_monthly_precipitation`), `rss.py` (151L, `build_rss_url`, `fetch_feed`, `normalize_title`, `parse_feed_date`, `format_pub_date`, `_sort_entries`), `article.py` (76L, `stage_extract_article`, `build_context`), `weather.py` (262L, `fetch_weather` orchestrator + helpers). Extended `utils.py` with `_extract_first_match`, `is_obituary_title`, `is_realt_estate_title`. Fixed `http_client.py` with proper `user_agent` param and `**params` passthrough. Migrated ~26 `log()` calls to Python `logging`. Fixed duplicate climate normal call (dead code at monolith line 988). Full pipeline validated: 56 stories, 0 errors, 85.6s.
- [2026-07-26 16:35] Version bumped to **v1.0.13** — P1 foundation extraction complete.
- [2026-07-26 16:30] Refactor (P1) — Created `src/daily_brief/` package (5 files): `__init__.py` (re-exports), `__main__.py` (entry point with `RotatingFileHandler`), `models.py` (6 dataclasses: Story, WeatherData, LakeData, AlertResult, ForecastPeriod, BriefOutput), `utils.py` (7 helpers: _safe_text, strip_html, _present_weather_value, _clean_number, _safe_sentence_summary, _count_sentences, _coerce_percent), `http_client.py` (async _fetch_json, _fetch_text, session management). All modules use standard Python `logging` throughout. Full import chain verified.
- [2026-07-26 16:25] Version bumped to **v1.0.12** — P0 cleanup applied (dead code, duplicate function, typo fix).
- [2026-07-26 16:20] Cleanup (P0) — Deleted dead code at `dashboard_pipeline.py:365-376` (12-line orphaned function body). Removed duplicate `is_obituary_title` at line 1561 (canonical at 358). Fixed typo `wundereground` → `wunderground` in `config.py:120`. Line count: 1944 → 1921. Full pipeline verified: 55 stories, 0 failures.
- [2026-07-26 03:30] Plan — Adopted comprehensive refactoring plan (P0-P6): modularize 1,942-line monolith into 18 files (40-250 lines each), add testing framework (4 tiers), add config validation + CLI management. Target: 35 hours total across 9 phases. Version bumped to **v1.0.11**.
- [2026-07-26 03:25] Fix — Removed unconditional "fallback-applied" log. Climate normal (Open-Meteo ERA5) now called before any forecast fallback. "Weather OK" summary properly detects `(fallback)` markers and reports PARTIAL.
- [2026-07-26 02:54] Feature — Added Open-Meteo ERA5 climate normal fetch for `avg_temp_today` (replaces Wunderground's inaccurate daily-high approximation). Uses `temperature_2m_max` with UTC date sync. Weather labels driven by `config.yaml:weather_labels.station_rows` (commit 299f4a0).
- [2026-07-26 02:32] Refactor — Switched from `import ollama` to `from openai import OpenAI`. Client init uses `base_url=...`, `timeout=180`. Removed `num_ctx` from `config.yaml` summary/alert options (vLLM rejects in API payload). Updated LLM response parsing from `r["message"]["content"]` to `r.choices[0].message.content`. Config defaults: `llm_model: "gemma4-e2b"` (commit cb52c50).
- [2026-07-26 02:10] Fix — Rewrote `_fetch_station_metrics` with BeautifulSoup table parser (commit df49693). Replaces broken regex that misread "Elev 187 ft" as temperature. Verified: `avg_temp_today=83.3°F`, `current_monthly_rainfall=7.42 Inches`.
- [2026-07-26 02:10] Fix — Updated "Weather OK" summary line to report "Weather PARTIAL" when any station value is "Unavailable" or fallback-derived (commit a72e559).
- [2026-07-26 02:10] Cleanup — Deleted debug scripts: `debug_station.py`, `debug_tables.py`, `test_station.py`.
- [2026-07-26 02:10] Verification — Ran full pipeline end-to-end: 55 stories, 0 failures, real station data throughout, no extreme-temperature warnings. Pipeline time: 10.4s. Bumped to **v1.0.10**.
- [2026-07-24 00:15] Fix - Resolved NameError in dashboard_pipeline.py (DEFAULT_CATEGORIES_COUNT) and verified end-to-end execution; version bumped to **v1.0.9**
- [2026-07-18 20:00] Release - Documentation and validation backlog closure completed; version bumped to **v1.0.7**
- [2026-07-18 19:35] Fix - Station metrics corrected to use live monthly average and current monthly totals from wunderground summary
- [2026-07-18 18:15] Fix - Lake trend table now reports separate values for Today / 1 Week Ago / 30 Days Ago
- [2026-07-18 16:05] Fix - Weather section order aligned to requirements examples (Example1/Example2)
- [2026-07-18 15:35] Fix - Weather summaries changed to 3-sentence format with dynamic content
- [2026-07-12 22:20] Feature - Fixed configuration loading issue in dashboard_pipeline.py by changing config.VERSION to VERSION in line 604
- [2026-07-12 22:20] Feature - Improved robustness of config.py to better handle multiple parsing scenarios
- [2026-07-12 22:20] Refactor - Created fallback category definitions in config.py for when complex parsing fails
- [2026-07-12 22:20] Version bump - Updated to v1.0.1
- [2026-07-13 17:00] Release - Tagged v1.0.1 and pushed to dev branch
- [2026-07-13 17:30] Fix - Removed all hardcoded fallback values from dashboard_pipeline.py
- [2026-07-13 17:30] Fix - Improved CATEGORIES dictionary parsing in config.py
- [2026-07-13 17:30] Release - Tagged v1.0.2 and pushed to dev branch
- [2026-07-13 19:30] Fix - Resolved configuration parsing bug that was preventing pipeline execution
- [2026-07-13 19:30] Release - Tagged v1.0.3 and pushed to dev branch
- [2026-07-13 20:00] Documentation - Updated all comments with detailed explanations of pipeline functionality and performance characteristics
- [2026-07-14 02:00] Enhancement - Implemented comprehensive enhanced tagging system with multi-tagging capabilities
- [2026-07-14 02:00] Enhancement - Extended keyword mapping to include specialized categories
- [2026-07-14 02:00] Release - Tagged v1.0.5 and pushed to dev branch

## Status
Fully functional and working correctly. The pipeline produces daily reports with validated dynamic weather sections, improved summary constraints, and config-driven behavior.


