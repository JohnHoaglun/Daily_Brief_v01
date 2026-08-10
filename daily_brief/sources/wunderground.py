"""
Daily Brief v1.0.139 — Wunderground Sources
============================================
Wunderground station scraping and precipitation parsing.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp
from bs4 import BeautifulSoup

import asyncio

from daily_brief.config import WUNDERGROUND_MONTHLY_TEMPLATE, WEATHER_WUNDERGROUND_STATION_ID
from daily_brief.http_client import _fetch_text
from daily_brief.sources.climate import _parse_climate_summary

logger = logging.getLogger(__name__)


def _parse_wu_monthly_precipitation(
    html: Optional[str],
    start_date: str,
    end_date: str,
) -> Optional[float]:
    """Extract monthly precipitation summary total (High) from WU monthly range page."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    if not text:
        return None

    def _pretty_date(d: str) -> Optional[str]:
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            return f"{dt.strftime('%B')} {dt.day}, {dt.year}"
        except Exception:
            return None

    start_label = _pretty_date(start_date)
    end_label = _pretty_date(end_date)

    start_idx = text.find("Summary")
    if start_idx == -1:
        return None

    end_idx = text.find("graph", start_idx)
    candidate = text[start_idx:end_idx] if end_idx != -1 else text[start_idx:]
    m = re.search(
        r"Summary.*?Precipitation\s+([0-9]+(?:\.[0-9]+)?)\s*°?\s*in",
        candidate,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if m and start_label and end_label:
        if not (start_label in candidate and end_label in candidate):
            date_pattern = re.escape(f"{start_label} - {end_label}")
            dated_match = re.search(
                rf"{date_pattern}.*?Precipitation\s+([0-9]+(?:\.[0-9]+)?)\s*°?\s*in",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if dated_match:
                m = dated_match
    if not m:
        return None
    try:
        val = float(m.group(1))
    except Exception:
        return None
    if 0.0 <= val <= 40.0:
        return val
    return None


async def _fetch_station_monthly_rainfall(
    session: aiohttp.ClientSession,
    reference: datetime,
) -> Dict[str, Optional[str]]:
    """Fetch station weather summary for current-month rain and Houston normals for average."""
    station_url = WUNDERGROUND_MONTHLY_TEMPLATE.format(
        station_id=WEATHER_WUNDERGROUND_STATION_ID,
        date=reference.strftime("%Y-%m-%d"),
    )
    month_start = reference.replace(day=1).strftime("%Y-%m-%d")
    month_end = reference.strftime("%Y-%m-%d")
    station_range_url = re.sub(
        r"/graph/[^/]+/[^/]+/monthly$",
        f"/graph/{month_start}/{month_end}/monthly",
        station_url,
    )

    climate_url = "https://www.weather.gov/hgx/climate_iah_normals_summary"
    station_html, climate_html = await asyncio.gather(
        _fetch_text(session, station_range_url),
        _fetch_text(session, climate_url)
    )
    if not station_html:
        logger.debug(
            "  Station monthly rainfall: no station monthly range html fetched (%s)",
            station_range_url,
        )

    station_current_rain = _parse_wu_monthly_precipitation(station_html, month_start, month_end)
    if station_current_rain is not None:
        logger.debug("  Station monthly rainfall: parsed station current month value %s", station_current_rain)
    if not climate_html:
        logger.debug("  Station monthly rainfall: no climate page HTML fetched")
        return {
            "avg_monthly_rainfall": None,
            "current_monthly_rainfall": station_current_rain,
        }

    text = BeautifulSoup(climate_html, "html.parser").get_text(" ", strip=True)
    logger.debug("  Station monthly rainfall: climate page text length %s", len(text))
    parsed = _parse_climate_summary(climate_html, reference.date())

    avg_rain = parsed.get("avg_monthly_rainfall")
    curr_rain = parsed.get("current_monthly_rainfall")

    def _safe_rainfall(v: Any) -> Optional[str]:
        if v is None:
            return None
        try:
            val = float(v)
            if 0.0 <= val <= 40.0:
                return f"{val}"
        except Exception:
            return None
        return None

    return {
        "avg_monthly_rainfall": _safe_rainfall(avg_rain),
        "current_monthly_rainfall": f"{station_current_rain}" if station_current_rain is not None else _safe_rainfall(curr_rain),
    }


async def _fetch_station_metrics(
    session: aiohttp.ClientSession,
    station_id: str,
    reference: datetime,
) -> Dict[str, Optional[str]]:
    """Return the station metrics shape.

    avg_temp_today is NOT fetched here — it comes from _fetch_climate_normal_high (Open-Meteo).
    avg_monthly_rainfall and current_monthly_rainfall come from _fetch_station_monthly_rainfall
    (climate.gov + Wunderground range URL). The old dashboard URL is no longer fetched separately;
    _fetch_station_monthly_rainfall covers the data with a single range-page request.
    """
    return {
        "avg_temp_today": None,
        "avg_monthly_rainfall": None,
        "current_monthly_rainfall": None,
    }
