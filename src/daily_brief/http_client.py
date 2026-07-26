"""
Daily Brief v1.0.12 — HTTP Client
==================================
Async HTTP fetch functions with session management.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)


_DEFAULT_USER_AGENT = "DailyBrief/1.0"


async def _fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    user_agent: str = _DEFAULT_USER_AGENT,
    timeout: int = 15,
    **params: Any,
) -> Optional[Dict[str, Any]]:
    """Fetch JSON from URL, return dict or None on failure.

    Accepts arbitrary **params forwarded to session.get() (e.g. params=, ssl=).
    """
    try:
        kwargs: Dict[str, Any] = dict(
            headers={"User-Agent": user_agent},
            timeout=aiohttp.ClientTimeout(total=timeout),
        )
        kwargs.update(params)
        async with session.get(url, **kwargs) as resp:
            if resp.status == 200:
                return await resp.json()
            logger.warning(f"[fetch_json error] {url} returned status {resp.status}")
            return None
    except Exception as exc:
        logger.error(f"[fetch_json error] {url}: {exc}")
        return None


async def _fetch_text(
    session: aiohttp.ClientSession,
    url: str,
    user_agent: str = _DEFAULT_USER_AGENT,
    timeout: int = 15,
    **params: Any,
) -> Optional[str]:
    """Fetch text from URL, return string or None on failure.

    Accepts arbitrary **params forwarded to session.get().
    """
    try:
        kwargs: Dict[str, Any] = dict(
            headers={"User-Agent": user_agent},
            timeout=aiohttp.ClientTimeout(total=timeout),
        )
        kwargs.update(params)
        async with session.get(url, **kwargs) as resp:
            if resp.status == 200:
                return await resp.text()
            logger.warning(f"[fetch_text error] {url} returned status {resp.status}")
            return None
    except Exception as exc:
        logger.error(f"[fetch_text error] {url}: {exc}")
        return None


async def _create_session() -> aiohttp.ClientSession:
    """Create and return a new aiohttp ClientSession."""
    return aiohttp.ClientSession()


async def _close_session(session: aiohttp.ClientSession) -> None:
    """Close an aiohttp ClientSession."""
    if session and not session.closed:
        await session.close()
