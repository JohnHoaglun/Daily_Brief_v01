"""
Daily Brief v1.0.127 — HTTP Client
==================================
Async HTTP fetch functions with session management.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Sequence

import aiohttp

logger = logging.getLogger(__name__)


HTTP_RETRY_ATTEMPTS = 3
HTTP_RETRY_BACKOFF = [0.25, 0.5]
HTTP_RETRYABLE_STATUSES = {429, 502, 503, 504}
HTTP_RETRYABLE_EXCEPTIONS = (asyncio.TimeoutError, aiohttp.ClientError)


_DEFAULT_USER_AGENT = "DailyBrief/1.0"


async def _safe_json_parse(text: str):
    """Safely parse text as JSON, logging decode errors."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(f"[json decode error] JSON parse failed: {exc}")
        return None


def _is_status_accepted(status: int, status_predicate=None) -> bool:
    """Check if status is acceptable, using predicate if provided, else status == 200."""
    if status_predicate is not None and callable(status_predicate):
        return status_predicate(status)
    return status == 200


def _should_retry(exc_or_status) -> bool:
    """Determine if failure is retryable."""
    if isinstance(exc_or_status, int):
        return exc_or_status in HTTP_RETRYABLE_STATUSES
    return isinstance(exc_or_status, HTTP_RETRYABLE_EXCEPTIONS)


async def _request_with_retry(
    session: aiohttp.ClientSession,
    url: str,
    user_agent: str = _DEFAULT_USER_AGENT,
    timeout: int = 15,
    status_predicate=None,
    max_attempts: int = HTTP_RETRY_ATTEMPTS,
    backoff: Sequence = None,
    **params: Any,
):
    """Fetch URL with bounded retry on transient failures.

    Returns:
        response_text: str | None (None on failure/exhausted)
        last_status: int | None
        attempts_made: int
    """
    if backoff is None:
        backoff = HTTP_RETRY_BACKOFF

    kwargs: Dict[str, Any] = dict(
        headers={"User-Agent": user_agent},
        timeout=aiohttp.ClientTimeout(total=timeout),
    )
    kwargs.update(params)

    last_status = None
    for attempt in range(max_attempts):
        try:
            async with session.get(url, **kwargs) as resp:
                status = resp.status
                last_status = status
                if _is_status_accepted(status, status_predicate):
                    return await resp.text(), status, attempt + 1
                if attempt < max_attempts - 1 and _should_retry(status):
                    delay = backoff[attempt] if attempt < len(backoff) else backoff[-1]
                    logger.warning(f"[http retry] attempt {attempt + 1}/{max_attempts} — {url} status {status}, retrying in {delay}s")
                    await asyncio.sleep(delay)
                    continue
                logger.warning(f"[http error] {url} status {status} (attempt {attempt + 1}/{max_attempts})")
                return None, status, attempt + 1
        except HTTP_RETRYABLE_EXCEPTIONS as exc:
            last_status = None
            if attempt < max_attempts - 1:
                delay = backoff[attempt] if attempt < len(backoff) else backoff[-1]
                logger.warning(f"[http retry] attempt {attempt + 1}/{max_attempts} — {url}: {exc}, retrying in {delay}s")
                await asyncio.sleep(delay)
                continue
            logger.error(f"[http error] {url}: {exc} (attempt {attempt + 1}/{max_attempts})")
            return None, None, attempt + 1
        except Exception as exc:
            logger.error(f"[http error] {url}: {exc} (attempt {attempt + 1}/{max_attempts})")
            return None, last_status, attempt + 1

    return None, last_status, max_attempts


async def _fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    user_agent: str = _DEFAULT_USER_AGENT,
    timeout: int = 15,
    **params: Any,
) -> Optional[Any]:
    """Fetch JSON from URL, return the parsed value or None on failure.

    The return value may be any valid JSON value (dict, list, str, int, float, bool, None).
    Consumers must validate the return type (e.g. isinstance(result, dict)) before
    calling dict methods like .get() or .keys().

    Accepts arbitrary **params forwarded to session.get() (e.g. params=, ssl=).
    """
    try:
        text, status, _ = await _request_with_retry(
            session, url, user_agent=user_agent, timeout=timeout, **params
        )
        if text is not None:
            return await _safe_json_parse(text)
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
    return (await _request_with_retry(
        session, url, user_agent=user_agent, timeout=timeout, **params
    ))[0]


async def _create_session() -> aiohttp.ClientSession:
    """Create and return a new aiohttp ClientSession."""
    return aiohttp.ClientSession()


async def _close_session(session: aiohttp.ClientSession) -> None:
    """Close an aiohttp ClientSession."""
    if session and not session.closed:
        await session.close()
