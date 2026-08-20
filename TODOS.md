# TODO: Daily Brief v01

Current baseline: 269 tests, 74.70% ratio (≤75% cap). All P0-P3 review findings completed — detailed history in `SUMMARY.md`.

## Active

## Completed — Recent releases (v1.0.163–v1.0.169)

Performance cache optimizations in `summary_parser.py` (word-set + normalized-headline fuzzy matching + all-pairs validation) and `tagging.py` (keyword word-count cache). Structural cleanup: `weather.py` split into orchestrator + `weather_model.py` (102-line pure merge logic). All zero behavioral changes.

## Past work — Completed (see `SUMMARY.md` for details)

- v1.0.165: RSS widening cursor optimization
- v1.0.163-1.0.164: Report contracts + weather late-binding + ratio cap enforcement
- v1.0.161: Phase 3D semantic validation enforcement
- v1.0.159: Config override correctness + Git provenance
- v1.0.157: HTTP body-size safety
- P1: Pipeline stage extraction, concurrency fix, build_context wiring

- P0: File size cap, test module splits, summarizer split (1014→5 modules), config validator split.




