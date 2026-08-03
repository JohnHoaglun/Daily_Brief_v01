# TODO: Daily Brief v01 - v1.0.101

## Status
Phases A/B/C complete. D.1 completed (v1.0.98). D.2 completed (v1.0.99). D.3 completed (v1.0.100). D.4 completed (v1.0.101). Phase D continues.

## Verification Gate — Phase D
- [x] D.1: config validate + one pipeline run proving configured values reach consumers
- [x] D.2: `pytest -q` + pipeline run, no story field regressions
- [x] D.3: `pytest -q`, import chain intact, no behavioral changes
- [x] D.4: 32 golden fixture tests (15 formats + 17 edge cases), coverage of all parser paths
- [ ] D.5: `pytest -q`, tagging computed once per story (verify with timing/probe)
- [ ] D.6: Bug-7/8 fix + pipeline run (no weather crashes); Bug-11: `__init__.py` version aligned
- [ ] D.7: harness returns typed result, weather errors surfaced in log, pipeline `pytest -q`
- [ ] Phase D final: `pytest -q`, `scripts/run_coverage.sh`, `python -m daily_brief config validate`, one full pipeline execution, all versions aligned

---

## Phase D — Architecture Follow-Up

### D.1 `Bug-4` / `Arch-4` — Unify config schema, loading, validation ~~(Substantial)~~ **DONE (v1.0.98)**
**Done:** Unified canonical YAML paths — runtime, validator, and config.yaml all agree:
- config.yaml: removed `runtime_defaults`, moved LLM retry/batch under `llm.*`, runtime under `runtime.*`, network under `network.*`
- config.py: nested `DEFAULTS`, `_get_nested()` helper, single YAML read, removed `globals().update()`
- config_validator.py: validates canonical `llm.*`, `network.*`, `runtime.*` paths; removed `cleanup.*` checks; `check_batch_scheduler()` reads YAML directly
- pipeline.py: replaced star import with explicit constants list
- tests/test_config.py: removed obsolete cleanup/runtime_defaults tests (101 passing)
- Legacy root `config.py` deleted
- 921/923 tests passing, config validate PASS

### D.2 `Arch-3` — Adopt one typed story model ~~(Medium)~~ **DONE (v1.0.99)**
**Done:** Promoted `models.Story` to canonical 7-field typed dataclass: `title`, `link`, `snippet`, `category`, `pub_dt`, `context`, `summary`. Replaced `StoryPipelineState` class in `summarizer.py` with alias `StoryPipelineState = Story`. Updated all construction sites (pipeline, capture_corpus, benchmark script, test factories) to use keyword args. Replaced `__slots__` test with dataclass fields check. 921/923 tests passing (2 pre-existing), config validate PASS.

### D.3 `Dup-1-4` / `Clean-1-3` — Canonicalize duplicate utilities ~~(Medium)~~ **DONE (v1.0.100)**
**Done:** Eliminated 4 exact-duplicate functions by consolidating all in `utils.py`:
- `_safe_sentence_summary`: removed from `summarizer.py`, imported from `utils.py`
- `_count_sentences`: removed from `summarizer.py`, imported from `utils.py`
- `build_context`: promoted to `utils.py` with `preview_chars: int = 600` (typed, no config deps); removed from `article.py` and `summarizer.py`; all callers pass `preview_chars=LLM_CONTEXT_PREVIEW_CHARS`
- `_coerce_temperature_f`: `pipeline.py` delegates to `utils.py` with thin wrapper for extreme temp logging
- Tests updated: `test_article.py` import changed; `test_summarizer.py`/`test_benchmark_llm_batches.py` imports work via summarizer re-export
- `__init__.py` exports `build_context`
- 921/923 tests passing (2 pre-existing). Config validate PASS.

### D.4 `Quality-3` — Decompose batch-response parsing with golden LLM fixtures ~~(Substantial)~~ **DONE — golden fixtures (v1.0.101)**
**Done (part 1 — golden fixtures):** 15 golden fixtures in `tests/fixtures/parser_golden_fixtures.py` covering all LLM response formats. 32 tests in `tests/test_parser_golden.py` (15 golden + 17 edge cases), all passing. Documents actual parser behavior including positional fallback quirks and data loss from duplicate fuzzy targets. Decomposition into named helpers (part 2) deferred — fixtures provide regression safety for future refactoring.
**Files:** `tests/fixtures/parser_golden_fixtures.py`, `tests/test_parser_golden.py`

### D.5 `Quality-4` / `Perf-10` — Tagging precompilation and single computation (Medium)
- `_word_boundary_match()` compiles two regexes per keyword comparison (`tagging.py:32-40`)
- `build_markdown()` tags each story twice: once for frontmatter aggregation, once for body rendering
- Boost semantics ambiguous: `category_boosts` entries are both tag names AND title keywords
**Files:** `src/daily_brief/tagging.py`, `src/daily_brief/rendering/report.py`
**Work:** Precompile keyword matchers once after config load. Compute tags once at story creation, reuse for frontmatter and body output. Separate `category_boost_tags` from `category_boost_keywords` in schema if both behaviors are desired.

### D.6 `Bug-7` / `Bug-8` / `Bug-11` / `Perf-12` — Weather bugs, version drift, parser loop (Medium)
- **Bug-7:** `weather.py:107-111` — NWS response `properties.forecast` URL is altered to append `/forecast`, corrupting valid endpoints. Fallback derives from `WEATHER_POINT_URL`, not the resolved point URL. Hardcoded suffix (`config.py:52-54`), YAML's `weather.forecast_suffix` is unused.
- **Bug-8:** `weather_table.py:41-45` — `station_rows[0]` / `[1]` / `[2]` indexed without type/length validation. Config validator doesn't check `weather_labels.station_rows`. Shortened config crashes rendering.
- **Bug-11:** `__init__.py` version is stale at `1.0.84`; YAML/config/README/PROJECT all say `1.0.97`. Legacy root `config.py` adds drift risk.
- **Perf-12:** RSS/feedparser and article/BeautifulSoup parsing run synchronously on the event loop. No loop-lag measurement exists.
**Files:** `src/daily_brief/sources/weather.py`, `src/daily_brief/rendering/weather_table.py`, `src/daily_brief/__init__.py`, `src/daily_brief/sources/rss.py`, `src/daily_brief/sources/article.py`
**Work:** Respect NWS-provided URL unchanged; explicit fallback only for missing forecast URL. Validate/fallback `station_rows` array entries. Derive package/YAML/display versions from one source. Add loop-lag instrumentation, use `asyncio.to_thread` only if measured as disruptive.

### D.7 `Rel-5` / `Quality-2/5` / `Arch-5` — Harness, weather errors, logging, probes (Medium)
- **Harness:** `run_test_harness()` returns `None` for all outcomes. Pipeline always logs "COMPLETED SUCCESSFULLY" afterward regardless.
- **Weather errors:** `weather["errors"]` kept but never surfaced in pipeline status line or report renderer. Report can show "Unavailable" without error attribution.
- **Logging:** `pipeline.py` uses custom lock/file/stderr `log()` writer; module logger messages don't land in per-run Markdown log. Some status output goes directly to stderr.
- **Probes:** `connectivity.run_all_checks()` hardcodes three probes; `run_smoke_test()` has six. Not declarative/configured.
**Files:** `src/daily_brief/harness.py`, `src/daily_brief/pipeline.py`, `src/daily_brief/sources/weather.py`, `src/daily_brief/rendering/weather_table.py`, `src/daily_brief/connectivity.py`
**Work:** Make harness return typed pass/warn/fail result. Surface concise weather degradation/errors in log. Route phase logs through standard logging or formalize the run-log sink explicitly. Define one named probe profile/configuration for preflight, CLI, and smoke test.
