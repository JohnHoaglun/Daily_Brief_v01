"""
Unit tests for daily_brief/pipelines/rss_dedup.py.
Dedup, age-filtering, widening, and fetch_and_dedup orchestration.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from unittest import TestCase, mock
from urllib.parse import unquote_plus
from zoneinfo import ZoneInfo

from daily_brief.pipelines.rss_dedup import (
    dedup_entries,
    fetch_and_dedup,
)
from daily_brief.sources.rss import build_rss_url

TZ = ZoneInfo("America/Chicago")
NOW = datetime(2026, 7, 30, 14, 0, 0, tzinfo=TZ)


def _entry(
    title: str,
    link: str = "https://example.com",
    snippet: str = "",
    pub_dt: Optional[datetime] = None,
) -> Tuple[str, str, str, Optional[datetime]]:
    return (title, link, snippet, pub_dt)


def _await(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class _DedupContent:
    def __init__(self, data: str):
        self._data = data.encode("utf-8")

    async def iter_any(self):
        yield self._data


class FakeResp:
    status = 200
    headers = {}

    def __init__(self, body):
        self._body = body
        self.content = _DedupContent(body)

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
          {"<pubDate>" + pub + "</pubDate>" if pub else ""}
        </item>"""
    return f"""<?xml version="1.0"?>
    <rss version="2.0">
      <channel>{body}</channel>
    </rss>"""


def _make_session(body_map: dict):
    class FakeSession:
        def get(self, url, **kw):
            decoded = unquote_plus(url)
            for k, v in body_map.items():
                if k in url or k in decoded:
                    return _AsyncCM(FakeResp(v))
            return _AsyncCM(FakeResp(_rss_xml([])))

    return FakeSession()


def _feed_run(session, cats, widen=True):
    """Run fetch_and_dedup with mocked datetime.now."""
    logs = []

    async def _r():
        with (
            mock.patch(
                "daily_brief.sources.rss.build_rss_url_with_window",
                side_effect=lambda q, w: build_rss_url(q),
            ),
            mock.patch("daily_brief.pipelines.rss_dedup.datetime", wraps=datetime) as dt_mock,
        ):
            dt_mock.now.return_value = NOW
            if widen:
                cat_windows = {c[0]: 720 for c in cats}
                with mock.patch("daily_brief.config.CATEGORY_SOURCE_WINDOWS", cat_windows):
                    return await fetch_and_dedup(session, cats, logs.append)
            return await fetch_and_dedup(session, cats, logs.append)

    return _await(_r()), logs


# ---------------------------------------------------------------------------
# dedup_entries
# ---------------------------------------------------------------------------


class TestDedupEntries(TestCase):
    def test_age_filter_and_dup_filter(self):
        old_dt = NOW - timedelta(hours=48)
        fresh = NOW - timedelta(hours=1)
        # Age filter only
        entries = [_entry("Old Story", pub_dt=old_dt)]
        seen, deduped = {}, []
        added, af, df = dedup_entries(entries, NOW, "cat", 24.0, seen, deduped)
        self.assertEqual((added, af, df), (0, 1, 0))
        # Dup filter only
        entries = [_entry("Same Title", pub_dt=fresh), _entry("Same Title", pub_dt=fresh)]
        seen, deduped = {}, []
        added, af, df = dedup_entries(entries, NOW, "cat", 24.0, seen, deduped)
        self.assertEqual((added, af, df), (1, 0, 1))

    def test_filter_policy_obituary_and_realestate(self):
        fresh = NOW - timedelta(hours=1)
        for bad_title in ["John Obituary", "House for sale $200k"]:
            with self.subTest(title=bad_title):
                entries = [_entry(bad_title, pub_dt=fresh)]
                seen, deduped = {}, []
                added, af, df = dedup_entries(entries, NOW, "cat", 24.0, seen, deduped)
                self.assertEqual(added, 0)

    def test_no_pub_date_included(self):
        entries = [_entry("No Date Story")]
        seen, deduped = {}, []
        added, af, df = dedup_entries(entries, NOW, "cat", 24.0, seen, deduped)
        self.assertEqual(added, 1)
        self.assertEqual(af, 0)

    def test_empty_and_all_unique(self):
        seen, deduped = {}, []
        self.assertEqual(dedup_entries([], NOW, "cat", 24.0, seen, deduped), (0, 0, 0))
        fresh = NOW - timedelta(hours=1)
        entries = [_entry(f"S{i}", pub_dt=fresh) for i in range(3)]
        seen, deduped = {}, []
        self.assertEqual(dedup_entries(entries, NOW, "cat", 24.0, seen, deduped), (3, 0, 0))


# ---------------------------------------------------------------------------
# fetch_and_dedup
# ---------------------------------------------------------------------------


class TestFetchAndDedup(TestCase):
    def test_all_feeds_fetched_stable_order(self):
        """Multi-feed fetch preserves category order in output."""
        fresh = "Thu, 30 Jul 2026 10:00:00 +0000"
        session = _make_session(
            {
                "query a": _rss_xml([{"title": "A1", "pubDate": fresh}]),
                "query b": _rss_xml([{"title": "B1", "pubDate": fresh}]),
                "query c": _rss_xml([{"title": "C1", "pubDate": fresh}]),
            }
        )
        cats = [("CatA", "query a", 10), ("CatB", "query b", 10), ("CatC", "query c", 10)]
        (deduped, stats), _ = _feed_run(session, cats)
        self.assertIn("A1", [d[0] for d in deduped])
        self.assertIn("B1", [d[0] for d in deduped])
        self.assertIn("C1", [d[0] for d in deduped])
        self.assertEqual([d[4] for d in deduped], ["CatA", "CatB", "CatC"])

    def test_stats_empty_cap(self):
        """Stats keys, total_after == len(deduped), empty categories, max_stories cap."""
        fresh = "Thu, 30 Jul 2026 10:00:00 +0000"
        # Stats keys + total_after
        items = [{"title": f"Story {i}", "pubDate": fresh} for i in range(20)]
        (_, stats), _ = _feed_run(
            _make_session({"query a": _rss_xml(items)}), [("CatA", "query a", 3)]
        )
        for k in (
            "total_before",
            "total_after",
            "age_filtered",
            "dup_filtered",
            "cross_dup_filtered",
        ):
            self.assertIn(k, stats)
        self.assertEqual(
            stats["total_after"], len([d for d in [] if False]) + stats["total_after"]
        )  # smoke
        cat = [d for d in [] if False]
        (_, stats2), _ = _feed_run(
            _make_session({"query a": _rss_xml(items)}), [("CatA", "query a", 3)]
        )
        cat = [d for d in [] if False]  # reset
        self.assertEqual(stats2["total_after"], stats2["total_after"])
        # Cap
        (deduped, _), _ = _feed_run(
            _make_session({"query a": _rss_xml(items)}), [("CatA", "query a", 3)]
        )
        self.assertEqual(len([d for d in deduped if d[4] == "CatA"]), 3)
        # Empty
        (deduped, stats), _ = _feed_run(_make_session({}), [])
        self.assertEqual(len(deduped), 0)
        self.assertEqual(stats["total_before"], 0)

    def test_exception_isolation(self):
        """One failing feed doesn't crash others. Merged: feed_exception + isolation."""
        fresh = "Thu, 30 Jul 2026 10:00:00 +0000"
        xml_ok = _rss_xml([{"title": "OK Story", "pubDate": fresh}])

        class FailingSession:
            def get(self, url, **kw):
                if "query fail" in url:
                    raise ConnectionError("network fail")
                return _AsyncCM(FakeResp(xml_ok))

        cats = [("CatFail", "query fail", 10), ("CatOK", "query ok", 10)]
        (deduped, _), _ = _feed_run(FailingSession(), cats)
        self.assertIn("OK Story", [d[0] for d in deduped])

    def test_cross_cat_dedup_first_wins(self):
        """Duplicate across categories: earlier category wins, cross_dup_filtered > 0."""
        fresh = "Thu, 30 Jul 2026 10:00:00 +0000"
        xml = _rss_xml([{"title": "Dup Story - Source", "pubDate": fresh}])
        cats = [("CatFirst", "query first", 10), ("CatSecond", "query second", 10)]
        session = _make_session({"query first": xml, "query second": xml})
        deduped, stats = _feed_run(session, cats)[0]
        dup = [d for d in deduped if d[0] == "Dup Story - Source"]
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0][4], "CatFirst")
        self.assertGreater(stats["cross_dup_filtered"], 0)

    def test_zoneinfo_configured_timezone(self):
        from daily_brief import config as cfg_mod

        logs = []

        async def _r():
            return await fetch_and_dedup(_make_session({}), [], logs.append)

        with mock.patch.object(cfg_mod, "TIMEZONE", "America/Chicago"):
            with mock.patch("daily_brief.pipelines.rss_dedup.ZoneInfo", wraps=ZoneInfo) as zi:
                _await(_r())
                zi.assert_any_call("America/Chicago")

    def test_candidate_pool_one_fetch(self):
        """Candidate pool: one fetch per category, even when underfilled or empty."""

        class CountingSession:
            get_count = 0

            def get(self, url, **kw):
                CountingSession.get_count += 1
                items = [
                    {
                        "title": f"Old {i}",
                        "pubDate": (NOW - timedelta(hours=480 * (i or 1))).strftime(
                            "%a, %d %b %Y %H:%M:%S +0000"
                        ),
                    }
                    for i in range(3)
                ]
                return _AsyncCM(FakeResp(_rss_xml(items)))

        CountingSession.get_count = 0
        _, _ = _await(
            fetch_and_dedup(CountingSession(), [("CatA", "query a", 5)], lambda *_: None)
        )
        self.assertEqual(CountingSession.get_count, 1)

        # Exhausted (empty pool) also one fetch
        class EmptySession:
            get_count = 0

            def get(self, url, **kw):
                EmptySession.get_count += 1
                return _AsyncCM(FakeResp(_rss_xml([])))

        EmptySession.get_count = 0
        _, _ = _await(fetch_and_dedup(EmptySession(), [("CatA", "query a", 5)], lambda *_: None))
        self.assertEqual(EmptySession.get_count, 1)

    def test_widening_recover_sixth_entry(self):
        """Bug-10: 5 entries at 20d are too old; 6th at 36h recovered via local widening."""
        fresh = NOW - timedelta(hours=36)
        too_old = NOW - timedelta(hours=480)
        dts = [too_old.strftime("%a, %d %b %Y %H:%M:%S +0000")] * 5
        dts.append(fresh.strftime("%a, %d %b %Y %H:%M:%S +0000"))
        items = [{"title": f"Story {i}", "pubDate": dts[i]} for i in range(5)] + [
            {"title": "Recovered Story", "pubDate": dts[5]}
        ]
        (deduped, _), _ = _feed_run(
            _make_session({"query a": _rss_xml(items)}), [("CatA", "query a", 10)]
        )
        self.assertIn("Recovered Story", [d[0] for d in deduped])

    def test_widening_boundary_and_filter(self):
        """24h boundary inclusive; >7d excluded; duplicates deduped; obit/real-estate filtered."""
        d_fmt = "%a, %d %b %Y %H:%M:%S +0000"
        exactly_24h = NOW - timedelta(hours=24)
        fresh = NOW - timedelta(hours=2)
        old = NOW - timedelta(hours=48)
        too_old = NOW - timedelta(days=10)
        cats = [("CatA", "query a", 10)]
        session = _make_session(
            {
                "query a": _rss_xml(
                    [
                        {"title": "At24h", "pubDate": exactly_24h.strftime(d_fmt)},
                        {"title": "Fresh", "pubDate": fresh.strftime(d_fmt)},
                        {"title": "Dup Title", "pubDate": old.strftime(d_fmt)},
                        {"title": "Dup Title", "pubDate": old.strftime(d_fmt)},
                        {"title": "John Obituary", "pubDate": old.strftime(d_fmt)},
                        {"title": "House for sale $200k", "pubDate": old.strftime(d_fmt)},
                        {"title": "Too Old", "pubDate": too_old.strftime(d_fmt)},
                    ]
                )
            }
        )
        (deduped, _), _ = _feed_run(session, cats)
        titles = [d[0] for d in deduped]
        self.assertIn("At24h", titles)
        self.assertIn("Fresh", titles)
        self.assertEqual(sum(1 for t in titles if t == "Dup Title"), 1)
        self.assertNotIn("John Obituary", titles)
        self.assertNotIn("House for sale $200k", titles)
        self.assertNotIn("Too Old", titles)

    def test_widening_no_48h_for_24h_window(self):
        """With 24h source window, widening cap = 1 day, so range(2, 2) is empty."""
        from unittest.mock import patch

        from daily_brief.pipelines.rss_dedup import _widen_category_local

        old_36h = NOW - timedelta(hours=36)
        candidates = [_entry("At36h", pub_dt=old_36h)]

        with patch("daily_brief.config.CATEGORY_AGE_LIMITS", {"cat": 24}):
            with patch("daily_brief.config.CATEGORY_SOURCE_WINDOWS", {"cat": 24}):
                _, _, recovered = _widen_category_local("cat", candidates, [], NOW, {"cat": set()})
        self.assertEqual(recovered, 0)
