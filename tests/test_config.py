"""
Tier 1 unit tests for config loading, type checks, defaults, and validation.
"""
import copy
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
    check_timezone_and_paths,
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


# ---------------------------------------------------------------------------
# 8.  Coverage boost — uncovered branches in config.py
# ---------------------------------------------------------------------------

class TestConfigUncoveredBranches(TestCase):
    """Hit uncovered lines in config.py for 100% coverage."""

    def test_load_malformed_yaml_returns_defaults(self):
        with mock.patch("yaml.safe_load", side_effect=yaml.YAMLError("bad yaml")):
            result = load_config_yaml()
            self.assertEqual(result, DEFAULTS)

    def test_category_age_limits_with_category_settings(self):
        mock_data = {
            "version": "1.0.0",
            "llm": {"model": "x", "host": "http://x", "summary_options": {"temperature": 0.3, "top_p": 0.8}, "alert_options": {"temperature": 0.1, "top_p": 0.3}, "context_preview_chars": 600, "summary_context_chars": 6000, "summary_trim_min_chars": 100},
            "rss": {"base_url": "http://x", "params": "x", "default_age_limit_hours": 24},
            "runtime": {"timezone": "UTC", "thread_pool_size": 1, "max_log_versions": 5},
            "cleanup": {"max_log_versions": 5},
            "directories": {"log_dir": "/tmp/logs", "news_dir": "/tmp/news"},
            "weather": {"lat": 30.0, "lon": -95.0, "wunderground_station_id": "X", "timezone": "America/Chicago", "lake_urls": {"l": "http://x"}},
            "categories": {"world": {"query": "news", "max_stories": 10}},
            "category_settings": {"world": {"boost": 1.5}},
            "category_priority": [],
            "category_boosts": {},
            "tagging_config": {"max_tags": 5, "score_cap": 5.0, "score_threshold": 0.3},
            "tagging_mappings": {"g": ["a"]},
            "tag_conflicts": [],
            "prompts": {"summary": "A" * 30, "system_batch": "B" * 30},
        }
        with mock.patch("daily_brief.config.yaml.safe_load", return_value=mock_data):
            from daily_brief import config as cfg_mod
            import importlib
            importlib.reload(cfg_mod)
            self.assertIn("world", cfg_mod.CATEGORY_AGE_LIMITS)


# ---------------------------------------------------------------------------
# 9.  Helper — get a deep-copied valid config
# ---------------------------------------------------------------------------

def _get_cfg():
    return copy.deepcopy(load_config_yaml())


# ---------------------------------------------------------------------------
# 10.  config_validator — check_types (14 tests)
# ---------------------------------------------------------------------------

class TestCheckTypes(TestCase):
    """check_types catches each wrong type individually."""

    def test_llm_temperature_not_float(self):
        cfg = _get_cfg()
        cfg["llm"]["summary_options"]["temperature"] = "high"
        issues = check_types(cfg)
        self.assertTrue(any("temperature" in i for i in issues))

    def test_llm_top_p_not_float(self):
        cfg = _get_cfg()
        cfg["llm"]["summary_options"]["top_p"] = "one"
        issues = check_types(cfg)
        self.assertTrue(any("top_p" in i for i in issues))

    def test_llm_char_count_not_int(self):
        cfg = _get_cfg()
        cfg["llm"]["context_preview_chars"] = "lots"
        issues = check_types(cfg)
        self.assertTrue(any("context_preview_chars" in i for i in issues))

    def test_weather_lat_not_float(self):
        cfg = _get_cfg()
        cfg["weather"]["lat"] = "forty"
        issues = check_types(cfg)
        self.assertTrue(any("lat" in i for i in issues))

    def test_weather_lon_not_float(self):
        cfg = _get_cfg()
        cfg["weather"]["lon"] = "negative"
        issues = check_types(cfg)
        self.assertTrue(any("lon" in i for i in issues))

    def test_rss_age_limit_not_int(self):
        cfg = _get_cfg()
        if "rss" not in cfg:
            cfg["rss"] = {}
        cfg["rss"]["default_age_limit_hours"] = "24hours"
        issues = check_types(cfg)
        self.assertTrue(any("default_age_limit_hours" in i for i in issues))

    def test_runtime_thread_pool_not_int(self):
        cfg = _get_cfg()
        if "runtime" not in cfg:
            cfg["runtime"] = {}
        cfg["runtime"]["thread_pool_size"] = "many"
        issues = check_types(cfg)
        self.assertTrue(any("thread_pool_size" in i for i in issues))

    def test_runtime_max_log_versions_not_int(self):
        cfg = _get_cfg()
        if "runtime" not in cfg:
            cfg["runtime"] = {}
        cfg["runtime"]["max_log_versions"] = "keep"
        issues = check_types(cfg)
        self.assertTrue(any("max_log_versions" in i for i in issues))

    def test_cleanup_max_log_versions_not_int(self):
        cfg = _get_cfg()
        if "cleanup" not in cfg:
            cfg["cleanup"] = {}
        cfg["cleanup"]["max_log_versions"] = "all"
        issues = check_types(cfg)
        self.assertTrue(any("max_log_versions" in i for i in issues))

    def test_tagging_max_tags_not_int(self):
        cfg = _get_cfg()
        tc = cfg.get("tagging_config", {})
        tc["max_tags"] = "too"
        cfg["tagging_config"] = tc
        issues = check_types(cfg)
        self.assertTrue(any("max_tags" in i for i in issues))

    def test_tagging_score_cap_not_float(self):
        cfg = _get_cfg()
        tc = cfg.get("tagging_config", {})
        tc["score_cap"] = "none"
        cfg["tagging_config"] = tc
        issues = check_types(cfg)
        self.assertTrue(any("score_cap" in i for i in issues))

    def test_tagging_score_threshold_not_float(self):
        cfg = _get_cfg()
        tc = cfg.get("tagging_config", {})
        tc["score_threshold"] = "low"
        cfg["tagging_config"] = tc
        issues = check_types(cfg)
        self.assertTrue(any("score_threshold" in i for i in issues))

    def test_lake_urls_not_dict(self):
        cfg = _get_cfg()
        cfg["weather"]["lake_urls"] = "not_a_dict"
        issues = check_types(cfg)
        self.assertTrue(any("lake_urls" in i for i in issues))

    def test_directories_subkey_missing(self):
        cfg = _get_cfg()
        del cfg["directories"]["log_dir"]
        issues = check_types(cfg)
        self.assertTrue(any("log_dir" in i for i in issues))


# ---------------------------------------------------------------------------
# 11.  config_validator — check_ranges (14 tests)
# ---------------------------------------------------------------------------

class TestCheckRanges(TestCase):
    """check_ranges catches each out-of-range value individually."""

    def test_top_p_out_of_range(self):
        cfg = _get_cfg()
        cfg["llm"]["summary_options"]["top_p"] = 1.5
        issues = check_ranges(cfg)
        self.assertTrue(any("top_p" in i for i in issues))

    def test_char_count_zero(self):
        cfg = _get_cfg()
        cfg["llm"]["context_preview_chars"] = 0
        issues = check_ranges(cfg)
        self.assertTrue(any("context_preview_chars" in i for i in issues))

    def test_rss_hours_out_of_range(self):
        cfg = _get_cfg()
        if "rss" not in cfg:
            cfg["rss"] = {}
        cfg["rss"]["default_age_limit_hours"] = 200
        issues = check_ranges(cfg)
        self.assertTrue(any("default_age_limit_hours" in i for i in issues))

    def test_rss_hours_zero(self):
        cfg = _get_cfg()
        if "rss" not in cfg:
            cfg["rss"] = {}
        cfg["rss"]["default_age_limit_hours"] = 0
        issues = check_ranges(cfg)
        self.assertTrue(any("default_age_limit_hours" in i for i in issues))

    def test_thread_pool_zero(self):
        cfg = _get_cfg()
        if "runtime" not in cfg:
            cfg["runtime"] = {}
        cfg["runtime"]["thread_pool_size"] = 0
        issues = check_ranges(cfg)
        self.assertTrue(any("thread_pool_size" in i for i in issues))

    def test_runtime_max_log_zero(self):
        cfg = _get_cfg()
        if "runtime" not in cfg:
            cfg["runtime"] = {}
        cfg["runtime"]["max_log_versions"] = 0
        issues = check_ranges(cfg)
        self.assertTrue(any("max_log_versions" in i for i in issues))

    def test_cleanup_max_log_zero(self):
        cfg = _get_cfg()
        if "cleanup" not in cfg:
            cfg["cleanup"] = {}
        cfg["cleanup"]["max_log_versions"] = 0
        issues = check_ranges(cfg)
        self.assertTrue(any("max_log_versions" in i for i in issues))

    def test_tagging_max_tags_zero(self):
        cfg = _get_cfg()
        tc = cfg.get("tagging_config", {})
        tc["max_tags"] = 0
        cfg["tagging_config"] = tc
        issues = check_ranges(cfg)
        self.assertTrue(any("max_tags" in i for i in issues))

    def test_tagging_score_cap_zero(self):
        cfg = _get_cfg()
        tc = cfg.get("tagging_config", {})
        tc["score_cap"] = 0
        cfg["tagging_config"] = tc
        issues = check_ranges(cfg)
        self.assertTrue(any("score_cap" in i for i in issues))

    def test_tagging_score_threshold_negative(self):
        cfg = _get_cfg()
        tc = cfg.get("tagging_config", {})
        tc["score_threshold"] = -0.5
        cfg["tagging_config"] = tc
        issues = check_ranges(cfg)
        self.assertTrue(any("score_threshold" in i for i in issues))

    def test_tagging_score_threshold_over_one(self):
        cfg = _get_cfg()
        tc = cfg.get("tagging_config", {})
        tc["score_threshold"] = 1.5
        cfg["tagging_config"] = tc
        issues = check_ranges(cfg)
        self.assertTrue(any("score_threshold" in i for i in issues))

    def test_tagging_mappings_empty(self):
        cfg = _get_cfg()
        tm = cfg.get("tagging_mappings", {})
        tm["group"] = []
        cfg["tagging_mappings"] = tm
        issues = check_ranges(cfg)
        self.assertTrue(any("tagging_mappings" in i for i in issues))

    def test_tag_conflicts_not_list(self):
        cfg = _get_cfg()
        cfg["tag_conflicts"] = "not_a_list"
        issues = check_ranges(cfg)
        self.assertTrue(any("tag_conflicts" in i for i in issues))

    def test_tag_conflicts_bad_pair(self):
        cfg = _get_cfg()
        cfg["tag_conflicts"] = [["single"]]
        issues = check_ranges(cfg)
        self.assertTrue(any("tag_conflicts" in i for i in issues))


# ---------------------------------------------------------------------------
# 12.  config_validator — check_categories (7 tests)
# ---------------------------------------------------------------------------

class TestCheckCategories(TestCase):
    """check_categories catches each category error individually."""

    def test_category_not_dict(self):
        cfg = _get_cfg()
        cats = cfg["categories"]
        first_key = list(cats.keys())[0]
        cfg["categories"] = {first_key: "not_dict"}
        issues = check_categories(cfg)
        self.assertTrue(any("not_dict" not in i and i for i in issues if first_key in i))

    def test_category_max_stories_not_int(self):
        cfg = _get_cfg()
        first_key = list(cfg["categories"].keys())[0]
        cfg["categories"][first_key]["max_stories"] = "ten"
        issues = check_categories(cfg)
        self.assertTrue(any("max_stories" in i for i in issues))

    def test_category_min_age_not_int(self):
        cfg = _get_cfg()
        first_key = list(cfg["categories"].keys())[0]
        cfg["categories"][first_key]["min_age_hours"] = "none"
        issues = check_categories(cfg)
        self.assertTrue(any("min_age_hours" in i for i in issues))

    def test_category_min_age_out_of_range(self):
        cfg = _get_cfg()
        first_key = list(cfg["categories"].keys())[0]
        cfg["categories"][first_key]["min_age_hours"] = 200
        issues = check_categories(cfg)
        self.assertTrue(any("min_age_hours" in i for i in issues))

    def test_category_priority_missing(self):
        cfg = _get_cfg()
        cfg["category_priority"] = ["NONEXISTENT_CAT"]
        issues = check_categories(cfg)
        self.assertTrue(any("NONEXISTENT_CAT" in i for i in issues))

    def test_category_boosts_missing_key(self):
        cfg = _get_cfg()
        cfg["category_boosts"] = {"NONEXISTENT_CAT": ["tag1"]}
        issues = check_categories(cfg)
        self.assertTrue(any("NONEXISTENT_CAT" in i for i in issues))

    def test_category_boosts_empty_list(self):
        cfg = _get_cfg()
        boost_key = list(cfg.get("category_boosts", {}).keys())[0] if cfg.get("category_boosts") else list(cfg["categories"].keys())[0]
        cfg["category_boosts"] = {boost_key: []}
        issues = check_categories(cfg)
        self.assertTrue(any("empty" in i.lower() or "non-empty" in i.lower() for i in issues))


# ---------------------------------------------------------------------------
# 13.  config_validator — other checks (5 tests)
# ---------------------------------------------------------------------------

class TestCheckOther(TestCase):
    """check_timezone_and_paths and validate_config exceptions."""

    def test_invalid_timezone(self):
        cfg = _get_cfg()
        if "runtime" not in cfg:
            cfg["runtime"] = {}
        cfg["runtime"]["timezone"] = "Not/Real"
        issues = check_timezone_and_paths(cfg)
        self.assertTrue(any("timezone" in i for i in issues))

    def test_relative_directory_path(self):
        cfg = _get_cfg()
        cfg["directories"]["log_dir"] = "logs"
        issues = check_timezone_and_paths(cfg)
        self.assertTrue(any("log_dir" in i for i in issues))

    def test_validate_config_exception_caught(self):
        import daily_brief.config_validator as cv
        orig_fn = cv.check_required_keys
        cv.check_required_keys = lambda c: (_ for _ in ()).throw(RuntimeError("boom"))
        cv.CHECK_GROUPS = [(name, fn if fn is not orig_fn else cv.check_required_keys) for name, fn in cv.CHECK_GROUPS]
        try:
            passed, issues = validate_config({"version": "1.0.0", "llm": {"model": "x", "host": "http://x"}, "directories": {"log_dir": "/x", "news_dir": "/x"}, "weather": {"lat": 0, "lon": 0, "wunderground_station_id": "x", "lake_urls": {"l": "http://x"}}, "categories": {"c": {"query": "q"}}, "prompts": {"summary": "A" * 30, "system_batch": "B" * 30}})
        finally:
            cv.check_required_keys = orig_fn
        self.assertFalse(passed)
        self.assertTrue(any("internal error" in i for i in issues))

    def test_category_boosts_not_list(self):
        cfg = _get_cfg()
        boost_key = list(cfg.get("category_boosts", {}).keys())[0] if cfg.get("category_boosts") else list(cfg["categories"].keys())[0]
        cfg["category_boosts"] = {boost_key: "not_list"}
        issues = check_categories(cfg)
        self.assertTrue(any("non-empty" in i.lower() for i in issues))

    def test_tag_conflicts_pair_not_two_strings(self):
        cfg = _get_cfg()
        cfg["tag_conflicts"] = [["a", "b", "c"]]
        issues = check_ranges(cfg)
        self.assertTrue(any("pair" in i for i in issues))
