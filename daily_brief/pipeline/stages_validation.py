"""
Daily Brief — Pipeline validation stages (Phase 3D & Phase 5).

``stage_validate_stories`` validates Story objects immediately after
summarization (Phase 3D).  ``stage_validate`` validates the rendered
markdown report as a final sanity gate (Phase 5).

Both functions delegate to ``validate_stories()`` and ``validate_report()``
in ``daily_brief.validation`` to preserve late-patch resolution.
"""

import logging
import time

from daily_brief.llm.summarizer import StoryPipelineState

logger = logging.getLogger(__name__)


def _pip(name: str):
    """Resolve *name* from ``daily_brief.pipeline`` at call time."""
    import daily_brief.pipeline as _p  # noqa: F811, local import

    return getattr(_p, name)


# ---------------------------------------------------------------------------
# Phase 3D – Story validation
# ---------------------------------------------------------------------------


def stage_validate_stories(stories, ctx, log_fn):
    """Validate Story objects after summarization (Phase 3D).

    Returns ``(passed, issues)``.  *passed* is ``True`` when no more
    than 10 % of stories fail semantic checks.

    On failure logs the issues and returns ``True`` for *passed* so that
    ``main()`` in ``stages.py`` can still record the exit code — the
    decision to abort the pipeline is made by the caller itself.
    """
    t3d = time.monotonic()

    # Late-bind to support test patches and avoid circular imports
    validate_stories = _pip("validate_stories")

    passed, issues = validate_stories(stories)
    elapsed = time.monotonic() - t3d
    ctx.phase_timings["Phase 3D"] = elapsed

    if passed:
        log_fn(f"  Phase 3D completed in {elapsed:.2f}s")
        log_fn(f"  Validation: ALL {len(stories)} stories passed validation")
    else:
        log_fn(f"  Phase 3D completed in {elapsed:.2f}s")
        log_fn(
            f"  Validation: {len(issues)} issue(s) detected for {len(stories)} stories"
        )

    return passed, issues


# ---------------------------------------------------------------------------
# Phase 5 – Report validation
# ---------------------------------------------------------------------------


async def stage_validate(report_path, ctx, log_fn, run_start):
    """Validate the written report (Phase 5).

    Returns ``EXIT_CODE_VALIDATION`` (2) if validation fails,
    otherwise ``EXIT_CODE_SUCCESS`` (0).
    """
    # Late-bind to support test patches
    validate_report = _pip("validate_report")

    log_fn("\n[Phase 5] Validating report...")
    t5 = time.monotonic()
    validation_passed, validation_issues = validate_report(report_path)
    el5 = time.monotonic() - t5
    ctx.phase_timings["Phase 5"] = el5
    log_fn(f"  Phase 5 completed in {el5:.2f}s")

    if not validation_passed:
        total_elapsed = time.monotonic() - run_start
        log_fn(f"TOTAL PIPELINE TIME: {total_elapsed:.2f}s")
        log_fn("\n*** RUN VALIDATION FAILED — Report has broken summaries ***")
        log_fn(f"STATUS: FAILED ({len(validation_issues)} issues found)")
        print(f"\n*** RUN FAILED — {len(validation_issues)} validation issues found ***")
        print(f"File: {report_path}")
        print(f"Log: {ctx.run_logfile}")
        log_fn("\n=== PIPELINE EXIT CODE: VALIDATION FAILURE ===")
        return 2  # EXIT_CODE_VALIDATION

    total_elapsed = time.monotonic() - run_start
    log_fn(f"TOTAL PIPELINE TIME: {total_elapsed:.2f}s")
    log_fn("\n=== PIPELINE COMPLETED SUCCESSFULLY ===")
    print(f"\nDone. File: {report_path}")
    log_fn(f"  Time: {time.monotonic() - run_start:.1f}s")
    return 0  # EXIT_CODE_SUCCESS
