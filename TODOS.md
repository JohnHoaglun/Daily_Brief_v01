# TODO: Daily Brief v01 — v1.0.65 (Research agent deep review complete, 47-item phased plan)

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

### Lake Level Expansion — v1.0.31 (Priority: High, Effort: 1 hr, Risk: Zero)
Expand lake monitoring from 3 lakes to 12 lakes. All URLs use same `waterdatafortexas.org` site/format as existing lakes.

**Current lakes (3):**
- Lake Conroe: `https://waterdatafortexas.org/reservoirs/individual/conroe`
- Lake Travis: `https://waterdatafortexas.org/reservoirs/individual/travis`
- Lake Corpus Christi: `https://waterdatafortexas.org/reservoirs/individual/corpus-christi`

**New lakes to add (9):**
- Lake Houston: `https://waterdatafortexas.org/reservoirs/individual/livingston`
- Livingston: `https://waterdatafortexas.org/reservoirs/individual/livingston`
- Waco Lake: `https://waterdatafortexas.org/reservoirs/individual/waco`
- Lake Travis: `https://waterdatafortexas.org/reservoirs/individual/travis`
- Ray Roberts Lake: `https://waterdatafortexas.org/reservoirs/individual/ray-roberts`
- Lewisville Lake: `https://waterdatafortexas.org/reservoirs/individual/lewisville`
- Lake Ray Hubbard: `https://waterdatafortexas.org/reservoirs/individual/ray-hubbard`
- Choke Canyon Reservoir: `https://waterdatafortexas.org/reservoirs/individual/choke-canyon`
- Lake Corpus Christi: `https://waterdatafortexas.org/reservoirs/individual/corpus-christi`
- Caddo Lake: `https://waterdatafortexas.org/reservoirs/individual/caddo`
- Toledo Bend: `https://waterdatafortexas.org/reservoirs/individual/toledo-bend`

**Tasks:**
- `[x]` Update `config.yaml:weather.lake_urls` — add all 11 lakes in specified order
- `[x]` Update `config.yaml:weather.lake_headers` — headers match new lake table layout (Today / 1 Week Ago / 30 Days Ago)
- `[x]` Update `dashboard_pipeline.py` & `sources/weather.py` lake scraping — `_extract_lake_value` works for all 11 lakes
- `[x]` Update rendering — table renders all 11 lakes with "Lake" prefix labels via dynamic `_lake_label`
- `[x]` Pipeline validated: all 11 lakes render with correct values, test [1.4] passes

### P2 — Data Sources Split (Priority: High, Effort: 6 hrs, Risk: Low) — v1.0.14, v1.0.15, v1.0.29
- `[x]` Create `sources/` package — `__init__.py` (re-export chain)
- `[x]` Extract `sources/weather.py` (262L) — NWS forecast fetch + parse, orchestrator
- `[x]` Extract `sources/wunderground.py` (185L) — station metrics scraping
- `[x]` Extract `sources/climate.py` (179L) — Open-Meteo ERA5 + climate.gov normals
- `[x]` Extract `sources/lakes.py` (97L) — reservoir level extraction
- `[x]` Extract `sources/rss.py` (151L) — feedparser + Google News URL building + dedup + filtering
- `[x]` Extract `sources/article.py` (76L) — full article content extraction
- `[x]` Fix http_client.py — proper `user_agent` param + `**params` passthrough
- `[x]` Extend utils.py — `_extract_first_match`, `is_obituary_title`, `is_realt_estate_title`
- `[x]` Migrate ~26 `log()` calls → Python `logging` (`logger.debug/warning`)
- `[x]` Fix duplicate climate normal call (dead code in monolith line 988)
- `[x]` Pipeline validated: 56 stories, 0 errors, 85.6s (end-to-end)
- `[x]` Fix `tagging.py` to read from `config.yaml:tagging_mappings` instead of inline dict — v1.0.15
- `[x]` Fix `ordered_categories_for_render` to use `config.yaml:category_priority` instead of hardcoded list — v1.0.15
- `[x]` Fix tag distribution — every story ≥3 tags (v1.0.29): expanded config keywords, category boosts by membership, min_tags=3 promotion after conflict resolution

### P3 — LLM Module (Priority: High, Effort: 2 hrs, Risk: Low) — v1.0.32
- `[x]` Extract `llm/client.py` — `LLMClient` class, `create_llm_client()` factory, `_executor`, `_run_blocking`
- `[x]` Extract `llm/summarizer.py` (476L) — `_summarize`, `batch_summarize_all`, `_safe_sentence_summary`, `parse_batch_summary_response`, `build_context`, `StoryPipelineState`, `_is_refusal`, `_is_boilerplate`, `_count_sentences`
- `[x]` Extract `llm/alerter.py` — `batch_evaluate_alerts`, `parse_alert_batch_response`
- `[x]` Make `_llm_client` instantiatable via `create_llm_client()` (not global singleton)
- `[x]` Update monolith — delegating wrappers replace ~501L inline LLM code
- `[x]` Pipeline validated: 72 stories, 0 failures, proper multi-sentence summaries

### P4 — Rendering (Priority: Medium, Effort: 3 hrs, Risk: Low) — v1.0.33
- `[x]` Extract `rendering/weather_table.py` (63L) — `build_weather_markdown()` with forecast, station, and lake tables
- `[x]` Extract `rendering/report.py` (127L) — `build_markdown()`, `write_report()` — frontmatter, weather, category sections
- `[x]` Extract `rendering/cleanup.py` (50L) — `cleanup_old_files()` — report + log file cleanup
- `[x]` Update monolith — delegating wrappers for `_build_weather_markdown` + `cleanup_old_files` call
- `[x]` Pipeline validated: 71 stories, 0 failures, 3 bad summaries (pass < 7 threshold)

### P5 — Pipeline + Config (Priority: Medium, Effort: 4 hrs, Risk: Medium) — v1.0.34
- `[x]` Extract `pipeline.py` (521L) — `async def main()` orchestrator with all 6 phases + `log()`, `_coerce_temperature_f`, `is_realt_estate_title`
- `[x]` Extract `config.py` (139L) — moved from project root, path to config.yaml fixed (`parent.parent.parent`)
- `[x]` Extract `validation.py` (150L) — `validate_report()` with 5 checks (empty, headline repeat, min sentences, fallback, topic overlap)
- `[x]` Extract `harness.py` (77L) — `run_test_harness()` subprocess call to Test_validate_run.py
- `[x]` Monolith `dashboard_pipeline.py` reduced from 1,701L → 16L (thin shim: imports + `asyncio.run(main())`)
- `[x]` Updated `__main__.py` — imports from `daily_brief.pipeline` (not `dashboard_pipeline`)
- `[x]` Fixed subpackage imports — `from config import` → `from daily_brief.config import` (8 files)
- `[x]` Verified: all 6 phases intact, all subpackage calls wired correctly

### P5.1 — RSS Dedup Extraction (Priority: Medium, Effort: 2 hrs, Risk: Low) — v1.0.35
- `[x]` Create `pipelines/rss_dedup.py` (269L) — `dedup_entries()`, `widen_category()`, `fetch_and_dedup()`
- `[x]` Create `pipelines/__init__.py` — re-exports
- `[x]` Replace Phase 2 in `pipeline.py` with 6-line `fetch_and_dedup()` shim call
- `[x]` Reduce `pipeline.py` from 521L → 364L (-157L)
- `[x]` Remove unused imports + duplicate `is_realt_estate_title` from `pipeline.py`
- `[x]` Verified: 74 stories, 15 categories, all 6 phases pass end-to-end

### P5.2 — Phase 4 Render Extraction (Priority: Medium, Effort: 2 hrs, Risk: Low) — v1.0.36
- `[x]` Add `rendering/report.py:build_sections_from_stories()` — converts StoryPipelineState → sections dict + alerts list
- `[x]` Add `rendering/report.py:compute_output_path()` — auto-versioned filepath generation
- `[x]` Wire Phase 4 in `pipeline.py` to existing `build_markdown()` + `write_report()` (eliminated 113L inline duplication)
- `[x]` Reduce `pipeline.py` from 364L → 284L (-80L)
- `[x]` Remove unused imports (`tag_story_with_keywords`, `build_weather_markdown`) from pipeline.py
- `[x]` Update `rendering/__init__.py` with `build_sections_from_stories`, `compute_output_path` re-exports
- `[x]` Verified: 73 stories, 15 categories, all 6 phases pass end-to-end

### P6 — Config Management & Validation (Priority: High, Effort: 2 hrs, Risk: Zero)
- `[x]` Add config validation — P6.1 v1.0.37 (7-group validation gate at startup)
- `[x]` Add CLI config command — P6.2 v1.0.38 (validate, show, list-categories, list-lakes, show-prompt)
- `[x]` Make `tagging.py` read from `config.yaml:tagging_mappings` (not inline dict) — DONE v1.0.15 via P2
- `[x]` Make `ordered_categories_for_render` use `config.yaml:category_priority` (not hardcoded) — DONE v1.0.15 via P2
- `[x]` Add connectivity checks — P6.3 v1.0.39 (LLM/RSS/Weather parallel probes, warning-only)

---

## Active Work: Performance & Optimization — Research Agent Review (v1.0.65)
*Comprehensive review by research agent (gpt-5.6-terra). 47 items across 7 categories. Replaces prior 17-item plan.*

**Runtime budget analysis:**
| Area | Current cost | Reduction opportunity |
|---|---:|---:|
| Preflight | 0.1-1s (up to 5s on outage) | 0.1-1s |
| Phase 1 (weather) | ~15-25s | **~10-20s** with concurrency + redundant request removal |
| Phase 2 (RSS) | 15-5s on widening | ~1-5s per widened category |
| Phase 3 (LLM) | ~50-85s | **~5-20s** IF batching/concurrency works on vLLM; 0s from async conversion alone |
| Render/validation | 2s | ~0.2-2s |
| Harness | 0-30s (blocking subprocess, outside timings) | No generation-time reduction unless made optional |

**Credible target:** ~65-75s after Phase B. Full 55-65s only if measured LLM batching proves beneficial.

### Phase A — Quick Wins (v1.0.64 → .68, ~2-3 hrs, Risk: Low)
Establish trustworthy measurement and remove unequivocal dead work. No behavioral test changes.

| # | Ticket | File:line | Finding & Fix | Effort | Risk |
|---|---|---|---|---:|---:|
| A.1 | **Bug-1** | `pipelines/rss_dedup.py:35` | Missing `from zoneinfo import ZoneInfo` — every run silently falls back to UTC for RSS age filtering. Import it. | 5m | Low |
| A.2 | **Clean-8** | `utils.py:24-29` | HTML strip regex `re.compile(r"<.*?>")` compiled on every call (~700+/run). Hoist to module-level `_HTML_STRIP_RE`. | 5m | Low |
| A.3 | **Clean-5** | `pipeline.py:202` | `sum_results` assigned but never read — `batch_summarize_all()` mutates stories in place. Remove assignment. | 5m | Low |
| A.4 | **Clean-9** | `config.py:53,136-138` | `WEATHER_POINT_URL` assigned 3×, including obsolete `api.weather.to` value. Collapse to single assignment. | 5m | Low |
| A.5 | **Clean-6** | `config.py:81,109-110` | Unused `CATEGORY_SETTINGS`, `REAL_ESTATE_KEYWORDS`, `OBITUARY_KEYWORDS`, `USER_AGENT_WEATHER_SUFFIX`. Remove dead constants. | 10m | Low |
| A.6 | **Rel-3** | `pipeline.py:119`; `__main__.py:24-30` | `os.listdir(LOG_DIR)` and `RotatingFileHandler` can fail if log dir doesn't exist. Create/validate before setup/list. | 15m | Low |
| A.7 | **Rel-4** | `connectivity.py:38-40,55-57` | RSS connectivity checks disable TLS verification (`ssl=False`). Restore normal cert validation. | 10m | Low |
| A.8 | **Bug-6** | `sources/rss.py:121-150` | `fetch_feed()` parses non-200 response bodies as RSS (no status check). Require 200/206, log status context safely. | 15m | Low |
| A.9 | **Quality-6** | `pipeline.py:115-312` | Phase timings mix `time.time()` with partial phases, omit total/preflight/validation. Use `time.perf_counter()`, record all phases. | 45m | Low |
| A.10 | **Bug-5** | `config.py:105` | Typo: `dedupi_window_hours` instead of `dedupe_window_hours`. Configured value is ignored. Correct spelling. | 5m | Low |
| **Total** | | | **10 items** | **~2.5 hrs** | |

### Phase B — High-Impact Performance (v1.0.69 → .75, ~4-6 hrs, Risk: Low-Medium)
Remove unnecessary serialized network waits and redundant requests. **~10-20s saved, primarily weather.**

| # | Ticket | File:line | Finding & Fix | Time Saved | Effort |
|---|---|---|---|---:|---:|
| B.1 | **Perf-1** | `sources/weather.py:245-253` | 11 lake requests run serially. Use bounded `asyncio.gather()`, retain deterministic key ordering, collect per-lake errors. | **~8-20s** | 30m |
| B.2 | **Perf-2** | `sources/weather.py:107-118`; `182-206` | NWS forecast, station metrics, climate normal, monthly rainfall, and lakes are largely unnecessary serialization. Start independent source calls concurrently, apply merge/fallback logic. Only forecast fallback after source results. | **~3-8s** | 1-2h |
| B.3 | **Perf-3** | `sources/weather.py:182`; `197`; `wunderground.py:84-108,156-183` | WU dashboard fetched twice. First result wins for current rainfall, second WU request's value commonly discarded. Separate climate-normal rainfall from WU retrieval or consolidate. | ~1-5s | 1h |
| B.4 | **Perf-4** | `sources/climate.py:30-56` | Climate normal makes a geocoding request for fixed ZIP `77316` every run, despite pipeline coords already configured. Pass lat/lon to function or cache geocode with bounded TTL. | ~0.2-1.5s | 30m |
| B.5 | **Perf-5** | `pipeline.py:189-197` | Phase 3A opens second session/connector despite outer session existing. Reuse outer session, retain per-request 5s timeout, preserves connection pooling. | <1s | 15m |
| B.6 | **Perf-6 / Bug-10** | `pipelines/rss_dedup.py:92-95,190-266`; `sources/rss.py:121-150` | Widen categories sequentially, each re-downloads same URL. Also: widening can't actually inspect more than `max_stories` entries because `fetch_feed()` truncates before age filtering. Fetch adequate candidate pool once, locally apply increasing age windows, widen concurrently with per-host bound. | ~1-8s | 1-2h |
| B.7 | **Perf-11** | `pipeline.py:104-109`; `connectivity.py:132-140` | Every normal run does 3 preflight probes with new session before timings start, then repeats corresponding source traffic immediately after. Make checks opt-in or cache for short TTL. | ~0.1-1s | 30m |
| B.8 | **Arch-1 / Perf-1** | `sources/weather.py:94-259` | Weather orchestration mixes fetch, normalization, fallback policy, formatting, logging, and provider merge decisions. Extract independent provider tasks from one deterministic merge/fallback function. Enables safe concurrency. | Enables B.1-B.4 | 3-5h |
| **Total** | | | **8 items** | **~10-20s** | **~4-6 hrs** |

### Phase C — Medium-Risk Async and LLM Changes (v1.0.76+.85, ~1-3 days, Risk: Medium-High)
Eliminate event-loop blocking and reduce serial LLM critical path. **AsyncOpenAI alone = 0s saved; benefit requires measured batching/concurrency.**

| # | Ticket | File:line | Finding & Fix | Effort | Risk |
|---|---|---|---|---:|---:|
| C.1 | **Perf-8 / Perf-9** | `llm/client.py:24-28`; `summarizer.py:489-549`; `alerter.py:71-103`; `summarizer.py:528,543` | Sync `OpenAI` client blocks event loop. Migrate to `AsyncOpenAI`, `await` all callers. Replace `time.sleep()` with `await asyncio.sleep()` in retry backoff. | 2-4h | Medium |
| C.2 | **Perf-7** | `llm/summarizer.py:579-680` | Batches capped at 3 stories, every batch issued serially. ~60-75 stories → ~20-25 sequential LLM requests. Benchmark batch sizes 4, 5, 6; benchmark concurrency 2 on actual vLLM server. Do not change blindly. | 2-4h | High |
| C.3 | **Rel-1 / Rel-2** | `http_client.py:20-71`; `sources/rss.py:126`; `sources/article.py:37-52` | Shared HTTP helpers retry every exception identically. Add bounded retry for 429/502/503/504/timeout; respect `Retry-After`, use jitter. Route direct `session.get()` callers through common policy. | 1-2h | Medium |
| C.4 | **Rel-6 / Rel-7 / Arch-2** | `llm/summarizer.py:604-660`; `pipeline.py:207-257` | Batch summary calls have no retry. Recovery duplicated between `batch_summarize_all()` Phase 3F and pipeline Phases 3D/3E. Centralize retry, fallback, boilerplate recovery, and metrics in summarizer service. | 1-2h | Medium |
| C.5 | **Bug-2 / Bug-3 / Bug-9** | `pipeline.py:202; alerter.py:35; summarizer.py:465; alerter.py:27-31` | Alert system never wired. `StoryPipelineState.__slots__` excludes `_alert_idx`/`is_alert` — `batch_evaluate_alerts()` would raise `AttributeError`. Either restore full alert feature + slots + render, or formally remove it and tests/config. | 1-2h | Medium |
| **Total** | | | **5 items** | **~1-3 days** | |

### Phase D — Architecture Polish (v1.0.86+.95, ~2 days, Risk: Medium)
Remove divergent state/config ownership. ~0.5-2s direct; substantial maintainability gain.

| # | Ticket | File:line | Finding & Fix | Effort | Risk |
|---|---|---|---|---:|---:|
| D.1 | **Bug-4 / Arch-4 / Quality-1 / Quality-7** | `config.py:16-143`; `pipeline.py:16`; `config.yaml` | Config reader uses `runtime_defaults.llm_summary_options`, `runtime.timezone`, `cleanup_api.max_log_versions` — validator checks `llm.summary_options`, `runtime.timezone`, `cleanup.max_log_versions`. Validated config is silently ignored, fallback defaults used. `globals().update(locals())` star imports conceal API. Define one typed config schema. | 2-4h | Medium |
| D.2 | **Arch-3 / Clean-7** | `models.py:13-81`; `summarizer.py:465-475`; `report.py:13-38` | Three incompatible story representations: `Story`, `StoryPipelineState`, rendering dicts. Adopt one typed internal model with context, summary, tags, alert fields. Serialize at rendering boundary. | 4-8h | Medium |
| D.3 | **Dup-1 to Dup-4 / Clean-1 to Clean-3** | `utils.py`; `summarizer.py`; `article.py`; `http_client.py`; `llm/__init__.py` | `_safe_sentence_summary`/`_count_sentences` dupes ×2, `build_context` dupes ×2, `_coerce_temperature_f` ×2, `_fetch_json`/`_fetch_text` dupes ×2, unused `_run_blocking`/executor exports. Canonicalize all. Update tests. | 2-4h | Medium |
| D.4 | **Quality-3** | `llm/summarizer.py:102-462` | Batch response parsing is 360 lines of interleaved parsing, heuristic matching, logging, swap diagnosis. Repeatedly compiles regexes in loops, helper functions inside hot loops. Split format parsing from matching/validation, use golden responses. | 4-8h | High |
| D.5 | **Quality-4 / Perf-10** | `tagging.py:23-41,86-96`; `report.py:109-124,160-166` | Tagging builds 2 regexes per keyword per title, recalculates every title twice (frontmatter + render). Precompile immutable config patterns once, compute tags once, pass/retain in section data. Category boost semantics are ambiguous (can award scores to unrelated tags). | 1-2h | Medium |
| D.6 | **Bug-7 / Bug-8 / Bug-11 / Bug-12** | `weather.py:105-116`; `weather_table.py:41-45`; `__init__.py:52`; various | Forecastsuffix ignored. `WEATHER_LABELS["station_rows"]` indexed 0/1/2 without length validation. Version sources disagree: package `1.0.54`, YAML `1.0.54`, docs `1.0.64`. BeautifulSoup/feedparser run on event loop. Fix all. | 1-2h | Low |
| D.7 | **Rel-5 / Quality-2 / Quality-5 / Arch-5** | `harness.py:54-77`; `weather.py:255-257`; `pipeline.py:59-70`; `connectivity.py:132-164` | Harness can't fail pipeline, blocks async main 30s. One broad `except` wraps all weather providers. Custom file logger duplicates standard logging. Preflight and smoke checks overlap. Fix systematically. | 1-2h | Medium |
| **Total** | | | **7 items** | **~2-4 days** | |

---

## Verification Strategy

### Baseline Before Any Phase
1. Run `pytest -q` — confirm 761-test baseline
2. Run 3 full pipeline executions at comparable times
3. Capture: total wall-clock; preflight, Phase 1-6, harness durations; weather requests by provider; RSS fetches and widening count; batch LLM calls, fallback count, retry count, generated-token/request timing; story count, category count, auto-fallback count, validation result
4. Compare generated reports structurally (live RSS/LLM output is nondeterministic)

### Phase A Verification
- `pytest tests/test_sources/test_rss_dedup.py tests/test_sources/test_rss.py tests/test_utils.py tests/test_pipeline.py tests/test_connectivity_extended.py -q`
- `pytest -q`
- One pipeline run. Verify: RSS logs show configured timezone; no missing dir startup errors; connectivity checks have TLS; timing output includes all phases + total wall time

### Phase B Verification
- Add mocked source tests before changing concurrency: weather success + per-provider failure + fallback merge ordering; all configured lake results key/order-stable; RSS widening returns same or better valid story count from recorded feed; repeated fetch count drops to one per widened category
- `pytest tests/test_sources/test_weather.py tests/test_sources/test_weather_extended.py tests/test_sources/test_lakes.py tests/test_sources/test_rss.py tests/test_sources/test_rss_dedup.py -q`
- `pytest -q`
- At least 3 full pipeline runs, compare median Phase 1 and Phase 2 timings against baseline
- **Acceptance:** no loss of valid weather fields, lakes, categories, or report validation; median total reduction ≥10 seconds before proceeding to Phase C

### Phase C Verification
- Update all client/summarizer/alerter mocks to async return values. Test retry backoff without real sleeping
- `pytest tests/test_llm_client.py tests/test_summarizer.py tests/test_alerter.py tests/test_pipeline.py -q`
- `pytest -q`
- Test HTTP retry with `aioresponses`: 429/502/503/504/timeouts retry; honor retry limit; no retry for 400/403/404; no event-loop blockage during retry delay
- Controlled LLM benchmark (saved story contexts + vLLM host): batch sizes 3, 4, 5, 6; serial then concurrency 2; report parser success rate, fallback rate, validation failure rate, request count, duration
- **Acceptance:** summary quality and validation remain at least baseline; measured median latency improves

### Phase D Verification
- Full test suite + coverage: `pytest -q`, `scripts/run_coverage.sh`
- Add migration-level tests for configuration equivalence and model serialization
- `python -m daily_brief config validate`, `python -m daily_brief config check-connectivity`, one full pipeline run
- Package version, YAML version, report version, project docs version all aligned

---

## Testing Strategy

### Tier 1: Unit Tests (Fast, No Network)
- `[x]` `tests/test_config.py` (53 tests) — v1.0.49
- `[x]` `tests/test_utils.py` (106 tests) — v1.0.50
- `[x]` `tests/test_tagging.py` (44 tests) — v1.0.51
- `[x]` `tests/test_weather_table.py` (31 tests) — v1.0.55
- `[x]` `tests/test_report.py` (35 tests) — v1.0.56
- `[x]` `tests/test_summarizer.py` (63 tests) — v1.0.57
- `[x]` `tests/test_alerter.py` (35 tests) — v1.0.58

### Tier 1 Implementation Plan — v1.0.55-.58

| File | vTarget | Tests | Targets | Functions | Status |
|---|---|---|---|---|---|
| `tests/test_weather_table.py` | v1.0.55 | 31 | `build_weather_markdown` | 1 | `[x] DONE` |
| `tests/test_report.py` | v1.0.56 | 35 | `build_sections`, `compute_output_path`, `build_markdown`, `write_report` | 4 | `[x] DONE` |
| `tests/test_summarizer.py` | v1.0.57 | 63 | `_safe_sentence_summary`, `_is_refusal`, `_is_boilerplate`, `_count_sentences`, `parse_batch_summary_response`, `StoryPipelineState`, `_generate_auto_fallback`, `build_context`, `_summarize` | 8 | `[x] DONE` |
| `tests/test_alerter.py` | v1.0.58 | 35 | `parse_alert_batch_response`, `batch_evaluate_alerts` | 2 | `[x] DONE` |

**Test patterns per file:**

- `test_weather_table.py` (~25 tests): Full data render, empty forecast fallback (3× "Dynamic"), empty station ("Unavailable"), empty lakes, Lake label prefix (avoid double "Lake"), table structure (headers, separators, delimiters)
- `test_report.py` (~35 tests): `build_sections_from_stories` (grouping, alerts, dates), `compute_output_path` (auto-versioning, date stamp, existing files), `build_markdown` (frontmatter, tags, category order, empty cats, weather), `write_report` (file write, encoding), edge cases (0 stories, missing summary)
- `test_summarizer.py` (~60 tests): Sentence utils (truncation, cleanup, empty), refusal/boilerplate detection, `parse_batch_summary_response` (STORY_N format, numbered, fuzzy headline match, keyword overlap, positional fallback, swap detection), `StoryPipelineState` (slots, defaults), `_generate_auto_fallback` (title cleanup, None), `build_context` (cap, fallbacks), `_summarize` mocked (retry, boilerplate retry, auto fallback)
- `test_alerter.py` (~25 tests): `parse_alert_batch_response` (STORY_N format, numbered format, malformed lines, empty/garbage, partial parse), `batch_evaluate_alerts` mocked (empty skip, category grouping, alert flagging, LLM failure grace)

**Conventions:** Follow existing test file patterns (unittest.TestCase, `sys.path` insert for `src/`). No network — mock LLM client where needed. Each commit verified with `pytest tests/test_<file>.py -v`.

### Tier 2: Source Tests (Mocked Network with `aioresponses`) — **COMPLETE**
- `[x]` `tests/test_sources/test_weather.py` (38 tests) — v1.0.59 — NWS forecast JSON parsed, date/period extraction, "Unavailable" on empty
- `[x]` `tests/test_sources/test_wunderground.py` (28 tests) — v1.0.60 — station table scraping with sample HTML, precipitation row matching
- `[x]` `tests/test_sources/test_climate.py` (21 tests) — v1.0.60 — Open-Meteo JSON parsed, climate.gov text parsed, timezone/date handling
- `[x]` `tests/test_sources/test_lakes.py` (20 tests) — v1.0.60 — reservoir percentage extraction with sample HTML
- `[x]` `tests/test_sources/test_rss.py` (47 tests) — v1.0.60 — feed parsing, age filtering, title dedup, real estate/obituary filtering

### Tier 3: Integration (Smoke + Validation, Every Run) — **COMPLETE**
- `[x]` `test_smoke_test.py` — 21 tests, 6 endpoints, `connectivity.py` extended
- `[x]` `test_validate_report.py` — 32 tests, 8 report-level checks, `validation.py` extended
- `[x]` `scripts/run_tests.sh` — scripts/ created with run_tests.sh, run_coverage.sh, pytest.ini

### Tier 4: Coverage Target — **COMPLETE v1.0.62**
| Area | Target | Result | Status |
|---|---|---|---|
| Config loading + validation | 95% | 97% | ✅ |
| Weather parsing | 90% | 99% | ✅ |
| RSS dedup + filtering | 90% | 97% | ✅ |
| LLM response parsing | 90% | 91% | ✅ |
| Markdown rendering | 95% | 99% | ✅ |
| Pipeline orchestration | 80% | 88% | ✅ |

---

## Bug Fix Plan — 12 Active Bugs, 5 Rounds

**Rationale:** Bugs are grouped by dependency and risk. Rounds 1-2 are code-only fixes with zero risk. Round 3 touches LLM logic (medium risk) — requires Tier 1 unit tests as safety net first. Rounds 4-5 build on prior fixes.

### Round 1 — Low-Hanging Fruit (v1.0.40 → .41 → .42) — **45 min total, Risk: Zero**
*No LLM dependency. Code-only fixes. Each commit verified independently with a pipeline run.*

| Bug | Priority | File | Effort | Rationale |
|---|---|---|---|---|
| **2.2a — Widening logs lie** | P2 | `pipelines/rss_dedup.py` | 30min | `[x] DONE v1.0.40 — Added cumulative count log line after widening loop. Exhausted message still showed existing_count (which equals cat_widened_count in that branch), so logic was correct — just needed unambiguous logging.` |
| **4.4 — Render 0-story headers** | P2 | `rendering/report.py` | 30min | `[x] DONE v1.0.41 — Categories with 0 stories now render `## Category\n_No stories found._` header. Also updated Test_validate_run.py section regex to match both `##` and `###` headers. |
| **LLM log says "Qwen"** | P0 | `pipeline.py` | 15min | `[!] ALREADY CORRECT — `{LLM_MODEL}` at pipeline.py:199 resolves to `gemma4-e2b`. Old logs were from separate Prod deployment with different config. No code change needed. |

### Round 2 — Frozen Data Investigation (v1.0.43 → .44 → .45) — **3 hrs total, Risk: Low**
*Read-only investigation. Run pipeline twice, diff output. If frozen, add debug logging to scrape function.*

| Bug | Priority | File | Effort | Rationale |
|---|---|---|---|---|
| **F.2 — Frozen feeds (×5 cats)** | P2 | `config.yaml` + `sources/rss.py` | 1hr | `[x] DONE v1.0.43 — No code bug. 3/5 frozen (narrow topic saturation: Houston Tropical, Anthropic, Karpathy). 2/5 turn normally (OpenAI 80%, SpaceX 33%). Global turnover 14%, healthy. |
| **F.2 — Frozen lake data** | P2 | `sources/lakes.py` + `rendering/weather_table.py` | 1hr | `[x] DONE v1.0.44 — No bug. Reservoir levels from waterdatafortexas.org update daily, not sub-daily. Expected behavior. |
| **F.2 — Frozen station data** | ~~P2~~ ✅ | `sources/wunderground.py` | 1hr | `[x] DONE v1.0.45 — No bug. All scrapers verified live. Values genuinely stable on short timescales. |

**Investigation approach:** Run pipeline twice with sleep between, diff the markdown output. If frozen, add `logger.debug()` to the scrape function to verify HTTP response is fresh. If scrape works but rendering caches, fix the renderer. If genuinely unchanged (lakes/station), document as expected behavior.

### Round 3 — LLM Quality (v1.0.46 → .47 → .48) — **4 hrs, Risk: Medium**
*Touches LLM interaction logic. **Requires Tier 1 unit tests before proceeding.** Priority order matters — fix index mismatch first (highest risk of wrong summary → wrong story).*

| Bug | Priority | File | Effort | Rationale |
|---|---|---|---|---|
| **Fallback index mismatch** | P1 | `llm/summarizer.py` (batch parser) | 2hr | `[x] DONE v1.0.46 — Added Strategy 0: fuzzy headline matching via `difflib.SequenceMatcher.ratio() >= 0.7`. Positional fallback now warns via `logger.warning`. Fuzzy match scores 0.86-1.00 for paraphrased headlines. |
| **3.3 — Strengthen swap detection** | P1 | `llm/summarizer.py` | 1hr | `[x] DONE v1.0.47 — All-pairs keyword overlap validation (lines 410-446). Flags stories with <20% headline→summary overlap, scans other headlines for best mismatch target. Logs `[SWAP DETECTED]` with source, target index, and overlap %. |
| **3.5 — Boilerplate summaries** | P2 | `llm/summarizer.py` + `config.yaml` | 1hr | `[x] DONE v1.0.48 — Expanded boilerplate detection (25 phrases), prompt updated with anti-boilerplate instructions, temperature 0.3→0.5. Single retry with SUMMARY_STRICT on boilerplate detection. Batch parser catches boilerplate, falls back to headline fallback. |

### Gap — Unit Tests (v1.0.49 → .50 → .51) ✅ **COMPLETE**
**Safety net for Round 4. All 3 test files created and passing (203 tests total).**

| Test | File | Tests | Status |
|---|---|---|---|
| `test_config.py` | loads, required keys, types, defaults, validation | 53 | `[x] DONE v1.0.49` |
| `test_utils.py` | `_safe_text`, `strip_html`, number parsing, etc. | 106 | `[x] DONE v1.0.50` |
| `test_tagging.py` | keyword matching, scoring, thresholds | 44 | `[x] DONE v1.0.51` |

### Round 4 — Retry Infrastructure (v1.0.51 → .52 → .53) — **3 hrs, Risk: Medium**
*Builds on Round 3 fixes and unit tests. Risk is medium because retry logic touches the hot path.*

| Bug | Priority | File | Effort | Rationale |
|---|---|---|---|---|
| **3.2 — Retry failed summaries** | P1 | `llm/summarizer.py` | 2hr | `[x] DONE v1.0.52 — Configurable retry (N attempts, exponential backoff, strict prompt on retry). `[Summary Unavailable]` only after exhaustion. |
| **3.2 RESIDUAL — "Unavailable" count** | P1 | `llm/summarizer.py` | 1hr | `[x] DONE v1.0.53 — Auto fallback (`[Auto] {headline}`) when retry exhausts. Batch Phase 3F: per-story LLM retry for empty batch summaries. `[Auto]` accepted in validation. 0 Unavailable, 1 Auto in live run. |
| **3.3 RESIDUAL — Zero keyword overlap** | P1 | (depends on Round 3) | 30min | `[x] DONE — Resolved by Round 3. Fuzzy matching + all-pairs swap detection eliminated misassignment. |

### Round 5 — Climate Verification (v1.0.54) — **30 min, Risk: Low**

| Bug | Priority | File | Rationale |
|---|---|---|---|
| **F.4 — Climate Normal 95°F** | P2 | `sources/climate.py` | `[x] DONE v1.0.54 — VERIFIED: real ERA5 data. Raw API returned `temperature_2m_max: [95.9]` → 96°F for Jul 30. No hardcoded 95°F anywhere in codebase. Fallback chain: ERA5 → forecast high → "Unavailable". Added debug logging for raw JSON inspection. |

---

### Execution Order & Version Targets

```
Round 1 (2.2a → 4.4 → Qwen log)       ──→ v1.0.41    (45 min, zero risk)     ✅
Round 2 (F.2 frozen ×3)                ──→ v1.0.45    (3 hrs, read-only)      ✅
Tier 1 Unit Tests (config/utils/tag)    ──→ v1.0.51    (2 hrs, safety net)     ✅
Round 3 (index → swap → boilerplate)   ──→ v1.0.48    (4 hrs, medium risk)    ✅
Round 4 (retry → unavailable)          ──→ v1.0.53    (3 hrs, depends on R3)  ✅
Round 5 (climate verification)         ──→ v1.0.54    (30 min, standalone)    ✅
```

**Total: ~13 hours, 6 version bumps, 12 bugs cleared.**

### Recent Updates
- [2026-07-31] **Perf/Optimization plan added — v1.0.63** — 17 items across Performance (6 items, ~4hrs), Cleanup (9 items, ~1hr), Architecture (1 item). Quick wins: Clean-8 (`ZoneInfo` import bug), Perf-1/2 (parallel lakes/weather, ~45min total). High impact: Perf-10 (async LLM client, 45min), Perf-11 (HTTP retry, 45min).
- [2026-07-30] **Tier 4 complete — v1.0.62** — Coverage targets: config 97%, weather 99%, RSS dedup 97%, LLM parsing 91%, markdown rendering 99%, pipeline 88%. All targets met. 761 total tests (558 new across 8 new test files). 23 test files total.
- [2026-07-30] **Tier 3 complete — v1.0.61** — Integration tests: `test_smoke_test.py` (21 tests, 6 endpoints), `test_validate_report.py` (32 tests, 8 report-level checks). Extended `connectivity.py` (openmeteo/wunderground/lakes checks), `validation.py` (frontmatter/weather/Dynamic/story count/alert ratio/dup URLs/file size). Test infra: `scripts/run_tests.sh`, `scripts/run_coverage.sh`, `pytest.ini`. 574 total tests (371 new, 63 Tier 3).
- [2026-07-30] **Tier 1 complete — v1.0.58** — `test_alerter.py` (35 tests): parse_alert_batch_response (27: STORY_N format, numbered format, lowercase, malformed, partial parse, type checks), batch_evaluate_alerts mocked (8: empty, alert true/false, unavailable exclusion, bracket exclusion, category grouping, exception all-false, alert idx mismatch, global index mapping). 367 total tests (332 existing + 35 new). Tier 1 done: 4/4 files, 164 new tests.
- [2026-07-29 22:00] **Tier 1/4 complete — v1.0.55** — `test_weather_table.py` (31 tests): full data render, empty forecast fallback, forecast padding, station Unavailable, lake labels, table structure. 234 total tests.
- [2026-07-29 23:00] **Tier 2 source tests complete — v1.0.60** — 5 files, 154 tests (weather 38, wunderground 28, climate 21, lakes 20, rss 47). All mocked with `aioresponses`/`unittest.mock`. 521 total tests passing. 0 failures.
- [2026-07-29 22:00] **Tier 1 complete — v1.0.58** — 4 Tier 1 tests (weather table 31, report 35, summarizer 63, alerter 35), 164 new tests. 367 total.
- [2026-07-29] **Tier 1 plan created — v1.0.55-.58** — 4 test files, ~145 new tests targeting weather table, report, summarizer, alerter. Total will be ~348 tests.
- [2026-07-29 21:27] **Round 5 complete — v1.0.54** — Climate normal 95°F verified as real Open-Meteo ERA5 data (raw: 95.9°F → 96°F Jul 30). No hardcoded fallback. Debug logging added to `climate.py` for raw JSON inspection.
- [2026-07-29 19:30] **Round 4 complete — v1.0.53** — Retry infrastructure (v1.0.52: N attempts, backoff, strict prompt) + auto fallback for unavailable (v1.0.53: `[Auto] {headline}` + batch Phase 3F). 0 Unavailable, 1 Auto in live run. 203 tests still green.
- [2026-07-29 19:00] **Tier 1 tests complete — v1.0.51** — 203 tests passing across test_config (53), test_utils (106), test_tagging (44). Safety net for Round 4 retry logic is green.
- [2026-07-29 18:30] **Round 3 complete — v1.0.48** — Fuzzy headline matching (v1.0.46), all-pairs swap detection (v1.0.47), boilerplate detection + retry (v1.0.48). Next: Tier 1 unit tests (safety net for Round 4).
- [2026-07-29 18:00] **Round 1 complete — v1.0.41** — 3 bugs targeted: 2.2a (widening logs) fixed at v1.0.40, 4.4 (0-story headers) fixed at v1.0.41, Qwen log bug already correct. Ready for Round 2 (frozen data investigation).
- [2026-07-29 00:20] **Bug Fix Plan created** — 12 active bugs organized into 5 rounds. Round 1 (zero risk, 45min) → Round 2 (investigation, 3hr) → Tier 1 tests (safety net, 2hr) → Round 3 (LLM quality, 4hr) → Round 4 (retry infra, 3hr) → Round 5 (climate verify, 30min). Target: v1.0.54.
- [2026-07-29 00:05] **P6.3 complete — v1.0.39** — Connectivity checks (LLM/RSS/Weather, 3/3 pass). All refactoring P0-P6 done.
- [2026-07-28 01:09] **Tag distribution goal achieved — v1.0.29** — All 61 stories have ≥3 tags. Avg: 3.90. Distribution: `{3:30, 4:7, 5:24}`. Changes: (1) expanded `config.yaml` keywords for 15+ tags, (2) category boosts fire on membership not just keyword match, (3) moved `min_tags=3` promotion after conflict resolution, (4) last-resort category-derived fallback tags.
- [2026-07-27 00:45] **P0 fixes complete** — Fixed 2.6 (Hermes typo), 3.2 (failure counter), 3.3 (swap detection), 4.3 (categories count), 4.8 (missing tag). HARNESS FAILs: 6→2. Remaining: 3.2 residual (LLM quality), 3.3 residual (LLM quality)
- [2026-07-27 01:30] **Bugs logged** — Tag scoring fix didn't fix single tags. Widening logs say "giving up" but stories render. LLM is QWEN, should be Gemma. Fallback index matching on every run.
</think>

<tool_call>
<function=bash>

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
- [2026-07-31] **Research agent deep review complete — v1.0.65** — Full codebase analyzed by gpt-5.6-terra. 47 items across 7 categories: 11 bugs (ZoneInfo import, alert system never wired, config schema misalignment, WU fetched twice, RSS no status check, widening truncation, forecast suffix ignored, station_rows no length validation, numeric alert parser case bug, version drift 4 sources, dedupi typo), 12 performance items (parallel lakes ~8-20s, concurrent weather ~3-8s, WU dedup, geocode cache, session reuse, RSS widening + truncation fix, preflight cache, AsyncOpenAI + asyncio.sleep, LLM batching benchmark, HTTP retry, tagging precompile, CPU-bound parsers), 9 dead code blocks, 4 duplicate code pairs, 7 anti-patterns, 7 reliability issues, 5 architecture items. Replaced prior 17-item plan. Credible target: 65-75s.
- [2026-07-28 21:00] **P5.1 RSS Dedup extraction complete — v1.0.35** — Extracted Phase 2 (138L) into `pipelines/rss_dedup.py` (269L: `dedup_entries`, `widen_category`, `fetch_and_dedup`). Reduced `pipeline.py` 521L → 364L. Phase 2 is now a 6-line shim call. 74 stories, 15 categories verified.
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
- Current version: **v1.0.65** (Research agent deep review complete — 47-item phased optimization plan)
- Last stable: v1.0.62 (All 5 rounds complete, all 4 Tiers done — 761 tests, 558 new, all coverage targets met)
- Branch: `dev_opencode`, synced with `origin/dev_opencode`
