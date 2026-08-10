"""
Extended unit tests for weather.py.
Uniquely covered lines: forecast URL behavior, malformed NWS payload, lake fetch loop.
"""

import asyncio
from datetime import datetime
from unittest import TestCase, mock
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from daily_brief.sources.weather import fetch_weather

CHICTZ = ZoneInfo("America/Chicago")


class TestWeatherForecastUrl(TestCase):
    """weather.py: NWS-provided forecast URL used as-is; fallback suffix when missing."""

    def setUp(self):
        self.today = datetime(2026, 7, 18, tzinfo=CHICTZ)
        self.forecast_url_no_suffix = "https://api.weather.gov/grid/EAX/250,125"

    def test_provided_url_used_as_is(self):
        calls = []

        async def capture_fetch(session, url, **k):
            calls.append(url)
            if not hasattr(capture_fetch, "cc"):
                capture_fetch.cc = 0
            capture_fetch.cc += 1
            if capture_fetch.cc == 1:
                return {"properties": {"forecast": self.forecast_url_no_suffix}}
            return {"properties": {"periods": []}}

        with (
            mock.patch(
                "daily_brief.sources.weather._fetch_json", new=AsyncMock(side_effect=capture_fetch)
            ),
            mock.patch(
                "daily_brief.sources.weather.get_reference_datetime", return_value=self.today
            ),
            mock.patch(
                "daily_brief.sources.weather._fetch_climate_normal_high",
                new=AsyncMock(return_value=None),
            ),
            mock.patch(
                "daily_brief.sources.weather._fetch_station_monthly_rainfall",
                new=AsyncMock(
                    return_value={
                        "avg_monthly_rainfall": None,
                        "current_monthly_rainfall": None,
                    }
                ),
            ),
            mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}),
        ):
            asyncio.get_event_loop().run_until_complete(fetch_weather(None, 30.286, -95.566))

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1], self.forecast_url_no_suffix)

    def test_fallback_uses_suffix(self):
        calls = []

        async def capture_fetch(session, url, **k):
            calls.append(url)
            if not hasattr(capture_fetch, "cc"):
                capture_fetch.cc = 0
            capture_fetch.cc += 1
            if capture_fetch.cc == 1:
                return {"properties": {}}
            return {"properties": {"periods": []}}

        with (
            mock.patch(
                "daily_brief.sources.weather._fetch_json", new=AsyncMock(side_effect=capture_fetch)
            ),
            mock.patch(
                "daily_brief.sources.weather.get_reference_datetime", return_value=self.today
            ),
            mock.patch(
                "daily_brief.sources.weather._fetch_climate_normal_high",
                new=AsyncMock(return_value=None),
            ),
            mock.patch(
                "daily_brief.sources.weather._fetch_station_monthly_rainfall",
                new=AsyncMock(
                    return_value={
                        "avg_monthly_rainfall": None,
                        "current_monthly_rainfall": None,
                    }
                ),
            ),
            mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}),
        ):
            asyncio.get_event_loop().run_until_complete(fetch_weather(None, 30.286, -95.566))

        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[1].rstrip("/").endswith("forecast"))


class TestWeatherForecastPayloadNotDict(TestCase):
    """weather.py: non-dict forecast payload triggers warning, graceful handling."""

    def test_forecast_payload_not_dict(self):
        today = datetime(2026, 7, 18, tzinfo=CHICTZ)

        async def side_effect(*a, **k):
            if not hasattr(side_effect, "cc"):
                side_effect.cc = 0
            side_effect.cc += 1
            if side_effect.cc == 1:
                return {"properties": {"forecast": "https://example.com/forecast"}}
            return [{"periods": []}]

        with (
            mock.patch(
                "daily_brief.sources.weather._fetch_json", new=AsyncMock(side_effect=side_effect)
            ),
            mock.patch("daily_brief.sources.weather.get_reference_datetime", return_value=today),
            mock.patch(
                "daily_brief.sources.weather._fetch_climate_normal_high",
                new=AsyncMock(return_value=None),
            ),
            mock.patch(
                "daily_brief.sources.weather._fetch_station_monthly_rainfall",
                new=AsyncMock(
                    return_value={
                        "avg_monthly_rainfall": None,
                        "current_monthly_rainfall": None,
                    }
                ),
            ),
            mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}),
        ):
            with mock.patch("daily_brief.sources.weather.logger") as mock_logger:
                result = asyncio.get_event_loop().run_until_complete(
                    fetch_weather(None, 30.286, -95.566)
                )
                mock_logger.warning.assert_called()
                call_args = str(mock_logger.warning.call_args)
                self.assertIn("not a dict", call_args)
                self.assertEqual(len(result["forecast"]), 0)


class TestWeatherLakeFetchLoop(TestCase):
    """weather.py: lake fetch loop executes when WEATHER_LAKE_URLS is non-empty."""

    def test_lake_fetch_loop_executes(self):
        today = datetime(2026, 7, 18, tzinfo=CHICTZ)
        lake_urls = {"lake_crawford": "https://example.com/lake_crawford"}

        async def fetch_json_side(*a, **k):
            if not hasattr(fetch_json_side, "cc"):
                fetch_json_side.cc = 0
            fetch_json_side.cc += 1
            return (
                {"properties": {"forecast": "https://example.com/forecast"}}
                if fetch_json_side.cc == 1
                else {"properties": {"periods": []}}
            )

        async def mock_extract_lake(session, key, url, ref):
            mock_extract_lake.called_keys.append(key)
            return {"today": "65%", "one_week_ago": "60%", "thirty_days_ago": "55%"}

        mock_extract_lake.called_keys = []

        with (
            mock.patch(
                "daily_brief.sources.weather._fetch_json",
                new=AsyncMock(side_effect=fetch_json_side),
            ),
            mock.patch("daily_brief.sources.weather.get_reference_datetime", return_value=today),
            mock.patch(
                "daily_brief.sources.weather._fetch_climate_normal_high",
                new=AsyncMock(return_value=None),
            ),
            mock.patch(
                "daily_brief.sources.weather._fetch_station_monthly_rainfall",
                new=AsyncMock(
                    return_value={
                        "avg_monthly_rainfall": None,
                        "current_monthly_rainfall": None,
                    }
                ),
            ),
            mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", lake_urls),
            mock.patch(
                "daily_brief.sources.weather._extract_lake_value",
                mock_extract_lake,
            ),
        ):
            result = asyncio.get_event_loop().run_until_complete(
                fetch_weather(None, 30.286, -95.566)
            )
            self.assertIn("lake_crawford", mock_extract_lake.called_keys)
            self.assertIn("lake_crawford", result["lakes"])


class TestWeatherSourceConcurrency(TestCase):
    """weather.py: all four providers (NWS, climate, rainfall, lakes) start concurrently."""

    def test_all_four_providers_start_concurrently(self):
        today = datetime(2026, 7, 18, tzinfo=CHICTZ)

        nws_entered = asyncio.Event()
        climate_entered = asyncio.Event()
        rainfall_entered = asyncio.Event()
        lakes_entered = asyncio.Event()
        release = asyncio.Event()

        async def gated_nws(*a, **k):
            nws_entered.set()
            await release.wait()
            return []

        async def gated_climate(*a, **k):
            climate_entered.set()
            await release.wait()
            return 75

        async def gated_rainfall(*a, **k):
            rainfall_entered.set()
            await release.wait()
            return {"avg_monthly_rainfall": None, "current_monthly_rainfall": None}

        async def gated_lakes(*a, **k):
            lakes_entered.set()
            await release.wait()
            return ([], [])

        async def run():
            with (
                mock.patch(
                    "daily_brief.sources.weather.get_reference_datetime", return_value=today
                ),
                mock.patch("daily_brief.sources.weather.fetch_nws_forecast", gated_nws),
                mock.patch(
                    "daily_brief.sources.weather._fetch_climate_normal_high", gated_climate
                ),
                mock.patch(
                    "daily_brief.sources.weather._fetch_station_monthly_rainfall",
                    gated_rainfall,
                ),
                mock.patch("daily_brief.sources.weather.fetch_lakes", gated_lakes),
            ):
                task = asyncio.create_task(fetch_weather(None, 30.286, -95.566))
                await asyncio.gather(
                    nws_entered.wait(),
                    climate_entered.wait(),
                    rainfall_entered.wait(),
                    lakes_entered.wait(),
                )
                release.set()
                result = await task

            self.assertTrue(nws_entered.is_set())
            self.assertTrue(climate_entered.is_set())
            self.assertTrue(rainfall_entered.is_set())
            self.assertTrue(lakes_entered.is_set())
            self.assertIn("forecast", result)
            self.assertIn("station", result)
            self.assertIn("avg_temp_today", result["station"])
            self.assertIn("lakes", result)

        asyncio.get_event_loop().run_until_complete(run())
