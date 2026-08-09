"""
Unit tests for daily_brief/sources/lakes.py.
Reservoir level scraping: table parsing, label matching, date fallback, regex fallback.
"""
import asyncio
from datetime import datetime
from unittest import TestCase, mock
from unittest.mock import AsyncMock

from daily_brief.sources.lakes import _extract_lake_value

REF = datetime(2026, 7, 18, 10, 0, 0)


def _table_html(today_pct="65.2", week_pct="60.0", month_pct="55.5",
                label_today="Today", label_week="1 week ago", label_30="30 days ago"):
    return (
        f"<table><tbody>"
        f"<tr><td>{label_today}</td><td>2026-07-18</td><td>{today_pct}%</td></tr>"
        f"<tr><td>{label_week}</td><td>2026-07-11</td><td>{week_pct}%</td></tr>"
        f"<tr><td>{label_30}</td><td>2026-06-18</td><td>{month_pct}%</td></tr>"
        f"</tbody></table>"
    )


class TestExtractLakeValueLabelMatching(TestCase):
    """Table row label matching — representative labels for today, 7-day, 30-day."""

    async def _run(self, html):
        with mock.patch("daily_brief.sources.lakes._fetch_text", new=AsyncMock(return_value=html)):
            return await _extract_lake_value(None, "lake1", "http://example.com", REF)

    def test_today_labels(self):
        r1 = asyncio.get_event_loop().run_until_complete(self._run(_table_html(label_today="Today")))
        self.assertEqual(r1["today"], "65.2%")

        r2 = asyncio.get_event_loop().run_until_complete(self._run(_table_html(today_pct="70.0", label_today="Current")))
        self.assertEqual(r2["today"], "70.0%")

    def test_week_labels(self):
        r1 = asyncio.get_event_loop().run_until_complete(self._run(_table_html(label_week="1 week ago")))
        self.assertEqual(r1["one_week_ago"], "60.0%")

        r2 = asyncio.get_event_loop().run_until_complete(self._run(_table_html(label_week="Week ago")))
        self.assertEqual(r2["one_week_ago"], "60.0%")

    def test_30_day_labels(self):
        r1 = asyncio.get_event_loop().run_until_complete(self._run(_table_html(label_30="30 days ago")))
        self.assertEqual(r1["thirty_days_ago"], "55.5%")

        r2 = asyncio.get_event_loop().run_until_complete(self._run(_table_html(label_30="thirty days ago")))
        self.assertEqual(r2["thirty_days_ago"], "55.5%")

class TestExtractLakeValueEdgeCases(TestCase):
    """Edge cases: no HTML, invalid content, malformed dates."""

    async def _run(self, html):
        with mock.patch("daily_brief.sources.lakes._fetch_text", new=AsyncMock(return_value=html)):
            return await _extract_lake_value(None, "lake1", "http://example.com", REF)

    def test_no_html_empty_invalid(self):
        with mock.patch("daily_brief.sources.lakes._fetch_text", new=AsyncMock(return_value=None)):
            result = asyncio.get_event_loop().run_until_complete(self._run(None))
        self.assertIsNone(result["today"])

        result2 = asyncio.get_event_loop().run_until_complete(self._run(""))
        self.assertIsNone(result2["today"])

        html = "<table><tbody><tr><td>Today</td><td>2026-07-18</td><td>n/a</td></tr></tbody></table>"
        result3 = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertIsNone(result3["today"])

    def test_date_fallback(self):
        html = "<table><tbody><tr><td>Snapshot</td><td>2026-07-18</td><td>65.2%</td></tr></tbody></table>"
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["today"], "65.2%")

    def test_regex_fallback(self):
        html = "<html><body>72.5% 68.3% 61.0%</body></html>"
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["today"], "72.5%")
        self.assertEqual(result["one_week_ago"], "68.3%")
        self.assertEqual(result["thirty_days_ago"], "61.0%")

        partial = _table_html() + "<html><body>60.0% 55.5%</body></html>"
        result2 = asyncio.get_event_loop().run_until_complete(self._run(partial))
        self.assertEqual(result2["today"], "65.2%")
        self.assertIsNotNone(result2["one_week_ago"])
        self.assertIsNotNone(result2["thirty_days_ago"])

    def test_malformed_date_skipped(self):
        html = (
            "<table><tbody>"
            "<tr><td>Snapshot</td><td>July 18, 2026</td><td>65.2%</td></tr>"
            "<tr><td>Snapshot</td><td>2026-07-11</td><td>60.0%</td></tr>"
            "</tbody></table>"
        )
        result = asyncio.get_event_loop().run_until_complete(self._run(html))
        self.assertEqual(result["one_week_ago"], "60.0%")
