"""
Tier 1 unit tests for config loading, type checks, defaults, and validation.
"""
import os
import re
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest import mock, TestCase

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from daily_brief.config import (
    _get_nested,
    BASE_DIR,
    DEFAULTS,
    load_config_yaml,
    LLM_MODEL,
    OLLAMA_HOST,
    VERSION,
    WEATHER_LAT,
    WEATHER_LON,
    CATEGORIES,
    WEATHER_LAKE_URLS,
    PROMPTS,
)
from daily_brief.config_validator import (
    ConfigValidationError,
    check_required_keys,
    check_types,
    check_ranges,
    check_categories,
    check_lake_urls,
    check_prompts,
    validate_config,
)


# ---------------------------------------------------------------------------
# 1.  Config loading from YAML
# ---------------------------------------------------------------------------

class TestConfigLoading(TestCase):
    """Config loads from YAML file successfully."""

    def test_load_returns_dict(self):
        cfg = load_config_yaml()
        self.assertIsInstance(cfg, dict)

    def test_load_returns_non_empty(self):
        cfg = load_config_yaml()
        self.assertGreater(len(cfg), 0)

    def test_load_version_present(self):
        cfg = load_config_yaml()
        self.assertIn("version", cfg)

    def test_load_llm_section(self):
        cfg = load_config_yaml()
        self.assertIn("llm", cfg)
        llm = cfg["llm"]
        self.assertIsInstance(llm, dict)
        self.assertIn("model", llm)
        self.assertIn("host", llm)

    def test_load_weather_section(self):
        cfg = load_config_yaml()
        self.assertIn("weather", cfg)
        weather = cfg["weather"]
        self.assertIn("lat", weather)
        self.assertIn("lon", weather)

    def test_load_categories_section(self):
        cfg = load_config_yaml()
        self.assertIn("categories", cfg)
        self.assertIsInstance(cfg["categories"], dict)
        self.assertGreater(len(cfg["categories"]), 0)

    def test_load_prompts_section(self):
        cfg = load_config_yaml()
        self.assertIn("prompts", cfg)
        prompts = cfg["prompts"]
        self.assertIn("summary", prompts)
        self.assertIn("system_batch", prompts)


# ---------------------------------------------------------------------------
# 2.  Required top-level keys
# ---------------------------------------------------------------------------

class TestRequiredKeys(TestCase):
    """All required top-level keys exist."""

    def setUp(self):
        self.cfg = load_config_yaml()

    def _check(self, keys):
        for k in keys:
            self.assertIn(k, self.cfg, f"Missing required key: {k}")

    def test_required_top_level_keys(self):
        self._check([
            "version", "llm", "rss", "weather",
            "categories", "prompts", "runtime_defaults",
            "directories", "tagging_config",
        ])

    def test_required_llm_keys(self):
        self._check(["llm"])
        self._check_in(self.cfg["llm"], ["model", "host"])

    def test_required_weather_keys(self):
        self._check(["weather"])
        self._check_in(self.cfg["weather"], ["lat", "lon", "lake_urls"])

    def test_required_directories_keys(self):
        self._check(["directories"])
        self._check_in(self.cfg["directories"], ["log_dir", "news_dir"])

    @staticmethod
    def _check_in(parent, keys):
        for k in keys:
            assert k in parent, f"Missing: {k}"


# ---------------------------------------------------------------------------
# 3.  Type checks
# ---------------------------------------------------------------------------

class TestConfigTypes(TestCase):
    """Critical configuration values have correct types."""

    def test_llm_model_is_str(self):
        self.assertIsInstance(LLM_MODEL, str)
        self.assertGreater(len(LLM_MODEL), 0)

    def test_ollama_host_is_str(self):
        self.assertIsInstance(OLLAMA_HOST, str)
        self.assertTrue(OLLAMA_HOST.startswith("http"))

    def test_version_is_str(self):
        self.assertIsInstance(VERSION, str)
        self.assertGreater(len(VERSION), 0)

    def test_weather_lat_is_float(self):
        self.assertIsInstance(WEATHER_LAT, float)

    def test_weather_lon_is_float(self):
        self.assertIsInstance(WEATHER_LON, float)

    def test_categories_is_list(self):
        self.assertIsInstance(CATEGORIES, list)

    def test_lakes_is_dict(self):
        self.assertIsInstance(WEATHER_LAKE_URLS, dict)
        self.assertGreater(len(WEATHER_LAKE_URLS), 0)

    def test_prompts_is_dict(self):
        self.assertIsInstance(PROMPTS, dict)
        self.assertIn("summary", PROMPTS)


# ---------------------------------------------------------------------------
# 4.  Default values when key missing
# ---------------------------------------------------------------------------

class TestConfigDefaults(TestCase):
    """When a YAML key is absent, the module-level constant falls back to DEFAULTS."""

    def test_nested_get_falls_back(self):
        self.assertIsNone(_get_nested({}, "anything"))
        self.assertEqual(_get_nested({"a": 1}, "a"), 1)
        self.assertIsNone(_get_nested({"a": 1}, "b"))

    def test_nested_deep_get(self):
        data = {"a": {"b": {"c": "deep"}}}
        self.assertEqual(_get_nested(data, "a.b.c"), "deep")

    def test_nested_get_non_dict(self):
        self.assertIsNone(_get_nested("not a dict", "x"))
        self.assertIsNone(_get_nested(42, "x"))

    def test_llm_model_default(self):
        with mock.patch("daily_brief.config.CONFIG_YAML", {}):
            from daily_brief import config as cfg_mod
            orig = cfg_mod.LLM_MODEL
            cfg_mod.LLM_MODEL = cfg_mod._get_nested({}, "llm.model") or DEFAULTS["llm_model"]
            self.assertEqual(cfg_mod.LLM_MODEL, DEFAULTS["llm_model"])
            cfg_mod.LLM_MODEL = orig

    def test_load_missing_file_returns_defaults(self):
        tmpdir = Path(tempfile.mkdtemp())
        with mock.patch("daily_brief.config.BASE_DIR", tmpdir):
            from daily_brief import config as cfg_mod
            result = cfg_mod.load_config_yaml()
            self.assertIsInstance(result, dict)
            self.assertEqual(result, DEFAULTS)


# ---------------------------------------------------------------------------
# 5.  Version parse
# ---------------------------------------------------------------------------

class TestVersionParse(TestCase):
    """Version string matches X.Y.Z semver format."""

    def setUp(self):
        self.cfg = load_config_yaml()

    def test_version_semver_format(self):
        v = self.cfg.get("version", "")
        self.assertRegex(v, r"^\d+\.\d+\.\d+$",
                         f"Version '{v}' does not match X.Y.Z")

    def test_version_parts(self):
        v = self.cfg.get("version", "0.0.0")
        parts = v.split(".")
        self.assertEqual(len(parts), 3)
        for p in parts:
            self.assertIsInstance(int(p), int)

    def test_version_module_constant(self):
        self.assertRegex(VERSION, r"^\d+\.\d+\.\d+$")


# ---------------------------------------------------------------------------
# 6.  Validator — catches invalid configs
# ---------------------------------------------------------------------------

class TestValidatorCatchesInvalid(TestCase):
    """Validator returns issues for malformed config files."""

    # --- Required keys ---

    def test_missing_top_level_key(self):
        issues = check_required_keys({})
        self.assertGreater(len(issues), 0)
        issue_text = "\n".join(issues)
        self.assertIn("version", issue_text)

    def test_missing_llm_model(self):
        issues = check_required_keys({"llm": {"host": "http://x"}})
        msg = "llm.model"
        self.assertTrue(any(msg in i for i in issues), issues)

    def test_missing_prompt(self):
        issues = check_required_keys({"prompts": {"summary": "ok"}})
        self.assertTrue(any("system_batch" in i for i in issues), issues)

    # --- Type checks ---

    def test_bad_llm_model_type(self):
        issues = check_types({"llm": {"model": 123, "host": "http://x"}})
        self.assertTrue(any("llm.model" in i for i in issues))

    def test_bad_llm_host_type(self):
        issues = check_types({"llm": {"model": "ok", "host": 123}})
        self.assertTrue(any("llm.host" in i for i in issues))

    def test_categories_not_dict(self):
        issues = check_types({"categories": "not a dict"})
        self.assertTrue(any("categories" in i for i in issues))

    # --- Range checks ---

    def test_bad_lat(self):
        issues = check_ranges({"weather": {"lat": 999, "lon": 0}})
        self.assertTrue(any("weather.lat" in i for i in issues))

    def test_bad_lon(self):
        issues = check_ranges({"weather": {"lat": 0, "lon": 999}})
        self.assertTrue(any("weather.lon" in i for i in issues))

    def test_bad_llm_host_url(self):
        issues = check_ranges({"llm": {"host": "not-a-url"}})
        self.assertTrue(any("llm.host" in i for i in issues))

    def test_temperature_out_of_range(self):
        issues = check_ranges({
            "llm": {"summary_options": {"temperature": 99}}
        })
        self.assertTrue(any("temperature" in i for i in issues))

    def test_version_not_semver(self):
        issues = check_ranges({"version": "not-semver"})
        self.assertTrue(any("version" in i for i in issues))

    # --- Categories ---

    def test_empty_categories(self):
        issues = check_categories({"categories": {}})
        self.assertGreater(len(issues), 0)

    def test_missing_category_query(self):
        issues = check_categories({
            "categories": {"BadCat": {"max_stories": 5}}
        })
        self.assertTrue(any("query" in i for i in issues))

    def test_negative_max_stories(self):
        issues = check_categories({
            "categories": {"Cat": {"query": "q", "max_stories": -1}}
        })
        self.assertTrue(any("max_stories" in i for i in issues))

    # --- Lake URLs ---

    def test_lake_urls_not_dict(self):
        issues = check_lake_urls({"weather": {"lake_urls": "bad"}})
        self.assertGreater(len(issues), 0)

    def test_empty_lake_url(self):
        issues = check_lake_urls({"weather": {"lake_urls": {"x": ""}}})
        self.assertGreater(len(issues), 0)

    def test_lake_url_not_http(self):
        issues = check_lake_urls({"weather": {"lake_urls": {"x": "ftp://x.com"}}})
        self.assertGreater(len(issues), 0)

    # --- Prompts ---

    def test_prompts_not_dict(self):
        issues = check_prompts({"prompts": "bad"})
        self.assertGreater(len(issues), 0)

    def test_short_prompt(self):
        issues = check_prompts({"prompts": {"summary": "x", "system_batch": "x"}})
        self.assertTrue(any("too short" in i for i in issues))

    # --- Full validation pipeline ---

    def test_validate_config_passes_good_config(self):
        cfg = load_config_yaml()
        passed, issues = validate_config(cfg)
        self.assertTrue(passed, f"Config should pass: {issues}")

    def test_validate_config_fails_empty(self):
        passed, issues = validate_config({})
        self.assertFalse(passed)
        self.assertGreater(len(issues), 0)

    def test_validate_config_catches_multiple_issues(self):
        bad = {
            "version": "bad",
            "llm": {"model": 123, "host": "noturl"},
            "weather": {"lat": 999, "lon": 999, "lake_urls": {"x": ""}},
            "categories": {"BadCat": {"max_stories": 5}},
            "prompts": {"summary": "x"},
        }
        passed, issues = validate_config(bad)
        self.assertFalse(passed)
        self.assertGreater(len(issues), 5)


# ---------------------------------------------------------------------------
# 7.  Integration: config.yaml round-trip
# ---------------------------------------------------------------------------

class TestConfigYAMLRoundtrip(TestCase):
    """Load config from disk, validate it, ensure consistent values."""

    def test_config_yaml_validates_clean(self):
        cfg = load_config_yaml()
        passed, issues = validate_config(cfg)
        if not passed:
            print("Validation issues:", issues)
        self.assertTrue(passed, f"config.yaml has {len(issues)} validation issues")

    def test_all_categories_have_query(self):
        cfg = load_config_yaml()
        for name, cat in cfg["categories"].items():
            self.assertIn("query", cat, f"Category '{name}' missing 'query'")
            self.assertIsInstance(cat["query"], str)

    def test_all_lake_urls_are_http(self):
        cfg = load_config_yaml()
        lakes = cfg.get("weather", {}).get("lake_urls", {})
        for name, url in lakes.items():
            self.assertTrue(
                url.startswith("http"),
                f"Lake '{name}' URL not http: {url}"
            )

    def test_category_priority_entries_exist(self):
        cfg = load_config_yaml()
        cats = set(cfg["categories"].keys())
        for entry in cfg.get("category_priority", []):
            self.assertIn(entry, cats, f"Priority '{entry}' not in categories")
