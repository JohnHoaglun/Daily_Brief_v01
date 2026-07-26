# Project Summary: Daily_Brief_v01

## Overview
Automated daily news brief generator that fetches news from 17 content categories and produces Markdown reports with AI summaries via vLLM (OpenAI-compatible client).

## Change Log
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


