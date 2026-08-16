"""Daily Brief — Pipeline Orchestration (5 phases: weather, RSS, LLM, render, validate)."""

from __future__ import annotations

import aiohttp
import asyncio
import os
import sys
import time

from daily_brief.config import (
    ARTICLE_MAX_CONCURRENCY, CATEGORIES, CONFIG_YAML,
    CATEGORY_PRIORITY, DEFAULT_AGE_LIMIT_HOURS, FRONTMATTER_TAG_SEEDS, LLM_MODEL,
    LLM_SUMMARY_BATCH_SIZE, LLM_SUMMARY_MAX_CONCURRENCY, LOG_DIR,
    MAX_LOG_VERSIONS, NEWS_DIR, OLLAMA_HOST, PREFLIGHT_CHECKS_ENABLED,
    TIMEZONE, USER_AGENT, VERSION, WEATHER_LAT, WEATHER_LON, WEATHER_SECTION_TITLE,
)
from daily_brief.categorization import ordered_categories_for_render
from daily_brief.sources.rss import format_pub_date
from daily_brief.config_validator import validate_config
from daily_brief.llm import create_llm_client
from daily_brief.llm.summarizer import StoryPipelineState, batch_summarize_all as llm_batch_summarize_all
from daily_brief.llm.summary_metrics import SummaryMetrics
from daily_brief.sources.article import stage_extract_article
from daily_brief.sources.weather import fetch_weather
from daily_brief.pipelines.rss_dedup import fetch_and_dedup
from daily_brief.rendering import cleanup_old_files
from daily_brief.rendering.report import (
    build_markdown, build_sections_from_stories, compute_output_path, write_report,
)
from daily_brief.validation import validate_report
from daily_brief.pipeline.stages import (
    main, stage_weather,
    EXIT_CODE_SUCCESS, EXIT_CODE_CONFIG, EXIT_CODE_VALIDATION,
)
from daily_brief.pipeline.context import (
    DEFAULT_CONTENT_AGE_WINDOW_HOURS, RunContext,
    _EventLoopLagMonitor, _coerce_temperature_f, _count_extracted,
    _normalize_weather_for_rendering, _percentile,
    _setup_run_logger, _teardown_run_logger, ACTIVE_TIMEZONE,
)

# --- Test-hub: task-local context accessor (replaces dead _current_context) ---
import contextvars

_current_context_var: contextvars.ContextVar[Optional[RunContext]] = contextvars.ContextVar(
    "_current_context_var", default=None,
)
# Legacy module-level holder — persists after run_until_complete() returns,
# providing backward compat for tests that do not use asyncio.gather().
_current_context: Optional[RunContext] = None


def get_current_run_context() -> Optional[RunContext]:
    """Return the RunContext for the *currently executing task*.

    Falls back to the module-level ``_current_context`` when the value is not
    set (e.g. after ``run_until_complete`` returns), providing backward
    compatibility.  For truly concurrent tests (``asyncio.gather``), use
    ``_current_context`` directly inside each coroutine _before_ that
    coroutine yields back to the gather parent.
    """
    ctx = _current_context_var.get()
    if ctx is not None:
        return ctx
    return _current_context


def _set_current_run_context(ctx: RunContext) -> None:
    """Called by main() — sets both task-local and module-level context."""
    _current_context_var.set(ctx)
    global _current_context
    _current_context = ctx


__all__ = [
    "aiohttp", "asyncio", "os", "sys", "time",
    "ARTICLE_MAX_CONCURRENCY", "CATEGORIES", "CONFIG_YAML",
    "DEFAULT_AGE_LIMIT_HOURS", "FRONTMATTER_TAG_SEEDS", "LLM_MODEL",
    "LLM_SUMMARY_BATCH_SIZE", "LLM_SUMMARY_MAX_CONCURRENCY", "LOG_DIR",
    "MAX_LOG_VERSIONS", "NEWS_DIR", "OLLAMA_HOST", "PREFLIGHT_CHECKS_ENABLED",
    "TIMEZONE", "USER_AGENT", "VERSION", "WEATHER_LAT", "WEATHER_LON", "WEATHER_SECTION_TITLE",
    "CATEGORIES", "CATEGORY_PRIORITY", "format_pub_date",
    "main", "stage_weather",
    "_EventLoopLagMonitor", "_percentile", "_count_extracted",
    "_normalize_weather_for_rendering", "_coerce_temperature_f",
    "EXIT_CODE_SUCCESS", "EXIT_CODE_CONFIG", "EXIT_CODE_VALIDATION",
    "DEFAULT_CONTENT_AGE_WINDOW_HOURS", "RunContext",
    "_setup_run_logger", "_teardown_run_logger", "ACTIVE_TIMEZONE",
    "get_current_run_context", "_current_context",
    "validate_config", "validate_report", "create_llm_client", "llm_batch_summarize_all",
    "fetch_weather", "fetch_and_dedup", "stage_extract_article",
    "ordered_categories_for_render", "build_sections_from_stories", "build_markdown",
    "compute_output_path", "write_report", "cleanup_old_files", "StoryPipelineState",
    "SummaryMetrics",
]
