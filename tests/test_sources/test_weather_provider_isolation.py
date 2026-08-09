"""
Unit tests for B.8: Weather provider isolation and deterministic merge.
NWS failure with independent collection, merge policy, and fallback behavior.
"""
import asyncio
from datetime import datetime, timedelta
from unittest import TestCase, mock
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from daily_brief.sources.weather import (
    fetch_nws_forecast,
    fetch_lakes,
    merge_weather_data,
    fetch_weather,
)

CHICTZ = ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# 1. NWS failure + independent provider collection
# ---------------------------------------------------------------------------

class TestNwsFailureIndependentCollection(TestCase):
    """NWS failure does not prevent ERA5/rainfall/lakes collection."""

    def setUp(self):
        self.today = datetime(2026, 7, 18, tzinfo=CHICTZ)

    async def _run_nws_fail(self):
        async def raise_dns(*a, **k):
            raise ConnectionError("DNS failure")
        with mock.patch("daily_brief.sources.weather._fetch_json", new=AsyncMock(side_effect=raise_dns)):
            with mock.patch("daily_brief.sources.weather.get_reference_datetime", return_value=self.today):
                with mock.patch("daily_brief.sources.weather._fetch_climate_normal_high",
                                new=AsyncMock(return_value=91)):
                    with mock.patch("daily_brief.sources.weather._fetch_station_monthly_rainfall",
                                    new=AsyncMock(return_value={"avg_monthly_rainfall": 3.2, "current_monthly_rainfall": 2.1})):
                        with mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
                            return await fetch_weather(None, 30.286, -95.566)

    def test_nws_fail_collects_era5_rainfall_lakes(self):
        result = asyncio.get_event_loop().run_until_complete(self._run_nws_fail())
        self.assertEqual(len(result["forecast"]), 0)
        self.assertIn("91\u00b0", result["station"]["avg_temp_today"])
        self.assertIn("3.2", result["station"]["avg_monthly_rainfall"])
        self.assertIn("2.1", result["station"]["current_monthly_rainfall"])
        self.assertIn("forecast", result)
        self.assertIn("station", result)
        self.assertIn("lakes", result)
        self.assertIn("errors", result)


# ---------------------------------------------------------------------------
# 2. Combined provider failure permutations
# ---------------------------------------------------------------------------

class TestProviderFailurePermutations(TestCase):
    """Climate and rainfall individual/combined failure handling."""

    def setUp(self):
        self.today = datetime(2026, 7, 18, tzinfo=CHICTZ)

    async def _run(self, climate_result=None, rain_result=None, raise_climate=False, raise_rain=False):
        if raise_climate:
            climate_coro = AsyncMock(side_effect=RuntimeError("Climate error"))
        else:
            climate_coro = AsyncMock(return_value=climate_result)
        if raise_rain:
            rain_coro = AsyncMock(side_effect=RuntimeError("Rain error"))
        else:
            rain_coro = AsyncMock(return_value=rain_result)

        point = {"properties": {"forecast": "https://example.com/forecast"}}
        forecast = {"properties": {"periods": [
            {"number": 1, "isDaytime": True, "startTime": self.today.isoformat(),
             "temperature": 95, "temperatureUnit": "F", "shortForecast": "Sunny",
             "windSpeed": "10 mph", "probabilityOfPrecipitation": {"value": 10}},
            {"number": 2, "isDaytime": False,
             "startTime": (self.today + timedelta(hours=12)).isoformat(),
             "temperature": 75, "temperatureUnit": "F", "shortForecast": "Clear",
             "windSpeed": "5 mph", "probabilityOfPrecipitation": {"value": 5}},
            {"number": 3, "isDaytime": True,
             "startTime": (self.today + timedelta(days=1)).isoformat(),
             "temperature": 93, "temperatureUnit": "F", "shortForecast": "Partly Sunny",
             "windSpeed": "8 mph", "probabilityOfPrecipitation": {"value": 20}},
        ]}}

        async def side_effect(*a, **k):
            if not hasattr(side_effect, "cc"):
                side_effect.cc = 0
            side_effect.cc += 1
            return point if side_effect.cc == 1 else forecast

        with mock.patch("daily_brief.sources.weather._fetch_json", new=AsyncMock(side_effect=side_effect)):
            with mock.patch("daily_brief.sources.weather.get_reference_datetime", return_value=self.today):
                with mock.patch("daily_brief.sources.weather._fetch_climate_normal_high", climate_coro):
                    with mock.patch("daily_brief.sources.weather._fetch_station_monthly_rainfall", rain_coro):
                        with mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}):
                            return await fetch_weather(None, 30.286, -95.566)

    def test_climate_fail_rain_succeeds(self):
        result = asyncio.get_event_loop().run_until_complete(
            self._run(raise_climate=True, rain_result={"avg_monthly_rainfall": 3.2, "current_monthly_rainfall": 2.1}))
        self.assertEqual(len(result["forecast"]), 3)
        self.assertIn("3.2", result["station"]["avg_monthly_rainfall"])

    def test_rain_fail_climate_succeeds(self):
        result = asyncio.get_event_loop().run_until_complete(
            self._run(climate_result=91, raise_rain=True))
        self.assertEqual(len(result["forecast"]), 3)
        self.assertIn("91\u00b0", result["station"]["avg_temp_today"])

    def test_both_fail_no_fallback(self):
        """When both ERA5 and rainfall fail, station data is 'Unavailable' — no forecast fallback."""
        result = asyncio.get_event_loop().run_until_complete(
            self._run(raise_climate=True, raise_rain=True))
        self.assertEqual(len(result["forecast"]), 3)
        self.assertEqual(result["station"]["avg_temp_today"], "Unavailable")
        self.assertEqual(result["station"]["avg_monthly_rainfall"], "Unavailable")
        self.assertEqual(result["station"]["current_monthly_rainfall"], "Unavailable")


# ---------------------------------------------------------------------------
# 3. merge_weather_data direct tests
# ---------------------------------------------------------------------------

class TestMergeWeatherData(TestCase):
    """Direct tests for the pure merge function."""

    def test_full_provider_data(self):
        forecast = [{"date": "Sat", "high": "95\u00b0F", "low": "75\u00b0F",
                     "day": "Sunny", "night": "Clear", "precip": "10%", "wind": "10 mph"}]
        climate_high = 91
        station_monthly = {"avg_monthly_rainfall": 3.2, "current_monthly_rainfall": 2.1}
        lakes = {"lake_crawford": {"today": "65%", "one_week_ago": "60%", "thirty_days_ago": "55%"}}
        errors = ["lake:testlake:ConnectionError"]

        result = merge_weather_data(forecast, climate_high, station_monthly, lakes, errors)
        self.assertEqual(len(result["forecast"]), 1)
        self.assertEqual(result["forecast"][0]["date"], "Sat")
        self.assertEqual(result["station"]["avg_temp_today"], "91\u00b0F")
        self.assertIn("3.2", result["station"]["avg_monthly_rainfall"])
        self.assertIn("2.1", result["station"]["current_monthly_rainfall"])
        self.assertIn("lake_crawford", result["lakes"])
        self.assertEqual(len(result["errors"]), 1)

    def test_era5_absent_no_fallback(self):
        """When ERA5 climate normal is unavailable, avg_temp_today is 'Unavailable' — no forecast fallback."""
        forecast = [{"date": "Sat", "high": "92\u00b0F", "low": "72\u00b0F"}]
        result = merge_weather_data(forecast, None,
                                    {"avg_monthly_rainfall": 3.2, "current_monthly_rainfall": 2.1}, {}, [])
        self.assertEqual(result["station"]["avg_temp_today"], "Unavailable")

    def test_rainfall_formatting(self):
        result = merge_weather_data([], 91,
                                    {"avg_monthly_rainfall": 5.1, "current_monthly_rainfall": 3.2}, {}, [])
        self.assertIn("5.1", result["station"]["avg_monthly_rainfall"])
        self.assertIn("Inches", result["station"]["avg_monthly_rainfall"])
        self.assertIn("3.2", result["station"]["current_monthly_rainfall"])

    def test_equal_rainfall_suppressed_and_invalid_payload(self):
        result = merge_weather_data([], None,
                                    {"avg_monthly_rainfall": 4.2, "current_monthly_rainfall": 4.2}, {}, [])
        self.assertEqual(result["station"]["current_monthly_rainfall"], "Unavailable")

        result2 = merge_weather_data([], None, "not a dict", {}, [])
        self.assertEqual(result2["station"]["avg_monthly_rainfall"], "Unavailable")

    def test_lake_ordering_preserved(self):
        lakes = {
            "lake_crawford": {"today": "65%", "one_week_ago": "60%", "thirty_days_ago": "55%"},
            "lake_conroe": {"today": "70%", "one_week_ago": "68%", "thirty_days_ago": "58%"},
        }
        result = merge_weather_data([], 91,
                                    {"avg_monthly_rainfall": 3.2, "current_monthly_rainfall": 2.1}, lakes, [])
        self.assertIn("lake_crawford", result["lakes"])
        self.assertIn("lake_conroe", result["lakes"])
        self.assertEqual(result["lakes"]["lake_crawford"]["today"], "65%")
        self.assertEqual(result["lakes"]["lake_conroe"]["today"], "70%")

    def test_errors_and_all_unavailable(self):
        result = merge_weather_data([], 91,
                                    {"avg_monthly_rainfall": 3.2, "current_monthly_rainfall": 2.1}, {},
                                    ["lake:testlake:ConnectionError", "lake:testlake2:Timeout"])
        self.assertEqual(len(result["errors"]), 2)

        result2 = merge_weather_data([], None,
                                      {"avg_monthly_rainfall": None, "current_monthly_rainfall": None}, {}, [])
        self.assertEqual(result2["station"]["avg_temp_today"], "Unavailable")
        self.assertEqual(result2["station"]["avg_monthly_rainfall"], "Unavailable")


# ---------------------------------------------------------------------------
# 4. Lake fetching (direct fetch_lakes)
# ---------------------------------------------------------------------------

class TestLakeFetchDirect(TestCase):
    """Direct fetch_lakes tests: concurrency bound, failure isolation, ordering."""

    def test_sequential_limit_bounded(self):
        today = datetime(2026, 7, 18, tzinfo=CHICTZ)
        lake_urls = {"lake_a": "http://a", "lake_b": "http://b", "lake_c": "http://c", "lake_d": "http://d"}
        active_lock = asyncio.Lock()
        active_count = [0]
        max_active = [0]

        async def track_limit(session, key, url, ref):
            async with active_lock:
                active_count[0] += 1
                if active_count[0] > max_active[0]:
                    max_active[0] = active_count[0]
            await asyncio.sleep(0.02)
            async with active_lock:
                active_count[0] -= 1
            return {"today": key, "one_week_ago": None, "thirty_days_ago": None}

        async def runner():
            with mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", lake_urls):
                with mock.patch("daily_brief.sources.weather._extract_lake_value", track_limit):
                    lakes, errors = await fetch_lakes(None, today)
            return lakes, max_active[0]

        lakes, peak = asyncio.get_event_loop().run_until_complete(runner())
        self.assertLessEqual(peak, 3)
        self.assertEqual(len(lakes), 4)

    def test_lake_failure_isolated(self):
        today = datetime(2026, 7, 18, tzinfo=CHICTZ)
        lake_urls = {"lake_a": "http://a", "lake_b": "http://b", "lake_c": "http://c"}

        async def failing_once(session, key, url, ref):
            if key == "lake_b":
                raise RuntimeError("lake fetch failed")
            return {"today": f"{key}_today", "one_week_ago": None, "thirty_days_ago": None}

        async def runner():
            with mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", lake_urls):
                with mock.patch("daily_brief.sources.weather._extract_lake_value", failing_once):
                    lakes, errors = await fetch_lakes(None, today)
            return lakes, errors

        lakes, errors = asyncio.get_event_loop().run_until_complete(runner())
        self.assertEqual(lakes["lake_a"]["today"], "lake_a_today")
        self.assertEqual(lakes["lake_c"]["today"], "lake_c_today")
        self.assertIsNone(lakes["lake_b"]["today"])
        self.assertTrue(any("lake_b" in err for err in errors))

    def test_lake_order_stable(self):
        today = datetime(2026, 7, 18, tzinfo=CHICTZ)
        lake_urls = {"first": "http://1", "second": "http://2", "third": "http://3"}

        async def out_of_order(session, key, url, ref):
            if key == "third":
                await asyncio.sleep(0)
            return {"today": key, "one_week_ago": None, "thirty_days_ago": None}

        async def runner():
            with mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", lake_urls):
                with mock.patch("daily_brief.sources.weather._extract_lake_value", out_of_order):
                    lakes, errors = await fetch_lakes(None, today)
            return lakes

        lakes = asyncio.get_event_loop().run_until_complete(runner())
        self.assertEqual(list(lakes.keys()), ["first", "second", "third"])
