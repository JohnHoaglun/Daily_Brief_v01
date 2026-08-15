"""Tier 1 unit tests for config loading, builder, and validation."""

import copy
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

from daily_brief.config import (
    CATEGORIES,
    DEFAULTS,
    WEATHER_LAKE_URLS,
    WEATHER_LAT,
    _get_nested,
    build_runtime_config,
    load_config_yaml,
    load_raw_config,
)
from daily_brief.config_validator import (
    check_categories,
    check_lake_urls,
    check_prompts,
    check_ranges,
    check_timezone_and_paths,
    check_types,
    validate_config,
)


def _get_cfg():
    return copy.deepcopy(load_config_yaml())


# ---------------------------------------------------------------------------
# 1.  Raw config loading
# ---------------------------------------------------------------------------


class TestRawConfig(TestCase):
    def test_valid_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("version: 1.2.3\nllm:\n  model: test\n")
            path = f.name
        try:
            self.assertEqual(load_raw_config(path), {"version": "1.2.3", "llm": {"model": "test"}})
        finally:
            os.unlink(path)

    def test_missing_file(self):
        self.assertEqual(load_raw_config("/nonexistent/path.yaml"), {})

    def test_malformed_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("bad: [unterminated")
            path = f.name
        try:
            self.assertEqual(load_raw_config(path), {})
        finally:
            os.unlink(path)

    def test_scalar_yaml_returns_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("just a string\n")
            path = f.name
        try:
            self.assertEqual(load_raw_config(path), {})
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# 2.  Nested getter
# ---------------------------------------------------------------------------


class TestGetNested(TestCase):
    def test_simple(self):
        self.assertEqual(_get_nested({"a": 1}, "a"), 1)
        self.assertIsNone(_get_nested({"a": 1}, "b"))
        self.assertIsNone(_get_nested({}, "anything"))

    def test_deep_and_non_dict(self):
        self.assertEqual(_get_nested({"a": {"b": {"c": "v"}}}, "a.b.c"), "v")
        self.assertIsNone(_get_nested("not a dict", "x"))
        self.assertIsNone(_get_nested(42, "x"))
        self.assertEqual(_get_nested({"a": 1}, "a", "default"), 1)


# ---------------------------------------------------------------------------
# 3.  Runtime builder
# ---------------------------------------------------------------------------


class TestBuildRuntimeConfig(TestCase):
    def _min_cfg(self):
        return {
            "version": "1.0.0",
            "llm": {
                "model": "x",
                "host": "http://x",
                "summary_options": {"temperature": 0.3, "top_p": 0.8},
                "context_preview_chars": 600,
                "summary_context_chars": 6000,
                "summary_trim_min_chars": 100,
            },
            "rss": {"base_url": "http://x", "params": "x", "default_age_limit_hours": 24},
            "runtime": {"timezone": "UTC", "thread_pool_size": 1, "max_log_versions": 5},
            "network": {"user_agent": "UA"},
            "directories": {"log_dir": "/tmp/l", "news_dir": "/tmp/n"},
            "weather": {
                "lat": 30.0,
                "lon": -95.0,
                "wunderground_station_id": "X",
                "lake_urls": {"l": "http://x"},
            },
            "categories": {"news": {"query": "news", "max_stories": 10}},
            "category_priority": [],
            "category_boosts": {},
            "tagging_config": {"max_tags": 5, "score_cap": 5.0, "score_threshold": 0.3},
            "tagging_mappings": {},
            "tag_conflicts": [],
            "prompts": {"summary": "A" * 30, "system_batch": "B" * 30},
        }

    def test_defaults_valid(self):
        runtime = build_runtime_config(_get_cfg())
        self.assertEqual(runtime["WEATHER_LAT"], WEATHER_LAT)
        self.assertEqual(runtime["CATEGORIES"], CATEGORIES)
        self.assertEqual(runtime["WEATHER_LAKE_URLS"], WEATHER_LAKE_URLS)

    def test_overrides(self):
        cfg = self._min_cfg()
        cfg["llm"]["model"] = "custom-model"
        cfg["weather"]["lat"] = 40.0
        r = build_runtime_config(cfg)
        self.assertEqual(r["LLM_MODEL"], "custom-model")
        self.assertEqual(r["WEATHER_LAT"], 40.0)

    def test_bad_numeric_coercion_falls_back(self):
        cfg = self._min_cfg()
        cfg["weather"]["lat"] = "north"
        cfg["runtime"]["max_log_versions"] = "five"
        r = build_runtime_config(cfg)
        self.assertEqual(r["WEATHER_LAT"], DEFAULTS["weather"]["lat"])
        self.assertEqual(r["MAX_LOG_VERSIONS"], DEFAULTS["runtime"]["max_log_versions"])

    def test_category_projection(self):
        cfg = self._min_cfg()
        cfg["categories"] = {"A": {"query": "a", "max_stories": 5}, "B": {"query": "b"}}
        r = build_runtime_config(cfg)
        self.assertEqual(r["CATEGORY_AGE_LIMITS"], {"A": 24, "B": 24})
        self.assertEqual(len(r["CATEGORIES"]), 2)

    def test_retry_backoff_scalar_to_list(self):
        cfg = self._min_cfg()
        cfg["llm"]["summary_retry"] = {"attempts": 3, "backoff": 2.0}
        r = build_runtime_config(cfg)
        self.assertEqual(r["LLM_SUMMARY_RETRY_BACKOFF"], [2.0])

    def test_vault_path_passthrough(self):
        cfg = self._min_cfg()
        cfg["llm"]["host"] = "http://custom:8080/v1"
        r = build_runtime_config(cfg)
        self.assertEqual(r["OLLAMA_HOST"], "http://custom:8080/v1")


# ---------------------------------------------------------------------------
# 4.  Validator scenarios
# ---------------------------------------------------------------------------


class TestValidatorScenarios(TestCase):
    def _bare(self):
        return _get_cfg()

    def test_required_strings(self):
        cfg = self._bare()
        cfg["llm"]["model"] = ""
        issues = check_types(cfg)
        texts = "\n".join(issues)
        self.assertIn("llm.model", texts)

    def test_type_check_float(self):
        cfg = self._bare()
        cfg["weather"]["lat"] = "forty"
        self.assertTrue(any("lat" in i for i in check_types(cfg)))

    def test_type_check_int(self):
        cfg = self._bare()
        cfg["runtime"]["max_log_versions"] = "five"
        self.assertTrue(any("max_log_versions" in i for i in check_types(cfg)))

    def test_type_check_bool(self):
        cfg = self._bare()
        cfg["runtime"]["preflight_checks_enabled"] = "true"
        self.assertTrue(any("preflight_checks_enabled" in i for i in check_types(cfg)))
        cfg["runtime"]["preflight_checks_enabled"] = 1
        self.assertTrue(any("preflight_checks_enabled" in i for i in check_types(cfg)))
        cfg["runtime"]["preflight_checks_enabled"] = True
        self.assertFalse(any("preflight_checks_enabled" in i for i in check_types(cfg)))

    def test_range_check_latlon(self):
        cfg = self._bare()
        cfg["weather"]["lat"] = 999
        self.assertTrue(any("lat" in i for i in check_ranges(cfg)))

    def test_range_check_llm_host(self):
        cfg = self._bare()
        cfg["llm"]["host"] = "not-a-url"
        self.assertTrue(any("llm.host" in i for i in check_ranges(cfg)))

    def test_range_check_temperature(self):
        cfg = self._bare()
        cfg["llm"]["summary_options"]["temperature"] = 99
        self.assertTrue(any("temperature" in i for i in check_ranges(cfg)))

    def test_category_format(self):
        cfg = {"categories": {"BadCat": {"max_stories": 5}}}
        issues = check_categories(cfg)
        self.assertTrue(any("query" in i for i in issues))
        cfg["categories"]["BadCat"]["query"] = "x"
        cfg["categories"]["BadCat"]["max_stories"] = "ten"
        issues = check_categories(cfg)
        self.assertTrue(any("max_stories" in i for i in issues))

    def test_category_priority_missing(self):
        cfg = self._bare()
        cfg["category_priority"] = ["NONEXISTENT"]
        self.assertTrue(any("NONEXISTENT" in i for i in check_categories(cfg)))

    def test_lake_url_format(self):
        issues = check_lake_urls({"weather": {"lake_urls": "bad"}})
        self.assertGreater(len(issues), 0)
        issues = check_lake_urls({"weather": {"lake_urls": {"x": ""}}})
        self.assertGreater(len(issues), 0)
        issues = check_lake_urls({"weather": {"lake_urls": {"x": "ftp://x.com"}}})
        self.assertTrue(any("http" in i for i in issues))

    def test_prompt_non_empty(self):
        issues = check_prompts({"prompts": "bad"})
        self.assertGreater(len(issues), 0)
        issues = check_prompts({"prompts": {"summary": "x", "system_batch": "y"}})
        self.assertTrue(any("too short" in i for i in issues))

    def test_scheduler_range(self):
        cfg = self._bare()
        cfg["llm"]["summary_batch_size"] = 0
        from daily_brief.config_validator import check_batch_scheduler

        self.assertTrue(any("batch_size" in i for i in check_batch_scheduler(cfg)))
        cfg["llm"]["summary_max_concurrency"] = 0
        self.assertTrue(any("concurrency" in i for i in check_batch_scheduler(cfg)))

    def test_timezone_and_directory(self):
        cfg = self._bare()
        cfg["runtime"]["timezone"] = "Not/Real"
        issues = check_timezone_and_paths(cfg)
        self.assertTrue(any("timezone" in i for i in issues))
        cfg["runtime"]["timezone"] = "America/Chicago"
        cfg["directories"]["log_dir"] = "relative"
        issues = check_timezone_and_paths(cfg)
        self.assertTrue(any("log_dir" in i for i in issues))

    def test_full_validation_good_and_bad(self):
        passed, _ = validate_config(_get_cfg())
        self.assertTrue(passed)

        cfg = {**_get_cfg(), "llm": {"summary_options": {"temperature": 5}}}
        passed, issues = validate_config(cfg)
        self.assertFalse(passed)
        self.assertTrue(any("temperature" in i for i in issues))


# ---------------------------------------------------------------------------
# 5.  Checked-in config
# ---------------------------------------------------------------------------


class TestCheckedInConfig(TestCase):
    def test_config_yaml_validates(self):
        cfg = load_config_yaml()
        passed, issues = validate_config(cfg)
        self.assertTrue(passed, f"{len(issues)} issues: {issues}")

    def test_cli_subprocess_validates(self):
        result = subprocess.run(
            [sys.executable, "-m", "daily_brief", "config", "validate"],
            cwd=Path(__file__).resolve().parent.parent,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_cli_malformed_yaml(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("version: 1.0.0\nllm:\n  model: test\nbad: [unterminated")
            path = f.name
        try:
            env = os.environ.copy()
            env["DAILY_BRIEF_CONFIG"] = path
            result = subprocess.run(
                [sys.executable, "-m", "daily_brief", "config", "validate"],
                cwd=Path(__file__).resolve().parent.parent,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            out = result.stdout or result.stderr
            self.assertTrue("error" in out.lower() or result.returncode != 0)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# 6.  Config roundtrip
# ---------------------------------------------------------------------------


class TestConfigRoundtrip(TestCase):
    def test_config_identity(self):
        cfg1 = load_config_yaml()
        cfg2 = load_config_yaml()
        self.assertEqual(cfg1, cfg2)

    def test_runtime_stability(self):
        cfg = _get_cfg()
        r1 = build_runtime_config(cfg)
        r2 = build_runtime_config(cfg)
        self.assertEqual(r1, r2)


# ---------------------------------------------------------------------------
# 7.  Article max concurrency
# ---------------------------------------------------------------------------


class TestArticleMaxConcurrency(TestCase):
    def test_default_is_four(self):
        self.assertEqual(DEFAULTS["runtime"]["article_max_concurrency"], 4)

    def test_typed_coerce_integer(self):
        r = build_runtime_config({"runtime": {"article_max_concurrency": 8}})
        self.assertIsInstance(r["ARTICLE_MAX_CONCURRENCY"], int)
        self.assertEqual(r["ARTICLE_MAX_CONCURRENCY"], 8)

    def test_typed_coerce_string_fallback(self):
        r = build_runtime_config({"runtime": {"article_max_concurrency": "eight"}})
        self.assertEqual(
            r["ARTICLE_MAX_CONCURRENCY"], DEFAULTS["runtime"]["article_max_concurrency"]
        )

    def test_valid_range_config(self):
        for val in (1, 25, 50):
            cfg = {"runtime": {"article_max_concurrency": val}}
            passed, _ = validate_config(cfg)
            # Types and ranges for this key alone — may fail other required keys
            issues = check_types(cfg) + check_ranges(cfg)
            self.assertFalse(
                any("article_max_concurrency" in i for i in issues),
                f"Value {val} should pass validation",
            )

    def test_below_range_config(self):
        cfg = {"runtime": {"article_max_concurrency": 0}}
        issues = check_ranges(cfg)
        self.assertTrue(any("article_max_concurrency" in i for i in issues))

    def test_above_range_config(self):
        cfg = {"runtime": {"article_max_concurrency": 51}}
        issues = check_ranges(cfg)
        self.assertTrue(any("article_max_concurrency" in i for i in issues))

    def test_non_integer_config(self):
        cfg = {"rss": {"candidate_pool_limit": "high"}}
        issues = check_types(cfg)
        self.assertTrue(any("candidate_pool_limit" in i for i in issues))


# ---------------------------------------------------------------------------
# 8.  Candidate pool limits
# ---------------------------------------------------------------------------


class TestCandidatePoolConfig(TestCase):
    def test_global_default(self):
        self.assertEqual(DEFAULTS["rss"]["candidate_pool_limit"], 50)

    def test_typed_coerce_integer(self):
        r = build_runtime_config({"rss": {"candidate_pool_limit": 75}})
        self.assertIsInstance(r["RSS_CANDIDATE_POOL_LIMIT"], int)
        self.assertEqual(r["RSS_CANDIDATE_POOL_LIMIT"], 75)

    def test_typed_coerce_string_fallback(self):
        r = build_runtime_config({"rss": {"candidate_pool_limit": "high"}})
        self.assertEqual(r["RSS_CANDIDATE_POOL_LIMIT"], DEFAULTS["rss"]["candidate_pool_limit"])

    def test_valid_range_config(self):
        for val in (5, 25, 50, 100):
            cfg = {"rss": {"candidate_pool_limit": val}}
            issues = check_ranges(cfg)
            self.assertFalse(
                any("candidate_pool_limit" in i for i in issues),
                f"Value {val} should pass validation",
            )

    def test_below_range_config(self):
        cfg = {"rss": {"candidate_pool_limit": 0}}
        issues = check_ranges(cfg)
        self.assertTrue(any("candidate_pool_limit" in i for i in issues))

    def test_above_range_config(self):
        cfg = {"rss": {"candidate_pool_limit": 501}}
        issues = check_ranges(cfg)
        self.assertTrue(any("candidate_pool_limit" in i for i in issues))

    def test_non_integer_config(self):
        cfg = {"rss": {"candidate_pool_limit": "high"}}
        issues = check_types(cfg)
        self.assertTrue(any("candidate_pool_limit" in i for i in issues))
