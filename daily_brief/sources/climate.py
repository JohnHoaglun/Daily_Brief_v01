"""
Daily Brief v1.0.136 — Climate Sources
======================================
Climate data fetching and parsing functions extracted from the monolith.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import aiohttp
from bs4 import BeautifulSoup

from daily_brief.http_client import _fetch_json
from daily_brief.utils import _safe_text

logger = logging.getLogger(__name__)


async def _fetch_climate_normal_high(
    session: aiohttp.ClientSession,
    lat: float,
    lon: float,
    reference_date: Optional[datetime] = None,
) -> Optional[int]:
    """Fetch the historical average high temperature for the given reference date
    from Open-Meteo ERA5.

    Returns the climate normal (long-term average) for the calendar month+day of
    reference_date — NOT the forecast.  Uses the 1991-2020 climatology period.
    Coordinates are provided by the caller to avoid a per-run geocoding request.
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc)
    today_str = reference_date.strftime("%Y-%m-%d")
    try:
        archive_url = "https://archive-api.open-meteo.com/v1/era5"
        params: Dict[str, Any] = {
            "latitude": lat,
            "longitude": lon,
            "start_date": today_str,
            "end_date": today_str,
            "daily": "temperature_2m_max",
            "temperature_unit": "fahrenheit",
        }
        climate = await _fetch_json(
            session,
            archive_url,
            **{"params": params, "timeout": 10},
        )
        if not climate:
            logger.debug(f"  [ERA5] No climate response from {archive_url}")
            return None
        logger.debug(f"  [ERA5] Raw response keys: {list(climate.keys())}")
        logger.debug(f"  [ERA5] Full daily block: {climate.get('daily', {})}")
        daily = climate.get("daily", {})
        temps = daily.get("temperature_2m_max", [])
        logger.debug(f"  [ERA5].temperature_2m_max list: {temps}")
        logger.debug(f"  [ERA5] Request params: {params}")
        if temps:
            val = round(temps[0])
            logger.debug(f"  Climate normal high for {today_str}: {val}°F (raw: {temps[0]})")
            return val
        logger.debug(f"  [ERA5] No temperature_2m_max data in response")
        return None
    except Exception as e:
        logger.warning(f"  WARNING Open-Meteo climate normal fetch failed: {e}")
    return None


def _parse_climate_summary(
    text: Optional[str],
    current_month: datetime,
) -> Dict[str, Optional[float]]:
    """Parse Houston HGX climate summary text for monthly normals and current values.

    Returns a dict with:
      - avg_monthly_rainfall: normal precipitation for the current month
      - current_monthly_rainfall: best-effort total/value for current month
    """
    if not text:
        return {"avg_monthly_rainfall": None, "current_monthly_rainfall": None}

    month_names = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    month_short = current_month.strftime("%b")
    month_idx = month_names.index(month_short) if month_short in month_names else 0

    def _clean_number(value) -> Optional[float]:
        if value is None:
            return None
        cleaned = _safe_text(value).replace(",", "").replace(" ", "")
        m = re.search(r"\d+(?:\.\d+)?", cleaned)
        if not m:
            return None
        try:
            return float(m.group(0))
        except Exception:
            return None

    soup = BeautifulSoup(text, "html.parser")
    tables = soup.find_all("table")
    avg_rainfall: Optional[float] = None
    current_rainfall: Optional[float] = None

    # Parse normals table first: row labeled "Rain Totals (in)" with Jan..Dec columns.
    for table in tables:
        rows = table.find_all("tr")
        cleaned_rows: list[list[str]] = []
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if cells:
                cleaned_rows.append(cells)
        for i, row in enumerate(cleaned_rows):
            if not row or "rain totals" not in row[0].lower():
                continue
            header_row: Optional[list[str]] = None
            for j in range(i - 1, max(-1, i - 4), -1):
                if j < 0:
                    continue
                candidate = [c.lower() for c in cleaned_rows[j]]
                if len(candidate) >= 12 and any(month.lower() in candidate for month in month_names):
                    header_row = cleaned_rows[j]
                    break
            if header_row:
                norm_col = month_idx + 1
                if len(row) > norm_col:
                    avg_rainfall = _clean_number(row[norm_col])
            if avg_rainfall is not None:
                break
        if avg_rainfall is not None:
            break

    # Parse annual summary only for current-year rows when available; do not
    # fallback to older years for current-month values.
    target_year = str(current_month.year)
    for table in tables:
        rows = table.find_all("tr")
        cleaned_rows: list[list[str]] = []
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["th", "td"])]
            if cells:
                cleaned_rows.append(cells)

        # Find row for current year and strip departure text from month cells.
        year_row: Optional[list[str]] = None
        for row in cleaned_rows:
            if row and _safe_text(row[0]).strip() == target_year and len(row) > month_idx + 1:
                year_row = row
                break
        if year_row is None:
            continue

        for row in cleaned_rows:
            if not row or "rain totals" not in row[0].lower():
                continue
            if row is year_row or all(c == "" for c in row):
                continue
            rain_col = month_idx + 1
            if len(row) > rain_col:
                candidate_text = _safe_text(row[rain_col])
                candidate = _clean_number(candidate_text.split("(")[0].strip())
                if candidate is not None:
                    current_rainfall = candidate
                    break
        if current_rainfall is not None:
            break

    # Keep values in plausible range and distinct when one-side data is absent.
    if avg_rainfall is not None and not (0.0 <= avg_rainfall <= 40.0):
        avg_rainfall = None
    if current_rainfall is not None and not (0.0 <= current_rainfall <= 40.0):
        current_rainfall = None

    return {
        "avg_monthly_rainfall": avg_rainfall,
        "current_monthly_rainfall": current_rainfall,
    }
