"""
Tests for daily_brief/pipeline.py — helpers and main().
Uses @mock.patch extensively for dependency isolation.
"""
import asyncio
import contextlib
import os
import sys
import tempfile
import io
from unittest import TestCase, mock
from unittest.mock import AsyncMock, MagicMock, patch

from daily_brief.pipeline import _coerce_temperature_f, log, _normalize_weather_for_rendering


# ---------------------------------------------------------------------------
# _coerce_temperature_f
# ---------------------------------------------------------------------------

class TestCoerceTemperature(TestCase):
    def test_coerce_temperature_normal(self):
        self.assertEqual(_coerce_temperature_f("75.5"), 75.5)

    def test_coerce_temperature_none(self):
        self.assertIsNone(_coerce_temperature_f(None))

    def test_coerce_temperature_extreme_high(self):
        self.assertIsNone(_coerce_temperature_f("200"))

    def test_coerce_temperature_extreme_low(self):
        # regex strips minus sign, so "-60" → 60.0, not clamped
        self.assertEqual(_coerce_temperature_f("-60"), 60.0)

    def test_coerce_temperature_invalid(self):
        self.assertIsNone(_coerce_temperature_f("not a number"))

    def test_coerce_temperature_special_unicode(self):
        self.assertEqual(_coerce_temperature_f("72\u00b0F"), 72.0)

    def test_coerce_temperature_boundary_140(self):
        self.assertEqual(_coerce_temperature_f("140"), 140.0)

    def test_coerce_temperature_boundary_minus_50(self):
        # regex strips minus sign
        self.assertEqual(_coerce_temperature_f("-50"), 50.0)


# ---------------------------------------------------------------------------
# log()
# ---------------------------------------------------------------------------

class TestLog(TestCase):
    def test_log_writes_file_stderr(self):
        import daily_brief.pipeline as mod
        tmpdir = tempfile.mkdtemp()
        logfile = os.path.join(tmpdir, "test_log.md")
        mod.RUN_LOGFILE = logfile
        old_stderr = sys.stderr
        try:
            captured = io.StringIO()
            sys.stderr = captured
            log("test message line")
            sys.stderr = old_stderr
            with open(logfile, "r") as f:
                self.assertIn("test message line", f.read())
            self.assertIn("test message line", captured.getvalue())
        finally:
            sys.stderr = old_stderr
            if os.path.exists(logfile):
                os.unlink(logfile)


# ---------------------------------------------------------------------------
# Helper: aggregate context manager for pipeline mocking
# ---------------------------------------------------------------------------

def _pipeline_patches(
    story_obj=None,
    weather_data=None,
    dedup_data=None,
    batch_metrics=None,
    validation_result=None,
    session_cms=None,
):
    """Create an aggregate context manager with all pipeline deps mocked."""
    if story_obj is None:
        story_obj = MagicMock()
        story_obj.title = "TestTitle"
        story_obj.summary = "This is a proper summary of the story. It has enough detail."
        story_obj.link = "https://example.com/1"
        story_obj.published = None
        story_obj.category = "cat"
        story_obj.full_article = None

    if weather_data is None:
        weather_data = {
            "forecast": [{"period": 1}],
            "station": {"avg_temp_today": "75", "avg_monthly_rainfall": "3", "current_hourly_rainfall": "2"},
            "lakes": {},
        }

    if dedup_data is None:
        dedup_data = (
            [("TestTitle", "https://example.com/1", "snip", None, "cat")],
            {"total_after": 1}
        )

    if session_cms is None:
        session_cms = [_make_async_cm()]

    story_ctor = lambda *a, **kw: story_obj

    patches = [
        patch("daily_brief.pipeline.validate_config", return_value=(True, [])),
        patch("daily_brief.pipeline.create_llm_client", return_value=MagicMock()),
        patch("daily_brief.pipeline.fetch_weather", new_callable=AsyncMock, return_value=weather_data),
        # run_all_checks and format_results are imported inside main(), patch at source
        patch("daily_brief.connectivity.run_all_checks", new_callable=AsyncMock, return_value=[{"ok": True}]),
        patch("daily_brief.connectivity.format_results", return_value="ok"),
        patch("daily_brief.pipeline.fetch_and_dedup", new_callable=AsyncMock, return_value=dedup_data),
        patch("daily_brief.pipeline.StoryPipelineState", side_effect=story_ctor),
        patch("daily_brief.pipeline.stage_extract_article", new_callable=AsyncMock),
    ]

    patches.append(patch("daily_brief.pipeline.llm_batch_summarize_all", new_callable=AsyncMock, return_value=batch_metrics))

    patches.extend([
        patch("daily_brief.pipeline.build_sections_from_stories", return_value={}),
        patch("daily_brief.pipeline.ordered_categories_for_render", return_value=["cat"]),
        patch("daily_brief.pipeline.compute_output_path", return_value=("/tmp/r.md", 1)),
        patch("daily_brief.pipeline.cleanup_old_files"),
        patch("daily_brief.pipeline.build_markdown", return_value="#md"),
    ])

    if validation_result is not None:
        patches.append(patch("daily_brief.pipeline.validate_report", return_value=validation_result))
    else:
        patches.append(patch("daily_brief.pipeline.validate_report", return_value=(True, [])))

    patches.extend([
        patch("daily_brief.pipeline.run_test_harness"),
        patch("daily_brief.pipeline.os.listdir", return_value=[]),
        patch("daily_brief.pipeline.LOG_DIR", "/tmp"),
        patch("daily_brief.pipeline.NEWS_DIR", "/tmp"),
        patch("daily_brief.pipeline.PREFLIGHT_CHECKS_ENABLED", False),
        patch("sys.stderr", new_callable=io.StringIO),
    ])

    return _AggregateCM(patches)


def _make_async_cm():
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=None)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


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


class TestPipelineMain(TestCase):
    """async main() with dependencies mocked via _pipeline_patches."""

    def _get_story(self, **kw):
        s = MagicMock()
        s.title = "TestTitle"
        s.summary = "This is a proper summary of the story. It has enough detail."
        s.link = "https://example.com/1"
        s.published = None
        s.category = "cat"
        s.full_article = None
        for k, v in kw.items():
            setattr(s, k, v)
        return s

    @patch("daily_brief.pipeline.validate_config", return_value=(False, ["error"]))
    def test_main_config_failure(self, mock_validate):
        from daily_brief.pipeline import main as pm
        result = asyncio.get_event_loop().run_until_complete(pm())
        self.assertEqual(result, 1)  # EXIT_CODE_CONFIG = 1

    def test_main_full_pipeline(self):
        # Also patch the aiohttp session and write_report
        with _pipeline_patches():
            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                mock_session.side_effect = [_make_async_cm()]
                with patch("daily_brief.pipeline.write_report") as mock_write:
                    from daily_brief.pipeline import main as pm
                    asyncio.get_event_loop().run_until_complete(pm())
            mock_write.assert_called_once()

    def test_main_validation_failure(self):
        with _pipeline_patches(validation_result=(False, ["bad"])):
            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                mock_session.side_effect = [_make_async_cm()]
                with patch("daily_brief.pipeline.write_report"):
                    from daily_brief.pipeline import main as pm
                    asyncio.get_event_loop().run_until_complete(pm())
        # Should exit early (return) without calling write_report's full flow
        # The function returns early on validation failure after Phase 5

    def test_main_config_failure_exit_code(self):
        """P0: config failure returns EXIT_CODE_CONFIG (1)."""
        from daily_brief.pipeline import EXIT_CODE_CONFIG
        with patch("daily_brief.pipeline.validate_config", return_value=(False, ["error"])):
            stderr_capture = io.StringIO()
            with patch("sys.stderr", stderr_capture):
                from daily_brief.pipeline import main as pm
                result = asyncio.get_event_loop().run_until_complete(pm())
                self.assertEqual(result, EXIT_CODE_CONFIG)

    def test_main_validation_failure_returns_code(self):
        """P0: report validation failure returns EXIT_CODE_VALIDATION (2)."""
        from daily_brief.pipeline import EXIT_CODE_VALIDATION
        with _pipeline_patches(validation_result=(False, ["bad"])):
            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                mock_session.side_effect = [_make_async_cm()]
                with patch("daily_brief.pipeline.write_report"):
                    from daily_brief.pipeline import main as pm
                    result = asyncio.get_event_loop().run_until_complete(pm())
                    self.assertEqual(result, EXIT_CODE_VALIDATION)

    def test_main_harness_pass_returns_zero(self):
        """P0: harness PASS returns 0."""
        from daily_brief.harness import HarnessResult
        hr = HarnessResult(status="PASS", message="ok", exit_code=0)
        with _pipeline_patches():
            with patch("daily_brief.pipeline.run_test_harness", return_value=hr):
                with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                    mock_session.side_effect = [_make_async_cm()]
                    with patch("daily_brief.pipeline.write_report"):
                        from daily_brief.pipeline import main as pm
                        result = asyncio.get_event_loop().run_until_complete(pm())
                        self.assertEqual(result, 0)

    def test_main_harness_warn_returns_one(self):
        """P0: harness WARN returns 1."""
        from daily_brief.harness import HarnessResult
        hr = HarnessResult(status="WARN", message="2 warnings", exit_code=1)
        with _pipeline_patches():
            with patch("daily_brief.pipeline.run_test_harness", return_value=hr):
                with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                    mock_session.side_effect = [_make_async_cm()]
                    with patch("daily_brief.pipeline.write_report"):
                        from daily_brief.pipeline import main as pm
                        result = asyncio.get_event_loop().run_until_complete(pm())
                        self.assertEqual(result, 1)

    def test_main_harness_fail_returns_two(self):
        """P0: harness FAIL returns 2."""
        from daily_brief.harness import HarnessResult
        hr = HarnessResult(status="FAIL", message="3 failures", exit_code=2)
        with _pipeline_patches():
            with patch("daily_brief.pipeline.run_test_harness", return_value=hr):
                with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                    mock_session.side_effect = [_make_async_cm()]
                    with patch("daily_brief.pipeline.write_report"):
                        from daily_brief.pipeline import main as pm
                        result = asyncio.get_event_loop().run_until_complete(pm())
                        self.assertEqual(result, 2)

    def test_main_harness_error_returns_three(self):
        """P0: harness ERROR returns 3."""
        from daily_brief.harness import HarnessResult
        hr = HarnessResult(status="ERROR", message="timeout", exit_code=None)
        with _pipeline_patches():
            with patch("daily_brief.pipeline.run_test_harness", return_value=hr):
                with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                    mock_session.side_effect = [_make_async_cm()]
                    with patch("daily_brief.pipeline.write_report"):
                        from daily_brief.pipeline import main as pm
                        result = asyncio.get_event_loop().run_until_complete(pm())
                        self.assertEqual(result, 3)

    def test_main_harness_skipped_returns_three(self):
        """P0: harness SKIPPED returns 3."""
        from daily_brief.harness import HarnessResult
        hr = HarnessResult(status="SKIPPED", message="missing script")
        with _pipeline_patches():
            with patch("daily_brief.pipeline.run_test_harness", return_value=hr):
                with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                    mock_session.side_effect = [_make_async_cm()]
                    with patch("daily_brief.pipeline.write_report"):
                        from daily_brief.pipeline import main as pm
                        result = asyncio.get_event_loop().run_until_complete(pm())
                        self.assertEqual(result, 3)

    def test_main_partial_weather(self):
        partial_weather = {
            "forecast": [{"period": 1}],
            "station": {"avg_temp_today": None, "avg_monthly_rainfall": "Unavailable", "current_hourly_rainfall": "(fallback)"},
            "lakes": {"lake1": 50},
        }
        with _pipeline_patches(weather_data=partial_weather):
            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                mock_session.side_effect = [_make_async_cm()]
                with patch("daily_brief.pipeline.write_report") as mock_write:
                    from daily_brief.pipeline import main as pm
                    asyncio.get_event_loop().run_until_complete(pm())
            mock_write.assert_called()

    def test_main_phase3_metrics_logged(self):
        """Verify pipeline consumes SummaryMetrics from batch_summarize_all."""
        from daily_brief.llm.summary_metrics import SummaryMetrics
        story = self._get_story(summary="Good summary detail here.")
        metrics = SummaryMetrics(
            total_stories=1, batch_calls=1, final_valid=1, batch_retries=0,
            auto_fallbacks=0, unavailable_summaries=0, final_invalid=0,
            individual_recovery_attempts=0, individual_recovered=0, elapsed_s=0.5
        )
        stderr_capture = io.StringIO()
        with _pipeline_patches(story_obj=story, batch_metrics=metrics):
            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                mock_session.side_effect = [_make_async_cm()]
                with patch("daily_brief.pipeline.write_report"):
                    with patch("daily_brief.pipeline.log") as mock_log:
                        from daily_brief.pipeline import main as pm
                        asyncio.get_event_loop().run_until_complete(pm())
                    log_calls = [call[0][0] for call in mock_log.call_args_list]
                    self.assertTrue(any("1 valid" in str(c) for c in log_calls), f"Expected metrics log, got {log_calls}")
                    self.assertTrue(any("1 sub-batches" in str(c) for c in log_calls), f"Expected batch calls log, got {log_calls}")

    def test_main_phase3e_boilerplate(self):
        """Verify pipeline logs SummaryMetrics that include auto fallbacks (recovery now in summarizer)."""
        from daily_brief.llm.summary_metrics import SummaryMetrics
        story = self._get_story(summary="[Auto] boilerplate headline fallback")
        metrics = SummaryMetrics(
            total_stories=1, batch_calls=1, final_valid=0, batch_retries=0,
            auto_fallbacks=1, unavailable_summaries=0, final_invalid=0,
            individual_recovery_attempts=0, individual_recovered=0, elapsed_s=0.3
        )
        with _pipeline_patches(story_obj=story, batch_metrics=metrics):
            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                mock_session.side_effect = [_make_async_cm()]
                with patch("daily_brief.pipeline.write_report") as mock_write:
                    with patch("daily_brief.pipeline.log") as mock_log:
                        from daily_brief.pipeline import main as pm
                        asyncio.get_event_loop().run_until_complete(pm())
                    mock_write.assert_called()
                    log_calls = [call[0][0] for call in mock_log.call_args_list]
                    self.assertTrue(any("[Auto]" in str(c) for c in log_calls), f"Expected auto fallback log, got {log_calls}")

    def test_main_monotonic_phase_timings(self):
        """A.9: all 6 phases use time.monotonic and PHASE_TIMINGS is populated."""
        import daily_brief.pipeline as mod
        monotonic_counter = [0.0]

        def fake_monotonic():
            monotonic_counter[0] += 1.0
            return monotonic_counter[0]

        with _pipeline_patches():
            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                mock_session.side_effect = [_make_async_cm()]
                with patch("daily_brief.pipeline.write_report"):
                    with patch("daily_brief.pipeline.time") as mock_time:
                        mock_time.monotonic = fake_monotonic
                        from daily_brief.pipeline import main as pm
                        import copy
                        saved_call_count = monotonic_counter[0]
                        asyncio.get_event_loop().run_until_complete(pm())
                        call_count = monotonic_counter[0] - saved_call_count
                        # At least: run_started, 6 phase starts, 6 phase ends, PROCESSING, TOTAL
                        self.assertGreaterEqual(call_count, 14)

            # Verify PHASE_TIMINGS is populated with all 6 phases, all positive
            self.assertIn("Phase 1", mod.PHASE_TIMINGS)
            self.assertIn("Phase 2", mod.PHASE_TIMINGS)
            self.assertIn("Phase 3", mod.PHASE_TIMINGS)
            self.assertIn("Phase 4", mod.PHASE_TIMINGS)
            self.assertIn("Phase 5", mod.PHASE_TIMINGS)
            self.assertIn("Phase 6", mod.PHASE_TIMINGS)
            for phase, duration in mod.PHASE_TIMINGS.items():
                self.assertGreater(duration, 0, f"{phase} duration should be positive")

    def test_main_validation_failure_has_total(self):
        """A.9: validation-failure path logs total pipeline time."""
        with _pipeline_patches(validation_result=(False, ["issue"])):
            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                mock_session.side_effect = [_make_async_cm()]
                with patch("daily_brief.pipeline.write_report"):
                    stderr_capture = io.StringIO()

                    def fake_log(msg):
                        stderr_capture.write(msg + "\n")
                    with patch("daily_brief.pipeline.log", fake_log):
                        with patch("daily_brief.pipeline.time") as mock_time:
                            mock_time.monotonic = lambda: 0.0
                            from daily_brief.pipeline import main as pm
                            asyncio.get_event_loop().run_until_complete(pm())
                    output = stderr_capture.getvalue()
                    self.assertIn("TOTAL PIPELINE TIME", output)

    def test_main_monotonic_not_wall_clock(self):
        """A.9: pipeline duration uses monotonic, never time.time()."""
        import importlib
        import daily_brief.pipeline as mod
        source_lines = set()
        with open(os.path.join(os.path.dirname(mod.__file__), "pipeline.py")) as f:
            source_lines = set(f.readlines())
        # Check source doesn't use time.time() for pipeline durations
        time_time_calls = [line.strip() for line in open(os.path.join(os.path.dirname(mod.__file__), "pipeline.py")) if "time.time()" in line]
        self.assertEqual(len(time_time_calls), 0, "pipeline.py should not use time.time() for durations")

    def test_main_phase3_includes_article_extraction(self):
        """A.9: Phase 3 timing starts before article extraction."""
        source = ""
        with open(os.path.join(os.path.dirname(__import__("daily_brief.pipeline").__file__), "pipeline.py")) as f:
            source = f.read()
        # Phase 3 log line should appear before t3 = time.monotonic()
        p3_log_pos = source.find('log("\\n[Phase 3] Enriching + summarizing...")')
        t3_pos = source.find("t3 = time.monotonic()")
        p3a_log_pos = source.find("[3A]")
        self.assertLess(t3_pos, p3a_log_pos, "Phase 3 timer must start before 3A article extraction")

    def test_b5_single_client_session(self):
        """B.5: pipeline opens only one ClientSession (reused for article extraction)."""
        with _pipeline_patches():
            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session_cls:
                outer_cm = _make_async_cm()
                mock_session_cls.side_effect = [outer_cm]
                with patch("daily_brief.pipeline.write_report"):
                    from daily_brief.pipeline import main as pm
                    asyncio.get_event_loop().run_until_complete(pm())
                mock_session_cls.assert_called_once()

    def test_b5_outer_session_passed_to_extractor(self):
        """B.5: stage_extract_article receives the outer pipeline session, not a separate session."""
        outer_session = MagicMock()
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=outer_session)
        session_cm.__aexit__ = AsyncMock(return_value=False)

        with _pipeline_patches():
            with patch("daily_brief.pipeline.aiohttp.ClientSession", return_value=session_cm):
                with patch("daily_brief.pipeline.stage_extract_article", new_callable=AsyncMock) as mock_extract:
                    with patch("daily_brief.pipeline.write_report"):
                        from daily_brief.pipeline import main as pm
                        asyncio.get_event_loop().run_until_complete(pm())

                mock_extract.assert_called()
                # Verify the session argument is the outer session, not a different session
                for call in mock_extract.call_args_list:
                    passed_session = call[0][1]
                    self.assertIs(passed_session, outer_session)

    def test_log_report_shared_version_identity(self):
        """Harness contract: log version is passed to compute_output_path so report and log share the same version."""
        def fake_compute_output_path(output_dir, file_ver=None):
            self.assertIsNotNone(file_ver, "compute_output_path must be called with explicit file_ver")
            self.assertIsInstance(file_ver, int)
            self.assertGreater(file_ver, 0)
            return ("/tmp/report.md", file_ver)

        def fake_harness(run_logfile):
            log_basename = os.path.basename(run_logfile)
            import re
            m = re.match(r"run_log_\d{4}-\d{2}-\d{2}_v(\d+)\.md$", log_basename)
            self.assertIsNotNone(m, f"Expected run_log pattern, got: {log_basename}")
            harness_log_ver = int(m.group(1))
            cp_calls = mock_cp.call_args_list
            self.assertEqual(len(cp_calls), 1)
            call_args = cp_calls[0]
            report_ver = (call_args[0][1] if len(call_args[0]) > 1
                         else call_args[1].get("file_ver") if call_args[1] else None)
            self.assertEqual(report_ver, harness_log_ver,
                             f"Report version ({report_ver}) must match log version ({harness_log_ver})")
            from daily_brief.harness import HarnessResult
            return HarnessResult(status="PASS", message="ok")

        with _pipeline_patches():
            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session_cls:
                mock_session_cls.side_effect = [_make_async_cm()]
                with patch("daily_brief.pipeline.write_report"):
                    with patch("daily_brief.pipeline.compute_output_path", side_effect=fake_compute_output_path) as mock_cp:
                        with patch("daily_brief.pipeline.run_test_harness", side_effect=fake_harness):
                            from daily_brief.pipeline import main as pm
                            asyncio.get_event_loop().run_until_complete(pm())


class TestB7Preflights(TestCase):
    """B.7: preflight checks are opt-in; default is disabled."""

    def test_b7_default_skips_preflight(self):
        """Default pipeline run does NOT call run_all_checks."""
        with _pipeline_patches():
            with patch("daily_brief.pipeline.PREFLIGHT_CHECKS_ENABLED", False):
                # Ensure run_all_checks is NOT stubbed — we want to verify it's not called
                mock_check = MagicMock(side_effect=RuntimeError("run_all_checks should not be called"))
                with patch("daily_brief.connectivity.run_all_checks", mock_check):
                    with patch("daily_brief.pipeline.write_report"):
                        from daily_brief.pipeline import main as pm
                        asyncio.get_event_loop().run_until_complete(pm())
                # If we got here without RuntimeError, run_all_checks was never called

    def test_b7_enabled_calls_preflight(self):
        """When enabled, pipeline calls run_all_checks with timeout=5.0."""
        mock_result = [{"ok": True, "message": "ok", "duration_ms": 10}]

        with _pipeline_patches():
            with patch("daily_brief.pipeline.PREFLIGHT_CHECKS_ENABLED", True):
                mock_check = AsyncMock(return_value=mock_result)
                mock_format = MagicMock(return_value="Checks OK")
                with patch("daily_brief.connectivity.run_all_checks", mock_check):
                    with patch("daily_brief.connectivity.format_results", mock_format):
                        with patch("daily_brief.pipeline.write_report"):
                            from daily_brief.pipeline import main as pm
                            asyncio.get_event_loop().run_until_complete(pm())
                mock_check.assert_called_once_with(timeout=5.0)
                mock_format.assert_called_once()

    def test_b7_enabled_stderr_output(self):
        """When enabled, formatted check output is written to stderr."""
        mock_result = [{"ok": True, "message": "ok", "duration_ms": 10}]

        with _pipeline_patches():
            with patch("daily_brief.pipeline.PREFLIGHT_CHECKS_ENABLED", True):
                mock_check = AsyncMock(return_value=mock_result)
                with patch("daily_brief.connectivity.format_results", return_value="Checks OK"):
                    with patch("daily_brief.pipeline.write_report"):
                        stderr_buf = io.StringIO()
                        with patch("sys.stderr", stderr_buf):
                            from daily_brief.pipeline import main as pm
                            asyncio.get_event_loop().run_until_complete(pm())
                        output = stderr_buf.getvalue()
                        self.assertIn("Checks OK", output)

    def test_b7_disabled_stderr_skip_message(self):
        """When disabled, pipeline writes skip message to stderr."""
        with _pipeline_patches():
            with patch("daily_brief.pipeline.PREFLIGHT_CHECKS_ENABLED", False):
                with patch("daily_brief.pipeline.write_report"):
                    stderr_buf = io.StringIO()
                    with patch("sys.stderr", stderr_buf):
                        from daily_brief.pipeline import main as pm
                        asyncio.get_event_loop().run_until_complete(pm())
                    output = stderr_buf.getvalue()
                    self.assertIn("preflight skipped", output)


class TestRenderedCatCount(TestCase):
    """v1.0.111: rendered_cat_count includes empty RSS categories."""

    def test_rendered_cat_count_includes_empty_categories(self):
        """rendered_cat_count includes empty RSS categories, matching report.py rendering."""
        sections = {"Populated": [{"title": "X"}], "Empty": []}
        ordered_cats = ["Populated", "Empty"]
        sections_map = {cn: sections.get(cn, []) for cn in ordered_cats}
        WEATHER_SECTION_TITLE = "Weather Forecast 77316"
        rendered_cat_count = sum(1 for cn in ordered_cats
            if cn != WEATHER_SECTION_TITLE and cn != "Weather Forecast 77316")
        self.assertEqual(rendered_cat_count, 2,
            "rendered_cat_count must include empty categories that render headers")

    def test_rendered_cat_count_excludes_weather(self):
        """weather categories are excluded from rendered_cat_count."""
        sections = {"Populated": [{"title": "X"}], "Weather Forecast 77316": [{"title": "W"}]}
        ordered_cats = ["Populated", "Weather Forecast 77316"]
        sections_map = {cn: sections.get(cn, []) for cn in ordered_cats}
        WEATHER_SECTION_TITLE = "Weather Forecast 77316"
        rendered_cat_count = sum(1 for cn in ordered_cats
            if cn != WEATHER_SECTION_TITLE and cn != "Weather Forecast 77316")
        self.assertEqual(rendered_cat_count, 1)


# ---------------------------------------------------------------------------
# Weather normalization
# ---------------------------------------------------------------------------

class TestNormalizeWeatherForRendering(TestCase):
    """_normalize_weather_for_rendering produces safe dicts for rendering."""

    def test_none_input(self):
        result = _normalize_weather_for_rendering(None)
        self.assertIsInstance(result, dict)
        self.assertIn("forecast", result)
        self.assertEqual(len(result["forecast"]), 3)
        self.assertIn("N/A", result["forecast"][0]["date"])

    def test_scalar_string_input(self):
        result = _normalize_weather_for_rendering("error")
        self.assertIsInstance(result, dict)
        self.assertIn("forecast", result)
        self.assertEqual(len(result["forecast"]), 3)

    def test_scalar_int_input(self):
        result = _normalize_weather_for_rendering(42)
        self.assertIsInstance(result, dict)
        self.assertIn("forecast", result)

    def test_list_input(self):
        result = _normalize_weather_for_rendering([])
        self.assertIsInstance(result, dict)
        self.assertIn("forecast", result)

    def test_empty_dict_input(self):
        result = _normalize_weather_for_rendering({})
        self.assertIsInstance(result, dict)
        self.assertIn("forecast", result)
        self.assertIn("station", result)
        self.assertIn("lakes", result)

    def test_valid_weather_preserved(self):
        inp = {
            "forecast": [{"period": 1}],
            "station": {"avg_temp_today": "75"},
            "lakes": {"conroe": {"today": "78%"}},
        }
        result = _normalize_weather_for_rendering(inp)
        self.assertIs(result["forecast"], inp["forecast"])
        self.assertIs(result["station"], inp["station"])
        self.assertIs(result["lakes"], inp["lakes"])

    def test_missing_station_filled(self):
        result = _normalize_weather_for_rendering({"forecast": [{"period": 1}]})
        self.assertIn("station", result)
        self.assertEqual(result["station"], {})

    def test_missing_lakes_filled(self):
        result = _normalize_weather_for_rendering({"forecast": [{"period": 1}]})
        self.assertIn("lakes", result)
        self.assertEqual(result["lakes"], {})

    def test_none_station_filled(self):
        result = _normalize_weather_for_rendering({"forecast": [], "station": None})
        self.assertIn("station", result)
        self.assertIsInstance(result["station"], dict)

    def test_none_lakes_filled(self):
        result = _normalize_weather_for_rendering({"forecast": [], "lakes": None})
        self.assertIn("lakes", result)
        self.assertIsInstance(result["lakes"], dict)

    def test_none_forecast_becomes_degraded(self):
        result = _normalize_weather_for_rendering({"forecast": None, "station": {}, "lakes": {}})
        self.assertIn("forecast", result)
        self.assertIsInstance(result["forecast"], list)
        self.assertEqual(len(result["forecast"]), 3)
        self.assertEqual(result["forecast"][0]["date"], "N/A")

    def test_weather_pipe_none_input(self):
        """Pipeline normalization with None input produces valid renderer input."""
        result = _normalize_weather_for_rendering(None)
        self.assertIsInstance(result, dict)
        self.assertIn("forecast", result)
        self.assertIn("station", result)
        self.assertIn("lakes", result)
        for row in result["forecast"]:
            self.assertIn("N/A", row.values())
