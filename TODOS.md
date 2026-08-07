# TODO: Daily Brief v01 - v1.0.112

## Status
v1.0.112: Added summarizer topic-alignment validation — batch and recovery summaries that share zero significant keywords with the headline are rejected and fall back to `\[Auto\]`. Eliminates harness check 3.3 zero-overlap failures. 977/984 passing (7 pre-existing RSS dedup failures), config validate PASS. Live smoke test: WARN (no FAILs).

## Completed (v1.0.107 - v1.0.112)

### v1.0.112 — Summarizer topic-alignment guard
- **Bug:** Batch and individual recovery summaries could pass validation with zero shared keywords between headline and summary, producing grammatically valid but semantically unrelated summaries. Triggered external harness check 3.3 FAIL on live runs.
- **Fix:** Added `_has_topic_overlap()` check to `_is_valid_summary()` (line 531), explicit rejection log in batch path (`_summarize_sub_batch` line 638), and `_has_topic_overlap()` gate in individual recovery (`batch_summarize_all` line 739). Topic-mismatched summaries now fall through to `\[Auto\] <headline>` fallback.
- **Tests:** 7 new unit tests across `test_summarizer.py`: `TestHasTopicOverlap` (3), `TestIsValidSummaryTopicMismatch` (2), `TestIsValidSummaryStopWords` (2). 2 batch-level tests: `TestBatchTopicMismatchRejection` (2).
- **Files:** `src/daily_brief/llm/summarizer.py`, `tests/test_summarizer.py`, `tests/test_batch_behavior_regression.py`, `tests/test_batch_failure_fixtures.py`

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

## Blockers

### RSS Dedup Test Suite (7/984 pre-existing failures)
- All 7 failures are in `tests/test_sources/test_rss_dedup.py` — pre-existing, predates v1.0.112 changes. Root cause under investigation.

### Live Smoke Test — Obsidian Vault Access (RESOLVED v1.0.112)
- Vault access restored. v1.0.112 live smoke test completed successfully: WARN (zero FAILs, 55.63s, 77 valid stories). Previous v1.0.111 run failed check 3.3 (zero shared keywords).
