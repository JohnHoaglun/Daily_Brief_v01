"""
Daily Brief v1.0.122 — Article Extraction
=========================================
Fetch full article text for summary context. ``build_context`` is in utils.py.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

from daily_brief.config import LLM_CONTEXT_PREVIEW_CHARS, USER_AGENT
from daily_brief.http_client import _fetch_text
from daily_brief.utils import is_obituary_title

logger = logging.getLogger(__name__)


async def stage_extract_article(story: Any, session: aiohttp.ClientSession) -> None:
    """Fetch full article text and build story context for summarization.

    Skips obituary titles, invalid URLs, and Google News tracking links. On
    success, populates ``story.context`` with cleaned text capped at the
    configured preview length.
    """
    if is_obituary_title(story.title) and story.category in ("Conroe TX News", "Houston TX News"):
        return

    url = story.link.strip()
    if not url or url == "#" or url.startswith("#"):
        return
    if "news.google.com" in url:
        return

    try:
        html = await _fetch_text(
            session, url, user_agent=USER_AGENT, timeout=5
        )
        if html is None:
            logger.debug("  [extract error] '%s': fetch failed", story.title[:60])
            return
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        text = " ".join(text.split())[:LLM_CONTEXT_PREVIEW_CHARS]
        if len(text) >= 50:
            story.context = text
    except Exception as exc:
        logger.debug("  [extract error] '%s...': %s", story.title[:60], exc)
