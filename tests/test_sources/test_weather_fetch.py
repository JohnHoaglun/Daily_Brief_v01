"""Unit tests for fetch_weather orchestration in daily_brief/sources/weather.py."""

import asyncio
from datetime import datetime, timedelta
from unittest import TestCase, mock
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from daily_brief.sources.weather import fetch_weather

CHICTZ = ZoneInfo("America/Chicago")


def _make_forecast(today, tomorrow):
    """Return a minimal NWS forecast response with 3 periods."""
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
            ]
        }
    }


class TestFetchWeather(TestCase):
    """NWS normal response, NWS failure→fallback, and concurrent dispatch."""

    async def _run(self, point_resp, forecast_resp):
        with (
            mock.patch(
                "daily_brief.sources.weather._fetch_json",
                new=AsyncMock(side_effect=[point_resp, forecast_resp]),
            ),
            mock.patch(
                "daily_brief.sources.weather.get_reference_datetime",
                return_value=datetime(2026, 7, 18, tzinfo=CHICTZ),
            ),
            mock.patch(
                "daily_brief.sources.weather._fetch_climate_normal_high",
                new=AsyncMock(return_value=91),
            ),
            mock.patch(
                "daily_brief.sources.weather._fetch_station_monthly_rainfall",
                new=AsyncMock(return_value={"avg_monthly_rainfall": 3.2, "current_monthly_rainfall": 2.1}),
            ),
            mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}),
        ):
            return await fetch_weather(None, 30.286, -95.566)

    def test_nws_normal_response(self):
        """NWS normal path: forecast rows, temp formatting, station data."""
        point = {"properties": {"forecast": "https://api.weather.gov/grid/.../forecast"}}
        forecast = _make_forecast(
            datetime(2026, 7, 18, tzinfo=CHICTZ),
            datetime(2026, 7, 19, tzinfo=CHICTZ),
        )
        result = asyncio.get_event_loop().run_until_complete(self._run(point, forecast))
        assert len(result["forecast"]) == 3
        assert "Sunny" in result["forecast"][0]["day"]
        assert "Mostly" in result["forecast"][0]["night"]
        assert "\u00b0F" in result["forecast"][0]["high"]
        assert "91" in result["station"]["avg_temp_today"]
        assert "3.2" in result["station"]["avg_monthly_rainfall"]

    def test_nws_failure_fallback(self):
        """NWS failure returns empty forecast and 'Unavailable' station fields."""
        async def failing(*a, **k):
            return None
        with (
            mock.patch(
                "daily_brief.sources.weather._fetch_json",
                new=AsyncMock(side_effect=failing),
            ),
            mock.patch(
                "daily_brief.sources.weather.get_reference_datetime",
                return_value=datetime(2026, 7, 18, tzinfo=CHICTZ),
            ),
            mock.patch(
                "daily_brief.sources.weather._fetch_climate_normal_high",
                new=AsyncMock(return_value=None),
            ),
            mock.patch(
                "daily_brief.sources.weather._fetch_station_monthly_rainfall",
                new=AsyncMock(return_value={"avg_monthly_rainfall": None, "current_monthly_rainfall": None}),
            ),
            mock.patch("daily_brief.sources.weather.WEATHER_LAKE_URLS", {}),
        ):
            result = asyncio.get_event_loop().run_until_complete(
                fetch_weather(None, 30.286, -95.566)
            )
        assert len(result["forecast"]) == 0
        assert result["station"]["avg_temp_today"] == "Unavailable"

    def test_concurrent_dispatch(self):
        """All four providers start concurrently via asyncio.gather."""
        nws_entered = asyncio.Event()
        climate_entered = asyncio.Event()
        rainfall_entered = asyncio.Event()
        lakes_entered = asyncio.Event()
        release = asyncio.Event()

        async def gated(*a, **k):
            for evt in [nws_entered, climate_entered, rainfall_entered, lakes_entered]:
                evt.set()
            await release.wait()
            return []

        async def gated_lakes(*a, **k):
            lakes_entered.set()
            await release.wait()
            return ([], [])

        async def runner():
            task = asyncio.create_task(fetch_weather(None, 30.286, -95.566))
            await asyncio.gather(
                nws_entered.wait(),
                climate_entered.wait(),
                rainfall_entered.wait(),
                lakes_entered.wait(),
            )
            release.set()
            return await task

        with (
            mock.patch(
                "daily_brief.sources.weather.get_reference_datetime",
                return_value=datetime(2026, 7, 18, tzinfo=CHICTZ),
            ),
            mock.patch("daily_brief.sources.weather.fetch_nws_forecast", gated),
            mock.patch("daily_brief.sources.weather._fetch_climate_normal_high", gated),
            mock.patch("daily_brief.sources.weather._fetch_station_monthly_rainfall", gated),
            mock.patch("daily_brief.sources.weather.fetch_lakes", gated_lakes),
        ):
            result = asyncio.get_event_loop().run_until_complete(runner())

        assert nws_entered.is_set()
        assert climate_entered.is_set()
        assert rainfall_entered.is_set()
        assert lakes_entered.is_set()
        assert "station" in result
        assert "lakes" in result
