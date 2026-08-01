"""
Unit tests for src/daily_brief/sources/weather.py.
NWS forecast JSON parsing, date extraction, label generation, and fetch orchestration.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest import TestCase, mock
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import aiohttp

from daily_brief.sources.weather import (
    _parse_date_for_weather,
    get_weather_label_for_offset,
    get_reference_datetime,
    fetch_weather,
)


CHICTZ = ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# 1. _parse_date_for_weather
# ---------------------------------------------------------------------------

class TestParseDateForWeather(TestCase):
    """NWS forecast date string parsing."""

    def test_iso_format_with_z(self):
        result = _parse_date_for_weather("2026-07-18T12:00:00Z")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 7)
        self.assertEqual(result.day, 18)

    def test_strptime_format_with_tz(self):
        result = _parse_date_for_weather("2026-07-18T14:30:00+0000")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)

    def test_strptime_format_no_tz(self):
        result = _parse_date_for_weather("2026-07-18T08:00:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.tzinfo, CHICTZ)

    def test_bracket_tz_format(self):
        result = _parse_date_for_weather("2026-07-18T20:00:00-05:00[America/Chicago]")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)

    def test_none_input(self):
        self.assertIsNone(_parse_date_for_weather(None))

    def test_empty_string(self):
        self.assertIsNone(_parse_date_for_weather(""))

    def test_garbage_string(self):
        self.assertIsNone(_parse_date_for_weather("not-a-date"))


# ---------------------------------------------------------------------------
# 2. get_weather_label_for_offset
# ---------------------------------------------------------------------------

class TestGetWeatherLabelForOffset(TestCase):
    """Weather label generation for forecast offsets."""

    def _ref(self, year=2026, month=7, day=18):
        return datetime(year, month, day, 10, 0, 0, tzinfo=CHICTZ)

    def test_offset_zero(self):
        self.assertEqual(get_weather_label_for_offset(self._ref(), 0), "Today")

    def test_offset_one(self):
        self.assertEqual(get_weather_label_for_offset(self._ref(), 1), "Tonight")

    def test_offset_two(self):
        label = get_weather_label_for_offset(self._ref(), 2)
        target = (self._ref().date() + timedelta(days=2)).strftime("%A")
        self.assertEqual(label, target)

    def test_offset_three(self):
        label = get_weather_label_for_offset(self._ref(), 3)
        target = (self._ref().date() + timedelta(days=3)).strftime("%A")
        self.assertEqual(label, target)

    def test_negative_offset(self):
        label = get_weather_label_for_offset(self._ref(), -1)
        target = (self._ref().date() + timedelta(days=-1)).strftime("%A")
        self.assertEqual(label, target)


# ---------------------------------------------------------------------------
# 3. get_reference_datetime
# ---------------------------------------------------------------------------

class TestGetReferenceDatetime(TestCase):
    """Reference datetime with optional override."""

    def test_returns_datetime_with_tz(self):
        dt = get_reference_datetime()
        self.assertIsNotNone(dt.tzinfo)

    def test_date_override_iso_string(self):
        with mock.patch("daily_brief.sources.weather.DATE_OVERRIDE", "2026-01-15T10:00:00"):
            dt = get_reference_datetime()
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 15)

    def test_date_override_with_tz(self):
        with mock.patch("daily_brief.sources.weather.DATE_OVERRIDE", "2026-06-01T08:00:00+00:00"):
            dt = get_reference_datetime()
        self.assertEqual(dt.year, 2026)

    def test_date_override_invalid_fallback(self):
        with mock.patch("daily_brief.sources.weather.DATE_OVERRIDE", "bad-value"):
            dt = get_reference_datetime()
        self.assertIsNotNone(dt)


# ---------------------------------------------------------------------------
# 4. fetch_weather — happy path & parsing
# ---------------------------------------------------------------------------

def _make_forecast(today, tomorrow):
    """Build an NWS-style forecast JSON with day+night periods."""
    return {
        "properties": {
            "periods": [
                {
                    "number": 1,
                    "name": "Saturday",
                    "startTime": (today + timedelta(hours=6)).isoformat(),
                    "endTime": (today + timedelta(hours=18)).isoformat(),
                    "isDaytime": True,
                    "temperature": 92,
                    "temperatureUnit": "F",
                    "shortForecast": "Sunny and Hot",
                    "windSpeed": "10 mph",
                    "windDirection": "S",
                    "probabilityOfPrecipitation": {"value": 10},
                },
                {
                    "number": 2,
                    "name": "Saturday Night",
                    "startTime": (today + timedelta(hours=18)).isoformat(),
                    "endTime": (tomorrow + timedelta(hours=6)).isoformat(),
                    "isDaytime": False,
                    "temperature": 78,
                    "temperatureUnit": "F",
                    "shortForecast": "Mostly Clear",
                    "windSpeed": "5 mph",
                    "windDirection": "SE",
                    "probabilityOfPrecipitation": {"value": 5},
                },
                {
                    "number": 3,
                    "name": "Sunday",
                    "startTime": (tomorrow + timedelta(hours=6)).isoformat(),
                    "endTime": (tomorrow + timedelta(hours=18)).isoformat(),
                    "isDaytime": True,
                    "temperature": 90,
                    "temperatureUnit": "F",
                    "shortForecast": "Partly Sunny",
                    "windSpeed": "8 mph",
                    "windDirection": "S",
                    "probabilityOfPrecipitation": {"value": 30},
                },
                {
                    "number": 4,
                    "name": "Sunday Night",
                    "startTime": (tomorrow + timedelta(hours=18)).isoformat(),
                    "endTime": (tomorrow + timedelta(days=1, hours=6)).isoformat(),
                    "isDaytime": False,
                    "temperature": 76,
                    "temperatureUnit": "F",
                    "shortForecast": "Partly Cloudy",
                    "windSpeed": "6 mph",
                    "windDirection": "S",
                    "probabilityOfPrecipitation": {"value": 25},
                },
                {
                    "number": 5,
                    "name": "Monday",
                    "startTime": (tomorrow + timedelta(days=1, hours=6)).isoformat(),
                    "endTime": (tomorrow + timedelta(days=1, hours=18)).isoformat(),
                    "isDaytime": True,
                    "temperature": 95,
                    "temperatureUnit": "F",
                    "shortForecast": "Hot",
                    "windSpeed": "12 mph",
                    "windDirection": "SW",
                    "probabilityOfPrecipitation": {"value": 0},
                },
                {
                    "number": 6,
                    "name": "Monday Night",
                    "startTime": (tomorrow + timedelta(days=1, hours=18)).isoformat(),
                    "endTime": (tomorrow + timedelta(days=2, hours=6)).isoformat(),
                    "isDaytime": False,
                    "temperature": 80,
                    "temperatureUnit": "F",
                    "shortForecast": "Clear",
                    "windSpeed": "7 mph",
                    "windDirection": "W",
                    "probabilityOfPrecipitation": {"value": 0},
                },
            ]
        }
    }


class TestFetchWeatherHappyPath(TestCase):
    """fetch_weather successful NWS forecast parsing."""

    def setUp(self):
        self.today = datetime(2026, 7, 18, tzinfo=CHICTZ)
        self.tomorrow = self.today + timedelta(days=1)
        self.point_url = "https://api.weather.gov/points/30.286,-95.566"
        self.forecast_url = "https://api.weather.gov/grid/.../forecast"

    async def _run(self, point_resp, forecast_resp):
        mock_fetch_json = asyncio.coroutine(
            mock.MagicMock(side_effect=[point_resp, forecast_resp])
        )
        with mock.patch("daily_brief.sources.weather._fetch_json", mock_fetch_json):
            with mock.patch("daily_brief.sources.weather.get_reference_datetime", return_value=self.today):
                with mock.patch("daily_brief.sources.weather._fetch_climate_normal_high", new_callable=lambda: asyncio.coroutine(mock.MagicMock(return_value=91))):
                    with mock.patch("daily_brief.sources.weather._fetch_station_monthly_rainfall", new_callable=lambda: asyncio.coroutine(mock.MagicMock(return_value={"avg_monthly_rainfall": 3.2, "current_monthly_rainfall": 2.1}))):
                        with mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
                            return await fetch_weather(None, 30.286, -95.566)

    def test_full_happy_path(self):
        point = {"properties": {"forecast": self.forecast_url}}
        forecast = _make_forecast(self.today, self.tomorrow)
        result = asyncio.get_event_loop().run_until_complete(self._run(point, forecast))
        self.assertEqual(len(result["forecast"]), 3)
        self.assertEqual(result["forecast"][0]["date"], "Today")
        self.assertEqual(result["forecast"][1]["date"], "Tonight")
        self.assertIn("Sunny", result["forecast"][0]["day"])
        self.assertIn("Mostly", result["forecast"][0]["night"])

    def test_high_temperature_format(self):
        point = {"properties": {"forecast": self.forecast_url}}
        forecast = _make_forecast(self.today, self.tomorrow)
        result = asyncio.get_event_loop().run_until_complete(self._run(point, forecast))
        self.assertIn("92\u00b0F", result["forecast"][0]["high"])

    def test_low_temperature_format(self):
        point = {"properties": {"forecast": self.forecast_url}}
        forecast = _make_forecast(self.today, self.tomorrow)
        result = asyncio.get_event_loop().run_until_complete(self._run(point, forecast))
        self.assertIn("78\u00b0F", result["forecast"][0]["low"])

    def test_precipitation_percent_format(self):
        point = {"properties": {"forecast": self.forecast_url}}
        forecast = _make_forecast(self.today, self.tomorrow)
        result = asyncio.get_event_loop().run_until_complete(self._run(point, forecast))
        self.assertIn("%", result["forecast"][0]["precip"])

    def test_wind_speed_and_direction_combined(self):
        point = {"properties": {"forecast": self.forecast_url}}
        forecast = _make_forecast(self.today, self.tomorrow)
        result = asyncio.get_event_loop().run_until_complete(self._run(point, forecast))
        self.assertIn("10", result["forecast"][0]["wind"])
        self.assertIn("S", result["forecast"][0]["wind"])

    def test_climate_normal_high_added(self):
        point = {"properties": {"forecast": self.forecast_url}}
        forecast = _make_forecast(self.today, self.tomorrow)
        result = asyncio.get_event_loop().run_until_complete(self._run(point, forecast))
        station = result["station"]
        self.assertIn("91", station["avg_temp_today"])

    def test_monthly_rainfall_populated(self):
        point = {"properties": {"forecast": self.forecast_url}}
        forecast = _make_forecast(self.today, self.tomorrow)
        result = asyncio.get_event_loop().run_until_complete(self._run(point, forecast))
        station = result["station"]
        self.assertIsNotNone(station["avg_monthly_rainfall"])
        self.assertIsNotNone(station["current_monthly_rainfall"])


# ---------------------------------------------------------------------------
# 5. fetch_weather — edge cases
# ---------------------------------------------------------------------------

class TestFetchWeatherEdgeCases(TestCase):
    """fetch_weather error handling and boundary conditions."""

    def setUp(self):
        self.today = datetime(2026, 7, 18, tzinfo=CHICTZ)
        self.forecast_url = "https://api.weather.gov/grid/.../forecast"

    async def _run(self, point_resp, forecast_resp):
        mock_fetch_json = asyncio.coroutine(
            mock.MagicMock(side_effect=[point_resp, forecast_resp])
        )
        with mock.patch("daily_brief.sources.weather._fetch_json", mock_fetch_json):
            with mock.patch("daily_brief.sources.weather.get_reference_datetime", return_value=self.today):
                with mock.patch("daily_brief.sources.weather._fetch_climate_normal_high", new_callable=lambda: asyncio.coroutine(mock.MagicMock(return_value=None))):
                    with mock.patch("daily_brief.sources.weather._fetch_station_monthly_rainfall", new_callable=lambda: asyncio.coroutine(mock.MagicMock(return_value={"avg_monthly_rainfall": None, "current_monthly_rainfall": None}))):
                        with mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
                            return await fetch_weather(None, 30.286, -95.566)

    def test_point_missing_properties(self):
        point = {"not_properties": True}
        result = asyncio.get_event_loop().run_until_complete(self._run(point, None))
        self.assertEqual(len(result["forecast"]), 0)

    def test_empty_periods(self):
        point = {"properties": {"forecast": self.forecast_url}}
        forecast = {"properties": {"periods": []}}
        result = asyncio.get_event_loop().run_until_complete(self._run(point, forecast))
        self.assertEqual(len(result["forecast"]), 3)

    def test_empty_periods_dynamic_fallback(self):
        point = {"properties": {"forecast": self.forecast_url}}
        forecast = {"properties": {"periods": []}}
        result = asyncio.get_event_loop().run_until_complete(self._run(point, forecast))
        self.assertEqual(result["forecast"][0]["high"], "Dynamic")

    def test_forecast_periods_none(self):
        point = {"properties": {"forecast": self.forecast_url}}
        forecast = {"properties": {"periods": None}}
        result = asyncio.get_event_loop().run_until_complete(self._run(point, forecast))
        self.assertEqual(len(result["forecast"]), 3)

    def test_missing_temperature_keys(self):
        point = {"properties": {"forecast": self.forecast_url}}
        forecast = {"properties": {"periods": [
            {"number": 1, "isDaytime": True, "startTime": self.today.isoformat(), "shortForecast": "Clear"},
            {"number": 2, "isDaytime": False, "startTime": self.today.isoformat(), "shortForecast": "Clear"},
            {"number": 3, "isDaytime": True, "startTime": (self.today + timedelta(days=1)).isoformat()},
            {"number": 4, "isDaytime": False, "startTime": (self.today + timedelta(days=1)).isoformat()},
            {"number": 5, "isDaytime": True, "startTime": (self.today + timedelta(days=2)).isoformat()},
            {"number": 6, "isDaytime": False, "startTime": (self.today + timedelta(days=2)).isoformat()},
        ]}}
        result = asyncio.get_event_loop().run_until_complete(self._run(point, forecast))
        self.assertEqual(len(result["forecast"]), 3)

    def test_station_unavailable_fallback(self):
        point = {"properties": {"forecast": self.forecast_url}}
        forecast = {"properties": {"periods": []}}
        result = asyncio.get_event_loop().run_until_complete(self._run(point, forecast))
        station = result["station"]
        self.assertEqual(station["avg_temp_today"], "Unavailable")
        self.assertEqual(station["avg_monthly_rainfall"], "Unavailable")
        self.assertEqual(station["current_monthly_rainfall"], "Unavailable")

    def test_http_error_returns_empty(self):
        point = {"properties": {"forecast": self.forecast_url}}
        async def side_effect(url, **kwargs):
            return None
        mock_fn = asyncio.coroutine(mock.MagicMock(side_effect=side_effect))
        with mock.patch("daily_brief.sources.weather._fetch_json", mock_fn):
            with mock.patch("daily_brief.sources.weather.get_reference_datetime", return_value=self.today):
                with mock.patch("daily_brief.sources.weather._fetch_climate_normal_high", new_callable=lambda: asyncio.coroutine(mock.MagicMock(return_value=None))):
                    with mock.patch("daily_brief.sources.weather._fetch_station_monthly_rainfall", new_callable=lambda: asyncio.coroutine(mock.MagicMock(return_value={"avg_monthly_rainfall": None, "current_monthly_rainfall": None}))):
                        with mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
                            result = asyncio.get_event_loop().run_until_complete(fetch_weather(None, 30.286, -95.566))
        self.assertEqual(len(result["forecast"]), 0)

    def test_exception_during_fetch(self):
        async def side_effect(*a, **k):
            raise ConnectionError("DNS failure")
        mock_fetch = asyncio.coroutine(mock.MagicMock(side_effect=side_effect))
        with mock.patch("daily_brief.sources.weather._fetch_json", mock_fetch):
            with mock.patch("daily_brief.sources.weather.get_reference_datetime", return_value=self.today):
                with mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
                    result = asyncio.get_event_loop().run_until_complete(fetch_weather(None, 30.286, -95.566))
        self.assertEqual(len(result["forecast"]), 0)
        self.assertIn("DNS failure", result["errors"][0])

    def test_point_url_constructed_from_lat_lon(self):
        calls = []
        original = "daily_brief.sources.weather._fetch_json"
        async def capture(session, url, **k):
            calls.append(url)
            return {"properties": {"forecast": self.forecast_url}}
        mock_fn = asyncio.coroutine(mock.MagicMock(side_effect=capture))
        with mock.patch(original, mock_fn):
            with mock.patch("daily_brief.sources.weather.get_reference_datetime", return_value=self.today):
                with mock.patch("daily_brief.sources.weather._fetch_climate_normal_high", new_callable=lambda: asyncio.coroutine(mock.MagicMock(return_value=None))):
                    with mock.patch("daily_brief.sources.weather._fetch_station_monthly_rainfall", new_callable=lambda: asyncio.coroutine(mock.MagicMock(return_value={"avg_monthly_rainfall": None, "current_monthly_rainfall": None}))):
                        with mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
                                asyncio.get_event_loop().run_until_complete(fetch_weather(None, 30.286, -95.566))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], "https://api.weather.gov/points/30.286,-95.566")

    def test_forecast_no_forecast_url_uses_suffix(self):
        point = {"properties": {}}
        today = datetime(2026, 7, 18, tzinfo=CHICTZ)
        forecast = _make_forecast(today, today + timedelta(days=1))
        
        async def side_effect(*a, **k):
            if not hasattr(side_effect, "call_count"):
                side_effect.call_count = 0
            side_effect.call_count += 1
            if side_effect.call_count == 1:
                return point
            return forecast
        
        mock_fn = asyncio.coroutine(mock.MagicMock(side_effect=side_effect))
        with mock.patch("daily_brief.sources.weather._fetch_json", mock_fn):
            with mock.patch("daily_brief.sources.weather.get_reference_datetime", return_value=today):
                with mock.patch("daily_brief.sources.weather._fetch_climate_normal_high", new_callable=lambda: asyncio.coroutine(mock.MagicMock(return_value=None))):
                    with mock.patch("daily_brief.sources.weather._fetch_station_monthly_rainfall", new_callable=lambda: asyncio.coroutine(mock.MagicMock(return_value={"avg_monthly_rainfall": None, "current_monthly_rainfall": None}))):
                        with mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
                            result = asyncio.get_event_loop().run_until_complete(fetch_weather(None, 30.286, -95.566))
        self.assertEqual(len(result["forecast"]), 3)


# ---------------------------------------------------------------------------
# 6. fetch_weather — period extraction details
# ---------------------------------------------------------------------------

class TestFetchWeatherPeriodExtraction(TestCase):
    """Period-specific parsing: day vs night slotting."""

    async def _run_with(self, periods):
        today = datetime(2026, 7, 18, tzinfo=CHICTZ)
        point = {"properties": {"forecast": "https://example.com/forecast"}}
        forecast = {"properties": {"periods": periods}}

        async def side_effect(*a, **k):
            if not hasattr(side_effect, "call_count"):
                side_effect.call_count = 0
            side_effect.call_count += 1
            return point if side_effect.call_count == 1 else forecast

        mock_fn = asyncio.coroutine(mock.MagicMock(side_effect=side_effect))
        with mock.patch("daily_brief.sources.weather._fetch_json", mock_fn):
            with mock.patch("daily_brief.sources.weather.get_reference_datetime", return_value=today):
                with mock.patch("daily_brief.sources.weather._fetch_climate_normal_high", new_callable=lambda: asyncio.coroutine(mock.MagicMock(return_value=None))):
                    with mock.patch("daily_brief.sources.weather._fetch_station_monthly_rainfall", new_callable=lambda: asyncio.coroutine(mock.MagicMock(return_value={"avg_monthly_rainfall": None, "current_monthly_rainfall": None}))):
                        with mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
                                return await fetch_weather(None, 30.286, -95.566)

    def test_day_slot_used_for_high(self):
        periods = [
            {"number": 1, "isDaytime": True, "startTime": datetime(2026, 7, 18, 6, tzinfo=CHICTZ).isoformat(), "temperature": 95, "temperatureUnit": "F", "shortForecast": "Sunny", "windSpeed": "10 mph"},
            {"number": 2, "isDaytime": False, "startTime": datetime(2026, 7, 18, 18, tzinfo=CHICTZ).isoformat(), "temperature": 75, "temperatureUnit": "F", "shortForecast": "Clear", "windSpeed": "5 mph"},
        ]
        result = asyncio.get_event_loop().run_until_complete(self._run_with(periods))
        self.assertIn("95", result["forecast"][0]["high"])
        self.assertIn("75", result["forecast"][0]["low"])

    def test_non_dict_period_skipped(self):
        periods = [
            "not_a_dict",
            {"number": 1, "isDaytime": True, "startTime": datetime(2026, 7, 18, 6, tzinfo=CHICTZ).isoformat(), "temperature": 90, "temperatureUnit": "F", "shortForecast": "OK"},
            {"number": 2, "isDaytime": False, "startTime": datetime(2026, 7, 18, 18, tzinfo=CHICTZ).isoformat(), "temperature": 70, "temperatureUnit": "F", "shortForecast": "OK"},
        ]
        result = asyncio.get_event_loop().run_until_complete(self._run_with(periods))
        self.assertEqual(len(result["forecast"]), 3)

    def test_malformed_start_date_skipped(self):
        periods = [
            {"number": 99, "isDaytime": True, "startTime": "garbage", "temperature": 99, "temperatureUnit": "F", "shortForecast": "Skip Me"},
            {"number": 1, "isDaytime": True, "startTime": datetime(2026, 7, 18, 6, tzinfo=CHICTZ).isoformat(), "temperature": 88, "temperatureUnit": "F", "shortForecast": "Good", "windSpeed": "5 mph"},
            {"number": 2, "isDaytime": False, "startTime": datetime(2026, 7, 18, 18, tzinfo=CHICTZ).isoformat(), "temperature": 72, "temperatureUnit": "F", "shortForecast": "Good", "windSpeed": "3 mph"},
        ]
        result = asyncio.get_event_loop().run_until_complete(self._run_with(periods))
        self.assertIn("88", result["forecast"][0]["high"])

    def test_no_precip_key_fallback(self):
        periods = [
            {"number": 1, "isDaytime": True, "startTime": datetime(2026, 7, 18, 6, tzinfo=CHICTZ).isoformat(), "temperature": 90, "temperatureUnit": "F", "shortForecast": "Dry", "windSpeed": "5 mph"},
            {"number": 2, "isDaytime": False, "startTime": datetime(2026, 7, 18, 18, tzinfo=CHICTZ).isoformat(), "temperature": 70, "temperatureUnit": "F", "shortForecast": "Dry", "windSpeed": "3 mph"},
        ]
        result = asyncio.get_event_loop().run_until_complete(self._run_with(periods))
        self.assertEqual(result["forecast"][0]["precip"], "Dynamic")

    def test_no_wind_speed_fallback(self):
        periods = [
            {"number": 1, "isDaytime": True, "startTime": datetime(2026, 7, 18, 6, tzinfo=CHICTZ).isoformat(), "temperature": 90, "temperatureUnit": "F", "shortForecast": "Calm"},
            {"number": 2, "isDaytime": False, "startTime": datetime(2026, 7, 18, 18, tzinfo=CHICTZ).isoformat(), "temperature": 70, "temperatureUnit": "F", "shortForecast": "Calm"},
        ]
        result = asyncio.get_event_loop().run_until_complete(self._run_with(periods))
        self.assertEqual(result["forecast"][0]["wind"], "Dynamic")
