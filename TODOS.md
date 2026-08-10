# TODO: Daily Brief v01 — v1.0.143 (Active)

## Remaining Work

## Priority 3 - Packaging, CI, And Repository Hygiene
- [ ] Establish one canonical version source and add a release-consistency check for package/runtime/YAML/README/tracking files.
- [ ] Add `pyproject.toml` with `src` package discovery and declared runtime/test dependencies; replace per-test/script `sys.path` mutation with editable installation.
- [ ] Add dependency locking appropriate to the selected package manager and CI for supported Python versions, tests, config validation, lint/format/type checks, warnings policy, and opt-in integration checks.
- [ ] Repair `scripts/run_tests.sh` unreachable failure reporting caused by `set -e`; add a measured coverage threshold to `scripts/run_coverage.sh`.
- [ ] Remove tracked generated coverage databases and add standard Python, pytest, coverage, HTML-report, and virtual-environment patterns to `.gitignore`.
- [ ] Add the intended license text or remove the README MIT claim until licensing is confirmed.

## Verification Gates
- [ ] Run a fresh environment with `pip install .[test]`, `python -m pytest`, and `python -m daily_brief config validate` after packaging is added.
- [ ] Run controlled before/after benchmarks for concurrency and backpressure changes; retain only improvements that preserve report and harness validity.
- [ ] Run a live smoke test after each implementation slice and record report validation, harness status, process exit status, duration, story count, and retention behavior.

## Blockers
- [ ] Product decision: define whether harness `WARN` and `SKIPPED` should cause a nonzero process exit.
- [ ] Product decision: select the intended license before adding a license file and package metadata.
