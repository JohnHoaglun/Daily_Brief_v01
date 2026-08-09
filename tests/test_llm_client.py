"""
Unit tests for daily_brief/llm/client.py.
"""
import asyncio
from unittest import TestCase, mock
from unittest.mock import AsyncMock

from daily_brief.llm.client import LLMClient, create_llm_client


# ---------------------------------------------------------------------------
# 1.  LLMClient
# ---------------------------------------------------------------------------

class TestLLMClient(TestCase):
    """LLMClient initialization and async behavior (Perf-8)."""

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_llm_client_init(self, mock_async_openai_cls):
        mock_instance = mock.MagicMock()
        mock_async_openai_cls.return_value = mock_instance
        client = LLMClient(model="test-model", base_url="http://localhost:8080/v1", timeout=120)
        self.assertEqual(client.model, "test-model")
        self.assertEqual(client.client, mock_instance)
        mock_async_openai_cls.assert_called_once_with(
            api_key="not-needed",
            base_url="http://localhost:8080/v1",
            timeout=120,
            max_retries=0,
        )

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_chat_completions_create(self, mock_async_openai_cls):
        mock_instance = mock.MagicMock()
        mock_async_openai_cls.return_value = mock_instance
        mock_instance.chat.completions.create = AsyncMock(return_value="response")
        client = LLMClient(model="m", base_url="http://base")

        async def _run():
            result = await client.chat_completions_create(model="m", messages=[])
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "response")
        mock_instance.chat.completions.create.assert_called_once_with(model="m", messages=[])

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_default_timeout_180(self, mock_async_openai_cls):
        mock_async_openai_cls.return_value = mock.MagicMock()
        LLMClient(model="m", base_url="http://base")
        mock_async_openai_cls.assert_called_once_with(
            api_key="not-needed",
            base_url="http://base",
            timeout=180,
            max_retries=0,
        )

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_custom_timeout_passed(self, mock_async_openai_cls):
        mock_async_openai_cls.return_value = mock.MagicMock()
        LLMClient(model="m", base_url="http://base", timeout=300)
        call_kwargs = mock_async_openai_cls.call_args.kwargs
        self.assertEqual(call_kwargs["timeout"], 300)

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_chat_completions_is_coroutine(self, mock_async_openai_cls):
        """Verify chat_completions_create is a coroutine function (async)."""
        mock_async_openai_cls.return_value = mock.MagicMock()
        client = LLMClient(model="m", base_url="http://base")
        self.assertTrue(asyncio.iscoroutinefunction(client.chat_completions_create))


# ---------------------------------------------------------------------------
# 2.  create_llm_client
# ---------------------------------------------------------------------------

class TestCreateLLMClient(TestCase):
    """Factory function create_llm_client."""

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_create_llm_client_factory(self, mock_async_openai_cls):
        mock_async_openai_cls.return_value = mock.MagicMock()
        client = create_llm_client(model="gpt-4", base_url="http://example.com/v1", timeout=200)
        self.assertIsInstance(client, LLMClient)
        self.assertEqual(client.model, "gpt-4")
        self.assertEqual(client.client, mock_async_openai_cls.return_value)


# ---------------------------------------------------------------------------
# 3.  LLMClient max_retries and aclose
# ---------------------------------------------------------------------------

class TestLLMClientMaxRetries(TestCase):
    """LLMClient max_retries parameter and aclose lifecycle."""

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_default_max_retries_zero(self, mock_async_openai_cls):
        """Default max_retries is 0."""
        mock_async_openai_cls.return_value = mock.MagicMock()
        LLMClient(model="m", base_url="http://base")
        call_kwargs = mock_async_openai_cls.call_args.kwargs
        self.assertEqual(call_kwargs["max_retries"], 0)

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_custom_max_retries_forwarded(self, mock_async_openai_cls):
        """Custom max_retries=3 is forwarded to AsyncOpenAI."""
        mock_async_openai_cls.return_value = mock.MagicMock()
        LLMClient(model="m", base_url="http://base", max_retries=3)
        call_kwargs = mock_async_openai_cls.call_args.kwargs
        self.assertEqual(call_kwargs["max_retries"], 3)

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_aclose_calls_client_close(self, mock_async_openai_cls):
        """aclose() calls client.close() and handles exceptions."""
        mock_client = mock.MagicMock()
        mock_client.close = AsyncMock()
        mock_async_openai_cls.return_value = mock_client
        from daily_brief.llm.client import LLMClient
        client = LLMClient(model="m", base_url="http://base")
        client.client = mock_client

        async def _run():
            await client.aclose()
            mock_client.close.assert_called_once()

        asyncio.get_event_loop().run_until_complete(_run())

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_aclose_idempotent(self, mock_async_openai_cls):
        """aclose() can be called multiple times without error."""
        mock_client = mock.MagicMock()
        mock_client.close = AsyncMock(side_effect=Exception("Already closed"))
        mock_async_openai_cls.return_value = mock_client
        from daily_brief.llm.client import LLMClient
        client = LLMClient(model="m", base_url="http://base")
        client.client = mock_client

        async def _run():
            await client.aclose()
            await client.aclose()  # Second call should not raise
            self.assertEqual(mock_client.close.call_count, 2)

        asyncio.get_event_loop().run_until_complete(_run())


# ---------------------------------------------------------------------------
# 4.  create_llm_client forwarding
# ---------------------------------------------------------------------------

class TestCreateLLMClientForwarding(TestCase):
    """Factory function forwards max_retries correctly."""

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_create_llm_client_default_max_retries(self, mock_async_openai_cls):
        """Default max_retries=0 is passed through create_llm_client."""
        mock_async_openai_cls.return_value = mock.MagicMock()
        create_llm_client(model="m", base_url="http://base")
        call_kwargs = mock_async_openai_cls.call_args.kwargs
        self.assertEqual(call_kwargs["max_retries"], 0)

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_create_llm_client_custom_max_retries(self, mock_async_openai_cls):
        """Custom max_retries=5 is passed through create_llm_client."""
        mock_async_openai_cls.return_value = mock.MagicMock()
        create_llm_client(model="m", base_url="http://base", max_retries=5)
        call_kwargs = mock_async_openai_cls.call_args.kwargs
        self.assertEqual(call_kwargs["max_retries"], 5)
