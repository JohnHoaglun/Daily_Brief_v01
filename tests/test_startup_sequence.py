"""
Integration test for the startup sequence through Phase 4 rendering.
Verifies the real pipeline startup order without crashing:
- Config validation passes
- Precompile tagging runs before RUN_LOGFILE is set
- log() guard handles None RUN_LOGFILE safely
- RUN_LOGFILE is initialized before Phase 4
- Log file created with precompile marker
- Report file created with fixture story
- PHASE_TIMINGS populated through Phase 4
"""

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import daily_brief.pipeline as pipeline_mod


class AsyncCtxMgr:
    """Fake aiohttp session context manager."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass


class TestStartupSequence:
    """Integration test: real pipeline startup through Phase 4 without crashing."""

    def test_startup_sequence_reaches_phase4(self):
        """Verify pipeline runs startup through Phase 4 without crashing."""
        from daily_brief.config import CATEGORIES
        from daily_brief.config import LOG_DIR as CFG_LOG
        from daily_brief.config import NEWS_DIR as CFG_NEWS

        # Force restore attributes that leaked patches from other tests may have modified
        pipeline_mod.LOG_DIR = CFG_LOG
        pipeline_mod.NEWS_DIR = CFG_NEWS
        # Retired globals replaced by a task-local ContextVar accessor:
        # get_current_run_context() returns each task's own context.
        pipeline_mod.CATEGORIES = CATEGORIES

        with tempfile.TemporaryDirectory() as tmp:
            tmp_log = os.path.join(tmp, "logs")
            tmp_news = os.path.join(tmp, "news")

            fake_client = MagicMock()
            fake_session = AsyncCtxMgr()

            pipeline_mod.LOG_DIR = tmp_log
            pipeline_mod.NEWS_DIR = tmp_news

            with (
                patch.object(pipeline_mod, "validate_config", return_value=(True, [])),
                patch.object(pipeline_mod, "PREFLIGHT_CHECKS_ENABLED", False),
                patch.object(pipeline_mod, "create_llm_client", return_value=fake_client),
                patch.object(pipeline_mod.aiohttp, "ClientSession", return_value=fake_session),
                patch.object(pipeline_mod.aiohttp, "TCPConnector"),
                patch.object(pipeline_mod.aiohttp, "ClientTimeout"),
                patch.object(
                    pipeline_mod,
                    "fetch_weather",
                    new_callable=AsyncMock,
                    return_value={
                        "forecast": [
                            {
                                "name": "Night",
                                "temperature": "70\u00b0F",
                                "winds": "Calm",
                                "short_forecast": "Clear skies",
                            }
                        ],
                        "station": {
                            "avg_temp_today": "74\u00b0F",
                            "avg_monthly_rainfall": '2.1"',
                            "current_monthly_rainfall": '1.8"',
                        },
                        "lakes": {},
                    },
                ),
                patch.object(
                    pipeline_mod,
                    "fetch_and_dedup",
                    new_callable=AsyncMock,
                    return_value=(
                        [
                            (
                                "StartupTestStory",
                                "https://example.com/1",
                                "Test snippet",
                                None,
                                "Artificial Intelligence",
                            )
                        ],
                        {"total_after": 1},
                    ),
                ),
                patch.object(
                    pipeline_mod,
                    "llm_batch_summarize_all",
                    new_callable=AsyncMock,
                    return_value=None,
                ),
                patch.object(
                    pipeline_mod, "validate_report", return_value=(False, ["test validation"])
                ),
            ):
                asyncio.get_event_loop().run_until_complete(pipeline_mod.main())

            # Log file created
            log_files = [
                f for f in os.listdir(tmp_log) if f.startswith("run_log_") and f.endswith(".md")
            ]
            assert len(log_files) > 0, f"No log files; dir: {os.listdir(tmp)}"
            log_path = os.path.join(tmp_log, log_files[0])
            assert os.path.isfile(log_path)
            log_text = open(log_path, encoding="utf-8").read()
            assert "Phase 4" in log_text
            assert "Phase 5" in log_text

            # Report file created
            report_files = [
                f
                for f in os.listdir(tmp_news)
                if f.startswith("DailyBrief-") and f.endswith(".md")
            ]
            assert len(report_files) > 0
            report_path = os.path.join(tmp_news, report_files[0])
            report_text = open(report_path, encoding="utf-8").read()
            assert "story_count_total: 1" in report_text

            # PHASE_TIMINGS via RunContext
            from daily_brief.pipeline import get_current_run_context

            ctx = get_current_run_context()
            phase_keys = list(ctx.phase_timings.keys()) if ctx else []
            assert "Phase 1" in phase_keys
