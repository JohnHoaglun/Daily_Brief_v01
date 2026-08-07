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


def _make_boundary_session(pub_date: str):
    """Session that returns a boundary story at the given pubDate."""
    class FakeSession:
        def get(self, url, **kw):
            return _AsyncCM(FakeResp(_rss_xml([
                {"title": "Boundary Story", "pubDate": pub_date},
            ])))
    return FakeSession()


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
            with mock.patch("daily_brief.pipelines.rss_dedup.datetime", wraps=datetime) as dt_mock:
                dt_mock.now.return_value = NOW
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
            with mock.patch("daily_brief.pipelines.rss_dedup.datetime", wraps=datetime) as dt_mock:
                dt_mock.now.return_value = NOW
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
            with mock.patch("daily_brief.pipelines.rss_dedup.datetime", wraps=datetime) as dt_mock:
                dt_mock.now.return_value = NOW
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
            with mock.patch("daily_brief.pipelines.rss_dedup.datetime", wraps=datetime) as dt_mock:
                dt_mock.now.return_value = NOW
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
        from daily_brief import config as cfg_mod

        cats = []  # empty categories, no network
        session = self._make_session({})
        logs = []

        async def _run():
            return await fetch_and_dedup(session, cats, logs.append)

        with mock.patch.object(cfg_mod, "TIMEZONE", "America/Chicago"):
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
    """rss_dedup(widen_category) — compatibility wrapper, still callable."""

    def test_compat_wrapper_no_crash(self):
        """widen_category wrapper doesn't crash; returns unchanged count."""
        cats: list = []
        session = None
        seen: dict = {}
        deduped: list = []
        logs: list = []

        async def _run():
            return await widen_category(
                session, "CatW", 2, seen, deduped, NOW, cats, logs.append
            )

        final, added, waf, wdf = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(final, 2)
        self.assertEqual(added, 0)


class TestLocalWidening(TestCase):
    """B.6: local candidate-pool widening via fetch_and_dedup.

    Tests the one-fetch, local-widening behavior: fetch_feed returns the full
    provider candidate pool (no max_stories truncation), widen_category operates
    locally on those candidates without additional HTTP requests.
    """

    def test_bug10_sixth_entry_recovered(self):
        """Bug-10 proof: first 5 entries fail the 24h window; 6th is within 48h.

        Under old behavior, max_stories=5 truncation would discard the 6th entry.
        With full candidate pools, local widening recovers it.
        """
        fresh = NOW - timedelta(hours=36)  # within 48h, outside 24h
        too_old = NOW - timedelta(hours=480)  # 20 days old
        cats = [("CatA", "query a", 10)]
        session = self._make_session({"query a": _rss_xml([
            {"title": f"Story {i}", "pubDate": too_old.strftime("%a, %d %b %Y %H:%M:%S +0000")}
            for i in range(5)
        ] + [
            {"title": "Recovered Story", "pubDate": fresh.strftime("%a, %d %b %Y %H:%M:%S +0000")}
        ])})
        logs = []

        async def _run():
            with mock.patch("daily_brief.pipelines.rss_dedup.datetime", wraps=datetime) as dt_mock:
                dt_mock.now.return_value = NOW
                return await fetch_and_dedup(session, cats, logs.append)

        deduped, stats = asyncio.get_event_loop().run_until_complete(_run())
        titles = [d[0] for d in deduped]
        self.assertIn("Recovered Story", titles)

    def test_one_request_per_category(self):
        """B.6: an underfilled category makes only one session.get() call."""
        class CountingSession:
            get_count = 0
            def get(self, url, **kw):
                CountingSession.get_count += 1
                return _AsyncCM(FakeResp(_rss_xml([
                    {"title": f"Old {i}", "pubDate": (NOW - timedelta(hours=480 * i)).strftime("%a, %d %b %Y %H:%M:%S +0000")}
                    for i in range(3)
                ])))

        cats = [("CatA", "query a", 5)]
        logs = []

        async def _run():
            return await fetch_and_dedup(CountingSession(), cats, logs.append)

        CountingSession.get_count = 0
        asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(CountingSession.get_count, 1)

    def test_exhausted_no_extra_requests(self):
        """Empty candidate pool — no additional HTTP requests for widening."""
        class CountingSession:
            get_count = 0
            def get(self, url, **kw):
                CountingSession.get_count += 1
                return _AsyncCM(FakeResp(_rss_xml([])))

        cats = [("CatA", "query a", 5)]
        logs = []

        async def _run():
            return await fetch_and_dedup(CountingSession(), cats, logs.append)

        CountingSession.get_count = 0
        asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(CountingSession.get_count, 1)

    def test_stable_category_order(self):
        """B.6: categories complete out of order, results are in configured order."""
        fresh = "Thu, 30 Jul 2026 10:00:00 +0000"
        cats = [
            ("CatA", "query a", 10),
            ("CatB", "query b", 10),
            ("CatC", "query c", 10),
        ]
        session = self._make_session({
            "query a": _rss_xml([{"title": "A1", "pubDate": fresh}]),
            "query b": _rss_xml([{"title": "B1", "pubDate": fresh}]),
            "query c": _rss_xml([{"title": "C1", "pubDate": fresh}]),
        })
        logs = []

        async def _run():
            with mock.patch("daily_brief.pipelines.rss_dedup.datetime", wraps=datetime) as dt_mock:
                dt_mock.now.return_value = NOW
                return await fetch_and_dedup(session, cats, logs.append)

        deduped, stats = asyncio.get_event_loop().run_until_complete(_run())
        categories = [d[4] for d in deduped]
        self.assertEqual(categories, ["CatA", "CatB", "CatC"])

    def test_cross_cat_first_wins(self):
        """B.6: duplicate title in two categories retains earlier configured category."""
        fresh = "Thu, 30 Jul 2026 10:00:00 +0000"
        xml = _rss_xml([{"title": "Dup Story", "pubDate": fresh}])
        cats = [
            ("CatFirst", "query first", 10),
            ("CatSecond", "query second", 10),
        ]
        session = self._make_session({
            "query first": xml,
            "query second": xml,
        })
        logs = []

        async def _run():
            with mock.patch("daily_brief.pipelines.rss_dedup.datetime", wraps=datetime) as dt_mock:
                dt_mock.now.return_value = NOW
                return await fetch_and_dedup(session, cats, logs.append)

        deduped, stats = asyncio.get_event_loop().run_until_complete(_run())
        dup_entries = [d for d in deduped if d[0] == "Dup Story"]
        self.assertEqual(len(dup_entries), 1)
        self.assertEqual(dup_entries[0][4], "CatFirst")

    def test_max_stories_output_cap(self):
        """B.6: max_stories is enforced as the final per-category output ceiling."""
        fresh = "Thu, 30 Jul 2026 10:00:00 +0000"
        items = [{"title": f"Story {i}", "pubDate": fresh} for i in range(20)]
        cats = [("CatA", "query a", 3)]
        session = self._make_session({"query a": _rss_xml(items)})
        logs = []

        async def _run():
            with mock.patch("daily_brief.pipelines.rss_dedup.datetime", wraps=datetime) as dt_mock:
                dt_mock.now.return_value = NOW
                return await fetch_and_dedup(session, cats, logs.append)

        deduped, stats = asyncio.get_event_loop().run_until_complete(_run())
        cat_entries = [d for d in deduped if d[4] == "CatA"]
        self.assertEqual(len(cat_entries), 3)

    def test_widening_boundary_24h(self):
        """Entry at exactly 24h remains eligible in the initial window (predicate is >)."""
        exactly = NOW - timedelta(hours=24)
        cats = [("CatA", "query a", 10)]
        session = _make_boundary_session(exactly.strftime("%a, %d %b %Y %H:%M:%S +0000"))
        logs = []

        async def _run():
            with mock.patch("daily_brief.pipelines.rss_dedup.datetime", wraps=datetime) as dt_mock:
                dt_mock.now.return_value = NOW
                return await fetch_and_dedup(session, cats, logs.append)

        deduped, stats = asyncio.get_event_loop().run_until_complete(_run())
        titles = [d[0] for d in deduped]
        self.assertIn("Boundary Story", titles)

    def test_widening_boundary_older_excluded(self):
        """Entries older than 7d are never included."""
        too_old = NOW - timedelta(days=10)
        fresh = "Thu, 30 Jul 2026 10:00:00 +0000"
        cats = [("CatA", "query a", 10)]
        session = self._make_session({"query a": _rss_xml([
            {"title": "Boundary Story", "pubDate": fresh},
            {"title": "Too Old", "pubDate": too_old.strftime("%a, %d %b %Y %H:%M:%S +0000")},
        ])})
        logs = []

        async def _run():
            return await fetch_and_dedup(session, cats, logs.append)

        deduped, stats = asyncio.get_event_loop().run_until_complete(_run())
        titles = [d[0] for d in deduped]
        self.assertNotIn("Too Old", titles)

    def test_widening_filters_duplicates(self):
        """B.6: duplicate candidates during widening do not count as recovered."""
        cats = [("CatA", "query a", 10)]
        fresh = NOW - timedelta(hours=2)
        old = NOW - timedelta(hours=48)
        session = self._make_session({"query a": _rss_xml([
            {"title": "Fresh Story", "pubDate": fresh.strftime("%a, %d %b %Y %H:%M:%S +0000")},
            {"title": "Dup Title", "pubDate": old.strftime("%a, %d %b %Y %H:%M:%S +0000")},
            {"title": "Dup Title", "pubDate": old.strftime("%a, %d %b %Y %H:%M:%S +0000")},
        ])})
        logs = []

        async def _run():
            with mock.patch("daily_brief.pipelines.rss_dedup.datetime", wraps=datetime) as dt_mock:
                dt_mock.now.return_value = NOW
                return await fetch_and_dedup(session, cats, logs.append)

        deduped, stats = asyncio.get_event_loop().run_until_complete(_run())
        dup_titles = [d[0] for d in deduped if d[0] == "Dup Title"]
        self.assertEqual(len(dup_titles), 1)

    def test_widening_filters_obituary(self):
        """B.6: obituary candidates are not counted as recovered."""
        cats = [("CatA", "query a", 10)]
        old = NOW - timedelta(hours=48)
        session = self._make_session({"query a": _rss_xml([
            {"title": "John Obituary", "pubDate": old.strftime("%a, %d %b %Y %H:%M:%S +0000")},
        ])})
        logs = []

        async def _run():
            return await fetch_and_dedup(session, cats, logs.append)

        deduped, stats = asyncio.get_event_loop().run_until_complete(_run())
        titles = [d[0] for d in deduped]
        self.assertNotIn("John Obituary", titles)

    def test_widening_filters_realestate(self):
        """B.6: real-estate candidates are not counted as recovered."""
        cats = [("CatA", "query a", 10)]
        old = NOW - timedelta(hours=48)
        session = self._make_session({"query a": _rss_xml([
            {"title": "House for sale $200k", "pubDate": old.strftime("%a, %d %b %Y %H:%M:%S +0000")},
        ])})
        logs = []

        async def _run():
            return await fetch_and_dedup(session, cats, logs.append)

        deduped, stats = asyncio.get_event_loop().run_until_complete(_run())
        titles = [d[0] for d in deduped]
        self.assertNotIn("House for sale $200k", titles)

    def test_failure_isolation(self):
        """B.6: one failed feed does not prevent successful categories."""
        class FailingSession:
            get_count = 0
            def get(self, url, **kw):
                FailingSession.get_count += 1
                if "query fail" in url:
                    raise ConnectionError("network fail")
                return _AsyncCM(FakeResp(_rss_xml([
                    {"title": "OK Story", "pubDate": "Thu, 30 Jul 2026 10:00:00 +0000"},
                ])))

        cats = [
            ("CatFail", "query fail", 10),
            ("CatOK", "query ok", 10),
        ]
        logs = []

        async def _run():
            with mock.patch("daily_brief.pipelines.rss_dedup.datetime", wraps=datetime) as dt_mock:
                dt_mock.now.return_value = NOW
                return await fetch_and_dedup(FailingSession(), cats, logs.append)

        deduped, stats = asyncio.get_event_loop().run_until_complete(_run())
        titles = [d[0] for d in deduped]
        self.assertIn("OK Story", titles)

    def _make_session(self, body_map: dict):
        class FakeSession:
            def get(self, url, **kw):
                for k, v in body_map.items():
                    if k in url:
                        return _AsyncCM(FakeResp(v))
                return _AsyncCM(FakeResp(_rss_xml([])))
        return FakeSession()
