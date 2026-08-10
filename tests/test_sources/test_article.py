"""
Unit tests for daily_brief/sources/article.py.
Article extraction and context building.
"""

from __future__ import annotations

import asyncio
from unittest import TestCase

from daily_brief.config import LLM_CONTEXT_PREVIEW_CHARS
from daily_brief.sources.article import stage_extract_article
from daily_brief.utils import build_context


class MockStory:
    """Minimal story object with attributes article.py expects."""

    def __init__(
        self,
        title="Test Title",
        link="https://example.com/article",
        category="Test Category",
        snippet="",
        context="",
    ):
        self.title = title
        self.link = link
        self.category = category
        self.snippet = snippet
        self.context = context


class _FakeContent:
    def __init__(self, data: str):
        self._data = data.encode("utf-8")

    async def iter_any(self):
        yield self._data


class FakeResp:
    status = 200
    headers = {}

    def __init__(self, body):
        self._body = body
        self.content = _FakeContent(body)

    async def text(self):
        return self._body


class FakeSession:
    def __init__(self, body):
        self._body = body

    def get(self, *a, **kw):
        return _AsyncCM(FakeResp(self._body))


class _AsyncCM:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *a):
        pass


class _FailingSession:
    def get(self, *a, **kw):
        raise ConnectionError("simulated failure")


# ---------------------------------------------------------------------------
# stage_extract_article
# ---------------------------------------------------------------------------


class TestStageExtractArticle(TestCase):
    """article(stage_extract_article)."""

    def test_obituary_skip_conroe(self):
        story = MockStory(
            title="John Doe Obituary",
            link="https://example.com/obit/123",
            category="Conroe TX News",
        )

        async def _run():
            await stage_extract_article(story, FakeSession("<html></html>"))

        asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(story.context, "")

    def test_obituary_skip_houston(self):
        story = MockStory(
            title="Jane Doe Obituary",
            link="https://example.com/obit/456",
            category="Houston TX News",
        )

        async def _run():
            await stage_extract_article(story, FakeSession("<html></html>"))

        asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(story.context, "")

    def test_obituary_not_skipped_other_cat(self):
        story = MockStory(
            title="John Smith Obituary",
            link="https://example.com/obit/789",
            category="Politics",
        )
        long_text = "A" * 100
        html = f"<html><body>{long_text}</body></html>"

        async def _run():
            await stage_extract_article(story, FakeSession(html))

        asyncio.get_event_loop().run_until_complete(_run())
        self.assertNotEqual(story.context, "")

    def test_empty_url_returns_early(self):
        story = MockStory(link="")

        async def _run():
            await stage_extract_article(story, FakeSession("<html></html>"))

        asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(story.context, "")

    def test_hash_url_returns_early(self):
        story = MockStory(link="#fragment")

        async def _run():
            await stage_extract_article(story, FakeSession("<html></html>"))

        asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(story.context, "")

    def test_google_news_url_returns_early(self):
        story = MockStory(link="https://news.google.com/articles/abc123")

        async def _run():
            await stage_extract_article(story, FakeSession("<html></html>"))

        asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(story.context, "")

    def test_successful_extract_populates_context(self):
        long_text = "This is a sufficiently long piece of article body text that exceeds the fifty character minimum threshold easily."
        html = f"<html><body><p>{long_text}</p></body></html>"
        story = MockStory(
            title="Good Article",
            link="https://example.com/good",
            category="Tech",
        )

        async def _run():
            await stage_extract_article(story, FakeSession(html))

        asyncio.get_event_loop().run_until_complete(_run())
        self.assertNotEqual(story.context, "")
        self.assertGreaterEqual(len(story.context), 50)

    def test_short_text_no_context(self):
        html = "<html><body>Short</body></html>"
        story = MockStory(
            title="Brief",
            link="https://example.com/short",
            category="Tech",
        )

        async def _run():
            await stage_extract_article(story, FakeSession(html))

        asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(story.context, "")

    def test_fetch_exception_logged(self):
        story = MockStory(
            title="Failing",
            link="https://example.com/boom",
            category="Tech",
        )

        async def _run():
            await stage_extract_article(story, _FailingSession())

        asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(story.context, "")

    def test_empty_html_no_context(self):
        html = "<html><body></body></html>"
        story = MockStory(
            title="Empty",
            link="https://example.com/empty",
            category="Tech",
        )

        async def _run():
            await stage_extract_article(story, FakeSession(html))

        asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(story.context, "")

    def test_non_200_status_not_parsed(self):
        """Non-200 response should not be parsed — error pages should never enter context."""

        class ErrorResp:
            status = 500
            headers = {}
            content = _FakeContent(
                "<html><body>Error page content that should never be parsed</body></html>"
            )

            async def text(self):
                return "<html><body>Error page content that should never be parsed</body></html>"

        class ErrorSession:
            def get(self, *a, **kw):
                return _AsyncCM(ErrorResp())

        story = MockStory(
            title="Error Article",
            link="https://example.com/error",
            category="Tech",
        )

        async def _run():
            await stage_extract_article(story, ErrorSession())

        asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(story.context, "")


# ---------------------------------------------------------------------------
# build_context
# ---------------------------------------------------------------------------


class TestBuildContext(TestCase):
    """article(build_context)."""

    def test_context_used_when_long_enough(self):
        story = MockStory(
            title="T",
            link="https://x.com",
            category="Cat",
            context="This is a long enough context string that exceeds fifty characters easily.",
        )
        result = build_context(story)
        self.assertIn("long enough", result)

    def test_fallback_to_snippet_title(self):
        story = MockStory(
            title="My Title",
            link="https://x.com",
            category="MyCat",
            snippet="My snippet text here",
        )
        result = build_context(story)
        self.assertIn("My Title", result)
        self.assertIn("My snippet text here", result)
        self.assertIn("Category: MyCat", result)

    def test_fallback_no_snippet(self):
        story = MockStory(
            title="Alone",
            link="https://x.com",
            category="Solo",
        )
        result = build_context(story)
        self.assertIn("Alone", result)
        self.assertIn("Solo", result)

    def test_short_context_fallback(self):
        story = MockStory(
            title="Title",
            link="https://x.com",
            category="Cat",
            snippet="Snippet text here",
            context="Short",
        )
        result = build_context(story)
        self.assertIn("Snippet text here", result)

    def test_empty_parts_category_title(self):
        story = MockStory(
            title="",
            link="https://x.com",
            category="Blank",
            snippet="",
        )
        result = build_context(story)
        self.assertIn("Blank", result)

    def test_context_truncated(self):
        story = MockStory(
            title="T",
            link="https://x.com",
            category="Cat",
            context="A" * 2000,
        )
        result = build_context(story)
        self.assertEqual(len(result), LLM_CONTEXT_PREVIEW_CHARS)
