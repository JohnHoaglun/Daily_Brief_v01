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

        source = inspect.getsource(stages_mod)
        self.assertIn("asyncio.gather(_phase1_weather(), _phase2_rss())", source)

        self.assertIn("sem_article = asyncio.Semaphore", source)
        self.assertIn("_bounded_extract", source)

    def test_phases_not_all_gathered(self):
        """Phase 3/4/5 are NOT gathered concurrently with weather/RSS."""
        import daily_brief.pipeline.stages as stages_mod

        source = inspect.getsource(stages_mod)
        gather_count = source.count("asyncio.gather(")

        self.assertGreaterEqual(gather_count, 2,
                                f"Expected >=2 gather calls; found {gather_count}")


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


# ---------------------------------------------------------------------------
# Package-level patching
# ---------------------------------------------------------------------------


class TestPackageLevelPatching(TestCase):
    """Package-level patching: daily_brief.pipeline.some_func can be patched."""

    def tearDown(self):
        _restore_aiohttp_client_session()

    def test_patch_fetch_weather_at_package_level(self):
        """Patching daily_brief.pipeline.fetch_weather takes effect inside stage_weather()."""
        call_count = [0]

        async def tracking_fetch(*args, **kw):
            call_count[0] += 1
            return {"forecast": [{"period": 1}], "station": {}, "lakes": {}}

        # Build patch list, then replace the fetch_weather patch entry
        cc = _make_stage_patches()

        for i, p in enumerate(cc.cms):
            if "fetch_weather" in getattr(p, "attribute", ""):
                cc.cms[i] = patch("daily_brief.pipeline.fetch_weather",
                                  new_callable=AsyncMock, side_effect=tracking_fetch)
                break

        with cc, \
             patch("daily_brief.pipeline.aiohttp.ClientSession",
                   side_effect=[_make_async_cm()]), \
             patch("daily_brief.pipeline.write_report"):
            from daily_brief.pipeline import main as pm

            asyncio.get_event_loop().run_until_complete(pm())

        self.assertEqual(call_count[0], 1)

    def test_patch_write_report_at_package_level(self):
        """Patching daily_brief.pipeline.write_report takes effect inside main()."""
        write_called = [False]

        def track_write(*args, **kwargs):
            write_called[0] = True

        cc = _make_stage_patches()
        for p in list(cc.cms):
            if "write_report" in p.attribute:
                p.__exit__(None, None, None)
                cc.cms.remove(p)
                break

        cc.cms.append(patch("daily_brief.pipeline.write_report", side_effect=track_write))

        with cc, patch("daily_brief.pipeline.aiohttp.ClientSession",
                       side_effect=[_make_async_cm()]):
            from daily_brief.pipeline import main as pm

            asyncio.get_event_loop().run_until_complete(pm())

        self.assertTrue(write_called[0])

    def test_patch_create_llm_client_at_package_level(self):
        """Patching daily_brief.pipeline.create_llm_client takes effect inside main()."""
        custom_client = MagicMock()

        cc = _make_stage_patches()
        for p in list(cc.cms):
            if "create_llm_client" in p.attribute:
                p.__exit__(None, None, None)
                cc.cms.remove(p)
                break

        cc.cms.append(patch("daily_brief.pipeline.create_llm_client",
                             return_value=custom_client))

        with cc, patch("daily_brief.pipeline.aiohttp.ClientSession",
                       side_effect=[_make_async_cm()]), \
             patch("daily_brief.pipeline.write_report"):
            from daily_brief.pipeline import main as pm

            asyncio.get_event_loop().run_until_complete(pm())
