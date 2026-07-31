"""
Unit tests for src/daily_brief/sources/wunderground.py.
Wunderground station scraping, precipitation parsing, and metrics fetching.
"""
import asyncio
import os
import sys
from datetime import datetime
from unittest import TestCase, mock

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

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new_callable=lambda: asyncio.coroutine(mock.MagicMock(side_effect=mock_fetch_text))):
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

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new_callable=lambda: asyncio.coroutine(mock.MagicMock(side_effect=mock_fetch_text))):
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

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new_callable=lambda: asyncio.coroutine(mock.MagicMock(side_effect=mock_fetch_text))):
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

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new_callable=lambda: asyncio.coroutine(mock.MagicMock(side_effect=mock_fetch_text))):
                with mock.patch("daily_brief.sources.wunderground._parse_climate_summary", mock_parse_climate):
                    result = await _fetch_station_monthly_rainfall(None, ref)

            self.assertIsNone(result["avg_monthly_rainfall"])
            self.assertIsNone(result["current_monthly_rainfall"])

        asyncio.get_event_loop().run_until_complete(runner())


# ---------------------------------------------------------------------------
# 4. _fetch_station_metrics — async tests
# ---------------------------------------------------------------------------

class TestFetchStationMetrics(TestCase):
    """Async station metrics fetching from WU dashboard tables."""

    def test_happy_path_precipitation_row(self):
        async def runner():
            ref = datetime(2026, 7, 15, 12, 0, 0)
            html = """
            <html><body>
            <table>
                <tr><td>Precipitation</td><td>3.45</td><td>in</td><td>normal</td></tr>
                <tr><td>Temperature</td><td>90</td><td>F</td><td>max</td></tr>
            </table>
            </body></html>
            """

            async def mock_fetch_text(session, url, **kwargs):
                return html

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new_callable=lambda: asyncio.coroutine(mock.MagicMock(side_effect=mock_fetch_text))):
                result = await _fetch_station_metrics(None, "KTXMONTG645", ref)

            self.assertEqual(result["current_monthly_rainfall"], "3.45 Inches")
            self.assertIsNone(result["avg_temp_today"])

        asyncio.get_event_loop().run_until_complete(runner())

    def test_rain_keyword_match(self):
        async def runner():
            ref = datetime(2026, 7, 15)
            html = """
            <html><body>
            <table>
                <tr><td>Rain</td><td>1.2</td><td>in</td><td>x</td></tr>
            </table>
            </body></html>
            """

            async def mock_fetch_text(session, url, **kwargs):
                return html

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new_callable=lambda: asyncio.coroutine(mock.MagicMock(side_effect=mock_fetch_text))):
                result = await _fetch_station_metrics(None, "TEST123", ref)

            self.assertEqual(result["current_monthly_rainfall"], "1.2 Inches")

        asyncio.get_event_loop().run_until_complete(runner())

    def test_no_html_returns_empty_payload(self):
        async def runner():
            ref = datetime(2026, 7, 15)

            async def mock_fetch_text(session, url, **kwargs):
                return None

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new_callable=lambda: asyncio.coroutine(mock.MagicMock(side_effect=mock_fetch_text))):
                result = await _fetch_station_metrics(None, "KTXMONTG645", ref)

            self.assertIsNone(result["avg_temp_today"])
            self.assertIsNone(result["avg_monthly_rainfall"])
            self.assertIsNone(result["current_monthly_rainfall"])

        asyncio.get_event_loop().run_until_complete(runner())

    def test_no_precipitation_row(self):
        async def runner():
            ref = datetime(2026, 7, 15)
            html = """
            <html><body>
            <table>
                <tr><td>Temperature</td><td>90</td><td>F</td><td>max</td></tr>
                <tr><td>Humidity</td><td>65</td><td>%</td><td>avg</td></tr>
            </table>
            </body></html>
            """

            async def mock_fetch_text(session, url, **kwargs):
                return html

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new_callable=lambda: asyncio.coroutine(mock.MagicMock(side_effect=mock_fetch_text))):
                result = await _fetch_station_metrics(None, "KTXMONTG645", ref)

            self.assertIsNone(result["current_monthly_rainfall"])

        asyncio.get_event_loop().run_until_complete(runner())

    def test_precipitation_value_exceeds_60(self):
        async def runner():
            ref = datetime(2026, 7, 15)
            html = """
            <html><body>
            <table>
                <tr><td>Precipitation</td><td>75.0</td><td>in</td><td>x</td></tr>
            </table>
            </body></html>
            """

            async def mock_fetch_text(session, url, **kwargs):
                return html

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new_callable=lambda: asyncio.coroutine(mock.MagicMock(side_effect=mock_fetch_text))):
                result = await _fetch_station_metrics(None, "KTXMONTG645", ref)

            self.assertIsNone(result["current_monthly_rainfall"])

        asyncio.get_event_loop().run_until_complete(runner())

    def test_row_fewer_than_4_cols_skipped(self):
        async def runner():
            ref = datetime(2026, 7, 15)
            html = """
            <html><body>
            <table>
                <tr><td>Precipitation</td><td>2.0</td></tr>
            </table>
            </body></html>
            """

            async def mock_fetch_text(session, url, **kwargs):
                return html

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new_callable=lambda: asyncio.coroutine(mock.MagicMock(side_effect=mock_fetch_text))):
                result = await _fetch_station_metrics(None, "KTXMONTG645", ref)

            self.assertIsNone(result["current_monthly_rainfall"])

        asyncio.get_event_loop().run_until_complete(runner())

    def test_no_number_in_value_cell(self):
        async def runner():
            ref = datetime(2026, 7, 15)
            html = """
            <html><body>
            <table>
                <tr><td>Precipitation</td><td>N/A</td><td>in</td><td>x</td></tr>
            </table>
            </body></html>
            """

            async def mock_fetch_text(session, url, **kwargs):
                return html

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new_callable=lambda: asyncio.coroutine(mock.MagicMock(side_effect=mock_fetch_text))):
                result = await _fetch_station_metrics(None, "KTXMONTG645", ref)

            self.assertIsNone(result["current_monthly_rainfall"])

        asyncio.get_event_loop().run_until_complete(runner())

    def test_multiple_tables_stops_at_first_match(self):
        async def runner():
            ref = datetime(2026, 7, 15)
            html = """
            <html><body>
            <table>
                <tr><td>Precipitation</td><td>1.5</td><td>in</td><td>x</td></tr>
            </table>
            <table>
                <tr><td>Precipitation</td><td>99.9</td><td>in</td><td>x</td></tr>
            </table>
            </body></html>
            """

            async def mock_fetch_text(session, url, **kwargs):
                return html

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new_callable=lambda: asyncio.coroutine(mock.MagicMock(side_effect=mock_fetch_text))):
                result = await _fetch_station_metrics(None, "KTXMONTG645", ref)

            self.assertEqual(result["current_monthly_rainfall"], "1.5 Inches")

        asyncio.get_event_loop().run_until_complete(runner())

    def test_url_constructed_from_station_id_and_date(self):
        async def runner():
            ref = datetime(2026, 7, 20)
            captured_urls = []

            async def mock_fetch_text(session, url, **kwargs):
                captured_urls.append(url)
                return "<html><body><table><tr><td>Precipitation</td><td>1.0</td><td>in</td><td>x</td></tr></table></body></html>"

            with mock.patch("daily_brief.sources.wunderground._fetch_text", new_callable=lambda: asyncio.coroutine(mock.MagicMock(side_effect=mock_fetch_text))):
                await _fetch_station_metrics(None, "KTEST", ref)

            self.assertEqual(len(captured_urls), 1)
            self.assertIn("KTEST", captured_urls[0])
            self.assertIn("2026-07-20", captured_urls[0])

        asyncio.get_event_loop().run_until_complete(runner())
