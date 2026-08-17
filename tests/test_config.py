"""Config loading, validation — trimmed: raw yaml, runtime defaults, validation pass/fail."""

import os
import tempfile
from copy import deepcopy
from unittest import TestCase

from daily_brief.config import (
    DEFAULTS,
    build_runtime_config,
    load_config_yaml,
    load_raw_config,
)
from daily_brief.config_validator import validate_config

def _get_cfg():
    return deepcopy(load_config_yaml())

class TestRawYamlParse(TestCase):
    def test_raw_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("version: 1.2.3\nllm:\n  model: test\n")
            path = f.name
        try:
            self.assertEqual(load_raw_config(path), {"version": "1.2.3", "llm": {"model": "test"}})
        finally:
            os.unlink(path)
        self.assertEqual(load_raw_config("/nonexistent.yaml"), {})
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("bad: [unterminated")
            p2 = f.name
        try:
            self.assertEqual(load_raw_config(p2), {})
        finally:
            os.unlink(p2)

class TestBuildRuntimeConfig(TestCase):
    def test_defaults_and_overrides(self):
        cfg = deepcopy(load_config_yaml())
        cfg["llm"]["model"] = "custom-x"
        cfg["llm"]["host"] = "http://custom:8080/v1"
        cfg["llm"]["summary_retry"] = {"attempts": 3, "backoff": 2.0}
        cfg["weather"]["lat"] = 40.0
        r = build_runtime_config(cfg)
        self.assertEqual(r["LLM_MODEL"], "custom-x")
        self.assertEqual(r["OLLAMA_HOST"], "http://custom:8080/v1")
        self.assertEqual(r["WEATHER_LAT"], 40.0)
        self.assertEqual(r["LLM_SUMMARY_RETRY_BACKOFF"], [2.0])
        # bad numeric coercion falls back to defaults
        r2 = build_runtime_config({**cfg, "weather": {**cfg["weather"], "lat": "north"}})
        self.assertEqual(r2["WEATHER_LAT"], DEFAULTS["weather"]["lat"])

class TestValidation(TestCase):
    def test_validation_pass(self):
        passed, _ = validate_config(_get_cfg())
        self.assertTrue(passed)

    def test_validation_fail(self):
        cfg = {**_get_cfg(), "llm": {"summary_options": {"temperature": 5}}}
        passed, issues = validate_config(cfg)
        self.assertFalse(passed)
        self.assertTrue(any("temperature" in i for i in issues))

if __name__ == "__main__":
    import unittest
    unittest.main()
