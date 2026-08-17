"""Reduced: body-size cap, retry on transient error, timeout."""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp


class MockContent:
    def __init__(self, data: str):
        self._data = data.encode("utf-8")
        self._position = 0

    async def iter_chunked(self, size: int):
        yield self._data[self._position:self._position + size]
        self._position += size

    async def iter_any(self):
        chunk_size = 4
        start = 0
        while start < len(self._data):
            end = min(start + chunk_size, len(self._data))
            yield self._data[start:end]
            start = end


class MockResp:
    def __init__(self, status=200, text="ok", exception=None, content_length=None):
        self.status = status
        self._text = text
        self._exception = exception
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)
        self.content = MockContent(text)

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
    idx = [0]
    session = MagicMock()

    def get(url, **kwargs):
        resp = responses[idx[0] % len(responses)]
        idx[0] += 1
        return resp

    session.get = get
    return session


class TestBodySizeCap(unittest.TestCase):
    def _loop(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def _import(self):
        from daily_brief.http_client import _request_with_retry
        return _request_with_retry

    def test_content_length_rejects(self):
        fn = self._import()
        large = "x" * 500
        resp = MockResp(status=200, text=large, content_length=500)
        session = make_session(resp)
        text, status, _ = self._loop(fn(session, "http://x", max_bytes=100))
        self.assertIsNone(text)
        self.assertEqual(status, 200)

    def test_content_within_limit(self):
        fn = self._import()
        resp = MockResp(status=200, text="small body", content_length=10)
        session = make_session(resp)
        text, status, _ = self._loop(fn(session, "http://x", max_bytes=1000))
        self.assertEqual(text, "small body")

    def test_streaming_exceeds_limit(self):
        fn = self._import()
        large = "x" * 200
        resp = MockResp(status=200, text=large)
        session = make_session(resp)
        text, status, _ = self._loop(fn(session, "http://x", max_bytes=10))
        self.assertIsNone(text)


class TestRetryOnTransient(unittest.TestCase):
    def _loop(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def _import(self):
        from daily_brief.http_client import _request_with_retry
        return _request_with_retry

    def test_retry_then_recover(self):
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


class TestTimeout(unittest.TestCase):
    def _loop(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def _import(self):
        from daily_brief.http_client import _request_with_retry
        return _request_with_retry

    def test_timeout_then_recover(self):
        fn = self._import()
        session = make_session(
            MockResp(exception=asyncio.TimeoutError()),
            MockResp(status=200, text="ok"),
        )
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            text, status, _ = self._loop(fn(session, "http://x"))
        self.assertEqual(text, "ok")
        self.assertEqual(status, 200)

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
        self.assertEqual(attempts, 3)


if __name__ == "__main__":
    unittest.main()
