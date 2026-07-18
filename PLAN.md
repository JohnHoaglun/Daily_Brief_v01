# Plan: Daily_Brief_v01

## CURRENT STATUS — Dynamic Weather Release

Current baseline is now **v1.0.6** on branch `dev_codex` (commit `3e27e66` in this workflow).  
Weather section now includes dynamic forecast and station/lake metrics with example-aligned layout and no fake fallback values.

## Release Track

### Done
- Weather section order matched to requirements examples.
- 3-sentence story summaries enforced via prompt.
- Station metrics (avg temp, avg rainfall, current month rainfall) wired to live sources.
- Lake table now differentiates Today / 1 Week Ago / 30 Days Ago.
- Hardcoded weather strings removed from pipeline logic.

### Next (if continuing)
- Add parser-level fixtures/tests for weather sources.
- Add automated output-shape validation against requirement examples.
- Add a small CI workflow for nightly dry-run validation.

---
