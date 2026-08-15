"""
Daily Brief v1.0.151 — LLM Client
==================================
Instantiatable LLM client wrapping OpenAI-compatible API.
Migrated to AsyncOpenAI for non-blocking event loop (Perf-8).
"""

import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LLMClient:
    """OpenAI-compatible LLM client for async chat completions."""

    def __init__(self, model: str, base_url: str, timeout: int = 180, max_retries: int = 0):
        self.model = model
        self.client = AsyncOpenAI(
            api_key="not-needed", base_url=base_url, timeout=timeout, max_retries=max_retries
        )

    async def chat_completions_create(self, **kwargs):
        """Async wrap of self.client.chat.completions.create()."""
        return await self.client.chat.completions.create(**kwargs)

    async def aclose(self):
        """Idempotently close the underlying AsyncOpenAI transport."""
        try:
            await self.client.close()
        except Exception:
            pass  # Already closed or disconnected


def create_llm_client(
    model: str, base_url: str, timeout: int = 180, max_retries: int = 0
) -> LLMClient:
    """Factory: return a configured LLMClient instance."""
    return LLMClient(model=model, base_url=base_url, timeout=timeout, max_retries=max_retries)
