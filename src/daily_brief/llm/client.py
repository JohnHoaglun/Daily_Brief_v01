"""
Daily Brief v1.0.13 — LLM Client
==================================
Instantiatable LLM client wrapping OpenAI-compatible API.
Extracted from dashboard_pipeline.py monolith.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=3)


class LLMClient:
    """OpenAI-compatible LLM client for chat completions."""

    def __init__(self, model: str, base_url: str, timeout: int = 180):
        self.model = model
        self.client = OpenAI(api_key="not-needed", base_url=base_url, timeout=timeout)

    def chat_completions_create(self, **kwargs):
        """Wrap self.client.chat.completions.create()."""
        return self.client.chat.completions.create(**kwargs)


def create_llm_client(model: str, base_url: str, timeout: int = 180) -> LLMClient:
    """Factory: return a configured LLMClient instance."""
    return LLMClient(model=model, base_url=base_url, timeout=timeout)


def _run_blocking(fn, *args):
    """Run a blocking function in the thread pool executor."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(_executor, fn, *args)
