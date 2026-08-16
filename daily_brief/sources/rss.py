"""
Daily Brief RSS Source Module
==============================
RSS feed fetching, parsing, date handling, and URL construction for
Google News RSS sources.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import cmp_to_key
from typing import Any, List, Optional, Tuple
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import aiohttp
import feedparser

from daily_brief.config import RSS_BASE, RSS_PARAMS, TIMEZONE, USER_AGENT
from daily_brief.http_client import _fetch_text
from daily_brief.utils import strip_html

logger = logging.getLogger(__name__)

try:
    _ACTIVE_TIMEZONE = ZoneInfo(TIMEZONE)
except Exception:
    _ACTIVE_TIMEZONE = timezone.utc


def normalize_title(title: str) -> str:
    """Normalize an RSS title for deduplication identity.

    Applies NFKD Unicode normalization (collapses fullwidth, decomposes
    accents, maps smart quotes) so equivalent titles produce identical
    dedup keys.  Returns lower-cased, stripped string — no truncation
    and no site-suffix stripping.
    """
    import unicodedata

    normalized = unicodedata.normalize("NFKD", title)
    return normalized.strip().lower()


def parse_feed_date(entry: dict[str, Any]) -> Optional[datetime]:
    """Parse the published / updated date of an RSS entry into a timezone-aware datetime.

    Tries feedparser-friendly formats first (via ``email.utils``),
    then falls back to a few common strftime patterns.
    """
    raw_date: Optional[str] = None
    for attr in ("published", "updated"):
        val = entry.get(attr)
        if val and isinstance(val, str) and val.strip():
            raw_date = val.strip()
            break
    if not raw_date:
        return None
    try:
        dt = parsedate_to_datetime(raw_date)
        return dt
    except Exception:
        pass
    tz = _ACTIVE_TIMEZONE
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            result = datetime.strptime(raw_date.strip(), fmt)
            return result.replace(tzinfo=tz)
        except ValueError:
            continue
    return None


def format_pub_date(raw: Optional[str | datetime]) -> Optional[str]:
    """Format a publication date into a human-readable string.

    Accepts either a datetime object or a raw string.
    """
    if not raw:
        return None
    if isinstance(raw, datetime):
        tz = raw.strftime("%Z") if raw.tzinfo else ""
        return raw.strftime(f"%Y-%m-%d %H:%M:%S {tz}").strip()
    stripped = raw.strip()
    if len(stripped) >= 10 and stripped[:4].isdigit():
        return stripped
    return stripped[:40]


def _sort_entries(
    a: Tuple[str, str, str, Optional[datetime]],
    b: Tuple[str, str, str, Optional[datetime]],
) -> float:
    """Comparator for sorting RSS entries by publication date (newest first).

    Entries with missing dates are pushed to the end of the list.
    """
    pa: Optional[datetime] = a[3]
    pb: Optional[datetime] = b[3]
    if pa is None and pb is None:
        return 0.0
    if pa is None:
        return 1.0
    if pb is None:
        return -1.0
    return (pb - pa).total_seconds()


def build_rss_url(query: str) -> str:
    """Construct a Google News RSS feed URL for *query*, encoding the value."""
    encoded = quote_plus(query, safe="")
    return f"{RSS_BASE}{encoded}{RSS_PARAMS}"


def build_rss_url_with_window(query: str, window_hours: int) -> str:
    """Construct URL with when: prefix to widen the source time window.

    Converts *window_hours* to whole days (ceiling division) for the Google News
    ``when:<days>d`` query syntax.
    """
    days = -(-window_hours // 24)
    windowed_query = f"when:{days}d {query}"
    encoded = quote_plus(windowed_query, safe="")
    return f"{RSS_BASE}{encoded}{RSS_PARAMS}"


async def fetch_feed(
    session: aiohttp.ClientSession,
    name: str,
    rss_url: str,
    max_stories: Optional[int] = None,
) -> Tuple[str, List[Tuple[str, str, str, Optional[datetime]]]]:
    """Fetch and parse a single RSS feed.

    Returns ``(name, entries)`` where each entry is a 4-tuple of
    ``(title, link, plain_snippet, pub_dt)``.
    """
    try:
        text = await _fetch_text(
            session,
            rss_url,
            user_agent=USER_AGENT,
            timeout=10,
            status_predicate=lambda s: 200 <= s < 300,
            max_bytes=1 * 1024 * 1024,
        )
        if text is None:
            logger.warning(
                "feed fetch failed (%s): %s",
                name,
                rss_url,
            )
            return (name, [])
        feed = feedparser.parse(text)
        entries: List[Tuple[str, str, str, Optional[datetime]]] = []
        for e in feed.entries:
            title = (e.get("title", "") or "").strip() if isinstance(e.get("title"), str) else ""
            link = e.get("link") or "#"
            raw = (
                (e.get("summary") or e.get("description") or "").strip()
                if isinstance(e.get("summary"), str) and e["summary"]
                else ""
            )
            pub_dt = parse_feed_date(e)
            plain_snippet = strip_html(raw)
            if title and link:
                entries.append((title, link, plain_snippet, pub_dt))

        entries.sort(key=cmp_to_key(_sort_entries))
        if max_stories is not None:
            entries = entries[:max_stories]

        return (name, entries)
    except Exception as e:
        logger.warning("feed fetch failed (%s): %s", name, e)
        return (name, [])
