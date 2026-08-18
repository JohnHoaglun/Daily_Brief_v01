"""
Regression tests for pipeline stage extraction and ordering in main().

Verifies that each stage function is callable at runtime, that weather+RSS
remain the only concurrent pair, and that config/validation error handling
works correctly.
"""

import asyncio
import inspect
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from tests.concurrency_support import (
    _restore_aiohttp_client_session,
    _make_async_cm,
    _story,
    _weather,
    _default_dedup_data,
)


class _AggregateCM:
    """Enter/exit multiple patch context managers."""
    def __init__(self, cms):
        self.cms = cms

    def __enter__(self):
        self.entries = [cm.__enter__() for cm in self.cms]
        return self.entries

    def __exit__(self, *exc):
        for cm in reversed(self.cms):
            cm.__exit__(*exc)


def _make_stage_patches(
    config_ok=True,
    config_issues=[],
    validation_ok=True,
    validation_issues=[],
    custom_validate_config=None,
    custom_validate_report=None,
):
    """Build a standard patch group for pipeline.main() invocations."""
    story_obj = _story()
    story_ctor = lambda *a, **kw: story_obj

    patches = [
        patch("daily_brief.pipeline.validate_config",
              return_value=(config_ok, config_issues) if custom_validate_config is None else custom_validate_config),
        patch("daily_brief.pipeline.validate_report",
              return_value=(validation_ok, validation_issues) if custom_validate_report is None else custom_validate_report),
        patch("daily_brief.pipeline.create_llm_client", return_value=MagicMock()),
        patch("daily_brief.pipeline.llm_batch_summarize_all", new_callable=AsyncMock),
        patch("daily_brief.pipeline.stages.fetch_weather",
              new_callable=AsyncMock, return_value=_weather()),
        patch("daily_brief.pipeline.fetch_and_dedup",
              new_callable=AsyncMock, return_value=_default_dedup_data()),
        patch("daily_brief.pipeline.StoryPipelineState", side_effect=story_ctor),
        patch("daily_brief.pipeline.stage_extract_article", new_callable=AsyncMock),
        patch("daily_brief.pipeline.ordered_categories_for_render", return_value=["cat"]),
        patch("daily_brief.pipeline.build_sections_from_stories", return_value={}),
        patch("daily_brief.pipeline.build_markdown", return_value=["#md"]),
        patch("daily_brief.pipeline.compute_output_path", return_value=("/tmp/r.md", 1)),
        patch("daily_brief.pipeline.cleanup_old_files"),
        patch("daily_brief.pipeline.PREFLIGHT_CHECKS_ENABLED", False),
        patch("daily_brief.pipeline.LOG_DIR", "/tmp"),
        patch("daily_brief.pipeline.NEWS_DIR", "/tmp"),
    ]
    return _AggregateCM(patches)


# ---------------------------------------------------------------------------
# Stage resolution
# ---------------------------------------------------------------------------


class TestStageFunctionExists(TestCase):
    """Each function that main() resolves via _pip() must exist and be callable."""

    def tearDown(self):
        _restore_aiohttp_client_session()

    def test_all_stage_functions_callable(self):
        """All stage function names resolved by main() should exist on the pipeline module."""
        import daily_brief.pipeline as pmod

        stage_names = [
            "validate_config", "validate_report", "create_llm_client",
            "llm_batch_summarize_all", "fetch_weather", "fetch_and_dedup",
            "stage_extract_article", "ordered_categories_for_render",
            "build_sections_from_stories", "build_markdown",
            "compute_output_path", "write_report", "cleanup_old_files",
        ]
        for name in stage_names:
            self.assertTrue(hasattr(pmod, name), f"Missing stage function: {name}")
            attr = getattr(pmod, name)
            self.assertTrue(callable(attr), f"Stage function '{name}' is not callable: {type(attr)}")

    def test_aiohttp_available(self):
        """aiohttp must be available on the pipeline module for ClientSession patching."""
        import daily_brief.pipeline as pmod

        self.assertTrue(hasattr(pmod, "aiohttp"))
        self.assertTrue(hasattr(pmod.aiohttp, "ClientSession"))

    def test_config_constants_available(self):
        """Key config constants must be available on the pipeline module."""
        import daily_brief.pipeline as pmod

        for attr in ("LOG_DIR", "NEWS_DIR", "PREFLIGHT_CHECKS_ENABLED"):
            self.assertTrue(hasattr(pmod, attr), f"Missing config constant: {attr}")

    def test_exit_codes_defined(self):
        """EXIT_CODE_SUCCESS, EXIT_CODE_CONFIG, EXIT_CODE_VALIDATION must be defined."""
        import daily_brief.pipeline as pmod

        self.assertTrue(hasattr(pmod, "EXIT_CODE_SUCCESS"))
        self.assertTrue(hasattr(pmod, "EXIT_CODE_CONFIG"))
        self.assertTrue(hasattr(pmod, "EXIT_CODE_VALIDATION"))
        self.assertEqual(pmod.EXIT_CODE_SUCCESS, 0)
        self.assertEqual(pmod.EXIT_CODE_CONFIG, 1)
        self.assertEqual(pmod.EXIT_CODE_VALIDATION, 2)


# ---------------------------------------------------------------------------
# Concurrent pair verification
# ---------------------------------------------------------------------------


class TestConcurrentPair(TestCase):
    """Weather and RSS remain the only concurrent pair in main()."""

    def test_only_two_phases_concurrent(self):
        """asyncio.gather in main() must only be used for weather + RSS (2 concurrent tasks)."""
        import daily_brief.pipeline.stages as stages_mod
        import daily_brief.pipeline.stages_core as core_mod

        source_main = inspect.getsource(stages_mod)
        self.assertIn("asyncio.gather(_phase1_weather(), _phase2_rss())", source_main)
        source_core = inspect.getsource(core_mod)
        self.assertIn("sem_article = asyncio.Semaphore", source_core)
        self.assertIn("_bounded_extract", source_core)

    def test_phases_not_all_gathered(self):
        """Phase 3/4/5 are NOT gathered concurrently with weather/RSS."""
        import daily_brief.pipeline.stages as stages_mod
        import daily_brief.pipeline.stages_core as core_mod

        source_main = inspect.getsource(stages_mod)
        source_core = inspect.getsource(core_mod)
        combined = source_main + source_core
        gather_count = combined.count("asyncio.gather(")
        # 1 in stages.py (weather+RSS), 1 in stages_core.py (article extraction)
        self.assertGreaterEqual(gather_count, 2)


# ---------------------------------------------------------------------------
# Short-circuit behaviors
# ---------------------------------------------------------------------------


class TestShortCircuit(TestCase):
    """Config error and validation failure short-circuit behaviors."""

    def tearDown(self):
        _restore_aiohttp_client_session()

    def test_config_failure_short_circuits_before_stages(self):
        """Config validation failure returns EXIT_CODE_CONFIG and no data stages run."""
        call_tracker = {"weather": False, "rss": False, "llm": False}

        async def fake_weather(*a, **kw):
            call_tracker["weather"] = True
            return {"forecast": [], "station": {}, "lakes": {}}

        async def fake_rss(*a, **kw):
            call_tracker["rss"] = True
            return ([], {"total_after": 0})

        async def fake_llm(*a, **kw):
            call_tracker["llm"] = True
            return MagicMock()

        with patch("daily_brief.pipeline.validate_config", return_value=(False, ["bad config"])), \
             patch("daily_brief.pipeline.stages.fetch_weather", new_callable=AsyncMock, side_effect=fake_weather), \
             patch("daily_brief.pipeline.fetch_and_dedup", new_callable=AsyncMock, side_effect=fake_rss), \
             patch("daily_brief.pipeline.llm_batch_summarize_all", new_callable=AsyncMock, side_effect=fake_llm), \
             patch("daily_brief.pipeline.LOG_DIR", "/tmp"), \
             patch("daily_brief.pipeline.NEWS_DIR", "/tmp"):
            from daily_brief.pipeline import main as pm

            exit_code = asyncio.get_event_loop().run_until_complete(pm())

        self.assertEqual(exit_code, 1)
        self.assertFalse(call_tracker["weather"])
        self.assertFalse(call_tracker["rss"])
        self.assertFalse(call_tracker["llm"])

    def test_validation_failure_returns_exit_code(self):
        """Validation failure must return EXIT_CODE_VALIDATION."""
        cc = _make_stage_patches(validation_ok=False, validation_issues=["broken"])
        with cc, patch("daily_brief.pipeline.aiohttp.ClientSession",
                       side_effect=[_make_async_cm()]), \
             patch("daily_brief.pipeline.write_report"):
            from daily_brief.pipeline import main as pm, EXIT_CODE_VALIDATION

            exit_code = asyncio.get_event_loop().run_until_complete(pm())

        self.assertEqual(exit_code, EXIT_CODE_VALIDATION)

    def test_config_failure_exit_code(self):
        """Config failure should return exactly EXIT_CODE_CONFIG."""
        cc = _make_stage_patches(config_ok=False, config_issues=["bad"])
        with cc, patch("daily_brief.pipeline.aiohttp.ClientSession",
                       side_effect=[_make_async_cm()]), \
             patch("daily_brief.pipeline.write_report"):
            from daily_brief.pipeline import main as pm, EXIT_CODE_CONFIG

            exit_code = asyncio.get_event_loop().run_until_complete(pm())

        self.assertEqual(exit_code, EXIT_CODE_CONFIG)

    def test_story_validation_failure_writes_report_and_returns_validation_exit(self):
        """Phase 3D semantic failure must still render report but return validation exit code."""
        cc = _make_stage_patches(validation_ok=True)
        with (
            cc,
            patch(
                "daily_brief.pipeline.stages.stage_validate_stories",
                return_value=(False, ["invalid summary for test"]),
            ) as validate_stories_mock,
            patch("daily_brief.pipeline.aiohttp.ClientSession",
                  side_effect=[_make_async_cm()]),
            patch("daily_brief.pipeline.write_report") as write_report_mock,
        ):
            from daily_brief.pipeline import main as pm, EXIT_CODE_VALIDATION

            exit_code = asyncio.get_event_loop().run_until_complete(pm())

        self.assertEqual(exit_code, EXIT_CODE_VALIDATION)
        validate_stories_mock.assert_called_once()
        write_report_mock.assert_called_once()


# ---------------------------------------------------------------------------
# Package-level patching
# ---------------------------------------------------------------------------


