"""
Unit tests for src/daily_brief/sources/wunderground.py.
Wunderground station scraping, precipitation parsing, and metrics fetching.
"""
import asyncio
import os
import sys
from datetime import datetime
from unittest import TestCase, mock
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from daily_brief.sources.wunderground import (
    _parse_wu_monthly_precipitation,
    _fetch_station_monthly_rainfall,
    _fetch_station_metrics,
)


# ---------------------------------------------------------------------------
# 1. _parse_wu_monthly_precipitation — happy path
# ---------------------------------------------------------------------------

class TestParseWuMonthlyPrecipitationHappy(TestCase):
    """Correct precipitation extraction from WU monthly page."""

    def _html(self, body_fragment: str) -> str:
        return f"<html><body>{body_fragment}</body></html>"

    def test_basic_precipitation_extraction(self):
        """Precipitation value between Summary and graph."""
        html = self._html(
            "<div>Summary<div> July 1, 2026 - July 30, 2026 </div>"
            "<div>Precipitation 3.45 in</div>"
            "</div><div>graph</div>"
        )
        result = _parse_wu_monthly_precipitation(html, "2026-07-01", "2026-07-30")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 3.45, places=1)

    def test_precipitation_integer(self):
        """Integer precipitation value parsed correctly."""
        html = self._html(
            "<div>Summary Monthly data here. Precipitation 5 in next</div><div>graph</div>"
        )
        result = _parse_wu_monthly_precipitation(html, "2026-01-01", "2026-01-31")
        self.assertAlmostEqual(result, 5.0, places=1)

    def test_precipitation_with_degrees_symbol(self):
        """Degree symbol before 'in' handled."""
        html = self._html(
            "<div>Summary Precipitation 2.1° in data</div><div>graph</div>"
        )
        result = _parse_wu_monthly_precipitation(html, "2026-03-01", "2026-03-31")
        self.assertAlmostEqual(result, 2.1, places=1)

    def test_dates_in_candidate_no_dated_fallback(self):
        """When date labels are in the candidate, no dated fallback needed."""
        html = self._html(
            "<div>Summary July 1, 2026 - July 30, 2026 Precipitation 4.2 in</div><div>graph</div>"
        )
        result = _parse_wu_monthly_precipitation(html, "2026-07-01", "2026-07-30")
        self.assertAlmostEqual(result, 4.2, places=1)

    def test_dates_not_in_candidate_uses_dated_match(self):
        """When date labels are NOT in the Summary candidate, dated match works."""
        html = self._html(
            "<div>Summary some text</div>"
            "<div>July 1, 2026 - July 30, 2026 Precipitation 1.8 in</div>"
            "<div>graph</div>"
        )
        result = _parse_wu_monthly_precipitation(html, "2026-07-01", "2026-07-30")
        self.assertAlmostEqual(result, 1.8, places=1)

    def test_no_graph_anchor_uses_rest_of_text(self):
        """When no 'graph' text found, search remainder of text after Summary."""
        html = self._html(
            "<div>Summary Precipitation 0.5 in end</div>"
        )
        result = _parse_wu_monthly_precipitation(html, "2026-06-01", "2026-06-30")
        self.assertAlmostEqual(result, 0.5, places=1)


# ---------------------------------------------------------------------------
# 2. _parse_wu_monthly_precipitation — edge cases
# ---------------------------------------------------------------------------

class TestParseWuMonthlyPrecipitationEdgeCases(TestCase):
    """Boundary and error conditions for precipitation parsing."""

    def test_none_input(self):
        self.assertIsNone(_parse_wu_monthly_precipitation(None, "2026-01-01", "2026-01-31"))

    def test_empty_html(self):
        self.assertIsNone(_parse_wu_monthly_precipitation("<html></html>", "2026-01-01", "2026-01-31"))

    def test_no_summary_text(self):
        html = "<html><body>No summary section here</body></html>"
        self.assertIsNone(_parse_wu_monthly_precipitation(html, "2026-01-01", "2026-01-31"))

    def test_no_precipitation_match(self):
        html = "<html><body>Summary some unrelated content</body></html>"
        self.assertIsNone(_parse_wu_monthly_precipitation(html, "2026-01-01", "2026-01-31"))

    def test_value_exceeds_max_40(self):
        """Value over 40 is rejected."""
        html = "<html><body>Summary Precipitation 50.0 in</body></html>"
        self.assertIsNone(_parse_wu_monthly_precipitation(html, "2026-01-01", "2026-01-31"))

    def test_value_exactly_40_accepted(self):
        """Value at exactly 40.0 is accepted."""
        html = "<html><body>Summary Precipitation 40.0 in</body></html>"
        result = _parse_wu_monthly_precipitation(html, "2026-01-01", "2026-01-31")
        self.assertAlmostEqual(result, 40.0, places=1)

    def test_value_zero_accepted(self):
        """Value of 0.0 is accepted."""
        html = "<html><body>Summary Precipitation 0.0 in</body></html>"
        result = _parse_wu_monthly_precipitation(html, "2026-01-01", "2026-01-31")
        self.assertAlmostEqual(result, 0.0, places=1)

    def test_mixed_case_precipitation(self):
        """Case-insensitive matching for 'Precipitation'."""
        html = "<html><body>Summary precipitation 1.23 in</body></html>"
        result = _parse_wu_monthly_precipitation(html, "2026-01-01", "2026-01-31")
        self.assertAlmostEqual(result, 1.23, places=1)

    def test_precipitation_multiline(self):
        """DOTALL flag allows matching across newlines."""
        html = "<html><body>Summary\nPrecipitation 3.7 in</body></html>"
        result = _parse_wu_monthly_precipitation(html, "2026-02-01", "2026-02-28")
        self.assertAlmostEqual(result, 3.7, places=1)


# ---------------------------------------------------------------------------
# 3. _fetch_station_monthly_rainfall — async tests
# ---------------------------------------------------------------------------

class TestFetchStationMonthlyRainfall(TestCase):
    """Async station monthly rainfall fetching with mocks."""

    def test_happy_path_both_sources(self):
        async def runner():
            ref = datetime(2026, 7, 15, 10, 0, 0)
            station_fetches = []
            async def mock_fetch_text(session, url, **kwargs):
                station_fetches.append(url)
                if "wunderground" in url:
                    return "<html><body>Summary July 1, 2026 - July 15, 2026 Precipitation 2.5 in</body></html>"
                return (
                    "<html><body>Normal 3.0 Current 4.1</body></html>"
                )

            def mock_parse_climate(html, date):
                return {"avg_monthly_rainfall": 3.0, "current_monthly_rainfall": 4.1}

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new=AsyncMock(side_effect=mock_fetch_text)):
                with mock.patch("daily_brief.sources.wunderground._parse_climate_summary", mock_parse_climate):
                    result = await _fetch_station_monthly_rainfall(None, ref)

            self.assertEqual(len(station_fetches), 2)
            self.assertIsNotNone(result["current_monthly_rainfall"])
            self.assertEqual(result["avg_monthly_rainfall"], "3.0")

        asyncio.get_event_loop().run_until_complete(runner())

    def test_no_station_html(self):
        async def runner():
            ref = datetime(2026, 7, 15)
            fetch_count = [0]

            async def mock_fetch_text(session, url, **kwargs):
                fetch_count[0] += 1
                if fetch_count[0] == 1:
                    return None
                return "<html><body>climate data</body></html>"

            def mock_parse_climate(html, date):
                return {"avg_monthly_rainfall": 2.0, "current_monthly_rainfall": 3.5}

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new=AsyncMock(side_effect=mock_fetch_text)):
                with mock.patch("daily_brief.sources.wunderground._parse_climate_summary", mock_parse_climate):
                    result = await _fetch_station_monthly_rainfall(None, ref)

            self.assertEqual(result["current_monthly_rainfall"], "3.5")
            self.assertEqual(result["avg_monthly_rainfall"], "2.0")

        asyncio.get_event_loop().run_until_complete(runner())

    def test_no_climate_html_fallback(self):
        async def runner():
            ref = datetime(2026, 3, 10)
            fetch_count = [0]
            async def mock_fetch_text(session, url, **kwargs):
                fetch_count[0] += 1
                if fetch_count[0] == 1:
                    return "<html><body>Summary March 1, 2026 - March 10, 2026 Precipitation 1.2 in</body></html>"
                return None

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new=AsyncMock(side_effect=mock_fetch_text)):
                result = await _fetch_station_monthly_rainfall(None, ref)

            self.assertIsNotNone(result["current_monthly_rainfall"])
            self.assertIsNone(result["avg_monthly_rainfall"])

        asyncio.get_event_loop().run_until_complete(runner())

    def test_safe_rainfall_out_of_range(self):
        async def runner():
            ref = datetime(2026, 7, 15)
            fetch_count = [0]

            async def mock_fetch_text(session, url, **kwargs):
                fetch_count[0] += 1
                if fetch_count[0] == 1:
                    return None
                return "<html><body></body></html>"

            def mock_parse_climate(html, date):
                return {"avg_monthly_rainfall": 99.0, "current_monthly_rainfall": 50.0}

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new=AsyncMock(side_effect=mock_fetch_text)):
                with mock.patch("daily_brief.sources.wunderground._parse_climate_summary", mock_parse_climate):
                    result = await _fetch_station_monthly_rainfall(None, ref)

            self.assertIsNone(result["avg_monthly_rainfall"])
            self.assertIsNone(result["current_monthly_rainfall"])

        asyncio.get_event_loop().run_until_complete(runner())


# ---------------------------------------------------------------------------
# 4. _fetch_station_metrics — B.3 no-op regression
# ---------------------------------------------------------------------------

class TestFetchStationMetricsNoOp(TestCase):
    """B.3: _fetch_station_metrics is a no-op that returns the established empty payload shape."""

    def test_returns_empty_payload_shape(self):
        async def runner():
            ref = datetime(2026, 7, 15)
            result = await _fetch_station_metrics(None, "KTXMONTG645", ref)
            self.assertEqual(result["avg_temp_today"], None)
            self.assertEqual(result["avg_monthly_rainfall"], None)
            self.assertEqual(result["current_monthly_rainfall"], None)

        asyncio.get_event_loop().run_until_complete(runner())

    def test_does_not_fetch_text(self):
        """_fetch_text is not called — no dashboard HTTP request is made."""
        async def runner():
            ref = datetime(2026, 7, 15)
            with mock.patch("daily_brief.sources.wunderground._fetch_text", mock.MagicMock()) as mock_fetch:
                await _fetch_station_metrics(None, "KTXMONTG645", ref)
                mock_fetch.assert_not_called()

        asyncio.get_event_loop().run_until_complete(runner())
