# Daily Brief v1.0.7 - Weather Migration & Config Hardening

## Done
- [x] Refactored `config.py` loader to parse multiline dict/list values in `config.txt`.
- [x] Added runtime constants to `config.py` for prompts, context/summary limits, thresholds, frontmatter defaults, and weather source metadata.
- [x] Added matching values in `config.txt` (weather sources, lake URLs, WU config, prompt/options defaults, tag defaults, cleanup defaults).
- [x] Removed hardcoded weather and date behaviors from pipeline logic (Zoneint, tags, cleanup limits, summary fallback tags, etc.).
- [x] Repaired `batch_summarize_all` context loop indentation and `parse_feed_date` indentation bug.
- [x] Wired alert batch to use `SYSTEM_ALERT_PROMPT`.
- [x] Implemented dynamic weather fetch orchestration (forecast + station + lake) in `dashboard_pipeline.py`.
- [x] Added run-date labels for Today / Tomorrow / In 2 Days via `DATE_OVERRIDE`/timezone.
- [x] Added weather markdown block at top of output with forecast, station metrics, and lake percentages.
- [x] Enforced 3-sentence summary output format and ensured weather headlines are not reused as summaries.
- [x] Fixed weather section order to align with `Requirements/DailyBrief-Weather Example1.md` and `Example2.md`.
- [x] Fixed station metrics parsing:
  - `Average Temperature for 77316`
  : `Average Monthly rainfall for 77316`
  - `Current Monthly rainfall for 77316` (from wunderground monthly summary URL)
- [x] Fixed lake trend extraction to return separate values for Today / 1 Week Ago / 30 Days Ago for each lake.
- [x] Documented new run/version details and requirements in project markdown files.
- [x] All items from previous cleanup backlog removed.
- [x] Added Windows paths (commented out) and Mac paths to `config.txt` for cross-platform testing.

## To do
- [ ] Migrate configuration format from custom text parsing to YAML (using `PyYAML`)
- [ ] Move all hardcoded constants and static items from `dashboard_pipeline.py` and `config.py` into `config.yaml`
- [ ] Refactor `dashboard_pipeline.py` by decomposing it into specialized modules: `rss_service.py`, `weather_service.py`, `llm_service.py`, and `report_generator.py`
- [ ] Implement Python Dataclasses or Pydantic models for RSS stories, Weather, and Lake data to replace tuple/dict structures
- [ ] Transition weather/climate scraping from Regex to CSS selectors (using BeautifulSoup)
- [ ] Encapsulate blocking LLM calls within an `LLMService` with a unified `async` interface
- [ ] Replace custom `log()` function with standard Python `logging` module and `RotatingFileHandler`

## Version Notes
- `README`, `PROJECT`, `SUMMARY`, and `PLAN` now aligned to **v1.0.7**.
