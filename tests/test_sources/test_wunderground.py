"""
Unit tests for daily_brief/sources/wunderground.py.
Wunderground station scraping, precipitation parsing, and metrics fetching.
"""

import asyncio
from datetime import datetime
from unittest import TestCase, mock
from unittest.mock import AsyncMock

from daily_brief.sources.wunderground import (
    _fetch_station_metrics,
    _fetch_station_monthly_rainfall,
    _parse_wu_monthly_precipitation,
)


class TestParseWuMonthlyPrecipitation(TestCase):
    """Precipitation extraction - valid, dated fallback, edge cases."""

    def test_valid_extraction(self):
        html = "<html><body><div>Summary Jul 1-30 Precipitation 3.45 in</div><div>graph</div></body></html>"
        result = _parse_wu_monthly_precipitation(html, "2026-07-01", "2026-07-30")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 3.45, places=1)

        html2 = (
            "<html><body><div>Summary Precipitation 5 in next</div><div>graph</div></body></html>"
        )
        result2 = _parse_wu_monthly_precipitation(html2, "2026-01-01", "2026-01-31")
        self.assertAlmostEqual(result2, 5.0, places=1)

    def test_dated_fallback(self):
        html = (
            "<html><body>"
            "<div>Summary some text</div>"
            "<div>July 1, 2026 - July 30, 2026 Precipitation 1.8 in</div>"
            "<div>graph</div>"
            "</body></html>"
        )
        result = _parse_wu_monthly_precipitation(html, "2026-07-01", "2026-07-30")
        self.assertAlmostEqual(result, 1.8, places=1)

    def test_mixed_case_and_no_graph(self):
        html_lower = "<html><body>Summary precipitation 1.23 in</body></html>"
        result = _parse_wu_monthly_precipitation(html_lower, "2026-01-01", "2026-01-31")
        self.assertAlmostEqual(result, 1.23, places=1)

        html_node = "<html><body><div>Summary Precipitation 0.5 in end</div></body></html>"
        result2 = _parse_wu_monthly_precipitation(html_node, "2026-06-01", "2026-06-30")
        self.assertAlmostEqual(result2, 0.5, places=1)

    def test_no_match_and_invalid_range(self):
        self.assertIsNone(_parse_wu_monthly_precipitation(None, "2026-01-01", "2026-01-31"))
        self.assertIsNone(
            _parse_wu_monthly_precipitation("<html></html>", "2026-01-01", "2026-01-31")
        )
        self.assertIsNone(
            _parse_wu_monthly_precipitation(
                "<html><body>Summary unrelated content</body></html>", "2026-01-01", "2026-01-31"
            )
        )

        over = "<html><body>Summary Precipitation 50.0 in</body></html>"
        self.assertIsNone(_parse_wu_monthly_precipitation(over, "2026-01-01", "2026-01-31"))

        zero = "<html><body>Summary Precipitation 0.0 in</body></html>"
        self.assertAlmostEqual(
            _parse_wu_monthly_precipitation(zero, "2026-01-01", "2026-01-31"), 0.0, places=1
        )

    def test_both_source_merge(self):
        async def runner():
            ref = datetime(2026, 7, 15, 10, 0, 0)
            station_fetches = []

            async def mock_fetch_text(session, url, **kwargs):
                station_fetches.append(url)
                if "wunderground" in url:
                    return "<html><body>Summary July 1, 2026 - July 15, 2026 Precipitation 2.5 in</body></html>"
                return "<html><body>Normal 3.0 Current 4.1</body></html>"

            def mock_parse_climate(html, date):
                return {"avg_monthly_rainfall": 3.0, "current_monthly_rainfall": 4.1}

            with (
                mock.patch(
                    "daily_brief.sources.wunderground._fetch_text",
                    new=AsyncMock(side_effect=mock_fetch_text),
                ),
                mock.patch(
                    "daily_brief.sources.wunderground._parse_climate_summary", mock_parse_climate
                ),
            ):
                result = await _fetch_station_monthly_rainfall(None, ref)

            self.assertEqual(len(station_fetches), 2)
            self.assertIsNotNone(result["current_monthly_rainfall"])
            self.assertEqual(result["avg_monthly_rainfall"], "3.0")

        asyncio.get_event_loop().run_until_complete(runner())

    def test_station_missing(self):
        async def runner():
            ref = datetime(2026, 7, 15)

            async def mock_fetch_text(session, url, **kwargs):
                if "wunderground" in url:
                    return None
                return "<html><body>climate data</body></html>"

            def mock_parse_climate(html, date):
                return {"avg_monthly_rainfall": 2.0, "current_monthly_rainfall": 3.5}

            with (
                mock.patch(
                    "daily_brief.sources.wunderground._fetch_text",
                    new=AsyncMock(side_effect=mock_fetch_text),
                ),
                mock.patch(
                    "daily_brief.sources.wunderground._parse_climate_summary", mock_parse_climate
                ),
            ):
                result = await _fetch_station_monthly_rainfall(None, ref)

            self.assertEqual(result["current_monthly_rainfall"], "3.5")
            self.assertEqual(result["avg_monthly_rainfall"], "2.0")

        asyncio.get_event_loop().run_until_complete(runner())

    def test_climate_missing(self):
        async def runner():
            ref = datetime(2026, 3, 10)

            async def mock_fetch_text(session, url, **kwargs):
                if "wunderground" in url:
                    return "<html><body>Summary March 1, 2026 - March 10, 2026 Precipitation 1.2 in</body></html>"
                return None

            with mock.patch(
                "daily_brief.sources.wunderground._fetch_text",
                new=AsyncMock(side_effect=mock_fetch_text),
            ):
                result = await _fetch_station_monthly_rainfall(None, ref)

            self.assertIsNotNone(result["current_monthly_rainfall"])
            self.assertIsNone(result["avg_monthly_rainfall"])

        asyncio.get_event_loop().run_until_complete(runner())

    def test_out_of_range(self):
        async def runner():
            ref = datetime(2026, 7, 15)

            async def mock_fetch_text(session, url, **kwargs):
                if "wunderground" in url:
                    return None
                return "<html><body></body></html>"

            def mock_parse_climate(html, date):
                return {"avg_monthly_rainfall": 99.0, "current_monthly_rainfall": 50.0}

            with (
                mock.patch(
                    "daily_brief.sources.wunderground._fetch_text",
                    new=AsyncMock(side_effect=mock_fetch_text),
                ),
                mock.patch(
                    "daily_brief.sources.wunderground._parse_climate_summary", mock_parse_climate
                ),
            ):
                result = await _fetch_station_monthly_rainfall(None, ref)

            self.assertIsNone(result["avg_monthly_rainfall"])
            self.assertIsNone(result["current_monthly_rainfall"])

        asyncio.get_event_loop().run_until_complete(runner())

    def test_rainfall_fetches_concurrently(self):
        today = datetime(2026, 7, 15, 10, 0, 0)

        wunderground_entered = asyncio.Event()
        climate_entered = asyncio.Event()
        release = asyncio.Event()

        async def gated_wu(session, url, **kwargs):
            wunderground_entered.set()
            await release.wait()
            return "<html><body>Summary July 1, 2026 - July 15, 2026 Precipitation 2.5 in</body></html>"

        async def gated_climate(session, url, **kwargs):
            climate_entered.set()
            await release.wait()
            return "<html><body>climate data</body></html>"

        def mock_parse_climate(html, date):
            return {"avg_monthly_rainfall": 3.0, "current_monthly_rainfall": 4.1}

        async def run():
            async def url_route(session, url, **kwargs):
                if "wunderground" in url:
                    return await gated_wu(session, url)
                if "weather.gov" in url:
                    return await gated_climate(session, url)
                return None

            with (
                mock.patch(
                    "daily_brief.sources.wunderground._fetch_text",
                    new=AsyncMock(side_effect=url_route),
                ),
                mock.patch(
                    "daily_brief.sources.wunderground._parse_climate_summary", mock_parse_climate
                ),
            ):
                task = asyncio.create_task(_fetch_station_monthly_rainfall(None, today))
                await asyncio.wait_for(
                    asyncio.gather(
                        wunderground_entered.wait(),
                        climate_entered.wait(),
                    ),
                    timeout=1,
                )
                release.set()
                result = await task

            self.assertTrue(wunderground_entered.is_set())
            self.assertTrue(climate_entered.is_set())
            self.assertEqual(result["avg_monthly_rainfall"], "3.0")
            self.assertEqual(result["current_monthly_rainfall"], "2.5")

        asyncio.get_event_loop().run_until_complete(run())

    def test_retired_metrics_no_op(self):
        async def runner():
            ref = datetime(2026, 7, 15)
            result = await _fetch_station_metrics(None, "KTXMONTG645", ref)
            self.assertEqual(result["avg_temp_today"], None)
            self.assertEqual(result["avg_monthly_rainfall"], None)
            self.assertEqual(result["current_monthly_rainfall"], None)

            with mock.patch("daily_brief.sources.wunderground._fetch_text", mock.MagicMock()) as m:
                await _fetch_station_metrics(None, "KTXMONTG645", ref)
                m.assert_not_called()

        asyncio.get_event_loop().run_until_complete(runner())
