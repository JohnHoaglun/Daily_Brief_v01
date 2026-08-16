"""
Concurrency Contract -- Scheduling behavior tests.

Tests that Phase 1/2 timings are independently measurable and dispatched
concurrently, and that article extraction respects a concurrency bound.
"""

import asyncio
import os
import re
import tempfile
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from tests.concurrency_support import (
    _restore_aiohttp_client_session as _restore_aiohttp_client_session,
    _pipeline_patch_group as _pipeline_patch_group,
    _default_dedup_data as _default_dedup_data,
    _weather as _weather,
    _story as _story,
)


# ---------------------------------------------------------------------------
# 4. Independent Phase 1 / Phase 2 timing
# ---------------------------------------------------------------------------


class TestIndependentPhaseTimings(TestCase):
    """Phase 1 (weather) and Phase 2 (RSS) timings must be independently
    measurable even if run concurrently."""

    def tearDown(self):
        _restore_aiohttp_client_session()

    def test_phase_timings_records_both(self):
        """PHASE_TIMINGS must contain separate Phase 1 and Phase 2 entries."""
        tmpdir = tempfile.mkdtemp()
        patches = _pipeline_patch_group(tmpdir)
        for p in patches:
            p.__enter__()
        try:
            from daily_brief.pipeline import main as pm
            from daily_brief.pipeline import get_current_run_context

            asyncio.get_event_loop().run_until_complete(pm())
            ctx = get_current_run_context()

            assert ctx and "Phase 1" in ctx.phase_timings, "Phase 1 timing missing"
            assert ctx and "Phase 2" in ctx.phase_timings, "Phase 2 timing missing"
            for k in ("Phase 1", "Phase 2"):
                v = ctx.phase_timings[k]
                assert isinstance(v, (int, float)), f"{k} timing type {type(v)}"
        finally:
            for p in reversed(patches):
                p.__exit__(None, None, None)

    def test_phase_1_and_2_run_concurrent(self):
        """Phases 1 and 2 are dispatched concurrently via asyncio.gather().
        Verify with barrier: both phases start before either completes."""
        concurrent_max = [0]
        active = [0]
        barrier = [False]
        call_count = {"weather": 0, "rss": 0}

        async def slow_weather(*a, **kw):
            call_count["weather"] += 1
            active[0] += 1
            if active[0] > concurrent_max[0]:
                concurrent_max[0] = active[0]
            barrier[0] = True
            await asyncio.sleep(0.02)
            active[0] -= 1
            return _weather()

        async def slow_rss(*a, **kw):
            call_count["rss"] += 1
            active[0] += 1
            if active[0] > concurrent_max[0]:
                concurrent_max[0] = active[0]
            while not barrier[0]:
                await asyncio.sleep(0.001)
            await asyncio.sleep(0.02)
            active[0] -= 1
            return _default_dedup_data()

        tmpdir = tempfile.mkdtemp()
        # Build base patches without the weather/rss mocks
        base = _pipeline_patch_group(tmpdir)
        # Remove the original weather/rss patches and add our custom ones
        custom = [
            patch(
                "daily_brief.pipeline.fetch_weather",
                new_callable=AsyncMock,
                side_effect=slow_weather,
            ),
            patch(
                "daily_brief.pipeline.fetch_and_dedup",
                new_callable=AsyncMock,
                side_effect=slow_rss,
            ),
        ]
        all_patches = [
            b
            for b in base
            if not any(attr in b.attribute for attr in ("fetch_weather", "fetch_and_dedup"))
        ] + custom
        for p in all_patches:
            p.__enter__()
        try:
            from daily_brief.pipeline import main as pm

            asyncio.get_event_loop().run_until_complete(pm())
            assert call_count["weather"] > 0, "weather fetcher was not called"
            assert call_count["rss"] > 0, "RSS fetcher was not called"
            # If concurrent, peak concurrent count should be 2
            assert concurrent_max[0] == 2, (
                f"Expected 2 concurrent phases, got peak of {concurrent_max[0]}"
            )
        finally:
            for p in reversed(all_patches):
                p.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# 5. Bounded RSS/article concurrency
# ---------------------------------------------------------------------------


class TestBoundedArticleConcurrency(TestCase):
    """CONCURRENCY BUG: Phase 3A calls asyncio.gather for ALL stories
    simultaneously with no concurrency limit."""

    def tearDown(self):
        _restore_aiohttp_client_session()

    def test_article_fetch_is_bounded(self):
        """Article extraction is bounded by ARTICLE_MAX_CONCURRENCY.
        Peak concurrent extracts should not exceed the configured limit."""
        num_stories = 10
        stories = [
            (f"Story{i}", f"https://example.com/{i}", "snip", None, "cat")
            for i in range(num_stories)
        ]
        dedup = (stories, {"total_after": num_stories})

        max_concurrent = [0]
        concurrent_now = [0]

        async def counting_extract(story, session):
            concurrent_now[0] += 1
            if concurrent_now[0] > max_concurrent[0]:
                max_concurrent[0] = concurrent_now[0]
            await asyncio.sleep(0.01)
            concurrent_now[0] -= 1

        tmpdir = tempfile.mkdtemp()
        patches = _pipeline_patch_group(
            tmpdir,
            dedup_data=dedup,
            extract_mock=counting_extract,
            section_return={"cat": [_story()]},
        )

        for p in patches:
            p.__enter__()
        try:
            from daily_brief.pipeline import main as pm

            asyncio.get_event_loop().run_until_complete(pm())
        finally:
            for p in reversed(patches):
                p.__exit__(None, None, None)

        assert max_concurrent[0] > 0, (
            f"Expected concurrent extracts, got {max_concurrent[0]} out of {num_stories}"
        )
        assert max_concurrent[0] <= 4, f"Peak concurrency {max_concurrent[0]} exceeds limit of 4"

    def test_article_concurrency_configurable(self):
        """CONTRACT: Bounded concurrency should be configurable via
        ARTICLE_MAX_CONCURRENCY setting.  Implemented in v1.0.127."""
        import daily_brief.pipeline as pmod

        attrs = [a for a in dir(pmod) if "ARTICLE" in a.upper() and "CONCURRENCY" in a.upper()]
        assert attrs or hasattr(pmod, "ARTICLE_MAX_CONCURRENCY"), (
            "ARTICLE_MAX_CONCURRENCY config must exist after Wave 4"
        )
