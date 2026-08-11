# TODO: Daily Brief v01 — v1.0.144 (Priority 3 Complete)

## Priority 3 — Packaging, CI, and Repository Hygiene (COMPLETE)
- [x] Canonical version source (`daily_brief/_version.py`) — single `__version__` string.
- [x] `pyproject.toml` with flat-layout discovery, dynamic version, runtime/test dependencies, console entry point.
- [x] `uv.lock` dependency lockfile (56 packages resolved).
- [x] GitHub Actions CI (test matrix 3.9/3.13, build verification, ruff format/lint, mypy).
- [x] Ruff format applied; safe lint auto-fixes (296 fixes).
- [x] Mypy baseline (43 pre-existing errors, report-only).
- [x] `scripts/run_tests.sh` and `scripts/run_coverage.sh` failure reporting repaired.
- [x] `.gitignore` expanded (coverage variants, build/dist, venv, lint/type caches).
- [x] MIT `LICENSE` file added.
- [x] `sys.path` mutation removed from `tests/test_parser_golden.py`.
- [x] Wheel-compatible config delivery (`daily_brief/config.yaml` packaged, loader fallback chain).

## Verification Gates
- [x] `python -m pytest` — 635/635 passing.
- [x] `python -m daily_brief config validate` — PASS.
- [x] Wheel and source distribution build verified.
- [ ] Run controlled before/after benchmarks for concurrency and backpressure changes.
- [ ] Run a live smoke test and record report validation, harness status, process exit status, duration, story count, and retention behavior.

## Blockers
- [ ] Product decision: define whether harness `WARN` and `SKIPPED` should cause a nonzero process exit.
- [x] License confirmed: MIT (file added, package metadata set).
