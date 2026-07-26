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


async def _fetch_json(session: aiohttp.ClientSession, url: str, suffix: str = "", timeout: int = 15) -> Optional[Dict[str, Any]]:
    """Fetch JSON from URL, return dict or None on failure."""
    try:
        async with session.get(
            url,
            headers={"User-Agent": f"{suffix}"},
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status == 200:
                return await resp.json()
            logger.warning(f"[fetch_json error] {url} returned status {resp.status}")
            return None
    except Exception as exc:
        logger.error(f"[fetch_json error] {url}: {exc}")
        return None


async def _fetch_text(session: aiohttp.ClientSession, url: str, suffix: str = "", timeout: int = 15) -> Optional[str]:
    """Fetch text from URL, return string or None on failure."""
    try:
        async with session.get(
            url,
            headers={"User-Agent": f"{suffix}"},
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
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
