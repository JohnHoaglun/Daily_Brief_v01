"""
Daily Brief v1.0.131 — Weather Source
=====================================
NWS forecast fetch, parse, and orchestration of all weather data sources.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import aiohttp

from daily_brief.config import (
    WEATHER_LAT,
    WEATHER_LON,
    WEATHER_POINT_URL,
    WEATHER_POINT_FORECAST_SUFFIX,
    WEATHER_WUNDERGROUND_STATION_ID,
    WEATHER_LAKE_URLS,
    USER_AGENT,
    TIMEZONE as CONFIG_TIMEZONE,
    DATE_OVERRIDE,
)

try:
    _ACTIVE_TIMEZONE = ZoneInfo(CONFIG_TIMEZONE)
except Exception:
    _ACTIVE_TIMEZONE = timezone.utc
from daily_brief.http_client import _fetch_json, _fetch_text
from daily_brief.sources.climate import _fetch_climate_normal_high
from daily_brief.sources.lakes import _extract_lake_value
from daily_brief.sources.wunderground import _fetch_station_monthly_rainfall
from daily_brief.utils import _safe_text

logger = logging.getLogger(__name__)


def get_reference_datetime() -> datetime:
    """Return current runtime date/time in configured timezone, optionally overridden."""
    if DATE_OVERRIDE:
        try:
            dt = datetime.fromisoformat(str(DATE_OVERRIDE))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=_ACTIVE_TIMEZONE)
            return dt.astimezone(_ACTIVE_TIMEZONE)
        except Exception:
            pass
    return datetime.now(_ACTIVE_TIMEZONE)


def get_weather_label_for_offset(reference: datetime, offset_days: int, style: str = "long") -> str:
    """Generate day-of-week label for the target date (e.g. "Sun", "Mon")."""
    target = reference.date() + timedelta(days=offset_days)
    return target.strftime("%a")


def _parse_date_for_weather(raw_value: Optional[str]) -> Optional[datetime]:
    """Parse NWS forecast date string into datetime in active timezone."""
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).astimezone(_ACTIVE_TIMEZONE)
    except Exception:
        pass
    try:
        return datetime.strptime(raw_value, "%Y-%m-%dT%H:%M:%S%z").astimezone(_ACTIVE_TIMEZONE)
    except Exception:
        pass
    try:
        return datetime.strptime(raw_value, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=_ACTIVE_TIMEZONE)
    except Exception:
        try:
            # Handle rare format: 2026-07-18T20:00:00-05:00[America/Chicago]
            cleaned = raw_value.split("[", 1)[0]
            return datetime.fromisoformat(cleaned).astimezone(_ACTIVE_TIMEZONE)
        except Exception:
            return None


async def fetch_nws_forecast(
    session: aiohttp.ClientSession, lat: float, lon: float, reference: datetime
) -> List[Dict[str, Any]]:
    """Fetch and parse NWS forecast data from point lookup.
    
    Returns parsed forecast rows or empty list on any parsing failure.
    Does NOT construct full weather_data output.
    """
    weather_point_url = WEATHER_POINT_URL.format(lat=lat, lon=lon)
    logger.debug(f"[fetch_nws_forecast] Point URL: {weather_point_url}")
    try:
        point = await _fetch_json(session, weather_point_url, user_agent=USER_AGENT)
        if not isinstance(point, dict) or "properties" not in point:
            logger.warning("[fetch_nws_forecast] Point response invalid or missing properties")
            return []

        fc_url = point["properties"].get("forecast")
        if not fc_url:
            fc_url = WEATHER_POINT_URL.split("?")[0] + WEATHER_POINT_FORECAST_SUFFIX
        else:
            # Use NWS-provided URL as-is — don't alter it
            pass
        logger.debug(f"[fetch_nws_forecast] Forecast URL: {fc_url}")
        forecast_payload = await _fetch_json(session, fc_url, user_agent=USER_AGENT)
        if isinstance(forecast_payload, dict):
            periods = forecast_payload.get("properties", {}).get("periods", []) or []
            logger.debug(f"Weather forecast periods fetched: {len(periods)}")
            by_date: Dict[Any, Any] = {}
            day_periods: list = []
            night_periods: list = []
            for p in periods:
                if not isinstance(p, dict):
                    continue
                day_start = _parse_date_for_weather(p.get("startTime"))
                if not day_start:
                    continue
                if p.get("isDaytime"):
                    day_periods.append((day_start, p))
                else:
                    night_periods.append((day_start, p))
                day_key = day_start.date()
                slot = by_date.setdefault(day_key, {})
                slot_type = "day" if p.get("isDaytime") else "night"
                slot[slot_type] = p

            def _nearest_for_day(day_dt, slots):
                if not slots:
                    return None
                return min(slots, key=lambda it: abs((it[0].date() - day_dt.date()).days))[1]

            forecast_rows: List[Dict[str, Any]] = []
            for offset in range(3):
                row_date = reference.date() + timedelta(days=offset)
                day_slot = by_date.get(row_date, {})
                day = day_slot.get("day", {})
                night = day_slot.get("night", {})
                if not day:
                    day = _nearest_for_day(datetime.combine(row_date, datetime.min.time(), tzinfo=_ACTIVE_TIMEZONE), day_periods) or {}  # type: ignore[arg-type]
                if not night:
                    night = _nearest_for_day(datetime.combine(row_date, datetime.min.time(), tzinfo=_ACTIVE_TIMEZONE), night_periods) or {}  # type: ignore[arg-type]

                wind_speed = None
                wind_dir = None
                if isinstance(day, dict):
                    wind_speed = day.get("windSpeed")
                    wind_dir = day.get("windDirection")
                wind = _safe_text(wind_speed, "")
                if wind and wind_dir:
                    wind = f"{wind} {wind_dir}"
                row = {
                    "date": get_weather_label_for_offset(reference, offset),
                    "day": _safe_text((day or {}).get("shortForecast"), "Dynamic"),
                    "night": _safe_text((night or {}).get("shortForecast"), _safe_text((day or {}).get("shortForecast"), "Dynamic")),
                    "high": _safe_text((day or {}).get("temperature"), "Dynamic"),
                    "low": _safe_text((night or {}).get("temperature"), "Dynamic"),
                    "precip": _safe_text((day or {}).get("probabilityOfPrecipitation", {}).get("value"), "Dynamic"),
                    "wind": _safe_text(wind, "Dynamic"),
                }
                row["high"] = f"{row['high']}°{day.get('temperatureUnit', 'F')}" if row["high"] != "Dynamic" else "Dynamic"
                row["low"] = f"{row['low']}°{night.get('temperatureUnit', day.get('temperatureUnit', 'F'))}" if row["low"] != "Dynamic" else "Dynamic"
                if row["precip"] and row["precip"] != "Dynamic":
                    row["precip"] = f"{row['precip']}%"
                forecast_rows.append(row)
            logger.debug(f"Weather forecast rows: {len(forecast_rows)}")
            return forecast_rows
        else:
            logger.warning("[fetch_nws_forecast] Forecast payload was not a dict; skipping period parse")
            return []
    except Exception as e:
        logger.warning(f"[fetch_nws_forecast] NWS fetch failed: {e}")
        return []


async def _fetch_lake(
    session: aiohttp.ClientSession, key: str, url: str, now_ref: datetime, sem: asyncio.Semaphore
) -> Tuple[str, Optional[Dict[str, Any]], Optional[Exception]]:
    """Fetch a single lake value with semaphore bound.
    
    Returns (key, result_dict_or_none, exception_or_none).
    """
    try:
        async with sem:
            result = await _extract_lake_value(session, key, url, now_ref)
        return (key, result, None)
    except Exception as e:
        logger.warning(f"[fetch_weather] Lake fetch failed ({key}): {e}")
        return (key, None, e)


async def fetch_lakes(
    session: aiohttp.ClientSession, now_ref: datetime
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Fetch all lake values concurrently with bounded concurrency.
    
    Returns (lakes_dict, errors_list).
    Preserves configured lake ordering in output dict.
    """
    _MAX_CONCURRENT_LAKE_FETCHES = 3
    _LAKE_UNAVAILABLE = {"today": None, "one_week_ago": None, "thirty_days_ago": None}
    lake_items = list((WEATHER_LAKE_URLS or {}).items())

    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_LAKE_FETCHES)
    results = await asyncio.gather(
        *(_fetch_lake(session, k, u, now_ref, semaphore) for k, u in lake_items),
        return_exceptions=True,
    )
    
    lakes: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    
    for i, item_result in enumerate(results):
        key = lake_items[i][0]
        if isinstance(item_result, Exception):
            # The entire gather result was an exception
            errors.append(f"lake:{key}:{item_result}")
            lakes[key] = dict(_LAKE_UNAVAILABLE)
        else:
            # Tuple result
            try:
                k, result, exc = item_result
                if exc:
                    errors.append(f"lake:{key}:{exc}")
                    lakes[key] = dict(_LAKE_UNAVAILABLE)
                else:
                    lakes[key] = result or dict(_LAKE_UNAVAILABLE)
            except (TypeError, ValueError):
                # Malformed result
                errors.append(f"lake:{key}:unexpected result")
                lakes[key] = dict(_LAKE_UNAVAILABLE)
        logger.debug(f"[fetch_weather] Completed lake fetch: {key}")
        logger.debug(
            f"Lake {key}: "
            f"today={lakes[key].get('today')} "
            f"one_week_ago={lakes[key].get('one_week_ago')} "
            f"thirty_days_ago={lakes[key].get('thirty_days_ago')}"
        )

    return lakes, errors


def merge_weather_data(
    forecast: List[Dict[str, Any]],
    climate_high: Optional[int],
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
        "forecast": list(forecast),  # type: ignore[attr-defined]
        "station": {
            "avg_temp_today": None,
            "avg_monthly_rainfall": None,
            "current_monthly_rainfall": None,
        },
        "lakes": dict(lakes),
        "errors": list(errors),
    }
    
    # Normalize station_monthly
    if not isinstance(station_monthly, dict):
        station_monthly = {"avg_monthly_rainfall": None, "current_monthly_rainfall": None}
    
    # Populate station data deterministically
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
    if station_monthly.get("avg_monthly_rainfall") and not weather_data["station"].get("avg_monthly_rainfall"):
        weather_data["station"]["avg_monthly_rainfall"] = f"{station_monthly['avg_monthly_rainfall']} Inches"
    if station_monthly.get("current_monthly_rainfall") and not weather_data["station"].get("current_monthly_rainfall"):
        weather_data["station"]["current_monthly_rainfall"] = f"{station_monthly['current_monthly_rainfall']} Inches"

    station = weather_data["station"]
    if station.get("avg_monthly_rainfall") == station.get("current_monthly_rainfall"):
        station["current_monthly_rainfall"] = None
    for key in ("avg_temp_today", "avg_monthly_rainfall", "current_monthly_rainfall"):
        if not station.get(key):
            station[key] = "Unavailable"

    has_fallback = any("(forecast fallback)" in str(station.get(k, "")) for k in ("avg_temp_today",))
    has_missing = any(station.get(k) == "Unavailable" for k in ("avg_temp_today", "avg_monthly_rainfall", "current_monthly_rainfall"))

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


async def fetch_weather(session: aiohttp.ClientSession, lat: float, lon: float) -> Dict[str, Any]:
    """Fetch all required weather data blocks used by the Weather section.
    
    Collector: concurrently fetches NWS, climate normal, monthly rainfall, and lakes.
    Orchestrates: calls merge_weather_data once with collected provider outputs.
    """
    now_ref = get_reference_datetime()
    logger.debug("[fetch_weather] Entering weather fetch")
    weather_data: Dict[str, Any] = {
        "forecast": [],
        "station": {"avg_temp_today": None, "avg_monthly_rainfall": None, "current_monthly_rainfall": None},
        "lakes": {},
        "errors": [],
    }
    try:
        # Concurrent collection of all providers
        nws_result = await fetch_nws_forecast(session, lat, lon, now_ref)
        results = await asyncio.gather(
            _fetch_climate_normal_high(session, lat, lon),
            _fetch_station_monthly_rainfall(session, now_ref),
            return_exceptions=True,
        )
        climate_high = results[0] if not isinstance(results[0], Exception) else None
        station_monthly = results[1] if not isinstance(results[1], Exception) else {"avg_monthly_rainfall": None, "current_monthly_rainfall": None}
        lakes, lake_errors = await fetch_lakes(session, now_ref)
        logger.debug("[fetch_weather] Completed climate/monthly fetch")

        # Merge all data deterministically
        weather_data = merge_weather_data(nws_result, climate_high, station_monthly, lakes, lake_errors)

    except Exception as e:
        logger.warning(f"Weather fetch failed ({e})")
        weather_data["errors"].append(str(e))

    return weather_data
