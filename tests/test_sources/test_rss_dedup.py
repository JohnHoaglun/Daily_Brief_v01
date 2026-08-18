"""
Unit tests for daily_brief/pipelines/rss_dedup.py.
"""

from __future__ import annotations

import asyncio
import unittest.mock
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from urllib.parse import unquote_plus
from zoneinfo import ZoneInfo

from daily_brief.pipelines.rss_dedup import dedup_entries, fetch_and_dedup
from daily_brief.sources.rss import build_rss_url

TZ = ZoneInfo("America/Chicago")
NOW = datetime(2026, 7, 30, 14, 0, 0, tzinfo=TZ)
Await = lambda c: asyncio.get_event_loop().run_until_complete(c)


def _entry(title, link="https://example.com", pub_dt=None):
    return (title, link, "", pub_dt)


def _rss_xml(items):
    body = "".join(f'<item><title>{i.get("title","S")}</title>'
                   f'<link>{i.get("link","https://e.com/0")}</link>'
                   f'<summary></summary>'
                   f'{"<pubDate>"+i["pubDate"]+"</pubDate>" if i.get("pubDate") else ""}'
                   f"</item>" for i in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{body}</channel></rss>'


def _make_session(body_map):
    class S:
        def get(self, url, **kw):
            decoded = unquote_plus(url)
            for k, v in body_map.items():
                if k in url or k in decoded:
                    return _AsyncCM(FakeResp(v))
            return _AsyncCM(FakeResp(""))
    return S()


class _FakeContent:
    def __init__(self, data: str):
        self._data = data.encode("utf-8") if isinstance(data, str) else data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def read(self):
        return self._data

    async def iter_chunked(self, n):
        for i in range(0, len(self._data), n):
            yield self._data[i:i + n]


class FakeResp:
    status = 200
    headers = {}

    def __init__(self, body):
        self._body = body
        self.content = _FakeContent(body) if isinstance(body, (str, bytes)) else body
        self._text = body

    async def text(self):
        return self._body if isinstance(self._body, str) else self._body.decode("utf-8", errors="replace")


class _AsyncCM:
    def __init__(self, resp):
        self._resp = resp
    async def __aenter__(self):
        return self._resp
    async def __aexit__(self, *a):
        pass


class TestDedupEntries:
    def test_age_filter_and_dup_filter(self):
        old = NOW - timedelta(hours=48)
        fresh = NOW - timedelta(hours=1)
        entries = [_entry("Old", pub_dt=old)]
        assert dedup_entries(entries, NOW, "cat", 24.0, {}, []) == (0, 1, 0)
        entries = [_entry("Same", pub_dt=fresh), _entry("Same", pub_dt=fresh)]
        assert dedup_entries(entries, NOW, "cat", 24.0, {}, []) == (1, 0, 1)

    def test_no_pub_date(self):
        added, af, _ = dedup_entries([_entry("No Date")], NOW, "cat", 24.0, {}, [])
        assert added == 1 and af == 0


def _feed_run(session, cats, widen=True):
    async def _r():
        import unittest.mock as m
        with m.patch("daily_brief.sources.rss.build_rss_url_with_window",
                      side_effect=lambda q, w: build_rss_url(q)), \
             m.patch("daily_brief.pipelines.rss_dedup.datetime",
                      wraps=datetime) as dt:
            dt.now.return_value = NOW
            if widen:
                with m.patch("daily_brief.config.CATEGORY_SOURCE_WINDOWS",
                              {c[0]: 720 for c in cats}):
                    return await fetch_and_dedup(session, cats, lambda *_: None)
            return await fetch_and_dedup(session, cats, None)
    return Await(_r()), []


class TestFetchAndDedup:
    def test_cross_cat_dedup(self):
        """Dup across categories: earlier category wins."""
        xml = _rss_xml([{"title": "Dup", "pubDate": "Thu, 30 Jul 2026 10:00:00 +0000"}])
        cats = [("CF", "q1", 10), ("CS", "q2", 10)]
        (deduped, stats), _ = _feed_run(_make_session({"q1": xml, "q2": xml}), cats)
        dup = [d for d in deduped if d[0] == "Dup"]
        assert len(dup) == 1 and dup[0][4] == "CF" and stats["cross_dup_filtered"] > 0

    def test_stories_capped(self):
        """Cap limits results per category."""
        fresh = "Thu, 30 Jul 2026 10:00:00 +0000"
        items = [{"title": f"S{i}", "pubDate": fresh} for i in range(20)]
        (deduped, _), _ = _feed_run(_make_session({"q": _rss_xml(items)}), [("CA", "q", 3)])
        assert len([d for d in deduped if d[4] == "CA"]) == 3

    def test_widening_recovers(self):
        """6th entry recovered via local widening."""
        fresh = (NOW - timedelta(hours=36)).strftime("%a, %d %b %Y %H:%M:%S +0000")
        old = [(NOW - timedelta(hours=480)).strftime("%a, %d %b %Y %H:%M:%S +0000")] * 5
        items = [{"title": f"S{i}", "pubDate": old[i]} for i in range(5)] + [
            {"title": "Recovered", "pubDate": fresh}]
        (deduped, _), _ = _feed_run(_make_session({"q": _rss_xml(items)}), [("CA", "q", 10)])
        assert "Recovered" in [d[0] for d in deduped]

    def test_failed_feed(self):
        """One failing feed doesn't crash others."""
        xml_ok = _rss_xml([{"title": "OK", "pubDate": "Thu, 30 Jul 2026 10:00:00 +0000"}])
        class FS:
            def get(self, url, **kw):
                if "fail" in url:
                    raise ConnectionError("fail")
                return _AsyncCM(FakeResp(xml_ok))
        cats = [("CF", "fail", 10), ("CO", "ok", 10)]
        (deduped, _), _ = _feed_run(FS(), cats)
        assert "OK" in [d[0] for d in deduped]


class TestWidening:
    def test_multi_band_widening_order_and_cap(self):
        """Stories recovered across widening bands in newest-first order;
        outer cap truncates after widening stops."""
        items = []
        for h, t in [(40, "S1"), (64, "S2"), (88, "S3"), (112, "S4"),
                     (36, "S0"), (480, "Sold")]:
            offset = (NOW - timedelta(hours=h)).strftime("%a, %d %b %Y %H:%M:%S +0000")
            items.append({"title": t, "pubDate": offset})
        (deduped, _), _ = _feed_run(
            _make_session({"q": _rss_xml(items)}),
            [("CA", "q", 2)],
        )
        cat_stories = [d[0] for d in deduped if d[4] == "CA"]
        assert "S0" in cat_stories
        cap = max(2, 0)
        assert len(cat_stories) == cap

    def test_widening_local_dedup_state_shared_with_initial(self):
        """Local widening shares the category seen-set from initial pass;
        a title already in seen should increment dup_filtered but not
        be added to accepted."""
        from daily_brief.pipelines.rss_dedup import _widen_category_local
        import datetime as dt_mod

        t0 = NOW - timedelta(hours=20)
        t1 = NOW - timedelta(hours=36)
        candidates = [
            ("Dup Title", "https://a.com", "", t0),
            ("Unique", "https://b.com", "", t1),
        ]
        accepted: list = []
        seen_map: dict = {"W": {"dup title"}}  # already seen in initial pass

        with (
            unittest.mock.patch(
                "daily_brief.config.CATEGORY_AGE_LIMITS",
                {"W": 10},
            ),
            unittest.mock.patch(
                "daily_brief.config.CATEGORY_SOURCE_WINDOWS",
                {"W": 168},
            ),
            unittest.mock.patch.object(
                dt_mod, "datetime", wraps=dt_mod.datetime
            ) as mocked_dt,
        ):
            mocked_dt.now.return_value = NOW

            age_filtered, dup_filtered, recovered = _widen_category_local(
                "W", candidates, accepted, NOW, seen_map,
            )

        assert age_filtered == 0
        assert dup_filtered == 1
        assert recovered == 1
        assert len(accepted) == 1
        assert accepted[0][0] == "Unique"
