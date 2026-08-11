"""Daily Brief — HTTP Client tests (fully mocked, no network)."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp


class MockContent:
    """Mock aiohttp.response.content supporting iter_any()."""

    def __init__(self, data: str):
        self._data = data.encode("utf-8")
        self._position = 0

    async def iter_any(self):
        chunk_size = 4
        start = 0
        while start < len(self._data):
            end = min(start + chunk_size, len(self._data))
            yield self._data[start:end]
            start = end


class MockResp:
    """Mock aiohttp response context manager."""

    def __init__(self, status=200, text="ok", exception=None, content_length=None):
        self.status = status
        self._text = text
        self._exception = exception
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

        async_iter = MockContent(text)
        self.content = async_iter

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

    def test_default_200_accepted_others_rejected(self):
        fn = self._import()
        self.assertTrue(fn(200))
        self.assertFalse(fn(201))
        self.assertFalse(fn(404))

    def test_custom_predicate(self):
        fn = self._import()
        self.assertTrue(fn(201, lambda s: 200 <= s < 300))
        self.assertFalse(fn(400, lambda s: 200 <= s < 300))


class TestShouldRetry(unittest.TestCase):
    """_should_retry — retryable statuses and exceptions."""

    def _import(self):
        from daily_brief.http_client import _should_retry

        return _should_retry

    def test_transient_statuses_retry(self):
        fn = self._import()
        for status in (429, 502, 503, 504):
            self.assertTrue(fn(status), f"{status} should be retryable")

    def test_client_error_statuses_no_retry(self):
        fn = self._import()
        for status in (400, 401, 403, 404):
            self.assertFalse(fn(status), f"{status} should not be retryable")

    def test_exceptions(self):
        fn = self._import()
        self.assertTrue(fn(asyncio.TimeoutError()))

        self.assertTrue(fn(aiohttp.ClientError()))


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

    def test_retry_then_recover(self):
        """503, 503, 200 → returns text with 3 attempts, 2 sleeps."""
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

    def test_retry_exhaustion(self):
        """Three transient failures → returns None text, last status, 3 attempts."""
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

    def test_timeout_then_recover(self):
        """Timeout then 200 → 2 attempts, 1 sleep."""
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

    def test_non_retryable_immediate_no_retry(self):
        """Non-retryable status returns immediately with 1 attempt, no sleep."""
        fn = self._import()
        for status in (400, 401, 403, 404):
            session = make_session(MockResp(status=status))
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                text, got_status, attempts = self._loop(fn(session, "http://x"))
            self.assertEqual(got_status, status)
            self.assertEqual(attempts, 1)
            mock_sleep.assert_not_called()

    def test_status_predicate_accept_2xx(self):
        fn = self._import()
        session = make_session(MockResp(status=201, text="created"))
        text, status, attempts = self._loop(
            fn(session, "http://x", status_predicate=lambda s: 200 <= s < 300)
        )
        self.assertEqual(text, "created")
        self.assertEqual(status, 201)
        self.assertEqual(attempts, 1)

    def test_header_and_timeout_forwarding(self):
        session = make_session(MockResp(status=200, text="ok"))
        fn = self._import()

        # Verify User-Agent is forwarded
        ua = "CustomAgent/2.0"
        with patch.object(session, "get", wraps=session.get) as gw:
            self._loop(fn(session, "http://x", user_agent=ua))
        gw.assert_called()
        kwargs = gw.call_args[1]
        self.assertIn("headers", kwargs)
        self.assertEqual(kwargs["headers"]["User-Agent"], ua)

    def test_non_retryable_exception(self):
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

    def test_valid_json_dict_and_list(self):
        fn = self._import()
        payload = json.dumps({"weather": "sunny"})
        session = make_session(MockResp(status=200, text=payload))
        result = self._loop(fn(session, "http://x"))
        self.assertEqual(result, {"weather": "sunny"})

        payload = json.dumps([1, 2, 3])
        session = make_session(MockResp(status=200, text=payload))
        result = self._loop(fn(session, "http://x"))
        self.assertEqual(result, [1, 2, 3])

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

    def test_valid_and_invalid(self):
        fn = self._import()
        result = self._loop(fn('{"a":1}'))
        self.assertEqual(result, {"a": 1})
        result = self._loop(fn("{bad"))
        self.assertIsNone(result)
        result = self._loop(fn(""))
        self.assertIsNone(result)


class TestExceedsContentLengthHeader(unittest.TestCase):
    """_exceeds_content_length_header — pre-check logic."""

    def _import(self):
        from daily_brief.http_client import _exceeds_content_length_header

        return _exceeds_content_length_header

    def test_no_header(self):
        fn = self._import()
        resp = MockResp(status=200, text="hello")
        self.assertFalse(fn(resp, limit=100))

    def test_under_limit(self):
        fn = self._import()
        resp = MockResp(status=200, text="hello", content_length=5)
        self.assertFalse(fn(resp, limit=10))

    def test_at_limit(self):
        fn = self._import()
        resp = MockResp(status=200, text="hello", content_length=10)
        self.assertFalse(fn(resp, limit=10))

    def test_over_limit(self):
        fn = self._import()
        resp = MockResp(status=200, text="hello", content_length=15)
        self.assertTrue(fn(resp, limit=10))


class TestRequestWithRetryBounded(unittest.TestCase):
    """_request_with_retry — bounded content-length handling."""

    def _import(self):
        from daily_brief.http_client import _request_with_retry

        return _request_with_retry

    def _loop(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_content_length_precheck_rejects(self):
        """Declared Content-Length > limit → rejected without reading body."""
        fn = self._import()
        large_text = "x" * 500
        resp = MockResp(status=200, text=large_text, content_length=500)
        session = make_session(resp)
        text, status, attempts = self._loop(fn(session, "http://x", max_bytes=100))
        self.assertIsNone(text)
        self.assertEqual(status, 200)
        self.assertEqual(attempts, 1)

    def test_content_length_within_limit(self):
        """Declared Content-Length within limit → accepted normally."""
        fn = self._import()
        text_content = "small body"
        resp = MockResp(status=200, text=text_content, content_length=len(text_content))
        session = make_session(resp)
        text, status, attempts = self._loop(fn(session, "http://x", max_bytes=1000))
        self.assertEqual(text, text_content)
        self.assertEqual(status, 200)
        self.assertEqual(attempts, 1)

    def test_streaming_within_limit(self):
        """No Content-Length header; body within limit → accepted via streaming."""
        fn = self._import()
        text_content = "streamed body"
        resp = MockResp(status=200, text=text_content)
        session = make_session(resp)
        text, status, attempts = self._loop(fn(session, "http://x", max_bytes=1000))
        self.assertEqual(text, text_content)
        self.assertEqual(status, 200)
        self.assertEqual(attempts, 1)

    def test_streaming_exceeds_limit(self):
        """Body exceeds limit mid-stream → rejected with None."""
        fn = self._import()
        large_text = "x" * 200
        resp = MockResp(status=200, text=large_text)
        session = make_session(resp)
        text, status, attempts = self._loop(fn(session, "http://x", max_bytes=10))
        self.assertIsNone(text)
        self.assertEqual(attempts, 1)


class TestFetchTextBounded(unittest.TestCase):
    """_fetch_text — forwards max_bytes."""

    def _import(self):
        from daily_brief.http_client import _fetch_text

        return _fetch_text

    def _loop(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_rejects_oversized(self):
        fn = self._import()
        resp = MockResp(status=200, text="a" * 100, content_length=100)
        session = make_session(resp)
        result = self._loop(fn(session, "http://x", max_bytes=10))
        self.assertIsNone(result)


class TestFetchJsonBounded(unittest.TestCase):
    """_fetch_json — forwards max_bytes."""

    def _import(self):
        from daily_brief.http_client import _fetch_json

        return _fetch_json

    def _loop(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_rejects_oversized(self):
        fn = self._import()
        payload = json.dumps({"data": "x" * 100})
        resp = MockResp(status=200, text=payload, content_length=len(payload))
        session = make_session(resp)
        result = self._loop(fn(session, "http://x", max_bytes=10))
        self.assertIsNone(result)

    def test_within_limit(self):
        fn = self._import()
        payload = json.dumps({"ok": 1})
        resp = MockResp(status=200, text=payload)
        session = make_session(resp)
        result = self._loop(fn(session, "http://x", max_bytes=1000))
        self.assertEqual(result, {"ok": 1})


if __name__ == "__main__":
    unittest.main()
