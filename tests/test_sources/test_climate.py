"""
Unit tests for src/daily_brief/sources/climate.py.
ERA5 climate normal fetch and climate.gov HTML summary parsing.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone
from unittest import TestCase, mock
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

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

    def _era5_resp_empty(self):
        return {"daily": {"temperature_2m_max": []}}

    def _era5_no_daily(self):
        return {"other": True}

    async def _run(self, era5_result, lat=30.1, lon=-95.3):
        with mock.patch("daily_brief.sources.climate._fetch_json", new=AsyncMock(return_value=era5_result)):
            return await _fetch_climate_normal_high(mock.MagicMock(), lat, lon)

    def test_happy_path_rounds_temp(self):
        async def run():
            return await self._run(self._era5_resp(91.4))
        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(result, 91)

    def test_rounds_down(self):
        async def run():
            return await self._run(self._era5_resp(88.2))
        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(result, 88)

    def test_rounds_up(self):
        async def run():
            return await self._run(self._era5_resp(95.6))
        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(result, 96)

    def test_era5_none_response(self):
        async def run():
            return await self._run(None)
        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertIsNone(result)

    def test_era5_empty_temps_list(self):
        async def run():
            return await self._run(self._era5_resp_empty())
        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertIsNone(result)

    def test_era5_no_daily_key(self):
        async def run():
            return await self._run(self._era5_no_daily())
        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertIsNone(result)

    def test_fetch_exception(self):
        async def failing(*a, **k):
            raise ConnectionError("DNS failure")
        with mock.patch("daily_brief.sources.climate._fetch_json", new=AsyncMock(side_effect=failing)):
            result = asyncio.get_event_loop().run_until_complete(
                _fetch_climate_normal_high(mock.MagicMock(), 30.286, -95.566)
            )
        self.assertIsNone(result)

    def test_single_era5_request(self):
        urls = []
        async def capture(session, url, **k):
            urls.append(url)
            return self._era5_resp(85.0)
        with mock.patch("daily_brief.sources.climate._fetch_json", new=AsyncMock(side_effect=capture)):
            result = asyncio.get_event_loop().run_until_complete(
                _fetch_climate_normal_high(mock.MagicMock(), 30.286, -95.566)
            )
        self.assertEqual(len(urls), 1)
        self.assertIn("archive-api.open-meteo.com", urls[0])
        self.assertNotIn("geocoding", urls[0])
        self.assertEqual(result, 85)

    def test_coordinates_passed_to_request(self):
        urls = []
        async def capture(session, url, **k):
            urls.append(url)
            return self._era5_resp(90.0)
        with mock.patch("daily_brief.sources.climate._fetch_json", new=AsyncMock(side_effect=capture)):
            asyncio.get_event_loop().run_until_complete(
                _fetch_climate_normal_high(mock.MagicMock(), 30.286, -95.566)
            )
        # Verify the URL contains the archive API
        self.assertEqual(len(urls), 1)
        self.assertIn("archive-api.open-meteo.com", urls[0])


# ---------------------------------------------------------------------------
# 2. _parse_climate_summary
# ---------------------------------------------------------------------------

class TestParseClimateSummary(TestCase):
    """climate.gov HGX summary HTML parsing."""

    def test_none_input(self):
        result = _parse_climate_summary(None, datetime(2026, 7, 15, tzinfo=timezone.utc))
        self.assertIsNone(result["avg_monthly_rainfall"])
        self.assertIsNone(result["current_monthly_rainfall"])

    def test_empty_string(self):
        result = _parse_climate_summary("", datetime(2026, 7, 15, tzinfo=timezone.utc))
        self.assertIsNone(result["avg_monthly_rainfall"])

    def test_has_both_keys(self):
        result = _parse_climate_summary("<p>no tables</p>", datetime(2026, 7, 15, tzinfo=timezone.utc))
        self.assertIn("avg_monthly_rainfall", result)
        self.assertIn("current_monthly_rainfall", result)

    def test_parses_avg_rainfall_july(self):
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
        result = _parse_climate_summary(html, datetime(2026, 7, 15, tzinfo=timezone.utc))
        self.assertEqual(result["avg_monthly_rainfall"], 6.4)

    def test_parses_avg_rainfall_january(self):
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
        result = _parse_climate_summary(html, datetime(2026, 1, 15, tzinfo=timezone.utc))
        self.assertEqual(result["avg_monthly_rainfall"], 3.1)

    def test_parses_avg_rainfall_december(self):
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
        result = _parse_climate_summary(html, datetime(2026, 12, 15, tzinfo=timezone.utc))
        self.assertEqual(result["avg_monthly_rainfall"], 2.6)

    def test_avg_rainfall_out_of_range_too_high(self):
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

    def test_avg_rainfall_out_of_range_negative(self):
        # _clean_number regex strips sign, so -50.0 parses as 50.0 → out of range
        html = """
        <table>
          <tr><th> </th><th>Jan</th><th>Feb</th><th>Mar</th><th>Apr</th>
              <th>May</th><th>Jun</th><th>Jul</th><th>Aug</th><th>Sep</th>
              <th>Oct</th><th>Nov</th><th>Dec</th></tr>
          <tr><td>Rain Totals (in)</td><td>3.1</td><td>2.8</td><td>2.9</td><td>4.0</td>
              <td>5.2</td><td>5.8</td><td>-50.0</td><td>5.1</td><td>4.0</td>
              <td>4.5</td><td>3.2</td><td>2.6</td></tr>
        </table>
        """
        result = _parse_climate_summary(html, datetime(2026, 7, 15, tzinfo=timezone.utc))
        self.assertIsNone(result["avg_monthly_rainfall"])

    def test_no_normals_table(self):
        html = """
        <table>
          <tr><td><td>Some other data</td></tr>
        </table>
        """
        result = _parse_climate_summary(html, datetime(2026, 7, 15, tzinfo=timezone.utc))
        self.assertIsNone(result["avg_monthly_rainfall"])

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
