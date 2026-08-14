"""
Regression tests for build_context wiring in summary_service and summary_coordinator,
plus direct build_context truncation behavior.

Goal: verify that build_context is called with preview_chars=LLM_CONTEXT_PREVIEW_CHARS
in all production call sites, and that non-default preview_chars values are respected.
"""

import asyncio
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from daily_brief.config import LLM_CONTEXT_PREVIEW_CHARS
from daily_brief.llm.summarizer import StoryPipelineState
from daily_brief.utils import build_context


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_story(category="News", context=None, snippet=None, title=None):
    """Build a StoryPipelineState for testing."""
    s = StoryPipelineState(
        title=title or "Test Headline",
        link="https://example.com/1",
        snippet=snippet or "",
        pub_dt="2024-01-01",
        category=category,
    )
    if context is not None:
        s.context = context
    s.summary = None
    return s


# ---------------------------------------------------------------------------
# build_context truncation
# ---------------------------------------------------------------------------


class TestBuildContextTruncation(TestCase):
    """Direct tests for build_context with non-default preview_chars."""

    def test_context_path_truncates_at_custom_chars(self):
        """When context >= 50 chars, it is truncated to preview_chars."""
        s = _make_story(context="X" * 500, snippet="skip", category="Cat")
        result = build_context(s, preview_chars=25)
        self.assertEqual(len(result), 25)
        self.assertEqual(result, "X" * 25)

    def test_fallback_path_truncates_at_custom_chars(self):
        """When context falls through to snippet/title, result is truncated."""
        s = _make_story(context=None, snippet="My snippet text here", category="MyCat")
        result = build_context(s, preview_chars=15)
        self.assertLessEqual(len(result), 15)

    def test_fallback_truncation_includes_category(self):
        """Fallback path should include category before truncation, truncate after."""
        s = _make_story(context=None, snippet="My snippet text here", category="MyCat")
        full = build_context(s, preview_chars=9999)
        truncated = build_context(s, preview_chars=15)
        self.assertTrue(truncated.startswith(full[:15]))

    def test_context_empty_no_snippet_category_only(self):
        """When context and snippet are empty, fallback uses category+title."""
        s = _make_story(context=None, snippet=None, title="The Title", category="news")
        result = build_context(s, preview_chars=3)
        self.assertEqual(len(result), 3)
        self.assertTrue(result.startswith("The"))

    def test_context_short_falls_to_fallback_with_custom_chars(self):
        """Short context (<50 chars) should go through fallback path."""
        s = _make_story(context="short", snippet="snippet text here", category="news")
        result = build_context(s, preview_chars=10)
        self.assertTrue(result.startswith("snippet"))
        self.assertLessEqual(len(result), 10)

    # -----------------------------------------------------------------------
    # Default value regression
    # -----------------------------------------------------------------------

    def test_default_returns_full_preview_when_context_long(self):
        """Default preview_chars (600) returns up to 600 chars from context."""
        s = _make_story(context="A" * 800, category="Cat")
        result = build_context(s)
        self.assertEqual(len(result), 600)

    def test_config_value_matches_default(self):
        """LLM_CONTEXT_PREVIEW_CHARS from config should equal 600."""
        self.assertEqual(LLM_CONTEXT_PREVIEW_CHARS, 600)


# ---------------------------------------------------------------------------
# summary_service._summarize_sub_batch wiring
# ---------------------------------------------------------------------------


class TestSummaryServiceWiring(TestCase):
    """Test that _summarize_sub_batch calls build_context with configured preview_chars."""

    def test_summarize_sub_batch_calls_build_context_with_configured_preview_chars(self):
        """_summarize_sub_batch must call build_context(story, preview_chars=LLM_CONTEXT_PREVIEW_CHARS)."""
        s1 = _make_story(category="Finance", context="A" * 700)
        s2 = _make_story(category="Finance", context="B" * 700)

        build_ctx_calls = []

        def capture_build_context(story, preview_chars=None):
            build_ctx_calls.append(preview_chars)
            return str(story.context)[:400]

        with patch("daily_brief.llm.summary_service.build_context", side_effect=capture_build_context):
            client = MagicMock()
            client.chat_completions_create = AsyncMock(
                return_value=MagicMock(
                    choices=[MagicMock(message=MagicMock(content="STORY_0 | Finance = Summary.\nSTORY_1 | Finance = Summary."))]
                )
            )

            async def _run():
                from daily_brief.llm.summary_service import _summarize_sub_batch

                return await _summarize_sub_batch(client, "Finance", [s1, s2])

            asyncio.get_event_loop().run_until_complete(_run())

        # build_context should have been called once per story in the sub-batch
        self.assertEqual(len(build_ctx_calls), 2)
        for call_arg in build_ctx_calls:
            self.assertEqual(call_arg, LLM_CONTEXT_PREVIEW_CHARS)


# ---------------------------------------------------------------------------
# summary_coordinator recovery wiring
# ---------------------------------------------------------------------------


class TestSummaryCoordinatorWiring(TestCase):
    """Test that the individual recovery path calls build_context with configured preview_chars."""

    def test_summary_coordinator_recovery_calls_build_context_with_configured_preview_chars(self):
        """batch_summarize_all (which includes individual recovery) must call build_context(story, preview_chars=LLM_CONTEXT_PREVIEW_CHARS) during recovery."""
        s1 = _make_story(category="Finance")
        s1.context = None
        s1.summary = None

        build_ctx_calls = []

        def capture_build_context(story, preview_chars=None):
            build_ctx_calls.append(preview_chars)
            return str(getattr(story, "snippet", ""))

        with patch("daily_brief.llm.summary_coordinator.build_context", side_effect=capture_build_context):
            client = MagicMock()
            first_call = [True]

            async def chat_completions_create(**kwargs):
                msgs = kwargs.get("messages", [])
                system = msgs[0]["content"] if msgs else ""
                if "BATCH" in system or "batch" in system.lower():
                    # Batch call returns empty to trigger recovery
                    return MagicMock(choices=[MagicMock(message=MagicMock(content=""))])
                # Single-story summary call
                return MagicMock(choices=[MagicMock(message=MagicMock(content="Finance = recovered summary."))])

            client.chat_completions_create = chat_completions_create

            async def _run():
                from daily_brief.llm.summarizer import batch_summarize_all

                return await batch_summarize_all(
                    client,
                    [s1],
                    batch_size=1,
                    max_concurrency=1,
                )

            result = asyncio.get_event_loop().run_until_complete(_run())

        # build_context should be called during recovery for the story that needs it
        self.assertTrue(len(build_ctx_calls) > 0, "build_context should be called during recovery")
        for call_arg in build_ctx_calls:
            self.assertEqual(call_arg, LLM_CONTEXT_PREVIEW_CHARS)

    def test_summary_coordinator_batch_calls_use_configured_chars(self):
        """The initial batch phase should also use LLM_CONTEXT_PREVIEW_CHARS."""
        s1 = _make_story(category="Finance", snippet="some text here")
        s2 = _make_story(category="Finance", snippet="more text here")

        build_ctx_calls = []

        def capture_build_context(story, preview_chars=None):
            build_ctx_calls.append(preview_chars)
            return "context"

        with patch("daily_brief.llm.summary_coordinator.build_context", side_effect=capture_build_context):
            client = MagicMock()
            client.chat_completions_create = AsyncMock(
                return_value=MagicMock(
                    choices=[MagicMock(
                        message=MagicMock(content="STORY_0 | Finance = Summary.\nSTORY_1 | Finance = Summary.")
                    )]
                )
            )

            async def _run():
                from daily_brief.llm.summarizer import batch_summarize_all

                return await batch_summarize_all(
                    client,
                    [s1, s2],
                    batch_size=2,
                    max_concurrency=1,
                )

            asyncio.get_event_loop().run_until_complete(_run())

        self.assertTrue(len(build_ctx_calls) >= 2, "build_context should be called for each story")
        for call_arg in build_ctx_calls[:2]:
            self.assertEqual(call_arg, LLM_CONTEXT_PREVIEW_CHARS)
