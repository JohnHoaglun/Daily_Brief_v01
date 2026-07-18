# Daily Brief v1.0.0 - Weather Migration & Config Hardening Plan

## Done
- [x] Refactored `config.py` loader to parse multiline dict/list values in `config.txt`.
- [x] Added runtime constants to `config.py` for prompts, context/summary limits, thresholds, frontmatter defaults, and weather source metadata.
- [x] Added matching values in `config.txt` (weather sources, lake URLs, WunderGround config, prompt/options defaults, tag defaults, cleanup defaults).
- [x] Removed hardcoded:
  - `ZoneInfo("America/Chicago")` → `ZoneInfo(TIMEZONE)`.
  - hardcoded frontmatter `content_age_window` and `categories`.
  - hardcoded tag seed/fallback values.
  - hardcoded cleanup limit `5` for daily/log retention.
  - hardcoded summary fallback tag.
- [x] Repaired `batch_summarize_all` context loop indentation and `parse_feed_date` indentation bug so parser no longer has syntax-risk.
- [x] Wired alert batch to use `SYSTEM_ALERT_PROMPT` config value.
- [x] Implemented dynamic weather fetch orchestration (forecast + station + lake) in `dashboard_pipeline.py`.
- [x] Added dynamic date-label utility for Today/Tomorrow/In 2 Days using `DATE_OVERRIDE`/timezone-aware current date.
- [x] Added weather markdown render block at top of output with forecast, station metrics, and lake percentages.
- [x] Added fallback-safe weather parsing so missing data returns `"Dynamic"` placeholders instead of crashing.

## To do (small, incremental)
1. [x] Re-scan and replace remaining static weather strings in `dashboard_pipeline.py` with config-driven values (`WEATHER_*`, `USER_AGENT_*`, `DATE_OVERRIDE`).
2. [x] Add a single utility for run-date labels (`Today`, `Tomorrow`, `In 2 Days`) sourced from system date / `DATE_OVERRIDE`.
3. [x] Implement 3-day forecast parser in `dashboard_pipeline.py`:
   - map date labels dynamically,
   - extract Day/Night/High/Low/Precip/Wind fields.
4. [x] Implement station metrics parser:
   - average temp today,
   - monthly avg rainfall for 77316,
   - current monthly rainfall total from `WEATHER_WUNDERGROUND_STATION_ID`.
5. [x] Implement lake metrics parser for:
   - today,
   - 1 week ago,
   - 30 days ago,
   using `WEATHER_LAKE_URLS`.
6. [x] Render `## Weather for 77316` section in markdown in the same block order as `Example1.md` / `Example2.md`.
7. [x] Add failure-safe fallbacks:
   - log warning when any weather source fails,
   - write explicit fallback values instead of blank cells.
8. [ ] Add a targeted validation pass:
   - compare produced file structure to `Requirements/DailyBrief-Weather Example2.md` placeholders then `Example1.md`,
   - ensure section order, tag behavior, and frontmatter keys match.
9. [ ] Add small parser-level tests/fixtures for forecast, wunderground, and lake pages.
10. [ ] Update any docs (`PROJECT`/`README`/`PLAN`) with config keys and required weather input URLs.

