# PLAN: v1.0.127 — Wave 4 Concurrency Safety

## Objective
Resolve the four known concurrency-contract failures and add Phase 1/2 parallelism, bounded article extraction, and filesystem-backed run reservations.

## Scope Decisions
- Filesystem reservation for run identity (cross-process safe)
- Remove dead `widen_category` compatibility wrapper
- Remove logging consolidation scope out of this wave — deferred to RunContext follow-on
- Phase 1/2 parallelism in same release, not separate wave
- Article extraction bounded by configurable `runtime.article_max_concurrency` (default 4)

## Parallel Slice Plan
1. Agents A-D run concurrently (no shared file edits)
2. Merge and verify A-D in isolation
3. Single integration owner touches pipeline.py and concurrency contract tests

## Verification
- `tests/test_concurrency_contract.py`: 4 failing tests → 0
- Full pytest suite: 0 regressions
- Live smoke: PASS or WARN, zero FAILs
- Config validation: PASS

## Blockers
- None blocking. All dependencies established.
