"""
Tests for daily_brief/harness.py — run_test_harness subprocess handling.
"""
import os
import subprocess
import tempfile
from unittest import TestCase, mock

from daily_brief.harness import run_test_harness


class TestHarnessEdgeCases(TestCase):
    """Edge cases: missing script, missing/empty logfile, parse failure."""

    def test_script_not_found(self):
        run_test_harness("/tmp/nonexistent_run_log_2026-07-29_v01.md", script_dir="/tmp/nowhere")

    def test_no_logfile_or_empty(self):
        run_test_harness(None, script_dir="/tmp")
        run_test_harness("", script_dir="/tmp")

    def test_parse_failure(self):
        with mock.patch("os.path.exists", return_value=True):
            run_test_harness("/tmp/bad_filename.md", script_dir="/tmp")


class TestHarnessExitCodes(TestCase):
    """Harness handles different subprocess exit codes."""

    def _mock_script_dir(self):
        d = tempfile.mkdtemp()
        config = os.path.join(d, "config.yaml")
        with open(config, "w") as f:
            f.write("{}")
        return d

    def test_pass(self):
        d = self._mock_script_dir()
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stdout = "All checks PASSED\n"
        mock_result.stderr = ""

        with mock.patch("subprocess.run", return_value=mock_result):
            with mock.patch("logging.Logger.info") as mock_log:
                run_test_harness("/tmp/run_log_2026-07-29_v01.md", script_dir=d)
                calls = [str(c) for c in mock_log.call_args_list]
                self.assertTrue(any("PASS" in c for c in calls))

    def test_warn(self):
        d = self._mock_script_dir()
        mock_result = mock.Mock()
        mock_result.returncode = 1
        mock_result.stdout = "Some warnings\n"
        mock_result.stderr = ""

        with mock.patch("subprocess.run", return_value=mock_result):
            with mock.patch("logging.Logger.info") as mock_log:
                run_test_harness("/tmp/run_log_2026-07-29_v01.md", script_dir=d)
                calls = [str(c) for c in mock_log.call_args_list]
                self.assertTrue(any("WARN" in c for c in calls))

    def test_fail(self):
        d = self._mock_script_dir()
        mock_result = mock.Mock()
        mock_result.returncode = 2
        mock_result.stdout = "FAIL: something\n"
        mock_result.stderr = ""

        with mock.patch("subprocess.run", return_value=mock_result):
            with mock.patch("logging.Logger.info") as mock_log:
                run_test_harness("/tmp/run_log_2026-07-29_v01.md", script_dir=d)
                calls = [str(c) for c in mock_log.call_args_list]
                self.assertTrue(any("FAIL" in c for c in calls))


class TestHarnessExceptions(TestCase):
    """Harness handles subprocess exceptions gracefully."""

    def _mock_script_dir(self):
        d = tempfile.mkdtemp()
        config = os.path.join(d, "config.yaml")
        with open(config, "w") as f:
            f.write("{}")
        return d

    def test_timeout(self):
        d = self._mock_script_dir()
        timeout_exc = subprocess.TimeoutExpired(cmd=["python"], timeout=30)

        with mock.patch("subprocess.run", side_effect=timeout_exc):
            with mock.patch("logging.Logger.error") as mock_log:
                run_test_harness("/tmp/run_log_2026-07-29_v01.md", script_dir=d)
                calls = [str(c) for c in mock_log.call_args_list]
                self.assertTrue(
                    any("timed out" in c.lower() or "timeout" in c.lower() for c in calls)
                )

    def test_file_not_found(self):
        d = self._mock_script_dir()

        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            with mock.patch("logging.Logger.error") as mock_log:
                run_test_harness("/tmp/run_log_2026-07-29_v01.md", script_dir=d)
                calls = [str(c) for c in mock_log.call_args_list]
                self.assertTrue(any("not found" in c.lower() for c in calls))


class TestHarnessPreservesOutput(TestCase):
    """HarnessResult preserves stdout_lines and stderr_lines from subprocess."""

    def _mock_script_dir(self):
        d = tempfile.mkdtemp()
        config = os.path.join(d, "config.yaml")
        with open(config, "w") as f:
            f.write("{}")
        return d

    def test_preserves_stdout_stderr_lines(self):
        d = self._mock_script_dir()
        mock_result = mock.Mock()
        mock_result.returncode = 2
        mock_result.stdout = "  - [3.7] finding A\n  another finding B\n"
        mock_result.stderr = "stderr line 1\nstderr line 2\n"

        with mock.patch("subprocess.run", return_value=mock_result):
            result = run_test_harness("/tmp/run_log_2026-07-29_v01.md", script_dir=d)
            self.assertEqual(result.status, "FAIL")
            self.assertEqual(result.exit_code, 2)
            self.assertEqual(result.stdout_lines, ["- [3.7] finding A", "  another finding B"])
            self.assertEqual(result.stderr_lines, ["stderr line 1", "stderr line 2"])

    def test_empty_output_yields_empty_lists(self):
        d = self._mock_script_dir()
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with mock.patch("subprocess.run", return_value=mock_result):
            result = run_test_harness("/tmp/run_log_2026-07-29_v01.md", script_dir=d)
            self.assertEqual(result.stdout_lines, [])
            self.assertEqual(result.stderr_lines, [])


if __name__ == "__main__":
    import unittest
    unittest.main()
