"""
Daily Brief — Weather data merge / model.

Pure deterministic merge of weather provider outputs into a single
structured dict. No I/O, no network calls.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def merge_weather_data(
    forecast: List[Dict[str, Any]],
    climate_high: int | None,
    station_monthly: Dict[str, Any],
    lakes: Dict[str, Dict[str, Any]],
    errors: List[str],
) -> Dict[str, Any]:
    """Pure deterministic merge of weather provider outputs.

    Owns:
    - Station data formatting (ERA5 normal high, rainfall values)
    - Forecast fallback when ERA5 is unavailable
    - Equal rainfall suppression
    - "Unavailable" defaults
    """
    weather_data: Dict[str, Any] = {
        "forecast": list(forecast),
        "station": {
            "avg_temp_today": None,
            "avg_monthly_rainfall": None,
            "current_monthly_rainfall": None,
        },
        "lakes": dict(lakes),
        "errors": list(errors),
    }

    if not isinstance(station_monthly, dict):
        station_monthly = {"avg_monthly_rainfall": None, "current_monthly_rainfall": None}

    if climate_high is not None:
        weather_data["station"]["avg_temp_today"] = f"{climate_high}°F"

    logger.debug(
        "Weather station data: "
        f"avg_temp_today={weather_data['station'].get('avg_temp_today', 'Dynamic')} "
        f"avg_monthly_rainfall={weather_data['station'].get('avg_monthly_rainfall', 'Dynamic')} "
        f"current_monthly_rainfall={weather_data['station'].get('current_monthly_rainfall', 'Dynamic')}"
    )
    logger.debug(
        "Station monthly rainfall: "
        f"avg={station_monthly.get('avg_monthly_rainfall', 'Dynamic')} "
        f"current={station_monthly.get('current_monthly_rainfall', 'Dynamic')}"
    )
    if station_monthly.get("avg_monthly_rainfall") and not weather_data["station"].get(
        "avg_monthly_rainfall"
    ):
        weather_data["station"]["avg_monthly_rainfall"] = (
            f"{station_monthly['avg_monthly_rainfall']} Inches"
        )
    if station_monthly.get("current_monthly_rainfall") and not weather_data["station"].get(
        "current_monthly_rainfall"
    ):
        weather_data["station"]["current_monthly_rainfall"] = (
            f"{station_monthly['current_monthly_rainfall']} Inches"
        )

    station = weather_data["station"]
    if station.get("avg_monthly_rainfall") == station.get("current_monthly_rainfall"):
        station["current_monthly_rainfall"] = None
    for key in ("avg_temp_today", "avg_monthly_rainfall", "current_monthly_rainfall"):
        if not station.get(key):
            station[key] = "Unavailable"

    has_fallback = any(
        "(forecast fallback)" in str(station.get(k, "")) for k in ("avg_temp_today",)
    )
    has_missing = any(
        station.get(k) == "Unavailable"
        for k in ("avg_temp_today", "avg_monthly_rainfall", "current_monthly_rainfall")
    )

    if has_fallback or has_missing:
        logger.debug(
            "[fetch_weather] Station data (partial/missing): "
            f"avg_temp_today={station.get('avg_temp_today')} "
            f"avg_monthly_rainfall={station.get('avg_monthly_rainfall')} "
            f"current_monthly_rainfall={station.get('current_monthly_rainfall')}"
        )
    else:
        logger.debug(
            "[fetch_weather] Station data complete: "
            f"avg_temp_today={station.get('avg_temp_today')} "
            f"avg_monthly_rainfall={station.get('avg_monthly_rainfall')} "
            f"current_monthly_rainfall={station.get('current_monthly_rainfall')}"
        )

    return weather_data
