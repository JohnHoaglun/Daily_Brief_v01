# TODO: Daily Brief v01 - v1.0.97

## Status
Phases A/B/C complete. Phase D is next work.

## Verification Gate — Phase D
- [ ] D.1: config validate + one pipeline run proving configured values reach consumers
- [ ] D.2: `pytest -q` + pipeline run, no story field regressions
- [ ] D.3: `pytest -q`, import chain intact, no behavioral changes
- [ ] D.4: parser golden fixtures covering all LLM response formats, coverage ≥90%
- [ ] D.5: `pytest -q`, tagging computed once per story (verify with timing/probe)
- [ ] D.6: Bug-7/8 fix + pipeline run (no weather crashes); Bug-11: `__init__.py` version aligned
- [ ] D.7: harness returns typed result, weather errors surfaced in log, pipeline `pytest -q`
- [ ] Phase D final: `pytest -q`, `scripts/run_coverage.sh`, `python -m daily_brief config validate`, one full pipeline execution, all versions aligned

---

## Phase D — Architecture Follow-Up

### D.1 `Bug-4` / `Arch-4` — Unify config schema, loading, validation (Substantial)
Runtime reads divergent YAML paths from what the validator checks → configured values silently ignored:
- `TIMEZONE`: runtime reads top-level `timezone`; YAML/validator use `runtime.timezone` → always falls back to `America/Chicago`
- `USER_AGENT`: runtime reads top-level `user_agent`; YAML uses `network.user_agent`
- `MAX_LOG_VERSIONS`: runtime reads `cleanup_api.max_log_versions`; YAML/validator use `cleanup.max_log_versions` → falls back to `5`
- LLM options: YAML defines `llm.*` (display?) and `runtime_defaults.*` (actual); runtime reads the latter, validator validates the former
- `globals().update(locals())` at `config.py:139`
**Files:** `src/daily_brief/config.py`, `src/daily_brief/config_validator.py`, `config.yaml`
**Work:** Establish one typed/defaulted config schema. Load YAML once. Validate exactly the consumed fields. Remove obsolete duplicate YAML locations and `globals().update()`. Add regression tests proving configured values reach consumers.

### D.2 `Arch-3` — Adopt one typed story model (Medium)
Two disparate types in circulation: `models.Story` (missing `snippet`, `pub_dt`, `context`) and `summarizer.StoryPipelineState` (used by pipeline/LLM/article/rendering). Benchmark/corpus scripts import the LLM-layer class.
**Files:** `src/daily_brief/models.py`, `src/daily_brief/llm/summarizer.py:466-477`, `src/daily_brief/sources/article.py`, `src/daily_brief/rendering/report.py`, `scripts/capture_corpus.py`, `scripts/benchmark_llm_batches.py`
**Work:** Choose one `Story` dataclass as the internal representation. Normalize field names. Migrate pipeline/LLM/article/rendering/scripts/tests. Keep render-only dicts private.

### D.3 `Dup-1-4` / `Clean-1-3` — Canonicalize duplicate utilities (Medium)
Exact duplicates remain; HTTP request plumbing is largely resolved by Phase C.3:
- `_safe_sentence_summary` / `_count_sentences`: duplicated in `utils.py` and `summarizer.py`
- `build_context`: verbatim copy in `article.py` and `summarizer.py`
- `_coerce_temperature_f`: duplicated in `pipeline.py` and `utils.py`, neither appears used in active path
**Files:** `src/daily_brief/utils.py`, `src/daily_brief/llm/summarizer.py`, `src/daily_brief/sources/article.py`, `src/daily_brief/pipeline.py`, `src/daily_brief/validation.py`
**Work:** Retain one implementation of each in `utils.py` (neutral module). Redirect imports and tests. Delete or consolidate temperature coercion. Document why connectivity probes use separate request paths.

### D.4 `Quality-3` — Decompose batch-response parsing with golden LLM fixtures (Substantial)
`parse_batch_summary_response()` is 361 lines: multi-strategy, nested functions, per-call regex compilation, accumulated defensive logic, positional fallbacks, swap mutation. No checked-in golden corpus.
**Files:** `src/daily_brief/llm/summarizer.py:103-463`, `tests/test_summarizer.py`
**Work:** (1) Capture representative sanitized LLM response fixtures as golden files, (2) Split into named helpers: lexing/block extraction, headline matching, positional fallback, cleanup, swap detection, (3) Add fixture-driven tests for expected assignments and non-regression.

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
