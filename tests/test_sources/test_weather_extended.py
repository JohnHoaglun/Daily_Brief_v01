"""
Extended unit tests for weather.py.
Lake fetch loop, source concurrency, and non-dict payload handling.
"""

import asyncio
from datetime import datetime
from unittest import TestCase, mock
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from daily_brief.sources.weather import fetch_weather

CHICTZ = ZoneInfo("America/Chicago")


class TestWeatherLakeFetchLoop(TestCase):
    """Lake fetch loop executes when WEATHER_LAKE_URLS is non-empty."""

    def test_lake_fetch_loop_executes(self):
        today = datetime(2026, 7, 18, tzinfo=CHICTZ)
        lake_urls = {"lake_crawford": "https://example.com/lake_crawford"}
        call_count = [0]

        async def fetch_json_side(*a, **k):
            call_count[0] += 1
            return (
                {"properties": {"forecast": "https://example.com/forecast"}}
                if call_count[0] == 1
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
            mock.patch("daily_brief.sources.weather._fetch_climate_normal_high", new=AsyncMock(return_value=None)),
            mock.patch(
                "daily_brief.sources.weather._fetch_station_monthly_rainfall",
                new=AsyncMock(return_value={"avg_monthly_rainfall": None, "current_monthly_rainfall": None}),
            ),
            mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", lake_urls),
            mock.patch("daily_brief.sources.weather._extract_lake_value", mock_extract_lake),
        ):
            result = asyncio.get_event_loop().run_until_complete(
                fetch_weather(None, 30.286, -95.566)
            )
        self.assertIn("lake_crawford", mock_extract_lake.called_keys)
        self.assertIn("lake_crawford", result["lakes"])


class TestWeatherSourceConcurrency(TestCase):
    """All four providers start concurrently via asyncio.gather."""

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

        async def runner():
            task = asyncio.create_task(fetch_weather(None, 30.286, -95.566))
            await asyncio.gather(
                nws_entered.wait(), climate_entered.wait(),
                rainfall_entered.wait(), lakes_entered.wait(),
            )
            release.set()
            return await task

        with (
            mock.patch("daily_brief.sources.weather.get_reference_datetime", return_value=today),
            mock.patch("daily_brief.sources.weather.fetch_nws_forecast", gated_nws),
            mock.patch("daily_brief.sources.weather._fetch_climate_normal_high", gated_climate),
            mock.patch("daily_brief.sources.weather._fetch_station_monthly_rainfall", gated_rainfall),
            mock.patch("daily_brief.sources.weather.fetch_lakes", gated_lakes),
        ):
            result = asyncio.get_event_loop().run_until_complete(runner())

        self.assertTrue(nws_entered.is_set())
        self.assertTrue(climate_entered.is_set())
        self.assertTrue(rainfall_entered.is_set())
        self.assertTrue(lakes_entered.is_set())
        self.assertIn("avg_temp_today", result["station"])


class TestWeatherPayloadNotDict(TestCase):
    """Non-dict forecast payload triggers warning, graceful handling."""

    def test_forecast_payload_not_dict(self):
        today = datetime(2026, 7, 18, tzinfo=CHICTZ)

        async def side_effect(*a, **k):
            if not hasattr(side_effect, "cc"):
                side_effect.cc = 0
            side_effect.cc += 1
            return (
                {"properties": {"forecast": "https://example.com/forecast"}}
                if side_effect.cc == 1
                else [{"periods": []}]
            )

        with (
            mock.patch("daily_brief.sources.weather._fetch_json", new=AsyncMock(side_effect=side_effect)),
            mock.patch("daily_brief.sources.weather.get_reference_datetime", return_value=today),
            mock.patch("daily_brief.sources.weather._fetch_climate_normal_high", new=AsyncMock(return_value=None)),
            mock.patch("daily_brief.sources.weather._fetch_station_monthly_rainfall",
                        new=AsyncMock(return_value={"avg_monthly_rainfall": None, "current_monthly_rainfall": None})),
            mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}),
        ):
            with mock.patch("daily_brief.sources.weather.logger") as mock_logger:
                result = asyncio.get_event_loop().run_until_complete(
                    fetch_weather(None, 30.286, -95.566)
                )
                mock_logger.warning.assert_called()
                self.assertEqual(len(result["forecast"]), 0)
