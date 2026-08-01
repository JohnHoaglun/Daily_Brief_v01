"""
Extended connectivity tests — success paths, formatting, and edge cases.
Covers check_llm, check_rss, check_weather success/error HTTP paths,
run_all_checks, format_results, and report().
"""
import asyncio
import os
import sys
import io
from unittest import TestCase, mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import aiohttp
from aioresponses import aioresponses
from daily_brief.connectivity import (
    check_llm,
    check_rss,
    check_weather,
    check_openmeteo,
    check_wunderground,
    check_lakes,
    run_all_checks,
    run_smoke_test,
    format_results,
    report,
    _result,
    _ensure_v1,
)


def _mock_configs():
    """Patch connectivity config with known test values."""
    patches = {}
    patches["llm"] = mock.patch("daily_brief.connectivity.OLLAMA_HOST", "http://localhost:11434/v1")
    patches["rss_base"] = mock.patch("daily_brief.connectivity.RSS_BASE", "https://news.google.com/rss/search?q=")
    patches["rss_params"] = mock.patch("daily_brief.connectivity.RSS_PARAMS", "&hl=en-US&gl=US&ceid=US:en")
    patches["weather_lat"] = mock.patch("daily_brief.connectivity.WEATHER_LAT", 30.286)
    patches["weather_lon"] = mock.patch("daily_brief.connectivity.WEATHER_LON", -95.566)
    patches["weather_url"] = mock.patch("daily_brief.connectivity.WEATHER_POINT_URL", "https://api.weather.gov/points/{lat},{lon}")
    patches["categories"] = mock.patch("daily_brief.connectivity.CATEGORIES", [("World News", "world news", 10)])
    return patches


class TestCheckLLM(TestCase):
    """check_llm HTTP success and error paths."""

    def test_check_llm_success(self):
        async def run():
            with mock.patch("daily_brief.connectivity.OLLAMA_HOST", "http://localhost:11434/v1"):
                with aioresponses() as m:
                    m.get("http://localhost:11434/v1/models", status=200)
                    async with aiohttp.ClientSession() as session:
                        result = await check_llm(session, timeout=5.0)
                    return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(result["ok"])
        self.assertIn("LLM host reachable", result["message"])

    def test_check_llm_http_error(self):
        async def run():
            with mock.patch("daily_brief.connectivity.OLLAMA_HOST", "http://localhost:11434/v1"):
                with aioresponses() as m:
                    m.get("http://localhost:11434/v1/models", status=500)
                    async with aiohttp.ClientSession() as session:
                        result = await check_llm(session, timeout=5.0)
                    return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertFalse(result["ok"])
        self.assertIn("HTTP 500", result["message"])


class TestCheckRSS(TestCase):
    """check_rss HTTP success and error paths."""

    def test_check_rss_success(self):
        async def run():
            with mock.patch("daily_brief.connectivity.CATEGORIES", [("World News", "testq", 10)]):
                with mock.patch("daily_brief.connectivity.RSS_BASE", "https://news.google.com/rss/search?q="):
                    with mock.patch("daily_brief.connectivity.RSS_PARAMS", "&hl=en-US"):
                        with aioresponses() as m:
                            m.get("https://news.google.com/rss/search?q=testq&hl=en-US", status=200)
                            async with aiohttp.ClientSession() as session:
                                result = await check_rss(session, timeout=5.0)
                            return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(result["ok"])
        self.assertIn("RSS feed reachable", result["message"])

    def test_check_rss_http_error(self):
        async def run():
            with mock.patch("daily_brief.connectivity.CATEGORIES", [("World News", "testq", 10)]):
                with mock.patch("daily_brief.connectivity.RSS_BASE", "https://news.google.com/rss/search?q="):
                    with mock.patch("daily_brief.connectivity.RSS_PARAMS", "&hl=en-US"):
                        with aioresponses() as m:
                            m.get("https://news.google.com/rss/search?q=testq&hl=en-US", status=404)
                            async with aiohttp.ClientSession() as session:
                                result = await check_rss(session, timeout=5.0)
                            return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertFalse(result["ok"])
        self.assertIn("HTTP 404", result["message"])

    def test_check_rss_tls_verification_enabled(self):
        """Regression test: ssl=False was removed from check_rss session.get()."""
        import inspect
        source = inspect.getsource(check_rss)
        self.assertNotIn("ssl=False", source)
        self.assertNotIn("ssl=", source)


class TestCheckWeather(TestCase):
    """check_weather HTTP success path."""

    def test_check_weather_success(self):
        async def run():
            with aioresponses() as m:
                m.get("https://api.weather.gov/points/30.286,-95.566", status=200)
                async with aiohttp.ClientSession() as session:
                    result = await check_weather(session, timeout=5.0)
                return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(result["ok"])
        self.assertIn("Weather.gov reachable", result["message"])


class TestCheckOpenmeteo(TestCase):
    """check_openmeteo success path."""

    def test_check_openmeteo_success(self):
        async def run():
            with aioresponses() as m:
                m.get("https://geocoding-api.open-meteo.com/api/docs", status=200)
                async with aiohttp.ClientSession() as session:
                    result = await check_openmeteo(session, timeout=5.0)
                return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(result["ok"])
        self.assertIn("Open-Meteo reachable", result["message"])


class TestCheckWunderground(TestCase):
    """check_wunderground success path."""

    def test_check_wunderground_success(self):
        async def run():
            with aioresponses() as m:
                m.head("https://www.wunderground.com/", status=200)
                async with aiohttp.ClientSession() as session:
                    result = await check_wunderground(session, timeout=5.0)
                return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(result["ok"])
        self.assertIn("Wunderground reachable", result["message"])


class TestCheckLakes(TestCase):
    """check_lakes success path."""

    def test_check_lakes_success(self):
        async def run():
            with aioresponses() as m:
                m.head("https://waterdatafortexas.org/reservoirs/individual/conroe", status=200)
                async with aiohttp.ClientSession() as session:
                    result = await check_lakes(session, timeout=5.0)
                return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(result["ok"])


class TestRunAllChecks(TestCase):
    """run_all_checks returns 3 check results."""

    def test_run_all_checks_returns_three(self):
        async def run():
            mc = _mock_configs()
            with mc["llm"], mc["rss_base"], mc["rss_params"], mc["weather_lat"], mc["weather_lon"], mc["weather_url"], mc["categories"]:
                with aioresponses() as m:
                    m.get("http://localhost:11434/v1/models", status=200)
                    m.get("https://news.google.com/rss/search?q=world news&hl=en-US&gl=US&ceid=US:en", status=200)
                    m.get("https://api.weather.gov/points/30.286,-95.566", status=200)
                    results = await run_all_checks(timeout=5.0)
                return results

        results = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertIn("ok", r)
            self.assertIn("message", r)
            self.assertIn("duration_ms", r)


class TestSmokeTestTimeout(TestCase):
    """run_smoke_test handles TimeoutError gracefully."""

    def test_run_smoke_test_timeout(self):
        async def check_always_timeout(session, timeout):
            raise asyncio.TimeoutError("mock")

        async def run():
            mc = _mock_configs()
            with mc["llm"], mc["rss_base"], mc["rss_params"], mc["weather_lat"], mc["weather_lon"], mc["weather_url"], mc["categories"]:
                with mock.patch("daily_brief.connectivity.check_llm", check_always_timeout):
                    with mock.patch("daily_brief.connectivity.check_rss", check_always_timeout):
                        with mock.patch("daily_brief.connectivity.check_weather", check_always_timeout):
                            with mock.patch("daily_brief.connectivity.check_openmeteo", check_always_timeout):
                                with mock.patch("daily_brief.connectivity.check_wunderground", check_always_timeout):
                                    with mock.patch("daily_brief.connectivity.check_lakes", check_always_timeout):
                                        results = await run_smoke_test(timeout=0.01)
                                    return results

        results = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(len(results), 6)
        for r in results:
            self.assertFalse(r["ok"])
            self.assertIn("name", r)


class TestFormatResults(TestCase):
    """format_results produces console-friendly output."""

    def test_format_results_all_ok(self):
        results = [
            {"ok": True, "duration_ms": 10, "message": "ok1"},
            {"ok": True, "duration_ms": 20, "message": "ok2"},
            {"ok": True, "duration_ms": 30, "message": "ok3"},
        ]
        output = format_results(results)
        self.assertIn("Connectivity Checks:", output)
        self.assertIn("[+] LLM Host", output)
        self.assertIn("[+] RSS Feed", output)
        self.assertIn("[+] Weather.gov", output)
        self.assertIn("OK", output)
        self.assertIn("3/3 passed", output)
        self.assertIn("0 warning", output)


class TestReport(TestCase):
    """report() prints and returns pass/fail status."""

    def test_report_ok(self):
        results = [
            {"ok": True, "duration_ms": 10, "message": "ok"},
            {"ok": True, "duration_ms": 10, "message": "ok"},
            {"ok": True, "duration_ms": 10, "message": "ok"},
        ]
        out = io.StringIO()
        rv = report(results, file=out)
        self.assertTrue(rv)

    def test_report_fail(self):
        results = [
            {"ok": True, "duration_ms": 10, "message": "ok"},
            {"ok": False, "duration_ms": 10, "message": "fail"},
            {"ok": True, "duration_ms": 10, "message": "ok"},
        ]
        out = io.StringIO()
        rv = report(results, file=out)
        self.assertFalse(rv)


class TestEnsureV1(TestCase):
    """_ensure_v1 appends /v1 if missing."""

    def test_already_has_v1(self):
        self.assertEqual(_ensure_v1("http://localhost:11434/v1"), "http://localhost:11434/v1")

    def test_needs_v1(self):
        self.assertEqual(_ensure_v1("http://localhost:11434"), "http://localhost:11434/v1")
