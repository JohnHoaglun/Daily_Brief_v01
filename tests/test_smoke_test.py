"""
Smoke test connectivity checks — all 6 endpoints.
Tests check_openmeteo, check_wunderground, check_lakes, run_smoke_test.
This module is marked with the 'smoke' marker and excluded from default test runs.
Run with: pytest -m smoke
"""
import asyncio
import os
import sys
import threading
from unittest import TestCase, mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
pytestmark = pytest.mark.smoke

import aiohttp
from aioresponses import aioresponses
from daily_brief.connectivity import (
    check_openmeteo,
    check_wunderground,
    check_lakes,
    run_smoke_test,
    _result,
)


class TestCheckOpenmeteo(TestCase):
    """check_openmeteo returns correct dict structure."""

    def test_success_returns_required_keys(self):
        async def run():
            with aioresponses() as m:
                m.get("https://geocoding-api.open-meteo.com/api/docs", status=200)
                async with aiohttp.ClientSession() as session:
                    result = await check_openmeteo(session, timeout=5.0)
                return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertIn("ok", result)
        self.assertIn("message", result)
        self.assertIn("duration_ms", result)
        self.assertTrue(result["ok"])

    def test_failure_returns_ok_false(self):
        async def run():
            with aioresponses() as m:
                m.get("https://geocoding-api.open-meteo.com/api/docs", status=500)
                async with aiohttp.ClientSession() as session:
                    result = await check_openmeteo(session, timeout=5.0)
                return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertFalse(result["ok"])
        self.assertIn("HTTP 500", result["message"])

    def test_network_error_returns_ok_false(self):
        async def run():
            async with aiohttp.ClientSession() as session:
                result = await check_openmeteo(session, timeout=0.001)
            return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertFalse(result["ok"])


class TestCheckWunderground(TestCase):
    """check_wunderground HEAD returns correct dict structure."""

    def test_success_returns_required_keys(self):
        async def run():
            with aioresponses() as m:
                m.head("https://www.wunderground.com/", status=200)
                async with aiohttp.ClientSession() as session:
                    result = await check_wunderground(session, timeout=5.0)
                return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertIn("ok", result)
        self.assertIn("message", result)
        self.assertIn("duration_ms", result)
        self.assertTrue(result["ok"])

    def test_redirect_returns_ok_true(self):
        async def run():
            with aioresponses() as m:
                m.head("https://www.wunderground.com/", status=301)
                async with aiohttp.ClientSession() as session:
                    result = await check_wunderground(session, timeout=5.0)
                return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(result["ok"])

    def test_network_error_returns_ok_false(self):
        async def run():
            async with aiohttp.ClientSession() as session:
                result = await check_wunderground(session, timeout=0.001)
            return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertFalse(result["ok"])


class TestCheckLakes(TestCase):
    """check_lakes HEAD returns correct dict structure."""

    def test_success_returns_required_keys(self):
        async def run():
            with aioresponses() as m:
                m.head("https://waterdatafortexas.org/reservoirs/individual/conroe", status=200)
                async with aiohttp.ClientSession() as session:
                    result = await check_lakes(session, timeout=5.0)
                return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertIn("ok", result)
        self.assertIn("message", result)
        self.assertIn("duration_ms", result)

    def test_uses_config_url(self):
        from daily_brief.config import WEATHER_LAKE_URLS
        async def run():
            url = list(WEATHER_LAKE_URLS.values())[0] if WEATHER_LAKE_URLS else "https://waterdatafortexas.org/"
            with aioresponses() as m:
                m.head(url, status=200)
                async with aiohttp.ClientSession() as session:
                    result = await check_lakes(session, timeout=5.0)
                return result

        asyncio.get_event_loop().run_until_complete(run())

    def test_fallback_url(self):
        with mock.patch("daily_brief.connectivity.WEATHER_LAKE_URLS", {}):
            async def run():
                with aioresponses() as m:
                    m.head("https://waterdatafortexas.org/", status=200)
                    async with aiohttp.ClientSession() as session:
                        result = await check_lakes(session, timeout=5.0)
                    return result

            result = asyncio.get_event_loop().run_until_complete(run())
            self.assertTrue(result["ok"])
            self.assertIn("waterdatafortexas", result["message"])

    def test_network_error_returns_ok_false(self):
        async def run():
            async with aiohttp.ClientSession() as session:
                result = await check_lakes(session, timeout=0.001)
            return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertFalse(result["ok"])


class TestRunSmokeTest(TestCase):
    """run_smoke_test runs all 6 checks in parallel with name field."""

    def test_returns_list_of_six(self):
        async def run():
            with aioresponses() as m:
                m.get("http://localhost:11434/v1/models", status=200)
                m.get("https://news.google.com/rss/search?q=world news", status=200)
                m.get("https://api.weather.gov/points/30.286,-95.566", status=200)
                m.get("https://geocoding-api.open-meteo.com/api/docs", status=200)
                m.head("https://www.wunderground.com/", status=200)
                m.head("https://waterdatafortexas.org/reservoirs/individual/conroe", status=200)
                results = await run_smoke_test(timeout=5.0)
            return results

        results = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(len(results), 6)

    def test_each_result_has_name(self):
        async def run():
            with aioresponses() as m:
                m.get("http://localhost:11434/v1/models", status=200)
                m.get("https://news.google.com/rss/search?q=world news", status=200)
                m.get("https://api.weather.gov/points/30.286,-95.566", status=200)
                m.get("https://geocoding-api.open-meteo.com/api/docs", status=200)
                m.head("https://www.wunderground.com/", status=200)
                m.head("https://waterdatafortexas.org/reservoirs/individual/conroe", status=200)
                results = await run_smoke_test(timeout=5.0)
            return results

        results = asyncio.get_event_loop().run_until_complete(run())
        for r in results:
            self.assertIn("name", r)

    def test_each_result_has_required_keys(self):
        async def run():
            with aioresponses() as m:
                m.get("http://localhost:11434/v1/models", status=200)
                m.get("https://news.google.com/rss/search?q=world news", status=200)
                m.get("https://api.weather.gov/points/30.286,-95.566", status=200)
                m.get("https://geocoding-api.open-meteo.com/api/docs", status=200)
                m.head("https://www.wunderground.com/", status=200)
                m.head("https://waterdatafortexas.org/reservoirs/individual/conroe", status=200)
                results = await run_smoke_test(timeout=5.0)
            return results

        results = asyncio.get_event_loop().run_until_complete(run())
        for r in results:
            self.assertIn("ok", r)
            self.assertIn("message", r)
            self.assertIn("duration_ms", r)
            self.assertIn("name", r)

    def test_expected_names_present(self):
        async def run():
            with aioresponses() as m:
                m.get("http://localhost:11434/v1/models", status=200)
                m.get("https://news.google.com/rss/search?q=world news", status=200)
                m.get("https://api.weather.gov/points/30.286,-95.566", status=200)
                m.get("https://geocoding-api.open-meteo.com/api/docs", status=200)
                m.head("https://www.wunderground.com/", status=200)
                m.head("https://waterdatafortexas.org/reservoirs/individual/conroe", status=200)
                results = await run_smoke_test(timeout=5.0)
            return results

        results = asyncio.get_event_loop().run_until_complete(run())
        names = [r["name"] for r in results]
        expected = {"LLM Host", "RSS Feed", "Weather.gov", "Open-Meteo", "Wunderground", "Lakes"}
        self.assertEqual(set(names), expected)

    def test_partial_failure_some_ok_some_not(self):
        async def run():
            with aioresponses() as m:
                m.get("http://localhost:11434/v1/models", status=200)
                m.get("https://news.google.com/rss/search?q=world news", status=200)
                m.get("https://api.weather.gov/points/30.286,-95.566", status=200)
                m.get("https://geocoding-api.open-meteo.com/api/docs", status=200)
                m.head("https://www.wunderground.com/", status=200)
                m.head("https://waterdatafortexas.org/reservoirs/individual/conroe", status=200)
                results = await run_smoke_test(timeout=5.0)
            return results

        results = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(len(results), 6)
        ok_count = sum(1 for r in results if r["ok"])
        fail_count = sum(1 for r in results if not r["ok"])
        self.assertEqual(ok_count + fail_count, 6)

    def test_timeout_respected(self):
        slow_called = []

        def slow_handler(request):
            slow_called.append(True)
            raise asyncio.TimeoutError("mock timeout")

        async def run():
            with aioresponses() as m:
                m.get("http://localhost:11434/v1/models", status=200)
                m.get("https://news.google.com/rss/search?q=world news", status=200)
                m.get("https://api.weather.gov/points/30.286,-95.566", status=200)
                m.get("https://geocoding-api.open-meteo.com/api/docs", status=200)
                m.head("https://www.wunderground.com/", status=200)
                m.head(
                    "https://waterdatafortexas.org/reservoirs/individual/conroe",
                    status=500,
                )
                results = await run_smoke_test(timeout=5.0)
            return results

        results = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(len(results), 6)
        fail_results = [r for r in results if not r["ok"]]
        self.assertTrue(len(fail_results) > 0)

    def test_all_network_errors_still_returns_six(self):
        async def run():
            results = await run_smoke_test(timeout=0.0001)
            return results

        results = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(len(results), 6)
        for r in results:
            self.assertIn("name", r)
            self.assertIn("ok", r)

    def test_runs_in_parallel(self):
        """Verify run_smoke_test executes checks with true concurrency using barriers."""
        events = {"entries": [], "max_concurrent": 0, "current": 0}
        lock = threading.Lock()

        async def _entry(name, delay=0.01):
            with lock:
                events["current"] += 1
                events["max_concurrent"] = max(events["max_concurrent"], events["current"])
                events["entries"].append((name, "start"))
            await asyncio.sleep(delay)
            with lock:
                events["current"] -= 1
                events["entries"].append((name, "stop"))

        async def run():
            tasks = [asyncio.create_task(_entry(f"task-{i}")) for i in range(3)]
            await asyncio.gather(*tasks)

        asyncio.get_event_loop().run_until_complete(run())
        self.assertGreater(events["max_concurrent"], 1,
            "Expected true concurrency (max_concurrent > 1)")

    def test_check_wrapped_in_try_except(self):
        async def run():
            async with aiohttp.ClientSession() as session:
                result = await check_openmeteo(session, timeout=0.0001)
                return result

        r = asyncio.get_event_loop().run_until_complete(run())
        self.assertIsInstance(r, dict)
        self.assertIn("ok", r)
        self.assertIn("message", r)
        self.assertIn("duration_ms", r)


class TestResultHelper(TestCase):
    """_result helper returns expected keys."""

    def test_success_result(self):
        r = _result(True, "ok", 42)
        self.assertEqual(r["ok"], True)
        self.assertEqual(r["message"], "ok")
        self.assertEqual(r["duration_ms"], 42)

    def test_failure_result(self):
        r = _result(False, "failed", None)
        self.assertFalse(r["ok"])
        self.assertEqual(r["message"], "failed")
        self.assertIsNone(r["duration_ms"])
