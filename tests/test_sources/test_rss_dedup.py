"""
Unit tests for src/daily_brief/pipelines/rss_dedup.py.
Dedup, age-filtering, widening, and fetch_and_dedup orchestration.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Tuple
from unittest import TestCase, mock
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from daily_brief.pipelines.rss_dedup import (
    dedup_entries,
    fetch_and_dedup,
    widen_category,
)
from daily_brief.sources.rss import normalize_title


TZ = ZoneInfo("America/Chicago")
NOW = datetime(2026, 7, 30, 14, 0, 0, tzinfo=TZ)


def _entry(title: str, link: str = "https://example.com", snippet: str = "", pub_dt: Optional[datetime] = None) -> Tuple[str, str, str, Optional[datetime]]:
    return (title, link, snippet, pub_dt)


# ---------------------------------------------------------------------------
# dedup_entries
# ---------------------------------------------------------------------------


class TestDedupEntries(TestCase):
    """rss_dedup(dedup_entries)."""

    def test_age_filter_removes_old(self):
        old_dt = NOW - timedelta(hours=48)
        entries = [_entry("Old Story", pub_dt=old_dt)]
        seen: dict = {}
        deduped: list = []
        added, af, df = dedup_entries(entries, NOW, "cat", 24.0, seen, deduped)
        self.assertEqual(added, 0)
        self.assertEqual(af, 1)

    def test_dup_filter_removes_dups(self):
        fresh = NOW - timedelta(hours=1)
        entries = [
            _entry("Same Title", pub_dt=fresh),
            _entry("Same Title", pub_dt=fresh),
        ]
        seen: dict = {}
        deduped: list = []
        added, af, df = dedup_entries(entries, NOW, "cat", 24.0, seen, deduped)
        self.assertEqual(added, 1)
        self.assertEqual(df, 1)

    def test_obituary_title_skipped(self):
        fresh = NOW - timedelta(hours=1)
        entries = [_entry("John Obituary", pub_dt=fresh)]
        seen: dict = {}
        deduped: list = []
        added, af, df = dedup_entries(entries, NOW, "cat", 24.0, seen, deduped)
        self.assertEqual(added, 0)

    def test_real_estate_title_skipped(self):
        fresh = NOW - timedelta(hours=1)
        entries = [_entry("House for sale $200k", pub_dt=fresh)]
        seen: dict = {}
        deduped: list = []
        added, af, df = dedup_entries(entries, NOW, "cat", 24.0, seen, deduped)
        self.assertEqual(added, 0)

    def test_no_pub_date_included(self):
        entries = [_entry("No Date Story")]
        seen: dict = {}
        deduped: list = []
        added, af, df = dedup_entries(entries, NOW, "cat", 24.0, seen, deduped)
        self.assertEqual(added, 1)
        self.assertEqual(af, 0)

    def test_empty_entries_returns_empty(self):
        seen: dict = {}
        deduped: list = []
        added, af, df = dedup_entries([], NOW, "cat", 24.0, seen, deduped)
        self.assertEqual(added, 0)
        self.assertEqual(af, 0)
        self.assertEqual(df, 0)

    def test_all_unique_kept(self):
        fresh = NOW - timedelta(hours=1)
        entries = [
            _entry("Story A", pub_dt=fresh),
            _entry("Story B", pub_dt=fresh),
            _entry("Story C", pub_dt=fresh),
        ]
        seen: dict = {}
        deduped: list = []
        added, af, df = dedup_entries(entries, NOW, "cat", 24.0, seen, deduped)
        self.assertEqual(added, 3)
        self.assertEqual(af, 0)
        self.assertEqual(df, 0)


# ---------------------------------------------------------------------------
# fetch_and_dedup
# ---------------------------------------------------------------------------

class FakeResp:
    status = 200

    def __init__(self, body):
        self._body = body

    async def text(self):
        return self._body


class _AsyncCM:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *a):
        pass


def _rss_xml(items: List[dict]) -> str:
    body = ""
    for i, item in enumerate(items):
        title = item.get("title", f"Story {i}")
        link = item.get("link", f"https://example.com/{i}")
        summary = item.get("summary", f"Summary {i}")
        pub = item.get("pubDate", "")
        body += f"""<item>
          <title>{title}</title>
          <link>{link}</link>
          <summary>{summary}</summary>
          {'<pubDate>' + pub + '</pubDate>' if pub else ''}
        </item>"""
    return f"""<?xml version="1.0"?>
    <rss version="2.0">
      <channel>{body}</channel>
    </rss>"""


class TestFetchAndDedup(TestCase):
    """rss_dedup(fetch_and_dedup)."""

    def _make_session(self, body_map: dict):
        class FakeSession:
            def get(self, url, **kw):
                for k, v in body_map.items():
                    if k in url:
                        return _AsyncCM(FakeResp(v))
                return _AsyncCM(FakeResp(_rss_xml([])))
        return FakeSession()

    def test_all_feeds_fetched(self):
        fresh = "Thu, 30 Jul 2026 10:00:00 +0000"

        xml_a = _rss_xml([
            {"title": "Story A1", "pubDate": fresh},
        ])
        xml_b = _rss_xml([
            {"title": "Story B1", "pubDate": fresh},
        ])

        cats = [
            ("CatA", "query a", 10),
            ("CatB", "query b", 10),
        ]
        session = self._make_session({"query a": xml_a, "query b": xml_b})
        logs = []

        async def _run():
            return await fetch_and_dedup(session, cats, logs.append)

        deduped, stats = asyncio.get_event_loop().run_until_complete(_run())
        self.assertGreater(len(deduped), 0)
        titles = [d[0] for d in deduped]
        self.assertIn("Story A1", titles)
        self.assertIn("Story B1", titles)

    def test_feed_exception_dont_crash(self):
        fresh = "Thu, 30 Jul 2026 10:00:00 +0000"
        xml_ok = _rss_xml([{"title": "OK Story", "pubDate": fresh}])
        xml_bad = "<?xml error"  # this won't cause an exception from feedparser, but let's fake it

        class FailingSession:
            call_count = 0

            def get(self, url, **kw):
                FailingSession.call_count += 1
                if "query fail" in url:
                    raise ConnectionError("network fail")
                return _AsyncCM(FakeResp(xml_ok))

        cats = [
            ("CatFail", "query fail", 10),
            ("CatOK", "query ok", 10),
        ]
        session = FailingSession()
        logs = []

        async def _run():
            return await fetch_and_dedup(session, cats, logs.append)

        deduped, stats = asyncio.get_event_loop().run_until_complete(_run())
        titles = [d[0] for d in deduped]
        self.assertIn("OK Story", titles)

    def test_cross_cat_dedup(self):
        fresh = "Thu, 30 Jul 2026 10:00:00 +0000"
        # Same story in two categories
        xml_dup = _rss_xml([{"title": "Dup Story - Source", "pubDate": fresh}])

        cats = [
            ("CatA", "query a", 10),
            ("CatB", "query b", 10),
        ]
        session = self._make_session({"query a": xml_dup, "query b": xml_dup})
        logs = []

        async def _run():
            return await fetch_and_dedup(session, cats, logs.append)

        deduped, stats = asyncio.get_event_loop().run_until_complete(_run())
        dup_titles = [d[0] for d in deduped if d[0] == "Dup Story - Source"]
        self.assertEqual(len(dup_titles), 1)
        self.assertGreater(stats["cross_dup_filtered"], 0)

    def test_stats_returned(self):
        fresh = "Thu, 30 Jul 2026 10:00:00 +0000"
        xml_a = _rss_xml([{"title": "Story", "pubDate": fresh}])

        cats = [("CatA", "query a", 10)]
        session = self._make_session({"query a": xml_a})
        logs = []

        async def _run():
            return await fetch_and_dedup(session, cats, logs.append)

        deduped, stats = asyncio.get_event_loop().run_until_complete(_run())
        self.assertIn("total_before", stats)
        self.assertIn("total_after", stats)
        self.assertIn("age_filtered", stats)
        self.assertIn("dup_filtered", stats)
        self.assertIn("cross_dup_filtered", stats)
        self.assertEqual(stats["total_after"], len(deduped))

    def test_empty_categories_skipped(self):
        logs = []

        async def _run():
            session = self._make_session({})
            return await fetch_and_dedup(session, [], logs.append)

        deduped, stats = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(len(deduped), 0)
        self.assertEqual(stats["total_before"], 0)

    def test_zoneinfo_uses_configured_timezone(self):
        """A.1 Bug-1: verify feed_and_dedup() resolves the configured timezone via ZoneInfo."""
        cats = []  # empty categories, no network
        session = self._make_session({})
        logs = []

        async def _run():
            return await fetch_and_dedup(session, cats, logs.append)

        with mock.patch(
            "daily_brief.pipelines.rss_dedup.ZoneInfo",
            wraps=ZoneInfo,
        ) as zi_mock:
            asyncio.get_event_loop().run_until_complete(_run())
            zi_mock.assert_any_call("America/Chicago")


# ---------------------------------------------------------------------------
# widen_category
# ---------------------------------------------------------------------------


class TestWidenCategory(TestCase):
    """rss_dedup(widen_category)."""

    def _make_widen_session(self, entries_per_call: List[list]):
        """Session that returns different entries each call."""
        class FakeSession:
            call_idx = 0

            def get(self, url, **kw):
                idx = FakeSession.call_idx
                FakeSession.call_idx += 1
                if idx < len(entries_per_call):
                    body = _rss_xml(entries_per_call[idx])
                else:
                    body = _rss_xml([])
                return _AsyncCM(FakeResp(body))

        return FakeSession()

    def test_widening_expands_age(self):
        """Category with < 3 stories triggers widening loop."""
        fresh = "Thu, 30 Jul 2026 10:00:00 +0000"
        widen_entries = [
            [{"title": "Widen1", "pubDate": fresh}],
            [{"title": "Widen2", "pubDate": fresh}],
            [{"title": "Widen3", "pubDate": fresh}],
        ]

        cats = [("CatW", "query w", 10)]
        session = self._make_widen_session(widen_entries)
        seen: dict = {}
        deduped: list = []
        logs = []

        async def _run():
            return await widen_category(
                session, "CatW", 0, seen, deduped, NOW, cats, logs.append
            )

        session.call_idx = 0
        final, added, waf, wdf = asyncio.get_event_loop().run_until_complete(_run())
        self.assertGreater(added, 0)

    def test_widening_stops_at_3(self):
        """Widening stops when >= 3 stories collected."""
        fresh = "Thu, 30 Jul 2026 10:00:00 +0000"
        widen_entries = [
            [{"title": "W1", "pubDate": fresh}, {"title": "W2", "pubDate": fresh}],
            [{"title": "W3", "pubDate": fresh}],
            [{"title": "W4", "pubDate": fresh}],
        ]

        cats = [("CatW", "query w", 10)]
        session = self._make_widen_session(widen_entries)
        seen: dict = {}
        deduped: list = []
        logs = []

        async def _run():
            return await widen_category(
                session, "CatW", 0, seen, deduped, NOW, cats, logs.append
            )

        session.call_idx = 0
        final, added, waf, wdf = asyncio.get_event_loop().run_until_complete(_run())
        self.assertGreaterEqual(final, 3)

    def test_widening_exhausts_to_7d(self):
        """When feed returns no more entries, widening stops after all widening rounds."""
        cats = [("CatE", "query e", 10)]
        session = self._make_widen_session([[], [], [], [], []])
        seen: dict = {}
        deduped: list = []
        logs = []

        async def _run():
            return await widen_category(
                session, "CatE", 0, seen, deduped, NOW, cats, logs.append
            )

        session.call_idx = 0
        final, added, waf, wdf = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(final, 0)
        self.assertEqual(added, 0)

    def test_no_match_returns_early(self):
        """Category not in categories list returns early unchanged."""
        cats = [("Other", "query o", 10)]
        session = self._make_widen_session([])
        seen: dict = {}
        deduped: list = []
        logs = []

        async def _run():
            return await widen_category(
                session, "NoSuchCat", 5, seen, deduped, NOW, cats, logs.append
            )

        final, added, waf, wdf = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(final, 5)
        self.assertEqual(added, 0)

    def test_empty_feed_no_add(self):
        """Widened fetch returns empty feed — no stories added."""
        cats = [("CatE", "query e", 10)]
        session = self._make_widen_session([[]])
        seen: dict = {}
        deduped: list = []
        logs = []

        async def _run():
            return await widen_category(
                session, "CatE", 1, seen, deduped, NOW, cats, logs.append
            )

        session.call_idx = 0
        final, added, waf, wdf = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(added, 0)
        self.assertEqual(final, 1)
