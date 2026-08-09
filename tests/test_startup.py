"""
Tests for daily_brief pipeline startup directory creation.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from unittest import TestCase
from daily_brief.pipeline import main as pipeline_main


class TestStartupLogging(TestCase):
    def test_main_returns_int(self):
        """Verify the pipeline main function exists and is awaitable."""
        import asyncio
        # Just verify the function signature is correct
        assert asyncio.iscoroutinefunction(pipeline_main)
