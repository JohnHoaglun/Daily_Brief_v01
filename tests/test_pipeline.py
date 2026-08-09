"""
Tests for daily_brief/pipeline.py -- helpers and main().
"""
import asyncio
import os
import sys
import io
import tempfile
import pytest
from unittest import TestCase, mock
from unittest.mock import AsyncMock, MagicMock, patch

from daily_brief.pipeline import _coerce_temperature_f, _normalize_weather_for_rendering


# ---------------------------------------------------------------------------
# _coerce_temperature_f
# ---------------------------------------------------------------------------

class TestCoerceTemperature(TestCase):
    def test_normal_float(self):
        assert _coerce_temperature_f("75.5") == 75.5

    def test_none(self):
        assert _coerce_temperature_f(None) is None

    def test_invalid(self):
        assert _coerce_temperature_f("not a number") is None

    def test_unicode_degree(self):
        assert _coerce_temperature_f("72\u00b0F") == 72.0

    def test_extreme_high_clamped(self):
        assert _coerce_temperature_f("200") is None

    def test_boundary_140(self):
        assert _coerce_temperature_f("140") == 140.0


# ---------------------------------------------------------------------------
# Weather normalization
# ---------------------------------------------------------------------------

class TestNormalizeWeather(TestCase):
    def test_none_input_safedefault(self):
        result = _normalize_weather_for_rendering(None)
        assert isinstance(result, dict)
        for key in ("forecast", "station", "lakes"):
            assert key in result
        assert len(result["forecast"]) == 3
        assert "N/A" in result["forecast"][0]["date"]

    def test_scalar_and_list_input(self):
        for inp in ("error", 42, []):
            result = _normalize_weather_for_rendering(inp)
            assert isinstance(result, dict) and "forecast" in result

    def test_empty_dict(self):
        result = _normalize_weather_for_rendering({})
        assert all(k in result for k in ("forecast", "station", "lakes"))

    def test_valid_weather_passthrough(self):
        inp = {"forecast": [{"period": 1}], "station": {"a": "b"}, "lakes": {"x": 1}}
        result = _normalize_weather_for_rendering(inp)
        assert result["forecast"] is inp["forecast"]
        assert result["station"] is inp["station"]
        assert result["lakes"] is inp["lakes"]


# ---------------------------------------------------------------------------
# Pipeline main -- helpers
# ---------------------------------------------------------------------------

def _make_async_cm():
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=None)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _story(title="TestTitle", summary="Good summary detail here. Enough detail.",
           link="https://example.com/1", category="cat"):
    s = MagicMock()
    s.title = title
    s.summary = summary
    s.link = link
    s.published = None
    s.category = category
    s.full_article = None
    return s


def _patches(story_obj=None, weather_data=None, validation_result=None,
             batch_metrics=None, dedup_data=None):
    if story_obj is None:
        story_obj = _story()
    if weather_data is None:
        weather_data = {
            "forecast": [{"period": 1}],
            "station": {"avg_temp_today": "75", "avg_monthly_rainfall": "3", "current_hourly_rainfall": "2"},
            "lakes": {},
        }
    if dedup_data is None:
        dedup_data = ([("TestTitle", "https://example.com/1", "snip", None, "cat")],
                      {"total_after": 1})
    story_ctor = lambda *a, **kw: story_obj

    patches = [
        patch("daily_brief.pipeline.validate_config", return_value=(True, [])),
        patch("daily_brief.pipeline.create_llm_client", return_value=MagicMock()),
        patch("daily_brief.pipeline.fetch_weather", new_callable=AsyncMock, return_value=weather_data),
        patch("daily_brief.connectivity.run_all_checks", new_callable=AsyncMock, return_value=[{"ok": True}]),
        patch("daily_brief.connectivity.format_results", return_value="ok"),
        patch("daily_brief.pipeline.fetch_and_dedup", new_callable=AsyncMock, return_value=dedup_data),
        patch("daily_brief.pipeline.StoryPipelineState", side_effect=story_ctor),
        patch("daily_brief.pipeline.stage_extract_article", new_callable=AsyncMock),
        patch("daily_brief.pipeline.llm_batch_summarize_all", new_callable=AsyncMock, return_value=batch_metrics),
        patch("daily_brief.pipeline.build_sections_from_stories", return_value={}),
        patch("daily_brief.pipeline.ordered_categories_for_render", return_value=["cat"]),
        patch("daily_brief.pipeline.compute_output_path", return_value=("/tmp/r.md", 1)),
        patch("daily_brief.pipeline.cleanup_old_files"),
        patch("daily_brief.pipeline.build_markdown", return_value=["#md"]),
        patch("daily_brief.pipeline.validate_report", return_value=validation_result or (True, [])),
        patch("daily_brief.pipeline.run_test_harness"),
        patch("daily_brief.pipeline.os.listdir", return_value=[]),
        patch("daily_brief.pipeline.LOG_DIR", "/tmp"),
        patch("daily_brief.pipeline.NEWS_DIR", "/tmp"),
        patch("daily_brief.pipeline.PREFLIGHT_CHECKS_ENABLED", False),
        patch("sys.stderr", new_callable=io.StringIO),
    ]
    return _AggregateCM(patches)


class _AggregateCM:
    def __init__(self, cms):
        self.cms = cms
    def __enter__(self):
        self.entries = [cm.__enter__() for cm in self.cms]
        return self.entries
    def __exit__(self, *exc):
        for cm in reversed(self.cms):
            cm.__exit__(*exc)


# ---------------------------------------------------------------------------
# Pipeline main
# ---------------------------------------------------------------------------

def _run_main(patches_ctx, session_cm=None, extra_patches=None):
    with patches_ctx:
        with patch("daily_brief.pipeline.aiohttp.ClientSession") as mock_session_cls:
            if session_cm is None:
                mock_session_cls.side_effect = [_make_async_cm()]
            else:
                mock_session_cls.side_effect = [session_cm]
            with patch("daily_brief.pipeline.write_report"):
                if extra_patches:
                    for ep in extra_patches:
                        ep.__enter__()
                    try:
                            from daily_brief.pipeline import main as pm
                            import asyncio
                            return asyncio.get_event_loop().run_until_complete(pm())
                    finally:
                        for ep in reversed(extra_patches):
                            ep.__exit__(None, None, None)
                else:
                    from daily_brief.pipeline import main as pm
                    import asyncio
                    return asyncio.get_event_loop().run_until_complete(pm())


class TestPipelineMain(TestCase):

    def test_happy_path_writes_report(self):
        mock_write = MagicMock()
        with _patches():
            session_p = patch("daily_brief.pipeline.aiohttp.ClientSession", side_effect=[_make_async_cm()])
            write_p = patch("daily_brief.pipeline.write_report", mock_write)
            session_p.__enter__()
            write_p.__enter__()
            try:
                from daily_brief.pipeline import main as pm
                asyncio.get_event_loop().run_until_complete(pm())
            finally:
                write_p.__exit__(None, None, None)
                session_p.__exit__(None, None, None)
        mock_write.assert_called_once()

    def test_config_failure_exit(self):
        from daily_brief.pipeline import EXIT_CODE_CONFIG
        with patch("daily_brief.pipeline.validate_config", return_value=(False, ["bad"])):
            from daily_brief.pipeline import main as pm
            import asyncio
            result = asyncio.get_event_loop().run_until_complete(pm())
            assert result == EXIT_CODE_CONFIG

    def test_validation_failure_exit(self):
        from daily_brief.pipeline import EXIT_CODE_VALIDATION
        with _patches(validation_result=(False, ["bad"])):
            session = patch("daily_brief.pipeline.aiohttp.ClientSession")
            session.side_effect = [_make_async_cm()]
            session.__enter__()
            wr = patch("daily_brief.pipeline.write_report")
            wr.__enter__()
            try:
                from daily_brief.pipeline import main as pm
                import asyncio
                result = asyncio.get_event_loop().run_until_complete(pm())
            finally:
                wr.__exit__(None, None, None)
                session.__exit__(None, None, None)
            assert result == EXIT_CODE_VALIDATION

    def test_harness_status_mapping(self):
        """PASS=0, WARN=1, FAIL=2, ERROR=3, SKIPPED=3."""
        from daily_brief.harness import HarnessResult
        for status, expected in [("PASS", 0), ("WARN", 1), ("FAIL", 2), ("ERROR", 3), ("SKIPPED", 3)]:
            hr = HarnessResult(status=status, message="msg", exit_code=0 if status != "ERROR" else None)
            with _patches():
                hr_patch = patch("daily_brief.pipeline.run_test_harness", return_value=hr)
                sess = patch("daily_brief.pipeline.aiohttp.ClientSession", side_effect=[_make_async_cm()])
                wr = patch("daily_brief.pipeline.write_report")
                hr_patch.__enter__()
                sess.__enter__()
                wr.__enter__()
                try:
                    from daily_brief.pipeline import main as pm
                    import asyncio
                    result = asyncio.get_event_loop().run_until_complete(pm())
                finally:
                    wr.__exit__(None, None, None)
                    sess.__exit__(None, None, None)
                    hr_patch.__exit__(None, None, None)
                assert result == expected, f"Expected {expected} for {status}, got {result}"

    def test_partial_weather_handoff(self):
        partial = {
            "forecast": [{"period": 1}],
            "station": {"avg_temp_today": None, "avg_monthly_rainfall": "Unavailable", "current_hourly_rainfall": "(fallback)"},
            "lakes": {"lake1": 50},
        }
        mock_write = MagicMock()
        with _patches(weather_data=partial):
            sess_p = patch("daily_brief.pipeline.aiohttp.ClientSession", side_effect=[_make_async_cm()])
            wr_p = patch("daily_brief.pipeline.write_report", mock_write)
            sess_p.__enter__()
            wr_p.__enter__()
            try:
                from daily_brief.pipeline import main as pm
                asyncio.get_event_loop().run_until_complete(pm())
            finally:
                wr_p.__exit__(None, None, None)
                sess_p.__exit__(None, None, None)
        mock_write.assert_called()

    def test_report_log_shared_version(self):
        """compute_output_path called with explicit file_ver; report and log share version."""
        captured_ver = [None]
        def fake_compute(output_dir, file_ver=None):
            captured_ver[0] = file_ver
            assert file_ver is not None and isinstance(file_ver, int) and file_ver > 0
            return ("/tmp/report.md", file_ver)

        def fake_harness(run_logfile):
            from daily_brief.harness import HarnessResult
            import re
            basename = os.path.basename(run_logfile)
            m = re.match(r"run_log_\d{4}-\d{2}-\d{2}_v(\d+)\.md$", basename)
            assert m is not None, f"Unexpected log name: {basename}"
            return HarnessResult(status="PASS", message="ok")

        with _patches():
            cp = patch("daily_brief.pipeline.compute_output_path", side_effect=fake_compute)
            hr = patch("daily_brief.pipeline.run_test_harness", side_effect=fake_harness)
            sess = patch("daily_brief.pipeline.aiohttp.ClientSession", side_effect=[_make_async_cm()])
            wr = patch("daily_brief.pipeline.write_report")
            cp.__enter__()
            hr.__enter__()
            sess.__enter__()
            wr.__enter__()
            try:
                from daily_brief.pipeline import main as pm
                import asyncio
                asyncio.get_event_loop().run_until_complete(pm())
            finally:
                wr.__exit__(None, None, None)
                sess.__exit__(None, None, None)
                hr.__exit__(None, None, None)
                cp.__exit__(None, None, None)
        assert captured_ver[0] is not None

    def test_session_reuse(self):
        """One ClientSession opened; stage_extract_article receives it."""
        outer_session = MagicMock()
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=outer_session)
        session_cm.__aexit__ = AsyncMock(return_value=False)

        mock_extract = AsyncMock()
        with _patches():
            sess_p = patch("daily_brief.pipeline.aiohttp.ClientSession", return_value=session_cm)
            ext_p = patch("daily_brief.pipeline.stage_extract_article", mock_extract)
            wr_p = patch("daily_brief.pipeline.write_report")
            sess_p.__enter__()
            ext_p.__enter__()
            wr_p.__enter__()
            try:
                from daily_brief.pipeline import main as pm
                asyncio.get_event_loop().run_until_complete(pm())
            finally:
                wr_p.__exit__(None, None, None)
                ext_p.__exit__(None, None, None)
                sess_p.__exit__(None, None, None)
        mock_extract.assert_called()
        for call in mock_extract.call_args_list:
            assert call[0][1] is outer_session

    def test_preflight_default_disabled(self):
        """Default: preflight checks not called."""
        with _patches():
            mock_check = MagicMock(side_effect=RuntimeError("should not be called"))
            pc = patch("daily_brief.connectivity.run_all_checks", mock_check)
            pc.__enter__()
            try:
                from daily_brief.pipeline import main as pm
                import asyncio
                asyncio.get_event_loop().run_until_complete(pm())
            finally:
                pc.__exit__(None, None, None)

    def test_preflight_enabled(self):
        """When enabled, run_all_checks(timeout=5.0) is called."""
        with _patches():
            mock_check = AsyncMock(return_value=[{"ok": True, "message": "ok", "duration_ms": 10}])
            mock_fmt = MagicMock(return_value="Checks OK")
            pc = patch("daily_brief.pipeline.PREFLIGHT_CHECKS_ENABLED", True)
            cc = patch("daily_brief.connectivity.run_all_checks", mock_check)
            fc = patch("daily_brief.connectivity.format_results", mock_fmt)
            pc.__enter__()
            cc.__enter__()
            fc.__enter__()
            try:
                from daily_brief.pipeline import main as pm
                import asyncio
                asyncio.get_event_loop().run_until_complete(pm())
            finally:
                fc.__exit__(None, None, None)
                cc.__exit__(None, None, None)
                pc.__exit__(None, None, None)
            mock_check.assert_called_once_with(timeout=5.0)
            mock_fmt.assert_called_once()


# ---------------------------------------------------------------------------
# Harness diagnostics (stdout/stderr lines logged to run log)
# ---------------------------------------------------------------------------

class TestHarnessDiagnostics(TestCase):
    def _run_pipeline_with_harness(self, harness_result):
        """Helper: run pipeline with given harness result, return tmpdir."""
        from tests.test_concurrency_contract import _pipeline_patch_group
        tmpdir = tempfile.mkdtemp()
        patches = _pipeline_patch_group(tmpdir)
        hr_p = patch("daily_brief.pipeline.run_test_harness", return_value=harness_result)
        patches.append(hr_p)
        for p in patches:
            p.__enter__()
        try:
            from daily_brief.pipeline import main as pm
            asyncio.get_event_loop().run_until_complete(pm())
        finally:
            for p in reversed(patches):
                p.__exit__(None, None, None)
        return tmpdir

    def _read_log_content(self, tmpdir):
        """Read the run log file content from tmpdir."""
        log_files = sorted(f for f in os.listdir(tmpdir) if f.startswith("run_log_"))
        assert log_files, f"No log files found in {tmpdir}"
        return open(os.path.join(tmpdir, log_files[0])).read()

    def test_fail_harness_logs_stdout_stderr(self):
        """FAIL harness: stdout_lines and stderr_lines logged with [Harness] prefix."""
        from daily_brief.harness import HarnessResult
        from daily_brief.pipeline import EXIT_CODE_VALIDATION
        hr = HarnessResult(
            status="FAIL", message="exit code 2", exit_code=2,
            stdout_lines=["  - [3.7] some finding", "  another line"],
            stderr_lines=["stderr line"],
        )
        tmpdir = self._run_pipeline_with_harness(hr)
        log_content = self._read_log_content(tmpdir)
        self.assertIn("[Harness] ", log_content)
        self.assertIn("[Harness err] stderr line", log_content)

    def test_pass_harness_empty_lines_no_prefix(self):
        """PASS harness with empty stdout/stderr: no prefixed lines logged."""
        from daily_brief.harness import HarnessResult
        hr = HarnessResult(
            status="PASS", message="ok", exit_code=0,
            stdout_lines=[], stderr_lines=[],
        )
        tmpdir = self._run_pipeline_with_harness(hr)
        log_content = self._read_log_content(tmpdir)
        self.assertFalse(any("[Harness] " in line for line in log_content.split("\n")
                              if not line.startswith("[Harness] [Harness]")))
        # With empty lines, no [Harness] prefixed content lines should exist
        harness_lines = [l for l in log_content.split("\n")
                         if "[Harness] " in l]
        self.assertEqual(len(harness_lines), 0)
