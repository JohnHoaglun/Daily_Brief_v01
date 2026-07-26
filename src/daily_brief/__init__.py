"""
Daily Brief v1.0.12 — Package Exports
======================================
Public API for the daily_brief package.
"""

from daily_brief.models import (
    Story,
    WeatherData,
    LakeData,
    AlertResult,
    ForecastPeriod,
    BriefOutput,
)
from daily_brief.utils import (
    _safe_text,
    strip_html,
    _present_weather_value,
    _clean_number,
    _safe_sentence_summary,
    _count_sentences,
    _coerce_percent,
)
from daily_brief.http_client import _fetch_json, _fetch_text

__all__ = [
    # Models
    "Story",
    "WeatherData",
    "LakeData",
    "AlertResult",
    "ForecastPeriod",
    "BriefOutput",
    # Utils
    "_safe_text",
    "strip_html",
    "_present_weather_value",
    "_clean_number",
    "_safe_sentence_summary",
    "_count_sentences",
    "_coerce_percent",
    # HTTP
    "_fetch_json",
    "_fetch_text",
]

__version__ = "1.0.12"
