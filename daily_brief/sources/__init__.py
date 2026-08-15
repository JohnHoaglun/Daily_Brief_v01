"""
Daily Brief v1.0.150 — Data Sources
===================================
Pluggable data source modules for weather, RSS, lakes, climate, and wunderground.
"""

from daily_brief.sources.climate import _fetch_climate_normal_high, _parse_climate_summary
from daily_brief.sources.lakes import _extract_lake_value
from daily_brief.sources.rss import build_rss_url, fetch_feed
from daily_brief.sources.weather import fetch_weather
from daily_brief.sources.wunderground import (
    _fetch_station_metrics,
    _fetch_station_monthly_rainfall,
    _parse_wu_monthly_precipitation,
)

__all__ = [
    "_extract_lake_value",
    "_fetch_climate_normal_high",
    "_fetch_station_metrics",
    "_fetch_station_monthly_rainfall",
    "_parse_climate_summary",
    "_parse_wu_monthly_precipitation",
    "build_rss_url",
    "fetch_feed",
    "fetch_weather",
]
