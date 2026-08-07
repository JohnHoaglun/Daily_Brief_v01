# Plan: Daily Brief v01 - v1.0.109

## Objective
Reduce the measured ~105s pipeline runtime while improving correctness, reliability, and maintainability. This plan is the canonical record of the research-agent review; `TODOS.md` is the executable checklist.

## Measured Baseline (v1.0.67, 3 runs)
| Area | Measured | Credible reduction |
|---|---:|---:|
| Preflight probes | <1s | — |
| Phase 1 weather | 5–11s (~8s avg) | 3–5s (parallel lakes + concurrent sources) |
| Phase 2 RSS | ~3.5s | small (RSS widening fix, session reuse) |
| Phase 3 LLM | 96–100s | 0s from async alone; 5–20s only if benchmarking proves batching/concurrency helps |
| Phase 4 render | ~30s | 0.2–2s (precompile, single-pass tags) |
| Harness | outside phase timing | no reduction unless made optional |

**Target:** ~93–103s after Phase B. Breaking below 90s requires a proven LLM throughput gain (Phase C).

## Research Findings

### Bugs and Correctness
- `Bug-1` `pipelines/rss_dedup.py:35`: missing `ZoneInfo` import silently makes RSS age filtering use UTC.
- `Bug-2` `pipeline.py:202`, `llm/alerter.py:35`, `llm/summarizer.py:465`: alert evaluation is not invoked; its state fields are absent from `StoryPipelineState.__slots__`.
- `Bug-3` `rendering/report.py:24,68-170`: alert results are not rendered; alert validation is therefore ineffective.
- `Bug-4` `config.py`, `config.yaml`, `config_validator.py`: configuration reader and validator use divergent paths and silently apply fallback values.
- `Bug-5` `config.py:105`: misspelled `dedupi_window_hours` ignores the configured dedupe value.
- `Bug-6` `sources/rss.py:121-150`: feeds parse non-success HTTP bodies because response status is unchecked.
- `Bug-7` `sources/weather.py:105-116`: configured forecast suffix is unused and appending `/forecast` can corrupt a valid NWS URL.
- `Bug-8` `rendering/weather_table.py:41-45`: unvalidated `station_rows` indexing can crash rendering.
- `Bug-9` `llm/alerter.py:27-31`: lowercase `true`/`false` numeric fallback values are rejected before normalization.
- `Bug-10` `sources/rss.py:145-146`, `pipelines/rss_dedup.py:232-242`: RSS widening cannot discover entries beyond `max_stories` because truncation happens first.
- `Bug-11` `__init__.py`, `config.yaml`, `PROJECT.md`, `config.py`: version sources disagree.

### Performance
- `Perf-1` `sources/weather.py:245-253`: eleven lake requests are serial; bounded concurrency saves about 8-20s.
- `Perf-2` `sources/weather.py:107-118,182-206`: independent weather sources are serialized; concurrent fetch/ordered merge saves 3-8s.
- `Perf-3` `sources/weather.py`, `sources/wunderground.py`: Wunderground dashboard is fetched twice; remove or separate the redundant work.
- `Perf-4` `sources/climate.py:30-56`: fixed ZIP geocoding occurs every run despite configured coordinates.
- `Perf-5` `pipeline.py:189-197`: article extraction opens a second HTTP session.
- `Perf-6` `pipelines/rss_dedup.py:92-95,190-266`: widening is serial and redownloads the same URL; fetch candidates once and widen locally.
- `Perf-7` `llm/summarizer.py:579-680`: LLM batches of three run serially; benchmark larger batches and bounded concurrency.
- `Perf-8` `llm/client.py`, `llm/summarizer.py`, `llm/alerter.py`: synchronous OpenAI calls block the event loop. Async conversion enables overlap but does not itself reduce wall-clock time.
- `Perf-9` `llm/summarizer.py:528,543`: `time.sleep()` blocks the async event loop during retry backoff.
- `Perf-10` `tagging.py`, `rendering/report.py`: dynamic patterns are repeatedly compiled and tags calculated twice per story.
- `Perf-11` `pipeline.py`, `connectivity.py`: normal production runs perform redundant preflight traffic outside tracked timings.
- `Perf-12` RSS and HTML parsers run on the event loop; measure loop lag before moving substantial parsing to threads.

### Cleanup, Reliability, and Architecture
- `Clean-1` to `Clean-9`: duplicate temperature and sentence helpers, duplicate context construction, duplicate HTTP request plumbing, unused session/executor helpers, unused constants/imports, repeated weather URL declarations, and runtime regex compilation.
- `Dup-1` to `Dup-4`: canonicalize sentence helpers, context construction, temperature coercion, and HTTP request setup.
- `Quality-1` to `Quality-7`: remove `globals().update()` and star imports; isolate provider failures; decompose response parsing; make tag boosts explicit; unify logging; measure with monotonic clocks; avoid import-time config fallback.
- `Rel-1` to `Rel-7`: add bounded transient-status retry; route direct requests through it; create log directories before setup; restore TLS verification; define harness failure behavior; retry failed summary batches once; centralize summary recovery.
- `Arch-1` to `Arch-5`: separate weather fetch/merge responsibility, centralize Phase 3 ownership, adopt a typed story model, establish one config schema, and make connectivity probes declarative.

## Phase Sequencing

### Phase A - Quick Wins
Implement `Bug-1`, `Bug-5`, `Bug-6`, `Clean-5`, `Clean-6`, `Clean-8`, `Clean-9`, `Rel-3`, `Rel-4`, and `Quality-6`.

**Expected:** negligible to 1s improvement; trustworthy timings and immediate correctness fixes. Do not remove public/tested compatibility helpers merely because they appear unused.

### Phase B - High-Impact Performance
Implement `Arch-1`, `Perf-1` through `Perf-6`, `Bug-10`, and `Perf-11`. Preserve provider fallback semantics and stable lake/report ordering.

**Expected:** 10-20s median total-runtime reduction. Require three comparable pipeline runs before accepting the phase.

### Phase C - Async, LLM, and Reliability
Implement `Perf-8`, `Perf-9`, `Rel-1`, `Rel-2`, `Rel-6`, `Rel-7`, and `Arch-2`; then benchmark `Perf-7`. Resolve the alert feature decision (`Bug-2`, `Bug-3`, `Bug-9`) as an explicit product choice.

**Expected:** no speed gain from client async alone. Adopt LLM batch/concurrency changes only if controlled benchmarking preserves parser success, report validation, and summary quality while improving median duration.

### Phase D - Architecture Follow-Up
Implement config unification (`Bug-4`, `Arch-4`, `Quality-1`, `Quality-7`); one story model (`Arch-3`); duplicate cleanup; parser decomposition; tagging optimization; remaining config/version/parser issues; and harness/logging/probe ownership cleanup.

## Verification

### Baseline
1. Run `pytest -q` and confirm the 761-test baseline.
2. Run three representative full pipeline executions at comparable times.
3. Record wall-clock time, preflight and phase durations, harness time, weather request counts, RSS requests/widening, LLM batch/fallback/retry counts, report counts, and validation result.

### Phase A
- Run targeted RSS, utility, pipeline, and connectivity tests, then `pytest -q`.
- Confirm local timezone logging, TLS verification, directory creation, response-status diagnostics, and complete timing output.

### Phase B
- Add mocked tests for provider failure/merge ordering, stable lake order, and one-fetch RSS widening.
- Run relevant weather/RSS tests, then `pytest -q`.
- Require unchanged report validity and at least 10s median total reduction across three runs before Phase C.

### Phase C
- Convert mocks to async and test retry backoff without real sleep.
- Test 429/502/503/504/timeout retry policy and non-retryable 4xx behavior.
- Benchmark batch sizes 3-6, then concurrency 2, against saved contexts and the actual vLLM host.

### Phase D
- Run `pytest -q`, `scripts/run_coverage.sh`, `python -m daily_brief config validate`, `python -m daily_brief config check-connectivity`, and one full pipeline execution.
- Confirm package, YAML, report, and project documentation versions are aligned.

## Blockers
- ~~Alert feature disposition is unresolved: restore and render it, or retire it completely.~~ Resolved: retired end-to-end in v1.0.97 (C.5).
- LLM concurrency is an experiment, not an assumed optimization; it depends on controlled vLLM benchmarking.
- **v1.0.111 live smoke test** — Obsidian vault access blocked. `PermissionError: [Errno 1]` on `os.listdir(LOG_DIR)` at `pipeline.py:140`. Path: `/Users/johnhoaglun/Documents/Obsidian_Shared_AI/Shared_AI/vault/OpenCode/Daily_Brief_v01/Dev/logs/`. Last successful run 2026-08-06. macOS Errno 1 (not Unix permission mask). No code change caused this. Unblock: check macOS security/settings, restart Obsidian, or temporarily override `config.yaml` directories for smoke test.
