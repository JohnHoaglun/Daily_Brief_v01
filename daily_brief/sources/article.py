"""
Daily Brief v1.0.150 — Article Extraction
=========================================
Fetch full article text for summary context. ``build_context`` is in utils.py.

HTML parsing is offloaded to a worker thread via asyncio.to_thread.
Includes per-article fetch/parse timing instrumentation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from daily_brief.config import LLM_CONTEXT_PREVIEW_CHARS, USER_AGENT
from daily_brief.http_client import _fetch_text
from daily_brief.utils import is_obituary_title

logger = logging.getLogger(__name__)


def _parse_article_html(html: str) -> str:
    """Pure synchronous HTML-to-clean-text extraction.

    Removes script/style/nav/header/footer/aside tags, extracts and
    normalizes text, and truncates to the configured preview length.
    Safe to run in a worker thread — takes only a string, returns a string.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return " ".join(text.split())[:LLM_CONTEXT_PREVIEW_CHARS]


async def stage_extract_article(story: Any, session: aiohttp.ClientSession) -> None:
    """Fetch full article text and build story context for summarization.

    Skips obituary titles, invalid URLs, and Google News tracking links. On
    success, populates ``story.context`` with cleaned text capped at the
    configured preview length.

    HTML parsing is offloaded to a worker thread via ``asyncio.to_thread``.

    Sets timing attributes on the story for instrumentation:
    - ``extract_fetch_time_s``: seconds from fetch start to completion
    - ``extract_parse_time_s``: seconds for BeautifulSoup and text cleanup
    - ``extract_bytes``: response body length in bytes
    """
    if is_obituary_title(story.title) and story.category in ("Conroe TX News", "Houston TX News"):
        return

    url = story.link.strip()
    if not url or url == "#" or url.startswith("#"):
        return
    if "news.google.com" in url:
        return

    try:
        t_fetch = time.monotonic()
        html = await _fetch_text(session, url, user_agent=USER_AGENT, timeout=5)
        story.extract_fetch_time_s = time.monotonic() - t_fetch

        if html is None:
            logger.debug("  [extract error] '%s': fetch failed", story.title[:60])
            return

        story.extract_bytes = len(html)
        t_parse = time.monotonic()
        text = await asyncio.to_thread(_parse_article_html, html)
        story.extract_parse_time_s = time.monotonic() - t_parse
        if len(text) >= 50:
            story.context = text
    except Exception as exc:
        logger.debug("  [extract error] '%s...': %s", story.title[:60], exc)
