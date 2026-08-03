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
**Done (v1.0.102):** `tagging.py` — `precompile_tagging()` builds 410 precompiled regex pairs at startup. `_word_boundary_match()` delegates to precompiled cache (falls back to runtime compile if precompile hasn't run). `pipeline.py` calls `precompile_tagging()` after config validation. `report.py` — single tag computation per story via `id(st)` cache, reused for frontmatter + body (eliminated duplicate `tag_story_with_keywords()` calls). 953/955 tests passing.
**Files:** `src/daily_brief/tagging.py`, `src/daily_brief/rendering/report.py`, `src/daily_brief/pipeline.py`

### D.6 `Bug-7` / `Bug-8` / `Bug-11` / `Perf-12` — Weather bugs, version drift, parser loop (Medium)
**Done (v1.0.103):** Bug-7 — NWS `forecast` URL used unchanged, suffix appended only on missing URL. Bug-8 — `station_rows` indexed safely with `len()` guard and fallback defaults, no crash on short config. Bug-11 — version bumped to 1.0.103, all sources (`__init__.py`, `config.py`, `config.yaml`, `PROJECT.md`) aligned. Perf-12 deferred (no loop-lag instrumentation yet). 954/956 tests passing (2 pre-existing).
**Files:** `src/daily_brief/sources/weather.py`, `src/daily_brief/rendering/weather_table.py`, `src/daily_brief/__init__.py`, `src/daily_brief/config.py`, `config.yaml`, `tests/test_sources/test_weather_extended.py`

### D.7 `Rel-5` / `Quality-2/5` / `Arch-5` — Harness, weather errors, logging, probes (Medium)
**Done (v1.0.104):** Harness — `run_test_harness()` returns `HarnessResult` dataclass (status: PASS/WARN/FAIL/SKIPPED/ERROR, message, exit_code, stdout/stderr lines). Weather errors — `weather["errors"]` surfaced in pipeline log with concise summary. Probes — `run_all_checks()` and `run_smoke_test()` unified via `CHECK_LIST`/`SMOKE_TEST_CHECKS` declarative lists + `_wrapped()` helper with `name` field. 954/956 tests passing.
**Files:** `src/daily_brief/harness.py`, `src/daily_brief/pipeline.py`, `src/daily_brief/connectivity.py`
