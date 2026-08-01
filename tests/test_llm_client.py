"""
Unit tests for src/daily_brief/llm/client.py.
"""
import asyncio
import os
import sys
from unittest import TestCase, mock
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

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
