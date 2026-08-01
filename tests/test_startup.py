"""
Tests for daily_brief.__main__.py setup_logging and pipeline directory creation on startup.
"""
import os
import sys
import tempfile
from unittest import TestCase
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import logging
from daily_brief.__main__ import setup_logging


class TestSetupLoggingCreatesDir(TestCase):
    def test_creates_missing_log_directory_and_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_dir = os.path.join(tmp, "nonexistent", "logs")
            self.assertFalse(os.path.isdir(log_dir))
            setup_logging(log_dir=log_dir)
            self.assertTrue(os.path.isdir(log_dir))
            self.assertTrue(os.path.isfile(os.path.join(log_dir, "daily_brief.log")))
            # Clean up root handlers to avoid leaking state
            for h in list(logging.root.handlers):
                logging.root.removeHandler(h)


class TestPipelineCreatesDirs(TestCase):
    def _make_async_cm(self):
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=None)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    def test_pipeline_creates_log_and_news_dirs(self):
        """Verify both LOG_DIR and NEWS_DIR are created on startup before os.listdir(LOG_DIR) runs."""
        import asyncio

        with tempfile.TemporaryDirectory() as tmp:
            log_dir = os.path.join(tmp, "testrun", "logs")
            news_dir = os.path.join(tmp, "testrun", "news")
            original_makedirs = os.makedirs
            makedirs_paths = []

            def _wrap_makedirs(path, *a, **kw):
                makedirs_paths.append(str(path))
                original_makedirs(path, *a, **kw)

            patches = [
                patch("daily_brief.pipeline.os.makedirs", side_effect=_wrap_makedirs),
                patch("daily_brief.pipeline.os.listdir", return_value=[]),
                patch("daily_brief.pipeline.LOG_DIR", log_dir),
                patch("daily_brief.pipeline.NEWS_DIR", news_dir),
                patch("daily_brief.pipeline.validate_config", return_value=(True, [])),
                patch("daily_brief.pipeline.create_llm_client", return_value=MagicMock()),
                patch("daily_brief.pipeline.fetch_weather", new_callable=AsyncMock, return_value={
                    "forecast": [{"period": 1}],
                    "station": {"avg_temp_today": "75", "avg_monthly_rainfall": "3", "current_hourly_rainfall": "2"},
                    "lakes": {},
                }),
                patch("daily_brief.connectivity.run_all_checks", new_callable=AsyncMock, return_value=[{"ok": True}]),
                patch("daily_brief.connectivity.format_results", return_value="ok"),
                patch("daily_brief.pipeline.fetch_and_dedup", new_callable=AsyncMock, return_value=(
                    [("TestTitle", "https://example.com/1", "snip", None, "cat")],
                    {"total_after": 1}
                )),
                patch("daily_brief.pipeline.StoryPipelineState", return_value=MagicMock()),
                patch("daily_brief.pipeline.llm_summarize", return_value=None),
                patch("daily_brief.pipeline.llm_batch_summarize_all", return_value=None),
                patch("daily_brief.pipeline._is_refusal", return_value=False),
                patch("daily_brief.pipeline._is_boilerplate", return_value=False),
                patch("daily_brief.pipeline.build_sections_from_stories", return_value=({}, [])),
                patch("daily_brief.pipeline.ordered_categories_for_render", return_value=["cat"]),
                patch("daily_brief.pipeline.compute_output_path", return_value=(os.path.join(news_dir, "r.md"), 1)),
                patch("daily_brief.pipeline.cleanup_old_files"),
                patch("daily_brief.pipeline.build_markdown", return_value="#md"),
                patch("daily_brief.pipeline.validate_report", return_value=(True, [])),
                patch("daily_brief.pipeline.run_test_harness"),
                patch("sys.stderr"),
            ]

            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session_cls:
                mock_session_cls.side_effect = [self._make_async_cm()]
                with patch("daily_brief.pipeline.write_report"):
                    with patch("daily_brief.pipeline.sys.exit", side_effect=SystemExit(1)):
                        with _AggregateCM(patches):
                            try:
                                from daily_brief.pipeline import main as pm
                                asyncio.get_event_loop().run_until_complete(pm())
                            except SystemExit:
                                pass

            self.assertIn(log_dir, makedirs_paths)
            self.assertTrue(os.path.isdir(log_dir))
            self.assertIn(news_dir, makedirs_paths)
            self.assertTrue(os.path.isdir(news_dir))


class _AggregateCM:
    """Aggregate multiple context managers into one."""
    def __init__(self, cms):
        self.cms = cms

    def __enter__(self):
        self.entries = [cm.__enter__() for cm in self.cms]
        return self.entries

    def __exit__(self, *exc):
        for cm in reversed(self.cms):
            cm.__exit__(*exc)
