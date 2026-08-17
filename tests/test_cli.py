"""Reduced: validate and connectivity CLI dispatch."""

import asyncio
import io
import unittest
from unittest import TestCase, mock
from unittest.mock import AsyncMock

from daily_brief.cli import cmd_check_connectivity, cmd_show_prompt, cmd_validate, run

class TestRunDispatch(TestCase):
    def test_run_config_validate(self):
        with mock.patch("daily_brief.cli.cmd_validate", return_value=0) as mock_cmd:
            rv = run(["config", "validate"])
            mock_cmd.assert_called_once()

    def test_run_config_check_connectivity(self):
        with mock.patch("daily_brief.cli.cmd_check_connectivity", return_value=0) as mock_cmd:
            rv = run(["config", "check-connectivity"])
            mock_cmd.assert_called_once()
            self.assertEqual(rv, 0)

    def test_run_pipeline_passthrough(self):
        rv = run([])
        self.assertIsNone(rv)

class TestCmdValidate(TestCase):
    def test_pass_returns_zero(self):
        with mock.patch("daily_brief.cli.validate_config", return_value=(True, [])):
            with mock.patch("builtins.print"):
                rv = cmd_validate()
            self.assertEqual(rv, 0)

    def test_fail_returns_one(self):
        with mock.patch("daily_brief.cli.validate_config", return_value=(False, ["issue1"])):
            with mock.patch("builtins.print"):
                rv = cmd_validate()
            self.assertEqual(rv, 1)

class TestCmdShowPrompt(TestCase):
    def test_existing_prompt(self):
        with mock.patch("builtins.print"):
            rv = cmd_show_prompt("summary")
        self.assertEqual(rv, 0)

class TestCmdCheckConnectivity(TestCase):
    def _run_on_existing_loop(self, coro):
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return loop.create_task(coro)
        return loop.run_until_complete(coro)

    def test_all_pass_returns_zero(self):
        with (
            mock.patch("daily_brief.cli._cmd_check_connectivity_impl", new_callable=AsyncMock, return_value=0),
            mock.patch("asyncio.run", side_effect=self._run_on_existing_loop),
        ):
            rv = cmd_check_connectivity()
        self.assertEqual(rv, 0)

    def test_any_fail_returns_one(self):
        with (
            mock.patch("daily_brief.cli._cmd_check_connectivity_impl", new_callable=AsyncMock, return_value=1),
            mock.patch("asyncio.run", side_effect=self._run_on_existing_loop),
        ):
            rv = cmd_check_connectivity()
        self.assertEqual(rv, 1)

if __name__ == "__main__":
    unittest.main()
