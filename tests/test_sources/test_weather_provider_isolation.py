"""
Unit tests for B.8: Weather provider isolation and deterministic merge.
NWS failure with independent collection, merge policy, and fallback behavior.
"""

import asyncio
from datetime import datetime
from unittest import TestCase, mock
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from daily_brief.sources.weather import fetch_lakes, fetch_weather, merge_weather_data

CHICTZ = ZoneInfo("America/Chicago")


class TestProviderIsolation(TestCase):
    """NWS failure does not prevent ERA5/rainfall/lakes collection."""

    def test_nws_fail_collects_era5_rainfall_lakes(self):
        today = datetime(2026, 7, 18, tzinfo=CHICTZ)

        async def raise_dns(*a, **k):
            raise ConnectionError("DNS failure")

        with (
            mock.patch("daily_brief.sources.weather._fetch_json", new=AsyncMock(side_effect=raise_dns)),
            mock.patch("daily_brief.sources.weather.get_reference_datetime", return_value=today),
            mock.patch("daily_brief.sources.weather._fetch_climate_normal_high", new=AsyncMock(return_value=91)),
            mock.patch(
                "daily_brief.sources.weather._fetch_station_monthly_rainfall",
                new=AsyncMock(return_value={"avg_monthly_rainfall": 3.2, "current_monthly_rainfall": 2.1}),
            ),
            mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}),
        ):
            result = asyncio.get_event_loop().run_until_complete(fetch_weather(None, 30.286, -95.566))
        self.assertEqual(len(result["forecast"]), 0)
        self.assertIn("91\u00b0", result["station"]["avg_temp_today"])
        self.assertIn("3.2", result["station"]["avg_monthly_rainfall"])
        self.assertIn("lakes", result)

    def test_both_climate_and_rainfall_fail(self):
        """When both climate and rainfall fail, station data is 'Unavailable'."""
        today = datetime(2026, 7, 18, tzinfo=CHICTZ)
        point = {"properties": {"forecast": "https://example.com/forecast"}}
        forecast = {
            "properties": {
                "periods": [
                    {
                        "number": 1, "isDaytime": True, "startTime": today.isoformat(),
                        "temperature": 95, "temperatureUnit": "F", "shortForecast": "Sunny",
                        "windSpeed": "10 mph", "probabilityOfPrecipitation": {"value": 10},
                    },
                ]
            }
        }

        async def side_effect(*a, **k):
            if not hasattr(side_effect, "cc"):
                side_effect.cc = 0
            side_effect.cc += 1
            return point if side_effect.cc == 1 else forecast

        with (
            mock.patch("daily_brief.sources.weather._fetch_json", new=AsyncMock(side_effect=side_effect)),
            mock.patch("daily_brief.sources.weather.get_reference_datetime", return_value=today),
            mock.patch("daily_brief.sources.weather._fetch_climate_normal_high", new=AsyncMock(side_effect=RuntimeError("Climate error"))),
            mock.patch("daily_brief.sources.weather._fetch_station_monthly_rainfall", new=AsyncMock(side_effect=RuntimeError("Rain error"))),
            mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}),
        ):
            result = asyncio.get_event_loop().run_until_complete(fetch_weather(None, 30.286, -95.566))
        self.assertEqual(result["station"]["avg_temp_today"], "Unavailable")
        self.assertEqual(result["station"]["avg_monthly_rainfall"], "Unavailable")


class TestMergeWeatherData(TestCase):
    """Direct tests for the pure merge function."""

    def test_full_provider_data(self):
        forecast = [{
            "date": "Sat", "high": "95\u00b0F", "low": "75\u00b0F",
            "day": "Sunny", "night": "Clear", "precip": "10%", "wind": "10 mph",
        }]
        lakes = {"lake_crawford": {"today": "65%", "one_week_ago": "60%", "thirty_days_ago": "55%"}}
        result = merge_weather_data(forecast, 91, {"avg_monthly_rainfall": 3.2, "current_monthly_rainfall": 2.1}, lakes, ["lake:testlake:ConnectionError"])
        self.assertEqual(len(result["forecast"]), 1)
        self.assertEqual(result["station"]["avg_temp_today"], "91\u00b0F")
        self.assertIn("3.2", result["station"]["avg_monthly_rainfall"])
        self.assertIn("lake_crawford", result["lakes"])
        self.assertEqual(len(result["errors"]), 1)

    def test_era5_absent_no_fallback(self):
        """When ERA5 is unavailable, avg_temp_today is 'Unavailable'."""
        result = merge_weather_data(
            [], None, {"avg_monthly_rainfall": 3.2, "current_monthly_rainfall": 2.1}, {}, []
        )
        self.assertEqual(result["station"]["avg_temp_today"], "Unavailable")

    def test_invalid_payload_returns_unavailable(self):
        result = merge_weather_data(
            [], None, "not a dict", {}, []
        )
        self.assertEqual(result["station"]["avg_monthly_rainfall"], "Unavailable")


class TestLakeFetchDirect(TestCase):
    """Direct fetch_lakes tests: concurrency bound, failure isolation."""

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
        self.assertIsNone(lakes["lake_b"]["today"])
        self.assertTrue(any("lake_b" in err for err in errors))
