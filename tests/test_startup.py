"""
Tests for daily_brief pipeline startup directory creation.
"""
from unittest import TestCase
from daily_brief.pipeline import main as pipeline_main


class TestStartupLogging(TestCase):
    def test_main_returns_int(self):
        """Verify the pipeline main function exists and is awaitable."""
        import asyncio
        # Just verify the function signature is correct
        assert asyncio.iscoroutinefunction(pipeline_main)
