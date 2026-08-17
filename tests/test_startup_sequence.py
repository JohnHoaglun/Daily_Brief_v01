"""
Integration test for the startup sequence.
"""

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import daily_brief.pipeline as pipeline_mod


class AsyncCtxMgr:
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        pass


class TestStartupSequence:
    def test_startup_reaches_phase4(self):
        CFG_LOG = "/tmp/logs"
        CFG_NEWS = "/tmp/news"
        pipeline_mod.LOG_DIR = CFG_LOG
        pipeline_mod.NEWS_DIR = CFG_NEWS
        pipeline_mod.CATEGORIES = []

        with tempfile.TemporaryDirectory() as tmp:
            tmp_log = os.path.join(tmp, "logs")
            tmp_news = os.path.join(tmp, "news")
            pipeline_mod.LOG_DIR = tmp_log
            pipeline_mod.NEWS_DIR = tmp_news

            with (
                patch.object(pipeline_mod, "validate_config", return_value=(True, [])),
                patch.object(pipeline_mod, "PREFLIGHT_CHECKS_ENABLED", False),
                patch.object(pipeline_mod, "create_llm_client", return_value=MagicMock()),
                patch.object(pipeline_mod.aiohttp, "ClientSession", return_value=AsyncCtxMgr()),
                patch.object(pipeline_mod.aiohttp, "TCPConnector"),
                patch.object(pipeline_mod.aiohttp, "ClientTimeout"),
                patch.object(pipeline_mod, "fetch_weather", new_callable=AsyncMock,
                             return_value={"forecast": [{"name": "Night"}], "station": {}, "lakes": {}}),
                patch.object(pipeline_mod, "fetch_and_dedup", new_callable=AsyncMock,
                             return_value=( [("T", "https://e.com/1", "T", None, "AI")], {"total_after": 1})),
                patch.object(pipeline_mod, "llm_batch_summarize_all", new_callable=AsyncMock, return_value=None),
                patch.object(pipeline_mod, "validate_report", return_value=(False, ["t"])),
            ):
                asyncio.get_event_loop().run_until_complete(pipeline_mod.main())

            logs = [f for f in os.listdir(tmp_log) if f.startswith("run_log_") and f.endswith(".md")]
            assert len(logs) > 0
            assert "Phase 4" in open(os.path.join(tmp_log, logs[0]), encoding="utf-8").read()

            reports = [f for f in os.listdir(tmp_news) if f.startswith("DailyBrief-") and f.endswith(".md")]
            assert len(reports) > 0

            from daily_brief.pipeline import get_current_run_context
            ctx = get_current_run_context()
            assert ctx and "Phase 1" in ctx.phase_timings
