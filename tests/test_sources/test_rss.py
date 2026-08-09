"""
Unit tests for daily_brief/sources/rss.py.
RSS feed URL construction, title normalization, date parsing, sorting, and async fetch.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest import TestCase, mock
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import aiohttp
import feedparser

from daily_brief.sources.rss import (
    normalize_title,
    parse_feed_date,
    format_pub_date,
    _sort_entries,
    build_rss_url,
    fetch_feed,
)


# ---------------------------------------------------------------------------
# 1. normalize_title
# ---------------------------------------------------------------------------

class TestNormalizeTitle(TestCase):
    def test_suffix_stripped_lowercased_truncated(self):
        self.assertEqual(normalize_title("Breaking News"), "breaking news")
        self.assertEqual(normalize_title("Breaking News - CNN"), "breaking news")
        self.assertEqual(normalize_title("Breaking News - Section - CNN"), "breaking news")
        self.assertEqual(normalize_title("Just a Title"), "just a title")
        self.assertEqual(normalize_title("a" * 100), "a" * 80)
        self.assertEqual(normalize_title(""), "")
        self.assertEqual(normalize_title("   "), "")
        self.assertEqual(normalize_title(" - Reuters"), "reuters")


# ---------------------------------------------------------------------------
# 2. date parsing + formatting + sorting (utility contracts)
# ---------------------------------------------------------------------------

class TestDateParsingFormats(TestCase):
    def test_rfc2822_iso8601_dateonly(self):
        self.assertEqual(parse_feed_date({"published": "Thu, 30 Jul 2026 12:00:00 +0000"}).year, 2026)
        self.assertEqual(parse_feed_date({"updated": "2026-07-30T12:00:00Z"}).year, 2026)
        r = parse_feed_date({"published": "2026-07-30"})
        self.assertEqual(r.day, 30)

    def test_fallback_chain(self):
        """published wins; falls back to updated; garbage/empty/whitespace return None."""
        self.assertEqual(
            parse_feed_date({"published": "2026-07-30T10:00:00Z", "updated": "2026-07-30T18:00:00Z"}).hour, 10)
        self.assertEqual(parse_feed_date({"updated": "2026-06-15T08:00:00Z"}).month, 6)
        self.assertEqual(parse_feed_date({"published": "", "updated": "2026-01-01T00:00:00Z"}).month, 1)
        self.assertIsNone(parse_feed_date({}))
        self.assertIsNone(parse_feed_date({"published": "not a date"}))
        self.assertIsNone(parse_feed_date({"published": "   "}))

    def test_iso_no_tz_gets_tzinfo(self):
        self.assertIsNotNone(parse_feed_date({"published": "2026-07-30 14:30:00"}).tzinfo)


class TestSortAndFormat(TestCase):
    def _e(self, title, pub_date):
        return (title, "http://x.com", "", pub_date)

    def test_sort_newest_first_no_none_equal(self):
        dt = datetime(2026, 7, 30, tzinfo=timezone.utc)
        dt2 = datetime(2026, 7, 29, tzinfo=timezone.utc)
        self.assertGreater(_sort_entries(self._e("O", dt2), self._e("N", dt)), 0)
        self.assertLess(_sort_entries(self._e("N", dt), self._e("O", dt2)), 0)
        self.assertEqual(_sort_entries(self._e("A", dt), self._e("B", dt)), 0.0)

    def test_sort_none_handling(self):
        self.assertEqual(_sort_entries(self._e("A", None), self._e("B", None)), 0.0)
        dt = datetime(2026, 7, 30, tzinfo=timezone.utc)
        self.assertEqual(_sort_entries(self._e("A", None), self._e("B", dt)), 1.0)
        self.assertEqual(_sort_entries(self._e("A", dt), self._e("B", None)), -1.0)

    def test_format_pub_date(self):
        s = format_pub_date(datetime(2026, 7, 30, 12, 30, 45, tzinfo=timezone.utc))
        self.assertIn("2026-07-30", s)
        self.assertIn("12:30:45", s)
        self.assertIn("2026-07-30", format_pub_date(datetime(2026, 7, 30, tzinfo=ZoneInfo("America/Chicago"))))
        self.assertIn("2026-01-01", format_pub_date(datetime(2026, 1, 1, 8, 0, 0)))
        self.assertEqual(format_pub_date("2026-07-30T12:00:00Z"), "2026-07-30T12:00:00Z")
        self.assertIsNone(format_pub_date(None))


# ---------------------------------------------------------------------------
# 3. build_rss_url
# ---------------------------------------------------------------------------

class TestBuildRssUrl(TestCase):
    def test_query_base_params(self):
        url = build_rss_url("technology news")
        self.assertIn("technology news", url)
        self.assertIn("news.google.com", url)
        self.assertIn("hl=", url)
        self.assertIn("gl=US", url)
        self.assertIn("AI", build_rss_url("AI"))


# ---------------------------------------------------------------------------
# 4. fetch_feed — contracts
# ---------------------------------------------------------------------------

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>New Story - CNN</title>
      <link>https://example.com/1</link>
      <summary>&lt;p&gt;First story summary&lt;/p&gt;</summary>
      <pubDate>Thu, 30 Jul 2026 14:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Older Story</title>
      <link>https://example.com/2</link>
      <description>Second story plain text</description>
      <pubDate>Wed, 29 Jul 2026 10:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Third Story</title>
      <link>https://example.com/3</link>
      <summary>Third story</summary>
    </item>
  </channel>
</rss>
"""


def _fake_session(rss_text: str):
    class FakeResp:
        status = 200
        async def text(self):
            return rss_text
    class _ACM:
        async def __aenter__(self):
            return FakeResp()
        async def __aexit__(self, *a):
            pass
    class FakeSession:
        def get(self, *a, **kw):
            return _ACM()
    return FakeSession()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestFetchFeedContract(TestCase):
    """Core contracts: mapping, order, shape, limiting, errors."""

    def test_mapping_order_shape_and_html(self):
        """Feed name, 3 entries, newest first, 4-tuple shape, HTML stripped, description fallback, dates."""
        async def run():
            return await fetch_feed(_fake_session(_SAMPLE_RSS), "test-feed", "https://example.com/rss", 10)
        name, entries = _run(run())
        self.assertEqual(name, "test-feed")
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0][0], "New Story - CNN")
        self.assertEqual(entries[1][0], "Older Story")
        self.assertEqual(entries[2][0], "Third Story")
        for title, link, snippet, pub_dt in entries:
            self.assertIsInstance(title, str)
            self.assertIsInstance(link, str)
            self.assertIsInstance(snippet, str)
        self.assertNotIn("<", entries[0][2])
        self.assertIn("First story summary", entries[0][2])
        self.assertIn("Second story plain text", entries[1][2])
        self.assertIsNotNone(entries[0][3])
        self.assertEqual(entries[0][3].year, 2026)
        self.assertIsNone(entries[2][3])

    def test_empty_feed(self):
        async def run():
            return await fetch_feed(_fake_session("<rss version='2.0'><channel></channel></rss>"), "test-feed", "https://example.com/rss", 10)
        name, entries = _run(run())
        self.assertEqual(name, "test-feed")
        self.assertEqual(len(entries), 0)

    def test_limit_capped_and_unlimited(self):
        async def _gen(n, cap):
            items = ""
            for i in range(n):
                items += f"""<item><title>S{i}</title><link>https://x.com/{i}</link><summary>S{i}</summary><pubDate>Thu, 30 Jul 2026 14:{i:02d}:00 +0000</pubDate></item>"""
            xml = f"""<?xml version="1.0"?><rss version="2.0"><channel>{items}</channel></rss>"""
            return await fetch_feed(_fake_session(xml), "x", "https://x.com", cap)
        _, e1 = _run(_gen(12, None))
        self.assertEqual(len(e1), 12)
        _, e2 = _run(_gen(20, 3))
        self.assertEqual(len(e2), 3)

    def test_session_passes_url_and_headers(self):
        url_called = []
        headers_called = {}
        class FakeResp:
            status = 200
            async def text(self):
                return _SAMPLE_RSS
        class _ACM:
            async def __aenter__(self):
                return FakeResp()
            async def __aexit__(self, *a):
                pass
        class FakeSession:
            def get(self, url, headers=None, timeout=None):
                url_called.append(url)
                headers_called.update(headers or {})
                return _ACM()
        _run(fetch_feed(FakeSession(), "name", "https://example.com/rss", 5))
        self.assertEqual(url_called[0], "https://example.com/rss")
        self.assertIn("User-Agent", headers_called)

    def test_fetch_exception_return_empty(self):
        class FailingSession:
            def get(self, *a, **kw):
                raise ConnectionError("network failure")
        name, entries = _run(fetch_feed(FailingSession(), "fail-feed", "https://bad.com", 5))
        self.assertEqual(name, "fail-feed")
        self.assertEqual(len(entries), 0)

    def test_http_status_matrix_no_parse(self):
        """Non-2xx status codes return empty, never parse body."""
        for status_code in [404, 403, 500, 502, 503]:
            with self.subTest(status=status_code):
                class FakeResp:
                    status = status_code
                    async def text(self):
                        return _SAMPLE_RSS
                class _ACM:
                    async def __aenter__(self):
                        return FakeResp()
                    async def __aexit__(self, *a):
                        pass
                class FakeSession:
                    def get(self, *a, **kw):
                        return _ACM()
                async def run():
                    with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None), \
                         mock.patch("daily_brief.sources.rss.feedparser.parse") as mp:
                        result = await fetch_feed(FakeSession(), "fail-feed", "https://example.com/rss", 5)
                        return result, mp.called
                result, was_called = _run(run())
                self.assertEqual(result[0], "fail-feed")
                self.assertEqual(len(result[1]), 0)
                self.assertFalse(was_called, f"feedparser.parse called for status {status_code}")

    def test_http_error_logs_status_and_name(self):
        import logging
        class FakeResp:
            status = 502
            async def text(self):
                return "error"
        class _ACM:
            async def __aenter__(self):
                return FakeResp()
            async def __aexit__(self, *a):
                pass
        class FakeSession:
            def get(self, *a, **kw):
                return _ACM()
        async def run():
            with mock.patch("asyncio.sleep", new_callable=AsyncMock, return_value=None), \
                 self.assertLogs("daily_brief", level=logging.WARNING) as cm:
                result = await fetch_feed(FakeSession(), "fail-feed", "https://example.com/rss", 5)
            return result, list(cm.records)
        result, records = _run(run())
        self.assertEqual(len(result[1]), 0)
        combined = " ".join(r.getMessage() for r in records)
        self.assertIn("fail-feed", combined)
        self.assertIn("502", combined)
