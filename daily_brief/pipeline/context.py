"""
Daily Brief — Pipeline shared context and state.

Module-level globals shim for test fixtures, RunContext dataclass,
logger setup/teardown, weather normalization, event-loop lag monitor,
and shared utility functions.
"""

import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from daily_brief.config import (
    LOG_DIR,
    NEWS_DIR,
    OLLAMA_HOST,
    TIMEZONE,
)
from daily_brief.llm import create_llm_client


try:
    ACTIVE_TIMEZONE = ZoneInfo(TIMEZONE)
except Exception:
    ACTIVE_TIMEZONE = timezone.utc
    TIMEZONE = "UTC"


DEFAULT_CONTENT_AGE_WINDOW_HOURS = 48


@dataclass
class RunContext:
    """Per-run state — isolates mutable pipeline globals for concurrent safety."""

    phase_timings: Dict[str, float] = field(default_factory=dict)
    run_logfile: Optional[str] = None
    output_dir: Optional[str] = None
    input_log_dir: Optional[str] = None
    input_news_dir: Optional[str] = None
    article_max_concurrency: int = 3  # default: from config
    llm_client: Any = None
    reservation: Optional[Any] = None


class _RunTimestampFormatter(logging.Formatter):
    """Emits [YYYY-MM-DD HH:MM:SS] msg."""

    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    def format(self, record):
        return f"[{self.formatTime(record)}] {record.getMessage()}"


def _setup_run_logger(logfile: str, name: str = "daily_brief") -> logging.Logger:
    """Create a dedicated logger with file + stderr handlers for one run."""
    logger = logging.getLogger(f"{name}_{id(logfile)}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False
    formatter = _RunTimestampFormatter()
    os.makedirs(os.path.dirname(logfile), exist_ok=True)
    fh = logging.FileHandler(logfile, encoding="utf-8")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(formatter)
    logger.addHandler(sh)
    return logger


def _teardown_run_logger(logger: logging.Logger) -> None:
    """Close and remove all handlers from a run-scoped logger."""
    for h in list(logger.handlers):
        try:
            h.close()
        except Exception:
            pass
    logger.handlers.clear()


from daily_brief.utils import _coerce_temperature_f as _coerce_temperature_f  # noqa: F401


def _normalize_weather_for_rendering(weather_data):
    """Normalize weather data for safe rendering."""
    if weather_data is None:
        return {
            "forecast": [
                {
                    "date": "N/A",
                    "day": "N/A",
                    "night": "N/A",
                    "high": "N/A",
                    "low": "N/A",
                    "precip": "N/A",
                    "wind": "N/A",
                }
            ] * 3,
            "station": {},
            "lakes": {},
        }
    if not isinstance(weather_data, dict):
        return {
            "forecast": [
                {
                    "date": "N/A",
                    "day": "N/A",
                    "night": "N/A",
                    "high": "N/A",
                    "low": "N/A",
                    "precip": "N/A",
                    "wind": "N/A",
                }
            ] * 3,
            "station": {},
            "lakes": {},
        }
    result = dict(weather_data)
    if "forecast" not in result or not isinstance(result.get("forecast"), list):
        result["forecast"] = [
            {
                "date": "N/A",
                "day": "N/A",
                "night": "N/A",
                "high": "N/A",
                "low": "N/A",
                "precip": "N/A",
                "wind": "N/A",
            }
        ] * 3
    if "station" not in result or not isinstance(result.get("station"), dict):
        result["station"] = {}
    if "lakes" not in result or not isinstance(result.get("lakes"), dict):
        result["lakes"] = {}
    return result


class _EventLoopLagMonitor:
    """Lightweight event-loop lag monitor."""

    def __init__(self, interval_s: float):
        self._interval = interval_s
        self._samples: list[float] = []
        self._task: Optional[asyncio.Task[None]] = None
        self._stop_event: Optional[asyncio.Event] = None

    def start(self):
        if self._task is not None and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._samples = []
        self._task = asyncio.create_task(self._run())

    def stop(self) -> list[float]:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None and not self._task.done():
            self._task.cancel()
        return list(self._samples)

    async def stop_async(self) -> list[float]:
        self.stop()
        if self._task is not None and not self._task.done():
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        return list(self._samples)

    async def _run(self):
        while not self._stop_event.is_set():
            deadline = time.monotonic() + self._interval
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval)
                return
            except asyncio.TimeoutError:
                pass
            elapsed = time.monotonic() - deadline
            self._samples.append(max(0, elapsed))


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Calculate the given percentile from sorted values."""
    if not sorted_values:
        return 0.0
    sorted_v = sorted(sorted_values)
    idx = (pct / 100) * (len(sorted_v) - 1)
    lower = int(idx)
    upper = min(lower + 1, len(sorted_v) - 1)
    frac = idx - lower
    return sorted_v[lower] + (sorted_v[upper] - sorted_v[lower]) * frac


def _count_extracted(stories: list[Any]) -> int:
    """Count stories that have populated context from extraction."""
    return sum(1 for s in stories if getattr(s, "context", None))
