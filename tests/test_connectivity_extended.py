"""
Extended connectivity tests — one contract each for LLM, RSS, weather,
aggregate checks, formatter, timeout, and TLS behavior.
"""
import asyncio
import io
import unittest
from unittest import TestCase, mock

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
    _ensure_v1,
    _safe_netloc,
)


class TestCheckLLM(TestCase):
    """check_llm HTTP success and error paths."""

    def test_llm_reachable(self):
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

    def test_llm_http_error(self):
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

    def test_rss_reachable(self):
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

    def test_rss_http_error(self):
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

    def test_rss_no_ssl_false(self):
        """Regression: ssl=False must not appear in check_rss source."""
        import inspect
        source = inspect.getsource(check_rss)
        self.assertNotIn("ssl=False", source)
        self.assertNotIn("ssl=", source)


class TestCheckWeather(TestCase):
    """check_weather and alternate provider reachability."""

    def test_weather_gov_reachable(self):
        async def run():
            with aioresponses() as m:
                m.get("https://api.weather.gov/points/30.286,-95.566", status=200)
                async with aiohttp.ClientSession() as session:
                    result = await check_weather(session, timeout=5.0)
                return result
        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(result["ok"])
        self.assertIn("Weather.gov reachable", result["message"])

    def test_openmeteo_reachable(self):
        async def run():
            with aioresponses() as m:
                m.get("https://geocoding-api.open-meteo.com/api/docs", status=200)
                async with aiohttp.ClientSession() as session:
                    result = await check_openmeteo(session, timeout=5.0)
                return result
        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(result["ok"])
        self.assertIn("Open-Meteo reachable", result["message"])

    def test_wunderground_and_lakes_reachable(self):
        async def run():
            with aioresponses() as m:
                m.head("https://www.wunderground.com/", status=200)
                m.head("https://waterdatafortexas.org/reservoirs/individual/conroe", status=200)
                async with aiohttp.ClientSession() as session:
                    wr = await check_wunderground(session, timeout=5.0)
                    lr = await check_lakes(session, timeout=5.0)
                    return wr, lr
        wr, lr = asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(wr["ok"])
        self.assertIn("Wunderground reachable", wr["message"])
        self.assertTrue(lr["ok"])


def _mock_configs():
    patches = {}
    patches["llm"] = mock.patch("daily_brief.connectivity.OLLAMA_HOST", "http://localhost:11434/v1")
    patches["rss_base"] = mock.patch("daily_brief.connectivity.RSS_BASE", "https://news.google.com/rss/search?q=")
    patches["rss_params"] = mock.patch("daily_brief.connectivity.RSS_PARAMS", "&hl=en-US&gl=US&ceid=US:en")
    patches["weather_lat"] = mock.patch("daily_brief.connectivity.WEATHER_LAT", 30.286)
    patches["weather_lon"] = mock.patch("daily_brief.connectivity.WEATHER_LON", -95.566)
    patches["weather_url"] = mock.patch("daily_brief.connectivity.WEATHER_POINT_URL", "https://api.weather.gov/points/{lat},{lon}")
    patches["categories"] = mock.patch("daily_brief.connectivity.CATEGORIES", [("World News", "world news", 10)])
    return patches


class TestRunAllChecks(TestCase):

    def test_returns_three_results(self):
        async def run():
            mc = _mock_configs()
            with mc["llm"], mc["rss_base"], mc["rss_params"], mc["weather_lat"], mc["weather_lon"], mc["weather_url"], mc["categories"]:
                with aioresponses() as m:
                    m.get("http://localhost:11434/v1/models", status=200)
                    m.get("https://news.google.com/rss/search?q=world+news&hl=en-US&gl=US&ceid=US:en", status=200)
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

    def test_timeout_graceful(self):
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

    def test_format_ok_and_fail(self):
        results = [
            {"ok": True, "duration_ms": 10, "message": "ok1"},
            {"ok": True, "duration_ms": 20, "message": "ok2"},
            {"ok": True, "duration_ms": 30, "message": "ok3"},
        ]
        output = format_results(results, labels=["LLM Host", "RSS Feed", "Weather.gov"])
        self.assertIn("Connectivity Checks:", output)
        self.assertIn("[+] LLM Host", output)
        self.assertIn("3/3 passed", output)

    def test_report_returns_status(self):
        ok_results = [
            {"ok": True, "duration_ms": 10, "message": "ok"},
            {"ok": True, "duration_ms": 10, "message": "ok"},
        ]
        out = io.StringIO()
        self.assertTrue(report(ok_results, file=out))

        fail_results = [
            {"ok": True, "duration_ms": 10, "message": "ok"},
            {"ok": False, "duration_ms": 10, "message": "fail"},
        ]
        out = io.StringIO()
        self.assertFalse(report(fail_results, file=out))


class TestEnsureV1(TestCase):

    def test_already_has_and_needs_v1(self):
        self.assertEqual(_ensure_v1("http://localhost:11434/v1"), "http://localhost:11434/v1")
        self.assertEqual(_ensure_v1("http://localhost:11434"), "http://localhost:11434/v1")


class TestLLMTLS(TestCase):
    """TLS verification is not disabled for the LLM probe."""

    def test_llm_no_ssl_disabled(self):
        """check_llm must not disable TLS verification (ssl=False)."""
        import inspect
        source = inspect.getsource(check_llm)
        self.assertNotIn("ssl=False", source)
        self.assertNotIn("ssl=", source)


def _capturing_cm(method="GET", status=200):
    """Return a (captured, cm) pair where cm is callable and is an async context manager.
    Calling cm records kwargs in captured dict."""
    captured = {}
    _status = status
    _method = method

    class _Resp:
        status = _status
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    class _CM:
        async def __aenter__(self): return _Resp()
        async def __aexit__(self, *a): pass
        def __call__(self, *a, **kw):
            captured["method"] = _method
            captured["headers"] = dict(kw.get("headers", {}))
            return self

    return captured, _CM()


class TestUserAgent(TestCase):
    """All connectivity probes send the configured User-Agent."""

    def test_llm_sends_user_agent(self):
        async def run():
            with mock.patch("daily_brief.connectivity.USER_AGENT", "TestAgent/1.0"):
                captured, cm = _capturing_cm()
                fake = mock.Mock()
                fake.get = cm
                await check_llm(fake, timeout=5.0)
                return captured

        captured = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(captured["headers"]["User-Agent"], "TestAgent/1.0")

    def test_rss_sends_user_agent(self):
        async def run():
            with mock.patch("daily_brief.connectivity.CATEGORIES", [("News", "test", 10)]):
                with mock.patch("daily_brief.connectivity.RSS_BASE", "https://example.com/rss?q="):
                    with mock.patch("daily_brief.connectivity.RSS_PARAMS", "&hl=en"):
                        with mock.patch("daily_brief.connectivity.USER_AGENT", "TestAgent/1.0"):
                            captured, cm = _capturing_cm()
                            fake = mock.Mock()
                            fake.get = cm
                            await check_rss(fake, timeout=5.0)
                            return captured

        captured = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(captured["headers"]["User-Agent"], "TestAgent/1.0")

    def test_weather_sends_user_agent(self):
        async def run():
            with mock.patch("daily_brief.connectivity.USER_AGENT", "TestAgent/1.0"):
                captured, cm = _capturing_cm()
                fake = mock.Mock()
                fake.get = cm
                await check_weather(fake, timeout=5.0)
                return captured

        captured = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(captured["headers"]["User-Agent"], "TestAgent/1.0")

    def test_openmeteo_sends_user_agent(self):
        async def run():
            with mock.patch("daily_brief.connectivity.USER_AGENT", "TestAgent/1.0"):
                captured, cm = _capturing_cm()
                fake = mock.Mock()
                fake.get = cm
                await check_openmeteo(fake, timeout=5.0)
                return captured

        captured = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(captured["headers"]["User-Agent"], "TestAgent/1.0")

    def test_wunderground_sends_user_agent(self):
        async def run():
            with mock.patch("daily_brief.connectivity.USER_AGENT", "TestAgent/1.0"):
                captured, cm = _capturing_cm(method="HEAD")
                fake = mock.Mock()
                fake.head = cm
                await check_wunderground(fake, timeout=5.0)
                return captured

        captured = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(captured["headers"]["User-Agent"], "TestAgent/1.0")

    def test_lakes_sends_user_agent(self):
        async def run():
            with mock.patch("daily_brief.connectivity.WEATHER_LAKE_URLS", {"Conroe": "https://example.org/lakes"}):
                with mock.patch("daily_brief.connectivity.USER_AGENT", "TestAgent/1.0"):
                    captured, cm = _capturing_cm(method="HEAD")
                    fake = mock.Mock()
                    fake.head = cm
                    await check_lakes(fake, timeout=5.0)
                    return captured

        captured = asyncio.get_event_loop().run_until_complete(run())
        self.assertEqual(captured["headers"]["User-Agent"], "TestAgent/1.0")


class TestRSSQueryEncoding(TestCase):
    """RSS probe URL uses percent-encoding for reserved characters."""

    def test_rss_encodes_reserved_chars(self):
        async def run():
            with mock.patch("daily_brief.connectivity.CATEGORIES", [("energy & markets/ma\u00f1ana", "energy & markets/ma\u00f1ana", 10)]):
                with mock.patch("daily_brief.connectivity.RSS_BASE", "https://news.google.com/rss/search?q="):
                    with mock.patch("daily_brief.connectivity.RSS_PARAMS", "&hl=en"):
                        with aioresponses() as m:
                            encoded = "energy+%26+markets%2Fma%C3%B1ana"
                            m.get(f"https://news.google.com/rss/search?q={encoded}&hl=en", status=200)
                            async with aiohttp.ClientSession() as session:
                                result = await check_rss(session, timeout=5.0)
                            return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(result["ok"])


class TestSafeNetloc(TestCase):
    """_safe_netloc handles well-formed and malformed URLs without raising."""

    def test_normal_urls(self):
        self.assertEqual(_safe_netloc("https://waterdatafortexas.org/reservoirs"), "waterdatafortexas.org")
        self.assertEqual(_safe_netloc("http://example.com"), "example.com")

    def test_malformed_urls_fallback(self):
        """Malformed URLs that pass the shallow validator still produce safe output."""
        self.assertEqual(_safe_netloc("https://"), "https://")
        self.assertEqual(_safe_netloc("https://a"), "a")

    def test_lakes_success_message_safe(self):
        """Check lakes success message does not raise for malformed URLs."""
        async def run():
            captured, cm = _capturing_cm(method="HEAD")
            with mock.patch("daily_brief.connectivity.WEATHER_LAKE_URLS", {"Bad": "https://"}):
                fake = mock.Mock()
                fake.head = cm
                result = await check_lakes(fake, timeout=5.0)
                return result

        result = asyncio.get_event_loop().run_until_complete(run())
        self.assertTrue(result["ok"])
        self.assertIn("Lakes source reachable", result["message"])


if __name__ == "__main__":
    unittest.main()
