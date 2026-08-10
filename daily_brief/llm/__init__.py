"""
Daily Brief v1.0.135 — LLM Subpackage
=====================================
Re-exports from the llm subpackage.
"""

from daily_brief.llm.client import (
    LLMClient,
    create_llm_client,
)

__all__ = [
    "LLMClient",
    "create_llm_client",
]
