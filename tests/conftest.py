import asyncio
import importlib
import os

import aiohttp
import pytest

import daily_brief.pipeline


@pytest.fixture(autouse=True)
def _restore_pipeline_mocks():
    """Restore pipeline module attributes patched by contract tests to prevent
    mock leaks from bleeding into other test suites.

    In Python 3.9+ asyncio.run() closes event loops, leaving get_event_loop()
    unable to find one. This fixture ensures a fresh loop is available before
    each test runs.
    """
    _real_listdir = os.listdir
    _real_session = aiohttp.ClientSession
    _loop_policy = asyncio.get_event_loop_policy()

    # Ensure a fresh event loop is available for this test
    # This prevents "Event loop is closed" errors from previous tests
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except Exception:
        pass

    yield

    daily_brief.pipeline.aiohttp.ClientSession = _real_session
    daily_brief.pipeline.os.listdir = _real_listdir
    # Remove any leftover mock objects from _pipeline_patch_group and re-import
    # the real function references from daily_brief.pipeline's own imports
    for attr in (
        "write_report",
        "validate_config",
        "fetch_weather",
        "fetch_and_dedup",
        "StoryPipelineState",
        "stage_extract_article",
        "llm_batch_summarize_all",
        "build_sections_from_stories",
        "ordered_categories_for_render",
        "cleanup_old_files",
        "build_markdown",
        "validate_report",
        "run_test_harness",
        "create_llm_client",
    ):
        if hasattr(daily_brief.pipeline, attr):
            delattr(daily_brief.pipeline, attr)
    # Re-import the module to restore all real references
    importlib.reload(daily_brief.pipeline)
    # Restore event loop policy after tests that modify it (e.g., benchmark tests)
    try:
        asyncio.set_event_loop_policy(_loop_policy)
    except Exception:
        pass
