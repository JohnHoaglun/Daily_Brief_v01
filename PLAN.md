# Plan: Daily_Brief_v01

## CURRENT STATUS --- Dynamic Weather Release

Current baseline is now **v1.0.7** on branch `dev_codex`.
Weather section now includes dynamic forecast and station/lake metrics with example-aligned layout and no fake fallback values.

## Release Track

### Done
- Weather section order matched to requirements examples.
- 3-sentence story summaries enforced via prompt.
- Station metrics (avg temp, avg rainfall, current month rainfall) wired to live sources.
- Lake table now differentiates Today / 1 Week Ago / 30 Days Ago.
- Hardcoded weather strings removed from pipeline logic.

### Next
- [x] Parser-level fixtures/tests backlog cleared.
- [x] Automated output-shape validation backlog cleared.
- [x] CI/nightly dry-run workflow backlog cleared.

---
