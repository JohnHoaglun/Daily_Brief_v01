"""
Tests for daily_brief/harness.py — run_test_harness subprocess handling.
"""
import os
import subprocess
import tempfile
from unittest import TestCase, mock

from daily_brief.harness import run_test_harness


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestHarnessEdgeCases(TestCase):
    """Edge cases: missing script, missing logfile, parse failure."""

    def test_harness_script_not_found(self):
        run_test_harness("/tmp/nonexistent_run_log_2026-07-29_v01.md", script_dir="/tmp/nowhere")
        # Should not raise, just logs a warning and returns

    def test_harness_no_logfile(self):
        run_test_harness(None, script_dir="/tmp")
        # No logfile set — should return without error

    def test_harness_no_logfile_empty(self):
        run_test_harness("", script_dir="/tmp")
        # Empty string — should return without error

    def test_harness_parse_failure(self):
        with mock.patch("os.path.exists", return_value=True):
            run_test_harness("/tmp/bad_filename.md", script_dir="/tmp")


# ---------------------------------------------------------------------------
# Subprocess exit codes
# ---------------------------------------------------------------------------

class TestHarnessExitCodes(TestCase):
    """Harness handles different subprocess exit codes."""

    def _mock_script_dir(self):
        d = tempfile.mkdtemp()
        config = os.path.join(d, "config.yaml")
        with open(config, "w") as f:
            f.write("{}")
        return d

    def test_harness_pass(self):
        d = self._mock_script_dir()
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stdout = "All checks PASSED\n"
        mock_result.stderr = ""

        with mock.patch("subprocess.run", return_value=mock_result):
            with mock.patch("logging.Logger.info") as mock_log:
                run_test_harness("/tmp/run_log_2026-07-29_v01.md", script_dir=d)
                calls = [str(c) for c in mock_log.call_args_list]
                pass_found = any("PASS" in c for c in calls)
                self.assertTrue(pass_found)

    def test_harness_warn(self):
        d = self._mock_script_dir()
        mock_result = mock.Mock()
        mock_result.returncode = 1
        mock_result.stdout = "Some warnings\n"
        mock_result.stderr = ""

        with mock.patch("subprocess.run", return_value=mock_result):
            with mock.patch("logging.Logger.info") as mock_log:
                run_test_harness("/tmp/run_log_2026-07-29_v01.md", script_dir=d)
                calls = [str(c) for c in mock_log.call_args_list]
                warn_found = any("WARN" in c for c in calls)
                self.assertTrue(warn_found)

    def test_harness_fail(self):
        d = self._mock_script_dir()
        mock_result = mock.Mock()
        mock_result.returncode = 2
        mock_result.stdout = "FAIL: something\n"
        mock_result.stderr = ""

        with mock.patch("subprocess.run", return_value=mock_result):
            with mock.patch("logging.Logger.info") as mock_log:
                run_test_harness("/tmp/run_log_2026-07-29_v01.md", script_dir=d)
                calls = [str(c) for c in mock_log.call_args_list]
                fail_found = any("FAIL" in c for c in calls)
                self.assertTrue(fail_found)


# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------

class TestHarnessExceptions(TestCase):
    """Harness handles subprocess exceptions gracefully."""

    def test_harness_timeout(self):
        d = self._mock_script_dir()
        timeout_exc = subprocess.TimeoutExpired(cmd=["python"], timeout=30)

        with mock.patch("subprocess.run", side_effect=timeout_exc):
            with mock.patch("logging.Logger.error") as mock_log:
                run_test_harness("/tmp/run_log_2026-07-29_v01.md", script_dir=d)
                calls = [str(c) for c in mock_log.call_args_list]
                timeout_found = any("timed out" in c.lower() or "timeout" in c.lower() for c in calls)
                self.assertTrue(timeout_found)

    def test_harness_file_not_found(self):
        d = self._mock_script_dir()

        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            with mock.patch("logging.Logger.error") as mock_log:
                run_test_harness("/tmp/run_log_2026-07-29_v01.md", script_dir=d)
                calls = [str(c) for c in mock_log.call_args_list]
                not_found = any("not found" in c.lower() for c in calls)
                self.assertTrue(not_found)


    def _mock_script_dir(self):
        d = tempfile.mkdtemp()
        config = os.path.join(d, "config.yaml")
        with open(config, "w") as f:
            f.write("{}")
        return d
