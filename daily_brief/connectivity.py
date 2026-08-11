"""
Connectivity probes.
Runs lightweight reachability checks against external services.
Called after config validation, before pipeline Phase 1.
"""

from __future__ import annotations

import asyncio
import sys
import time
from urllib.parse import quote_plus, urlsplit

import aiohttp

from daily_brief.config import (
    CATEGORIES,
    OLLAMA_HOST,
    RSS_BASE,
    RSS_PARAMS,
    USER_AGENT,
    WEATHER_LAKE_URLS,
    WEATHER_LAT,
    WEATHER_LON,
    WEATHER_POINT_URL,
)


def _ensure_v1(base: str) -> str:
    return base if "/v1" in base else f"{base}/v1"


def _headers() -> dict:
    return {"User-Agent": USER_AGENT}


def _result(ok: bool, message: str, duration_ms: int | None) -> dict:
    return {"ok": ok, "message": message, "duration_ms": duration_ms}


def _safe_netloc(url: str) -> str:
    """Return the netloc of a URL, or the original URL if parsing fails."""
    try:
        parsed = urlsplit(url)
        return parsed.netloc or url
    except Exception:
        return url


async def check_llm(session: aiohttp.ClientSession, timeout: float = 5.0) -> dict:
    url = _ensure_v1(OLLAMA_HOST.rstrip("/")) + "/models"
    t0 = time.time()
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout), headers=_headers()
        ) as resp:
            elapsed_ms = int((time.time() - t0) * 1000)
            if resp.status == 200:
                return _result(True, f"LLM host reachable ({url})", elapsed_ms)
            return _result(False, f"LLM host returned HTTP {resp.status} ({url})", elapsed_ms)
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return _result(False, f"LLM host unreachable: {e} ({url})", elapsed_ms)


async def check_rss(session: aiohttp.ClientSession, timeout: float = 5.0) -> dict:
    sample_query = CATEGORIES[0][1] if CATEGORIES else "world news"
    encoded_query = quote_plus(sample_query, safe="")
    url = f"{RSS_BASE}{encoded_query}{RSS_PARAMS}"
    t0 = time.time()
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout), headers=_headers()
        ) as resp:
            elapsed_ms = int((time.time() - t0) * 1000)
            if resp.status in (200, 206):
                return _result(True, f"RSS feed reachable ({url.split('?')[0]})", elapsed_ms)
            return _result(False, f"RSS feed returned HTTP {resp.status} ({url})", elapsed_ms)
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return _result(False, f"RSS feed unreachable: {e}", elapsed_ms)


async def check_weather(session: aiohttp.ClientSession, timeout: float = 5.0) -> dict:
    url = WEATHER_POINT_URL.format(lat=WEATHER_LAT, lon=WEATHER_LON)
    t0 = time.time()
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout), headers=_headers()
        ) as resp:
            elapsed_ms = int((time.time() - t0) * 1000)
            if resp.status == 200:
                return _result(True, f"Weather.gov reachable ({url})", elapsed_ms)
            return _result(False, f"Weather.gov returned HTTP {resp.status} ({url})", elapsed_ms)
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return _result(False, f"Weather.gov unreachable: {e} ({url})", elapsed_ms)


async def check_openmeteo(session: aiohttp.ClientSession, timeout: float = 5.0) -> dict:
    url = "https://geocoding-api.open-meteo.com/api/docs"
    t0 = time.time()
    try:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout), headers=_headers()
        ) as resp:
            elapsed_ms = int((time.time() - t0) * 1000)
            if resp.status == 200:
                return _result(True, f"Open-Meteo reachable ({url})", elapsed_ms)
            return _result(False, f"Open-Meteo returned HTTP {resp.status} ({url})", elapsed_ms)
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return _result(False, f"Open-Meteo unreachable: {e} ({url})", elapsed_ms)


async def check_wunderground(session: aiohttp.ClientSession, timeout: float = 5.0) -> dict:
    url = "https://www.wunderground.com/"
    t0 = time.time()
    try:
        async with session.head(
            url, timeout=aiohttp.ClientTimeout(total=timeout), headers=_headers()
        ) as resp:
            elapsed_ms = int((time.time() - t0) * 1000)
            if resp.status in (200, 301, 302):
                return _result(True, f"Wunderground reachable ({url})", elapsed_ms)
            return _result(False, f"Wunderground returned HTTP {resp.status} ({url})", elapsed_ms)
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return _result(False, f"Wunderground unreachable: {e} ({url})", elapsed_ms)


async def check_lakes(session: aiohttp.ClientSession, timeout: float = 5.0) -> dict:
    lake_urls = list(WEATHER_LAKE_URLS.values()) if WEATHER_LAKE_URLS else []
    url = lake_urls[0] if lake_urls else "https://waterdatafortexas.org/"
    t0 = time.time()
    try:
        async with session.head(
            url, timeout=aiohttp.ClientTimeout(total=timeout), headers=_headers()
        ) as resp:
            elapsed_ms = int((time.time() - t0) * 1000)
            if resp.status in (200, 301, 302):
                return _result(True, f"Lakes source reachable ({_safe_netloc(url)})", elapsed_ms)
            return _result(False, f"Lakes source returned HTTP {resp.status} ({url})", elapsed_ms)
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return _result(False, f"Lakes source unreachable: {e} ({url})", elapsed_ms)


CHECK_LIST = [
    ("LLM Host", check_llm),
    ("RSS Feed", check_rss),
    ("Weather.gov", check_weather),
]

SMOKE_TEST_CHECKS = [
    ("LLM Host", check_llm),
    ("RSS Feed", check_rss),
    ("Weather.gov", check_weather),
    ("Open-Meteo", check_openmeteo),
    ("Wunderground", check_wunderground),
    ("Lakes", check_lakes),
]


async def _wrapped(name: str, fn, session: aiohttp.ClientSession, timeout: float):
    """Run a single check with timeout wrapping and name field."""
    try:
        res = await asyncio.wait_for(fn(session, timeout), timeout=timeout)
        res["name"] = name
        return res
    except asyncio.TimeoutError:
        return {
            "name": name,
            "ok": False,
            "message": f"Timeout after {timeout}s",
            "duration_ms": int(timeout * 1000),
        }
    except Exception as e:
        return {"name": name, "ok": False, "message": str(e), "duration_ms": None}


async def run_all_checks(timeout: float = 5.0) -> list[dict]:
    """Run standard 3 connectivity checks (LLM, RSS, Weather) in parallel, returning results with name field."""
    async with aiohttp.ClientSession() as session:
        return await asyncio.gather(
            *[_wrapped(name, fn, session, timeout) for name, fn in CHECK_LIST]
        )


async def run_smoke_test(timeout: float = 5.0) -> list[dict]:
    """Run full 6 connectivity checks (including Open-Meteo, Wunderground, Lakes) in parallel."""
    async with aiohttp.ClientSession() as session:
        return await asyncio.gather(
            *[_wrapped(name, fn, session, timeout) for name, fn in SMOKE_TEST_CHECKS]
        )


def format_results(results: list[dict], labels: list[str] = None) -> str:
    """Console-friendly output for connectivity results.

    Uses result["name"] when present; falls back to *labels* list if provided;
    otherwise falls back to "Check N".
    """
    lines = ["\nConnectivity Checks:"]
    lines.append("-" * 62)
    ok_count = 0
    total = len(results)
    label_iter = iter(labels) if labels else None
    for i, res in enumerate(results):
        label = (
            res.get("name") or (next(label_iter, None) if label_iter else None) or f"Check {i + 1}"
        )
        status = "OK" if res["ok"] else "WARN"
        icon = "+" if res["ok"] else "!"
        if res["ok"]:
            ok_count += 1
        ms = f"{res['duration_ms']}ms" if res["duration_ms"] is not None else "N/A"
        lines.append(f"  [{icon}] {label:<16} {status:<6} ({ms})")
        if not res["ok"]:
            lines.append(f"       {res['message']}")
    lines.append("-" * 62)
    failed = total - ok_count
    lines.append(f"  Result: {ok_count}/{total} passed, {failed} warning(s)")
    return "\n".join(lines)


def report(results: list[dict], file=sys.stderr) -> bool:
    """Print formatted results. Returns True if all passed."""
    print(format_results(results), file=file)
    return all(r["ok"] for r in results)
