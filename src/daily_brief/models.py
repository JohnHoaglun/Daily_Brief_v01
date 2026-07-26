"""
Daily Brief v1.0.12 — Models
=============================
Dataclasses for the daily brief pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Story:
    """Represents a single news story."""

    title: str = ""
    link: str = ""
    pubDate: str = ""
    summary: str = ""
    category: str = ""
    tags: list[str] = field(default_factory=list)
    alert: Optional[str] = None
    source: Optional[str] = None


@dataclass
class WeatherData:
    """Represents aggregated weather data."""

    current_temp: Optional[str] = None
    current_condition: Optional[str] = None
    avg_temp_today: Optional[str] = None
    avg_monthly_rainfall: Optional[str] = None
    current_monthly_rainfall: Optional[str] = None
    forecast_periods: list[dict] = field(default_factory=list)
    station_rows: list[dict] = field(default_factory=list)
    lake_rows: list[dict] = field(default_factory=list)
    source: Optional[str] = None


@dataclass
class LakeData:
    """Represents reservoir/lake level data."""

    name: str = ""
    today: Optional[str] = None
    one_week_ago: Optional[str] = None
    thirty_days_ago: Optional[str] = None
    source: Optional[str] = None


@dataclass
class AlertResult:
    """Represents a single alert evaluation result."""

    story_index: int = -1
    is_alert: bool = False
    reason: str = ""
    category: str = ""


@dataclass
class ForecastPeriod:
    """Represents a single forecast period from NWS."""

    name: str = ""
    temperature: Optional[str] = None
    winds: Optional[str] = None
    short_forecast: Optional[str] = None


@dataclass
class BriefOutput:
    """Represents a generated brief section output."""

    title: str = ""
    content: str = ""
    story_count: int = 0
    category: str = ""
    tags: list[str] = field(default_factory=list)
