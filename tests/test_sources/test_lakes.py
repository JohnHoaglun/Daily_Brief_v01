"""
Unit tests for src/daily_brief/sources/lakes.py.
Reservoir level scraping: table parsing, label matching, date fallback, and regex fallback.
"""
import asyncio
from datetime import datetime, timedelta
from unittest import TestCase, mock
from unittest.mock import AsyncMock

from daily_brief.sources.lakes import _extract_lake_value


REF = datetime(2026, 7, 18, 10, 0, 0)


def _table_html(
    today_pct="65.2",
    week_pct="60.0",
    month_pct="55.5",
    today_date="2026-07-18",
    week_date="2026-07-11",
    month_date="2026-06-18",
    label_today="Today",
    label_week="1 week ago",
    label_30="30 days ago",
    extra_rows=None,
):
    rows = []
    rows.append(
        f"<tr><td>{label_today}</td><td>{today_date}</td><td>{today_pct}%</td></tr>"
    )
    rows.append(
        f"<tr><td>{label_week}</td><td>{week_date}</td><td>{week_pct}%</td></tr>"
    )
    rows.append(
        f"<tr><td>{label_30}</td><td>{month_date}</td><td>{month_pct}%</td></tr>"
    )
    if extra_rows:
        rows.extend(extra_rows)
    return f"<table><tbody>{''.join(rows)}</tbody></table>"


def _text_only_html(pcts):
    body = " ".join(f"{v}%" for v in pcts)
    return f"<html><body>{body}</body></html>"


class TestExtractLakeValueLabelMatching(TestCase):
    """Table row label matching — happy paths."""

    async def _run(self, html):
        with mock.patch("daily_brief.sources.lakes._fetch_text", new=AsyncMock(return_value=html)):
            return await _extract_lake_value(None, "lake1", "http://example.com", REF)

    def test_today_label(self):
        html = _table_html(today_pct="65.2", label_today="Today")
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["today"], "65.2%")

    def test_current_label(self):
        html = _table_html(today_pct="70.0", label_today="Current")
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["today"], "70.0%")

    def test_one_week_ago_label(self):
        html = _table_html(week_pct="60.0", label_week="1 week ago")
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["one_week_ago"], "60.0%")

    def test_week_ago_short_label(self):
        html = _table_html(week_pct="60.0", label_week="Week ago")
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["one_week_ago"], "60.0%")

    def test_7_day_label(self):
        html = _table_html(week_pct="60.0", label_week="7 day ago")
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["one_week_ago"], "60.0%")

    def test_30_days_ago_label(self):
        html = _table_html(month_pct="55.5", label_30="30 days ago")
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["thirty_days_ago"], "55.5%")

    def test_thirty_days_ago_label(self):
        html = _table_html(month_pct="55.5", label_30="thirty days ago")
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["thirty_days_ago"], "55.5%")

    def test_1_month_ago_label(self):
        html = _table_html(month_pct="55.5", label_30="1 month ago")
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["thirty_days_ago"], "55.5%")

    def test_30d_label(self):
        html = _table_html(month_pct="55.5", label_30="30d")
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["thirty_days_ago"], "55.5%")

    def test_full_happy_path(self):
        html = _table_html(today_pct="65.2", week_pct="60.0", month_pct="55.5")
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["today"], "65.2%")
        self.assertEqual(result["one_week_ago"], "60.0%")
        self.assertEqual(result["thirty_days_ago"], "55.5%")


class TestExtractLakeValueNoneResults(TestCase):
    """Edge cases: empty html, short rows, bad percents."""

    async def _run(self, html):
        with mock.patch("daily_brief.sources.lakes._fetch_text", new=AsyncMock(return_value=html)):
            return await _extract_lake_value(None, "lake1", "http://example.com", REF)

    def test_no_html_returns_all_none(self):
        with mock.patch("daily_brief.sources.lakes._fetch_text", new=AsyncMock(return_value=None)):
            result = asyncio.get_event_loop().run_until_complete(self._run(None))
        self.assertIsNone(result["today"])
        self.assertIsNone(result["one_week_ago"])
        self.assertIsNone(result["thirty_days_ago"])

    def test_empty_html(self):
        result = asyncio.get_event_loop().run_until_complete(self._run(""))
        self.assertIsNone(result["today"])

    def test_short_rows_skipped(self):
        html = "<table><tbody><tr><td>A</td><td>B</td></tr></tbody></table>"
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertIsNone(result["today"])

    def test_bad_percent_skipped(self):
        html = "<table><tbody><tr><td>Today</td><td>2026-07-18</td><td>n/a</td></tr></tbody></table>"
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertIsNone(result["today"])


class TestExtractLakeValueDateFallback(TestCase):
    """Date-based matching when label matching doesn't fill a slot."""

    async def _run(self, html):
        with mock.patch("daily_brief.sources.lakes._fetch_text", new=AsyncMock(return_value=html)):
            return await _extract_lake_value(None, "lake1", "http://example.com", REF)

    def test_exact_date_match_today(self):
        html = (
            "<table><tbody>"
            "<tr><td>Snapshot</td><td>2026-07-18</td><td>65.2%</td></tr>"
            "</tbody></table>"
        )
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["today"], "65.2%")

    def test_exact_date_match_week(self):
        # Label doesn't match "1 week ago", so falls back to date matching
        html = (
            "<table><tbody>"
            "<tr><td>Weekly</td><td>2026-07-11</td><td>60.0%</td></tr>"
            "</tbody></table>"
        )
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["one_week_ago"], "60.0%")

    def test_exact_date_match_30(self):
        html = (
            "<table><tbody>"
            "<tr><td>Monthly</td><td>2026-06-18</td><td>55.5%</td></tr>"
            "</tbody></table>"
        )
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["thirty_days_ago"], "55.5%")

    def test_closest_date_fallback(self):
        # No exact match for 2026-07-18; closest row is 2026-07-17
        html = (
            "<table><tbody>"
            "<tr><td>Reading</td><td>2026-07-17</td><td>64.0%</td></tr>"
            "</tbody></table>"
        )
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["today"], "64.0%")


class TestExtractLakeValueRegexFallback(TestCase):
    """Legacy regex fallback when table parsing leaves None values."""

    async def _run(self, html):
        with mock.patch("daily_brief.sources.lakes._fetch_text", new=AsyncMock(return_value=html)):
            return await _extract_lake_value(None, "lake1", "http://example.com", REF)

    def test_regex_fills_all_none(self):
        html = _text_only_html(["72.5", "68.3", "61.0"])
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["today"], "72.5%")
        self.assertEqual(result["one_week_ago"], "68.3%")
        self.assertEqual(result["thirty_days_ago"], "61.0%")

    def test_regex_partial_fallback(self):
        html = (
            _table_html(today_pct="65.2")
            + _text_only_html(["60.0", "55.5"])
        )
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["today"], "65.2%")
        self.assertIsNotNone(result["one_week_ago"])
        self.assertIsNotNone(result["thirty_days_ago"])
