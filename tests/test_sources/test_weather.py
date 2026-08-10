"""
Consolidated unit tests for daily_brief/sources/weather.py.
NWS forecast parsing, date extraction, label generation, fetch orchestration.
"""

import asyncio
from datetime import datetime, timedelta
from unittest import TestCase, mock
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from daily_brief.sources.weather import (
    _parse_date_for_weather,
    fetch_weather,
    get_reference_datetime,
    get_weather_label_for_offset,
)

CHICTZ = ZoneInfo("America/Chicago")


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


# ---------------------------------------------------------------------------
# 1. _parse_date_for_weather
# ---------------------------------------------------------------------------


class TestParseDateForWeather(TestCase):
    """NWS forecast date string parsing — representative cases."""

    def test_iso_format_with_z(self):
        result = _parse_date_for_weather("2026-07-18T12:00:00Z")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 7)
        self.assertEqual(result.day, 18)

    def test_strptime_no_tz_uses_default(self):
        result = _parse_date_for_weather("2026-07-18T08:00:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.tzinfo, CHICTZ)

    def test_bracket_tz_format(self):
        result = _parse_date_for_weather("2026-07-18T20:00:00-05:00[America/Chicago]")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)

    def test_garbage_returns_none(self):
        self.assertIsNone(_parse_date_for_weather("not-a-date"))
        self.assertIsNone(_parse_date_for_weather(""))
        self.assertIsNone(_parse_date_for_weather(None))


# ---------------------------------------------------------------------------
# 2. get_weather_label_for_offset
# ---------------------------------------------------------------------------


class TestGetWeatherLabelForOffset(TestCase):
    """Weather label generation for forecast offsets."""

    def _ref(self, year=2026, month=7, day=18):
        return datetime(year, month, day, 10, 0, 0, tzinfo=CHICTZ)

    def test_offsets(self):
        # All offsets return abbreviated day-of-week names
        ref = self._ref()  # 2026-07-18 is Saturday
        self.assertEqual(get_weather_label_for_offset(ref, 0), "Sat")
        self.assertEqual(get_weather_label_for_offset(ref, 1), "Sun")
        self.assertEqual(get_weather_label_for_offset(ref, 2), "Mon")
        self.assertEqual(get_weather_label_for_offset(ref, -1), "Fri")
        self.assertEqual(get_weather_label_for_offset(ref, -7), "Sat")


# ---------------------------------------------------------------------------
# 3. get_reference_datetime
# ---------------------------------------------------------------------------


class TestGetReferenceDatetime(TestCase):
    """Reference datetime with optional override."""

    def test_returns_datetime_with_tz(self):
        dt = get_reference_datetime()
        self.assertIsNotNone(dt.tzinfo)

    def test_date_override_and_fallback(self):
        with mock.patch("daily_brief.sources.weather.DATE_OVERRIDE", "2026-01-15T10:00:00"):
            dt = get_reference_datetime()
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 15)

        with mock.patch("daily_brief.sources.weather.DATE_OVERRIDE", "bad-value"):
            dt2 = get_reference_datetime()
        self.assertIsNotNone(dt2)


# ---------------------------------------------------------------------------
# 4. fetch_weather — consolidated happy path
# ---------------------------------------------------------------------------


class TestFetchWeatherHappyPath(TestCase):
    """fetch_weather successful NWS forecast parsing — all row assertions in one test."""

    def setUp(self):
        self.today = datetime(2026, 7, 18, tzinfo=CHICTZ)
        self.tomorrow = self.today + timedelta(days=1)
        self.forecast_url = "https://api.weather.gov/grid/.../forecast"

    async def _run(self, point_resp, forecast_resp):
        with mock.patch(
            "daily_brief.sources.weather._fetch_json",
            new=AsyncMock(side_effect=[point_resp, forecast_resp]),
        ), mock.patch(
            "daily_brief.sources.weather.get_reference_datetime", return_value=self.today
        ), mock.patch(
            "daily_brief.sources.weather._fetch_climate_normal_high",
            new=AsyncMock(return_value=91),
        ), mock.patch(
            "daily_brief.sources.weather._fetch_station_monthly_rainfall",
            new=AsyncMock(
                return_value={
                    "avg_monthly_rainfall": 3.2,
                    "current_monthly_rainfall": 2.1,
                }
            ),
        ), mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
            return await fetch_weather(None, 30.286, -95.566)

    def test_full_happy_path(self):
        point = {"properties": {"forecast": self.forecast_url}}
        forecast = _make_forecast(self.today, self.tomorrow)
        result = asyncio.get_event_loop().run_until_complete(self._run(point, forecast))

        # Forecast rows — day-of-week labels (Sat/Sun/Mon for 2026-07-18 reference)
        self.assertEqual(len(result["forecast"]), 3)
        self.assertEqual(result["forecast"][0]["date"], "Sat")
        self.assertEqual(result["forecast"][1]["date"], "Sun")
        self.assertEqual(result["forecast"][2]["date"], "Mon")

        # Day/night descriptions
        self.assertIn("Sunny", result["forecast"][0]["day"])
        self.assertIn("Mostly", result["forecast"][0]["night"])

        # Temperature formatting
        self.assertIn("92\u00b0F", result["forecast"][0]["high"])
        self.assertIn("78\u00b0F", result["forecast"][0]["low"])

        # Precipitation
        self.assertIn("%", result["forecast"][0]["precip"])

        # Wind
        self.assertIn("10", result["forecast"][0]["wind"])
        self.assertIn("S", result["forecast"][0]["wind"])

        # Station data
        station = result["station"]
        self.assertIn("91", station["avg_temp_today"])
        self.assertIsNotNone(station["avg_monthly_rainfall"])
        self.assertIsNotNone(station["current_monthly_rainfall"])


# ---------------------------------------------------------------------------
# 5. fetch_weather — edge cases consolidated
# ---------------------------------------------------------------------------


class TestFetchWeatherEdgeCases(TestCase):
    """fetch_weather error handling and boundary conditions."""

    def setUp(self):
        self.today = datetime(2026, 7, 18, tzinfo=CHICTZ)
        self.forecast_url = "https://api.weather.gov/grid/.../forecast"

    async def _run(self, point_resp, forecast_resp):
        with mock.patch(
            "daily_brief.sources.weather._fetch_json",
            new=AsyncMock(side_effect=[point_resp, forecast_resp]),
        ), mock.patch(
            "daily_brief.sources.weather.get_reference_datetime", return_value=self.today
        ), mock.patch(
            "daily_brief.sources.weather._fetch_climate_normal_high",
            new=AsyncMock(return_value=None),
        ), mock.patch(
            "daily_brief.sources.weather._fetch_station_monthly_rainfall",
            new=AsyncMock(
                return_value={
                    "avg_monthly_rainfall": None,
                    "current_monthly_rainfall": None,
                }
            ),
        ), mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
            return await fetch_weather(None, 30.286, -95.566)

    def test_missing_point_and_empty_periods(self):
        result = asyncio.get_event_loop().run_until_complete(
            self._run({"not_properties": True}, None)
        )
        self.assertEqual(len(result["forecast"]), 0)

        forecast = {"properties": {"periods": []}}
        result2 = asyncio.get_event_loop().run_until_complete(
            self._run({"properties": {"forecast": self.forecast_url}}, forecast)
        )
        self.assertEqual(result2["forecast"][0]["high"], "Dynamic")

        # Station unavailable fallback
        station = result2["station"]
        self.assertEqual(station["avg_temp_today"], "Unavailable")
        self.assertEqual(station["avg_monthly_rainfall"], "Unavailable")
        self.assertEqual(station["current_monthly_rainfall"], "Unavailable")

    def test_http_error_and_exception(self):
        async def none_side(*a, **k):
            return None

        with mock.patch(
            "daily_brief.sources.weather._fetch_json", new=AsyncMock(side_effect=none_side)
        ), mock.patch(
            "daily_brief.sources.weather.get_reference_datetime", return_value=self.today
        ), mock.patch(
            "daily_brief.sources.weather._fetch_climate_normal_high",
            new=AsyncMock(return_value=None),
        ), mock.patch(
            "daily_brief.sources.weather._fetch_station_monthly_rainfall",
            new=AsyncMock(
                return_value={
                    "avg_monthly_rainfall": None,
                    "current_monthly_rainfall": None,
                }
            ),
        ), mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
            result = asyncio.get_event_loop().run_until_complete(
                fetch_weather(None, 30.286, -95.566)
            )
        self.assertEqual(len(result["forecast"]), 0)

        async def err_side(*a, **k):
            raise ConnectionError("DNS failure")

        with mock.patch(
            "daily_brief.sources.weather._fetch_json", new=AsyncMock(side_effect=err_side)
        ), mock.patch(
            "daily_brief.sources.weather.get_reference_datetime", return_value=self.today
        ), mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
            result2 = asyncio.get_event_loop().run_until_complete(
                fetch_weather(None, 30.286, -95.566)
            )
        self.assertEqual(len(result2["forecast"]), 0)
        self.assertEqual(len(result2["errors"]), 0)

    def test_point_url_constructed(self):
        calls = []

        async def capture(session, url, **k):
            calls.append(url)
            return {"properties": {"forecast": self.forecast_url}}

        with mock.patch(
            "daily_brief.sources.weather._fetch_json", new=AsyncMock(side_effect=capture)
        ), mock.patch(
            "daily_brief.sources.weather.get_reference_datetime", return_value=self.today
        ), mock.patch(
            "daily_brief.sources.weather._fetch_climate_normal_high",
            new=AsyncMock(return_value=None),
        ), mock.patch(
            "daily_brief.sources.weather._fetch_station_monthly_rainfall",
            new=AsyncMock(
                return_value={
                    "avg_monthly_rainfall": None,
                    "current_monthly_rainfall": None,
                }
            ),
        ), mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
            asyncio.get_event_loop().run_until_complete(
                fetch_weather(None, 30.286, -95.566)
            )
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], "https://api.weather.gov/points/30.286,-95.566")

    def test_provided_forecast_url_used(self):
        point = {"properties": {"forecast": "https://api.weather.gov/grid/EAX/250,125"}}
        calls = []

        async def capture(session, url, **k):
            calls.append(url)
            if not hasattr(capture, "cc"):
                capture.cc = 0
            capture.cc += 1
            if capture.cc == 1:
                return point
            return {"properties": {"periods": []}}

        with mock.patch(
            "daily_brief.sources.weather._fetch_json", new=AsyncMock(side_effect=capture)
        ), mock.patch(
            "daily_brief.sources.weather.get_reference_datetime", return_value=self.today
        ), mock.patch(
            "daily_brief.sources.weather._fetch_climate_normal_high",
            new=AsyncMock(return_value=None),
        ), mock.patch(
            "daily_brief.sources.weather._fetch_station_monthly_rainfall",
            new=AsyncMock(
                return_value={
                    "avg_monthly_rainfall": None,
                    "current_monthly_rainfall": None,
                }
            ),
        ), mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
            asyncio.get_event_loop().run_until_complete(
                fetch_weather(None, 30.286, -95.566)
            )
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1], "https://api.weather.gov/grid/EAX/250,125")

    def test_missing_forecast_url_uses_suffix(self):
        point = {"properties": {}}
        forecast_date = datetime(2026, 7, 18, tzinfo=CHICTZ)
        forecast = _make_forecast(forecast_date, forecast_date + timedelta(days=1))
        calls = []

        async def side_effect(*a, **k):
            if not hasattr(side_effect, "cc"):
                side_effect.cc = 0
            side_effect.cc += 1
            calls.append(a[1] if len(a) > 1 else k.get("url", ""))
            if side_effect.cc == 1:
                return point
            return forecast

        with mock.patch(
            "daily_brief.sources.weather._fetch_json", new=AsyncMock(side_effect=side_effect)
        ), mock.patch(
            "daily_brief.sources.weather.get_reference_datetime", return_value=forecast_date
        ), mock.patch(
            "daily_brief.sources.weather._fetch_climate_normal_high",
            new=AsyncMock(return_value=None),
        ), mock.patch(
            "daily_brief.sources.weather._fetch_station_monthly_rainfall",
            new=AsyncMock(
                return_value={
                    "avg_monthly_rainfall": None,
                    "current_monthly_rainfall": None,
                }
            ),
        ), mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
            result = asyncio.get_event_loop().run_until_complete(
                fetch_weather(None, 30.286, -95.566)
            )
        self.assertEqual(len(result["forecast"]), 3)
        self.assertTrue(calls[1].rstrip("/").endswith("forecast"))


# ---------------------------------------------------------------------------
# 6. fetch_weather — period extraction consolidated
# ---------------------------------------------------------------------------


class TestFetchWeatherPeriodExtraction(TestCase):
    """Period-specific parsing: day vs night slotting, malformed period handling."""

    async def _run_with(self, periods):
        today = datetime(2026, 7, 18, tzinfo=CHICTZ)
        point = {"properties": {"forecast": "https://example.com/forecast"}}
        forecast = {"properties": {"periods": periods}}

        async def side_effect(*a, **k):
            if not hasattr(side_effect, "cc"):
                side_effect.cc = 0
            side_effect.cc += 1
            return point if side_effect.cc == 1 else forecast

        with mock.patch(
            "daily_brief.sources.weather._fetch_json", new=AsyncMock(side_effect=side_effect)
        ), mock.patch(
            "daily_brief.sources.weather.get_reference_datetime", return_value=today
        ), mock.patch(
            "daily_brief.sources.weather._fetch_climate_normal_high",
            new=AsyncMock(return_value=None),
        ), mock.patch(
            "daily_brief.sources.weather._fetch_station_monthly_rainfall",
            new=AsyncMock(
                return_value={
                    "avg_monthly_rainfall": None,
                    "current_monthly_rainfall": None,
                }
            ),
        ), mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
            return await fetch_weather(None, 30.286, -95.566)

    def test_day_night_slotting(self):
        periods = [
            {
                "number": 1,
                "isDaytime": True,
                "startTime": datetime(2026, 7, 18, 6, tzinfo=CHICTZ).isoformat(),
                "temperature": 95,
                "temperatureUnit": "F",
                "shortForecast": "Sunny",
                "windSpeed": "10 mph",
            },
            {
                "number": 2,
                "isDaytime": False,
                "startTime": datetime(2026, 7, 18, 18, tzinfo=CHICTZ).isoformat(),
                "temperature": 75,
                "temperatureUnit": "F",
                "shortForecast": "Clear",
                "windSpeed": "5 mph",
            },
        ]
        result = asyncio.get_event_loop().run_until_complete(self._run_with(periods))
        self.assertIn("95", result["forecast"][0]["high"])
        self.assertIn("75", result["forecast"][0]["low"])

    def test_malformed_periods_fallback(self):
        periods = [
            "not_a_dict",
            {
                "number": 99,
                "isDaytime": True,
                "startTime": "garbage",
                "temperature": 99,
                "temperatureUnit": "F",
                "shortForecast": "Skip Me",
            },
            {
                "number": 1,
                "isDaytime": True,
                "startTime": datetime(2026, 7, 18, 6, tzinfo=CHICTZ).isoformat(),
                "temperature": 88,
                "temperatureUnit": "F",
                "shortForecast": "Good",
                "windSpeed": "5 mph",
            },
            {
                "number": 2,
                "isDaytime": False,
                "startTime": datetime(2026, 7, 18, 18, tzinfo=CHICTZ).isoformat(),
                "temperature": 72,
                "temperatureUnit": "F",
                "shortForecast": "Good",
                "windSpeed": "3 mph",
            },
        ]
        result = asyncio.get_event_loop().run_until_complete(self._run_with(periods))
        self.assertEqual(len(result["forecast"]), 3)
        self.assertIn("88", result["forecast"][0]["high"])

    def test_missing_keys_safe_fallback(self):
        periods = [
            {
                "number": 1,
                "isDaytime": True,
                "startTime": datetime(2026, 7, 18, 6, tzinfo=CHICTZ).isoformat(),
                "temperature": 90,
                "temperatureUnit": "F",
                "shortForecast": "Dry",
            },
            {
                "number": 2,
                "isDaytime": False,
                "startTime": datetime(2026, 7, 18, 18, tzinfo=CHICTZ).isoformat(),
                "temperature": 70,
                "temperatureUnit": "F",
                "shortForecast": "Dry",
            },
        ]
        result = asyncio.get_event_loop().run_until_complete(self._run_with(periods))
        self.assertEqual(result["forecast"][0]["precip"], "Dynamic")
        self.assertEqual(result["forecast"][0]["wind"], "Dynamic")
