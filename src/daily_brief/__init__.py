"""
Daily Brief v1.0.104 — Package Exports
=======================================
Public API for the daily_brief package.
"""

from daily_brief.models import (
    Story,
    WeatherData,
    LakeData,
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
    _coerce_temperature_f,
    build_context,
)
from daily_brief.http_client import _fetch_json, _fetch_text
from daily_brief.config_validator import validate_config

__all__ = [
    # Models
    "Story",
    "WeatherData",
    "LakeData",
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
    "_coerce_temperature_f",
    "build_context",
    # HTTP
    "_fetch_json",
    "_fetch_text",
    # Validation
    "validate_config",
]

__version__ = "1.0.108"
