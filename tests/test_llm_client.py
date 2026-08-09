"""
Unit tests for daily_brief/llm/client.py.
"""
import asyncio
from unittest import TestCase, mock
from unittest.mock import AsyncMock

from daily_brief.llm.client import LLMClient, create_llm_client


class TestLLMClient(TestCase):
    """LLMClient initialization, forwarding, and async behavior."""

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_init_with_custom_timeout(self, mock_cls):
        mock_cls.return_value = mock.MagicMock()
        client = LLMClient(model="test-model", base_url="http://localhost:8080/v1", timeout=120)
        self.assertEqual(client.model, "test-model")
        self.assertEqual(client.client, mock_cls.return_value)
        mock_cls.assert_called_once_with(
            api_key="not-needed",
            base_url="http://localhost:8080/v1",
            timeout=120,
            max_retries=0,
        )

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_default_timeout_and_retries(self, mock_cls):
        mock_cls.return_value = mock.MagicMock()
        LLMClient(model="m", base_url="http://base")
        mock_cls.assert_called_once_with(
            api_key="not-needed",
            base_url="http://base",
            timeout=180,
            max_retries=0,
        )

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_custom_max_retries(self, mock_cls):
        mock_cls.return_value = mock.MagicMock()
        LLMClient(model="m", base_url="http://base", max_retries=3)
        call_kwargs = mock_cls.call_args.kwargs
        self.assertEqual(call_kwargs["max_retries"], 3)

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_chat_completions_create(self, mock_cls):
        mock_instance = mock.MagicMock()
        mock_cls.return_value = mock_instance
        mock_instance.chat.completions.create = AsyncMock(return_value="response")
        client = LLMClient(model="m", base_url="http://base")

        async def _run():
            result = await client.chat_completions_create(model="m", messages=[])
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        self.assertEqual(result, "response")
        mock_instance.chat.completions.create.assert_called_once_with(model="m", messages=[])

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_aclose(self, mock_cls):
        """aclose() calls client.close(); idempotent on second call."""
        mock_client = mock.MagicMock()
        mock_client.close = AsyncMock(side_effect=[None, Exception("Already closed")])
        mock_cls.return_value = mock_client
        client = LLMClient(model="m", base_url="http://base")
        client.client = mock_client

        async def _run():
            await client.aclose()
            await client.aclose()
            self.assertEqual(mock_client.close.call_count, 2)

        asyncio.get_event_loop().run_until_complete(_run())


class TestCreateLLMClient(TestCase):
    """Factory function forwards parameters correctly."""

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_factory_creates_client(self, mock_cls):
        mock_cls.return_value = mock.MagicMock()
        client = create_llm_client(model="gpt-4", base_url="http://example.com/v1", timeout=200)
        self.assertIsInstance(client, LLMClient)
        self.assertEqual(client.model, "gpt-4")

    @mock.patch("daily_brief.llm.client.AsyncOpenAI")
    def test_factory_forwards_max_retries(self, mock_cls):
        mock_cls.return_value = mock.MagicMock()
        create_llm_client(model="m", base_url="http://base", max_retries=5)
        call_kwargs = mock_cls.call_args.kwargs
        self.assertEqual(call_kwargs["max_retries"], 5)


if __name__ == "__main__":
    unittest.main()
