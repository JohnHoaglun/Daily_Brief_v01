"""
Tests for src/daily_brief/cli.py — parser building, run(), and subcommands.
"""
import os
import sys
import io
import sys as sysmod
from unittest import TestCase, mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from daily_brief.cli import build_parser, run, cmd_validate, cmd_show, cmd_list_categories, cmd_list_lakes, cmd_show_prompt, cmd_check_connectivity


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------

class TestBuildParser(TestCase):
    """build_parser returns argparse.ArgumentParser with subcommands."""

    def test_build_parser(self):
        import argparse
        parser = build_parser()
        self.assertIsInstance(parser, argparse.ArgumentParser)


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------

class TestRun(TestCase):
    """run() dispatch and passthrough."""

    def test_run_pipeline_passthrough(self):
        rv = run([])
        self.assertIsNone(rv)

    def test_run_config_validate(self):
        with mock.patch("daily_brief.cli.cmd_validate", return_value=0) as mock_cmd:
            rv = run(["config", "validate"])
            mock_cmd.assert_called_once()


# ---------------------------------------------------------------------------
# cmd_validate
# ---------------------------------------------------------------------------

class TestCmdValidate(TestCase):
    """cmd_validate calls validate_config and returns exit code."""

    def test_cmd_validate_pass(self):
        with mock.patch("daily_brief.cli.validate_config", return_value=(True, [])):
            with mock.patch("builtins.print"):
                rv = cmd_validate()
            self.assertEqual(rv, 0)

    def test_cmd_validate_fail(self):
        with mock.patch("daily_brief.cli.validate_config", return_value=(False, ["issue1", "issue2"])):
            with mock.patch("builtins.print"):
                rv = cmd_validate()
            self.assertEqual(rv, 1)


# ---------------------------------------------------------------------------
# cmd_show
# ---------------------------------------------------------------------------

class TestCmdShow(TestCase):
    """cmd_show prints YAML and returns 0."""

    def test_cmd_show(self):
        with mock.patch("builtins.print"):
            rv = cmd_show()
        self.assertEqual(rv, 0)


# ---------------------------------------------------------------------------
# cmd_list_categories
# ---------------------------------------------------------------------------

class TestCmdListCategories(TestCase):
    """cmd_list_categories prints category table."""

    def test_cmd_list_categories(self):
        with mock.patch("builtins.print"):
            rv = cmd_list_categories()
        self.assertEqual(rv, 0)


# ---------------------------------------------------------------------------
# cmd_list_lakes
# ---------------------------------------------------------------------------

class TestCmdListLakes(TestCase):
    """cmd_list_lakes prints lake URLs."""

    def test_cmd_list_lakes(self):
        with mock.patch("builtins.print"):
            rv = cmd_list_lakes()
        self.assertEqual(rv, 0)


# ---------------------------------------------------------------------------
# cmd_show_prompt
# ---------------------------------------------------------------------------

class TestCmdShowPrompt(TestCase):
    """cmd_show_prompt prints prompt or error."""

    def test_cmd_show_prompt_exists(self):
        with mock.patch("builtins.print"):
            rv = cmd_show_prompt("summary")
        self.assertEqual(rv, 0)

    def test_cmd_show_prompt_missing(self):
        old_stderr = sysmod.stderr
        try:
            sysmod.stderr = io.StringIO()
            rv = cmd_show_prompt("nonexistent_prompt_xyz")
        finally:
            sysmod.stderr = old_stderr
        self.assertEqual(rv, 1)


# ---------------------------------------------------------------------------
# cmd_check_connectivity
# ---------------------------------------------------------------------------

class TestCmdCheckConnectivity(TestCase):
    """B.7: check-connectivity dispatch and exit semantics."""

    def test_check_connectivity_all_pass(self):
        """Returns 0 when all probes report ok."""
        with mock.patch("asyncio.run", new=lambda *a, **k: 0):
            with mock.patch("builtins.print"):
                rv = cmd_check_connectivity()
            self.assertEqual(rv, 0)

    def test_check_connectivity_any_fail(self):
        """Returns 1 when any probe fails."""
        with mock.patch("asyncio.run", new=lambda *a, **k: 1):
            with mock.patch("builtins.print"):
                rv = cmd_check_connectivity()
            self.assertEqual(rv, 1)

    def test_run_dispatch_check_connectivity(self):
        """run() dispatches config check-connectivity to cmd_check_connectivity."""
        with mock.patch("daily_brief.cli.cmd_check_connectivity", return_value=0) as mock_cmd:
            rv = run(["config", "check-connectivity"])
            mock_cmd.assert_called_once()
            self.assertEqual(rv, 0)
