"""
Daily Brief v1.0.12 — Utilities
===============================
Helper functions used throughout the pipeline.
"""

from __future__ import annotations

import re
from typing import Optional


def _safe_text(value, fallback="N/A") -> str:
    """Normalize user-facing text values for markdown rendering."""
    if value is None:
        return fallback
    try:
        s = str(value).strip()
        return s if s else fallback
    except Exception:
        return fallback


def strip_html(html_text: str) -> str:
    """Remove HTML tags from text."""
    if not html_text:
        return ""
    clean = re.compile(r"<.*?>")
    return re.sub(clean, "", html_text).strip()


def _present_weather_value(value, fallback="Unavailable") -> str:
    """Present weather value for display, handling None and placeholder values."""
    if value is None:
        return fallback
    try:
        text = str(value).strip()
        if not text or text.lower() in {"none", "n/a", "na"}:
            return fallback
        # "Dynamic" is a valid placeholder used for forecasted periods
        return text
    except Exception:
        return fallback


def _clean_number(value, fallback: str = "0") -> str:
    """Extract a numeric value from a string, return as formatted string."""
    if value is None:
        return fallback
    text = _safe_text(value)
    m = re.search(r"(-?\d{1,3}(?:\.\d+)?)", text)
    if not m:
        return fallback
    try:
        val = float(m.group(1))
        return f"{int(val) if val.is_integer() else val}"
    except Exception:
        return fallback


def _safe_sentence_summary(text: str) -> str:
    """Truncate text to at most 3 sentences."""
    if not text:
        return ""
    s = re.sub(r"\s+", " ", str(text)).strip()
    s = s.replace("..", ".").strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", s)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) >= 3:
        return " ".join(parts[:3]).strip()
    return s


def _count_sentences(text: str) -> int:
    """Count sentences in text."""
    if not text:
        return 0
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", re.sub(r"\s+", " ", str(text)).strip())
    parts = [p.strip() for p in parts if p.strip()]
    return len(parts)


def _coerce_percent(value) -> Optional[str]:
    """Extract percentage from string, return as formatted string."""
    if value is None:
        return None
    text = _safe_text(value)
    m = re.match(r"^(\d+(?:\.\d+)?).*?$", text)
    if not m:
        return None
    try:
        return f"{float(m.group(1)):.1f}%"
    except Exception:
        return None
