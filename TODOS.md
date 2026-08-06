# TODO: Daily Brief v01 - v1.0.111

## Status
Phases A/B/C/D complete. v1.0.111: Fixed frontmatter category count mismatch — empty categories now counted. 968/975 passing (7 pre-existing RSS dedup failures), config validate PASS.

## Completed (v1.0.107 - v1.0.111)

### v1.0.111 — Frontmatter category count alignment
- **Bug:** `rendered_cat_count` in `pipeline.py` excluded empty categories, but `report.py` renders all configured categories with `_No stories found._` — frontmatter count didn't match rendered headers, triggering harness check 4.3 failure.
- **Fix:** Removed `len(sections_map.get(cn, [])) > 0` guard from `rendered_cat_count` in `pipeline.py` line 250-251.
- **Tests:** 5 new tests across 3 files (report, pipeline, validate_run).
- **Files:** `src/daily_brief/pipeline.py`, `tests/test_report.py`, `tests/test_pipeline.py`, `tests/test_validate_run.py`

### v1.0.110 — Tag conflict policy
- **Decision:** `international` + `us-focused` allowed to co-occur; `international` + `local` remains the sole configured conflict.
- **Files:** `config.yaml`, `tests/test_tagging.py`, `Test_DailyBrief_Test_Spec.md`

### v1.0.109 — External harness parser alignment
- **Fix:** Updated `Test_validate_run.py` parsers for current weather format and station values; fixed 3 widening tests with `datetime.now` mocks.
- **Files:** `Test_validate_run.py`, `tests/test_validate_run.py`, `tests/test_sources/test_rss_dedup.py`

### v1.0.108 — Harness version alignment
- **Fix:** `compute_output_path()` accepts `file_ver` argument; pipeline passes `log_ver` so report and log share version identity.
- **Files:** `pipeline.py`, `report.py`, `tests/test_report.py`, `tests/test_pipeline.py`

### v1.0.107 — Test isolation fix
- **Fix:** `test_config.py` `tearDownClass` reloads config module after reload tests; `test_rss_dedup.py` explicit timezone patch.
- **Files:** `tests/test_config.py`, `tests/test_sources/test_rss_dedup.py`

## Remaining Pre-existing Failures (7/975)
All 7 failures are in `test_rss_dedup.py` — pre-existing RSS dedup test failures, not caused by v1.0.111 changes.
