"""
Daily Brief v1.0.12 — Weather Source
=====================================
NWS forecast fetch, parse, and orchestration of all weather data sources.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

import aiohttp

from config import (
    WEATHER_LAT,
    WEATHER_LON,
    WEATHER_POINT_URL,
    WEATHER_POINT_FORECAST_SUFFIX,
    WEATHER_WUNDERGROUND_STATION_ID,
    WEATHER_LAKE_URLS,
    USER_AGENT,
    USER_AGENT_WEATHER_SUFFIX,
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
from daily_brief.sources.wunderground import (
    _fetch_station_metrics,
    _fetch_station_monthly_rainfall,
)
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
    """Generate weather label for a given offset from reference date."""
    target = reference.date() + timedelta(days=offset_days)
    today = reference.date()
    tomorrow = today + timedelta(days=1)
    if target == today:
        return "Today"
    if target == tomorrow:
        return "Tonight"
    return target.strftime("%A")


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


async def fetch_weather(session: aiohttp.ClientSession, lat: float, lon: float) -> Dict[str, Any]:
    """Fetch all required weather data blocks used by the Weather section."""
    now_ref = get_reference_datetime()
    logger.debug("[fetch_weather] Entering weather fetch")
    weather_data: Dict[str, Any] = {
        "forecast": [],
        "station": {"avg_temp_today": None, "avg_monthly_rainfall": None, "current_monthly_rainfall": None},
        "lakes": {},
        "errors": [],
    }
    try:
        weather_point_url = WEATHER_POINT_URL.format(lat=lat, lon=lon)
        logger.debug(f"[fetch_weather] Point URL: {weather_point_url}")
        point = await _fetch_json(session, weather_point_url, user_agent=USER_AGENT)
        if not isinstance(point, dict) or "properties" not in point:
            logger.warning("[fetch_weather] Point response invalid or missing properties")
            return weather_data

        fc_url = point["properties"].get("forecast")
        if not fc_url:
            fc_url = WEATHER_POINT_URL.split("?")[0] + WEATHER_POINT_FORECAST_SUFFIX
        if WEATHER_POINT_FORECAST_SUFFIX and not fc_url.rstrip("/").endswith(WEATHER_POINT_FORECAST_SUFFIX):
            fc_url = fc_url.rstrip("/") + f"/{WEATHER_POINT_FORECAST_SUFFIX}"
        logger.debug(f"[fetch_weather] Forecast URL: {fc_url}")
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

            for offset in range(3):
                row_date = now_ref.date() + timedelta(days=offset)
                day_slot = by_date.get(row_date, {})
                day = day_slot.get("day", {})
                night = day_slot.get("night", {})
                if not day:
                    day = _nearest_for_day(datetime.combine(row_date, datetime.min.time(), tzinfo=_ACTIVE_TIMEZONE), day_periods) or {}
                if not night:
                    night = _nearest_for_day(datetime.combine(row_date, datetime.min.time(), tzinfo=_ACTIVE_TIMEZONE), night_periods) or {}

                wind_speed = None
                wind_dir = None
                if isinstance(day, dict):
                    wind_speed = day.get("windSpeed")
                    wind_dir = day.get("windDirection")
                wind = _safe_text(wind_speed, "")
                if wind and wind_dir:
                    wind = f"{wind} {wind_dir}"
                row = {
                    "date": get_weather_label_for_offset(now_ref, offset),
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
                weather_data["forecast"].append(row)
            logger.debug(f"Weather forecast rows: {len(weather_data['forecast'])}")
        else:
            logger.warning("[fetch_weather] Forecast payload was not a dict; skipping period parse")

        # Station metrics
        weather_data["station"] = await _fetch_station_metrics(session, WEATHER_WUNDERGROUND_STATION_ID, now_ref)
        logger.debug("[fetch_weather] Completed station fetch")

        # Climate normal (historical average high for this date)
        climate_high = await _fetch_climate_normal_high(session)
        if climate_high is not None:
            weather_data["station"]["avg_temp_today"] = f"{climate_high}°F"
        logger.debug(
            "Weather station data: "
            f"avg_temp_today={weather_data['station'].get('avg_temp_today', 'Dynamic')} "
            f"avg_monthly_rainfall={weather_data['station'].get('avg_monthly_rainfall', 'Dynamic')} "
            f"current_monthly_rainfall={weather_data['station'].get('current_monthly_rainfall', 'Dynamic')}"
        )

        # Merge with climate normals source for monthly rain values
        station_monthly = await _fetch_station_monthly_rainfall(session, now_ref)
        logger.debug(
            "Station monthly rainfall: "
            f"avg={station_monthly.get('avg_monthly_rainfall', 'Dynamic')} "
            f"current={station_monthly.get('current_monthly_rainfall', 'Dynamic')}"
        )
        if station_monthly.get("avg_monthly_rainfall") and not weather_data["station"].get("avg_monthly_rainfall"):
            weather_data["station"]["avg_monthly_rainfall"] = f"{station_monthly['avg_monthly_rainfall']} Inches"
        if station_monthly.get("current_monthly_rainfall") and not weather_data["station"].get("current_monthly_rainfall"):
            weather_data["station"]["current_monthly_rainfall"] = f"{station_monthly['current_monthly_rainfall']} Inches"

        # Fallback: use forecast high if climate normal failed
        if weather_data["station"]:
            station = weather_data["station"]
            if not station.get("avg_temp_today") and weather_data["forecast"]:
                logger.debug("[fetch_weather] Climate normal unavailable, falling back to forecast high")
                first_row = weather_data["forecast"][0]
                temp_candidates = [first_row.get("high"), first_row.get("low")]
                for val in temp_candidates:
                    m = re.search(r"(-?\d+(?:\.\d+)?)", _safe_text(val, ""))
                    if m:
                        station["avg_temp_today"] = f"{m.group(0)}°F (forecast fallback)"
                        break
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

        # Lake levels
        for key in ("conroe", "corpus_christi", "travis"):
            lake_url = WEATHER_LAKE_URLS.get(key)
            if not lake_url:
                continue
            weather_data["lakes"][key] = await _extract_lake_value(session, key, lake_url, now_ref)
            logger.debug(f"[fetch_weather] Completed lake fetch: {key}")
            logger.debug(
                f"Lake {key}: "
                f"today={weather_data['lakes'][key].get('today')} "
                f"one_week_ago={weather_data['lakes'][key].get('one_week_ago')} "
                f"thirty_days_ago={weather_data['lakes'][key].get('thirty_days_ago')}"
            )

    except Exception as e:
        logger.warning(f"Weather fetch failed ({e})")
        weather_data["errors"].append(str(e))

    return weather_data
