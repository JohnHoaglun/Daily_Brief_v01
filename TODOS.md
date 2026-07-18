# Daily Brief v1.0.6 - Weather Migration & Config Hardening

## Done
- [x] Refactored `config.py` loader to parse multiline dict/list values in `config.txt`.
- [x] Added runtime constants to `config.py` for prompts, context/summary limits, thresholds, frontmatter defaults, and weather source metadata.
- [x] Added matching values in `config.txt` (weather sources, lake URLs, WU config, prompt/options defaults, tag defaults, cleanup defaults).
- [x] Removed hardcoded weather and date behaviors from pipeline logic (ZoneInfo, tags, cleanup limits, summary fallback tags, etc.).
- [x] Repaired `batch_summarize_all` context loop indentation and `parse_feed_date` indentation bug.
- [x] Wired alert batch to use `SYSTEM_ALERT_PROMPT`.
- [x] Implemented dynamic weather fetch orchestration (forecast + station + lake) in `dashboard_pipeline.py`.
- [x] Added run-date labels for Today / Tomorrow / In 2 Days via `DATE_OVERRIDE`/timezone.
- [x] Added weather markdown block at top of output with forecast, station metrics, and lake percentages.
- [x] Enforced 3-sentence summary output format and ensured weather headlines are not reused as summaries.
- [x] Fixed weather section order to align with `Requirements/DailyBrief-Weather Example1.md` and `Example2.md`.
- [x] Fixed station metrics parsing:
  - `Average Temperature for 77316`
  - `Average Monthly rainfall for 77316`
  - `Current Monthly rainfall for 77316` (from wunderground monthly summary URL)
- [x] Fixed lake trend extraction to return separate values for Today / 1 Week Ago / 30 Days Ago for each lake.
- [x] Documented new run/version details and requirements in project markdown files.

## To do (small, incremental)
1. [ ] Add parser-level fixtures/tests for forecast, wunderground, and lake pages.
2. [ ] Add automated output-shape validation against `Requirements/DailyBrief-Weather Example2.md` (then `Example1.md`) to catch ordering/format regressions.
3. [ ] Add CI/nightly dry-run check that validates required weather sections exist before publish.

## Version Notes
- `README`, `PROJECT`, `SUMMARY`, and `PLAN` now aligned to **v1.0.6**.
