"""
Daily Brief — LLM summary service.

Single-story summarize and sub-batch processing with retry and quality checks.
"""

import asyncio
import logging
import time

from daily_brief.config import (
    LLM_CONTEXT_PREVIEW_CHARS,
    LLM_MODEL,
    LLM_SUMMARY_CONTEXT_CHARS,
    LLM_SUMMARY_OPTIONS,
    LLM_SUMMARY_RETRY_ATTEMPTS,
    LLM_SUMMARY_RETRY_BACKOFF,
    LLM_SUMMARY_TRIM_MIN_CHARS,
    SUMMARY_PROMPT,
    SUMMARY_STRICT_PROMPT,
    SYSTEM_BATCH_PROMPT,
)
from daily_brief.llm.summary_parser import parse_batch_summary_response
from daily_brief.llm.summary_quality import (
    _generate_auto_fallback,
    _has_topic_overlap,
    _is_boilerplate,
    _is_valid_summary,
)
from daily_brief.llm.summary_metrics import SummaryMetrics, empty_metrics
from daily_brief.models import Story
from daily_brief.utils import build_context
from datetime import datetime

logger = logging.getLogger(__name__)

StoryPipelineState = Story

async def _summarize(
    client, context, title=None, min_chars=LLM_SUMMARY_TRIM_MIN_CHARS, strict=False
):
    """Async summary call with configurable retry and boilerplate detection.

    On retry: switches to strict prompt, applies exponential backoff.
    If all attempts exhausted: returns [Auto] {title} fallback (deterministic
    summary from headline). Only falls through to "[Summary Unavailable]" if
    title is also missing.

    Configured via runtime_defaults.summary_retry in config.yaml.
    """
    if not context or len(context.strip()) < min_chars:
        return None

    max_attempts = LLM_SUMMARY_RETRY_ATTEMPTS
    backoff_delays = list(LLM_SUMMARY_RETRY_BACKOFF) if LLM_SUMMARY_RETRY_BACKOFF else []
    prompt = SUMMARY_STRICT_PROMPT if strict else SUMMARY_PROMPT

    for attempt in range(max_attempts):
        try:
            t0 = time.monotonic()
            r = await client.chat_completions_create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": context[:LLM_SUMMARY_CONTEXT_CHARS]},
                ],
                **LLM_SUMMARY_OPTIONS,
            )
            logger.debug(f"{'STRICT ' if strict else ''}SUMMARIZE: {time.monotonic() - t0:.2f}s")
            summary_text = r.choices[0].message.content or ""
            summary_text = " ".join(
                [ln.strip() for ln in str(summary_text).splitlines() if ln.strip()]
            )
            if not summary_text.strip():
                logger.warning(f"Empty LLM response on attempt {attempt + 1}")
                is_last = attempt >= max_attempts - 1
                if not is_last:
                    delay = (
                        backoff_delays[attempt]
                        if attempt < len(backoff_delays)
                        else backoff_delays[-1]
                    )
                    logger.warning(
                        f"[RETRY] attempt {attempt + 1}/{max_attempts} empty response, retrying in {delay}s"
                    )
                    await asyncio.sleep(delay)
                    prompt = SUMMARY_STRICT_PROMPT
                    strict = True
                    continue
            if not strict and _is_boilerplate(summary_text):
                logger.warning(
                    f"BOILERPLACE DETECTED in summary attempt {attempt + 1}, retrying with strict prompt..."
                )
                prompt = SUMMARY_STRICT_PROMPT
                strict = True
                continue
            return summary_text
        except Exception as e:
            is_last = attempt >= max_attempts - 1
            delay = (
                backoff_delays[attempt] if attempt < len(backoff_delays) else backoff_delays[-1]
            )
            if not is_last:
                logger.warning(
                    f"[RETRY] attempt {attempt + 1}/{max_attempts} failed ({e}), retrying in {delay}s"
                )
                await asyncio.sleep(delay)
                prompt = SUMMARY_STRICT_PROMPT
                strict = True
            else:
                logger.warning(f"{'STRICT ' if strict else ''}SUMMARIZE ERROR (final): {e}")
    # Fallback: deterministic auto-summary from title
    return _generate_auto_fallback(title)

async def _summarize_sub_batch(client, cat_name, sub_batch, *, semaphore=None, batch_size=3):
    """Process one sub-batch of stories through a single LLM batch call.

    Args:
        client: LLM client with chat_completions_create method
        cat_name: Category name for logging
        sub_batch: List of StoryPipelineState objects
        semaphore: Optional asyncio.Semaphore for bounded concurrency
        batch_size: Unused parameter kept for API compatibility
    """
    # Build contexts for this sub-batch
    valid_count = 0
    context_lines = []
    for idx, s in enumerate(sub_batch):
        context_parts = [s.title]
        content = build_context(s, preview_chars=LLM_CONTEXT_PREVIEW_CHARS)
        if len(content) > LLM_CONTEXT_PREVIEW_CHARS:
            content = content[:LLM_CONTEXT_PREVIEW_CHARS]
        context_parts.append(content)
        entry = f"{idx + 1}. {cat_name}\n" + "\n".join(context_parts)
        context_lines.append(entry)

    batch_text = "\n---\n\n".join(context_lines)

    try:
        t0 = time.monotonic()
        if semaphore:
            async with semaphore:
                r = await client.chat_completions_create(
                    model=LLM_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_BATCH_PROMPT},
                        {"role": "user", "content": batch_text},
                    ],
                    **LLM_SUMMARY_OPTIONS,
                )
        else:
            r = await client.chat_completions_create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_BATCH_PROMPT},
                    {"role": "user", "content": batch_text},
                ],
                **LLM_SUMMARY_OPTIONS,
            )
        elapsed = time.monotonic() - t0
        sub_batch_label = f"{cat_name} (batch {len(sub_batch)})"
        logger.debug(f"BATCH SUMMARIZE ({sub_batch_label}): {elapsed:.1f}s")

        resp_text = r.choices[0].message.content if r.choices else ""
        logger.debug(f"BATCH OUTPUT ({sub_batch_label}): {resp_text[:400]}")

        parsed_summaries = parse_batch_summary_response(
            resp_text, len(sub_batch), story_headlines=[s.title for s in sub_batch]
        )
        for idx, s in enumerate(sub_batch):
            summary = parsed_summaries[idx] if idx < len(parsed_summaries) else ""
            headline = s.title.strip()
            if not summary or not summary.strip():
                s.summary = ""
                continue
            if _is_boilerplate(summary):
                logger.warning(
                    f"BOILERPLACE DETECTED for story {idx} ({headline}): '{summary[:80]}...' — marking for fallback"
                )
                s.summary = ""
                continue
            if not _has_topic_overlap(summary, headline):
                logger.warning(
                    f"TOPIC MISMATCH for story {idx} ({headline}): summary shares zero keywords — marking for fallback"
                )
                s.summary = ""
                continue
            if _is_valid_summary(summary, headline):
                s.summary = summary
                valid_count += 1
            else:
                s.summary = ""

    except Exception as e:
        logger.warning(f"BATCH SUMMARIZE ERROR ({cat_name}): {e}")
        for s in sub_batch:
            s.summary = ""
        return {"success": False, "valid_count": 0, "failed": True}

    return {"success": valid_count > 0, "valid_count": valid_count, "failed": valid_count == 0}
