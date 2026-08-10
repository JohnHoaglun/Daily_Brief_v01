"""Measurement instrumentation tests — extraction metrics and event-loop lag."""

import asyncio
import time
import unittest
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, patch


class MockStory:
    """Minimal story with extraction timing attributes."""

    def __init__(self, title="Test", link="https://example.com/a", category="Tech", context=""):
        self.title = title
        self.link = link
        self.category = category
        self.context = context
        self.extract_fetch_time_s = None
        self.extract_parse_time_s = None
        self.extract_bytes = None


class MockContent:
    """Mock aiohttp.response.content supporting iter_any()."""

    def __init__(self, data: str):
        self._data = data.encode("utf-8")

    async def iter_any(self):
        yield self._data


class MockResp:
    """Mock aiohttp response context manager."""

    def __init__(self, status=200, text="ok", content_length=None):
        self.status = status
        self._text = text
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
        self.content = MockContent(text)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def text(self):
        return self._text


class TestEventLoopLagMonitor(unittest.TestCase):
    """_EventLoopLagMonitor — lag collection and lifecycle."""

    def _import(self):
        from daily_brief.pipeline import _EventLoopLagMonitor
        return _EventLoopLagMonitor

    def _loop(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_start_stop_collects_samples(self):
        """Normal ticks produce positive lag samples."""
        fn = self._import()
        monitor = fn(interval_s=0.01)

        async def _test():
            monitor.start()
            sleep_start = time.monotonic()
            await asyncio.sleep(0.04)
            sleep_elapsed = time.monotonic() - sleep_start
            samples = monitor.stop()
            self.assertGreaterEqual(len(samples), sleep_elapsed / 0.015, "should collect at least 2 samples")
            for s in samples:
                self.assertGreaterEqual(s, 0, "lag should not be negative")

        self._loop(_test())

    def test_stop_async_completes_task(self):
        """stop_async signals stop and awaits background task completion."""
        fn = self._import()
        monitor = fn(interval_s=0.01)

        async def _test():
            monitor.start()
            await asyncio.sleep(0.02)
            samples = await monitor.stop_async()
            self.assertTrue(monitor._task.done())
            return len(samples) > 0

        collected = self._loop(_test())
        self.assertTrue(collected)

    def test_no_lag_when_unblocked(self):
        """When the loop is unblocked, lag should be near zero."""
        fn = self._import()
        monitor = fn(interval_s=0.01)

        async def _test():
            monitor.start()
            await asyncio.sleep(0.03)
            samples = monitor.stop()
            avg_lag = sum(samples) / len(samples) if samples else 0
            self.assertLess(avg_lag, 0.01, f"avg lag {avg_lag:.4f}s is too high")

        self._loop(_test())


class TestExtractionTiming(unittest.TestCase):
    """stage_extract_article — per-article timing attributes."""

    def _import(self):
        from daily_brief.sources.article import stage_extract_article
        return stage_extract_article

    def _loop(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_timing_attributes_set_on_success(self):
        """Fetch and parse times are populated on successful extraction."""
        fn = self._import()
        body = "x" * 100
        resp = MockResp(status=200, text=f"<html><body><p>{body} text here</p></body></html>")

        class FakeSession:
            def get(self, *a, **kw):
                return resp

        story = MockStory(title="Article", link="https://example.com/a", context="")
        self._loop(fn(story, FakeSession()))

        self.assertIsNotNone(story.extract_fetch_time_s)
        self.assertIsNotNone(story.extract_parse_time_s)
        self.assertIsNotNone(story.extract_bytes)
        self.assertGreater(story.extract_fetch_time_s, 0)
        self.assertGreaterEqual(story.extract_parse_time_s, 0)
        self.assertGreater(story.extract_bytes, 0)

    def test_timing_attributes_not_set_on_skip(self):
        """Skipped stories (e.g., obituary in local category) have no timing attributes set."""
        fn = self._import()

        class FakeSession:
            def get(self, *a, **kw):
                return MockResp(status=200, text="<html><body></body></html>")

        story = MockStory(
            title="John Doe Obituary",
            link="https://example.com/obit",
            category="Conroe TX News",
            context="pre-existing"
        )
        self._loop(fn(story, FakeSession()))

        self.assertIsNone(story.extract_fetch_time_s)
        self.assertIsNone(story.extract_parse_time_s)
        self.assertIsNone(story.extract_bytes)
        self.assertEqual(story.context, "pre-existing")

    def test_parse_time_includes_bs_work(self):
        """Parse time should reflect BeautifulSoup processing time."""
        fn = self._import()

        class FakeSession:
            def get(self, *a, **kw):
                body = "A" * 2000
                return MockResp(status=200, text=f"<html><body><p>{body} here extra text to ensure enough chars for context extraction</p></body></html>")

        story = MockStory(title="Article", link="https://x.com", context="")
        self._loop(fn(story, FakeSession()))

        self.assertGreater(story.extract_parse_time_s, 0, "parse time should be measurable")


class TestPercentileCalculation(unittest.TestCase):
    """_percentile — statistical calculation for lag samples."""

    def _import(self):
        from daily_brief.pipeline import _percentile
        return _percentile

    def test_p50_single_value(self):
        fn = self._import()
        self.assertAlmostEqual(fn([0.01], 50), 0.01)

    def test_p50_two_values(self):
        fn = self._import()
        self.assertAlmostEqual(fn([0.01, 0.03], 50), 0.02)

    def test_p100(self):
        fn = self._import()
        self.assertAlmostEqual(fn([0.01, 0.02, 0.03], 100), 0.03)

    def test_p0(self):
        fn = self._import()
        self.assertAlmostEqual(fn([0.01, 0.02, 0.03], 0), 0.01)

    def test_empty_list(self):
        fn = self._import()
        self.assertEqual(fn([], 50), 0.0)


class TestCountExtracted(unittest.TestCase):
    """_count_extracted — counts stories with populated context."""

    def _import(self):
        from daily_brief.pipeline import _count_extracted
        return _count_extracted

    def test_all_populated(self):
        fn = self._import()
        stories = [MockStory(context="text") for _ in range(5)]
        self.assertEqual(fn(stories), 5)

    def test_mixed(self):
        fn = self._import()
        stories = [
            MockStory(context="text"),
            MockStory(context=""),
            MockStory(context="more text"),
            MockStory(context=None),
        ]
        self.assertEqual(fn(stories), 2)

    def test_empty_list(self):
        fn = self._import()
        self.assertEqual(fn([]), 0)


if __name__ == "__main__":
    unittest.main()
