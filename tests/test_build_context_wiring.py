"""Reduced: ONE context construction verification and ONE boundary case."""

import asyncio
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from daily_brief.config import LLM_CONTEXT_PREVIEW_CHARS
from daily_brief.llm.summarizer import StoryPipelineState
from daily_brief.utils import build_context


def _make_story(context=None, category="News"):
    s = StoryPipelineState(
        title="Test Headline", link="https://example.com/1",
        snippet="", pub_dt="2024-01-01", category=category,
    )
    if context is not None:
        s.context = context
    s.summary = None
    return s


class TestBuildContextWiring(TestCase):
    def test_build_context_uses_configured_preview_chars(self):
        """build_context (via _summarize_sub_batch) calls with preview_chars=LLM_CONTEXT_PREVIEW_CHARS."""
        s1 = _make_story(context="A" * 700, category="Finance")
        s2 = _make_story(context="B" * 700, category="Finance")

        build_ctx_calls = []

        def capture(story, preview_chars=None):
            build_ctx_calls.append(preview_chars)
            return str(story.context)[:400]

        with patch("daily_brief.llm.summary_service.build_context", side_effect=capture):
            client = MagicMock()
            client.chat_completions_create = AsyncMock(
                return_value=MagicMock(
                    choices=[MagicMock(message=MagicMock(
                        content="STORY_0 | Finance = Summary.\nSTORY_1 | Finance = Summary."))]
                )
            )

            async def _run():
                from daily_brief.llm.summary_service import _summarize_sub_batch
                return await _summarize_sub_batch(client, "Finance", [s1, s2])

            asyncio.get_event_loop().run_until_complete(_run())

        self.assertEqual(len(build_ctx_calls), 2)
        for call_arg in build_ctx_calls:
            self.assertEqual(call_arg, LLM_CONTEXT_PREVIEW_CHARS)


class TestBuildContextBoundary(TestCase):
    def test_context_truncates_at_custom_chars(self):
        """When context >= 50 chars, it is truncated to preview_chars."""
        s = _make_story(context="X" * 500, category="Cat")
        result = build_context(s, preview_chars=25)
        self.assertEqual(len(result), 25)
        self.assertEqual(result, "X" * 25)

    def test_fallback_truncation(self):
        """Fallback path truncates at preview_chars."""
        s = _make_story(context=None, category="MyCat")
        s.snippet = "My snippet text here"
        result = build_context(s, preview_chars=15)
        self.assertLessEqual(len(result), 15)

    def test_config_preview_chars_value(self):
        self.assertEqual(LLM_CONTEXT_PREVIEW_CHARS, 600)


if __name__ == "__main__":
    import unittest
    unittest.main()
