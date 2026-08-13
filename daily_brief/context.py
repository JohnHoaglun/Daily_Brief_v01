"""
Daily Brief — Run context and logging helpers.

Extracted from pipeline.py: shared RunContext dataclass, the
`_RunTimestampFormatter`, and the `_setup_run_logger`/`_teardown_run_logger`
helpers that pipeline stages import during execution.
"""

import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from daily_brief.config import (
    ARTICLE_MAX_CONCURRENCY,
    NEWS_DIR,
    LOG_DIR,
    TIMEZONE,
)
from daily_brief.lifecycle import RunReservation


@dataclass
class RunContext:
    """Per-run state — isolates mutable pipeline globals for concurrent safety."""

    phase_timings: Dict[str, float] = field(default_factory=dict)
    run_logfile: Optional[str] = None
    output_dir: Optional[str] = None
    input_log_dir: Optional[str] = None
    input_news_dir: Optional[str] = None
    article_max_concurrency: int = ARTICLE_MAX_CONCURRENCY
    llm_client: Any = None
    reservation: Optional[RunReservation] = None


class _RunTimestampFormatter(logging.Formatter):
    """Emits [YYYY-MM-DD HH:MM:SS] msg — same format as legacy _log_ctx."""

    def formatTime(self, record, datefmt=None):
        return datetime.utcfromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")

    def format(self, record):
        return f"[{self.formatTime(record)}] {record.getMessage()}"


def _setup_run_logger(logfile: str, name: str = "daily_brief") -> logging.Logger:
    """Create a dedicated logger with file + stderr handlers for one run.

    Handlers must be removed with `_teardown_run_logger` to prevent
    cross-run contamination during concurrent invocations.
    """
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


try:
    from zoneinfo import ZoneInfo

    ACTIVE_TIMEZONE = ZoneInfo(TIMEZONE)
except Exception:
    from zoneinfo import ZoneInfo

    ACTIVE_TIMEZONE = timezone.utc
    TIMEZONE = "UTC"

DEFAULT_CONTENT_AGE_WINDOW_HOURS = 48
