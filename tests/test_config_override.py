"""Config override: precedence, explicit-missing failure, runtime rebuild."""

import os
import subprocess
import sys
import textwrap
import tempfile
from pathlib import Path
from unittest import TestCase

_PROJECT = Path(__file__).parent.parent


def _run_python(code: str) -> subprocess.CompletedProcess:
    """Run a Python snippet in a subprocess."""
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(_PROJECT),
        env={**os.environ, "PYTHONPATH": str(_PROJECT)},
    )


def _create_yaml(contents: str) -> str:
    """Write contents to a temp yaml file. Returns absolute path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, dir=str(_PROJECT / "tests")
    )
    f.write(contents)
    f.flush()
    path = f.name
    f.close()
    return path


def _cleanup(path: str) -> None:
    if os.path.exists(path):
        os.unlink(path)


class TestResolverPrecedence(TestCase):
    """Confirm CLI override beats env, beats project/user/packaged."""

    def test_cli_override_wins_over_env(self):
        """CLI --config path must override DAILY_BRIEF_CONFIG env var."""
        env_path = _create_yaml("llm:\n  model: env-model\nruntime:\n  timezone: Europe/London\n")
        cli_path = _create_yaml("llm:\n  model: cli-model\nruntime:\n  timezone: Asia/Tokyo\n")
        try:
            code = f"""\
import os
os.environ["DAILY_BRIEF_CONFIG"] = {env_path!r}
from daily_brief.config import _find_config_path, use_config_path

path = _find_config_path(override={cli_path!r})
assert str(path) == {cli_path!r}, f"Expected cli path but got {{path}}"

use_config_path({cli_path!r})
import daily_brief.config as cfg
assert cfg.LLM_MODEL == "cli-model", f"LLM_MODEL is {{cfg.LLM_MODEL!r}} expected cli-model"
assert cfg.TIMEZONE == "Asia/Tokyo", f"TIMEZONE is {{cfg.TIMEZONE!r}} expected Asia/Tokyo"
print("PRECEDENCE_OK")
"""
            result = _run_python(code)
            self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
            self.assertIn("PRECEDENCE_OK", result.stdout)
        finally:
            _cleanup(env_path)
            _cleanup(cli_path)

    def test_env_beats_project(self):
        """DAILY_BRIEF_CONFIG env var beats project config.yaml."""
        env_path = _create_yaml("llm:\n  model: env-model\nruntime:\n  timezone: Europe/Paris\n")
        try:
            code = f"""\
import os
os.environ["DAILY_BRIEF_CONFIG"] = {env_path!r}
from daily_brief.config import _find_config_path
path = _find_config_path(override=None)
assert str(path) == {env_path!r}, f"Expected env path but got {{path}}"
print("ENV_WINS_OK")
"""
            result = _run_python(code)
            self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
            self.assertIn("ENV_WINS_OK", result.stdout)
        finally:
            _cleanup(env_path)


class TestExplicitMissingConfig(TestCase):
    """Explicit missing config should fail, not degrade silently."""

    def test_use_config_path_raises_on_missing(self):
        """use_config_path() with a nonexistent path raises FileNotFoundError."""
        code = """\
from daily_brief.config import use_config_path
try:
    use_config_path("/nonexistent/config.yaml")
    assert False, "should have raised"
except FileNotFoundError as e:
    assert "/nonexistent/config.yaml" in str(e)
print("MISSING_OK")
"""
        result = _run_python(code)
        self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
        self.assertIn("MISSING_OK", result.stdout)


class TestRuntimeRebuild(TestCase):
    """use_config_path() must rebuild _RUNTIME_CONFIG, not just CONFIG_YAML."""

    def test_runtime_config_refreshes(self):
        """After use_config_path, runtime constants from __getattr__ reflect new config."""
        new_path = _create_yaml(textwrap.dedent("""\
            llm:
              model: override-model
              host: http://override-host:1234/v1
            runtime:
              timezone: Australia/Sydney
              max_log_versions: 10
            weather:
              lat: -33.0
              lon: 151.0
            categories:
              technology:
                query: technology
                max_stories: 5
              economy:
                query: economy
                max_stories: 3
        """))
        try:
            code = f"""\
from daily_brief.config import use_config_path
use_config_path({new_path!r})
import daily_brief.config as cfg

assert cfg.LLM_MODEL == "override-model", f"LLM_MODEL: {{cfg.LLM_MODEL}}"
assert cfg.OLLAMA_HOST == "http://override-host:1234/v1", f"OLLAMA_HOST: {{cfg.OLLAMA_HOST}}"
assert cfg.WEATHER_LAT == -33.0, f"WEATHER_LAT: {{cfg.WEATHER_LAT}}"
assert cfg.MAX_LOG_VERSIONS == 10, f"MAX_LOG_VERSIONS: {{cfg.MAX_LOG_VERSIONS}}"
assert cfg.TIMEZONE == "Australia/Sydney", f"TIMEZONE: {{cfg.TIMEZONE}}"
assert cfg._RUNTIME_CONFIG["LLM_MODEL"] == "override-model"
assert cfg.config_source() == {new_path!r}
assert cfg.config_source() != cfg._DEFAULT_CONFIG_SOURCE
print("REBUILD_OK")
"""
            result = _run_python(code)
            self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
            self.assertIn("REBUILD_OK", result.stdout)
        finally:
            _cleanup(new_path)

    def test_config_source_differs_after_override(self):
        """After override, config_source != _DEFAULT_CONFIG_SOURCE."""
        new_path = _create_yaml("llm:\n  model: x\n")
        try:
            code = f"""\
from daily_brief.config import use_config_path, config_source, _DEFAULT_CONFIG_SOURCE
use_config_path({new_path!r})
assert config_source() == {new_path!r}
assert config_source() != _DEFAULT_CONFIG_SOURCE
print("DIFFERS_OK")
"""
            result = _run_python(code)
            self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
            self.assertIn("DIFFERS_OK", result.stdout)
        finally:
            _cleanup(new_path)


class TestLoadRawConfigPrecedence(TestCase):
    """load_raw_config respects override vs env var."""

    def test_load_raw_config_uses_override_over_env(self):
        """load_raw_config(override) uses override, ignores env var."""
        env_path = _create_yaml("llm:\n  model: env-model\nruntime:\n  timezone: Europe/London\n")
        load_path = _create_yaml("llm:\n  model: load-model\nruntime:\n  timezone: Asia/Tokyo\n")
        try:
            code = f"""\
import os
os.environ["DAILY_BRIEF_CONFIG"] = {env_path!r}
from daily_brief.config import load_raw_config
data = load_raw_config({load_path!r})
assert data["llm"]["model"] == "load-model", f"Expected load-model, got {{data['llm']['model']!r}}"
print("LOAD_RAW_OK")
"""
            result = _run_python(code)
            self.assertEqual(result.returncode, 0, f"stderr: {result.stderr}")
            self.assertIn("LOAD_RAW_OK", result.stdout)
        finally:
            _cleanup(env_path)
            _cleanup(load_path)


if __name__ == "__main__":
    unittest.main()
