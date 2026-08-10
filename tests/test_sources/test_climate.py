"""
Unit tests for daily_brief/sources/climate.py.
ERA5 climate normal fetch and climate.gov HTML summary parsing.
"""

import asyncio
from datetime import datetime, timezone
from unittest import TestCase, mock
from unittest.mock import AsyncMock

from daily_brief.sources.climate import (
    _fetch_climate_normal_high,
    _parse_climate_summary,
)

# ---------------------------------------------------------------------------
# 1. _fetch_climate_normal_high
# ---------------------------------------------------------------------------


class TestFetchClimateNormalHigh(TestCase):
    """Open-Meteo ERA5 climate normal high temperature fetch (no geocoding)."""

    def _era5_resp(self, temp=91.4):
        return {"daily": {"temperature_2m_max": [temp]}}

    async def _run(self, era5_result, lat=30.1, lon=-95.3):
        with mock.patch(
            "daily_brief.sources.climate._fetch_json", new=AsyncMock(return_value=era5_result)
        ):
            return await _fetch_climate_normal_high(mock.MagicMock(), lat, lon)

    def test_happy_path_rounds(self):
        async def run():
            return await self._run(self._era5_resp(91.4))

        self.assertEqual(asyncio.get_event_loop().run_until_complete(run()), 91)

        async def run2():
            return await self._run(self._era5_resp(88.2))

        self.assertEqual(asyncio.get_event_loop().run_until_complete(run2()), 88)

        async def run3():
            return await self._run(self._era5_resp(95.6))

        self.assertEqual(asyncio.get_event_loop().run_until_complete(run3()), 96)

    def test_no_data_and_fetch_failure(self):
        async def r1():
            return await self._run({"daily": {"temperature_2m_max": []}})

        self.assertIsNone(asyncio.get_event_loop().run_until_complete(r1()))

        async def r2():
            return await self._run({"other": True})

        self.assertIsNone(asyncio.get_event_loop().run_until_complete(r2()))

        async def r3():
            return await self._run(None)

        self.assertIsNone(asyncio.get_event_loop().run_until_complete(r3()))

        async def failing(*a, **k):
            raise ConnectionError("DNS failure")

        with mock.patch(
            "daily_brief.sources.climate._fetch_json", new=AsyncMock(side_effect=failing)
        ):
            result = asyncio.get_event_loop().run_until_complete(
                _fetch_climate_normal_high(mock.MagicMock(), 30.286, -95.566)
            )
        self.assertIsNone(result)

    def test_single_request_with_coordinates(self):
        urls = []

        async def capture(session, url, **k):
            urls.append(url)
            return self._era5_resp(85.0)

        with mock.patch(
            "daily_brief.sources.climate._fetch_json", new=AsyncMock(side_effect=capture)
        ):
            result = asyncio.get_event_loop().run_until_complete(
                _fetch_climate_normal_high(mock.MagicMock(), 30.286, -95.566)
            )
        self.assertEqual(len(urls), 1)
        self.assertIn("archive-api.open-meteo.com", urls[0])
        self.assertNotIn("geocoding", urls[0])
        self.assertEqual(result, 85)


# ---------------------------------------------------------------------------
# 2. _parse_climate_summary
# ---------------------------------------------------------------------------


class TestParseClimateSummary(TestCase):
    """climate.gov HGX summary HTML parsing."""

    def test_none_and_empty_input(self):
        result = _parse_climate_summary(None, datetime(2026, 7, 15, tzinfo=timezone.utc))
        self.assertIsNone(result["avg_monthly_rainfall"])
        self.assertIsNone(result["current_monthly_rainfall"])

        result2 = _parse_climate_summary("", datetime(2026, 7, 15, tzinfo=timezone.utc))
        self.assertIsNone(result2["avg_monthly_rainfall"])

    def test_has_keys_after_no_table(self):
        result = _parse_climate_summary(
            "<p>no tables</p>", datetime(2026, 7, 15, tzinfo=timezone.utc)
        )
        self.assertIn("avg_monthly_rainfall", result)
        self.assertIn("current_monthly_rainfall", result)

    def test_normal_rain_parse_two_positions(self):
        html = """
        <table>
          <tr><th> </th><th>Jan</th><th>Feb</th><th>Mar</th><th>Apr</th>
              <th>May</th><th>Jun</th><th>Jul</th><th>Aug</th><th>Sep</th>
              <th>Oct</th><th>Nov</th><th>Dec</th></tr>
          <tr><td>Rain Totals (in)</td><td>3.1</td><td>2.8</td><td>2.9</td><td>4.0</td>
              <td>5.2</td><td>5.8</td><td>6.4</td><td>5.1</td><td>4.0</td>
              <td>4.5</td><td>3.2</td><td>2.6</td></tr>
        </table>
        """
        r = _parse_climate_summary(html, datetime(2026, 7, 15, tzinfo=timezone.utc))
        self.assertEqual(r["avg_monthly_rainfall"], 6.4)
        r2 = _parse_climate_summary(html, datetime(2026, 1, 15, tzinfo=timezone.utc))
        self.assertEqual(r2["avg_monthly_rainfall"], 3.1)

    def test_invalid_safe_nulls(self):
        html = """
        <table>
          <tr><th> </th><th>Jan</th><th>Feb</th><th>Mar</th><th>Apr</th>
              <th>May</th><th>Jun</th><th>Jul</th><th>Aug</th><th>Sep</th>
              <th>Oct</th><th>Nov</th><th>Dec</th></tr>
          <tr><td>Rain Totals (in)</td><td>3.1</td><td>2.8</td><td>2.9</td><td>4.0</td>
              <td>5.2</td><td>5.8</td><td>50.0</td><td>5.1</td><td>4.0</td>
              <td>4.5</td><td>3.2</td><td>2.6</td></tr>
        </table>
        """
        result = _parse_climate_summary(html, datetime(2026, 7, 15, tzinfo=timezone.utc))
        self.assertIsNone(result["avg_monthly_rainfall"])
        self.assertIsNone(
            _parse_climate_summary(
                "<table><tr><td>not a normals table</td></tr></table>",
                datetime(2026, 7, 15, tzinfo=timezone.utc),
            )["avg_monthly_rainfall"]
        )

    def test_header_row_before_rain_row(self):
        html = """
        <table>
          <tr><td>Some info</td></tr>
          <tr><th> </th><th>Jan</th><th>Feb</th><th>Mar</th><th>Apr</th>
              <th>May</th><th>Jun</th><th>Jul</th><th>Aug</th><th>Sep</th>
              <th>Oct</th><th>Nov</th><th>Dec</th></tr>
          <tr><td>Rain Totals (in)</td><td>3.1</td><td>2.8</td><td>2.9</td><td>4.0</td>
              <td>5.2</td><td>5.8</td><td>6.4</td><td>5.1</td><td>4.0</td>
              <td>4.5</td><td>3.2</td><td>2.6</td></tr>
        </table>
        """
        result = _parse_climate_summary(html, datetime(2026, 7, 15, tzinfo=timezone.utc))
        self.assertEqual(result["avg_monthly_rainfall"], 6.4)
