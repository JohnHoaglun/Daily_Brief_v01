# TODO: Daily Brief v01

Current baseline: 269 tests, 74.70% ratio (≤75% cap). All P0-P3 review findings completed — detailed history in `SUMMARY.md`.

## Active

## Completed — Recent releases (v1.0.163–v1.0.170)

Performance cache optimizations in `summary_parser.py` (word-set + fuzzy + all-pairs validation) and `tagging.py` (keyword word-count cache). Structural cleanup: `weather.py` → `weather_model.py` (102-line pure module). All zero behavioral changes.

## Past work — Completed

- v1.0.165: RSS widening cursor
- v1.0.163-1.0.164: Report contracts, ratio cap
- v1.0.161: Phase 3D validation enforcement
- v1.0.159: Config override, Git provenance
- v1.0.157: HTTP body-size safety
- P0: File size cap, 11 test module splits, summarizer (1014→5), config validator (614→2)
- P1: Pipeline stage extraction, concurrency fix, `build_context` wiring
- P2: Dead globals removal, regex dedup, module-level globals cleanup


