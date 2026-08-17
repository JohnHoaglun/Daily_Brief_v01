"""
Unit tests for daily_brief/sources/wunderground.py.
Wunderground station scraping, precipitation parsing, and metrics fetching.
"""

import asyncio
from datetime import datetime
from unittest import TestCase, mock
from unittest.mock import AsyncMock

from daily_brief.sources.wunderground import (
    _fetch_station_monthly_rainfall,
    _parse_wu_monthly_precipitation,
)


class TestParseWuMonthlyPrecipitation(TestCase):
    """Valid extraction, dated fallback, and no-match."""

    def test_valid_extraction(self):
        html = "<html><body><div>Summary Jul 1-30 Precipitation 3.45 in</div><div>graph</div></body></html>"
        result = _parse_wu_monthly_precipitation(html, "2026-07-01", "2026-07-30")
        self.assertAlmostEqual(result, 3.45, places=1)

        html2 = "<html><body><div>Summary Precipitation 5 in next</div></body></html>"
        result2 = _parse_wu_monthly_precipitation(html2, "2026-01-01", "2026-01-31")
        self.assertAlmostEqual(result2, 5.0, places=1)

    def test_dated_fallback(self):
        html = "<html><body><div>Summary July 1, 2026 - July 30, 2026 Precipitation 1.8 in</div></body></html>"
        result = _parse_wu_monthly_precipitation(html, "2026-07-01", "2026-07-30")
        self.assertAlmostEqual(result, 1.8, places=1)

    def test_no_match_and_null(self):
        self.assertIsNone(_parse_wu_monthly_precipitation(None, "2026-01-01", "2026-01-31"))
        self.assertIsNone(_parse_wu_monthly_precipitation("<html></html>", "2026-01-01", "2026-01-31"))
        self.assertIsNone(_parse_wu_monthly_precipitation("<html><body>unrelated</body></html>", "2026-01-01", "2026-01-31"))


class TestFetchStationMonthlyRainfall(TestCase):
    """Merge success, missing data fallback, and concurrency."""

    def test_both_sources_merge(self):
        ref = datetime(2026, 7, 15, 10, 0, 0)
        station_fetches = []

        async def mock_fetch_text(session, url, **kwargs):
            station_fetches.append(url)
            if "wunderground" in url:
                return "<html><body>Summary July 1, 2026 - July 15, 2026 Precipitation 2.5 in</body></html>"
            return "<html><body>Normal 3.0 Current 4.1</body></html>"

        with mock.patch("daily_brief.sources.wunderground._fetch_text", new=AsyncMock(side_effect=mock_fetch_text)):
            with mock.patch("daily_brief.sources.wunderground._parse_climate_summary", return_value={"avg_monthly_rainfall": 3.0, "current_monthly_rainfall": 4.1}):
                result = asyncio.get_event_loop().run_until_complete(
                    _fetch_station_monthly_rainfall(None, ref)
                )

        self.assertEqual(len(station_fetches), 2)
        self.assertEqual(result["avg_monthly_rainfall"], "3.0")
        self.assertEqual(result["current_monthly_rainfall"], "2.5")

    def test_wunderground_missing_climate_succeeds(self):
        ref = datetime(2026, 3, 10)

        async def mock_fetch_text(session, url, **kwargs):
            if "wunderground" in url:
                return "<html><body>Summary March 1, 2026 - March 10, 2026 Precipitation 1.2 in</body></html>"
            return None

        with mock.patch("daily_brief.sources.wunderground._fetch_text", new=AsyncMock(side_effect=mock_fetch_text)):
            result = asyncio.get_event_loop().run_until_complete(
                _fetch_station_monthly_rainfall(None, ref)
            )
            self.assertEqual(result["current_monthly_rainfall"], 1.2)
        self.assertEqual(result["avg_monthly_rainfall"], None)

    def test_both_sources_fail(self):
        ref = datetime(2026, 7, 15)

        async def mock_fetch_text(session, url, **kwargs):
            return None

        with mock.patch("daily_brief.sources.wunderground._fetch_text", new=AsyncMock(side_effect=mock_fetch_text)):
            result = asyncio.get_event_loop().run_until_complete(
                _fetch_station_monthly_rainfall(None, ref)
            )
        self.assertIsNone(result["avg_monthly_rainfall"])
        self.assertIsNone(result["current_monthly_rainfall"])

    def test_two_fetches_called(self):
        """Both wunderground and climate sources are called."""
        ref = datetime(2026, 7, 15, 10, 0, 0)
        called_urls = []

        async def capture_fetch(session, url, **kwargs):
            called_urls.append(url)
            if "wunderground" in url:
                return "<html><body>Summary Precipitation 2.5 in</body></html>"
            return "<html><body>climate data</body></html>"

        with mock.patch("daily_brief.sources.wunderground._fetch_text", new=AsyncMock(side_effect=capture_fetch)):
            with mock.patch("daily_brief.sources.wunderground._parse_climate_summary", return_value={"avg_monthly_rainfall": 3.0, "current_monthly_rainfall": 4.1}):
                result = asyncio.get_event_loop().run_until_complete(
                    _fetch_station_monthly_rainfall(None, ref)
                )

        self.assertEqual(len(called_urls), 2)
        self.assertEqual(result["current_monthly_rainfall"], "2.5")
