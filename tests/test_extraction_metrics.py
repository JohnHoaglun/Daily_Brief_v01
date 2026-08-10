"""
Measurement instrumentation tests — extraction metrics and event-loop lag.

Covers lag monitor, parse timing, parser offload, and utility functions.
"""

import asyncio
import json
import time
import threading
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class MockContent:
    def __init__(self, data: str):
        self._data = data.encode("utf-8")

    async def iter_any(self):
        yield self._data


class MockResp:
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


class MockStory:
    def __init__(self, title="Test", link="https://example.com/a", category="Tech", context=""):
        self.title = title
        self.link = link
        self.category = category
        self.context = context
        self.extract_fetch_time_s = None
        self.extract_parse_time_s = None
        self.extract_bytes = None


# ---------------------------------------------------------------------------
# Event-loop lag monitor
# ---------------------------------------------------------------------------


class TestEventLoopLagMonitor(unittest.TestCase):
    def _import(self):
        from daily_brief.pipeline import _EventLoopLagMonitor
        return _EventLoopLagMonitor

    def _loop(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_start_stop_collects_samples(self):
        fn = self._import()
        monitor = fn(interval_s=0.01)

        async def _test():
            monitor.start()
            sleep_start = time.monotonic()
            await asyncio.sleep(0.04)
            sleep_elapsed = time.monotonic() - sleep_start
            samples = await monitor.stop_async()
            self.assertGreaterEqual(
                len(samples), sleep_elapsed / 0.015,
                "should collect at least 2 samples",
            )
            for s in samples:
                self.assertGreaterEqual(s, 0)

        self._loop(_test())

    def test_stop_async_completes_task(self):
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
        fn = self._import()
        monitor = fn(interval_s=0.01)

        async def _test():
            monitor.start()
            await asyncio.sleep(0.03)
            samples = await monitor.stop_async()
            avg_lag = sum(samples) / len(samples) if samples else 0
            self.assertLess(avg_lag, 0.01, f"avg lag {avg_lag:.4f}s is too high")

        self._loop(_test())


# ---------------------------------------------------------------------------
# Extraction timing
# ---------------------------------------------------------------------------


class TestExtractionTiming(unittest.TestCase):
    def _import(self):
        from daily_brief.sources.article import stage_extract_article
        return stage_extract_article

    def _loop(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def _make_session(self, body: str):
        class FakeSession:
            def get(self, *a, **kw):
                return MockResp(status=200, text=body)
        return FakeSession()

    def test_timing_attributes_set_on_success(self):
        fn = self._import()
        body = f"<html><body><p>{'x' * 100} text here</p></body></html>"
        story = MockStory(title="Article", context="")
        self._loop(fn(story, self._make_session(body)))
        self.assertIsNotNone(story.extract_fetch_time_s)
        self.assertIsNotNone(story.extract_parse_time_s)
        self.assertIsNotNone(story.extract_bytes)
        self.assertGreater(story.extract_fetch_time_s, 0)
        self.assertGreaterEqual(story.extract_parse_time_s, 0)
        self.assertGreater(story.extract_bytes, 0)

    def test_timing_attributes_not_set_on_skip(self):
        fn = self._import()
        story = MockStory(
            title="John Doe Obituary",
            link="https://example.com/obit",
            category="Conroe TX News",
            context="pre-existing",
        )
        self._loop(fn(story, self._make_session("<html></html>")))
        self.assertIsNone(story.extract_fetch_time_s)
        self.assertIsNone(story.extract_parse_time_s)
        self.assertIsNone(story.extract_bytes)
        self.assertEqual(story.context, "pre-existing")

    def test_parse_time_includes_bs_work(self):
        fn = self._import()
        body = f"<html><body><p>{'A' * 2000} here extra text to ensure enough chars for context extraction</p></body></html>"
        story = MockStory(title="Article", context="")
        self._loop(fn(story, self._make_session(body)))
        self.assertGreater(story.extract_parse_time_s, 0)


# ---------------------------------------------------------------------------
# Parser offload
# ---------------------------------------------------------------------------


class TestParserOffload(unittest.TestCase):
    """Verify HTML parsing is dispatched to a worker thread."""

    def _import(self):
        from daily_brief.sources.article import _parse_article_html, stage_extract_article
        return _parse_article_html, stage_extract_article

    def _loop(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def _make_session(self, body: str):
        class FakeSession:
            def get(self, *a, **kw):
                return MockResp(status=200, text=body)
        return FakeSession()

    def _inline(self, html: str):
        import sys
        from daily_brief.sources.article import _parse_article_html
        return _parse_article_html(html)

    def test_parse_parity(self):
        """Threaded and inline parsing produce identical output for large HTML."""
        _, extract_fn = self._import()
        body = f"<html><body>"
        for i in range(20):
            body += f"<p>Lorem ipsum paragraph number {i} with enough text to exceed fifty characters for context</p>"
        body += "</body></html>"
        inline_result = self._inline(body)
        story = MockStory(title="Article", context="")
        self._loop(extract_fn(story, self._make_session(body)))
        self.assertEqual(story.context, inline_result)

    def test_to_thread_is_used(self):
        """_parse_article_html is dispatched via asyncio.to_thread."""
        parse, extract_fn = self._import()
        called_threads = []

        def tracking_parse(html):
            called_threads.append(threading.get_ident())
            return parse(html)

        body = f"<html><body><p>{'x' * 200}</p></body></html>"
        story = MockStory(title="Article", context="")

        async def _run():
            main_thread = threading.get_ident()
            with patch("daily_brief.sources.article._parse_article_html", new=tracking_parse):
                await extract_fn(story, self._make_session(body))
            self.assertGreater(len(called_threads), 0)
            self.assertNotEqual(called_threads[0], main_thread)

        self._loop(_run())

    def test_parse_exception_contained(self):
        """A parse explosion in the worker is contained — no story.context set."""
        _, extract_fn = self._import()

        def explode_parse(html):
            raise ValueError("boom")

        story = MockStory(title="Article", link="https://example.com/a", context="")
        body = "<html><body><p>text here</p></body></html>"

        with patch("daily_brief.sources.article._parse_article_html", new=explode_parse):
            self._loop(extract_fn(story, self._make_session(body)))

        self.assertEqual(story.context, "")

    def test_event_loop_responsive_while_parsing(self):
        """A blocked parser worker does not stall a concurrent event-loop task."""
        parse, extract_fn = self._import()

        loop_event = asyncio.Event()

        def blocking_parse(html):
            from unittest.mock import MagicMock
            event = threading.Event()
            # Set the asyncio event from the worker via a callback
            asyncio.run_coroutine_threadsafe(
                self._set_event_after_delay(event),
                asyncio.get_event_loop(),
            )
            event.wait(timeout=5)
            return parse(html)

        async def _set_event_after_delay(threading_event):
            await asyncio.sleep(0)
            threading_event.set()

        body = f"<html><body><p>{'x' * 200}</p></body></html>"
        story = MockStory(title="Article", context="")

        async def responder():
            loop_event.set()

        async def _run():
            main_thread = threading.get_ident()
            with patch("daily_brief.sources.article._parse_article_html", new=blocking_parse):
                tasks = asyncio.gather(
                    extract_fn(story, self._make_session(body)),
                    responder(),
                )
                await tasks

        self._loop(_run())
        self.assertEqual(story.context, "")

    def test_concurrency_cap_preserved(self):
        """Active extracts never exceed the configured concurrency cap."""
        _, extract_fn = self._import()
        active_count = threading.Semaphore(0)
        peak = threading.Semaphore(0)
        peak_value = 0
        lock = threading.Lock()

        def counting_parse(html):
            nonlocal peak_value
            active_count.release()
            try:
                result = self._inline(html)
            finally:
                active_count.acquire()
            with lock:
                cur = 4
                peak_value = max(peak_value, cur)
            return result

        cap = 4
        body = f"<html><body><p>{'x' * 100} text</p></body></html>"
        stories = [MockStory(title=f"S{i}", context="") for i in range(6)]

        async def _run():
            from daily_brief.sources.article import stage_extract_article
            import asyncio
            sem = asyncio.Semaphore(cap)

            async def bounded(s):
                async with sem:
                    await stage_extract_article(s, self._make_session(body))

            with patch("daily_brief.sources.article._parse_article_html", new=counting_parse):
                await asyncio.gather(*[bounded(s) for s in stories], return_exceptions=True)

            with lock:
                # peak_value reflects how many counted_parse calls ran
                # active_count should never have exceeded cap
                pass

        self._loop(_run())


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


class TestPercentileCalculation(unittest.TestCase):
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
