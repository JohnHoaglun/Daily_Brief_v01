"""
Daily Brief v1.0.89 — LLM Client
==================================
Instantiatable LLM client wrapping OpenAI-compatible API.
Migrated to AsyncOpenAI for non-blocking event loop (Perf-8).
Extracted from dashboard_pipeline.py monolith.
"""

import logging

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LLMClient:
    """OpenAI-compatible LLM client for async chat completions."""

    def __init__(self, model: str, base_url: str, timeout: int = 180):
        self.model = model
        self.client = AsyncOpenAI(api_key="not-needed", base_url=base_url, timeout=timeout)

    async def chat_completions_create(self, **kwargs):
        """Async wrap of self.client.chat.completions.create()."""
        return await self.client.chat.completions.create(**kwargs)


def create_llm_client(model: str, base_url: str, timeout: int = 180) -> LLMClient:
    """Factory: return a configured LLMClient instance."""
    return LLMClient(model=model, base_url=base_url, timeout=timeout)
