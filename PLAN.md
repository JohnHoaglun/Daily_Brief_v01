# PLAN: v1.0.138 — Extraction Measurement ✅ COMPLETE

## Status: COMPLETED — implementation done, 569/569 tests passing.

## Objective
Bound HTTP response handling so untrusted responses cannot exceed source-appropriate byte limits before parsing.

## Scope
- [x] Centralize bounded response streaming in `daily_brief/http_client.py`.
- [x] Default byte limit `DEFAULT_MAX_CONTENT_BYTES = 5 MB`; configurable per-call.
- [x] Reject excessive `Content-Length` before reading body.
- [x] Stream body with `ContentLengthError` on limit exceed.
- [x] Preserve current retry and status-acceptance semantics.
- [x] Mock support: `headers` and `content.iter_any()` across all test files.

## Verification
- [x] 11 new bounded-response tests in `test_http_client.py`.
- [x] 555/555 full suite passing, 0 regressions.
- [x] Config validation: PASS.

## Non-Goals
- Do not move HTML parsing off the event loop without benchmark evidence of loop lag.
- Do not change the RSS candidate pool or its widening behavior.
