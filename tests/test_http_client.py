"""Daily Brief — HTTP Client tests (fully mocked, no network)."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock


class MockResp:
    """Mock aiohttp response context manager."""

    def __init__(self, status=200, text="ok", exception=None):
        self.status = status
        self._text = text
        self._exception = exception

    async def __aenter__(self):
        if self._exception:
            raise self._exception
        return self

    async def __aexit__(self, *a):
        pass

    async def text(self):
        return self._text

    async def json(self):
        return json.loads(self._text)


def make_session(*responses):
    """Return a mock session whose .get() iterates over *responses* in order."""
    idx = [0]
    session = MagicMock()

    def get(url, **kwargs):
        resp = responses[idx[0] % len(responses)]
        idx[0] += 1
        return resp

    session.get = get
    return session


class TestIsStatusAccepted(unittest.TestCase):
    """_is_status_accepted — default and predicate behaviour."""

    def _import(self):
        from daily_brief.http_client import _is_status_accepted
        return _is_status_accepted

    def test_exact_200_default(self):
        fn = self._import()
        self.assertTrue(fn(200))

    def test_non_200_default(self):
        fn = self._import()
        self.assertFalse(fn(201))
        self.assertFalse(fn(404))

    def test_predicate_match(self):
        fn = self._import()
        self.assertTrue(fn(201, lambda s: 200 <= s < 300))

    def test_predicate_miss(self):
        fn = self._import()
        self.assertFalse(fn(400, lambda s: 200 <= s < 300))


class TestShouldRetry(unittest.TestCase):
    """_should_retry — retryable statuses and exceptions."""

    def _import(self):
        from daily_brief.http_client import _should_retry
        return _should_retry

    def test_retryable_429(self):
        self.assertTrue(self._import()(429))

    def test_retryable_502(self):
        self.assertTrue(self._import()(502))

    def test_retryable_503(self):
        self.assertTrue(self._import()(503))

    def test_retryable_504(self):
        self.assertTrue(self._import()(504))

    def test_not_retryable_400(self):
        self.assertFalse(self._import()(400))

    def test_not_retryable_401(self):
        self.assertFalse(self._import()(401))

    def test_not_retryable_403(self):
        self.assertFalse(self._import()(403))

    def test_not_retryable_404(self):
        self.assertFalse(self._import()(404))

    def test_retryable_timeout_error(self):
        self.assertTrue(self._import()(asyncio.TimeoutError()))

    def test_retryable_client_error(self):
        import aiohttp
        self.assertTrue(self._import()(aiohttp.ClientError()))


class TestRequestWithRetry(unittest.TestCase):
    """_request_with_retry — core retry executor."""

    def _import(self):
        from daily_brief.http_client import _request_with_retry
        return _request_with_retry

    def _loop(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_immediate_200_no_sleep(self):
        fn = self._import()
        session = make_session(MockResp(status=200, text='{"ok":1}'))
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            text, status, attempts = self._loop(fn(session, "http://x"))
        self.assertEqual(text, '{"ok":1}')
        self.assertEqual(status, 200)
        self.assertEqual(attempts, 1)
        mock_sleep.assert_not_called()

    def test_retry_recovery_503_503_200(self):
        fn = self._import()
        session = make_session(
            MockResp(status=503),
            MockResp(status=503),
            MockResp(status=200, text="recovered"),
        )
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            text, status, attempts = self._loop(fn(session, "http://x"))
        self.assertEqual(text, "recovered")
        self.assertEqual(status, 200)
        self.assertEqual(attempts, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    def test_retry_exhaustion_502_thrice(self):
        fn = self._import()
        session = make_session(
            MockResp(status=502),
            MockResp(status=502),
            MockResp(status=502),
        )
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            text, status, attempts = self._loop(fn(session, "http://x"))
        self.assertIsNone(text)
        self.assertEqual(status, 502)
        self.assertEqual(attempts, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    def test_timeout_then_200(self):
        fn = self._import()
        session = make_session(
            MockResp(exception=asyncio.TimeoutError()),
            MockResp(status=200, text="ok"),
        )
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            text, status, attempts = self._loop(fn(session, "http://x"))
        self.assertEqual(text, "ok")
        self.assertEqual(status, 200)
        self.assertEqual(attempts, 2)
        self.assertEqual(mock_sleep.call_count, 1)

    def test_timeout_exhaustion(self):
        fn = self._import()
        session = make_session(
            MockResp(exception=asyncio.TimeoutError()),
            MockResp(exception=asyncio.TimeoutError()),
            MockResp(exception=asyncio.TimeoutError()),
        )
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            text, status, attempts = self._loop(fn(session, "http://x"))
        self.assertIsNone(text)
        self.assertIsNone(status)
        self.assertEqual(attempts, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    def test_non_retryable_400_single(self):
        fn = self._import()
        session = make_session(MockResp(status=400))
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            text, status, attempts = self._loop(fn(session, "http://x"))
        self.assertIsNone(text)
        self.assertEqual(status, 400)
        self.assertEqual(attempts, 1)
        mock_sleep.assert_not_called()

    def test_non_retryable_401_single(self):
        fn = self._import()
        session = make_session(MockResp(status=401))
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            text, status, attempts = self._loop(fn(session, "http://x"))
        self.assertEqual(attempts, 1)
        mock_sleep.assert_not_called()

    def test_non_retryable_403_single(self):
        fn = self._import()
        session = make_session(MockResp(status=403))
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            text, status, attempts = self._loop(fn(session, "http://x"))
        self.assertEqual(attempts, 1)
        mock_sleep.assert_not_called()

    def test_non_retryable_404_single(self):
        fn = self._import()
        session = make_session(MockResp(status=404))
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            text, status, attempts = self._loop(fn(session, "http://x"))
        self.assertEqual(attempts, 1)
        mock_sleep.assert_not_called()

    def test_status_predicate_200_299(self):
        fn = self._import()
        session = make_session(MockResp(status=201, text="created"))
        text, status, attempts = self._loop(
            fn(session, "http://x", status_predicate=lambda s: 200 <= s < 300)
        )
        self.assertEqual(text, "created")
        self.assertEqual(status, 201)
        self.assertEqual(attempts, 1)

    def test_status_predicate_rejects_400(self):
        fn = self._import()
        session = make_session(MockResp(status=400))
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            text, status, attempts = self._loop(
                fn(session, "http://x", status_predicate=lambda s: 200 <= s < 300)
            )
        self.assertIsNone(text)
        self.assertEqual(attempts, 1)
        mock_sleep.assert_not_called()

    def test_header_forwarding_user_agent(self):
        fn = self._import()
        session = make_session(MockResp(status=200, text="ok"))
        ua = "CustomAgent/2.0"
        with patch.object(session, "get", wraps=session.get) as gw:
            self._loop(fn(session, "http://x", user_agent=ua))
        gw.assert_called_once()
        kwargs = gw.call_args[1]
        self.assertIn("headers", kwargs)
        self.assertEqual(kwargs["headers"]["User-Agent"], ua)

    def test_header_forwarding_timeout(self):
        fn = self._import()
        session = make_session(MockResp(status=200, text="ok"))
        orig_get = session.get
        captured_kwargs = {}

        def capture_get(url, **kwargs):
            captured_kwargs.update(kwargs)
            return orig_get(url, **kwargs)

        session.get = capture_get
        self._loop(fn(session, "http://x", timeout=30))
        self.assertEqual(captured_kwargs["timeout"].total, 30)

    def test_non_retryable_exception_single(self):
        fn = self._import()
        session = make_session(MockResp(exception=ValueError("boom")))
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            text, status, attempts = self._loop(fn(session, "http://x"))
        self.assertIsNone(text)
        self.assertIsNone(status)
        self.assertEqual(attempts, 1)
        mock_sleep.assert_not_called()


class TestFetchJson(unittest.TestCase):
    """_fetch_json — JSON parsing with retry."""

    def _import(self):
        from daily_brief.http_client import _fetch_json
        return _fetch_json

    def _loop(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_200_returns_parsed_dict(self):
        fn = self._import()
        payload = json.dumps({"weather": "sunny"})
        session = make_session(MockResp(status=200, text=payload))
        result = self._loop(fn(session, "http://x"))
        self.assertEqual(result, {"weather": "sunny"})

    def test_failed_status_returns_none(self):
        fn = self._import()
        session = make_session(MockResp(status=500))
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = self._loop(fn(session, "http://x"))
        self.assertIsNone(result)

    def test_bad_json_returns_none(self):
        fn = self._import()
        session = make_session(MockResp(status=200, text="not json at all"))
        result = self._loop(fn(session, "http://x"))
        self.assertIsNone(result)

    def test_valid_json_returned(self):
        fn = self._import()
        payload = json.dumps([1, 2, 3])
        session = make_session(MockResp(status=200, text=payload))
        result = self._loop(fn(session, "http://x"))
        self.assertEqual(result, [1, 2, 3])


class TestFetchText(unittest.TestCase):
    """_fetch_text — plain text with retry."""

    def _import(self):
        from daily_brief.http_client import _fetch_text
        return _fetch_text

    def _loop(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_200_returns_text(self):
        fn = self._import()
        session = make_session(MockResp(status=200, text="hello world"))
        result = self._loop(fn(session, "http://x"))
        self.assertEqual(result, "hello world")

    def test_failed_status_returns_none(self):
        fn = self._import()
        session = make_session(MockResp(status=500))
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = self._loop(fn(session, "http://x"))
        self.assertIsNone(result)


class TestSafeJsonParse(unittest.TestCase):
    """_safe_json_parse — standalone JSON parsing."""

    def _import(self):
        from daily_brief.http_client import _safe_json_parse
        return _safe_json_parse

    def _loop(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_valid_dict(self):
        fn = self._import()
        result = self._loop(fn('{"a":1}'))
        self.assertEqual(result, {"a": 1})

    def test_invalid(self):
        fn = self._import()
        result = self._loop(fn('{bad'))
        self.assertIsNone(result)

    def test_empty_string(self):
        fn = self._import()
        result = self._loop(fn(""))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
