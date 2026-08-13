"""
Daily Brief — LLM batch summarization.

Compatibility facade: imports from split modules for backward compatibility.
"""
from __future__ import annotations

import asyncio
import difflib
import logging
import re

from daily_brief.config import (
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
    _generate_auto_fallback as _generate_auto_fallback,
    _has_topic_overlap as _has_topic_overlap,
    _is_boilerplate as _is_boilerplate,
    _is_refusal as _is_refusal,
    _is_valid_summary as _is_valid_summary,
    _significant_words as _significant_words,
)
from daily_brief.llm.summary_service import _summarize as _summarize
from daily_brief.llm.summary_service import _summarize_sub_batch as _summarize_sub_batch
from daily_brief.llm.summary_service import StoryPipelineState
from daily_brief.llm.summary_coordinator import batch_summarize_all
from daily_brief.utils import _count_sentences as _count_sentences
from daily_brief.utils import _safe_sentence_summary as _safe_sentence_summary

logger = logging.getLogger(__name__)

__all__ = [
    "StoryPipelineState",
    "batch_summarize_all",
    "parse_batch_summary_response",
    "LLM_SUMMARY_RETRY_ATTEMPTS",
    "_is_refusal",
    "_is_boilerplate",
    "_is_valid_summary",
    "_has_topic_overlap",
    "_generate_auto_fallback",
    "_significant_words",
    "_summarize",
    "_summarize_sub_batch",
    "_count_sentences",
    "_safe_sentence_summary",
    "LLM_MODEL",
    "LLM_SUMMARY_CONTEXT_CHARS",
    "LLM_SUMMARY_OPTIONS",
    "LLM_SUMMARY_RETRY_ATTEMPTS",
    "LLM_SUMMARY_RETRY_BACKOFF",
    "LLM_SUMMARY_TRIM_MIN_CHARS",
    "SUMMARY_PROMPT",
    "SUMMARY_STRICT_PROMPT",
    "SYSTEM_BATCH_PROMPT",
    "logger",
]
