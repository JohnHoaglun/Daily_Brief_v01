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

### P6 — Config Management & Validation (Priority: High, Effort: 2 hrs, Risk: Zero)
- `[ ]` Add config validation — check required keys, types, value ranges at startup
- `[ ]` Add config validation — P6 (deferred to after P5)
- `[x]` Make `tagging.py` read from `config.yaml:tagging_mappings` (not inline dict) — DONE v1.0.15 via P2
- `[x]` Make `ordered_categories_for_render` use `config.yaml:category_priority` (not hardcoded) — DONE v1.0.15 via P2
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

## Bugs (Test Harness FAILs — v1.0.14, 2026-07-27 run)

### P0 — Immediate Fixes (verified by Test_validate_run.py)
- `[x]` **2.6** FIX: Hermes Agent News query typo: `herms agent` → `hermes agent` in `config.yaml` (commit 6feacad)
- `[x]` **3.2** FIX: Summary failure counter — now counts empty strings as failed (commit 910d62b)
- `[ ]` **3.2** RESIDUAL: 7 "Unavailable" summaries in v02 output — LLM quality issue, not pipeline bug (requires retry/re-prompt strategy)
- `[x]` **3.3** FIX: Added swap detection for adjacent story misalignment in batch summary parser (commit e31a741)
- `[ ]` **3.3** RESIDUAL: US News #4 still shows zero keyword overlap in v02 — LLM returned wrong summary for that story
- `[x]` **4.3** FIX: Frontmatter `categories` now counts actual rendered sections (commit 7e6e027)
- `[x]` **4.8** FIX: Read `frontmatter_tag_segments` from `runtime.config`, not `runtime_defaults` (commit 8f9313f)
- `[x]` **Tags: 1 per story (target 3) — QUALITY REGRESSION — FIXED v15** — Root cause was 2 issues: (1) keyword taxonomy too narrow (212 keywords didn't cover general news topics like war, diplomacy, executions). (2) strict word boundary matching failed on stemmed words ("arrested" ≠ "arrest") and possessive without apostrophe ("Houstons" ≠ "houston"). Fix: expanded keyword mappings (added `geopolitical`, `defense`, `government`, `diplomacy` tags; expanded `politics`, `economy`, `crime`, `international`, `sports`, `environment`), added suffix-tolerant matching (+s/+es/+ed/+ing), added possessive fallback. Result: v12 {1:38, 2:11, 3:3, 5:11} → v13+ {1:23, 2:19, 3:7, 4:3, 5:13}. 1-tag down 15, 2+ tag stories up 15.
- `[x]` **Station data bug — avg_monthly_rainfall failing** — Variable name mismatch: climate page retry edit changed `html` → `climate_html` at fetch but references at lines 591-593 stayed `html`, causing `NameError` silently swallowed. Fix + 3-attempt retry on all 3 weather fetches (Wunderground station, Wunderground range, climate.gov). v15: 0 FAILs.
- `[ ]` **LLM should be Gemma, not QWEN** — Log shows `[3BC] Running BATCH summaries via Qwen...` but requirements/docs specify Gemma model. `LLM_MODEL` in `config.py` reads `llm.model` — check if `config.yaml` is set to Qwen, or if the pipeline should force Gemma for summaries. (BUG)

### P1 — Remaining FAILs (LLM quality, requires pipeline changes)
- `[ ]` **3.2** Implement retry/re-prompt for failed summaries — currently 3/52 stories get no valid summary
- `[ ]` **3.3** Strengthen batch prompt enforcement (STORY_N ordering) or add post-run swap detection for larger batches
- `[ ]` **Fallback index mismatch in batch summary parser** — Log shows `Unmatched stories by headline: indices [0, 1, 2] (will use fallback index matching)` on every run. Summary parser cannot match LLM output headlines back to input stories by text, must fall back to positional index matching. Likely causes: LLM truncates/headlines differ from input, or fuzzy matching threshold too strict. Risk: wrong summary assigned to wrong story if order drifts.

### P2 — WARN-Category Improvements (test harness flags, non-blocking)
- `[ ]` **F.4** Climate Normal High == 95°F — verify live parse succeeded (not fallback default)
- `[ ]` **2.2a** Widening logs lie: "0 stories, giving up" but output renders widened stories** — Log prints `[fetch_rss] Category 'Conroe TX News' widened to 7 days, still 0 stories — giving up` yet v04 output renders 3 stories for Conroe TX News (from 2026-07-21/23). Same for Montgomery County TX News: log says "0 stories at 7 days" but 4 stories rendered. Root cause: widen loop logs "0 stories" for every day that returns 0, then the *next* iteration finds stories. The "giving up" message appears because the loop exhausted to 7d for a *different* category or the `else` clause on the `for` fires after the last iteration where 0 was returned, even though previous widening iterations *did* find stories. Log misleads about actual story count. (BUG)
- `[ ]` **F.2** Investigate frozen feeds — Houston Tropical Weather, OpenAI, Anthropic, SpaceX, Karpathy all show 100% URL overlap
- `[ ]` **F.2** Investigate frozen lake data — conroe, corpus_christi, travis values identical across runs
- `[ ]` **F.2** Investigate frozen station data — avg_temp_today/rainfall identical across runs
- `[ ]` **3.5** Reduce generic/boilerplate summaries
- `[ ]` **4.4** Render section headers for 0-story categories (Conroe, Montgomery County)

### Recent Updates
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
- Current version: **v1.0.29** (P2 complete — tag distribution goal met, all stories ≥3 tags)
- Last stable: v1.0.24 (tag distribution work in progress, 2026-07-28)
- Branch: `dev_opencode`, ahead of `origin/dev_opencode`
