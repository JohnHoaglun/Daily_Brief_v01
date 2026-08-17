"""Reduced: connectivity check success and failure."""

import asyncio
import io
import unittest
from unittest import TestCase, mock

import aiohttp
from aioresponses import aioresponses

from daily_brief.connectivity import (
    _ensure_v1,
    check_lakes,
    check_llm,
    check_rss,
    check_weather,
    format_results,
    report,
    run_all_checks,
)


class TestConnectivitySuccess(TestCase):
    def test_llm_reachable(self):
        async def run():
            with mock.patch("daily_brief.connectivity.OLLAMA_HOST", "http://localhost:11434/v1"):
                with aioresponses() as m:
                    m.get("http://localhost:11434/v1/models", status=200)
                    async with aiohttp.ClientSession() as session:
                        return await check_llm(session, timeout=5.0)
        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(result["ok"])
        self.assertIn("reachable", result["message"])

    def test_rss_reachable(self):
        async def run():
            with mock.patch("daily_brief.connectivity.CATEGORIES", [("World News", "testq", 10)]):
                with mock.patch("daily_brief.connectivity.RSS_BASE", "https://news.google.com/rss/search?q="):
                    with mock.patch("daily_brief.connectivity.RSS_PARAMS", "&hl=en-US"):
                        with aioresponses() as m:
                            m.get("https://news.google.com/rss/search?q=testq&hl=en-US", status=200)
                            async with aiohttp.ClientSession() as session:
                                return await check_rss(session, timeout=5.0)
        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(result["ok"])
        self.assertIn("reachable", result["message"])

    def test_weather_reachable(self):
        async def run():
            with aioresponses() as m:
                m.get("https://api.weather.gov/points/30.286,-95.566", status=200)
                async with aiohttp.ClientSession() as session:
                    return await check_weather(session, timeout=5.0)
        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(result["ok"])
        self.assertIn("reachable", result["message"])

    def test_lakes_reachable(self):
        async def run():
            with mock.patch("daily_brief.connectivity.WEATHER_LAKE_URLS", {"Conroe": "https://waterdatafortexas.org/reservoirs/individual/conroe"}):
                with aioresponses() as m:
                    m.head("https://waterdatafortexas.org/reservoirs/individual/conroe", status=200)
                    async with aiohttp.ClientSession() as session:
                        return await check_lakes(session, timeout=5.0)
        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(result["ok"])

    def test_all_checks_return_three(self):
        async def run():
            with mock.patch("daily_brief.connectivity.OLLAMA_HOST", "http://localhost:11434/v1"):
                with mock.patch("daily_brief.connectivity.RSS_BASE", "https://news.google.com/rss/search?q="):
                    with mock.patch("daily_brief.connectivity.RSS_PARAMS", "&hl=en-US&gl=US&ceid=US:en"):
                        with mock.patch("daily_brief.connectivity.CATEGORIES", [("World News", "world news", 10)]):
                            with mock.patch("daily_brief.connectivity.WEATHER_LAT", 30.286):
                                with mock.patch("daily_brief.connectivity.WEATHER_LON", -95.566):
                                    with mock.patch("daily_brief.connectivity.WEATHER_POINT_URL", "https://api.weather.gov/points/{lat},{lon}"):
                                        with aioresponses() as m:
                                            m.get("http://localhost:11434/v1/models", status=200)
                                            m.get("https://news.google.com/rss/search?q=world+news&hl=en-US&gl=US&ceid=US:en", status=200)
                                            m.get("https://api.weather.gov/points/30.286,-95.566", status=200)
                                            return await run_all_checks(timeout=5.0)
        results = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertIn("ok", r)

    def test_format_ok(self):
        results = [
            {"ok": True, "duration_ms": 10, "message": "ok"},
            {"ok": True, "duration_ms": 20, "message": "ok"},
        ]
        output = format_results(results, labels=["LLM", "RSS"])
        self.assertIn("Connectivity Checks:", output)
        self.assertIn("2/2 passed", output)

    def test_report_returns_status(self):
        ok_results = [{"ok": True, "duration_ms": 10, "message": "ok"}]
        fail_results = [{"ok": True, "duration_ms": 10, "message": "ok"}, {"ok": False, "duration_ms": 10, "message": "fail"}]
        self.assertTrue(report(ok_results, file=io.StringIO()))
        self.assertFalse(report(fail_results, file=io.StringIO()))


class TestConnectivityFailure(TestCase):
    def test_llm_http_error(self):
        async def run():
            with mock.patch("daily_brief.connectivity.OLLAMA_HOST", "http://localhost:11434/v1"):
                with aioresponses() as m:
                    m.get("http://localhost:11434/v1/models", status=500)
                    async with aiohttp.ClientSession() as session:
                        return await check_llm(session, timeout=5.0)
        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertFalse(result["ok"])
        self.assertIn("500", result["message"])

    def test_rss_http_error(self):
        async def run():
            with mock.patch("daily_brief.connectivity.CATEGORIES", [("World News", "testq", 10)]):
                with mock.patch("daily_brief.connectivity.RSS_BASE", "https://news.google.com/rss/search?q="):
                    with mock.patch("daily_brief.connectivity.RSS_PARAMS", "&hl=en-US"):
                        with aioresponses() as m:
                            m.get("https://news.google.com/rss/search?q=testq&hl=en-US", status=404)
                            async with aiohttp.ClientSession() as session:
                                return await check_rss(session, timeout=5.0)
        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertFalse(result["ok"])
        self.assertIn("404", result["message"])


class TestEnsureV1(TestCase):
    def test_already_has_and_needs_v1(self):
        self.assertEqual(_ensure_v1("http://localhost:11434/v1"), "http://localhost:11434/v1")
        self.assertEqual(_ensure_v1("http://localhost:11434"), "http://localhost:11434/v1")


if __name__ == "__main__":
    unittest.main()
