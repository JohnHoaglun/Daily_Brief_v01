# TODO: Daily Brief v01 - v1.0.68

## Status Legend
- `[ ]` TODO
- `[~]` In progress
- `[!]` Blocked by a decision or external dependency

## Active Work: Research Review Execution
Detailed findings, implementation constraints, and verification commands are in `PLAN.md`.

### Phase A - Quick Wins (2-3 hours, low risk)
- [x] A.1 `Bug-1`: import `ZoneInfo` for RSS age filtering.
- [ ] A.2 `Clean-8`: precompile the HTML-strip regex.
- [ ] A.3 `Clean-5`: remove the unused `sum_results` assignment.
- [ ] A.4 `Clean-9`: retain one `WEATHER_POINT_URL` assignment.
- [ ] A.5 `Clean-6`: remove unused configuration constants.
- [ ] A.6 `Rel-3`: create output/log directories before logging setup or listing.
- [ ] A.7 `Rel-4`: restore TLS verification in RSS connectivity probes.
- [ ] A.8 `Bug-6`: reject and diagnose unsuccessful RSS HTTP responses.
- [ ] A.9 `Quality-6`: add monotonic total and per-phase timings.
- [ ] A.10 `Bug-5`: correct `dedupi_window_hours` to `dedupe_window_hours`.

### Phase B - High-Impact Performance (4-6 hours, low-medium risk)
- [ ] B.1 `Perf-1`: fetch lake levels with bounded concurrency and stable output ordering.
- [ ] B.2 `Perf-2`: concurrently collect independent weather sources, then merge deterministically.
- [ ] B.3 `Perf-3`: eliminate the redundant Wunderground dashboard request.
- [ ] B.4 `Perf-4`: pass configured coordinates to climate retrieval or cache fixed-ZIP geocoding.
- [ ] B.5 `Perf-5`: reuse the outer HTTP session for article extraction.
- [ ] B.6 `Perf-6` / `Bug-10`: fetch adequate RSS candidate pools once; widen locally and concurrently.
- [ ] B.7 `Perf-11`: make production preflight probes opt-in or short-TTL cached.
- [ ] B.8 `Arch-1`: separate weather provider fetching from deterministic merge/fallback policy.

### Phase C - Async, LLM, and Reliability (1-3 days, medium-high risk)
- [ ] C.1 `Perf-8` / `Perf-9`: migrate LLM calls to `AsyncOpenAI` and retry delays to `asyncio.sleep()`.
- [ ] C.2 `Perf-7`: benchmark LLM batch sizes 3-6 and concurrency 2 before production changes.
- [ ] C.3 `Rel-1` / `Rel-2`: centralize bounded HTTP retry and status handling.
- [ ] C.4 `Rel-6` / `Rel-7` / `Arch-2`: centralize batch retry, fallback, and summarization metrics.
- [!] C.5 `Bug-2` / `Bug-3` / `Bug-9`: decide whether to restore the alert feature end-to-end or remove it.

### Phase D - Architecture Follow-Up (2-4 days, medium risk)
- [ ] D.1 `Bug-4` / `Arch-4`: unify configuration schema, loading, validation, and imports.
- [ ] D.2 `Arch-3`: adopt one typed internal story representation.
- [ ] D.3 `Dup-1` to `Dup-4` / `Clean-1` to `Clean-3`: canonicalize duplicate utilities and request helpers.
- [ ] D.4 `Quality-3`: decompose batch-response parsing with golden LLM fixtures.
- [ ] D.5 `Quality-4` / `Perf-10`: precompile tagging patterns, compute tags once, and clarify boost semantics.
- [ ] D.6 `Bug-7`, `Bug-8`, `Bug-11`, `Perf-12`: resolve remaining configuration, version, and parser-loop issues.
- [ ] D.7 `Rel-5`, `Quality-2`, `Quality-5`, `Arch-5`: clarify harness failures, weather errors, logging, and probe ownership.

## Verification Gate
- [x] Establish a three-run timing and report-quality baseline before Phase A. (Recorded: 761 tests pass. Wall-clock 137–147s. P1 ~8s, P2 ~3.5s, P3 96–100s, P4 30s. LLM dominant.)
- [ ] Run phase-specific tests and `pytest -q` after each phase.
- [ ] Record timing medians, report validation, and production outcomes in `SUMMARY.md`.

## Blocked Decisions
- [!] Alert-system disposition is required before C.5.
- [!] LLM batching/concurrency changes require a controlled vLLM benchmark before adoption.
