"""
Unit tests for src/daily_brief/sources/rss.py.
RSS feed URL construction, title normalization, date parsing, sorting, and async fetch.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest import TestCase, mock
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

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
    """Title normalization for deduplication."""

    def test_simple_title(self):
        self.assertEqual(normalize_title("Breaking News"), "breaking news")

    def test_site_suffix_stripped(self):
        result = normalize_title("Breaking News - CNN")
        self.assertEqual(result, "breaking news")

    def test_multiple_dashes(self):
        result = normalize_title("Breaking News - Section - CNN")
        self.assertEqual(result, "breaking news")

    def test_truncates_to_80_chars(self):
        long_title = "a" * 100
        result = normalize_title(long_title)
        self.assertEqual(len(result), 80)
        self.assertEqual(result, "a" * 80)

    def test_empty_string(self):
        result = normalize_title("")
        self.assertEqual(result, "")

    def test_whitespace_only(self):
        result = normalize_title("   ")
        self.assertEqual(result, "")

    def test_only_suffix(self):
        result = normalize_title(" - Reuters")
        self.assertEqual(result, "reuters")

    def test_no_suffix(self):
        result = normalize_title("Just a Title")
        self.assertEqual(result, "just a title")


# ---------------------------------------------------------------------------
# 2. parse_feed_date
# ---------------------------------------------------------------------------

class TestParseFeedDate(TestCase):
    """RSS entry date parsing."""

    def test_rfc2822_format(self):
        entry = {"published": "Thu, 30 Jul 2026 12:00:00 +0000"}
        result = parse_feed_date(entry)
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 7)
        self.assertEqual(result.day, 30)

    def test_iso8601_with_z(self):
        entry = {"updated": "2026-07-30T12:00:00Z"}
        result = parse_feed_date(entry)
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)

    def test_iso8601_no_tz(self):
        entry = {"published": "2026-07-30 14:30:00"}
        result = parse_feed_date(entry)
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.tzinfo)

    def test_date_only_format(self):
        entry = {"published": "2026-07-30"}
        result = parse_feed_date(entry)
        self.assertIsNotNone(result)
        self.assertEqual(result.day, 30)

    def test_published_prefers_over_updated(self):
        entry = {
            "published": "2026-07-30T10:00:00Z",
            "updated": "2026-07-30T18:00:00Z",
        }
        result = parse_feed_date(entry)
        self.assertIsNotNone(result)

    def test_falls_back_to_updated(self):
        entry = {"updated": "2026-06-15T08:00:00Z"}
        result = parse_feed_date(entry)
        self.assertIsNotNone(result)
        self.assertEqual(result.month, 6)

    def test_none_entry(self):
        self.assertIsNone(parse_feed_date({}))

    def test_garbage_date(self):
        entry = {"published": "not a date"}
        self.assertIsNone(parse_feed_date(entry))

    def test_empty_published(self):
        entry = {"published": "", "updated": "2026-01-01T00:00:00Z"}
        result = parse_feed_date(entry)
        self.assertIsNotNone(result)
        self.assertEqual(result.month, 1)

    def test_whitespace_date(self):
        entry = {"published": "   "}
        result = parse_feed_date(entry)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# 3. format_pub_date
# ---------------------------------------------------------------------------

class TestFormatPubDate(TestCase):
    """Publication date formatting."""

    def test_datetime_object(self):
        dt = datetime(2026, 7, 30, 12, 30, 45, tzinfo=timezone.utc)
        result = format_pub_date(dt)
        self.assertIsNotNone(result)
        self.assertIn("2026-07-30", result)
        self.assertIn("12:30:45", result)

    def test_datetime_with_zone(self):
        dt = datetime(2026, 7, 30, 12, 0, 0, tzinfo=ZoneInfo("America/Chicago"))
        result = format_pub_date(dt)
        self.assertIsNotNone(result)
        self.assertIn("2026-07-30", result)

    def test_naive_datetime(self):
        dt = datetime(2026, 1, 1, 8, 0, 0)
        result = format_pub_date(dt)
        self.assertIsNotNone(result)
        self.assertIn("2026-01-01", result)

    def test_iso_string_input(self):
        result = format_pub_date("2026-07-30T12:00:00Z")
        self.assertEqual(result, "2026-07-30T12:00:00Z")

    def test_none_input(self):
        self.assertIsNone(format_pub_date(None))

    def test_short_string_truncated(self):
        result = format_pub_date("a" * 60)
        self.assertEqual(len(result), 40)


# ---------------------------------------------------------------------------
# 4. _sort_entries
# ---------------------------------------------------------------------------

class TestSortEntries(TestCase):
    """RSS entry date sorting."""

    def _entry(self, title: str, pub_date: Optional[datetime]) -> tuple:
        return (title, "http://example.com", "", pub_date)

    def test_newer_first(self):
        newer = self._entry("Newer", datetime(2026, 7, 30, tzinfo=timezone.utc))
        older = self._entry("Older", datetime(2026, 7, 29, tzinfo=timezone.utc))
        result = _sort_entries(older, newer)
        self.assertGreater(result, 0)

    def test_older_first(self):
        newer = self._entry("Newer", datetime(2026, 7, 30, tzinfo=timezone.utc))
        older = self._entry("Older", datetime(2026, 7, 29, tzinfo=timezone.utc))
        result = _sort_entries(newer, older)
        self.assertLess(result, 0)

    def test_both_none(self):
        a = self._entry("A", None)
        b = self._entry("B", None)
        result = _sort_entries(a, b)
        self.assertEqual(result, 0.0)

    def test_a_none(self):
        a = self._entry("A", None)
        b = self._entry("B", datetime(2026, 7, 30, tzinfo=timezone.utc))
        result = _sort_entries(a, b)
        self.assertEqual(result, 1.0)

    def test_b_none(self):
        a = self._entry("A", datetime(2026, 7, 30, tzinfo=timezone.utc))
        b = self._entry("B", None)
        result = _sort_entries(a, b)
        self.assertEqual(result, -1.0)

    def test_equal_dates(self):
        dt = datetime(2026, 7, 30, tzinfo=timezone.utc)
        a = self._entry("A", dt)
        b = self._entry("B", dt)
        result = _sort_entries(a, b)
        self.assertEqual(result, 0.0)


# ---------------------------------------------------------------------------
# 5. build_rss_url
# ---------------------------------------------------------------------------

class TestBuildRssUrl(TestCase):
    """Google News RSS URL construction."""

    def test_basic_query(self):
        url = build_rss_url("technology news")
        self.assertIn("technology news", url)

    def test_contains_base(self):
        url = build_rss_url("test")
        self.assertIn("news.google.com", url)

    def test_contains_params(self):
        url = build_rss_url("test")
        self.assertIn("hl=", url)
        self.assertIn("gl=US", url)

    def test_single_word(self):
        url = build_rss_url("AI")
        self.assertIn("AI", url)


# ---------------------------------------------------------------------------
# 6. fetch_feed — happy path & parsing
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


async def _mock_fetch(rss_text: str, **kwargs):
    """Run fetch_feed against mocked aiohttp session."""
    class FakeResp:
        status = 200
        async def text(self):
            return rss_text
    class FakeSession:
        def get(self, *a, **kw):
            return _AsyncCM(FakeResp())
    class _AsyncCM:
        def __init__(self, resp):
            self._resp = resp
        async def __aenter__(self):
            return self._resp
        async def __aexit__(self, *a):
            pass
    return await fetch_feed(FakeSession(), "test-feed", "https://example.com/rss", 10)


class TestFetchFeedHappy(TestCase):
    """fetch_feed successful parsing."""

    def test_returns_name(self):
        result = asyncio.get_event_loop().run_until_complete(_mock_fetch(_SAMPLE_RSS))
        self.assertEqual(result[0], "test-feed")

    def test_parses_entries(self):
        result = asyncio.get_event_loop().run_until_complete(_mock_fetch(_SAMPLE_RSS))
        entries = result[1]
        self.assertEqual(len(entries), 3)

    def test_newest_first(self):
        result = asyncio.get_event_loop().run_until_complete(_mock_fetch(_SAMPLE_RSS))
        entries = result[1]
        self.assertEqual(entries[0][0], "New Story - CNN")
        self.assertEqual(entries[1][0], "Older Story")

    def test_html_stripped(self):
        result = asyncio.get_event_loop().run_until_complete(_mock_fetch(_SAMPLE_RSS))
        entries = result[1]
        snippet = entries[0][2]
        self.assertNotIn("<", snippet)
        self.assertIn("First story summary", snippet)

    def test_description_fallback(self):
        result = asyncio.get_event_loop().run_until_complete(_mock_fetch(_SAMPLE_RSS))
        entries = result[1]
        self.assertIn("Second story plain text", entries[1][2])

    def test_entry_has_link(self):
        result = asyncio.get_event_loop().run_until_complete(_mock_fetch(_SAMPLE_RSS))
        entries = result[1]
        self.assertEqual(entries[0][1], "https://example.com/1")

    def test_entry_has_date(self):
        result = asyncio.get_event_loop().run_until_complete(_mock_fetch(_SAMPLE_RSS))
        entries = result[1]
        self.assertIsNotNone(entries[0][3])
        self.assertEqual(entries[0][3].year, 2026)

    def test_no_date_entry(self):
        result = asyncio.get_event_loop().run_until_complete(_mock_fetch(_SAMPLE_RSS))
        entries = result[1]
        third = entries[2]
        self.assertEqual(third[0], "Third Story")
        self.assertIsNone(third[3])

    def test_max_stories_limited(self):
        async def _limited():
            class FakeResp:
                status = 200
                async def text(self):
                    items = ""
                    for i in range(20):
                        items += f"""<item>
                          <title>Story {i}</title>
                          <link>https://example.com/{i}</link>
                          <summary>Summary {i}</summary>
                          <pubDate>Thu, 30 Jul 2026 14:{i:02d}:00 +0000</pubDate>
                        </item>"""
                    return f"""<?xml version="1.0"?><rss version="2.0"><channel>{items}</channel></rss>"""
            class FakeSession:
                def get(self, *a, **kw):
                    return _AsyncCM(FakeResp())
            class _AsyncCM:
                def __init__(self, r):
                    self._r = r
                async def __aenter__(self):
                    return self._r
                async def __aexit__(self, *a):
                    pass
            return await fetch_feed(FakeSession(), "test", "https://x.com", 3)
        result = asyncio.get_event_loop().run_until_complete(_limited())
        self.assertEqual(len(result[1]), 3)

    def test_no_limit_returns_all(self):
        """B.6: when max_stories is None, fetch_feed returns all provider candidates."""
        async def _unlimited():
            class FakeResp:
                status = 200
                async def text(self):
                    items = ""
                    for i in range(12):
                        items += f"""<item>
                          <title>Story {i}</title>
                          <link>https://example.com/{i}</link>
                          <summary>Summary {i}</summary>
                          <pubDate>Thu, 30 Jul 2026 14:{i:02d}:00 +0000</pubDate>
                        </item>"""
                    return f"""<?xml version="1.0"?><rss version="2.0"><channel>{items}</channel></rss>"""
            class FakeSession:
                def get(self, *a, **kw):
                    return _AsyncCM(FakeResp())
            class _AsyncCM:
                def __init__(self, r):
                    self._r = r
                async def __aenter__(self):
                    return self._r
                async def __aexit__(self, *a):
                    pass
            return await fetch_feed(FakeSession(), "test", "https://x.com", None)
        result = asyncio.get_event_loop().run_until_complete(_unlimited())
        self.assertEqual(len(result[1]), 12)

    def test_empty_feed(self):
        result = asyncio.get_event_loop().run_until_complete(_mock_fetch("<rss version='2.0'><channel></channel></rss>"))
        self.assertEqual(result[0], "test-feed")
        self.assertEqual(len(result[1]), 0)

    def test_entry_tuple_shape(self):
        result = asyncio.get_event_loop().run_until_complete(_mock_fetch(_SAMPLE_RSS))
        entries = result[1]
        for entry in entries:
            self.assertEqual(len(entry), 4)
            title, link, snippet, pub_dt = entry
            self.assertIsInstance(title, str)
            self.assertIsInstance(link, str)
            self.assertIsInstance(snippet, str)

    def test_session_headers(self):
        url_called = []
        headers_called = {}
        class FakeResp:
            status = 200
            async def text(self):
                return _SAMPLE_RSS
        class FakeSession:
            def get(self, url, headers=None, timeout=None):
                url_called.append(url)
                headers_called.update(headers or {})
                return _AsyncCM2(FakeResp())
        class _AsyncCM2:
            def __init__(self, r):
                self._r = r
            async def __aenter__(self):
                return self._r
            async def __aexit__(self, *a):
                pass
        asyncio.get_event_loop().run_until_complete(
            fetch_feed(FakeSession(), "name", "https://example.com/rss", 5)
        )
        self.assertEqual(len(url_called), 1)
        self.assertEqual(url_called[0], "https://example.com/rss")
        self.assertIn("User-Agent", headers_called)

    def test_fetch_error_returns_empty(self):
        class FailingSession:
            def get(self, *a, **kw):
                raise ConnectionError("network failure")
        result = asyncio.get_event_loop().run_until_complete(
            fetch_feed(FailingSession(), "fail-feed", "https://bad.com", 5)
        )
        self.assertEqual(result[0], "fail-feed")
        self.assertEqual(len(result[1]), 0)

    def test_http_404_returns_empty_no_parse(self):
        """A.8: non-success status returns empty, never parses body."""
        parse_called = {}
        original_parse = feedparser.parse

        def capture_parse(*a, **kw):
            parse_called["called"] = True
            return original_parse(*a, **kw)

        class FakeResp:
            status = 404
            async def text(self):
                return _SAMPLE_RSS

        class FakeSession:
            def get(self, *a, **kw):
                return _AsyncCM(FakeResp())

        class _AsyncCM:
            def __init__(self, r):
                self._r = r
            async def __aenter__(self):
                return self._r
            async def __aexit__(self, *a):
                pass

        async def run():
            with mock.patch("daily_brief.sources.rss.feedparser", wraps=original_parse) as mp:
                original_parse2 = feedparser.parse
                def cap(*a, **kw):
                    parse_called["called"] = True
                    return original_parse2(*a, **kw)
                mp.parse = cap
                result = await fetch_feed(FakeSession(), "fail-feed", "https://example.com/rss", 5)
            return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(result[0], "fail-feed")
        self.assertEqual(len(result[1]), 0)
        self.assertFalse(parse_called.get("called", False))

    def test_http_503_returns_empty_no_parse(self):
        """A.8: server-error status returns empty, never parses body."""
        parse_called = {}

        class FakeResp:
            status = 503
            async def text(self):
                return _SAMPLE_RSS

        class FakeSession:
            def get(self, *a, **kw):
                return _AsyncCM(FakeResp())

        class _AsyncCM:
            def __init__(self, r):
                self._r = r
            async def __aenter__(self):
                return self._r
            async def __aexit__(self, *a):
                pass

        async def run():
            with mock.patch("daily_brief.sources.rss.feedparser.parse") as mp:
                result = await fetch_feed(FakeSession(), "fail-feed", "https://example.com/rss", 5)
                return result, mp.called
            return (result, mp.called)

        result, was_called = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(result[0], "fail-feed")
        self.assertEqual(len(result[1]), 0)
        self.assertFalse(was_called)

    def test_http_error_logs_status_and_name(self):
        """A.8: logs feed name and HTTP status in warning."""
        import logging

        class FakeResp:
            status = 502
            async def text(self):
                return "error"

        class FakeSession:
            def get(self, *a, **kw):
                return _AsyncCM(FakeResp())

        class _AsyncCM:
            def __init__(self, r):
                self._r = r
            async def __aenter__(self):
                return self._r
            async def __aexit__(self, *a):
                pass

        async def run():
            with self.assertLogs("daily_brief.sources.rss", level=logging.WARNING) as cm:
                result = await fetch_feed(FakeSession(), "fail-feed", "https://example.com/rss", 5)
            return result, list(cm.records)

        result, records = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(result[0], "fail-feed")
        self.assertEqual(len(result[1]), 0)
        self.assertTrue(len(records) >= 1)
        combined = " ".join(r.getMessage() for r in records)
        self.assertIn("fail-feed", combined)
        self.assertIn("502", combined)
