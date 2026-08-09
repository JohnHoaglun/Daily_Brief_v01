"""
Daily Brief v1.0.127 — Utilities
=================================
Helper functions used throughout the pipeline. No config dependencies.
"""

from __future__ import annotations

import re
from typing import Any, Optional

_HTML_TAG_RE = re.compile(r"<.*?>")


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
    return _HTML_TAG_RE.sub("", html_text).strip()


def _present_weather_value(value, fallback="Unavailable") -> str:
    """Present weather value for display, handling None and placeholder values."""
    if value is None:
        return fallback
    try:
        text = str(value).strip()
        if not text or text.lower() in {"none", "n/a", "na"}:
            return fallback
        # "Dynamic" is a valid placeholder used for forecasted periods
        return text.replace("|", "&#124;")
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


def _extract_first_match(text: str, patterns: list) -> Optional[str]:
    """Return first regex match group from text against multiple patterns."""
    if not text:
        return None
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1)
    return None


def is_obituary_title(title: str) -> bool:
    """Check if a title contains obituary-related keywords."""
    if not title:
        return False
    keywords = ["obituary", "passed away", "death notice", "funeral services for", "memorial service for"]
    title_lower = title.lower()
    return any(kw in title_lower for kw in keywords)


def is_realt_estate_title(title: str) -> bool:
    """Check if a title contains real estate markers that should be filtered out."""
    if not title:
        return False
    realtor_keywords = [
        "realtor", "zillow", "redfin", "listing", "for sale", "house for",
        "home for", "property", "$"
    ]
    title_lower = title.lower()
    return any(keyword in title_lower for keyword in realtor_keywords)


def _coerce_temperature_f(val):
    """Safely convert temperature string/none to float and sanity check."""
    if val is None:
        return None
    try:
        clean_val = re.sub(r"[^\d.]", "", str(val))
        if not clean_val:
            return None
        temp = float(clean_val)
        if temp < -50 or temp > 140:
            return None
        return temp
    except (ValueError, TypeError):
        return None


def build_context(story: Any, preview_chars: int = 600) -> str:
    """Build text context for a single story.

    Returns up to *preview_chars* characters. Prefers ``story.context``
    (extracted article text) when it is at least 50 characters; otherwise falls
    back to ``snippet``, ``title``, and ``category``.
    """
    context = story.context
    if context and len(str(context).strip()) >= 50:
        return str(context).strip()[:preview_chars]

    parts = [
        v.strip()
        for v in (story.snippet, story.title)
        if v and len((v or "").strip()) > 0
    ]

    if not parts:
        return f"{story.category}: {story.title}"

    inner = "\n---\n".join(parts + [f"Category: {story.category}"])
    return inner[:preview_chars]
