"""
Daily Brief — Batch summarization coordinator.

Orchestrates batch dispatch, retry, individual recovery, and fallback.
"""

import asyncio
import logging
import time
from datetime import datetime

from daily_brief.config import (
    LLM_CONTEXT_PREVIEW_CHARS,
    LLM_SUMMARY_RETRY_BACKOFF,
)
from daily_brief.llm.summary_metrics import SummaryMetrics, empty_metrics
from daily_brief.llm.summary_quality import (
    _generate_auto_fallback,
    _is_valid_summary,
)
from daily_brief.llm.summary_service import StoryPipelineState, _summarize as _summarize
from daily_brief.llm.summary_service import _summarize_sub_batch as _summarize_sub_batch
from daily_brief.utils import build_context

logger = logging.getLogger(__name__)

async def batch_summarize_all(
    client,
    stories,
    session=None,
    *,
    batch_size: int = 3,
    max_concurrency: int = 1,
    recovery_max_concurrency: int = 2,
    recovery_deadline_s: float = 0.0,
):
    """Async batch summarization with batch retry, individual recovery, fallback, and structured metrics.

    Args:
        client: LLM client with chat_completions_create method
        stories: List of StoryPipelineState objects
        session: Optional HTTP session (unused, kept for API compatibility)
        batch_size: Stories per sub-batch (default 3)
        max_concurrency: Max concurrent sub-batch LLM calls (default 1, serial)

    Returns SummaryMetrics with full accounting of all outcomes.
    """
    if not stories:
        return empty_metrics()

    t_start = time.monotonic()

    # Group by category
    by_category = {}
    for s in stories:
        by_category.setdefault(s.category, []).append(s)

    # Collect all sub-batches
    all_sub_batches = []
    for cat_name, cat_stories in by_category.items():
        for i in range(0, len(cat_stories), batch_size):
            all_sub_batches.append((cat_name, cat_stories[i : i + batch_size]))

    metrics = SummaryMetrics(total_stories=len(stories), sub_batches=len(all_sub_batches))

    # Phase 1: Initial batch dispatch
    batch_results = []
    if max_concurrency > 1:
        sem = asyncio.Semaphore(max_concurrency)
        tasks = [
            _summarize_sub_batch(client, cat_name, sb, semaphore=sem)
            for cat_name, sb in all_sub_batches
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                cat_name, _ = all_sub_batches[i]
                logger.warning(f"BATCH SUB-BATCH EXCEPTION ({cat_name}): {result}")
                batch_results.append({"success": False, "valid_count": 0, "failed": True})
            else:
                batch_results.append(result)
    else:
        for cat_name, sb in all_sub_batches:
            result = await _summarize_sub_batch(client, cat_name, sb)
            batch_results.append(result)

    metrics.batch_calls = len(all_sub_batches)

    # Phase 2: Retry failed full sub-batches once
    failed_indices = [i for i, r in enumerate(batch_results) if r.get("failed")]

    if failed_indices:
        metrics.batch_retries = len(failed_indices)
        metrics.batch_failures = len(failed_indices)

        # Small backoff before retry
        backoff = LLM_SUMMARY_RETRY_BACKOFF[0] if LLM_SUMMARY_RETRY_BACKOFF else 0.5
        await asyncio.sleep(backoff)

        retry_entries = [(all_sub_batches[i][0], all_sub_batches[i][1]) for i in failed_indices]
        retry_results = []
        if max_concurrency > 1:
            sem = asyncio.Semaphore(max_concurrency)
            retry_tasks = [
                _summarize_sub_batch(client, cat_name, sb, semaphore=sem)
                for cat_name, sb in retry_entries
            ]
            raw = await asyncio.gather(*retry_tasks, return_exceptions=True)
            for idx, result in enumerate(raw):
                if isinstance(result, Exception):
                    cat_name, _ = retry_entries[idx]
                    logger.warning(f"BATCH RETRY EXCEPTION ({cat_name}): {result}")
                    retry_results.append({"success": False, "valid_count": 0, "failed": True})
                else:
                    retry_results.append(result)
        else:
            for cat_name, sb in retry_entries:
                result = await _summarize_sub_batch(client, cat_name, sb)
                retry_results.append(result)

        metrics.batch_calls += len(failed_indices)

        for idx, result in enumerate(retry_results):
            original_index = failed_indices[idx]
            batch_results[original_index] = result

    # Phase 3: Individual recovery for unresolved stories with bounded concurrency
    needs_recovery = [s for s in stories if not s.summary or not s.summary.strip()]
    recovery_count = 0
    recovery_started = 0

    if needs_recovery:
        deadline_ts = time.monotonic() + recovery_deadline_s if recovery_deadline_s > 0 else None

        async def _recover_one(s):
            nonlocal recovery_count, recovery_started
            recovery_started += 1
            if deadline_ts is not None and time.monotonic() >= deadline_ts:
                return  # Past deadline, skip
            context = build_context(s, preview_chars=LLM_CONTEXT_PREVIEW_CHARS)
            try:
                coro = _summarize(client, context, title=s.title)
                if deadline_ts is not None:
                    remaining = deadline_ts - time.monotonic()
                    if remaining <= 0:
                        return
                    try:
                        retry = await asyncio.wait_for(coro, timeout=remaining)
                    except asyncio.TimeoutError:
                        return
                else:
                    retry = await coro
            except asyncio.CancelledError:
                raise
            except Exception:
                return
            if _is_valid_summary(retry, s.title):
                s.summary = retry
                recovery_count += 1
            elif not s.summary or not s.summary.strip():
                s.summary = _generate_auto_fallback(s.title)

        sem = asyncio.Semaphore(recovery_max_concurrency)

        async def _sem_wrapped(s):
            async with sem:
                await _recover_one(s)

        tasks = [asyncio.create_task(_sem_wrapped(s)) for s in needs_recovery]

        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.warning(f"RECOVERY GATHER ERROR: {e}")

        # Cancel all tasks if deadline is now past
        if deadline_ts is not None and time.monotonic() >= deadline_ts:
            logger.warning(
                f"[RECOVERY DEADLINE] exhausted after {recovery_deadline_s}s -- cancelling remaining work"
            )
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            # Assign [Auto] to stories still unresolved after cancellation
            for s in needs_recovery:
                if not s.summary or not s.summary.strip():
                    s.summary = _generate_auto_fallback(s.title)

    # Phase 4: Count final outcomes
    auto_fallbacks = 0
    unavailable = 0
    final_valid = 0
    final_invalid = 0

    for s in stories:
        if not s.summary or not s.summary.strip():
            final_invalid += 1
        elif s.summary.strip().startswith("[Summary Unavailable]"):
            unavailable += 1
        elif s.summary.strip().startswith("[Auto]"):
            auto_fallbacks += 1
        else:
            final_valid += 1

    metrics.individual_recovery_attempts = recovery_started
    metrics.individual_recovered = recovery_count
    metrics.auto_fallbacks = auto_fallbacks
    metrics.unavailable_summaries = unavailable
    metrics.final_valid = final_valid
    metrics.final_invalid = final_invalid
    metrics.elapsed_s = time.monotonic() - t_start

    # Logging
    if auto_fallbacks:
        logger.info(
            f"[AUTO FALLBACK] {auto_fallbacks} stories fell back to [Auto] headline summary"
        )
    if recovery_count:
        logger.info(
            f"[BATCH RETRY] {recovery_count}/{len(needs_recovery)} empty batch stories recovered via single-story LLM"
        )
    if metrics.batch_retries:
        logger.info(f"[BATCH RETRY] {metrics.batch_retries} sub-batches retried")

    return metrics
