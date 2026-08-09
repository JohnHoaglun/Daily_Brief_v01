"""
Daily Brief v1.0.131 — Models
=============================
Canonical story model (promoted from StoryPipelineState). Weather, lake,
forecast, and brief output dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Story:
    """Canonical story model — pipeline work item from RSS through LLM to report."""

    title: str = ""
    link: str = ""
    snippet: str = ""
    category: str = ""
    pub_dt: Optional[str] = None
    context: Optional[str] = None
    summary: Optional[str] = None


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
