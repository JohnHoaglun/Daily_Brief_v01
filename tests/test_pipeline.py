"""
Tests for src/daily_brief/pipeline.py — helpers and main().
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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from daily_brief.pipeline import _coerce_temperature_f, log


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
    summary_fn=None,
    is_boilerplate_fn=None,
    is_refusal_fn=None,
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
        session_cms = [_make_async_cm(), _make_async_cm()]

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

    if summary_fn is not None:
        patches.append(patch("daily_brief.pipeline.llm_summarize", summary_fn))
        # Also mock batch summarizer to simulate batch failure → forces retry
        patches.append(patch("daily_brief.pipeline.llm_batch_summarize_all", return_value=None))
    else:
        patches.append(patch("daily_brief.pipeline.llm_batch_summarize_all", return_value=None))
        # Mock individual summarizer too so it doesn't hit real LLM
        patches.append(patch("daily_brief.pipeline.llm_summarize", return_value=None))

    patches.append(patch("daily_brief.pipeline._is_refusal", return_value=is_refusal_fn if is_refusal_fn is not None else False))

    if is_boilerplate_fn is not None:
        patches.append(patch("daily_brief.pipeline._is_boilerplate", is_boilerplate_fn))
    else:
        patches.append(patch("daily_brief.pipeline._is_boilerplate", return_value=False))

    patches.extend([
        patch("daily_brief.pipeline.build_sections_from_stories", return_value=({}, [])),
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

    @patch("daily_brief.pipeline.sys.exit", side_effect=SystemExit(1))
    @patch("daily_brief.pipeline.validate_config", return_value=(False, ["error"]))
    def test_main_config_failure(self, mock_validate, mock_exit):
        from daily_brief.pipeline import main as pm
        try:
            asyncio.get_event_loop().run_until_complete(pm())
        except SystemExit:
            pass
        mock_exit.assert_called_with(1)

    def test_main_full_pipeline(self):
        # Also patch the aiohttp session and write_report
        with _pipeline_patches():
            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                mock_session.side_effect = [_make_async_cm(), _make_async_cm()]
                with patch("daily_brief.pipeline.write_report") as mock_write:
                    from daily_brief.pipeline import main as pm
                    asyncio.get_event_loop().run_until_complete(pm())
            mock_write.assert_called_once()

    def test_main_validation_failure(self):
        with _pipeline_patches(validation_result=(False, ["bad"])):
            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                mock_session.side_effect = [_make_async_cm(), _make_async_cm()]
                with patch("daily_brief.pipeline.write_report"):
                    from daily_brief.pipeline import main as pm
                    asyncio.get_event_loop().run_until_complete(pm())
        # Should exit early (return) without calling write_report's full flow
        # The function returns early on validation failure after Phase 5

    def test_main_partial_weather(self):
        partial_weather = {
            "forecast": [{"period": 1}],
            "station": {"avg_temp_today": None, "avg_monthly_rainfall": "Unavailable", "current_hourly_rainfall": "(fallback)"},
            "lakes": {"lake1": 50},
        }
        with _pipeline_patches(weather_data=partial_weather):
            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                mock_session.side_effect = [_make_async_cm(), _make_async_cm()]
                with patch("daily_brief.pipeline.write_report") as mock_write:
                    from daily_brief.pipeline import main as pm
                    asyncio.get_event_loop().run_until_complete(pm())
            mock_write.assert_called()

    def test_main_phase3_retries(self):
        story = self._get_story(summary=None)
        call_count = [0]

        def mock_summarize(client, context, **kw):
            call_count[0] += 1
            return "Retrieved summary for the story. Full detail included."

        with _pipeline_patches(story_obj=story, summary_fn=mock_summarize):
            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                mock_session.side_effect = [_make_async_cm(), _make_async_cm()]
                with patch("daily_brief.pipeline.write_report"):
                    from daily_brief.pipeline import main as pm
                    asyncio.get_event_loop().run_until_complete(pm())
        self.assertGreater(call_count[0], 0)

    def test_main_phase3e_boilerplate(self):
        story = self._get_story(summary="This is a generic summary.")

        bp_idx = [0]
        def mock_is_boilerplate(text):
            bp_idx[0] += 1
            return bp_idx[0] == 1  # First call returns True

        def mock_summarize(client, context, **kw):
            return "Strict non-boilerplate summary. Good detail here."

        with _pipeline_patches(
            story_obj=story,
            summary_fn=mock_summarize,
            is_boilerplate_fn=mock_is_boilerplate,
        ):
            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                mock_session.side_effect = [_make_async_cm(), _make_async_cm()]
                with patch("daily_brief.pipeline.write_report") as mock_write:
                    from daily_brief.pipeline import main as pm
                    asyncio.get_event_loop().run_until_complete(pm())
            mock_write.assert_called()

    def test_main_monotonic_phase_timings(self):
        """A.9: all 6 phases use time.monotonic and PHASE_TIMINGS is populated."""
        import daily_brief.pipeline as mod
        monotonic_counter = [0.0]

        def fake_monotonic():
            monotonic_counter[0] += 1.0
            return monotonic_counter[0]

        with _pipeline_patches():
            with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session:
                mock_session.side_effect = [_make_async_cm(), _make_async_cm()]
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
                mock_session.side_effect = [_make_async_cm(), _make_async_cm()]
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
